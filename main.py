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
from google.cloud import secretmanager
from openai import OpenAI
import threading

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
GCP_PROJECT_ID = "jobs-data-linkedin"
SECRET_NAME = "openai-api-key"


def get_openai_api_key():
    """Retrieve OpenAI API key from GCP Secret Manager."""
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{GCP_PROJECT_ID}/secrets/{SECRET_NAME}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8").strip()
    except Exception as e:
        print(f"Error retrieving API key: {e}")
        return None


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

    cursor.execute("""
        SELECT COUNT(*) as total
        FROM leads
        WHERE hook IS NOT NULL AND hook != ''
    """)
    total_hooks = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COUNT(*) as total
        FROM leads
        WHERE viewed = TRUE
    """)
    total_viewed = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COUNT(*) as total
        FROM leads
        WHERE viewed = FALSE OR viewed IS NULL
    """)
    total_unviewed = cursor.fetchone()['total']

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
                         total_hooks=total_hooks,
                         total_viewed=total_viewed,
                         total_unviewed=total_unviewed,
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
        total_new_leads = 0

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
                    total_new_leads += result.get('inserted', 0)
                except Exception as e:
                    results.append({
                        'filename': filename,
                        'success': False,
                        'error': str(e)
                    })

        # Auto-generate hooks for new leads in background
        if total_new_leads > 0:
            try:
                # Start background thread to generate hooks
                thread = threading.Thread(target=generate_hooks_background, daemon=True)
                thread.start()
                flash(f'CSV upload complete! Generating AI hooks for {total_new_leads} new leads in the background...', 'success')
            except Exception as e:
                print(f"Error starting background hook generation: {e}")
                flash(f'Warning: Could not start background hook generation. Error: {str(e)}', 'warning')

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


def generate_hook_for_lead(lead):
    """Generate a personalized hook for a lead using GPT-4o."""
    name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
    credentials = lead.get('headline', '') or ''
    title_keywords = lead.get('current_title', '') or ''
    location = lead.get('location', '') or ''
    current_role = lead.get('current_title', '') or ''
    company = lead.get('current_company', '') or ''

    prompt = f"""Parse this information about a professional:

Name: {name}
Credentials: {credentials}
Title keywords: {title_keywords}
Location: {location}
Current role: {current_role}
Company: {company}

Use the Name, Credentials, Title keywords, Current role, and Company fields to craft a 1-paragraph "hook". The hook is to establish my credibility as someone who can help secure them a job in this tough market impacted by AI. The language needs to be very simple. The last sentence should be something like - Mobiusengine.ai can help you land your next role... something like that.

The "hook" should:
- Challenge the reader's current positioning (e.g., "many firms still treat this as…")
- Point to the elevated value they bring (based on credentials/title keywords)
- Be concise and impactful
- Be super pithy, plain, direct and succinct. No more than 3 short sentences
- Create need by citing how recruiting for roles like theirs are changing due to AI
- Do not include step-by-step service description or promotion—just the paragraph
- Write in second person ("you") and reference the credentials and experience from the input
- Maintain a professional tone suited for a senior-level audience

Generate only the hook paragraph, nothing else."""

    try:
        api_key = get_openai_api_key()
        if not api_key:
            return None

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at crafting compelling, concise professional outreach messages."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )

        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating hook: {e}")
        return None


def generate_hooks_background():
    """Background task to generate hooks for leads without hooks."""
    try:
        print("🚀 Starting background hook generation...")
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get leads without hooks
        cursor.execute("SELECT * FROM leads WHERE hook IS NULL OR hook = '' ORDER BY id")
        leads_without_hooks = cursor.fetchall()

        total_leads = len(leads_without_hooks)
        print(f"📊 Found {total_leads} leads without hooks")

        hooks_generated = 0
        for idx, lead in enumerate(leads_without_hooks, 1):
            print(f"⏳ Generating hook {idx}/{total_leads} for lead ID {lead['id']}...")
            hook = generate_hook_for_lead(lead)
            if hook:
                cursor.execute("""
                    UPDATE leads
                    SET hook = %s, hook_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (hook, lead['id']))
                conn.commit()
                hooks_generated += 1
                print(f"✅ Generated hook {hooks_generated}/{total_leads}")

        cursor.close()
        conn.close()

        print(f"🎉 Background hook generation complete! Generated {hooks_generated} hooks.")
    except Exception as e:
        print(f"❌ Error in background hook generation: {e}")


@app.route('/api/generate-hook/<int:lead_id>', methods=['POST'])
def api_generate_hook(lead_id):
    """API endpoint to generate hook for a specific lead."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get lead
    cursor.execute("SELECT * FROM leads WHERE id = %s", (lead_id,))
    lead = cursor.fetchone()

    if not lead:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Lead not found'}), 404

    # Generate hook
    hook = generate_hook_for_lead(lead)

    if hook:
        # Update database
        cursor.execute("""
            UPDATE leads
            SET hook = %s, hook_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (hook, lead_id))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({'success': True, 'hook': hook})
    else:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Failed to generate hook'}), 500


@app.route('/api/generate-all-hooks', methods=['POST'])
def api_generate_all_hooks():
    """API endpoint to generate hooks for all leads without hooks."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get leads without hooks
    cursor.execute("SELECT * FROM leads WHERE hook IS NULL OR hook = '' ORDER BY id")
    leads = cursor.fetchall()

    total = len(leads)
    success = 0
    failed = 0

    for lead in leads:
        hook = generate_hook_for_lead(lead)
        if hook:
            cursor.execute("""
                UPDATE leads
                SET hook = %s, hook_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (hook, lead['id']))
            conn.commit()
            success += 1
        else:
            failed += 1

    cursor.close()
    conn.close()

    return jsonify({
        'success': True,
        'total': total,
        'generated': success,
        'failed': failed
    })


@app.route('/api/mark-viewed/<int:lead_id>', methods=['POST'])
def api_mark_viewed(lead_id):
    """API endpoint to mark a lead as viewed."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get user info from request (you can enhance this with actual user authentication)
    user = request.json.get('user', 'admin') if request.json else 'admin'

    # Update lead as viewed
    cursor.execute("""
        UPDATE leads
        SET viewed = TRUE,
            viewed_at = CURRENT_TIMESTAMP,
            viewed_by = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        RETURNING viewed, viewed_at, viewed_by
    """, (user, lead_id))

    result = cursor.fetchone()
    conn.commit()

    cursor.close()
    conn.close()

    if result:
        return jsonify({
            'success': True,
            'viewed': result['viewed'],
            'viewed_at': result['viewed_at'].isoformat() if result['viewed_at'] else None,
            'viewed_by': result['viewed_by']
        })
    else:
        return jsonify({'error': 'Lead not found'}), 404


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)

