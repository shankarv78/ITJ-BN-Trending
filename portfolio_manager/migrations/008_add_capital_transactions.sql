-- Portfolio Manager - Capital Transactions Ledger
-- Migration: 008_add_capital_transactions.sql
-- Created: 2025-12-26
-- Description: Track capital deposits and withdrawals with full audit trail

-- ============================================================================
-- Table: capital_transactions
-- Ledger for all capital movements (deposits/withdrawals)
-- ============================================================================

CREATE TABLE IF NOT EXISTS capital_transactions (
    id SERIAL PRIMARY KEY,

    -- Transaction details
    transaction_type VARCHAR(20) NOT NULL CHECK (transaction_type IN ('DEPOSIT', 'WITHDRAW')),
    amount DECIMAL(15,2) NOT NULL CHECK (amount > 0),
    notes TEXT,

    -- Audit trail
    equity_before DECIMAL(15,2) NOT NULL,
    equity_after DECIMAL(15,2) NOT NULL,

    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(50) DEFAULT 'API'  -- 'API', 'MANUAL', 'SYSTEM'
);

-- Index for efficient date-range queries
CREATE INDEX idx_capital_transactions_date ON capital_transactions(created_at);
CREATE INDEX idx_capital_transactions_type ON capital_transactions(transaction_type);

-- ============================================================================
-- View: capital_summary
-- Quick view of total deposits, withdrawals, and net capital added
-- ============================================================================

CREATE OR REPLACE VIEW capital_summary AS
SELECT
    COUNT(*) FILTER (WHERE transaction_type = 'DEPOSIT') AS deposit_count,
    COALESCE(SUM(amount) FILTER (WHERE transaction_type = 'DEPOSIT'), 0) AS total_deposits,
    COUNT(*) FILTER (WHERE transaction_type = 'WITHDRAW') AS withdraw_count,
    COALESCE(SUM(amount) FILTER (WHERE transaction_type = 'WITHDRAW'), 0) AS total_withdrawals,
    COALESCE(SUM(CASE WHEN transaction_type = 'DEPOSIT' THEN amount ELSE -amount END), 0) AS net_capital_change,
    MIN(created_at) AS first_transaction,
    MAX(created_at) AS last_transaction
FROM capital_transactions;

-- ============================================================================
-- End of Migration
-- ============================================================================
