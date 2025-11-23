#!/usr/bin/env python3
"""
Generate AI-powered hooks for LinkedIn leads using OpenAI GPT-4o.
"""

import os
import sys
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from google.cloud import secretmanager
from openai import OpenAI

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '35.193.184.122'),
    'database': os.getenv('DB_NAME', 'linkedin_leads_data'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': sys.argv[1] if len(sys.argv) > 1 else os.getenv('DB_PASSWORD', ''),
}

GCP_PROJECT_ID = "jobs-data-linkedin"
SECRET_NAME = "openai-api-key"


def get_openai_api_key():
    """Retrieve OpenAI API key from GCP Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{GCP_PROJECT_ID}/secrets/{SECRET_NAME}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8").strip()


def generate_hook(lead):
    """
    Generate a personalized hook for a lead using GPT-4o.
    
    Args:
        lead: Dictionary containing lead information
        
    Returns:
        Generated hook text
    """
    # Extract relevant fields
    name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
    credentials = lead.get('headline', '') or ''
    title_keywords = lead.get('current_title', '') or ''
    location = lead.get('location', '') or ''
    current_role = lead.get('current_title', '') or ''
    company = lead.get('current_company', '') or ''
    
    # Build the prompt
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
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert at crafting compelling, concise professional outreach messages."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200
        )

        hook = response.choices[0].message.content.strip()
        return hook

    except Exception as e:
        import traceback
        print(f"  ❌ Error generating hook: {e}")
        print(f"  📋 Details: {traceback.format_exc()}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate_hooks.py <database_password> [--limit N] [--regenerate]")
        print("\nOptions:")
        print("  --limit N       Generate hooks for only N leads")
        print("  --regenerate    Regenerate hooks even if they already exist")
        sys.exit(1)
    
    # Parse arguments
    limit = None
    regenerate = False
    
    for i, arg in enumerate(sys.argv[2:], start=2):
        if arg == '--limit' and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
        elif arg == '--regenerate':
            regenerate = True
    
    print("🔑 Retrieving OpenAI API key from Secret Manager...")
    api_key = get_openai_api_key()
    os.environ['OPENAI_API_KEY'] = api_key
    print("✅ API key retrieved\n")
    
    print("📊 Connecting to database...")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get leads that need hooks
    if regenerate:
        query = "SELECT * FROM leads ORDER BY id"
    else:
        query = "SELECT * FROM leads WHERE hook IS NULL OR hook = '' ORDER BY id"
    
    if limit:
        query += f" LIMIT {limit}"
    
    cursor.execute(query)
    leads = cursor.fetchall()
    
    total = len(leads)
    print(f"📝 Found {total} leads to process\n")
    
    if total == 0:
        print("✅ All leads already have hooks!")
        cursor.close()
        conn.close()
        return
    
    print("=" * 80)
    
    success_count = 0
    error_count = 0
    
    for i, lead in enumerate(leads, 1):
        name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
        company = lead.get('current_company', '') or 'Unknown'
        
        print(f"\n[{i}/{total}] Generating hook for: {name} @ {company}")
        
        hook = generate_hook(lead)
        
        if hook:
            # Update database
            cursor.execute("""
                UPDATE leads 
                SET hook = %s, hook_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (hook, lead['id']))
            conn.commit()
            
            print(f"  ✅ Hook generated ({len(hook)} chars)")
            print(f"  📝 Preview: {hook[:100]}...")
            success_count += 1
        else:
            error_count += 1
        
        # Rate limiting - be nice to the API
        if i < total:
            time.sleep(0.5)  # 500ms delay between requests
    
    print("\n" + "=" * 80)
    print("📊 Summary:")
    print(f"  ✅ Success: {success_count}")
    print(f"  ❌ Errors: {error_count}")
    print(f"  📈 Total: {total}")
    print("=" * 80)
    
    cursor.close()
    conn.close()
    
    print("\n✅ Hook generation complete!")


if __name__ == "__main__":
    main()

