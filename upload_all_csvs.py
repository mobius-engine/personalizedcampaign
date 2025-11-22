#!/usr/bin/env python3
"""Upload all CSV files from Google Drive to the database."""

import os
import sys
import csv
from io import StringIO
import psycopg2
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
FOLDER_ID = "1wdE3pA0JzTi831Yn3QeDwHDmbo5eNFc3"
SERVICE_ACCOUNT_KEY = os.path.expanduser("~/Downloads/jobs-data-linkedin-52d03efe8395.json")
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

DB_CONFIG = {
    'host': '35.193.184.122',
    'database': 'linkedin_leads_data',
    'user': 'postgres',
    'password': sys.argv[1] if len(sys.argv) > 1 else '',
}


def get_drive_service():
    """Initialize Google Drive service."""
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_KEY, scopes=SCOPES
    )
    return build('drive', 'v3', credentials=credentials)


def list_csv_files():
    """List all CSV files in the Google Drive folder."""
    service = get_drive_service()
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType='text/csv'",
        pageSize=100,
        orderBy='modifiedTime desc',
        fields="files(id, name, mimeType, modifiedTime)"
    ).execute()
    return results.get('files', [])


def download_csv(file_id):
    """Download CSV content from Google Drive."""
    service = get_drive_service()
    request = service.files().get_media(fileId=file_id)
    content = request.execute().decode('utf-8')
    return content


def normalize_column_name(name):
    """Convert CSV column names to database column names."""
    mapping = {
        'First Name': 'first_name',
        'Last Name': 'last_name',
        'Headline': 'headline',
        'Location': 'location',
        'Current Title': 'current_title',
        'Current Company': 'current_company',
        'Email Address': 'email_address',
        'Phone Number': 'phone_number',
        'Profile URL': 'profile_url',
        'Active Project': 'active_project',
        'Notes': 'notes',
        'Feedback': 'feedback',
    }
    return mapping.get(name, name.lower().replace(' ', '_'))


def upload_csv_to_db(csv_content, filename, conn):
    """Upload CSV data to database with upsert logic."""
    cursor = conn.cursor()
    
    csv_reader = csv.DictReader(StringIO(csv_content))
    
    rows_inserted = 0
    rows_updated = 0
    rows_failed = 0
    
    for row in csv_reader:
        try:
            data = {normalize_column_name(k): v for k, v in row.items()}
            
            if not data.get('profile_url'):
                rows_failed += 1
                continue
            
            query = """
                INSERT INTO leads (
                    first_name, last_name, headline, location, current_title,
                    current_company, email_address, phone_number, profile_url,
                    active_project, notes, feedback
                ) VALUES (
                    %(first_name)s, %(last_name)s, %(headline)s, %(location)s, %(current_title)s,
                    %(current_company)s, %(email_address)s, %(phone_number)s, %(profile_url)s,
                    %(active_project)s, %(notes)s, %(feedback)s
                )
                ON CONFLICT (profile_url) DO UPDATE SET
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    headline = EXCLUDED.headline,
                    location = EXCLUDED.location,
                    current_title = EXCLUDED.current_title,
                    current_company = EXCLUDED.current_company,
                    email_address = COALESCE(NULLIF(EXCLUDED.email_address, ''), leads.email_address),
                    phone_number = COALESCE(NULLIF(EXCLUDED.phone_number, ''), leads.phone_number),
                    active_project = EXCLUDED.active_project,
                    notes = COALESCE(NULLIF(EXCLUDED.notes, ''), leads.notes),
                    feedback = COALESCE(NULLIF(EXCLUDED.feedback, ''), leads.feedback),
                    updated_at = CURRENT_TIMESTAMP
                RETURNING (xmax = 0) AS inserted;
            """
            
            cursor.execute(query, data)
            result = cursor.fetchone()
            
            if result and result[0]:
                rows_inserted += 1
            else:
                rows_updated += 1
                
        except Exception as e:
            print(f"  ⚠️  Error processing row: {e}")
            rows_failed += 1
            continue
    
    cursor.execute("""
        INSERT INTO upload_history (filename, rows_inserted, rows_updated, rows_failed, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (filename, rows_inserted, rows_updated, rows_failed, 'success'))
    
    conn.commit()
    cursor.close()
    
    return rows_inserted, rows_updated, rows_failed


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 upload_all_csvs.py <database_password>")
        sys.exit(1)
    
    # Connect to database
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ Connected to database\n")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)
    
    # Get all CSV files
    files = list_csv_files()
    print(f"Found {len(files)} CSV files to upload")
    print("=" * 80)
    
    total_inserted = 0
    total_updated = 0
    total_failed = 0
    
    for i, file in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] Uploading: {file['name']}")
        
        try:
            csv_content = download_csv(file['id'])
            inserted, updated, failed = upload_csv_to_db(csv_content, file['name'], conn)
            
            print(f"  ✅ Inserted: {inserted}, Updated: {updated}, Failed: {failed}")
            
            total_inserted += inserted
            total_updated += updated
            total_failed += failed
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    print("\n" + "=" * 80)
    print("📊 Summary:")
    print(f"  Total Inserted: {total_inserted}")
    print(f"  Total Updated: {total_updated}")
    print(f"  Total Failed: {total_failed}")
    print("=" * 80)
    
    conn.close()


if __name__ == "__main__":
    main()

