#!/usr/bin/env python3
"""Test script to generate sample hooks with new AI-focused prompt."""

import os
from openai import OpenAI

# Sample leads to test
sample_leads = [
    {
        'name': 'Sarah Chen',
        'title': 'Senior Data Analyst',
        'company': 'Microsoft',
        'location': 'Seattle, WA'
    },
    {
        'name': 'Michael Rodriguez',
        'title': 'Product Manager',
        'company': 'Amazon',
        'location': 'San Francisco, CA'
    },
    {
        'name': 'Jennifer Williams',
        'title': 'Marketing Director',
        'company': 'Salesforce',
        'location': 'New York, NY'
    },
    {
        'name': 'David Kim',
        'title': 'Software Engineer',
        'company': 'Google',
        'location': 'Mountain View, CA'
    },
    {
        'name': 'Emily Thompson',
        'title': 'HR Manager',
        'company': 'Meta',
        'location': 'Austin, TX'
    }
]

def generate_hook(lead):
    """Generate AI-focused hook for a lead."""
    client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
    
    name = lead['name']
    title = lead['title']
    company = lead['company']
    location = lead.get('location', '')
    
    profile_summary = f"{name} is a {title}"
    if company:
        profile_summary += f" at {company}"
    if location:
        profile_summary += f" in {location}"
    
    prompt = f"""Write a conversational 2-sentence hook for this person. Use direct address ("you're", "your").

Profile: {profile_summary}

SENTENCE 1 - Challenger insight about their FUNCTIONAL ROLE:
- Challenge their current approach to their SPECIFIC job function (data analysis, product management, marketing, etc.)
- Focus on how AI is changing their day-to-day work or making their current approach obsolete
- Start with "If you're still..." or "Most [role]..." or "Your [specific task]..."
- Make them question if their functional skills are falling behind

SENTENCE 2 - mobiusengine.ai value proposition:
- MUST start with: "At mobiusengine.ai, we've worked with many [their role/background] and landed them roles without the frustration of online job applications"
- Be specific about their role (e.g., "senior data analysts", "product managers", "marketing directors")
- Keep the exact phrasing about "without the frustration of online job applications"

Example: "If you're still doing manual data analysis in Excel, AI is already doing it faster and better. At mobiusengine.ai, we've worked with many data analysts and landed them roles without the frustration of online job applications."

Write ONLY the 2-sentence hook (under 50 words):"""
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a strategic career advisor focused on AI's impact on professional roles. Be direct and insightful."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.8,
        max_tokens=150
    )
    
    hook = response.choices[0].message.content.strip()
    hook = hook.strip('"').strip("'")
    
    return hook

if __name__ == '__main__':
    print("🎯 Generating AI-Focused Hooks\n")
    print("=" * 80)
    
    for i, lead in enumerate(sample_leads, 1):
        print(f"\n{i}. {lead['name']} - {lead['title']} at {lead['company']}")
        print("-" * 80)
        
        try:
            hook = generate_hook(lead)
            print(f"HOOK: {hook}")
        except Exception as e:
            print(f"ERROR: {e}")
        
        print()
    
    print("=" * 80)
    print("✅ Sample generation complete!")

