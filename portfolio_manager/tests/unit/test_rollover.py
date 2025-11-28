"""
Unit tests for rollover system

Tests:
- Expiry utilities (strike rounding, days to expiry, etc.)
- Rollover scanner (identifying candidates)
- Rollover executor (order execution logic)
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.models import Position, InstrumentType
from core.config import PortfolioConfig
from live.expiry_utils import (
    get_last_wednesday_of_month,
    get_last_day_of_month,
    get_banknifty_expiry,
    get_gold_mini_expiry,
    get_next_month_expiry,
    format_expiry_string,
    parse_expiry_string,
    days_to_expiry,
    is_within_rollover_window,
    get_rollover_strike,
    format_banknifty_option_symbol,
    format_gold_mini_futures_symbol,
    is_market_hours
)


class TestExpiryUtils:
    """Tests for expiry_utils.py"""

    # =========================================================================
    # Last Wednesday calculation
    # =========================================================================

    def test_last_wednesday_december_2025(self):
        """December 2025 last Wednesday is 31st"""
        result = get_last_wednesday_of_month(2025, 12)
        assert result.day == 31
        assert result.weekday() == 2  # Wednesday

    def test_last_wednesday_november_2025(self):
        """November 2025 last Wednesday is 26th"""
        result = get_last_wednesday_of_month(2025, 11)
        assert result.day == 26
        assert result.weekday() == 2

    def test_last_wednesday_january_2026(self):
        """January 2026 last Wednesday is 28th"""
        result = get_last_wednesday_of_month(2026, 1)
        assert result.day == 28
        assert result.weekday() == 2

    # =========================================================================
    # Last day of month calculation
    # =========================================================================

    def test_last_day_december(self):
        """December has 31 days"""
        result = get_last_day_of_month(2025, 12)
        assert result.day == 31

    def test_last_day_november(self):
        """November has 30 days"""
        result = get_last_day_of_month(2025, 11)
        assert result.day == 30

    def test_last_day_february_2024(self):
        """February 2024 is leap year - 29 days"""
        result = get_last_day_of_month(2024, 2)
        assert result.day == 29

    def test_last_day_february_2025(self):
        """February 2025 is not leap year - 28 days"""
        result = get_last_day_of_month(2025, 2)
        assert result.day == 28

    # =========================================================================
    # Expiry string formatting
    # =========================================================================

    def test_format_expiry_string(self):
        """Test expiry string format"""
        dt = datetime(2025, 12, 25)
        result = format_expiry_string(dt)
        assert result == "25DEC25"

    def test_format_expiry_string_january(self):
        """Test January expiry format"""
        dt = datetime(2026, 1, 28)
        result = format_expiry_string(dt)
        assert result == "26JAN28"

    def test_parse_expiry_string(self):
        """Test parsing expiry string"""
        result = parse_expiry_string("25DEC25")
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 25

    def test_parse_expiry_string_invalid(self):
        """Test invalid expiry string returns None"""
        result = parse_expiry_string("INVALID")
        assert result is None

    # =========================================================================
    # Days to expiry
    # =========================================================================

    def test_days_to_expiry_future(self):
        """Test days to expiry for future date"""
        today = datetime(2025, 12, 18)
        result = days_to_expiry("25DEC25", today)
        assert result == 7

    def test_days_to_expiry_past(self):
        """Test days to expiry for past date returns 0"""
        today = datetime(2025, 12, 26)
        result = days_to_expiry("25DEC25", today)
        assert result == 0

    def test_days_to_expiry_same_day(self):
        """Test days to expiry on expiry day"""
        today = datetime(2025, 12, 25)
        result = days_to_expiry("25DEC25", today)
        assert result == 0

    # =========================================================================
    # Rollover window check
    # =========================================================================

    def test_within_rollover_window_true(self):
        """6 days to expiry, 7 day threshold -> within window"""
        today = datetime(2025, 12, 19)
        result = is_within_rollover_window("25DEC25", rollover_days=7, from_date=today)
        assert result is True

    def test_within_rollover_window_false(self):
        """10 days to expiry, 7 day threshold -> not within window"""
        today = datetime(2025, 12, 15)
        result = is_within_rollover_window("25DEC25", rollover_days=7, from_date=today)
        assert result is False

    def test_within_rollover_window_exactly_7_days(self):
        """Exactly 7 days to expiry, 7 day threshold -> not within (need < 7)"""
        today = datetime(2025, 12, 18)
        result = is_within_rollover_window("25DEC25", rollover_days=7, from_date=today)
        assert result is False

    # =========================================================================
    # Rollover strike calculation
    # =========================================================================

    def test_rollover_strike_round_to_lower_1000(self):
        """52100 -> 52000 (prefer 1000s, closer to 52000)"""
        result = get_rollover_strike(52100, strike_interval=500, prefer_1000s=True)
        assert result == 52000

    def test_rollover_strike_round_to_upper_1000(self):
        """52850 -> 53000 (prefer 1000s, closer to 53000)"""
        result = get_rollover_strike(52850, strike_interval=500, prefer_1000s=True)
        assert result == 53000

    def test_rollover_strike_stay_at_500(self):
        """52400 -> 52500 (closer to 52500 than any 1000)"""
        result = get_rollover_strike(52400, strike_interval=500, prefer_1000s=True)
        assert result == 52500

    def test_rollover_strike_already_1000(self):
        """52050 -> 52000 (already rounds to 1000)"""
        result = get_rollover_strike(52050, strike_interval=500, prefer_1000s=True)
        assert result == 52000

    def test_rollover_strike_no_prefer_1000s(self):
        """52100 -> 52000 (nearest 500 without preference)"""
        result = get_rollover_strike(52100, strike_interval=500, prefer_1000s=False)
        assert result == 52000

    def test_rollover_strike_mid_point(self):
        """52250 -> 52000 (equidistant, prefer 1000s)"""
        result = get_rollover_strike(52250, strike_interval=500, prefer_1000s=True)
        assert result == 52000

    def test_rollover_strike_mid_point_upper(self):
        """52750 -> 53000 (equidistant to 52500 and 53000, prefer 1000)"""
        result = get_rollover_strike(52750, strike_interval=500, prefer_1000s=True)
        assert result == 53000

    # =========================================================================
    # Symbol formatting
    # =========================================================================

    def test_banknifty_option_symbol_zerodha(self):
        """Test Bank Nifty option symbol for Zerodha"""
        result = format_banknifty_option_symbol("25DEC25", 52000, "PE", "zerodha")
        assert result == "BANKNIFTY25DEC2552000PE"

    def test_banknifty_option_symbol_ce(self):
        """Test Bank Nifty CE option symbol"""
        result = format_banknifty_option_symbol("25DEC25", 52000, "CE", "zerodha")
        assert result == "BANKNIFTY25DEC2552000CE"

    def test_gold_mini_futures_symbol_zerodha(self):
        """Test Gold Mini futures symbol for Zerodha"""
        result = format_gold_mini_futures_symbol("25DEC31", "zerodha")
        assert result == "GOLDM25DEC31FUT"

    # =========================================================================
    # Market hours check
    # =========================================================================

    def test_market_hours_nse_within(self):
        """10 AM on weekday is within NSE hours"""
        check_time = datetime(2025, 12, 15, 10, 0)  # Monday 10 AM
        result = is_market_hours("BANK_NIFTY", check_time)
        assert result is True

    def test_market_hours_nse_before(self):
        """8 AM is before NSE open"""
        check_time = datetime(2025, 12, 15, 8, 0)  # Monday 8 AM
        result = is_market_hours("BANK_NIFTY", check_time)
        assert result is False

    def test_market_hours_nse_after(self):
        """4 PM is after NSE close"""
        check_time = datetime(2025, 12, 15, 16, 0)  # Monday 4 PM
        result = is_market_hours("BANK_NIFTY", check_time)
        assert result is False

    def test_market_hours_mcx_evening(self):
        """8 PM on weekday is within MCX hours"""
        check_time = datetime(2025, 12, 15, 20, 0)  # Monday 8 PM
        result = is_market_hours("GOLD_MINI", check_time)
        assert result is True

    def test_market_hours_weekend(self):
        """Saturday is not market hours"""
        check_time = datetime(2025, 12, 20, 10, 0)  # Saturday 10 AM
        result = is_market_hours("BANK_NIFTY", check_time)
        assert result is False


class TestRolloverScanner:
    """Tests for rollover_scanner.py"""

    @pytest.fixture
    def mock_portfolio(self):
        """Create mock portfolio state manager"""
        portfolio = Mock()
        return portfolio

    @pytest.fixture
    def config(self):
        """Create test config"""
        config = PortfolioConfig()
        config.banknifty_rollover_days = 7
        config.gold_mini_rollover_days = 8
        return config

    def test_scanner_no_positions(self, mock_portfolio, config):
        """Test scanner with no open positions"""
        from live.rollover_scanner import RolloverScanner

        mock_state = Mock()
        mock_state.get_open_positions.return_value = {}
        mock_portfolio.get_current_state.return_value = mock_state

        scanner = RolloverScanner(config)
        result = scanner.scan_positions(mock_portfolio)

        assert result.total_positions == 0
        assert result.positions_to_roll == 0
        assert len(result.candidates) == 0

    def test_scanner_position_needs_rollover(self, mock_portfolio, config):
        """Test scanner identifies position needing rollover"""
        from live.rollover_scanner import RolloverScanner

        # Create position expiring in 5 days (within 7-day window)
        position = Position(
            position_id="BANK_NIFTY_Long_1",
            instrument="BANK_NIFTY",
            entry_timestamp=datetime.now(),
            entry_price=52000,
            lots=3,
            quantity=105,
            initial_stop=51500,
            current_stop=51500,
            highest_close=52000,
            expiry="25DEC25",  # December 25, 2025
            strike=52000
        )

        mock_state = Mock()
        mock_state.get_open_positions.return_value = {"BANK_NIFTY_Long_1": position}
        mock_portfolio.get_current_state.return_value = mock_state

        scanner = RolloverScanner(config)
        # Scan from December 20 (5 days to expiry)
        result = scanner.scan_positions(mock_portfolio, scan_date=datetime(2025, 12, 20))

        assert result.total_positions == 1
        assert result.positions_to_roll == 1
        assert len(result.candidates) == 1
        assert result.candidates[0].position.position_id == "BANK_NIFTY_Long_1"
        assert result.candidates[0].days_to_expiry == 5

    def test_scanner_position_not_in_window(self, mock_portfolio, config):
        """Test scanner skips position not in rollover window"""
        from live.rollover_scanner import RolloverScanner

        # Create position expiring in 15 days (outside 7-day window)
        position = Position(
            position_id="BANK_NIFTY_Long_1",
            instrument="BANK_NIFTY",
            entry_timestamp=datetime.now(),
            entry_price=52000,
            lots=3,
            quantity=105,
            initial_stop=51500,
            current_stop=51500,
            highest_close=52000,
            expiry="25DEC25",
            strike=52000
        )

        mock_state = Mock()
        mock_state.get_open_positions.return_value = {"BANK_NIFTY_Long_1": position}
        mock_portfolio.get_current_state.return_value = mock_state

        scanner = RolloverScanner(config)
        # Scan from December 10 (15 days to expiry)
        result = scanner.scan_positions(mock_portfolio, scan_date=datetime(2025, 12, 10))

        assert result.total_positions == 1
        assert result.positions_to_roll == 0
        assert len(result.candidates) == 0

    def test_scanner_already_rolled_position(self, mock_portfolio, config):
        """Test scanner skips already rolled position"""
        from live.rollover_scanner import RolloverScanner

        position = Position(
            position_id="BANK_NIFTY_Long_1",
            instrument="BANK_NIFTY",
            entry_timestamp=datetime.now(),
            entry_price=52000,
            lots=3,
            quantity=105,
            initial_stop=51500,
            current_stop=51500,
            highest_close=52000,
            expiry="25DEC25",
            strike=52000,
            rollover_status="rolled"  # Already rolled
        )

        mock_state = Mock()
        mock_state.get_open_positions.return_value = {"BANK_NIFTY_Long_1": position}
        mock_portfolio.get_current_state.return_value = mock_state

        scanner = RolloverScanner(config)
        result = scanner.scan_positions(mock_portfolio, scan_date=datetime(2025, 12, 20))

        assert result.positions_to_roll == 0


class TestRolloverExecutor:
    """Tests for rollover_executor.py"""

    @pytest.fixture
    def mock_openalgo(self):
        """Create mock OpenAlgo client"""
        client = Mock()
        client.get_quote.return_value = {'ltp': 52000, 'bid': 51990, 'ask': 52010}
        client.place_order.return_value = {'status': 'success', 'orderid': 'ORDER123'}
        client.get_order_status.return_value = {'status': 'COMPLETE', 'price': 52000}
        client.modify_order.return_value = {'status': 'success'}
        client.cancel_order.return_value = {'status': 'success'}
        return client

    @pytest.fixture
    def mock_portfolio(self):
        """Create mock portfolio"""
        return Mock()

    @pytest.fixture
    def config(self):
        """Create test config"""
        config = PortfolioConfig()
        config.rollover_initial_buffer_pct = 0.25
        config.rollover_increment_pct = 0.05
        config.rollover_max_retries = 5
        config.rollover_retry_interval_sec = 0.1  # Fast for testing
        config.rollover_strike_interval = 500
        config.rollover_prefer_1000s = True
        return config

    def test_executor_calculates_correct_new_strike(self, mock_openalgo, mock_portfolio, config):
        """Test executor calculates correct new strike"""
        from live.rollover_executor import RolloverExecutor
        from live.rollover_scanner import RolloverCandidate

        # Set LTP to 52100 - should round to 52000
        mock_openalgo.get_quote.return_value = {'ltp': 52100, 'bid': 52090, 'ask': 52110}

        executor = RolloverExecutor(mock_openalgo, mock_portfolio, config)

        position = Position(
            position_id="BANK_NIFTY_Long_1",
            instrument="BANK_NIFTY",
            entry_timestamp=datetime.now(),
            entry_price=51500,
            lots=3,
            quantity=105,
            initial_stop=51000,
            current_stop=51000,
            highest_close=52000,
            expiry="25DEC25",
            strike=51500,
            pe_symbol="BANKNIFTY25DEC2551500PE",
            ce_symbol="BANKNIFTY25DEC2551500CE"
        )

        candidate = RolloverCandidate(
            position=position,
            days_to_expiry=5,
            current_expiry="25DEC25",
            next_expiry="26JAN28",
            next_expiry_date=datetime(2026, 1, 28),
            instrument="BANK_NIFTY",
            reason="Test"
        )

        # Mock market hours
        with patch('live.rollover_executor.is_market_hours', return_value=True):
            result = executor._rollover_banknifty_position(candidate, dry_run=True)

        assert result.new_strike == 52000  # 52100 -> 52000 (prefer 1000s)

    def test_executor_dry_run_no_orders(self, mock_openalgo, mock_portfolio, config):
        """Test dry run doesn't place orders"""
        from live.rollover_executor import RolloverExecutor
        from live.rollover_scanner import RolloverCandidate

        executor = RolloverExecutor(mock_openalgo, mock_portfolio, config)

        position = Position(
            position_id="BANK_NIFTY_Long_1",
            instrument="BANK_NIFTY",
            entry_timestamp=datetime.now(),
            entry_price=52000,
            lots=3,
            quantity=105,
            initial_stop=51500,
            current_stop=51500,
            highest_close=52000,
            expiry="25DEC25",
            strike=52000,
            pe_symbol="BANKNIFTY25DEC2552000PE",
            ce_symbol="BANKNIFTY25DEC2552000CE"
        )

        candidate = RolloverCandidate(
            position=position,
            days_to_expiry=5,
            current_expiry="25DEC25",
            next_expiry="26JAN28",
            next_expiry_date=datetime(2026, 1, 28),
            instrument="BANK_NIFTY",
            reason="Test"
        )

        with patch('live.rollover_executor.is_market_hours', return_value=True):
            result = executor._rollover_banknifty_position(candidate, dry_run=True)

        assert result.success is True
        # No orders should be placed
        mock_openalgo.place_order.assert_not_called()

    def test_executor_order_retry_logic(self, mock_openalgo, mock_portfolio, config):
        """Test order retry logic increases buffer"""
        from live.rollover_executor import RolloverExecutor

        # First call returns pending, second returns complete
        mock_openalgo.get_order_status.side_effect = [
            {'status': 'PENDING'},
            {'status': 'COMPLETE', 'price': 52005}
        ]

        executor = RolloverExecutor(mock_openalgo, mock_portfolio, config)

        result = executor._execute_order_with_retry(
            "BANKNIFTY25DEC2552000PE",
            "SELL",
            105,
            "Test order"
        )

        assert result.success is True
        assert result.attempts == 2
        # Should have called modify_order once
        assert mock_openalgo.modify_order.call_count == 1


class TestNextMonthExpiry:
    """Tests for next month expiry calculation"""

    def test_next_month_banknifty_december_to_january(self):
        """December BN expiry -> January expiry"""
        current = datetime(2025, 12, 25)  # Last Wednesday Dec 2025
        next_date, next_str = get_next_month_expiry("BANK_NIFTY", current)

        assert next_date.month == 1
        assert next_date.year == 2026
        assert next_date.weekday() == 2  # Wednesday
        assert "JAN" in next_str

    def test_next_month_gold_december_to_january(self):
        """December Gold expiry -> January expiry"""
        current = datetime(2025, 12, 31)
        next_date, next_str = get_next_month_expiry("GOLD_MINI", current)

        assert next_date.month == 1
        assert next_date.year == 2026
        assert next_date.day == 31  # Last day of Jan
        assert "JAN" in next_str

    def test_next_month_gold_november_to_december(self):
        """November Gold expiry -> December expiry"""
        current = datetime(2025, 11, 30)
        next_date, next_str = get_next_month_expiry("GOLD_MINI", current)

        assert next_date.month == 12
        assert next_date.year == 2025
        assert next_date.day == 31


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
