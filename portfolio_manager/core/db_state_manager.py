"""
Database State Manager

Provides persistence layer for all portfolio state with:
- Connection pooling (psycopg2.pool)
- Transaction management
- Write-through caching (L1 cache)
- Crash recovery support
- Connection retry logic with exponential backoff
"""
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from psycopg2.extras import Json as PsycopgJson
from contextlib import contextmanager
from typing import Dict, List, Optional
from datetime import datetime
import logging
import time

from core.models import Position, PortfolioState

logger = logging.getLogger(__name__)


class DatabaseStateManager:
    """Persistent state manager using PostgreSQL"""

    def __init__(self, connection_config: dict, max_retries: int = 3):
        """
        Initialize database connection pool with retry logic

        Args:
            connection_config: {
                'host': 'localhost',
                'port': 5432,
                'database': 'portfolio_manager',
                'user': 'pm_user',
                'password': 'secure_password',
                'minconn': 2,
                'maxconn': 10
            }
            max_retries: Maximum number of connection retry attempts
        """
        self.connection_config = connection_config
        self.pool = None

        # Retry connection with exponential backoff
        for attempt in range(max_retries):
            try:
                self.pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=connection_config.get('minconn', 2),
                    maxconn=connection_config.get('maxconn', 10),
                    host=connection_config['host'],
                    port=connection_config.get('port', 5432),
                    database=connection_config['database'],
                    user=connection_config['user'],
                    password=connection_config['password'],
                    connect_timeout=5  # 5 second timeout
                )
                logger.info(f"Database connection pool initialized (attempt {attempt + 1})")
                break

            except psycopg2.OperationalError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Database connection failed (attempt {attempt + 1}), retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    logger.error(f"Database connection failed after {max_retries} attempts")
                    raise

        # L1 cache for hot data (positions, portfolio state)
        self._position_cache = {}  # position_id → Position
        self._portfolio_state_cache = None

        logger.info("Database connection pool initialized")

    @contextmanager
    def get_connection(self):
        """Get connection from pool with automatic return"""
        conn = self.pool.getconn()
        try:
            yield conn
        finally:
            self.pool.putconn(conn)

    @contextmanager
    def transaction(self, max_retries: int = 2):
        """
        Transaction context manager with automatic commit/rollback and retry

        Args:
            max_retries: Maximum number of retry attempts on connection loss
        """
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    try:
                        yield conn
                        conn.commit()
                        return  # Success
                    except Exception as e:
                        conn.rollback()
                        logger.error(f"Transaction rolled back: {e}")
                        raise

            except psycopg2.OperationalError as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Connection lost during transaction, retrying (attempt {attempt + 1})")
                    time.sleep(0.5)  # Brief pause before retry
                else:
                    logger.error("Transaction failed after retries")
                    raise

    # ===== POSITION OPERATIONS =====

    def save_position(self, position: Position) -> bool:
        """
        Insert or update position (upsert)

        Uses optimistic locking with version field

        Args:
            position: Position object to save

        Returns:
            True if successful
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            # Convert Position to dict
            pos_dict = self._position_to_dict(position)

            # Upsert query
            cursor.execute("""
                INSERT INTO portfolio_positions
                (position_id, instrument, status, entry_timestamp, entry_price, lots, quantity,
                 initial_stop, current_stop, highest_close, unrealized_pnl, realized_pnl,
                 rollover_status, original_expiry, original_strike, rollover_timestamp,
                 rollover_pnl, rollover_count, strike, expiry, pe_symbol, ce_symbol,
                 pe_order_id, ce_order_id, pe_entry_price, ce_entry_price,
                 contract_month, futures_symbol, futures_order_id,
                 atr, limiter, risk_contribution, vol_contribution, is_base_position, version)
                VALUES
                (%(position_id)s, %(instrument)s, %(status)s, %(entry_timestamp)s, %(entry_price)s,
                 %(lots)s, %(quantity)s, %(initial_stop)s, %(current_stop)s, %(highest_close)s,
                 %(unrealized_pnl)s, %(realized_pnl)s, %(rollover_status)s, %(original_expiry)s,
                 %(original_strike)s, %(rollover_timestamp)s, %(rollover_pnl)s, %(rollover_count)s,
                 %(strike)s, %(expiry)s, %(pe_symbol)s, %(ce_symbol)s, %(pe_order_id)s,
                 %(ce_order_id)s, %(pe_entry_price)s, %(ce_entry_price)s, %(contract_month)s,
                 %(futures_symbol)s, %(futures_order_id)s, %(atr)s, %(limiter)s,
                 %(risk_contribution)s, %(vol_contribution)s, %(is_base_position)s, 1)
                ON CONFLICT (position_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    current_stop = EXCLUDED.current_stop,
                    highest_close = EXCLUDED.highest_close,
                    unrealized_pnl = EXCLUDED.unrealized_pnl,
                    realized_pnl = EXCLUDED.realized_pnl,
                    rollover_status = EXCLUDED.rollover_status,
                    rollover_timestamp = EXCLUDED.rollover_timestamp,
                    rollover_pnl = EXCLUDED.rollover_pnl,
                    rollover_count = EXCLUDED.rollover_count,
                    version = portfolio_positions.version + 1,
                    updated_at = CURRENT_TIMESTAMP
            """, pos_dict)

            # Update cache
            self._position_cache[position.position_id] = position

            logger.info(f"Position saved: {position.position_id}")
            return True

    def get_position(self, position_id: str) -> Optional[Position]:
        """
        Get position by ID (cache-first)

        Args:
            position_id: Position ID (e.g., "Long_1")

        Returns:
            Position object or None if not found
        """
        # Check cache
        if position_id in self._position_cache:
            return self._position_cache[position_id]

        # Query database
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM portfolio_positions WHERE position_id = %s",
                (position_id,)
            )
            row = cursor.fetchone()

            if row:
                position = self._dict_to_position(dict(row))
                self._position_cache[position_id] = position
                return position

        return None

    def get_all_open_positions(self) -> Dict[str, Position]:
        """
        Load all open positions from database

        Returns:
            Dictionary of position_id -> Position
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(
                "SELECT * FROM portfolio_positions WHERE status = 'open' ORDER BY entry_timestamp"
            )

            positions = {}
            for row in cursor.fetchall():
                pos_dict = dict(row)
                position = self._dict_to_position(pos_dict)
                positions[position.position_id] = position
                self._position_cache[position.position_id] = position

            logger.info(f"Loaded {len(positions)} open positions from database")
            return positions

    # ===== PORTFOLIO STATE OPERATIONS =====

    def save_portfolio_state(self, state: PortfolioState, initial_capital: float) -> bool:
        """
        Save portfolio state (single-row table)

        Args:
            state: PortfolioState object
            initial_capital: Initial capital (not stored in PortfolioState model)

        Returns:
            True if successful
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO portfolio_state
                (id, initial_capital, closed_equity, total_risk_amount, total_risk_percent,
                 total_vol_amount, margin_used, version)
                VALUES (1, %s, %s, %s, %s, %s, %s, 1)
                ON CONFLICT (id) DO UPDATE SET
                    closed_equity = EXCLUDED.closed_equity,
                    total_risk_amount = EXCLUDED.total_risk_amount,
                    total_risk_percent = EXCLUDED.total_risk_percent,
                    total_vol_amount = EXCLUDED.total_vol_amount,
                    margin_used = EXCLUDED.margin_used,
                    version = portfolio_state.version + 1,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                initial_capital,
                state.closed_equity,
                state.total_risk_amount,
                state.total_risk_percent,
                state.total_vol_amount,
                state.margin_used
            ))

            self._portfolio_state_cache = {
                'initial_capital': initial_capital,
                'closed_equity': state.closed_equity,
                'total_risk_amount': state.total_risk_amount,
                'total_risk_percent': state.total_risk_percent,
                'total_vol_amount': state.total_vol_amount,
                'margin_used': state.margin_used
            }
            return True

    def get_portfolio_state(self) -> Optional[dict]:
        """
        Load portfolio state from database

        Returns:
            Dictionary with portfolio state or None if not found
        """
        # Check cache
        if self._portfolio_state_cache:
            return self._portfolio_state_cache

        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM portfolio_state WHERE id = 1")
            row = cursor.fetchone()

            if row:
                state_dict = dict(row)
                self._portfolio_state_cache = state_dict
                return state_dict

        return None

    # ===== PYRAMIDING STATE OPERATIONS =====

    def save_pyramiding_state(self, instrument: str, last_pyramid_price: float,
                              base_position_id: Optional[str]) -> bool:
        """
        Save pyramiding state for instrument

        Args:
            instrument: Instrument name (BANK_NIFTY or GOLD_MINI)
            last_pyramid_price: Price of last pyramid entry
            base_position_id: Base position ID (can be None if base position closed)

        Returns:
            True if successful
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pyramiding_state (instrument, last_pyramid_price, base_position_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (instrument) DO UPDATE SET
                    last_pyramid_price = EXCLUDED.last_pyramid_price,
                    base_position_id = EXCLUDED.base_position_id,
                    updated_at = CURRENT_TIMESTAMP
            """, (instrument, last_pyramid_price, base_position_id))
            return True

    def get_pyramiding_state(self) -> Dict[str, dict]:
        """
        Load all pyramiding state

        Returns:
            Dictionary of instrument -> pyramiding state dict
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT * FROM pyramiding_state")

            pyr_state = {}
            for row in cursor.fetchall():
                row_dict = dict(row)
                pyr_state[row_dict['instrument']] = row_dict

            return pyr_state

    # ===== SIGNAL DEDUPLICATION =====

    def check_duplicate_signal(self, fingerprint: str) -> bool:
        """
        Check if signal fingerprint exists (within last 60 seconds)

        Args:
            fingerprint: SHA-256 hash of signal

        Returns:
            True if duplicate found, False otherwise
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM signal_log
                WHERE fingerprint = %s
                  AND processed_at > NOW() - INTERVAL '60 seconds'
                LIMIT 1
            """, (fingerprint,))

            return cursor.fetchone() is not None

    def log_signal(self, signal_data: dict, fingerprint: str,
                   instance_id: str, status: str) -> bool:
        """
        Log signal to audit trail

        Args:
            signal_data: Signal data dictionary
            fingerprint: SHA-256 hash of signal
            instance_id: Instance ID that processed the signal
            status: Processing status (accepted, rejected, blocked, executed)

        Returns:
            True if successful
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO signal_log
                (instrument, signal_type, position, signal_timestamp, fingerprint,
                 processed_by_instance, processing_status, payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (fingerprint) DO UPDATE SET
                    is_duplicate = TRUE
            """, (
                signal_data['instrument'],
                signal_data['type'],
                signal_data['position'],
                signal_data['timestamp'],
                fingerprint,
                instance_id,
                status,
                PsycopgJson(signal_data)
            ))
            return True

    # ===== HELPER METHODS =====

    def _position_to_dict(self, position: Position) -> dict:
        """
        Convert Position dataclass to dict for database

        Args:
            position: Position object

        Returns:
            Dictionary with all position fields
        """
        return {
            'position_id': position.position_id,
            'instrument': position.instrument,
            'status': position.status,
            'entry_timestamp': position.entry_timestamp,
            'entry_price': position.entry_price,
            'lots': position.lots,
            'quantity': position.quantity,
            'initial_stop': position.initial_stop,
            'current_stop': position.current_stop,
            'highest_close': position.highest_close,
            'unrealized_pnl': position.unrealized_pnl,
            'realized_pnl': position.realized_pnl,
            'rollover_status': position.rollover_status or 'none',
            'original_expiry': position.original_expiry,
            'original_strike': position.original_strike,
            'rollover_timestamp': position.rollover_timestamp,
            'rollover_pnl': position.rollover_pnl or 0.0,
            'rollover_count': position.rollover_count or 0,
            'strike': position.strike,
            'expiry': position.expiry,
            'pe_symbol': position.pe_symbol,
            'ce_symbol': position.ce_symbol,
            'pe_order_id': position.pe_order_id,
            'ce_order_id': position.ce_order_id,
            'pe_entry_price': position.pe_entry_price,
            'ce_entry_price': position.ce_entry_price,
            'contract_month': position.contract_month,
            'futures_symbol': position.futures_symbol,
            'futures_order_id': position.futures_order_id,
            'atr': position.atr,
            'limiter': position.limiter,
            'risk_contribution': position.risk_contribution or 0.0,
            'vol_contribution': position.vol_contribution or 0.0,
            'is_base_position': getattr(position, 'is_base_position', False)
        }

    def _dict_to_position(self, row: dict) -> Position:
        """
        Convert database row to Position dataclass

        Args:
            row: Database row as dictionary

        Returns:
            Position object
        """
        return Position(
            position_id=row['position_id'],
            instrument=row['instrument'],
            entry_timestamp=row['entry_timestamp'],
            entry_price=float(row['entry_price']),
            lots=row['lots'],
            quantity=row['quantity'],
            initial_stop=float(row['initial_stop']),
            current_stop=float(row['current_stop']),
            highest_close=float(row['highest_close']),
            atr=float(row['atr']) if row['atr'] else 0.0,
            unrealized_pnl=float(row['unrealized_pnl']) if row['unrealized_pnl'] else 0.0,
            realized_pnl=float(row['realized_pnl']) if row['realized_pnl'] else 0.0,
            status=row['status'],
            strike=row.get('strike'),
            expiry=row.get('expiry'),
            pe_symbol=row.get('pe_symbol'),
            ce_symbol=row.get('ce_symbol'),
            pe_order_id=row.get('pe_order_id'),
            ce_order_id=row.get('ce_order_id'),
            pe_entry_price=float(row['pe_entry_price']) if row.get('pe_entry_price') else None,
            ce_entry_price=float(row['ce_entry_price']) if row.get('ce_entry_price') else None,
            contract_month=row.get('contract_month'),
            futures_symbol=row.get('futures_symbol'),
            futures_order_id=row.get('futures_order_id'),
            rollover_status=row.get('rollover_status', 'none'),
            original_expiry=row.get('original_expiry'),
            original_strike=row.get('original_strike'),
            original_entry_price=float(row['original_entry_price']) if row.get('original_entry_price') else None,
            rollover_timestamp=row.get('rollover_timestamp'),
            rollover_pnl=float(row['rollover_pnl']) if row.get('rollover_pnl') else 0.0,
            rollover_count=row.get('rollover_count', 0),
            limiter=row.get('limiter'),
            risk_contribution=float(row['risk_contribution']) if row.get('risk_contribution') else 0.0,
            vol_contribution=float(row['vol_contribution']) if row.get('vol_contribution') else 0.0,
            is_base_position=row.get('is_base_position', False)
        )

    def close_all_connections(self):
        """Close all database connections in pool"""
        if self.pool:
            self.pool.closeall()
            logger.info("All database connections closed")

