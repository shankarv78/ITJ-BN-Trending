"""
Auto-Hedge System - Strategy Scheduler Service

Manages strategy schedule and finds upcoming entries.
Provides lookahead functionality to determine when hedges are needed.
"""

import logging
from datetime import datetime, date, time, timedelta
from typing import Optional, List, Tuple
from dataclasses import dataclass

import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hedge_models import StrategySchedule, DailySession
from app.models.hedge_constants import HEDGE_CONFIG, IndexName, ExpiryType

logger = logging.getLogger(__name__)

# India Standard Time
IST = pytz.timezone('Asia/Kolkata')


@dataclass
class ScheduledEntry:
    """Represents a scheduled strategy entry."""
    portfolio_name: str
    entry_time: time
    exit_time: Optional[time]
    index_name: str
    expiry_type: str


@dataclass
class UpcomingEntry:
    """Represents an upcoming entry with time until."""
    entry: ScheduledEntry
    seconds_until: int
    entry_datetime: datetime


class StrategySchedulerService:
    """
    Manages strategy schedule and finds upcoming entries.

    Core responsibilities:
    - Get today's schedule based on day of week
    - Find next upcoming entry
    - Determine if entry is imminent (within lookahead window)
    - Track executed vs remaining entries
    """

    def __init__(self, db: AsyncSession, config=None):
        """
        Initialize the strategy scheduler.

        Args:
            db: AsyncSession for database operations
            config: Optional HedgeConfig (uses global default if not provided)
        """
        self.db = db
        self.config = config or HEDGE_CONFIG
        self._schedule_cache: Optional[List[ScheduledEntry]] = None
        self._cache_date: Optional[date] = None

    def _now_ist(self) -> datetime:
        """Get current time in IST."""
        return datetime.now(IST)

    def _today_ist(self) -> date:
        """Get today's date in IST."""
        return self._now_ist().date()

    def _get_day_name(self, d: date = None) -> str:
        """Get day name (Monday, Tuesday, etc.) for a date."""
        if d is None:
            d = self._today_ist()
        return d.strftime("%A")

    async def get_today_schedule(self, force_refresh: bool = False) -> List[ScheduledEntry]:
        """
        Get all scheduled entries for today.

        Uses caching to avoid repeated database queries.

        Args:
            force_refresh: Force cache refresh

        Returns:
            List of ScheduledEntry objects sorted by entry_time
        """
        today = self._today_ist()

        # Return cached if valid
        if (not force_refresh and
            self._schedule_cache is not None and
            self._cache_date == today):
            return self._schedule_cache

        day_name = self._get_day_name(today)

        # Query database
        result = await self.db.execute(
            select(StrategySchedule)
            .where(StrategySchedule.day_of_week == day_name)
            .where(StrategySchedule.is_active == True)
            .order_by(StrategySchedule.entry_time)
        )
        rows = result.scalars().all()

        # Convert to dataclass
        entries = [
            ScheduledEntry(
                portfolio_name=row.portfolio_name,
                entry_time=row.entry_time,
                exit_time=row.exit_time,
                index_name=row.index_name,
                expiry_type=row.expiry_type
            )
            for row in rows
        ]

        # Update cache
        self._schedule_cache = entries
        self._cache_date = today

        logger.info(f"[SCHEDULER] Loaded {len(entries)} entries for {day_name}")

        return entries

    async def get_next_entry(self) -> Optional[UpcomingEntry]:
        """
        Get the next scheduled strategy entry.

        Returns:
            UpcomingEntry with entry details and seconds until, or None if no more entries today
        """
        now = self._now_ist()
        current_time = now.time()

        schedule = await self.get_today_schedule()

        for entry in schedule:
            if entry.entry_time > current_time:
                # Calculate seconds until entry
                entry_datetime = datetime.combine(now.date(), entry.entry_time)
                entry_datetime = IST.localize(entry_datetime)
                seconds_until = int((entry_datetime - now).total_seconds())

                return UpcomingEntry(
                    entry=entry,
                    seconds_until=seconds_until,
                    entry_datetime=entry_datetime
                )

        return None

    async def get_entries_in_window(self, minutes: int) -> List[UpcomingEntry]:
        """
        Get all entries within the next N minutes.

        Args:
            minutes: Window size in minutes

        Returns:
            List of UpcomingEntry objects
        """
        now = self._now_ist()
        current_time = now.time()

        # Calculate window end time
        window_end_dt = now + timedelta(minutes=minutes)
        window_end = window_end_dt.time()

        schedule = await self.get_today_schedule()
        upcoming = []

        for entry in schedule:
            if current_time < entry.entry_time <= window_end:
                entry_datetime = datetime.combine(now.date(), entry.entry_time)
                entry_datetime = IST.localize(entry_datetime)
                seconds_until = int((entry_datetime - now).total_seconds())

                upcoming.append(UpcomingEntry(
                    entry=entry,
                    seconds_until=seconds_until,
                    entry_datetime=entry_datetime
                ))

        return upcoming

    async def is_entry_imminent(self) -> Tuple[bool, Optional[UpcomingEntry]]:
        """
        Check if a strategy entry is imminent (within lookahead window).

        Uses config.lookahead_minutes to determine the window.

        Returns:
            Tuple of (is_imminent, upcoming_entry)
        """
        result = await self.get_next_entry()

        if result is None:
            return (False, None)

        lookahead_seconds = self.config.lookahead_minutes * 60
        is_imminent = result.seconds_until <= lookahead_seconds

        if is_imminent:
            logger.info(
                f"[SCHEDULER] Entry imminent: {result.entry.portfolio_name} "
                f"in {result.seconds_until}s"
            )

        return (is_imminent, result if is_imminent else None)

    async def should_hold_hedges(self) -> Tuple[bool, Optional[UpcomingEntry]]:
        """
        Check if hedges should be held (entry within exit buffer window).

        Uses config.exit_buffer_minutes to determine the window.

        Returns:
            Tuple of (should_hold, upcoming_entry)
        """
        entries_soon = await self.get_entries_in_window(self.config.exit_buffer_minutes)

        if entries_soon:
            return (True, entries_soon[0])

        return (False, None)

    async def get_executed_count(self) -> int:
        """
        Get count of strategies already executed today.

        Returns:
            Number of entries whose entry_time has passed
        """
        current_time = self._now_ist().time()
        schedule = await self.get_today_schedule()

        return sum(1 for entry in schedule if entry.entry_time < current_time)

    async def get_remaining_count(self) -> int:
        """
        Get count of strategies remaining today.

        Returns:
            Number of entries whose entry_time has not passed
        """
        current_time = self._now_ist().time()
        schedule = await self.get_today_schedule()

        return sum(1 for entry in schedule if entry.entry_time > current_time)

    async def get_schedule_summary(self) -> dict:
        """
        Get summary of today's schedule.

        Returns:
            Dict with schedule statistics
        """
        now = self._now_ist()
        schedule = await self.get_today_schedule()
        next_entry = await self.get_next_entry()

        # Group by index
        by_index: dict = {}
        for entry in schedule:
            if entry.index_name not in by_index:
                by_index[entry.index_name] = 0
            by_index[entry.index_name] += 1

        executed = await self.get_executed_count()
        remaining = await self.get_remaining_count()

        return {
            'date': self._today_ist().isoformat(),
            'day_name': self._get_day_name(),
            'total_entries': len(schedule),
            'executed': executed,
            'remaining': remaining,
            'by_index': by_index,
            'next_entry': {
                'portfolio': next_entry.entry.portfolio_name,
                'entry_time': next_entry.entry.entry_time.isoformat(),
                'seconds_until': next_entry.seconds_until
            } if next_entry else None
        }

    def clear_cache(self):
        """Clear the schedule cache."""
        self._schedule_cache = None
        self._cache_date = None
        logger.info("[SCHEDULER] Cache cleared")
