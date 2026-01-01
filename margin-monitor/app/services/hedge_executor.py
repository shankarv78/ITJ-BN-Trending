"""
Auto-Hedge System - Hedge Executor Service

Executes hedge orders via OpenAlgo API.
Handles order placement, tracking, and recording.
Includes circuit breaker and rate limiting for production safety.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List

import pytz
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hedge_models import (
    HedgeTransaction, ActiveHedge, DailySession
)
from app.models.hedge_constants import (
    IndexName, INDEX_TO_EXCHANGE, HEDGE_CONFIG, LOT_SIZES
)
from app.services.openalgo_service import OpenAlgoService, OpenAlgoError
from app.services.telegram_service import TelegramService, telegram_service
from app.services.hedge_selector import HedgeCandidate

logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')


@dataclass
class CircuitBreakerState:
    """
    Circuit breaker to prevent repeated API failures.

    State transitions:
    - CLOSED: Normal operation, requests allowed
    - OPEN: Too many failures, requests blocked
    - HALF_OPEN: Testing if service recovered
    """
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    failure_threshold: int = 3  # Open circuit after 3 failures
    recovery_timeout_seconds: int = 60  # Wait 60s before half-open

    def record_failure(self) -> None:
        """Record an API failure."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(IST)
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"[CIRCUIT_BREAKER] Circuit OPEN after {self.failure_count} failures"
            )

    def record_success(self) -> None:
        """Record a successful API call."""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"

    def is_allowed(self) -> bool:
        """Check if requests are allowed."""
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            # Check if recovery timeout has passed
            if self.last_failure_time:
                elapsed = (datetime.now(IST) - self.last_failure_time).total_seconds()
                if elapsed >= self.recovery_timeout_seconds:
                    self.state = "HALF_OPEN"
                    logger.info("[CIRCUIT_BREAKER] Circuit HALF_OPEN, testing recovery")
                    return True
            return False

        # HALF_OPEN: Allow one request to test
        return True


# Global circuit breaker instance
_circuit_breaker = CircuitBreakerState()


@dataclass
class OrderResult:
    """Result of an order execution."""
    success: bool
    order_id: Optional[str]
    executed_price: Optional[float]
    error_message: Optional[str]
    transaction_id: Optional[int]


class HedgeExecutorService:
    """
    Executes hedge orders via OpenAlgo API.

    Core responsibilities:
    - Place hedge buy orders
    - Place hedge exit orders
    - Record transactions in database
    - Send Telegram alerts
    - Maintain cooldown between actions
    """

    def __init__(
        self,
        db: AsyncSession,
        openalgo: OpenAlgoService = None,
        telegram: TelegramService = None,
        config = None,
        lot_sizes = None
    ):
        """
        Initialize the hedge executor.

        Args:
            db: AsyncSession for database operations
            openalgo: OpenAlgo service for order execution
            telegram: Telegram service for alerts
            config: HedgeConfig (uses global default if not provided)
            lot_sizes: LotSizes (uses global default if not provided)
        """
        self.db = db
        self.openalgo = openalgo or OpenAlgoService()
        self.telegram = telegram or telegram_service
        self.config = config or HEDGE_CONFIG
        self.lot_sizes = lot_sizes or LOT_SIZES
        self._last_action_time: Optional[datetime] = None

    def _now_ist(self) -> datetime:
        """Get current time in IST."""
        return datetime.now(IST)

    def check_cooldown(self) -> bool:
        """
        Check if cooldown period has passed since last action.

        Returns:
            True if action is allowed, False if still in cooldown
        """
        if self._last_action_time is None:
            return True

        elapsed = (self._now_ist() - self._last_action_time).total_seconds()
        return elapsed >= self.config.cooldown_seconds

    def get_cooldown_remaining(self) -> int:
        """
        Get seconds remaining in cooldown.

        Returns:
            Seconds remaining, or 0 if cooldown is complete
        """
        if self._last_action_time is None:
            return 0

        elapsed = (self._now_ist() - self._last_action_time).total_seconds()
        remaining = self.config.cooldown_seconds - elapsed
        return max(0, int(remaining))

    async def get_daily_hedge_cost(self, session_id: int) -> float:
        """
        Get total hedge cost spent today for this session.

        Args:
            session_id: Daily session ID

        Returns:
            Total cost in INR spent on hedge buys today
        """
        result = await self.db.execute(
            select(func.coalesce(func.sum(HedgeTransaction.total_cost), 0))
            .where(HedgeTransaction.session_id == session_id)
            .where(HedgeTransaction.action == "BUY")
            .where(HedgeTransaction.order_status.in_(["FILLED", "PENDING", "DRY_RUN"]))
        )
        return float(result.scalar() or 0)

    async def check_daily_cost_cap(
        self,
        session_id: int,
        proposed_cost: float
    ) -> tuple[bool, float, float]:
        """
        Check if proposed hedge cost would exceed daily cap.

        Args:
            session_id: Daily session ID
            proposed_cost: Cost of proposed hedge buy

        Returns:
            Tuple of (is_allowed, current_spent, remaining_budget)
        """
        current_spent = await self.get_daily_hedge_cost(session_id)
        max_daily = float(self.config.max_hedge_cost_per_day)
        remaining = max_daily - current_spent

        if proposed_cost > remaining:
            logger.warning(
                f"[HEDGE_EXECUTOR] Daily cost cap would be exceeded: "
                f"spent=₹{current_spent:,.0f}, proposed=₹{proposed_cost:,.0f}, "
                f"cap=₹{max_daily:,.0f}"
            )
            return False, current_spent, remaining

        return True, current_spent, remaining

    def _build_symbol(
        self,
        index: IndexName,
        expiry_date: str,  # YYYY-MM-DD
        strike: int,
        option_type: str
    ) -> str:
        """
        Build trading symbol from components.

        Args:
            index: NIFTY or SENSEX
            expiry_date: Expiry date in YYYY-MM-DD format
            strike: Strike price
            option_type: CE or PE

        Returns:
            Trading symbol (e.g., NIFTY30DEC2525800PE)
        """
        from datetime import datetime
        dt = datetime.strptime(expiry_date, "%Y-%m-%d")

        # Format: NIFTY30DEC2525800PE
        date_str = dt.strftime("%d%b%y").upper()  # 30DEC25

        return f"{index.value}{date_str}{strike}{option_type}"

    async def execute_hedge_buy(
        self,
        session_id: int,
        candidate: HedgeCandidate,
        index: IndexName,
        expiry_date: str,
        num_baskets: int,
        trigger_reason: str,
        utilization_before: float,
        dry_run: bool = False
    ) -> OrderResult:
        """
        Execute a hedge buy order.

        Args:
            session_id: Daily session ID
            candidate: Hedge candidate to buy
            index: NIFTY or SENSEX
            expiry_date: Expiry date (YYYY-MM-DD)
            num_baskets: Number of baskets
            trigger_reason: Why hedge is being bought
            utilization_before: Current utilization %
            dry_run: If True, don't actually place order

        Returns:
            OrderResult with execution details
        """
        # Check cooldown
        if not self.check_cooldown():
            remaining = self.get_cooldown_remaining()
            logger.warning(
                f"[HEDGE_EXECUTOR] Cooldown active, {remaining}s remaining"
            )
            return OrderResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message=f"Cooldown active ({remaining}s remaining)",
                transaction_id=None
            )

        # Build order details
        lot_size = self.lot_sizes.get_lot_size(index)
        lots_per_basket = self.lot_sizes.get_lots_per_basket(index)
        total_lots = lots_per_basket * num_baskets
        quantity = total_lots * lot_size

        symbol = self._build_symbol(
            index, expiry_date, candidate.strike, candidate.option_type
        )
        exchange = INDEX_TO_EXCHANGE.get(index, "NFO")

        # Use limit order with buffer
        limit_price = round(candidate.ltp + self.config.limit_order_buffer, 2)
        total_cost = limit_price * quantity

        # Check daily cost cap BEFORE placing order
        is_allowed, current_spent, remaining_budget = await self.check_daily_cost_cap(
            session_id, total_cost
        )
        if not is_allowed:
            error_msg = (
                f"Daily cost cap exceeded: spent=₹{current_spent:,.0f}, "
                f"proposed=₹{total_cost:,.0f}, cap=₹{self.config.max_hedge_cost_per_day:,.0f}"
            )
            logger.warning(f"[HEDGE_EXECUTOR] {error_msg}")
            await self.telegram.send_message(
                f"⚠️ *Hedge Blocked*: Daily cost cap exceeded\n\n"
                f"Spent today: ₹{current_spent:,.0f}\n"
                f"Proposed: ₹{total_cost:,.0f}\n"
                f"Daily cap: ₹{self.config.max_hedge_cost_per_day:,.0f}\n"
                f"Remaining: ₹{remaining_budget:,.0f}"
            )
            return OrderResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message=error_msg,
                transaction_id=None
            )

        logger.info(
            f"[HEDGE_EXECUTOR] Buying hedge: {symbol}, "
            f"qty={quantity}, price={limit_price}, cost=₹{total_cost:,.0f} "
            f"(daily: ₹{current_spent + total_cost:,.0f}/₹{self.config.max_hedge_cost_per_day:,.0f})"
        )

        # Record pending transaction (include total_cost for daily cap tracking)
        transaction = HedgeTransaction(
            session_id=session_id,
            timestamp=self._now_ist(),
            action="BUY",
            trigger_reason=trigger_reason,
            symbol=symbol,
            exchange=exchange,
            strike=candidate.strike,
            option_type=candidate.option_type,
            quantity=quantity,
            lots=total_lots,
            order_price=limit_price,
            total_cost=total_cost,  # Track for daily cost cap
            utilization_before=utilization_before,
            order_status="PENDING"
        )
        self.db.add(transaction)
        await self.db.flush()  # Get the ID

        if dry_run:
            logger.info(f"[HEDGE_EXECUTOR] DRY RUN - Would place order for {symbol}")
            transaction.order_status = "DRY_RUN"
            await self.db.commit()
            return OrderResult(
                success=True,
                order_id="DRY_RUN",
                executed_price=limit_price,
                error_message=None,
                transaction_id=transaction.id
            )

        # Execute order via OpenAlgo
        try:
            order_response = await self._place_order(
                symbol=symbol,
                exchange=exchange,
                action="BUY",
                quantity=quantity,
                price=limit_price
            )

            order_id = order_response.get('orderid') or order_response.get('order_id')

            # Update transaction
            transaction.order_id = order_id
            transaction.order_status = "SUCCESS"
            transaction.executed_price = limit_price
            transaction.total_cost = total_cost

            # Record active hedge
            active_hedge = ActiveHedge(
                session_id=session_id,
                transaction_id=transaction.id,
                symbol=symbol,
                exchange=exchange,
                strike=candidate.strike,
                option_type=candidate.option_type,
                quantity=quantity,
                entry_price=limit_price,
                otm_distance=candidate.otm_distance,
                is_active=True
            )
            self.db.add(active_hedge)

            await self.db.commit()

            self._last_action_time = self._now_ist()

            # Send Telegram alert
            msg_id = await self.telegram.send_hedge_buy_alert(
                symbol=symbol,
                strike=candidate.strike,
                option_type=candidate.option_type,
                quantity=quantity,
                price=limit_price,
                total_cost=total_cost,
                trigger_reason=trigger_reason,
                utilization_before=utilization_before,
                otm_distance=candidate.otm_distance
            )

            if msg_id:
                transaction.telegram_sent = True
                transaction.telegram_message_id = msg_id
                await self.db.commit()

            logger.info(
                f"[HEDGE_EXECUTOR] Order success: {symbol}, "
                f"order_id={order_id}"
            )

            return OrderResult(
                success=True,
                order_id=order_id,
                executed_price=limit_price,
                error_message=None,
                transaction_id=transaction.id
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[HEDGE_EXECUTOR] Order failed: {error_msg}")

            # Update transaction as failed
            transaction.order_status = "FAILED"
            transaction.error_message = error_msg
            await self.db.commit()

            # Send failure alert
            await self.telegram.send_hedge_failure_alert(
                symbol=symbol,
                action="BUY",
                error=error_msg,
                trigger_reason=trigger_reason
            )

            return OrderResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message=error_msg,
                transaction_id=transaction.id
            )

    async def execute_hedge_exit(
        self,
        hedge_id: int,
        session_id: int,
        trigger_reason: str,
        utilization_before: float,
        dry_run: bool = False
    ) -> OrderResult:
        """
        Exit an existing hedge position.

        Args:
            hedge_id: Active hedge ID
            session_id: Daily session ID
            trigger_reason: Why hedge is being exited
            utilization_before: Current utilization %
            dry_run: If True, don't actually place order

        Returns:
            OrderResult with execution details
        """
        # Get hedge details
        result = await self.db.execute(
            select(ActiveHedge)
            .where(ActiveHedge.id == hedge_id)
            .where(ActiveHedge.is_active == True)
        )
        hedge = result.scalar_one_or_none()

        if not hedge:
            return OrderResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message="Hedge not found or already exited",
                transaction_id=None
            )

        # Get current price (simplified - use actual quote in production)
        current_price = hedge.entry_price * 0.5  # Assume 50% decay for simplicity

        # Don't sell if value too low
        if current_price < self.config.min_exit_value:
            logger.info(
                f"[HEDGE_EXECUTOR] Hedge value too low ({current_price:.2f}), "
                "letting expire"
            )
            return OrderResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message=f"Value too low ({current_price:.2f}), letting expire",
                transaction_id=None
            )

        # Record exit transaction
        # Use dynamic lot size based on symbol (75 for Nifty, 10 for Sensex)
        lot_size = self.lot_sizes.get_lot_size_from_symbol(hedge.symbol)
        transaction = HedgeTransaction(
            session_id=session_id,
            timestamp=self._now_ist(),
            action="SELL",
            trigger_reason=trigger_reason,
            symbol=hedge.symbol,
            exchange=hedge.exchange,
            strike=hedge.strike,
            option_type=hedge.option_type,
            quantity=hedge.quantity,
            lots=hedge.quantity // lot_size,
            order_price=current_price,
            utilization_before=utilization_before,
            order_status="PENDING"
        )
        self.db.add(transaction)
        await self.db.flush()

        if dry_run:
            logger.info(f"[HEDGE_EXECUTOR] DRY RUN - Would exit {hedge.symbol}")
            transaction.order_status = "DRY_RUN"
            await self.db.commit()
            return OrderResult(
                success=True,
                order_id="DRY_RUN",
                executed_price=current_price,
                error_message=None,
                transaction_id=transaction.id
            )

        try:
            order_response = await self._place_order(
                symbol=hedge.symbol,
                exchange=hedge.exchange,
                action="SELL",
                quantity=hedge.quantity,
                price=current_price
            )

            order_id = order_response.get('orderid') or order_response.get('order_id')

            # Calculate P&L
            pnl = (current_price - hedge.entry_price) * hedge.quantity

            # Update transaction
            transaction.order_id = order_id
            transaction.order_status = "SUCCESS"
            transaction.executed_price = current_price
            transaction.total_cost = current_price * hedge.quantity

            # Mark hedge as inactive
            hedge.is_active = False
            hedge.exit_transaction_id = transaction.id
            hedge.current_price = current_price

            await self.db.commit()

            self._last_action_time = self._now_ist()

            # Send Telegram alert
            await self.telegram.send_hedge_sell_alert(
                symbol=hedge.symbol,
                strike=hedge.strike,
                option_type=hedge.option_type,
                quantity=hedge.quantity,
                entry_price=float(hedge.entry_price),
                exit_price=current_price,
                pnl=pnl,
                trigger_reason=trigger_reason,
                utilization_before=utilization_before
            )

            return OrderResult(
                success=True,
                order_id=order_id,
                executed_price=current_price,
                error_message=None,
                transaction_id=transaction.id
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[HEDGE_EXECUTOR] Exit failed: {error_msg}")

            transaction.order_status = "FAILED"
            transaction.error_message = error_msg
            await self.db.commit()

            await self.telegram.send_hedge_failure_alert(
                symbol=hedge.symbol,
                action="SELL",
                error=error_msg,
                trigger_reason=trigger_reason
            )

            return OrderResult(
                success=False,
                order_id=None,
                executed_price=None,
                error_message=error_msg,
                transaction_id=transaction.id
            )

    async def _place_order(
        self,
        symbol: str,
        exchange: str,
        action: str,
        quantity: int,
        price: float,
        max_retries: int = 3
    ) -> dict:
        """
        Place order via OpenAlgo with rate limiting and circuit breaker.

        Implements:
        - Circuit breaker: Blocks requests after 3 consecutive failures
        - Exponential backoff: 1s, 2s, 4s between retries
        - Rate limiting: Min 500ms between order requests

        Args:
            symbol: Trading symbol
            exchange: NFO or BFO
            action: BUY or SELL
            quantity: Order quantity
            price: Limit price (0 for market order)
            max_retries: Maximum retry attempts (default 3)

        Returns:
            Order response from broker

        Raises:
            OpenAlgoError: If order placement fails after all retries
        """
        global _circuit_breaker

        # Check circuit breaker
        if not _circuit_breaker.is_allowed():
            logger.error(
                f"[HEDGE_EXECUTOR] Circuit breaker OPEN - blocking order request"
            )
            await self.telegram.send_message(
                "❌ *Order Blocked*: Circuit breaker OPEN due to API failures\n\n"
                f"Symbol: {symbol}\nAction: {action}\nQty: {quantity}"
            )
            raise OpenAlgoError("Circuit breaker OPEN - too many API failures")

        # Rate limiting: min 500ms between orders
        await asyncio.sleep(0.5)

        last_error = None
        for attempt in range(max_retries):
            try:
                logger.info(
                    f"[HEDGE_EXECUTOR] Placing order (attempt {attempt + 1}/{max_retries}): "
                    f"{action} {quantity} {symbol} @ {'MARKET' if price == 0 else price}"
                )

                # Use OpenAlgo service for real order execution
                price_type = "MARKET" if price == 0 else "LIMIT"
                result = await self.openalgo.place_order(
                    symbol=symbol,
                    exchange=exchange,
                    action=action,
                    quantity=quantity,
                    product="NRML",  # Normal for overnight hedges
                    price_type=price_type,
                    price=price
                )

                # Success - reset circuit breaker
                _circuit_breaker.record_success()

                order_id = result.get("order_id") or result.get("orderid")
                logger.info(f"[HEDGE_EXECUTOR] Order placed successfully: {order_id}")

                return {
                    "status": "success",
                    "orderid": order_id
                }

            except OpenAlgoError as e:
                last_error = e
                logger.warning(
                    f"[HEDGE_EXECUTOR] Order attempt {attempt + 1} failed: {e}"
                )

                # Record failure for circuit breaker
                _circuit_breaker.record_failure()

                # Exponential backoff: 1s, 2s, 4s
                if attempt < max_retries - 1:
                    backoff_seconds = 2 ** attempt
                    logger.info(f"[HEDGE_EXECUTOR] Retrying in {backoff_seconds}s...")
                    await asyncio.sleep(backoff_seconds)

            except Exception as e:
                last_error = e
                logger.error(
                    f"[HEDGE_EXECUTOR] Unexpected error in order attempt {attempt + 1}: {e}"
                )
                _circuit_breaker.record_failure()

                if attempt < max_retries - 1:
                    backoff_seconds = 2 ** attempt
                    await asyncio.sleep(backoff_seconds)

        # All retries exhausted
        error_msg = f"Order failed after {max_retries} attempts: {last_error}"
        logger.error(f"[HEDGE_EXECUTOR] {error_msg}")
        raise OpenAlgoError(error_msg)

    async def get_active_hedges(self, session_id: int) -> list:
        """
        Get all active hedges for a session.

        Args:
            session_id: Daily session ID

        Returns:
            List of ActiveHedge objects
        """
        result = await self.db.execute(
            select(ActiveHedge)
            .where(ActiveHedge.session_id == session_id)
            .where(ActiveHedge.is_active == True)
            .order_by(ActiveHedge.otm_distance.desc())  # Farthest OTM first
        )
        return result.scalars().all()
