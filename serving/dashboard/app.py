"""
KOL Platform Dashboard - Streamlit UI
Real-time KOL analytics and recommendations
"""

import streamlit as st
import requests
import pandas as pd
import time
import os

# ============================================================================
# DATA SOURCE CONFIGURATION
# ============================================================================
# Switch between API mode (production) and Direct Redis mode (testing)
# - API Mode: Full features via REST API (recommended)
# - Redis Mode: Direct Redis connection (for debugging)
# ============================================================================

USE_API = True  # Use API for all data access

# API Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Redis Configuration (fallback for debugging)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")  # "redis" in Docker, "localhost" outside
REDIS_PORT = int(os.getenv("REDIS_PORT", "16379"))  # 16379 external, 6379 internal

st.set_page_config(
    page_title="KOL Platform Dashboard",
    page_icon="🔥",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    .stMetric {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
st.sidebar.title("⚙️ Settings")
platform_filter = st.sidebar.selectbox("Platform", ["All", "TikTok", "YouTube"], index=0)
auto_refresh = st.sidebar.checkbox("Auto Refresh (30s)", value=False)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 System Status")
if USE_API:
    st.sidebar.markdown(f"**Mode:** API")
    st.sidebar.markdown(f"**API:** {API_URL}")
else:
    st.sidebar.markdown(f"**Mode:** Direct Redis (Testing)")
    st.sidebar.markdown(f"**Redis:** {REDIS_HOST}:{REDIS_PORT}")

# Header
st.title("🔥 KOL Platform Dashboard")
if USE_API:
    st.markdown("Real-time KOL analytics powered by Spark Streaming & AI")
else:
    st.markdown("🧪 **Testing Mode:** Direct Redis connection (Real-time trending only)")

# Tabs
tab1, tab2 = st.tabs(["🔥 Realtime Hot KOL", "📊 KOL Scorecard (Batch)"])

# ============ TAB 1: REALTIME HOT KOL ============
with tab1:
    st.header("🔥 Top Hot KOL (Real-time)")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("*Cập nhật mỗi 2h từ Spark Streaming → Redis*")
    with col2:
        if st.button("🔄 Refresh", key="refresh1"):
            st.rerun()
    
    try:
        if USE_API:
            # =====================================================================
            # PRODUCTION MODE: Fetch from API
            # =====================================================================
            with st.spinner("Loading data from API..."):
                # Get trending KOLs from API
                platform_param = platform_filter.lower() if platform_filter != "All" else "tiktok"
                response = requests.get(
                    f"{API_URL}/api/v1/trending/detailed",
                    params={"platform": platform_param, "limit": 50},
                    timeout=10
                )
                
                if response.status_code == 200:
                    api_data = response.json()
                    data = api_data.get('data', [])
                else:
                    st.warning(f"API returned status {response.status_code}")
                    data = []
            
            if len(data) > 0:
                # Transform API data to dashboard format
                df_data = []
                for item in data:
                    df_data.append({
                        'username': item.get('kol_id', ''),
                        'platform': item.get('platform', 'tiktok').upper(),
                        'trust_score': item.get('trust_score') or 0,
                        'success_score': item.get('success_score') or 0,
                        'trending_score': item.get('trending_score') or 0,
                        'final_score': item.get('composite_score') or 0,
                        'rank': item.get('rank', 0),
                        'trending_label': item.get('trending_label', 'N/A'),
                        'updated_at': '',
                    })
                df = pd.DataFrame(df_data)
            else:
                df = pd.DataFrame()
        
        else:
            # =====================================================================
            # TESTING MODE: Direct Redis connection (Trending only)
            # =====================================================================
            import redis
            
            with st.spinner("Loading data from Redis..."):
                r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
                
                # Get all trending KOL keys
                all_keys = r.keys("streaming_scores:*")
                
                # Filter by platform
                if platform_filter == "All":
                    keys = all_keys
                else:
                    keys = [k for k in all_keys if r.hget(k, "platform") == platform_filter.lower()]
                
                if len(keys) > 0:
                    data = []
                    for key in keys:
                        username = key.split(':')[1]
                        scores = r.hgetall(key)
                        
                        # Get platform and video metrics from Redis
                        platform = scores.get('platform', 'tiktok')
                        views = int(scores.get('view', 0))
                        likes = int(scores.get('like', 0))
                        shares = int(scores.get('share', 0))
                        video_count = int(scores.get('video_count', 0))
                        
                        # Get scores from Hot Path
                        trust_score = float(scores.get('trust_score', 0) or 0)
                        success_score = float(scores.get('success_score', 0) or 0)
                        trending_score = float(scores.get('trending_score', 0) or scores.get('score', 0) or 0)
                        
                        # Final score = composite or weighted combination
                        final_score = float(scores.get('score', 0) or trending_score)
                        
                        data.append({
                            'username': username,
                            'platform': platform.upper(),
                            'trust_score': trust_score,
                            'success_score': success_score,
                            'trending_score': trending_score,
                            'final_score': final_score,
                            'label': scores.get('label', 'N/A'),
                            'updated_at': scores.get('updated_at', scores.get('ts', ''))
                        })
                    
                    df = pd.DataFrame(data).sort_values('final_score', ascending=False)
                else:
                    df = pd.DataFrame()
        
        if len(df) > 0:
            
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total KOLs", len(df))
            col2.metric("Avg Trust Score", f"{df['trust_score'].mean():.1f}")
            col3.metric("Avg Trending Score", f"{df['trending_score'].mean():.1f}")
            col4.metric("Avg Final Score", f"{df['final_score'].mean():.1f}")
            
            st.markdown("---")
            
            # Table
            st.subheader("📋 Top KOLs by Final Score")
            
            # Prepare display columns based on available data
            display_cols = ['username', 'platform', 'trust_score', 'trending_score', 'final_score']
            if 'success_score' in df.columns:
                display_cols.insert(3, 'success_score')
            if 'label' in df.columns:
                display_cols.append('label')
            if 'updated_at' in df.columns:
                display_cols.append('updated_at')
            
            display_df = df[display_cols].copy()
            
            # Format score columns
            for col in ['trust_score', 'success_score', 'trending_score', 'final_score']:
                if col in display_df.columns:
                    display_df[col] = display_df[col].apply(lambda x: f"{x:.1f}")
            
            st.dataframe(
                display_df,
                use_container_width=True,
                height=400
            )
            
            # Chart - only include available score columns
            st.subheader("📈 Top 10 Score Breakdown")
            chart_cols = []
            for col in ['trust_score', 'trending_score', 'success_score']:
                if col in df.columns:
                    chart_cols.append(col)
            
            if chart_cols:
                # Need numeric values for chart
                chart_df = df.head(10).copy()
                for col in chart_cols:
                    chart_df[col] = pd.to_numeric(chart_df[col], errors='coerce').fillna(0)
                chart_data = chart_df.set_index('username')[chart_cols]
                st.bar_chart(chart_data)
            
        else:
            if USE_API:
                st.warning("⚠️ No trending data available from API.")
                st.info("💡 Data will appear after Spark Streaming processes events and writes to Redis.")
            else:
                st.warning("⚠️ No data in Redis. Please check if Spark Streaming is running.")
                st.info("💡 Expected Redis keys: `streaming_scores:{username}`")
            
    except requests.exceptions.ConnectionError:
        st.error(f"❌ Cannot connect to API at {API_URL}")
        st.info("Make sure API server is running: `python -m uvicorn serving.api.main:app --port 8000`")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

# ============ TAB 2: KOL SCORECARD ============
with tab2:
    st.header("📊 KOL Scorecard (Batch)")
    
    st.markdown("*KOL profiles from database with Trust/Success scores*")
    st.markdown("---")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        batch_platform = st.selectbox("Platform", ["All", "tiktok", "youtube"], key="batch_platform")
    with col2:
        sort_by = st.selectbox("Sort By", ["followers_count", "post_count"], key="sort_by")
    with col3:
        limit = st.number_input("Limit", 10, 500, 50)
    
    if st.button("🔄 Load KOLs", key="refresh2"):
        st.rerun()
    
    try:
        with st.spinner("Loading KOL data..."):
            # Fetch KOL list from API
            params = {"limit": limit}
            if batch_platform != "All":
                params["platform"] = batch_platform
            
            response = requests.get(
                f"{API_URL}/api/v1/kols",
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                api_data = response.json()
                data = api_data.get('data', [])
                total = api_data.get('total', 0)
                data_source = api_data.get('data_source', 'unknown')
            else:
                st.warning(f"API returned status {response.status_code}")
                data = []
                total = 0
                data_source = "error"
        
        if len(data) > 0:
            df = pd.DataFrame(data)
            
            # Metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total KOLs", total)
            col2.metric("Shown", len(df))
            if 'followers_count' in df.columns:
                col3.metric("Avg Followers", f"{df['followers_count'].mean():,.0f}")
            if 'post_count' in df.columns:
                col4.metric("Avg Posts", f"{df['post_count'].mean():,.0f}")
            
            st.caption(f"Data source: {data_source}")
            st.markdown("---")
            
            # Table
            st.subheader("📋 KOL Profiles")
            
            # Format columns for display
            display_cols = ['kol_id', 'platform', 'username']
            if 'followers_count' in df.columns:
                display_cols.append('followers_count')
            if 'post_count' in df.columns:
                display_cols.append('post_count')
            if 'verified' in df.columns:
                display_cols.append('verified')
            
            display_df = df[[c for c in display_cols if c in df.columns]].copy()
            
            # Format numbers
            if 'followers_count' in display_df.columns:
                display_df['followers_count'] = display_df['followers_count'].apply(
                    lambda x: f"{x:,}" if pd.notna(x) else "N/A"
                )
            
            st.dataframe(display_df, use_container_width=True, height=500)
            
        else:
            st.warning("⚠️ No KOL data available.")
            st.info("💡 Data will be available after running the ETL pipeline to populate Silver layer.")
            
    except requests.exceptions.ConnectionError:
        st.error(f"❌ Cannot connect to API at {API_URL}")
        st.info("Make sure API server is running.")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        import traceback
        st.code(traceback.format_exc())

# Footer
st.markdown("---")
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("**KOL Platform** | Powered by Spark Streaming, Redis, Trino, and AI")
with col2:
    st.caption(f"API: {API_URL}")

# Auto-refresh logic
if auto_refresh:
    time.sleep(30)
    st.rerun()