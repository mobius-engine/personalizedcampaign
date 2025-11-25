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
from concurrent.futures import ThreadPoolExecutor, as_completed

# Database configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', '35.193.184.122'),
    'database': os.getenv('DB_NAME', 'linkedin_leads_data'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'Mobius@2024'),
}

GCP_PROJECT_ID = "jobs-data-linkedin"
SECRET_NAME = "openai-api-key"


def get_openai_api_key():
    """Retrieve OpenAI API key from environment variable."""
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY environment variable not set!")
    return api_key


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
            model="gpt-4.1-mini",
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
    completed = 0

    print(f"🚀 Processing with 30 parallel workers...\n")

    # Process leads in parallel
    with ThreadPoolExecutor(max_workers=30) as executor:
        # Submit all tasks
        future_to_lead = {executor.submit(estimate_salary, lead, openai_client): lead for lead in all_leads}

        # Process results as they complete
        for future in as_completed(future_to_lead):
            lead = future_to_lead[future]
            completed += 1

            name = f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip()
            title = lead.get('current_title', '') or 'Unknown'

            try:
                result = future.result()

                if result['likely_150k_plus']:
                    leads_to_keep.append(lead)
                    print(f"[{completed}/{total_leads}] ✅ KEEP - {name} - {title}")
                    print(f"   💡 {result['reasoning'][:100]}...\n")
                else:
                    leads_to_remove.append(lead)
                    print(f"[{completed}/{total_leads}] ❌ REMOVE - {name} - {title}")
                    print(f"   💡 {result['reasoning'][:100]}...\n")

                # Progress update every 100 leads
                if completed % 100 == 0:
                    print(f"📊 Progress: {completed}/{total_leads} ({int(completed/total_leads*100)}%) - Keeping: {len(leads_to_keep)}, Removing: {len(leads_to_remove)}\n")

            except Exception as e:
                print(f"[{completed}/{total_leads}] ⚠️  Error analyzing {name}: {e}")
                leads_to_keep.append(lead)  # Keep by default on error

    print(f"\n{'='*70}")
    print(f"📊 ANALYSIS COMPLETE")
    print(f"{'='*70}")
    print(f"Total leads analyzed: {total_leads}")
    print(f"✅ Leads to KEEP (likely $150K+): {len(leads_to_keep)}")
    print(f"❌ Leads to REMOVE (likely < $150K): {len(leads_to_remove)}")
    print(f"{'='*70}\n")
    
    if leads_to_remove:
        # Save IDs to file for batch deletion
        ids_to_remove = [lead['id'] for lead in leads_to_remove]
        with open('leads_to_remove_ids.json', 'w') as f:
            json.dump(ids_to_remove, f)
        print(f"💾 Saved {len(ids_to_remove)} lead IDs to leads_to_remove_ids.json")

        print(f"\n⚠️  About to DELETE {len(leads_to_remove)} leads from database!")
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
            print("\n🗑️  Deleting leads in batches...")
            # Delete in batches of 1000 for speed
            batch_size = 1000
            for i in range(0, len(ids_to_remove), batch_size):
                batch = ids_to_remove[i:i+batch_size]
                cursor.execute("DELETE FROM leads WHERE id = ANY(%s)", (batch,))
                conn.commit()
                print(f"  ✅ Deleted batch {i//batch_size + 1}/{(len(ids_to_remove)-1)//batch_size + 1} ({len(batch)} leads)")
            print(f"\n✅ Successfully deleted {len(leads_to_remove)} leads!")
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

