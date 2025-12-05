"""
ATTRIBUTION MODEL: Distribute product sales across multiple KOLs
================================================================

Problem: 
- Product X has sold_delta = 1000 units/day
- Multiple KOLs promote same product
- How to attribute sales to each KOL?

Solution: Multi-touch Attribution Models
1. Proportional: by engagement share
2. Time-Decay: recent videos weighted more
3. Position-Based: first/last touch bonus

Output: Estimated sales per KOL for LightGBM training
"""
import math
from datetime import datetime, timedelta
from typing import List, Dict


def proportional_attribution(
    sold_delta: int,
    kol_videos: List[Dict],
    organic_share: float = 0.15,  # 15% sales are organic (not from KOLs)
) -> List[Dict]:
    """
    Simple proportional attribution based on engagement
    
    Args:
        sold_delta: Total product sales change
        kol_videos: List of {kol_id, video_id, views, likes, comments, shares}
        organic_share: Portion of sales not attributed to any KOL
    
    Returns:
        List of {kol_id, video_id, attributed_sales, attribution_pct}
    """
    # Calculate engagement for each video
    for video in kol_videos:
        video['engagement'] = (
            video.get('likes', 0) + 
            video.get('comments', 0) * 2 +  # Comments weighted 2x
            video.get('shares', 0) * 3      # Shares weighted 3x (high intent)
        )
        video['weighted_reach'] = video['views'] * (video['engagement'] / max(video['views'], 1))
    
    total_weighted = sum(v['weighted_reach'] for v in kol_videos)
    
    if total_weighted == 0:
        return kol_videos
    
    # Attributable sales (excluding organic)
    attributable_sales = sold_delta * (1 - organic_share)
    
    # Distribute
    results = []
    for video in kol_videos:
        pct = video['weighted_reach'] / total_weighted
        attributed = int(attributable_sales * pct)
        
        results.append({
            'kol_id': video['kol_id'],
            'video_id': video['video_id'],
            'views': video['views'],
            'engagement': video['engagement'],
            'attribution_pct': round(pct * 100, 2),
            'attributed_sales': attributed,
        })
    
    return sorted(results, key=lambda x: x['attributed_sales'], reverse=True)


def time_decay_attribution(
    sold_delta: int,
    kol_videos: List[Dict],
    decay_half_life_hours: float = 48,  # 50% decay after 48 hours
    organic_share: float = 0.15,
) -> List[Dict]:
    """
    Time-decay attribution: recent videos get more credit
    
    Args:
        sold_delta: Total product sales change
        kol_videos: List with 'posted_at' datetime field
        decay_half_life_hours: Hours until weight drops to 50%
    """
    now = datetime.utcnow()
    lambda_decay = math.log(2) / decay_half_life_hours
    
    for video in kol_videos:
        # Calculate hours since posted
        posted_at = video.get('posted_at', now)
        if isinstance(posted_at, str):
            posted_at = datetime.fromisoformat(posted_at.replace('Z', ''))
        
        hours_ago = (now - posted_at).total_seconds() / 3600
        
        # Decay weight
        decay_weight = math.exp(-lambda_decay * hours_ago)
        
        # Engagement
        engagement = (
            video.get('likes', 0) + 
            video.get('comments', 0) * 2 + 
            video.get('shares', 0) * 3
        )
        
        video['decay_weight'] = decay_weight
        video['weighted_score'] = engagement * decay_weight
    
    total_weighted = sum(v['weighted_score'] for v in kol_videos)
    
    if total_weighted == 0:
        return kol_videos
    
    attributable_sales = sold_delta * (1 - organic_share)
    
    results = []
    for video in kol_videos:
        pct = video['weighted_score'] / total_weighted
        attributed = int(attributable_sales * pct)
        
        results.append({
            'kol_id': video['kol_id'],
            'video_id': video['video_id'],
            'views': video['views'],
            'decay_weight': round(video['decay_weight'], 3),
            'attribution_pct': round(pct * 100, 2),
            'attributed_sales': attributed,
        })
    
    return sorted(results, key=lambda x: x['attributed_sales'], reverse=True)


def position_based_attribution(
    sold_delta: int,
    kol_videos: List[Dict],
    first_touch_weight: float = 0.3,  # 30% to first video
    last_touch_weight: float = 0.3,   # 30% to most recent
    organic_share: float = 0.15,
) -> List[Dict]:
    """
    Position-based: First and last touch get bonus
    
    - First video (awareness) gets 30%
    - Last video (conversion) gets 30%
    - Middle videos share remaining 40%
    """
    if not kol_videos:
        return []
    
    # Sort by posted time
    sorted_videos = sorted(kol_videos, key=lambda x: x.get('posted_at', ''))
    
    attributable_sales = sold_delta * (1 - organic_share)
    
    n = len(sorted_videos)
    middle_weight = (1 - first_touch_weight - last_touch_weight) / max(n - 2, 1)
    
    results = []
    for i, video in enumerate(sorted_videos):
        if i == 0:
            weight = first_touch_weight
            position = 'first_touch'
        elif i == n - 1:
            weight = last_touch_weight
            position = 'last_touch'
        else:
            weight = middle_weight
            position = 'middle'
        
        attributed = int(attributable_sales * weight)
        
        results.append({
            'kol_id': video['kol_id'],
            'video_id': video['video_id'],
            'position': position,
            'attribution_pct': round(weight * 100, 2),
            'attributed_sales': attributed,
        })
    
    return results


def aggregate_kol_attribution(attributions: List[Dict]) -> Dict:
    """
    Aggregate video-level attributions to KOL-level
    
    Returns: {kol_id: total_attributed_sales}
    """
    kol_totals = {}
    
    for attr in attributions:
        kol_id = attr['kol_id']
        if kol_id not in kol_totals:
            kol_totals[kol_id] = {
                'kol_id': kol_id,
                'total_attributed_sales': 0,
                'total_videos': 0,
                'total_views': 0,
            }
        
        kol_totals[kol_id]['total_attributed_sales'] += attr['attributed_sales']
        kol_totals[kol_id]['total_videos'] += 1
        kol_totals[kol_id]['total_views'] += attr.get('views', 0)
    
    return kol_totals


# ============================================================
# DEMO
# ============================================================

if __name__ == "__main__":
    print("="*80)
    print("📊 MULTI-KOL ATTRIBUTION MODEL")
    print("="*80)
    
    # Example: Product X có 3 KOLs promote
    sold_delta = 1000  # 1000 units sold today
    
    kol_videos = [
        {
            'kol_id': 'kol_001',
            'video_id': 'vid_a',
            'views': 500_000,
            'likes': 25_000,
            'comments': 1_000,
            'shares': 500,
            'posted_at': datetime.utcnow() - timedelta(hours=6),
        },
        {
            'kol_id': 'kol_002', 
            'video_id': 'vid_b',
            'views': 300_000,
            'likes': 12_000,
            'comments': 500,
            'shares': 200,
            'posted_at': datetime.utcnow() - timedelta(hours=24),
        },
        {
            'kol_id': 'kol_003',
            'video_id': 'vid_c',
            'views': 200_000,
            'likes': 6_000,
            'comments': 300,
            'shares': 100,
            'posted_at': datetime.utcnow() - timedelta(hours=72),
        },
        {
            'kol_id': 'kol_001',  # Same KOL, another video
            'video_id': 'vid_d',
            'views': 100_000,
            'likes': 5_000,
            'comments': 200,
            'shares': 50,
            'posted_at': datetime.utcnow() - timedelta(hours=2),
        },
    ]
    
    print(f"\n📦 Product sold_delta: {sold_delta:,} units")
    print(f"👥 KOLs promoting: {len(set(v['kol_id'] for v in kol_videos))}")
    print(f"🎬 Total videos: {len(kol_videos)}")
    
    # 1. Proportional Attribution
    print("\n" + "-"*40)
    print("1️⃣ PROPORTIONAL ATTRIBUTION")
    print("-"*40)
    
    results = proportional_attribution(sold_delta, kol_videos)
    for r in results:
        print(f"   {r['kol_id']} | {r['video_id']} | {r['views']:,} views | {r['attribution_pct']}% → {r['attributed_sales']} sales")
    
    # 2. Time-Decay Attribution
    print("\n" + "-"*40)
    print("2️⃣ TIME-DECAY ATTRIBUTION (48h half-life)")
    print("-"*40)
    
    results = time_decay_attribution(sold_delta, kol_videos)
    for r in results:
        print(f"   {r['kol_id']} | {r['video_id']} | decay={r['decay_weight']} | {r['attribution_pct']}% → {r['attributed_sales']} sales")
    
    # 3. Aggregate by KOL
    print("\n" + "-"*40)
    print("📊 AGGREGATED BY KOL (Time-Decay)")
    print("-"*40)
    
    kol_totals = aggregate_kol_attribution(results)
    for kol_id, data in sorted(kol_totals.items(), key=lambda x: x[1]['total_attributed_sales'], reverse=True):
        print(f"   {kol_id}: {data['total_attributed_sales']} sales ({data['total_videos']} videos, {data['total_views']:,} views)")
    
    print("\n" + "="*80)
    print("💡 USE FOR LIGHTGBM TRAINING:")
    print("   target = attributed_sales (not raw sold_delta)")
    print("   This creates KOL-specific success metrics!")
    print("="*80)
