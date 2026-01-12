-- Migration 010: Add TRADING_PNL transaction type to capital_transactions
-- This allows the ledger to track P&L from closed trades automatically

-- Drop the existing check constraint
ALTER TABLE capital_transactions
DROP CONSTRAINT IF EXISTS capital_transactions_transaction_type_check;

-- Add new check constraint with TRADING_PNL type
ALTER TABLE capital_transactions
ADD CONSTRAINT capital_transactions_transaction_type_check
CHECK (transaction_type IN ('DEPOSIT', 'WITHDRAW', 'TRADING_PNL'));

-- Add optional position_id column to link P&L entries to their source position
ALTER TABLE capital_transactions
ADD COLUMN IF NOT EXISTS position_id VARCHAR(50);

-- Add index for position_id lookups
CREATE INDEX IF NOT EXISTS idx_capital_transactions_position
ON capital_transactions(position_id) WHERE position_id IS NOT NULL;

-- Comment on new column
COMMENT ON COLUMN capital_transactions.position_id IS 'Links TRADING_PNL entries to their source position';
