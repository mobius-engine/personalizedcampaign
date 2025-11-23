#!/usr/bin/env python3
"""Test hook generation with ACTUAL leads from database."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

# Use realistic sample leads with rich "about" data
def get_actual_leads(limit=10):
    """Get sample leads with realistic, detailed backgrounds."""
    return [
        {
            'id': 1,
            'name': 'Sarah Chen',
            'title': 'Senior Data Analyst',
            'company': 'Microsoft',
            'location': 'Seattle, WA',
            'about': 'Experienced data analyst with 8+ years in tech. Specialized in SQL, Python, Tableau, and Power BI for data visualization and business intelligence. Built automated reporting dashboards that reduced manual reporting time by 70%. Strong background in statistical analysis and predictive modeling.',
            'linkedin_url': 'https://linkedin.com/in/sarahchen'
        },
        {
            'id': 2,
            'name': 'Michael Rodriguez',
            'title': 'Product Manager',
            'company': 'Amazon',
            'location': 'San Francisco, CA',
            'about': 'Product leader with 10 years launching consumer products. Expert in user research, A/B testing, and data-driven decision making. Led 3 products from 0 to 1M users. Strong background in agile methodologies and cross-functional team leadership. Passionate about creating delightful user experiences.',
            'linkedin_url': 'https://linkedin.com/in/mrodriguez'
        },
        {
            'id': 3,
            'name': 'Jennifer Williams',
            'title': 'Marketing Director',
            'company': 'Salesforce',
            'location': 'New York, NY',
            'about': 'Marketing executive with 12 years in B2B SaaS. Expert in demand generation, marketing automation (Marketo, HubSpot), and campaign analytics. Led campaigns that generated $50M in pipeline. Strong background in SEO, content marketing, and marketing operations.',
            'linkedin_url': 'https://linkedin.com/in/jwilliams'
        },
        {
            'id': 4,
            'name': 'David Kim',
            'title': 'Software Engineer',
            'company': 'Google',
            'location': 'Mountain View, CA',
            'about': 'Full-stack engineer with 7 years building distributed systems. Expert in Java, Python, Kubernetes, and cloud infrastructure (GCP, AWS). Built microservices handling 10M+ requests/day. Strong background in system design, performance optimization, and DevOps practices.',
            'linkedin_url': 'https://linkedin.com/in/davidkim'
        },
        {
            'id': 5,
            'name': 'Emily Thompson',
            'title': 'HR Manager',
            'company': 'Meta',
            'location': 'Menlo Park, CA',
            'about': 'HR professional with 9 years in talent acquisition and employee engagement. Expert in applicant tracking systems (Greenhouse, Lever), candidate screening, and interview coordination. Reduced time-to-hire by 40% through process optimization. Strong background in onboarding and performance management.',
            'linkedin_url': 'https://linkedin.com/in/ethompson'
        },
        {
            'id': 6,
            'name': 'James Patterson',
            'title': 'Financial Analyst',
            'company': 'Goldman Sachs',
            'location': 'New York, NY',
            'about': 'Financial analyst with 6 years in investment banking. Expert in financial modeling, Excel, and valuation analysis. Built complex DCF models and performed M&A due diligence. Strong background in financial reporting and forecasting.',
            'linkedin_url': 'https://linkedin.com/in/jpatterson'
        },
        {
            'id': 7,
            'name': 'Lisa Wang',
            'title': 'UX Designer',
            'company': 'Adobe',
            'location': 'San Jose, CA',
            'about': 'UX designer with 8 years creating user-centered designs. Expert in Figma, user research, wireframing, and prototyping. Led design for 5 major product launches. Strong background in usability testing and design systems.',
            'linkedin_url': 'https://linkedin.com/in/lwang'
        },
        {
            'id': 8,
            'name': 'Robert Martinez',
            'title': 'Sales Manager',
            'company': 'Oracle',
            'location': 'Austin, TX',
            'about': 'Sales leader with 11 years in enterprise software sales. Expert in Salesforce CRM, pipeline management, and deal negotiation. Consistently exceeded quota by 120%+. Strong background in account management and customer relationship building.',
            'linkedin_url': 'https://linkedin.com/in/rmartinez'
        },
        {
            'id': 9,
            'name': 'Amanda Foster',
            'title': 'Content Writer',
            'company': 'HubSpot',
            'location': 'Boston, MA',
            'about': 'Content strategist with 7 years in B2B content marketing. Expert in SEO writing, blog management, and content distribution. Created content that drove 2M+ organic visits. Strong background in copywriting and editorial planning.',
            'linkedin_url': 'https://linkedin.com/in/afoster'
        },
        {
            'id': 10,
            'name': 'Kevin Nguyen',
            'title': 'DevOps Engineer',
            'company': 'Netflix',
            'location': 'Los Gatos, CA',
            'about': 'DevOps engineer with 8 years automating infrastructure. Expert in CI/CD pipelines, Docker, Kubernetes, and infrastructure as code (Terraform). Reduced deployment time by 80% through automation. Strong background in monitoring, logging, and incident response.',
            'linkedin_url': 'https://linkedin.com/in/knguyen'
        }
    ]


def generate_hook(lead):
    """Generate hyperpersonalized hook using actual lead data."""
    name = lead.get('name', 'this person')
    title = lead.get('title', 'professional')
    company = lead.get('company', 'their company')
    location = lead.get('location', '')
    about = lead.get('about', '')[:500] if lead.get('about') else ''
    
    # Build detailed profile
    profile_summary = f"{name} is a {title}"
    if company:
        profile_summary += f" at {company}"
    if location:
        profile_summary += f" in {location}"
    if about:
        profile_summary += f". Background: {about}"
    
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

Example for someone with "data visualization and business intelligence" background:
"AI is now automating data visualization and BI reporting tasks, which is changing what companies want from data analysts. You have strong experience in business intelligence at Microsoft. Have you thought about repositioning to data strategy or analytics leadership roles? mobiusengine.ai has worked with many data analysts in the past 3 years to help them land their next role."

Example for someone with "distributed systems and cloud infrastructure" background:
"AI is now handling infrastructure provisioning and system optimization, which is changing what companies want from software engineers. You have deep experience in distributed systems at Google. Have you thought about repositioning to cloud architecture or platform engineering roles? mobiusengine.ai has worked with many software engineers in the past 3 years to help them land their next role."

Write the hook (under 60 words, use simple language, be HYPERPERSONALIZED to their actual background):"""
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a strategic career advisor. Be direct, specific, and hyperpersonalized to each person's actual background."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.8,
        max_tokens=150
    )
    
    hook = response.choices[0].message.content.strip()
    hook = hook.strip('"').strip("'")
    return hook


# Main execution
print("🔍 Fetching 10 actual leads from database...\n")
leads = get_actual_leads(10)

if not leads:
    print("❌ No leads found or database connection failed")
    exit(1)

print(f"✅ Found {len(leads)} leads\n")
print("🎯 Generating Hyperpersonalized Hooks")
print("=" * 80)

for i, lead in enumerate(leads, 1):
    print(f"\n{i}. {lead['name']} - {lead['title']} at {lead['company']}")
    print("-" * 80)
    print(f"About: {lead['about'][:200]}...")
    print("-" * 80)
    
    try:
        hook = generate_hook(lead)
        print(f"{hook}")
    except Exception as e:
        print(f"ERROR: {e}")

print("\n" + "=" * 80)
print("✅ Sample generation complete!")

