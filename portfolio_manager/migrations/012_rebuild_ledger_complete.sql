-- Migration 012: Rebuild ledger with ALL trades in chronological order
-- This fixes the missing P&L from trades before Dec 26
-- Amount is now signed: positive for profits, negative for losses

BEGIN;

-- Clear existing transactions (we'll rebuild from scratch)
DELETE FROM capital_transactions;

-- Reset sequence
ALTER SEQUENCE capital_transactions_id_seq RESTART WITH 1;

-- 1. First deposit: Nov 1, 2025
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, created_at)
VALUES ('DEPOSIT', 5000000.00, 'Initial capital for Trend Following portfolio', 0.00, 5000000.00, 'MANUAL', '2025-11-01 09:00:00');

-- 2. BANK_NIFTY_Long_2: Nov 19, +43059 (PROFIT)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 43059.00, 'BANK_NIFTY trade P&L: +₹43,059.00', 5000000.00, 5043059.00, 'MIGRATION', 'BANK_NIFTY_Long_2', '2025-11-19 15:30:00');

-- 3. BANK_NIFTY_Long_3: Nov 21, -105000 (LOSS)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', -105000.00, 'BANK_NIFTY trade P&L: -₹1,05,000.00', 5043059.00, 4938059.00, 'MIGRATION', 'BANK_NIFTY_Long_3', '2025-11-21 15:30:00');

-- 4. GOLD_MINI_Long_4: Nov 27, +10733 (PROFIT)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 10733.00, 'GOLD_MINI trade P&L: +₹10,733.00', 4938059.00, 4948792.00, 'MIGRATION', 'GOLD_MINI_Long_4', '2025-11-27 15:30:00');

-- 5. BANK_NIFTY_Long_5: Dec 2, -16375 (LOSS)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', -16375.00, 'BANK_NIFTY trade P&L: -₹16,375.00', 4948792.00, 4932417.00, 'MIGRATION', 'BANK_NIFTY_Long_5', '2025-12-02 15:30:00');

-- 6. GOLD_MINI_Long_6: Dec 2, +89450 (PROFIT)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 89450.00, 'GOLD_MINI trade P&L: +₹89,450.00', 4932417.00, 5021867.00, 'MIGRATION', 'GOLD_MINI_Long_6', '2025-12-02 15:30:01');

-- 7. BANK_NIFTY_Long_7: Dec 8, -9451 (LOSS)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', -9451.00, 'BANK_NIFTY trade P&L: -₹9,451.00', 5021867.00, 5012416.00, 'MIGRATION', 'BANK_NIFTY_Long_7', '2025-12-08 15:30:00');

-- 8. GOLD_MINI_Long_8: Dec 11, +34690 (PROFIT)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 34690.00, 'GOLD_MINI trade P&L: +₹34,690.00', 5012416.00, 5047106.00, 'MIGRATION', 'GOLD_MINI_Long_8', '2025-12-11 15:30:00');

-- 9. GOLD_MINI_Long_9: Dec 12, +89100 (PROFIT)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 89100.00, 'GOLD_MINI trade P&L: +₹89,100.00', 5047106.00, 5136206.00, 'MIGRATION', 'GOLD_MINI_Long_9', '2025-12-12 15:30:00');

-- 10. GOLD_MINI_Long_10: Dec 23, +15560 (PROFIT)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 15560.00, 'GOLD_MINI trade P&L: +₹15,560.00', 5136206.00, 5151766.00, 'MIGRATION', 'GOLD_MINI_Long_10', '2025-12-23 15:30:00');

-- 11. SILVER_MINI_Long_11: Dec 26 15:30, +35010 (PROFIT - BEFORE the deposit at 21:33)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 35010.00, 'SILVER_MINI trade P&L: +₹35,010.00', 5151766.00, 5186776.00, 'MIGRATION', 'SILVER_MINI_Long_11', '2025-12-26 15:30:00');

-- 12. Second deposit: Dec 26 21:33:05 (equity_before now correctly reflects all prior P&L)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, created_at)
VALUES ('DEPOSIT', 5000000.00, 'Increasing capital as we have 2.5R profits', 5186776.00, 10186776.00, 'API', '2025-12-26 21:33:05.370418');

-- 13. SILVER_MINI_Long_12: Dec 29, +46815 (PROFIT)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 46815.00, 'SILVER_MINI trade P&L: +₹46,815.00', 10186776.00, 10233591.00, 'MIGRATION', 'SILVER_MINI_Long_12', '2025-12-29 15:30:00');

-- 14. SILVER_MINI_Long_13: Dec 31, -36955 (LOSS)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', -36955.00, 'SILVER_MINI trade P&L: -₹36,955.00', 10233591.00, 10196636.00, 'MIGRATION', 'SILVER_MINI_Long_13', '2025-12-31 15:30:00');

-- 15. BANK_NIFTY_Long_14: Dec 31, -2064 (LOSS)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', -2064.00, 'BANK_NIFTY trade P&L: -₹2,064.00', 10196636.00, 10194572.00, 'MIGRATION', 'BANK_NIFTY_Long_14', '2025-12-31 15:30:01');

-- 16. GOLD_MINI_Long_1: Jan 2, -105811.20 (LOSS)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', -105811.20, 'GOLD_MINI trade P&L: -₹1,05,811.20', 10194572.00, 10088760.80, 'MIGRATION', 'GOLD_MINI_Long_1', '2026-01-02 19:00:00');

-- 17. BANK_NIFTY_Long_1: Jan 5, +23280 (PROFIT)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 23280.00, 'BANK_NIFTY trade P&L: +₹23,280.00', 10088760.80, 10112040.80, 'MIGRATION', 'BANK_NIFTY_Long_1', '2026-01-05 14:19:12');

-- 18. SILVER_MINI_Long_1: Jan 7, +11880 (PROFIT)
INSERT INTO capital_transactions (transaction_type, amount, notes, equity_before, equity_after, created_by, position_id, created_at)
VALUES ('TRADING_PNL', 11880.00, 'SILVER_MINI trade P&L: +₹11,880.00', 10112040.80, 10123920.80, 'MIGRATION', 'SILVER_MINI_Long_1', '2026-01-07 19:00:19.91178');

-- Update portfolio_state to match
UPDATE portfolio_state
SET closed_equity = 10123920.80,
    initial_capital = 10000000.00,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE id = 1;

COMMIT;

-- Verification queries
SELECT 'Final ledger equity' as check, equity_after as value FROM capital_transactions ORDER BY created_at DESC LIMIT 1;
