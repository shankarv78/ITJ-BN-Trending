"""
Shared fixtures for integration tests
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import date


def create_mock_translated_symbol(instrument: str, action: str = "BUY"):
    """
    Create a mock TranslatedSymbol with proper order_legs for testing.

    Bank Nifty uses synthetic futures (2 legs: PE + CE)
    Gold Mini uses simple futures (1 leg)
    """
    from core.symbol_mapper import TranslatedSymbol, OrderLeg

    if instrument == "BANK_NIFTY":
        # Synthetic futures: PE SELL + CE BUY for entry
        pe_action = "SELL" if action == "BUY" else "BUY"
        ce_action = "BUY" if action == "BUY" else "SELL"

        return TranslatedSymbol(
            instrument=instrument,
            exchange="NFO",
            symbols=["BANKNIFTY30DEC25PE", "BANKNIFTY30DEC25CE"],
            expiry_date=date(2025, 12, 30),
            is_synthetic=True,
            atm_strike=52000,
            order_legs=[
                OrderLeg(symbol="BANKNIFTY30DEC25PE", exchange="NFO", action=pe_action, leg_type="PE"),
                OrderLeg(symbol="BANKNIFTY30DEC25CE", exchange="NFO", action=ce_action, leg_type="CE"),
            ]
        )
    else:  # GOLD_MINI
        return TranslatedSymbol(
            instrument=instrument,
            exchange="MCX",
            symbols=["GOLDM05JAN26FUT"],
            expiry_date=date(2026, 1, 5),
            is_synthetic=False,
            atm_strike=None,
            order_legs=[
                OrderLeg(symbol="GOLDM05JAN26FUT", exchange="MCX", action=action, leg_type="FUT"),
            ]
        )


@pytest.fixture(autouse=True)
def mock_symbol_mapper():
    """
    Mock the symbol_mapper module to prevent SyntheticFuturesExecutor initialization issues.

    This is required because LiveTradingEngine tries to get_symbol_mapper() on init,
    and without init_symbol_mapper() being called first in production startup,
    it returns None causing Bank Nifty trades to fail.

    This fixture is autouse=True so it applies to all integration tests automatically.
    """
    mock_mapper = MagicMock()

    # Mock translate() to return proper TranslatedSymbol with order_legs
    def mock_translate(instrument, action="BUY", current_price=None, reference_date=None):
        return create_mock_translated_symbol(instrument, action)

    mock_mapper.translate.side_effect = mock_translate
    mock_mapper.get_lot_size.return_value = 35  # Bank Nifty lot size
    mock_mapper.get_bank_nifty_synthetic_symbols.return_value = ("BANKNIFTY30DEC25PE", "BANKNIFTY30DEC25CE")
    mock_mapper.get_gold_mini_symbol.return_value = "GOLDM05JAN26FUT"

    with patch('core.symbol_mapper.get_symbol_mapper', return_value=mock_mapper):
        yield mock_mapper
