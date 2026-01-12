"""
Audit Trail Integration

Provides a clean integration layer between LiveTradingEngine and audit services.
Handles:
- Signal audit record creation and updates
- Order execution logging
- Validation result capture
- Sizing calculation capture

Usage in LiveTradingEngine:
    self.audit = AuditIntegration(db_pool)

    # In process_signal:
    audit_id = self.audit.start_signal(signal, fingerprint)
    self.audit.add_validation(audit_id, condition_result, execution_result)
    self.audit.add_sizing(audit_id, sizing_data)
    self.audit.complete_signal(audit_id, outcome, execution_result)
"""

import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any

from core.signal_audit_service import (
    SignalAuditService, SignalOutcome, SignalAuditRecord
)
from core.order_execution_logger import OrderExecutionLogger, OrderLogEntry
from core.signal_validator import (
    ConditionValidationResult, ExecutionValidationResult, SignalValidator
)

logger = logging.getLogger(__name__)


class AuditIntegration:
    """
    Integration layer for audit trail in LiveTradingEngine.

    Provides simplified methods for recording signal audit trail
    without requiring extensive changes to the engine code.
    """

    def __init__(self, db_pool, instance_id: str = "primary"):
        """
        Initialize audit integration.

        Args:
            db_pool: psycopg2 connection pool
            instance_id: Instance identifier for HA tracking
        """
        self.db_pool = db_pool
        self.instance_id = instance_id
        self.audit_service = SignalAuditService(db_pool)
        self.order_logger = OrderExecutionLogger(db_pool)

        # Track active signal audits
        self._active_audits: Dict[str, int] = {}  # fingerprint -> audit_id
        self._audit_start_times: Dict[int, float] = {}  # audit_id -> start_time

        logger.info(f"[AuditIntegration] Initialized for instance: {instance_id}")

    def start_signal(
        self,
        signal: Any,
        fingerprint: str,
        received_at: Optional[datetime] = None
    ) -> Optional[int]:
        """
        Start recording a signal audit.

        Call this at the beginning of process_signal().

        Args:
            signal: Signal object being processed
            fingerprint: Unique signal fingerprint
            received_at: When signal was received (defaults to now)

        Returns:
            Audit ID (database ID) or None on failure
        """
        try:
            start_time = time.time()

            record = SignalAuditRecord(
                signal_fingerprint=fingerprint,
                instrument=signal.instrument,
                signal_type=signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type),
                position=signal.position,
                signal_timestamp=signal.timestamp,
                received_at=received_at or datetime.now(),
                outcome=SignalOutcome.PROCESSED,  # Will be updated later
                outcome_reason="processing",
                processed_by_instance=self.instance_id
            )

            audit_id = self.audit_service.create_audit_record(record)

            if audit_id:
                self._active_audits[fingerprint] = audit_id
                self._audit_start_times[audit_id] = start_time
                logger.debug(f"[AuditIntegration] Started audit for {fingerprint}, id={audit_id}")

            return audit_id

        except Exception as e:
            logger.error(f"[AuditIntegration] Failed to start signal audit: {e}")
            return None

    def add_validation(
        self,
        audit_id: int,
        condition_result: Optional[ConditionValidationResult] = None,
        execution_result: Optional[ExecutionValidationResult] = None
    ) -> bool:
        """
        Add validation results to the audit record.

        Args:
            audit_id: Audit ID from start_signal()
            condition_result: Result from condition validation
            execution_result: Result from execution validation

        Returns:
            True if update successful
        """
        try:
            validation_data = SignalValidator.create_validation_result_for_audit(
                condition_result,
                execution_result
            ) if condition_result else None

            if validation_data:
                return self.audit_service.update_validation_result(audit_id, validation_data)
            return True

        except Exception as e:
            logger.error(f"[AuditIntegration] Failed to add validation: {e}")
            return False

    def add_sizing(
        self,
        audit_id: int,
        sizing_data: Dict[str, Any]
    ) -> bool:
        """
        Add position sizing calculation to the audit record.

        Args:
            audit_id: Audit ID from start_signal()
            sizing_data: Sizing calculation data from position_sizer.create_sizing_data_for_audit()

        Returns:
            True if update successful
        """
        try:
            return self.audit_service.update_sizing_calculation(audit_id, sizing_data)
        except Exception as e:
            logger.error(f"[AuditIntegration] Failed to add sizing: {e}")
            return False

    def add_risk_assessment(
        self,
        audit_id: int,
        risk_data: Dict[str, Any]
    ) -> bool:
        """
        Add risk assessment to the audit record.

        Args:
            audit_id: Audit ID from start_signal()
            risk_data: Risk assessment data

        Returns:
            True if update successful
        """
        try:
            return self.audit_service.update_risk_assessment(audit_id, risk_data)
        except Exception as e:
            logger.error(f"[AuditIntegration] Failed to add risk assessment: {e}")
            return False

    def log_order_execution(
        self,
        audit_id: int,
        position_id: Optional[str],
        instrument: str,
        symbol: str,
        action: str,
        lots: int,
        quantity: int,
        order_type: str,
        signal_price: float,
        limit_price: float,
        execution_result: Any,
        exchange: str = "NFO"
    ) -> Optional[int]:
        """
        Log order execution and link to audit record.

        Args:
            audit_id: Audit ID from start_signal()
            position_id: Position being affected
            instrument: Instrument name
            symbol: Actual trading symbol
            action: BUY or SELL
            lots: Number of lots
            quantity: Order quantity
            order_type: Order type
            signal_price: Original signal price
            limit_price: Limit price sent to broker
            execution_result: Result from order executor
            exchange: Exchange code

        Returns:
            Order log ID or None
        """
        try:
            order_log_id = self.order_logger.log_simple_execution(
                signal_audit_id=audit_id,
                position_id=position_id,
                instrument=instrument,
                symbol=symbol,
                action=action,
                lots=lots,
                quantity=quantity,
                order_type=order_type,
                signal_price=signal_price,
                limit_price=limit_price,
                execution_result=execution_result,
                exchange=exchange
            )

            return order_log_id

        except Exception as e:
            logger.error(f"[AuditIntegration] Failed to log order execution: {e}")
            return None

    def log_synthetic_execution(
        self,
        audit_id: int,
        position_id: Optional[str],
        instrument: str,
        lots: int,
        signal_price: float,
        synthetic_result: Any,
        action: str = "BUY",
        lot_size: int = 30
    ) -> Optional[int]:
        """
        Log synthetic futures execution (2-leg order).

        Args:
            audit_id: Audit ID from start_signal()
            position_id: Position being affected
            instrument: Instrument name (BANK_NIFTY)
            lots: Number of lots
            signal_price: Signal price
            synthetic_result: SyntheticExecutionResult
            action: BUY or SELL
            lot_size: Lot size

        Returns:
            Parent order log ID or None
        """
        try:
            order_log_id = self.order_logger.log_synthetic_execution(
                signal_audit_id=audit_id,
                position_id=position_id,
                instrument=instrument,
                lots=lots,
                signal_price=signal_price,
                synthetic_result=synthetic_result,
                action=action,
                lot_size=lot_size
            )

            return order_log_id

        except Exception as e:
            logger.error(f"[AuditIntegration] Failed to log synthetic execution: {e}")
            return None

    def complete_signal(
        self,
        audit_id: int,
        outcome: SignalOutcome,
        outcome_reason: Optional[str] = None,
        order_log_id: Optional[int] = None,
        execution_result: Any = None,
        signal_price: Optional[float] = None
    ) -> bool:
        """
        Complete the signal audit record with final outcome.

        Call this at the end of process_signal().

        Args:
            audit_id: Audit ID from start_signal()
            outcome: Final signal outcome
            outcome_reason: Human-readable reason
            order_log_id: ID of order_execution_log entry
            execution_result: Result from order executor
            signal_price: Original signal price (for execution summary)

        Returns:
            True if update successful
        """
        try:
            # Calculate processing duration
            processing_duration_ms = None
            if audit_id in self._audit_start_times:
                processing_duration_ms = int(
                    (time.time() - self._audit_start_times[audit_id]) * 1000
                )
                del self._audit_start_times[audit_id]

            # Create order execution summary if we have results
            order_execution_data = None
            if execution_result and signal_price:
                order_execution_data = self.order_logger.create_execution_summary_for_audit(
                    order_log_id=order_log_id,
                    execution_result=execution_result,
                    signal_price=signal_price,
                    execution_time_ms=processing_duration_ms
                )

            # Update the audit record
            success = self.audit_service.update_outcome(
                audit_id=audit_id,
                outcome=outcome,
                outcome_reason=outcome_reason,
                processing_duration_ms=processing_duration_ms
            )

            # Update order execution data separately
            if order_execution_data:
                self.audit_service.update_order_execution(audit_id, order_execution_data)

            # Clean up fingerprint tracking
            for fingerprint, aid in list(self._active_audits.items()):
                if aid == audit_id:
                    del self._active_audits[fingerprint]
                    break

            logger.debug(
                f"[AuditIntegration] Completed audit {audit_id}: {outcome.value} "
                f"({processing_duration_ms}ms)"
            )

            return success

        except Exception as e:
            logger.error(f"[AuditIntegration] Failed to complete signal audit: {e}")
            return False

    def reject_signal(
        self,
        audit_id: int,
        outcome: SignalOutcome,
        reason: str
    ) -> bool:
        """
        Mark a signal as rejected.

        Convenience method for rejection cases.

        Args:
            audit_id: Audit ID from start_signal()
            outcome: Rejection outcome (REJECTED_VALIDATION, REJECTED_RISK, etc.)
            reason: Human-readable rejection reason

        Returns:
            True if update successful
        """
        return self.complete_signal(
            audit_id=audit_id,
            outcome=outcome,
            outcome_reason=reason
        )

    def get_fingerprint_audit_id(self, fingerprint: str) -> Optional[int]:
        """
        Get audit ID for a fingerprint if still active.

        Args:
            fingerprint: Signal fingerprint

        Returns:
            Audit ID or None if not found
        """
        return self._active_audits.get(fingerprint)

    # Convenience methods for common rejection outcomes

    def reject_validation_failure(
        self,
        audit_id: int,
        reason: str,
        condition_result: Optional[ConditionValidationResult] = None,
        execution_result: Optional[ExecutionValidationResult] = None
    ) -> bool:
        """Reject due to validation failure."""
        if condition_result or execution_result:
            self.add_validation(audit_id, condition_result, execution_result)
        return self.reject_signal(audit_id, SignalOutcome.REJECTED_VALIDATION, reason)

    def reject_risk_failure(self, audit_id: int, reason: str, risk_data: Optional[Dict] = None) -> bool:
        """Reject due to risk check failure."""
        if risk_data:
            self.add_risk_assessment(audit_id, risk_data)
        return self.reject_signal(audit_id, SignalOutcome.REJECTED_RISK, reason)

    def reject_duplicate(self, audit_id: int, reason: str = "duplicate_signal") -> bool:
        """Reject as duplicate signal."""
        return self.reject_signal(audit_id, SignalOutcome.REJECTED_DUPLICATE, reason)

    def reject_market_closed(self, audit_id: int, reason: str = "market_closed") -> bool:
        """Reject due to market being closed."""
        return self.reject_signal(audit_id, SignalOutcome.REJECTED_MARKET, reason)

    def reject_manual(self, audit_id: int, reason: str = "user_rejected") -> bool:
        """Reject due to manual user rejection."""
        return self.reject_signal(audit_id, SignalOutcome.REJECTED_MANUAL, reason)

    def mark_order_failed(self, audit_id: int, reason: str) -> bool:
        """Mark signal as failed during order execution."""
        return self.reject_signal(audit_id, SignalOutcome.FAILED_ORDER, reason)

    def mark_partial_fill(
        self,
        audit_id: int,
        reason: str,
        order_log_id: Optional[int] = None,
        execution_result: Any = None,
        signal_price: Optional[float] = None
    ) -> bool:
        """Mark signal as partially filled."""
        return self.complete_signal(
            audit_id=audit_id,
            outcome=SignalOutcome.PARTIAL_FILL,
            outcome_reason=reason,
            order_log_id=order_log_id,
            execution_result=execution_result,
            signal_price=signal_price
        )


def create_risk_assessment_data(
    equity: float,
    margin_available: float,
    margin_required: float,
    pre_trade_positions: int,
    post_trade_positions: int,
    checks_passed: list,
    checks_failed: list = None
) -> Dict[str, Any]:
    """
    Helper function to create risk assessment data structure.

    Args:
        equity: Current portfolio equity
        margin_available: Available margin
        margin_required: Margin required for this trade
        pre_trade_positions: Number of positions before trade
        post_trade_positions: Number of positions after trade
        checks_passed: List of passed risk checks
        checks_failed: List of failed risk checks

    Returns:
        Dictionary suitable for add_risk_assessment()
    """
    return {
        "equity": equity,
        "margin_available": margin_available,
        "margin_required": margin_required,
        "margin_utilization_pct": (margin_required / margin_available * 100) if margin_available > 0 else 0,
        "pre_trade_positions": pre_trade_positions,
        "post_trade_positions": post_trade_positions,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed or []
    }
