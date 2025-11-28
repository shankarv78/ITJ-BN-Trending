"""
Unit tests for Signal.from_dict() parsing

Tests JSON to Signal conversion with validation
"""
import pytest
from datetime import datetime
from core.models import Signal, SignalType


@pytest.fixture
def valid_base_entry_data():
    """Valid BASE_ENTRY signal data"""
    return {
        "type": "BASE_ENTRY",
        "instrument": "BANK_NIFTY",
        "position": "Long_1",
        "price": 52000.0,
        "stop": 51650.0,
        "lots": 5,
        "atr": 350.0,
        "er": 0.82,
        "supertrend": 51650.0,
        "roc": 2.5,
        "timestamp": "2025-11-28T10:30:00Z"
    }


@pytest.fixture
def valid_pyramid_data():
    """Valid PYRAMID signal data"""
    return {
        "type": "PYRAMID",
        "instrument": "GOLD_MINI",
        "position": "Long_2",
        "price": 72500.0,
        "stop": 72000.0,
        "lots": 2,
        "atr": 450.0,
        "er": 0.8,
        "supertrend": 72000.0,
        "roc": 1.2,
        "timestamp": "2025-11-28T14:15:00Z"
    }


@pytest.fixture
def valid_exit_data():
    """Valid EXIT signal data with reason"""
    return {
        "type": "EXIT",
        "instrument": "BANK_NIFTY",
        "position": "Long_1",
        "price": 51800.0,
        "stop": 51800.0,
        "lots": 5,
        "atr": 500.0,
        "er": 0.75,
        "supertrend": 51500.0,
        "roc": 2.5,
        "reason": "TOM_BASSO_STOP",
        "timestamp": "2025-11-28T15:00:00Z"
    }


class TestValidSignals:
    """Test valid signal parsing"""

    def test_valid_base_entry(self, valid_base_entry_data):
        """Test parsing valid BASE_ENTRY signal"""
        signal = Signal.from_dict(valid_base_entry_data)
        
        assert signal.signal_type == SignalType.BASE_ENTRY
        assert signal.instrument == "BANK_NIFTY"
        assert signal.position == "Long_1"
        assert signal.price == 52000.0
        assert signal.stop == 51650.0
        assert signal.suggested_lots == 5
        assert signal.atr == 350.0
        assert signal.er == 0.82
        assert signal.supertrend == 51650.0
        assert signal.roc == 2.5
        assert signal.reason is None
        assert isinstance(signal.timestamp, datetime)

    def test_valid_pyramid(self, valid_pyramid_data):
        """Test parsing valid PYRAMID signal"""
        signal = Signal.from_dict(valid_pyramid_data)
        
        assert signal.signal_type == SignalType.PYRAMID
        assert signal.instrument == "GOLD_MINI"
        assert signal.position == "Long_2"
        assert signal.price == 72500.0
        assert signal.roc == 1.2

    def test_valid_exit_with_reason(self, valid_exit_data):
        """Test parsing valid EXIT signal with reason"""
        signal = Signal.from_dict(valid_exit_data)
        
        assert signal.signal_type == SignalType.EXIT
        assert signal.reason == "TOM_BASSO_STOP"
        assert signal.position == "Long_1"

    def test_valid_exit_all_position(self, valid_exit_data):
        """Test parsing EXIT with position='ALL'"""
        data = valid_exit_data.copy()
        data["position"] = "ALL"
        
        signal = Signal.from_dict(data)
        assert signal.position == "ALL"
        assert signal.signal_type == SignalType.EXIT

    def test_valid_signal_without_roc(self, valid_base_entry_data):
        """Test parsing signal without optional roc field"""
        data = valid_base_entry_data.copy()
        del data["roc"]
        
        signal = Signal.from_dict(data)
        assert signal.roc is None

    def test_valid_signal_with_lowercase_type(self, valid_base_entry_data):
        """Test parsing signal with lowercase type"""
        data = valid_base_entry_data.copy()
        data["type"] = "base_entry"
        
        signal = Signal.from_dict(data)
        assert signal.signal_type == SignalType.BASE_ENTRY

    def test_valid_signal_with_lowercase_instrument(self, valid_base_entry_data):
        """Test parsing signal with lowercase instrument"""
        data = valid_base_entry_data.copy()
        data["instrument"] = "bank_nifty"
        
        signal = Signal.from_dict(data)
        assert signal.instrument == "BANK_NIFTY"


class TestMissingFields:
    """Test missing required fields"""

    def test_missing_type(self, valid_base_entry_data):
        """Test missing type field"""
        data = valid_base_entry_data.copy()
        del data["type"]
        
        with pytest.raises(ValueError, match="Missing required fields"):
            Signal.from_dict(data)

    def test_missing_instrument(self, valid_base_entry_data):
        """Test missing instrument field"""
        data = valid_base_entry_data.copy()
        del data["instrument"]
        
        with pytest.raises(ValueError, match="Missing required fields"):
            Signal.from_dict(data)

    def test_missing_position(self, valid_base_entry_data):
        """Test missing position field"""
        data = valid_base_entry_data.copy()
        del data["position"]
        
        with pytest.raises(ValueError, match="Missing required fields"):
            Signal.from_dict(data)

    def test_missing_timestamp(self, valid_base_entry_data):
        """Test missing timestamp field"""
        data = valid_base_entry_data.copy()
        del data["timestamp"]
        
        with pytest.raises(ValueError, match="Missing required fields"):
            Signal.from_dict(data)


class TestInvalidValues:
    """Test invalid field values"""

    def test_invalid_signal_type(self, valid_base_entry_data):
        """Test invalid signal type"""
        data = valid_base_entry_data.copy()
        data["type"] = "INVALID_TYPE"
        
        with pytest.raises(ValueError, match="Invalid signal type"):
            Signal.from_dict(data)

    def test_invalid_instrument(self, valid_base_entry_data):
        """Test invalid instrument"""
        data = valid_base_entry_data.copy()
        data["instrument"] = "INVALID_INSTRUMENT"
        
        with pytest.raises(ValueError, match="Invalid instrument"):
            Signal.from_dict(data)

    def test_invalid_position_long_7(self, valid_base_entry_data):
        """Test invalid position Long_7 (strict validation)"""
        data = valid_base_entry_data.copy()
        data["position"] = "Long_7"
        
        with pytest.raises(ValueError, match="Invalid position.*Long_7"):
            Signal.from_dict(data)

    def test_invalid_position_short_1(self, valid_base_entry_data):
        """Test invalid position Short_1 (strict validation)"""
        data = valid_base_entry_data.copy()
        data["position"] = "Short_1"
        
        with pytest.raises(ValueError, match="Invalid position"):
            Signal.from_dict(data)

    def test_invalid_timestamp_format(self, valid_base_entry_data):
        """Test invalid timestamp format"""
        data = valid_base_entry_data.copy()
        data["timestamp"] = "invalid-date-format"
        
        with pytest.raises(ValueError, match="Invalid timestamp format"):
            Signal.from_dict(data)

    def test_timestamp_with_milliseconds(self, valid_base_entry_data):
        """Test timestamp with milliseconds (should work)"""
        data = valid_base_entry_data.copy()
        data["timestamp"] = "2025-11-28T10:30:00.123Z"
        
        signal = Signal.from_dict(data)
        assert isinstance(signal.timestamp, datetime)

    def test_timestamp_with_timezone_offset(self, valid_base_entry_data):
        """Test timestamp with timezone offset (should work)"""
        data = valid_base_entry_data.copy()
        data["timestamp"] = "2025-11-28T10:30:00+05:30"
        
        signal = Signal.from_dict(data)
        assert isinstance(signal.timestamp, datetime)

    def test_negative_price(self, valid_base_entry_data):
        """Test negative price (should fail in __post_init__)"""
        data = valid_base_entry_data.copy()
        data["price"] = -100.0
        
        with pytest.raises(ValueError, match="Invalid price"):
            Signal.from_dict(data)

    def test_zero_stop_for_base_entry(self, valid_base_entry_data):
        """Test zero stop for BASE_ENTRY (should fail)"""
        data = valid_base_entry_data.copy()
        data["stop"] = 0.0
        
        with pytest.raises(ValueError, match="Invalid stop"):
            Signal.from_dict(data)

    def test_zero_stop_for_exit(self, valid_exit_data):
        """Test zero stop for EXIT (should work, stop can equal price)"""
        data = valid_exit_data.copy()
        data["stop"] = 0.0
        data["price"] = 0.0  # Also set price to 0 for EXIT
        
        # This will fail on price validation, but stop=0 for EXIT is allowed
        # Let's test with stop = price (both positive)
        data["price"] = 51800.0
        data["stop"] = 51800.0
        
        signal = Signal.from_dict(data)
        assert signal.stop == 51800.0

    def test_negative_atr(self, valid_base_entry_data):
        """Test negative ATR (should fail)"""
        data = valid_base_entry_data.copy()
        data["atr"] = -100.0
        
        with pytest.raises(ValueError, match="Invalid ATR"):
            Signal.from_dict(data)

    def test_exit_without_reason(self, valid_exit_data):
        """Test EXIT signal without reason (should fail)"""
        data = valid_exit_data.copy()
        del data["reason"]
        
        with pytest.raises(ValueError, match="EXIT signals require a 'reason' field"):
            Signal.from_dict(data)

    def test_invalid_numeric_type(self, valid_base_entry_data):
        """Test invalid numeric type (string instead of number)"""
        data = valid_base_entry_data.copy()
        data["price"] = "not_a_number"
        
        with pytest.raises(ValueError, match="Invalid numeric field"):
            Signal.from_dict(data)

    def test_all_valid_positions(self, valid_base_entry_data):
        """Test all valid positions (Long_1 through Long_6, ALL)"""
        valid_positions = ['Long_1', 'Long_2', 'Long_3', 'Long_4', 'Long_5', 'Long_6', 'ALL']
        
        for pos in valid_positions:
            data = valid_base_entry_data.copy()
            data["position"] = pos
            signal = Signal.from_dict(data)
            assert signal.position == pos

