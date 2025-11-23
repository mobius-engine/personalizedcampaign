#!/usr/bin/env python3
"""Extract 10 sample leads from database."""

import psycopg2
from psycopg2.extras import RealDictCursor
import json

# Database connection
conn = psycopg2.connect(
    host="/cloudsql/jobs-data-linkedin:us-central1:linkedin-leads-db/.s.PGSQL.5432",
    database="linkedin_leads_data",
    user="postgres",
    password=""
)

cursor = conn.cursor(cursor_factory=RealDictCursor)

# Get 10 diverse leads
cursor.execute("""
    SELECT id, name, title, company, location, about, linkedin_url
    FROM leads
    WHERE title IS NOT NULL AND company IS NOT NULL
    ORDER BY RANDOM()
    LIMIT 10
""")

leads = cursor.fetchall()

for i, lead in enumerate(leads, 1):
    print(f"\n{'='*80}")
    print(f"LEAD {i}")
    print(f"{'='*80}")
    print(f"ID: {lead['id']}")
    print(f"Name: {lead['name']}")
    print(f"Title: {lead['title']}")
    print(f"Company: {lead['company']}")
    print(f"Location: {lead['location']}")
    print(f"About: {lead['about'][:300] if lead['about'] else 'N/A'}...")
    print(f"LinkedIn: {lead['linkedin_url']}")

cursor.close()
conn.close()
