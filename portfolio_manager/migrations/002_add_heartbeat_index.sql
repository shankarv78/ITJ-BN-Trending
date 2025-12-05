-- Migration 002: Add Index for Stale Leader Detection
-- Date: 2025-11-29
-- Purpose: Optimize queries for detecting stale leaders and split-brain scenarios
--
-- This index enables efficient queries for:
-- 1. Stale leader detection (get_stale_instances)
-- 2. Current leader lookup (get_current_leader_from_db)
-- 3. Split-brain detection (comparing Redis vs DB leader)

-- Index for efficient stale leader queries
-- Filters on is_leader = TRUE and orders by last_heartbeat DESC
CREATE INDEX IF NOT EXISTS idx_instance_metadata_heartbeat_leader
ON instance_metadata(last_heartbeat DESC, is_leader)
WHERE is_leader = TRUE;

-- Note: The existing idx_last_heartbeat index (from 001_initial_schema.sql)
-- covers general heartbeat queries, but this partial index is optimized
-- specifically for leader-related queries.

