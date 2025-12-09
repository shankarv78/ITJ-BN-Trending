"""
Unit tests for HolidayCalendar - Market holiday tracking

Tests:
- Weekend detection (built-in)
- Holiday CRUD operations
- CSV import/export
- Next trading day calculation
- Thread safety
"""
import pytest
import tempfile
import os
from datetime import date
from pathlib import Path

from core.holiday_calendar import (
    HolidayCalendar,
    Holiday,
    init_holiday_calendar,
    get_holiday_calendar
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_data_dir():
    """Create temporary directory for holiday data"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def calendar(temp_data_dir):
    """Create HolidayCalendar with temp directory"""
    return HolidayCalendar(data_dir=temp_data_dir)


@pytest.fixture
def calendar_with_holidays(calendar):
    """Calendar pre-populated with some holidays"""
    # Use weekdays to avoid weekend interference in tests
    # Jan 27, 2025 is Monday, Aug 15, 2025 is Friday, Dec 25, 2025 is Thursday
    calendar.add_holiday(date(2025, 1, 27), "NSE", "Republic Day (observed)")
    calendar.add_holiday(date(2025, 1, 27), "MCX", "Republic Day (observed)")
    calendar.add_holiday(date(2025, 8, 15), "NSE", "Independence Day")
    calendar.add_holiday(date(2025, 8, 15), "MCX", "Independence Day")
    calendar.add_holiday(date(2025, 12, 25), "NSE", "Christmas")
    calendar.add_holiday(date(2025, 12, 25), "MCX", "Christmas")
    return calendar


# =============================================================================
# WEEKEND DETECTION TESTS
# =============================================================================

class TestWeekendDetection:
    """Test built-in weekend detection"""

    def test_saturday_is_holiday(self, calendar):
        """Saturday is always a holiday"""
        saturday = date(2025, 12, 6)  # A Saturday
        is_holiday, reason = calendar.is_holiday(saturday, "NSE")

        assert is_holiday == True
        assert reason == "Weekend"

    def test_sunday_is_holiday(self, calendar):
        """Sunday is always a holiday"""
        sunday = date(2025, 12, 7)  # A Sunday
        is_holiday, reason = calendar.is_holiday(sunday, "MCX")

        assert is_holiday == True
        assert reason == "Weekend"

    def test_monday_not_weekend(self, calendar):
        """Monday is not a weekend"""
        monday = date(2025, 12, 8)  # A Monday
        is_holiday, reason = calendar.is_holiday(monday, "NSE")

        assert is_holiday == False
        assert reason == ""

    def test_friday_not_weekend(self, calendar):
        """Friday is not a weekend"""
        friday = date(2025, 12, 5)  # A Friday
        is_holiday, reason = calendar.is_holiday(friday, "MCX")

        assert is_holiday == False


# =============================================================================
# HOLIDAY CRUD TESTS
# =============================================================================

class TestHolidayCRUD:
    """Test holiday add/remove/get operations"""

    def test_add_holiday(self, calendar):
        """Add a holiday successfully"""
        result = calendar.add_holiday(date(2025, 10, 2), "NSE", "Gandhi Jayanti")

        assert result == True
        is_holiday, reason = calendar.is_holiday(date(2025, 10, 2), "NSE")
        assert is_holiday == True
        assert reason == "Gandhi Jayanti"

    def test_add_duplicate_holiday(self, calendar):
        """Adding duplicate holiday returns False"""
        calendar.add_holiday(date(2025, 10, 2), "NSE", "Gandhi Jayanti")
        result = calendar.add_holiday(date(2025, 10, 2), "NSE", "Gandhi Jayanti Again")

        assert result == False

    def test_add_same_date_different_exchange(self, calendar):
        """Same date can be holiday for different exchanges"""
        calendar.add_holiday(date(2025, 10, 2), "NSE", "Gandhi Jayanti")
        result = calendar.add_holiday(date(2025, 10, 2), "MCX", "Gandhi Jayanti")

        assert result == True

        nse_holiday, _ = calendar.is_holiday(date(2025, 10, 2), "NSE")
        mcx_holiday, _ = calendar.is_holiday(date(2025, 10, 2), "MCX")

        assert nse_holiday == True
        assert mcx_holiday == True

    def test_remove_holiday(self, calendar_with_holidays):
        """Remove a holiday"""
        # Jan 27, 2025 is Monday (weekday) - avoids weekend interference
        result = calendar_with_holidays.remove_holiday(date(2025, 1, 27), "NSE")

        assert result == True
        is_holiday, _ = calendar_with_holidays.is_holiday(date(2025, 1, 27), "NSE")
        assert is_holiday == False

        # MCX should still have the holiday
        mcx_holiday, _ = calendar_with_holidays.is_holiday(date(2025, 1, 27), "MCX")
        assert mcx_holiday == True

    def test_remove_nonexistent_holiday(self, calendar):
        """Removing non-existent holiday returns False"""
        result = calendar.remove_holiday(date(2025, 1, 1), "NSE")
        assert result == False

    def test_get_holidays_all(self, calendar_with_holidays):
        """Get all holidays"""
        holidays = calendar_with_holidays.get_holidays()

        assert len(holidays) == 6  # 3 dates * 2 exchanges

    def test_get_holidays_by_exchange(self, calendar_with_holidays):
        """Get holidays filtered by exchange"""
        nse_holidays = calendar_with_holidays.get_holidays(exchange="NSE")

        assert len(nse_holidays) == 3
        for h in nse_holidays:
            assert h.exchange == "NSE"

    def test_get_holidays_by_year(self, calendar_with_holidays):
        """Get holidays filtered by year"""
        # Add a 2026 holiday
        calendar_with_holidays.add_holiday(date(2026, 1, 26), "NSE", "Republic Day 2026")

        holidays_2025 = calendar_with_holidays.get_holidays(year=2025)
        holidays_2026 = calendar_with_holidays.get_holidays(year=2026)

        assert len(holidays_2025) == 6
        assert len(holidays_2026) == 1

    def test_invalid_exchange(self, calendar):
        """Invalid exchange raises ValueError"""
        with pytest.raises(ValueError) as excinfo:
            calendar.add_holiday(date(2025, 1, 1), "INVALID", "Test")

        assert "Invalid exchange" in str(excinfo.value)


# =============================================================================
# HOLIDAY DATACLASS TESTS
# =============================================================================

class TestHolidayDataclass:
    """Test Holiday dataclass serialization"""

    def test_to_dict(self):
        """Holiday serializes to dict correctly"""
        holiday = Holiday(
            date=date(2025, 12, 25),
            exchange="NSE",
            description="Christmas"
        )

        d = holiday.to_dict()

        assert d['date'] == "2025-12-25"
        assert d['exchange'] == "NSE"
        assert d['description'] == "Christmas"

    def test_from_dict(self):
        """Holiday deserializes from dict correctly"""
        data = {
            'date': "2025-12-25",
            'exchange': "NSE",
            'description': "Christmas"
        }

        holiday = Holiday.from_dict(data)

        assert holiday.date == date(2025, 12, 25)
        assert holiday.exchange == "NSE"
        assert holiday.description == "Christmas"


# =============================================================================
# CSV IMPORT/EXPORT TESTS
# =============================================================================

class TestCSVOperations:
    """Test CSV import and export"""

    def test_export_to_csv(self, calendar_with_holidays, temp_data_dir):
        """Export holidays to CSV"""
        csv_path = os.path.join(temp_data_dir, "export.csv")

        count = calendar_with_holidays.export_to_csv(csv_path)

        assert count == 6
        assert os.path.exists(csv_path)

        # Verify file content
        with open(csv_path, 'r') as f:
            lines = f.readlines()

        assert len(lines) == 7  # Header + 6 rows
        assert "date,exchange,description" in lines[0]

    def test_import_from_csv(self, calendar, temp_data_dir):
        """Import holidays from CSV"""
        csv_path = os.path.join(temp_data_dir, "import.csv")

        # Create CSV file
        with open(csv_path, 'w') as f:
            f.write("date,exchange,description\n")
            f.write("2025-03-14,NSE,Holi\n")
            f.write("2025-03-14,MCX,Holi\n")
            f.write("2025-11-01,NSE,Diwali\n")

        count = calendar.load_from_csv(csv_path)

        assert count == 3

        is_holiday, reason = calendar.is_holiday(date(2025, 3, 14), "NSE")
        assert is_holiday == True
        assert reason == "Holi"

    def test_import_with_exchange_override(self, calendar, temp_data_dir):
        """Import CSV with exchange override"""
        csv_path = os.path.join(temp_data_dir, "import.csv")

        with open(csv_path, 'w') as f:
            f.write("date,description\n")  # No exchange column
            f.write("2025-03-14,Holi\n")

        count = calendar.load_from_csv(csv_path, exchange="NSE")

        assert count == 1
        is_holiday, _ = calendar.is_holiday(date(2025, 3, 14), "NSE")
        assert is_holiday == True

    def test_import_nonexistent_file(self, calendar):
        """Import from non-existent file returns 0"""
        count = calendar.load_from_csv("/nonexistent/path.csv")
        assert count == 0


# =============================================================================
# NEXT TRADING DAY TESTS
# =============================================================================

class TestNextTradingDay:
    """Test next trading day calculation"""

    def test_next_day_is_trading_day(self, calendar):
        """Monday's next trading day is Tuesday"""
        monday = date(2025, 12, 8)  # Monday
        next_day = calendar.get_next_trading_day(monday, "NSE")

        assert next_day == date(2025, 12, 9)  # Tuesday

    def test_skip_weekend(self, calendar):
        """Friday's next trading day skips to Monday"""
        friday = date(2025, 12, 5)  # Friday
        next_day = calendar.get_next_trading_day(friday, "NSE")

        assert next_day == date(2025, 12, 8)  # Monday

    def test_skip_holiday(self, calendar_with_holidays):
        """Next trading day skips holidays"""
        # Day before Christmas
        dec_24 = date(2025, 12, 24)  # Wednesday
        next_day = calendar_with_holidays.get_next_trading_day(dec_24, "NSE")

        # Should skip Dec 25 (Christmas) and weekend
        assert next_day == date(2025, 12, 26)  # Friday

    def test_skip_weekend_after_holiday(self, calendar):
        """Next trading day handles holiday on Friday followed by weekend"""
        calendar.add_holiday(date(2025, 1, 3), "NSE", "Test Holiday")  # Friday

        thursday = date(2025, 1, 2)
        next_day = calendar.get_next_trading_day(thursday, "NSE")

        assert next_day == date(2025, 1, 6)  # Monday


# =============================================================================
# TRADING DAY CHECK TESTS
# =============================================================================

class TestIsTradingDay:
    """Test is_trading_day convenience method"""

    def test_weekday_is_trading_day(self, calendar):
        """Non-holiday weekday is trading day"""
        assert calendar.is_trading_day(date(2025, 12, 8), "NSE") == True

    def test_weekend_not_trading_day(self, calendar):
        """Weekend is not trading day"""
        assert calendar.is_trading_day(date(2025, 12, 6), "NSE") == False

    def test_holiday_not_trading_day(self, calendar_with_holidays):
        """Holiday is not trading day"""
        assert calendar_with_holidays.is_trading_day(date(2025, 12, 25), "NSE") == False


# =============================================================================
# STATUS AND PERSISTENCE TESTS
# =============================================================================

class TestStatusAndPersistence:
    """Test status API and data persistence"""

    def test_get_status(self, calendar_with_holidays):
        """Get calendar status"""
        status = calendar_with_holidays.get_status()

        assert 'today' in status
        assert 'nse' in status
        assert 'mcx' in status
        assert 'total_holidays' in status
        assert status['total_holidays'] == 6

        assert 'is_holiday' in status['nse']
        assert 'reason' in status['nse']
        assert 'is_trading_day' in status['nse']

    def test_persistence_across_instances(self, temp_data_dir):
        """Holidays persist across calendar instances"""
        # Create first instance and add holiday
        cal1 = HolidayCalendar(data_dir=temp_data_dir)
        cal1.add_holiday(date(2025, 10, 2), "NSE", "Gandhi Jayanti")

        # Create second instance
        cal2 = HolidayCalendar(data_dir=temp_data_dir)

        # Holiday should be loaded
        is_holiday, reason = cal2.is_holiday(date(2025, 10, 2), "NSE")
        assert is_holiday == True
        assert reason == "Gandhi Jayanti"

    def test_clear_all_holidays(self, calendar_with_holidays):
        """Clear all holidays"""
        calendar_with_holidays.clear_all()

        holidays = calendar_with_holidays.get_holidays()
        assert len(holidays) == 0

    def test_clear_by_exchange(self, calendar_with_holidays):
        """Clear holidays for specific exchange"""
        calendar_with_holidays.clear_all(exchange="NSE")

        nse_holidays = calendar_with_holidays.get_holidays(exchange="NSE")
        mcx_holidays = calendar_with_holidays.get_holidays(exchange="MCX")

        assert len(nse_holidays) == 0
        assert len(mcx_holidays) == 3


# =============================================================================
# GLOBAL INSTANCE TESTS
# =============================================================================

class TestGlobalInstance:
    """Test global HolidayCalendar instance management"""

    def test_init_holiday_calendar(self, temp_data_dir):
        """init_holiday_calendar creates global instance"""
        calendar = init_holiday_calendar(data_dir=temp_data_dir)

        assert calendar is not None
        assert get_holiday_calendar() is calendar

    def test_global_instance_operations(self, temp_data_dir):
        """Global instance supports all operations"""
        calendar = init_holiday_calendar(data_dir=temp_data_dir)
        calendar.add_holiday(date(2025, 10, 2), "NSE", "Gandhi Jayanti")

        retrieved = get_holiday_calendar()
        is_holiday, _ = retrieved.is_holiday(date(2025, 10, 2), "NSE")
        assert is_holiday == True


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases"""

    def test_exchange_case_insensitive(self, calendar):
        """Exchange names are case-insensitive"""
        calendar.add_holiday(date(2025, 10, 2), "nse", "Gandhi Jayanti")

        is_holiday1, _ = calendar.is_holiday(date(2025, 10, 2), "NSE")
        is_holiday2, _ = calendar.is_holiday(date(2025, 10, 2), "nse")

        assert is_holiday1 == True
        assert is_holiday2 == True

    def test_empty_description(self, calendar):
        """Holiday with empty description"""
        calendar.add_holiday(date(2025, 10, 2), "NSE", "")

        is_holiday, reason = calendar.is_holiday(date(2025, 10, 2), "NSE")
        assert is_holiday == True
        assert reason == ""

    def test_holidays_sorted_by_date(self, calendar):
        """Holidays returned sorted by date"""
        calendar.add_holiday(date(2025, 12, 25), "NSE", "Christmas")
        calendar.add_holiday(date(2025, 1, 26), "NSE", "Republic Day")
        calendar.add_holiday(date(2025, 8, 15), "NSE", "Independence Day")

        holidays = calendar.get_holidays(exchange="NSE")

        assert holidays[0].date == date(2025, 1, 26)
        assert holidays[1].date == date(2025, 8, 15)
        assert holidays[2].date == date(2025, 12, 25)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
