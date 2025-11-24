#!/usr/bin/env python3
"""Test hook generation for a single lead to debug issues."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI

# Database connection
DB_HOST = '35.193.184.122'
DB_NAME = 'linkedin_leads_data'
DB_USER = 'postgres'
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'Mobius@2024')

# Get OpenAI API key
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')

def test_single_lead():
    """Test hook generation for one lead."""
    
    # Connect to database
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get one lead
    cursor.execute("SELECT * FROM leads LIMIT 1")
    lead = cursor.fetchone()
    
    print(f"Testing lead: {lead['name']}")
    print(f"Title: {lead.get('title', 'N/A')}")
    print(f"Company: {lead.get('company', 'N/A')}")
    print(f"About: {lead.get('about', 'N/A')[:200] if lead.get('about') else 'N/A'}")
    print("-" * 80)
    
    # Build profile summary
    name = lead.get('name', 'this person')
    title = lead.get('title', 'professional')
    company = lead.get('company', 'their company')
    location = lead.get('location', '')
    about = lead.get('about', '')[:500] if lead.get('about') else ''
    
    profile_summary = f"{name} is a {title}"
    if company:
        profile_summary += f" at {company}"
    if location:
        profile_summary += f" in {location}"
    if about:
        profile_summary += f". Background: {about}"
    
    print(f"Profile Summary:\n{profile_summary}")
    print("-" * 80)
    
    # Build prompt
    if about:
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
        prompt = f"""Write a direct, simple hook (3-4 sentences) for this person. Use simple words.

Profile: {profile_summary}

Structure:
1. PROBLEM STATEMENT: "AI is now automating [common tasks for their role], which is changing what companies want from [their role]."
2. ACKNOWLEDGE: "You have experience as a {title} at {company}."
3. QUESTION: "Have you thought about repositioning to [natural evolution like strategy, leadership, architecture]?"
4. CLOSE: "mobiusengine.ai has worked with many [their role] in the past 3 years to help them land their next role."

Example for Mechanical Engineer: "AI is now automating CAD design and simulation tasks, which is changing what companies want from mechanical engineers. You have experience as a Mechanical Engineer at Amentum. Have you thought about repositioning to engineering leadership or systems architecture roles? mobiusengine.ai has worked with many mechanical engineers in the past 3 years to help them land their next role."

Write the hook (under 60 words, use simple language):"""
    
    print(f"Prompt:\n{prompt[:500]}...")
    print("-" * 80)
    
    # Call OpenAI
    print("Calling OpenAI API...")
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a career advisor writing personalized LinkedIn outreach messages."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        
        hook = response.choices[0].message.content.strip()
        print(f"\n✅ Generated Hook:\n{hook}")
        print("-" * 80)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    test_single_lead()

