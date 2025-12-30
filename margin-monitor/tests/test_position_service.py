"""
Tests for Position Service
"""

import pytest
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.position_service import PositionService
from tests.test_data import SAMPLE_POSITIONS


class TestPositionService:
    """Tests for PositionService."""

    def setup_method(self):
        """Setup test fixtures."""
        self.service = PositionService()
        # Normalize positions (convert string prices to float)
        self.positions = [
            {
                **pos,
                'average_price': float(pos['average_price']),
            }
            for pos in SAMPLE_POSITIONS
        ]

    def test_filter_by_expiry_30dec25(self):
        """Filter positions to today's expiry (30-Dec-2025)."""
        result = self.service.filter_positions(
            self.positions,
            index_name="NIFTY",
            expiry_date="2025-12-30"
        )

        # 30DEC25 positions
        assert len(result['short_positions']) == 3  # 3 active short PEs
        assert len(result['closed_positions']) == 3  # 3 closed CEs (qty=0)
        assert len(result['long_positions']) == 0  # No long 30DEC25

        # 29DEC26 positions should be excluded
        assert len(result['excluded_positions']) == 3

    def test_short_positions_have_negative_qty(self):
        """Short positions should have negative quantity."""
        result = self.service.filter_positions(
            self.positions,
            index_name="NIFTY",
            expiry_date="2025-12-30"
        )

        for pos in result['short_positions']:
            assert pos['quantity'] < 0

    def test_closed_positions_have_zero_qty(self):
        """Closed positions should have zero quantity."""
        result = self.service.filter_positions(
            self.positions,
            index_name="NIFTY",
            expiry_date="2025-12-30"
        )

        for pos in result['closed_positions']:
            assert pos['quantity'] == 0

    def test_excluded_positions_have_reason(self):
        """Excluded positions should have a reason."""
        result = self.service.filter_positions(
            self.positions,
            index_name="NIFTY",
            expiry_date="2025-12-30"
        )

        for pos in result['excluded_positions']:
            assert 'reason' in pos
            assert 'Expiry mismatch' in pos['reason'] or 'Index mismatch' in pos['reason']

    def test_summary_short_count(self):
        """Summary should count short positions correctly."""
        result = self.service.filter_positions(
            self.positions,
            index_name="NIFTY",
            expiry_date="2025-12-30"
        )
        summary = self.service.get_summary(result)

        assert summary['short_count'] == 3
        assert summary['short_qty'] == 3375  # 3 × 1125

    def test_summary_closed_count(self):
        """Summary should count closed positions correctly."""
        result = self.service.filter_positions(
            self.positions,
            index_name="NIFTY",
            expiry_date="2025-12-30"
        )
        summary = self.service.get_summary(result)

        assert summary['closed_count'] == 3

    def test_filter_by_wrong_index(self):
        """Filtering by wrong index should exclude all."""
        result = self.service.filter_positions(
            self.positions,
            index_name="SENSEX",
            expiry_date="2025-12-30"
        )

        assert len(result['short_positions']) == 0
        assert len(result['long_positions']) == 0
        assert len(result['closed_positions']) == 0
        assert len(result['excluded_positions']) == len(self.positions)

    def test_hedge_cost_calculation(self):
        """Hedge cost = sum(avg_price × qty) for long positions."""
        # Create test data with long positions
        long_positions = [
            {'average_price': 100.0, 'quantity': 75},
            {'average_price': 50.0, 'quantity': 150},
        ]

        hedge_cost = self.service.calculate_hedge_cost(long_positions)

        # 100 × 75 + 50 × 150 = 7500 + 7500 = 15000
        assert hedge_cost == 15000.0

    def test_total_pnl_calculation(self):
        """Total P&L = short_pnl + long_pnl + closed_pnl."""
        result = self.service.filter_positions(
            self.positions,
            index_name="NIFTY",
            expiry_date="2025-12-30"
        )
        summary = self.service.get_summary(result)

        # Total should equal sum of all categories
        expected_total = summary['short_pnl'] + summary['long_pnl'] + summary['closed_pnl']
        assert summary['total_pnl'] == expected_total


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
