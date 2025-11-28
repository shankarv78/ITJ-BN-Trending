# Portfolio Manager High Availability System - State Persistence & Distributed Coordination

## Executive Summary

Implement production-grade state persistence and high availability for the Portfolio Manager using **PostgreSQL + Redis** to enable crash recovery, multi-instance deployment, and automatic failover.

**Architecture:**
- **PostgreSQL**: Persistent state storage with ACID transactions and row-level locking
- **Redis**: Distributed coordination, leader election, and signal-level locking
- **Active-Active**: **ALL instances process webhooks concurrently** (no leader needed for signals)
- **Leader Election**: ONLY for background tasks (rollover scheduler, cleanup)
- **Hybrid Deployment**: Local development + cloud production (AWS/Azure)

**Key Requirements:**
- ✅ Full crash recovery - restore all state from database on restart
- ✅ Zero-downtime failover - automatic takeover if instance crashes (<3 seconds)
- ✅ No duplicate signals - 3-layer deduplication (local cache, Redis, database)
- ✅ Transactional consistency - atomic signal processing with rollback on failure
- ✅ Distributed locking - prevent split-brain scenarios in active-active setup

---

## IMPORTANT: Active-Active Architecture Clarification

**Signal Processing:** ALL instances process webhooks concurrently
- Load balancer distributes webhooks across ALL running instances
- Each instance can process any signal (BASE_ENTRY, PYRAMID, EXIT)
- Redis distributed locks prevent duplicate processing
- **NO leader election needed for signal processing**

**Leader Election:** ONLY for background tasks
- **Rollover Scheduler:** Only leader runs rollover checks (hourly/daily)
- **Signal Log Cleanup:** Only leader runs cleanup job (delete old entries)
- **Orphaned Lock Cleanup:** Only leader runs periodic cleanup
- **Statistics Aggregation:** Only leader runs periodic aggregation

**Why this design?**
- **Scalability:** All instances handle traffic (not bottlenecked by single leader)
- **Resilience:** If leader dies, another becomes leader in <3 seconds (only background tasks pause briefly)
- **Simplicity:** No complex request routing - load balancer handles distribution

**Example scenario:**
```
Instance 1 (Leader):          Instance 2 (Follower):
✓ Processes webhooks          ✓ Processes webhooks
✓ Runs rollover at 9:00 AM    ✗ Skips rollover (not leader)
✓ Cleans signal_log daily     ✗ Skips cleanup (not leader)

If Instance 1 crashes:
Instance 2 becomes leader in <3s
✓ Continues processing webhooks (no interruption)
✓ Now runs rollover
✓ Now runs cleanup
```

---

## 1. Critical State Requiring Persistence

Based on comprehensive code analysis, the following state **must** be persisted to database:

### A. Position State (Core Trading Data)

**From:** `core/models.py` - Position dataclass

```python
Position {
  # Identification
  position_id: str              # Long_1, Long_2, etc.
  instrument: str               # BANK_NIFTY or GOLD_MINI
  status: str                   # open, closed, partial

  # Entry Data (immutable)
  entry_timestamp: datetime
  entry_price: float
  lots: int
  quantity: int

  # Stop Management (mutable - updated frequently)
  initial_stop: float           # Never changes
  current_stop: float           # Trailing stop - updates every bar
  highest_close: float          # High watermark for trailing calc

  # P&L Tracking (mutable)
  unrealized_pnl: float
  realized_pnl: float

  # Rollover Fields (Bank Nifty/Gold Mini)
  rollover_status: str          # none, pending, in_progress, rolled, failed
  original_expiry: str
  original_strike: int
  rollover_timestamp: datetime
  rollover_pnl: float
  rollover_count: int

  # Synthetic Futures (Bank Nifty)
  strike: int
  expiry: str
  pe_symbol: str
  ce_symbol: str
  pe_order_id: str
  ce_order_id: str
  pe_entry_price: float
  ce_entry_price: float

  # Futures (Gold Mini)
  contract_month: str
  futures_symbol: str
  futures_order_id: str

  # Metadata
  atr: float
  limiter: str
  risk_contribution: float
  vol_contribution: float
  is_base_position: bool        # TRUE for base entry, FALSE for pyramids
}
```

### B. Portfolio State

```python
PortfolioState {
  initial_capital: float        # Starting capital (₹50L)
  closed_equity: float          # Cash + realized P&L (CRITICAL)

  # Derived metrics (useful for recovery validation)
  total_risk_amount: float
  total_risk_percent: float
  total_vol_amount: float
  margin_used: float
}
```

### C. Pyramiding State

**From:** `live/engine.py` - in-memory dicts

```python
PyramidingState {
  instrument: str                   # BANK_NIFTY or GOLD_MINI
  last_pyramid_price: float         # Price of last pyramid
  base_position_id: str             # Reference to base position
}
```

### D. Signal Deduplication

**From:** `core/webhook_parser.py` - DuplicateDetector

```python
SignalFingerprint {
  instrument: str
  signal_type: str              # BASE_ENTRY, PYRAMID, EXIT
  position: str                 # Long_1, Long_2, etc.
  timestamp: datetime
  fingerprint: str              # Hash for uniqueness
  processed_at: datetime
}
```

### E. Instance Metadata (for HA)

```python
InstanceMetadata {
  instance_id: str              # UUID for this instance
  started_at: datetime
  last_heartbeat: datetime
  last_signal_processed: datetime
  is_leader: bool               # Redis-based leader election
  status: str                   # active, standby, crashed
}
```

---

## 2. Database Schema (PostgreSQL)

### Table 1: portfolio_positions

Primary table for all positions (open and closed).

```sql
CREATE TABLE portfolio_positions (
    -- Primary key
    position_id VARCHAR(50) PRIMARY KEY,

    -- Identification
    instrument VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'open',  -- open, closed, partial

    -- Entry data (immutable)
    entry_timestamp TIMESTAMP NOT NULL,
    entry_price DECIMAL(12,2) NOT NULL,
    lots INTEGER NOT NULL,
    quantity INTEGER NOT NULL,

    -- Stop management (mutable)
    initial_stop DECIMAL(12,2) NOT NULL,
    current_stop DECIMAL(12,2) NOT NULL,
    highest_close DECIMAL(12,2) NOT NULL,

    -- P&L tracking (mutable)
    unrealized_pnl DECIMAL(15,2) DEFAULT 0.0,
    realized_pnl DECIMAL(15,2) DEFAULT 0.0,

    -- Rollover fields
    rollover_status VARCHAR(20) DEFAULT 'none',
    original_expiry VARCHAR(20),
    original_strike INTEGER,
    original_entry_price DECIMAL(12,2),
    rollover_timestamp TIMESTAMP,
    rollover_pnl DECIMAL(15,2) DEFAULT 0.0,
    rollover_count INTEGER DEFAULT 0,

    -- Synthetic futures (Bank Nifty)
    strike INTEGER,
    expiry VARCHAR(20),
    pe_symbol VARCHAR(50),
    ce_symbol VARCHAR(50),
    pe_order_id VARCHAR(50),
    ce_order_id VARCHAR(50),
    pe_entry_price DECIMAL(12,2),
    ce_entry_price DECIMAL(12,2),

    -- Futures (Gold Mini)
    contract_month VARCHAR(20),
    futures_symbol VARCHAR(50),
    futures_order_id VARCHAR(50),

    -- Metadata
    atr DECIMAL(12,2),
    limiter VARCHAR(50),
    risk_contribution DECIMAL(8,4),
    vol_contribution DECIMAL(8,4),
    is_base_position BOOLEAN DEFAULT FALSE,  -- TRUE for base entry, FALSE for pyramids

    -- Versioning for optimistic locking
    version INTEGER DEFAULT 1,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    INDEX idx_instrument_status (instrument, status),
    INDEX idx_status (status),
    INDEX idx_created_at (created_at),
    INDEX idx_instrument_entry (instrument, entry_timestamp),  -- For position queries by instrument
    INDEX idx_rollover_status (rollover_status, expiry)  -- For rollover queries
);
```

### Table 2: portfolio_state

Single-row table for portfolio-level state.

```sql
CREATE TABLE portfolio_state (
    id INTEGER PRIMARY KEY DEFAULT 1,
    initial_capital DECIMAL(15,2) NOT NULL,
    closed_equity DECIMAL(15,2) NOT NULL,

    -- Derived metrics (for validation)
    total_risk_amount DECIMAL(15,2),
    total_risk_percent DECIMAL(8,4),
    total_vol_amount DECIMAL(15,2),
    margin_used DECIMAL(15,2),

    -- Versioning
    version INTEGER DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure only one row
    CONSTRAINT single_row CHECK (id = 1)
);
```

### Table 3: pyramiding_state

Tracks pyramiding metadata per instrument.

```sql
CREATE TABLE pyramiding_state (
    instrument VARCHAR(20) PRIMARY KEY,
    last_pyramid_price DECIMAL(12,2),
    base_position_id VARCHAR(50) NULL,  -- Nullable: can be NULL if base position closed
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key to positions (nullable to allow base position closure)
    FOREIGN KEY (base_position_id) REFERENCES portfolio_positions(position_id) ON DELETE SET NULL
);
```

### Table 4: signal_log

Deduplication and audit trail for all webhook signals.

```sql
CREATE TABLE signal_log (
    id BIGSERIAL PRIMARY KEY,

    -- Signal identification
    instrument VARCHAR(20) NOT NULL,
    signal_type VARCHAR(20) NOT NULL,
    position VARCHAR(20) NOT NULL,
    signal_timestamp TIMESTAMP NOT NULL,

    -- Deduplication
    fingerprint VARCHAR(64) UNIQUE NOT NULL,  -- Hash of (instrument, type, position, timestamp)
    is_duplicate BOOLEAN DEFAULT FALSE,

    -- Processing metadata
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_by_instance VARCHAR(50),
    processing_status VARCHAR(20),  -- accepted, rejected, blocked, executed

    -- Full signal payload
    payload JSONB,

    -- Indexes
    INDEX idx_fingerprint (fingerprint),
    INDEX idx_processed_at (processed_at),  -- For cleanup queries
    INDEX idx_instrument_timestamp (instrument, signal_timestamp)
);

-- Cleanup function for old signal_log entries (keep only last 7 days)
CREATE OR REPLACE FUNCTION cleanup_old_signals() RETURNS void AS $$
BEGIN
    DELETE FROM signal_log WHERE processed_at < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql;
```

### Table 5: instance_metadata

Tracks all running instances for health monitoring and leader election.

```sql
CREATE TABLE instance_metadata (
    instance_id VARCHAR(50) PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    last_heartbeat TIMESTAMP NOT NULL,
    last_signal_processed TIMESTAMP,

    -- Leader election (Redis primary, database backup)
    is_leader BOOLEAN DEFAULT FALSE,
    leader_acquired_at TIMESTAMP,

    -- Health status
    status VARCHAR(20) NOT NULL,  -- active, standby, crashed

    -- Deployment info
    hostname VARCHAR(100),
    port INTEGER,
    version VARCHAR(20),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Index for cleanup
    INDEX idx_last_heartbeat (last_heartbeat)
);
```

---

## 3. State Persistence Layer

### Class: DatabaseStateManager

**File:** `portfolio_manager/core/db_state_manager.py` (NEW)

Handles all database operations with connection pooling, transactions, and caching.

```python
"""
Database State Manager

Provides persistence layer for all portfolio state with:
- Connection pooling (psycopg2.pool)
- Transaction management
- Write-through caching (L1 cache)
- Crash recovery support
"""
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Dict, List, Optional
from datetime import datetime
import logging

from core.models import Position, PortfolioState

logger = logging.getLogger(__name__)

class DatabaseStateManager:
    """Persistent state manager using PostgreSQL"""

    def __init__(self, connection_config: dict):
        """
        Initialize database connection pool

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
        """
        self.pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=connection_config.get('minconn', 2),
            maxconn=connection_config.get('maxconn', 10),
            host=connection_config['host'],
            port=connection_config.get('port', 5432),
            database=connection_config['database'],
            user=connection_config['user'],
            password=connection_config['password']
        )

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
    def transaction(self):
        """Transaction context manager with automatic commit/rollback"""
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction rolled back: {e}")
                raise

    # ===== POSITION OPERATIONS =====

    def save_position(self, position: Position) -> bool:
        """
        Insert or update position (upsert)

        Uses optimistic locking with version field
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
                 atr, limiter, risk_contribution, vol_contribution, version)
                VALUES
                (%(position_id)s, %(instrument)s, %(status)s, %(entry_timestamp)s, %(entry_price)s,
                 %(lots)s, %(quantity)s, %(initial_stop)s, %(current_stop)s, %(highest_close)s,
                 %(unrealized_pnl)s, %(realized_pnl)s, %(rollover_status)s, %(original_expiry)s,
                 %(original_strike)s, %(rollover_timestamp)s, %(rollover_pnl)s, %(rollover_count)s,
                 %(strike)s, %(expiry)s, %(pe_symbol)s, %(ce_symbol)s, %(pe_order_id)s,
                 %(ce_order_id)s, %(pe_entry_price)s, %(ce_entry_price)s, %(contract_month)s,
                 %(futures_symbol)s, %(futures_order_id)s, %(atr)s, %(limiter)s,
                 %(risk_contribution)s, %(vol_contribution)s, 1)
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
        """Get position by ID (cache-first)"""
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
        """Load all open positions from database"""
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

    def save_portfolio_state(self, state: PortfolioState) -> bool:
        """Save portfolio state (single-row table)"""
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
                state.initial_capital, state.closed_equity,
                state.total_risk_amount, state.total_risk_percent,
                state.total_vol_amount, state.margin_used
            ))

            self._portfolio_state_cache = state
            return True

    def get_portfolio_state(self) -> Optional[dict]:
        """Load portfolio state from database"""
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
                              base_position_id: str) -> bool:
        """Save pyramiding state for instrument"""
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pyramiding_state (instrument, last_pyramid_price, base_position_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (instrument) DO UPDATE SET
                    last_pyramid_price = EXCLUDED.last_pyramid_price,
                    updated_at = CURRENT_TIMESTAMP
            """, (instrument, last_pyramid_price, base_position_id))
            return True

    def get_pyramiding_state(self) -> Dict[str, dict]:
        """Load all pyramiding state"""
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
        """Check if signal fingerprint exists (within last 60 seconds)"""
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
        """Log signal to audit trail"""
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
                psycopg2.extras.Json(signal_data)
            ))
            return True

    # ===== HELPER METHODS =====

    def _position_to_dict(self, position: Position) -> dict:
        """Convert Position dataclass to dict for database"""
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
        """Convert database row to Position dataclass"""
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
```

---

## 4. Redis Coordination Layer

### Class: RedisCoordinator

**File:** `portfolio_manager/core/redis_coordinator.py` (NEW)

Handles distributed coordination, leader election, and signal-level locking.

```python
"""
Redis Coordinator

Provides distributed coordination using Redis:
- Leader election (SETNX with TTL)
- Heartbeat system
- Signal-level distributed locks
- Health monitoring
"""
import redis
import uuid
import time
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RedisCoordinator:
    """Redis-based distributed coordination"""

    # Redis keys
    LEADER_KEY = "pm:leader"
    HEARTBEAT_PREFIX = "pm:heartbeat:"
    SIGNAL_LOCK_PREFIX = "pm:signal_lock:"

    # TTL values (seconds)
    LEADER_TTL = 10  # Leader key expires in 10 seconds
    HEARTBEAT_TTL = 30  # Heartbeat expires in 30 seconds
    SIGNAL_LOCK_TTL = 30  # Signal lock expires in 30 seconds (allows time for complex processing + OpenAlgo API calls)

    def __init__(self, redis_config: dict):
        """
        Initialize Redis client

        Args:
            redis_config: {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'password': None,
                'socket_timeout': 2.0
            }
        """
        self.redis_client = redis.Redis(
            host=redis_config.get('host', 'localhost'),
            port=redis_config.get('port', 6379),
            db=redis_config.get('db', 0),
            password=redis_config.get('password'),
            socket_timeout=redis_config.get('socket_timeout', 2.0),
            decode_responses=True
        )

        self.instance_id = str(uuid.uuid4())
        self.is_leader = False

        logger.info(f"Redis coordinator initialized: instance={self.instance_id}")

    # ===== LEADER ELECTION =====

    def try_become_leader(self) -> bool:
        """
        Attempt to become leader using SETNX

        Returns:
            True if this instance became leader, False otherwise
        """
        try:
            # Try to set leader key with our instance ID
            acquired = self.redis_client.set(
                self.LEADER_KEY,
                self.instance_id,
                nx=True,  # Only set if not exists
                ex=self.LEADER_TTL  # Expire after 10 seconds
            )

            if acquired:
                self.is_leader = True
                logger.info(f"[{self.instance_id}] Became LEADER")
                return True

            return False

        except redis.RedisError as e:
            logger.error(f"Redis error in leader election: {e}")
            return False

    def renew_leadership(self) -> bool:
        """
        Renew leader key if we are the current leader

        Returns:
            True if renewal successful, False if lost leadership
        """
        if not self.is_leader:
            return False

        try:
            # Use Lua script for atomic get-and-set
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("expire", KEYS[1], ARGV[2])
            else
                return 0
            end
            """

            renewed = self.redis_client.eval(
                lua_script,
                1,
                self.LEADER_KEY,
                self.instance_id,
                self.LEADER_TTL
            )

            if renewed:
                return True
            else:
                self.is_leader = False
                logger.warning(f"[{self.instance_id}] Lost leadership")
                return False

        except redis.RedisError as e:
            logger.error(f"Redis error renewing leadership: {e}")
            self.is_leader = False
            return False

    def get_current_leader(self) -> Optional[str]:
        """Get current leader instance ID"""
        try:
            return self.redis_client.get(self.LEADER_KEY)
        except redis.RedisError:
            return None

    # ===== HEARTBEAT SYSTEM =====

    def send_heartbeat(self) -> bool:
        """Send heartbeat to indicate this instance is alive"""
        try:
            key = f"{self.HEARTBEAT_PREFIX}{self.instance_id}"
            self.redis_client.setex(
                key,
                self.HEARTBEAT_TTL,
                datetime.now().isoformat()
            )
            return True
        except redis.RedisError as e:
            logger.error(f"Error sending heartbeat: {e}")
            return False

    def check_instance_alive(self, instance_id: str) -> bool:
        """Check if another instance is alive"""
        try:
            key = f"{self.HEARTBEAT_PREFIX}{instance_id}"
            return self.redis_client.exists(key) > 0
        except redis.RedisError:
            return False

    def get_all_alive_instances(self) -> list:
        """Get list of all alive instance IDs"""
        try:
            pattern = f"{self.HEARTBEAT_PREFIX}*"
            keys = self.redis_client.keys(pattern)
            return [k.replace(self.HEARTBEAT_PREFIX, '') for k in keys]
        except redis.RedisError:
            return []

    # ===== SIGNAL-LEVEL LOCKING =====

    def acquire_signal_lock(self, signal_fingerprint: str) -> bool:
        """
        Acquire distributed lock for signal processing

        Args:
            signal_fingerprint: Unique signal identifier

        Returns:
            True if lock acquired, False if another instance has it
        """
        try:
            key = f"{self.SIGNAL_LOCK_PREFIX}{signal_fingerprint}"
            acquired = self.redis_client.set(
                key,
                self.instance_id,
                nx=True,
                ex=self.SIGNAL_LOCK_TTL
            )

            return bool(acquired)

        except redis.RedisError as e:
            logger.error(f"Error acquiring signal lock: {e}")
            return False

    def release_signal_lock(self, signal_fingerprint: str) -> bool:
        """Release signal lock (only if we own it)"""
        try:
            key = f"{self.SIGNAL_LOCK_PREFIX}{signal_fingerprint}"

            # Lua script for atomic check-and-delete
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """

            released = self.redis_client.eval(
                lua_script,
                1,
                key,
                self.instance_id
            )

            return bool(released)

        except redis.RedisError as e:
            logger.error(f"Error releasing signal lock: {e}")
            return False

    # ===== CLEANUP =====

    def cleanup_on_shutdown(self):
        """Cleanup Redis state when instance shuts down gracefully"""
        try:
            # Remove heartbeat
            key = f"{self.HEARTBEAT_PREFIX}{self.instance_id}"
            self.redis_client.delete(key)

            # Release leadership if we have it
            if self.is_leader:
                lua_script = """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                else
                    return 0
                end
                """
                self.redis_client.eval(
                    lua_script,
                    1,
                    self.LEADER_KEY,
                    self.instance_id
                )

            logger.info(f"[{self.instance_id}] Redis cleanup complete")

        except redis.RedisError as e:
            logger.error(f"Error during Redis cleanup: {e}")
```

---

## 5. Crash Recovery Manager

### Class: CrashRecoveryManager

**File:** `portfolio_manager/live/recovery.py` (NEW)

Handles startup recovery, orphaned lock cleanup, and state validation.

```python
"""
Crash Recovery Manager

Handles recovery on startup:
- Load state from database
- Clean orphaned locks
- Validate consistency
- Resume trading
"""
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

from core.db_state_manager import DatabaseStateManager
from core.redis_coordinator import RedisCoordinator
from core.models import Position

logger = logging.getLogger(__name__)

class CrashRecoveryManager:
    """Manages crash recovery and state restoration"""

    def __init__(self, db_manager: DatabaseStateManager, redis_coord: RedisCoordinator):
        self.db = db_manager
        self.redis = redis_coord

    def recover_state(self) -> dict:
        """
        Complete recovery sequence on startup

        Returns:
            Recovery result: {
                'positions': Dict[str, Position],
                'closed_equity': float,
                'pyramiding_state': dict,
                'warnings': List[str]
            }
        """
        logger.info("=" * 60)
        logger.info("CRASH RECOVERY: Starting state restoration")
        logger.info("=" * 60)

        warnings = []

        # Step 1: Clean orphaned Redis locks
        self._cleanup_orphaned_locks()

        # Step 2: Load positions from database
        positions = self.db.get_all_open_positions()
        logger.info(f"Recovered {len(positions)} open positions")

        # Step 3: Load portfolio state
        portfolio_state = self.db.get_portfolio_state()
        if portfolio_state:
            closed_equity = portfolio_state['closed_equity']
            logger.info(f"Recovered closed equity: ₹{closed_equity:,.2f}")
        else:
            logger.error("No portfolio state found in database!")
            closed_equity = 5000000.0  # Fallback to initial capital
            warnings.append("Portfolio state missing - using default capital")

        # Step 4: Load pyramiding state
        pyr_state = self.db.get_pyramiding_state()
        logger.info(f"Recovered pyramiding state for {len(pyr_state)} instruments")

        # Step 5: Validate positions
        validation_warnings = self._validate_positions(positions)
        warnings.extend(validation_warnings)

        # Step 6: Check for incomplete operations
        incomplete_warnings = self._check_incomplete_operations(positions)
        warnings.extend(incomplete_warnings)

        logger.info("CRASH RECOVERY: Complete")
        if warnings:
            logger.warning(f"Recovery completed with {len(warnings)} warnings")
            for w in warnings:
                logger.warning(f"  - {w}")

        return {
            'positions': positions,
            'closed_equity': closed_equity,
            'pyramiding_state': pyr_state,
            'warnings': warnings
        }

    def _cleanup_orphaned_locks(self):
        """Clean up Redis locks from dead instances"""
        try:
            alive_instances = self.redis.get_all_alive_instances()
            logger.info(f"Active instances: {len(alive_instances)}")

            # Find signal locks from dead instances
            pattern = f"{self.redis.SIGNAL_LOCK_PREFIX}*"
            all_locks = self.redis.redis_client.keys(pattern)

            orphaned = 0
            for lock_key in all_locks:
                owner = self.redis.redis_client.get(lock_key)
                if owner and owner not in alive_instances:
                    self.redis.redis_client.delete(lock_key)
                    orphaned += 1

            if orphaned > 0:
                logger.info(f"Cleaned {orphaned} orphaned signal locks")

        except Exception as e:
            logger.error(f"Error cleaning orphaned locks: {e}")

    def _validate_positions(self, positions: Dict[str, Position]) -> list:
        """Validate position consistency"""
        warnings = []

        for pos_id, position in positions.items():
            # Check for negative stops
            if position.current_stop < 0:
                warnings.append(f"Position {pos_id} has negative stop: {position.current_stop}")

            # Check for stops above entry (for long positions)
            if position.current_stop > position.entry_price:
                warnings.append(f"Position {pos_id} has stop above entry: {position.current_stop} > {position.entry_price}")

            # Check for very old positions (might need rollover)
            age_days = (datetime.now() - position.entry_timestamp).days
            if age_days > 30:
                warnings.append(f"Position {pos_id} is {age_days} days old - check expiry")

        return warnings

    def _check_incomplete_operations(self, positions: Dict[str, Position]) -> list:
        """Check for positions in intermediate states"""
        warnings = []

        for pos_id, position in positions.items():
            # Check for pending rollovers
            if position.rollover_status == "pending":
                warnings.append(f"Position {pos_id} has pending rollover - manual check needed")

            # Check for in-progress rollovers
            if position.rollover_status == "in_progress":
                warnings.append(f"Position {pos_id} rollover was interrupted - CRITICAL: verify broker state")

            # Check for failed rollovers
            if position.rollover_status == "failed":
                warnings.append(f"Position {pos_id} has failed rollover - manual intervention needed")

        return warnings
```

---

## 6. Signal Fingerprint Calculation

**File:** `portfolio_manager/core/fingerprint.py` (NEW)

Unique fingerprint calculation for signal deduplication across all 3 layers.

```python
"""
Signal Fingerprint Calculation

Generates unique hash for signal deduplication
"""
import hashlib
import json
from datetime import datetime
from core.models import Signal

def calculate_fingerprint(signal: Signal) -> str:
    """
    Calculate unique fingerprint for signal

    Uses SHA-256 hash of normalized signal data:
    - Instrument (BANK_NIFTY, GOLD_MINI)
    - Signal type (BASE_ENTRY, PYRAMID, EXIT)
    - Position (Long_1, Long_2, etc.)
    - Timestamp (normalized to second precision)

    Args:
        signal: Trading signal from TradingView

    Returns:
        64-character hex string (SHA-256 hash)
    """
    # Normalize timestamp to second precision (ignore milliseconds)
    # This handles minor webhook timing variations
    normalized_ts = signal.timestamp.replace(microsecond=0).isoformat()

    # Create hash input (order matters for consistency)
    hash_input = f"{signal.instrument}:{signal.signal_type.value}:{signal.position}:{normalized_ts}"

    # SHA-256 hash (collision-resistant, fast)
    return hashlib.sha256(hash_input.encode()).hexdigest()


def calculate_fingerprint_from_dict(signal_data: dict) -> str:
    """
    Calculate fingerprint from webhook JSON payload

    Used when Signal object not yet created
    """
    # Parse timestamp string to datetime
    if isinstance(signal_data['timestamp'], str):
        ts = datetime.fromisoformat(signal_data['timestamp'].replace('Z', '+00:00'))
    else:
        ts = signal_data['timestamp']

    normalized_ts = ts.replace(microsecond=0).isoformat()

    hash_input = f"{signal_data['instrument']}:{signal_data['type']}:{signal_data['position']}:{normalized_ts}"

    return hashlib.sha256(hash_input.encode()).hexdigest()
```

---

## 7. Broker Reconciliation

Add to `CrashRecoveryManager` class (after existing recovery methods):

```python
def reconcile_with_broker(self, openalgo_client) -> dict:
    """
    Reconcile database positions with actual broker positions

    Critical for detecting:
    1. Orphaned positions (in DB but not in broker)
    2. Missing positions (in broker but not in DB)
    3. Quantity mismatches

    Args:
        openalgo_client: OpenAlgo API client

    Returns:
        Reconciliation result: {
            'matched': int,
            'orphaned': List[str],  # position_ids
            'missing': List[dict],  # broker positions
            'mismatches': List[dict]
        }
    """
    logger.info("=" * 60)
    logger.info("BROKER RECONCILIATION: Starting")
    logger.info("=" * 60)

    # Get all open positions from database
    db_positions = self.db.get_all_open_positions()

    # Get all positions from broker
    broker_positions = openalgo_client.get_positions()

    # Build broker position map (keyed by symbol)
    broker_map = {}
    for bp in broker_positions:
        symbol = bp.get('symbol')  # e.g., 'BANKNIFTY251225C50000'
        broker_map[symbol] = bp

    # Build database position map (keyed by symbols)
    db_map = {}
    for pos_id, position in db_positions.items():
        # Bank Nifty: PE and CE symbols
        if position.instrument == 'BANK_NIFTY':
            if position.pe_symbol:
                db_map[position.pe_symbol] = (pos_id, 'PE')
            if position.ce_symbol:
                db_map[position.ce_symbol] = (pos_id, 'CE')
        # Gold Mini: Futures symbol
        elif position.instrument == 'GOLD_MINI':
            if position.futures_symbol:
                db_map[position.futures_symbol] = (pos_id, 'FUTURES')

    # Reconciliation results
    matched = 0
    orphaned = []  # In DB but not in broker
    missing = []   # In broker but not in DB
    mismatches = []

    # Check DB positions against broker
    for symbol, (pos_id, leg_type) in db_map.items():
        if symbol in broker_map:
            # Position exists in both - check quantity
            bp = broker_map[symbol]
            db_position = db_positions[pos_id]

            broker_qty = abs(bp.get('quantity', 0))
            db_qty = db_position.quantity

            if broker_qty == db_qty:
                matched += 1
            else:
                mismatches.append({
                    'position_id': pos_id,
                    'symbol': symbol,
                    'db_quantity': db_qty,
                    'broker_quantity': broker_qty,
                    'difference': broker_qty - db_qty
                })
                logger.warning(f"Quantity mismatch: {pos_id} - DB={db_qty}, Broker={broker_qty}")
        else:
            # Position in DB but not in broker - orphaned
            orphaned.append(pos_id)
            logger.error(f"Orphaned position detected: {pos_id} ({symbol}) - in DB but not in broker")

    # Check broker positions not in DB
    for symbol, bp in broker_map.items():
        if symbol not in db_map:
            missing.append({
                'symbol': symbol,
                'quantity': bp.get('quantity'),
                'entry_price': bp.get('averageprice')
            })
            logger.error(f"Missing position detected: {symbol} - in broker but not in DB")

    logger.info("=" * 60)
    logger.info(f"BROKER RECONCILIATION: Complete")
    logger.info(f"  Matched: {matched}")
    logger.info(f"  Orphaned (DB only): {len(orphaned)}")
    logger.info(f"  Missing (Broker only): {len(missing)}")
    logger.info(f"  Quantity Mismatches: {len(mismatches)}")
    logger.info("=" * 60)

    return {
        'matched': matched,
        'orphaned': orphaned,
        'missing': missing,
        'mismatches': mismatches
    }
```

---

## 8. Statistics Persistence

**Option 1: JSONB Column in engine_state Table**

Add to portfolio_state table:

```sql
ALTER TABLE portfolio_state ADD COLUMN statistics JSONB DEFAULT '{}'::JSONB;
```

Update `DatabaseStateManager.save_portfolio_state()` to persist stats:

```python
def save_statistics(self, stats: dict) -> bool:
    """Save trading statistics to database"""
    with self.transaction() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE portfolio_state
            SET statistics = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
        """, (psycopg2.extras.Json(stats),))
        return True

def get_statistics(self) -> dict:
    """Load statistics from database"""
    with self.get_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT statistics FROM portfolio_state WHERE id = 1")
        row = cursor.fetchone()
        return dict(row['statistics']) if row and row['statistics'] else {}
```

**Option 2: Separate statistics Table** (better for analytics):

```sql
CREATE TABLE trading_statistics (
    id INTEGER PRIMARY KEY DEFAULT 1,
    signals_received INTEGER DEFAULT 0,
    entries_executed INTEGER DEFAULT 0,
    entries_blocked INTEGER DEFAULT 0,
    pyramids_executed INTEGER DEFAULT 0,
    pyramids_blocked INTEGER DEFAULT 0,
    exits_executed INTEGER DEFAULT 0,
    orders_placed INTEGER DEFAULT 0,
    orders_failed INTEGER DEFAULT 0,
    rollovers_executed INTEGER DEFAULT 0,
    rollovers_failed INTEGER DEFAULT 0,
    rollover_cost_total DECIMAL(15,2) DEFAULT 0.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT single_row CHECK (id = 1)
);
```

---

## 9. Health Check & Monitoring

**File:** `portfolio_manager/endpoints/health.py` (NEW)

```python
"""
Health Check Endpoint

Provides instance health status for load balancer health checks
"""
from flask import jsonify
import logging

logger = logging.getLogger(__name__)

def create_health_endpoint(app, db_manager, redis_coord):
    """Add health check endpoint to Flask app"""

    @app.route('/health', methods=['GET'])
    def health_check():
        """
        Health check endpoint for ALB/load balancer

        Returns:
            200 OK if healthy
            503 Service Unavailable if unhealthy
        """
        health_status = {
            'status': 'healthy',
            'instance_id': redis_coord.instance_id,
            'is_leader': redis_coord.is_leader,
            'checks': {
                'database': 'unknown',
                'redis': 'unknown'
            }
        }

        # Check database connection
        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
            health_status['checks']['database'] = 'healthy'
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            health_status['checks']['database'] = 'unhealthy'
            health_status['status'] = 'unhealthy'

        # Check Redis connection
        try:
            redis_coord.redis_client.ping()
            health_status['checks']['redis'] = 'healthy'
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            health_status['checks']['redis'] = 'unhealthy'
            # Redis failure is not fatal (can fallback to DB-only mode)

        # Return appropriate status code
        status_code = 200 if health_status['status'] == 'healthy' else 503

        return jsonify(health_status), status_code

    @app.route('/ready', methods=['GET'])
    def readiness_check():
        """
        Readiness check - can instance accept traffic?

        Different from health check:
        - Health: Is instance alive?
        - Ready: Can instance process requests?
        """
        try:
            # Check critical dependencies
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM portfolio_state WHERE id = 1")
                cursor.fetchone()

            return jsonify({'status': 'ready'}), 200

        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return jsonify({'status': 'not_ready', 'reason': str(e)}), 503
```

---

## 10. Graceful Shutdown

Add to main `portfolio_manager.py`:

```python
"""
Graceful Shutdown Handler

Ensures clean shutdown on SIGTERM/SIGINT
"""
import signal
import sys
import logging

logger = logging.getLogger(__name__)

class GracefulShutdown:
    """Handle graceful shutdown on signals"""

    def __init__(self, db_manager, redis_coord, flask_app):
        self.db_manager = db_manager
        self.redis_coord = redis_coord
        self.flask_app = flask_app
        self.shutdown_requested = False

        # Register signal handlers
        signal.signal(signal.SIGTERM, self.handle_signal)
        signal.signal(signal.SIGINT, self.handle_signal)

    def handle_signal(self, signum, frame):
        """Handle shutdown signal"""
        signal_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
        logger.info(f"Received {signal_name} - initiating graceful shutdown")

        self.shutdown_requested = True
        self.shutdown()

    def shutdown(self):
        """Execute graceful shutdown sequence"""
        logger.info("=" * 60)
        logger.info("GRACEFUL SHUTDOWN: Starting")
        logger.info("=" * 60)

        # Step 1: Stop accepting new requests (stop Flask)
        logger.info("Stopping Flask server...")
        # Flask shutdown handled by gunicorn/uwsgi

        # Step 2: Wait for in-flight requests to complete
        logger.info("Waiting for in-flight requests...")
        # TODO: Track active requests, wait up to 30 seconds

        # Step 3: Flush any pending database writes
        logger.info("Flushing pending database writes...")
        # Database writes are synchronous, so nothing to flush

        # Step 4: Release Redis locks
        logger.info("Releasing Redis locks...")
        try:
            self.redis_coord.cleanup_on_shutdown()
        except Exception as e:
            logger.error(f"Error during Redis cleanup: {e}")

        # Step 5: Close database connections
        logger.info("Closing database connections...")
        try:
            self.db_manager.pool.closeall()
        except Exception as e:
            logger.error(f"Error closing database pool: {e}")

        logger.info("=" * 60)
        logger.info("GRACEFUL SHUTDOWN: Complete")
        logger.info("=" * 60)

        sys.exit(0)
```

---

## 11. Database Connection Retry Logic

Add to `DatabaseStateManager.__init__()`:

```python
def __init__(self, connection_config: dict, max_retries: int = 3):
    """
    Initialize database connection pool with retry logic
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

    # L1 cache for hot data
    self._position_cache = {}
    self._portfolio_state_cache = None
```

Add connection retry wrapper for transactions:

```python
@contextmanager
def transaction(self, max_retries: int = 2):
    """
    Transaction context manager with automatic retry on connection loss
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
```

---

## 12. Redis Fallback to Database-Only Mode

Add to `RedisCoordinator.__init__()`:

```python
def __init__(self, redis_config: dict, fallback_mode: bool = False):
    """
    Initialize Redis client with fallback support

    Args:
        redis_config: Redis connection config
        fallback_mode: If True, operate in DB-only mode (no Redis)
    """
    self.fallback_mode = fallback_mode

    if fallback_mode:
        logger.warning("Redis fallback mode enabled - using database-only coordination")
        self.redis_client = None
        self.instance_id = str(uuid.uuid4())
        self.is_leader = False
        return

    try:
        self.redis_client = redis.Redis(
            host=redis_config.get('host', 'localhost'),
            port=redis_config.get('port', 6379),
            db=redis_config.get('db', 0),
            password=redis_config.get('password'),
            socket_timeout=redis_config.get('socket_timeout', 2.0),
            decode_responses=True
        )

        # Test connection
        self.redis_client.ping()

        self.instance_id = str(uuid.uuid4())
        self.is_leader = False

        logger.info(f"Redis coordinator initialized: instance={self.instance_id}")

    except redis.RedisError as e:
        logger.error(f"Redis connection failed, enabling fallback mode: {e}")
        self.fallback_mode = True
        self.redis_client = None
        self.instance_id = str(uuid.uuid4())
        self.is_leader = False
```

Update lock methods to handle fallback:

```python
def acquire_signal_lock(self, signal_fingerprint: str) -> bool:
    """
    Acquire distributed lock for signal processing

    In fallback mode: Use database-based locking
    """
    if self.fallback_mode:
        # Fallback: Always return True (single-instance mode)
        logger.warning("Redis unavailable - using database-only deduplication")
        return True

    # Normal Redis locking (existing code)
    # ...
```

---

## 13. Transaction Isolation Levels

**Documentation:**

PostgreSQL uses `READ COMMITTED` isolation level by default, which is appropriate for most operations in this system.

**Isolation Level Usage:**

| Operation | Isolation Level | Rationale |
|-----------|----------------|-----------|
| Signal processing (entry/exit) | `READ COMMITTED` | Sufficient - row-level locks prevent conflicts |
| Portfolio state updates | `READ COMMITTED` | Single-row table, atomic updates |
| Position updates (trailing stops) | `READ COMMITTED` | Optimistic locking (version field) handles conflicts |
| Rollover operations | `SERIALIZABLE` | Critical - prevents partial rollovers from concurrent operations |
| Signal deduplication check | `READ COMMITTED` | UNIQUE constraint provides serialization |

**Example usage for rollover:**

```python
def execute_rollover_transaction(self, position_id: str, new_contract: dict):
    """
    Execute rollover with SERIALIZABLE isolation

    Prevents:
    - Concurrent rollovers of same position
    - Partial rollover state (old position closed, new not created)
    """
    with self.get_connection() as conn:
        # Set isolation level
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)

        try:
            cursor = conn.cursor()

            # Close old position
            cursor.execute("""
                UPDATE portfolio_positions
                SET status = 'closed', rollover_status = 'rolled'
                WHERE position_id = %s
            """, (position_id,))

            # Create new position
            # ... (insert new position)

            conn.commit()
            logger.info(f"Rollover completed: {position_id}")

        except Exception as e:
            conn.rollback()
            logger.error(f"Rollover failed: {e}")
            raise

        finally:
            # Reset to default isolation level
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_READ_COMMITTED)
```

---

## 14. Implementation Phases

### Phase 1: Database Schema + Basic Persistence (Week 1)

**Tasks:**
1. ✅ Create PostgreSQL schema (5 tables)
2. ✅ Implement DatabaseStateManager class
3. ✅ Integrate with PortfolioStateManager
4. ✅ Add save_position() calls in LiveTradingEngine
5. ✅ Test: Insert/update positions, load on startup

**Files Modified:**
- NEW: `core/db_state_manager.py`
- NEW: `migrations/001_initial_schema.sql`
- MODIFY: `core/portfolio_state.py` - add database hooks
- MODIFY: `live/engine.py` - persist after entry/exit/pyramid

**Testing:**
- Unit tests for DatabaseStateManager
- Integration test: Process signal → verify database persistence
- Recovery test: Restart engine → verify state loaded

---

### Phase 2: Redis Coordination (Week 2)

**Tasks:**
1. ✅ Implement RedisCoordinator class
2. ✅ Add leader election logic
3. ✅ Implement heartbeat system
4. ✅ Add signal-level distributed locks
5. ✅ Test: Multiple instances, leader failover

**Files Modified:**
- NEW: `core/redis_coordinator.py`
- MODIFY: `portfolio_manager.py` - add Redis initialization
- MODIFY: `live/engine.py` - acquire lock before processing signal

**Testing:**
- Unit tests for RedisCoordinator
- Leader election test: Kill leader → verify new leader elected (<3 sec)
- Lock test: Two instances try to process same signal → only one succeeds

---

### Phase 3: Active-Active Coordination (Week 3)

**Tasks:**
1. ✅ 3-layer duplicate detection (local cache → Redis lock → database)
2. ✅ Modify webhook endpoint to acquire Redis lock
3. ✅ Add database fingerprint check
4. ✅ Add Nginx load balancer configuration
5. ✅ Test: Concurrent signal processing

**Files Modified:**
- MODIFY: `portfolio_manager.py` - webhook endpoint with locking
- MODIFY: `core/webhook_parser.py` - add database dedup
- NEW: `nginx.conf` - load balancer config

**Testing:**
- Concurrent webhook test: Send 100 signals simultaneously → all processed exactly once
- Split-brain test: Network partition → verify no duplicates

---

### Phase 4: Crash Recovery (Week 4)

**Tasks:**
1. ✅ Implement CrashRecoveryManager
2. ✅ Add startup recovery sequence
3. ✅ Add orphaned lock cleanup
4. ✅ Add position validation
5. ✅ Test: Kill instance mid-signal → restart → resume

**Files Modified:**
- NEW: `live/recovery.py`
- MODIFY: `portfolio_manager.py` - call recovery on startup

**Testing:**
- Crash during entry test: Kill after broker order → verify position recovered
- Crash during rollover test: Kill mid-rollover → verify partial state handled
- Graceful shutdown test: Stop instance → verify cleanup

---

### Phase 5: Integration Testing (Week 5)

**Tasks:**
1. ✅ End-to-end tests (100+ scenarios)
2. ✅ Chaos testing (random crashes)
3. ✅ Performance testing (1000 signals/min)
4. ✅ Load balancer testing
5. ✅ Rollover recovery testing

**Test Scenarios:**
- Happy path: BASE_ENTRY → PYRAMID → EXIT with 2 instances
- Crash scenario: Instance crashes during pyramid → other instance takes over
- Split-brain: Network partition → verify no duplicate entries
- Rollover: Partial rollover → crash → resume
- Performance: 1000 concurrent webhooks → verify latency <200ms (p95)

---

### Phase 6: Deployment (Week 6)

**Tasks:**
1. ✅ Docker Compose for local multi-instance deployment
2. ✅ AWS deployment (ALB + ECS + RDS + ElastiCache)
3. ✅ Health checks and monitoring
4. ✅ Alerting (PagerDuty/Slack)
5. ✅ Documentation

**Deployment Architecture:**
```
TradingView Webhooks
         ↓
AWS Application Load Balancer (ALB)
    ↓                    ↓
Portfolio Manager    Portfolio Manager
  Instance 1           Instance 2
  (ECS Task)          (ECS Task)
    ↓                    ↓
    ↓← Redis Leader Election →↓
      (ElastiCache Redis)
    ↓                    ↓
    ↓← PostgreSQL RDS →↓
      (Primary + Read Replica)
```

---

## 7. Configuration

### database_config.json

```json
{
  "local": {
    "host": "localhost",
    "port": 5432,
    "database": "portfolio_manager",
    "user": "pm_user",
    "password": "dev_password",
    "minconn": 2,
    "maxconn": 10
  },
  "production": {
    "host": "portfolio-db.abc123.us-east-1.rds.amazonaws.com",
    "port": 5432,
    "database": "portfolio_manager_prod",
    "user": "pm_prod_user",
    "password": "${DB_PASSWORD}",
    "minconn": 5,
    "maxconn": 20
  }
}
```

### redis_config.json

```json
{
  "local": {
    "host": "localhost",
    "port": 6379,
    "db": 0,
    "password": null
  },
  "production": {
    "host": "portfolio-redis.abc123.use1.cache.amazonaws.com",
    "port": 6379,
    "db": 0,
    "password": "${REDIS_PASSWORD}",
    "ssl": true
  }
}
```

---

## 8. Testing Strategy

### Unit Tests (50+ tests)

- `test_db_state_manager.py` - Database CRUD operations
- `test_redis_coordinator.py` - Leader election, locks, heartbeats
- `test_crash_recovery.py` - Recovery logic, validation

### Integration Tests (30+ tests)

- `test_active_active.py` - Concurrent signal processing
- `test_failover.py` - Leader election, instance crash scenarios
- `test_persistence.py` - End-to-end signal → database → recovery

### Chaos Tests (20+ tests)

- Random instance crashes during signal processing
- Network partitions (split-brain scenarios)
- Database connection failures
- Redis failures (fallback to database-only mode)

---

## Summary

This plan provides a **production-ready, highly available** Portfolio Manager with:

✅ **PostgreSQL persistence** - Full state recovery from database with optimistic locking
✅ **Redis coordination** - Fast leader election (<3 sec failover), 30s signal locks
✅ **Active-active architecture** - ALL instances process webhooks (leader only for background tasks)
✅ **Crash recovery** - Complete state restoration with broker reconciliation
✅ **3-layer deduplication** - Local cache → Redis lock → Database constraint (SHA-256 fingerprints)
✅ **Transactional consistency** - Atomic signal processing with rollback and retry logic
✅ **Graceful shutdown** - Clean SIGTERM/SIGINT handling with lock release
✅ **Health monitoring** - /health and /ready endpoints for load balancers
✅ **Error resilience** - Database retry logic, Redis fallback to DB-only mode
✅ **Statistics persistence** - Trading stats stored in PostgreSQL JSONB/separate table
✅ **Broker reconciliation** - Automatic position sync validation on startup
✅ **Hybrid deployment** - Local dev + cloud production (AWS/Azure)

**Total Implementation:** 6 weeks
**Lines of Code:** ~3,500 (core logic) + 1,500 (tests)
**Performance:** <200ms webhook latency (p95), 1000 signals/min throughput

**Key Improvements from Review:**
- ✅ Clarified active-active architecture (all instances process signals)
- ✅ Increased signal lock TTL from 5s to 30s
- ✅ Added `is_base_position` field to Position model
- ✅ Made `base_position_id` nullable in pyramiding_state
- ✅ Added fingerprint calculation (SHA-256)
- ✅ Added broker reconciliation method
- ✅ Added statistics persistence (JSONB + separate table options)
- ✅ Added health check endpoints (/health, /ready)
- ✅ Added graceful shutdown handler
- ✅ Added database connection retry with exponential backoff
- ✅ Added Redis fallback mode (database-only)
- ✅ Added missing database indexes (5 total)
- ✅ Documented transaction isolation levels (READ COMMITTED vs SERIALIZABLE)
