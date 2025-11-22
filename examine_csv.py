#!/usr/bin/env python3
"""Download and examine CSV structure from Google Drive."""

import os
import csv
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from io import StringIO

FOLDER_ID = "1wdE3pA0JzTi831Yn3QeDwHDmbo5eNFc3"
SERVICE_ACCOUNT_KEY = os.path.expanduser("~/Downloads/jobs-data-linkedin-52d03efe8395.json")
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


def main():
    """Download and analyze the first CSV file."""
    # Load credentials
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_KEY, scopes=SCOPES
    )
    
    # Build Drive service
    service = build('drive', 'v3', credentials=credentials)
    
    # List CSV files in the folder
    results = service.files().list(
        q=f"'{FOLDER_ID}' in parents and mimeType='text/csv'",
        pageSize=1,
        orderBy='modifiedTime desc',
        fields="files(id, name, mimeType, modifiedTime)"
    ).execute()
    
    files = results.get('files', [])
    
    if not files:
        print("No CSV files found!")
        return
    
    # Get the most recent CSV
    file = files[0]
    print(f"Examining: {file['name']}")
    print(f"Modified: {file['modifiedTime']}")
    print("=" * 80)
    
    # Download the file
    request = service.files().get_media(fileId=file['id'])
    content = request.execute().decode('utf-8')
    
    # Parse CSV
    csv_reader = csv.DictReader(StringIO(content))
    
    # Get headers
    headers = csv_reader.fieldnames
    print(f"\nFound {len(headers)} columns:")
    print("-" * 80)
    for i, header in enumerate(headers, 1):
        print(f"{i:2d}. {header}")
    
    # Examine first few rows
    print("\n" + "=" * 80)
    print("Sample Data (first 3 rows):")
    print("=" * 80)
    
    rows = []
    for i, row in enumerate(csv_reader):
        if i >= 3:
            break
        rows.append(row)
    
    # Analyze data types
    print("\nColumn Analysis:")
    print("-" * 80)
    
    for header in headers:
        sample_values = [row.get(header, '') for row in rows if row.get(header)]
        if sample_values:
            sample = sample_values[0]
            print(f"\n{header}:")
            print(f"  Sample: {sample[:100] if sample else '(empty)'}")
            print(f"  Length: {len(sample) if sample else 0}")
    
    # Save sample to file
    with open('sample_csv_data.json', 'w') as f:
        json.dump({
            'filename': file['name'],
            'headers': headers,
            'sample_rows': rows
        }, f, indent=2)
    
    print("\n" + "=" * 80)
    print("✅ Sample data saved to: sample_csv_data.json")


if __name__ == "__main__":
    main()

