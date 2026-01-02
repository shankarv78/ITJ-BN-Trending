"""
Order Execution Strategies

Implements different execution strategies for placing orders:
1. SimpleLimitExecutor: Single limit order with timeout
2. ProgressiveExecutor: Progressive price improvement with slippage limits
"""
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict

from core.models import Signal

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Execution status"""
    EXECUTED = "executed"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    PARTIAL = "partial"  # Partial fill (remaining cancelled)


class PartialFillStrategy(Enum):
    """Strategy for handling partial fills"""
    CANCEL_REMAINDER = "cancel"      # Cancel remaining lots immediately (default)
    WAIT_FOR_FILL = "wait"           # Wait with timeout for full fill
    REATTEMPT = "reattempt"          # Try again with adjusted price


@dataclass
class ExecutionResult:
    """Result of order execution"""
    status: ExecutionStatus
    execution_price: Optional[float] = None
    lots_filled: Optional[int] = None
    slippage_pct: Optional[float] = None  # Calculated: (execution_price - signal_price) / signal_price
    rejection_reason: Optional[str] = None
    order_id: Optional[str] = None
    attempts: int = 1
    lots_cancelled: Optional[int] = None  # For partial fills
    notes: Optional[str] = None

    def calculate_slippage(self, signal_price: float):
        """Calculate slippage percentage"""
        if self.execution_price is not None and signal_price > 0:
            self.slippage_pct = (self.execution_price - signal_price) / signal_price


class OrderExecutor(ABC):
    """
    Abstract base class for order execution strategies

    NOTE: This executor uses blocking I/O (time.sleep).
    It is designed for synchronous use in live/engine.py.
    If integrating into async systems, run in thread pool or use AsyncOrderExecutor.
    """

    def __init__(
        self,
        openalgo_client,
        partial_fill_strategy: PartialFillStrategy = PartialFillStrategy.CANCEL_REMAINDER,
        partial_fill_wait_timeout: int = 30
    ):
        """
        Initialize order executor

        Args:
            openalgo_client: OpenAlgo API client instance
            partial_fill_strategy: Strategy for handling partial fills (default: CANCEL_REMAINDER)
            partial_fill_wait_timeout: Timeout in seconds for WAIT_FOR_FILL strategy (default: 30)
        """
        self.openalgo = openalgo_client
        self.partial_fill_strategy = partial_fill_strategy
        self.partial_fill_wait_timeout = partial_fill_wait_timeout

    @abstractmethod
    def execute(
        self,
        signal: Signal,
        lots: int,
        limit_price: float,
        action: str = None
    ) -> ExecutionResult:
        """
        Execute order using this strategy

        NOTE: This method blocks with time.sleep().
        For async systems, wrap in asyncio.run_in_executor() or use AsyncOrderExecutor.

        Args:
            signal: Trading signal
            lots: Number of lots to execute
            limit_price: Limit price for order
            action: Override action (BUY/SELL). If None, derives from signal type.

        Returns:
            ExecutionResult with execution outcome
        """
        pass

    def get_quote(self, instrument: str) -> Dict:
        """
        Get current quote from broker

        Args:
            instrument: Trading symbol

        Returns:
            Quote dictionary with ltp, bid, ask
        """
        # Determine exchange based on instrument
        if "GOLD" in instrument.upper() or "COPPER" in instrument.upper() or "SILVER" in instrument.upper():
            exchange = "MCX"
        else:
            exchange = "NFO"

        return self.openalgo.get_quote(instrument, exchange=exchange)

    def place_order(
        self,
        instrument: str,
        action: str,
        quantity: int,
        order_type: str,
        price: float
    ) -> Dict:
        """
        Place order via OpenAlgo client

        Args:
            instrument: Trading symbol (internal name like GOLD_MINI or actual symbol)
            action: BUY or SELL
            quantity: Order quantity
            order_type: LIMIT or MARKET
            price: Limit price (if LIMIT)

        Returns:
            Order response dictionary
        """
        # Determine exchange and translate internal instrument names to actual symbols
        actual_symbol = instrument

        if instrument == "GOLD_MINI":
            # Gold Mini futures: GOLDM{DD}{MMM}{YY}FUT (e.g., GOLDM05JAN26FUT)
            exchange = "MCX"
            try:
                from core.expiry_calendar import ExpiryCalendar
                from datetime import date
                expiry_cal = ExpiryCalendar()
                expiry = expiry_cal.get_expiry_after_rollover("GOLD_MINI", date.today())
                actual_symbol = f"GOLDM{expiry.strftime('%d%b%y').upper()}FUT"
                logger.info(f"[OrderExecutor] Translated GOLD_MINI -> {actual_symbol}")
            except Exception as e:
                logger.error(f"[OrderExecutor] Failed to translate GOLD_MINI symbol: {e}")
                actual_symbol = "GOLDM05JAN26FUT"  # Fallback
        elif instrument == "COPPER":
            # Copper futures: COPPER{DD}{MMM}{YY}FUT (e.g., COPPER31DEC25FUT)
            exchange = "MCX"
            try:
                from core.expiry_calendar import ExpiryCalendar
                from datetime import date
                expiry_cal = ExpiryCalendar()
                expiry = expiry_cal.get_expiry_after_rollover("COPPER", date.today())
                actual_symbol = f"COPPER{expiry.strftime('%d%b%y').upper()}FUT"
                logger.info(f"[OrderExecutor] Translated COPPER -> {actual_symbol}")
            except Exception as e:
                logger.error(f"[OrderExecutor] Failed to translate COPPER symbol: {e}")
                actual_symbol = "COPPER31DEC25FUT"  # Fallback
        elif instrument == "SILVER_MINI":
            # Silver Mini futures: SILVERM{DD}{MMM}{YY}FUT (e.g., SILVERM27FEB26FUT)
            exchange = "MCX"
            try:
                from core.expiry_calendar import ExpiryCalendar
                from datetime import date
                expiry_cal = ExpiryCalendar()
                expiry = expiry_cal.get_expiry_after_rollover("SILVER_MINI", date.today())
                actual_symbol = f"SILVERM{expiry.strftime('%d%b%y').upper()}FUT"
                logger.info(f"[OrderExecutor] Translated SILVER_MINI -> {actual_symbol}")
            except Exception as e:
                logger.error(f"[OrderExecutor] Failed to translate SILVER_MINI symbol: {e}")
                actual_symbol = "SILVERM27FEB26FUT"  # Fallback
        elif "GOLD" in instrument.upper() or "COPPER" in instrument.upper() or "SILVER" in instrument.upper():
            exchange = "MCX"
        else:
            exchange = "NFO"  # Bank Nifty and other NSE derivatives

        return self.openalgo.place_order(
            symbol=actual_symbol,
            action=action,
            quantity=quantity,
            order_type=order_type,
            price=price,
            exchange=exchange
        )

    def get_order_status(self, order_id: str) -> Dict:
        """
        Get order status from broker

        Args:
            order_id: Order ID

        Returns:
            Order status dictionary
        """
        return self.openalgo.get_order_status(order_id)

    def modify_order(self, order_id: str, new_price: float,
                     symbol: str = None, action: str = None, exchange: str = None,
                     quantity: int = None, product: str = None) -> Dict:
        """
        Modify existing order price

        Args:
            order_id: Order ID
            new_price: New limit price
            symbol: Trading symbol (required by OpenAlgo)
            action: BUY or SELL (required by OpenAlgo)
            exchange: Exchange code NFO/MCX (required by OpenAlgo)
            quantity: Order quantity (required by OpenAlgo)
            product: Product type NRML/MIS (required by OpenAlgo)

        Returns:
            Modification response
        """
        if hasattr(self.openalgo, 'modify_order'):
            return self.openalgo.modify_order(
                order_id=order_id,
                new_price=new_price,
                symbol=symbol,
                action=action,
                exchange=exchange,
                quantity=quantity,
                product=product
            )
        else:
            # Fallback: cancel and place new order
            self.cancel_order(order_id)
            logger.warning("modify_order not available, using cancel+reorder fallback")
            return {'status': 'error', 'error': 'modify_order_not_available'}

    def cancel_order(self, order_id: str) -> Dict:
        """
        Cancel order

        Args:
            order_id: Order ID

        Returns:
            Cancellation response
        """
        return self.openalgo.cancel_order(order_id)

    def handle_partial_fill(
        self,
        order_id: str,
        filled_lots: int,
        remaining_lots: int,
        avg_fill_price: float,
        signal: Optional[Signal] = None
    ) -> ExecutionResult:
        """
        Handle partial fill using configured strategy.

        Strategies:
        - CANCEL_REMAINDER: Cancel remaining lots immediately (default)
        - WAIT_FOR_FILL: Wait with timeout for full fill
        - REATTEMPT: Place new order for remaining lots with adjusted price

        Args:
            order_id: Order ID
            filled_lots: Number of lots filled
            remaining_lots: Number of lots remaining
            avg_fill_price: Average fill price
            signal: Original signal (required for REATTEMPT strategy)

        Returns:
            ExecutionResult with PARTIAL or EXECUTED status
        """
        if self.partial_fill_strategy == PartialFillStrategy.CANCEL_REMAINDER:
            # Cancel remaining lots (current behavior)
            self.cancel_order(order_id)

            return ExecutionResult(
                status=ExecutionStatus.PARTIAL,
                execution_price=avg_fill_price,
                lots_filled=filled_lots,
                lots_cancelled=remaining_lots,
                order_id=order_id,
                notes="partial_fill_remaining_cancelled"
            )

        elif self.partial_fill_strategy == PartialFillStrategy.WAIT_FOR_FILL:
            # Wait for remaining lots to fill
            logger.info(
                f"[SimpleLimitExecutor] Waiting for remaining {remaining_lots} lots "
                f"(timeout: {self.partial_fill_wait_timeout}s)"
            )

            wait_start = time.time()
            while time.time() - wait_start < self.partial_fill_wait_timeout:
                try:
                    status_response = self.get_order_status(order_id)
                    fill_status = status_response.get('fill_status', '').upper()

                    if fill_status == 'COMPLETE':
                        # Fully filled during wait
                        final_filled = status_response.get('filled_lots', filled_lots)
                        final_price = status_response.get('avg_fill_price', avg_fill_price)

                        logger.info(
                            f"[SimpleLimitExecutor] Order fully filled during wait: "
                            f"{final_filled} lots @ ₹{final_price:,.2f}"
                        )

                        return ExecutionResult(
                            status=ExecutionStatus.EXECUTED,
                            execution_price=float(final_price),
                            lots_filled=int(final_filled),
                            order_id=order_id,
                            notes="partial_fill_completed_after_wait"
                        )
                except Exception as e:
                    logger.warning(f"[SimpleLimitExecutor] Error checking order status: {e}")

                time.sleep(2.0)  # Poll every 2 seconds

            # Timeout - cancel remainder
            logger.warning(
                f"[SimpleLimitExecutor] Wait timeout, cancelling remaining {remaining_lots} lots"
            )
            self.cancel_order(order_id)

            return ExecutionResult(
                status=ExecutionStatus.PARTIAL,
                execution_price=avg_fill_price,
                lots_filled=filled_lots,
                lots_cancelled=remaining_lots,
                order_id=order_id,
                notes="partial_fill_wait_timeout_cancelled"
            )

        elif self.partial_fill_strategy == PartialFillStrategy.REATTEMPT:
            # Cancel current order and place new order for remaining lots
            logger.info(
                f"[SimpleLimitExecutor] Reattempting order for remaining {remaining_lots} lots "
                f"with adjusted price"
            )

            self.cancel_order(order_id)

            # Adjust price slightly more aggressive (0.1% for buy orders)
            # This is a simple approach - could be enhanced with order book analysis
            adjusted_price = avg_fill_price * 1.001  # 0.1% higher for buy

            logger.info(
                f"[SimpleLimitExecutor] Placing new order: {remaining_lots} lots @ ₹{adjusted_price:,.2f}"
            )

            # Place new order (simplified - no recursive retry to avoid complexity)
            try:
                order_response = self.place_order(
                    instrument=signal.instrument if signal else "UNKNOWN",
                    action="BUY",
                    quantity=remaining_lots,
                    order_type="LIMIT",
                    price=adjusted_price
                )

                if order_response.get('status') == 'success':
                    new_order_id = order_response.get('orderid')

                    # Wait briefly for new order (simplified - 10s timeout)
                    time.sleep(5.0)
                    status_response = self.get_order_status(new_order_id)

                    if status_response.get('fill_status', '').upper() == 'COMPLETE':
                        additional_filled = status_response.get('filled_lots', 0)
                        additional_price = status_response.get('fill_price', adjusted_price)

                        # Calculate weighted average price
                        total_filled = filled_lots + additional_filled
                        weighted_price = (
                            (filled_lots * avg_fill_price + additional_filled * additional_price) /
                            total_filled
                        )

                        logger.info(
                            f"[SimpleLimitExecutor] Reattempt successful: "
                            f"+{additional_filled} lots @ ₹{additional_price:,.2f}"
                        )

                        return ExecutionResult(
                            status=ExecutionStatus.EXECUTED if total_filled == (filled_lots + remaining_lots) else ExecutionStatus.PARTIAL,
                            execution_price=weighted_price,
                            lots_filled=total_filled,
                            lots_cancelled=remaining_lots - additional_filled if additional_filled < remaining_lots else 0,
                            order_id=new_order_id,
                            notes="partial_fill_reattempt_successful"
                        )
                    else:
                        # Reattempt didn't fill - cancel and return partial
                        self.cancel_order(new_order_id)

                        return ExecutionResult(
                            status=ExecutionStatus.PARTIAL,
                            execution_price=avg_fill_price,
                            lots_filled=filled_lots,
                            lots_cancelled=remaining_lots,
                            order_id=order_id,
                            notes="partial_fill_reattempt_failed"
                        )
            except Exception as e:
                logger.error(f"[SimpleLimitExecutor] Reattempt order failed: {e}")

                return ExecutionResult(
                    status=ExecutionStatus.PARTIAL,
                    execution_price=avg_fill_price,
                    lots_filled=filled_lots,
                    lots_cancelled=remaining_lots,
                    order_id=order_id,
                    notes=f"partial_fill_reattempt_error: {str(e)}"
                )

        else:
            # Unknown strategy - fallback to cancel
            logger.warning(
                f"[SimpleLimitExecutor] Unknown partial fill strategy: {self.partial_fill_strategy}, "
                f"defaulting to CANCEL_REMAINDER"
            )
            self.cancel_order(order_id)

            return ExecutionResult(
                status=ExecutionStatus.PARTIAL,
                execution_price=avg_fill_price,
                lots_filled=filled_lots,
                lots_cancelled=remaining_lots,
                order_id=order_id,
                notes="partial_fill_unknown_strategy_cancelled"
        )


class SimpleLimitExecutor(OrderExecutor):
    """
    Simple limit order executor.

    Places single limit order at signal price, waits for fill (timeout 30s),
    rejects if not filled.
    """

    def __init__(
        self,
        openalgo_client,
        timeout_seconds: int = 30,
        poll_interval_seconds: float = 2.0,
        partial_fill_strategy: PartialFillStrategy = PartialFillStrategy.CANCEL_REMAINDER,
        partial_fill_wait_timeout: int = 30
    ):
        """
        Initialize simple limit executor

        Args:
            openalgo_client: OpenAlgo API client
            timeout_seconds: Timeout for order fill (default: 30s)
            poll_interval_seconds: Interval between status checks (default: 2s)
            partial_fill_strategy: Strategy for handling partial fills (default: CANCEL_REMAINDER)
            partial_fill_wait_timeout: Timeout for WAIT_FOR_FILL strategy (default: 30s)
        """
        super().__init__(openalgo_client, partial_fill_strategy, partial_fill_wait_timeout)
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def execute(
        self,
        signal: Signal,
        lots: int,
        limit_price: float,
        action: str = None
    ) -> ExecutionResult:
        """
        Execute order with simple limit strategy

        NOTE: This method blocks with time.sleep() during order status polling.
        Designed for synchronous use in live/engine.py.

        Args:
            signal: Trading signal
            lots: Number of lots
            limit_price: Limit price
            action: Optional - "BUY" or "SELL" (auto-detected from signal_type if not provided)

        Returns:
            ExecutionResult
        """
        # Determine action from signal type if not provided
        if action is None:
            from core.models import SignalType
            if signal.signal_type == SignalType.EXIT:
                action = "SELL"
            else:
                action = "BUY"  # BASE_ENTRY, PYRAMID

        logger.info(
            f"[SimpleLimitExecutor] Executing {signal.signal_type.value} order: "
            f"{action} {lots} lots @ ₹{limit_price:,.2f}"
        )

        # Place limit order
        try:
            order_response = self.place_order(
                instrument=signal.instrument,
                action=action,
                quantity=lots,
                order_type="LIMIT",
                price=limit_price
            )
        except Exception as e:
            logger.error(f"[SimpleLimitExecutor] Order placement failed: {e}")
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                rejection_reason=f"order_placement_failed: {str(e)}",
                attempts=1
            )

        if order_response.get('status') != 'success':
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                rejection_reason=f"order_placement_rejected: {order_response.get('error', 'unknown')}",
                attempts=1
            )

        order_id = order_response.get('orderid')
        if not order_id:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                rejection_reason="no_order_id_returned",
                attempts=1
            )

        # Wait for fill with timeout
        start_time = time.time()
        attempts = 1

        while time.time() - start_time < self.timeout_seconds:
            try:
                status_response = self.get_order_status(order_id)
                status = status_response.get('status', '').upper()
                fill_status = status_response.get('fill_status', '').upper()

                # Check if order is filled
                if status in ['COMPLETE', 'FILLED'] or fill_status == 'COMPLETE':
                    # Try multiple field names for fill price
                    fill_price = (
                        status_response.get('averageprice') or
                        status_response.get('average_price') or
                        status_response.get('tradedprice') or
                        status_response.get('avgprice') or
                        status_response.get('fill_price') or
                        status_response.get('price') or
                        limit_price
                    )
                    filled_lots = (
                        status_response.get('filledshares') or
                        status_response.get('filled_lots') or
                        status_response.get('filled_quantity') or
                        status_response.get('lots') or
                        lots
                    )

                    # If orderbook didn't have fill price, try tradebook
                    if fill_price == limit_price and order_id:
                        for tradebook_attempt in range(3):
                            if tradebook_attempt > 0:
                                time.sleep(1.0)
                            tradebook_price = self.openalgo.get_trade_fill_price(order_id)
                            if tradebook_price and tradebook_price != limit_price:
                                fill_price = tradebook_price
                                logger.info(
                                    f"[SimpleLimitExecutor] Using tradebook fill price: ₹{fill_price:,.2f}"
                                )
                                break

                    if fill_price == limit_price:
                        logger.warning(
                            f"[SimpleLimitExecutor] Could not find actual fill price, using limit price. "
                            f"Orderbook data: {status_response}"
                        )

                    result = ExecutionResult(
                        status=ExecutionStatus.EXECUTED,
                        execution_price=float(fill_price),
                        lots_filled=int(filled_lots),
                        order_id=order_id,
                        attempts=attempts
                    )
                    result.calculate_slippage(signal.price)

                    logger.info(
                        f"[SimpleLimitExecutor] Order filled: {filled_lots} lots @ ₹{fill_price:,.2f} "
                        f"(slippage: {result.slippage_pct:.2%})"
                    )
                    return result

                # Check for partial fill
                if fill_status == 'PARTIAL':
                    filled_lots = (
                        status_response.get('filledshares') or
                        status_response.get('filled_lots') or
                        status_response.get('filled_quantity') or
                        0
                    )
                    remaining_lots = status_response.get('remaining_lots', lots - filled_lots)
                    avg_fill_price = (
                        status_response.get('averageprice') or
                        status_response.get('average_price') or
                        status_response.get('avg_fill_price') or
                        limit_price
                    )

                    # Try tradebook for actual fill price
                    if avg_fill_price == limit_price and order_id:
                        tradebook_price = self.openalgo.get_trade_fill_price(order_id)
                        if tradebook_price:
                            avg_fill_price = tradebook_price

                    logger.info(
                        f"[SimpleLimitExecutor] Partial fill: {filled_lots}/{lots} lots, "
                        f"handling with strategy: {self.partial_fill_strategy.value}"
                    )

                    return self.handle_partial_fill(
                        order_id, filled_lots, remaining_lots, float(avg_fill_price), signal
                    )

            except Exception as e:
                logger.warning(f"[SimpleLimitExecutor] Error checking order status: {e}")

            # Wait before next check
            time.sleep(self.poll_interval_seconds)
            attempts += 1

        # Timeout - cancel order
        logger.warning(
            f"[SimpleLimitExecutor] Order timeout after {self.timeout_seconds}s, cancelling"
        )
        try:
            self.cancel_order(order_id)
        except Exception as e:
            logger.error(f"[SimpleLimitExecutor] Error cancelling order: {e}")

        return ExecutionResult(
            status=ExecutionStatus.TIMEOUT,
            rejection_reason="timeout_no_fill",
            order_id=order_id,
            attempts=attempts
        )


class ProgressiveExecutor(OrderExecutor):
    """
    Progressive price improvement executor.

    Uses aggressive price chasing similar to SyntheticFuturesExecutor:
    - Short intervals (1.5-2 seconds) between attempts
    - Progressive price improvements
    - Hard slippage limit (2%)
    """

    def __init__(
        self,
        openalgo_client,
        max_attempts: int = 10,  # More attempts with shorter intervals
        attempt_intervals: list = None,
        improvement_steps: list = None,
        hard_slippage_limit: float = 0.02,  # 2%
        partial_fill_strategy: PartialFillStrategy = PartialFillStrategy.CANCEL_REMAINDER,
        partial_fill_wait_timeout: int = 30
    ):
        """
        Initialize progressive executor

        Args:
            openalgo_client: OpenAlgo API client
            max_attempts: Maximum price improvement attempts (default: 10)
            attempt_intervals: Seconds to wait per attempt (default: 1.5s like BN)
            improvement_steps: Price improvement percentages (default: 0.1% per step)
            hard_slippage_limit: Maximum total slippage (default: 2%)
            partial_fill_strategy: Strategy for handling partial fills (default: CANCEL_REMAINDER)
            partial_fill_wait_timeout: Timeout for WAIT_FOR_FILL strategy (default: 30s)
        """
        super().__init__(openalgo_client, partial_fill_strategy, partial_fill_wait_timeout)
        self.max_attempts = max_attempts
        # Same 1.5 second intervals as Bank Nifty SyntheticFuturesExecutor
        self.attempt_intervals = attempt_intervals or [1.5] * max_attempts
        # Progressive 0.1% steps (roughly ₹130 per step for Gold Mini at ~₹130,000)
        self.improvement_steps = improvement_steps or [i * 0.001 for i in range(max_attempts)]
        self.hard_slippage_limit = hard_slippage_limit

        # Ensure we have enough intervals and steps
        if len(self.attempt_intervals) < self.max_attempts:
            self.attempt_intervals.extend([1.5] * (self.max_attempts - len(self.attempt_intervals)))
        if len(self.improvement_steps) < self.max_attempts:
            # Extend with linear progression
            last_step = self.improvement_steps[-1] if self.improvement_steps else 0.0
            step_size = 0.005
            for i in range(len(self.improvement_steps), self.max_attempts):
                self.improvement_steps.append(min(last_step + step_size, self.hard_slippage_limit))
                last_step = self.improvement_steps[-1]

    def execute(
        self,
        signal: Signal,
        lots: int,
        limit_price: float,
        action: str = None
    ) -> ExecutionResult:
        """
        Execute order with progressive price improvement

        NOTE: This method blocks with time.sleep() during order status polling.
        Designed for synchronous use in live/engine.py.

        Args:
            signal: Trading signal
            lots: Number of lots
            limit_price: Initial limit price (usually broker price)
            action: Optional - "BUY" or "SELL" (auto-detected from signal_type if not provided)

        Returns:
            ExecutionResult
        """
        # Determine action from signal type if not provided
        if action is None:
            from core.models import SignalType
            if signal.signal_type == SignalType.EXIT:
                action = "SELL"
            else:
                action = "BUY"  # BASE_ENTRY, PYRAMID

        logger.info(
            f"[ProgressiveExecutor] Executing {signal.signal_type.value} order: "
            f"{action} {lots} lots @ ₹{limit_price:,.2f} (signal: ₹{signal.price:,.2f})"
        )
        order_id = None
        signal_price = signal.price

        # Attempt progressive price improvement
        for attempt in range(self.max_attempts):
            attempt_num = attempt + 1
            improvement_pct = self.improvement_steps[attempt]

            # Direction depends on action:
            # BUY: increase price to be more aggressive (pay more to get filled)
            # SELL: decrease price to be more aggressive (accept less to get filled)
            if action == "SELL":
                attempt_price = limit_price * (1 - improvement_pct)
            else:
                attempt_price = limit_price * (1 + improvement_pct)

            # Check hard slippage limit (absolute value for both directions)
            slippage_vs_signal = abs(attempt_price - signal_price) / signal_price
            if slippage_vs_signal > self.hard_slippage_limit:
                logger.warning(
                    f"[ProgressiveExecutor] Attempt {attempt_num} would exceed hard slippage limit "
                    f"({slippage_vs_signal:.2%} > {self.hard_slippage_limit:.2%}), aborting"
                )

                if order_id:
                    try:
                        self.cancel_order(order_id)
                    except Exception as e:
                        logger.error(f"[ProgressiveExecutor] Error cancelling order: {e}")

                return ExecutionResult(
                    status=ExecutionStatus.REJECTED,
                    rejection_reason=f"hard_slippage_limit_exceeded_{slippage_vs_signal:.2%}",
                    attempts=attempt_num
                )

            # Log with correct direction indicator
            direction = "-" if action == "SELL" else "+"
            slippage_direction = "-" if attempt_price < signal_price else "+"
            logger.info(
                f"[ProgressiveExecutor] Attempt {attempt_num}/{self.max_attempts}: "
                f"Price ₹{attempt_price:,.2f} ({direction}{improvement_pct:.2%} vs limit, "
                f"{slippage_direction}{slippage_vs_signal:.2%} vs signal)"
            )

            try:
                # Determine exchange and actual symbol for order placement/modification
                if signal.instrument == "GOLD_MINI":
                    exchange = "MCX"
                    try:
                        from core.expiry_calendar import ExpiryCalendar
                        from datetime import date
                        expiry_cal = ExpiryCalendar()
                        expiry = expiry_cal.get_expiry_after_rollover("GOLD_MINI", date.today())
                        actual_symbol = f"GOLDM{expiry.strftime('%d%b%y').upper()}FUT"
                    except Exception:
                        actual_symbol = "GOLDM05JAN26FUT"  # Fallback
                elif signal.instrument == "COPPER":
                    exchange = "MCX"
                    try:
                        from core.expiry_calendar import ExpiryCalendar
                        from datetime import date
                        expiry_cal = ExpiryCalendar()
                        expiry = expiry_cal.get_expiry_after_rollover("COPPER", date.today())
                        actual_symbol = f"COPPER{expiry.strftime('%d%b%y').upper()}FUT"
                    except Exception:
                        actual_symbol = "COPPER31DEC25FUT"  # Fallback
                elif signal.instrument == "SILVER_MINI":
                    exchange = "MCX"
                    try:
                        from core.expiry_calendar import ExpiryCalendar
                        from datetime import date
                        expiry_cal = ExpiryCalendar()
                        expiry = expiry_cal.get_expiry_after_rollover("SILVER_MINI", date.today())
                        actual_symbol = f"SILVERM{expiry.strftime('%d%b%y').upper()}FUT"
                    except Exception:
                        actual_symbol = "SILVERM27FEB26FUT"  # Fallback
                elif "GOLD" in signal.instrument.upper() or "COPPER" in signal.instrument.upper() or "SILVER" in signal.instrument.upper():
                    exchange = "MCX"
                    actual_symbol = signal.instrument
                else:
                    exchange = "NFO"
                    actual_symbol = signal.instrument

                # Round price to tick size
                # MCX Gold Mini: Rs 1 tick, MCX Copper: Rs 0.05 tick, MCX Silver Mini: Rs 1 tick, NFO: Rs 0.05 tick
                if signal.instrument == "COPPER":
                    tick_size = 0.05  # Copper tick size is Rs 0.05 per kg
                elif signal.instrument == "SILVER_MINI":
                    tick_size = 1.0  # Silver Mini tick size is Rs 1 per kg
                elif exchange == "MCX":
                    tick_size = 1.0  # Gold Mini tick size
                else:
                    tick_size = 0.05  # NFO tick size
                attempt_price = round(round(attempt_price / tick_size) * tick_size, 2)

                if order_id and attempt > 0:
                    # FIRST: Check if order was already filled before trying to modify
                    status_check = self.get_order_status(order_id)
                    if status_check:
                        check_status = (status_check.get('order_status') or status_check.get('status') or '').upper()
                        if check_status in ['COMPLETE', 'FILLED']:
                            # OpenAlgo/Zerodha field variations for fill price
                            fill_price = (
                                status_check.get('averageprice') or
                                status_check.get('average_price') or
                                status_check.get('tradedprice') or
                                status_check.get('avgprice') or
                                status_check.get('fill_price') or
                                status_check.get('price') or
                                attempt_price
                            )
                            filled_lots = status_check.get('filledshares') or status_check.get('filled_quantity') or lots

                            result = ExecutionResult(
                                status=ExecutionStatus.EXECUTED,
                                execution_price=float(fill_price),
                                lots_filled=int(filled_lots),
                                order_id=order_id,
                                attempts=attempt_num
                            )
                            result.calculate_slippage(signal_price)

                            logger.info(
                                f"[ProgressiveExecutor] Order already filled before modify attempt {attempt_num}: "
                                f"{filled_lots} lots @ ₹{fill_price:,.2f} "
                                f"(slippage: {result.slippage_pct:.2%})"
                            )
                            return result

                    # Order still open - try to modify
                    modify_response = self.modify_order(
                        order_id=order_id,
                        new_price=attempt_price,
                        symbol=actual_symbol,
                        action=action,
                        exchange=exchange,
                        quantity=lots,
                        product="NRML"
                    )
                    if modify_response.get('status') != 'success':
                        # Modify failed - could be because order was just filled
                        # Re-check status
                        recheck = self.get_order_status(order_id)
                        if recheck:
                            recheck_status = (recheck.get('order_status') or recheck.get('status') or '').upper()
                            if recheck_status in ['COMPLETE', 'FILLED']:
                                # OpenAlgo/Zerodha field variations for fill price
                                fill_price = (
                                    recheck.get('averageprice') or
                                    recheck.get('average_price') or
                                    recheck.get('tradedprice') or
                                    recheck.get('avgprice') or
                                    recheck.get('fill_price') or
                                    recheck.get('price') or
                                    attempt_price
                                )
                                filled_lots = recheck.get('filledshares') or recheck.get('filled_quantity') or lots

                                result = ExecutionResult(
                                    status=ExecutionStatus.EXECUTED,
                                    execution_price=float(fill_price),
                                    lots_filled=int(filled_lots),
                                    order_id=order_id,
                                    attempts=attempt_num
                                )
                                result.calculate_slippage(signal_price)

                                logger.info(
                                    f"[ProgressiveExecutor] Order filled (detected after modify fail): "
                                    f"{filled_lots} lots @ ₹{fill_price:,.2f}"
                                )
                                return result

                        logger.warning(
                            f"[ProgressiveExecutor] Order modification failed: {modify_response}"
                        )
                        # Continue to next attempt or cancel
                        try:
                            self.cancel_order(order_id)
                        except Exception:
                            pass
                        order_id = None
                        continue  # Skip to next iteration to place new order
                else:
                    # Place new order
                    order_response = self.place_order(
                        instrument=signal.instrument,
                        action=action,
                        quantity=lots,
                        order_type="LIMIT",
                        price=attempt_price
                    )

                    if order_response.get('status') != 'success':
                        logger.warning(
                            f"[ProgressiveExecutor] Order placement failed: {order_response}"
                        )
                        continue

                    order_id = order_response.get('orderid')
                    if not order_id:
                        continue

                # Wait for fill
                wait_time = self.attempt_intervals[attempt]
                time.sleep(wait_time)

                # Check order status
                status_response = self.get_order_status(order_id)
                if not status_response:
                    logger.warning(f"[ProgressiveExecutor] Could not get order status for {order_id}")
                    continue

                # OpenAlgo uses 'order_status', Zerodha uses 'status'
                status = (status_response.get('order_status') or status_response.get('status') or '').upper()

                if status in ['COMPLETE', 'FILLED']:
                    # DEBUG: Log the full response to identify correct field names
                    logger.debug(f"[ProgressiveExecutor] Order status response: {status_response}")

                    # OpenAlgo/Zerodha field variations for fill price
                    # Common fields: averageprice, average_price, tradedprice, avgprice, price
                    fill_price = (
                        status_response.get('averageprice') or
                        status_response.get('average_price') or
                        status_response.get('tradedprice') or
                        status_response.get('avgprice') or
                        status_response.get('fill_price') or
                        status_response.get('price') or
                        attempt_price
                    )

                    # If orderbook didn't have fill price, try tradebook for actual execution price
                    # Add delay for broker to update tradebook, then retry
                    if fill_price == attempt_price and order_id:
                        # Tradebook may not be updated immediately - wait and retry
                        for tradebook_attempt in range(3):
                            if tradebook_attempt > 0:
                                time.sleep(1.0)  # Wait 1 second between retries
                            tradebook_price = self.openalgo.get_trade_fill_price(order_id)
                            if tradebook_price and tradebook_price != attempt_price:
                                fill_price = tradebook_price
                                logger.info(
                                    f"[ProgressiveExecutor] Using tradebook fill price: ₹{fill_price:,.2f} "
                                    f"(attempt {tradebook_attempt + 1})"
                                )
                                break

                    # Warn if we still had to fall back to attempt_price
                    if fill_price == attempt_price:
                        logger.warning(
                            f"[ProgressiveExecutor] Could not find fill price in orderbook or tradebook, using attempt_price ₹{attempt_price:,.2f}. "
                            f"Orderbook data: {status_response}"
                        )

                    # OpenAlgo returns 'filledshares' for filled quantity
                    filled_lots = status_response.get('filledshares') or status_response.get('filled_quantity') or lots

                    result = ExecutionResult(
                        status=ExecutionStatus.EXECUTED,
                        execution_price=float(fill_price),
                        lots_filled=int(filled_lots),
                        order_id=order_id,
                        attempts=attempt_num
                    )
                    result.calculate_slippage(signal_price)

                    logger.info(
                        f"[ProgressiveExecutor] Order filled on attempt {attempt_num}: "
                        f"{filled_lots} lots @ ₹{fill_price:,.2f} "
                        f"(slippage: {result.slippage_pct:.2%})"
                    )
                    return result

                # Check for partial fill
                if status == 'PARTIAL' or status_response.get('filledshares', 0) > 0:
                    filled_lots = status_response.get('filledshares') or status_response.get('filled_quantity', 0)
                    remaining_lots = lots - filled_lots
                    # OpenAlgo/Zerodha field variations for fill price
                    avg_fill_price = (
                        status_response.get('averageprice') or
                        status_response.get('average_price') or
                        status_response.get('tradedprice') or
                        status_response.get('avgprice') or
                        status_response.get('fill_price') or
                        status_response.get('price') or
                        attempt_price
                    )

                    # Try tradebook for actual fill price if orderbook didn't have it
                    if avg_fill_price == attempt_price and order_id:
                        for tradebook_attempt in range(3):
                            if tradebook_attempt > 0:
                                time.sleep(1.0)
                            tradebook_price = self.openalgo.get_trade_fill_price(order_id)
                            if tradebook_price and tradebook_price != attempt_price:
                                avg_fill_price = tradebook_price
                                logger.info(
                                    f"[ProgressiveExecutor] Partial fill using tradebook price: ₹{avg_fill_price:,.2f}"
                                )
                                break

                    logger.info(
                        f"[ProgressiveExecutor] Partial fill on attempt {attempt_num}: "
                        f"{filled_lots}/{lots} lots, handling with strategy: {self.partial_fill_strategy.value}"
                    )

                    return self.handle_partial_fill(
                        order_id, filled_lots, remaining_lots, float(avg_fill_price), signal
                    )

            except Exception as e:
                logger.error(f"[ProgressiveExecutor] Error on attempt {attempt_num}: {e}")
                if order_id:
                    try:
                        self.cancel_order(order_id)
                    except Exception:
                        pass
                    order_id = None
                continue

        # All attempts failed - but FIRST check if any order actually went through
        # This handles the case where HTTP timeout occurred but order was executed at broker
        logger.warning(
            f"[ProgressiveExecutor] All {self.max_attempts} attempts failed, "
            f"checking orderbook for orphaned fills..."
        )

        # Determine the actual symbol we were trying to trade
        # Uses ExpiryCalendar for dynamic symbol construction (no hardcoded expiries)
        recovery_symbol = None
        try:
            from core.expiry_calendar import ExpiryCalendar
            from datetime import date
            expiry_cal = ExpiryCalendar()

            if signal.instrument == "GOLD_MINI":
                expiry = expiry_cal.get_expiry_after_rollover("GOLD_MINI", date.today())
                recovery_symbol = f"GOLDM{expiry.strftime('%d%b%y').upper()}FUT"
            elif signal.instrument == "COPPER":
                expiry = expiry_cal.get_expiry_after_rollover("COPPER", date.today())
                recovery_symbol = f"COPPER{expiry.strftime('%d%b%y').upper()}FUT"
            elif signal.instrument == "SILVER_MINI":
                expiry = expiry_cal.get_expiry_after_rollover("SILVER_MINI", date.today())
                recovery_symbol = f"SILVERM{expiry.strftime('%d%b%y').upper()}FUT"
            # Note: BANK_NIFTY uses synthetic futures (options), not recovered here
        except Exception as e:
            logger.error(
                f"[ProgressiveExecutor] Cannot determine symbol for recovery - "
                f"ExpiryCalendar error: {e}. Skipping orphan order check."
            )

        if recovery_symbol:
            # Check if order was actually filled despite our timeout/failures
            recovered_order = self.openalgo.find_recent_filled_order(
                symbol=recovery_symbol,
                action=action,
                quantity=lots,
                max_age_seconds=120  # Look for orders placed in last 2 minutes
            )

            if recovered_order:
                # Order was actually filled! Recovery successful.
                recovered_order_id = recovered_order.get('orderid')
                fill_price = (
                    recovered_order.get('averageprice') or
                    recovered_order.get('average_price') or
                    recovered_order.get('tradedprice') or
                    recovered_order.get('price') or
                    limit_price
                )
                filled_lots = int(
                    recovered_order.get('filledshares') or
                    recovered_order.get('filled_quantity') or
                    lots
                )

                logger.warning(
                    f"[ProgressiveExecutor] ⚠️ RECOVERY: Found orphaned filled order! "
                    f"Order {recovered_order_id} was filled despite timeout. "
                    f"{filled_lots} lots @ ₹{float(fill_price):,.2f}"
                )

                result = ExecutionResult(
                    status=ExecutionStatus.EXECUTED,
                    execution_price=float(fill_price),
                    lots_filled=int(filled_lots),
                    order_id=str(recovered_order_id),
                    attempts=self.max_attempts
                )
                result.calculate_slippage(signal_price)
                return result

        # Cancel any pending order we might have
        if order_id:
            try:
                self.cancel_order(order_id)
            except Exception as e:
                logger.error(f"[ProgressiveExecutor] Error cancelling order: {e}")

        return ExecutionResult(
            status=ExecutionStatus.REJECTED,
            rejection_reason=f"all_attempts_failed_{self.max_attempts}_attempts",
            order_id=order_id,
            attempts=self.max_attempts
        )


# =============================================================================
# SYNTHETIC FUTURES EXECUTOR - For Bank Nifty 2-Leg Execution
# =============================================================================

@dataclass
class LegExecutionResult:
    """Result of a single leg execution"""
    success: bool
    order_id: Optional[str] = None
    fill_price: Optional[float] = None
    filled_quantity: Optional[int] = None
    error: Optional[str] = None
    leg_type: str = ""  # "PE" or "CE"
    symbol: Optional[str] = None  # Actual symbol used


@dataclass
class SyntheticExecutionResult:
    """Result of synthetic futures execution (2 legs)"""
    status: ExecutionStatus
    pe_result: Optional[LegExecutionResult] = None
    ce_result: Optional[LegExecutionResult] = None
    rollback_performed: bool = False
    rollback_success: bool = False
    rejection_reason: Optional[str] = None
    notes: Optional[str] = None
    # Actual symbols executed (e.g., BANKNIFTY30DEC2560000PE, BANKNIFTY30DEC2560000CE)
    # These contain all info needed: instrument, expiry date, strike, option type
    pe_symbol: Optional[str] = None
    ce_symbol: Optional[str] = None
    # ATM strike used for synthetic futures (needed for price calculation)
    strike: Optional[int] = None

    def get_synthetic_price(self) -> Optional[float]:
        """
        Calculate synthetic futures price using correct formula.

        Synthetic Long Entry = Strike + CE_Premium - PE_Premium

        For ENTRY (SELL PE + BUY CE):
        - We SELL PE at market (receive premium, short position)
        - We BUY CE at market (pay premium, long position)
        - Net position = Long synthetic futures at (Strike + CE - PE)

        For EXIT (BUY PE + SELL CE):
        - We BUY PE to close short (pay premium)
        - We SELL CE to close long (receive premium)
        - Synthetic exit price = Strike + CE_received - PE_paid

        Returns:
            Synthetic futures price, or None if calculation not possible
        """
        if self.strike is None:
            logger.warning(
                "[SyntheticExecutionResult] Cannot calculate synthetic price: strike is None"
            )
            return None

        pe_price = self.pe_result.fill_price if self.pe_result else None
        ce_price = self.ce_result.fill_price if self.ce_result else None

        if pe_price is None or ce_price is None:
            logger.warning(
                f"[SyntheticExecutionResult] Cannot calculate synthetic price: "
                f"PE_price={'None' if pe_price is None else pe_price}, "
                f"CE_price={'None' if ce_price is None else ce_price}"
            )
            return None

        # Synthetic = Strike + CE - PE
        synthetic_price = self.strike + ce_price - pe_price

        # Edge case protection: synthetic price should never be negative
        if synthetic_price <= 0:
            logger.error(
                f"[SyntheticExecutionResult] INVALID synthetic price {synthetic_price:.2f} "
                f"(strike={self.strike}, CE={ce_price}, PE={pe_price}). Check option prices!"
            )
            return None

        return synthetic_price

    def to_execution_result(self, lots: int, signal_price: float) -> ExecutionResult:
        """Convert to standard ExecutionResult for compatibility"""
        if self.status == ExecutionStatus.EXECUTED:
            pe_price = self.pe_result.fill_price if self.pe_result else 0
            ce_price = self.ce_result.fill_price if self.ce_result else 0

            # Use correct synthetic futures price formula: Strike + CE - PE
            # Fallback to signal_price if strike not available
            synthetic_price = self.get_synthetic_price()

            if synthetic_price is not None:
                execution_price = synthetic_price
            else:
                execution_price = signal_price
                logger.warning(
                    f"[SyntheticExecutionResult] Using signal_price fallback ₹{signal_price:,.2f} "
                    f"(synthetic price calculation failed)"
                )

            result = ExecutionResult(
                status=ExecutionStatus.EXECUTED,
                execution_price=execution_price,
                lots_filled=lots,
                order_id=f"PE:{self.pe_result.order_id if self.pe_result else 'N/A'}|CE:{self.ce_result.order_id if self.ce_result else 'N/A'}",
                attempts=1,
                notes=f"Synthetic futures: strike={self.strike}, PE={pe_price}, CE={ce_price}, synthetic_price={execution_price:.2f}"
            )
            result.calculate_slippage(signal_price)
            return result
        else:
            return ExecutionResult(
                status=self.status,
                rejection_reason=self.rejection_reason or "synthetic_execution_failed",
                notes=self.notes
            )


class SyntheticFuturesExecutor:
    """
    Execute synthetic futures (Bank Nifty) with 2-leg execution and rollback.

    Synthetic Future = ATM PE Sell + ATM CE Buy

    Entry Long:  SELL PE (leg 1), then BUY CE (leg 2)
    Exit Long:   BUY PE (leg 1), then SELL CE (leg 2)

    CRITICAL: If leg 2 fails, MUST rollback leg 1 to prevent naked option exposure.
    """

    def __init__(
        self,
        openalgo_client,
        symbol_mapper=None,
        timeout_seconds: int = 30,
        poll_interval_seconds: float = 2.0
    ):
        """
        Initialize SyntheticFuturesExecutor.

        Args:
            openalgo_client: OpenAlgo API client
            symbol_mapper: SymbolMapper instance for symbol translation
            timeout_seconds: Timeout for each leg (default: 30s)
            poll_interval_seconds: Interval between status checks (default: 2s)
        """
        self.openalgo = openalgo_client
        self.symbol_mapper = symbol_mapper
        self.timeout_seconds = timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

        logger.info("[SyntheticFuturesExecutor] Initialized with rollback protection")

    def execute_entry(
        self,
        instrument: str,
        lots: int,
        current_price: float,
        reference_date=None
    ) -> SyntheticExecutionResult:
        """
        Execute synthetic futures ENTRY (Long).

        Legs:
        1. SELL PE (creates short put position)
        2. BUY CE (creates long call position)

        If leg 2 fails, rollback leg 1.

        Args:
            instrument: "BANK_NIFTY"
            lots: Number of lots
            current_price: Current index price for ATM calculation
            reference_date: Reference date for expiry calculation

        Returns:
            SyntheticExecutionResult
        """
        logger.info(
            f"[SyntheticFuturesExecutor] ENTRY: {instrument}, {lots} lots, "
            f"price={current_price:,.2f}"
        )

        # Get translated symbols
        if self.symbol_mapper is None:
            from core.symbol_mapper import SymbolMapper
            self.symbol_mapper = SymbolMapper()

        translated = self.symbol_mapper.translate(
            instrument=instrument,
            action="BUY",  # Entry
            current_price=current_price,
            reference_date=reference_date
        )

        if not translated.is_synthetic or len(translated.order_legs) != 2:
            return SyntheticExecutionResult(
                status=ExecutionStatus.REJECTED,
                rejection_reason=f"Expected synthetic futures with 2 legs, got {len(translated.order_legs)}"
            )

        pe_leg = translated.order_legs[0]  # PE
        ce_leg = translated.order_legs[1]  # CE

        logger.info(
            f"[SyntheticFuturesExecutor] Executing entry: "
            f"PE={pe_leg.symbol}({pe_leg.action}), CE={ce_leg.symbol}({ce_leg.action})"
        )

        # Calculate quantity
        lot_size = self.symbol_mapper.get_lot_size(instrument)
        quantity = lots * lot_size

        result = self._execute_two_legs(
            pe_leg=pe_leg,
            ce_leg=ce_leg,
            quantity=quantity,
            lots=lots,
            current_price=current_price
        )

        # Store the ATM strike used for synthetic price calculation
        result.strike = translated.atm_strike

        # Log synthetic price if execution succeeded
        if result.status == ExecutionStatus.EXECUTED:
            synthetic_price = result.get_synthetic_price()
            if synthetic_price:
                logger.info(
                    f"[SyntheticFuturesExecutor] Synthetic entry price: ₹{synthetic_price:,.2f} "
                    f"(strike={result.strike}, PE={result.pe_result.fill_price if result.pe_result else 'N/A'}, "
                    f"CE={result.ce_result.fill_price if result.ce_result else 'N/A'})"
                )

        return result

    def execute_exit(
        self,
        instrument: str,
        lots: int,
        current_price: float,
        pe_symbol: str = None,
        ce_symbol: str = None,
        reference_date=None
    ) -> SyntheticExecutionResult:
        """
        Execute synthetic futures EXIT (Close Long).

        Legs:
        1. BUY PE (closes short put)
        2. SELL CE (closes long call)

        If leg 2 fails, rollback leg 1.

        Args:
            instrument: "BANK_NIFTY"
            lots: Number of lots
            current_price: Current index price
            pe_symbol: Optional - use existing PE symbol (for closing same strike)
            ce_symbol: Optional - use existing CE symbol (for closing same strike)
            reference_date: Reference date for expiry calculation

        Returns:
            SyntheticExecutionResult
        """
        logger.info(
            f"[SyntheticFuturesExecutor] EXIT: {instrument}, {lots} lots, "
            f"price={current_price:,.2f}"
        )

        # Get translated symbols (or use provided ones)
        exit_strike = None

        if pe_symbol and ce_symbol:
            # Use provided symbols (closing at same strike as entry)
            from core.symbol_mapper import OrderLeg, ExchangeCode
            pe_leg = OrderLeg(
                symbol=pe_symbol,
                exchange=ExchangeCode.NFO.value,
                action="BUY",  # Close short put
                leg_type="PE"
            )
            ce_leg = OrderLeg(
                symbol=ce_symbol,
                exchange=ExchangeCode.NFO.value,
                action="SELL",  # Close long call
                leg_type="CE"
            )
            # Extract strike from symbol (e.g., BANKNIFTY30DEC2560000PE -> 60000)
            exit_strike = self._extract_strike_from_symbol(pe_symbol)
        else:
            # Calculate new ATM symbols
            if self.symbol_mapper is None:
                from core.symbol_mapper import SymbolMapper
                self.symbol_mapper = SymbolMapper()

            translated = self.symbol_mapper.translate(
                instrument=instrument,
                action="SELL",  # Exit
                current_price=current_price,
                reference_date=reference_date
            )

            if not translated.is_synthetic or len(translated.order_legs) != 2:
                return SyntheticExecutionResult(
                    status=ExecutionStatus.REJECTED,
                    rejection_reason=f"Expected synthetic futures with 2 legs"
                )

            pe_leg = translated.order_legs[0]
            ce_leg = translated.order_legs[1]
            exit_strike = translated.atm_strike

        logger.info(
            f"[SyntheticFuturesExecutor] Executing exit: "
            f"PE={pe_leg.symbol}({pe_leg.action}), CE={ce_leg.symbol}({ce_leg.action}), strike={exit_strike}"
        )

        # Calculate quantity
        if self.symbol_mapper:
            lot_size = self.symbol_mapper.get_lot_size(instrument)
        else:
            lot_size = 30  # Bank Nifty default (Dec 2025 onwards)
        quantity = lots * lot_size

        result = self._execute_two_legs(
            pe_leg=pe_leg,
            ce_leg=ce_leg,
            quantity=quantity,
            lots=lots,
            current_price=current_price
        )

        # Store the strike used for synthetic exit price calculation
        result.strike = exit_strike

        # Log synthetic exit price if execution succeeded
        if result.status == ExecutionStatus.EXECUTED:
            synthetic_price = result.get_synthetic_price()
            if synthetic_price:
                logger.info(
                    f"[SyntheticFuturesExecutor] Synthetic exit price: ₹{synthetic_price:,.2f} "
                    f"(strike={result.strike}, PE={result.pe_result.fill_price if result.pe_result else 'N/A'}, "
                    f"CE={result.ce_result.fill_price if result.ce_result else 'N/A'})"
                )

        return result

    def _execute_two_legs(
        self,
        pe_leg,
        ce_leg,
        quantity: int,
        lots: int,
        current_price: float
    ) -> SyntheticExecutionResult:
        """
        Execute two legs with rollback protection.

        CRITICAL: If leg 2 fails, MUST rollback leg 1.
        """
        pe_result = None
        ce_result = None

        # ============================
        # LEG 1: Execute PE
        # ============================
        logger.info(f"[SyntheticFuturesExecutor] Leg 1: {pe_leg.action} {pe_leg.symbol}")

        pe_result = self._execute_single_leg(
            symbol=pe_leg.symbol,
            exchange=pe_leg.exchange,
            action=pe_leg.action,
            quantity=quantity,
            leg_type="PE"
        )

        if not pe_result.success:
            logger.error(f"[SyntheticFuturesExecutor] Leg 1 (PE) FAILED: {pe_result.error}")
            return SyntheticExecutionResult(
                status=ExecutionStatus.REJECTED,
                pe_result=pe_result,
                rejection_reason=f"pe_leg_failed: {pe_result.error}"
            )

        logger.info(
            f"[SyntheticFuturesExecutor] Leg 1 (PE) SUCCESS: "
            f"order_id={pe_result.order_id}, price={pe_result.fill_price}"
        )

        # ============================
        # LEG 2: Execute CE
        # ============================
        logger.info(f"[SyntheticFuturesExecutor] Leg 2: {ce_leg.action} {ce_leg.symbol}")

        ce_result = self._execute_single_leg(
            symbol=ce_leg.symbol,
            exchange=ce_leg.exchange,
            action=ce_leg.action,
            quantity=quantity,
            leg_type="CE"
        )

        if not ce_result.success:
            logger.error(
                f"[SyntheticFuturesExecutor] Leg 2 (CE) FAILED: {ce_result.error}. "
                f"INITIATING ROLLBACK of Leg 1!"
            )

            # ============================
            # ROLLBACK LEG 1
            # ============================
            rollback_action = "BUY" if pe_leg.action == "SELL" else "SELL"
            logger.warning(
                f"[SyntheticFuturesExecutor] ROLLBACK: {rollback_action} {pe_leg.symbol}"
            )

            rollback_result = self._execute_single_leg(
                symbol=pe_leg.symbol,
                exchange=pe_leg.exchange,
                action=rollback_action,
                quantity=quantity,
                leg_type="PE_ROLLBACK"
            )

            if rollback_result.success:
                logger.info("[SyntheticFuturesExecutor] Rollback SUCCESS")
                return SyntheticExecutionResult(
                    status=ExecutionStatus.REJECTED,
                    pe_result=pe_result,
                    ce_result=ce_result,
                    rollback_performed=True,
                    rollback_success=True,
                    rejection_reason=f"ce_leg_failed_with_rollback: {ce_result.error}",
                    notes="PE leg rolled back successfully after CE leg failure"
                )
            else:
                # CRITICAL: Rollback failed - naked option exposure!
                logger.critical(
                    f"[SyntheticFuturesExecutor] CRITICAL: ROLLBACK FAILED! "
                    f"Naked {pe_leg.action} position on {pe_leg.symbol}! "
                    f"Manual intervention required!"
                )
                return SyntheticExecutionResult(
                    status=ExecutionStatus.REJECTED,
                    pe_result=pe_result,
                    ce_result=ce_result,
                    rollback_performed=True,
                    rollback_success=False,
                    rejection_reason=f"ce_leg_failed_rollback_failed: CRITICAL",
                    notes=f"CRITICAL: Naked {pe_leg.action} position! Manual intervention required!"
                )

        # ============================
        # BOTH LEGS SUCCESS
        # ============================
        logger.info(
            f"[SyntheticFuturesExecutor] Both legs SUCCESS: "
            f"PE order_id={pe_result.order_id}, CE order_id={ce_result.order_id}"
        )

        # Store symbols in leg results for reference
        pe_result.symbol = pe_leg.symbol
        ce_result.symbol = ce_leg.symbol

        return SyntheticExecutionResult(
            status=ExecutionStatus.EXECUTED,
            pe_result=pe_result,
            ce_result=ce_result,
            pe_symbol=pe_leg.symbol,
            ce_symbol=ce_leg.symbol
        )

    def _execute_single_leg(
        self,
        symbol: str,
        exchange: str,
        action: str,
        quantity: int,
        leg_type: str
    ) -> LegExecutionResult:
        """
        Execute a single leg order with aggressive LIMIT order chasing.

        Strategy:
        - Use LIMIT orders (NOT MARKET) to control slippage
        - Start with avg(best_bid, best_offer) price
        - Aggressively update price every 1-2 seconds
        - Use 5-10 rupee increments
        - 30 second timeout
        - NRML product type (overnight positions)
        - Max ~20 modifications (Zerodha limit is ~25)

        Args:
            symbol: OpenAlgo format symbol
            exchange: Exchange code (NFO, MCX)
            action: BUY or SELL
            quantity: Order quantity
            leg_type: "PE", "CE", or "PE_ROLLBACK"

        Returns:
            LegExecutionResult
        """
        # Configuration for aggressive order chasing
        PRICE_INCREMENT = 5.0  # ₹5 increments (per step, not cumulative)
        UPDATE_INTERVAL = 1.5  # Update every 1.5 seconds
        MAX_MODIFICATIONS = 20  # Stay under Zerodha's 25 limit
        MAX_CHASE_AMOUNT = 100.0  # Max ₹100 total chase from initial price

        try:
            # Get initial price from market depth
            initial_price = self._get_limit_price(symbol, action, exchange)
            if initial_price is None or initial_price <= 0:
                logger.error(f"[SyntheticFuturesExecutor] Failed to get price for {symbol}")
                return LegExecutionResult(
                    success=False,
                    error="failed_to_get_market_price",
                    leg_type=leg_type
                )

            current_price = initial_price
            logger.info(
                f"[SyntheticFuturesExecutor] {leg_type} starting: {action} {symbol} "
                f"@ ₹{current_price:.2f} (NRML LIMIT)"
            )

            # Place initial LIMIT order with NRML
            order_response = self.openalgo.place_order(
                symbol=symbol,
                action=action,
                quantity=quantity,
                order_type="LIMIT",
                price=current_price,
                exchange=exchange,
                product="NRML"  # NRML for overnight positions
            )

            if order_response.get('status') != 'success':
                return LegExecutionResult(
                    success=False,
                    error=f"order_rejected: {order_response.get('error', 'unknown')}",
                    leg_type=leg_type
                )

            order_id = order_response.get('orderid')
            if not order_id:
                return LegExecutionResult(
                    success=False,
                    error="no_order_id_returned",
                    leg_type=leg_type
                )

            # Aggressive order chasing loop
            start_time = time.time()
            modifications = 0
            modify_failures = 0  # Track consecutive modify failures
            total_chase = 0.0  # Track total price chase
            last_update_time = start_time
            last_logged_status = None

            while time.time() - start_time < self.timeout_seconds:
                try:
                    # Check order status
                    status_response = self.openalgo.get_order_status(order_id)
                    if not status_response:
                        logger.warning(f"[SyntheticFuturesExecutor] {leg_type}: No status response for order {order_id}")
                        time.sleep(0.5)
                        continue

                    # OpenAlgo uses 'order_status' field
                    status = (status_response.get('order_status') or status_response.get('status') or '').upper()

                    # Log status changes for debugging
                    if status != last_logged_status:
                        logger.debug(f"[SyntheticFuturesExecutor] {leg_type} order {order_id} status: {status}")
                        last_logged_status = status

                    if status in ['COMPLETE', 'FILLED']:
                        fill_price = status_response.get('fill_price') or status_response.get('price') or status_response.get('averageprice', 0) or current_price
                        filled_qty = status_response.get('filled_quantity') or status_response.get('quantity') or quantity

                        logger.info(
                            f"[SyntheticFuturesExecutor] {leg_type} FILLED: {filled_qty} @ ₹{fill_price:.2f} "
                            f"(modifications: {modifications})"
                        )

                        return LegExecutionResult(
                            success=True,
                            order_id=order_id,
                            fill_price=float(fill_price) if fill_price else current_price,
                            filled_quantity=int(filled_qty),
                            leg_type=leg_type
                        )

                    if status in ['REJECTED', 'CANCELLED']:
                        logger.warning(f"[SyntheticFuturesExecutor] {leg_type} order {status}: {status_response}")
                        return LegExecutionResult(
                            success=False,
                            order_id=order_id,
                            error=f"order_{status.lower()}",
                            leg_type=leg_type
                        )

                    # Order is OPEN/PENDING - check if we should modify the price
                    elapsed_since_update = time.time() - last_update_time
                    can_modify = (
                        elapsed_since_update >= UPDATE_INTERVAL and
                        modifications < MAX_MODIFICATIONS and
                        total_chase < MAX_CHASE_AMOUNT
                    )

                    if can_modify:
                        # Calculate new aggressive price (fixed increment, not cumulative)
                        new_chase = total_chase + PRICE_INCREMENT

                        # Min price based on exchange tick size (MCX: 1.0, NFO: 0.05)
                        min_tick = 1.0 if exchange.upper() == "MCX" else 0.05

                        # For BUY: increase price; for SELL: decrease price
                        if action == "BUY":
                            new_price = initial_price + new_chase
                        else:
                            new_price = max(min_tick, initial_price - new_chase)

                        # Round to tick size for MCX
                        new_price = self._round_to_tick(new_price, exchange)

                        # Try to modify the order (OpenAlgo requires all order details)
                        logger.info(
                            f"[SyntheticFuturesExecutor] {leg_type} MODIFYING order {order_id}: "
                            f"₹{current_price:.2f} → ₹{new_price:.2f} (chase: ₹{new_chase:.0f})"
                        )
                        try:
                            modify_response = self.openalgo.modify_order(
                                order_id=order_id,
                                new_price=new_price,
                                symbol=symbol,
                                action=action,
                                exchange=exchange,
                                quantity=quantity,
                                product="NRML"
                            )

                            if modify_response.get('status') == 'success':
                                modifications += 1
                                total_chase = new_chase
                                current_price = new_price
                                last_update_time = time.time()
                                modify_failures = 0  # Reset failure counter on success

                                logger.info(
                                    f"[SyntheticFuturesExecutor] {leg_type} price updated: "
                                    f"₹{new_price:.2f} (mod #{modifications}, chase: ₹{total_chase:.0f})"
                                )
                            else:
                                modify_failures += 1
                                error_msg = modify_response.get('error') or modify_response.get('message') or str(modify_response)

                                # "does not exist" usually means order was already filled
                                if 'does not exist' in error_msg.lower():
                                    logger.info(
                                        f"[SyntheticFuturesExecutor] {leg_type} order {order_id} modify returned 'does not exist' - "
                                        f"order likely already filled, checking status..."
                                    )
                                else:
                                    logger.warning(
                                        f"[SyntheticFuturesExecutor] {leg_type} modify FAILED order {order_id} ({modify_failures}x): {error_msg}"
                                    )

                                # Immediately re-check order status after modify failure
                                # (order might have filled, or be in an unexpected state)
                                try:
                                    recheck_status = self.openalgo.get_order_status(order_id)
                                    if recheck_status:
                                        recheck_state = (recheck_status.get('order_status') or recheck_status.get('status') or '').upper()
                                        logger.info(
                                            f"[SyntheticFuturesExecutor] {leg_type} status after modify fail: {recheck_state}"
                                        )

                                        # If order filled, return success immediately
                                        if recheck_state in ['COMPLETE', 'FILLED']:
                                            fill_price = recheck_status.get('fill_price') or recheck_status.get('averageprice', 0) or current_price
                                            filled_qty = recheck_status.get('filled_quantity') or quantity
                                            logger.info(
                                                f"[SyntheticFuturesExecutor] {leg_type} was FILLED (detected after modify fail): "
                                                f"{filled_qty} @ ₹{fill_price:.2f}"
                                            )
                                            return LegExecutionResult(
                                                success=True,
                                                order_id=order_id,
                                                fill_price=float(fill_price) if fill_price else current_price,
                                                filled_quantity=int(filled_qty),
                                                leg_type=leg_type
                                            )
                                except Exception as e:
                                    logger.warning(f"[SyntheticFuturesExecutor] {leg_type} status recheck failed: {e}")

                                # After 2 consecutive modify failures, convert to MARKET (reduced from 3)
                                if modify_failures >= 2:
                                    logger.error(
                                        f"[SyntheticFuturesExecutor] {leg_type}: {modify_failures} modify failures! "
                                        f"Converting to MARKET order immediately!"
                                    )
                                    # Cancel and place market (break to trigger chase_exhausted logic)
                                    total_chase = MAX_CHASE_AMOUNT  # Force chase exhausted
                                    last_update_time = time.time() - UPDATE_INTERVAL  # Force immediate check
                                    continue
                        except Exception as e:
                            modify_failures += 1
                            logger.warning(f"[SyntheticFuturesExecutor] {leg_type} order {order_id} modify exception ({modify_failures}x): {e}")

                            if modify_failures >= 2:
                                logger.error(
                                    f"[SyntheticFuturesExecutor] {leg_type}: {modify_failures} modify exceptions! "
                                    f"Converting to MARKET order immediately!"
                                )
                                total_chase = MAX_CHASE_AMOUNT
                                last_update_time = time.time() - UPDATE_INTERVAL
                                continue
                    elif elapsed_since_update >= UPDATE_INTERVAL:
                        # Max chase reached - convert to MARKET order
                        chase_exhausted = (modifications >= MAX_MODIFICATIONS or total_chase >= MAX_CHASE_AMOUNT)
                        if chase_exhausted:
                            logger.warning(
                                f"[SyntheticFuturesExecutor] {leg_type}: Chase exhausted "
                                f"(mods: {modifications}, chase: ₹{total_chase:.0f}). Converting to MARKET order!"
                            )

                            # Cancel existing limit order
                            try:
                                self.openalgo.cancel_order(order_id)
                                time.sleep(0.3)  # Brief pause for cancel to process
                            except Exception as e:
                                logger.warning(f"[SyntheticFuturesExecutor] Cancel before market failed: {e}")

                            # Place MARKET order
                            try:
                                market_response = self.openalgo.place_order(
                                    symbol=symbol,
                                    action=action,
                                    quantity=quantity,
                                    order_type="MARKET",
                                    price=0,
                                    exchange=exchange,
                                    product="NRML"
                                )

                                if market_response.get('status') == 'success':
                                    market_order_id = market_response.get('orderid')
                                    logger.info(f"[SyntheticFuturesExecutor] {leg_type} MARKET order placed: {market_order_id}")

                                    # Wait for market order fill (should be instant)
                                    time.sleep(1.0)
                                    market_status = self.openalgo.get_order_status(market_order_id)
                                    if market_status:
                                        mkt_status = (market_status.get('order_status') or market_status.get('status') or '').upper()
                                        if mkt_status in ['COMPLETE', 'FILLED']:
                                            fill_price = market_status.get('fill_price') or market_status.get('averageprice', 0)
                                            filled_qty = market_status.get('filled_quantity') or quantity
                                            logger.info(
                                                f"[SyntheticFuturesExecutor] {leg_type} MARKET FILLED: "
                                                f"{filled_qty} @ ₹{fill_price:.2f}"
                                            )
                                            return LegExecutionResult(
                                                success=True,
                                                order_id=market_order_id,
                                                fill_price=float(fill_price) if fill_price else current_price,
                                                filled_quantity=int(filled_qty),
                                                leg_type=leg_type
                                            )
                                else:
                                    logger.error(f"[SyntheticFuturesExecutor] {leg_type} MARKET order failed: {market_response}")
                            except Exception as e:
                                logger.error(f"[SyntheticFuturesExecutor] {leg_type} MARKET order error: {e}")

                            # If market order also failed, break out of loop
                            break

                except Exception as e:
                    logger.warning(f"[SyntheticFuturesExecutor] {leg_type} chase loop error: {e}")

                time.sleep(0.5)  # Check status every 500ms

            # Timeout - cancel limit order and place MARKET order
            logger.error(
                f"[SyntheticFuturesExecutor] {leg_type} TIMEOUT after {self.timeout_seconds}s! "
                f"Order {order_id} still not filled. Modifications: {modifications}, Chase: ₹{total_chase:.0f}. "
                f"Last status: {last_logged_status}. Converting to MARKET order..."
            )

            # Try to cancel limit order
            cancel_success = False
            try:
                self.openalgo.cancel_order(order_id)
                cancel_success = True
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"[SyntheticFuturesExecutor] Failed to cancel: {e}")

            # Place MARKET order to ensure fill
            try:
                market_response = self.openalgo.place_order(
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    order_type="MARKET",
                    price=0,
                    exchange=exchange,
                    product="NRML"
                )

                if market_response.get('status') == 'success':
                    market_order_id = market_response.get('orderid')
                    logger.info(f"[SyntheticFuturesExecutor] {leg_type} MARKET order placed: {market_order_id}")

                    # Wait for market order fill
                    time.sleep(1.0)
                    market_status = self.openalgo.get_order_status(market_order_id)
                    if market_status:
                        mkt_status = (market_status.get('order_status') or market_status.get('status') or '').upper()
                        if mkt_status in ['COMPLETE', 'FILLED']:
                            fill_price = market_status.get('fill_price') or market_status.get('averageprice', 0)
                            filled_qty = market_status.get('filled_quantity') or quantity
                            logger.info(
                                f"[SyntheticFuturesExecutor] {leg_type} MARKET FILLED: "
                                f"{filled_qty} @ ₹{fill_price:.2f}"
                            )
                            return LegExecutionResult(
                                success=True,
                                order_id=market_order_id,
                                fill_price=float(fill_price) if fill_price else current_price,
                                filled_quantity=int(filled_qty),
                                leg_type=leg_type
                            )
                else:
                    logger.error(f"[SyntheticFuturesExecutor] {leg_type} MARKET order failed: {market_response}")
            except Exception as e:
                logger.error(f"[SyntheticFuturesExecutor] {leg_type} MARKET order error: {e}")

            # CRITICAL: Check final status after cancel attempt
            # The order might have filled during our cancel attempt!
            time.sleep(0.5)  # Give broker time to process
            try:
                final_status = self.openalgo.get_order_status(order_id)
                if final_status:
                    status = (final_status.get('order_status') or final_status.get('status') or '').upper()

                    if status in ['COMPLETE', 'FILLED']:
                        # Order actually filled! Return success
                        fill_price = final_status.get('fill_price') or final_status.get('averageprice', 0) or current_price
                        filled_qty = final_status.get('filled_quantity') or final_status.get('quantity') or quantity

                        logger.info(
                            f"[SyntheticFuturesExecutor] {leg_type} FILLED (after timeout check): "
                            f"{filled_qty} @ ₹{fill_price:.2f}"
                        )

                        return LegExecutionResult(
                            success=True,
                            order_id=order_id,
                            fill_price=float(fill_price) if fill_price else current_price,
                            filled_quantity=int(filled_qty),
                            leg_type=leg_type
                        )

                    elif status in ['OPEN', 'PENDING', 'TRIGGER PENDING'] and not cancel_success:
                        # Order still open and cancel failed - DANGEROUS!
                        logger.critical(
                            f"[SyntheticFuturesExecutor] CRITICAL: {leg_type} order {order_id} "
                            f"is STILL OPEN after failed cancel! Manual intervention required!"
                        )
                        return LegExecutionResult(
                            success=False,
                            order_id=order_id,
                            error=f"timeout_cancel_failed_order_still_open",
                            leg_type=leg_type
                        )
            except Exception as e:
                logger.warning(f"[SyntheticFuturesExecutor] Could not verify final status: {e}")

            return LegExecutionResult(
                success=False,
                order_id=order_id,
                error=f"timeout_after_{modifications}_modifications",
                leg_type=leg_type
            )

        except Exception as e:
            logger.error(f"[SyntheticFuturesExecutor] {leg_type} execution error: {e}")
            return LegExecutionResult(
                success=False,
                error=str(e),
                leg_type=leg_type
            )

    def _round_to_tick(self, price: float, exchange: str = "NFO") -> float:
        """
        Round price to nearest tick size based on exchange.

        Tick sizes:
        - NFO (Options): 0.05
        - MCX (Gold Mini): 1.0

        Args:
            price: Raw price
            exchange: Exchange code (NFO, MCX)

        Returns:
            Price rounded to nearest tick
        """
        # Tick size varies by exchange
        if exchange.upper() == "MCX":
            tick_size = 1.0  # Gold Mini on MCX has tick size of 1
        else:
            tick_size = 0.05  # NFO options

        return round(round(price / tick_size) * tick_size, 2)

    def _extract_strike_from_symbol(self, symbol: str) -> Optional[int]:
        """
        Extract strike price from Bank Nifty option symbol.

        Symbol format: BANKNIFTY[DDMMMYY][STRIKE][PE/CE]
        Example: BANKNIFTY27JAN2660000CE -> 60000

        Note: The year (e.g., '26') immediately precedes the strike, so we need
        to properly separate them. Bank Nifty strikes are typically 5 digits
        (e.g., 60000, 59500) and never start with the year digits.

        Args:
            symbol: Option symbol string

        Returns:
            Strike price as integer, or None if extraction fails
        """
        import re
        try:
            # Pattern: BANKNIFTY + DD + MMM + YY + STRIKE + PE/CE
            # Example: BANKNIFTY27JAN2660000CE
            # The year is 2 digits (YY), followed by strike (typically 5 digits for BN)

            # First try: Match the full format with month name
            # BANKNIFTY27JAN2660000CE -> captures: day=27, month=JAN, year=26, strike=60000
            match = re.search(r'BANKNIFTY\d{1,2}[A-Z]{3}(\d{2})(\d{5})(PE|CE)$', symbol)
            if match:
                # Year is group 1, strike is group 2 (5 digits)
                strike = int(match.group(2))
                logger.debug(f"Extracted strike {strike} from {symbol} (5-digit pattern)")
                return strike

            # Second try: 6-digit strike (for very high index levels, unlikely for BN)
            match = re.search(r'BANKNIFTY\d{1,2}[A-Z]{3}(\d{2})(\d{6})(PE|CE)$', symbol)
            if match:
                strike = int(match.group(2))
                logger.debug(f"Extracted strike {strike} from {symbol} (6-digit pattern)")
                return strike

            # Fallback: Try weekly format BANKNIFTYWK[DDMMM][STRIKE][PE/CE]
            match = re.search(r'BANKNIFTY\d{1,2}[A-Z]{3}(\d{5,6})(PE|CE)$', symbol)
            if match:
                strike = int(match.group(1))
                logger.debug(f"Extracted strike {strike} from {symbol} (weekly pattern)")
                return strike

            logger.warning(f"Could not extract strike from symbol: {symbol}")
            return None
        except Exception as e:
            logger.warning(f"Failed to extract strike from {symbol}: {e}")
            return None

    def _get_limit_price(self, symbol: str, action: str, exchange: str = "NFO") -> Optional[float]:
        """
        Get initial limit price from market depth.

        Price = avg(best_bid, best_offer), rounded to tick size

        Args:
            symbol: OpenAlgo format symbol
            action: BUY or SELL
            exchange: Exchange code (NFO, MCX) for tick size calculation

        Returns:
            Initial limit price or None if unavailable
        """
        try:
            # Get quote/depth from OpenAlgo
            quote = self.openalgo.get_quote(symbol)

            if not quote:
                logger.warning(f"[SyntheticFuturesExecutor] No quote for {symbol}")
                return None

            # Try to get bid/offer from quote
            best_bid = quote.get('bid', 0) or quote.get('best_bid_price', 0) or quote.get('bidprice', 0)
            best_offer = quote.get('ask', 0) or quote.get('best_ask_price', 0) or quote.get('askprice', 0)
            ltp = quote.get('ltp', 0) or quote.get('last_price', 0)

            # Calculate average price and round to tick size (exchange-specific)
            if best_bid > 0 and best_offer > 0:
                avg_price = (best_bid + best_offer) / 2
                rounded_price = self._round_to_tick(avg_price, exchange)
                logger.info(
                    f"[SyntheticFuturesExecutor] Price for {symbol}: "
                    f"bid={best_bid:.2f}, ask={best_offer:.2f}, avg={avg_price:.2f}, rounded={rounded_price:.2f}"
                )
                return rounded_price
            elif ltp > 0:
                rounded_ltp = self._round_to_tick(ltp, exchange)
                logger.warning(f"[SyntheticFuturesExecutor] Using LTP for {symbol}: {ltp} → {rounded_ltp}")
                return rounded_ltp
            else:
                return None

        except Exception as e:
            logger.error(f"[SyntheticFuturesExecutor] Error getting price: {e}")
            return None
