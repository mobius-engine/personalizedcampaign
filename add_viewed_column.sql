-- Add viewed tracking columns to leads table

ALTER TABLE leads 
ADD COLUMN IF NOT EXISTS viewed BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS viewed_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS viewed_by VARCHAR(255);

-- Create index for faster queries on viewed status
CREATE INDEX IF NOT EXISTS idx_leads_viewed ON leads(viewed);

-- Create index for faster queries on viewed_at
CREATE INDEX IF NOT EXISTS idx_leads_viewed_at ON leads(viewed_at);

COMMENT ON COLUMN leads.viewed IS 'Whether this lead has been viewed/contacted';
COMMENT ON COLUMN leads.viewed_at IS 'When the lead was marked as viewed';
COMMENT ON COLUMN leads.viewed_by IS 'User who viewed the lead';

