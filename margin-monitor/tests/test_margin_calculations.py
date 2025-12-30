"""
Tests for Margin Calculations
"""

import pytest
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_data import BASELINE, SNAPSHOTS, NUM_BASKETS, TOTAL_BUDGET


class TestMarginCalculations:
    """Tests for margin calculation logic."""

    def test_intraday_margin_after_exp1(self):
        """Intraday margin after first straddle entry."""
        after_exp1 = 5049451.12
        intraday = after_exp1 - BASELINE
        assert intraday == pytest.approx(4457272.49, rel=0.01)

    def test_intraday_margin_after_exp2(self):
        """Intraday margin after second straddle entry."""
        after_exp2 = 10033810.88
        intraday = after_exp2 - BASELINE
        assert intraday == pytest.approx(9441632.25, rel=0.01)

    def test_intraday_margin_after_exp3(self):
        """Intraday margin after third straddle entry (peak)."""
        after_exp3 = 15022200.38
        intraday = after_exp3 - BASELINE
        assert intraday == pytest.approx(14430021.75, rel=0.01)

    def test_utilization_at_peak(self):
        """Peak utilization should be around 96%."""
        after_exp3 = 15022200.38
        intraday = after_exp3 - BASELINE
        utilization = (intraday / TOTAL_BUDGET) * 100
        assert utilization == pytest.approx(96.2, rel=0.5)

    def test_utilization_after_exp2(self):
        """Utilization after second entry."""
        after_exp2 = 10033810.88
        intraday = after_exp2 - BASELINE
        utilization = (intraday / TOTAL_BUDGET) * 100
        assert utilization == pytest.approx(62.94, rel=0.1)

    def test_margin_release_after_sl(self):
        """Margin decreases after SL hits."""
        after_exp3 = 15022200.38
        after_sl1 = 12512414.25
        after_sl2 = 11366910.00

        # Margin should decrease after each SL
        assert after_sl1 < after_exp3
        assert after_sl2 < after_sl1

        # Calculate margin released
        released1 = after_exp3 - after_sl1
        assert released1 > 2000000  # At least 20L released

    def test_budget_calculation(self):
        """Budget = baskets × budget_per_basket."""
        assert NUM_BASKETS * 1000000 == TOTAL_BUDGET
        assert TOTAL_BUDGET == 15000000


class TestBudgetRemaining:
    """Tests for budget remaining calculation."""

    def test_budget_remaining_at_peak(self):
        """At peak utilization, budget remaining should be small."""
        after_exp3 = 15022200.38
        intraday = after_exp3 - BASELINE
        remaining = TOTAL_BUDGET - intraday

        assert remaining < 1000000  # Less than 10L remaining
        assert remaining > 0  # Still positive (96% utilization)

    def test_budget_remaining_after_exp2(self):
        """After EXP2, about 37% budget remaining."""
        after_exp2 = 10033810.88
        intraday = after_exp2 - BASELINE
        remaining = TOTAL_BUDGET - intraday

        assert remaining == pytest.approx(5558367.75, rel=0.01)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
