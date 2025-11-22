#!/usr/bin/env python3
"""
LinkedIn Leads Admin Panel
Flask web application for managing LinkedIn leads database
"""

import os
import csv
from io import StringIO, BytesIO
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '35.193.184.122'),
    'database': os.getenv('DB_NAME', 'linkedin_leads_data'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
}

ALLOWED_EXTENSIONS = {'csv'}


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(**DB_CONFIG)


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


def process_csv(csv_content, filename):
    """Process CSV and upload to database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    csv_reader = csv.DictReader(StringIO(csv_content))
    
    rows_inserted = 0
    rows_updated = 0
    rows_failed = 0
    errors = []
    
    for row_num, row in enumerate(csv_reader, start=2):
        try:
            data = {normalize_column_name(k): v for k, v in row.items()}
            
            if not data.get('profile_url'):
                rows_failed += 1
                errors.append(f"Row {row_num}: Missing profile URL")
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
            rows_failed += 1
            errors.append(f"Row {row_num}: {str(e)}")
            continue
    
    # Record upload history
    cursor.execute("""
        INSERT INTO upload_history (filename, rows_inserted, rows_updated, rows_failed, status, error_message)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (filename, rows_inserted, rows_updated, rows_failed, 
          'success' if rows_failed == 0 else 'partial', 
          '\n'.join(errors[:10]) if errors else None))
    
    # Run deduplication
    cursor.execute("SELECT run_dedupe()")
    dedupe_result = cursor.fetchone()[0]
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return {
        'inserted': rows_inserted,
        'updated': rows_updated,
        'failed': rows_failed,
        'errors': errors[:10],
        'dedupe': dedupe_result
    }


@app.route('/')
def index():
    """Home page with dashboard."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get statistics
    cursor.execute("SELECT COUNT(*) as total FROM leads")
    total_leads = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM upload_history")
    total_uploads = cursor.fetchone()['total']
    
    cursor.execute("""
        SELECT COUNT(DISTINCT current_company) as total 
        FROM leads 
        WHERE current_company IS NOT NULL AND current_company != ''
    """)
    total_companies = cursor.fetchone()['total']
    
    # Get recent uploads
    cursor.execute("""
        SELECT * FROM upload_history 
        ORDER BY upload_date DESC 
        LIMIT 10
    """)
    recent_uploads = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('index.html', 
                         total_leads=total_leads,
                         total_uploads=total_uploads,
                         total_companies=total_companies,
                         recent_uploads=recent_uploads)


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    """CSV upload page."""
    if request.method == 'POST':
        # Check if files were uploaded
        if 'files[]' not in request.files:
            flash('No files selected', 'error')
            return redirect(request.url)
        
        files = request.files.getlist('files[]')
        results = []
        
        for file in files:
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                csv_content = file.read().decode('utf-8')
                
                try:
                    result = process_csv(csv_content, filename)
                    results.append({
                        'filename': filename,
                        'success': True,
                        **result
                    })
                except Exception as e:
                    results.append({
                        'filename': filename,
                        'success': False,
                        'error': str(e)
                    })
        
        return render_template('upload_results.html', results=results)
    
    return render_template('upload.html')


@app.route('/leads')
def leads():
    """View all leads."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page
    
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT COUNT(*) as total FROM leads")
    total = cursor.fetchone()['total']
    
    cursor.execute("""
        SELECT * FROM leads 
        ORDER BY created_at DESC 
        LIMIT %s OFFSET %s
    """, (per_page, offset))
    
    leads_list = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('leads.html', 
                         leads=leads_list, 
                         page=page, 
                         total_pages=total_pages,
                         total=total)


@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    cursor.execute("SELECT COUNT(*) as total FROM leads")
    stats = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return jsonify(stats)


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)

