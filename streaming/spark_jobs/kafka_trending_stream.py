#!/usr/bin/env python3
"""
Kafka Trending Stream - Alias for Unified Hot Path
===================================================

This file is an ALIAS/WRAPPER for backward compatibility.
All functionality has been moved to unified_hot_path.py which includes:
- Trending Score (velocity-based)
- Success Score (LightGBM)
- Trust Score (rule-based)
- Composite Score (weighted average)

Usage (still works):
    spark-submit kafka_trending_stream.py

Recommended (use new file):
    spark-submit unified_hot_path.py
"""

# Import and run unified hot path
if __name__ == "__main__":
    import sys
    import os
    
    # Add current directory to path
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    # Import from unified_hot_path
    from unified_hot_path import run_unified_hot_path
    
    print("=" * 60)
    print("  NOTE: kafka_trending_stream.py is now an ALIAS")
    print("        Running unified_hot_path.py instead")
    print("=" * 60)
    
    # Run with local mode if no arguments
    local_mode = "--mode" not in sys.argv or "local" in sys.argv
    run_unified_hot_path(local=local_mode)
