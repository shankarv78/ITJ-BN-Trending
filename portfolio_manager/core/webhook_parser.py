"""
Webhook Parser Utility Module

Handles:
- Signal fingerprinting for duplicate detection
- Duplicate detection with rolling time window
- JSON structure validation
- Signal parsing with error handling
- EOD_MONITOR signal parsing for pre-close execution
"""
import logging
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Union
from dataclasses import dataclass

from core.models import Signal, EODMonitorSignal

logger = logging.getLogger(__name__)


@dataclass
class SignalFingerprint:
    """
    Fingerprint for duplicate detection

    Matches signals based on:
    - instrument
    - signal_type
    - position
    - timestamp (within time window)
    """
    instrument: str
    signal_type: str
    position: str
    timestamp: datetime

    def matches(self, other: 'SignalFingerprint', window_seconds: int = 60) -> bool:
        """
        Check if this fingerprint matches another within time window

        Args:
            other: Other SignalFingerprint to compare
            window_seconds: Time window in seconds (default: 60)

        Returns:
            True if signals are duplicates (same instrument, type, position within time window)
        """
        if (self.instrument != other.instrument or
            self.signal_type != other.signal_type or
            self.position != other.position):
            return False

        # Check if timestamps are within window
        time_diff = abs((self.timestamp - other.timestamp).total_seconds())
        return time_diff <= window_seconds


class DuplicateDetector:
    """
    Rolling window duplicate detection for webhook signals

    Features:
    - Thread-safe (uses threading.Lock())
    - 60-second rolling window
    - Automatic cleanup of old entries
    - Memory-efficient (deque with maxlen)
    """

    def __init__(self, window_seconds: int = 60, max_history: int = 1000):
        """
        Initialize duplicate detector

        Args:
            window_seconds: Time window for duplicate detection (default: 60 seconds)
            max_history: Maximum number of fingerprints to keep (default: 1000)
        """
        self.window_seconds = window_seconds
        self.max_history = max_history
        self._history = deque(maxlen=max_history)
        self._lock = threading.Lock()  # Thread safety for concurrent webhook requests
        self._stats = {
            'total_checked': 0,
            'duplicates_found': 0,
            'cleanups_performed': 0
        }

    def is_duplicate(self, signal: Signal) -> bool:
        """
        Check if signal is a duplicate

        Args:
            signal: Signal to check

        Returns:
            True if duplicate detected, False otherwise
        """
        with self._lock:  # Acquire lock for thread-safe access
            self._stats['total_checked'] += 1

            # Create fingerprint for this signal
            fingerprint = SignalFingerprint(
                instrument=signal.instrument,
                signal_type=signal.signal_type.value,
                position=signal.position,
                timestamp=signal.timestamp
            )

            # Check against history
            for existing_fp in self._history:
                if fingerprint.matches(existing_fp, self.window_seconds):
                    self._stats['duplicates_found'] += 1
                    return True

            # Not a duplicate, add to history
            self._history.append(fingerprint)

            # Periodic cleanup (every 100 checks to avoid overhead)
            if self._stats['total_checked'] % 100 == 0:
                self._clean_old_entries()

            return False

    def remove_failed_signal(self, signal: Signal) -> bool:
        """
        Remove a signal from duplicate history after failed processing.

        This allows the same signal to be retried if it fails
        (e.g., EXIT fails due to no positions, then positions are opened,
        next EXIT should not be blocked as duplicate).

        Args:
            signal: Signal that failed processing

        Returns:
            True if signal was found and removed, False otherwise
        """
        with self._lock:
            fingerprint = SignalFingerprint(
                instrument=signal.instrument,
                signal_type=signal.signal_type.value,
                position=signal.position,
                timestamp=signal.timestamp
            )

            # Find and remove matching fingerprint
            new_history = deque(maxlen=self.max_history)
            removed = False
            for fp in self._history:
                if not fingerprint.matches(fp, self.window_seconds):
                    new_history.append(fp)
                else:
                    removed = True

            if removed:
                self._history = new_history
                logger.debug(f"Removed failed signal from duplicate history: {signal.signal_type.value} {signal.position}")

            return removed

    def _clean_old_entries(self):
        """
        Remove entries older than window_seconds

        Called periodically to prevent memory growth
        """
        if not self._history:
            return

        now = datetime.now()
        cutoff_time = now - timedelta(seconds=self.window_seconds)

        # Remove old entries (deque doesn't support direct removal, so rebuild)
        # Since we use maxlen, old entries are automatically evicted, but we
        # can still clean up entries that are definitely too old
        new_history = deque(maxlen=self.max_history)
        for fp in self._history:
            if fp.timestamp >= cutoff_time:
                new_history.append(fp)

        removed = len(self._history) - len(new_history)
        if removed > 0:
            self._history = new_history
            self._stats['cleanups_performed'] += 1

    def get_stats(self) -> Dict:
        """
        Get detector statistics

        Returns:
            Dictionary with stats:
            - total_checked: Total signals checked
            - duplicates_found: Number of duplicates detected
            - cleanups_performed: Number of cleanup operations
            - history_size: Current number of fingerprints in history
        """
        with self._lock:
            return {
                'total_checked': self._stats['total_checked'],
                'duplicates_found': self._stats['duplicates_found'],
                'cleanups_performed': self._stats['cleanups_performed'],
                'history_size': len(self._history),
                'window_seconds': self.window_seconds,
                'max_history': self.max_history
            }

    def clear(self):
        """Clear all history (useful for testing)"""
        with self._lock:
            self._history.clear()
            self._stats = {
                'total_checked': 0,
                'duplicates_found': 0,
                'cleanups_performed': 0
            }


def validate_json_structure(data: dict) -> Tuple[bool, Optional[str]]:
    """
    Validate basic JSON structure before parsing

    Args:
        data: JSON data dictionary

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if structure is valid
        - error_message: None if valid, error description if invalid
    """
    if not isinstance(data, dict):
        return False, "Data must be a dictionary"

    if not data:
        return False, "Data dictionary is empty"

    # Check for required top-level fields (quick check before full parsing)
    required_fields = ['type', 'instrument', 'position', 'timestamp']
    missing = [f for f in required_fields if f not in data]
    if missing:
        return False, f"Missing required fields: {', '.join(missing)}"

    return True, None


def parse_webhook_signal(data: dict) -> Tuple[Optional[Signal], Optional[str]]:
    """
    Parse webhook JSON data into Signal object with better error messages

    Wrapper around Signal.from_dict() that provides more context in error messages

    Args:
        data: JSON data dictionary from webhook

    Returns:
        Tuple of (signal, error_message)
        - signal: Signal object if parsing successful, None otherwise
        - error_message: None if successful, error description if failed
    """
    # First validate structure
    is_valid, structure_error = validate_json_structure(data)
    if not is_valid:
        return None, structure_error

    # Try to parse using Signal.from_dict()
    try:
        signal = Signal.from_dict(data)
        return signal, None
    except ValueError as e:
        # ValueError from Signal.from_dict() contains detailed error message
        return None, f"Validation error: {str(e)}"
    except Exception as e:
        # Unexpected errors
        return None, f"Unexpected error parsing signal: {str(e)}"


# ============================================================
# EOD_MONITOR Signal Parsing
# ============================================================

def is_eod_monitor_signal(data: dict) -> bool:
    """
    Check if the incoming data is an EOD_MONITOR signal.

    Args:
        data: JSON data dictionary from webhook

    Returns:
        True if this is an EOD_MONITOR signal
    """
    if not isinstance(data, dict):
        return False

    signal_type = data.get('type', '').upper()
    return signal_type == 'EOD_MONITOR'


def validate_eod_json_structure(data: dict) -> Tuple[bool, Optional[str]]:
    """
    Validate JSON structure for EOD_MONITOR signals.

    EOD_MONITOR signals have a different structure than regular signals:
    - type: "EOD_MONITOR"
    - instrument: "BANK_NIFTY" or "GOLD_MINI"
    - timestamp: ISO format datetime
    - price: Current price
    - conditions: Dict with all 7 entry conditions + long_entry/long_exit flags
    - indicators: Dict with RSI, EMA, DC_upper, ADX, ER, SuperTrend, ATR values
    - position_status: Dict with in_position, pyramid_count
    - sizing: Dict with suggested_lots, stop_level

    Args:
        data: JSON data dictionary

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(data, dict):
        return False, "Data must be a dictionary"

    if not data:
        return False, "Data dictionary is empty"

    # Check for required top-level fields
    # NOTE: 'sizing' is NOT required - Python calculates position sizing using real portfolio equity
    # TradingView sends raw data (conditions, indicators, price, position_status)
    # Python Portfolio Manager uses Tom Basso methodology with SHARED capital across instruments
    required_fields = ['type', 'instrument', 'timestamp', 'price',
                       'conditions', 'indicators', 'position_status']
    missing = [f for f in required_fields if f not in data]
    if missing:
        return False, f"EOD_MONITOR missing required fields: {', '.join(missing)}"

    # Validate type
    if data.get('type', '').upper() != 'EOD_MONITOR':
        return False, f"Invalid signal type for EOD: {data.get('type')}"

    # Validate conditions dict
    conditions = data.get('conditions', {})
    if not isinstance(conditions, dict):
        return False, "conditions must be a dictionary"

    # Check required condition fields
    required_conditions = ['rsi_condition', 'ema_condition', 'dc_condition',
                          'adx_condition', 'er_condition', 'st_condition',
                          'not_doji', 'long_entry', 'long_exit']
    missing_conditions = [c for c in required_conditions if c not in conditions]
    if missing_conditions:
        return False, f"conditions missing fields: {', '.join(missing_conditions)}"

    # Validate indicators dict
    indicators = data.get('indicators', {})
    if not isinstance(indicators, dict):
        return False, "indicators must be a dictionary"

    # Check required indicator fields
    required_indicators = ['rsi', 'ema', 'dc_upper', 'adx', 'er', 'supertrend', 'atr']
    missing_indicators = [i for i in required_indicators if i not in indicators]
    if missing_indicators:
        return False, f"indicators missing fields: {', '.join(missing_indicators)}"

    # Validate position_status dict
    position_status = data.get('position_status', {})
    if not isinstance(position_status, dict):
        return False, "position_status must be a dictionary"

    if 'in_position' not in position_status:
        return False, "position_status missing 'in_position' field"

    # NOTE: 'sizing' is OPTIONAL - if present, validate structure but not required
    # Python calculates position sizing using real portfolio equity (shared across instruments)
    sizing = data.get('sizing')
    if sizing is not None:
        if not isinstance(sizing, dict):
            return False, "sizing must be a dictionary if provided"
        # sizing fields are optional - Python will calculate its own values

    return True, None


def parse_eod_monitor_signal(data: dict) -> Tuple[Optional[EODMonitorSignal], Optional[str]]:
    """
    Parse webhook JSON data into EODMonitorSignal object.

    EOD_MONITOR signals contain RAW DATA from TradingView:
    - All 7 entry condition states (boolean)
    - All indicator values (float)
    - Current position status (for reference)

    IMPORTANT: TradingView is ONLY a signal generator.
    Python Portfolio Manager calculates position sizing using:
    - REAL portfolio equity (shared across Bank Nifty + Gold Mini)
    - Tom Basso methodology
    - Current margin availability

    Args:
        data: JSON data dictionary from webhook

    Returns:
        Tuple of (signal, error_message)
        - signal: EODMonitorSignal object if parsing successful, None otherwise
        - error_message: None if successful, error description if failed

    Example input (from v8.0 Pine Script):
        {
            "type": "EOD_MONITOR",
            "instrument": "BANK_NIFTY",
            "timestamp": "2025-12-02T15:25:00Z",
            "price": 52450.50,
            "conditions": {
                "rsi_condition": true,
                "ema_condition": true,
                "dc_condition": true,
                "adx_condition": true,
                "er_condition": true,
                "st_condition": true,
                "not_doji": true,
                "long_entry": true,
                "long_exit": false
            },
            "indicators": {
                "rsi": 72.5,
                "ema": 51800.25,
                "dc_upper": 52300.00,
                "adx": 28.5,
                "er": 0.85,
                "supertrend": 52100.00,
                "atr": 180.5
            },
            "position_status": {
                "in_position": false,
                "pyramid_count": 0
            }
        }

    Note: 'sizing' field is NOT sent by Pine Script v8.0+.
    Python calculates position sizing using real portfolio equity.
    """
    # First validate structure
    is_valid, structure_error = validate_eod_json_structure(data)
    if not is_valid:
        logger.warning(f"[EOD] Invalid EOD_MONITOR structure: {structure_error}")
        return None, structure_error

    # Try to parse using EODMonitorSignal.from_dict()
    try:
        signal = EODMonitorSignal.from_dict(data)

        # Log successful parse
        action = signal.get_signal_type_to_execute()
        logger.info(
            f"[EOD] Parsed EOD_MONITOR signal: {signal.instrument}, "
            f"price={signal.price:.2f}, "
            f"potential_action={action.value if action else 'None'}, "
            f"conditions_met={signal.conditions.all_entry_conditions_met()}"
        )

        return signal, None

    except ValueError as e:
        error_msg = f"EOD validation error: {str(e)}"
        logger.warning(f"[EOD] {error_msg}")
        return None, error_msg

    except Exception as e:
        error_msg = f"Unexpected error parsing EOD_MONITOR signal: {str(e)}"
        logger.error(f"[EOD] {error_msg}", exc_info=True)
        return None, error_msg


def parse_any_signal(data: dict) -> Tuple[Optional[Union[Signal, EODMonitorSignal]], Optional[str], str]:
    """
    Parse any webhook signal (regular or EOD_MONITOR).

    This is the main entry point for webhook signal parsing that handles
    both regular trading signals and EOD_MONITOR signals.

    Args:
        data: JSON data dictionary from webhook

    Returns:
        Tuple of (signal, error_message, signal_type)
        - signal: Signal or EODMonitorSignal object if successful, None otherwise
        - error_message: None if successful, error description if failed
        - signal_type: 'regular', 'eod_monitor', or 'unknown'

    Example:
        signal, error, sig_type = parse_any_signal(webhook_data)
        if error:
            log_error(error)
        elif sig_type == 'eod_monitor':
            handle_eod_signal(signal)
        else:
            handle_regular_signal(signal)
    """
    if not isinstance(data, dict):
        return None, "Data must be a dictionary", "unknown"

    # Check if this is an EOD_MONITOR signal
    if is_eod_monitor_signal(data):
        signal, error = parse_eod_monitor_signal(data)
        return signal, error, 'eod_monitor'

    # Regular signal
    signal, error = parse_webhook_signal(data)
    return signal, error, 'regular'
