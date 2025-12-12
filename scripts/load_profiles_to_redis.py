#!/usr/bin/env python3
"""
Load KOL Profiles & Products to Redis
=======================================

This script loads crawled KOL profiles and products from JSON export files 
into Redis so that the Dashboard and API can fetch ACTUAL data for ML scoring.

Keys created in Redis:
    - kol:profile:{username} (hash) - individual profile data with ML scores
    - kol:profiles:list:tiktok (string/JSON) - list of all profiles
    - kol:products:{username} (string/JSON) - products per KOL
    - ranking:tiktok:trending (sorted set) - trending scores

Usage:
    python scripts/load_profiles_to_redis.py
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime
import math

try:
    import redis
except ImportError:
    print("ERROR: redis not installed. Run: pip install redis")
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None  # Will use fallback formula


# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
EXPORT_DIR = PROJECT_ROOT / "data" / "kafka_export"
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "16379"))
API_URL = os.environ.get("API_URL", "http://localhost:8000")
REDIS_TTL = 86400  # 24 hours


def parse_count(count_str: str) -> int:
    """Parse human-readable count string to integer.
    
    Examples:
        "1.3M" -> 1300000
        "751.8K" -> 751800
        "2684" -> 2684
    """
    if not count_str:
        return 0
    
    count_str = str(count_str).strip().upper()
    
    # Remove any non-numeric prefix/suffix except . K M B
    count_str = re.sub(r'[^\d.KMB]', '', count_str)
    
    try:
        if 'M' in count_str:
            return int(float(count_str.replace('M', '')) * 1_000_000)
        elif 'K' in count_str:
            return int(float(count_str.replace('K', '')) * 1_000)
        elif 'B' in count_str:
            return int(float(count_str.replace('B', '')) * 1_000_000_000)
        else:
            return int(float(count_str))
    except (ValueError, TypeError):
        return 0


def estimate_account_age_days(profile: dict) -> int:
    """Estimate account age based on activity patterns.
    
    This is a rough estimate based on:
    - Number of posts
    - Engagement patterns
    - Follower count
    
    In production, this would come from actual account creation date.
    """
    followers = parse_count(profile.get('followers_raw', '0'))
    posts = parse_count(profile.get('post_count', '0')) or 100  # Default estimate
    
    # Estimate based on typical growth patterns
    # Larger accounts typically take longer to build
    if followers > 1_000_000:
        return 1095  # ~3 years
    elif followers > 500_000:
        return 730  # ~2 years
    elif followers > 100_000:
        return 547  # ~1.5 years
    elif followers > 50_000:
        return 365  # ~1 year
    elif followers > 10_000:
        return 270  # ~9 months
    else:
        return 180  # ~6 months


def transform_profile(raw_profile: dict) -> dict:
    """Transform raw crawled profile to standardized format for ML."""
    username = raw_profile.get('username', '')
    
    # Parse counts
    followers_count = parse_count(raw_profile.get('followers_raw', '0'))
    following_count = parse_count(raw_profile.get('following_raw', '0'))
    likes_count = parse_count(raw_profile.get('likes_raw', '0'))
    
    # Estimate posts (TikTok API doesn't always return this)
    # Using likes/engagement ratio as proxy
    post_count = raw_profile.get('post_count')
    if not post_count:
        # Estimate: avg 500 likes per post for active KOLs
        post_count = max(10, likes_count // 500) if likes_count > 0 else 50
    else:
        post_count = parse_count(post_count)
    
    # Bio analysis
    bio = raw_profile.get('bio', '')
    has_bio = bool(bio and bio.strip() and bio.strip().lower() != 'no bio yet.')
    has_url = bool(bio and ('http' in bio.lower() or '@' in bio or '.com' in bio.lower()))
    bio_length = len(bio) if bio else 0
    
    return {
        'kol_id': username,
        'username': username,
        'platform': raw_profile.get('platform', 'tiktok'),
        'nickname': raw_profile.get('nickname', username),
        'followers_count': followers_count,
        'following_count': following_count,
        'post_count': post_count,
        'favorites_count': likes_count,
        'verified': raw_profile.get('verified', False),
        'account_age_days': estimate_account_age_days(raw_profile),
        'has_bio': has_bio,
        'has_url': has_url,
        'has_profile_image': True,  # Assume true (hard to verify from data)
        'bio_length': bio_length,
        'bio': bio,
        'profile_url': raw_profile.get('profile_url', ''),
        'avatar_url': raw_profile.get('avatar_url', ''),
        'loaded_at': datetime.utcnow().isoformat(),
    }


def load_products_data() -> dict:
    """Load and aggregate product data per KOL for Success Score calculation."""
    products_files = list(EXPORT_DIR.glob("kol_products_raw*.json"))
    if not products_files:
        print("   ⚠️ No product files found, skipping success score ML")
        return {}
    
    products_file = sorted(products_files)[-1]
    print(f"\n📦 Loading products from: {products_file.name}")
    
    with open(products_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    
    # Aggregate products by KOL
    kol_products = {}
    for record in raw_data:
        data = record.get('data', record)
        username = data.get('username', '')
        if not username:
            continue
        
        if username not in kol_products:
            kol_products[username] = []
        
        kol_products[username].append({
            'video_views': data.get('video_views') or 0,
            'video_likes': data.get('video_likes') or 0,
            'video_comments': data.get('video_comments') or 0,
            'video_shares': data.get('video_shares') or 0,
            'engagement_total': (data.get('video_likes') or 0) + (data.get('video_comments') or 0) + (data.get('video_shares') or 0),
            'price': data.get('price') or 0,
            'sold_count': data.get('sold_count') or 0,
            'product_title': data.get('product_title', ''),
        })
    
    print(f"   Found {len(kol_products)} KOLs with product data")
    return kol_products


def calculate_success_score_ml(products: list, profile: dict = None) -> tuple:
    """
    Calculate Success Score for a KOL using ML model inference via API.
    
    Returns: (score, method) where method is 'ml_api', 'sales_based', or 'profile_based'
    """
    if not products:
        # No product data - estimate from profile engagement
        # This is less accurate but provides variance
        if profile:
            followers = profile.get('followers_count', 0)
            likes = profile.get('favorites_count', 0)
            posts = profile.get('post_count', 0)
            
            # Engagement-based estimation (proxy for success potential)
            engagement_ratio = likes / max(followers, 1)
            avg_engagement_per_post = likes / max(posts, 1)
            
            # Score based on engagement metrics
            # High engagement indicates content resonance → better sales potential
            if engagement_ratio >= 50:  # 50x likes per follower (very high)
                score = 70 + min(20, (engagement_ratio - 50) / 5)
            elif engagement_ratio >= 20:  # 20-50x
                score = 55 + (engagement_ratio - 20) / 2
            elif engagement_ratio >= 10:  # 10-20x
                score = 40 + (engagement_ratio - 10) * 1.5
            elif engagement_ratio >= 1:   # 1-10x
                score = 25 + (engagement_ratio - 1) * 1.67
            else:                          # < 1x
                score = 15 + engagement_ratio * 10
            
            # Follower tier bonus (larger KOLs may have better brand deals)
            if followers >= 1_000_000:
                score += 5
            elif followers >= 500_000:
                score += 3
            elif followers >= 100_000:
                score += 1
            
            return min(100, max(10, score)), 'profile_based'
        
        return 30, 'no_data'  # Default score when no data available
    
    # Aggregate metrics across all products
    total_views = sum(p['video_views'] for p in products)
    total_likes = sum(p['video_likes'] for p in products)
    total_comments = sum(p['video_comments'] for p in products)
    total_shares = sum(p['video_shares'] for p in products)
    total_sold = sum(p['sold_count'] for p in products)
    num_products = len(products)
    
    # Average metrics per product
    avg_views = total_views / num_products
    avg_likes = total_likes / num_products
    avg_comments = total_comments / num_products
    avg_shares = total_shares / num_products
    avg_engagement = (avg_likes + avg_comments + avg_shares)
    avg_price = sum(p['price'] for p in products) / num_products
    
    # Calculate engagement rate
    engagement_rate = avg_engagement / max(avg_views, 1)
    est_ctr = min(0.1, avg_engagement / max(avg_views, 1) * 2)
    est_clicks = avg_views * est_ctr
    
    # Try ML API first
    if requests:
        try:
            response = requests.post(
                f"{API_URL}/predict/success",
                json={
                    "kol_id": "aggregated",
                    "video_views": avg_views,
                    "video_likes": avg_likes,
                    "video_comments": avg_comments,
                    "video_shares": avg_shares,
                    "engagement_total": avg_engagement,
                    "engagement_rate": engagement_rate,
                    "est_clicks": est_clicks,
                    "est_ctr": est_ctr,
                    "price": avg_price,
                },
                timeout=2
            )
            if response.status_code == 200:
                return response.json().get('success_score', 50), 'ml_api'
        except Exception:
            pass  # Fallback to formula
    
    # Fallback: Calculate success score based on sales performance
    # This uses the actual sold_count which is the ground truth
    avg_sold = total_sold / num_products
    
    # Sales-based scoring (mimicking ML model output):
    # Top 25% sold = High (score 60-100)
    # Rest = Not-High (score 0-60)
    # Based on ML report: P75 threshold ≈ 200 sold_count
    
    if avg_sold >= 5000:
        score = 90 + min(10, (avg_sold - 5000) / 1000)
    elif avg_sold >= 1000:
        score = 75 + (avg_sold - 1000) / 267  # 1000-5000 → 75-90
    elif avg_sold >= 200:
        score = 60 + (avg_sold - 200) / 53    # 200-1000 → 60-75
    elif avg_sold >= 50:
        score = 40 + (avg_sold - 50) / 7.5    # 50-200 → 40-60
    elif avg_sold >= 10:
        score = 25 + (avg_sold - 10) / 2.67   # 10-50 → 25-40
    else:
        score = max(10, avg_sold * 2.5)       # 0-10 → 10-25
    
    return min(100, max(0, score)), 'sales_based'


def main():
    print("=" * 60)
    print("  KOL PROFILES & PRODUCTS → REDIS LOADER")
    print("=" * 60)
    
    # Connect to Redis
    print(f"\n📡 Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
    try:
        r = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True,
            socket_timeout=5.0
        )
        r.ping()
        print("✅ Redis connected!")
    except redis.ConnectionError as e:
        print(f"❌ Redis connection failed: {e}")
        sys.exit(1)
    
    # Find profiles JSON file
    profiles_files = list(EXPORT_DIR.glob("kol_profiles_raw*.json"))
    if not profiles_files:
        print(f"❌ No profiles files found in {EXPORT_DIR}")
        sys.exit(1)
    
    # Use most recent file
    profiles_file = sorted(profiles_files)[-1]
    print(f"\n📂 Loading profiles from: {profiles_file.name}")
    
    # Load and parse
    with open(profiles_file, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)
    
    print(f"   Found {len(raw_data)} raw records")
    
    # Process and deduplicate (keep latest for each username)
    profiles_by_username = {}
    for record in raw_data:
        data = record.get('data', record)
        username = data.get('username')
        if username:
            profiles_by_username[username] = data
    
    print(f"   Unique KOLs: {len(profiles_by_username)}")
    
    # Load products data for Success Score calculation
    kol_products = load_products_data()
    
    # Transform and load to Redis
    print("\n🔄 Loading profiles to Redis...")
    
    pipe = r.pipeline()
    all_profiles = []
    success_scores_info = {'ml_api': 0, 'sales_based': 0, 'profile_based': 0, 'no_data': 0}
    
    for username, raw_profile in profiles_by_username.items():
        profile = transform_profile(raw_profile)
        
        # Calculate Success Score using products data (or profile-based fallback)
        products = kol_products.get(username, [])
        success_score, method = calculate_success_score_ml(products, profile)
        profile['success_score'] = round(success_score, 1)
        profile['success_score_method'] = method
        profile['product_count'] = len(products)
        
        if products:
            profile['total_sold'] = sum(p['sold_count'] for p in products)
            profile['avg_video_views'] = sum(p['video_views'] for p in products) / len(products)
        else:
            profile['total_sold'] = 0
            profile['avg_video_views'] = 0
        
        success_scores_info[method] = success_scores_info.get(method, 0) + 1
        
        all_profiles.append(profile)
        
        # Store individual profile as hash
        key = f"kol:profile:{username}"
        pipe.hset(key, mapping={k: str(v) for k, v in profile.items()})
        pipe.expire(key, REDIS_TTL)
        
        # Store products data if available
        if products:
            pipe.set(f"kol:products:{username}", json.dumps(products), ex=REDIS_TTL)
    
    # Store list of all profiles as JSON
    pipe.set(
        "kol:profiles:list:tiktok",
        json.dumps(all_profiles),
        ex=REDIS_TTL
    )
    
    # Store in trending ranking with actual engagement-based scores (for diversity)
    # This gives each KOL a different initial score based on their metrics
    import math
    
    for profile in all_profiles:
        username = profile['username']
        followers = profile['followers_count']
        likes = profile['favorites_count']
        posts = profile['post_count']
        
        # Calculate trending score using multiple factors:
        # 1. Engagement ratio (likes per follower) - normalized
        # 2. Follower tier bonus
        # 3. Activity (posts) factor
        # 4. Add randomness based on username hash for variety
        
        engagement_ratio = likes / max(followers, 1)
        
        # Base score from engagement (0-50 range)
        # Log scale to handle wide range of ratios (1 to 1000+)
        engagement_score = min(50, max(0, 15 + math.log10(engagement_ratio + 1) * 15))
        
        # Follower tier bonus (0-25 range)
        if followers >= 1_000_000:
            tier_bonus = 25  # Mega
        elif followers >= 500_000:
            tier_bonus = 20  # Macro
        elif followers >= 100_000:
            tier_bonus = 15  # Mid
        elif followers >= 10_000:
            tier_bonus = 10  # Micro
        else:
            tier_bonus = 5   # Nano
        
        # Activity score (0-15 range)
        activity_score = min(15, posts / 20)
        
        # Add deterministic variety based on username (0-10 range)
        username_hash = sum(ord(c) for c in username) % 100 / 10
        
        # Final trending score
        initial_score = min(100, max(5, engagement_score + tier_bonus + activity_score + username_hash))
        
        pipe.zadd("ranking:tiktok:trending", {username: round(initial_score, 2)})
        pipe.zadd("trending:ranking:tiktok", {username: round(initial_score, 2)})
    
    pipe.execute()
    
    print(f"\n✅ Loaded {len(all_profiles)} profiles to Redis!")
    
    # Success Score summary
    print(f"\n📈 Success Score calculation methods:")
    for method, count in success_scores_info.items():
        if count > 0:
            print(f"   - {method}: {count} KOLs")
    
    print("\n📊 Sample profiles loaded:")
    print("-" * 80)
    
    for profile in sorted(all_profiles, key=lambda x: x['followers_count'], reverse=True)[:10]:
        success = profile.get('success_score', 0)
        method = profile.get('success_score_method', 'N/A')[:5]
        print(f"  @{profile['username']:<25} "
              f"Followers: {profile['followers_count']:>10,} "
              f"Success: {success:>5.1f} ({method})")
    
    print("-" * 80)
    print(f"\n🔑 Redis keys created:")
    print(f"   - kol:profile:{{username}} (hash) × {len(all_profiles)}")
    print(f"   - kol:profiles:list:tiktok (JSON list)")
    print(f"   - kol:products:{{username}} (JSON) × {sum(1 for k in kol_products if k in profiles_by_username)}")
    print(f"   - ranking:tiktok:trending (sorted set)")
    print(f"   - TTL: {REDIS_TTL // 3600} hours")
    
    # Verify
    print("\n🔍 Verification:")
    sample_key = f"kol:profile:{all_profiles[0]['username']}"
    sample_data = r.hgetall(sample_key)
    print(f"   Sample key: {sample_key}")
    print(f"   followers_count: {sample_data.get('followers_count')}")
    print(f"   success_score: {sample_data.get('success_score')} (method: {sample_data.get('success_score_method')})")
    
    # Show Success Score distribution
    print("\n   Success Score distribution:")
    scores = [p.get('success_score', 0) for p in all_profiles]
    score_ranges = [(0, 25), (25, 50), (50, 75), (75, 100)]
    for low, high in score_ranges:
        count = sum(1 for s in scores if low <= s < high)
        print(f"      {low:>2}-{high:<3}: {count} KOLs {'█' * min(30, count)}")
    
    ranking = r.zrevrange("ranking:tiktok:trending", 0, 4, withscores=True)
    print(f"\n   Top 5 by score:")
    for kol_id, score in ranking:
        print(f"      {kol_id}: {score:.2f}")
    
    print("\n" + "=" * 60)
    print("  DONE! Profiles are now available in Redis.")
    print("  Dashboard can now fetch REAL profile data for ML scoring.")
    print("=" * 60)


if __name__ == "__main__":
    main()
