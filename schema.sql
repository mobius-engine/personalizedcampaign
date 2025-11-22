-- LinkedIn Leads Database Schema

-- Create leads table
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    headline TEXT,
    location VARCHAR(255),
    current_title VARCHAR(500),
    current_company VARCHAR(255),
    email_address VARCHAR(255),
    phone_number VARCHAR(50),
    profile_url VARCHAR(500) UNIQUE,
    active_project VARCHAR(255),
    notes TEXT,
    feedback TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on profile_url for faster lookups
CREATE INDEX IF NOT EXISTS idx_leads_profile_url ON leads(profile_url);

-- Create index on email for faster lookups
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email_address);

-- Create index on active_project for filtering
CREATE INDEX IF NOT EXISTS idx_leads_active_project ON leads(active_project);

-- Create index on company for filtering
CREATE INDEX IF NOT EXISTS idx_leads_company ON leads(current_company);

-- Create function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to automatically update updated_at
CREATE TRIGGER update_leads_updated_at BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Create upload_history table to track CSV uploads
CREATE TABLE IF NOT EXISTS upload_history (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(500),
    rows_inserted INTEGER,
    rows_updated INTEGER,
    rows_failed INTEGER,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50),
    error_message TEXT
);

-- Grant permissions to app_user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO app_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO app_user;

