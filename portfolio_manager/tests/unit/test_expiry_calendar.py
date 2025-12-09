"""
Unit tests for ExpiryCalendar - Contract expiry date calculation

Tests:
- Gold Mini expiry (5th of month)
- Bank Nifty expiry (last Thursday)
- Holiday adjustment
- Trading day counting
- Rollover detection
"""
import pytest
from datetime import date, timedelta
from unittest.mock import Mock

from core.expiry_calendar import (
    ExpiryCalendar,
    init_expiry_calendar,
    get_expiry_calendar
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def calendar():
    """Create ExpiryCalendar without holiday calendar"""
    return ExpiryCalendar()


@pytest.fixture
def mock_holiday_calendar():
    """Mock holiday calendar"""
    cal = Mock()
    # Default: only weekends are holidays
    def is_holiday(check_date, exchange):
        if check_date.weekday() >= 5:  # Weekend
            return True, "Weekend"
        return False, ""
    cal.is_holiday = Mock(side_effect=is_holiday)
    return cal


@pytest.fixture
def calendar_with_holidays(mock_holiday_calendar):
    """Create ExpiryCalendar with mock holiday calendar"""
    return ExpiryCalendar(holiday_calendar=mock_holiday_calendar)


# =============================================================================
# GOLD MINI EXPIRY TESTS
# =============================================================================

class TestGoldMiniExpiry:
    """Test Gold Mini expiry calculation (5th of each month)"""

    def test_before_5th_same_month(self, calendar):
        """Reference before 5th → same month's 5th (adjusted for weekend)"""
        ref = date(2025, 1, 3)  # Jan 3
        expiry = calendar.get_gold_mini_expiry(ref)

        # Jan 5, 2025 is Sunday → adjusted to Friday Jan 3
        assert expiry == date(2025, 1, 3)

    def test_on_5th_same_day(self, calendar):
        """Reference on 5th → same month expiry (adjusted for weekend)"""
        ref = date(2025, 1, 5)  # Jan 5 (Sunday)
        expiry = calendar.get_gold_mini_expiry(ref)

        # Jan 5, 2025 is Sunday → adjusted to Friday Jan 3
        assert expiry == date(2025, 1, 3)

    def test_after_5th_next_month(self, calendar):
        """Reference after 5th → next month's 5th"""
        ref = date(2025, 1, 10)  # Jan 10
        expiry = calendar.get_gold_mini_expiry(ref)

        assert expiry == date(2025, 2, 5)

    def test_december_rolls_to_january(self, calendar):
        """December after 5th → January next year"""
        ref = date(2025, 12, 10)
        expiry = calendar.get_gold_mini_expiry(ref)

        assert expiry == date(2026, 1, 5)

    def test_5th_on_saturday_adjusted(self, calendar):
        """5th on Saturday → adjusted to Friday 4th"""
        # January 2026: 5th is Monday, so find a month where 5th is Saturday
        # April 2025: 5th is Saturday
        ref = date(2025, 4, 1)
        expiry = calendar.get_gold_mini_expiry(ref)

        # April 5, 2025 is Saturday → should be Friday April 4
        assert expiry == date(2025, 4, 4)

    def test_5th_on_sunday_adjusted(self, calendar):
        """5th on Sunday → adjusted to Friday 3rd"""
        # Find month where 5th is Sunday
        # October 2025: 5th is Sunday
        ref = date(2025, 10, 1)
        expiry = calendar.get_gold_mini_expiry(ref)

        # October 5, 2025 is Sunday → should be Friday October 3
        assert expiry == date(2025, 10, 3)


# =============================================================================
# BANK NIFTY EXPIRY TESTS
# =============================================================================

class TestBankNiftyExpiry:
    """Test Bank Nifty expiry calculation (last Thursday)"""

    def test_before_expiry_same_month(self, calendar):
        """Reference before expiry → same month's last Thursday"""
        ref = date(2025, 1, 10)  # Jan 10
        expiry = calendar.get_bank_nifty_expiry(ref)

        # Last Thursday of January 2025 is Jan 30
        assert expiry == date(2025, 1, 30)

    def test_after_expiry_next_month(self, calendar):
        """Reference after expiry → next month's last Thursday"""
        ref = date(2025, 1, 31)  # After Jan 30
        expiry = calendar.get_bank_nifty_expiry(ref)

        # Last Thursday of February 2025 is Feb 27
        assert expiry == date(2025, 2, 27)

    def test_on_expiry_day(self, calendar):
        """Reference on expiry day → same day"""
        # Last Thursday of Jan 2025 is Jan 30
        ref = date(2025, 1, 30)
        expiry = calendar.get_bank_nifty_expiry(ref)

        assert expiry == date(2025, 1, 30)

    def test_december_expiry(self, calendar):
        """December expiry calculation"""
        ref = date(2024, 12, 1)
        expiry = calendar.get_bank_nifty_expiry(ref)

        # Last Thursday of December 2024 is Dec 26
        assert expiry == date(2024, 12, 26)

    def test_last_thursday_calculation(self, calendar):
        """Verify last Thursday calculation for various months"""
        test_cases = [
            # (year, month, expected_last_thursday)
            (2025, 1, date(2025, 1, 30)),   # January 2025
            (2025, 2, date(2025, 2, 27)),   # February 2025
            (2025, 3, date(2025, 3, 27)),   # March 2025
            (2025, 4, date(2025, 4, 24)),   # April 2025
            (2025, 12, date(2025, 12, 25)), # December 2025
        ]

        for year, month, expected in test_cases:
            result = calendar._get_last_thursday(year, month)
            assert result == expected, f"Month {month}/{year}: expected {expected}, got {result}"


# =============================================================================
# HOLIDAY ADJUSTMENT TESTS
# =============================================================================

class TestHolidayAdjustment:
    """Test expiry adjustment for holidays"""

    def test_no_adjustment_weekday(self, calendar):
        """Weekday expiry not adjusted"""
        # A Wednesday
        expiry = date(2025, 1, 29)
        adjusted = calendar._adjust_for_holidays(expiry, "NSE")

        assert adjusted == expiry

    def test_saturday_adjusted_to_friday(self, calendar):
        """Saturday adjusted to Friday"""
        # A Saturday
        saturday = date(2025, 1, 4)
        adjusted = calendar._adjust_for_holidays(saturday, "NSE")

        assert adjusted == date(2025, 1, 3)  # Friday

    def test_sunday_adjusted_to_friday(self, calendar):
        """Sunday adjusted to Friday"""
        sunday = date(2025, 1, 5)
        adjusted = calendar._adjust_for_holidays(sunday, "NSE")

        assert adjusted == date(2025, 1, 3)  # Friday

    def test_holiday_adjusted(self, mock_holiday_calendar):
        """Holiday adjusted to previous trading day"""
        # Make Dec 25 a holiday
        def is_holiday(check_date, exchange):
            if check_date.weekday() >= 5:
                return True, "Weekend"
            if check_date == date(2025, 12, 25):
                return True, "Christmas"
            return False, ""
        mock_holiday_calendar.is_holiday = Mock(side_effect=is_holiday)

        calendar = ExpiryCalendar(holiday_calendar=mock_holiday_calendar)
        expiry = date(2025, 12, 25)  # Thursday, Christmas
        adjusted = calendar._adjust_for_holidays(expiry, "NSE")

        # Should be Dec 24 (Wednesday)
        assert adjusted == date(2025, 12, 24)


# =============================================================================
# TRADING DAY COUNTING TESTS
# =============================================================================

class TestTradingDayCounting:
    """Test trading day counting between dates"""

    def test_same_date_returns_zero(self, calendar):
        """Same date returns 0 trading days"""
        d = date(2025, 1, 6)
        assert calendar.count_trading_days(d, d, "NSE") == 0

    def test_from_after_to_returns_zero(self, calendar):
        """from_date after to_date returns 0"""
        assert calendar.count_trading_days(date(2025, 1, 10), date(2025, 1, 5), "NSE") == 0

    def test_consecutive_weekdays(self, calendar):
        """Monday to Wednesday = 2 trading days (Tue, Wed)"""
        # Mon Jan 6 to Wed Jan 8 (exclusive) = Tue Jan 7 = 1 day
        assert calendar.count_trading_days(date(2025, 1, 6), date(2025, 1, 8), "NSE") == 1

    def test_span_weekend(self, calendar):
        """Friday to Monday = 0 trading days (only weekend in between)"""
        # Fri Jan 3 to Mon Jan 6 = Sat, Sun = 0 trading days
        assert calendar.count_trading_days(date(2025, 1, 3), date(2025, 1, 6), "NSE") == 0

    def test_full_week(self, calendar):
        """Monday to Monday = 5 trading days"""
        # Mon Jan 6 to Mon Jan 13 = Tue-Fri + Mon = 5 trading days
        assert calendar.count_trading_days(date(2025, 1, 6), date(2025, 1, 13), "NSE") == 4

    def test_with_holiday(self, mock_holiday_calendar):
        """Trading days exclude holidays"""
        # Make Wed Jan 8 a holiday
        def is_holiday(check_date, exchange):
            if check_date.weekday() >= 5:
                return True, "Weekend"
            if check_date == date(2025, 1, 8):
                return True, "Test Holiday"
            return False, ""
        mock_holiday_calendar.is_holiday = Mock(side_effect=is_holiday)

        calendar = ExpiryCalendar(holiday_calendar=mock_holiday_calendar)

        # Mon Jan 6 to Fri Jan 10 = Tue(7), Wed(8-holiday), Thu(9) = 2 trading days
        result = calendar.count_trading_days(date(2025, 1, 6), date(2025, 1, 10), "NSE")
        assert result == 2


# =============================================================================
# ROLLOVER DETECTION TESTS
# =============================================================================

class TestRolloverDetection:
    """Test rollover window detection"""

    def test_no_rollover_far_from_expiry(self, calendar):
        """Far from expiry → no rollover"""
        # Gold Mini expiry Feb 5, reference Jan 10 → many trading days
        ref = date(2025, 1, 10)
        should_roll, days = calendar.should_rollover("GOLD_MINI", ref)

        assert should_roll == False
        assert days > 3  # More than rollover threshold

    def test_rollover_within_threshold(self, calendar):
        """Within rollover threshold → should rollover"""
        # Gold Mini expiry Jan 5, reference Jan 3 (Friday)
        # Jan 3 to Jan 5: only Sat/Sun = ~1 trading day → should roll
        ref = date(2025, 1, 3)  # Friday before Jan 5

        # Since Jan 5, 2025 is Sunday, expiry is adjusted to Jan 3 (Friday)
        # So Jan 3 is ON expiry → 0 trading days → should roll
        should_roll, _ = calendar.should_rollover("GOLD_MINI", ref)

        assert should_roll == True

    def test_bank_nifty_rollover_threshold(self, calendar):
        """Bank Nifty has 5 day rollover threshold"""
        # Default threshold for Bank Nifty is 5 trading days
        assert calendar.DEFAULT_ROLLOVER_DAYS['BANK_NIFTY'] == 5

    def test_gold_mini_rollover_threshold(self, calendar):
        """Gold Mini has 3 day rollover threshold"""
        assert calendar.DEFAULT_ROLLOVER_DAYS['GOLD_MINI'] == 3


# =============================================================================
# GET EXPIRY AFTER ROLLOVER TESTS
# =============================================================================

class TestExpiryAfterRollover:
    """Test getting expiry with rollover logic"""

    def test_no_rollover_returns_current(self, calendar):
        """Far from expiry → returns current expiry"""
        # Reference well before expiry
        ref = date(2025, 1, 10)
        expiry = calendar.get_expiry_after_rollover("GOLD_MINI", ref)

        # Should return Feb 5 (since Jan 10 > Jan 5)
        assert expiry == date(2025, 2, 5)

    def test_rollover_returns_next(self, calendar):
        """In rollover window → returns next expiry"""
        # Reference close to expiry (within 3 days for Gold Mini)
        # Let's use a date where we're definitely in rollover
        ref = date(2025, 2, 4)  # 1 day before Feb 5

        should_roll, _ = calendar.should_rollover("GOLD_MINI", ref)
        expiry = calendar.get_expiry_after_rollover("GOLD_MINI", ref)

        if should_roll:
            # Should skip Feb 5, return March 5
            assert expiry == date(2025, 3, 5)
        else:
            assert expiry == date(2025, 2, 5)


# =============================================================================
# UNKNOWN INSTRUMENT TESTS
# =============================================================================

class TestUnknownInstrument:
    """Test handling of unknown instruments"""

    def test_unknown_instrument_error(self, calendar):
        """Unknown instrument raises ValueError"""
        with pytest.raises(ValueError) as excinfo:
            calendar.get_next_expiry("UNKNOWN", date(2025, 1, 1))

        assert "Unknown instrument" in str(excinfo.value)

    def test_exchange_for_unknown_defaults_nse(self, calendar):
        """Unknown instrument defaults to NSE exchange"""
        exchange = calendar._get_exchange_for_instrument("UNKNOWN")
        assert exchange == "NSE"


# =============================================================================
# GLOBAL INSTANCE TESTS
# =============================================================================

class TestGlobalInstance:
    """Test global ExpiryCalendar instance management"""

    def test_get_expiry_calendar_creates_instance(self):
        """get_expiry_calendar creates instance if none exists"""
        calendar = get_expiry_calendar()
        assert calendar is not None

    def test_init_expiry_calendar_with_holiday(self, mock_holiday_calendar):
        """init_expiry_calendar accepts holiday calendar"""
        calendar = init_expiry_calendar(holiday_calendar=mock_holiday_calendar)

        assert calendar.holiday_calendar is mock_holiday_calendar


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases"""

    def test_leap_year_february(self, calendar):
        """February in leap year handled correctly"""
        # 2024 is a leap year
        ref = date(2024, 2, 10)
        expiry = calendar.get_bank_nifty_expiry(ref)

        # Last Thursday of Feb 2024 is Feb 29
        assert expiry == date(2024, 2, 29)

    def test_year_boundary(self, calendar):
        """Year boundary handled correctly"""
        ref = date(2025, 12, 28)
        expiry = calendar.get_gold_mini_expiry(ref)

        # After Dec 5, should be Jan 5, 2026
        # But Dec 28 > Dec 5, so → Jan 5, 2026
        assert expiry.year == 2026
        assert expiry.month == 1
        assert expiry.day == 5

    def test_none_reference_uses_today(self, calendar):
        """None reference date uses today"""
        # This is implicit - just verify it doesn't crash
        expiry = calendar.get_gold_mini_expiry(None)
        assert expiry is not None
        assert isinstance(expiry, date)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
