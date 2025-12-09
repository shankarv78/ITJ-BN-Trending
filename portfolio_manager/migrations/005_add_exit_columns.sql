-- Portfolio Manager - Add Exit Columns
-- Migration: 002_add_exit_columns.sql
-- Created: 2025-12-07
-- Description: Add exit timestamp, price and reason for closed positions

-- Add exit columns to portfolio_positions
ALTER TABLE portfolio_positions
ADD COLUMN IF NOT EXISTS exit_timestamp TIMESTAMP,
ADD COLUMN IF NOT EXISTS exit_price DECIMAL(12,2),
ADD COLUMN IF NOT EXISTS exit_reason VARCHAR(50);  -- STOP_LOSS, MANUAL, EOD, SIGNAL

-- Add index for exit timestamp (useful for trade history queries)
CREATE INDEX IF NOT EXISTS idx_exit_timestamp ON portfolio_positions(exit_timestamp);

-- Update the existing manual trade with exit data
UPDATE portfolio_positions
SET exit_timestamp = '2025-12-05 16:30:00',
    exit_price = 129145.00,
    exit_reason = 'STOP_LOSS'
WHERE position_id = 'manual_gold_20251205_1540';

-- Verify
SELECT position_id, instrument, status, entry_timestamp, exit_timestamp, entry_price, exit_price, exit_reason, realized_pnl
FROM portfolio_positions
WHERE position_id = 'manual_gold_20251205_1540';
