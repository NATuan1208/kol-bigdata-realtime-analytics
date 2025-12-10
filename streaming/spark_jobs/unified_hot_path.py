#!/usr/bin/env python3
"""
Unified Hot Path - Backward Compatibility Wrapper
==================================================

DEPRECATED: This file is kept for backward compatibility only.

The hot path has been refactored into focused jobs:
- trending_stream.py: Trending Score calculation (recommended)
- kafka_profile_stream.py: Profile metrics to Redis
- features_stream.py: Windowed metrics to Cassandra

Architecture Decision (2024-12 Refactor):
-----------------------------------------
BEFORE: unified_hot_path.py calculated ALL scores (Trending + Trust + Success)
AFTER: 
  - Trending Score: Spark Streaming (real-time, velocity-based)
  - Trust Score: API on-demand (ML model)
  - Success Score: API on-demand (ML model)
  - Final Score: API composes from all 3

Why this change:
- Trending needs real-time streaming (velocity changes frequently)
- Trust/Success are stable, don't need streaming
- Reduces Spark job complexity
- Better separation of concerns

Usage (backward compatible - runs trending_stream):
    spark-submit unified_hot_path.py
    spark-submit unified_hot_path.py --mode local

Recommended (use new focused jobs):
    spark-submit trending_stream.py --mode local
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def run_unified_hot_path(local: bool = False):
    """
    Backward compatible entry point.
    Now delegates to trending_stream.py
    """
    print("=" * 60)
    print("  DEPRECATION NOTICE")
    print("  unified_hot_path.py is deprecated.")
    print("  Running trending_stream.py instead.")
    print("=" * 60)
    print()
    print("  Refactored Architecture:")
    print("  - Trending Score: Spark Streaming (this job)")
    print("  - Trust Score: API on-demand")
    print("  - Success Score: API on-demand")
    print("  - Final Score: API composition")
    print()
    print("=" * 60)
    
    # Import and run trending stream
    from trending_stream import run_trending_stream
    run_trending_stream(local=local)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Unified Hot Path (Deprecated)")
    parser.add_argument("--mode", choices=["local", "cluster"], default="local")
    parser.add_argument("--debug", action="store_true")
    
    args = parser.parse_args()
    
    run_unified_hot_path(local=(args.mode == "local"))

