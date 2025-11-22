-- Deduplication function for leads table
-- Keeps the oldest record (lowest id) for each unique profile_url
-- Merges non-empty data from duplicates into the kept record

CREATE OR REPLACE FUNCTION dedupe_leads()
RETURNS TABLE(
    duplicates_found INTEGER,
    duplicates_removed INTEGER
) AS $$
DECLARE
    dup_count INTEGER;
    removed_count INTEGER;
BEGIN
    -- Count duplicates before deduplication
    SELECT COUNT(*) - COUNT(DISTINCT profile_url) INTO dup_count
    FROM leads
    WHERE profile_url IS NOT NULL AND profile_url != '';
    
    -- Create temporary table with the records to keep (oldest for each profile_url)
    CREATE TEMP TABLE IF NOT EXISTS leads_to_keep AS
    SELECT DISTINCT ON (profile_url) *
    FROM leads
    WHERE profile_url IS NOT NULL AND profile_url != ''
    ORDER BY profile_url, id ASC;
    
    -- Update the kept records with any non-empty data from duplicates
    UPDATE leads
    SET
        email_address = COALESCE(NULLIF(leads.email_address, ''), dup.email_address),
        phone_number = COALESCE(NULLIF(leads.phone_number, ''), dup.phone_number),
        notes = COALESCE(NULLIF(leads.notes, ''), dup.notes),
        feedback = COALESCE(NULLIF(leads.feedback, ''), dup.feedback),
        updated_at = CURRENT_TIMESTAMP
    FROM (
        SELECT 
            l.profile_url,
            MAX(CASE WHEN l.email_address != '' THEN l.email_address END) as email_address,
            MAX(CASE WHEN l.phone_number != '' THEN l.phone_number END) as phone_number,
            MAX(CASE WHEN l.notes != '' THEN l.notes END) as notes,
            MAX(CASE WHEN l.feedback != '' THEN l.feedback END) as feedback
        FROM leads l
        WHERE l.profile_url IS NOT NULL AND l.profile_url != ''
        GROUP BY l.profile_url
        HAVING COUNT(*) > 1
    ) dup
    WHERE leads.id IN (
        SELECT id FROM leads_to_keep WHERE leads_to_keep.profile_url = dup.profile_url
    )
    AND leads.profile_url = dup.profile_url;
    
    -- Delete duplicate records (keeping only the oldest)
    DELETE FROM leads
    WHERE id NOT IN (SELECT id FROM leads_to_keep)
    AND profile_url IN (SELECT profile_url FROM leads_to_keep);
    
    GET DIAGNOSTICS removed_count = ROW_COUNT;
    
    -- Clean up temp table
    DROP TABLE IF EXISTS leads_to_keep;
    
    -- Return results
    RETURN QUERY SELECT dup_count, removed_count;
END;
$$ LANGUAGE plpgsql;

-- Create a simpler function that just returns a summary
CREATE OR REPLACE FUNCTION run_dedupe()
RETURNS TEXT AS $$
DECLARE
    result RECORD;
    message TEXT;
BEGIN
    SELECT * INTO result FROM dedupe_leads();
    
    message := format('Deduplication complete: Found %s duplicates, removed %s records', 
                     result.duplicates_found, 
                     result.duplicates_removed);
    
    RETURN message;
END;
$$ LANGUAGE plpgsql;

