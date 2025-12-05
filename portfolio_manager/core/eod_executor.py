"""
EOD (End-of-Day) Executor - Order Execution for Pre-Close Trading

Handles order placement and tracking specifically for EOD pre-close execution.
Features:
- Tight timeouts (10 seconds default)
- Limit order with market fallback
- Order tracking with polling
- Compatible with existing execution result types

Timeline:
- T-30 sec: Place limit order (LTP + buffer)
- T-15 sec: Track order, fallback to market if not filled
- T-0: Market closes
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from core.models import (
    Signal, SignalType, EODMonitorSignal,
    EODConditions, EODIndicators, EODPositionStatus, EODSizing
)
from core.config import PortfolioConfig
from core.order_executor import ExecutionResult, ExecutionStatus

logger = logging.getLogger(__name__)


class EODExecutionPhase(Enum):
    """Phases of EOD execution"""
    CONDITION_CHECK = "condition_check"
    ORDER_PLACEMENT = "order_placement"
    ORDER_TRACKING = "order_tracking"
    FALLBACK = "fallback"
    COMPLETE = "complete"


@dataclass
class EODExecutionContext:
    """
    Context for tracking an EOD execution attempt.
    Carries state through the execution phases.
    """
    instrument: str
    phase: EODExecutionPhase = EODExecutionPhase.CONDITION_CHECK
    signal: Optional[EODMonitorSignal] = None
    signal_type: Optional[SignalType] = None
    converted_signal: Optional[Signal] = None

    # Execution state
    order_id: Optional[str] = None
    limit_price: Optional[float] = None
    lots: int = 0

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Results
    success: bool = False
    execution_price: Optional[float] = None
    filled_lots: int = 0
    fallback_used: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging/storage"""
        return {
            'instrument': self.instrument,
            'phase': self.phase.value,
            'signal_type': self.signal_type.value if self.signal_type else None,
            'order_id': self.order_id,
            'limit_price': self.limit_price,
            'lots': self.lots,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'success': self.success,
            'execution_price': self.execution_price,
            'filled_lots': self.filled_lots,
            'fallback_used': self.fallback_used,
            'error': self.error
        }


class EODExecutor:
    """
    EOD-specific order executor with tight timeouts.

    Designed for pre-close execution where timing is critical.
    Uses limit orders with optional market fallback.

    Usage:
        executor = EODExecutor(config, openalgo_client)

        # Step 1: Condition check (T-45 sec)
        context = executor.prepare_execution(instrument, eod_signal, signal_type)

        # Step 2: Place order (T-30 sec)
        context = executor.execute_order(context)

        # Step 3: Track order (T-15 sec)
        context = executor.track_order(context)

        # Check result
        if context.success:
            print(f"Filled {context.filled_lots} lots @ {context.execution_price}")
    """

    def __init__(self, config: PortfolioConfig, openalgo_client):
        """
        Initialize EOD Executor.

        Args:
            config: Portfolio configuration with EOD settings
            openalgo_client: OpenAlgo API client for order operations
        """
        self.config = config
        self.openalgo = openalgo_client

        # Execution parameters from config
        self.order_timeout = config.eod_order_timeout
        self.limit_buffer_pct = config.eod_limit_buffer_pct
        self.fallback_to_market = config.eod_fallback_to_market
        self.tracking_poll_interval = config.eod_tracking_poll_interval

        logger.info(
            f"[EOD-Executor] Initialized: timeout={self.order_timeout}s, "
            f"buffer={self.limit_buffer_pct}%, fallback={self.fallback_to_market}"
        )

    def prepare_execution(
        self,
        instrument: str,
        eod_signal: EODMonitorSignal,
        signal_type: SignalType
    ) -> EODExecutionContext:
        """
        Prepare execution context (Phase 1: Condition Check).

        Validates signal and prepares execution context.
        Called at T-45 sec.

        Args:
            instrument: Trading instrument
            eod_signal: EOD monitor signal with conditions and sizing
            signal_type: Type of signal (BASE_ENTRY, PYRAMID, EXIT)

        Returns:
            EODExecutionContext ready for order placement
        """
        context = EODExecutionContext(
            instrument=instrument,
            phase=EODExecutionPhase.CONDITION_CHECK,
            signal=eod_signal,
            signal_type=signal_type,
            started_at=datetime.now()
        )

        # Validate signal
        if signal_type == SignalType.BASE_ENTRY:
            if not eod_signal.conditions.all_entry_conditions_met():
                context.error = "Entry conditions not met"
                logger.warning(f"[EOD-Executor] {instrument}: {context.error}")
                return context

        elif signal_type == SignalType.EXIT:
            if not eod_signal.should_execute_exit():
                context.error = "Exit conditions not met"
                logger.warning(f"[EOD-Executor] {instrument}: {context.error}")
                return context

        # Get sizing
        context.lots = eod_signal.sizing.suggested_lots
        if context.lots <= 0:
            context.error = "Invalid lot size"
            logger.warning(f"[EOD-Executor] {instrument}: {context.error}")
            return context

        # Calculate limit price with buffer
        base_price = eod_signal.price
        if signal_type in [SignalType.BASE_ENTRY, SignalType.PYRAMID]:
            # Buy order: LTP + buffer (more aggressive)
            context.limit_price = base_price * (1 + self.limit_buffer_pct / 100)
        else:
            # Sell order: LTP - buffer (more aggressive)
            context.limit_price = base_price * (1 - self.limit_buffer_pct / 100)

        # Round to tick size (assuming 0.05 for now, could be configurable)
        context.limit_price = round(context.limit_price, 2)

        context.phase = EODExecutionPhase.ORDER_PLACEMENT

        logger.info(
            f"[EOD-Executor] {instrument}: Prepared {signal_type.value}, "
            f"lots={context.lots}, limit={context.limit_price:.2f}"
        )

        return context

    def execute_order(self, context: EODExecutionContext) -> EODExecutionContext:
        """
        Place the order (Phase 2: Order Placement).

        Places a limit order and returns updated context.
        Called at T-30 sec.

        Args:
            context: Execution context from prepare_execution()

        Returns:
            Updated context with order_id
        """
        if context.phase != EODExecutionPhase.ORDER_PLACEMENT:
            context.error = f"Invalid phase for execution: {context.phase.value}"
            logger.warning(f"[EOD-Executor] {context.error}")
            return context

        if context.error:
            logger.warning(f"[EOD-Executor] Skipping execution due to error: {context.error}")
            return context

        try:
            # Determine action
            if context.signal_type in [SignalType.BASE_ENTRY, SignalType.PYRAMID]:
                action = "BUY"
            else:
                action = "SELL"

            # Place limit order
            logger.info(
                f"[EOD-Executor] Placing {action} order for {context.instrument}: "
                f"{context.lots} lots @ {context.limit_price:.2f}"
            )

            order_response = self.openalgo.place_order(
                symbol=context.instrument,
                action=action,
                quantity=context.lots,
                order_type="LIMIT",
                price=context.limit_price
            )

            if order_response.get('status') == 'success':
                context.order_id = order_response.get('orderid')
                context.phase = EODExecutionPhase.ORDER_TRACKING
                logger.info(f"[EOD-Executor] Order placed: {context.order_id}")
            else:
                context.error = f"Order placement failed: {order_response.get('error', 'unknown')}"
                logger.error(f"[EOD-Executor] {context.error}")

        except Exception as e:
            context.error = f"Order placement exception: {str(e)}"
            logger.error(f"[EOD-Executor] {context.error}", exc_info=True)

        return context

    def track_order(self, context: EODExecutionContext) -> EODExecutionContext:
        """
        Track order to completion (Phase 3: Order Tracking).

        Polls order status and handles fallback to market if needed.
        Called at T-15 sec.

        Args:
            context: Execution context with order_id

        Returns:
            Updated context with execution result
        """
        if context.phase != EODExecutionPhase.ORDER_TRACKING:
            context.error = f"Invalid phase for tracking: {context.phase.value}"
            logger.warning(f"[EOD-Executor] {context.error}")
            return context

        if not context.order_id:
            context.error = "No order_id to track"
            logger.warning(f"[EOD-Executor] {context.error}")
            return context

        start_time = time.time()
        poll_count = 0

        while time.time() - start_time < self.order_timeout:
            poll_count += 1

            try:
                status = self.openalgo.get_order_status(context.order_id)

                fill_status = status.get('fill_status', status.get('status', ''))

                if fill_status == 'COMPLETE':
                    # Order fully filled
                    context.success = True
                    context.execution_price = status.get('fill_price', context.limit_price)
                    context.filled_lots = status.get('filled_lots', context.lots)
                    context.phase = EODExecutionPhase.COMPLETE
                    context.completed_at = datetime.now()

                    logger.info(
                        f"[EOD-Executor] Order filled: {context.instrument} "
                        f"{context.filled_lots} lots @ {context.execution_price:.2f}"
                    )
                    return context

                elif fill_status in ['REJECTED', 'CANCELLED']:
                    context.error = f"Order {fill_status}: {status.get('reason', 'unknown')}"
                    logger.warning(f"[EOD-Executor] {context.error}")
                    break

                # Still pending, continue polling
                time.sleep(self.tracking_poll_interval)

            except Exception as e:
                logger.warning(f"[EOD-Executor] Status poll error: {e}")
                time.sleep(self.tracking_poll_interval)

        # Timeout reached - try market fallback
        if self.fallback_to_market and not context.success:
            context = self._execute_market_fallback(context)

        if not context.success:
            context.error = context.error or "Order tracking timeout"
            context.phase = EODExecutionPhase.COMPLETE
            context.completed_at = datetime.now()

        return context

    def _execute_market_fallback(self, context: EODExecutionContext) -> EODExecutionContext:
        """
        Fallback to market order if limit not filled.

        Args:
            context: Current execution context

        Returns:
            Updated context with fallback result
        """
        logger.warning(f"[EOD-Executor] {context.instrument}: Limit timeout, using market fallback")
        context.phase = EODExecutionPhase.FALLBACK
        context.fallback_used = True

        try:
            # Cancel existing limit order
            if context.order_id:
                try:
                    self.openalgo.cancel_order(context.order_id)
                    logger.info(f"[EOD-Executor] Cancelled limit order: {context.order_id}")
                except Exception as e:
                    logger.warning(f"[EOD-Executor] Cancel failed: {e}")

            # Determine action
            if context.signal_type in [SignalType.BASE_ENTRY, SignalType.PYRAMID]:
                action = "BUY"
            else:
                action = "SELL"

            # Place market order
            order_response = self.openalgo.place_order(
                symbol=context.instrument,
                action=action,
                quantity=context.lots,
                order_type="MARKET",
                price=0  # Market order
            )

            if order_response.get('status') == 'success':
                market_order_id = order_response.get('orderid')

                # Brief wait for market order fill
                time.sleep(2)

                status = self.openalgo.get_order_status(market_order_id)
                if status.get('fill_status', status.get('status', '')) == 'COMPLETE':
                    context.success = True
                    context.order_id = market_order_id
                    context.execution_price = status.get('fill_price', 0)
                    context.filled_lots = status.get('filled_lots', context.lots)

                    logger.info(
                        f"[EOD-Executor] Market fallback filled: {context.instrument} "
                        f"{context.filled_lots} lots @ {context.execution_price:.2f}"
                    )
                else:
                    context.error = f"Market order not filled: {status.get('status')}"
            else:
                context.error = f"Market order failed: {order_response.get('error')}"

        except Exception as e:
            context.error = f"Market fallback exception: {str(e)}"
            logger.error(f"[EOD-Executor] {context.error}", exc_info=True)

        return context

    def execute_full_flow(
        self,
        instrument: str,
        eod_signal: EODMonitorSignal,
        signal_type: SignalType
    ) -> EODExecutionContext:
        """
        Execute the complete EOD flow in one call.

        Combines prepare_execution, execute_order, and track_order.
        Use this for testing or when phases don't need to be separated.

        Args:
            instrument: Trading instrument
            eod_signal: EOD monitor signal
            signal_type: Type of signal

        Returns:
            Final EODExecutionContext with execution result
        """
        # Phase 1: Prepare
        context = self.prepare_execution(instrument, eod_signal, signal_type)
        if context.error:
            return context

        # Phase 2: Execute
        context = self.execute_order(context)
        if context.error or not context.order_id:
            return context

        # Phase 3: Track
        context = self.track_order(context)

        return context

    def to_execution_result(self, context: EODExecutionContext) -> ExecutionResult:
        """
        Convert EODExecutionContext to standard ExecutionResult.

        For compatibility with existing engine metrics.

        Args:
            context: EOD execution context

        Returns:
            ExecutionResult compatible with existing code
        """
        if context.success:
            status = ExecutionStatus.EXECUTED
        elif context.error and 'timeout' in context.error.lower():
            status = ExecutionStatus.TIMEOUT
        elif context.filled_lots > 0 and context.filled_lots < context.lots:
            status = ExecutionStatus.PARTIAL
        else:
            status = ExecutionStatus.REJECTED

        result = ExecutionResult(
            status=status,
            execution_price=context.execution_price,
            lots_filled=context.filled_lots,
            rejection_reason=context.error,
            order_id=context.order_id,
            notes=f"EOD execution, fallback={'yes' if context.fallback_used else 'no'}"
        )

        # Calculate slippage if we have signal price
        if context.signal and context.execution_price:
            result.calculate_slippage(context.signal.price)

        return result
