-- Add override tracking columns to guardrail_checks
ALTER TABLE guardrail_checks
ADD COLUMN IF NOT EXISTS override_reason TEXT,
ADD COLUMN IF NOT EXISTS overridden_by TEXT,
ADD COLUMN IF NOT EXISTS overridden_at TIMESTAMPTZ;
