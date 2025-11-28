"""
Unit tests for Tom Basso Stop Manager

Tests independent ATR trailing stops:
- Initial stop calculation
- Trailing stop updates (ratchet up only)
- Stop hit detection
"""
import pytest
from datetime import datetime
from core.stop_manager import TomBassoStopManager
from core.models import Position, InstrumentType

@pytest.fixture
def stop_manager():
    """Create stop manager instance"""
    return TomBassoStopManager()

@pytest.fixture
def gold_position():
    """Sample Gold position"""
    return Position(
        position_id="Gold_Long_1",
        instrument="GOLD_MINI",
        entry_timestamp=datetime(2025, 11, 15),
        entry_price=78500.0,
        lots=3,
        quantity=300,
        initial_stop=77800.0,
        current_stop=77800.0,
        highest_close=78500.0,
        status="open"
    )

class TestTomBassoStopManager:
    """Test suite for stop manager"""
    
    def test_initial_stop_calculation_gold(self, stop_manager):
        """Test initial stop for Gold Mini"""
        # Gold: initial_atr_mult = 1.0
        entry = 78500.0
        atr = 700.0
        
        initial_stop = stop_manager.calculate_initial_stop(
            entry, atr, InstrumentType.GOLD_MINI
        )
        
        # Expected: 78500 - (1.0 × 700) = 77800
        assert initial_stop == pytest.approx(77800.0)
    
    def test_initial_stop_calculation_bn(self, stop_manager):
        """Test initial stop for Bank Nifty"""
        # BN: initial_atr_mult = 1.5
        entry = 52000.0
        atr = 400.0
        
        initial_stop = stop_manager.calculate_initial_stop(
            entry, atr, InstrumentType.BANK_NIFTY
        )
        
        # Expected: 52000 - (1.5 × 400) = 51400
        assert initial_stop == pytest.approx(51400.0)
    
    def test_trailing_stop_moves_up_on_price_increase(self, stop_manager, gold_position):
        """Test trailing stop ratchets up when price increases"""
        # Price moves to 79000
        # Highest close becomes 79000
        # Trailing stop = 79000 - (2.0 × 700) = 77600
        # But current stop is 77800, so stop stays at 77800 (doesn't move down)
        
        new_stop = stop_manager.update_trailing_stop(gold_position, 79000.0, 700.0)
        
        # Expected: MAX(77800, 79000 - 1400) = MAX(77800, 77600) = 77800
        assert new_stop == pytest.approx(77800.0)
        assert gold_position.highest_close == 79000.0
    
    def test_trailing_stop_ratchets_up_significantly(self, stop_manager, gold_position):
        """Test stop moves up significantly when price runs"""
        # Price runs to 80000
        # Trailing stop = 80000 - (2.0 × 700) = 78600
        # Current stop: 77800 → 78600 (moves up!)
        
        new_stop = stop_manager.update_trailing_stop(gold_position, 80000.0, 700.0)
        
        assert new_stop == pytest.approx(78600.0)
        assert new_stop > 77800.0  # Stop moved up
        assert gold_position.current_stop == 78600.0
    
    def test_stop_never_moves_down(self, stop_manager, gold_position):
        """Test stop never moves down (ratchet effect)"""
        # Set stop to 78600
        gold_position.current_stop = 78600.0
        gold_position.highest_close = 80000.0
        
        # Price retraces to 79000
        new_stop = stop_manager.update_trailing_stop(gold_position, 79000.0, 700.0)
        
        # Trailing would be: 80000 - 1400 = 78600 (highest close doesn't change)
        # Stop stays at 78600
        assert new_stop == 78600.0
        assert gold_position.current_stop == 78600.0  # Didn't move
    
    def test_stop_hit_detection(self, stop_manager, gold_position):
        """Test stop hit detection"""
        gold_position.current_stop = 78000.0
        
        # Price above stop
        assert stop_manager.check_stop_hit(gold_position, 78200.0) is False
        
        # Price at stop
        assert stop_manager.check_stop_hit(gold_position, 78000.0) is False
        
        # Price below stop
        assert stop_manager.check_stop_hit(gold_position, 77900.0) is True
    
    def test_update_all_stops_for_multiple_positions(self, stop_manager):
        """Test updating stops for multiple positions"""
        positions = {
            "Gold_Long_1": Position(
                position_id="Gold_Long_1",
                instrument="GOLD_MINI",
                entry_timestamp=datetime(2025, 11, 15),
                entry_price=78500.0,
                lots=3,
                quantity=300,
                initial_stop=77800.0,
                current_stop=77800.0,
                highest_close=78500.0,
                status="open"
            ),
            "BN_Long_1": Position(
                position_id="BN_Long_1",
                instrument="BANK_NIFTY",
                entry_timestamp=datetime(2025, 11, 15),
                entry_price=52000.0,
                lots=5,
                quantity=175,
                initial_stop=51400.0,
                current_stop=51400.0,
                highest_close=52000.0,
                status="open"
            )
        }
        
        prices = {"GOLD_MINI": 79500.0, "BANK_NIFTY": 53000.0}
        atrs = {"GOLD_MINI": 700.0, "BANK_NIFTY": 400.0}
        
        stops_hit = stop_manager.update_all_stops(positions, prices, atrs)
        
        # No stops should be hit (prices are up)
        assert len(stops_hit) == 0
        
        # Stops should have moved up
        assert positions["Gold_Long_1"].current_stop > 77800.0
        assert positions["BN_Long_1"].current_stop > 51400.0
    
    def test_stop_hit_detection_multiple_positions(self, stop_manager):
        """Test detecting stop hits across multiple positions"""
        positions = {
            "Gold_Long_1": Position(
                position_id="Gold_Long_1",
                instrument="GOLD_MINI",
                entry_timestamp=datetime(2025, 11, 15),
                entry_price=78500.0,
                lots=3,
                quantity=300,
                initial_stop=77800.0,
                current_stop=78200.0,  # Trailed up
                highest_close=79500.0,
                status="open"
            ),
            "Gold_Long_2": Position(
                position_id="Gold_Long_2",
                instrument="GOLD_MINI",
                entry_timestamp=datetime(2025, 11, 16),
                entry_price=79000.0,
                lots=2,
                quantity=200,
                initial_stop=78300.0,
                current_stop=78800.0,
                highest_close=79500.0,
                status="open"
            )
        }
        
        # Price drops to 78100
        # Long_1 stop: 78200 → price 78100 < 78200 → HIT
        # Long_2 stop: 78800 → price 78100 < 78800 → HIT
        # Both stops should be hit!
        prices = {"GOLD_MINI": 78100.0}
        atrs = {"GOLD_MINI": 700.0}
        
        stops_hit = stop_manager.update_all_stops(positions, prices, atrs)
        
        assert len(stops_hit) == 2  # Both stops hit
        assert "Gold_Long_1" in stops_hit
        assert "Gold_Long_2" in stops_hit

