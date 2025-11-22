#!/usr/bin/env python3
"""Run deduplication on the leads database."""

import sys
import psycopg2

DB_CONFIG = {
    'host': '35.193.184.122',
    'database': 'linkedin_leads_data',
    'user': 'postgres',
    'password': sys.argv[1] if len(sys.argv) > 1 else '',
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 run_dedupe.py <password>")
        sys.exit(1)
    
    print("Connecting to database...")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Count before dedupe
    cursor.execute("SELECT COUNT(*) FROM leads")
    before_count = cursor.fetchone()[0]
    print(f"Total leads before dedupe: {before_count}")
    
    # Check for duplicates
    cursor.execute("""
        SELECT profile_url, COUNT(*) as count
        FROM leads
        WHERE profile_url IS NOT NULL AND profile_url != ''
        GROUP BY profile_url
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        LIMIT 10
    """)
    
    duplicates = cursor.fetchall()
    if duplicates:
        print(f"\nFound {len(duplicates)} profile URLs with duplicates:")
        for url, count in duplicates[:5]:
            print(f"  - {url[:60]}... ({count} copies)")
    else:
        print("\n✅ No duplicates found!")
        cursor.close()
        conn.close()
        return
    
    # Load dedupe function
    print("\nLoading deduplication function...")
    with open('dedupe.sql', 'r') as f:
        dedupe_sql = f.read()
    
    cursor.execute(dedupe_sql)
    conn.commit()
    print("✅ Dedupe function loaded")
    
    # Run dedupe
    print("\nRunning deduplication...")
    cursor.execute("SELECT * FROM dedupe_leads()")
    result = cursor.fetchone()
    conn.commit()
    
    duplicates_found = result[0]
    duplicates_removed = result[1]
    
    # Count after dedupe
    cursor.execute("SELECT COUNT(*) FROM leads")
    after_count = cursor.fetchone()[0]
    
    print("\n" + "=" * 80)
    print("📊 Deduplication Results:")
    print(f"  Before: {before_count} leads")
    print(f"  After: {after_count} leads")
    print(f"  Duplicates found: {duplicates_found}")
    print(f"  Records removed: {duplicates_removed}")
    print("=" * 80)
    
    cursor.close()
    conn.close()
    
    print("\n✅ Deduplication complete!")


if __name__ == "__main__":
    main()

