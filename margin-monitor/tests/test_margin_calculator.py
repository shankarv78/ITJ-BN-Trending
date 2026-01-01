"""
Unit tests for MarginCalculatorService

Tests margin calculations, projections, and hedge requirement evaluation.
"""

import pytest
from app.services.margin_calculator import MarginCalculatorService, MarginProjection
from app.models.hedge_constants import (
    MarginConstants, HedgeConfig, IndexName, ExpiryType
)


@pytest.fixture
def calculator():
    """Create a MarginCalculatorService instance with default config."""
    return MarginCalculatorService()


@pytest.fixture
def custom_calculator():
    """Create a MarginCalculatorService with custom config for testing."""
    config = HedgeConfig()
    config.entry_trigger_pct = 90.0
    config.entry_target_pct = 80.0
    config.exit_trigger_pct = 60.0
    return MarginCalculatorService(config=config)


class TestMarginPerStraddle:
    """Tests for margin per straddle calculations."""

    def test_sensex_0dte_without_hedge_1_basket(self, calculator):
        """Test Sensex 0DTE margin without hedge - 1 basket."""
        margin = calculator.get_margin_per_straddle(
            IndexName.SENSEX, ExpiryType.ZERO_DTE,
            has_hedge=False, num_baskets=1
        )
        assert margin == pytest.approx(366666.67, rel=0.01)

    def test_sensex_0dte_with_hedge_1_basket(self, calculator):
        """Test Sensex 0DTE margin with hedge - 1 basket."""
        margin = calculator.get_margin_per_straddle(
            IndexName.SENSEX, ExpiryType.ZERO_DTE,
            has_hedge=True, num_baskets=1
        )
        assert margin == pytest.approx(160000.00, rel=0.01)

    def test_nifty_0dte_without_hedge_1_basket(self, calculator):
        """Test Nifty 0DTE margin without hedge - 1 basket."""
        margin = calculator.get_margin_per_straddle(
            IndexName.NIFTY, ExpiryType.ZERO_DTE,
            has_hedge=False, num_baskets=1
        )
        assert margin == pytest.approx(433333.33, rel=0.01)

    def test_nifty_0dte_with_hedge_1_basket(self, calculator):
        """Test Nifty 0DTE margin with hedge - 1 basket."""
        margin = calculator.get_margin_per_straddle(
            IndexName.NIFTY, ExpiryType.ZERO_DTE,
            has_hedge=True, num_baskets=1
        )
        assert margin == pytest.approx(186666.67, rel=0.01)

    def test_margin_scales_with_baskets(self, calculator):
        """Test margin scales correctly with basket count."""
        margin_1 = calculator.get_margin_per_straddle(
            IndexName.SENSEX, ExpiryType.ZERO_DTE,
            has_hedge=False, num_baskets=1
        )
        margin_15 = calculator.get_margin_per_straddle(
            IndexName.SENSEX, ExpiryType.ZERO_DTE,
            has_hedge=False, num_baskets=15
        )
        assert margin_15 == margin_1 * 15

    def test_nifty_1dte_margin(self, calculator):
        """Test Nifty 1DTE margin calculation."""
        margin = calculator.get_margin_per_straddle(
            IndexName.NIFTY, ExpiryType.ONE_DTE,
            has_hedge=False, num_baskets=1
        )
        assert margin == pytest.approx(320000.00, rel=0.01)


class TestUtilizationCalculations:
    """Tests for utilization percentage calculations."""

    def test_current_utilization_50_percent(self, calculator):
        """Test 50% utilization calculation."""
        util = calculator.calculate_current_utilization(
            intraday_margin=5000000,
            total_budget=10000000
        )
        assert util == 50.0

    def test_current_utilization_100_percent(self, calculator):
        """Test 100% utilization calculation."""
        util = calculator.calculate_current_utilization(
            intraday_margin=10000000,
            total_budget=10000000
        )
        assert util == 100.0

    def test_current_utilization_over_100_percent(self, calculator):
        """Test over 100% utilization (breach)."""
        util = calculator.calculate_current_utilization(
            intraday_margin=12000000,
            total_budget=10000000
        )
        assert util == 120.0

    def test_projected_utilization(self, calculator):
        """Test projected utilization after entry."""
        # Budget: 1.5Cr, Current: 85L, Next entry: 55L
        projected = calculator.calculate_projected_utilization(
            current_intraday_margin=8500000,
            total_budget=15000000,
            margin_for_next_entry=5500000
        )
        # (85 + 55) / 150 * 100 = 93.33%
        assert projected == pytest.approx(93.33, rel=0.01)


class TestHedgeRequirement:
    """Tests for hedge requirement determination."""

    def test_hedge_not_required_below_threshold(self, calculator):
        """Test hedge not required when projected < threshold (95%)."""
        required = calculator.is_hedge_required(
            projected_utilization=90.0
        )
        assert required is False

    def test_hedge_required_above_threshold(self, calculator):
        """Test hedge required when projected > threshold (95%)."""
        required = calculator.is_hedge_required(
            projected_utilization=100.0
        )
        assert required is True

    def test_hedge_required_at_threshold(self, calculator):
        """Test hedge NOT required when exactly at threshold."""
        required = calculator.is_hedge_required(
            projected_utilization=95.0
        )
        assert required is False  # Not greater than threshold

    def test_hedge_required_just_above_threshold(self, calculator):
        """Test hedge required when just above threshold."""
        required = calculator.is_hedge_required(
            projected_utilization=95.1
        )
        assert required is True

    def test_custom_threshold(self, custom_calculator):
        """Test hedge requirement with custom threshold (90%)."""
        required = custom_calculator.is_hedge_required(
            projected_utilization=92.0
        )
        assert required is True


class TestMarginReductionNeeded:
    """Tests for margin reduction calculations."""

    def test_reduction_needed_when_over_target(self, calculator):
        """Test reduction needed when projected exceeds target."""
        # Projected: 120%, Target: 85%, Budget: 1Cr
        # Need to reduce from 120L to 85L = 35L reduction
        reduction = calculator.calculate_margin_reduction_needed(
            current_intraday_margin=7000000,  # 70L
            total_budget=10000000,            # 1Cr
            margin_for_next_entry=5000000     # 50L (would make 120%)
        )
        # Target: 1Cr * 0.85 = 85L
        # Projected: 70L + 50L = 120L
        # Reduction: 120L - 85L = 35L
        assert reduction == pytest.approx(3500000, rel=0.01)

    def test_no_reduction_needed_when_under_target(self, calculator):
        """Test no reduction needed when projected is under target."""
        reduction = calculator.calculate_margin_reduction_needed(
            current_intraday_margin=5000000,  # 50L
            total_budget=10000000,            # 1Cr
            margin_for_next_entry=2000000     # 20L (would make 70%)
        )
        assert reduction == 0.0


class TestHedgeBenefit:
    """Tests for hedge margin benefit estimation."""

    def test_sensex_0dte_hedge_benefit(self, calculator):
        """Test Sensex 0DTE hedge benefit."""
        benefit = calculator.estimate_hedge_margin_benefit(
            IndexName.SENSEX, ExpiryType.ZERO_DTE, num_baskets=1
        )
        # Without: 366666.67, With: 160000 = Benefit: 206666.67
        assert benefit == pytest.approx(206666.67, rel=0.01)

    def test_nifty_0dte_hedge_benefit(self, calculator):
        """Test Nifty 0DTE hedge benefit."""
        benefit = calculator.estimate_hedge_margin_benefit(
            IndexName.NIFTY, ExpiryType.ZERO_DTE, num_baskets=1
        )
        # Without: 433333.33, With: 186666.67 = Benefit: 246666.66
        assert benefit == pytest.approx(246666.66, rel=0.01)

    def test_hedge_benefit_scales_with_baskets(self, calculator):
        """Test hedge benefit scales with basket count."""
        benefit_1 = calculator.estimate_hedge_margin_benefit(
            IndexName.SENSEX, ExpiryType.ZERO_DTE, num_baskets=1
        )
        benefit_15 = calculator.estimate_hedge_margin_benefit(
            IndexName.SENSEX, ExpiryType.ZERO_DTE, num_baskets=15
        )
        assert benefit_15 == benefit_1 * 15


class TestFullProjection:
    """Tests for full margin projection."""

    def test_full_projection_hedge_required(self, calculator):
        """Test full projection when hedge is required."""
        projection = calculator.calculate_full_projection(
            current_intraday_margin=13000000,  # 130L (86.67% of 1.5Cr)
            total_budget=15000000,             # 1.5Cr
            index=IndexName.SENSEX,
            expiry_type=ExpiryType.ZERO_DTE,
            num_baskets=1,
            has_existing_hedge=False
        )

        assert isinstance(projection, MarginProjection)
        assert projection.hedge_required is True
        assert projection.current_utilization == pytest.approx(86.67, rel=0.01)
        assert projection.projected_utilization > 95.0

    def test_full_projection_hedge_not_required(self, calculator):
        """Test full projection when hedge is not required."""
        projection = calculator.calculate_full_projection(
            current_intraday_margin=3000000,   # 30L (20% of 1.5Cr)
            total_budget=15000000,             # 1.5Cr
            index=IndexName.SENSEX,
            expiry_type=ExpiryType.ZERO_DTE,
            num_baskets=1,
            has_existing_hedge=False
        )

        assert projection.hedge_required is False
        assert projection.current_utilization == 20.0


class TestHedgeExit:
    """Tests for hedge exit determination."""

    def test_should_exit_when_low_utilization(self, calculator):
        """Test should exit when utilization is low."""
        should_exit = calculator.should_exit_hedge(
            current_utilization=50.0
        )
        assert should_exit is True  # 50% < 70% threshold

    def test_should_not_exit_when_high_utilization(self, calculator):
        """Test should not exit when utilization is high."""
        should_exit = calculator.should_exit_hedge(
            current_utilization=80.0
        )
        assert should_exit is False  # 80% > 70% threshold

    def test_should_not_exit_at_threshold(self, calculator):
        """Test should not exit when at threshold."""
        should_exit = calculator.should_exit_hedge(
            current_utilization=70.0
        )
        assert should_exit is False  # Not less than threshold
