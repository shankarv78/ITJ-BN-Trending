-- Migration: Add test mode columns to portfolio_positions table
-- Purpose: Track test mode positions and original calculated lots
-- Run: psql -d portfolio_manager -f migrations/004_add_test_mode_columns.sql

-- Add is_test column to mark test mode positions
ALTER TABLE portfolio_positions
ADD COLUMN IF NOT EXISTS is_test BOOLEAN DEFAULT FALSE;

-- Add original_lots column to store what would have been calculated
ALTER TABLE portfolio_positions
ADD COLUMN IF NOT EXISTS original_lots INTEGER;

-- Add index for quick filtering of test positions
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_is_test ON portfolio_positions(is_test) WHERE is_test = TRUE;

-- Add comment for documentation
COMMENT ON COLUMN portfolio_positions.is_test IS 'True if position was created in test mode (1 lot only)';
COMMENT ON COLUMN portfolio_positions.original_lots IS 'Original calculated lots before test mode override (NULL if not test mode)';
