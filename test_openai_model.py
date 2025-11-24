#!/usr/bin/env python3
"""Test if gpt-4.1-mini model exists."""

import os
from openai import OpenAI

api_key = os.environ.get('OPENAI_API_KEY')
if not api_key:
    print("ERROR: OPENAI_API_KEY not set")
    exit(1)

client = OpenAI(api_key=api_key)

print("Testing gpt-4.1-mini model...")
print()

try:
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "user", "content": "Say 'test successful'"}
        ],
        max_tokens=10
    )
    print("✅ SUCCESS! Model gpt-4.1-mini works!")
    print(f"Response: {response.choices[0].message.content}")
except Exception as e:
    print(f"❌ ERROR: {e}")
    print()
    print("Trying gpt-4o-mini instead...")
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "Say 'test successful'"}
            ],
            max_tokens=10
        )
        print("✅ gpt-4o-mini works!")
        print(f"Response: {response.choices[0].message.content}")
    except Exception as e2:
        print(f"❌ gpt-4o-mini also failed: {e2}")

