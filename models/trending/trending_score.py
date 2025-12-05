#!/usr/bin/env python3
"""TrendingScore - Streaming Velocity Approach"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "kafka_export"


def load_events_data() -> pd.DataFrame:
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
                    "video_views": event.get("video_views", 0),
                    "video_id": event.get("video_id"),
                })
    df = pd.DataFrame(events)
    print(f"  Loaded {len(df)} events")
    return df


def calculate_trending_score(current_velocity: float, baseline_velocity: float = 1.0, global_avg_velocity: float = 1.0) -> Dict:
    personal_ratio = current_velocity / baseline_velocity if baseline_velocity > 0 else 1.0
    global_ratio = current_velocity / global_avg_velocity if global_avg_velocity > 0 else 1.0
    raw_score = 0.6 * personal_ratio + 0.4 * global_ratio
    trending_score = min(raw_score / 5 * 100, 100)
    
    if trending_score < 20:
        label = "Cold"
    elif trending_score < 40:
        label = "Normal"
    elif trending_score < 60:
        label = "Warm"
    elif trending_score < 80:
        label = "Hot"
    else:
        label = "Viral"
    
    return {
        "trending_score": round(trending_score, 2),
        "trending_label": label,
        "personal_ratio": round(personal_ratio, 2),
        "global_ratio": round(global_ratio, 2),
        "current_velocity": current_velocity,
    }


def calculate_all_trending_scores(df: Optional[pd.DataFrame] = None) -> Dict[str, Dict]:
    if df is None:
        df = load_events_data()
    if df.empty:
        return {}
    
    df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")
    velocity_df = df.groupby("username").agg(
        event_count=("event_time", "count"),
        total_views=("video_views", "sum"),
        unique_videos=("video_id", "nunique"),
    ).reset_index()
    
    global_avg = velocity_df["event_count"].mean()
    print(f"\nCalculating TrendingScore...")
    print(f"  Global avg events: {global_avg:.2f}")
    print(f"  Total KOLs: {len(velocity_df)}")
    
    results = {}
    for _, row in velocity_df.iterrows():
        username = row["username"]
        current = row["event_count"]
        baseline = global_avg
        scores = calculate_trending_score(current, baseline, global_avg)
        scores["total_views"] = int(row["total_views"])
        scores["unique_videos"] = int(row["unique_videos"])
        results[username] = scores
    return results


def get_top_trending(n: int = 10) -> List[Dict]:
    all_scores = calculate_all_trending_scores()
    sorted_kols = sorted(all_scores.items(), key=lambda x: x[1]["trending_score"], reverse=True)
    return [{"username": username, **scores} for username, scores in sorted_kols[:n]]


def main():
    print("=" * 60)
    print("  TRENDING SCORE CALCULATION")
    print("=" * 60)
    
    results = calculate_all_trending_scores()
    if not results:
        print("No data to process")
        return
    
    scores = [r["trending_score"] for r in results.values()]
    print(f"\nScore Distribution:")
    print(f"  Min:  {min(scores):.2f}")
    print(f"  Max:  {max(scores):.2f}")
    print(f"  Mean: {np.mean(scores):.2f}")
    
    labels = [r["trending_label"] for r in results.values()]
    label_counts = pd.Series(labels).value_counts()
    print(f"\nLabel Distribution:")
    for label, count in label_counts.items():
        pct = count / len(labels) * 100
        print(f"  {label:<8}: {count:>4} ({pct:.1f}%)")
    
    print(f"\nTop 10 Trending KOLs:")
    sorted_results = sorted(results.items(), key=lambda x: x[1]["trending_score"], reverse=True)
    for i, (username, sc) in enumerate(sorted_results[:10], 1):
        print(f"  {i:>2}. {username:<25} Score: {sc['trending_score']:>5.1f} ({sc['trending_label']})")
    
    print("\n" + "=" * 60)
    print("  TRENDING SCORE COMPLETE")
    print("=" * 60)
    return results


if __name__ == "__main__":
    main()
