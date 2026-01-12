-- Migration 013: Simplify amount constraint for capital_transactions
--
-- Ledger now uses signed amounts consistently:
--   DEPOSIT: positive (adds to equity)
--   WITHDRAW: negative (subtracts from equity)
--   TRADING_PNL: positive (profit) or negative (loss)
--
-- This means SUM(amount) = total change in equity from zero.

-- Drop the old complex constraint
ALTER TABLE capital_transactions DROP CONSTRAINT IF EXISTS capital_transactions_amount_check;

-- Simple constraint: amount just can't be zero
ALTER TABLE capital_transactions ADD CONSTRAINT capital_transactions_amount_check
CHECK (amount <> 0);
