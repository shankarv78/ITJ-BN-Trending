-- Portfolio Manager - Broker Position Tracking
-- Migration: 007_add_broker_position_tracking.sql
-- Created: 2025-12-09
-- Description: Track broker positions assigned to strategies (without importing to PM)

-- ============================================================================
-- Table: broker_position_tags
-- Maps broker position symbols to strategies for tracking P&L
-- ============================================================================

CREATE TABLE IF NOT EXISTS broker_position_tags (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(100) NOT NULL,        -- Broker symbol (e.g., NIFTY29DEC2625000CE)
    strategy_id INTEGER NOT NULL REFERENCES trading_strategies(strategy_id),
    instrument VARCHAR(50),               -- Detected instrument type
    quantity INTEGER,                     -- Position quantity (positive=long, negative=short)
    entry_price DECIMAL(15,2),           -- Average price at time of tagging
    tagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,      -- FALSE when position is closed
    closed_at TIMESTAMP,
    exit_price DECIMAL(15,2),
    realized_pnl DECIMAL(15,2),
    notes TEXT,
    UNIQUE(symbol, strategy_id, tagged_at)
);

-- Indexes for efficient lookups
CREATE INDEX idx_broker_tags_symbol ON broker_position_tags(symbol);
CREATE INDEX idx_broker_tags_strategy ON broker_position_tags(strategy_id);
CREATE INDEX idx_broker_tags_active ON broker_position_tags(is_active);
CREATE INDEX idx_broker_tags_strategy_active ON broker_position_tags(strategy_id, is_active);

-- ============================================================================
-- View: broker_positions_by_strategy
-- Shows all tagged broker positions grouped by strategy
-- ============================================================================

CREATE OR REPLACE VIEW broker_positions_by_strategy AS
SELECT
    s.strategy_id,
    s.strategy_name,
    bpt.symbol,
    bpt.instrument,
    bpt.quantity,
    bpt.entry_price,
    bpt.tagged_at,
    bpt.is_active,
    bpt.realized_pnl
FROM broker_position_tags bpt
JOIN trading_strategies s ON s.strategy_id = bpt.strategy_id
ORDER BY s.strategy_id, bpt.tagged_at DESC;

-- ============================================================================
-- End of Migration
-- ============================================================================
