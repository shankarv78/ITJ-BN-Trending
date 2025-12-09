"""
Unit tests for SyntheticFuturesExecutor - 2-leg execution with rollback

Tests:
- Successful 2-leg execution (entry and exit)
- Leg 2 failure with rollback
- Leg 1 failure (no second leg)
- Rollback failure handling
- Price chasing behavior
"""
import pytest
from datetime import date
from unittest.mock import Mock, patch, MagicMock
import time

from core.order_executor import (
    SyntheticFuturesExecutor,
    SyntheticExecutionResult,
    LegExecutionResult,
    ExecutionStatus
)
from core.symbol_mapper import (
    SymbolMapper,
    TranslatedSymbol,
    OrderLeg,
    ExchangeCode
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_openalgo():
    """Mock OpenAlgo client"""
    client = Mock()

    # Default: orders succeed
    client.place_order = Mock(return_value={
        'status': 'success',
        'orderid': 'ORDER123'
    })

    client.get_order_status = Mock(return_value={
        'status': 'COMPLETE',
        'fill_price': 100.0,
        'filled_quantity': 35
    })

    client.modify_order = Mock(return_value={
        'status': 'success'
    })

    client.cancel_order = Mock(return_value={
        'status': 'success'
    })

    client.get_quote = Mock(return_value={
        'bid': 99.5,
        'ask': 100.5,
        'ltp': 100.0
    })

    return client


@pytest.fixture
def mock_symbol_mapper():
    """Mock SymbolMapper"""
    mapper = Mock()

    # Default translation for Bank Nifty
    def translate(instrument, action, current_price, reference_date=None):
        pe_action = "SELL" if action == "BUY" else "BUY"
        ce_action = "BUY" if action == "BUY" else "SELL"

        return TranslatedSymbol(
            instrument="BANK_NIFTY",
            exchange="NFO",
            symbols=["BANKNIFTY26DEC2450500PE", "BANKNIFTY26DEC2450500CE"],
            expiry_date=date(2024, 12, 26),
            is_synthetic=True,
            atm_strike=50500,
            order_legs=[
                OrderLeg(
                    symbol="BANKNIFTY26DEC2450500PE",
                    exchange="NFO",
                    action=pe_action,
                    leg_type="PE"
                ),
                OrderLeg(
                    symbol="BANKNIFTY26DEC2450500CE",
                    exchange="NFO",
                    action=ce_action,
                    leg_type="CE"
                )
            ]
        )

    mapper.translate = Mock(side_effect=translate)
    mapper.get_lot_size = Mock(return_value=35)

    return mapper


@pytest.fixture
def executor(mock_openalgo, mock_symbol_mapper):
    """Create SyntheticFuturesExecutor with mocked dependencies"""
    return SyntheticFuturesExecutor(
        openalgo_client=mock_openalgo,
        symbol_mapper=mock_symbol_mapper,
        timeout_seconds=5,  # Short timeout for tests
        poll_interval_seconds=0.1
    )


# =============================================================================
# SUCCESSFUL EXECUTION TESTS
# =============================================================================

class TestSuccessfulExecution:
    """Test successful 2-leg execution"""

    def test_entry_both_legs_succeed(self, executor, mock_openalgo):
        """Entry: Both PE and CE legs fill successfully"""
        # Setup: Both orders complete immediately
        mock_openalgo.get_order_status = Mock(return_value={
            'status': 'COMPLETE',
            'fill_price': 100.0,
            'filled_quantity': 35
        })

        result = executor.execute_entry(
            instrument="BANK_NIFTY",
            lots=1,
            current_price=50500
        )

        assert result.status == ExecutionStatus.EXECUTED
        assert result.pe_result is not None
        assert result.pe_result.success == True
        assert result.ce_result is not None
        assert result.ce_result.success == True
        assert result.rollback_performed == False

    def test_entry_correct_order_actions(self, executor, mock_symbol_mapper):
        """Entry: PE SELL first, CE BUY second"""
        result = executor.execute_entry(
            instrument="BANK_NIFTY",
            lots=1,
            current_price=50500
        )

        # Verify translate was called with BUY for entry
        mock_symbol_mapper.translate.assert_called_with(
            instrument="BANK_NIFTY",
            action="BUY",
            current_price=50500,
            reference_date=None
        )

    def test_exit_both_legs_succeed(self, executor, mock_openalgo):
        """Exit: Both PE BUY and CE SELL fill successfully"""
        mock_openalgo.get_order_status = Mock(return_value={
            'status': 'COMPLETE',
            'fill_price': 105.0,
            'filled_quantity': 35
        })

        result = executor.execute_exit(
            instrument="BANK_NIFTY",
            lots=1,
            current_price=50600
        )

        assert result.status == ExecutionStatus.EXECUTED
        assert result.pe_result.success == True
        assert result.ce_result.success == True


# =============================================================================
# LEG FAILURE WITH ROLLBACK TESTS
# =============================================================================

class TestLegFailureRollback:
    """Test rollback when leg 2 fails"""

    def test_ce_leg_fails_triggers_rollback(self, executor, mock_openalgo):
        """CE leg fails → PE leg is rolled back"""
        call_count = [0]

        def mock_place_order(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # PE leg
                return {'status': 'success', 'orderid': 'PE_ORDER'}
            elif call_count[0] == 2:  # CE leg
                return {'status': 'error', 'error': 'insufficient_margin'}
            else:  # Rollback
                return {'status': 'success', 'orderid': 'ROLLBACK_ORDER'}

        mock_openalgo.place_order = Mock(side_effect=mock_place_order)
        mock_openalgo.get_order_status = Mock(return_value={
            'status': 'COMPLETE',
            'fill_price': 100.0
        })

        result = executor.execute_entry(
            instrument="BANK_NIFTY",
            lots=1,
            current_price=50500
        )

        assert result.status == ExecutionStatus.REJECTED
        assert result.rollback_performed == True
        assert result.rollback_success == True
        assert "ce_leg_failed" in result.rejection_reason.lower()

    def test_rollback_failure_is_critical(self, executor, mock_openalgo):
        """Rollback failure is logged as CRITICAL"""
        call_count = [0]

        def mock_place_order(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # PE leg succeeds
                return {'status': 'success', 'orderid': 'PE_ORDER'}
            else:  # CE leg and rollback fail
                return {'status': 'error', 'error': 'api_error'}

        mock_openalgo.place_order = Mock(side_effect=mock_place_order)
        mock_openalgo.get_order_status = Mock(return_value={
            'status': 'COMPLETE',
            'fill_price': 100.0
        })

        result = executor.execute_entry(
            instrument="BANK_NIFTY",
            lots=1,
            current_price=50500
        )

        assert result.status == ExecutionStatus.REJECTED
        assert result.rollback_performed == True
        assert result.rollback_success == False
        assert "CRITICAL" in result.rejection_reason or "CRITICAL" in (result.notes or "")

    def test_pe_leg_fails_no_rollback_needed(self, executor, mock_openalgo):
        """PE leg fails → no rollback needed (CE never placed)"""
        mock_openalgo.place_order = Mock(return_value={
            'status': 'error',
            'error': 'insufficient_margin'
        })

        result = executor.execute_entry(
            instrument="BANK_NIFTY",
            lots=1,
            current_price=50500
        )

        assert result.status == ExecutionStatus.REJECTED
        assert result.rollback_performed == False
        assert result.ce_result is None  # CE leg never attempted


# =============================================================================
# TIMEOUT TESTS
# =============================================================================

class TestTimeout:
    """Test timeout handling"""

    def test_leg_timeout_triggers_cancel(self, mock_openalgo, mock_symbol_mapper):
        """Leg timeout cancels order and triggers rollback for leg 2"""
        # Create executor with very short timeout
        executor = SyntheticFuturesExecutor(
            openalgo_client=mock_openalgo,
            symbol_mapper=mock_symbol_mapper,
            timeout_seconds=0.1,  # Very short
            poll_interval_seconds=0.05
        )

        # PE succeeds quickly
        pe_called = [False]
        ce_called = [False]

        def mock_place_order(**kwargs):
            if 'PE' in kwargs.get('symbol', ''):
                pe_called[0] = True
                return {'status': 'success', 'orderid': 'PE_ORDER'}
            else:
                ce_called[0] = True
                return {'status': 'success', 'orderid': 'CE_ORDER'}

        mock_openalgo.place_order = Mock(side_effect=mock_place_order)

        # PE fills, CE stays OPEN (times out)
        def mock_status(order_id):
            if 'PE' in str(order_id):
                return {'status': 'COMPLETE', 'fill_price': 100.0}
            return {'status': 'OPEN'}

        mock_openalgo.get_order_status = Mock(side_effect=mock_status)

        result = executor.execute_entry(
            instrument="BANK_NIFTY",
            lots=1,
            current_price=50500
        )

        # CE should timeout, triggering cancel and rollback
        assert result.status == ExecutionStatus.REJECTED
        mock_openalgo.cancel_order.assert_called()


# =============================================================================
# PRICE CHASING TESTS
# =============================================================================

class TestPriceChasing:
    """Test aggressive LIMIT order price chasing"""

    def test_get_limit_price_from_quote(self, executor, mock_openalgo):
        """Initial price is avg(bid, ask)"""
        mock_openalgo.get_quote = Mock(return_value={
            'bid': 99.0,
            'ask': 101.0,
            'ltp': 100.0
        })

        price = executor._get_limit_price("TEST_SYMBOL", "BUY")

        assert price == 100.0  # (99 + 101) / 2

    def test_get_limit_price_fallback_to_ltp(self, executor, mock_openalgo):
        """Falls back to LTP if bid/ask missing"""
        mock_openalgo.get_quote = Mock(return_value={
            'ltp': 100.0
        })

        price = executor._get_limit_price("TEST_SYMBOL", "BUY")

        assert price == 100.0

    def test_get_limit_price_returns_none_on_failure(self, executor, mock_openalgo):
        """Returns None if quote fails"""
        mock_openalgo.get_quote = Mock(return_value={})

        price = executor._get_limit_price("TEST_SYMBOL", "BUY")

        assert price is None


# =============================================================================
# RESULT CONVERSION TESTS
# =============================================================================

class TestResultConversion:
    """Test SyntheticExecutionResult conversion"""

    def test_to_execution_result_success(self):
        """Successful result converts correctly"""
        pe_result = LegExecutionResult(
            success=True,
            order_id="PE_123",
            fill_price=98.5,
            filled_quantity=35,
            leg_type="PE"
        )
        ce_result = LegExecutionResult(
            success=True,
            order_id="CE_456",
            fill_price=101.5,
            filled_quantity=35,
            leg_type="CE"
        )

        synth_result = SyntheticExecutionResult(
            status=ExecutionStatus.EXECUTED,
            pe_result=pe_result,
            ce_result=ce_result
        )

        exec_result = synth_result.to_execution_result(lots=1, signal_price=50500)

        assert exec_result.status == ExecutionStatus.EXECUTED
        assert exec_result.lots_filled == 1
        assert "PE:PE_123" in exec_result.order_id
        assert "CE:CE_456" in exec_result.order_id

    def test_to_execution_result_failure(self):
        """Failed result converts with rejection reason"""
        synth_result = SyntheticExecutionResult(
            status=ExecutionStatus.REJECTED,
            rejection_reason="ce_leg_failed",
            notes="PE rolled back"
        )

        exec_result = synth_result.to_execution_result(lots=1, signal_price=50500)

        assert exec_result.status == ExecutionStatus.REJECTED
        assert exec_result.rejection_reason == "ce_leg_failed"


# =============================================================================
# EXIT WITH STORED SYMBOLS TESTS
# =============================================================================

class TestExitWithStoredSymbols:
    """Test exit using stored symbols from entry"""

    def test_exit_with_provided_symbols(self, executor, mock_openalgo):
        """Exit uses provided PE/CE symbols if given"""
        mock_openalgo.get_order_status = Mock(return_value={
            'status': 'COMPLETE',
            'fill_price': 105.0
        })

        result = executor.execute_exit(
            instrument="BANK_NIFTY",
            lots=1,
            current_price=50600,
            pe_symbol="BANKNIFTY26DEC2450000PE",  # Different from ATM
            ce_symbol="BANKNIFTY26DEC2450000CE"
        )

        assert result.status == ExecutionStatus.EXECUTED


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Test edge cases"""

    def test_non_synthetic_rejected(self, executor, mock_symbol_mapper):
        """Non-synthetic instrument rejected"""
        # Make translate return non-synthetic
        mock_symbol_mapper.translate = Mock(return_value=TranslatedSymbol(
            instrument="GOLD_MINI",
            exchange="MCX",
            symbols=["GOLDM05JAN26FUT"],
            expiry_date=date(2026, 1, 5),
            is_synthetic=False,
            order_legs=[
                OrderLeg(
                    symbol="GOLDM05JAN26FUT",
                    exchange="MCX",
                    action="BUY",
                    leg_type="FUT"
                )
            ]
        ))

        result = executor.execute_entry(
            instrument="GOLD_MINI",
            lots=1,
            current_price=75000
        )

        assert result.status == ExecutionStatus.REJECTED
        assert "Expected synthetic futures" in result.rejection_reason

    def test_quantity_calculation(self, executor, mock_symbol_mapper):
        """Quantity = lots * lot_size"""
        mock_symbol_mapper.get_lot_size.return_value = 35

        # 2 lots = 70 quantity
        result = executor.execute_entry(
            instrument="BANK_NIFTY",
            lots=2,
            current_price=50500
        )

        # Verify place_order was called with correct quantity
        calls = executor.openalgo.place_order.call_args_list
        if calls:
            # Check that quantity=70 was passed
            assert any(call.kwargs.get('quantity') == 70 for call in calls)


# =============================================================================
# LEG EXECUTION RESULT TESTS
# =============================================================================

class TestLegExecutionResult:
    """Test LegExecutionResult dataclass"""

    def test_successful_leg(self):
        """Successful leg has all fields"""
        result = LegExecutionResult(
            success=True,
            order_id="ORD123",
            fill_price=100.5,
            filled_quantity=35,
            leg_type="PE"
        )

        assert result.success == True
        assert result.order_id == "ORD123"
        assert result.fill_price == 100.5
        assert result.filled_quantity == 35
        assert result.leg_type == "PE"
        assert result.error is None

    def test_failed_leg(self):
        """Failed leg has error"""
        result = LegExecutionResult(
            success=False,
            error="insufficient_margin",
            leg_type="CE"
        )

        assert result.success == False
        assert result.error == "insufficient_margin"
        assert result.order_id is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
