#!/usr/bin/env python3
"""Quick API test script - Run separately from server"""

import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_api():
    print("=" * 60)
    print("KOL PLATFORM API TEST")
    print("=" * 60)
    
    # Test 1: Health
    print("\n[1] Health Check...")
    try:
        r = requests.get(f"{BASE_URL}/healthz", timeout=5)
        print(f"    ✅ Status: {r.status_code}")
        print(f"    Response: {r.json()}")
    except Exception as e:
        print(f"    ❌ Error: {e}")
    
    # Test 2: Success Model Info
    print("\n[2] Success Model Info...")
    try:
        r = requests.get(f"{BASE_URL}/predict/success/model-info", timeout=5)
        print(f"    ✅ Status: {r.status_code}")
        data = r.json()
        print(f"    Model: {data.get('model_type', 'N/A')}")
        print(f"    Features: {data.get('features_count', 'N/A')}")
        print(f"    Status: {data.get('status', 'N/A')}")
    except Exception as e:
        print(f"    ❌ Error: {e}")
    
    # Test 3: Success Prediction
    print("\n[3] Success Prediction...")
    try:
        payload = {
            "kol_id": "test_kol_viral",
            "video_views": 1000000,
            "video_likes": 80000,
            "video_comments": 5000,
            "video_shares": 3000,
            "engagement_total": 88000,
            "engagement_rate": 0.088,
            "est_clicks": 30000,
            "est_ctr": 0.03,
            "price": 199000
        }
        r = requests.post(f"{BASE_URL}/predict/success", json=payload, timeout=5)
        print(f"    ✅ Status: {r.status_code}")
        data = r.json()
        print(f"    KOL: {data.get('kol_id')}")
        print(f"    Score: {data.get('success_score')}")
        print(f"    Label: {data.get('success_label')}")
        print(f"    Confidence: {data.get('confidence')}")
        print(f"    Method: {data.get('method')}")
    except Exception as e:
        print(f"    ❌ Error: {e}")
    
    # Test 4: Trending Prediction
    print("\n[4] Trending Prediction...")
    try:
        payload = {
            "kol_id": "test_kol_viral",
            "current_velocity": 100,
            "baseline_velocity": 20,
            "global_avg_velocity": 30,
            "momentum": 0.8
        }
        r = requests.post(f"{BASE_URL}/predict/trending", json=payload, timeout=5)
        print(f"    ✅ Status: {r.status_code}")
        data = r.json()
        print(f"    KOL: {data.get('kol_id')}")
        print(f"    Score: {data.get('trending_score')}")
        print(f"    Label: {data.get('trending_label')}")
        print(f"    Personal Growth: {data.get('personal_growth')}x")
        print(f"    Market Position: {data.get('market_position')}x")
    except Exception as e:
        print(f"    ❌ Error: {e}")
    
    # Test 5: Trust Model Info
    print("\n[5] Trust Model Info...")
    try:
        r = requests.get(f"{BASE_URL}/predict/trust/model-info", timeout=5)
        print(f"    ✅ Status: {r.status_code}")
        data = r.json()
        print(f"    Model: {data.get('model_name', 'N/A')}")
        print(f"    Status: {data.get('status', 'N/A')}")
    except Exception as e:
        print(f"    ❌ Error: {e}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    print("\n💡 Make sure server is running:")
    print("   uvicorn serving.api.main:app --host 127.0.0.1 --port 8000")


if __name__ == "__main__":
    test_api()
