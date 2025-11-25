"""
Utility functions for OpenAlgo Bridge
"""
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def is_market_hours(start_hour=9, start_minute=15, end_hour=15, end_minute=25) -> bool:
    """
    Check if current time is within market hours
    
    Args:
        start_hour: Market start hour (default 9)
        start_minute: Market start minute (default 15)
        end_hour: Market end hour (default 15)
        end_minute: Market end minute (default 25, buffer before 3:30)
        
    Returns:
        True if within market hours, False otherwise
    """
    now = datetime.now()
    
    # Check if weekend
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        logger.debug("Market closed: Weekend")
        return False
    
    # Create time boundaries
    start_time = now.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
    end_time = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
    
    in_hours = start_time <= now <= end_time
    
    if not in_hours:
        logger.debug(f"Outside market hours: {now.strftime('%H:%M')}")
    
    return in_hours

def get_atm_strike(price: float, strike_interval: int = 100) -> int:
    """
    Calculate ATM (At-The-Money) strike for Bank Nifty
    
    Args:
        price: Current Bank Nifty price
        strike_interval: Strike interval (default 100 for Bank Nifty)
        
    Returns:
        Nearest ATM strike
        
    Examples:
        get_atm_strike(52040) -> 52000
        get_atm_strike(52060) -> 52100
        get_atm_strike(52050) -> 52100 (rounds to nearest)
    """
    strike = round(price / strike_interval) * strike_interval
    logger.debug(f"ATM strike for {price}: {strike}")
    return int(strike)

def get_expiry_date(use_monthly: bool = True, target_date: datetime = None) -> str:
    """
    Get option expiry date in symbol format
    
    Bank Nifty expiries:
    - Weekly: Every Wednesday
    - Monthly: Last Wednesday of month
    
    Args:
        use_monthly: True for monthly, False for weekly
        target_date: Date to calculate from (default: today)
        
    Returns:
        String in format YYMONDD (e.g., '25DEC25')
    """
    if target_date is None:
        target_date = datetime.now()
    
    if use_monthly:
        # Find last Wednesday of current month
        year = target_date.year
        month = target_date.month
        
        # Get last day of month
        if month == 12:
            next_month = target_date.replace(year=year+1, month=1, day=1)
        else:
            next_month = target_date.replace(month=month+1, day=1)
        
        last_day = next_month - timedelta(days=1)
        
        # Find last Wednesday (weekday 2 = Wednesday)
        offset = (last_day.weekday() - 2) % 7
        last_wednesday = last_day - timedelta(days=offset)
        
        # If today is past expiry, get next month
        if target_date.date() > last_wednesday.date():
            if month == 12:
                month = 1
                year += 1
            else:
                month += 1
            
            # Recalculate for next month
            if month == 12:
                next_month = datetime(year+1, 1, 1)
            else:
                next_month = datetime(year, month+1, 1)
            
            last_day = next_month - timedelta(days=1)
            offset = (last_day.weekday() - 2) % 7
            last_wednesday = last_day - timedelta(days=offset)
        
        expiry_date = last_wednesday
    
    else:
        # Weekly expiry: Find next Wednesday
        days_ahead = 2 - target_date.weekday()  # Wednesday = 2
        if days_ahead <= 0:  # If today is Wed or later, get next Wed
            days_ahead += 7
        expiry_date = target_date + timedelta(days=days_ahead)
    
    # Format: YYMONDD (e.g., 25DEC25)
    yy = str(expiry_date.year)[-2:]
    mon = expiry_date.strftime("%b").upper()
    dd = expiry_date.strftime("%d")
    
    expiry_str = f"{yy}{mon}{dd}"
    logger.debug(f"{'Monthly' if use_monthly else 'Weekly'} expiry: {expiry_str} ({expiry_date.strftime('%Y-%m-%d')})")
    
    return expiry_str

def format_symbol(underlying: str, expiry: str, strike: int, option_type: str, broker: str = 'zerodha') -> str:
    """
    Format option symbol for specific broker
    
    Args:
        underlying: BANKNIFTY
        expiry: 25DEC25
        strike: 52000
        option_type: CE or PE
        broker: zerodha or dhan
        
    Returns:
        Formatted symbol string
        
    Examples:
        Zerodha: BANKNIFTY25DEC2552000CE
        Dhan: BANKNIFTY 25DEC25 52000 CE (verify format!)
    """
    broker = broker.lower()
    
    if broker == 'zerodha':
        # Zerodha format: BANKNIFTY25DEC2552000CE (no spaces)
        symbol = f"{underlying}{expiry}{strike}{option_type}"
    
    elif broker == 'dhan':
        # Dhan format: May have spaces (TODO: verify with OpenAlgo docs)
        symbol = f"{underlying} {expiry} {strike} {option_type}"
    
    else:
        # Default to Zerodha format
        logger.warning(f"Unknown broker '{broker}', using Zerodha format")
        symbol = f"{underlying}{expiry}{strike}{option_type}"
    
    logger.debug(f"Formatted symbol for {broker}: {symbol}")
    return symbol

def days_to_expiry(expiry_str: str) -> int:
    """
    Calculate days remaining to expiry
    
    Args:
        expiry_str: Expiry in format YYMONDD (e.g., '25DEC25')
        
    Returns:
        Number of days to expiry
    """
    try:
        # Parse expiry string
        yy = int("20" + expiry_str[:2])
        mon = expiry_str[2:5]
        dd = int(expiry_str[5:7])
        
        # Convert month name to number
        month_map = {
            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
            'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
            'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
        }
        mm = month_map.get(mon.upper())
        
        if mm is None:
            logger.error(f"Invalid month in expiry: {mon}")
            return 0
        
        expiry_date = datetime(yy, mm, dd)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        days = (expiry_date - today).days
        logger.debug(f"Days to expiry ({expiry_str}): {days}")
        
        return max(0, days)
    
    except Exception as e:
        logger.error(f"Failed to calculate days to expiry: {e}")
        return 0

def validate_signal(signal: dict) -> tuple:
    """
    Validate signal payload has required fields
    
    Args:
        signal: Signal dictionary from webhook
        
    Returns:
        (is_valid, error_message)
    """
    required_fields = ['type', 'position', 'price', 'timestamp']
    
    for field in required_fields:
        if field not in signal:
            return False, f"Missing required field: {field}"
    
    # Validate signal type
    valid_types = ['BASE_ENTRY', 'PYRAMID', 'EXIT']
    if signal['type'] not in valid_types:
        return False, f"Invalid signal type: {signal['type']}"
    
    # Validate position format
    position = signal.get('position', '')
    if not position.startswith('Long_'):
        return False, f"Invalid position format: {position}"
    
    try:
        position_num = int(position.split('_')[1])
        if position_num < 1 or position_num > 6:
            return False, f"Position number out of range: {position_num}"
    except (IndexError, ValueError):
        return False, f"Invalid position format: {position}"
    
    # Validate numeric fields
    try:
        float(signal['price'])
        if 'stop' in signal:
            float(signal['stop'])
        if 'suggested_lots' in signal:
            int(signal['suggested_lots'])
    except (ValueError, TypeError) as e:
        return False, f"Invalid numeric field: {e}"
    
    return True, ""


