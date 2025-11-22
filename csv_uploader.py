#!/usr/bin/env python3
"""
CSV Uploader for LinkedIn Leads Database

This utility uploads CSV files from Google Drive to Cloud SQL database.
It handles both new inserts and updates based on profile_url.
"""

import os
import sys
import csv
import argparse
from io import StringIO
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Configuration
FOLDER_ID = "1wdE3pA0JzTi831Yn3QeDwHDmbo5eNFc3"
SERVICE_ACCOUNT_KEY = os.path.expanduser("~/Downloads/jobs-data-linkedin-52d03efe8395.json")
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']

# Database configuration (will be set via environment variables or arguments)
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '35.193.184.122'),
    'database': os.getenv('DB_NAME', 'linkedin_leads_data'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
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
        fields="files(id, name, mimeType, modifiedTime, size)"
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
    
    # Parse CSV
    csv_reader = csv.DictReader(StringIO(csv_content))
    
    rows_inserted = 0
    rows_updated = 0
    rows_failed = 0
    
    for row in csv_reader:
        try:
            # Normalize column names and prepare data
            data = {normalize_column_name(k): v for k, v in row.items()}
            
            # Skip rows without profile URL
            if not data.get('profile_url'):
                rows_failed += 1
                continue
            
            # Upsert query
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
            print(f"Error processing row: {e}")
            rows_failed += 1
            continue
    
    # Record upload history
    cursor.execute("""
        INSERT INTO upload_history (filename, rows_inserted, rows_updated, rows_failed, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (filename, rows_inserted, rows_updated, rows_failed, 'success'))
    
    conn.commit()
    cursor.close()
    
    return rows_inserted, rows_updated, rows_failed


def main():
    parser = argparse.ArgumentParser(description='Upload LinkedIn leads CSV to database')
    parser.add_argument('--file-id', help='Specific Google Drive file ID to upload')
    parser.add_argument('--list', action='store_true', help='List available CSV files')
    parser.add_argument('--password', help='Database password', required=False)
    args = parser.parse_args()
    
    if args.password:
        DB_CONFIG['password'] = args.password
    
    # List files if requested
    if args.list:
        print("Available CSV files in Google Drive:")
        print("=" * 80)
        files = list_csv_files()
        for i, file in enumerate(files, 1):
            size_mb = int(file.get('size', 0)) / 1024 / 1024
            print(f"{i}. {file['name']}")
            print(f"   ID: {file['id']}")
            print(f"   Modified: {file['modifiedTime']}")
            print(f"   Size: {size_mb:.2f} MB")
            print()
        return
    
    # Connect to database
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ Connected to database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        sys.exit(1)
    
    # Upload specific file or latest
    if args.file_id:
        file_id = args.file_id
        filename = f"file_{file_id}"
    else:
        files = list_csv_files()
        if not files:
            print("No CSV files found in Google Drive folder")
            sys.exit(1)
        file = files[0]
        file_id = file['id']
        filename = file['name']
    
    print(f"Uploading: {filename}")
    print("=" * 80)
    
    # Download and upload
    csv_content = download_csv(file_id)
    rows_inserted, rows_updated, rows_failed = upload_csv_to_db(csv_content, filename, conn)
    
    print(f"\n✅ Upload complete!")
    print(f"   Inserted: {rows_inserted}")
    print(f"   Updated: {rows_updated}")
    print(f"   Failed: {rows_failed}")
    
    conn.close()


if __name__ == "__main__":
    main()

