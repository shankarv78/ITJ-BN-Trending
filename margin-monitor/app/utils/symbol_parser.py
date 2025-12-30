"""
Margin Monitor - Symbol Parser for Option Symbols

Parses trading symbols like NIFTY30DEC2525800PE to extract:
- Index (NIFTY, SENSEX, BANKNIFTY, FINNIFTY)
- Expiry date (30-Dec-2025)
- Strike price (25800)
- Option type (CE/PE)

Format: {INDEX}{DD}{MMM}{YY}{STRIKE}{CE/PE}
Pattern: ^(NIFTY|SENSEX|BANKNIFTY|FINNIFTY)(DD)(MMM)(YY)(STRIKE)(CE|PE)$
"""

import re
from datetime import datetime
from typing import Optional, NamedTuple


class ParsedSymbol(NamedTuple):
    """Parsed components of an option symbol."""
    index: str          # NIFTY, SENSEX, BANKNIFTY, FINNIFTY
    day: int            # 30
    month: str          # DEC
    year: int           # 25
    expiry_date: str    # 2025-12-30 (YYYY-MM-DD format)
    strike: int         # 25800
    option_type: str    # CE or PE


# Month abbreviation to number mapping
MONTH_MAP = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
    'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
    'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
}

# Symbol pattern regex - supports NIFTY, SENSEX, BANKNIFTY, FINNIFTY
SYMBOL_PATTERN = re.compile(
    r'^(NIFTY|SENSEX|BANKNIFTY|FINNIFTY)(\d{2})([A-Z]{3})(\d{2})(\d+)(CE|PE)$'
)


def parse_symbol(symbol: str) -> Optional[ParsedSymbol]:
    """
    Parse option symbol to extract components.

    Args:
        symbol: Trading symbol (e.g., NIFTY30DEC2525800PE)

    Returns:
        ParsedSymbol with all components, or None if parsing fails.

    Examples:
        >>> parse_symbol("NIFTY30DEC2525800PE")
        ParsedSymbol(index='NIFTY', day=30, month='DEC', year=25,
                     expiry_date='2025-12-30', strike=25800, option_type='PE')

        >>> parse_symbol("INVALID")
        None
    """
    if not symbol:
        return None

    match = SYMBOL_PATTERN.match(symbol)
    if not match:
        return None

    index, day_str, month, year_str, strike_str, option_type = match.groups()

    # Validate month
    if month not in MONTH_MAP:
        return None

    day = int(day_str)
    year = int(year_str)
    strike = int(strike_str)

    # Build expiry date
    try:
        full_year = 2000 + year
        expiry_dt = datetime(full_year, MONTH_MAP[month], day)
        expiry_date = expiry_dt.strftime('%Y-%m-%d')
    except ValueError:
        # Invalid date (e.g., Feb 30)
        return None

    return ParsedSymbol(
        index=index,
        day=day,
        month=month,
        year=year,
        expiry_date=expiry_date,
        strike=strike,
        option_type=option_type
    )


def is_matching_expiry(symbol: str, target_expiry: str) -> bool:
    """
    Check if symbol matches the target expiry date.

    Args:
        symbol: Trading symbol (e.g., NIFTY30DEC2525800PE)
        target_expiry: Target expiry date (e.g., 2025-12-30)

    Returns:
        True if symbol's expiry matches target, False otherwise.

    Examples:
        >>> is_matching_expiry("NIFTY30DEC2525800PE", "2025-12-30")
        True

        >>> is_matching_expiry("NIFTY29DEC2625000CE", "2025-12-30")
        False
    """
    parsed = parse_symbol(symbol)
    return parsed is not None and parsed.expiry_date == target_expiry


def is_matching_index(symbol: str, target_index: str) -> bool:
    """
    Check if symbol is for the target index.

    Args:
        symbol: Trading symbol (e.g., NIFTY30DEC2525800PE)
        target_index: Target index name (e.g., NIFTY)

    Returns:
        True if symbol's index matches target.

    Examples:
        >>> is_matching_index("NIFTY30DEC2525800PE", "NIFTY")
        True

        >>> is_matching_index("SENSEX02JAN2578000PE", "NIFTY")
        False
    """
    return symbol.startswith(target_index)


def get_position_type(quantity: int) -> str:
    """
    Determine position type from quantity.

    Args:
        quantity: Position quantity (-ve=short, +ve=long, 0=closed)

    Returns:
        'SHORT', 'LONG', or 'CLOSED'
    """
    if quantity < 0:
        return 'SHORT'
    elif quantity > 0:
        return 'LONG'
    else:
        return 'CLOSED'
