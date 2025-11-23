#!/usr/bin/env python3
"""
Filter leads by estimated salary using AI analysis.
Remove leads likely making less than $150K per year.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from google.cloud import secretmanager
from openai import OpenAI
import json
import time

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
        # Try environment variable as fallback
        return os.getenv('OPENAI_API_KEY')


def estimate_salary(lead, openai_client):
    """Use AI to estimate if a lead likely makes $150K+ per year."""
    
    title = lead.get('current_title', '') or ''
    company = lead.get('current_company', '') or ''
    headline = lead.get('headline', '') or ''
    location = lead.get('location', '') or ''
    
    prompt = f"""Analyze this professional profile and determine if they likely earn $150,000+ per year in the United States job market.

Job Title: {title}
Company: {company}
Headline: {headline}
Location: {location}

Consider:
- Job title seniority (C-level, VP, Director, Senior, Manager, etc.)
- Industry and company type
- Geographic location (major tech hubs pay more)
- Typical salary ranges for this role
- Professional credentials and experience level indicated

Respond with ONLY a JSON object in this exact format:
{{"likely_150k_plus": true/false, "confidence": "high/medium/low", "reasoning": "brief explanation"}}"""

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are an expert salary analyst with deep knowledge of US job market compensation. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        
        result_text = response.choices[0].message.content.strip()
        # Parse JSON response
        result = json.loads(result_text)
        return result
    except Exception as e:
        print(f"   ⚠️  Error analyzing lead: {e}")
        return {"likely_150k_plus": True, "confidence": "low", "reasoning": "Error - keeping lead by default"}


def main():
    """Filter leads by salary estimation."""
    print("🚀 Starting salary-based lead filtering...")
    print("📊 Target: Remove leads likely making < $150K/year\n")
    
    api_key = get_openai_api_key()
    if not api_key:
        print("❌ No OpenAI API key available")
        return
    
    openai_client = OpenAI(api_key=api_key)
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get all leads
    cursor.execute("SELECT * FROM leads ORDER BY id")
    all_leads = cursor.fetchall()
    
    total_leads = len(all_leads)
    print(f"📊 Total leads in database: {total_leads}\n")

    leads_to_remove = []
    leads_to_keep = []
    
    for idx, lead in enumerate(all_leads, 1):
        name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
        title = lead.get('current_title', '') or 'Unknown'
        
        print(f"[{idx}/{total_leads}] Analyzing: {name} - {title}")
        
        result = estimate_salary(lead, openai_client)
        
        if result['likely_150k_plus']:
            leads_to_keep.append(lead)
            print(f"   ✅ KEEP - Likely $150K+ ({result['confidence']} confidence)")
        else:
            leads_to_remove.append(lead)
            print(f"   ❌ REMOVE - Likely < $150K ({result['confidence']} confidence)")
        
        print(f"   💡 {result['reasoning']}\n")
        
        # Small delay to avoid rate limits
        if idx % 10 == 0:
            time.sleep(1)

    print(f"\n{'='*70}")
    print(f"📊 ANALYSIS COMPLETE")
    print(f"{'='*70}")
    print(f"Total leads analyzed: {total_leads}")
    print(f"✅ Leads to KEEP (likely $150K+): {len(leads_to_keep)}")
    print(f"❌ Leads to REMOVE (likely < $150K): {len(leads_to_remove)}")
    print(f"{'='*70}\n")
    
    if leads_to_remove:
        print(f"⚠️  About to DELETE {len(leads_to_remove)} leads from database!")
        print("Leads to be removed:")
        for lead in leads_to_remove[:10]:  # Show first 10
            name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
            title = lead.get('current_title', '')
            print(f"  - {name} ({title})")
        if len(leads_to_remove) > 10:
            print(f"  ... and {len(leads_to_remove) - 10} more")
        
        print("\n")
        response = input("Type 'DELETE' to confirm removal: ")
        if response == 'DELETE':
            print("\n🗑️  Deleting leads...")
            for lead in leads_to_remove:
                cursor.execute("DELETE FROM leads WHERE id = %s", (lead['id'],))
            conn.commit()
            print(f"✅ Successfully deleted {len(leads_to_remove)} leads")
        else:
            print("❌ Deletion cancelled")
    else:
        print("✅ No leads to remove - all leads likely make $150K+")

    cursor.close()
    conn.close()

    print(f"\n{'='*70}")
    print(f"✅ FILTERING COMPLETE")
    print(f"Remaining leads in database: {len(leads_to_keep)}")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()

