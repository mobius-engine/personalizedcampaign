-- Add hook column to leads table
ALTER TABLE leads ADD COLUMN IF NOT EXISTS hook TEXT;

-- Add index for searching hooks
CREATE INDEX IF NOT EXISTS idx_leads_hook ON leads(hook);

-- Add column to track when hook was generated
ALTER TABLE leads ADD COLUMN IF NOT EXISTS hook_generated_at TIMESTAMP;

