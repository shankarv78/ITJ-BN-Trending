-- Migration 015: Add equity_high for Tom Basso position sizing
-- equity_high tracks the highest closed_equity ever reached (high watermark)
-- Used for position sizing to maintain consistent sizes during drawdowns

-- Add equity_high column to portfolio_state
ALTER TABLE portfolio_state
ADD COLUMN IF NOT EXISTS equity_high NUMERIC(15,2);

-- Initialize equity_high to current closed_equity for existing data
UPDATE portfolio_state
SET equity_high = closed_equity
WHERE equity_high IS NULL;

-- Add comment for documentation
COMMENT ON COLUMN portfolio_state.equity_high IS 'Highest closed_equity ever reached (Tom Basso high watermark for position sizing)';
