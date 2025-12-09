-- Restore data from position-calculator.csv backup
-- Source: /Users/shankarvasudevan/Library/CloudStorage/OneDrive-Personal/Performance/2025 to 2026/position-calculator.csv
-- Date: 2025-12-09

BEGIN;

-- 1. Restore portfolio_state
-- Starting equity: 5,111,496
-- Current equity after loss: 5,084,296 (5,111,496 - 27,200)
INSERT INTO portfolio_state (id, initial_capital, closed_equity, total_risk_amount, total_risk_percent, total_vol_amount, margin_used, version)
VALUES (1, 5111496.00, 5084296.00, 0.00, 0.00, 0.00, 0.00, 1)
ON CONFLICT (id) DO UPDATE SET
    initial_capital = EXCLUDED.initial_capital,
    closed_equity = EXCLUDED.closed_equity,
    updated_at = CURRENT_TIMESTAMP;

-- 2. Add closed trade to strategy_trade_history
-- Trade: GOLD_MINI LONG, entry 130051.67, exit 129145, loss -27200.10
INSERT INTO strategy_trade_history (
    strategy_id,
    position_id,
    instrument,
    symbol,
    direction,
    lots,
    entry_price,
    exit_price,
    realized_pnl,
    opened_at,
    closed_at
) VALUES (
    1,  -- ITJ Trend Follow
    'Long_1',
    'GOLD_MINI',
    'GOLDM25DEC31FUT',
    'LONG',
    3,
    130051.67,
    129145.00,
    -27200.10,
    '2025-12-05 15:40:00',
    '2025-12-05 16:30:00'
);

-- 3. Update strategy cumulative P&L
UPDATE trading_strategies
SET cumulative_realized_pnl = -27200.10,
    updated_at = CURRENT_TIMESTAMP
WHERE strategy_id = 1;

COMMIT;

-- Verify restoration
SELECT 'portfolio_state' as table_name, initial_capital, closed_equity FROM portfolio_state;
SELECT 'strategy_trade_history' as table_name, position_id, instrument, realized_pnl FROM strategy_trade_history;
SELECT 'trading_strategies' as table_name, strategy_name, cumulative_realized_pnl FROM trading_strategies WHERE strategy_id = 1;
