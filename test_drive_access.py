#!/usr/bin/env python3
"""Test Google Drive access with service accounts."""

import os
import sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Folder ID from the URL
FOLDER_ID = "1wdE3pA0JzTi831Yn3QeDwHDmbo5eNFc3"

# Service account key files to test
SERVICE_ACCOUNT_KEYS = [
    "~/Downloads/jobs-data-linkedin-04c6e4060679.json",  # algolia
    "~/Downloads/jobs-data-linkedin-2efe0d724ac1.json",  # gmail-processor
    "~/Downloads/jobs-data-linkedin-52d03efe8395.json",  # dataengineer-dev
]

SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


def test_service_account(key_path):
    """Test if a service account can access the Drive folder."""
    expanded_path = os.path.expanduser(key_path)
    
    if not os.path.exists(expanded_path):
        print(f"❌ Key file not found: {key_path}")
        return False
    
    try:
        # Load credentials
        credentials = service_account.Credentials.from_service_account_file(
            expanded_path, scopes=SCOPES
        )
        
        # Build Drive service
        service = build('drive', 'v3', credentials=credentials)
        
        # Get service account email
        with open(expanded_path, 'r') as f:
            import json
            key_data = json.load(f)
            email = key_data.get('client_email', 'unknown')
        
        print(f"\n🔍 Testing: {email}")
        
        # Try to get folder metadata
        folder = service.files().get(
            fileId=FOLDER_ID,
            fields='id, name, mimeType, owners, permissions'
        ).execute()
        
        print(f"✅ SUCCESS! Can access folder: {folder.get('name')}")
        
        # List files in the folder
        results = service.files().list(
            q=f"'{FOLDER_ID}' in parents",
            pageSize=10,
            fields="files(id, name, mimeType, modifiedTime)"
        ).execute()
        
        files = results.get('files', [])
        print(f"   Found {len(files)} files/folders:")
        for file in files[:5]:  # Show first 5
            print(f"   - {file['name']} ({file['mimeType']})")
        
        return True
        
    except Exception as e:
        print(f"❌ FAILED: {str(e)}")
        return False


def main():
    """Test all service accounts."""
    print("=" * 60)
    print("Testing Google Drive Access")
    print(f"Folder ID: {FOLDER_ID}")
    print("=" * 60)
    
    successful = []
    
    for key_path in SERVICE_ACCOUNT_KEYS:
        if test_service_account(key_path):
            successful.append(key_path)
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"✅ {len(successful)} service account(s) have access")
    print(f"❌ {len(SERVICE_ACCOUNT_KEYS) - len(successful)} service account(s) do NOT have access")
    print("=" * 60)
    
    if successful:
        print("\n✅ Service accounts with access:")
        for key in successful:
            print(f"   - {key}")
    else:
        print("\n⚠️  None of the tested service accounts have access to this folder.")
        print("   You may need to:")
        print("   1. Share the folder with one of these service accounts")
        print("   2. Use a different service account")
        print("   3. Use OAuth2 user credentials instead")


if __name__ == "__main__":
    main()

