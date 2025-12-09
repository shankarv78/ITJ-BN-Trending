"""
Unit tests for SignalValidator
"""
import pytest
from datetime import datetime, timedelta, timezone
from core.signal_validator import (
    SignalValidator,
    SignalValidationConfig,
    ConditionValidationResult,
    ExecutionValidationResult,
    ValidationSeverity
)
from core.models import Signal, SignalType, Position, PortfolioState, InstrumentType


class TestSignalValidationConfig:
    """Test SignalValidationConfig dataclass"""

    def test_default_values(self):
        """Test that default values are set correctly"""
        config = SignalValidationConfig()

        assert config.max_divergence_base_entry == 0.02  # 2%
        assert config.max_divergence_pyramid == 0.01  # 1%
        assert config.max_divergence_exit == 0.01  # 1%
        assert config.max_risk_increase_pyramid == 0.20  # 20%
        assert config.max_risk_increase_base == 0.50  # 50%
        assert config.max_signal_age_normal == 10
        assert config.max_signal_age_warning == 30
        assert config.max_signal_age_elevated == 60
        assert config.default_execution_strategy == "progressive"

    def test_override_values(self):
        """Test that values can be overridden"""
        config = SignalValidationConfig(
            max_divergence_base_entry=0.03,
            max_divergence_pyramid=0.015
        )

        assert config.max_divergence_base_entry == 0.03
        assert config.max_divergence_pyramid == 0.015
        assert config.max_divergence_base_entry != 0.02  # Different from default


class TestSignalValidatorInitialization:
    """Test SignalValidator initialization"""

    def test_validator_initialization_with_defaults(self):
        """Test validator can be initialized with default config"""
        validator = SignalValidator()
        assert validator.config is not None
        assert isinstance(validator.config, SignalValidationConfig)

    def test_validator_initialization_with_custom_config(self):
        """Test validator can be initialized with custom config"""
        config = SignalValidationConfig(max_divergence_base_entry=0.03)
        validator = SignalValidator(config=config)
        assert validator.config.max_divergence_base_entry == 0.03

    def test_validator_initialization_with_portfolio_manager(self):
        """Test validator can be initialized with portfolio manager"""
        validator = SignalValidator(portfolio_manager=None)
        assert validator.portfolio_manager is None

    def test_invalid_config_raises_error(self):
        """Test that invalid config raises ValueError"""
        config = SignalValidationConfig(max_divergence_base_entry=-0.01)
        with pytest.raises(ValueError, match="must be positive"):
            SignalValidator(config=config)


class TestConditionValidation:
    """Test condition validation with signal price"""

    @pytest.fixture
    def reference_time(self):
        """Fixed reference time for consistent testing"""
        return datetime(2025, 12, 7, 12, 0, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def validator(self, reference_time):
        """Validator with fixed time source"""
        return SignalValidator(time_source=lambda: reference_time)

    @pytest.fixture
    def fresh_signal(self, reference_time):
        """Create a fresh BASE_ENTRY signal"""
        return Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49400.0,
            suggested_lots=10,
            atr=300.0,
            er=1.5,
            supertrend=49800.0
        )

    @pytest.fixture
    def stale_signal(self, reference_time):
        """Create a stale signal (>60s old)"""
        return Signal(
            timestamp=reference_time - timedelta(seconds=70),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49400.0,
            suggested_lots=10,
            atr=300.0,
            er=1.5,
            supertrend=49800.0
        )

    def test_valid_base_entry_signal(self, validator, fresh_signal):
        """Test that valid BASE_ENTRY signal passes condition validation"""
        result = validator.validate_conditions_with_signal_price(fresh_signal)

        assert result.is_valid is True
        assert result.severity == ValidationSeverity.NORMAL
        assert result.reason == "conditions_met"

    def test_signal_too_old_rejected(self, validator, stale_signal):
        """Test that signal older than 60s is rejected"""
        result = validator.validate_conditions_with_signal_price(stale_signal)

        assert result.is_valid is False
        assert result.severity == ValidationSeverity.REJECTED
        assert "stale" in result.reason.lower()
        assert result.signal_age_seconds > 60

    def test_signal_age_tiered_validation_normal(self, validator, reference_time):
        """Test normal signal age (<10s)"""
        signal = Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49400.0,
            suggested_lots=10,
            atr=300.0,
            er=1.5,
            supertrend=49800.0
        )

        result = validator.validate_conditions_with_signal_price(signal)
        assert result.is_valid is True
        assert result.severity == ValidationSeverity.NORMAL

    def test_signal_age_tiered_validation_warning(self, validator, reference_time):
        """Test warning signal age (10-30s)"""
        signal = Signal(
            timestamp=reference_time - timedelta(seconds=25),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49400.0,
            suggested_lots=10,
            atr=300.0,
            er=1.5,
            supertrend=49800.0
        )

        result = validator.validate_conditions_with_signal_price(signal)
        assert result.is_valid is True
        assert result.severity == ValidationSeverity.WARNING

    def test_signal_age_tiered_validation_elevated(self, validator, reference_time):
        """Test elevated signal age (30-60s)"""
        signal = Signal(
            timestamp=reference_time - timedelta(seconds=45),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49400.0,
            suggested_lots=10,
            atr=300.0,
            er=1.5,
            supertrend=49800.0
        )

        result = validator.validate_conditions_with_signal_price(signal)
        assert result.is_valid is True
        assert result.severity == ValidationSeverity.ELEVATED

    def test_future_timestamp_rejected(self, validator, reference_time):
        """Test that future timestamp is rejected"""
        signal = Signal(
            timestamp=reference_time + timedelta(seconds=10),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49400.0,
            suggested_lots=10,
            atr=300.0,
            er=1.5,
            supertrend=49800.0
        )

        result = validator.validate_conditions_with_signal_price(signal)
        assert result.is_valid is False
        assert "future" in result.reason.lower()


class TestPyramidConditionValidation:
    """Test PYRAMID-specific condition validation"""

    @pytest.fixture
    def reference_time(self):
        """Fixed reference time for consistent testing"""
        return datetime(2025, 12, 7, 12, 0, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def validator(self, reference_time):
        """Validator with fixed time source"""
        return SignalValidator(time_source=lambda: reference_time)

    @pytest.fixture
    def base_position(self, reference_time):
        """Create a base position"""
        return Position(
            position_id="BANK_NIFTY_Long_1",
            instrument="BANK_NIFTY",
            entry_timestamp=reference_time - timedelta(hours=1),
            entry_price=49000.0,
            lots=10,
            quantity=350,
            initial_stop=48500.0,
            current_stop=48500.0,
            highest_close=49500.0,
            is_base_position=True
        )

    @pytest.fixture
    def portfolio_state(self, reference_time, base_position):
        """Create portfolio state with base position"""
        return PortfolioState(
            timestamp=reference_time,
            equity=5000000.0,
            closed_equity=5000000.0,
            open_equity=5000000.0,
            blended_equity=5000000.0,
            positions={"BANK_NIFTY_Long_1": base_position}
        )

    def test_valid_pyramid_signal_1r_moved(self, validator, portfolio_state, reference_time):
        """Test valid PYRAMID signal with 1R movement"""
        # Signal price is 520 points above base (49000), ATR is 300
        # 1.5 * ATR = 450, so 520 > 450 (valid)
        signal = Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=49520.0,  # 520 points above base
            stop=49200.0,
            suggested_lots=5,
            atr=300.0,
            er=1.5,
            supertrend=49400.0
        )

        result = validator.validate_conditions_with_signal_price(signal, portfolio_state)
        assert result.is_valid is True

    def test_pyramid_insufficient_1r_movement(self, validator, portfolio_state, reference_time):
        """Test PYRAMID signal rejected if < 1R movement"""
        # Signal price is only 300 points above base, ATR is 300
        # 1.5 * ATR = 450, so 300 < 450 (invalid)
        signal = Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=49300.0,  # Only 300 points above base
            stop=49200.0,
            suggested_lots=5,
            atr=300.0,
            er=1.5,
            supertrend=49400.0
        )

        result = validator.validate_conditions_with_signal_price(signal, portfolio_state)
        assert result.is_valid is False
        assert "insufficient_1r" in result.reason.lower()

    def test_pyramid_negative_pnl_rejected(self, validator, portfolio_state, reference_time):
        """Test PYRAMID signal rejected if price is below base entry (insufficient 1R movement)

        Note: Validator checks 1R movement first. With price 48500 and base 49000,
        movement is -500 vs required 450 (1.5 * ATR of 300). This fails the 1R check.
        """
        # Create signal where current price would result in negative P&L
        # Base position at 49000, signal at 48500 (below entry)
        signal = Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=48500.0,  # Below base entry price
            stop=48200.0,
            suggested_lots=5,
            atr=300.0,
            er=1.5,
            supertrend=48400.0
        )

        result = validator.validate_conditions_with_signal_price(signal, portfolio_state)
        assert result.is_valid is False
        # 1R check fails first (movement -500 < required 450)
        assert "insufficient_1r" in result.reason.lower()

    def test_pyramid_no_base_position_rejected(self, validator, reference_time):
        """Test PYRAMID signal rejected if no base position exists"""
        empty_state = PortfolioState(
            timestamp=reference_time,
            equity=5000000.0,
            closed_equity=5000000.0,
            open_equity=5000000.0,
            blended_equity=5000000.0,
            positions={}
        )

        signal = Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=49520.0,
            stop=49200.0,
            suggested_lots=5,
            atr=300.0,
            er=1.5,
            supertrend=49400.0
        )

        result = validator.validate_conditions_with_signal_price(signal, empty_state)
        assert result.is_valid is False
        assert "no_base_position" in result.reason.lower()


class TestExecutionValidation:
    """Test execution price validation with broker price"""

    @pytest.fixture
    def reference_time(self):
        """Fixed reference time for consistent testing"""
        return datetime(2025, 12, 7, 12, 0, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def validator(self, reference_time):
        """Validator with fixed time source"""
        return SignalValidator(time_source=lambda: reference_time)

    @pytest.fixture
    def base_entry_signal(self, reference_time):
        return Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49400.0,
            suggested_lots=10,
            atr=300.0,
            er=1.5,
            supertrend=49800.0
        )

    def test_valid_base_entry_no_divergence(self, validator, base_entry_signal):
        """Test valid BASE_ENTRY with no divergence"""
        result = validator.validate_execution_price(base_entry_signal, 50000.0)

        assert result.is_valid is True
        assert result.divergence_pct == 0.0
        assert result.risk_increase_pct == 0.0

    def test_valid_base_entry_small_divergence(self, validator, base_entry_signal):
        """Test valid BASE_ENTRY with small divergence (<2%)"""
        result = validator.validate_execution_price(base_entry_signal, 50050.0)  # 0.1% divergence

        assert result.is_valid is True
        assert result.divergence_pct == pytest.approx(0.001, abs=0.0001)

    def test_invalid_base_entry_large_risk_increase(self, validator, base_entry_signal):
        """Test invalid BASE_ENTRY with large risk increase

        Signal: price=50000, stop=49400 (original risk=600)
        Broker: price=51000 → execution risk=1600
        Risk increase: (1600-600)/600 = 166.67% (exceeds 50% threshold)
        """
        result = validator.validate_execution_price(base_entry_signal, 51000.0)

        assert result.is_valid is False
        # Rejected for risk increase, not divergence (divergence is only 2%)
        assert "risk_increase" in result.reason.lower()

    def test_invalid_execution_price_below_stop(self, validator, base_entry_signal):
        """Test execution price below stop is rejected"""
        result = validator.validate_execution_price(base_entry_signal, 49300.0)  # Below stop

        assert result.is_valid is False
        assert "below_stop" in result.reason.lower()

    def test_risk_increase_validation_pyramid(self, validator, reference_time):
        """Test risk increase validation for PYRAMID

        Original risk: 50000 - 49400 = 600 points
        PYRAMID max_risk_increase = 20%

        Test cases:
        - 50100: risk 700, increase = 16.7% → OK
        - 50120: risk 720, increase = 20% → at threshold, OK
        - 50150: risk 750, increase = 25% → exceeds 20%, REJECT
        """
        pyramid_signal = Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=50000.0,
            stop=49400.0,  # Original risk: 600
            suggested_lots=5,
            atr=300.0,
            er=1.5,
            supertrend=49800.0
        )

        # Broker price 50100: risk = 50100-49400 = 700 (16.7% increase - OK)
        result = validator.validate_execution_price(pyramid_signal, 50100.0)
        assert result.is_valid is True

        # Broker price 50120: risk = 50120-49400 = 720 (20% increase - at threshold)
        result = validator.validate_execution_price(pyramid_signal, 50120.0)
        assert result.is_valid is True

        # Broker price 50150: risk = 50150-49400 = 750 (25% increase - exceeds 20% threshold)
        result = validator.validate_execution_price(pyramid_signal, 50150.0)
        assert result.is_valid is False
        assert "risk_increase" in result.reason.lower()


class TestExitValidation:
    """Test EXIT signal validation"""

    @pytest.fixture
    def reference_time(self):
        """Fixed reference time for consistent testing"""
        return datetime(2025, 12, 7, 12, 0, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def validator(self, reference_time):
        """Validator with fixed time source"""
        return SignalValidator(time_source=lambda: reference_time)

    @pytest.fixture
    def exit_signal(self, reference_time):
        return Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.EXIT,
            position="ALL",
            price=51000.0,
            stop=0.0,  # Not used for EXIT
            suggested_lots=0,  # Not used for EXIT
            atr=300.0,
            er=1.5,
            supertrend=50800.0,
            reason="trailing_stop_hit"
        )

    def test_exit_at_signal_price(self, validator, exit_signal):
        """Test EXIT at signal price (no divergence)

        Note: At exact signal price (0% divergence), direction is implementation-defined.
        Validator considers 0 divergence as neutral/unfavorable rather than favorable.
        """
        result = validator.validate_execution_price(exit_signal, 51000.0)

        assert result.is_valid is True
        assert result.divergence_pct == 0.0
        # At 0 divergence, direction is "unfavorable" (no improvement, neutral)
        assert result.direction == "unfavorable"

    def test_exit_at_better_price(self, validator, exit_signal):
        """Test EXIT at better price (favorable)"""
        result = validator.validate_execution_price(exit_signal, 51100.0)  # 100 points better

        assert result.is_valid is True
        assert result.divergence_pct > 0
        assert result.direction == "favorable"

    def test_exit_at_slightly_worse_price(self, validator, exit_signal):
        """Test EXIT at slightly worse price (<1% - accept)"""
        result = validator.validate_execution_price(exit_signal, 50900.0)  # 0.2% worse

        assert result.is_valid is True
        assert result.divergence_pct < 0
        assert result.direction == "unfavorable"

    def test_exit_at_significantly_worse_price(self, validator, exit_signal):
        """Test EXIT at significantly worse price (>1% - reject)"""
        result = validator.validate_execution_price(exit_signal, 50400.0)  # 1.2% worse

        assert result.is_valid is False
        assert "unfavorable" in result.reason.lower()


class TestPositionSizeAdjustment:
    """Test position size adjustment for execution"""

    @pytest.fixture
    def reference_time(self):
        """Fixed reference time for consistent testing"""
        return datetime(2025, 12, 7, 12, 0, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def validator(self, reference_time):
        """Validator with fixed time source"""
        return SignalValidator(time_source=lambda: reference_time)

    @pytest.fixture
    def signal(self, reference_time):
        return Signal(
            timestamp=reference_time - timedelta(seconds=5),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=50000.0,
            stop=49400.0,  # Risk: 600 points
            suggested_lots=10,
            atr=300.0,
            er=1.5,
            supertrend=49800.0
        )

    def test_no_adjustment_needed(self, validator, signal):
        """Test no adjustment when broker price equals signal price"""
        adjusted = validator.adjust_position_size_for_execution(signal, 50000.0, 10)
        assert adjusted == 10

    def test_adjustment_market_surge(self, validator, signal):
        """Test lots reduced when market surges"""
        # Broker price 50300, risk becomes 900 (50% increase)
        # Risk ratio: 600/900 = 0.667
        # Adjusted lots: 10 * 0.667 = 6.67 → 6
        adjusted = validator.adjust_position_size_for_execution(signal, 50300.0, 10)
        assert adjusted == 6

    def test_adjustment_market_pullback(self, validator, signal):
        """Test lots increased when market pulls back"""
        # Broker price 49900, risk becomes 500 (decrease)
        # Risk ratio: 600/500 = 1.2
        # Since ratio > 1, keep original lots (no increase)
        adjusted = validator.adjust_position_size_for_execution(signal, 49900.0, 10)
        assert adjusted == 10  # No increase, keep original

    def test_minimum_lots_enforced(self, validator, signal):
        """Test that minimum 1 lot is enforced"""
        # Extreme surge: broker price 51000, risk becomes 1600
        # Risk ratio: 600/1600 = 0.375
        # Adjusted lots: 10 * 0.375 = 3.75 → 3
        adjusted = validator.adjust_position_size_for_execution(signal, 51000.0, 10)
        assert adjusted >= 1

    def test_division_by_zero_protection(self, validator, signal):
        """Test protection against division by zero"""
        # Broker price equals stop (execution_risk = 0)
        adjusted = validator.adjust_position_size_for_execution(signal, 49400.0, 10)
        assert adjusted == 10  # Should return original lots
