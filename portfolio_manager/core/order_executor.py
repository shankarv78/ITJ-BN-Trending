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
        limit_price: float
    ) -> ExecutionResult:
        """
        Execute order using this strategy
        
        NOTE: This method blocks with time.sleep().
        For async systems, wrap in asyncio.run_in_executor() or use AsyncOrderExecutor.
        
        Args:
            signal: Trading signal
            lots: Number of lots to execute
            limit_price: Limit price for order
            
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
        if "GOLD" in instrument.upper():
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
            instrument: Trading symbol
            action: BUY or SELL
            quantity: Order quantity
            order_type: LIMIT or MARKET
            price: Limit price (if LIMIT)

        Returns:
            Order response dictionary
        """
        # Determine exchange based on instrument
        if "GOLD" in instrument.upper():
            exchange = "MCX"
        else:
            exchange = "NFO"  # Bank Nifty and other NSE derivatives

        return self.openalgo.place_order(
            symbol=instrument,
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
    
    def modify_order(self, order_id: str, new_price: float) -> Dict:
        """
        Modify existing order price
        
        Args:
            order_id: Order ID
            new_price: New limit price
            
        Returns:
            Modification response
        """
        if hasattr(self.openalgo, 'modify_order'):
            return self.openalgo.modify_order(order_id, new_price)
        else:
            # Fallback: cancel and place new order
            self.cancel_order(order_id)
            # Note: This is a simplified fallback - real implementation would need
            # to preserve order details (instrument, action, quantity)
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
        limit_price: float
    ) -> ExecutionResult:
        """
        Execute order with simple limit strategy
        
        NOTE: This method blocks with time.sleep() during order status polling.
        Designed for synchronous use in live/engine.py.
        
        Args:
            signal: Trading signal
            lots: Number of lots
            limit_price: Limit price
            
        Returns:
            ExecutionResult
        """
        logger.info(
            f"[SimpleLimitExecutor] Executing {signal.signal_type.value} order: "
            f"{lots} lots @ ₹{limit_price:,.2f}"
        )
        
        # Determine action (BUY for long positions)
        action = "BUY"  # System is LONG-only
        
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
                    fill_price = status_response.get('fill_price') or status_response.get('price') or limit_price
                    filled_lots = status_response.get('filled_lots') or status_response.get('lots') or lots
                    
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
                    filled_lots = status_response.get('filled_lots', 0)
                    remaining_lots = status_response.get('remaining_lots', lots - filled_lots)
                    avg_fill_price = status_response.get('avg_fill_price') or limit_price
                    
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
    
    Improves price progressively (3-4 attempts: +0%, +0.5%, +1.0%, +1.5%)
    with hard slippage limit (2%). Balances fill probability with slippage control.
    """
    
    def __init__(
        self,
        openalgo_client,
        max_attempts: int = 4,
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
            max_attempts: Maximum price improvement attempts (default: 4)
            attempt_intervals: Seconds to wait per attempt (default: [10, 10, 10, 10])
            improvement_steps: Price improvement percentages (default: [0, 0.005, 0.01, 0.015])
            hard_slippage_limit: Maximum total slippage (default: 2%)
            partial_fill_strategy: Strategy for handling partial fills (default: CANCEL_REMAINDER)
            partial_fill_wait_timeout: Timeout for WAIT_FOR_FILL strategy (default: 30s)
        """
        super().__init__(openalgo_client, partial_fill_strategy, partial_fill_wait_timeout)
        self.max_attempts = max_attempts
        self.attempt_intervals = attempt_intervals or [10.0, 10.0, 10.0, 10.0]
        self.improvement_steps = improvement_steps or [0.0, 0.005, 0.01, 0.015]
        self.hard_slippage_limit = hard_slippage_limit
        
        # Ensure we have enough intervals and steps
        if len(self.attempt_intervals) < self.max_attempts:
            self.attempt_intervals.extend([10.0] * (self.max_attempts - len(self.attempt_intervals)))
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
        limit_price: float
    ) -> ExecutionResult:
        """
        Execute order with progressive price improvement
        
        NOTE: This method blocks with time.sleep() during order status polling.
        Designed for synchronous use in live/engine.py.
        
        Args:
            signal: Trading signal
            lots: Number of lots
            limit_price: Initial limit price (usually broker price)
            
        Returns:
            ExecutionResult
        """
        logger.info(
            f"[ProgressiveExecutor] Executing {signal.signal_type.value} order: "
            f"{lots} lots @ ₹{limit_price:,.2f} (signal: ₹{signal.price:,.2f})"
        )
        
        action = "BUY"  # System is LONG-only
        order_id = None
        signal_price = signal.price
        
        # Attempt progressive price improvement
        for attempt in range(self.max_attempts):
            attempt_num = attempt + 1
            improvement_pct = self.improvement_steps[attempt]
            attempt_price = limit_price * (1 + improvement_pct)
            
            # Check hard slippage limit
            slippage_vs_signal = (attempt_price - signal_price) / signal_price
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
            
            logger.info(
                f"[ProgressiveExecutor] Attempt {attempt_num}/{self.max_attempts}: "
                f"Price ₹{attempt_price:,.2f} (+{improvement_pct:.2%} vs limit, "
                f"+{slippage_vs_signal:.2%} vs signal)"
            )
            
            try:
                if order_id and attempt > 0:
                    # Modify existing order
                    modify_response = self.modify_order(order_id, attempt_price)
                    if modify_response.get('status') != 'success':
                        logger.warning(
                            f"[ProgressiveExecutor] Order modification failed: {modify_response}"
                        )
                        # Continue to next attempt or cancel
                        try:
                            self.cancel_order(order_id)
                        except Exception:
                            pass
                        order_id = None
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
                status = status_response.get('status', '').upper()
                fill_status = status_response.get('fill_status', '').upper()
                
                if status in ['COMPLETE', 'FILLED'] or fill_status == 'COMPLETE':
                    fill_price = status_response.get('fill_price') or status_response.get('price') or attempt_price
                    filled_lots = status_response.get('filled_lots') or status_response.get('lots') or lots
                    
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
                if fill_status == 'PARTIAL':
                    filled_lots = status_response.get('filled_lots', 0)
                    remaining_lots = status_response.get('remaining_lots', lots - filled_lots)
                    avg_fill_price = status_response.get('avg_fill_price') or attempt_price
                    
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
        
        # All attempts failed - cancel order
        if order_id:
            logger.warning(
                f"[ProgressiveExecutor] All {self.max_attempts} attempts failed, cancelling order"
            )
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

