-- Portfolio Manager - Strategy Framework
-- Migration: 006_add_strategies.sql
-- Created: 2025-12-09
-- Description: Adds multi-strategy support with P&L tracking per strategy

-- ============================================================================
-- Table 1: trading_strategies
-- Defines trading strategies with capital allocation and cumulative P&L
-- ============================================================================

CREATE TABLE trading_strategies (
    strategy_id SERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    allocated_capital DECIMAL(15,2) DEFAULT 0,
    cumulative_realized_pnl DECIMAL(15,2) DEFAULT 0,  -- Running total of closed trades
    is_system BOOLEAN DEFAULT FALSE,  -- TRUE for ITJ Trend Follow, unknown
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed default strategies
INSERT INTO trading_strategies (strategy_id, strategy_name, description, is_system, allocated_capital) VALUES
(1, 'ITJ Trend Follow', 'Automated trend following for Bank Nifty and Gold Mini', TRUE, 5000000.0),
(2, 'unknown', 'Unassigned broker positions (manual trades)', TRUE, 0);

-- Reset sequence to continue after seeded IDs
SELECT setval('trading_strategies_strategy_id_seq', 2, true);

-- ============================================================================
-- Table 2: strategy_trade_history
-- Audit trail for closed positions (for cumulative P&L calculation)
-- ============================================================================

CREATE TABLE strategy_trade_history (
    trade_id SERIAL PRIMARY KEY,
    strategy_id INTEGER NOT NULL REFERENCES trading_strategies(strategy_id),
    position_id VARCHAR(50) NOT NULL,
    instrument VARCHAR(50) NOT NULL,
    symbol VARCHAR(100),
    direction VARCHAR(10),  -- LONG/SHORT
    lots INTEGER,
    entry_price DECIMAL(15,2),
    exit_price DECIMAL(15,2),
    realized_pnl DECIMAL(15,2),
    opened_at TIMESTAMP,
    closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for trade history
CREATE INDEX idx_trade_history_strategy ON strategy_trade_history(strategy_id);
CREATE INDEX idx_trade_history_closed_at ON strategy_trade_history(closed_at);
CREATE INDEX idx_trade_history_instrument ON strategy_trade_history(instrument);

-- ============================================================================
-- Modify portfolio_positions to include strategy_id
-- ============================================================================

-- Add strategy_id column with foreign key
ALTER TABLE portfolio_positions
ADD COLUMN strategy_id INTEGER REFERENCES trading_strategies(strategy_id) DEFAULT 1;

-- Index for strategy queries
CREATE INDEX idx_position_strategy ON portfolio_positions(strategy_id);
CREATE INDEX idx_position_strategy_status ON portfolio_positions(strategy_id, status);

-- Update existing positions to use default strategy (ITJ Trend Follow)
UPDATE portfolio_positions SET strategy_id = 1 WHERE strategy_id IS NULL;

-- ============================================================================
-- End of Migration
-- ============================================================================
