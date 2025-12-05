"""
Signal Validation Metrics Collection

Tracks validation and execution metrics for monitoring and alerting
"""
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum

from core.models import SignalType
from core.signal_validator import ValidationSeverity
from core.order_executor import ExecutionStatus

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics tracked"""
    VALIDATION = "validation"
    EXECUTION = "execution"
    DIVERGENCE = "divergence"
    SLIPPAGE = "slippage"
    RISK_ADJUSTMENT = "risk_adjustment"


@dataclass
class ValidationMetric:
    """Single validation metric entry"""
    timestamp: datetime
    signal_type: SignalType
    instrument: str
    validation_stage: str  # 'condition' or 'execution'
    result: str  # 'passed' or 'failed'
    severity: Optional[ValidationSeverity] = None
    divergence_pct: Optional[float] = None
    risk_increase_pct: Optional[float] = None
    signal_age_seconds: Optional[float] = None
    rejection_reason: Optional[str] = None


@dataclass
class ExecutionMetric:
    """Single execution metric entry"""
    timestamp: datetime
    signal_type: SignalType
    instrument: str
    execution_strategy: str
    status: ExecutionStatus
    lots: int
    slippage_pct: Optional[float] = None
    attempts: int = 1
    execution_time_ms: Optional[float] = None
    rejection_reason: Optional[str] = None


class SignalValidationMetrics:
    """
    Collects and aggregates metrics for signal validation and execution
    
    Maintains rolling window of last N events for real-time monitoring
    """
    
    def __init__(self, window_size: int = 1000, time_source=None):
        """
        Initialize metrics collector
        
        Args:
            window_size: Number of events to keep in rolling window
            time_source: Optional callable that returns datetime (defaults to datetime.now)
                        Useful for testing with fixed time
        """
        self.window_size = window_size
        self.time_source = time_source or datetime.now
        
        # Rolling windows
        self.validation_metrics: deque = deque(maxlen=window_size)
        self.execution_metrics: deque = deque(maxlen=window_size)
        
        # Aggregated counters
        self.total_signals = 0
        self.total_validations = 0
        self.total_executions = 0
        
    def record_validation(
        self,
        signal_type: SignalType,
        instrument: str,
        validation_stage: str,
        result: str,
        severity: Optional[ValidationSeverity] = None,
        divergence_pct: Optional[float] = None,
        risk_increase_pct: Optional[float] = None,
        signal_age_seconds: Optional[float] = None,
        rejection_reason: Optional[str] = None
    ):
        """
        Record a validation event
        
        Args:
            signal_type: Type of signal
            instrument: Trading instrument
            validation_stage: 'condition' or 'execution'
            result: 'passed' or 'failed'
            severity: Validation severity level
            divergence_pct: Price divergence percentage
            risk_increase_pct: Risk increase percentage
            signal_age_seconds: Signal age in seconds
            rejection_reason: Reason for rejection if failed
        """
        metric = ValidationMetric(
            timestamp=self.time_source(),
            signal_type=signal_type,
            instrument=instrument,
            validation_stage=validation_stage,
            result=result,
            severity=severity,
            divergence_pct=divergence_pct,
            risk_increase_pct=risk_increase_pct,
            signal_age_seconds=signal_age_seconds,
            rejection_reason=rejection_reason
        )
        
        self.validation_metrics.append(metric)
        self.total_validations += 1
        
        # Structured logging
        logger.info("validation_metric", extra={
            'metric_type': 'validation',
            'signal_type': signal_type.value,
            'instrument': instrument,
            'validation_stage': validation_stage,
            'result': result,
            'severity': severity.value if severity else None,
            'divergence_pct': divergence_pct,
            'risk_increase_pct': risk_increase_pct,
            'signal_age_seconds': signal_age_seconds,
            'rejection_reason': rejection_reason,
            'timestamp': metric.timestamp.isoformat()
        })
    
    def record_execution(
        self,
        signal_type: SignalType,
        instrument: str,
        execution_strategy: str,
        status: ExecutionStatus,
        lots: int,
        slippage_pct: Optional[float] = None,
        attempts: int = 1,
        execution_time_ms: Optional[float] = None,
        rejection_reason: Optional[str] = None
    ):
        """
        Record an execution event
        
        Args:
            signal_type: Type of signal
            instrument: Trading instrument
            execution_strategy: 'simple_limit' or 'progressive'
            status: Execution status
            lots: Number of lots
            slippage_pct: Slippage percentage
            attempts: Number of execution attempts
            execution_time_ms: Execution time in milliseconds
            rejection_reason: Reason for rejection if failed
        """
        metric = ExecutionMetric(
            timestamp=self.time_source(),
            signal_type=signal_type,
            instrument=instrument,
            execution_strategy=execution_strategy,
            status=status,
            lots=lots,
            slippage_pct=slippage_pct,
            attempts=attempts,
            execution_time_ms=execution_time_ms,
            rejection_reason=rejection_reason
        )
        
        self.execution_metrics.append(metric)
        self.total_executions += 1
        
        # Structured logging
        logger.info("execution_metric", extra={
            'metric_type': 'execution',
            'signal_type': signal_type.value,
            'instrument': instrument,
            'execution_strategy': execution_strategy,
            'status': status.value,
            'lots': lots,
            'slippage_pct': slippage_pct,
            'attempts': attempts,
            'execution_time_ms': execution_time_ms,
            'rejection_reason': rejection_reason,
            'timestamp': metric.timestamp.isoformat()
        })
    
    def get_validation_stats(self, window_minutes: int = 60) -> Dict:
        """
        Get validation statistics for the last N minutes
        
        Args:
            window_minutes: Time window in minutes (default: 60)
            
        Returns:
            Dictionary with validation statistics
        """
        cutoff_time = self.time_source().timestamp() - (window_minutes * 60)
        
        recent_validations = [
            m for m in self.validation_metrics
            if m.timestamp.timestamp() > cutoff_time
        ]
        
        if not recent_validations:
            return {
                'total': 0,
                'passed': 0,
                'failed': 0,
                'pass_rate': 0.0,
                'by_stage': {},
                'by_severity': {},
                'avg_divergence_pct': 0.0,
                'avg_signal_age_seconds': 0.0
            }
        
        passed = sum(1 for m in recent_validations if m.result == 'passed')
        failed = sum(1 for m in recent_validations if m.result == 'failed')
        
        by_stage = {}
        for stage in ['condition', 'execution']:
            stage_validations = [m for m in recent_validations if m.validation_stage == stage]
            by_stage[stage] = {
                'total': len(stage_validations),
                'passed': sum(1 for m in stage_validations if m.result == 'passed'),
                'failed': sum(1 for m in stage_validations if m.result == 'failed')
            }
        
        by_severity = {}
        for severity in ValidationSeverity:
            severity_validations = [
                m for m in recent_validations
                if m.severity == severity
            ]
            by_severity[severity.value] = len(severity_validations)
        
        divergences = [m.divergence_pct for m in recent_validations if m.divergence_pct is not None]
        ages = [m.signal_age_seconds for m in recent_validations if m.signal_age_seconds is not None]
        
        return {
            'total': len(recent_validations),
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / len(recent_validations) if recent_validations else 0.0,
            'by_stage': by_stage,
            'by_severity': by_severity,
            'avg_divergence_pct': sum(divergences) / len(divergences) if divergences else 0.0,
            'max_divergence_pct': max(divergences) if divergences else 0.0,
            'avg_signal_age_seconds': sum(ages) / len(ages) if ages else 0.0,
            'max_signal_age_seconds': max(ages) if ages else 0.0
        }
    
    def get_execution_stats(self, window_minutes: int = 60) -> Dict:
        """
        Get execution statistics for the last N minutes
        
        Args:
            window_minutes: Time window in minutes (default: 60)
            
        Returns:
            Dictionary with execution statistics
        """
        cutoff_time = self.time_source().timestamp() - (window_minutes * 60)
        
        recent_executions = [
            m for m in self.execution_metrics
            if m.timestamp.timestamp() > cutoff_time
        ]
        
        if not recent_executions:
            return {
                'total': 0,
                'executed': 0,
                'rejected': 0,
                'timeout': 0,
                'partial': 0,
                'success_rate': 0.0,
                'avg_slippage_pct': 0.0,
                'avg_attempts': 0.0,
                'avg_execution_time_ms': 0.0
            }
        
        executed = sum(1 for m in recent_executions if m.status == ExecutionStatus.EXECUTED)
        rejected = sum(1 for m in recent_executions if m.status == ExecutionStatus.REJECTED)
        timeout = sum(1 for m in recent_executions if m.status == ExecutionStatus.TIMEOUT)
        partial = sum(1 for m in recent_executions if m.status == ExecutionStatus.PARTIAL)
        
        slippages = [m.slippage_pct for m in recent_executions if m.slippage_pct is not None]
        attempts = [m.attempts for m in recent_executions]
        execution_times = [
            m.execution_time_ms for m in recent_executions
            if m.execution_time_ms is not None
        ]
        
        return {
            'total': len(recent_executions),
            'executed': executed,
            'rejected': rejected,
            'timeout': timeout,
            'partial': partial,
            'success_rate': executed / len(recent_executions) if recent_executions else 0.0,
            'avg_slippage_pct': sum(slippages) / len(slippages) if slippages else 0.0,
            'max_slippage_pct': max(slippages) if slippages else 0.0,
            'avg_attempts': sum(attempts) / len(attempts) if attempts else 0.0,
            'avg_execution_time_ms': sum(execution_times) / len(execution_times) if execution_times else 0.0,
            'max_execution_time_ms': max(execution_times) if execution_times else 0.0
        }
    
    def export_prometheus_format(self) -> List[str]:
        """
        Export metrics in Prometheus format
        
        Returns:
            List of Prometheus metric lines
        """
        lines = []
        
        # Validation metrics
        validation_stats = self.get_validation_stats()
        lines.append(f'# HELP signal_validation_total Total validation attempts')
        lines.append(f'# TYPE signal_validation_total counter')
        lines.append(f'signal_validation_total {validation_stats["total"]}')
        
        lines.append(f'# HELP signal_validation_passed Total passed validations')
        lines.append(f'# TYPE signal_validation_passed counter')
        lines.append(f'signal_validation_passed {validation_stats["passed"]}')
        
        lines.append(f'# HELP signal_validation_failed Total failed validations')
        lines.append(f'# TYPE signal_validation_failed counter')
        lines.append(f'signal_validation_failed {validation_stats["failed"]}')
        
        lines.append(f'# HELP signal_validation_pass_rate Validation pass rate')
        lines.append(f'# TYPE signal_validation_pass_rate gauge')
        lines.append(f'signal_validation_pass_rate {validation_stats["pass_rate"]}')
        
        # Execution metrics
        execution_stats = self.get_execution_stats()
        lines.append(f'# HELP signal_execution_total Total execution attempts')
        lines.append(f'# TYPE signal_execution_total counter')
        lines.append(f'signal_execution_total {execution_stats["total"]}')
        
        lines.append(f'# HELP signal_execution_success_rate Execution success rate')
        lines.append(f'# TYPE signal_execution_success_rate gauge')
        lines.append(f'signal_execution_success_rate {execution_stats["success_rate"]}')
        
        lines.append(f'# HELP signal_execution_avg_slippage_pct Average slippage percentage')
        lines.append(f'# TYPE signal_execution_avg_slippage_pct gauge')
        lines.append(f'signal_execution_avg_slippage_pct {execution_stats["avg_slippage_pct"]}')
        
        return lines
    
    def clear(self):
        """Clear all metrics (for testing)"""
        self.validation_metrics.clear()
        self.execution_metrics.clear()
        self.total_signals = 0
        self.total_validations = 0
        self.total_executions = 0

