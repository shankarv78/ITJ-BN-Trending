-- Portfolio Manager HA System - Initial Database Schema
-- Migration: 001_initial_schema.sql
-- Created: 2025-11-28
-- Description: Creates all 5 tables for PostgreSQL persistence

-- ============================================================================
-- Table 1: portfolio_positions
-- Primary table for all positions (open and closed)
-- ============================================================================

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

    -- Constraints
    CONSTRAINT check_status CHECK (status IN ('open', 'closed', 'partial')),
    CONSTRAINT check_rollover_status CHECK (rollover_status IN ('none', 'pending', 'in_progress', 'rolled', 'failed'))
);

-- Indexes for portfolio_positions
CREATE INDEX idx_instrument_status ON portfolio_positions(instrument, status);
CREATE INDEX idx_status ON portfolio_positions(status);
CREATE INDEX idx_created_at ON portfolio_positions(created_at);
CREATE INDEX idx_instrument_entry ON portfolio_positions(instrument, entry_timestamp);  -- For position queries by instrument
CREATE INDEX idx_rollover_status ON portfolio_positions(rollover_status, expiry);  -- For rollover queries

-- ============================================================================
-- Table 2: portfolio_state
-- Single-row table for portfolio-level state
-- ============================================================================

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

-- Insert initial row
INSERT INTO portfolio_state (id, initial_capital, closed_equity, total_risk_amount, total_risk_percent, total_vol_amount, margin_used)
VALUES (1, 5000000.0, 5000000.0, 0.0, 0.0, 0.0, 0.0)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- Table 3: pyramiding_state
-- Tracks pyramiding metadata per instrument
-- ============================================================================

CREATE TABLE pyramiding_state (
    instrument VARCHAR(20) PRIMARY KEY,
    last_pyramid_price DECIMAL(12,2),
    base_position_id VARCHAR(50) NULL,  -- Nullable: can be NULL if base position closed
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key to positions (nullable to allow base position closure)
    FOREIGN KEY (base_position_id) REFERENCES portfolio_positions(position_id) ON DELETE SET NULL
);

-- ============================================================================
-- Table 4: signal_log
-- Deduplication and audit trail for all webhook signals
-- ============================================================================

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
    payload JSONB
);

-- Indexes for signal_log
CREATE UNIQUE INDEX idx_fingerprint ON signal_log(fingerprint);
CREATE INDEX idx_processed_at ON signal_log(processed_at);  -- For cleanup queries
CREATE INDEX idx_instrument_timestamp ON signal_log(instrument, signal_timestamp);

-- Cleanup function for old signal_log entries (keep only last 7 days)
CREATE OR REPLACE FUNCTION cleanup_old_signals() RETURNS void AS $$
BEGIN
    DELETE FROM signal_log WHERE processed_at < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Table 5: instance_metadata
-- Tracks all running instances for health monitoring and leader election
-- ============================================================================

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
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for cleanup
CREATE INDEX idx_last_heartbeat ON instance_metadata(last_heartbeat);

-- ============================================================================
-- End of Migration
-- ============================================================================


