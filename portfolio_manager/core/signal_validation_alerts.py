"""
Signal Validation Alerting System

Monitors validation and execution metrics and triggers alerts for anomalies
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from enum import Enum

from core.signal_validation_metrics import SignalValidationMetrics

logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Single alert instance"""
    timestamp: datetime
    severity: AlertSeverity
    alert_type: str
    message: str
    details: Dict = field(default_factory=dict)


class SignalValidationAlerts:
    """
    Monitors validation and execution metrics and triggers alerts
    
    Implements rate limiting to prevent alert spam
    """
    
    def __init__(
        self,
        metrics: SignalValidationMetrics,
        alert_channels: Optional[List] = None
    ):
        """
        Initialize alerting system
        
        Args:
            metrics: SignalValidationMetrics instance
            alert_channels: List of alert channel handlers (Telegram, Email, etc.)
        """
        self.metrics = metrics
        self.alert_channels = alert_channels or []
        
        # Rate limiting: track last alert time per type
        self.last_alert_time: Dict[str, datetime] = {}
        self.alert_cooldown_seconds = 300  # 5 minutes between same-type alerts
        
        # Alert thresholds
        self.high_rejection_rate_threshold = 0.50  # 50%
        self.execution_timeout_rate_threshold = 0.30  # 30%
        self.extreme_risk_increase_threshold = 0.50  # 50%
        self.abnormal_slippage_threshold = 0.015  # 1.5%
        self.broker_api_failure_threshold = 3  # consecutive failures
    
    def check_alerts(self, window_minutes: int = 60) -> List[Alert]:
        """
        Check all alert conditions and return triggered alerts
        
        Args:
            window_minutes: Time window for metrics analysis (default: 60)
            
        Returns:
            List of triggered alerts
        """
        alerts = []
        
        # Get recent metrics
        validation_stats = self.metrics.get_validation_stats(window_minutes)
        execution_stats = self.metrics.get_execution_stats(window_minutes)
        
        # Check each alert condition
        alerts.extend(self._check_high_rejection_rate(validation_stats))
        alerts.extend(self._check_execution_timeout_spike(execution_stats))
        alerts.extend(self._check_extreme_risk_increase(validation_stats))
        alerts.extend(self._check_abnormal_slippage(execution_stats))
        
        # Send alerts through channels
        for alert in alerts:
            self._send_alert(alert)
        
        return alerts
    
    def _check_high_rejection_rate(self, validation_stats: Dict) -> List[Alert]:
        """Check for high signal rejection rate"""
        alerts = []
        
        if validation_stats['total'] == 0:
            return alerts
        
        rejection_rate = 1.0 - validation_stats['pass_rate']
        
        if rejection_rate > self.high_rejection_rate_threshold:
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.WARNING,
                alert_type='high_rejection_rate',
                message=(
                    f"High signal rejection rate: {rejection_rate:.1%} rejected "
                    f"({validation_stats['failed']}/{validation_stats['total']} signals)"
                ),
                details={
                    'rejection_rate': rejection_rate,
                    'total_signals': validation_stats['total'],
                    'failed_signals': validation_stats['failed'],
                    'passed_signals': validation_stats['passed'],
                    'by_stage': validation_stats['by_stage']
                }
            )
            
            if self._should_alert('high_rejection_rate'):
                alerts.append(alert)
        
        return alerts
    
    def _check_execution_timeout_spike(self, execution_stats: Dict) -> List[Alert]:
        """Check for high execution timeout rate"""
        alerts = []
        
        if execution_stats['total'] == 0:
            return alerts
        
        timeout_rate = execution_stats['timeout'] / execution_stats['total']
        
        if timeout_rate > self.execution_timeout_rate_threshold:
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.WARNING,
                alert_type='execution_timeout_spike',
                message=(
                    f"High execution timeout rate: {timeout_rate:.1%} "
                    f"({execution_stats['timeout']}/{execution_stats['total']} attempts)"
                ),
                details={
                    'timeout_rate': timeout_rate,
                    'total_executions': execution_stats['total'],
                    'timeout_count': execution_stats['timeout'],
                    'success_rate': execution_stats['success_rate']
                }
            )
            
            if self._should_alert('execution_timeout_spike'):
                alerts.append(alert)
        
        return alerts
    
    def _check_extreme_risk_increase(self, validation_stats: Dict) -> List[Alert]:
        """Check for extreme risk increase violations"""
        alerts = []
        
        # This would require tracking individual risk increases
        # For now, we check max divergence as a proxy
        max_divergence = validation_stats.get('max_divergence_pct', 0.0)
        
        # If max divergence suggests extreme risk increase
        if max_divergence > 0.05:  # 5% divergence suggests extreme risk
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.CRITICAL,
                alert_type='extreme_risk_increase',
                message=(
                    f"Extreme risk increase detected: {max_divergence:.2%} divergence "
                    f"(may indicate risk increase > {self.extreme_risk_increase_threshold:.0%})"
                ),
                details={
                    'max_divergence_pct': max_divergence,
                    'avg_divergence_pct': validation_stats.get('avg_divergence_pct', 0.0)
                }
            )
            
            if self._should_alert('extreme_risk_increase'):
                alerts.append(alert)
        
        return alerts
    
    def _check_abnormal_slippage(self, execution_stats: Dict) -> List[Alert]:
        """Check for abnormal slippage"""
        alerts = []
        
        max_slippage = execution_stats.get('max_slippage_pct', 0.0)
        
        if max_slippage > self.abnormal_slippage_threshold:
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.WARNING,
                alert_type='abnormal_slippage',
                message=(
                    f"High slippage detected: {max_slippage:.2%} on execution "
                    f"(threshold: {self.abnormal_slippage_threshold:.2%})"
                ),
                details={
                    'max_slippage_pct': max_slippage,
                    'avg_slippage_pct': execution_stats.get('avg_slippage_pct', 0.0),
                    'execution_strategy': 'progressive'  # Would come from metrics
                }
            )
            
            if self._should_alert('abnormal_slippage'):
                alerts.append(alert)
        
        return alerts
    
    def _should_alert(self, alert_type: str) -> bool:
        """
        Check if alert should be sent (rate limiting)
        
        Args:
            alert_type: Type of alert
            
        Returns:
            True if alert should be sent
        """
        now = datetime.now()
        last_alert = self.last_alert_time.get(alert_type)
        
        if last_alert is None:
            self.last_alert_time[alert_type] = now
            return True
        
        time_since_last = (now - last_alert).total_seconds()
        
        if time_since_last >= self.alert_cooldown_seconds:
            self.last_alert_time[alert_type] = now
            return True
        
        return False
    
    def _send_alert(self, alert: Alert):
        """
        Send alert through configured channels
        
        Args:
            alert: Alert to send
        """
        # Log alert
        log_level = logging.WARNING if alert.severity == AlertSeverity.WARNING else logging.CRITICAL
        logger.log(
            log_level,
            f"[ALERT] {alert.alert_type}: {alert.message}",
            extra={
                'alert_type': alert.alert_type,
                'severity': alert.severity.value,
                'message': alert.message,
                'details': alert.details,
                'timestamp': alert.timestamp.isoformat()
            }
        )
        
        # Send through channels (if configured)
        for channel in self.alert_channels:
            try:
                channel.send(alert)
            except Exception as e:
                logger.error(f"Failed to send alert through channel {channel}: {e}")
    
    def check_broker_api_health(self, consecutive_failures: int) -> Optional[Alert]:
        """
        Check broker API health and alert if needed
        
        Args:
            consecutive_failures: Number of consecutive API failures
            
        Returns:
            Alert if threshold exceeded, None otherwise
        """
        if consecutive_failures >= self.broker_api_failure_threshold:
            alert = Alert(
                timestamp=datetime.now(),
                severity=AlertSeverity.CRITICAL,
                alert_type='broker_api_unavailable',
                message=(
                    f"Broker API unavailable: {consecutive_failures} consecutive failures"
                ),
                details={
                    'consecutive_failures': consecutive_failures,
                    'threshold': self.broker_api_failure_threshold
                }
            )
            
            if self._should_alert('broker_api_unavailable'):
                self._send_alert(alert)
                return alert
        
        return None

