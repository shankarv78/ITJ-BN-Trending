"""
Margin Monitor - Date/Time Utilities
"""

from datetime import datetime, date
import pytz

# Indian Standard Time
IST = pytz.timezone('Asia/Kolkata')


def now_ist() -> datetime:
    """Get current time in IST."""
    return datetime.now(IST)


def today_ist() -> date:
    """Get current date in IST."""
    return now_ist().date()


def get_day_of_week(d: date) -> int:
    """Get day of week (0=Monday, 4=Friday)."""
    return d.weekday()


def get_day_name(d: date) -> str:
    """Get day name (Monday, Tuesday, etc.)."""
    return d.strftime('%A')


def parse_date(date_str: str) -> date:
    """Parse date string (YYYY-MM-DD) to date object."""
    return datetime.strptime(date_str, '%Y-%m-%d').date()


def format_date(d: date) -> str:
    """Format date to string (YYYY-MM-DD)."""
    return d.strftime('%Y-%m-%d')


def format_datetime_ist(dt: datetime) -> str:
    """Format datetime to ISO string with IST timezone."""
    if dt.tzinfo is None:
        dt = IST.localize(dt)
    return dt.isoformat()


def is_market_hours() -> bool:
    """Check if current time is within market hours (09:15 - 15:30 IST)."""
    now = now_ist()

    # Skip weekends
    if now.weekday() > 4:  # Saturday = 5, Sunday = 6
        return False

    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    return market_open <= now <= market_close


def is_pre_market() -> bool:
    """Check if current time is before market open (before 09:15 IST on weekdays)."""
    now = now_ist()

    # Skip weekends
    if now.weekday() > 4:
        return False

    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    return now < market_open


def is_post_market() -> bool:
    """Check if current time is after market close (after 15:30 IST on weekdays)."""
    now = now_ist()

    # Skip weekends
    if now.weekday() > 4:
        return False

    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return now > market_close


def is_market_holiday(d: date = None) -> bool:
    """
    Check if given date is a market holiday.

    NSE/BSE holidays for 2025. Update annually.
    Source: https://www.nseindia.com/resources/exchange-communication-holidays
    """
    if d is None:
        d = today_ist()

    # 2025 NSE/BSE Holidays (excluding weekends)
    HOLIDAYS_2025 = {
        date(2025, 2, 26),   # Mahashivratri
        date(2025, 3, 14),   # Holi
        date(2025, 3, 31),   # Id-Ul-Fitr (Ramadan Eid)
        date(2025, 4, 10),   # Shri Mahavir Jayanti
        date(2025, 4, 14),   # Dr. Ambedkar Jayanti
        date(2025, 4, 18),   # Good Friday
        date(2025, 5, 1),    # Maharashtra Day
        date(2025, 6, 7),    # Bakri Id (Eid ul-Adha)
        date(2025, 8, 15),   # Independence Day
        date(2025, 8, 16),   # Parsi New Year
        date(2025, 10, 2),   # Mahatma Gandhi Jayanti
        date(2025, 10, 21),  # Diwali Laxmi Pujan
        date(2025, 10, 22),  # Diwali Balipratipada
        date(2025, 11, 5),   # Prakash Gurpurb Sri Guru Nanak Dev
        date(2025, 12, 25),  # Christmas
    }

    return d in HOLIDAYS_2025


def get_market_status() -> dict:
    """
    Get comprehensive market status.

    Returns:
        dict with:
        - is_open: bool - market is currently open
        - is_pre_market: bool - before 09:15
        - is_post_market: bool - after 15:30
        - is_weekend: bool - Saturday or Sunday
        - is_holiday: bool - market holiday
        - session_status: str - 'pre_market', 'open', 'closed', 'weekend', 'holiday'
        - next_event: str - description of next market event
        - market_open_time: str - "09:15"
        - market_close_time: str - "15:30"
    """
    now = now_ist()
    is_weekend = now.weekday() > 4
    is_holiday = is_market_holiday(now.date())

    if is_weekend:
        return {
            "is_open": False,
            "is_pre_market": False,
            "is_post_market": False,
            "is_weekend": True,
            "is_holiday": False,
            "session_status": "weekend",
            "next_event": "Market opens Monday 09:15 IST",
            "market_open_time": "09:15",
            "market_close_time": "15:30",
        }

    if is_holiday:
        return {
            "is_open": False,
            "is_pre_market": False,
            "is_post_market": False,
            "is_weekend": False,
            "is_holiday": True,
            "session_status": "holiday",
            "next_event": "Market closed (holiday)",
            "market_open_time": "09:15",
            "market_close_time": "15:30",
        }

    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

    if now < market_open:
        return {
            "is_open": False,
            "is_pre_market": True,
            "is_post_market": False,
            "is_weekend": False,
            "is_holiday": False,
            "session_status": "pre_market",
            "next_event": f"Market opens at 09:15 IST",
            "market_open_time": "09:15",
            "market_close_time": "15:30",
        }
    elif now > market_close:
        return {
            "is_open": False,
            "is_pre_market": False,
            "is_post_market": True,
            "is_weekend": False,
            "is_holiday": False,
            "session_status": "closed",
            "next_event": "Market closed for today",
            "market_open_time": "09:15",
            "market_close_time": "15:30",
        }
    else:
        time_to_close = market_close - now
        mins_remaining = int(time_to_close.total_seconds() / 60)
        return {
            "is_open": True,
            "is_pre_market": False,
            "is_post_market": False,
            "is_weekend": False,
            "is_holiday": False,
            "session_status": "open",
            "next_event": f"Market closes in {mins_remaining} minutes",
            "market_open_time": "09:15",
            "market_close_time": "15:30",
        }
