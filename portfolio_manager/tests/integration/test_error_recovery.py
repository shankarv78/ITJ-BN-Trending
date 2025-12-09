"""
Integration tests for error recovery and broker API failure handling

Tests various failure scenarios and recovery mechanisms
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
import time

from core.models import Signal, SignalType
from core.config import PortfolioConfig, SignalValidationConfig
from core.signal_validator import ConditionValidationResult, ValidationSeverity
from live.engine import LiveTradingEngine
from tests.mocks.mock_broker import MockBrokerSimulator

# Note: mock_symbol_mapper fixture is provided by conftest.py (autouse=True)


@pytest.fixture
def portfolio_config():
    """Portfolio configuration with validation enabled"""
    config = PortfolioConfig()
    config.signal_validation_enabled = True
    config.execution_strategy = "simple_limit"  # Use simple limit for easier testing
    config.signal_validation_config = SignalValidationConfig()
    config.initial_capital = 10000000.0  # 1 crore for sufficient margin
    config.risk_per_trade_pct = 0.02  # 2% risk per trade
    return config


@pytest.fixture
def base_entry_signal():
    """Fresh base entry signal with UTC-aware timestamp"""
    return Signal(
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=5),
        instrument="BANK_NIFTY",  # Use underscore (not BANKNIFTY)
        signal_type=SignalType.BASE_ENTRY,
        position="Long_1",
        price=50000.0,
        stop=49900.0,
        suggested_lots=1,
        atr=100.0,
        er=0.5,
        supertrend=49800.0
    )


class TestBrokerAPIFailureRecovery:
    """Test recovery from broker API failures"""

    def test_broker_api_down_fallback(self, portfolio_config, base_entry_signal):
        """Test fallback to signal price when broker API is completely down"""
        # Use MockBrokerSimulator but patch get_quote to fail
        mock_broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)

        engine = LiveTradingEngine(
            initial_capital=portfolio_config.initial_capital,
            openalgo_client=mock_broker,
            config=portfolio_config
        )

        # Patch get_quote to simulate complete API failure
        with patch.object(mock_broker, 'get_quote', side_effect=Exception("Broker API is down")):
            result = engine.process_signal(base_entry_signal)

        # Should proceed with signal price (validation bypassed)
        assert result['status'] in ['executed', 'rejected', 'blocked']

        # Verify metrics recorded bypassed validation
        bypassed_metrics = [
            m for m in engine.metrics.validation_metrics
            if m.result == 'bypassed'
        ]
        assert len(bypassed_metrics) > 0, "Should have recorded bypassed validation"

    def test_broker_api_timeout(self, portfolio_config, base_entry_signal):
        """Test timeout handling and fallback"""
        mock_broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)

        engine = LiveTradingEngine(
            initial_capital=portfolio_config.initial_capital,
            openalgo_client=mock_broker,
            config=portfolio_config
        )

        # Patch get_quote to simulate timeout
        with patch.object(mock_broker, 'get_quote', side_effect=TimeoutError("Request timed out")) as mock_get_quote:
            result = engine.process_signal(base_entry_signal)

            # Should proceed with signal price after timeout
            assert result['status'] in ['executed', 'rejected', 'blocked']

            # Verify retry logic was executed (initial + retries)
            assert mock_get_quote.call_count >= 3

    def test_validation_bypassed_flag(self, portfolio_config, base_entry_signal):
        """Test that validation_bypassed flag is set when broker fails"""
        mock_broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)

        engine = LiveTradingEngine(
            initial_capital=portfolio_config.initial_capital,
            openalgo_client=mock_broker,
            config=portfolio_config
        )

        # Patch get_quote to simulate connection error
        with patch.object(mock_broker, 'get_quote', side_effect=ConnectionError("Connection refused")):
            result = engine.process_signal(base_entry_signal)

        # Should have metrics indicating bypassed validation
        bypassed_metrics = [
            m for m in engine.metrics.validation_metrics
            if m.result == 'bypassed'
        ]
        assert len(bypassed_metrics) > 0, "Should have recorded bypassed validation"

    def test_exponential_backoff(self, portfolio_config, base_entry_signal):
        """Test exponential backoff retry mechanism"""
        mock_broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)

        engine = LiveTradingEngine(
            initial_capital=portfolio_config.initial_capital,
            openalgo_client=mock_broker,
            config=portfolio_config
        )

        # Track call times to verify backoff
        call_times = []

        def failing_get_quote(*args, **kwargs):
            call_times.append(time.time())
            raise TimeoutError("Timeout")

        # Patch get_quote to track calls
        with patch.object(mock_broker, 'get_quote', side_effect=failing_get_quote):
            result = engine.process_signal(base_entry_signal)

        # Should have multiple retry attempts (initial + retries)
        assert len(call_times) >= 3

        # Verify backoff delays (approximately)
        if len(call_times) >= 3:
            # First retry should have ~0.5s delay
            delay1 = call_times[1] - call_times[0]
            # Second retry should have ~1.0s delay
            delay2 = call_times[2] - call_times[1]

            # Allow some tolerance for execution time
            assert delay1 >= 0.4, f"First retry delay too short: {delay1}s"
            assert delay2 >= 0.9, f"Second retry delay too short: {delay2}s"

    def test_partial_broker_failure_recovery(self, portfolio_config, base_entry_signal):
        """Test recovery when broker API fails then recovers"""
        mock_broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)

        engine = LiveTradingEngine(
            initial_capital=portfolio_config.initial_capital,
            openalgo_client=mock_broker,
            config=portfolio_config
        )

        # Fail first 2 attempts, succeed on 3rd
        call_count = 0
        def intermittent_get_quote(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("Timeout")
            return {'ltp': 50000.0, 'bid': 49990.0, 'ask': 50010.0}

        # Patch get_quote to fail then succeed
        with patch.object(mock_broker, 'get_quote', side_effect=intermittent_get_quote):
            result = engine.process_signal(base_entry_signal)

        # Should succeed after retry
        assert result['status'] in ['executed', 'rejected', 'blocked']

        # Should have made at least 3 attempts (up to 4 max with ProgressiveExecutor)
        assert call_count >= 3, f"Expected at least 3 attempts, got {call_count}"

        # Validation should NOT be bypassed (succeeded on retry)
        bypassed_metrics = [
            m for m in engine.metrics.validation_metrics
            if m.result == 'bypassed'
        ]
        # Should be 0 or very few bypassed (since we succeeded on retry)
        assert len(bypassed_metrics) == 0, "Validation should not be bypassed when retry succeeds"


class TestValidationDisabledFallback:
    """Test behavior when validation is disabled"""

    def test_validation_disabled_no_broker_calls(self, base_entry_signal):
        """Test that broker API is not called when validation is disabled"""
        config = PortfolioConfig()
        config.signal_validation_enabled = False  # Disabled

        mock_broker = Mock()
        mock_broker.get_funds.return_value = {'availablecash': 1000000.0}
        mock_broker.place_order.return_value = {
            'status': 'success',
            'orderid': 'TEST_ORDER_123'
        }
        mock_broker.get_order_status.return_value = {
            'status': 'COMPLETE',
            'fill_status': 'COMPLETE',
            'fill_price': 50000.0,
            'filled_lots': 1,
            'lots': 1
        }

        engine = LiveTradingEngine(
            initial_capital=1000000.0,
            openalgo_client=mock_broker,
            config=config
        )

        result = engine.process_signal(base_entry_signal)

        # Should not call get_quote when validation is disabled
        assert mock_broker.get_quote.call_count == 0

        # Should still execute order
        assert result['status'] in ['executed', 'rejected', 'blocked']


class TestMetricsUnderFailure:
    """Test that metrics are correctly recorded during failures"""

    def test_metrics_record_bypassed_validation(self, portfolio_config, base_entry_signal):
        """Test that metrics correctly record bypassed validation"""
        mock_broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)

        engine = LiveTradingEngine(
            initial_capital=portfolio_config.initial_capital,
            openalgo_client=mock_broker,
            config=portfolio_config
        )

        # Patch get_quote to fail
        with patch.object(mock_broker, 'get_quote', side_effect=Exception("API Error")):
            result = engine.process_signal(base_entry_signal)

        # Check metrics
        assert len(engine.metrics.validation_metrics) > 0

        # Should have bypassed validation metric
        bypassed = [m for m in engine.metrics.validation_metrics if m.result == 'bypassed']
        assert len(bypassed) > 0

        # Should have correct rejection reason
        assert bypassed[0].rejection_reason == 'broker_api_unavailable'

    def test_metrics_record_retry_attempts(self, portfolio_config, base_entry_signal):
        """Test that metrics reflect multiple retry attempts"""
        mock_broker = MockBrokerSimulator(scenario="normal", base_price=50000.0)

        engine = LiveTradingEngine(
            initial_capital=portfolio_config.initial_capital,
            openalgo_client=mock_broker,
            config=portfolio_config
        )

        # Patch get_quote to fail all attempts
        with patch.object(mock_broker, 'get_quote', side_effect=TimeoutError("Timeout")) as mock_get_quote:
            result = engine.process_signal(base_entry_signal)

            # Verify retry attempts were made (initial + retries)
            assert mock_get_quote.call_count >= 3

            # Should have metrics recorded
            assert len(engine.metrics.validation_metrics) > 0
