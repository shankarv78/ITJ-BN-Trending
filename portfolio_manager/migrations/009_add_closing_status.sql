-- Portfolio Manager - Add 'closing' status to check_status constraint
-- Migration: 009_add_closing_status.sql
-- Created: 2026-01-05
-- Description: Adds 'closing' as valid status for PM-initiated stop exits
--
-- Background:
-- The PM-side stop monitoring feature (commit f65c746) introduced 'closing'
-- as a transient state to prevent race conditions during exits. However,
-- the database constraint was not updated, causing stop exits to fail with:
--   "new row for relation 'portfolio_positions' violates check constraint 'check_status'"
--
-- This migration fixes that oversight.

-- Drop old constraint
ALTER TABLE portfolio_positions DROP CONSTRAINT IF EXISTS check_status;

-- Add new constraint with 'closing' status
ALTER TABLE portfolio_positions ADD CONSTRAINT check_status
  CHECK (status IN ('open', 'closed', 'partial', 'closing'));

-- Status meanings:
--   'open'    - Position is active
--   'closing' - Exit order placed, awaiting fill (transient, prevents double exits)
--   'closed'  - Position fully closed
--   'partial' - Position partially closed (scaled exits)
