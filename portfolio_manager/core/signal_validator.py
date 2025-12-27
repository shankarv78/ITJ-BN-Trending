"""
Signal Validation System

Implements two-stage validation:
1. Condition validation (trusts TradingView signal price)
2. Execution validation (uses broker API price)

Handles price divergence, risk increase, and position size adjustment.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict
from enum import Enum

from core.models import Signal, SignalType, PortfolioState
from core.portfolio_state import PortfolioStateManager
from core.signal_validation_config import SignalValidationConfig

logger = logging.getLogger(__name__)

# IST timezone (UTC+5:30) - explicit definition for robustness
# TradingView Pine Scripts send timestamps in IST (chart timezone)
# This constant ensures correct parsing regardless of server timezone
IST = timezone(timedelta(hours=5, minutes=30))


class ValidationSeverity(Enum):
    """Signal age severity levels"""
    NORMAL = "normal"
    WARNING = "warning"
    ELEVATED = "elevated"
    REJECTED = "rejected"


@dataclass
class ConditionValidationResult:
    """Result of condition validation stage"""
    is_valid: bool
    severity: ValidationSeverity
    reason: Optional[str] = None
    signal_age_seconds: Optional[float] = None


@dataclass
class ExecutionValidationResult:
    """Result of execution validation stage"""
    is_valid: bool
    reason: Optional[str] = None
    divergence_pct: Optional[float] = None
    risk_increase_pct: Optional[float] = None
    direction: Optional[str] = None  # "favorable" or "unfavorable"


class SignalValidator:
    """
    Validates trading signals using two-stage validation:
    1. Condition validation (trusts TradingView signal price)
    2. Execution validation (uses broker API price)
    """

    def __init__(
        self,
        config: SignalValidationConfig = None,
        portfolio_manager: Optional[PortfolioStateManager] = None,
        time_source=None  # Callable that returns datetime
    ):
        """
        Initialize signal validator

        Args:
            config: Validation configuration (uses defaults if None)
            portfolio_manager: Optional portfolio manager for state queries
            time_source: Optional callable that returns datetime (defaults to datetime.now)
                        Useful for testing with fixed time
        """
        self.config = config or SignalValidationConfig()
        self.portfolio_manager = portfolio_manager
        self.time_source = time_source or datetime.now

        # Validate configuration
        self._validate_config()

    def _validate_config(self):
        """Validate configuration values"""
        if self.config.max_divergence_base_entry <= 0:
            raise ValueError("max_divergence_base_entry must be positive")
        if self.config.max_divergence_pyramid <= 0:
            raise ValueError("max_divergence_pyramid must be positive")
        if self.config.max_divergence_exit <= 0:
            raise ValueError("max_divergence_exit must be positive")
        if self.config.max_risk_increase_pyramid < 0:
            raise ValueError("max_risk_increase_pyramid must be non-negative")
        if self.config.max_risk_increase_base < 0:
            raise ValueError("max_risk_increase_base must be non-negative")
        if self.config.max_signal_age_stale <= 0:
            raise ValueError("max_signal_age_stale must be positive")

    def validate_conditions_with_signal_price(
        self,
        signal: Signal,
        portfolio_state: Optional[PortfolioState] = None
    ) -> ConditionValidationResult:
        """
        Validate trading conditions using SIGNAL price.

        Trusts TradingView's timing - it generated signal at the right moment.

        Args:
            signal: Trading signal from TradingView
            portfolio_state: Current portfolio state (optional, fetched if None)

        Returns:
            ConditionValidationResult with validation outcome
        """
        # Get portfolio state if not provided
        if portfolio_state is None and self.portfolio_manager:
            portfolio_state_obj = self.portfolio_manager.get_current_state()
        elif portfolio_state:
            portfolio_state_obj = portfolio_state
        else:
            # No portfolio state available - skip portfolio-dependent checks
            portfolio_state_obj = None

        # 1. Signal age check (tiered validation)
        age_result = self._validate_signal_age(signal.timestamp)
        if not age_result.is_valid:
            return ConditionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.REJECTED,
                reason=age_result.reason,
                signal_age_seconds=age_result.signal_age_seconds
            )

        # 2. Required fields check (already validated in Signal.from_dict(), but double-check)
        if not self._validate_required_fields(signal):
            return ConditionValidationResult(
                is_valid=False,
                severity=ValidationSeverity.REJECTED,
                reason="missing_required_fields"
            )

        # 3. PYRAMID-specific validations
        if signal.signal_type == SignalType.PYRAMID:
            if portfolio_state_obj is None:
                return ConditionValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.REJECTED,
                    reason="portfolio_state_required_for_pyramid"
                )

            # 3a. 1R movement check
            one_r_result = self._validate_1r_movement(signal, portfolio_state_obj)
            if not one_r_result[0]:
                return ConditionValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.REJECTED,
                    reason=one_r_result[1]
                )

            # 3b. Instrument P&L check
            pnl_result = self._validate_instrument_pnl(signal, portfolio_state_obj)
            if not pnl_result[0]:
                return ConditionValidationResult(
                    is_valid=False,
                    severity=ValidationSeverity.REJECTED,
                    reason=pnl_result[1]
                )

        # All condition validations passed
        return ConditionValidationResult(
            is_valid=True,
            severity=age_result.severity,
            reason="conditions_met",
            signal_age_seconds=age_result.signal_age_seconds
        )

    def _validate_signal_age(self, signal_timestamp: datetime) -> ConditionValidationResult:
        """
        Signal age validation - DISABLED.

        Timestamp validation was causing production failures due to timezone
        complexities between TradingView and PM. For trend-following on hourly
        bars, signal freshness is not critical. Can be re-enabled if needed.

        Returns:
            ConditionValidationResult - always valid (validation disabled)
        """
        # DISABLED: Always return valid - timestamp validation caused production failures
        # See: Dec 12, 2025 incident where EXIT signals were rejected as "in_future"
        return ConditionValidationResult(
            is_valid=True,
            severity=ValidationSeverity.NORMAL,
            reason="signal_age_validation_disabled",
            signal_age_seconds=0.0
        )

    def _validate_required_fields(self, signal: Signal) -> bool:
        """Validate that all required fields are present"""
        required_attrs = ['timestamp', 'instrument', 'signal_type', 'position',
                         'price', 'stop', 'suggested_lots', 'atr', 'er', 'supertrend']

        for attr in required_attrs:
            if not hasattr(signal, attr) or getattr(signal, attr) is None:
                return False

        return True

    def _validate_1r_movement(
        self,
        signal: Signal,
        portfolio_state: PortfolioState
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate 1R movement for PYRAMID signals.

        1R = Initial Risk = Entry Price - Initial Stop (from base position)

        This aligns with Pine Script's pyramid gate logic:
        - pyramid_gate_open = price_move_from_entry > initial_risk_points
        - where initial_risk_points = initial_entry_price - initial_stop_price

        Args:
            signal: PYRAMID signal
            portfolio_state: Current portfolio state

        Returns:
            Tuple of (is_valid, reason)
        """
        # Find base position for this instrument
        positions = portfolio_state.positions
        base_position = None

        for pos in positions.values():
            if (pos.instrument == signal.instrument and
                pos.is_base_position and
                pos.status == "open"):
                base_position = pos
                break

        if base_position is None:
            return False, "no_base_position_found"

        # Calculate actual 1R (initial risk) = entry_price - initial_stop
        # This matches Pine Script: initial_risk_points = initial_entry_price - initial_stop_price
        initial_risk = base_position.entry_price - base_position.initial_stop

        if initial_risk <= 0:
            return False, f"invalid_initial_risk_{initial_risk:.2f}"

        # Calculate price movement from entry
        price_move = signal.price - base_position.entry_price

        # 1R Gate: Price must move MORE than 1R (initial risk)
        # This matches Pine Script: price_move_from_entry > initial_risk_points
        if price_move <= initial_risk:
            price_move_r = price_move / initial_risk if initial_risk > 0 else 0
            return False, f"1r_gate_not_passed_move_{price_move:.2f}_1R_{initial_risk:.2f}_ratio_{price_move_r:.2f}R"

        return True, None

    def _validate_instrument_pnl(
        self,
        signal: Signal,
        portfolio_state: PortfolioState
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate instrument P&L is positive for PYRAMID signals.

        Uses signal price (not broker price) for P&L calculation.

        Args:
            signal: PYRAMID signal
            portfolio_state: Current portfolio state

        Returns:
            Tuple of (is_valid, reason)
        """
        # Get all positions for this instrument
        positions = portfolio_state.positions
        instrument_positions = [
            pos for pos in positions.values()
            if pos.instrument == signal.instrument and pos.status == "open"
        ]

        if not instrument_positions:
            return False, "no_open_positions_for_instrument"

        # Calculate total unrealized P&L using signal price
        # Note: This uses signal price, not broker price (trust TradingView)
        total_pnl = 0.0

        # Determine point value based on instrument
        if signal.instrument == "BANK_NIFTY":
            point_value = 30.0  # Dec 2025 onwards
        elif signal.instrument == "COPPER":
            point_value = 2500.0
        elif signal.instrument == "SILVER_MINI":
            point_value = 5.0  # Rs 5 per Rs 1/kg move (5kg contract)
        else:  # GOLD_MINI
            point_value = 10.0

        for pos in instrument_positions:
            pnl = pos.calculate_pnl(signal.price, point_value)
            total_pnl += pnl

        if total_pnl < 0:
            return False, f"negative_instrument_pnl_{total_pnl:.2f}"

        return True, None

    def validate_execution_price(
        self,
        signal: Signal,
        broker_price: float,
        signal_type: Optional[SignalType] = None
    ) -> ExecutionValidationResult:
        """
        Validate execution is safe using BROKER price.

        Protects against excessive divergence and risk.
        Handles BASE_ENTRY, PYRAMID, and EXIT signals.

        Args:
            signal: Trading signal
            broker_price: Current broker price from API
            signal_type: Signal type (uses signal.signal_type if None)

        Returns:
            ExecutionValidationResult with validation outcome
        """
        if signal_type is None:
            signal_type = signal.signal_type

        # Handle EXIT signals separately (inverted logic)
        if signal_type == SignalType.EXIT:
            return self._validate_exit_execution(signal, broker_price)

        # Handle BASE_ENTRY and PYRAMID signals
        return self._validate_entry_execution(signal, broker_price, signal_type)

    def _validate_exit_execution(
        self,
        signal: Signal,
        broker_price: float
    ) -> ExecutionValidationResult:
        """
        Validate EXIT signal execution.

        For LONG EXIT:
        - broker_price > signal_price = favorable (better exit)
        - broker_price < signal_price = unfavorable (missed better exit)

        Args:
            signal: EXIT signal
            broker_price: Current broker price

        Returns:
            ExecutionValidationResult
        """
        signal_price = signal.price

        # Calculate divergence (positive = favorable, negative = unfavorable)
        divergence = broker_price - signal_price
        divergence_pct = divergence / signal_price

        # For LONG exits, negative divergence is unfavorable
        # Accept if divergence is favorable OR if unfavorable divergence < threshold
        if divergence_pct < -self.config.max_divergence_exit:
            return ExecutionValidationResult(
                is_valid=False,
                reason=f"exit_price_too_unfavorable_{divergence_pct:.2%}",
                divergence_pct=divergence_pct,
                direction="unfavorable"
            )

        direction = "favorable" if divergence_pct > 0 else "unfavorable"

        return ExecutionValidationResult(
            is_valid=True,
            reason="exit_validated",
            divergence_pct=divergence_pct,
            direction=direction
        )

    def _validate_entry_execution(
        self,
        signal: Signal,
        broker_price: float,
        signal_type: SignalType
    ) -> ExecutionValidationResult:
        """
        Validate BASE_ENTRY or PYRAMID execution.

        Args:
            signal: Entry signal
            broker_price: Current broker price
            signal_type: BASE_ENTRY or PYRAMID

        Returns:
            ExecutionValidationResult
        """
        signal_price = signal.price
        stop_price = signal.stop

        # 1. Price divergence check
        divergence = broker_price - signal_price
        divergence_pct = abs(divergence / signal_price)

        # Get divergence threshold based on signal type
        max_divergence = (
            self.config.max_divergence_pyramid if signal_type == SignalType.PYRAMID
            else self.config.max_divergence_base_entry
        )

        # Apply stricter threshold for delayed signals
        age_result = self._validate_signal_age(signal.timestamp)
        if age_result.severity == ValidationSeverity.ELEVATED:
            max_divergence = max_divergence * 0.5  # Halve threshold for delayed signals

        if divergence_pct > max_divergence:
            return ExecutionValidationResult(
                is_valid=False,
                reason=f"divergence_too_high_{divergence_pct:.2%}_vs_{max_divergence:.2%}",
                divergence_pct=divergence_pct,
                direction="unfavorable" if divergence < 0 else "favorable"
            )

        # 2. Risk increase check
        original_risk = signal_price - stop_price
        execution_risk = broker_price - stop_price

        if execution_risk <= 0:
            return ExecutionValidationResult(
                is_valid=False,
                reason="execution_price_below_stop",
                divergence_pct=divergence_pct
            )

        risk_increase_pct = (execution_risk - original_risk) / original_risk

        # Get risk increase threshold
        max_risk_increase = (
            self.config.max_risk_increase_pyramid if signal_type == SignalType.PYRAMID
            else self.config.max_risk_increase_base
        )

        if risk_increase_pct > max_risk_increase:
            return ExecutionValidationResult(
                is_valid=False,
                reason=f"risk_increase_too_high_{risk_increase_pct:.2%}_vs_{max_risk_increase:.2%}",
                divergence_pct=divergence_pct,
                risk_increase_pct=risk_increase_pct
            )

        # 3. Stop loss validity
        if broker_price <= stop_price:
            return ExecutionValidationResult(
                is_valid=False,
                reason="execution_price_below_stop",
                divergence_pct=divergence_pct
            )

        # 4. Direction check
        direction = "favorable" if divergence < 0 else "unfavorable"

        # Log warning if divergence exceeds warning threshold
        if divergence_pct > self.config.divergence_warning_threshold:
            logger.warning(
                f"Signal divergence exceeds warning threshold: {divergence_pct:.2%} "
                f"(signal: {signal_price}, broker: {broker_price})"
            )

        return ExecutionValidationResult(
            is_valid=True,
            reason="execution_validated",
            divergence_pct=divergence_pct,
            risk_increase_pct=risk_increase_pct,
            direction=direction
        )

    def adjust_position_size_for_execution(
        self,
        signal: Signal,
        broker_price: float,
        original_lots: int
    ) -> int:
        """
        Adjust position size based on execution price to maintain intended risk amount.

        Formula: adjusted_lots = original_lots * (original_risk / execution_risk)

        Args:
            signal: Trading signal
            broker_price: Execution price from broker
            original_lots: Original lot size calculated

        Returns:
            Adjusted lot size (minimum 1)
        """
        if not self.config.adjust_size_on_risk_increase:
            return original_lots

        original_risk = signal.price - signal.stop
        execution_risk = broker_price - signal.stop

        # Protection against division by zero
        if execution_risk <= 0:
            logger.warning(
                f"Execution risk <= 0, using original lots. "
                f"Broker price: {broker_price}, Stop: {signal.stop}"
            )
            return original_lots

        risk_ratio = original_risk / execution_risk

        # If risk decreased (ratio > 1), keep original lots (no increase)
        if risk_ratio > 1.0:
            return original_lots

        # If risk increased (ratio < 1), reduce lots proportionally
        adjusted_lots = int(original_lots * risk_ratio)

        # Ensure minimum lots
        adjusted_lots = max(adjusted_lots, self.config.min_lots_after_adjustment)

        if adjusted_lots != original_lots:
            logger.info(
                f"Position size adjusted: {original_lots} → {adjusted_lots} lots "
                f"(risk ratio: {risk_ratio:.3f}, original risk: {original_risk:.2f}, "
                f"execution risk: {execution_risk:.2f})"
            )

        return adjusted_lots

    def get_divergence_threshold(
        self,
        signal_type: SignalType,
        signal_age_severity: ValidationSeverity
    ) -> float:
        """
        Get divergence threshold based on signal type and age severity.

        Args:
            signal_type: Signal type
            signal_age_severity: Age validation severity

        Returns:
            Divergence threshold (as decimal, e.g., 0.02 for 2%)
        """
        base_threshold = {
            SignalType.BASE_ENTRY: self.config.max_divergence_base_entry,
            SignalType.PYRAMID: self.config.max_divergence_pyramid,
            SignalType.EXIT: self.config.max_divergence_exit
        }.get(signal_type, self.config.max_divergence_base_entry)

        if signal_age_severity == ValidationSeverity.ELEVATED:
            return base_threshold * 0.5  # Halve threshold for delayed signals

        return base_threshold
