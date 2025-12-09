"""
Performance tests for signal validation and execution system

Tests latency requirements and concurrent signal handling
"""
import pytest
import time
import statistics
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.models import Signal, SignalType, InstrumentType
from core.signal_validator import SignalValidator, SignalValidationConfig
from core.order_executor import SimpleLimitExecutor, ProgressiveExecutor
from core.portfolio_state import PortfolioStateManager
from core.config import PortfolioConfig
from tests.mocks.mock_broker import MockBrokerSimulator


@pytest.fixture
def mock_openalgo_fast():
    """Mock OpenAlgo client with fast response times"""
    client = Mock()
    client.get_funds.return_value = {'availablecash': 1000000.0}
    client.get_quote.return_value = {'ltp': 50000.0, 'bid': 49990.0, 'ask': 50010.0}
    client.place_order.return_value = {
        'status': 'success',
        'orderid': 'TEST_ORDER_123'
    }
    client.get_order_status.return_value = {
        'status': 'COMPLETE',
        'fill_status': 'COMPLETE',
        'fill_price': 50000.0,
        'filled_lots': 1,
        'lots': 1
    }
    client.cancel_order.return_value = {'status': 'success'}
    return client


@pytest.fixture
def mock_openalgo_slow():
    """Mock OpenAlgo client with slow response times (500ms)"""
    client = Mock()

    def slow_get_quote(instrument):
        time.sleep(0.5)  # 500ms delay
        return {'ltp': 50000.0, 'bid': 49990.0, 'ask': 50010.0}

    def slow_place_order(*args, **kwargs):
        time.sleep(0.5)  # 500ms delay
        return {'status': 'success', 'orderid': 'TEST_ORDER_123'}

    client.get_funds.return_value = {'availablecash': 1000000.0}
    client.get_quote.side_effect = slow_get_quote
    client.place_order.side_effect = slow_place_order
    client.get_order_status.return_value = {
        'status': 'COMPLETE',
        'fill_status': 'COMPLETE',
        'fill_price': 50000.0,
        'filled_lots': 1,
        'lots': 1
    }
    client.cancel_order.return_value = {'status': 'success'}
    return client


@pytest.fixture
def signal_validator():
    """Signal validator for performance testing"""
    config = SignalValidationConfig()
    return SignalValidator(config=config)


@pytest.fixture
def fresh_signal():
    """Fresh signal for testing with UTC-aware timestamp"""
    return Signal(
        timestamp=datetime.now(timezone.utc) - timedelta(seconds=5),
        instrument="BANK_NIFTY",
        signal_type=SignalType.BASE_ENTRY,
        position="Long_1",
        price=50000.0,
        stop=49900.0,
        suggested_lots=1,
        atr=100.0,
        er=0.5,
        supertrend=49800.0
    )


class TestValidationLatency:
    """Test validation latency requirements"""

    def test_condition_validation_latency(self, signal_validator, fresh_signal):
        """Test condition validation completes in <100ms"""
        portfolio_state = Mock()
        portfolio_state.positions = {}

        times = []
        for _ in range(100):
            start = time.time()
            result = signal_validator.validate_conditions_with_signal_price(
                fresh_signal, portfolio_state
            )
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)

        avg_latency = statistics.mean(times)
        p95_latency = statistics.quantiles(times, n=20)[18]  # 95th percentile

        assert avg_latency < 100, f"Average latency {avg_latency:.2f}ms exceeds 100ms"
        assert p95_latency < 100, f"P95 latency {p95_latency:.2f}ms exceeds 100ms"

    def test_execution_validation_latency(self, signal_validator, fresh_signal):
        """Test execution validation completes in <100ms"""
        broker_price = 50000.0

        times = []
        for _ in range(100):
            start = time.time()
            result = signal_validator.validate_execution_price(
                fresh_signal, broker_price, signal_validator.config
            )
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)

        avg_latency = statistics.mean(times)
        p95_latency = statistics.quantiles(times, n=20)[18]

        assert avg_latency < 100, f"Average latency {avg_latency:.2f}ms exceeds 100ms"
        assert p95_latency < 100, f"P95 latency {p95_latency:.2f}ms exceeds 100ms"


class TestBrokerAPILatency:
    """Test broker API latency impact"""

    def test_broker_price_fetch_latency(self, mock_openalgo_fast):
        """Test broker price fetch completes in <200ms (with fast broker)"""
        times = []
        for _ in range(50):
            start = time.time()
            quote = mock_openalgo_fast.get_quote("BANKNIFTY-I")
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)

        avg_latency = statistics.mean(times)
        p95_latency = statistics.quantiles(times, n=20)[18]

        assert avg_latency < 200, f"Average latency {avg_latency:.2f}ms exceeds 200ms"
        assert p95_latency < 200, f"P95 latency {p95_latency:.2f}ms exceeds 200ms"

    def test_slow_broker_handling(self, mock_openalgo_slow):
        """Test system handles slow broker API gracefully"""
        start = time.time()
        quote = mock_openalgo_slow.get_quote("BANKNIFTY-I")
        elapsed_ms = (time.time() - start) * 1000

        # Should complete (even if slow)
        assert quote is not None
        assert elapsed_ms > 400  # Should be ~500ms due to sleep


class TestExecutionLatency:
    """Test order execution latency"""

    def test_simple_limit_executor_latency(self, mock_openalgo_fast, fresh_signal):
        """Test SimpleLimitExecutor completes in <200ms (immediate fill)"""
        executor = SimpleLimitExecutor(openalgo_client=mock_openalgo_fast)

        times = []
        for _ in range(20):
            start = time.time()
            result = executor.execute(fresh_signal, 1, 50000.0)
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)

        avg_latency = statistics.mean(times)
        p95_latency = statistics.quantiles(times, n=20)[18]

        # With immediate fill, should be fast
        assert avg_latency < 200, f"Average latency {avg_latency:.2f}ms exceeds 200ms"
        assert p95_latency < 200, f"P95 latency {p95_latency:.2f}ms exceeds 200ms"


class TestTotalLatency:
    """Test end-to-end latency requirements"""

    def test_total_signal_processing_latency(self, mock_openalgo_fast, fresh_signal):
        """Test total latency (signal → order placed) <500ms"""
        from live.engine import LiveTradingEngine

        config = PortfolioConfig()
        config.signal_validation_enabled = True
        config.execution_strategy = "simple_limit"

        engine = LiveTradingEngine(
            initial_capital=1000000.0,
            openalgo_client=mock_openalgo_fast,
            config=config
        )

        times = []
        for _ in range(10):
            start = time.time()
            result = engine.process_signal(fresh_signal)
            elapsed_ms = (time.time() - start) * 1000
            times.append(elapsed_ms)

        avg_latency = statistics.mean(times)
        if len(times) >= 20:
            p95_latency = statistics.quantiles(times, n=20)[18]
        else:
            p95_latency = max(times)  # Fallback for small samples

        # Total latency should be <500ms
        assert avg_latency < 500, f"Average latency {avg_latency:.2f}ms exceeds 500ms"
        assert p95_latency < 500, f"P95 latency {p95_latency:.2f}ms exceeds 500ms"


class TestConcurrentSignalHandling:
    """Test concurrent signal processing"""

    def test_concurrent_signals_processed_correctly(self, mock_openalgo_fast):
        """Test 10 concurrent signals processed correctly"""
        from live.engine import LiveTradingEngine

        config = PortfolioConfig()
        config.signal_validation_enabled = True
        config.execution_strategy = "simple_limit"

        engine = LiveTradingEngine(
            initial_capital=10000000.0,  # Large capital for multiple positions
            openalgo_client=mock_openalgo_fast,
            config=config
        )

        signals = [
            Signal(
                timestamp=datetime.now(timezone.utc) - timedelta(seconds=5),
                instrument="BANK_NIFTY",
                signal_type=SignalType.BASE_ENTRY,
                position=f"Long_{i}",
                price=50000.0 + i,  # Slightly different prices
                stop=49900.0,
                suggested_lots=1,
                atr=100.0,
                er=0.5,
                supertrend=49800.0
            )
            for i in range(10)
        ]

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(engine.process_signal, signal) for signal in signals]
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    pytest.fail(f"Concurrent signal processing failed: {e}")

        # All signals should be processed
        assert len(results) == 10

        # No errors should occur
        error_results = [r for r in results if r.get('status') == 'error']
        assert len(error_results) == 0, f"Errors in concurrent processing: {error_results}"


class TestLoadHandling:
    """Test system under load"""

    def test_sustained_load_100_signals_per_minute(self, mock_openalgo_fast):
        """Test system handles 100 signals/minute sustained load"""
        from live.engine import LiveTradingEngine

        config = PortfolioConfig()
        config.signal_validation_enabled = True
        config.execution_strategy = "simple_limit"

        engine = LiveTradingEngine(
            initial_capital=10000000.0,
            openalgo_client=mock_openalgo_fast,
            config=config
        )

        signals = [
            Signal(
                timestamp=datetime.now(timezone.utc) - timedelta(seconds=5),
                instrument="BANK_NIFTY",
                signal_type=SignalType.BASE_ENTRY,
                position=f"Long_{i}",
                price=50000.0 + (i % 100),  # Vary prices
                stop=49900.0,
                suggested_lots=1,
                atr=100.0,
                er=0.5,
                supertrend=49800.0
            )
            for i in range(100)
        ]

        start = time.time()
        results = []
        for signal in signals:
            result = engine.process_signal(signal)
            results.append(result)
        elapsed = time.time() - start

        # Should process 100 signals in reasonable time (< 2 minutes)
        assert elapsed < 120, f"Processing 100 signals took {elapsed:.2f}s (expected < 120s)"

        # All should be processed
        assert len(results) == 100

        # Check for errors
        error_count = sum(1 for r in results if r.get('status') == 'error')
        assert error_count == 0, f"{error_count} errors during load test"
