#!/usr/bin/env python3
"""Verify data in the database."""

import sys
import psycopg2

DB_CONFIG = {
    'host': '35.193.184.122',
    'database': 'linkedin_leads_data',
    'user': 'postgres',
    'password': sys.argv[1] if len(sys.argv) > 1 else '',
}

conn = psycopg2.connect(**DB_CONFIG)
cursor = conn.cursor()

# Count total leads
cursor.execute("SELECT COUNT(*) FROM leads")
total = cursor.fetchone()[0]
print(f"Total leads in database: {total}")

# Show sample leads
print("\nSample leads:")
print("=" * 100)
cursor.execute("""
    SELECT first_name, last_name, current_company, current_title, active_project
    FROM leads
    LIMIT 5
""")

for row in cursor.fetchall():
    print(f"- {row[0]} {row[1]} | {row[2]} | {row[3][:50]}... | {row[4]}")

# Show upload history
print("\n" + "=" * 100)
print("Upload History:")
cursor.execute("SELECT * FROM upload_history ORDER BY upload_date DESC")
for row in cursor.fetchall():
    print(f"- {row[1]}: {row[2]} inserted, {row[3]} updated, {row[4]} failed ({row[6]})")

cursor.close()
conn.close()

