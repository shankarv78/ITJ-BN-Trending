"""
Unit tests for metrics time injection

Verifies that SignalValidationMetrics can use custom time source for testing
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from core.signal_validation_metrics import SignalValidationMetrics, ValidationMetric, ExecutionMetric
from core.models import SignalType
from core.signal_validator import ValidationSeverity
from core.order_executor import ExecutionStatus


class TestMetricsTimeInjection:
    """Test time injection in metrics"""
    
    def test_default_time_source(self):
        """Test that metrics use datetime.now() by default"""
        metrics = SignalValidationMetrics(window_size=10)
        
        before = datetime.now()
        metrics.record_validation(
            signal_type=SignalType.BASE_ENTRY,
            instrument="BANK_NIFTY",
            validation_stage='condition',
            result='passed',
            severity=ValidationSeverity.NORMAL
        )
        after = datetime.now()
        
        # Metric timestamp should be between before and after
        assert len(metrics.validation_metrics) == 1
        metric = metrics.validation_metrics[0]
        assert before <= metric.timestamp <= after
    
    def test_custom_time_source(self):
        """Test that metrics use custom time source when provided"""
        fixed_time = datetime(2025, 1, 1, 12, 0, 0)
        time_source = Mock(return_value=fixed_time)
        
        metrics = SignalValidationMetrics(window_size=10, time_source=time_source)
        
        metrics.record_validation(
            signal_type=SignalType.BASE_ENTRY,
            instrument="BANK_NIFTY",
            validation_stage='condition',
            result='passed',
            severity=ValidationSeverity.NORMAL
        )
        
        # Verify custom time source was used
        assert time_source.call_count == 1
        assert len(metrics.validation_metrics) == 1
        assert metrics.validation_metrics[0].timestamp == fixed_time
    
    def test_execution_metrics_time_injection(self):
        """Test time injection for execution metrics"""
        fixed_time = datetime(2025, 1, 1, 12, 0, 0)
        time_source = Mock(return_value=fixed_time)
        
        metrics = SignalValidationMetrics(window_size=10, time_source=time_source)
        
        metrics.record_execution(
            signal_type=SignalType.BASE_ENTRY,
            instrument="BANK_NIFTY",
            execution_strategy='simple_limit',
            status=ExecutionStatus.EXECUTED,
            lots=1,
            execution_time_ms=50.0
        )
        
        # Verify custom time source was used
        assert time_source.call_count == 1
        assert len(metrics.execution_metrics) == 1
        assert metrics.execution_metrics[0].timestamp == fixed_time
    
    def test_time_progression_simulation(self):
        """Test simulating time progression for testing"""
        # Simulate time advancing
        current_time = datetime(2025, 1, 1, 12, 0, 0)
        
        def advancing_time():
            nonlocal current_time
            current_time += timedelta(seconds=1)
            return current_time
        
        metrics = SignalValidationMetrics(window_size=10, time_source=advancing_time)
        
        # Record 3 events
        for i in range(3):
            metrics.record_validation(
                signal_type=SignalType.BASE_ENTRY,
                instrument="BANK_NIFTY",
                validation_stage='condition',
                result='passed',
                severity=ValidationSeverity.NORMAL
            )
        
        # Verify timestamps advance
        assert len(metrics.validation_metrics) == 3
        timestamps = [m.timestamp for m in metrics.validation_metrics]
        
        # Each timestamp should be 1 second apart
        assert timestamps[1] - timestamps[0] == timedelta(seconds=1)
        assert timestamps[2] - timestamps[1] == timedelta(seconds=1)
    
    def test_aggregation_with_fixed_time(self):
        """Test that metrics are recorded correctly with fixed time"""
        fixed_time = datetime(2025, 1, 1, 12, 0, 0)
        time_source = Mock(return_value=fixed_time)
        
        metrics = SignalValidationMetrics(window_size=10, time_source=time_source)
        
        # Record multiple events
        metrics.record_validation(
            signal_type=SignalType.BASE_ENTRY,
            instrument="BANK_NIFTY",
            validation_stage='condition',
            result='passed',
            severity=ValidationSeverity.NORMAL
        )
        
        metrics.record_validation(
            signal_type=SignalType.BASE_ENTRY,
            instrument="BANK_NIFTY",
            validation_stage='execution',
            result='failed',
            rejection_reason='price_divergence'
        )
        
        # Verify metrics were recorded with fixed time
        assert len(metrics.validation_metrics) == 2
        assert all(m.timestamp == fixed_time for m in metrics.validation_metrics)
        
        # Verify results
        results = [m.result for m in metrics.validation_metrics]
        assert 'passed' in results
        assert 'failed' in results


