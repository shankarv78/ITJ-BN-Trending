-- Migration 014: Fix capital_summary view for signed amounts
--
-- The view was created when amounts were always positive.
-- Now that we use signed amounts:
--   DEPOSIT: positive
--   WITHDRAW: negative
--   TRADING_PNL: signed (positive=profit, negative=loss)
--
-- Fix the view to handle this correctly.

-- Drop and recreate the view
DROP VIEW IF EXISTS capital_summary;

CREATE VIEW capital_summary AS
SELECT
    -- Deposit count and total (amounts are positive)
    COUNT(*) FILTER (WHERE transaction_type = 'DEPOSIT') AS deposit_count,
    COALESCE(SUM(amount) FILTER (WHERE transaction_type = 'DEPOSIT'), 0) AS total_deposits,

    -- Withdraw count and total (amounts are negative, show as positive for display)
    COUNT(*) FILTER (WHERE transaction_type = 'WITHDRAW') AS withdraw_count,
    COALESCE(ABS(SUM(amount) FILTER (WHERE transaction_type = 'WITHDRAW')), 0) AS total_withdrawals,

    -- Trading P&L count and total (amounts are signed)
    COUNT(*) FILTER (WHERE transaction_type = 'TRADING_PNL') AS trading_pnl_count,
    COALESCE(SUM(amount) FILTER (WHERE transaction_type = 'TRADING_PNL'), 0) AS total_trading_pnl,

    -- Net change is simply SUM of all signed amounts
    COALESCE(SUM(amount), 0) AS net_capital_change,

    -- Timestamps
    MIN(created_at) AS first_transaction,
    MAX(created_at) AS last_transaction
FROM capital_transactions;
