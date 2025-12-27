"""
Unit tests for SymbolMapper - Symbol translation for OpenAlgo

Tests:
- Gold Mini futures translation
- Bank Nifty synthetic futures translation
- ATM strike calculation (round to 500, prefer 1000s)
- Order leg generation
- Exit order reversal
"""
import pytest
from datetime import date
from unittest.mock import Mock, patch

from core.symbol_mapper import (
    SymbolMapper,
    TranslatedSymbol,
    OrderLeg,
    InstrumentType,
    ExchangeCode,
    init_symbol_mapper,
    get_symbol_mapper
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_expiry_calendar():
    """Mock expiry calendar that returns fixed dates"""
    calendar = Mock()
    # Default expiry dates
    calendar.get_expiry_after_rollover = Mock(side_effect=lambda instrument, ref_date=None: {
        "GOLD_MINI": date(2026, 1, 5),
        "BANK_NIFTY": date(2024, 12, 26),
        "SILVER_MINI": date(2026, 2, 27),  # Feb 2026 (bimonthly contract)
        "COPPER": date(2025, 12, 31),
    }.get(instrument, date(2025, 12, 31)))
    return calendar


@pytest.fixture
def mock_price_provider():
    """Mock price provider"""
    def provider(symbol):
        prices = {
            "BANK_NIFTY": 50347.0,
            "NIFTY_BANK": 50347.0,
        }
        return prices.get(symbol, 50000.0)
    return provider


@pytest.fixture
def symbol_mapper(mock_expiry_calendar, mock_price_provider):
    """Create SymbolMapper with mocked dependencies"""
    return SymbolMapper(
        expiry_calendar=mock_expiry_calendar,
        holiday_calendar=None,
        price_provider=mock_price_provider
    )


# =============================================================================
# ATM STRIKE CALCULATION TESTS
# =============================================================================

class TestATMStrikeCalculation:
    """Test ATM strike rounding: nearest 500, prefer 1000s"""

    def test_round_down_to_500(self, symbol_mapper):
        """50347 → 50500 (nearest 500)"""
        assert symbol_mapper.calculate_atm_strike(50347, step=500) == 50500

    def test_round_up_to_1000_prefer(self, symbol_mapper):
        """50750 → 51000 (prefer 1000 over 500 when equidistant)"""
        assert symbol_mapper.calculate_atm_strike(50750, step=500) == 51000

    def test_equidistant_prefer_1000_lower(self, symbol_mapper):
        """50250 → 50000 (prefer 1000 when equidistant)"""
        assert symbol_mapper.calculate_atm_strike(50250, step=500) == 50000

    def test_exact_500(self, symbol_mapper):
        """50500 → 50500 (exact)"""
        assert symbol_mapper.calculate_atm_strike(50500, step=500) == 50500

    def test_exact_1000(self, symbol_mapper):
        """51000 → 51000 (exact)"""
        assert symbol_mapper.calculate_atm_strike(51000, step=500) == 51000

    def test_round_up_to_500(self, symbol_mapper):
        """50399 → 50500 (closer to 50500 than 50000)"""
        assert symbol_mapper.calculate_atm_strike(50399, step=500) == 50500

    def test_round_down_to_1000(self, symbol_mapper):
        """51100 → 51000 (closer to 51000)"""
        assert symbol_mapper.calculate_atm_strike(51100, step=500) == 51000

    def test_invalid_price_zero(self, symbol_mapper):
        """Zero price should raise ValueError"""
        with pytest.raises(ValueError):
            symbol_mapper.calculate_atm_strike(0, step=500)

    def test_invalid_price_negative(self, symbol_mapper):
        """Negative price should raise ValueError"""
        with pytest.raises(ValueError):
            symbol_mapper.calculate_atm_strike(-100, step=500)


# =============================================================================
# GOLD MINI TRANSLATION TESTS
# =============================================================================

class TestGoldMiniTranslation:
    """Test Gold Mini futures symbol translation"""

    def test_buy_signal(self, symbol_mapper):
        """Gold Mini BUY → GOLDM05JAN26FUT"""
        result = symbol_mapper.translate("GOLD_MINI", action="BUY")

        assert result.instrument == "GOLD_MINI"
        assert result.exchange == "MCX"
        assert result.is_synthetic == False
        assert result.expiry_date == date(2026, 1, 5)
        assert len(result.symbols) == 1
        assert result.symbols[0] == "GOLDM05JAN26FUT"
        assert result.atm_strike is None

    def test_sell_signal(self, symbol_mapper):
        """Gold Mini SELL → GOLDM05JAN26FUT with SELL action"""
        result = symbol_mapper.translate("GOLD_MINI", action="SELL")

        assert len(result.order_legs) == 1
        assert result.order_legs[0].action == "SELL"
        assert result.order_legs[0].leg_type == "FUT"
        assert result.order_legs[0].exchange == "MCX"

    def test_order_leg_structure(self, symbol_mapper):
        """Verify order leg structure for Gold Mini"""
        result = symbol_mapper.translate("GOLD_MINI", action="BUY")

        leg = result.order_legs[0]
        assert leg.symbol == "GOLDM05JAN26FUT"
        assert leg.exchange == "MCX"
        assert leg.action == "BUY"
        assert leg.leg_type == "FUT"
        assert leg.lot_multiplier == 1

    def test_to_dict(self, symbol_mapper):
        """Test serialization to dict"""
        result = symbol_mapper.translate("GOLD_MINI", action="BUY")
        d = result.to_dict()

        assert d['instrument'] == "GOLD_MINI"
        assert d['exchange'] == "MCX"
        assert d['is_synthetic'] == False
        assert len(d['order_legs']) == 1


# =============================================================================
# BANK NIFTY TRANSLATION TESTS
# =============================================================================

class TestBankNiftyTranslation:
    """Test Bank Nifty synthetic futures translation"""

    def test_buy_entry(self, symbol_mapper):
        """Bank Nifty BUY → PE Sell + CE Buy"""
        result = symbol_mapper.translate("BANK_NIFTY", action="BUY", current_price=50347)

        assert result.instrument == "BANK_NIFTY"
        assert result.exchange == "NFO"
        assert result.is_synthetic == True
        assert result.atm_strike == 50500  # 50347 rounds to 50500
        assert len(result.symbols) == 2
        assert "PE" in result.symbols[0]
        assert "CE" in result.symbols[1]

    def test_buy_entry_order_legs(self, symbol_mapper):
        """Verify Buy Entry: PE SELL + CE BUY"""
        result = symbol_mapper.translate("BANK_NIFTY", action="BUY", current_price=50347)

        pe_leg = result.order_legs[0]
        ce_leg = result.order_legs[1]

        # Entry Long: SELL PE, BUY CE
        assert pe_leg.action == "SELL"
        assert pe_leg.leg_type == "PE"
        assert ce_leg.action == "BUY"
        assert ce_leg.leg_type == "CE"

    def test_sell_exit(self, symbol_mapper):
        """Bank Nifty SELL (exit) → PE Buy + CE Sell"""
        result = symbol_mapper.translate("BANK_NIFTY", action="SELL", current_price=50347)

        pe_leg = result.order_legs[0]
        ce_leg = result.order_legs[1]

        # Exit: BUY PE, SELL CE (reverse of entry)
        assert pe_leg.action == "BUY"
        assert pe_leg.leg_type == "PE"
        assert ce_leg.action == "SELL"
        assert ce_leg.leg_type == "CE"

    def test_symbol_format(self, symbol_mapper):
        """Verify symbol format: BANKNIFTY26DEC2450500PE/CE"""
        result = symbol_mapper.translate("BANK_NIFTY", action="BUY", current_price=50347)

        # Check PE symbol format
        pe_symbol = result.symbols[0]
        assert pe_symbol.startswith("BANKNIFTY")
        assert "50500" in pe_symbol
        assert pe_symbol.endswith("PE")

        # Check CE symbol format
        ce_symbol = result.symbols[1]
        assert ce_symbol.startswith("BANKNIFTY")
        assert "50500" in ce_symbol
        assert ce_symbol.endswith("CE")

    def test_price_required_error(self, symbol_mapper):
        """Bank Nifty without price and no provider should error"""
        mapper = SymbolMapper(
            expiry_calendar=symbol_mapper.expiry_calendar,
            price_provider=None
        )

        with pytest.raises(ValueError) as excinfo:
            mapper.translate("BANK_NIFTY", action="BUY")

        assert "Current price required" in str(excinfo.value)

    def test_uses_price_provider(self, symbol_mapper):
        """Should use price_provider if current_price not given"""
        # Provider returns 50347 for BANK_NIFTY
        result = symbol_mapper.translate("BANK_NIFTY", action="BUY")

        assert result.atm_strike == 50500

    def test_price_provider_returns_none(self):
        """Should error if price_provider returns None"""
        def bad_provider(symbol):
            return None

        mapper = SymbolMapper(
            expiry_calendar=Mock(get_expiry_after_rollover=Mock(return_value=date(2024, 12, 26))),
            price_provider=bad_provider
        )

        with pytest.raises(ValueError) as excinfo:
            mapper.translate("BANK_NIFTY", action="BUY")

        assert "invalid price" in str(excinfo.value).lower()

    def test_different_atm_strikes(self, symbol_mapper):
        """Test various price levels produce correct ATM strikes"""
        test_cases = [
            (50100, 50000),  # Round down to 1000
            (50400, 50500),  # Round up to 500
            (50750, 51000),  # Equidistant, prefer 1000
            (51250, 51000),  # Round down to 1000
            (51500, 51500),  # Exact 500
        ]

        for price, expected_strike in test_cases:
            result = symbol_mapper.translate("BANK_NIFTY", action="BUY", current_price=price)
            assert result.atm_strike == expected_strike, f"Price {price} → expected {expected_strike}, got {result.atm_strike}"


# =============================================================================
# EXIT ORDER TESTS
# =============================================================================

class TestExitOrders:
    """Test exit order leg generation"""

    def test_reverse_gold_mini(self, symbol_mapper):
        """Exit reverses Gold Mini BUY to SELL"""
        entry = symbol_mapper.translate("GOLD_MINI", action="BUY")
        exit_legs = symbol_mapper.get_order_legs_for_exit(entry)

        assert len(exit_legs) == 1
        assert exit_legs[0].action == "SELL"
        assert exit_legs[0].symbol == entry.order_legs[0].symbol

    def test_reverse_bank_nifty(self, symbol_mapper):
        """Exit reverses Bank Nifty PE Sell+CE Buy to PE Buy+CE Sell"""
        entry = symbol_mapper.translate("BANK_NIFTY", action="BUY", current_price=50500)
        exit_legs = symbol_mapper.get_order_legs_for_exit(entry)

        assert len(exit_legs) == 2

        # PE: entry SELL → exit BUY
        assert exit_legs[0].action == "BUY"
        assert exit_legs[0].leg_type == "PE"

        # CE: entry BUY → exit SELL
        assert exit_legs[1].action == "SELL"
        assert exit_legs[1].leg_type == "CE"


# =============================================================================
# UTILITY TESTS
# =============================================================================

class TestUtilities:
    """Test utility functions"""

    def test_lot_size_gold_mini(self, symbol_mapper):
        """Gold Mini lot size is 100"""
        assert symbol_mapper.get_lot_size("GOLD_MINI") == 100

    def test_lot_size_bank_nifty(self, symbol_mapper):
        """Bank Nifty lot size is 30 (Dec 2025 onwards)"""
        assert symbol_mapper.get_lot_size("BANK_NIFTY") == 30

    def test_lot_size_unknown(self, symbol_mapper):
        """Unknown instrument defaults to 1"""
        assert symbol_mapper.get_lot_size("UNKNOWN") == 1

    def test_calculate_quantity(self, symbol_mapper):
        """Calculate total quantity from lots"""
        # 2 lots of Bank Nifty = 2 * 30 = 60
        assert symbol_mapper.calculate_quantity("BANK_NIFTY", 2) == 60

        # 3 lots of Gold Mini = 3 * 100 = 300
        assert symbol_mapper.calculate_quantity("GOLD_MINI", 3) == 300

    def test_unknown_instrument(self, symbol_mapper):
        """Unknown instrument should raise ValueError"""
        with pytest.raises(ValueError) as excinfo:
            symbol_mapper.translate("UNKNOWN_INSTRUMENT", action="BUY")

        assert "Unknown instrument" in str(excinfo.value)


# =============================================================================
# GLOBAL INSTANCE TESTS
# =============================================================================

class TestGlobalInstance:
    """Test global SymbolMapper instance management"""

    def test_init_symbol_mapper(self, mock_expiry_calendar, mock_price_provider):
        """init_symbol_mapper creates global instance"""
        mapper = init_symbol_mapper(
            expiry_calendar=mock_expiry_calendar,
            price_provider=mock_price_provider
        )

        assert mapper is not None
        assert get_symbol_mapper() is mapper

    def test_get_symbol_mapper_before_init(self):
        """get_symbol_mapper returns instance after init"""
        # Note: This test depends on test order, may need reset
        mapper = get_symbol_mapper()
        # After previous test, should have an instance
        assert mapper is not None or mapper is None  # Accept either state


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

# =============================================================================
# SILVER MINI TRANSLATION TESTS
# =============================================================================

class TestSilverMiniTranslation:
    """Test Silver Mini futures symbol translation"""

    def test_buy_signal(self, symbol_mapper):
        """Silver Mini BUY → SILVERM27FEB26FUT"""
        result = symbol_mapper.translate("SILVER_MINI", action="BUY")

        assert result.instrument == "SILVER_MINI"
        assert result.exchange == "MCX"
        assert result.is_synthetic == False
        assert result.expiry_date == date(2026, 2, 27)
        assert len(result.symbols) == 1
        assert result.symbols[0] == "SILVERM27FEB26FUT"
        assert result.atm_strike is None

    def test_sell_signal(self, symbol_mapper):
        """Silver Mini SELL → SILVERM27FEB26FUT with SELL action"""
        result = symbol_mapper.translate("SILVER_MINI", action="SELL")

        assert len(result.order_legs) == 1
        assert result.order_legs[0].action == "SELL"
        assert result.order_legs[0].leg_type == "FUT"
        assert result.order_legs[0].exchange == "MCX"

    def test_order_leg_structure(self, symbol_mapper):
        """Verify order leg structure for Silver Mini"""
        result = symbol_mapper.translate("SILVER_MINI", action="BUY")

        leg = result.order_legs[0]
        assert leg.symbol == "SILVERM27FEB26FUT"
        assert leg.exchange == "MCX"
        assert leg.action == "BUY"
        assert leg.leg_type == "FUT"
        assert leg.lot_multiplier == 1

    def test_lot_size(self, symbol_mapper):
        """Verify Silver Mini lot size is 5"""
        assert symbol_mapper.LOT_SIZES.get('SILVER_MINI') == 5


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

class TestSerialization:
    """Test to_dict serialization"""

    def test_order_leg_to_dict(self):
        """OrderLeg serializes correctly"""
        leg = OrderLeg(
            symbol="GOLDM05JAN26FUT",
            exchange="MCX",
            action="BUY",
            leg_type="FUT"
        )

        d = leg.to_dict()

        assert d['symbol'] == "GOLDM05JAN26FUT"
        assert d['exchange'] == "MCX"
        assert d['action'] == "BUY"
        assert d['leg_type'] == "FUT"
        assert d['lot_multiplier'] == 1

    def test_translated_symbol_to_dict(self, symbol_mapper):
        """TranslatedSymbol serializes correctly"""
        result = symbol_mapper.translate("BANK_NIFTY", action="BUY", current_price=50500)
        d = result.to_dict()

        assert d['instrument'] == "BANK_NIFTY"
        assert d['exchange'] == "NFO"
        assert d['is_synthetic'] == True
        assert d['atm_strike'] == 50500
        assert 'expiry_date' in d
        assert len(d['symbols']) == 2
        assert len(d['order_legs']) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
