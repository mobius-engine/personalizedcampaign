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
    
    prompt = f"""Write a direct, simple hook (3-4 sentences) for this person. Use simple words.

Profile: {profile_summary}

Structure:
1. PROBLEM STATEMENT: "AI is now [automating specific tasks], which is changing what [hiring managers/companies] are looking for in [their role]."
   - Name specific tasks AI is doing
   - Show the impact/pain point for job seekers
2. ACKNOWLEDGE: "You have experience in [specific thing they do at their company]"
3. QUESTION: "Have you thought about repositioning to [specific new role/focus]?"
4. CLOSE: "mobiusengine.ai has worked with many [their role] in the past 3 years to help them land their next role."

Example for HR Manager:
"AI is now automating many HR tasks like screening resumes and scheduling interviews, which is changing what hiring managers are looking for in HR leaders. You have experience managing people and processes at Meta. Have you thought about repositioning to HR tech strategy roles? mobiusengine.ai has worked with many HR managers in the past 3 years to help them land their next role."

Example for Product Manager:
"AI now writes PRDs and runs A/B tests automatically, which is changing what companies want from product managers. You have experience building products at Amazon. Have you thought about repositioning to AI product strategy roles? mobiusengine.ai has worked with many product managers in the past 3 years to help them land their next role."

Write the hook (under 60 words, use simple language):"""
    
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

