"""
Tests for Symbol Parser
"""

import pytest
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.symbol_parser import (
    parse_symbol, is_matching_expiry, is_matching_index, get_position_type
)


class TestParseSymbol:
    """Tests for parse_symbol function."""

    def test_parse_nifty_weekly_put(self):
        """Parse Nifty weekly put option."""
        result = parse_symbol("NIFTY30DEC2525800PE")

        assert result is not None
        assert result.index == "NIFTY"
        assert result.day == 30
        assert result.month == "DEC"
        assert result.year == 25
        assert result.expiry_date == "2025-12-30"
        assert result.strike == 25800
        assert result.option_type == "PE"

    def test_parse_nifty_call(self):
        """Parse Nifty call option."""
        result = parse_symbol("NIFTY30DEC2525900CE")

        assert result is not None
        assert result.index == "NIFTY"
        assert result.strike == 25900
        assert result.option_type == "CE"

    def test_parse_nifty_future_year(self):
        """Parse Nifty option with future year (2026)."""
        result = parse_symbol("NIFTY29DEC2625000CE")

        assert result is not None
        assert result.expiry_date == "2026-12-29"
        assert result.year == 26
        assert result.strike == 25000

    def test_parse_sensex(self):
        """Parse Sensex option (expected format)."""
        result = parse_symbol("SENSEX02JAN2578000PE")

        assert result is not None
        assert result.index == "SENSEX"
        assert result.day == 2
        assert result.month == "JAN"
        assert result.year == 25
        assert result.expiry_date == "2025-01-02"
        assert result.strike == 78000
        assert result.option_type == "PE"

    def test_parse_banknifty(self):
        """Parse BankNifty option."""
        result = parse_symbol("BANKNIFTY31DEC2552000CE")

        assert result is not None
        assert result.index == "BANKNIFTY"
        assert result.strike == 52000

    def test_invalid_symbol_returns_none(self):
        """Invalid symbol should return None."""
        assert parse_symbol("INVALID") is None
        assert parse_symbol("") is None
        assert parse_symbol("NIFTY") is None
        assert parse_symbol("NIFTY30DEC25") is None

    def test_invalid_month_returns_none(self):
        """Invalid month should return None."""
        assert parse_symbol("NIFTY30XXX2525800PE") is None

    def test_invalid_date_returns_none(self):
        """Invalid date (Feb 30) should return None."""
        assert parse_symbol("NIFTY30FEB2525800PE") is None


class TestIsMatchingExpiry:
    """Tests for is_matching_expiry function."""

    def test_matching_expiry_returns_true(self):
        """Symbol with matching expiry returns True."""
        assert is_matching_expiry("NIFTY30DEC2525800PE", "2025-12-30") is True

    def test_different_expiry_returns_false(self):
        """Symbol with different expiry returns False."""
        assert is_matching_expiry("NIFTY29DEC2625000CE", "2025-12-30") is False

    def test_invalid_symbol_returns_false(self):
        """Invalid symbol returns False."""
        assert is_matching_expiry("INVALID", "2025-12-30") is False


class TestIsMatchingIndex:
    """Tests for is_matching_index function."""

    def test_matching_index_returns_true(self):
        """Symbol with matching index returns True."""
        assert is_matching_index("NIFTY30DEC2525800PE", "NIFTY") is True
        assert is_matching_index("SENSEX02JAN2578000PE", "SENSEX") is True

    def test_different_index_returns_false(self):
        """Symbol with different index returns False."""
        assert is_matching_index("NIFTY30DEC2525800PE", "SENSEX") is False
        assert is_matching_index("SENSEX02JAN2578000PE", "NIFTY") is False


class TestGetPositionType:
    """Tests for get_position_type function."""

    def test_negative_quantity_is_short(self):
        """Negative quantity returns SHORT."""
        assert get_position_type(-1125) == "SHORT"
        assert get_position_type(-1) == "SHORT"

    def test_positive_quantity_is_long(self):
        """Positive quantity returns LONG."""
        assert get_position_type(450) == "LONG"
        assert get_position_type(1) == "LONG"

    def test_zero_quantity_is_closed(self):
        """Zero quantity returns CLOSED."""
        assert get_position_type(0) == "CLOSED"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
