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
# - API Mode: Full features (Trending + Trust/Success from Trino + AI inference)
# - Redis Mode: Only Trending scores (for testing real-time flow)
# ============================================================================

USE_API = False  # Set to True when API is ready, False for testing with Redis only

# API Configuration (for future use)
API_URL = os.getenv("API_URL", "http://localhost:8000")

# Redis Configuration (for direct testing)
REDIS_HOST = os.getenv("REDIS_HOST", "redis")  # "redis" in Docker, "localhost" outside
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

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
            # PRODUCTION MODE: Fetch from API (Trending + Trust/Success + AI)
            # =====================================================================
            # TODO: Uncomment this section when API is ready
            with st.spinner("Loading data from API..."):
                response = requests.get(
                    f"{API_URL}/api/v1/kols/realtime",
                    params={"platform": platform_filter.lower(), "limit": 50},
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()['data']
            
            if len(data) > 0:
                df = pd.DataFrame(data)
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
                        
                        # Trust/Success scores (will be 0 in testing mode, from API in production)
                        trust_score = 0.0
                        success_score = 0.0
                        trending_score = float(scores.get('score', 0))
                        
                        # Final score = weighted combination (in testing: only trending)
                        final_score = trending_score  # TODO: Add trust/success weights when API ready
                        
                        data.append({
                            'username': username,
                            'platform': platform.upper(),  # TikTok / YouTube
                            'views': views,
                            'likes': likes,
                            'shares': shares,
                            'video_count': video_count,
                            'trust_score': trust_score,
                            'success_score': success_score,
                            'trending_score': trending_score,
                            'final_score': final_score,
                            'mode': 'realtime',
                            'updated_at': scores.get('ts', '')
                        })
                    
                    df = pd.DataFrame(data).sort_values('trending_score', ascending=False)
                else:
                    df = pd.DataFrame()
        
        if len(df) > 0:
            
            # Metrics (GIỮ SCORES, không phải Views/Likes)
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total KOLs", len(df))
            col2.metric("Avg Trust Score", f"{df['trust_score'].mean():.1f}")
            col3.metric("Avg Success Score", f"{df['success_score'].mean():.1f}")
            col4.metric("Avg Final Score", f"{df['final_score'].mean():.1f}")
            
            st.markdown("---")
            
            # Table
            st.subheader("📋 Top KOLs by Final Score")
            display_df = df[[
                'username', 'platform', 'trust_score', 'success_score', 'trending_score', 
                'final_score', 'video_count', 'updated_at'
            ]].copy()
            
            # Format columns
            display_df['trust_score'] = display_df['trust_score'].apply(lambda x: f"{x:.1f}")
            display_df['success_score'] = display_df['success_score'].apply(lambda x: f"{x:.1f}")
            display_df['trending_score'] = display_df['trending_score'].apply(lambda x: f"{x:.1f}")
            display_df['final_score'] = display_df['final_score'].apply(lambda x: f"{x:.1f}")
            
            st.dataframe(
                display_df,
                use_container_width=True,
                height=400
            )
            
            # Chart
            st.subheader("📈 Top 10 Score Breakdown")
            chart_data = df.head(10).set_index('username')[['trust_score', 'success_score', 'trending_score']]
            st.bar_chart(chart_data)
            
        else:
            if USE_API:
                st.warning("⚠️ No data available from API.")
            else:
                st.warning("⚠️ No data in Redis. Please check if Spark Streaming is running.")
                st.info("💡 Expected Redis keys: `streaming_scores:{username}`")
            
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        if USE_API:
            st.info(f"Make sure API is running at {API_URL}")
        else:
            st.info(f"Make sure Redis is accessible at {REDIS_HOST}:{REDIS_PORT}")
            st.code("docker exec kol-redis redis-cli KEYS 'streaming_scores:*'")

# ============ TAB 2: KOL SCORECARD ============
with tab2:
    st.header("📊 KOL Scorecard (Batch)")
    
    if not USE_API:
        st.warning("🚧 **Batch Scorecard requires API mode**")
        st.info("This tab shows KOL Trust/Success scores from batch processing (Trino). Set `USE_API = True` when API is ready.")
        st.markdown("---")
    
    st.markdown("*KOL ổn định về Trust/Success (không phụ thuộc trending)*")
    st.markdown("---")
    
    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        min_trust = st.slider("Min TrustScore", 0, 100, 70)
    with col2:
        min_success = st.slider("Min SuccessScore", 0, 100, 60)
    with col3:
        limit = st.number_input("Limit", 10, 500, 100)
    
    if not USE_API:
        st.info("💡 Enable API mode to see batch scores")
    else:
        try:
            # =====================================================================
            # PRODUCTION MODE: Fetch batch scores from API
            # =====================================================================
            with st.spinner("Loading batch data..."):
                response = requests.get(
                    f"{API_URL}/api/v1/kols",
                    params={
                        "platform": platform_filter.lower(),
                        "min_trust": min_trust,
                        "min_success": min_success,
                        "limit": limit
                    },
                    timeout=10
                )
                response.raise_for_status()
                data = response.json()['data']
            
            if len(data) > 0:
                df = pd.DataFrame(data)
                
                # Metrics
                col1, col2, col3 = st.columns(3)
                col1.metric("Qualified KOLs", len(df))
                col2.metric("Avg TrustScore", f"{df['trust_score'].mean():.1f}")
                col3.metric("Avg SuccessScore", f"{df['success_score'].mean():.1f}")
                
                st.markdown("---")
                
                # Table
                st.subheader("📋 Qualified KOLs")
                display_df = df.copy()
                display_df['followers'] = display_df['followers'].apply(lambda x: f"{x:,}")
                display_df['trust_score'] = display_df['trust_score'].apply(lambda x: f"{x:.1f}")
                display_df['success_score'] = display_df['success_score'].apply(lambda x: f"{x:.1f}")
                
                st.dataframe(display_df, use_container_width=True, height=500)
                
            else:
                st.warning("⚠️ No KOLs match the criteria. Try adjusting the filters.")
                
        except requests.exceptions.RequestException as e:
            st.error(f"❌ Failed to connect to API: {str(e)}")
            st.info(f"Make sure API is running at {API_URL}")

# Footer
st.markdown("---")
st.markdown("**KOL Platform** | Powered by Spark Streaming, Redis, Trino, and AI")

# Auto-refresh logic
if auto_refresh:
    time.sleep(30)
    st.rerun()
