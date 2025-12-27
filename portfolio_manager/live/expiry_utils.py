"""
Expiry calculation utilities for rollover system

Handles:
- Bank Nifty monthly expiry (hardcoded from NSE)
- Gold Mini expiry (5th of month, adjusted for weekends/holidays)
- Copper expiry (last calendar day of month)
- Days to expiry calculation
- ATM strike rounding (nearest 500, prefer 1000s)
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Import hardcoded expiry dates from core module
from core.expiry_calendar import BANKNIFTY_EXPIRY_DATES
from core.holiday_calendar import get_holiday_calendar


def get_last_wednesday_of_month(year: int, month: int) -> datetime:
    """
    Get the last Wednesday of a given month

    Args:
        year: Year (e.g., 2025)
        month: Month (1-12)

    Returns:
        datetime of last Wednesday
    """
    # Get first day of next month
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)

    # Last day of current month
    last_day = next_month - timedelta(days=1)

    # Find last Wednesday (weekday 2 = Wednesday)
    offset = (last_day.weekday() - 2) % 7
    last_wednesday = last_day - timedelta(days=offset)

    return last_wednesday


def get_last_day_of_month(year: int, month: int) -> datetime:
    """
    Get the last calendar day of a given month

    Args:
        year: Year (e.g., 2025)
        month: Month (1-12)

    Returns:
        datetime of last day
    """
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)

    return next_month - timedelta(days=1)


def get_banknifty_expiry(target_date: datetime = None) -> Tuple[datetime, str]:
    """
    Get Bank Nifty monthly expiry date from hardcoded NSE data.

    Uses BANKNIFTY_EXPIRY_DATES list from core.expiry_calendar.
    Falls back to calculation if date not in hardcoded list.

    Args:
        target_date: Date to calculate from (default: today)

    Returns:
        Tuple of (expiry_datetime, expiry_string in DDMMMYY format)
    """
    if target_date is None:
        target_date = datetime.now()

    target_as_date = target_date.date() if isinstance(target_date, datetime) else target_date

    # Find next expiry from hardcoded list
    for expiry in BANKNIFTY_EXPIRY_DATES:
        if expiry >= target_as_date:
            expiry_datetime = datetime.combine(expiry, datetime.min.time())
            expiry_str = format_expiry_string(expiry_datetime)
            logger.debug(f"[EXPIRY] Bank Nifty expiry from hardcoded: {expiry}")
            return expiry_datetime, expiry_str

    # Fallback: calculate if hardcoded dates exhausted
    logger.warning(
        f"[EXPIRY] No hardcoded Bank Nifty expiry for {target_as_date}. "
        f"Update BANKNIFTY_EXPIRY_DATES in core/expiry_calendar.py!"
    )
    return _calculate_banknifty_expiry_fallback(target_date)


def _calculate_banknifty_expiry_fallback(target_date: datetime) -> Tuple[datetime, str]:
    """Fallback: calculate last Tuesday of month."""
    year = target_date.year
    month = target_date.month

    # Get last Tuesday of current month
    expiry_date = get_last_tuesday_of_month(year, month)

    # If target date is past this expiry, get next month
    if target_date.date() > expiry_date.date():
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1
        expiry_date = get_last_tuesday_of_month(year, month)

    expiry_str = format_expiry_string(expiry_date)
    return expiry_date, expiry_str


def get_last_tuesday_of_month(year: int, month: int) -> datetime:
    """Get the last Tuesday of a given month."""
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    # Find last Tuesday (weekday 1 = Tuesday)
    offset = (last_day.weekday() - 1) % 7
    return last_day - timedelta(days=offset)


def get_gold_mini_expiry(target_date: datetime = None) -> Tuple[datetime, str]:
    """
    Get Gold Mini futures expiry date (5th of every month, adjusted for holidays)

    MCX Gold Mini contracts expire on the 5th of each month.
    If the 5th falls on a weekend or MCX holiday, expiry moves to the
    previous trading day. Examples:
    - 5th is Sunday → expiry on 3rd (Friday)
    - 5th is Monday holiday, 4th Sunday, 3rd Saturday → expiry on 2nd

    Args:
        target_date: Date to calculate from (default: today)

    Returns:
        Tuple of (expiry_datetime, expiry_string in YYMONDD format)
    """
    if target_date is None:
        target_date = datetime.now()

    year = target_date.year
    month = target_date.month

    # Nominal expiry is 5th of every month
    nominal_expiry = datetime(year, month, 5)

    # Adjust for weekends and holidays using holiday calendar
    holiday_cal = get_holiday_calendar()
    if holiday_cal:
        actual_expiry = holiday_cal.get_actual_expiry_date(nominal_expiry.date(), "MCX")
        expiry_date = datetime.combine(actual_expiry, datetime.min.time())
    else:
        # Fallback: just check weekends if no holiday calendar
        expiry_date = nominal_expiry
        while expiry_date.weekday() >= 5:  # Saturday=5, Sunday=6
            expiry_date -= timedelta(days=1)
        logger.warning("[EXPIRY] Holiday calendar not initialized, only weekend check applied")

    # If target date is past this expiry, get next month
    if target_date.date() > expiry_date.date():
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1

        # Recalculate for next month
        nominal_expiry = datetime(year, month, 5)

        if holiday_cal:
            actual_expiry = holiday_cal.get_actual_expiry_date(nominal_expiry.date(), "MCX")
            expiry_date = datetime.combine(actual_expiry, datetime.min.time())
        else:
            expiry_date = nominal_expiry
            while expiry_date.weekday() >= 5:
                expiry_date -= timedelta(days=1)

    # Format: YYMONDD (e.g., "26JAN05" or "26JAN03" if 5th is weekend)
    expiry_str = format_expiry_string(expiry_date)

    logger.debug(f"[EXPIRY] Gold Mini expiry: nominal={year}-{month:02d}-05, actual={expiry_date.date()}")

    return expiry_date, expiry_str


def get_copper_expiry(target_date: datetime = None) -> Tuple[datetime, str]:
    """
    Get Copper futures expiry date (last day of month)

    Args:
        target_date: Date to calculate from (default: today)

    Returns:
        Tuple of (expiry_datetime, expiry_string in YYMONDD format)
    """
    if target_date is None:
        target_date = datetime.now()

    year = target_date.year
    month = target_date.month

    # Get last day of current month
    expiry_date = get_last_day_of_month(year, month)

    # If target date is past this expiry, get next month
    if target_date.date() > expiry_date.date():
        if month == 12:
            month = 1
            year += 1
        else:
            month += 1
        expiry_date = get_last_day_of_month(year, month)

    # Format: YYMONDD (e.g., "25DEC31")
    expiry_str = format_expiry_string(expiry_date)

    return expiry_date, expiry_str


# Silver Mini bimonthly contract months (Feb, Apr, Jun, Aug, Nov)
SILVER_MINI_CONTRACT_MONTHS = [2, 4, 6, 8, 11]


def get_next_silver_mini_contract_month(current_month: int, current_year: int) -> Tuple[int, int]:
    """
    Get the next available Silver Mini contract month.

    Silver Mini has bimonthly contracts: Feb, Apr, Jun, Aug, Nov (NOT Oct/Dec).

    Args:
        current_month: Current month (1-12)
        current_year: Current year

    Returns:
        Tuple of (contract_month, year) - may roll to next year
    """
    for m in SILVER_MINI_CONTRACT_MONTHS:
        if m >= current_month:
            return m, current_year
    # Roll to next year's February (first contract month)
    return 2, current_year + 1


def get_silver_mini_expiry(target_date: datetime = None) -> Tuple[datetime, str]:
    """
    Get Silver Mini futures expiry date.

    Silver Mini expires on the LAST calendar day of bimonthly contract months:
    February, April, June, August, November (NOT October/December).

    If the last day is a holiday/weekend, expiry moves to prior trading day.

    Args:
        target_date: Date to calculate from (default: today)

    Returns:
        Tuple of (expiry_datetime, expiry_string in DDMMMYY format)
    """
    if target_date is None:
        target_date = datetime.now()

    year = target_date.year
    month = target_date.month

    # Find the next available contract month
    contract_month, contract_year = get_next_silver_mini_contract_month(month, year)

    # Get last day of contract month
    expiry_date = get_last_day_of_month(contract_year, contract_month)

    # Adjust for holidays using holiday calendar
    holiday_cal = get_holiday_calendar()
    if holiday_cal:
        actual_expiry = holiday_cal.get_actual_expiry_date(expiry_date.date(), "MCX")
        expiry_date = datetime.combine(actual_expiry, datetime.min.time())
    else:
        # Fallback: just check weekends if no holiday calendar
        while expiry_date.weekday() >= 5:  # Saturday=5, Sunday=6
            expiry_date -= timedelta(days=1)
        logger.warning("[EXPIRY] Holiday calendar not initialized, only weekend check applied for Silver Mini")

    # If target date is past this expiry, get next contract month
    if target_date.date() > expiry_date.date():
        # Move to next contract month
        if contract_month == 11:  # November -> February next year
            contract_month = 2
            contract_year += 1
        else:
            # Find next contract month in the list
            current_idx = SILVER_MINI_CONTRACT_MONTHS.index(contract_month)
            if current_idx < len(SILVER_MINI_CONTRACT_MONTHS) - 1:
                contract_month = SILVER_MINI_CONTRACT_MONTHS[current_idx + 1]
            else:
                contract_month = 2
                contract_year += 1

        expiry_date = get_last_day_of_month(contract_year, contract_month)

        if holiday_cal:
            actual_expiry = holiday_cal.get_actual_expiry_date(expiry_date.date(), "MCX")
            expiry_date = datetime.combine(actual_expiry, datetime.min.time())
        else:
            while expiry_date.weekday() >= 5:
                expiry_date -= timedelta(days=1)

    # Format: DDMMMYY (e.g., "27FEB26") - note: day-month-year format
    expiry_str = format_expiry_string(expiry_date)

    logger.debug(f"[EXPIRY] Silver Mini expiry: contract={contract_year}-{contract_month:02d}, actual={expiry_date.date()}")

    return expiry_date, expiry_str


def get_next_month_expiry(instrument: str, current_expiry: datetime) -> Tuple[datetime, str]:
    """
    Get the next month's expiry date

    Args:
        instrument: "BANK_NIFTY", "GOLD_MINI", or "COPPER"
        current_expiry: Current expiry datetime

    Returns:
        Tuple of (next_expiry_datetime, expiry_string)
    """
    # Move to next month
    year = current_expiry.year
    month = current_expiry.month

    if month == 12:
        month = 1
        year += 1
    else:
        month += 1

    if instrument == "BANK_NIFTY":
        next_expiry = get_last_wednesday_of_month(year, month)
    elif instrument == "GOLD_MINI":
        # Gold Mini expires on 5th of every month, adjusted for holidays
        nominal_expiry = datetime(year, month, 5)
        holiday_cal = get_holiday_calendar()
        if holiday_cal:
            actual_expiry = holiday_cal.get_actual_expiry_date(nominal_expiry.date(), "MCX")
            next_expiry = datetime.combine(actual_expiry, datetime.min.time())
        else:
            next_expiry = nominal_expiry
            while next_expiry.weekday() >= 5:
                next_expiry -= timedelta(days=1)
    elif instrument == "SILVER_MINI":
        # Silver Mini has bimonthly expiry (Feb, Apr, Jun, Aug, Nov)
        # Find the next contract month after current_expiry's month
        contract_month, contract_year = get_next_silver_mini_contract_month(month, year)
        next_expiry = get_last_day_of_month(contract_year, contract_month)
        holiday_cal = get_holiday_calendar()
        if holiday_cal:
            actual_expiry = holiday_cal.get_actual_expiry_date(next_expiry.date(), "MCX")
            next_expiry = datetime.combine(actual_expiry, datetime.min.time())
        else:
            while next_expiry.weekday() >= 5:
                next_expiry -= timedelta(days=1)
    else:  # COPPER (MCX futures - last day of month)
        next_expiry = get_last_day_of_month(year, month)

    expiry_str = format_expiry_string(next_expiry)

    return next_expiry, expiry_str


def format_expiry_string(expiry_date: datetime) -> str:
    """
    Format expiry date as DDMMMYY string (standard OpenAlgo/Zerodha format)

    Args:
        expiry_date: datetime object

    Returns:
        String like "05JAN26" or "31DEC25"
    """
    dd = expiry_date.strftime("%d")
    mon = expiry_date.strftime("%b").upper()
    yy = str(expiry_date.year)[-2:]
    return f"{dd}{mon}{yy}"


def parse_expiry_string(expiry_str: str) -> Optional[datetime]:
    """
    Parse expiry string back to datetime

    Args:
        expiry_str: String like "25DEC25" or "25DEC31"

    Returns:
        datetime object or None if parsing fails
    """
    try:
        if len(expiry_str) != 7:
            return None

        yy = int("20" + expiry_str[:2])
        mon_str = expiry_str[2:5]
        dd = int(expiry_str[5:7])

        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
            'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
            'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }

        month = month_map.get(mon_str.upper())
        if month is None:
            return None

        return datetime(yy, month, dd)

    except (ValueError, IndexError):
        return None


def get_contract_month(expiry_str: str) -> str:
    """
    Extract contract month from expiry string

    Args:
        expiry_str: String like "25DEC31"

    Returns:
        String like "DEC25"
    """
    if len(expiry_str) >= 5:
        yy = expiry_str[:2]
        mon = expiry_str[2:5]
        return f"{mon}{yy}"
    return ""


def days_to_expiry(expiry_str: str, from_date: datetime = None) -> int:
    """
    Calculate days remaining to expiry

    Args:
        expiry_str: Expiry in format YYMONDD (e.g., '25DEC25')
        from_date: Date to calculate from (default: today)

    Returns:
        Number of days to expiry (0 if expired or invalid)
    """
    if from_date is None:
        from_date = datetime.now()

    expiry_date = parse_expiry_string(expiry_str)
    if expiry_date is None:
        logger.error(f"Invalid expiry string: {expiry_str}")
        return 0

    # Compare dates only (ignore time)
    from_date = from_date.replace(hour=0, minute=0, second=0, microsecond=0)
    expiry_date = expiry_date.replace(hour=0, minute=0, second=0, microsecond=0)

    days = (expiry_date - from_date).days

    return max(0, days)


def is_within_rollover_window(
    expiry_str: str,
    rollover_days: int,
    from_date: datetime = None
) -> bool:
    """
    Check if position is within rollover window

    Args:
        expiry_str: Position's expiry string
        rollover_days: Days before expiry to trigger rollover
        from_date: Date to check from (default: today)

    Returns:
        True if within rollover window
    """
    days = days_to_expiry(expiry_str, from_date)
    return days < rollover_days


def get_rollover_strike(
    current_price: float,
    strike_interval: int = 500,
    prefer_1000s: bool = True
) -> int:
    """
    Calculate rollover strike price

    ATM rounded to nearest 500, with preference for 1000 multiples.

    Args:
        current_price: Current underlying price (Bank Nifty futures LTP)
        strike_interval: Base interval (default 500)
        prefer_1000s: Prefer 1000 multiples over 500s when close

    Returns:
        Strike price as integer

    Examples:
        52100 -> 52000 (prefer 1000s)
        52400 -> 52500 (closer to 52500)
        52750 -> 53000 (prefer 1000s when close)
        52600 -> 52500 (equidistant, but 52500 is closer)
    """
    # Round to nearest 500
    base_500 = round(current_price / strike_interval) * strike_interval

    if not prefer_1000s:
        return int(base_500)

    # Check if it's already a 1000 multiple
    if base_500 % 1000 == 0:
        return int(base_500)

    # It's a 500 multiple (like 52500). Check if a 1000 multiple is close enough
    lower_1000 = (int(base_500) // 1000) * 1000  # e.g., 52000
    upper_1000 = lower_1000 + 1000              # e.g., 53000

    dist_to_lower = abs(current_price - lower_1000)
    dist_to_upper = abs(current_price - upper_1000)
    dist_to_500 = abs(current_price - base_500)

    # Prefer 1000 if within 250 points (half of 500 interval)
    # This means: if price is 52100-52250, use 52000; if 52750-52900, use 53000
    threshold = strike_interval / 2  # 250 points

    if dist_to_lower <= threshold and dist_to_lower <= dist_to_500:
        logger.debug(f"Strike {current_price:.0f} -> {lower_1000} (prefer 1000s, dist={dist_to_lower:.0f})")
        return lower_1000
    elif dist_to_upper <= threshold and dist_to_upper <= dist_to_500:
        logger.debug(f"Strike {current_price:.0f} -> {upper_1000} (prefer 1000s, dist={dist_to_upper:.0f})")
        return upper_1000
    else:
        logger.debug(f"Strike {current_price:.0f} -> {int(base_500)} (nearest 500)")
        return int(base_500)


def format_banknifty_option_symbol(
    expiry: str,
    strike: int,
    option_type: str,
    broker: str = "zerodha"
) -> str:
    """
    Format Bank Nifty option symbol

    Args:
        expiry: Expiry string (e.g., "25DEC25")
        strike: Strike price (e.g., 52000)
        option_type: "PE" or "CE"
        broker: Broker name for symbol format

    Returns:
        Formatted symbol (e.g., "BANKNIFTY25DEC2552000PE")
    """
    broker = broker.lower()

    if broker == "zerodha":
        return f"BANKNIFTY{expiry}{strike}{option_type}"
    elif broker == "dhan":
        return f"BANKNIFTY {expiry} {strike} {option_type}"
    else:
        # Default to Zerodha format
        return f"BANKNIFTY{expiry}{strike}{option_type}"


def format_gold_mini_futures_symbol(
    expiry: str,
    broker: str = "zerodha"
) -> str:
    """
    Format Gold Mini futures symbol

    Args:
        expiry: Expiry string (e.g., "25DEC31")
        broker: Broker name for symbol format

    Returns:
        Formatted symbol (e.g., "GOLDM25DEC31FUT")
    """
    broker = broker.lower()

    if broker == "zerodha":
        return f"GOLDM{expiry}FUT"
    elif broker == "dhan":
        return f"GOLDM {expiry} FUT"
    else:
        return f"GOLDM{expiry}FUT"


def format_copper_futures_symbol(
    expiry: str,
    broker: str = "zerodha"
) -> str:
    """
    Format Copper futures symbol

    Args:
        expiry: Expiry string (e.g., "25DEC31")
        broker: Broker name for symbol format

    Returns:
        Formatted symbol (e.g., "COPPER25DEC31FUT")
    """
    broker = broker.lower()

    if broker == "zerodha":
        return f"COPPER{expiry}FUT"
    elif broker == "dhan":
        return f"COPPER {expiry} FUT"
    else:
        return f"COPPER{expiry}FUT"


def format_silver_mini_futures_symbol(
    expiry: str,
    broker: str = "zerodha"
) -> str:
    """
    Format Silver Mini futures symbol

    Args:
        expiry: Expiry string in DDMMMYY format (e.g., "27FEB26")
        broker: Broker name for symbol format

    Returns:
        Formatted symbol (e.g., "SILVERM27FEB26FUT")
    """
    broker = broker.lower()

    if broker == "zerodha":
        return f"SILVERM{expiry}FUT"
    elif broker == "dhan":
        return f"SILVERM {expiry} FUT"
    else:
        return f"SILVERM{expiry}FUT"


def is_market_hours(
    instrument: str,
    check_time: datetime = None,
    nse_start: str = "09:15",
    nse_end: str = "15:30",
    mcx_start: str = "09:00",
    mcx_end: str = "23:30"
) -> bool:
    """
    Check if current time is within market hours

    Args:
        instrument: "BANK_NIFTY", "GOLD_MINI", "COPPER", or "SILVER_MINI"
        check_time: Time to check (default: now)
        nse_start/nse_end: NSE market hours
        mcx_start/mcx_end: MCX market hours

    Returns:
        True if within market hours
    """
    if check_time is None:
        check_time = datetime.now()

    # Check if weekend
    if check_time.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False

    # Parse market hours
    if instrument == "BANK_NIFTY":
        start_h, start_m = map(int, nse_start.split(":"))
        end_h, end_m = map(int, nse_end.split(":"))
    else:  # GOLD_MINI, COPPER, SILVER_MINI (MCX)
        start_h, start_m = map(int, mcx_start.split(":"))
        end_h, end_m = map(int, mcx_end.split(":"))

    start_time = check_time.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    end_time = check_time.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

    return start_time <= check_time <= end_time
