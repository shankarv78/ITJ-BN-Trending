"""
Auto-Hedge System - Orchestrator Service

The main coordination service that:
1. Monitors margin utilization
2. Checks for upcoming strategy entries
3. Triggers hedge buys when needed
4. Triggers hedge exits when safe
5. Runs as a background task during market hours
"""

import logging
import asyncio
from datetime import datetime, date, time, timedelta
from typing import Optional

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hedge_models import DailySession, ActiveHedge, StrategyExecution
from app.models.hedge_constants import IndexName, ExpiryType, HEDGE_CONFIG, LOT_SIZES
from app.services.strategy_scheduler import StrategySchedulerService, UpcomingEntry
from app.services.margin_calculator import MarginCalculatorService
from app.services.hedge_selector import HedgeStrikeSelectorService
from app.services.hedge_executor import HedgeExecutorService
from app.services.telegram_service import TelegramService, telegram_service
from app.services.margin_service import MarginService
from app.services.position_service import position_service

logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')

# Market hours
MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)

# Simulation constants for dry run mode
HEDGE_DIMINISHING_FACTOR = 0.85  # Each additional hedge provides 85% of previous benefit
MAX_SIMULATED_HEDGES = 100  # Maximum tracked simulated hedges (memory limit)


class AutoHedgeOrchestrator:
    """
    Main orchestrator that monitors margin and triggers hedge actions.

    Runs as a background task during market hours, checking every 30 seconds:
    1. Is an entry imminent?
    2. Would that entry breach the budget?
    3. If yes, buy hedges
    4. If utilization is low and no entry soon, consider exiting hedges
    """

    def __init__(
        self,
        db_factory,  # Callable that returns AsyncSession
        margin_service: MarginService = None,
        scheduler: StrategySchedulerService = None,
        margin_calc: MarginCalculatorService = None,
        hedge_selector: HedgeStrikeSelectorService = None,
        hedge_executor: HedgeExecutorService = None,
        telegram: TelegramService = None,
        config = None
    ):
        """
        Initialize the orchestrator.

        Args:
            db_factory: Callable that creates async database sessions
            margin_service: Service for getting current margin data
            scheduler: Strategy scheduler service
            margin_calc: Margin calculator service
            hedge_selector: Hedge strike selector service
            hedge_executor: Hedge executor service
            telegram: Telegram notification service
            config: Hedge configuration
        """
        self.db_factory = db_factory  # Store factory, not session
        self.margin_service = margin_service
        self.scheduler = scheduler
        self.margin_calc = margin_calc or MarginCalculatorService()
        self.hedge_selector = hedge_selector
        self.hedge_executor = hedge_executor
        self.telegram = telegram or telegram_service
        self.config = config or HEDGE_CONFIG

        self._is_running = False
        self._session: Optional[DailySession] = None
        self._session_cache: Optional[dict] = None  # Cached session data to avoid lazy loading
        self._poll_interval = 30  # Lightweight time check every 30 seconds
        self._last_full_check: Optional[datetime] = None
        self._full_check_interval = 300  # Full margin check every 5 mins (for excess hedges)
        self._dry_run = False  # Set to True for paper trading

        # Simulated margin tracking for dry run mode
        # Tracks the cumulative margin benefit from simulated hedges
        self._simulated_margin_reduction: float = 0.0
        self._simulated_hedges: list = []  # Track simulated hedge details
        self._simulated_ce_qty: int = 0  # Track simulated CE hedge quantity
        self._simulated_pe_qty: int = 0  # Track simulated PE hedge quantity

        # Post-entry reactive check tracking
        # Maps entry_time -> scheduled_check_time (entry_time + 60s)
        self._pending_post_entry_checks: dict = {}
        self._post_entry_delay_seconds: int = 60  # Check 1 minute after entry

    def _now_ist(self) -> datetime:
        """Get current time in IST."""
        return datetime.now(IST)

    def _is_market_hours(self) -> bool:
        """Check if currently within market hours."""
        now = self._now_ist()
        current_time = now.time()
        return MARKET_OPEN <= current_time <= MARKET_CLOSE

    async def start(self, dry_run: bool = False):
        """
        Start the auto-hedge monitoring loop.

        Args:
            dry_run: If True, don't place actual orders
        """
        self._is_running = True
        self._dry_run = dry_run

        # Reset simulated margin tracking at start
        self._simulated_margin_reduction = 0.0
        self._simulated_hedges = []
        self._simulated_ce_qty = 0
        self._simulated_pe_qty = 0

        # Load or create today's session (this also populates _session_cache)
        self._session = await self._get_or_create_session()

        # In dry run mode, load existing dry run transactions to initialize simulated margin
        if dry_run and self._session_cache:
            await self._load_existing_dry_run_margin()

        if not self._session_cache:
            logger.warning("[ORCHESTRATOR] No session for today, auto-hedge not available")
            await self.telegram.send_system_status(
                status="No Session",
                extra_info="⚠️ No trading session configured for today"
            )
            return

        if not self._session_cache.get('auto_hedge_enabled', False):
            logger.info("[ORCHESTRATOR] Auto-hedge disabled for today")
            await self.telegram.send_system_status(
                status="Disabled",
                extra_info="ℹ️ Auto-hedge is disabled for today's session"
            )
            return

        # Send startup notification
        mode = "DRY RUN" if dry_run else "LIVE"
        await self.telegram.send_system_status(
            status=f"Started ({mode})",
            index_name=self._session_cache['index'],
            num_baskets=self._session_cache['baskets'],
            total_budget=self._session_cache['budget']
        )

        logger.info(
            f"[ORCHESTRATOR] Started - {mode} mode, "
            f"index={self._session_cache['index']}, "
            f"baskets={self._session_cache['baskets']}"
        )

        # Main monitoring loop - lightweight 30s poll
        while self._is_running:
            try:
                await self._check_and_act()
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Error in check cycle: {e}")
                await self.telegram.send_message(
                    f"❌ *Auto-hedge error:* {str(e)[:100]}"
                )
            finally:
                await asyncio.sleep(self._poll_interval)  # 30 seconds

    async def stop(self):
        """Stop the auto-hedge monitoring loop."""
        self._is_running = False
        logger.info("[ORCHESTRATOR] Stopped")
        await self.telegram.send_system_status(status="Stopped")

    def reset_simulated_margin(self):
        """Reset all simulated margin tracking (for dry run reset)."""
        self._simulated_margin_reduction = 0.0
        self._simulated_hedges = []
        self._simulated_ce_qty = 0
        self._simulated_pe_qty = 0
        logger.info("[ORCHESTRATOR] Reset simulated margin tracking")

    async def _apply_simulated_hedges_to_capacity(self, hedge_capacity: dict) -> dict:
        """
        In dry run mode, add simulated hedge quantities to capacity.
        This ensures we don't buy more hedges than short positions.

        CRITICAL: Queries DB directly for accurate quantities to prevent
        over-buying hedges due to stale in-memory values.
        """
        if not self._dry_run:
            return hedge_capacity

        # Log incoming values BEFORE modification
        broker_ce = hedge_capacity.get('long_ce_qty', 0)
        broker_pe = hedge_capacity.get('long_pe_qty', 0)

        # Query DB for authoritative hedge quantities (not in-memory which can be stale)
        db_ce_qty, db_pe_qty, db_count = await self._get_db_hedge_totals()

        logger.info(
            f"[ORCHESTRATOR] Capacity calculation: "
            f"broker_longs=(CE:{broker_ce}, PE:{broker_pe}), "
            f"db_simulated=(CE:{db_ce_qty}, PE:{db_pe_qty}, count:{db_count})"
        )

        hedge_capacity['long_ce_qty'] += db_ce_qty
        hedge_capacity['long_pe_qty'] += db_pe_qty
        hedge_capacity['remaining_ce_capacity'] = max(
            0, hedge_capacity['short_ce_qty'] - hedge_capacity['long_ce_qty']
        )
        hedge_capacity['remaining_pe_capacity'] = max(
            0, hedge_capacity['short_pe_qty'] - hedge_capacity['long_pe_qty']
        )
        hedge_capacity['is_fully_hedged'] = (
            hedge_capacity['remaining_ce_capacity'] == 0 and
            hedge_capacity['remaining_pe_capacity'] == 0
        )

        logger.info(
            f"[ORCHESTRATOR] Final capacity: "
            f"CE {hedge_capacity['long_ce_qty']}/{hedge_capacity['short_ce_qty']}, "
            f"PE {hedge_capacity['long_pe_qty']}/{hedge_capacity['short_pe_qty']}"
        )

        return hedge_capacity

    async def _check_and_act(self):
        """
        Main check cycle - lightweight 30-second poll.

        Only fetches margin data (API calls) when:
        1. Entry is imminent (within 5 mins) - proactive hedging
        2. Post-entry check is due (1 min after entry) - reactive check
        3. Full periodic check (every 5 mins) - excess hedges, critical util

        This reduces API calls from every 30s to only when needed.
        """
        # Only run during market hours
        if not self._is_market_hours():
            return

        if not self._session:
            return

        now = self._now_ist()
        total_budget = self._session_cache['budget']

        # Determine what checks are needed this cycle
        needs_margin_check = False
        check_reasons = []

        # 1. Check if any post-entry checks are due (1 min after entry)
        has_pending_post_entry = self._has_pending_post_entry_checks(now)
        if has_pending_post_entry:
            needs_margin_check = True
            check_reasons.append("post-entry")

        # 2. Check if entry is imminent (within lookahead window)
        is_imminent, upcoming = await self.scheduler.is_entry_imminent()
        if is_imminent and upcoming:
            needs_margin_check = True
            check_reasons.append(f"pre-entry:{upcoming.entry.portfolio_name}")

        # 3. Check if it's time for a full periodic check (every 5 mins)
        needs_periodic = self._needs_periodic_check(now)
        if needs_periodic:
            needs_margin_check = True
            check_reasons.append("periodic")

        # If no checks needed, just log and return (lightweight poll)
        if not needs_margin_check:
            # Silent poll - no logging to reduce noise
            return

        # Re-check if auto-hedge is still enabled (user may have toggled off)
        if not await self._is_auto_hedge_enabled():
            return

        logger.info(f"[ORCHESTRATOR] Running checks: {', '.join(check_reasons)}")

        # In dry run mode, sync hedge quantities from DB to ensure accuracy
        # This handles cases where in-memory tracking gets out of sync (e.g., restart)
        if self._dry_run:
            db_ce_qty, db_pe_qty, _ = await self._get_db_hedge_totals()
            if db_ce_qty != self._simulated_ce_qty or db_pe_qty != self._simulated_pe_qty:
                logger.info(
                    f"[ORCHESTRATOR] Syncing hedge qty from DB at check cycle: "
                    f"CE {self._simulated_ce_qty} -> {db_ce_qty}, "
                    f"PE {self._simulated_pe_qty} -> {db_pe_qty}"
                )
                self._simulated_ce_qty = db_ce_qty
                self._simulated_pe_qty = db_pe_qty

        # Get current margin status (API call)
        margin_data = await self._get_current_margin()
        if not margin_data:
            logger.warning("[ORCHESTRATOR] Could not get margin data")
            return

        real_util = margin_data['utilization_pct']
        real_intraday = margin_data.get('intraday_margin', 0)

        # In dry run mode, calculate simulated utilization based on COVERAGE
        # SPAN margin gives ~56% reduction when fully hedged (from Sensibull: ₹3.13Cr -> ₹1.37Cr)
        if self._dry_run and (self._simulated_ce_qty > 0 or self._simulated_pe_qty > 0):
            # Get current positions to calculate coverage
            positions = await self._get_positions()
            filtered = position_service.filter_positions(
                positions, self._session_cache['index'], self._session_cache['expiry_date']
            )
            summary = position_service.get_summary(filtered)

            # Calculate coverage percentage for each side
            short_ce = summary.get('short_ce_qty', 0) or 1  # Avoid division by zero
            short_pe = summary.get('short_pe_qty', 0) or 1
            ce_coverage = min(1.0, self._simulated_ce_qty / short_ce)
            pe_coverage = min(1.0, self._simulated_pe_qty / short_pe)

            # Average coverage (weighted by short quantity)
            total_short = short_ce + short_pe
            if total_short > 0:
                avg_coverage = (ce_coverage * short_ce + pe_coverage * short_pe) / total_short
            else:
                avg_coverage = 0

            # SPAN margin reduction: ~56% when fully hedged (SENSEX 0DTE empirical)
            # From Sensibull: ₹3.13Cr -> ₹1.37Cr = 56% reduction at full coverage
            MAX_REDUCTION_PCT = 0.56
            reduction_pct = avg_coverage * MAX_REDUCTION_PCT
            simulated_intraday = real_intraday * (1 - reduction_pct)
            simulated_util = (simulated_intraday / total_budget) * 100 if total_budget > 0 else 0

            # Update stored reduction for status API
            self._simulated_margin_reduction = real_intraday - simulated_intraday

            logger.info(
                f"[ORCHESTRATOR] real_util={real_util:.1f}%, "
                f"simulated_util={simulated_util:.1f}% "
                f"(coverage: CE={ce_coverage:.0%}, PE={pe_coverage:.0%}, avg={avg_coverage:.0%}, "
                f"reduction={reduction_pct:.0%}), intraday=₹{real_intraday:,.0f}"
            )
            current_util = simulated_util
            current_intraday = simulated_intraday
        else:
            current_util = real_util
            current_intraday = real_intraday
            logger.info(f"[ORCHESTRATOR] util={current_util:.1f}%, intraday=₹{current_intraday:,.0f}")

        # Update last full check time
        self._last_full_check = now

        # === RUN CHECKS ===

        # 1. Clear any due post-entry checks (just logs which entries triggered)
        triggered_entries = self._clear_due_post_entry_checks()

        # 2. CHECK EXCESS HEDGES (on periodic checks only)
        if needs_periodic:
            await self._check_excess_hedges(current_util=current_util)

        # 3. REACTIVE HEDGING: Critical utilization (runs on EVERY check)
        # This covers both periodic (every 5 mins) AND post-entry (entry + 1 min)
        critical_threshold = self.config.critical_threshold
        if current_util >= critical_threshold:
            trigger_source = f"post-entry ({', '.join(triggered_entries)})" if triggered_entries else "periodic"
            logger.warning(
                f"[ORCHESTRATOR] CRITICAL ({trigger_source}): "
                f"Utilization {current_util:.1f}% >= {critical_threshold}%!"
            )
            await self._handle_critical_utilization(
                current_util=current_util,
                current_intraday=current_intraday,
                total_budget=total_budget
            )
            return

        # 4. PROACTIVE HEDGING: Entry is imminent
        if is_imminent and upcoming:
            await self._handle_imminent_entry(
                upcoming=upcoming,
                current_util=current_util,
                current_intraday=current_intraday,
                total_budget=total_budget
            )
        elif needs_periodic:
            # Only check hedge exit on periodic checks when idle
            await self._check_hedge_exit(current_util=current_util)

    def _has_pending_post_entry_checks(self, now: datetime) -> bool:
        """Check if any post-entry checks are due."""
        for check_info in self._pending_post_entry_checks.values():
            if now >= check_info['check_time']:
                return True
        return False

    def _needs_periodic_check(self, now: datetime) -> bool:
        """Check if it's time for a full periodic check (every 5 mins)."""
        if self._last_full_check is None:
            return True
        seconds_since_last = (now - self._last_full_check).total_seconds()
        return seconds_since_last >= self._full_check_interval

    async def _handle_imminent_entry(
        self,
        upcoming: UpcomingEntry,
        current_util: float,
        current_intraday: float,
        total_budget: float
    ):
        """
        Handle logic when a strategy entry is imminent.

        1. Calculate margin for next entry
        2. Project utilization after entry
        3. If projected > threshold, buy hedges
        """
        entry = upcoming.entry
        index = IndexName(entry.index_name)
        expiry_type = ExpiryType(entry.expiry_type)
        num_baskets = self._session_cache['baskets']

        # Evaluate hedge requirement
        requirement = self.margin_calc.evaluate_hedge_requirement(
            current_intraday_margin=current_intraday,
            total_budget=total_budget,
            index=index,
            expiry_type=expiry_type,
            num_baskets=num_baskets,
            portfolio_name=entry.portfolio_name
        )

        # Log strategy execution tracking
        await self._log_strategy_execution(
            portfolio_name=entry.portfolio_name,
            entry_time=entry.entry_time,
            utilization_before=current_util,
            projected_utilization=requirement.projected_utilization,
            hedge_required=requirement.is_required
        )

        if requirement.is_required:
            logger.info(
                f"[ORCHESTRATOR] Hedge required for {entry.portfolio_name}: "
                f"{requirement.reason}"
            )
            await self._execute_hedge_entry(
                entry=entry,
                current_util=current_util,
                requirement=requirement,
                current_intraday=current_intraday,
                total_budget=total_budget
            )
        else:
            # Send info alert if close to threshold
            if requirement.projected_utilization > 85:
                await self.telegram.send_entry_imminent_alert(
                    portfolio_name=entry.portfolio_name,
                    seconds_until=upcoming.seconds_until,
                    current_util=current_util,
                    projected_util=requirement.projected_utilization,
                    hedge_required=False
                )

        # Schedule a post-entry reactive check (1 minute after entry)
        # This catches cases where entry causes utilization to spike
        self._schedule_post_entry_check(entry.entry_time, entry.portfolio_name)

    def _schedule_post_entry_check(self, entry_time: time, portfolio_name: str):
        """Schedule a reactive check 1 minute after entry."""
        now = self._now_ist()
        today = now.date()

        # Convert entry time to full datetime
        entry_datetime = datetime.combine(today, entry_time, tzinfo=IST)

        # Only schedule if entry is in the future or just passed
        if entry_datetime < now - timedelta(minutes=5):
            return  # Entry already long past, skip

        # Schedule check for 1 minute after entry
        check_time = entry_datetime + timedelta(seconds=self._post_entry_delay_seconds)

        # Don't duplicate if already scheduled
        key = entry_datetime.isoformat()
        if key not in self._pending_post_entry_checks:
            self._pending_post_entry_checks[key] = {
                'check_time': check_time,
                'portfolio_name': portfolio_name,
                'entry_time': entry_datetime
            }
            logger.info(
                f"[ORCHESTRATOR] Scheduled post-entry check for {portfolio_name} "
                f"at {check_time.strftime('%H:%M:%S')} (1 min after entry)"
            )

    def _clear_due_post_entry_checks(self) -> list:
        """
        Clear post-entry checks that are due and return their portfolio names.

        The actual critical util check is done by the main flow - this just
        marks which entries triggered the check.
        """
        if not self._pending_post_entry_checks:
            return []

        now = self._now_ist()
        completed = []

        for key, check_info in list(self._pending_post_entry_checks.items()):
            if now >= check_info['check_time']:
                portfolio_name = check_info['portfolio_name']
                logger.info(
                    f"[ORCHESTRATOR] Post-entry reactive check triggered for {portfolio_name}"
                )
                completed.append(portfolio_name)
                del self._pending_post_entry_checks[key]

        return completed

    async def _execute_hedge_entry(
        self,
        entry,
        current_util: float,
        requirement,
        current_intraday: float,
        total_budget: float
    ):
        """Execute hedge buy before strategy entry."""
        index = IndexName(entry.index_name)
        expiry_type = ExpiryType(entry.expiry_type)
        num_baskets = self._session_cache['baskets']
        expiry_date = self._session_cache['expiry_date']

        # Get current positions and calculate hedge capacity
        positions = await self._get_positions()
        short_positions = [p for p in positions if p.get('quantity', 0) < 0]

        # Calculate hedge capacity (how many more hedges can provide benefit)
        filtered = position_service.filter_positions(
            positions, self._session_cache['index'], expiry_date
        )
        summary = position_service.get_summary(filtered)
        hedge_capacity = position_service.get_hedge_capacity(summary)

        # In dry run, add simulated hedges to capacity calculation
        hedge_capacity = await self._apply_simulated_hedges_to_capacity(hedge_capacity)

        logger.info(
            f"[ORCHESTRATOR] Hedge capacity: "
            f"CE {hedge_capacity['long_ce_qty']}/{hedge_capacity['short_ce_qty']}, "
            f"PE {hedge_capacity['long_pe_qty']}/{hedge_capacity['short_pe_qty']}"
            f"{' (incl. simulated)' if self._dry_run else ''}"
        )

        # Check if fully hedged - STOP buying more hedges
        if hedge_capacity['is_fully_hedged']:
            logger.info("[ORCHESTRATOR] Fully hedged - no more hedges needed")
            await self.telegram.send_message(
                f"⚠️ *Cannot add more hedges - fully hedged!*\n\n"
                f"*CE:* {hedge_capacity['long_ce_qty']}/{hedge_capacity['short_ce_qty']}\n"
                f"*PE:* {hedge_capacity['long_pe_qty']}/{hedge_capacity['short_pe_qty']}"
            )
            return

        # Select optimal hedges (EQUAL allocation for proactive hedging)
        # Proactive = before strategy entry, buy CE and PE in equal qty
        selection = await self.hedge_selector.select_optimal_hedges(
            index=index,
            expiry_type=expiry_type,
            margin_reduction_needed=requirement.margin_reduction_needed,
            short_positions=short_positions,
            num_baskets=num_baskets,
            hedge_capacity=hedge_capacity,
            allocation_mode='equal'  # Equal allocation for proactive hedging
        )

        if not selection.selected:
            logger.warning(
                f"[ORCHESTRATOR] No suitable hedge found for "
                f"{entry.portfolio_name}"
            )
            await self.telegram.send_message(
                f"⚠️ *No suitable hedge found!*\n\n"
                f"*Portfolio:* {entry.portfolio_name}\n"
                f"*Projected util:* {requirement.projected_utilization:.1f}%\n"
                f"*Reduction needed:* ₹{requirement.margin_reduction_needed:,.0f}"
            )
            return

        # Execute hedge orders - recheck capacity after each to prevent over-hedging
        lot_size = LOT_SIZES.get_lot_size(index)
        for hedge in selection.selected:
            # CRITICAL: Recheck capacity before each hedge to prevent over-hedging
            # (previous hedge may have filled remaining capacity)
            current_capacity = await self._apply_simulated_hedges_to_capacity(
                position_service.get_hedge_capacity(summary)
            )
            if current_capacity['is_fully_hedged']:
                logger.info("[ORCHESTRATOR] Fully hedged after previous hedge - stopping")
                break

            trigger_reason = f"PRE_STRATEGY:{entry.portfolio_name}"

            # Pre-execution capacity check: verify this hedge won't exceed short qty
            # This guards against positions changing between selection and execution
            hedge_qty = hedge.total_lots * lot_size
            if hedge.option_type == 'CE':
                new_ce_total = self._simulated_ce_qty + hedge_qty
                if new_ce_total > hedge_capacity.get('short_ce_qty', 0):
                    logger.warning(
                        f"[ORCHESTRATOR] Skipping CE hedge - would exceed capacity: "
                        f"{new_ce_total} > {hedge_capacity.get('short_ce_qty', 0)}"
                    )
                    continue
            else:  # PE
                new_pe_total = self._simulated_pe_qty + hedge_qty
                if new_pe_total > hedge_capacity.get('short_pe_qty', 0):
                    logger.warning(
                        f"[ORCHESTRATOR] Skipping PE hedge - would exceed capacity: "
                        f"{new_pe_total} > {hedge_capacity.get('short_pe_qty', 0)}"
                    )
                    continue

            result = await self.hedge_executor.execute_hedge_buy(
                session_id=self._session_cache['id'],
                candidate=hedge,
                index=index,
                expiry_date=expiry_date,
                num_baskets=num_baskets,
                trigger_reason=trigger_reason,
                utilization_before=current_util,
                dry_run=self._dry_run
            )

            if result.success:
                # In dry run mode, track the simulated margin reduction
                if self._dry_run:
                    self._add_simulated_hedge_benefit(hedge, selection)
            else:
                logger.error(
                    f"[ORCHESTRATOR] Hedge buy failed: {result.error_message}"
                )

    async def _handle_critical_utilization(
        self,
        current_util: float,
        current_intraday: float,
        total_budget: float
    ):
        """
        Handle reactive hedging when utilization is critically high.

        This is different from proactive hedging - we hedge immediately
        to bring utilization down, regardless of upcoming entries.
        """
        index = IndexName(self._session_cache['index'])
        num_baskets = self._session_cache['baskets']
        expiry_date = self._session_cache['expiry_date']

        # Calculate how much margin reduction we need
        target_util = self.config.hedge_threshold  # e.g. 85%
        margin_reduction_needed = current_intraday - (total_budget * target_util / 100)

        if margin_reduction_needed <= 0:
            logger.info("[ORCHESTRATOR] No margin reduction needed")
            return

        logger.warning(
            f"[ORCHESTRATOR] Reactive hedge needed: "
            f"current={current_util:.1f}%, target={target_util}%, "
            f"reduction_needed=₹{margin_reduction_needed:,.0f}"
        )

        # Send alert
        await self.telegram.send_message(
            f"🚨 *CRITICAL UTILIZATION: {current_util:.1f}%*\n\n"
            f"*Target:* {target_util}%\n"
            f"*Margin reduction needed:* ₹{margin_reduction_needed:,.0f}\n\n"
            f"{'📝 DRY RUN - Simulating hedge...' if self._dry_run else '⚡ Placing hedge order...'}"
        )

        # Get current positions and calculate hedge capacity
        positions = await self._get_positions()
        short_positions = [p for p in positions if p.get('quantity', 0) < 0]
        expiry_date = self._session_cache['expiry_date']

        # Calculate hedge capacity (how many more hedges can provide benefit)
        filtered = position_service.filter_positions(
            positions, self._session_cache['index'], expiry_date
        )
        summary = position_service.get_summary(filtered)
        hedge_capacity = position_service.get_hedge_capacity(summary)

        # In dry run, add simulated hedges to capacity calculation
        hedge_capacity = await self._apply_simulated_hedges_to_capacity(hedge_capacity)

        logger.info(
            f"[ORCHESTRATOR] Hedge capacity: "
            f"CE {hedge_capacity['long_ce_qty']}/{hedge_capacity['short_ce_qty']}, "
            f"PE {hedge_capacity['long_pe_qty']}/{hedge_capacity['short_pe_qty']}"
            f"{' (incl. simulated)' if self._dry_run else ''}"
        )

        # Check if fully hedged - STOP buying more hedges
        if hedge_capacity['is_fully_hedged']:
            await self.telegram.send_message(
                f"⚠️ *Cannot add more hedges - fully hedged!*\n\n"
                f"*Current util:* {current_util:.1f}%\n"
                f"*CE:* {hedge_capacity['long_ce_qty']}/{hedge_capacity['short_ce_qty']}\n"
                f"*PE:* {hedge_capacity['long_pe_qty']}/{hedge_capacity['short_pe_qty']}\n\n"
                f"No more margin benefit possible from hedges."
            )
            return

        # Select optimal hedges (PROPORTIONAL allocation for reactive hedging)
        # Reactive = critical utilization, allocate based on exposure ratio
        selection = await self.hedge_selector.select_optimal_hedges(
            index=index,
            expiry_type=ExpiryType(self._session_cache.get('expiry_type', '2DTE')),
            margin_reduction_needed=margin_reduction_needed,
            short_positions=short_positions,
            num_baskets=num_baskets,
            hedge_capacity=hedge_capacity,
            allocation_mode='proportional'  # Proportional for reactive hedging
        )

        if not selection or not selection.selected:
            logger.warning("[ORCHESTRATOR] No suitable hedge found for critical utilization")
            await self.telegram.send_message(
                f"⚠️ *No suitable hedge found!*\n\n"
                f"*Current util:* {current_util:.1f}%\n"
                f"*Reduction needed:* ₹{margin_reduction_needed:,.0f}\n\n"
                f"Manual intervention may be required."
            )
            return

        # Execute hedge orders - recheck capacity after each to prevent over-hedging
        lot_size = LOT_SIZES.get_lot_size(index)
        for hedge in selection.selected:
            # CRITICAL: Recheck capacity before each hedge to prevent over-hedging
            # (previous hedge may have filled remaining capacity)
            current_capacity = await self._apply_simulated_hedges_to_capacity(
                position_service.get_hedge_capacity(summary)
            )
            if current_capacity['is_fully_hedged']:
                logger.info("[ORCHESTRATOR] Fully hedged after previous hedge - stopping reactive hedging")
                break

            trigger_reason = f"CRITICAL_UTIL:{current_util:.1f}%"

            # Pre-execution capacity check: verify this hedge won't exceed short qty
            hedge_qty = hedge.total_lots * lot_size
            if hedge.option_type == 'CE':
                new_ce_total = self._simulated_ce_qty + hedge_qty
                if new_ce_total > hedge_capacity.get('short_ce_qty', 0):
                    logger.warning(
                        f"[ORCHESTRATOR] Skipping CE hedge - would exceed capacity: "
                        f"{new_ce_total} > {hedge_capacity.get('short_ce_qty', 0)}"
                    )
                    continue
            else:  # PE
                new_pe_total = self._simulated_pe_qty + hedge_qty
                if new_pe_total > hedge_capacity.get('short_pe_qty', 0):
                    logger.warning(
                        f"[ORCHESTRATOR] Skipping PE hedge - would exceed capacity: "
                        f"{new_pe_total} > {hedge_capacity.get('short_pe_qty', 0)}"
                    )
                    continue

            result = await self.hedge_executor.execute_hedge_buy(
                session_id=self._session_cache['id'],
                candidate=hedge,
                index=index,
                expiry_date=expiry_date,
                num_baskets=num_baskets,
                trigger_reason=trigger_reason,
                utilization_before=current_util,
                dry_run=self._dry_run
            )

            if result.success:
                logger.info(
                    f"[ORCHESTRATOR] Reactive hedge placed: {hedge.strike} {hedge.option_type}"
                )

                # In dry run mode, track the simulated margin reduction
                if self._dry_run:
                    self._add_simulated_hedge_benefit(hedge, selection)
            else:
                logger.error(
                    f"[ORCHESTRATOR] Reactive hedge failed: {result.error_message}"
                )

    async def _check_hedge_exit(self, current_util: float):
        """
        Check if hedges should be exited.

        Only exit if:
        1. Current utilization is below exit threshold
        2. No entry is coming within buffer window
        """
        # Only consider exit if utilization is low
        if not self.margin_calc.should_exit_hedge(current_util):
            return

        # Check if any entry is coming soon
        should_hold, _ = await self.scheduler.should_hold_hedges()

        if should_hold:
            return  # Keep hedges for upcoming entry

        # Get active hedges
        active_hedges = await self.hedge_executor.get_active_hedges(
            self._session_cache['id']
        )

        if not active_hedges:
            return

        # Exit farthest OTM hedge first
        farthest_hedge = active_hedges[0]  # Already sorted by otm_distance desc

        logger.info(
            f"[ORCHESTRATOR] Considering exit for {farthest_hedge.symbol}, "
            f"current_util={current_util:.1f}%"
        )

        result = await self.hedge_executor.execute_hedge_exit(
            hedge_id=farthest_hedge.id,
            session_id=self._session_cache['id'],
            trigger_reason="EXCESS_MARGIN",
            utilization_before=current_util,
            dry_run=self._dry_run
        )

        if not result.success:
            logger.info(
                f"[ORCHESTRATOR] Hedge exit skipped: {result.error_message}"
            )

    async def _check_excess_hedges(self, current_util: float):
        """
        Check if hedge quantity exceeds sold quantity and exit excess hedges.

        When short positions decrease (exits, SL hits), hedges may exceed the
        sold qty. Excess hedges provide NO margin benefit and should be exited
        to recover premium.
        """
        if not self._session_cache:
            return

        index = IndexName(self._session_cache['index'])
        expiry_date = self._session_cache.get('expiry_date')

        if not expiry_date:
            return

        # Get current positions and calculate hedge capacity
        positions = await self._get_positions()
        if not positions:
            return

        filtered = position_service.filter_positions(
            positions, self._session_cache['index'], expiry_date
        )
        summary = position_service.get_summary(filtered)

        # Get current hedge quantities (real positions, not simulated)
        long_ce_qty = summary.get('long_ce_qty', 0)
        long_pe_qty = summary.get('long_pe_qty', 0)
        short_ce_qty = summary.get('short_ce_qty', 0)
        short_pe_qty = summary.get('short_pe_qty', 0)

        # In dry run, use simulated quantities instead
        if self._dry_run:
            long_ce_qty = self._simulated_ce_qty
            long_pe_qty = self._simulated_pe_qty

        # Check for excess hedges
        ce_excess = max(0, long_ce_qty - short_ce_qty)
        pe_excess = max(0, long_pe_qty - short_pe_qty)

        if ce_excess == 0 and pe_excess == 0:
            return  # No excess hedges

        logger.warning(
            f"[ORCHESTRATOR] EXCESS HEDGES DETECTED - "
            f"CE: {long_ce_qty}/{short_ce_qty} (excess: {ce_excess}), "
            f"PE: {long_pe_qty}/{short_pe_qty} (excess: {pe_excess})"
        )

        # Get active hedges to exit
        active_hedges = await self.hedge_executor.get_active_hedges(
            self._session_cache['id']
        )

        if not active_hedges:
            logger.info("[ORCHESTRATOR] No active hedges to exit for excess reduction")
            return

        # Determine which type has excess and exit that type first
        # Exit farthest OTM hedge of the excess type
        target_type = 'CE' if ce_excess > 0 else 'PE'
        excess_qty = ce_excess if target_type == 'CE' else pe_excess

        # Find hedges of the target type, sorted by OTM distance (farthest first)
        target_hedges = [h for h in active_hedges if h.option_type == target_type]

        # Sort by OTM distance descending (farthest first) - ensure correct order after filtering
        target_hedges.sort(key=lambda h: getattr(h, 'otm_distance', 0) or 0, reverse=True)

        if not target_hedges:
            logger.info(f"[ORCHESTRATOR] No active {target_type} hedges to exit")
            return

        # Exit farthest OTM hedge first (will be called again in next loop iteration for more)
        hedge_to_exit = target_hedges[0]
        lot_size = LOT_SIZES.get_lot_size(index)
        hedge_qty = (hedge_to_exit.quantity or 0) if hasattr(hedge_to_exit, 'quantity') else lot_size

        logger.info(
            f"[ORCHESTRATOR] Exiting excess {target_type} hedge: "
            f"{hedge_to_exit.symbol} (qty={hedge_qty}) to reduce excess"
        )

        result = await self.hedge_executor.execute_hedge_exit(
            hedge_id=hedge_to_exit.id,
            session_id=self._session_cache['id'],
            trigger_reason=f"EXCESS_{target_type}:{excess_qty}",
            utilization_before=current_util,
            dry_run=self._dry_run
        )

        if result.success:
            # In dry run, update simulated quantities
            if self._dry_run:
                if target_type == 'CE':
                    self._simulated_ce_qty = max(0, self._simulated_ce_qty - hedge_qty)
                else:
                    self._simulated_pe_qty = max(0, self._simulated_pe_qty - hedge_qty)
                logger.info(
                    f"[ORCHESTRATOR] DRY RUN - Reduced simulated {target_type} qty to "
                    f"{self._simulated_ce_qty if target_type == 'CE' else self._simulated_pe_qty}"
                )

            await self.telegram.send_message(
                f"🔄 *Excess hedge exited*\n\n"
                f"*Symbol:* {hedge_to_exit.symbol}\n"
                f"*Reason:* {target_type} hedge qty exceeded short qty\n"
                f"*Excess:* {excess_qty} qty"
            )
        else:
            logger.error(
                f"[ORCHESTRATOR] Failed to exit excess hedge: {result.error_message}"
            )

    async def _get_or_create_session(self) -> Optional[DailySession]:
        """Get or create today's session."""
        today = self._now_ist().date()

        async with self.db_factory() as db:
            result = await db.execute(
                select(DailySession)
                .where(DailySession.session_date == today)
            )
            session = result.scalar_one_or_none()

            if session:
                logger.info(f"[ORCHESTRATOR] Loaded session for {today}")
                # Cache the session data immediately while we have the db context
                self._session_cache = {
                    'id': session.id,
                    'date': session.session_date.isoformat(),
                    'index': session.index_name,
                    'baskets': session.num_baskets,
                    'budget': float(session.total_budget),
                    'auto_hedge_enabled': session.auto_hedge_enabled,
                    'expiry_date': session.expiry_date.isoformat() if session.expiry_date else None,
                    'expiry_type': session.expiry_type
                }
                return session

        # No session exists - could create one based on day of week
        # For now, just return None and let the setup API create it
        logger.info(f"[ORCHESTRATOR] No session found for {today}")
        return None

    async def _is_auto_hedge_enabled(self) -> bool:
        """
        Check if auto-hedge is currently enabled by refreshing from DB.

        This allows the toggle to work in real-time without restarting the orchestrator.
        """
        if not self._session_cache:
            return False

        session_id = self._session_cache['id']

        async with self.db_factory() as db:
            result = await db.execute(
                select(DailySession.auto_hedge_enabled)
                .where(DailySession.id == session_id)
            )
            enabled = result.scalar_one_or_none()

            if enabled is None:
                logger.warning(f"[ORCHESTRATOR] Session {session_id} not found in DB")
                return False

            # Update cache if changed
            if enabled != self._session_cache.get('auto_hedge_enabled'):
                self._session_cache['auto_hedge_enabled'] = enabled
                status = "ENABLED" if enabled else "DISABLED"
                logger.info(f"[ORCHESTRATOR] Auto-hedge toggled {status}")

            return enabled

    async def _load_existing_dry_run_margin(self):
        """
        Load existing dry run transactions from DB to initialize simulated margin.

        This ensures the simulated margin reduction is accurate even after server restart.

        NOTE: Per NSE SPAN margin system research:
        - Hedge benefits ARE cumulative at portfolio level
        - Each additional hedge progressively reduces portfolio risk
        - HOWEVER, there's a floor: minimum ~25% of baseline margin must remain
        - Diminishing returns apply for far OTM hedges
        """
        from app.models.hedge_models import HedgeTransaction

        session_id = self._session_cache['id']

        async with self.db_factory() as db:
            # Get all dry run BUY transactions for this session
            # Dry run transactions have order_status = 'DRY_RUN'
            result = await db.execute(
                select(HedgeTransaction)
                .where(HedgeTransaction.session_id == session_id)
                .where(HedgeTransaction.action == 'BUY')
                .where(HedgeTransaction.order_status == 'DRY_RUN')
                .order_by(HedgeTransaction.timestamp.desc())
            )
            transactions = result.scalars().all()

            if not transactions:
                logger.info("[ORCHESTRATOR] No existing dry run transactions to load")
                return

            num_transactions = len(transactions)

            # Calculate cumulative benefit with diminishing returns
            # First hedge pair gives full benefit, subsequent hedges give less
            base_benefit_per_hedge = self.margin_calc.estimate_hedge_margin_benefit(
                IndexName(self._session_cache['index']),
                ExpiryType(self._session_cache.get('expiry_type', '2DTE')),
                self._session_cache['baskets']
            ) / 2  # Per individual hedge (CE or PE)

            # Apply diminishing returns: each additional hedge gives reduced benefit
            # This models SPAN's portfolio-level calculation where far OTM hedges help less
            total_benefit = 0.0
            diminishing_factor = 1.0
            for i in range(num_transactions):
                benefit = base_benefit_per_hedge * diminishing_factor
                total_benefit += benefit
                diminishing_factor *= HEDGE_DIMINISHING_FACTOR  # Unified constant

            # Apply floor: cannot reduce margin below 25% of baseline (SEBI requirement)
            # Max reduction = 75% of intraday margin
            max_reduction = self._session_cache['budget'] * 0.75
            self._simulated_margin_reduction = min(total_benefit, max_reduction)

            # Load ALL transactions and track CE/PE quantities
            ce_count = 0
            pe_count = 0
            for txn in transactions:
                qty = txn.quantity or 0
                if txn.option_type == 'CE':
                    self._simulated_ce_qty += qty
                    ce_count += 1
                elif txn.option_type == 'PE':
                    self._simulated_pe_qty += qty
                    pe_count += 1

                # Add to simulated hedges list (for all, not just last 10)
                self._simulated_hedges.append({
                    'strike': txn.strike,
                    'option_type': txn.option_type,
                    'quantity': qty,
                    'margin_benefit': base_benefit_per_hedge,
                    'timestamp': txn.timestamp.isoformat() if txn.timestamp else ''
                })

            # Bound list size to prevent memory growth
            if len(self._simulated_hedges) > MAX_SIMULATED_HEDGES:
                self._simulated_hedges = self._simulated_hedges[-MAX_SIMULATED_HEDGES:]

            logger.info(
                f"[ORCHESTRATOR] Loaded {num_transactions} dry run transactions "
                f"(CE: {ce_count} hedges/{self._simulated_ce_qty} qty, "
                f"PE: {pe_count} hedges/{self._simulated_pe_qty} qty), "
                f"simulated reduction=₹{self._simulated_margin_reduction:,.0f} "
                f"(max allowed=₹{max_reduction:,.0f}, 75% of budget)"
            )

    def _add_simulated_hedge_benefit(self, hedge, selection):
        """
        Add simulated margin benefit for a dry run hedge with proper SPAN modeling.

        Per NSE SPAN research:
        - Hedge benefits ARE cumulative at portfolio level
        - BUT with diminishing returns (far OTM hedges help less)
        - AND a floor: minimum 25% of baseline must remain (max 75% reduction)

        The diminishing factor (0.85) models how additional hedges at different
        strikes provide progressively less benefit as the portfolio is already
        partially hedged.
        """
        # Base benefit estimate
        estimated_benefit = hedge.estimated_margin_benefit or selection.total_margin_benefit / len(selection.selected)

        # Apply diminishing returns based on existing hedge count
        num_existing = len(self._simulated_hedges)
        diminishing_factor = HEDGE_DIMINISHING_FACTOR ** num_existing  # Unified constant
        adjusted_benefit = estimated_benefit * diminishing_factor

        # Apply floor: cannot reduce margin below 25% of budget (SEBI requirement)
        max_reduction = self._session_cache['budget'] * 0.75
        new_total = self._simulated_margin_reduction + adjusted_benefit

        if new_total > max_reduction:
            # Cap at floor
            actual_benefit = max(0, max_reduction - self._simulated_margin_reduction)
            if actual_benefit <= 0:
                logger.info(
                    f"[ORCHESTRATOR] DRY RUN: At max reduction floor (₹{max_reduction:,.0f}), "
                    f"no additional benefit from {hedge.strike} {hedge.option_type}"
                )
                return
            adjusted_benefit = actual_benefit

        self._simulated_margin_reduction += adjusted_benefit

        # Track quantity by option type
        # HedgeCandidate has total_lots, HedgeTransaction has quantity
        if hasattr(hedge, 'quantity') and hedge.quantity:
            qty = hedge.quantity
        elif hasattr(hedge, 'total_lots') and hedge.total_lots:
            # Calculate quantity from lots * lot_size
            index = IndexName(self._session_cache.get('index', 'NIFTY'))
            lot_size = LOT_SIZES.get_lot_size(index)
            qty = hedge.total_lots * lot_size
        else:
            qty = 0

        if hedge.option_type == 'CE':
            self._simulated_ce_qty += qty
        else:
            self._simulated_pe_qty += qty

        self._simulated_hedges.append({
            'strike': hedge.strike,
            'option_type': hedge.option_type,
            'quantity': qty,
            'margin_benefit': adjusted_benefit,
            'timestamp': self._now_ist().isoformat()
        })

        # Bound list size to prevent memory growth
        if len(self._simulated_hedges) > MAX_SIMULATED_HEDGES:
            self._simulated_hedges = self._simulated_hedges[-MAX_SIMULATED_HEDGES:]

        logger.info(
            f"[ORCHESTRATOR] DRY RUN: Added {hedge.option_type} hedge, "
            f"qty={qty}, benefit=₹{adjusted_benefit:,.0f} "
            f"(total CE={self._simulated_ce_qty}, PE={self._simulated_pe_qty})"
        )

    async def _get_current_margin(self) -> Optional[dict]:
        """
        Get current margin data from margin service.

        CRITICAL: This must return real margin data. Never use fake/hardcoded values
        as they could cause incorrect hedge decisions with ₹50L+ at risk.
        """
        if not self.margin_service:
            logger.critical("[ORCHESTRATOR] No margin service configured!")
            await self.telegram.send_message(
                "❌ *CRITICAL*: Margin service not configured!\n\n"
                "Auto-hedge is disabled until this is resolved."
            )
            return None

        try:
            funds = await self.margin_service.get_current_status()
            if not funds:
                raise ValueError("Empty margin data received")
            return funds
        except Exception as e:
            logger.critical(f"[ORCHESTRATOR] Cannot fetch margin data: {e}")
            await self.telegram.send_message(
                f"❌ *CRITICAL*: Margin service unavailable!\n\n"
                f"Auto-hedge is disabled until resolved.\n\n"
                f"`{str(e)[:100]}`"
            )
            return None  # Fail explicitly, never use hardcoded values

    async def _get_positions(self) -> list:
        """Get current positions."""
        if self.margin_service:
            try:
                return await self.margin_service.get_filtered_positions()
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Error getting positions: {e}")

        return []

    async def _get_db_hedge_totals(self) -> tuple:
        """
        Query database for actual hedge quantity totals.

        This ensures accuracy even if in-memory tracking gets out of sync.

        Returns:
            Tuple of (ce_total_qty, pe_total_qty, total_hedge_count)
        """
        if not self._session_cache:
            return 0, 0, 0

        from app.models.hedge_models import HedgeTransaction
        from sqlalchemy import func, case

        session_id = self._session_cache['id']

        try:
            async with self.db_factory() as db:
                # Sum quantities by option type for DRY_RUN BUY transactions
                result = await db.execute(
                    select(
                        func.coalesce(
                            func.sum(
                                case(
                                    (HedgeTransaction.option_type == 'CE', HedgeTransaction.quantity),
                                    else_=0
                                )
                            ), 0
                        ).label('ce_qty'),
                        func.coalesce(
                            func.sum(
                                case(
                                    (HedgeTransaction.option_type == 'PE', HedgeTransaction.quantity),
                                    else_=0
                                )
                            ), 0
                        ).label('pe_qty'),
                        func.count(HedgeTransaction.id).label('count')
                    )
                    .where(HedgeTransaction.session_id == session_id)
                    .where(HedgeTransaction.action == 'BUY')
                    .where(HedgeTransaction.order_status == 'DRY_RUN')
                )
                row = result.first()

                if row:
                    ce_qty = int(row.ce_qty)
                    pe_qty = int(row.pe_qty)
                    count = int(row.count)
                    logger.debug(
                        f"[ORCHESTRATOR] DB hedge totals for session {session_id}: "
                        f"CE={ce_qty}, PE={pe_qty}, count={count}"
                    )
                    return ce_qty, pe_qty, count

        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Error querying hedge totals: {e}")

        return 0, 0, 0

    async def _log_strategy_execution(
        self,
        portfolio_name: str,
        entry_time: time,
        utilization_before: float,
        projected_utilization: float,
        hedge_required: bool
    ):
        """Log strategy execution tracking."""
        if not self._session_cache:
            logger.warning("[ORCHESTRATOR] Cannot log execution - no session cached")
            return

        async with self.db_factory() as db:
            execution = StrategyExecution(
                session_id=self._session_cache['id'],
                portfolio_name=portfolio_name,
                scheduled_entry_time=entry_time,
                utilization_before=utilization_before,
                projected_utilization=projected_utilization,
                hedge_required=hedge_required
            )
            db.add(execution)
            await db.commit()

    @property
    def is_running(self) -> bool:
        """Check if orchestrator is running."""
        return self._is_running

    @property
    def session(self) -> Optional[DailySession]:
        """Get current session."""
        return self._session

    async def get_status(self) -> dict:
        """Get current orchestrator status."""
        next_entry = await self.scheduler.get_next_entry() if self.scheduler else None
        active_hedges = []

        # Use cached session data to avoid SQLAlchemy lazy loading issues
        session_data = None
        if self._session_cache:
            session_data = self._session_cache
            try:
                active_hedges = await self.hedge_executor.get_active_hedges(
                    session_data['id']
                )
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Could not get active hedges: {e}")

        # Build response with simulated margin info for dry run mode
        response = {
            'is_running': self._is_running,
            'dry_run': self._dry_run,
            'session': session_data,
            'active_hedges': [
                {
                    'id': h.id,
                    'symbol': h.symbol,
                    'strike': h.strike,
                    'option_type': h.option_type,
                    'quantity': h.quantity,
                    'entry_price': float(h.entry_price),
                    'otm_distance': h.otm_distance
                }
                for h in active_hedges
            ],
            'next_entry': {
                'portfolio': next_entry.entry.portfolio_name,
                'portfolio_name': next_entry.entry.portfolio_name,  # Frontend expects this key
                'entry_time': next_entry.entry_datetime.isoformat() if hasattr(next_entry, 'entry_datetime') else next_entry.entry.entry_time.isoformat(),
                'seconds_until': next_entry.seconds_until,
                'minutes_until': max(0, next_entry.seconds_until // 60),  # Frontend expects minutes
                'num_baskets': self._session_cache.get('baskets', 0) if self._session_cache else 0,
                'is_imminent': next_entry.seconds_until <= (self.config.lookahead_minutes * 60)
            } if next_entry else None,
            'cooldown_remaining': self.hedge_executor.get_cooldown_remaining()
        }

        # Add simulated margin info for dry run mode
        if self._dry_run:
            # Get current real margin to calculate utilization comparison
            real_util = 0.0
            simulated_util = 0.0
            real_intraday = 0.0

            try:
                margin_data = await self._get_current_margin()
                if margin_data and self._session_cache:
                    real_util = margin_data.get('utilization_pct', 0)
                    real_intraday = margin_data.get('intraday_margin', 0)
                    total_budget = self._session_cache.get('budget', 1)

                    # Calculate simulated utilization
                    simulated_intraday = real_intraday - self._simulated_margin_reduction
                    simulated_util = (simulated_intraday / total_budget) * 100 if total_budget > 0 else 0
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Could not get margin for status: {e}")

            max_reduction = self._session_cache.get('budget', 0) * 0.75 if self._session_cache else 0

            # Query actual hedge quantities from DB to ensure accuracy
            # (in-memory tracking can get out of sync after restarts)
            db_ce_qty, db_pe_qty, db_hedge_count = await self._get_db_hedge_totals()

            # Update in-memory values to match DB (self-healing)
            if db_ce_qty != self._simulated_ce_qty or db_pe_qty != self._simulated_pe_qty:
                logger.info(
                    f"[ORCHESTRATOR] Syncing hedge qty from DB: "
                    f"CE {self._simulated_ce_qty} -> {db_ce_qty}, "
                    f"PE {self._simulated_pe_qty} -> {db_pe_qty}"
                )
                self._simulated_ce_qty = db_ce_qty
                self._simulated_pe_qty = db_pe_qty

            # Sanity check: if no hedges, no reduction
            hedge_count = db_hedge_count
            total_reduction = self._simulated_margin_reduction if hedge_count > 0 else 0.0

            response['simulated_margin'] = {
                'total_reduction': total_reduction,
                'max_reduction': max_reduction,
                'hedge_count': hedge_count,
                'ce_hedge_count': sum(1 for h in self._simulated_hedges if h.get('option_type') == 'CE'),
                'pe_hedge_count': sum(1 for h in self._simulated_hedges if h.get('option_type') == 'PE'),
                'ce_hedge_qty': db_ce_qty,  # Use DB value for accuracy
                'pe_hedge_qty': db_pe_qty,  # Use DB value for accuracy
                'real_utilization_pct': round(real_util, 1),
                'simulated_utilization_pct': round(simulated_util if hedge_count > 0 else real_util, 1),
                'hedges': self._simulated_hedges[-10:]  # Last 10 simulated hedges
            }

        # Add hedge capacity info (available in both dry run and live mode)
        # Use margin service's position summary (same as main margin monitor)
        try:
            if self._session_cache and self.margin_service:
                # Use margin service's get_position_summary if available
                if hasattr(self.margin_service, 'get_position_summary'):
                    summary = await self.margin_service.get_position_summary()
                    hedge_capacity = position_service.get_hedge_capacity(summary)
                    hedge_capacity = await self._apply_simulated_hedges_to_capacity(hedge_capacity)
                    response['hedge_capacity'] = hedge_capacity
                else:
                    # Fallback to manual filtering
                    positions = await self._get_positions()
                    expiry_date = self._session_cache.get('expiry_date')
                    if positions and expiry_date:
                        filtered = position_service.filter_positions(
                            positions, self._session_cache['index'], expiry_date
                        )
                        summary = position_service.get_summary(filtered)
                        hedge_capacity = position_service.get_hedge_capacity(summary)
                        hedge_capacity = await self._apply_simulated_hedges_to_capacity(hedge_capacity)
                        response['hedge_capacity'] = hedge_capacity

                # Check for over-hedging and add warnings
                if 'hedge_capacity' in response and self._dry_run:
                    hc = response['hedge_capacity']
                    warnings = []
                    if self._simulated_ce_qty > hc.get('short_ce_qty', 0):
                        ce_excess = self._simulated_ce_qty - hc.get('short_ce_qty', 0)
                        warnings.append(
                            f"CE OVER-HEDGED: {self._simulated_ce_qty} hedge qty > "
                            f"{hc.get('short_ce_qty', 0)} short qty (excess: {ce_excess})"
                        )
                        logger.warning(f"[ORCHESTRATOR] {warnings[-1]}")
                    if self._simulated_pe_qty > hc.get('short_pe_qty', 0):
                        pe_excess = self._simulated_pe_qty - hc.get('short_pe_qty', 0)
                        warnings.append(
                            f"PE OVER-HEDGED: {self._simulated_pe_qty} hedge qty > "
                            f"{hc.get('short_pe_qty', 0)} short qty (excess: {pe_excess})"
                        )
                        logger.warning(f"[ORCHESTRATOR] {warnings[-1]}")
                    if warnings:
                        response['over_hedge_warnings'] = warnings
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Could not get hedge capacity for status: {e}")

        return response
