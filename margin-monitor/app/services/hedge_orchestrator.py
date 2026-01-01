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
from app.models.hedge_constants import IndexName, ExpiryType, HEDGE_CONFIG
from app.services.strategy_scheduler import StrategySchedulerService, UpcomingEntry
from app.services.margin_calculator import MarginCalculatorService
from app.services.hedge_selector import HedgeStrikeSelectorService
from app.services.hedge_executor import HedgeExecutorService
from app.services.telegram_service import TelegramService, telegram_service
from app.services.margin_service import MarginService

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
        db: AsyncSession,
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
            db: Database session
            margin_service: Service for getting current margin data
            scheduler: Strategy scheduler service
            margin_calc: Margin calculator service
            hedge_selector: Hedge strike selector service
            hedge_executor: Hedge executor service
            telegram: Telegram notification service
            config: Hedge configuration
        """
        self.db = db
        self.margin_service = margin_service
        self.scheduler = scheduler or StrategySchedulerService(db)
        self.margin_calc = margin_calc or MarginCalculatorService()
        self.hedge_selector = hedge_selector or HedgeStrikeSelectorService()
        self.hedge_executor = hedge_executor or HedgeExecutorService(db)
        self.telegram = telegram or telegram_service
        self.config = config or HEDGE_CONFIG

        self._is_running = False
        self._session: Optional[DailySession] = None
        self._check_interval = 30  # seconds
        self._dry_run = False  # Set to True for paper trading

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

        # Load or create today's session
        self._session = await self._get_or_create_session()

        if not self._session:
            logger.warning("[ORCHESTRATOR] No session for today, auto-hedge not available")
            await self.telegram.send_system_status(
                status="No Session",
                extra_info="⚠️ No trading session configured for today"
            )
            return

        if not self._session.auto_hedge_enabled:
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
            index_name=self._session.index_name,
            num_baskets=self._session.num_baskets,
            total_budget=float(self._session.total_budget)
        )

        logger.info(
            f"[ORCHESTRATOR] Started - {mode} mode, "
            f"index={self._session.index_name}, "
            f"baskets={self._session.num_baskets}"
        )

        # Main monitoring loop
        while self._is_running:
            try:
                # Rollback any stale state before each cycle
                # This prevents accumulated stale connections in long-running loops
                await self.db.rollback()
                await self._check_and_act()
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Error in check cycle: {e}")
                # Clean up on error
                await self.db.rollback()
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

    async def _check_and_act(self):
        """
        Main check cycle - called every 30 seconds.

        1. Skip if outside market hours
        2. Get current margin status
        3. Check if entry is imminent
        4. If yes, evaluate if hedge is needed
        5. If no imminent entry, check if hedges should be exited
        """
        # Only run during market hours
        if not self._is_market_hours():
            return

        if not self._session:
            return

        # Get current margin status
        margin_data = await self._get_current_margin()
        if not margin_data:
            logger.warning("[ORCHESTRATOR] Could not get margin data")
            return

        current_util = margin_data['utilization_pct']
        current_intraday = margin_data['intraday_margin']
        total_budget = float(self._session.total_budget)

        # Check if entry is imminent
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
        num_baskets = self._session.num_baskets

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
        num_baskets = self._session.num_baskets
        expiry_date = self._session.expiry_date.isoformat()

        # Get current short positions to determine hedge side
        positions = await self._get_positions()
        short_positions = [p for p in positions if p.get('quantity', 0) < 0]

        # Select optimal hedges
        selection = await self.hedge_selector.select_optimal_hedges(
            index=index,
            expiry_type=expiry_type,
            margin_reduction_needed=requirement.margin_reduction_needed,
            short_positions=short_positions,
            num_baskets=num_baskets
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
                session_id=self._session.id,
                candidate=hedge,
                index=index,
                expiry_date=expiry_date,
                num_baskets=num_baskets,
                trigger_reason=trigger_reason,
                utilization_before=current_util,
                dry_run=self._dry_run
            )

            if not result.success:
                logger.error(
                    f"[ORCHESTRATOR] Hedge buy failed: {result.error_message}"
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
            self._session.id
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
            session_id=self._session.id,
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

        result = await self.db.execute(
            select(DailySession)
            .where(DailySession.session_date == today)
        )
        session = result.scalar_one_or_none()

        if session:
            logger.info(f"[ORCHESTRATOR] Loaded session for {today}")
            return session

        # No session exists - could create one based on day of week
        # For now, just return None and let the setup API create it
        logger.info(f"[ORCHESTRATOR] No session found for {today}")
        return None

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
        execution = StrategyExecution(
            session_id=self._session.id,
            portfolio_name=portfolio_name,
            scheduled_entry_time=entry_time,
            utilization_before=utilization_before,
            projected_utilization=projected_utilization,
            hedge_required=hedge_required
        )
        self.db.add(execution)
        await self.db.commit()

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

        if self._session:
            active_hedges = await self.hedge_executor.get_active_hedges(
                self._session.id
            )

        return {
            'is_running': self._is_running,
            'dry_run': self._dry_run,
            'session': {
                'date': self._session.session_date.isoformat() if self._session else None,
                'index': self._session.index_name if self._session else None,
                'baskets': self._session.num_baskets if self._session else None,
                'budget': float(self._session.total_budget) if self._session else None,
                'auto_hedge_enabled': self._session.auto_hedge_enabled if self._session else None
            } if self._session else None,
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
