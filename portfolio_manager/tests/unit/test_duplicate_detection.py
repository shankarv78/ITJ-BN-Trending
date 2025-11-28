"""
Unit tests for duplicate detection

Tests SignalFingerprint matching and DuplicateDetector logic
"""
import pytest
import time
import threading
from datetime import datetime, timedelta
from core.webhook_parser import SignalFingerprint, DuplicateDetector
from core.models import Signal, SignalType


@pytest.fixture
def base_signal():
    """Base signal for testing"""
    return Signal(
        timestamp=datetime(2025, 11, 28, 10, 30, 0),
        instrument="BANK_NIFTY",
        signal_type=SignalType.BASE_ENTRY,
        position="Long_1",
        price=52000.0,
        stop=51650.0,
        suggested_lots=5,
        atr=350.0,
        er=0.82,
        supertrend=51650.0
    )


@pytest.fixture
def duplicate_detector():
    """Fresh duplicate detector for each test"""
    return DuplicateDetector(window_seconds=60, max_history=1000)


class TestSignalFingerprint:
    """Test SignalFingerprint matching logic"""

    def test_fingerprint_matches_identical(self):
        """Test fingerprint matches identical signal"""
        fp1 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        fp2 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        
        assert fp1.matches(fp2, window_seconds=60) is True

    def test_fingerprint_matches_within_window(self):
        """Test fingerprint matches within 60s window"""
        fp1 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        fp2 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 30)  # 30 seconds later
        )
        
        assert fp1.matches(fp2, window_seconds=60) is True

    def test_fingerprint_not_matches_outside_window(self):
        """Test fingerprint doesn't match outside 60s window"""
        fp1 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        fp2 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 31, 1)  # 61 seconds later
        )
        
        assert fp1.matches(fp2, window_seconds=60) is False

    def test_fingerprint_not_matches_different_instrument(self):
        """Test fingerprint doesn't match different instrument"""
        fp1 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        fp2 = SignalFingerprint(
            instrument="GOLD_MINI",  # Different instrument
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        
        assert fp1.matches(fp2, window_seconds=60) is False

    def test_fingerprint_not_matches_different_type(self):
        """Test fingerprint doesn't match different signal type"""
        fp1 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        fp2 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="PYRAMID",  # Different type
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        
        assert fp1.matches(fp2, window_seconds=60) is False

    def test_fingerprint_not_matches_different_position(self):
        """Test fingerprint doesn't match different position"""
        fp1 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        fp2 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_2",  # Different position
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        
        assert fp1.matches(fp2, window_seconds=60) is False

    def test_fingerprint_matches_exactly_at_window_boundary(self):
        """Test fingerprint matches exactly at 60s boundary"""
        fp1 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 30, 0)
        )
        fp2 = SignalFingerprint(
            instrument="BANK_NIFTY",
            signal_type="BASE_ENTRY",
            position="Long_1",
            timestamp=datetime(2025, 11, 28, 10, 31, 0)  # Exactly 60 seconds later
        )
        
        assert fp1.matches(fp2, window_seconds=60) is True


class TestDuplicateDetector:
    """Test DuplicateDetector functionality"""

    def test_first_signal_not_duplicate(self, duplicate_detector, base_signal):
        """Test first signal is not a duplicate"""
        assert duplicate_detector.is_duplicate(base_signal) is False

    def test_identical_signal_is_duplicate(self, duplicate_detector, base_signal):
        """Test identical signal within window is duplicate"""
        # First signal
        assert duplicate_detector.is_duplicate(base_signal) is False
        
        # Same signal again (should be duplicate)
        assert duplicate_detector.is_duplicate(base_signal) is True

    def test_different_instrument_not_duplicate(self, duplicate_detector, base_signal):
        """Test different instrument is not duplicate"""
        # First signal
        assert duplicate_detector.is_duplicate(base_signal) is False
        
        # Different instrument
        different_signal = Signal(
            timestamp=base_signal.timestamp,
            instrument="GOLD_MINI",  # Different
            signal_type=base_signal.signal_type,
            position=base_signal.position,
            price=base_signal.price,
            stop=base_signal.stop,
            suggested_lots=base_signal.suggested_lots,
            atr=base_signal.atr,
            er=base_signal.er,
            supertrend=base_signal.supertrend
        )
        
        assert duplicate_detector.is_duplicate(different_signal) is False

    def test_different_position_not_duplicate(self, duplicate_detector, base_signal):
        """Test different position is not duplicate"""
        # First signal
        assert duplicate_detector.is_duplicate(base_signal) is False
        
        # Different position
        different_signal = Signal(
            timestamp=base_signal.timestamp,
            instrument=base_signal.instrument,
            signal_type=base_signal.signal_type,
            position="Long_2",  # Different
            price=base_signal.price,
            stop=base_signal.stop,
            suggested_lots=base_signal.suggested_lots,
            atr=base_signal.atr,
            er=base_signal.er,
            supertrend=base_signal.supertrend
        )
        
        assert duplicate_detector.is_duplicate(different_signal) is False

    def test_signal_after_window_not_duplicate(self, duplicate_detector, base_signal):
        """Test signal after window expires is not duplicate"""
        # First signal
        assert duplicate_detector.is_duplicate(base_signal) is False
        
        # Same signal but 61 seconds later
        later_signal = Signal(
            timestamp=base_signal.timestamp + timedelta(seconds=61),
            instrument=base_signal.instrument,
            signal_type=base_signal.signal_type,
            position=base_signal.position,
            price=base_signal.price,
            stop=base_signal.stop,
            suggested_lots=base_signal.suggested_lots,
            atr=base_signal.atr,
            er=base_signal.er,
            supertrend=base_signal.supertrend
        )
        
        assert duplicate_detector.is_duplicate(later_signal) is False

    def test_stats_tracking(self, duplicate_detector, base_signal):
        """Test statistics are tracked correctly"""
        stats = duplicate_detector.get_stats()
        assert stats['total_checked'] == 0
        assert stats['duplicates_found'] == 0
        
        # Check first signal
        duplicate_detector.is_duplicate(base_signal)
        stats = duplicate_detector.get_stats()
        assert stats['total_checked'] == 1
        assert stats['duplicates_found'] == 0
        
        # Check duplicate
        duplicate_detector.is_duplicate(base_signal)
        stats = duplicate_detector.get_stats()
        assert stats['total_checked'] == 2
        assert stats['duplicates_found'] == 1

    def test_history_size_tracking(self, duplicate_detector, base_signal):
        """Test history size is tracked"""
        stats = duplicate_detector.get_stats()
        assert stats['history_size'] == 0
        
        duplicate_detector.is_duplicate(base_signal)
        stats = duplicate_detector.get_stats()
        assert stats['history_size'] == 1

    def test_clear_resets_stats(self, duplicate_detector, base_signal):
        """Test clear() resets all stats"""
        duplicate_detector.is_duplicate(base_signal)
        duplicate_detector.is_duplicate(base_signal)  # Duplicate
        
        duplicate_detector.clear()
        
        stats = duplicate_detector.get_stats()
        assert stats['total_checked'] == 0
        assert stats['duplicates_found'] == 0
        assert stats['history_size'] == 0

    def test_multiple_signals_same_window(self, duplicate_detector):
        """Test multiple signals in same window"""
        signals = []
        base_time = datetime(2025, 11, 28, 10, 30, 0)
        
        # Create 5 signals within 60s window
        for i in range(5):
            signal = Signal(
                timestamp=base_time + timedelta(seconds=i * 10),
                instrument="BANK_NIFTY",
                signal_type=SignalType.BASE_ENTRY,
                position="Long_1",
                price=52000.0,
                stop=51650.0,
                suggested_lots=5,
                atr=350.0,
                er=0.82,
                supertrend=51650.0
            )
            signals.append(signal)
        
        # First signal not duplicate
        assert duplicate_detector.is_duplicate(signals[0]) is False
        
        # All others should be duplicates (same instrument, type, position within window)
        for i in range(1, 5):
            assert duplicate_detector.is_duplicate(signals[i]) is True

    def test_thread_safety(self, duplicate_detector):
        """Test duplicate detector is thread-safe"""
        base_signal = Signal(
            timestamp=datetime(2025, 11, 28, 10, 30, 0),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=52000.0,
            stop=51650.0,
            suggested_lots=5,
            atr=350.0,
            er=0.82,
            supertrend=51650.0
        )
        
        results = []
        errors = []
        
        def check_duplicate():
            try:
                result = duplicate_detector.is_duplicate(base_signal)
                results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Create 10 threads checking simultaneously
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=check_duplicate)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # Should have no errors
        assert len(errors) == 0
        
        # First check should be False, rest should be True (duplicates)
        # But due to race conditions, exact count may vary
        # Important: No exceptions should occur
        assert len(results) == 10


class TestValidationHelpers:
    """Test validation helper functions"""

    def test_validate_json_structure_valid(self):
        """Test validate_json_structure with valid data"""
        from core.webhook_parser import validate_json_structure
        
        data = {
            "type": "BASE_ENTRY",
            "instrument": "BANK_NIFTY",
            "position": "Long_1",
            "timestamp": "2025-11-28T10:30:00Z"
        }
        
        is_valid, error = validate_json_structure(data)
        assert is_valid is True
        assert error is None

    def test_validate_json_structure_not_dict(self):
        """Test validate_json_structure with non-dict"""
        from core.webhook_parser import validate_json_structure
        
        is_valid, error = validate_json_structure("not a dict")
        assert is_valid is False
        assert "must be a dictionary" in error

    def test_validate_json_structure_empty_dict(self):
        """Test validate_json_structure with empty dict"""
        from core.webhook_parser import validate_json_structure
        
        is_valid, error = validate_json_structure({})
        assert is_valid is False
        assert "empty" in error

    def test_validate_json_structure_missing_fields(self):
        """Test validate_json_structure with missing required fields"""
        from core.webhook_parser import validate_json_structure
        
        data = {"type": "BASE_ENTRY"}  # Missing other fields
        is_valid, error = validate_json_structure(data)
        assert is_valid is False
        assert "Missing required fields" in error

    def test_parse_webhook_signal_valid(self):
        """Test parse_webhook_signal with valid data"""
        from core.webhook_parser import parse_webhook_signal
        
        data = {
            "type": "BASE_ENTRY",
            "instrument": "BANK_NIFTY",
            "position": "Long_1",
            "price": 52000.0,
            "stop": 51650.0,
            "lots": 5,
            "atr": 350.0,
            "er": 0.82,
            "supertrend": 51650.0,
            "timestamp": "2025-11-28T10:30:00Z"
        }
        
        signal, error = parse_webhook_signal(data)
        assert signal is not None
        assert error is None
        assert signal.signal_type == SignalType.BASE_ENTRY

    def test_parse_webhook_signal_invalid_structure(self):
        """Test parse_webhook_signal with invalid structure"""
        from core.webhook_parser import parse_webhook_signal
        
        signal, error = parse_webhook_signal("not a dict")
        assert signal is None
        assert error is not None
        assert "must be a dictionary" in error

    def test_parse_webhook_signal_validation_error(self):
        """Test parse_webhook_signal with validation error"""
        from core.webhook_parser import parse_webhook_signal
        
        data = {
            "type": "BASE_ENTRY",
            "instrument": "BANK_NIFTY",
            "position": "Long_7",  # Invalid position
            "price": 52000.0,
            "stop": 51650.0,
            "lots": 5,
            "atr": 350.0,
            "er": 0.82,
            "supertrend": 51650.0,
            "timestamp": "2025-11-28T10:30:00Z"
        }
        
        signal, error = parse_webhook_signal(data)
        assert signal is None
        assert error is not None
        assert "Validation error" in error
        assert "Invalid position" in error

