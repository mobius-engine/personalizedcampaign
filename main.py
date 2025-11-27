#!/usr/bin/env python3
"""
LinkedIn Leads Admin Panel
Flask web application for managing LinkedIn leads database
"""

import os
import csv
from io import StringIO, BytesIO
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, make_response
import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.utils import secure_filename
from google.cloud import secretmanager
from openai import OpenAI
import threading
import time

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

# Database configuration
# Check if running on Cloud Run (use Unix socket) or locally (use TCP)
if os.getenv('K_SERVICE'):
    # Running on Cloud Run - use Unix socket
    DB_CONFIG = {
        'host': '/cloudsql/jobs-data-linkedin:us-central1:linkedin-leads-db',
        'database': os.getenv('DB_NAME', 'linkedin_leads_data'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', ''),
    }
else:
    # Running locally - use TCP connection
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', '35.193.184.122'),
        'database': os.getenv('DB_NAME', 'linkedin_leads_data'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', ''),
    }

# Scheduler database configuration (via Cloud SQL Proxy)
# This database contains prospects, bookings, availability_rules, settings, and blocked_dates
SCHEDULER_DB_HOST = os.getenv('SCHEDULER_DB_HOST', 'localhost')

# Check if we're using Unix socket (Cloud Run) or TCP (local)
if SCHEDULER_DB_HOST.startswith('/cloudsql/'):
    # Cloud Run - use Unix socket
    SCHEDULER_DB_CONFIG = {
        'host': SCHEDULER_DB_HOST,
        'database': os.getenv('SCHEDULER_DB_NAME', 'scheduler'),
        'user': os.getenv('SCHEDULER_DB_USER', 'scheduler-user'),
        'password': os.getenv('SCHEDULER_DB_PASSWORD', 'scheduler-password-123'),
    }
else:
    # Local - use TCP connection
    SCHEDULER_DB_CONFIG = {
        'host': SCHEDULER_DB_HOST,
        'port': os.getenv('SCHEDULER_DB_PORT', '5432'),
        'database': os.getenv('SCHEDULER_DB_NAME', 'scheduler'),
        'user': os.getenv('SCHEDULER_DB_USER', 'scheduler-user'),
        'password': os.getenv('SCHEDULER_DB_PASSWORD', 'scheduler-password-123'),
    }

ALLOWED_EXTENSIONS = {'csv'}
GCP_PROJECT_ID = "jobs-data-linkedin"
SECRET_NAME = "openai-api-key"

# Global list to store recent hook generation logs
hook_generation_logs = []
MAX_LOGS = 500


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


def get_scheduler_db_connection():
    """Create scheduler database connection (via Cloud SQL Proxy)."""
    return psycopg2.connect(**SCHEDULER_DB_CONFIG)


def init_task_status_table():
    """Create task_status table if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_status (
                task_name VARCHAR(50) PRIMARY KEY,
                running BOOLEAN DEFAULT FALSE,
                progress INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                current INTEGER DEFAULT 0,
                stat_value INTEGER DEFAULT 0,
                message TEXT DEFAULT 'Not started',
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Initialize default tasks
        cursor.execute("""
            INSERT INTO task_status (task_name) VALUES ('filtering'), ('hook_generation'), ('deduplication')
            ON CONFLICT (task_name) DO NOTHING
        """)

        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error initializing task_status table: {e}")


def get_task_status(task_name):
    """Get status of a specific task from database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM task_status WHERE task_name = %s", (task_name,))
        status = cursor.fetchone()
        cursor.close()
        conn.close()

        if status:
            return {
                'running': status['running'],
                'progress': status['progress'],
                'total': status['total'],
                'current': status['current'],
                'stat_value': status['stat_value'],
                'message': status['message'],
                'started_at': status['started_at'].isoformat() if status['started_at'] else None,
                'completed_at': status['completed_at'].isoformat() if status['completed_at'] else None
            }
        return None
    except Exception as e:
        print(f"Error getting task status: {e}")
        return None


def update_task_status(task_name, **kwargs):
    """Update task status in database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build update query dynamically
        updates = []
        values = []
        for key, value in kwargs.items():
            updates.append(f"{key} = %s")
            values.append(value)

        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(task_name)

        query = f"UPDATE task_status SET {', '.join(updates)} WHERE task_name = %s"
        cursor.execute(query, values)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error updating task status: {e}")


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
    """View all leads with filtering and sorting."""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    # Get filter parameters
    hook_filter = request.args.get('hook_filter', 'all')  # all, has_hook, no_hook
    contacted_filter = request.args.get('contacted_filter', 'all')  # all, contacted, not_contacted
    location_filter = request.args.get('location', '')
    title_filter = request.args.get('title', '')
    company_filter = request.args.get('company', '')
    search_query = request.args.get('search', '')

    # Get sort parameters
    sort_by = request.args.get('sort_by', 'created_at')  # created_at, first_name, current_title, current_company, location
    sort_order = request.args.get('sort_order', 'desc')  # asc, desc

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Build WHERE clause
    where_clauses = []
    params = []

    # Hook filter
    if hook_filter == 'has_hook':
        where_clauses.append("hook IS NOT NULL AND hook != ''")
    elif hook_filter == 'no_hook':
        where_clauses.append("(hook IS NULL OR hook = '')")

    # Contacted filter (viewed = contacted)
    if contacted_filter == 'contacted':
        where_clauses.append("viewed = TRUE")
    elif contacted_filter == 'not_contacted':
        where_clauses.append("(viewed = FALSE OR viewed IS NULL)")

    # Location filter
    if location_filter:
        where_clauses.append("location ILIKE %s")
        params.append(f"%{location_filter}%")

    # Title filter
    if title_filter:
        where_clauses.append("current_title ILIKE %s")
        params.append(f"%{title_filter}%")

    # Company filter
    if company_filter:
        where_clauses.append("current_company ILIKE %s")
        params.append(f"%{company_filter}%")

    # Search query (searches across name, title, company, location)
    if search_query:
        where_clauses.append("""
            (first_name ILIKE %s OR last_name ILIKE %s OR
             current_title ILIKE %s OR current_company ILIKE %s OR
             location ILIKE %s OR headline ILIKE %s)
        """)
        search_param = f"%{search_query}%"
        params.extend([search_param] * 6)

    # Build WHERE clause string
    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Validate sort_by to prevent SQL injection
    valid_sort_columns = ['created_at', 'first_name', 'last_name', 'current_title', 'current_company', 'location', 'viewed']
    if sort_by not in valid_sort_columns:
        sort_by = 'created_at'

    # Validate sort_order
    if sort_order not in ['asc', 'desc']:
        sort_order = 'desc'

    # Get total count with filters
    cursor.execute(f"SELECT COUNT(*) as total FROM leads {where_sql}", params)
    total = cursor.fetchone()['total']

    # Get filtered and sorted leads
    cursor.execute(f"""
        SELECT * FROM leads
        {where_sql}
        ORDER BY {sort_by} {sort_order.upper()}, id DESC
        LIMIT %s OFFSET %s
    """, params + [per_page, offset])

    leads_list = cursor.fetchall()

    # Get unique locations, titles, and companies for filter dropdowns (limit to top 50 for performance)
    cursor.execute("""
        SELECT DISTINCT location
        FROM leads
        WHERE location IS NOT NULL AND location != ''
        ORDER BY location
        LIMIT 50
    """)
    locations = [row['location'] for row in cursor.fetchall()]

    cursor.execute("""
        SELECT DISTINCT current_title
        FROM leads
        WHERE current_title IS NOT NULL AND current_title != ''
        ORDER BY current_title
        LIMIT 50
    """)
    titles = [row['current_title'] for row in cursor.fetchall()]

    cursor.execute("""
        SELECT DISTINCT current_company
        FROM leads
        WHERE current_company IS NOT NULL AND current_company != ''
        ORDER BY current_company
        LIMIT 50
    """)
    companies = [row['current_company'] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    total_pages = (total + per_page - 1) // per_page

    return render_template('leads.html',
                         leads=leads_list,
                         page=page,
                         total_pages=total_pages,
                         total=total,
                         hook_filter=hook_filter,
                         contacted_filter=contacted_filter,
                         location_filter=location_filter,
                         title_filter=title_filter,
                         company_filter=company_filter,
                         search_query=search_query,
                         sort_by=sort_by,
                         sort_order=sort_order,
                         locations=locations,
                         titles=titles,
                         companies=companies)


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
            model="gpt-4.1-mini",
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


def generate_hook_worker(lead, api_key):
    """Worker function to generate AI-focused hook for a single lead."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    try:
        # Extract lead data
        name = lead.get('name', 'this person')
        title = lead.get('title', 'professional')
        company = lead.get('company', 'their company')
        location = lead.get('location', '')
        about = lead.get('about', '')[:500] if lead.get('about') else ''

        # Build concise profile summary
        profile_summary = f"{name} is a {title}"
        if company:
            profile_summary += f" at {company}"
        if location:
            profile_summary += f" in {location}"
        if about:
            profile_summary += f". Background: {about}"

        # Build prompt based on available data
        if about:
            # Rich profile with background - hyperpersonalized
            prompt = f"""Write a direct, simple hook (3-4 sentences) for this person. Use simple words.

Profile: {profile_summary}

Structure:
1. HYPERPERSONALIZED PROBLEM STATEMENT: Use their ACTUAL experience/background from the profile to make this laser-focused.
   - Reference specific domain knowledge, tools, or expertise from their background
   - Then show how AI is automating those specific tasks
   - End with: "which is changing what [hiring managers/companies] are looking for in [their role]"
2. ACKNOWLEDGE: "You have experience in [specific thing from their background]"
3. QUESTION: "Have you thought about repositioning to [specific new role/focus]?"
   - BE SUBTLE - don't always say "AI-driven" or "AI-focused"
   - Suggest natural evolution (strategy, leadership, advisory, architecture, etc.)
4. CLOSE: "mobiusengine.ai has worked with many [their role] in the past 3 years to help them land their next role."

Example: "AI is now automating data visualization and BI reporting tasks, which is changing what companies want from data analysts. You have strong experience in business intelligence at Microsoft. Have you thought about repositioning to data strategy or analytics leadership roles? mobiusengine.ai has worked with many data analysts in the past 3 years to help them land their next role."

Write the hook (under 60 words, use simple language, be HYPERPERSONALIZED to their actual background):"""
        else:
            # Minimal profile - use title/company only
            prompt = f"""Write a direct, simple hook (3-4 sentences) for this person. Use simple words.

Profile: {profile_summary}

Structure:
1. PROBLEM STATEMENT: "AI is now automating [common tasks for their role], which is changing what companies want from [their role]."
2. ACKNOWLEDGE: "You have experience as a {title} at {company}."
3. QUESTION: "Have you thought about repositioning to [natural evolution like strategy, leadership, architecture]?"
4. CLOSE: "mobiusengine.ai has worked with many [their role] in the past 3 years to help them land their next role."

Example for Mechanical Engineer: "AI is now automating CAD design and simulation tasks, which is changing what companies want from mechanical engineers. You have experience as a Mechanical Engineer at Amentum. Have you thought about repositioning to engineering leadership or systems architecture roles? mobiusengine.ai has worked with many mechanical engineers in the past 3 years to help them land their next role."

Write the hook (under 60 words, use simple language):"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a strategic career advisor focused on AI's impact on professional roles. Be direct and insightful."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=150
        )

        hook = response.choices[0].message.content.strip()
        # Remove quotes if AI wrapped the response
        hook = hook.strip('"').strip("'")

        return {
            'id': lead['id'],
            'name': name,
            'title': title,
            'company': company,
            'linkedin_url': lead.get('linkedin_url', ''),
            'hook': hook,
            'success': True
        }
    except Exception as e:
        lead_id = lead.get('id', 'unknown')
        print(f"❌ Error generating hook for lead {lead_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            'id': lead.get('id'),
            'name': lead.get('name', ''),
            'title': lead.get('title', ''),
            'company': lead.get('company', ''),
            'linkedin_url': lead.get('linkedin_url', ''),
            'hook': None,
            'success': False
        }


def generate_hooks_background():
    """Background task to generate hooks and save to CSV file."""
    import csv
    from datetime import datetime

    # Log that function was called
    init_msg = "🔵 generate_hooks_background() function called"
    print(init_msg)
    hook_generation_logs.append({
        'timestamp': datetime.now().isoformat(),
        'message': init_msg
    })

    try:
        # Initialize status in database
        update_task_status('hook_generation',
            running=True,
            started_at=datetime.now(),
            message='Starting hook generation...',
            progress=0,
            current=0,
            stat_value=0
        )

        startup_msg = "🚀 Starting background hook generation with 30 parallel workers..."
        print(startup_msg)
        hook_generation_logs.append({
            'timestamp': datetime.now().isoformat(),
            'message': startup_msg
        })

        # Get OpenAI API key
        api_key = get_openai_api_key()
        if not api_key:
            error_msg = "❌ No OpenAI API key available"
            print(error_msg)
            hook_generation_logs.append({
                'timestamp': datetime.now().isoformat(),
                'message': error_msg
            })
            update_task_status('hook_generation', running=False, message='Error: No API key')
            return

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get ALL leads (not just those without hooks - regenerate all)
        cursor.execute("SELECT * FROM leads ORDER BY id")
        all_leads = cursor.fetchall()
        cursor.close()
        conn.close()

        total_leads = len(all_leads)
        update_task_status('hook_generation',
            total=total_leads,
            message=f'Found {total_leads} leads - generating AI-focused hooks with 30 parallel workers...'
        )

        print(f"📊 Generating AI-focused hooks for {total_leads} leads")

        # Create CSV file with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_filename = f'generated_hooks_{timestamp}.csv'
        csv_path = os.path.join('/tmp', csv_filename)

        print(f"📝 Saving hooks to {csv_path}")

        # Use ThreadPoolExecutor for parallel processing
        from concurrent.futures import ThreadPoolExecutor, as_completed
        hooks_generated = 0
        all_results = []
        batch_buffer = []  # Buffer for batching DB writes
        BATCH_SIZE = 50  # Write to DB every 50 hooks

        # Open persistent DB connection for batching
        db_conn = get_db_connection()
        db_cursor = db_conn.cursor()

        with ThreadPoolExecutor(max_workers=30) as executor:
            # Submit all tasks
            future_to_lead = {executor.submit(generate_hook_worker, lead, api_key): lead for lead in all_leads}

            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_lead):
                completed += 1
                result = future.result()

                if result['success'] and result['hook']:
                    all_results.append(result)
                    hooks_generated += 1
                    batch_buffer.append(result)

                    log_msg = f"✅ [{completed}/{total_leads}] {result['name']}: {result['hook'][:100]}..."
                    print(log_msg)
                    hook_generation_logs.append({
                        'timestamp': datetime.now().isoformat(),
                        'message': log_msg,
                        'hook': result['hook'],
                        'name': result['name']
                    })
                    if len(hook_generation_logs) > MAX_LOGS:
                        hook_generation_logs.pop(0)
                else:
                    log_msg = f"❌ [{completed}/{total_leads}] Failed for lead {result['id']}"
                    print(log_msg)
                    hook_generation_logs.append({
                        'timestamp': datetime.now().isoformat(),
                        'message': log_msg
                    })
                    if len(hook_generation_logs) > MAX_LOGS:
                        hook_generation_logs.pop(0)

                # Batch write to database every BATCH_SIZE completions
                if len(batch_buffer) >= BATCH_SIZE or completed == total_leads:
                    try:
                        for item in batch_buffer:
                            db_cursor.execute("""
                                UPDATE leads
                                SET hook = %s, hook_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (item['hook'], item['id']))
                        db_conn.commit()

                        log_msg = f"💾 Saved {len(batch_buffer)} hooks to database"
                        print(log_msg)
                        hook_generation_logs.append({
                            'timestamp': datetime.now().isoformat(),
                            'message': log_msg
                        })
                        if len(hook_generation_logs) > MAX_LOGS:
                            hook_generation_logs.pop(0)

                        batch_buffer = []
                    except Exception as e:
                        log_msg = f"⚠️ Failed to save batch to DB: {e}"
                        print(log_msg)
                        hook_generation_logs.append({
                            'timestamp': datetime.now().isoformat(),
                            'message': log_msg
                        })
                        if len(hook_generation_logs) > MAX_LOGS:
                            hook_generation_logs.pop(0)

                        db_conn.rollback()
                        batch_buffer = []

                # Update status in database every 10 completions
                if completed % 10 == 0 or completed == total_leads:
                    update_task_status('hook_generation',
                        current=completed,
                        progress=int((completed / total_leads) * 100),
                        stat_value=hooks_generated,
                        message=f'Generated {completed}/{total_leads} hooks - {hooks_generated} successful'
                    )

        # Close DB connection
        db_cursor.close()
        db_conn.close()

        # Write all results to CSV
        print(f"💾 Writing {len(all_results)} hooks to CSV...")
        with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['id', 'name', 'title', 'company', 'linkedin_url', 'hook']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for result in all_results:
                writer.writerow({
                    'id': result['id'],
                    'name': result['name'],
                    'title': result['title'],
                    'company': result['company'],
                    'linkedin_url': result['linkedin_url'],
                    'hook': result['hook']
                })

        # Mark as complete
        update_task_status('hook_generation',
            running=False,
            progress=100,
            completed_at=datetime.now(),
            message=f'Complete! Generated {hooks_generated} hooks. Download: {csv_filename}'
        )

        print(f"🎉 Hook generation complete! {hooks_generated} hooks saved to {csv_path}")
    except Exception as e:
        error_msg = f"❌ FATAL ERROR in background hook generation: {e}"
        print(error_msg)
        hook_generation_logs.append({
            'timestamp': datetime.now().isoformat(),
            'message': error_msg
        })
        update_task_status('hook_generation', running=False, message=f'Error: {str(e)}')
        import traceback
        traceback.print_exc()


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


def analyze_lead_worker(lead, api_key):
    """Worker function to analyze a single lead using AI."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
    title = lead.get('current_title', '') or ''
    company = lead.get('current_company', '') or ''
    headline = lead.get('headline', '') or ''

    # Use gpt-4.1-mini for fast, cost-effective analysis
    prompt = f"""Analyze this professional profile and determine if they are a TRADITIONAL CORPORATE EMPLOYEE who would actively apply to multiple jobs.

Title: {title}
Company: {company}
Headline: {headline}

REMOVE if they are:
- Independent consultants, freelancers, contractors
- Entrepreneurs, founders, business owners, CEOs of their own company
- Self-employed professionals
- "Helping companies..." or "Available for..." (consultant language)
- Board members, advisors (unless that's secondary)
- Retired or semi-retired
- Very senior executives who likely won't apply to jobs (e.g., C-suite at large companies)

KEEP if they are:
- Traditional W-2 corporate employees (mid to senior level)
- Directors, VPs, Managers at established companies
- Engineers, analysts, specialists at companies
- People in standard corporate roles who might need to job hunt

Respond with ONLY: KEEP or REMOVE"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are an expert at identifying employment types. Respond only with KEEP or REMOVE."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=10
        )

        decision = response.choices[0].message.content.strip().upper()
        return {
            'id': lead['id'],
            'name': name,
            'title': title,
            'company': company,
            'decision': 'REMOVE' if 'REMOVE' in decision else 'KEEP'
        }
    except Exception as e:
        print(f"   ⚠️  ERROR analyzing {name}: {e}")
        return {
            'id': lead['id'],
            'name': name,
            'title': title,
            'company': company,
            'decision': 'KEEP'  # Keep by default on error
        }


def filter_independent_workers_background():
    """Background task to filter out independent/non-traditional workers using AI with parallel processing."""
    try:
        # Initialize status in database
        update_task_status('filtering',
            running=True,
            started_at=datetime.now(),
            message='Starting filtering...',
            progress=0,
            current=0,
            stat_value=0
        )

        print("🚀 Starting independent worker filtering with parallel processing...")

        # Get OpenAI API key
        api_key = get_openai_api_key()
        if not api_key:
            print("❌ No OpenAI API key available")
            update_task_status('filtering', running=False, message='Error: No API key')
            return

        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get all leads
        cursor.execute("SELECT * FROM leads ORDER BY id")
        all_leads = cursor.fetchall()
        cursor.close()
        conn.close()

        total_leads = len(all_leads)
        update_task_status('filtering',
            total=total_leads,
            message=f'Analyzing {total_leads} leads with 10 parallel workers...'
        )

        print(f"📊 Analyzing {total_leads} leads for employment type with 10 parallel workers...")

        # Use ThreadPoolExecutor for parallel processing
        from concurrent.futures import ThreadPoolExecutor, as_completed
        leads_to_remove = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            # Submit all tasks
            future_to_lead = {executor.submit(analyze_lead_worker, lead, api_key): lead for lead in all_leads}

            # Process results as they complete
            completed = 0
            for future in as_completed(future_to_lead):
                completed += 1
                result = future.result()

                if result['decision'] == 'REMOVE':
                    leads_to_remove.append(result['id'])
                    print(f"   ❌ [{completed}/{total_leads}] REMOVE: {result['name']} - {result['title']} ({result['company']})")
                else:
                    print(f"   ✅ [{completed}/{total_leads}] KEEP: {result['name']} - {result['title']} ({result['company']})")

                # Update status in database every 10 completions
                if completed % 10 == 0 or completed == total_leads:
                    update_task_status('filtering',
                        current=completed,
                        progress=int((completed / total_leads) * 100),
                        stat_value=len(leads_to_remove),
                        message=f'Analyzed {completed}/{total_leads} - Removing {len(leads_to_remove)} leads'
                    )

        # Delete leads in a fresh connection
        update_task_status('filtering', message=f'Deleting {len(leads_to_remove)} leads from database...')

        if leads_to_remove:
            print(f"\n🗑️  Deleting {len(leads_to_remove)} independent/non-traditional workers...")
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM leads WHERE id = ANY(%s)", (leads_to_remove,))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"✅ Successfully deleted {len(leads_to_remove)} leads")
        else:
            print("✅ No leads to remove")

        # Mark as complete
        update_task_status('filtering',
            running=False,
            progress=100,
            completed_at=datetime.now(),
            message=f'Complete! Removed {len(leads_to_remove)} leads, kept {total_leads - len(leads_to_remove)} leads'
        )

        print(f"🎉 Independent worker filtering complete! Removed {len(leads_to_remove)} leads, kept {total_leads - len(leads_to_remove)} leads")

    except Exception as e:
        print(f"❌ Error in independent worker filtering: {e}")
        update_task_status('filtering', running=False, message=f'Error: {str(e)}')
        import traceback
        traceback.print_exc()


@app.route('/api/filter-independent-workers', methods=['POST'])
def api_filter_independent_workers():
    """API endpoint to filter out independent/non-traditional workers using AI."""
    # Start background thread for filtering
    thread = threading.Thread(target=filter_independent_workers_background)
    thread.daemon = True
    thread.start()

    # Return immediately
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT COUNT(*) as count FROM leads")
    count = cursor.fetchone()['count']
    cursor.close()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'Started AI-powered filtering to remove independent workers from {count} leads',
        'total': count
    })


@app.route('/api/generate-all-hooks', methods=['POST'])
def api_generate_all_hooks():
    """API endpoint to generate AI-focused hooks and save to CSV (async)."""
    # Start background thread for hook generation
    # NOTE: daemon=False so Cloud Run doesn't kill the thread when request completes
    thread = threading.Thread(target=generate_hooks_background)
    thread.daemon = False  # Keep container alive!
    thread.start()

    # Return immediately
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT COUNT(*) as count FROM leads")
    count = cursor.fetchone()['count']
    cursor.close()
    conn.close()

    return jsonify({
        'success': True,
        'message': f'Generating AI-focused hooks for {count} leads - will save to CSV',
        'total': count
    })


@app.route('/api/download-hooks/<filename>')
def api_download_hooks(filename):
    """Download generated hooks CSV file."""
    from flask import send_file

    # Security: only allow files matching the pattern
    if not filename.startswith('generated_hooks_') or not filename.endswith('.csv'):
        return jsonify({'error': 'Invalid filename'}), 400

    file_path = os.path.join('/tmp', filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(file_path, as_attachment=True, download_name=filename)


@app.route('/api/list-hook-files')
def api_list_hook_files():
    """List available hook CSV files."""
    import glob

    files = glob.glob('/tmp/generated_hooks_*.csv')
    file_list = []
    for f in files:
        filename = os.path.basename(f)
        size = os.path.getsize(f)
        mtime = os.path.getmtime(f)
        file_list.append({
            'filename': filename,
            'size': size,
            'modified': datetime.fromtimestamp(mtime).isoformat()
        })

    # Sort by modified time, newest first
    file_list.sort(key=lambda x: x['modified'], reverse=True)

    return jsonify({'files': file_list})


@app.route('/api/load-hooks-from-csv', methods=['POST'])
def api_load_hooks_from_csv():
    """Load hooks from CSV file into database."""
    import csv

    data = request.get_json()
    filename = data.get('filename')

    if not filename or not filename.startswith('generated_hooks_') or not filename.endswith('.csv'):
        return jsonify({'error': 'Invalid filename'}), 400

    file_path = os.path.join('/tmp', filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        loaded = 0
        with open(file_path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                cursor.execute("""
                    UPDATE leads
                    SET hook = %s, hook_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (row['hook'], int(row['id'])))
                loaded += 1

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'message': f'Loaded {loaded} hooks into database'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


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


@app.route('/admin')
def admin_panel():
    """Admin panel with task management."""
    return render_template('admin.html')


@app.route('/api/task-status')
def api_task_status():
    """Get status of all background tasks from database."""
    init_task_status_table()  # Ensure table exists

    filtering = get_task_status('filtering')
    hook_gen = get_task_status('hook_generation')
    dedup = get_task_status('deduplication')

    # Add legacy field names for backward compatibility
    default_status = {'running': False, 'progress': 0, 'total': 0, 'current': 0, 'stat_value': 0, 'message': 'Not started', 'started_at': None, 'completed_at': None}

    filtering_status = filtering or default_status.copy()
    hook_status = hook_gen or default_status.copy()
    dedup_status = dedup or default_status.copy()

    # Add legacy field names
    filtering_status['removed'] = filtering_status.get('stat_value', 0)
    hook_status['generated'] = hook_status.get('stat_value', 0)
    dedup_status['duplicates'] = dedup_status.get('stat_value', 0)

    return jsonify({
        'filtering': filtering_status,
        'hook_generation': hook_status,
        'deduplication': dedup_status
    })


@app.route('/api/start-deduplication', methods=['POST'])
def api_start_deduplication():
    """Start deduplication process."""
    status = get_task_status('deduplication')
    if status and status['running']:
        return jsonify({'error': 'Deduplication already running'}), 400

    thread = threading.Thread(target=run_deduplication_background)
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'message': 'Deduplication started'
    })


def run_deduplication_background():
    """Background task to deduplicate leads."""
    try:
        # Initialize status in database
        update_task_status('deduplication',
            running=True,
            started_at=datetime.now(),
            message='Starting deduplication...',
            progress=0,
            stat_value=0
        )

        print("🚀 Starting deduplication...")
        conn = get_db_connection()
        cursor = conn.cursor()

        # Find duplicates by LinkedIn URL
        update_task_status('deduplication', message='Finding duplicates...')
        cursor.execute("""
            SELECT linkedin_url, COUNT(*) as count, array_agg(id ORDER BY created_at) as ids
            FROM leads
            WHERE linkedin_url IS NOT NULL AND linkedin_url != ''
            GROUP BY linkedin_url
            HAVING COUNT(*) > 1
        """)
        duplicates = cursor.fetchall()

        total_groups = len(duplicates)
        update_task_status('deduplication',
            total=total_groups,
            message=f'Found {total_groups} duplicate groups'
        )

        print(f"📊 Found {total_groups} duplicate groups")

        total_removed = 0
        for idx, (url, count, ids) in enumerate(duplicates, 1):
            # Keep first, delete rest
            ids_to_delete = ids[1:]
            cursor.execute("DELETE FROM leads WHERE id = ANY(%s)", (ids_to_delete,))
            conn.commit()
            total_removed += len(ids_to_delete)

            print(f"✅ [{idx}/{total_groups}] Removed {len(ids_to_delete)} duplicates for {url}")

            # Update status every 10 groups or at the end
            if idx % 10 == 0 or idx == total_groups:
                update_task_status('deduplication',
                    current=idx,
                    progress=int((idx / total_groups) * 100) if total_groups > 0 else 100,
                    stat_value=total_removed,
                    message=f'Processed {idx}/{total_groups} groups - Removed {total_removed} duplicates'
                )

        cursor.close()
        conn.close()

        # Mark as complete
        update_task_status('deduplication',
            running=False,
            progress=100,
            completed_at=datetime.now(),
            message=f'Complete! Removed {total_removed} duplicate leads'
        )

        print(f"🎉 Deduplication complete! Removed {total_removed} duplicates")

    except Exception as e:
        print(f"❌ Error in deduplication: {e}")
        update_task_status('deduplication', running=False, message=f'Error: {str(e)}')
        import traceback
        traceback.print_exc()


@app.route('/analytics')
def analytics():
    """Analytics dashboard page."""
    return render_template('analytics.html')


@app.route('/api/analytics/summary')
def analytics_summary():
    """Get summary statistics for analytics dashboard."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Total leads
        cursor.execute("SELECT COUNT(*) as total FROM leads")
        total_leads = cursor.fetchone()['total']

        # Contacted (viewed) leads
        cursor.execute("SELECT COUNT(*) as contacted FROM leads WHERE viewed = TRUE")
        contacted_leads = cursor.fetchone()['contacted']

        # Uncontacted leads
        uncontacted_leads = total_leads - contacted_leads

        # Leads with hooks
        cursor.execute("SELECT COUNT(*) as with_hooks FROM leads WHERE hook IS NOT NULL AND hook != ''")
        leads_with_hooks = cursor.fetchone()['with_hooks']

        # Leads without hooks
        leads_without_hooks = total_leads - leads_with_hooks

        # Contact rate
        contact_rate = (contacted_leads / total_leads * 100) if total_leads > 0 else 0

        cursor.close()
        conn.close()

        return jsonify({
            'total_leads': total_leads,
            'contacted_leads': contacted_leads,
            'uncontacted_leads': uncontacted_leads,
            'leads_with_hooks': leads_with_hooks,
            'leads_without_hooks': leads_without_hooks,
            'contact_rate': round(contact_rate, 1)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/by-company')
def analytics_by_company():
    """Get lead statistics by company."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                current_company,
                COUNT(*) as total,
                SUM(CASE WHEN viewed = TRUE THEN 1 ELSE 0 END) as contacted
            FROM leads
            WHERE current_company IS NOT NULL AND current_company != ''
            GROUP BY current_company
            ORDER BY total DESC
            LIMIT 15
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify([dict(row) for row in results])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/by-location')
def analytics_by_location():
    """Get lead statistics by location."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                location,
                COUNT(*) as total,
                SUM(CASE WHEN viewed = TRUE THEN 1 ELSE 0 END) as contacted
            FROM leads
            WHERE location IS NOT NULL AND location != ''
            GROUP BY location
            ORDER BY total DESC
            LIMIT 15
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify([dict(row) for row in results])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/by-title')
def analytics_by_title():
    """Get lead statistics by job title."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                current_title,
                COUNT(*) as total,
                SUM(CASE WHEN viewed = TRUE THEN 1 ELSE 0 END) as contacted
            FROM leads
            WHERE current_title IS NOT NULL AND current_title != ''
            GROUP BY current_title
            ORDER BY total DESC
            LIMIT 15
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify([dict(row) for row in results])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/contact-timeline')
def analytics_contact_timeline():
    """Get contact activity over time."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                DATE(viewed_at) as date,
                COUNT(*) as contacts
            FROM leads
            WHERE viewed = TRUE AND viewed_at IS NOT NULL
            GROUP BY DATE(viewed_at)
            ORDER BY date DESC
            LIMIT 30
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Convert date objects to strings
        data = []
        for row in results:
            data.append({
                'date': row['date'].isoformat() if row['date'] else None,
                'contacts': row['contacts']
            })

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/analytics/contact-status')
def analytics_contact_status():
    """Get contact status breakdown for pie chart."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                CASE
                    WHEN viewed = TRUE THEN 'Contacted'
                    ELSE 'Not Contacted'
                END as status,
                COUNT(*) as count
            FROM leads
            GROUP BY viewed
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify([dict(row) for row in results])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduler/summary')
def scheduler_summary():
    """Get summary statistics from scheduler database."""
    try:
        conn = get_scheduler_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Total prospects
        cursor.execute("SELECT COUNT(*) as total FROM prospects")
        total_prospects = cursor.fetchone()['total']

        # Qualified prospects
        cursor.execute("SELECT COUNT(*) as qualified FROM prospects WHERE qualified = TRUE")
        qualified_prospects = cursor.fetchone()['qualified']

        # Total bookings
        cursor.execute("SELECT COUNT(*) as total FROM bookings")
        total_bookings = cursor.fetchone()['total']

        # Confirmed bookings
        cursor.execute("SELECT COUNT(*) as confirmed FROM bookings WHERE status = 'confirmed'")
        confirmed_bookings = cursor.fetchone()['confirmed']

        # Pending bookings
        cursor.execute("SELECT COUNT(*) as pending FROM bookings WHERE status = 'pending'")
        pending_bookings = cursor.fetchone()['pending']

        # Cancelled bookings
        cursor.execute("SELECT COUNT(*) as cancelled FROM bookings WHERE status = 'cancelled'")
        cancelled_bookings = cursor.fetchone()['cancelled']

        cursor.close()
        conn.close()

        return jsonify({
            'total_prospects': total_prospects,
            'qualified_prospects': qualified_prospects,
            'unqualified_prospects': total_prospects - qualified_prospects,
            'qualification_rate': round((qualified_prospects / total_prospects * 100) if total_prospects > 0 else 0, 1),
            'total_bookings': total_bookings,
            'confirmed_bookings': confirmed_bookings,
            'pending_bookings': pending_bookings,
            'cancelled_bookings': cancelled_bookings,
            'booking_rate': round((total_bookings / qualified_prospects * 100) if qualified_prospects > 0 else 0, 1)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduler/bookings-timeline')
def scheduler_bookings_timeline():
    """Get bookings over time from scheduler database."""
    try:
        conn = get_scheduler_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                DATE("createdAt") as date,
                COUNT(*) as bookings,
                SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END) as confirmed
            FROM bookings
            WHERE "createdAt" IS NOT NULL
            GROUP BY DATE("createdAt")
            ORDER BY date DESC
            LIMIT 30
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Convert date objects to strings
        data = []
        for row in results:
            data.append({
                'date': row['date'].isoformat() if row['date'] else None,
                'bookings': row['bookings'],
                'confirmed': row['confirmed']
            })

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduler/bookings-by-status')
def scheduler_bookings_by_status():
    """Get booking status breakdown for pie chart."""
    try:
        conn = get_scheduler_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                status,
                COUNT(*) as count
            FROM bookings
            GROUP BY status
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify([dict(row) for row in results])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduler/prospects-qualification')
def scheduler_prospects_qualification():
    """Get prospect qualification breakdown."""
    try:
        conn = get_scheduler_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                CASE
                    WHEN qualified = TRUE THEN 'Qualified'
                    ELSE 'Not Qualified'
                END as status,
                COUNT(*) as count
            FROM prospects
            GROUP BY qualified
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify([dict(row) for row in results])
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduler/debug-columns')
def scheduler_debug_columns():
    """Debug endpoint to see actual column names."""
    try:
        conn = get_scheduler_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("SELECT * FROM bookings LIMIT 1")
        bookings_row = cursor.fetchone()

        cursor.execute("SELECT id, email, name, company, phone, qualified, qualificationResponses FROM prospects LIMIT 1")
        prospects_row = cursor.fetchone()

        cursor.close()
        conn.close()

        result = {
            'bookings_columns': list(bookings_row.keys()) if bookings_row else [],
            'prospects_columns': list(prospects_row.keys()) if prospects_row else []
        }

        if prospects_row:
            result['sample_prospect'] = {
                'id': prospects_row['id'],
                'email': prospects_row['email'],
                'name': prospects_row['name'],
                'company': prospects_row['company'],
                'phone': prospects_row['phone'],
                'qualified': prospects_row['qualified'],
                'qualificationResponses': str(prospects_row['qualificationResponses']) if prospects_row['qualificationResponses'] else None
            }

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduler/todays-bookings')
def scheduler_todays_bookings():
    """Get bookings created today with prospect details."""
    try:
        conn = get_scheduler_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                bookings.id,
                bookings."startTime" as scheduled_at,
                bookings."createdAt" as created_at,
                bookings.status,
                prospects.name,
                prospects.email
            FROM bookings
            JOIN prospects ON bookings."prospectId" = prospects.id
            WHERE DATE(bookings."createdAt") = CURRENT_DATE
            ORDER BY bookings."createdAt" DESC
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Convert datetime objects to strings
        data = []
        for row in results:
            data.append({
                'id': row['id'],
                'scheduled_at': row['scheduled_at'].isoformat() if row['scheduled_at'] else None,
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'status': row['status'],
                'name': row['name'],
                'email': row['email']
            })

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scheduler/upcoming-calls')
def scheduler_upcoming_calls():
    """Get upcoming calls grouped by scheduled date."""
    try:
        conn = get_scheduler_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                DATE(bookings."startTime") as date,
                COUNT(*) as count,
                json_agg(
                    json_build_object(
                        'id', bookings.id,
                        'time', bookings."startTime",
                        'status', bookings.status,
                        'name', prospects.name,
                        'email', prospects.email
                    ) ORDER BY bookings."startTime"
                ) as bookings
            FROM bookings
            JOIN prospects ON bookings."prospectId" = prospects.id
            WHERE bookings."startTime" >= CURRENT_DATE
                AND bookings.status != 'cancelled'
            GROUP BY DATE(bookings."startTime")
            ORDER BY date ASC
            LIMIT 60
        """)

        results = cursor.fetchall()
        cursor.close()
        conn.close()

        # Convert date objects to strings
        data = []
        for row in results:
            data.append({
                'date': row['date'].isoformat() if row['date'] else None,
                'count': row['count'],
                'bookings': row['bookings']
            })

        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/hook-generation-logs')
def api_hook_generation_logs():
    """Get recent hook generation logs."""
    limit = request.args.get('limit', 100, type=int)
    return jsonify({
        'logs': hook_generation_logs[-limit:],
        'total': len(hook_generation_logs)
    })


@app.route('/api/download-leads-csv')
def download_leads_csv():
    """Download all leads as CSV with email in first column."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT
                email_address,
                first_name,
                last_name,
                current_company,
                current_title,
                location,
                headline,
                profile_url,
                phone_number,
                hook,
                viewed,
                active_project,
                notes,
                feedback
            FROM leads
            ORDER BY id
        """)

        leads = cursor.fetchall()
        cursor.close()
        conn.close()

        # Create CSV in memory
        output = StringIO()
        if leads:
            # Get column names from first row
            fieldnames = list(leads[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(leads)

        # Create response
        csv_data = output.getvalue()
        response = make_response(csv_data)
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=leads_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'

        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)
