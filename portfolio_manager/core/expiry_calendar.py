"""
Expiry Calendar - Calculate contract expiry dates

Supports:
- Gold Mini (MCX): 5th of each month
- Bank Nifty (NFO): Last Thursday of each month

Handles holidays and rollover detection.
"""
import logging
from datetime import date, timedelta
import calendar
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ExpiryCalendar:
    """
    Calculate contract expiry dates for various instruments.

    Expiry Rules:
    - Gold Mini (MCX): 5th of each month. If 5th is weekend/holiday, previous trading day.
    - Bank Nifty (NFO): Last Thursday of month. If Thursday is holiday, previous trading day.
    """

    # Default rollover days before expiry
    DEFAULT_ROLLOVER_DAYS = {
        'GOLD_MINI': 3,
        'BANK_NIFTY': 5
    }

    def __init__(self, holiday_calendar=None):
        """
        Initialize ExpiryCalendar.

        Args:
            holiday_calendar: Optional HolidayCalendar instance for holiday checking
        """
        self.holiday_calendar = holiday_calendar

    def get_gold_mini_expiry(self, reference_date: Optional[date] = None) -> date:
        """
        Get Gold Mini expiry date.

        Gold Mini expires on 5th of each month.
        If 5th is weekend/holiday, use previous trading day.

        Args:
            reference_date: Reference date (default: today)

        Returns:
            Expiry date
        """
        if reference_date is None:
            reference_date = date.today()

        year, month = reference_date.year, reference_date.month

        # If we're past the 5th, use next month
        if reference_date.day > 5:
            month += 1
            if month > 12:
                month = 1
                year += 1

        expiry = date(year, month, 5)

        # Adjust for weekends and holidays
        expiry = self._adjust_for_holidays(expiry, "MCX")

        return expiry

    def get_bank_nifty_expiry(self, reference_date: Optional[date] = None) -> date:
        """
        Get Bank Nifty MONTHLY expiry date.

        Bank Nifty monthly options expire on the LAST TUESDAY of the month.
        (Changed from last Thursday in 2024)
        If the last Tuesday is a holiday, shift to next trading day.

        Args:
            reference_date: Reference date (default: today)

        Returns:
            Monthly expiry date (last Wednesday of month - NSE changed from Tuesday in 2024)
        """
        if reference_date is None:
            reference_date = date.today()

        year, month = reference_date.year, reference_date.month

        # Find last Wednesday of this month (NSE changed from Tuesday to Wednesday in 2024)
        expiry = self._get_last_wednesday(year, month)

        # If we're past this month's expiry, get next month's
        if reference_date > expiry:
            month += 1
            if month > 12:
                month = 1
                year += 1
            expiry = self._get_last_wednesday(year, month)

        # Adjust for holidays - for Bank Nifty, shift FORWARD if holiday
        expiry = self._adjust_for_holidays_forward(expiry, "NSE")

        return expiry

    def _get_last_wednesday(self, year: int, month: int) -> date:
        """Get the last Wednesday of a given month (NSE changed from Tuesday in 2024)."""
        # Get last day of month
        last_day = calendar.monthrange(year, month)[1]

        # Find last Wednesday (Wednesday = 2, Tuesday = 1)
        last_date = date(year, month, last_day)
        while last_date.weekday() != 2:  # Wednesday = 2
            last_date -= timedelta(days=1)

        return last_date

    def _adjust_for_holidays_forward(self, expiry: date, exchange: str) -> date:
        """
        Adjust expiry date for holidays by moving FORWARD.

        Used for Bank Nifty where holiday adjustments typically move forward.
        """
        adjusted = expiry

        # Adjust for weekends and holidays by moving forward
        max_attempts = 10
        while max_attempts > 0:
            is_holiday = False

            # Check weekends
            if adjusted.weekday() >= 5:
                is_holiday = True
            # Check holidays
            elif self.holiday_calendar:
                is_hol, _ = self.holiday_calendar.is_holiday(adjusted, exchange)
                if is_hol:
                    is_holiday = True

            if not is_holiday:
                break

            adjusted += timedelta(days=1)
            max_attempts -= 1

        return adjusted

    def _get_last_thursday(self, year: int, month: int) -> date:
        """Get the last Thursday of a given month."""
        # Get last day of month
        last_day = calendar.monthrange(year, month)[1]

        # Find last Thursday
        last_date = date(year, month, last_day)
        while last_date.weekday() != 3:  # Thursday = 3
            last_date -= timedelta(days=1)

        return last_date

    def _adjust_for_holidays(self, expiry: date, exchange: str) -> date:
        """
        Adjust expiry date for weekends and holidays.

        If expiry falls on weekend/holiday, use previous trading day.
        """
        adjusted = expiry

        # Adjust for weekends (Saturday=5, Sunday=6)
        while adjusted.weekday() >= 5:
            adjusted -= timedelta(days=1)

        # Adjust for holidays if calendar available
        if self.holiday_calendar:
            while self.holiday_calendar.is_holiday(adjusted, exchange)[0]:
                adjusted -= timedelta(days=1)
                # Also skip weekends
                while adjusted.weekday() >= 5:
                    adjusted -= timedelta(days=1)

        return adjusted

    def get_next_expiry(self, instrument: str, reference_date: Optional[date] = None) -> date:
        """
        Get next expiry date for an instrument.

        Args:
            instrument: "GOLD_MINI" or "BANK_NIFTY"
            reference_date: Reference date (default: today)

        Returns:
            Next expiry date
        """
        if instrument == "GOLD_MINI":
            return self.get_gold_mini_expiry(reference_date)
        elif instrument == "BANK_NIFTY":
            return self.get_bank_nifty_expiry(reference_date)
        else:
            raise ValueError(f"Unknown instrument: {instrument}")

    def _get_exchange_for_instrument(self, instrument: str) -> str:
        """Get exchange code for an instrument."""
        if instrument == "GOLD_MINI":
            return "MCX"
        elif instrument == "BANK_NIFTY":
            return "NSE"
        else:
            return "NSE"  # Default

    def count_trading_days(self, from_date: date, to_date: date, exchange: str) -> int:
        """
        Count trading days between two dates (excluding holidays/weekends).

        Args:
            from_date: Start date (exclusive - we count days AFTER this date)
            to_date: End date (exclusive)
            exchange: Exchange code ("NSE" or "MCX")

        Returns:
            Number of trading days between from_date and to_date
        """
        if from_date >= to_date:
            return 0

        trading_days = 0
        current = from_date + timedelta(days=1)  # Start from next day

        while current < to_date:
            is_trading_day = True

            # Check weekends (Saturday=5, Sunday=6)
            if current.weekday() >= 5:
                is_trading_day = False
            # Check holidays if calendar available
            elif self.holiday_calendar:
                is_holiday, _ = self.holiday_calendar.is_holiday(current, exchange)
                if is_holiday:
                    is_trading_day = False

            if is_trading_day:
                trading_days += 1

            current += timedelta(days=1)

        return trading_days

    def should_rollover(self, instrument: str, reference_date: Optional[date] = None) -> Tuple[bool, int]:
        """
        Check if we should use next month's expiry (rollover window).

        Uses TRADING DAYS (not calendar days) to account for holidays.

        Example:
        - Today: Monday Dec 23
        - Expiry: Thursday Dec 26
        - If Dec 24 & 25 are holidays: only 1 trading day left → should rollover

        Returns:
            Tuple of (should_rollover, trading_days_to_expiry)
        """
        if reference_date is None:
            reference_date = date.today()

        expiry = self.get_next_expiry(instrument, reference_date)
        exchange = self._get_exchange_for_instrument(instrument)

        # Use trading days, not calendar days
        trading_days_to_expiry = self.count_trading_days(reference_date, expiry, exchange)

        rollover_days = self.DEFAULT_ROLLOVER_DAYS.get(instrument, 3)

        should_roll = trading_days_to_expiry <= rollover_days

        logger.debug(
            f"[EXPIRY] Rollover check for {instrument}: "
            f"expiry={expiry}, trading_days={trading_days_to_expiry}, "
            f"threshold={rollover_days}, should_roll={should_roll}"
        )

        return should_roll, trading_days_to_expiry

    def get_expiry_after_rollover(self, instrument: str, reference_date: Optional[date] = None) -> date:
        """
        Get expiry date, accounting for rollover window.

        If within rollover window, returns next expiry.

        Args:
            instrument: "GOLD_MINI" or "BANK_NIFTY"
            reference_date: Reference date (default: today)

        Returns:
            Expiry date (may be next month if in rollover window)
        """
        if reference_date is None:
            reference_date = date.today()

        current_expiry = self.get_next_expiry(instrument, reference_date)
        should_roll, _ = self.should_rollover(instrument, reference_date)

        if should_roll:
            # Get next month's expiry
            next_ref = current_expiry + timedelta(days=1)
            return self.get_next_expiry(instrument, next_ref)

        return current_expiry


# Global instance
_expiry_calendar: Optional[ExpiryCalendar] = None


def get_expiry_calendar() -> ExpiryCalendar:
    """Get global ExpiryCalendar instance."""
    global _expiry_calendar
    if _expiry_calendar is None:
        _expiry_calendar = ExpiryCalendar()
    return _expiry_calendar


def init_expiry_calendar(holiday_calendar=None) -> ExpiryCalendar:
    """Initialize global ExpiryCalendar with holiday calendar."""
    global _expiry_calendar
    _expiry_calendar = ExpiryCalendar(holiday_calendar=holiday_calendar)
    return _expiry_calendar
