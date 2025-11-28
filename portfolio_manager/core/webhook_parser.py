"""
Webhook Parser Utility Module

Handles:
- Signal fingerprinting for duplicate detection
- Duplicate detection with rolling time window
- JSON structure validation
- Signal parsing with error handling
"""
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict
from dataclasses import dataclass

from core.models import Signal


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

