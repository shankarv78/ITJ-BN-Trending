"""
Order Execution Logger

Logs detailed order execution information to the order_execution_log table.
Tracks:
- Order placement, fills, rejections
- Multi-leg orders (synthetic futures)
- Slippage calculation
- Timing metrics

Designed to integrate with SignalAuditService for complete audit trail.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, List

from psycopg2.extras import RealDictCursor, Json

logger = logging.getLogger(__name__)


@dataclass
class OrderLogEntry:
    """Data structure for order execution log entry"""
    # Links
    signal_audit_id: Optional[int] = None
    position_id: Optional[str] = None

    # Order identification
    order_id: Optional[str] = None
    broker_order_id: Optional[str] = None

    # Order details
    order_type: str = "LIMIT"  # SYNTHETIC_FUTURES, DIRECT_FUTURES, OPTION_BUY, OPTION_SELL, MARKET, LIMIT
    action: str = "BUY"  # BUY, SELL
    instrument: str = ""
    symbol: str = ""
    exchange: str = "NFO"

    # Quantity
    quantity: int = 0
    lots: int = 0

    # Pricing
    signal_price: Optional[float] = None
    limit_price: Optional[float] = None
    fill_price: Optional[float] = None
    slippage_pct: Optional[float] = None

    # Status
    order_status: str = "PENDING"  # PENDING, OPEN, COMPLETE, PARTIAL, REJECTED, CANCELLED, FAILED
    status_message: Optional[str] = None

    # Timing
    order_placed_at: Optional[datetime] = None
    order_filled_at: Optional[datetime] = None
    execution_duration_ms: Optional[int] = None

    # Multi-leg support
    parent_order_id: Optional[int] = None
    leg_number: Optional[int] = None

    # Raw data
    raw_response: Optional[Dict] = None

    def calculate_slippage(self):
        """Calculate slippage percentage"""
        if self.fill_price and self.signal_price and self.signal_price > 0:
            self.slippage_pct = (self.fill_price - self.signal_price) / self.signal_price


class OrderExecutionLogger:
    """
    Logs order execution details to database.

    Integrates with SignalAuditService and order executors.
    """

    def __init__(self, db_connection_pool):
        """
        Initialize order execution logger.

        Args:
            db_connection_pool: psycopg2 connection pool
        """
        self.pool = db_connection_pool
        logger.info("[OrderExecutionLogger] Initialized")

    def log_order(self, entry: OrderLogEntry) -> Optional[int]:
        """
        Log a single order execution entry.

        Args:
            entry: OrderLogEntry with order details

        Returns:
            Database ID of the logged entry, or None on failure
        """
        # Calculate slippage if not already done
        entry.calculate_slippage()

        query = """
            INSERT INTO order_execution_log (
                signal_audit_id, position_id,
                order_id, broker_order_id,
                order_type, action, instrument, symbol, exchange,
                quantity, lots,
                signal_price, limit_price, fill_price, slippage_pct,
                order_status, status_message,
                order_placed_at, order_filled_at, execution_duration_ms,
                parent_order_id, leg_number,
                raw_response
            ) VALUES (
                %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s,
                %s
            )
            RETURNING id
        """

        try:
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        entry.signal_audit_id, entry.position_id,
                        entry.order_id, entry.broker_order_id,
                        entry.order_type, entry.action, entry.instrument, entry.symbol, entry.exchange,
                        entry.quantity, entry.lots,
                        entry.signal_price, entry.limit_price, entry.fill_price, entry.slippage_pct,
                        entry.order_status, entry.status_message,
                        entry.order_placed_at, entry.order_filled_at, entry.execution_duration_ms,
                        entry.parent_order_id, entry.leg_number,
                        Json(entry.raw_response) if entry.raw_response else None
                    ))
                    result = cur.fetchone()
                    conn.commit()

                    log_id = result[0] if result else None
                    logger.debug(f"[OrderExecutionLogger] Logged order {entry.order_id}, db_id={log_id}")
                    return log_id
            finally:
                self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"[OrderExecutionLogger] Failed to log order: {e}")
            return None

    def log_simple_execution(
        self,
        signal_audit_id: Optional[int],
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
        Log a simple (non-synthetic) order execution.

        Args:
            signal_audit_id: Link to signal_audit record
            position_id: Position ID being affected
            instrument: Instrument name (BANK_NIFTY, GOLD_MINI, etc.)
            symbol: Actual trading symbol
            action: BUY or SELL
            lots: Number of lots
            quantity: Order quantity
            order_type: LIMIT, MARKET, DIRECT_FUTURES
            signal_price: Price from signal
            limit_price: Limit price sent to broker
            execution_result: ExecutionResult from order executor
            exchange: Exchange code

        Returns:
            Database ID of logged entry
        """
        entry = OrderLogEntry(
            signal_audit_id=signal_audit_id,
            position_id=position_id,
            order_id=str(execution_result.order_id) if execution_result.order_id else None,
            broker_order_id=str(execution_result.order_id) if execution_result.order_id else None,
            order_type=order_type,
            action=action,
            instrument=instrument,
            symbol=symbol,
            exchange=exchange,
            quantity=quantity,
            lots=lots,
            signal_price=signal_price,
            limit_price=limit_price,
            fill_price=execution_result.execution_price,
            order_status=self._map_execution_status(execution_result.status.value if hasattr(execution_result.status, 'value') else str(execution_result.status)),
            status_message=execution_result.rejection_reason or execution_result.notes if hasattr(execution_result, 'notes') else None,
            order_placed_at=datetime.now(),
            order_filled_at=datetime.now() if execution_result.execution_price else None,
            raw_response={"attempts": execution_result.attempts if hasattr(execution_result, 'attempts') else 1}
        )
        entry.calculate_slippage()

        return self.log_order(entry)

    def log_synthetic_execution(
        self,
        signal_audit_id: Optional[int],
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

        Creates a parent entry and child entries for PE/CE legs.

        Args:
            signal_audit_id: Link to signal_audit record
            position_id: Position ID being affected
            instrument: Instrument name (BANK_NIFTY)
            lots: Number of lots
            signal_price: Price from signal
            synthetic_result: SyntheticExecutionResult from executor
            action: BUY or SELL
            lot_size: Lot size for the instrument

        Returns:
            Database ID of parent order entry
        """
        quantity = lots * lot_size

        # Calculate synthetic fill price
        synthetic_fill_price = None
        if hasattr(synthetic_result, 'get_synthetic_price'):
            synthetic_fill_price = synthetic_result.get_synthetic_price()

        # Create parent entry
        parent_entry = OrderLogEntry(
            signal_audit_id=signal_audit_id,
            position_id=position_id,
            order_id=f"SYNTH_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            order_type="SYNTHETIC_FUTURES",
            action=action,
            instrument=instrument,
            symbol=f"{instrument}_SYNTHETIC",
            exchange="NFO",
            quantity=quantity,
            lots=lots,
            signal_price=signal_price,
            fill_price=synthetic_fill_price,
            order_status=self._map_execution_status(synthetic_result.status.value if hasattr(synthetic_result.status, 'value') else str(synthetic_result.status)),
            status_message=synthetic_result.notes if hasattr(synthetic_result, 'notes') else None,
            order_placed_at=datetime.now(),
            order_filled_at=datetime.now() if synthetic_fill_price else None,
            raw_response={
                "strike": synthetic_result.strike if hasattr(synthetic_result, 'strike') else None,
                "rollback_performed": synthetic_result.rollback_performed if hasattr(synthetic_result, 'rollback_performed') else False,
                "rollback_success": synthetic_result.rollback_success if hasattr(synthetic_result, 'rollback_success') else False
            }
        )
        parent_entry.calculate_slippage()

        parent_id = self.log_order(parent_entry)

        if parent_id:
            # Log PE leg
            if hasattr(synthetic_result, 'pe_result') and synthetic_result.pe_result:
                pe_result = synthetic_result.pe_result
                pe_action = "SELL" if action == "BUY" else "BUY"
                pe_entry = OrderLogEntry(
                    signal_audit_id=signal_audit_id,
                    position_id=position_id,
                    order_id=pe_result.order_id if pe_result.order_id else None,
                    broker_order_id=pe_result.order_id if pe_result.order_id else None,
                    order_type="OPTION_SELL" if pe_action == "SELL" else "OPTION_BUY",
                    action=pe_action,
                    instrument=instrument,
                    symbol=synthetic_result.pe_symbol if hasattr(synthetic_result, 'pe_symbol') else (pe_result.symbol if hasattr(pe_result, 'symbol') else ""),
                    exchange="NFO",
                    quantity=quantity,
                    lots=lots,
                    fill_price=pe_result.fill_price if pe_result.fill_price else None,
                    order_status="COMPLETE" if pe_result.success else "FAILED",
                    status_message=pe_result.error if hasattr(pe_result, 'error') else None,
                    order_placed_at=datetime.now(),
                    order_filled_at=datetime.now() if pe_result.fill_price else None,
                    parent_order_id=parent_id,
                    leg_number=1
                )
                self.log_order(pe_entry)

            # Log CE leg
            if hasattr(synthetic_result, 'ce_result') and synthetic_result.ce_result:
                ce_result = synthetic_result.ce_result
                ce_action = "BUY" if action == "BUY" else "SELL"
                ce_entry = OrderLogEntry(
                    signal_audit_id=signal_audit_id,
                    position_id=position_id,
                    order_id=ce_result.order_id if ce_result.order_id else None,
                    broker_order_id=ce_result.order_id if ce_result.order_id else None,
                    order_type="OPTION_BUY" if ce_action == "BUY" else "OPTION_SELL",
                    action=ce_action,
                    instrument=instrument,
                    symbol=synthetic_result.ce_symbol if hasattr(synthetic_result, 'ce_symbol') else (ce_result.symbol if hasattr(ce_result, 'symbol') else ""),
                    exchange="NFO",
                    quantity=quantity,
                    lots=lots,
                    fill_price=ce_result.fill_price if ce_result.fill_price else None,
                    order_status="COMPLETE" if ce_result.success else "FAILED",
                    status_message=ce_result.error if hasattr(ce_result, 'error') else None,
                    order_placed_at=datetime.now(),
                    order_filled_at=datetime.now() if ce_result.fill_price else None,
                    parent_order_id=parent_id,
                    leg_number=2
                )
                self.log_order(ce_entry)

        return parent_id

    def update_order_status(
        self,
        log_id: int,
        order_status: str,
        fill_price: Optional[float] = None,
        status_message: Optional[str] = None,
        broker_order_id: Optional[str] = None
    ) -> bool:
        """
        Update an existing order log entry.

        Args:
            log_id: Database ID of the order log entry
            order_status: New status
            fill_price: Fill price if filled
            status_message: Status message
            broker_order_id: Broker's order ID if now known

        Returns:
            True if update successful
        """
        query = """
            UPDATE order_execution_log
            SET order_status = %s,
                fill_price = COALESCE(%s, fill_price),
                status_message = COALESCE(%s, status_message),
                broker_order_id = COALESCE(%s, broker_order_id),
                order_filled_at = CASE WHEN %s IS NOT NULL THEN CURRENT_TIMESTAMP ELSE order_filled_at END,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """

        try:
            conn = self.pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute(query, (
                        order_status,
                        fill_price,
                        status_message,
                        broker_order_id,
                        fill_price,  # For CASE condition
                        log_id
                    ))
                    conn.commit()
                    return cur.rowcount > 0
            finally:
                self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"[OrderExecutionLogger] Failed to update order status: {e}")
            return False

    def get_recent_orders(
        self,
        limit: int = 20,
        instrument: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[Dict]:
        """
        Get recent order executions.

        Args:
            limit: Maximum number of orders to return
            instrument: Filter by instrument
            status: Filter by status

        Returns:
            List of order execution records
        """
        query = """
            SELECT *
            FROM order_execution_log
            WHERE (%s IS NULL OR instrument = %s)
              AND (%s IS NULL OR order_status = %s)
            ORDER BY order_placed_at DESC
            LIMIT %s
        """

        try:
            conn = self.pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (instrument, instrument, status, status, limit))
                    rows = cur.fetchall()
                    return [dict(row) for row in rows]
            finally:
                self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"[OrderExecutionLogger] Failed to get recent orders: {e}")
            return []

    def get_order_by_id(self, log_id: int) -> Optional[Dict]:
        """
        Get order by database ID.

        Args:
            log_id: Database ID

        Returns:
            Order record or None
        """
        query = "SELECT * FROM order_execution_log WHERE id = %s"

        try:
            conn = self.pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (log_id,))
                    row = cur.fetchone()
                    return dict(row) if row else None
            finally:
                self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"[OrderExecutionLogger] Failed to get order: {e}")
            return None

    def get_orders_by_signal(self, signal_audit_id: int) -> List[Dict]:
        """
        Get all orders linked to a signal audit record.

        Args:
            signal_audit_id: Signal audit ID

        Returns:
            List of order records
        """
        query = """
            SELECT *
            FROM order_execution_log
            WHERE signal_audit_id = %s
            ORDER BY leg_number NULLS FIRST, created_at
        """

        try:
            conn = self.pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (signal_audit_id,))
                    rows = cur.fetchall()
                    return [dict(row) for row in rows]
            finally:
                self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"[OrderExecutionLogger] Failed to get orders by signal: {e}")
            return []

    def get_slippage_stats(
        self,
        days: int = 30,
        instrument: Optional[str] = None
    ) -> Dict:
        """
        Get slippage statistics for analysis.

        Args:
            days: Number of days to analyze
            instrument: Filter by instrument

        Returns:
            Statistics dictionary
        """
        query = """
            SELECT
                instrument,
                order_type,
                COUNT(*) as order_count,
                AVG(slippage_pct) as avg_slippage_pct,
                MIN(slippage_pct) as min_slippage_pct,
                MAX(slippage_pct) as max_slippage_pct,
                STDDEV(slippage_pct) as stddev_slippage_pct,
                AVG(execution_duration_ms) as avg_duration_ms
            FROM order_execution_log
            WHERE created_at > NOW() - INTERVAL '%s days'
              AND order_status = 'COMPLETE'
              AND slippage_pct IS NOT NULL
              AND (%s IS NULL OR instrument = %s)
            GROUP BY instrument, order_type
            ORDER BY instrument, order_type
        """

        try:
            conn = self.pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(query, (days, instrument, instrument))
                    rows = cur.fetchall()
                    return {
                        "period_days": days,
                        "instrument_filter": instrument,
                        "statistics": [dict(row) for row in rows]
                    }
            finally:
                self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"[OrderExecutionLogger] Failed to get slippage stats: {e}")
            return {"period_days": days, "statistics": []}

    def _map_execution_status(self, status: str) -> str:
        """
        Map executor status to database status.

        Args:
            status: Status from executor

        Returns:
            Database-compatible status
        """
        status_map = {
            "executed": "COMPLETE",
            "rejected": "REJECTED",
            "timeout": "CANCELLED",
            "partial": "PARTIAL",
            "EXECUTED": "COMPLETE",
            "REJECTED": "REJECTED",
            "TIMEOUT": "CANCELLED",
            "PARTIAL": "PARTIAL",
            "ExecutionStatus.EXECUTED": "COMPLETE",
            "ExecutionStatus.REJECTED": "REJECTED",
            "ExecutionStatus.TIMEOUT": "CANCELLED",
            "ExecutionStatus.PARTIAL": "PARTIAL"
        }
        return status_map.get(status, status.upper())

    def create_execution_summary_for_audit(
        self,
        order_log_id: Optional[int],
        execution_result: Any,
        signal_price: float,
        execution_time_ms: Optional[int] = None
    ) -> Dict:
        """
        Create order execution summary for signal_audit.order_execution JSONB.

        Args:
            order_log_id: ID of order_execution_log entry
            execution_result: ExecutionResult or SyntheticExecutionResult
            signal_price: Original signal price
            execution_time_ms: Execution duration in milliseconds

        Returns:
            Dictionary suitable for signal_audit.order_execution JSONB
        """
        # Handle different result types
        if hasattr(execution_result, 'get_synthetic_price'):
            # SyntheticExecutionResult
            fill_price = execution_result.get_synthetic_price() or signal_price
            order_type = "SYNTHETIC_FUTURES"
            order_id = f"SYNTH_{datetime.now().strftime('%Y%m%d%H%M%S')}"

            legs = []
            if hasattr(execution_result, 'pe_result') and execution_result.pe_result:
                legs.append({
                    "leg": "PE",
                    "order_id": execution_result.pe_result.order_id,
                    "fill_price": execution_result.pe_result.fill_price,
                    "success": execution_result.pe_result.success
                })
            if hasattr(execution_result, 'ce_result') and execution_result.ce_result:
                legs.append({
                    "leg": "CE",
                    "order_id": execution_result.ce_result.order_id,
                    "fill_price": execution_result.ce_result.fill_price,
                    "success": execution_result.ce_result.success
                })
        else:
            # ExecutionResult
            fill_price = execution_result.execution_price or signal_price
            order_type = "DIRECT"
            order_id = str(execution_result.order_id) if execution_result.order_id else None
            legs = []

        # Calculate slippage
        slippage_pct = None
        if fill_price and signal_price and signal_price > 0:
            slippage_pct = (fill_price - signal_price) / signal_price

        # Determine execution status
        status = execution_result.status
        if hasattr(status, 'value'):
            status_str = status.value.upper()
        else:
            status_str = str(status).upper()

        execution_status = "SUCCESS" if status_str in ["EXECUTED", "COMPLETE"] else (
            "PARTIAL" if status_str == "PARTIAL" else "FAILED"
        )

        result = {
            "order_log_id": order_log_id,
            "order_id": order_id,
            "order_type": order_type,
            "execution_status": execution_status,
            "signal_price": signal_price,
            "fill_price": fill_price,
            "slippage_pct": round(slippage_pct, 6) if slippage_pct else None,
            "execution_time_ms": execution_time_ms
        }

        if legs:
            result["legs"] = legs

        # Add error message if failed
        if execution_status == "FAILED":
            result["error_message"] = execution_result.rejection_reason if hasattr(execution_result, 'rejection_reason') else str(execution_result)

        return result
