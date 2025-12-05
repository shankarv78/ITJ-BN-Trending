-- Migration 003: Add Leadership History Table
-- Date: 2025-11-29
-- Purpose: Track leadership transitions for audit trail and debugging
--
-- This table enables answering questions like:
-- - "Who was leader between 2PM-3PM?"
-- - "How long was each leadership session?"
-- - "Which instance had the most leadership changes?"
--
-- Note: Simplified for Phase 1 - no release_reason tracking (moved to Phase 3)

CREATE TABLE IF NOT EXISTS leadership_history (
    id SERIAL PRIMARY KEY,
    instance_id VARCHAR(255) NOT NULL,
    became_leader_at TIMESTAMP NOT NULL,
    released_leader_at TIMESTAMP,
    leadership_duration_seconds INTEGER,
    hostname VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index for timeline queries (most recent first)
CREATE INDEX IF NOT EXISTS idx_leadership_history_timeline
ON leadership_history(became_leader_at DESC, released_leader_at DESC);

-- Index for instance-specific queries
CREATE INDEX IF NOT EXISTS idx_leadership_history_instance
ON leadership_history(instance_id, became_leader_at DESC);

-- Note: release_reason column removed from Phase 1 (moved to Phase 3 per TASK22_3_ISSUEFIXPLAN.md)

