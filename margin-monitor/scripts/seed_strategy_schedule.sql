-- ================================================================
-- Auto-Hedge Strategy Schedule Seed Data
-- ================================================================
--
-- This script populates the strategy_schedule table with the
-- standard portfolio entry/exit times for each trading day.
--
-- Run with: psql -d portfolio_manager -f seed_strategy_schedule.sql
-- ================================================================

-- Clear existing data
TRUNCATE TABLE auto_hedge.strategy_schedule CASCADE;

-- ================================================================
-- MONDAY - Nifty 1DTE (for Tuesday expiry)
-- ================================================================
INSERT INTO auto_hedge.strategy_schedule
(day_of_week, index_name, expiry_type, portfolio_name, entry_time, exit_time)
VALUES
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 1', '09:19:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 2', '09:22:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 3', '09:52:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 4', '10:58:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 5', '12:38:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 6', '13:52:00', '15:25:00'),
('Monday', 'NIFTY', '1DTE', 'NF_MON_1DTE 7', '14:04:00', '15:25:00');

-- ================================================================
-- TUESDAY - Nifty 0DTE (Expiry Day)
-- ================================================================
INSERT INTO auto_hedge.strategy_schedule
(day_of_week, index_name, expiry_type, portfolio_name, entry_time, exit_time)
VALUES
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 1', '09:16:00', '14:15:00'),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 2', '09:24:00', '14:00:00'),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 3', '09:29:00', '14:15:00'),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 4', '10:16:30', '13:15:00'),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 5', '13:53:30', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 6', '14:11:00', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 7', '14:16:00', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 8', '14:25:00', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 9', '14:28:00', NULL),
('Tuesday', 'NIFTY', '0DTE', 'ITJ_NF_EXP 10', '14:35:00', NULL);

-- ================================================================
-- THURSDAY - Sensex 0DTE (Expiry Day)
-- ================================================================
INSERT INTO auto_hedge.strategy_schedule
(day_of_week, index_name, expiry_type, portfolio_name, entry_time, exit_time)
VALUES
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 1', '09:16:00', '14:00:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 2', '09:18:00', '13:15:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 3', '09:28:00', '14:00:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 4', '09:55:00', '14:30:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 5', '10:53:00', '14:30:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 6', '11:02:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 7', '11:37:00', '14:30:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 8', '12:09:00', '15:00:00'),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 9', '12:54:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 10', '13:58:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 11', '14:04:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 12', '14:34:00', NULL),
('Thursday', 'SENSEX', '0DTE', 'TH_SX_EXP 13', '14:43:00', NULL);

-- ================================================================
-- FRIDAY - Nifty 2DTE (for Tuesday expiry)
-- ================================================================
INSERT INTO auto_hedge.strategy_schedule
(day_of_week, index_name, expiry_type, portfolio_name, entry_time, exit_time)
VALUES
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 1', '09:19:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 2', '09:25:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 3', '09:33:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 4', '09:40:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 5', '10:50:00', '15:25:00'),
('Friday', 'NIFTY', '2DTE', 'NIFTY_FRI 6', '11:38:10', '15:25:00');

-- Verify
SELECT
    day_of_week,
    index_name,
    expiry_type,
    COUNT(*) as portfolio_count
FROM auto_hedge.strategy_schedule
WHERE is_active = true
GROUP BY day_of_week, index_name, expiry_type
ORDER BY
    CASE day_of_week
        WHEN 'Monday' THEN 1
        WHEN 'Tuesday' THEN 2
        WHEN 'Wednesday' THEN 3
        WHEN 'Thursday' THEN 4
        WHEN 'Friday' THEN 5
    END;
