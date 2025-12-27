"""
Holiday Calendar - Track market holidays for NSE and MCX

Features:
- Built-in weekend detection
- CSV loading for exchange holidays
- REST API for managing holidays
- Thread-safe operations
"""
import logging
import csv
import threading
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class Holiday:
    """Represents a market holiday."""
    date: date
    exchange: str  # "NSE" or "MCX"
    description: str

    def to_dict(self) -> Dict:
        return {
            'date': self.date.isoformat(),
            'exchange': self.exchange,
            'description': self.description
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Holiday':
        return cls(
            date=date.fromisoformat(data['date']),
            exchange=data['exchange'],
            description=data['description']
        )


class HolidayCalendar:
    """
    Market holiday calendar for NSE and MCX exchanges.

    Features:
    - Weekend detection (built-in)
    - CSV holiday loading
    - In-memory storage with file persistence
    - Thread-safe operations
    """

    VALID_EXCHANGES = {'NSE', 'MCX'}

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize HolidayCalendar.

        Args:
            data_dir: Directory for holiday data files (default: .taskmaster/data/)
        """
        self.data_dir = Path(data_dir) if data_dir else Path('.taskmaster/data')
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # In-memory storage: {(date, exchange): Holiday}
        self._holidays: Dict[Tuple[date, str], Holiday] = {}
        self._lock = threading.Lock()

        # Load existing holidays from JSON
        self._load_from_json()

        logger.info(f"[HOLIDAY] Calendar initialized with {len(self._holidays)} holidays")

    def is_holiday(self, check_date: date, exchange: str) -> Tuple[bool, str]:
        """
        Check if a date is a holiday.

        Built-in: Weekends are always holidays.

        Args:
            check_date: Date to check
            exchange: "NSE" or "MCX"

        Returns:
            Tuple of (is_holiday, reason)
        """
        # Weekend check (always)
        if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
            return True, "Weekend"

        # Exchange holiday check
        with self._lock:
            key = (check_date, exchange.upper())
            if key in self._holidays:
                return True, self._holidays[key].description

        return False, ""

    def is_trading_day(self, check_date: date, exchange: str) -> bool:
        """Check if a date is a trading day (not holiday)."""
        is_holiday, _ = self.is_holiday(check_date, exchange)
        return not is_holiday

    def add_holiday(self, holiday_date: date, exchange: str, description: str) -> bool:
        """
        Add a holiday.

        Args:
            holiday_date: Date of holiday
            exchange: "NSE" or "MCX"
            description: Holiday description

        Returns:
            True if added, False if already exists
        """
        exchange = exchange.upper()
        if exchange not in self.VALID_EXCHANGES:
            raise ValueError(f"Invalid exchange: {exchange}. Must be one of {self.VALID_EXCHANGES}")

        holiday = Holiday(date=holiday_date, exchange=exchange, description=description)

        with self._lock:
            key = (holiday_date, exchange)
            if key in self._holidays:
                logger.warning(f"[HOLIDAY] Holiday already exists: {holiday_date} {exchange}")
                return False

            self._holidays[key] = holiday
            self._save_to_json()

        logger.info(f"[HOLIDAY] Added: {holiday_date} {exchange} - {description}")
        return True

    def remove_holiday(self, holiday_date: date, exchange: str) -> bool:
        """
        Remove a holiday.

        Args:
            holiday_date: Date to remove
            exchange: "NSE" or "MCX"

        Returns:
            True if removed, False if not found
        """
        exchange = exchange.upper()

        with self._lock:
            key = (holiday_date, exchange)
            if key not in self._holidays:
                return False

            del self._holidays[key]
            self._save_to_json()

        logger.info(f"[HOLIDAY] Removed: {holiday_date} {exchange}")
        return True

    def get_holidays(self, exchange: Optional[str] = None, year: Optional[int] = None) -> List[Holiday]:
        """
        Get list of holidays.

        Args:
            exchange: Filter by exchange (optional)
            year: Filter by year (optional)

        Returns:
            List of Holiday objects
        """
        with self._lock:
            holidays = list(self._holidays.values())

        # Filter by exchange
        if exchange:
            exchange = exchange.upper()
            holidays = [h for h in holidays if h.exchange == exchange]

        # Filter by year
        if year:
            holidays = [h for h in holidays if h.date.year == year]

        # Sort by date
        holidays.sort(key=lambda h: h.date)

        return holidays

    def load_from_csv(self, csv_path: str, exchange: Optional[str] = None) -> int:
        """
        Load holidays from CSV file.

        CSV Format:
        date,exchange,description
        2025-01-26,NSE,Republic Day

        Args:
            csv_path: Path to CSV file
            exchange: Override exchange for all entries (optional)

        Returns:
            Number of holidays loaded
        """
        count = 0

        try:
            with open(csv_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    try:
                        holiday_date = date.fromisoformat(row['date'].strip())
                        holiday_exchange = exchange or row.get('exchange', '').strip().upper()
                        description = row.get('description', '').strip()

                        if not holiday_exchange:
                            logger.warning(f"[HOLIDAY] Skipping row without exchange: {row}")
                            continue

                        if holiday_exchange not in self.VALID_EXCHANGES:
                            logger.warning(f"[HOLIDAY] Invalid exchange {holiday_exchange} in CSV row: {row}")
                            continue

                        if self.add_holiday(holiday_date, holiday_exchange, description):
                            count += 1

                    except (ValueError, KeyError) as e:
                        logger.warning(f"[HOLIDAY] Error parsing CSV row {row}: {e}")
                        continue

            logger.info(f"[HOLIDAY] Loaded {count} holidays from {csv_path}")

        except FileNotFoundError:
            logger.error(f"[HOLIDAY] CSV file not found: {csv_path}")
        except Exception as e:
            logger.error(f"[HOLIDAY] Error loading CSV: {e}")

        return count

    def export_to_csv(self, csv_path: str, exchange: Optional[str] = None) -> int:
        """
        Export holidays to CSV file.

        Args:
            csv_path: Path to CSV file
            exchange: Filter by exchange (optional)

        Returns:
            Number of holidays exported
        """
        holidays = self.get_holidays(exchange=exchange)

        with open(csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['date', 'exchange', 'description'])
            writer.writeheader()

            for holiday in holidays:
                writer.writerow({
                    'date': holiday.date.isoformat(),
                    'exchange': holiday.exchange,
                    'description': holiday.description
                })

        logger.info(f"[HOLIDAY] Exported {len(holidays)} holidays to {csv_path}")
        return len(holidays)

    def _get_json_path(self) -> Path:
        """Get path to JSON storage file."""
        return self.data_dir / 'holidays.json'

    def _save_to_json(self):
        """Save holidays to JSON file (internal, called under lock)."""
        holidays = [h.to_dict() for h in self._holidays.values()]

        with open(self._get_json_path(), 'w', encoding='utf-8') as f:
            json.dump(holidays, f, indent=2)

    def _load_from_json(self):
        """Load holidays from JSON file on startup."""
        json_path = self._get_json_path()

        if not json_path.exists():
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for item in data:
                holiday = Holiday.from_dict(item)
                key = (holiday.date, holiday.exchange)
                self._holidays[key] = holiday

            logger.info(f"[HOLIDAY] Loaded {len(self._holidays)} holidays from {json_path}")

        except Exception as e:
            logger.error(f"[HOLIDAY] Error loading JSON: {e}")

    def clear_all(self, exchange: Optional[str] = None):
        """
        Clear all holidays (or for a specific exchange).

        Args:
            exchange: Optional exchange to clear (None = clear all)
        """
        with self._lock:
            if exchange:
                exchange = exchange.upper()
                keys_to_remove = [k for k in self._holidays.keys() if k[1] == exchange]
                for key in keys_to_remove:
                    del self._holidays[key]
            else:
                self._holidays.clear()

            self._save_to_json()

        logger.info(f"[HOLIDAY] Cleared holidays" + (f" for {exchange}" if exchange else ""))

    def get_next_trading_day(self, from_date: date, exchange: str) -> date:
        """
        Get next trading day after a given date.

        Args:
            from_date: Starting date
            exchange: Exchange to check

        Returns:
            Next trading day
        """
        next_day = from_date + timedelta(days=1)

        while not self.is_trading_day(next_day, exchange):
            next_day += timedelta(days=1)
            # Safety: Don't go more than 30 days ahead
            if (next_day - from_date).days > 30:
                break

        return next_day

    def get_previous_trading_day(self, from_date: date, exchange: str) -> date:
        """
        Get previous trading day before a given date.

        Used for expiry calculation when the nominal expiry date falls on
        a weekend or holiday. For example:
        - If 5th is Sunday, return 3rd (Friday)
        - If 5th is Monday holiday and 4th is Sunday, 3rd is Saturday, return 2nd

        Args:
            from_date: Starting date
            exchange: Exchange to check ("NSE" or "MCX")

        Returns:
            Previous trading day (may be the same date if it's a trading day)
        """
        check_date = from_date

        while not self.is_trading_day(check_date, exchange):
            check_date -= timedelta(days=1)
            # Safety: Don't go more than 10 days back
            if (from_date - check_date).days > 10:
                logger.warning(f"[HOLIDAY] Could not find trading day within 10 days before {from_date}")
                break

        return check_date

    def get_actual_expiry_date(self, nominal_expiry: date, exchange: str) -> date:
        """
        Get the actual expiry date, adjusting for weekends and holidays.

        If the nominal expiry date is a weekend or holiday, returns the
        previous trading day.

        Args:
            nominal_expiry: The nominal expiry date (e.g., 5th of month for Gold Mini)
            exchange: Exchange to check ("NSE" or "MCX")

        Returns:
            Actual expiry date (adjusted for holidays/weekends)
        """
        if self.is_trading_day(nominal_expiry, exchange):
            return nominal_expiry
        return self.get_previous_trading_day(nominal_expiry, exchange)

    def get_status(self) -> Dict:
        """Get calendar status for API response."""
        today = date.today()

        nse_holiday, nse_reason = self.is_holiday(today, "NSE")
        mcx_holiday, mcx_reason = self.is_holiday(today, "MCX")

        return {
            'today': today.isoformat(),
            'nse': {
                'is_holiday': nse_holiday,
                'reason': nse_reason,
                'is_trading_day': not nse_holiday
            },
            'mcx': {
                'is_holiday': mcx_holiday,
                'reason': mcx_reason,
                'is_trading_day': not mcx_holiday
            },
            'total_holidays': len(self._holidays)
        }


# Global instance
_holiday_calendar: Optional[HolidayCalendar] = None


def get_holiday_calendar() -> Optional[HolidayCalendar]:
    """Get global HolidayCalendar instance."""
    return _holiday_calendar


def init_holiday_calendar(data_dir: Optional[str] = None) -> HolidayCalendar:
    """Initialize global HolidayCalendar."""
    global _holiday_calendar
    _holiday_calendar = HolidayCalendar(data_dir=data_dir)
    return _holiday_calendar
