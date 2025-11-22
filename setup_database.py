#!/usr/bin/env python3
"""Initialize the database schema."""

import os
import sys
import psycopg2

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '35.193.184.122'),
    'database': os.getenv('DB_NAME', 'linkedin_leads_data'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 setup_database.py <password>")
        sys.exit(1)
    
    DB_CONFIG['password'] = sys.argv[1]
    
    print("Connecting to database...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print("✅ Connected successfully")
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        sys.exit(1)
    
    cursor = conn.cursor()
    
    # Read and execute schema
    print("\nExecuting schema.sql...")
    with open('schema.sql', 'r') as f:
        schema_sql = f.read()
    
    try:
        cursor.execute(schema_sql)
        conn.commit()
        print("✅ Schema created successfully")
    except Exception as e:
        print(f"❌ Failed to create schema: {e}")
        conn.rollback()
        sys.exit(1)
    
    # Verify tables
    print("\nVerifying tables...")
    cursor.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    
    tables = cursor.fetchall()
    print("Tables created:")
    for table in tables:
        print(f"  - {table[0]}")
    
    cursor.close()
    conn.close()
    
    print("\n✅ Database setup complete!")


if __name__ == "__main__":
    main()

