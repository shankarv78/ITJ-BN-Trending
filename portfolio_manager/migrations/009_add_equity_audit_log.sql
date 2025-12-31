-- Portfolio Manager - Equity Audit Log
-- Migration: 009_add_equity_audit_log.sql
-- Created: 2025-12-31
-- Description: Track all equity changes for audit trail and debugging

-- ============================================================================
-- Table: equity_audit_log
-- Records every change to closed_equity with reason and source
-- ============================================================================

CREATE TABLE IF NOT EXISTS equity_audit_log (
    id SERIAL PRIMARY KEY,

    -- Change details
    equity_before DECIMAL(15,2) NOT NULL,
    equity_after DECIMAL(15,2) NOT NULL,
    change_amount DECIMAL(15,2) NOT NULL,
    change_percent DECIMAL(8,4) NOT NULL,

    -- Reason for change
    reason VARCHAR(50) NOT NULL,  -- 'TRADE_CLOSE', 'CAPITAL_INJECT', 'CAPITAL_WITHDRAW', 'MANUAL_ADJUST', 'STARTUP_LOAD'
    source VARCHAR(100),          -- Position ID, transaction ID, or description

    -- Context
    position_id VARCHAR(100),     -- If change was from a trade
    transaction_id INTEGER,       -- If change was from capital transaction

    -- Audit
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(50) DEFAULT 'SYSTEM'
);

-- Index for efficient queries
CREATE INDEX idx_equity_audit_log_date ON equity_audit_log(created_at);
CREATE INDEX idx_equity_audit_log_reason ON equity_audit_log(reason);

-- ============================================================================
-- View: equity_audit_summary
-- Daily summary of equity changes
-- ============================================================================

CREATE OR REPLACE VIEW equity_audit_daily AS
SELECT
    DATE(created_at) as date,
    COUNT(*) as change_count,
    SUM(CASE WHEN reason = 'TRADE_CLOSE' THEN change_amount ELSE 0 END) as trading_pnl,
    SUM(CASE WHEN reason = 'CAPITAL_INJECT' THEN change_amount ELSE 0 END) as deposits,
    SUM(CASE WHEN reason = 'CAPITAL_WITHDRAW' THEN change_amount ELSE 0 END) as withdrawals,
    MIN(equity_before) as day_start_equity,
    MAX(equity_after) as day_end_equity
FROM equity_audit_log
GROUP BY DATE(created_at)
ORDER BY DATE(created_at) DESC;

-- ============================================================================
-- Comments
-- ============================================================================

COMMENT ON TABLE equity_audit_log IS 'Audit trail for all closed_equity changes';
COMMENT ON COLUMN equity_audit_log.reason IS 'TRADE_CLOSE, CAPITAL_INJECT, CAPITAL_WITHDRAW, MANUAL_ADJUST, STARTUP_LOAD';
COMMENT ON COLUMN equity_audit_log.source IS 'Human-readable description of change source';
