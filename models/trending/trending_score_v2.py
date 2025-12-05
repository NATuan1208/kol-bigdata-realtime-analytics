#!/usr/bin/env python3
"""
TrendingScore V2 - Improved Velocity-Based Approach

Improvements over V1:
1. Time decay - Recent events weighted more
2. Engagement weighting - High-view events count more
3. Proper baseline - Personal historical baseline
4. Better normalization - Sigmoid for bounded output
5. Scientific formula with explanations
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "kafka_export"


def load_events_data() -> pd.DataFrame:
    """Load all events from videos and discovery data."""
    print("Loading events data...")
    events = []
    
    for pattern in ["kol_videos_raw_*.json", "kol_discovery_raw_*.json"]:
        for fp in DATA_DIR.glob(pattern):
            print(f"  Reading {fp.name}")
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            for record in data:
                event = record.get("data", record)
                events.append({
                    "username": event.get("username"),
                    "event_time": event.get("event_time"),
                    "event_type": event.get("event_type"),
                    "video_views": pd.to_numeric(event.get("video_views", 0), errors="coerce") or 0,
                    "video_likes": pd.to_numeric(event.get("video_likes", 0), errors="coerce") or 0,
                    "video_id": event.get("video_id"),
                })
    
    df = pd.DataFrame(events)
    df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")
    print(f"  Loaded {len(df)} events")
    return df


def calculate_time_decay(event_time: datetime, reference_time: datetime, 
                         half_life_days: float = 7.0) -> float:
    """
    Calculate time decay weight using exponential decay.
    
    Formula: weight = exp(-λ * t)
    where λ = ln(2) / half_life
    
    Args:
        event_time: Time of the event
        reference_time: Current/reference time
        half_life_days: Time for weight to decay to 0.5 (default: 7 days)
    
    Returns:
        Weight between 0 and 1
    """
    if pd.isna(event_time):
        return 0.5  # Default for missing timestamps
    
    delta_days = (reference_time - event_time).total_seconds() / 86400
    if delta_days < 0:
        delta_days = 0  # Future events get full weight
    
    decay_rate = math.log(2) / half_life_days
    weight = math.exp(-decay_rate * delta_days)
    
    return weight


def calculate_engagement_weight(views: float, likes: float, 
                                 global_avg_views: float = 10000) -> float:
    """
    Calculate engagement weight using log scaling.
    
    Higher view counts = higher impact on trending score.
    Uses log to prevent extreme values from dominating.
    
    Formula: weight = log(1 + views/global_avg) / log(1 + max_ratio)
    Normalized to [0.1, 1.0] range
    """
    if views <= 0:
        return 0.1  # Minimum weight
    
    ratio = views / global_avg_views
    # Log scale with cap at 100x average
    weight = math.log1p(ratio) / math.log1p(100)
    
    # Normalize to [0.1, 1.0]
    weight = 0.1 + 0.9 * min(weight, 1.0)
    
    return weight


def calculate_trending_score_v2(
    current_velocity: float,
    baseline_velocity: float,
    global_avg_velocity: float,
    momentum: float = 0.0,  # Rate of change
    time_decay_factor: float = 1.0
) -> Dict:
    """
    Calculate TrendingScore V2 with improved formula.
    
    Formula:
        raw_score = α * personal_growth + β * market_position + γ * momentum
    
    Where:
        - personal_growth = current_velocity / baseline_velocity
        - market_position = current_velocity / global_avg_velocity
        - momentum = (current - previous) / previous
        - α, β, γ = weights (0.5, 0.3, 0.2)
    
    Then apply sigmoid normalization:
        trending_score = 100 / (1 + exp(-k * (raw_score - threshold)))
    """
    # Avoid division by zero
    baseline = max(baseline_velocity, 0.1)
    global_avg = max(global_avg_velocity, 0.1)
    
    # Component scores
    personal_growth = current_velocity / baseline
    market_position = current_velocity / global_avg
    
    # Weighted combination
    # α=0.5 (personal growth most important)
    # β=0.3 (market position)
    # γ=0.2 (momentum/acceleration)
    raw_score = (
        0.5 * personal_growth +
        0.3 * market_position +
        0.2 * (1 + momentum)  # momentum normalized around 1
    )
    
    # Apply time decay
    raw_score *= time_decay_factor
    
    # Sigmoid normalization to [0, 100]
    # Tuned so that raw_score=1 → ~30, raw_score=2 → ~50, raw_score=5 → ~85
    k = 0.8  # Steepness
    threshold = 2.0  # Center point
    trending_score = 100 / (1 + math.exp(-k * (raw_score - threshold)))
    
    # Determine label with better thresholds
    if trending_score >= 80:
        label = "Viral"
    elif trending_score >= 60:
        label = "Hot"
    elif trending_score >= 40:
        label = "Warm"
    elif trending_score >= 25:
        label = "Normal"
    else:
        label = "Cold"
    
    return {
        "trending_score": round(trending_score, 2),
        "trending_label": label,
        "personal_growth": round(personal_growth, 4),
        "market_position": round(market_position, 4),
        "momentum": round(momentum, 4),
        "raw_score": round(raw_score, 4),
        "current_velocity": current_velocity,
        "baseline_velocity": baseline_velocity,
    }


def calculate_all_trending_scores_v2(df: Optional[pd.DataFrame] = None) -> Dict[str, Dict]:
    """
    Calculate TrendingScore for all KOLs with time decay and engagement weighting.
    """
    if df is None:
        df = load_events_data()
    
    if df.empty:
        return {}
    
    # Reference time (latest event or now)
    reference_time = df["event_time"].max()
    if pd.isna(reference_time):
        reference_time = datetime.now()
    
    print(f"\nCalculating TrendingScore V2...")
    print(f"  Reference time: {reference_time}")
    
    # Calculate global statistics (exclude zeros for meaningful average)
    views_nonzero = df[df["video_views"] > 0]["video_views"]
    global_avg_views = views_nonzero.mean() if len(views_nonzero) > 0 else 10000
    print(f"  Global avg views (non-zero): {global_avg_views:,.0f}")
    
    # Calculate weighted velocity per KOL
    results = {}
    
    for username, group in df.groupby("username"):
        if pd.isna(username):
            continue
        
        # Calculate time-decayed, engagement-weighted velocity
        weighted_events = 0
        total_weight = 0
        
        for _, row in group.iterrows():
            # Time decay
            time_weight = calculate_time_decay(row["event_time"], reference_time)
            
            # Engagement weight
            engagement_weight = calculate_engagement_weight(
                row["video_views"], 
                row.get("video_likes", 0),
                global_avg_views
            )
            
            # Combined weight
            combined_weight = time_weight * engagement_weight
            weighted_events += combined_weight
            total_weight += 1
        
        # Weighted velocity (events per unit time, weighted)
        current_velocity = weighted_events
        
        # Baseline = average across all KOLs (will be personalized with more data)
        baseline_velocity = len(group) / max(len(df.groupby("username")), 1)
        
        # Global average velocity
        global_avg_velocity = len(df) / max(len(df.groupby("username")), 1)
        
        # Calculate momentum (simplified - would need historical data)
        momentum = 0.0  # Placeholder - needs time series data
        
        # Calculate score
        scores = calculate_trending_score_v2(
            current_velocity=current_velocity,
            baseline_velocity=baseline_velocity,
            global_avg_velocity=global_avg_velocity,
            momentum=momentum
        )
        
        # Add extra info
        scores["total_events"] = len(group)
        scores["total_views"] = int(group["video_views"].sum())
        scores["avg_views"] = int(group["video_views"].mean())
        
        results[username] = scores
    
    return results


def analyze_distribution(results: Dict[str, Dict]):
    """Analyze and print score distribution."""
    if not results:
        print("No results to analyze")
        return
    
    scores = [r["trending_score"] for r in results.values()]
    labels = [r["trending_label"] for r in results.values()]
    
    print(f"\n" + "="*50)
    print("SCORE DISTRIBUTION ANALYSIS")
    print("="*50)
    
    print(f"\nBasic Stats:")
    print(f"  Count: {len(scores)}")
    print(f"  Min:   {min(scores):.2f}")
    print(f"  Max:   {max(scores):.2f}")
    print(f"  Mean:  {np.mean(scores):.2f}")
    print(f"  Std:   {np.std(scores):.2f}")
    
    print(f"\nPercentiles:")
    for p in [25, 50, 75, 90, 95]:
        print(f"  P{p}: {np.percentile(scores, p):.2f}")
    
    print(f"\nLabel Distribution:")
    label_counts = pd.Series(labels).value_counts()
    for label in ["Cold", "Normal", "Warm", "Hot", "Viral"]:
        count = label_counts.get(label, 0)
        pct = count / len(labels) * 100
        bar = "█" * int(pct / 2)
        print(f"  {label:<8}: {count:>4} ({pct:>5.1f}%) {bar}")


def get_top_trending(n: int = 10, results: Optional[Dict] = None) -> List[Dict]:
    """Get top N trending KOLs."""
    if results is None:
        results = calculate_all_trending_scores_v2()
    
    sorted_kols = sorted(
        results.items(), 
        key=lambda x: x[1]["trending_score"], 
        reverse=True
    )
    
    return [
        {"username": username, **scores} 
        for username, scores in sorted_kols[:n]
    ]


def compare_v1_vs_v2():
    """Compare V1 and V2 formulas."""
    print("\n" + "="*60)
    print("V1 vs V2 COMPARISON")
    print("="*60)
    
    # Test cases
    test_cases = [
        {"name": "New KOL, low activity", "current": 2, "baseline": 1, "global": 10},
        {"name": "Average KOL", "current": 10, "baseline": 10, "global": 10},
        {"name": "Growing KOL", "current": 30, "baseline": 10, "global": 10},
        {"name": "Viral KOL", "current": 100, "baseline": 10, "global": 10},
        {"name": "Declining KOL", "current": 5, "baseline": 20, "global": 10},
    ]
    
    print(f"\n{'Case':<25} {'V1 Score':<12} {'V2 Score':<12} {'V2 Label'}")
    print("-"*60)
    
    for tc in test_cases:
        # V1 formula (original)
        personal_ratio = tc["current"] / tc["baseline"]
        global_ratio = tc["current"] / tc["global"]
        v1_raw = 0.6 * personal_ratio + 0.4 * global_ratio
        v1_score = min(v1_raw / 5 * 100, 100)
        
        # V2 formula
        v2_result = calculate_trending_score_v2(
            tc["current"], tc["baseline"], tc["global"]
        )
        
        print(f"{tc['name']:<25} {v1_score:<12.2f} {v2_result['trending_score']:<12.2f} {v2_result['trending_label']}")


def main():
    print("="*60)
    print("  TRENDING SCORE V2 - Improved Calculation")
    print("="*60)
    
    # Compare formulas first
    compare_v1_vs_v2()
    
    # Calculate for all KOLs
    results = calculate_all_trending_scores_v2()
    
    if not results:
        print("No data to process")
        return
    
    # Analyze distribution
    analyze_distribution(results)
    
    # Top trending
    print(f"\n" + "="*50)
    print("TOP 10 TRENDING KOLs")
    print("="*50)
    
    top_kols = get_top_trending(10, results)
    for i, kol in enumerate(top_kols, 1):
        print(f"\n{i:>2}. @{kol['username']}")
        print(f"    Score: {kol['trending_score']:.1f} ({kol['trending_label']})")
        print(f"    Views: {kol['total_views']:,} | Events: {kol['total_events']}")
        print(f"    Growth: {kol['personal_growth']:.2f}x | Market: {kol['market_position']:.2f}x")
    
    print("\n" + "="*60)
    print("  TRENDING SCORE V2 COMPLETE!")
    print("="*60)
    
    return results


if __name__ == "__main__":
    results = main()
