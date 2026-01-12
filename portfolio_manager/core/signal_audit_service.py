"""
Signal Audit Service

Provides comprehensive audit trail for all signals received by Portfolio Manager.
Records:
- Signal outcomes (processed, rejected, failed)
- Rejection reasons with context data
- Validation results
- Position sizing calculations
- Risk assessments
- Order execution details

Designed for:
- Post-trade analysis
- Debugging signal rejections
- Compliance/audit requirements
- Telegram bot queries
"""

import logging
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Any, List
from enum import Enum

from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class SignalOutcome(Enum):
    """Possible outcomes for signal processing"""
    PROCESSED = 'PROCESSED'                     # Signal accepted, order placed
    REJECTED_VALIDATION = 'REJECTED_VALIDATION' # Failed signal validation
    REJECTED_RISK = 'REJECTED_RISK'             # Failed risk checks
    REJECTED_DUPLICATE = 'REJECTED_DUPLICATE'   # Duplicate signal
    REJECTED_MARKET = 'REJECTED_MARKET'         # Market closed/holiday
    REJECTED_MANUAL = 'REJECTED_MANUAL'         # User rejected via prompt
    FAILED_ORDER = 'FAILED_ORDER'               # Order placement failed
    PARTIAL_FILL = 'PARTIAL_FILL'               # Order partially filled


@dataclass
class ValidationResultData:
    """Structured validation result data"""
    is_valid: bool
    severity: str = "NORMAL"  # NORMAL, WARNING, ELEVATED, REJECTED
    signal_age_seconds: Optional[float] = None
    divergence_pct: Optional[float] = None
    risk_increase_pct: Optional[float] = None
    direction: Optional[str] = None  # favorable, unfavorable
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SizingCalculationData:
    """Structured position sizing calculation data"""
    method: str = "TOM_BASSO"

    # Inputs
    equity_high: Optional[float] = None
    risk_percent: Optional[float] = None
    stop_distance: Optional[float] = None
    lot_size: Optional[int] = None
    point_value: Optional[float] = None
    efficiency_ratio: Optional[float] = None
    atr: Optional[float] = None

    # Calculation steps
    risk_amount: Optional[float] = None
    raw_lots: Optional[float] = None
    er_adjusted_lots: Optional[float] = None
    final_lots: Optional[int] = None

    # Constraints
    constraints_applied: List[Dict[str, Any]] = field(default_factory=list)
    limiter: Optional[str] = None  # RISK, VOLATILITY, MARGIN

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "method": self.method,
            "inputs": {},
            "calculation": {},
            "constraints_applied": self.constraints_applied,
            "limiter": self.limiter
        }

        # Build inputs
        for key in ['equity_high', 'risk_percent', 'stop_distance', 'lot_size',
                    'point_value', 'efficiency_ratio', 'atr']:
            val = getattr(self, key)
            if val is not None:
                result["inputs"][key] = val

        # Build calculation
        for key in ['risk_amount', 'raw_lots', 'er_adjusted_lots', 'final_lots']:
            val = getattr(self, key)
            if val is not None:
                result["calculation"][key] = val

        return result


@dataclass
class RiskAssessmentData:
    """Structured risk assessment data"""
    pre_trade_risk_pct: Optional[float] = None
    post_trade_risk_pct: Optional[float] = None
    margin_available: Optional[float] = None
    margin_required: Optional[float] = None
    margin_utilization_pct: Optional[float] = None
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class OrderExecutionData:
    """Structured order execution summary data"""
    order_id: Optional[str] = None
    order_type: Optional[str] = None  # SYNTHETIC_FUTURES, DIRECT_FUTURES
    execution_status: Optional[str] = None  # SUCCESS, FAILED, PARTIAL
    signal_price: Optional[float] = None
    execution_price: Optional[float] = None
    fill_price: Optional[float] = None
    slippage_pct: Optional[float] = None
    execution_time_ms: Optional[int] = None
    legs: List[Dict[str, Any]] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SignalAuditRecord:
    """Complete signal audit record"""
    # Required fields
    signal_fingerprint: str
    instrument: str
    signal_type: str
    position: str
    signal_timestamp: datetime
    received_at: datetime
    outcome: SignalOutcome

    # Optional context
    outcome_reason: Optional[str] = None
    signal_log_id: Optional[int] = None

    # Structured data (will be stored as JSONB)
    validation_result: Optional[ValidationResultData] = None
    sizing_calculation: Optional[SizingCalculationData] = None
    risk_assessment: Optional[RiskAssessmentData] = None
    order_execution: Optional[OrderExecutionData] = None

    # Metadata
    processing_duration_ms: Optional[int] = None
    processed_by_instance: Optional[str] = None


class SignalAuditService:
    """
    Service for managing signal audit trail.

    Usage:
        audit_service = SignalAuditService(db_manager)

        # Record a processed signal
        record = SignalAuditRecord(
            signal_fingerprint="abc123",
            instrument="BANK_NIFTY",
            signal_type="ENTRY",
            position="LONG",
            signal_timestamp=datetime.now(),
            received_at=datetime.now(),
            outcome=SignalOutcome.PROCESSED,
            sizing_calculation=SizingCalculationData(...)
        )
        audit_id = audit_service.create_audit_record(record)

        # Query for Telegram bot
        recent = audit_service.get_recent_signals(limit=10)
    """

    def __init__(self, db_manager):
        """
        Initialize with database manager.

        Args:
            db_manager: DatabaseStateManager instance with connection pool
        """
        self.db = db_manager
        logger.info("[AUDIT] SignalAuditService initialized")

    def create_audit_record(self, record: SignalAuditRecord) -> Optional[int]:
        """
        Insert a new signal audit record.

        Args:
            record: SignalAuditRecord with all relevant data

        Returns:
            Audit record ID if successful, None if failed
        """
        try:
            with self.db.transaction() as conn:
                with conn.cursor() as cursor:
                    query = """
                        INSERT INTO signal_audit (
                            signal_log_id, signal_fingerprint, instrument, signal_type,
                            position, signal_timestamp, received_at, outcome, outcome_reason,
                            validation_result, sizing_calculation, risk_assessment,
                            order_execution, processing_duration_ms, processed_by_instance
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        RETURNING id
                    """

                    params = (
                        record.signal_log_id,
                        record.signal_fingerprint,
                        record.instrument,
                        record.signal_type,
                        record.position,
                        record.signal_timestamp,
                        record.received_at,
                        record.outcome.value,
                        record.outcome_reason,
                        json.dumps(record.validation_result.to_dict()) if record.validation_result else None,
                        json.dumps(record.sizing_calculation.to_dict()) if record.sizing_calculation else None,
                        json.dumps(record.risk_assessment.to_dict()) if record.risk_assessment else None,
                        json.dumps(record.order_execution.to_dict()) if record.order_execution else None,
                        record.processing_duration_ms,
                        record.processed_by_instance
                    )

                    cursor.execute(query, params)
                    result = cursor.fetchone()
                    audit_id = result[0] if result else None

                    conn.commit()

                    logger.info(
                        f"[AUDIT] Created audit record {audit_id}: "
                        f"{record.instrument} {record.signal_type} -> {record.outcome.value}"
                    )
                    return audit_id

        except Exception as e:
            logger.error(f"[AUDIT] Failed to create audit record: {e}")
            return None

    def update_order_execution(
        self,
        audit_id: int,
        order_execution: OrderExecutionData
    ) -> bool:
        """
        Update order execution details for an existing audit record.

        Use this when order execution completes after initial audit record creation.

        Args:
            audit_id: Signal audit record ID
            order_execution: Order execution data

        Returns:
            True if update successful
        """
        try:
            with self.db.transaction() as conn:
                with conn.cursor() as cursor:
                    query = """
                        UPDATE signal_audit
                        SET order_execution = %s
                        WHERE id = %s
                    """
                    cursor.execute(query, (
                        json.dumps(order_execution.to_dict()),
                        audit_id
                    ))
                    conn.commit()

                    logger.debug(f"[AUDIT] Updated order execution for audit {audit_id}")
                    return True

        except Exception as e:
            logger.error(f"[AUDIT] Failed to update order execution: {e}")
            return False

    def update_outcome(
        self,
        audit_id: int,
        outcome: SignalOutcome,
        outcome_reason: Optional[str] = None
    ) -> bool:
        """
        Update outcome for an existing audit record.

        Use this when outcome changes (e.g., PROCESSED -> FAILED_ORDER).

        Args:
            audit_id: Signal audit record ID
            outcome: New outcome
            outcome_reason: Optional reason text

        Returns:
            True if update successful
        """
        try:
            with self.db.transaction() as conn:
                with conn.cursor() as cursor:
                    query = """
                        UPDATE signal_audit
                        SET outcome = %s, outcome_reason = %s
                        WHERE id = %s
                    """
                    cursor.execute(query, (outcome.value, outcome_reason, audit_id))
                    conn.commit()

                    logger.info(f"[AUDIT] Updated outcome for audit {audit_id} to {outcome.value}")
                    return True

        except Exception as e:
            logger.error(f"[AUDIT] Failed to update outcome: {e}")
            return False

    def get_audit_by_id(self, audit_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve full audit record by ID.

        Args:
            audit_id: Signal audit record ID

        Returns:
            Dict with all audit fields, or None if not found
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT * FROM signal_audit WHERE id = %s",
                        (audit_id,)
                    )
                    row = cursor.fetchone()
                    return dict(row) if row else None

        except Exception as e:
            logger.error(f"[AUDIT] Failed to get audit by ID: {e}")
            return None

    def get_audit_by_fingerprint(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve full audit record by signal fingerprint.

        Args:
            fingerprint: Signal fingerprint (hash)

        Returns:
            Dict with all audit fields, or None if not found
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "SELECT * FROM signal_audit WHERE signal_fingerprint = %s",
                        (fingerprint,)
                    )
                    row = cursor.fetchone()
                    return dict(row) if row else None

        except Exception as e:
            logger.error(f"[AUDIT] Failed to get audit by fingerprint: {e}")
            return None

    def get_recent_signals(
        self,
        limit: int = 10,
        instrument: Optional[str] = None,
        outcome: Optional[SignalOutcome] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent signal audit records.

        Used by Telegram bot /signals command.

        Args:
            limit: Maximum number of records to return
            instrument: Filter by instrument (optional)
            outcome: Filter by outcome (optional)

        Returns:
            List of audit records (most recent first)
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    conditions = []
                    params = []

                    if instrument:
                        conditions.append("instrument = %s")
                        params.append(instrument)

                    if outcome:
                        conditions.append("outcome = %s")
                        params.append(outcome.value)

                    where_clause = ""
                    if conditions:
                        where_clause = "WHERE " + " AND ".join(conditions)

                    query = f"""
                        SELECT id, signal_fingerprint, instrument, signal_type,
                               position, signal_timestamp, outcome, outcome_reason,
                               processing_duration_ms, created_at
                        FROM signal_audit
                        {where_clause}
                        ORDER BY created_at DESC
                        LIMIT %s
                    """
                    params.append(limit)

                    cursor.execute(query, params)
                    rows = cursor.fetchall()
                    return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"[AUDIT] Failed to get recent signals: {e}")
            return []

    def get_signals_today(self) -> List[Dict[str, Any]]:
        """
        Get all signals from today.

        Used by Telegram bot for daily summary.

        Returns:
            List of today's audit records
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT id, signal_fingerprint, instrument, signal_type,
                               position, signal_timestamp, outcome, outcome_reason,
                               processing_duration_ms, created_at
                        FROM signal_audit
                        WHERE DATE(created_at) = CURRENT_DATE
                        ORDER BY created_at DESC
                    """)
                    rows = cursor.fetchall()
                    return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"[AUDIT] Failed to get today's signals: {e}")
            return []

    def get_signal_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        Get signal statistics for the past N days.

        Used by Telegram bot for /stats command.

        Args:
            days: Number of days to include

        Returns:
            Dict with statistics
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        SELECT
                            COUNT(*) as total_signals,
                            COUNT(*) FILTER (WHERE outcome = 'PROCESSED') as processed,
                            COUNT(*) FILTER (WHERE outcome LIKE 'REJECTED%%') as rejected,
                            COUNT(*) FILTER (WHERE outcome = 'FAILED_ORDER') as failed,
                            COUNT(DISTINCT instrument) as instruments,
                            AVG(processing_duration_ms) as avg_processing_ms
                        FROM signal_audit
                        WHERE created_at > NOW() - INTERVAL '%s days'
                    """, (days,))

                    row = cursor.fetchone()
                    if row:
                        stats = dict(row)
                        # Calculate rates
                        total = stats.get('total_signals', 0) or 0
                        if total > 0:
                            stats['processed_rate'] = (stats.get('processed', 0) or 0) / total
                            stats['rejection_rate'] = (stats.get('rejected', 0) or 0) / total
                        else:
                            stats['processed_rate'] = 0
                            stats['rejection_rate'] = 0
                        return stats
                    return {}

        except Exception as e:
            logger.error(f"[AUDIT] Failed to get signal stats: {e}")
            return {}

    def get_rejection_reasons(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get breakdown of rejection reasons.

        Used for analyzing why signals are being rejected.

        Args:
            days: Number of days to include

        Returns:
            List of {outcome, count, percentage}
        """
        try:
            with self.db.get_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        WITH totals AS (
                            SELECT COUNT(*) as total
                            FROM signal_audit
                            WHERE created_at > NOW() - INTERVAL '%s days'
                        )
                        SELECT
                            outcome,
                            COUNT(*) as count,
                            ROUND(COUNT(*)::numeric / NULLIF(t.total, 0) * 100, 1) as percentage
                        FROM signal_audit, totals t
                        WHERE created_at > NOW() - INTERVAL '%s days'
                        GROUP BY outcome, t.total
                        ORDER BY count DESC
                    """, (days, days))

                    rows = cursor.fetchall()
                    return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"[AUDIT] Failed to get rejection reasons: {e}")
            return []


# Convenience function for quick audit recording
def record_signal_audit(
    db_manager,
    signal,  # Signal object from core.models
    outcome: SignalOutcome,
    outcome_reason: Optional[str] = None,
    validation_result: Optional[ValidationResultData] = None,
    sizing_calculation: Optional[SizingCalculationData] = None,
    risk_assessment: Optional[RiskAssessmentData] = None,
    order_execution: Optional[OrderExecutionData] = None,
    processing_duration_ms: Optional[int] = None,
    instance_id: Optional[str] = None
) -> Optional[int]:
    """
    Convenience function to record signal audit in one call.

    Args:
        db_manager: DatabaseStateManager instance
        signal: Signal object from core.models
        outcome: Signal outcome
        outcome_reason: Reason for outcome
        validation_result: Validation data
        sizing_calculation: Position sizing data
        risk_assessment: Risk check data
        order_execution: Order execution data
        processing_duration_ms: Processing time
        instance_id: PM instance identifier

    Returns:
        Audit record ID if successful
    """
    service = SignalAuditService(db_manager)

    record = SignalAuditRecord(
        signal_fingerprint=getattr(signal, 'fingerprint', str(hash(str(signal)))),
        instrument=signal.instrument,
        signal_type=signal.signal_type.value if hasattr(signal.signal_type, 'value') else str(signal.signal_type),
        position=signal.position,
        signal_timestamp=signal.timestamp if hasattr(signal, 'timestamp') else datetime.now(),
        received_at=datetime.now(),
        outcome=outcome,
        outcome_reason=outcome_reason,
        validation_result=validation_result,
        sizing_calculation=sizing_calculation,
        risk_assessment=risk_assessment,
        order_execution=order_execution,
        processing_duration_ms=processing_duration_ms,
        processed_by_instance=instance_id
    )

    return service.create_audit_record(record)
