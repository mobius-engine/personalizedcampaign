#!/usr/bin/env python3
"""
Kill idle database connections to free up connection slots.
"""

import os
import psycopg2

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '35.193.184.122'),
    'database': os.getenv('DB_NAME', 'linkedin_leads_data'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'TempPassword123!'),
}

def kill_idle_connections():
    """Kill idle database connections."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Get count of connections
        cursor.execute("""
            SELECT count(*) 
            FROM pg_stat_activity 
            WHERE datname = 'linkedin_leads_data'
        """)
        total_connections = cursor.fetchone()[0]
        print(f"📊 Total connections to database: {total_connections}")
        
        # Kill idle connections (except our own)
        cursor.execute("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = 'linkedin_leads_data'
              AND pid <> pg_backend_pid()
              AND state = 'idle'
              AND state_change < current_timestamp - INTERVAL '5 minutes'
        """)
        
        killed = cursor.rowcount
        conn.commit()
        
        print(f"✅ Killed {killed} idle connections")
        
        # Get new count
        cursor.execute("""
            SELECT count(*) 
            FROM pg_stat_activity 
            WHERE datname = 'linkedin_leads_data'
        """)
        remaining_connections = cursor.fetchone()[0]
        print(f"📊 Remaining connections: {remaining_connections}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    kill_idle_connections()

