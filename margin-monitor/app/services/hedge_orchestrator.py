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
from datetime import datetime, date, time
from typing import Optional

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hedge_models import DailySession, ActiveHedge, StrategyExecution
from app.models.hedge_constants import IndexName, ExpiryType, HEDGE_CONFIG, LotSizes
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
        self._check_interval = 30  # seconds
        self._dry_run = False  # Set to True for paper trading

        # Simulated margin tracking for dry run mode
        # Tracks the cumulative margin benefit from simulated hedges
        self._simulated_margin_reduction: float = 0.0
        self._simulated_hedges: list = []  # Track simulated hedge details
        self._simulated_ce_qty: int = 0  # Track simulated CE hedge quantity
        self._simulated_pe_qty: int = 0  # Track simulated PE hedge quantity

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

        # Main monitoring loop
        while self._is_running:
            try:
                await self._check_and_act()
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Error in check cycle: {e}")
                await self.telegram.send_message(
                    f"❌ *Auto-hedge error:* {str(e)[:100]}"
                )
            finally:
                await asyncio.sleep(self._check_interval)

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

    def _apply_simulated_hedges_to_capacity(self, hedge_capacity: dict) -> dict:
        """
        In dry run mode, add simulated hedge quantities to capacity.
        This ensures we don't buy more hedges than short positions.
        """
        if not self._dry_run:
            return hedge_capacity

        hedge_capacity['long_ce_qty'] += self._simulated_ce_qty
        hedge_capacity['long_pe_qty'] += self._simulated_pe_qty
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
        return hedge_capacity

    async def _check_and_act(self):
        """
        Main check cycle - called every 30 seconds.

        1. Skip if outside market hours
        2. Check if auto-hedge is still enabled (refresh from DB)
        3. Get current margin status
        4. Check if entry is imminent
        5. If yes, evaluate if hedge is needed
        6. If no imminent entry, check if hedges should be exited
        """
        # Only run during market hours
        if not self._is_market_hours():
            return

        if not self._session:
            return

        # Re-check if auto-hedge is still enabled (user may have toggled off)
        if not await self._is_auto_hedge_enabled():
            return

        # Get current margin status
        margin_data = await self._get_current_margin()
        if not margin_data:
            logger.warning("[ORCHESTRATOR] Could not get margin data")
            return

        real_util = margin_data['utilization_pct']
        real_intraday = margin_data.get('intraday_margin', 0)
        total_budget = self._session_cache['budget']

        # In dry run mode, calculate simulated utilization
        if self._dry_run and self._simulated_margin_reduction > 0:
            simulated_intraday = real_intraday - self._simulated_margin_reduction
            simulated_util = (simulated_intraday / total_budget) * 100 if total_budget > 0 else 0
            logger.info(
                f"[ORCHESTRATOR] Check cycle: real_util={real_util:.1f}%, "
                f"simulated_util={simulated_util:.1f}% "
                f"(simulated reduction=₹{self._simulated_margin_reduction:,.0f}), "
                f"intraday=₹{real_intraday:,.0f}"
            )
            # Use simulated values for decision making in dry run
            current_util = simulated_util
            current_intraday = simulated_intraday
        else:
            current_util = real_util
            current_intraday = real_intraday
            logger.info(f"[ORCHESTRATOR] Check cycle: util={current_util:.1f}%, intraday=₹{current_intraday:,.0f}")

        # REACTIVE HEDGING: If current utilization is critically high, hedge immediately
        critical_threshold = self.config.critical_threshold  # e.g. 95%
        if current_util >= critical_threshold:
            logger.warning(
                f"[ORCHESTRATOR] CRITICAL: Utilization {current_util:.1f}% >= {critical_threshold}% threshold!"
            )
            await self._handle_critical_utilization(
                current_util=current_util,
                current_intraday=current_intraday,
                total_budget=total_budget
            )
            return

        # PROACTIVE HEDGING: Check if entry is imminent
        is_imminent, upcoming = await self.scheduler.is_entry_imminent()

        if is_imminent and upcoming:
            await self._handle_imminent_entry(
                upcoming=upcoming,
                current_util=current_util,
                current_intraday=current_intraday,
                total_budget=total_budget
            )
        else:
            # Check if we should exit hedges
            await self._check_hedge_exit(
                current_util=current_util
            )

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
        hedge_capacity = self._apply_simulated_hedges_to_capacity(hedge_capacity)

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

        # Execute hedge orders
        for hedge in selection.selected:
            trigger_reason = f"PRE_STRATEGY:{entry.portfolio_name}"

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
        hedge_capacity = self._apply_simulated_hedges_to_capacity(hedge_capacity)

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

        # Execute hedge orders
        for hedge in selection.selected:
            trigger_reason = f"CRITICAL_UTIL:{current_util:.1f}%"

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

            # Apply diminishing returns: each additional hedge gives 80% of previous
            # This models SPAN's portfolio-level calculation where far OTM hedges help less
            total_benefit = 0.0
            diminishing_factor = 1.0
            for i in range(num_transactions):
                benefit = base_benefit_per_hedge * diminishing_factor
                total_benefit += benefit
                diminishing_factor *= 0.8  # 80% diminishing per additional hedge

            # Apply floor: cannot reduce margin below 25% of baseline (SEBI requirement)
            # Max reduction = 75% of intraday margin
            max_reduction = self._session_cache['budget'] * 0.75
            self._simulated_margin_reduction = min(total_benefit, max_reduction)

            # Load transactions and track CE/PE quantities
            for txn in transactions:
                qty = txn.quantity or 0
                if txn.option_type == 'CE':
                    self._simulated_ce_qty += qty
                elif txn.option_type == 'PE':
                    self._simulated_pe_qty += qty

            # Load last 10 for display
            for txn in transactions[:10]:
                self._simulated_hedges.append({
                    'strike': txn.strike,
                    'option_type': txn.option_type,
                    'quantity': txn.quantity or 0,
                    'margin_benefit': base_benefit_per_hedge,
                    'timestamp': txn.timestamp.isoformat() if txn.timestamp else ''
                })

            logger.info(
                f"[ORCHESTRATOR] Loaded {num_transactions} dry run transactions, "
                f"CE={self._simulated_ce_qty}, PE={self._simulated_pe_qty}, "
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
        diminishing_factor = 0.85 ** num_existing  # 85% of previous benefit
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
            lot_size = LotSizes.get_lot_size(index)
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
                'entry_time': next_entry.entry.entry_time.isoformat(),
                'seconds_until': next_entry.seconds_until
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

            response['simulated_margin'] = {
                'total_reduction': self._simulated_margin_reduction,
                'max_reduction': max_reduction,
                'hedge_count': len(self._simulated_hedges),
                'ce_hedge_count': sum(1 for h in self._simulated_hedges if h.get('option_type') == 'CE'),
                'pe_hedge_count': sum(1 for h in self._simulated_hedges if h.get('option_type') == 'PE'),
                'ce_hedge_qty': self._simulated_ce_qty,
                'pe_hedge_qty': self._simulated_pe_qty,
                'real_utilization_pct': round(real_util, 1),
                'simulated_utilization_pct': round(simulated_util, 1),
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
                    hedge_capacity = self._apply_simulated_hedges_to_capacity(hedge_capacity)
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
                        hedge_capacity = self._apply_simulated_hedges_to_capacity(hedge_capacity)
                        response['hedge_capacity'] = hedge_capacity
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Could not get hedge capacity for status: {e}")

        return response
