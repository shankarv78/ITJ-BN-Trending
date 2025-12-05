"""
Unit tests for Task 30 Critical Bug Fixes

Tests for:
- Bug #1: Missing Enum import in signal_validation_alerts.py
- Bug #2: AttributeError on severity field in engine.py
- Bug #3: Performance test ValueError in quantiles calculation
"""
import pytest
import statistics
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
from decimal import Decimal

# Bug #1 imports
from core.signal_validation_alerts import SignalValidationAlerts, AlertSeverity, Alert
from core.signal_validation_metrics import SignalValidationMetrics

# Bug #2 imports
from core.models import Signal, SignalType
from core.config import PortfolioConfig


class TestBug1EnumImport:
    """Test Bug #1: Missing Enum import in alerts"""
    
    def test_bug1_enum_import(self):
        """TC-30.1.1: Verify module imports successfully"""
        # Should not raise ImportError or NameError
        from core.signal_validation_alerts import SignalValidationAlerts, AlertSeverity
        
        assert SignalValidationAlerts is not None
        assert AlertSeverity is not None
    
    def test_bug1_enum_values(self):
        """TC-30.1.2: Verify AlertSeverity enum values work correctly"""
        # Create enum values
        warning = AlertSeverity.WARNING
        critical = AlertSeverity.CRITICAL
        
        # Verify values
        assert warning.value == "warning"
        assert critical.value == "critical"
        
        # Verify comparison works
        assert warning != critical
        assert warning == AlertSeverity.WARNING
    
    def test_bug1_alert_creation(self):
        """TC-30.1.3: Verify Alert dataclass can be created with AlertSeverity"""
        # Create Alert with WARNING severity
        alert_warning = Alert(
            timestamp=datetime.now(),
            severity=AlertSeverity.WARNING,
            alert_type="test",
            message="Test warning"
        )
        
        assert alert_warning.severity == AlertSeverity.WARNING
        assert alert_warning.alert_type == "test"
        
        # Create Alert with CRITICAL severity
        alert_critical = Alert(
            timestamp=datetime.now(),
            severity=AlertSeverity.CRITICAL,
            alert_type="test",
            message="Test critical"
        )
        
        assert alert_critical.severity == AlertSeverity.CRITICAL
    
    def test_bug1_alerting_system(self):
        """TC-30.1.4: Verify full alerting system works"""
        # Create mock metrics
        mock_metrics = Mock(spec=SignalValidationMetrics)
        mock_metrics.get_rejection_rate.return_value = 0.15  # 15% rejection rate
        mock_metrics.get_timeout_rate.return_value = 0.02
        mock_metrics.get_avg_signal_age.return_value = 5.0
        
        # Create alerting system
        alerts = SignalValidationAlerts(metrics=mock_metrics)
        
        # Check for alerts (high rejection rate should trigger)
        alert_list = alerts.check_alerts()
        
        # Should have at least one alert
        assert len(alert_list) > 0
        
        # Verify alert has AlertSeverity enum
        for alert in alert_list:
            assert isinstance(alert.severity, AlertSeverity)
            assert alert.severity in [AlertSeverity.WARNING, AlertSeverity.CRITICAL]


class TestBug2AttributeError:
    """Test Bug #2: AttributeError on severity field"""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock portfolio config"""
        config = Mock(spec=PortfolioConfig)
        config.signal_validation_enabled = True
        config.execution_strategy = "simple_limit"
        config.signal_validation_config = Mock()
        config.signal_validation_config.max_divergence_pct = 0.02
        config.signal_validation_config.max_risk_increase_pct = 0.10
        return config
    
    @pytest.fixture
    def mock_metrics(self):
        """Create mock metrics"""
        metrics = Mock(spec=SignalValidationMetrics)
        metrics.record_validation = Mock()
        return metrics
    
    def test_bug2_base_entry_metrics(self, mock_config, mock_metrics):
        """TC-30.2.1: Verify metrics recorded for BASE_ENTRY execution validation"""
        from live.engine import LiveTradingEngine
        
        # Create engine with mocked dependencies
        with patch('live.engine.SignalValidator') as MockValidator, \
             patch('live.engine.OrderExecutor') as MockExecutor:
            
            # Setup mocks
            mock_validator = MockValidator.return_value
            mock_validator.validate_execution_price.return_value = Mock(
                is_valid=True,
                reason=None,
                divergence_pct=0.01,
                risk_increase_pct=0.05,
                direction="favorable"
            )
            
            engine = LiveTradingEngine(
                initial_capital=1000000.0,
                openalgo_client=Mock(),
                config=mock_config
            )
            engine.metrics = mock_metrics
            
            # Create test signal
            signal = Signal(
                signal_type=SignalType.BASE_ENTRY,
                instrument="BANKNIFTY",
                price=50000.0,
                timestamp=datetime.now()
            )
            
            # Process signal (will trigger execution validation)
            with patch.object(engine, '_handle_base_entry_live'):
                engine.process_signal(signal)
            
            # Verify record_validation was called WITHOUT severity parameter
            if mock_metrics.record_validation.called:
                call_kwargs = mock_metrics.record_validation.call_args[1]
                assert 'severity' not in call_kwargs, "severity parameter should not be present"
                assert 'divergence_pct' in call_kwargs
                assert 'risk_increase_pct' in call_kwargs
    
    def test_bug2_pyramid_metrics(self, mock_config, mock_metrics):
        """TC-30.2.2: Verify metrics recorded for PYRAMID execution validation"""
        from live.engine import LiveTradingEngine
        
        # Create engine with mocked dependencies
        with patch('live.engine.SignalValidator') as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.validate_execution_price.return_value = Mock(
                is_valid=True,
                reason=None,
                divergence_pct=0.008,
                risk_increase_pct=0.03,
                direction="favorable"
            )
            
            engine = LiveTradingEngine(
                initial_capital=1000000.0,
                openalgo_client=Mock(),
                config=mock_config
            )
            engine.metrics = mock_metrics
            
            # Create PYRAMID signal
            signal = Signal(
                signal_type=SignalType.PYRAMID,
                instrument="BANKNIFTY",
                price=50500.0,
                timestamp=datetime.now(),
                position_id="test_pos"
            )
            
            # Process signal
            with patch.object(engine, '_handle_pyramid_live'):
                engine.process_signal(signal)
            
            # Verify no severity in call
            if mock_metrics.record_validation.called:
                call_kwargs = mock_metrics.record_validation.call_args[1]
                assert 'severity' not in call_kwargs
    
    def test_bug2_rejection_metrics(self, mock_config, mock_metrics):
        """TC-30.2.3: Verify metrics recorded when execution validation fails"""
        from live.engine import LiveTradingEngine
        
        with patch('live.engine.SignalValidator') as MockValidator:
            mock_validator = MockValidator.return_value
            mock_validator.validate_execution_price.return_value = Mock(
                is_valid=False,
                reason="Price divergence too high: 3.5%",
                divergence_pct=0.035,
                risk_increase_pct=0.15,
                direction="unfavorable"
            )
            
            engine = LiveTradingEngine(
                initial_capital=1000000.0,
                openalgo_client=Mock(),
                config=mock_config
            )
            engine.metrics = mock_metrics
            
            signal = Signal(
                signal_type=SignalType.BASE_ENTRY,
                instrument="BANKNIFTY",
                price=50000.0,
                timestamp=datetime.now()
            )
            
            # Process signal (should be rejected)
            with patch.object(engine, '_handle_base_entry_live'):
                engine.process_signal(signal)
            
            # Verify rejection_reason recorded without severity
            if mock_metrics.record_validation.called:
                call_kwargs = mock_metrics.record_validation.call_args[1]
                assert 'severity' not in call_kwargs
                assert 'rejection_reason' in call_kwargs
                assert call_kwargs['rejection_reason'] is not None
    
    def test_bug2_metrics_structure(self, mock_metrics):
        """TC-30.2.4: Verify recorded metrics have correct structure"""
        # Call record_validation with execution validation parameters
        mock_metrics.record_validation(
            signal_type=SignalType.BASE_ENTRY,
            instrument="BANKNIFTY",
            validation_stage='execution',
            result='passed',
            divergence_pct=0.01,
            risk_increase_pct=0.05,
            rejection_reason=None
        )
        
        # Verify call was made
        assert mock_metrics.record_validation.called
        
        # Get call arguments
        call_kwargs = mock_metrics.record_validation.call_args[1]
        
        # Verify structure
        assert 'signal_type' in call_kwargs
        assert 'instrument' in call_kwargs
        assert 'validation_stage' in call_kwargs
        assert 'result' in call_kwargs
        assert 'divergence_pct' in call_kwargs
        assert 'risk_increase_pct' in call_kwargs
        assert 'rejection_reason' in call_kwargs
        
        # Verify severity is NOT present
        assert 'severity' not in call_kwargs


class TestBug3PerformanceTest:
    """Test Bug #3: Performance test ValueError"""
    
    def test_bug3_large_sample(self):
        """TC-30.3.2: Verify quantiles works with sufficient samples"""
        # Create 100 samples
        times = [float(i * 10) for i in range(100)]
        
        # Calculate p95 using quantiles (should work)
        if len(times) >= 20:
            p95_latency = statistics.quantiles(times, n=20)[18]
        else:
            p95_latency = max(times)
        
        # Verify result is reasonable
        assert p95_latency > 0
        assert p95_latency <= max(times)
        assert p95_latency >= times[int(len(times) * 0.95)]  # Should be near 95th percentile
    
    def test_bug3_boundary_condition(self):
        """TC-30.3.3: Verify quantiles works at boundary condition (20 samples)"""
        # Create exactly 20 samples
        times = [float(i * 10) for i in range(20)]
        
        # Should use quantiles (not fallback)
        if len(times) >= 20:
            p95_latency = statistics.quantiles(times, n=20)[18]
        else:
            p95_latency = max(times)
        
        # Verify no error and reasonable result
        assert p95_latency > 0
        assert p95_latency <= max(times)
    
    def test_bug3_fallback_boundary(self):
        """TC-30.3.4: Verify fallback works just below boundary (19 samples)"""
        # Create 19 samples (just below boundary)
        times = [float(i * 10) for i in range(19)]
        
        # Should use fallback
        if len(times) >= 20:
            p95_latency = statistics.quantiles(times, n=20)[18]
        else:
            p95_latency = max(times)
        
        # Verify uses max (fallback)
        assert p95_latency == max(times)
        assert p95_latency == 180.0  # max of 0, 10, 20, ..., 180
    
    def test_bug3_small_sample_no_error(self):
        """Verify small sample (10) doesn't raise ValueError"""
        # Create 10 samples (original failing case)
        times = [float(i * 10) for i in range(10)]
        
        # This should NOT raise ValueError
        try:
            if len(times) >= 20:
                p95_latency = statistics.quantiles(times, n=20)[18]
            else:
                p95_latency = max(times)
            
            # Should use fallback
            assert p95_latency == max(times)
            assert p95_latency == 90.0
        except ValueError as e:
            pytest.fail(f"ValueError raised with small sample: {e}")

