-- ============================================================================
-- Migration 012: Audit Trail Cleanup Functions
--
-- Purpose: 90-day retention policy for signal_audit and order_execution_log
-- Schedule: Run daily via cron or PM background task
--
-- Author: Claude Code
-- Date: January 2026
-- ============================================================================

-- ============================================================================
-- Cleanup function for signal_audit (90 days retention)
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_old_signal_audits(retention_days INTEGER DEFAULT 90)
RETURNS TABLE(deleted_count BIGINT, oldest_remaining TIMESTAMP) AS $$
DECLARE
    cutoff_date TIMESTAMP;
    rows_deleted BIGINT;
    oldest_record TIMESTAMP;
BEGIN
    cutoff_date := NOW() - make_interval(days => retention_days);

    -- Delete old records
    DELETE FROM signal_audit
    WHERE created_at < cutoff_date;

    GET DIAGNOSTICS rows_deleted = ROW_COUNT;

    -- Get oldest remaining record
    SELECT MIN(created_at) INTO oldest_record FROM signal_audit;

    RETURN QUERY SELECT rows_deleted, oldest_record;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_signal_audits IS 'Deletes signal_audit records older than retention_days (default 90). Returns count deleted and oldest remaining.';

-- ============================================================================
-- Cleanup function for order_execution_log (90 days retention)
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_old_order_executions(retention_days INTEGER DEFAULT 90)
RETURNS TABLE(deleted_count BIGINT, oldest_remaining TIMESTAMP) AS $$
DECLARE
    cutoff_date TIMESTAMP;
    child_deleted BIGINT;
    parent_deleted BIGINT;
    oldest_record TIMESTAMP;
BEGIN
    cutoff_date := NOW() - make_interval(days => retention_days);

    -- Delete old records (child records first due to self-referencing FK)
    -- Step 1: Delete child legs (records with parent_order_id pointing to old parents)
    DELETE FROM order_execution_log
    WHERE parent_order_id IN (
        SELECT id FROM order_execution_log
        WHERE created_at < cutoff_date
        AND parent_order_id IS NULL  -- Only parent records
    );

    GET DIAGNOSTICS child_deleted = ROW_COUNT;

    -- Step 2: Delete parent records (now safe since children are gone)
    DELETE FROM order_execution_log
    WHERE created_at < cutoff_date
    AND parent_order_id IS NULL;

    GET DIAGNOSTICS parent_deleted = ROW_COUNT;

    -- Get oldest remaining record
    SELECT MIN(created_at) INTO oldest_record FROM order_execution_log;

    RETURN QUERY SELECT child_deleted + parent_deleted, oldest_record;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_old_order_executions IS 'Deletes order_execution_log records older than retention_days (default 90). Returns count deleted and oldest remaining.';

-- ============================================================================
-- Combined cleanup function (call this from scheduler)
-- ============================================================================

CREATE OR REPLACE FUNCTION cleanup_audit_trail(retention_days INTEGER DEFAULT 90)
RETURNS TABLE(
    table_name TEXT,
    deleted_count BIGINT,
    oldest_remaining TIMESTAMP
) AS $$
DECLARE
    signal_deleted BIGINT;
    signal_oldest TIMESTAMP;
    order_deleted BIGINT;
    order_oldest TIMESTAMP;
BEGIN
    -- Cleanup order_execution_log first (has FK to signal_audit)
    SELECT * INTO order_deleted, order_oldest
    FROM cleanup_old_order_executions(retention_days);

    -- Then cleanup signal_audit
    SELECT * INTO signal_deleted, signal_oldest
    FROM cleanup_old_signal_audits(retention_days);

    -- Return results
    RETURN QUERY
    SELECT 'order_execution_log'::TEXT, order_deleted, order_oldest
    UNION ALL
    SELECT 'signal_audit'::TEXT, signal_deleted, signal_oldest;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION cleanup_audit_trail IS 'Master cleanup function for audit trail. Call daily: SELECT * FROM cleanup_audit_trail(90);';

-- ============================================================================
-- View for audit trail statistics (for monitoring)
-- ============================================================================

CREATE OR REPLACE VIEW audit_trail_stats AS
SELECT
    'signal_audit' AS table_name,
    COUNT(*) AS total_records,
    MIN(created_at) AS oldest_record,
    MAX(created_at) AS newest_record,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 day') AS records_today,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') AS records_7days,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') AS records_30days,
    pg_size_pretty(pg_total_relation_size('signal_audit')) AS table_size
FROM signal_audit

UNION ALL

SELECT
    'order_execution_log' AS table_name,
    COUNT(*) AS total_records,
    MIN(created_at) AS oldest_record,
    MAX(created_at) AS newest_record,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 day') AS records_today,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') AS records_7days,
    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') AS records_30days,
    pg_size_pretty(pg_total_relation_size('order_execution_log')) AS table_size
FROM order_execution_log;

COMMENT ON VIEW audit_trail_stats IS 'Statistics view for monitoring audit trail tables. Query: SELECT * FROM audit_trail_stats;';

-- ============================================================================
-- Usage Examples
-- ============================================================================
--
-- 1. Run daily cleanup (90 days retention):
--    SELECT * FROM cleanup_audit_trail(90);
--
-- 2. Check audit trail statistics:
--    SELECT * FROM audit_trail_stats;
--
-- 3. Manual cleanup with custom retention:
--    SELECT * FROM cleanup_audit_trail(30);  -- Keep only 30 days
--
-- 4. Check what would be deleted (dry run):
--    SELECT COUNT(*) FROM signal_audit WHERE created_at < NOW() - INTERVAL '90 days';
--    SELECT COUNT(*) FROM order_execution_log WHERE created_at < NOW() - INTERVAL '90 days';
--
-- ============================================================================
