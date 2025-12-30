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
