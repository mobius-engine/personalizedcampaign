#!/usr/bin/env python3
"""
Generate hooks for all leads without hooks
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from google.cloud import secretmanager
from openai import OpenAI

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '35.193.184.122'),
    'database': os.getenv('DB_NAME', 'linkedin_leads_data'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'TempPassword123!'),
}

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
            print("❌ No API key available")
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
        print(f"❌ Error generating hook: {e}")
        return None


def main():
    """Generate hooks for all leads without hooks."""
    print("🚀 Starting hook generation for all leads...")
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get leads without hooks
    cursor.execute("SELECT * FROM leads WHERE hook IS NULL OR hook = '' ORDER BY id")
    leads_without_hooks = cursor.fetchall()
    
    total_leads = len(leads_without_hooks)
    print(f"📊 Found {total_leads} leads without hooks\n")

    if total_leads == 0:
        print("✅ All leads already have hooks!")
        cursor.close()
        conn.close()
        return

    hooks_generated = 0
    hooks_failed = 0
    
    for idx, lead in enumerate(leads_without_hooks, 1):
        lead_name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
        print(f"⏳ [{idx}/{total_leads}] Generating hook for: {lead_name} (ID: {lead['id']})...")
        
        hook = generate_hook_for_lead(lead)
        if hook:
            cursor.execute("""
                UPDATE leads
                SET hook = %s, hook_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (hook, lead['id']))
            conn.commit()
            hooks_generated += 1
            print(f"   ✅ Generated hook {hooks_generated}/{total_leads}")
            print(f"   📝 Hook: {hook[:100]}...\n")
        else:
            hooks_failed += 1
            print(f"   ❌ Failed to generate hook\n")

    cursor.close()
    conn.close()

    print(f"\n{'='*60}")
    print(f"🎉 Hook generation complete!")
    print(f"✅ Successfully generated: {hooks_generated} hooks")
    print(f"❌ Failed: {hooks_failed} hooks")
    print(f"📊 Total processed: {total_leads} leads")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

