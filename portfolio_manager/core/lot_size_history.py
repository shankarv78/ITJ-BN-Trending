"""
Historical Bank Nifty Lot Size Lookup

Provides historically accurate lot sizes for backtesting.
Mirrors the Pine Script getBankNiftyLotSize() function.

Sources: NSE F&O circulars, verified from NSE archives
"""
from datetime import date
from typing import Optional


# Historical lot size change dates and values
# Format: (effective_date, lot_size)
BANKNIFTY_LOT_SIZE_HISTORY = [
    # (date, lot_size) - ordered newest to oldest for efficiency
    (date(2025, 12, 30), 30),   # Dec 2025 onwards - per Zerodha circular
    (date(2025, 4, 25), 35),    # Apr 2025 - Dec 2025 (NSE/FAOP/67372)
    (date(2024, 11, 20), 30),   # Nov 2024 - Apr 2025
    (date(2023, 7, 1), 15),     # Jul 2023 - Nov 2024 (FAOP64625) - Recent minimum
    (date(2020, 5, 4), 25),     # May 2020 - Jun 2023 (NSE/F&O/035/2020)
    (date(2018, 10, 26), 20),   # Oct 2018 - May 2020 (NSE/F&O/091/2018)
    (date(2016, 4, 29), 40),    # Apr 2016 - Oct 2018 (NSE/F&O/034/2016) - Historical maximum
    (date(2015, 8, 28), 30),    # Aug 2015 - Apr 2016 (NSE/F&O/071/2015)
    (date(2010, 4, 30), 25),    # Apr 2010 - Aug 2015 (NSE/F&O/030/2010) - Longest stable
    (date(2007, 2, 23), 50),    # Feb 2007 - Apr 2010 (NSE/F&O/010/2007)
    (date(2005, 6, 13), 100),   # Launch - Feb 2007 (Bank Nifty F&O launch)
]

DEFAULT_LOT_SIZE = 25  # Fallback for dates before June 2005


def get_banknifty_lot_size(bar_date: date) -> int:
    """
    Returns historically accurate Bank Nifty lot size for a given date.

    Args:
        bar_date: The date to look up lot size for

    Returns:
        Lot size (units per lot) valid on that date

    Example:
        >>> get_banknifty_lot_size(date(2024, 1, 15))
        15  # Jul 2023 - Nov 2024 period

        >>> get_banknifty_lot_size(date(2025, 12, 31))
        30  # Dec 2025 onwards
    """
    for effective_date, lot_size in BANKNIFTY_LOT_SIZE_HISTORY:
        if bar_date >= effective_date:
            return lot_size
    return DEFAULT_LOT_SIZE


def get_banknifty_point_value(bar_date: date) -> float:
    """
    Returns point value (Rs per point per lot) for a given date.

    For Bank Nifty, point_value = lot_size since each unit moves ₹1 per point.

    Args:
        bar_date: The date to look up

    Returns:
        Point value in Rs
    """
    return float(get_banknifty_lot_size(bar_date))


def get_lot_size_for_instrument(instrument: str, bar_date: Optional[date] = None) -> int:
    """
    Get lot size for any instrument, optionally for a historical date.

    Args:
        instrument: "BANK_NIFTY", "GOLD_MINI", "COPPER", or "SILVER_MINI"
        bar_date: Optional date for historical lookup (Bank Nifty only)

    Returns:
        Lot size for the instrument
    """
    if instrument == "BANK_NIFTY":
        if bar_date:
            return get_banknifty_lot_size(bar_date)
        else:
            # Return current (latest) lot size
            return BANKNIFTY_LOT_SIZE_HISTORY[0][1]
    elif instrument == "GOLD_MINI":
        return 100  # Fixed
    elif instrument == "COPPER":
        return 2500  # Fixed
    elif instrument == "SILVER_MINI":
        return 5  # Fixed (5kg per contract)
    else:
        raise ValueError(f"Unknown instrument: {instrument}")
