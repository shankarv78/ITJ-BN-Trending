"""
Unit tests for Tom Basso Position Sizer

Tests the 3-constraint position sizing logic:
- Lot-R (Risk-based)
- Lot-V (Volatility-based)
- Lot-M (Margin-based)
"""
import pytest
from datetime import datetime
from core.position_sizer import TomBassoPositionSizer
from core.models import Signal, SignalType, InstrumentConfig, InstrumentType
from core.config import get_instrument_config

@pytest.fixture
def bank_nifty_config():
    """Bank Nifty configuration fixture"""
    return get_instrument_config(InstrumentType.BANK_NIFTY)

@pytest.fixture
def gold_config():
    """Gold Mini configuration fixture"""
    return get_instrument_config(InstrumentType.GOLD_MINI)

@pytest.fixture
def base_entry_signal_bn():
    """Sample Bank Nifty base entry signal"""
    return Signal(
        timestamp=datetime(2025, 11, 15, 10, 30),
        instrument="BANK_NIFTY",
        signal_type=SignalType.BASE_ENTRY,
        position="Long_1",
        price=52000.0,
        stop=51650.0,
        suggested_lots=12,
        atr=350.0,
        er=0.82,
        supertrend=51650.0
    )

@pytest.fixture
def base_entry_signal_gold():
    """Sample Gold Mini base entry signal"""
    return Signal(
        timestamp=datetime(2025, 11, 15, 10, 30),
        instrument="GOLD_MINI",
        signal_type=SignalType.BASE_ENTRY,
        position="Long_1",
        price=78500.0,
        stop=77800.0,
        suggested_lots=5,
        atr=450.0,
        er=0.85,
        supertrend=77800.0
    )

class TestTomBassoPositionSizer:
    """Test suite for position sizer"""

    def test_initialization(self, bank_nifty_config):
        """Test sizer initialization with config"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        assert sizer.lot_size == 35
        assert sizer.point_value == 35.0
        assert sizer.margin_per_lot == 270000.0

    def test_risk_based_lots_calculation(self, bank_nifty_config, base_entry_signal_bn):
        """Test Lot-R (risk-based) calculation"""
        sizer = TomBassoPositionSizer(bank_nifty_config)
        equity = 5000000.0  # Rs 50 lakhs

        # Expected calculation:
        # Risk% = 0.5% (initial risk)
        # Risk amount = 5000000 × 0.005 = 25,000
        # Risk per point = 52000 - 51650 = 350 points
        # Risk per lot = 350 × 35 = 12,250
        # Lot-R = (25000 / 12250) × 0.82 (ER) = 1.673 lots

        result = sizer.calculate_base_entry_size(
            base_entry_signal_bn,
            equity=equity,
            available_margin=3000000.0
        )

        assert result.lot_r == pytest.approx(1.673, rel=0.01)

    def test_volatility_based_lots_calculation(self, bank_nifty_config, base_entry_signal_bn):
        """Test Lot-V (volatility-based) calculation"""
        sizer = TomBassoPositionSizer(bank_nifty_config)
        equity = 5000000.0

        # Expected calculation (Bank Nifty config: initial_vol_percent = 0.5%):
        # Vol% = 0.5% (initial volatility for Bank Nifty)
        # Vol budget = 5000000 × 0.005 = 25,000
        # ATR = 350 points
        # Vol per lot = 350 × 35 = 12,250
        # Lot-V = 25000 / 12250 = 2.04 lots

        result = sizer.calculate_base_entry_size(
            base_entry_signal_bn,
            equity=equity,
            available_margin=3000000.0
        )

        assert result.lot_v == pytest.approx(2.04, rel=0.01)

    def test_margin_based_lots_calculation(self, bank_nifty_config, base_entry_signal_bn):
        """Test Lot-M (margin-based) calculation"""
        sizer = TomBassoPositionSizer(bank_nifty_config)
        available_margin = 540000.0  # Rs 5.4L

        # Expected calculation:
        # Margin per lot = 270,000
        # Lot-M = 540000 / 270000 = 2 lots

        result = sizer.calculate_base_entry_size(
            base_entry_signal_bn,
            equity=5000000.0,
            available_margin=available_margin
        )

        assert result.lot_m == pytest.approx(2.0, rel=0.01)

    def test_final_lots_takes_minimum(self, bank_nifty_config, base_entry_signal_bn):
        """Test that final lots = FLOOR(MIN(Lot-R, Lot-V, Lot-M))"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        # With Bank Nifty config (risk%=0.5%, vol%=0.5%):
        # Lot-R = (5M × 0.005) / (350 × 35) × 0.82 = 1.67 lots
        # Lot-V = (5M × 0.005) / (350 × 35) = 2.04 lots
        # Lot-M = 3M / 270k = 11.11 lots
        # MIN = 1.67 → FLOOR = 1 lot (risk limited)

        result = sizer.calculate_base_entry_size(
            base_entry_signal_bn,
            equity=5000000.0,
            available_margin=3000000.0
        )

        assert result.final_lots == 1  # Risk constraint is the limiter
        assert result.limiter == "risk"

    def test_limiter_identification(self, bank_nifty_config):
        """Test that limiter is correctly identified"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        # Scenario 1: Risk limited (tight stop, high ATR)
        signal1 = Signal(
            timestamp=datetime(2025, 11, 15),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=52000.0,
            stop=51900.0,  # Tight stop (100 points)
            suggested_lots=10,
            atr=200.0,  # Low ATR
            er=0.8,
            supertrend=51900.0
        )

        result1 = sizer.calculate_base_entry_size(signal1, 5000000.0, 3000000.0)
        # Lot-R will be smallest due to tight stop

        # Scenario 2: Margin limited (low available margin)
        signal2 = Signal(
            timestamp=datetime(2025, 11, 15),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=52000.0,
            stop=51650.0,
            suggested_lots=10,
            atr=350.0,
            er=0.8,
            supertrend=51650.0
        )
        result2 = sizer.calculate_base_entry_size(
            signal2,
            equity=5000000.0,
            available_margin=100000.0  # Only Rs 1L available
        )

        assert result2.final_lots == 0  # Not even 1 lot affordable
        assert result2.limiter == "margin"

    def test_zero_lots_when_invalid_risk(self, bank_nifty_config):
        """Test returns 0 lots when stop above entry (invalid)"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        bad_signal = Signal(
            timestamp=datetime(2025, 11, 15),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=52000.0,
            stop=52100.0,  # Stop ABOVE entry (invalid!)
            suggested_lots=10,
            atr=350.0,
            er=0.8,
            supertrend=52100.0
        )

        result = sizer.calculate_base_entry_size(bad_signal, 5000000.0, 3000000.0)

        assert result.final_lots == 0
        assert result.limiter == "invalid_risk"

    def test_gold_position_sizing(self, gold_config, base_entry_signal_gold):
        """Test position sizing for Gold Mini"""
        sizer = TomBassoPositionSizer(gold_config)
        equity = 5000000.0

        # Expected for Gold:
        # Lot-R: (5M × 0.5%) / (700 × 10) × 0.85 = 3.04 lots
        # Lot-V: (5M × 0.2%) / (450 × 10) = 2.22 lots
        # Lot-M: 3000000 / 105000 = 28.57 lots
        # MIN = 2.22 → FLOOR = 2 lots (volatility limited)

        result = sizer.calculate_base_entry_size(
            base_entry_signal_gold,
            equity=equity,
            available_margin=3000000.0
        )

        assert result.final_lots == 2
        assert result.limiter == "volatility"

    def test_pyramid_constraints_abc(self, bank_nifty_config):
        """Test pyramid triple constraint (A, B, C)"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        pyramid_signal = Signal(
            timestamp=datetime(2025, 11, 16),
            instrument="BANK_NIFTY",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=52500.0,
            stop=52000.0,
            suggested_lots=6,
            atr=370.0,
            er=0.85,
            supertrend=52000.0
        )

        result = sizer.calculate_pyramid_size(
            pyramid_signal,
            equity=5200000.0,
            available_margin=1000000.0,  # Rs 10L available
            base_position_size=10,  # Base entry was 10 lots
            profit_after_base_risk=150000.0  # Rs 1.5L profit beyond base risk
        )

        # Lot-A (margin): 1000000 / 270000 = 3.7 → 3 lots
        # Lot-B (50% rule): 10 × 0.5 = 5 lots
        # Lot-C (risk budget): (150000 × 0.5) / (500 × 35) = 4.28 lots
        # MIN = 3 lots (margin limited)

        assert result.final_lots == 3
        assert result.limiter == "margin"

    def test_peel_off_calculation(self, bank_nifty_config):
        """Test peel-off lots calculation when position too large"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        equity = 5000000.0
        current_lots = 10

        # Bank Nifty config: ongoing_risk_percent=1.0%, ongoing_vol_percent=0.7%
        #
        # Position risk = 400 × 10 × 35 = Rs 140,000 = 2.8% (exceeds 1.0% ongoing)
        # Risk peel: target=50k (1% of 5M), excess=90k, peel=CEIL(90k/14k) = 7 lots
        #
        # Position vol = 300 × 10 × 35 = Rs 105,000 = 2.1% (exceeds 0.7% ongoing)
        # Vol peel: target=35k (0.7% of 5M), excess=70k, peel=CEIL(70k/10.5k) = 7 lots
        #
        # Final = MAX(7, 7) = 7 lots

        position_risk = 400 * 10 * 35  # Rs 140,000
        position_vol = 300 * 10 * 35  # Rs 105,000

        lots_to_peel, reason = sizer.calculate_peel_off_size(
            position_risk=position_risk,
            position_vol=position_vol,
            equity=equity,
            current_lots=current_lots
        )

        assert lots_to_peel == 7  # Both risk and vol require 7 lots peel-off
        assert "risk" in reason or "vol" in reason

    def test_no_peel_off_when_within_limits(self, bank_nifty_config):
        """Test no peel-off when position within ongoing limits"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        equity = 5000000.0
        current_lots = 2  # Smaller position

        # Position risk = 100 × 2 × 35 = Rs 7,000 = 0.14% (under 1% limit) ✓
        # Position vol = 50 × 2 × 35 = Rs 3,500 = 0.07% (under 0.3% limit) ✓
        # Both under limits → no peel-off

        position_risk = 100 * 2 * 35  # Rs 7,000
        position_vol = 50 * 2 * 35    # Rs 3,500

        lots_to_peel, reason = sizer.calculate_peel_off_size(
            position_risk=position_risk,
            position_vol=position_vol,
            equity=equity,
            current_lots=current_lots
        )

        assert lots_to_peel == 0
        assert reason == ""

    def test_efficiency_ratio_multiplier_effect(self, bank_nifty_config):
        """Test that ER multiplier affects risk-based sizing"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        # Signal with high ER
        signal_high_er = Signal(
            timestamp=datetime(2025, 11, 15),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=52000.0,
            stop=51650.0,
            suggested_lots=10,
            atr=350.0,
            er=0.90,  # High efficiency
            supertrend=51650.0
        )

        # Signal with low ER
        signal_low_er = Signal(
            timestamp=datetime(2025, 11, 15),
            instrument="BANK_NIFTY",
            signal_type=SignalType.BASE_ENTRY,
            position="Long_1",
            price=52000.0,
            stop=51650.0,
            suggested_lots=10,
            atr=350.0,
            er=0.50,  # Low efficiency
            supertrend=51650.0
        )

        result_high = sizer.calculate_base_entry_size(signal_high_er, 5000000.0, 3000000.0)
        result_low = sizer.calculate_base_entry_size(signal_low_er, 5000000.0, 3000000.0)

        # Lot-R should be higher with higher ER
        assert result_high.lot_r > result_low.lot_r

    def test_pyramid_50_percent_rule(self, bank_nifty_config):
        """Test pyramid 50% rule (Lot-B)"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        pyramid_signal = Signal(
            timestamp=datetime(2025, 11, 16),
            instrument="BANK_NIFTY",
            signal_type=SignalType.PYRAMID,
            position="Long_2",
            price=52500.0,
            stop=52000.0,
            suggested_lots=5,
            atr=360.0,
            er=0.85,
            supertrend=52000.0
        )

        # Base was 10 lots
        # Lot-B = 10 × 0.5 = 5 lots

        result = sizer.calculate_pyramid_size(
            pyramid_signal,
            equity=5200000.0,
            available_margin=2000000.0,  # Plenty of margin
            base_position_size=10,
            profit_after_base_risk=500000.0  # Plenty of profit
        )

        # Lot-A (margin): 2M / 270k = 7.4 lots
        # Lot-B (50%): 10 × 0.5 = 5 lots ← Should limit
        # Lot-C (risk): (500k × 0.5) / (500 × 35) = 14.28 lots

        assert result.lot_v == 5.0  # Lot-B constraint
        assert result.final_lots == 5
        assert result.limiter == "50%_rule"

    def test_edge_case_zero_available_margin(self, bank_nifty_config, base_entry_signal_bn):
        """Test edge case: zero available margin"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        result = sizer.calculate_base_entry_size(
            base_entry_signal_bn,
            equity=5000000.0,
            available_margin=0.0  # No margin!
        )

        assert result.final_lots == 0
        assert result.limiter == "margin"

    def test_edge_case_zero_equity(self, bank_nifty_config, base_entry_signal_bn):
        """Test edge case: zero equity (account blown up)"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        result = sizer.calculate_base_entry_size(
            base_entry_signal_bn,
            equity=0.0,
            available_margin=100000.0
        )

        # With zero equity, Lot-R and Lot-V should be 0
        assert result.lot_r == 0.0
        assert result.lot_v == 0.0
        assert result.final_lots == 0

    def test_different_instruments_different_parameters(self, bank_nifty_config, gold_config):
        """Test that different instruments use different parameters"""
        bn_sizer = TomBassoPositionSizer(bank_nifty_config)
        gold_sizer = TomBassoPositionSizer(gold_config)

        # Bank Nifty: point_value = 35, margin = 270k
        assert bn_sizer.point_value == 35.0
        assert bn_sizer.margin_per_lot == 270000.0

        # Gold: point_value = 10, margin = 105k
        assert gold_sizer.point_value == 10.0
        assert gold_sizer.margin_per_lot == 105000.0

    def test_peel_off_volatility_trigger(self, bank_nifty_config):
        """Test peel-off triggered by volatility limit"""
        sizer = TomBassoPositionSizer(bank_nifty_config)

        equity = 5000000.0
        current_lots = 20

        # High volatility: ATR = 500, 20 lots
        # Position vol = 500 × 20 × 35 = Rs 350,000 = 7.0% (exceeds 3% limit)
        position_risk = 200 * 20 * 35  # Rs 140,000 (2.8%, under limit)
        position_vol = 500 * 20 * 35  # Rs 350,000 (7.0%, over limit!)

        lots_to_peel, reason = sizer.calculate_peel_off_size(
            position_risk=position_risk,
            position_vol=position_vol,
            equity=equity,
            current_lots=current_lots
        )

        assert lots_to_peel > 0
        assert "vol" in reason

@pytest.mark.parametrize("equity,expected_lots", [
    # Bank Nifty config: risk%=0.5%, vol%=0.5%
    # Signal: price=52000, stop=51650 (350 pts), ATR=350, ER=0.82
    # Lot-R = (equity × 0.005) / (350 × 35) × 0.82
    # Lot-V = (equity × 0.005) / (350 × 35)
    (1000000, 0),   # 10L: Lot-R=0.33, Lot-V=0.41 → 0 lots
    (5000000, 1),   # 50L: Lot-R=1.67, Lot-V=2.04 → 1 lot (risk limited)
    (10000000, 3),  # 1Cr: Lot-R=3.35, Lot-V=4.08 → 3 lots (risk limited)
])
def test_position_sizing_at_different_equity_levels(equity, expected_lots, bank_nifty_config, base_entry_signal_bn):
    """Parametrized test: position sizing at various equity levels"""
    sizer = TomBassoPositionSizer(bank_nifty_config)

    result = sizer.calculate_base_entry_size(
        base_entry_signal_bn,
        equity=equity,
        available_margin=equity * 0.6  # 60% available as margin
    )

    assert result.final_lots == expected_lots
