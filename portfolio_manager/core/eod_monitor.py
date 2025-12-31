"""
EOD (End-of-Day) Monitor - State Management for Pre-Close Execution

Manages the state of incoming EOD_MONITOR signals from TradingView,
tracks latest indicator values, and coordinates with EODScheduler
for pre-close order execution.

ARCHITECTURE (v8.0):
- TradingView = SIGNAL GENERATOR ONLY (sends raw conditions/indicators every tick)
- Python Portfolio Manager = TOM BASSO POSITION SIZING ENGINE
- Capital is SHARED across Bank Nifty + Gold Mini
- Position sizing MUST use actual portfolio equity, NOT Pine Script estimates

Timeline (v8.0):
- T-5 min: TradingView starts sending EOD_MONITOR signals (every tick during 5-min window)
- T-30 sec: Final condition check + Python calculates position size + places order
- T-15 sec: Order tracking to completion
- T-0: Market closes

Note: 'sizing' field is deprecated in v8.0 - Python calculates position sizing.
Signals are ignored once execution has started to prevent overwhelming the executor.
"""
import logging
import threading
from datetime import datetime, timedelta, time
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field

from core.models import (
    EODMonitorSignal, EODConditions, EODIndicators,
    EODPositionStatus, EODSizing, SignalType, Signal
)
from core.config import PortfolioConfig

logger = logging.getLogger(__name__)


@dataclass
class EODExecutionState:
    """
    Tracks the state of EOD execution for a single instrument on a single day.
    Used to prevent duplicate executions and track execution status.
    """
    instrument: str
    date: str  # YYYY-MM-DD format

    # Latest signal from TradingView
    latest_signal: Optional[EODMonitorSignal] = None
    signal_received_at: Optional[datetime] = None

    # Execution tracking
    execution_scheduled: bool = False
    execution_started: bool = False
    execution_completed: bool = False
    execution_result: Optional[Dict] = None

    # Order tracking
    order_id: Optional[str] = None
    order_placed_at: Optional[datetime] = None
    order_filled: bool = False
    order_fill_price: Optional[float] = None

    # Signal that was executed (for deduplication with regular signals)
    executed_signal_type: Optional[SignalType] = None
    executed_fingerprint: Optional[str] = None

    def is_stale(self, max_age_seconds: int) -> bool:
        """Check if the latest signal is too old"""
        if not self.signal_received_at:
            return True
        age = (datetime.now() - self.signal_received_at).total_seconds()
        return age > max_age_seconds

    def mark_execution_started(self):
        """Mark that execution has started"""
        self.execution_started = True
        logger.info(f"[EOD] Execution started for {self.instrument}")

    def mark_execution_completed(self, result: Dict, signal_type: SignalType, fingerprint: str):
        """Mark that execution has completed"""
        self.execution_completed = True
        self.execution_result = result
        self.executed_signal_type = signal_type
        self.executed_fingerprint = fingerprint
        logger.info(f"[EOD] Execution completed for {self.instrument}: {result.get('status')}")


class EODMonitor:
    """
    Manages EOD_MONITOR signals and coordinates pre-close execution.

    Thread-safe for concurrent webhook handling.

    Usage:
        monitor = EODMonitor(config)

        # Called by webhook handler when EOD_MONITOR signal received
        monitor.update_signal(eod_signal)

        # Called by EODScheduler at T-45 sec
        if monitor.should_execute(instrument):
            signal = monitor.prepare_for_execution(instrument)
            # Pass signal to EODExecutor

        # Called after order completion
        monitor.mark_executed(instrument, result, fingerprint)

        # Called when regular bar-close signal arrives (for deduplication)
        if monitor.was_executed_at_eod(instrument, fingerprint):
            # Skip processing - already executed at EOD
    """

    def __init__(self, config: PortfolioConfig):
        """
        Initialize EOD Monitor.

        Args:
            config: Portfolio configuration with EOD settings
        """
        self.config = config
        self._lock = threading.Lock()

        # Current day's execution state per instrument
        # Key: instrument (e.g., "BANK_NIFTY")
        # Value: EODExecutionState
        self._states: Dict[str, EODExecutionState] = {}

        # Signal history for deduplication (last 24 hours)
        self._signal_history: List[Tuple[str, datetime]] = []

        logger.info("[EOD] EODMonitor initialized")

    def _get_today_str(self) -> str:
        """Get today's date as YYYY-MM-DD string"""
        return datetime.now().strftime("%Y-%m-%d")

    def _get_or_create_state(self, instrument: str) -> EODExecutionState:
        """Get or create execution state for instrument (for today)"""
        today = self._get_today_str()

        # Check if state exists and is for today
        if instrument in self._states:
            state = self._states[instrument]
            if state.date == today:
                return state
            # State is from previous day - create new one
            logger.info(f"[EOD] Creating new state for {instrument} (new day)")

        # Create new state
        state = EODExecutionState(instrument=instrument, date=today)
        self._states[instrument] = state
        return state

    def update_signal(self, signal: EODMonitorSignal) -> bool:
        """
        Update with latest EOD_MONITOR signal from TradingView.

        Thread-safe. Called by webhook handler.

        Args:
            signal: EOD_MONITOR signal with indicator values

        Returns:
            True if signal was accepted, False if rejected (stale, duplicate, etc.)
        """
        with self._lock:
            instrument = signal.instrument

            # Check if EOD is enabled for this instrument
            if not self.config.eod_instruments_enabled.get(instrument, False):
                logger.debug(f"[EOD] Ignoring signal - EOD disabled for {instrument}")
                return False

            # Get or create state
            state = self._get_or_create_state(instrument)

            # Check if already executed today
            if state.execution_completed:
                logger.debug(f"[EOD] Ignoring signal - already executed today for {instrument}")
                return False

            # Check if execution has started (ignore signals during execution)
            # This prevents overwhelming the executor with continuous tick-by-tick signals
            if state.execution_started:
                logger.debug(f"[EOD] Ignoring signal - execution in progress for {instrument}")
                return False

            # Check signal age
            signal_age = (datetime.now() - signal.timestamp).total_seconds()
            if signal_age > self.config.eod_max_signal_age_seconds:
                logger.warning(
                    f"[EOD] Rejecting stale signal for {instrument} "
                    f"(age: {signal_age:.1f}s > {self.config.eod_max_signal_age_seconds}s)"
                )
                return False

            # Update state with new signal
            state.latest_signal = signal
            state.signal_received_at = datetime.now()

            # Log signal details
            action = signal.get_signal_type_to_execute()
            conditions_met = signal.conditions.all_entry_conditions_met()
            # Handle Scout mode where position_status may be None
            in_position_str = str(signal.position_status.in_position) if signal.position_status else "None (Scout mode)"
            logger.info(
                f"[EOD] Signal updated for {instrument}: "
                f"price={signal.price:.2f}, "
                f"conditions_met={conditions_met}, "
                f"potential_action={action.value if action else 'None'}, "
                f"in_position={in_position_str}"
            )

            # Add to history for deduplication
            fingerprint = f"{instrument}:{signal.timestamp.isoformat()}"
            self._signal_history.append((fingerprint, datetime.now()))
            self._cleanup_history()

            return True

    def should_execute(self, instrument: str) -> bool:
        """
        Check if we should execute an EOD order for this instrument.

        Called by EODScheduler at T-45 sec (final check time).

        Args:
            instrument: Instrument to check

        Returns:
            True if we should proceed with execution
        """
        with self._lock:
            if instrument not in self._states:
                logger.debug(f"[EOD] No state for {instrument}")
                return False

            state = self._states[instrument]

            # Check if already executed
            if state.execution_completed:
                logger.debug(f"[EOD] Already executed today for {instrument}")
                return False

            # Check if execution already started
            if state.execution_started:
                logger.debug(f"[EOD] Execution already in progress for {instrument}")
                return False

            # Check if we have a valid signal
            if not state.latest_signal:
                logger.debug(f"[EOD] No signal available for {instrument}")
                return False

            # Check signal freshness
            if state.is_stale(self.config.eod_max_signal_age_seconds):
                logger.warning(f"[EOD] Signal is stale for {instrument}")
                return False

            # Check if there's an action to execute
            signal = state.latest_signal
            action = signal.get_signal_type_to_execute()
            if action is None:
                logger.debug(f"[EOD] No action to execute for {instrument}")
                return False

            logger.info(f"[EOD] Should execute {action.value} for {instrument}")
            return True

    def prepare_for_execution(self, instrument: str) -> Optional[Tuple[EODMonitorSignal, SignalType]]:
        """
        Prepare for EOD execution. Returns the signal and action type.

        Called by EODScheduler after should_execute() returns True.
        Marks execution as started to prevent duplicate execution.

        Args:
            instrument: Instrument to prepare

        Returns:
            Tuple of (EODMonitorSignal, SignalType) or None if cannot execute
        """
        with self._lock:
            if instrument not in self._states:
                return None

            state = self._states[instrument]

            if not state.latest_signal:
                return None

            signal = state.latest_signal
            action = signal.get_signal_type_to_execute()

            if action is None:
                return None

            # Mark execution started
            state.mark_execution_started()

            logger.info(
                f"[EOD] Prepared for execution: {instrument} {action.value} "
                f"@ {signal.price:.2f} (Python will calculate position size)"
            )

            return (signal, action)

    def convert_to_signal(
        self,
        eod_signal: EODMonitorSignal,
        action: SignalType,
        calculated_lots: int = 0,
        calculated_stop: float = 0.0
    ) -> Signal:
        """
        Convert EODMonitorSignal to regular Signal for execution.

        IMPORTANT: Python calculates position sizing using real portfolio equity.
        The `calculated_lots` and `calculated_stop` parameters MUST be provided
        by the caller (LiveTradingEngine/EODExecutor), NOT from Pine Script.

        Args:
            eod_signal: The EOD monitor signal with raw data
            action: The action type (BASE_ENTRY, PYRAMID, EXIT)
            calculated_lots: Position size calculated by Python (Tom Basso methodology)
            calculated_stop: Stop level calculated by Python

        Returns:
            Signal object compatible with LiveTradingEngine
        """
        # Determine position string
        if action == SignalType.BASE_ENTRY:
            position = "Long_1"
        elif action == SignalType.PYRAMID:
            # Safety check: position_status should be populated by eod_condition_check
            pyramid_count = eod_signal.position_status.pyramid_count if eod_signal.position_status else 0
            position = f"Long_{pyramid_count + 2}"
        else:  # EXIT
            position = "ALL"

        # Use Python-calculated values, fallback to supertrend for stop if not provided
        stop_level = calculated_stop if calculated_stop > 0 else eod_signal.indicators.supertrend

        # Create Signal with Python-calculated sizing
        return Signal(
            timestamp=eod_signal.timestamp,
            instrument=eod_signal.instrument,
            signal_type=action,
            position=position,
            price=eod_signal.price,
            stop=stop_level,
            suggested_lots=calculated_lots,  # From Python calculation, NOT Pine Script
            atr=eod_signal.indicators.atr,
            er=eod_signal.indicators.er,
            supertrend=eod_signal.indicators.supertrend,
            roc=eod_signal.indicators.roc,
            reason="EOD_PRE_CLOSE" if action == SignalType.EXIT else None
        )

    def mark_executed(
        self,
        instrument: str,
        result: Dict,
        fingerprint: str,
        signal_type: SignalType
    ):
        """
        Mark EOD execution as completed.

        Called by EODExecutor after order is filled or execution fails.

        Args:
            instrument: Instrument that was executed
            result: Execution result dict
            fingerprint: Unique fingerprint for deduplication
            signal_type: Type of signal that was executed
        """
        with self._lock:
            if instrument not in self._states:
                return

            state = self._states[instrument]
            state.mark_execution_completed(result, signal_type, fingerprint)

    def mark_order_placed(self, instrument: str, order_id: str):
        """Mark that an order has been placed"""
        with self._lock:
            if instrument not in self._states:
                return

            state = self._states[instrument]
            state.order_id = order_id
            state.order_placed_at = datetime.now()
            logger.info(f"[EOD] Order placed for {instrument}: {order_id}")

    def mark_order_filled(self, instrument: str, fill_price: float):
        """Mark that an order has been filled"""
        with self._lock:
            if instrument not in self._states:
                return

            state = self._states[instrument]
            state.order_filled = True
            state.order_fill_price = fill_price
            logger.info(f"[EOD] Order filled for {instrument} @ {fill_price:.2f}")

    def was_executed_at_eod(
        self,
        instrument: str,
        fingerprint: str,
        signal_type: Optional[SignalType] = None,
        grace_period_minutes: int = 30
    ) -> bool:
        """
        Check if a signal was already executed at EOD.

        Used for deduplication when regular bar-close signal arrives.

        Timeline for MCX Gold Mini (winter):
        - EOD execution: ~23:54:30 (30 sec before 23:55 close)
        - Bar-close signal: 23:55:00 (when candle closes)
        - Grace period ensures bar-close signal within 30 mins of EOD is blocked

        Args:
            instrument: Instrument to check
            fingerprint: Signal fingerprint to check
            signal_type: Type of signal being checked (for type-specific dedup)
            grace_period_minutes: Minutes after EOD execution to still consider as duplicate

        Returns:
            True if this signal (or equivalent) was executed at EOD
        """
        with self._lock:
            if instrument not in self._states:
                return False

            state = self._states[instrument]

            # Check if execution completed
            if not state.execution_completed:
                return False

            # Check if within grace period
            # EOD execution at 23:54:30 should block bar-close at 23:55:00
            if state.order_placed_at:
                minutes_since_execution = (datetime.now() - state.order_placed_at).total_seconds() / 60
                if minutes_since_execution > grace_period_minutes:
                    logger.debug(
                        f"[EOD] EOD execution too old ({minutes_since_execution:.1f}m > {grace_period_minutes}m), "
                        f"not blocking signal for {instrument}"
                    )
                    return False
            else:
                # No order_placed_at, fall back to same-day check
                today = self._get_today_str()
                if state.date != today:
                    return False

            # Check signal type match (if provided)
            # Only deduplicate same signal type (e.g., PYRAMID at EOD blocks bar-close PYRAMID)
            if signal_type and state.executed_signal_type:
                if signal_type != state.executed_signal_type:
                    logger.debug(
                        f"[EOD] Signal type mismatch: EOD executed {state.executed_signal_type.value}, "
                        f"incoming is {signal_type.value} - not blocking"
                    )
                    return False

            # Execution was completed recently - the regular signal should be skipped
            logger.info(
                f"[EOD] Blocking duplicate signal for {instrument}: "
                f"EOD executed {state.executed_signal_type.value if state.executed_signal_type else 'unknown'} "
                f"at {state.order_placed_at}, incoming fingerprint: {fingerprint}"
            )
            return True

    def get_latest_signal(self, instrument: str) -> Optional[EODMonitorSignal]:
        """Get the latest EOD_MONITOR signal for an instrument"""
        with self._lock:
            if instrument not in self._states:
                return None
            return self._states[instrument].latest_signal

    def get_execution_state(self, instrument: str) -> Optional[EODExecutionState]:
        """Get the current execution state for an instrument"""
        with self._lock:
            return self._states.get(instrument)

    def get_active_instruments(self) -> List[str]:
        """Get list of instruments with active EOD monitoring"""
        with self._lock:
            today = self._get_today_str()
            return [
                inst for inst, state in self._states.items()
                if state.date == today and not state.execution_completed
            ]

    def is_in_eod_window(self, instrument: str) -> bool:
        """
        Check if we're currently in the EOD monitoring window for an instrument.

        Args:
            instrument: Instrument to check

        Returns:
            True if current time is within EOD monitoring window
        """
        # Use dynamic close time (handles MCX seasonal timing)
        close_time_str = self.config.get_market_close_time(instrument)
        if not close_time_str:
            return False

        # Parse close time
        hour, minute = map(int, close_time_str.split(':'))
        close_time = time(hour, minute)

        # Calculate monitoring start time
        start_minutes = self.config.eod_monitoring_start_minutes
        now = datetime.now()

        # Create datetime for today's close time
        close_datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        start_datetime = close_datetime - timedelta(minutes=start_minutes)

        # Check if current time is in window
        return start_datetime <= now < close_datetime

    def get_seconds_to_close(self, instrument: str) -> Optional[int]:
        """
        Get seconds until market close for an instrument.

        Args:
            instrument: Instrument to check

        Returns:
            Seconds until close, or None if not applicable
        """
        # Use dynamic close time (handles MCX seasonal timing)
        close_time_str = self.config.get_market_close_time(instrument)
        if not close_time_str:
            return None

        hour, minute = map(int, close_time_str.split(':'))
        now = datetime.now()
        close_datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        # If close time has passed, return None
        if now >= close_datetime:
            return None

        return int((close_datetime - now).total_seconds())

    def _cleanup_history(self):
        """Remove old entries from signal history (older than 24 hours)"""
        cutoff = datetime.now() - timedelta(hours=24)
        self._signal_history = [
            (fp, ts) for fp, ts in self._signal_history
            if ts > cutoff
        ]

    def reset_for_testing(self):
        """Reset all state (for testing purposes only)"""
        with self._lock:
            self._states.clear()
            self._signal_history.clear()
            logger.info("[EOD] State reset for testing")
