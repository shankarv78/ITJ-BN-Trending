-- ============================================================================
-- Migration 010: Signal Audit Table
--
-- Purpose: Comprehensive audit trail for all signals received by PM
-- Records: outcome, rejection reasons, validation results, sizing calculations
-- Retention: 90 days (vs 7 days for signal_log)
--
-- Author: Claude Code
-- Date: January 2026
-- ============================================================================

-- Drop table if exists (for clean re-runs during development)
-- REMOVE THIS LINE BEFORE PRODUCTION USE
-- DROP TABLE IF EXISTS signal_audit CASCADE;

CREATE TABLE IF NOT EXISTS signal_audit (
    id BIGSERIAL PRIMARY KEY,

    -- ========================================================================
    -- Signal Identification
    -- ========================================================================

    -- Link to original signal_log entry (optional - may not exist for all signals)
    signal_log_id BIGINT REFERENCES signal_log(id) ON DELETE SET NULL,

    -- Unique fingerprint for deduplication (same as signal_log)
    signal_fingerprint VARCHAR(64) NOT NULL,

    -- Signal details (denormalized for query performance)
    instrument VARCHAR(20) NOT NULL,        -- BANK_NIFTY, GOLD_MINI, SILVER_MINI
    signal_type VARCHAR(20) NOT NULL,       -- ENTRY, PYRAMID, EXIT, EXIT_ALL
    position VARCHAR(20) NOT NULL,          -- LONG, SHORT, ALL
    signal_timestamp TIMESTAMP NOT NULL,    -- When signal was generated (from TV)
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- When PM received it

    -- ========================================================================
    -- Outcome & Decision
    -- ========================================================================

    -- Final outcome of signal processing
    outcome VARCHAR(30) NOT NULL,
    -- Valid outcomes:
    --   PROCESSED           - Signal accepted, order placed
    --   REJECTED_VALIDATION - Failed signal validation (stale, future, etc.)
    --   REJECTED_RISK       - Failed risk checks (margin, position limit)
    --   REJECTED_DUPLICATE  - Duplicate signal (already processed)
    --   REJECTED_MARKET     - Market closed or holiday
    --   REJECTED_MANUAL     - User rejected via voice prompt
    --   FAILED_ORDER        - Signal valid but order placement failed
    --   PARTIAL_FILL        - Order partially filled

    -- Human-readable reason for outcome
    outcome_reason TEXT,

    -- ========================================================================
    -- Decision Data (JSONB for flexibility)
    -- ========================================================================

    -- Validation stage results
    -- {
    --   "condition_validation": {"is_valid": true, "severity": "NORMAL", "signal_age_seconds": 3.2},
    --   "execution_validation": {"is_valid": true, "divergence_pct": 0.12, "direction": "favorable"}
    -- }
    validation_result JSONB,

    -- Position sizing calculation
    -- {
    --   "method": "TOM_BASSO",
    --   "inputs": {"equity_high": 5200000, "risk_percent": 1.0, "stop_distance": 245.5, ...},
    --   "calculation": {"risk_amount": 52000, "raw_lots": 4.72, "final_lots": 3},
    --   "constraints_applied": [{"constraint": "FLOOR", "before": 3.4, "after": 3}],
    --   "limiter": "RISK"
    -- }
    sizing_calculation JSONB,

    -- Risk assessment
    -- {
    --   "pre_trade_risk_pct": 2.5,
    --   "post_trade_risk_pct": 3.5,
    --   "margin_available": 1500000,
    --   "margin_required": 390000,
    --   "checks_passed": ["MARGIN", "MAX_POSITIONS", "RISK_LIMIT"]
    -- }
    risk_assessment JSONB,

    -- Order execution summary (detailed in order_execution_log)
    -- {
    --   "order_id": "ZRD_123456",
    --   "execution_status": "SUCCESS",
    --   "fill_price": 52172.80,
    --   "slippage_pct": 0.053,
    --   "execution_time_ms": 1850
    -- }
    order_execution JSONB,

    -- ========================================================================
    -- Metadata
    -- ========================================================================

    -- Processing performance
    processing_duration_ms INTEGER,

    -- Which PM instance processed this signal (for HA debugging)
    processed_by_instance VARCHAR(50),

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- ========================================================================
    -- Constraints
    -- ========================================================================

    -- Ensure unique fingerprint (same signal can't be audited twice)
    CONSTRAINT uq_signal_audit_fingerprint UNIQUE (signal_fingerprint),

    -- Validate outcome values
    CONSTRAINT chk_signal_audit_outcome CHECK (
        outcome IN (
            'PROCESSED',
            'REJECTED_VALIDATION',
            'REJECTED_RISK',
            'REJECTED_DUPLICATE',
            'REJECTED_MARKET',
            'REJECTED_MANUAL',
            'FAILED_ORDER',
            'PARTIAL_FILL'
        )
    ),

    -- Validate signal_type values
    CONSTRAINT chk_signal_audit_type CHECK (
        signal_type IN ('ENTRY', 'PYRAMID', 'EXIT', 'EXIT_ALL', 'MARKET_DATA', 'EOD_MONITOR')
    ),

    -- Validate instrument values
    CONSTRAINT chk_signal_audit_instrument CHECK (
        instrument IN ('BANK_NIFTY', 'GOLD_MINI', 'SILVER_MINI', 'NIFTY', 'SENSEX')
    )
);

-- ============================================================================
-- Indexes for common query patterns
-- ============================================================================

-- Query signals by instrument and time range
CREATE INDEX IF NOT EXISTS idx_signal_audit_instrument_time
    ON signal_audit(instrument, signal_timestamp DESC);

-- Query signals by outcome (e.g., find all rejections)
CREATE INDEX IF NOT EXISTS idx_signal_audit_outcome
    ON signal_audit(outcome);

-- Query recent signals (for Telegram bot /signals command)
CREATE INDEX IF NOT EXISTS idx_signal_audit_created
    ON signal_audit(created_at DESC);

-- Query by signal type
CREATE INDEX IF NOT EXISTS idx_signal_audit_type
    ON signal_audit(signal_type);

-- Combined index for dashboard queries
CREATE INDEX IF NOT EXISTS idx_signal_audit_instrument_outcome
    ON signal_audit(instrument, outcome, created_at DESC);

-- ============================================================================
-- Comments for documentation
-- ============================================================================

COMMENT ON TABLE signal_audit IS 'Comprehensive audit trail for all signals received by Portfolio Manager. 90-day retention.';
COMMENT ON COLUMN signal_audit.outcome IS 'Final outcome: PROCESSED, REJECTED_*, FAILED_ORDER, PARTIAL_FILL';
COMMENT ON COLUMN signal_audit.validation_result IS 'JSON containing condition and execution validation results';
COMMENT ON COLUMN signal_audit.sizing_calculation IS 'JSON containing position sizing inputs, calculation, and constraints';
COMMENT ON COLUMN signal_audit.risk_assessment IS 'JSON containing risk checks performed before order placement';
COMMENT ON COLUMN signal_audit.order_execution IS 'JSON summary of order execution (details in order_execution_log)';

-- ============================================================================
-- Verification query (run after migration)
-- ============================================================================
-- SELECT
--     table_name,
--     column_name,
--     data_type,
--     is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'signal_audit'
-- ORDER BY ordinal_position;
