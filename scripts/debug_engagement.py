#!/usr/bin/env python3
"""Debug script to analyze engagement ratio issues."""
import json

# Check raw profile data
with open('data/kafka_export/kol_profiles_raw_20251202_195259.json', 'r', encoding='utf-8') as f:
    profiles = json.load(f)

print('='*70)
print('RAW PROFILE DATA ANALYSIS')
print('='*70)

for record in profiles[:8]:
    data = record.get('data', record)
    print(f"Username: {data.get('username')}")
    print(f"  followers_raw: {data.get('followers_raw')}")
    print(f"  following_raw: {data.get('following_raw')}")
    print(f"  likes_raw: {data.get('likes_raw')}")  
    print(f"  post_count: {data.get('post_count')}")
    print()

print('='*70)
print('ENGAGEMENT RATIO INTERPRETATION')
print('='*70)
print("""
On TikTok:
- 'favorites_count' or 'likes_raw' = TOTAL LIKES received across ALL videos
- This is NOT engagement per post!

CORRECT Engagement Rate formula options:

Option A: Likes-to-Followers Ratio (simple)
  = Total Likes / Followers
  → Shows how many likes per follower overall
  → Values like 39x (3900%) are NORMAL for viral creators

Option B: Average Engagement per Post
  = (Total Likes / Number of Posts) / Followers × 100
  → Shows avg likes per post relative to followers
  → Values typically 0.1% - 10%

The current "3872%" is actually CORRECT interpretation:
→ It means the KOL has received 39x more likes than their follower count
→ This is a measure of VIRALITY, not traditional engagement rate

RECOMMENDATION: Either rename to "Likes/Followers Ratio" or use Option B
""")
