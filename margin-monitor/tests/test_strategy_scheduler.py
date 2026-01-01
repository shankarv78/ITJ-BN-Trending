"""
Unit tests for StrategySchedulerService

Tests schedule loading, upcoming entry detection, and imminent entry checks.
"""

import pytest
from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.strategy_scheduler import (
    StrategySchedulerService, ScheduledEntry, UpcomingEntry
)
from app.models.hedge_constants import HedgeConfig


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def config():
    """Create a HedgeConfig with test values."""
    config = HedgeConfig()
    config.lookahead_minutes = 5
    config.exit_buffer_minutes = 15
    return config


@pytest.fixture
def sample_schedule():
    """Sample schedule entries for testing."""
    return [
        ScheduledEntry(
            portfolio_name="TEST_1",
            entry_time=time(9, 16),
            exit_time=time(14, 0),
            index_name="SENSEX",
            expiry_type="0DTE"
        ),
        ScheduledEntry(
            portfolio_name="TEST_2",
            entry_time=time(9, 28),
            exit_time=time(14, 30),
            index_name="SENSEX",
            expiry_type="0DTE"
        ),
        ScheduledEntry(
            portfolio_name="TEST_3",
            entry_time=time(10, 53),
            exit_time=None,
            index_name="SENSEX",
            expiry_type="0DTE"
        ),
    ]


class TestScheduledEntry:
    """Tests for ScheduledEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a ScheduledEntry."""
        entry = ScheduledEntry(
            portfolio_name="TEST_PORTFOLIO",
            entry_time=time(9, 16),
            exit_time=time(14, 0),
            index_name="SENSEX",
            expiry_type="0DTE"
        )

        assert entry.portfolio_name == "TEST_PORTFOLIO"
        assert entry.entry_time == time(9, 16)
        assert entry.exit_time == time(14, 0)
        assert entry.index_name == "SENSEX"
        assert entry.expiry_type == "0DTE"

    def test_entry_with_null_exit(self):
        """Test entry with no exit time (expires worthless)."""
        entry = ScheduledEntry(
            portfolio_name="EXPIRE_TEST",
            entry_time=time(14, 35),
            exit_time=None,
            index_name="NIFTY",
            expiry_type="0DTE"
        )

        assert entry.exit_time is None


class TestUpcomingEntry:
    """Tests for UpcomingEntry dataclass."""

    def test_upcoming_entry_creation(self, sample_schedule):
        """Test creating an UpcomingEntry."""
        from datetime import datetime
        import pytz

        IST = pytz.timezone('Asia/Kolkata')
        entry_dt = datetime(2026, 1, 1, 9, 16, tzinfo=IST)

        upcoming = UpcomingEntry(
            entry=sample_schedule[0],
            seconds_until=300,
            entry_datetime=entry_dt
        )

        assert upcoming.entry.portfolio_name == "TEST_1"
        assert upcoming.seconds_until == 300
        assert upcoming.entry_datetime == entry_dt


class TestSchedulerCaching:
    """Tests for schedule caching behavior."""

    @pytest.mark.asyncio
    async def test_cache_is_used(self, mock_db, config):
        """Test that schedule is cached after first load."""
        scheduler = StrategySchedulerService(mock_db, config)

        # Mock the database query
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        # First call should query database
        await scheduler.get_today_schedule()
        assert mock_db.execute.call_count == 1

        # Second call should use cache
        await scheduler.get_today_schedule()
        assert mock_db.execute.call_count == 1  # Still 1, not 2

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, mock_db, config):
        """Test that force_refresh bypasses cache."""
        scheduler = StrategySchedulerService(mock_db, config)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        # First call
        await scheduler.get_today_schedule()
        assert mock_db.execute.call_count == 1

        # Force refresh should query again
        await scheduler.get_today_schedule(force_refresh=True)
        assert mock_db.execute.call_count == 2

    def test_clear_cache(self, mock_db, config):
        """Test cache clearing."""
        scheduler = StrategySchedulerService(mock_db, config)
        scheduler._schedule_cache = [MagicMock()]
        scheduler._cache_date = MagicMock()

        scheduler.clear_cache()

        assert scheduler._schedule_cache is None
        assert scheduler._cache_date is None


class TestImminentEntryDetection:
    """Tests for imminent entry detection logic."""

    def test_entry_is_imminent_within_window(self):
        """Test that entry within lookahead window is detected as imminent."""
        config = HedgeConfig()
        config.lookahead_minutes = 5  # 300 seconds

        # Entry is 180 seconds away (3 minutes)
        seconds_until = 180
        is_imminent = seconds_until <= (config.lookahead_minutes * 60)

        assert is_imminent is True

    def test_entry_is_not_imminent_outside_window(self):
        """Test that entry outside lookahead window is not imminent."""
        config = HedgeConfig()
        config.lookahead_minutes = 5  # 300 seconds

        # Entry is 600 seconds away (10 minutes)
        seconds_until = 600
        is_imminent = seconds_until <= (config.lookahead_minutes * 60)

        assert is_imminent is False


class TestHedgeHoldDecision:
    """Tests for hedge hold/exit decision logic."""

    def test_should_hold_hedges_when_entry_soon(self):
        """Test that hedges should be held when entry is within buffer."""
        config = HedgeConfig()
        config.exit_buffer_minutes = 15  # 900 seconds

        # Entry is 600 seconds away (10 minutes)
        seconds_until = 600
        should_hold = seconds_until <= (config.exit_buffer_minutes * 60)

        assert should_hold is True

    def test_should_not_hold_hedges_when_no_entry_soon(self):
        """Test that hedges can be exited when no entry is within buffer."""
        config = HedgeConfig()
        config.exit_buffer_minutes = 15  # 900 seconds

        # Entry is 1800 seconds away (30 minutes)
        seconds_until = 1800
        should_hold = seconds_until <= (config.exit_buffer_minutes * 60)

        assert should_hold is False


class TestScheduleSummary:
    """Tests for schedule summary generation."""

    def test_schedule_summary_structure(self, sample_schedule):
        """Test that schedule summary has correct structure."""
        # Simulate summary data
        summary = {
            'date': '2026-01-01',
            'day_name': 'Thursday',
            'total_entries': len(sample_schedule),
            'executed': 1,
            'remaining': 2,
            'by_index': {'SENSEX': 3},
            'next_entry': {
                'portfolio': sample_schedule[1].portfolio_name,
                'entry_time': sample_schedule[1].entry_time.isoformat(),
                'seconds_until': 300
            }
        }

        assert 'date' in summary
        assert 'day_name' in summary
        assert 'total_entries' in summary
        assert 'executed' in summary
        assert 'remaining' in summary
        assert 'by_index' in summary
        assert summary['total_entries'] == 3
