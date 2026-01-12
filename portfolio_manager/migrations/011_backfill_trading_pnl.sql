-- Migration 011: Backfill trading P&L for trades closed after last capital transaction
-- This brings the ledger into sync with actual trading activity

-- Start transaction for atomicity
BEGIN;

-- Get the last capital transaction's equity_after as starting point
-- Expected: 10071205.00 (Dec 26 deposit)

-- Insert trading P&L entries in chronological order
-- Each entry uses the previous entry's equity_after as its equity_before

-- Trade 1: SILVER_MINI_Long_12 closed 2025-12-29 with +₹46,815
INSERT INTO capital_transactions
(transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES
('TRADING_PNL', 46815.00, 'SILVER_MINI trade P&L: +₹46,815.00',
 10071205.00, 10118020.00, 'MIGRATION', 'SILVER_MINI_Long_12', '2025-12-29 15:30:00');

-- Trade 2: SILVER_MINI_Long_13 closed 2025-12-31 with -₹36,955
INSERT INTO capital_transactions
(transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES
('TRADING_PNL', 36955.00, 'SILVER_MINI trade P&L: -₹36,955.00',
 10118020.00, 10081065.00, 'MIGRATION', 'SILVER_MINI_Long_13', '2025-12-31 15:30:00');

-- Trade 3: BANK_NIFTY_Long_14 closed 2025-12-31 with -₹2,064
INSERT INTO capital_transactions
(transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES
('TRADING_PNL', 2064.00, 'BANK_NIFTY trade P&L: -₹2,064.00',
 10081065.00, 10079001.00, 'MIGRATION', 'BANK_NIFTY_Long_14', '2025-12-31 15:30:01');

-- Trade 4: GOLD_MINI_Long_1 closed 2026-01-02 with -₹1,05,811.20
INSERT INTO capital_transactions
(transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES
('TRADING_PNL', 105811.20, 'GOLD_MINI trade P&L: -₹1,05,811.20',
 10079001.00, 9973189.80, 'MIGRATION', 'GOLD_MINI_Long_1', '2026-01-02 19:00:00');

-- Trade 5: BANK_NIFTY_Long_1 closed 2026-01-05 with +₹23,280
INSERT INTO capital_transactions
(transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES
('TRADING_PNL', 23280.00, 'BANK_NIFTY trade P&L: +₹23,280.00',
 9973189.80, 9996469.80, 'MIGRATION', 'BANK_NIFTY_Long_1', '2026-01-05 14:19:12');

-- Trade 6: SILVER_MINI_Long_1 closed 2026-01-07 with +₹11,880
INSERT INTO capital_transactions
(transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES
('TRADING_PNL', 11880.00, 'SILVER_MINI trade P&L: +₹11,880.00',
 9996469.80, 10008349.80, 'MIGRATION', 'SILVER_MINI_Long_1', '2026-01-07 19:00:19.91178');

-- Update portfolio_state to match ledger
UPDATE portfolio_state
SET closed_equity = 10008349.80,
    initial_capital = 10000000.00,  -- Net capital (deposits - withdrawals)
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 1;

COMMIT;

-- Verify the final state
SELECT
  'Ledger equity' as source,
  equity_after as equity
FROM capital_transactions
ORDER BY created_at DESC
LIMIT 1

UNION ALL

SELECT
  'Portfolio state' as source,
  closed_equity as equity
FROM portfolio_state
WHERE id = 1;
