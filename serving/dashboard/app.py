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

# Custom CSS - Professional design with proper contrast
st.markdown("""
<style>
    .main > div {
        padding-top: 2rem;
    }
    
    /* =========================================== */
    /* METRICS CARDS - Professional Dark Theme    */
    /* =========================================== */
    [data-testid="metric-container"] {
        background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%) !important;
        border: 1px solid #334155 !important;
        padding: 1.25rem !important;
        border-radius: 0.75rem !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3) !important;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        color: #f8fafc !important;
        text-shadow: 0 1px 2px rgba(0,0,0,0.2) !important;
    }
    
    [data-testid="stMetricLabel"] {
        font-size: 0.85rem !important;
        font-weight: 600 !important;
        color: #94a3b8 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.8px !important;
    }
    
    [data-testid="stMetricDelta"] {
        font-size: 0.85rem !important;
        color: #4ade80 !important;
    }
    
    [data-testid="stMetricDelta"][data-testid-delta-type="negative"] {
        color: #f87171 !important;
    }
    
    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        font-weight: 600;
    }
    
    /* Table styling */
    .stDataFrame {
        border-radius: 0.5rem;
        overflow: hidden;
    }
    
    /* Header styling - Keep white for dark theme */
    h1, h2, h3 {
        color: #1f2937 !important;
    }
    
    /* Info/Warning boxes */
    .stInfo, .stWarning {
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
                # Use /trending?metric=trending (has data) instead of /trending/detailed (requires composite ranking)
                platform_param = platform_filter.lower() if platform_filter != "All" else "tiktok"
                response = requests.get(
                    f"{API_URL}/api/v1/trending",
                    params={"platform": platform_param, "metric": "trending", "limit": 50},
                    timeout=10
                )
                
                if response.status_code == 200:
                    api_data = response.json()
                    data = api_data.get('data', [])
                else:
                    st.warning(f"API returned status {response.status_code}")
                    data = []
            
            if len(data) > 0:
                # Transform API data to dashboard format and enrich with ML scores
                df_data = []
                
                # First, fetch all profile data from Redis for actual metrics
                import redis
                r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
                
                # Progress bar for enrichment
                progress_text = "Fetching profile data & computing ML scores..."
                progress_bar = st.progress(0, text=progress_text)
                
                for idx, item in enumerate(data):
                    kol_id = item.get('kol_id', '')
                    trending_score = item.get('score') or item.get('trending_score') or 0
                    
                    # Fetch ACTUAL profile data from Redis
                    profile_key = f"kol:profile:{kol_id}"
                    profile_data = r.hgetall(profile_key)
                    
                    # Use actual data if available, otherwise use defaults
                    if profile_data:
                        followers_count = int(profile_data.get('followers_count', 50000))
                        following_count = int(profile_data.get('following_count', 500))
                        post_count = int(profile_data.get('post_count', 100))
                        favorites_count = int(profile_data.get('favorites_count', 25000))
                        account_age_days = int(profile_data.get('account_age_days', 365))
                        verified = profile_data.get('verified', 'False').lower() == 'true'
                        has_bio = profile_data.get('has_bio', 'True').lower() == 'true'
                        has_url = profile_data.get('has_url', 'False').lower() == 'true'
                        bio_length = int(profile_data.get('bio_length', 50))
                    else:
                        # Default values for KOLs without profile data
                        followers_count = 50000
                        following_count = 500
                        post_count = 100
                        favorites_count = 25000
                        account_age_days = 365
                        verified = False
                        has_bio = True
                        has_url = False
                        bio_length = 50
                    
                    # Try to get trust score from ML API with ACTUAL profile data
                    trust_score = 0
                    success_score = 0
                    
                    try:
                        trust_response = requests.post(
                            f"{API_URL}/predict/trust",
                            json={
                                "kol_id": kol_id,
                                "followers_count": followers_count,
                                "following_count": following_count,
                                "post_count": post_count,
                                "favorites_count": favorites_count,
                                "account_age_days": account_age_days,
                                "verified": verified,
                                "has_bio": has_bio,
                                "has_url": has_url,
                                "has_profile_image": True,
                                "bio_length": bio_length
                            },
                            timeout=2
                        )
                        if trust_response.status_code == 200:
                            trust_data = trust_response.json()
                            trust_score = trust_data.get('trust_score', 0)
                    except:
                        pass
                    
                    # Get pre-computed Success Score from Redis profile
                    # (Calculated by load_profiles_to_redis.py using ML API or profile-based estimation)
                    success_score = float(profile_data.get('success_score', 0)) if profile_data else 0
                    
                    # Fallback: estimate from engagement if no pre-computed score
                    if success_score == 0:
                        import math
                        if followers_count > 0 and favorites_count > 0:
                            virality = favorites_count / followers_count
                            # Log scale normalization for virality index
                            success_score = min(100, max(0, 20 + math.log10(virality + 1) * 30))
                        else:
                            success_score = min(100, trending_score * 1.2) if trending_score > 0 else 0
                    
                    # Calculate composite/final score
                    final_score = (0.4 * trending_score + 0.35 * success_score + 0.25 * trust_score)
                    
                    df_data.append({
                        'username': kol_id,
                        'platform': platform_param.upper(),
                        'trust_score': round(trust_score, 1),
                        'success_score': round(success_score, 1),
                        'trending_score': round(trending_score, 1),
                        'final_score': round(final_score, 1),
                        'rank': item.get('rank', idx + 1),
                        'trending_label': item.get('label') or item.get('trending_label', 'N/A'),
                        'updated_at': '',
                    })
                    
                    # Update progress
                    progress_bar.progress((idx + 1) / len(data), text=f"{progress_text} ({idx + 1}/{len(data)})")
                
                progress_bar.empty()
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
                width='stretch',  # Updated from deprecated use_container_width=True
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

# ============ TAB 2: KOL SCORECARD (COLD PATH) ============
with tab2:
    st.header("📊 KOL Scorecard - Cold Path Analytics")
    
    st.markdown("""
    *Comprehensive KOL analysis from batch-processed data (Bronze → Silver → Gold)*
    
    **Data Sources:**
    - 🥉 **Bronze**: Raw crawled profiles from MinIO
    - 🥈 **Silver**: Cleaned & normalized profiles  
    - 🥇 **Gold**: Aggregated metrics with ML scores
    - 📊 **Redis Cache**: Pre-computed profile data
    """)
    st.markdown("---")
    
    # Filters - Enhanced with more options
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        batch_platform = st.selectbox("Platform", ["All", "tiktok", "youtube"], key="batch_platform")
    with col2:
        sort_by = st.selectbox("Sort By", [
            "followers_count", 
            "favorites_count",
            "virality_index",
            "trending_score",
            "trust_score"
        ], key="sort_by")
    with col3:
        tier_filter = st.selectbox("Follower Tier", [
            "All",
            "Mega (1M+)",
            "Macro (500K-1M)", 
            "Mid (100K-500K)",
            "Micro (10K-100K)",
            "Nano (<10K)"
        ], key="tier_filter")
    with col4:
        limit = st.number_input("Limit", 10, 500, 50)
    
    if st.button("🔄 Load KOL Profiles", key="refresh2"):
        st.rerun()
    
    try:
        with st.spinner("Loading Cold Path data from Redis cache..."):
            import redis
            import json
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            
            # =====================================================================
            # COLD PATH DATA STRATEGY (Principal Architect Design)
            # =====================================================================
            # Priority 1: Redis profile cache (kol:profiles:list:tiktok)
            # Priority 2: Individual profile hashes (kol:profile:{username})
            # Priority 3: Trending fallback with profile enrichment
            # =====================================================================
            
            data = []
            data_source = "unknown"
            
            # Priority 1: Try to get cached profiles list from Redis
            profiles_json = r.get("kol:profiles:list:tiktok")
            
            if profiles_json:
                profiles = json.loads(profiles_json)
                data_source = "redis_cache (Cold Path)"
                
                # Enrich with ML scores
                for profile in profiles:
                    kol_id = profile.get('username', '')
                    followers = int(profile.get('followers_count', 0))
                    likes = int(profile.get('favorites_count', 0))
                    posts = int(profile.get('post_count', 0))
                    
                    # Calculate Virality Index (Total Likes / Followers ratio)
                    # Note: TikTok 'favorites_count' is TOTAL likes across all videos
                    # This shows how "viral" a creator is - values like 39x are normal
                    virality_index = (likes / followers) if followers > 0 else 0
                    
                    # Get trending score from Redis
                    trending_score = r.zscore("ranking:tiktok:trending", kol_id) or 0
                    
                    # Calculate Trust Score via API (batch mode - cached)
                    trust_score = 0
                    try:
                        trust_resp = requests.post(
                            f"{API_URL}/predict/trust",
                            json={
                                "kol_id": kol_id,
                                "followers_count": followers,
                                "following_count": int(profile.get('following_count', 0)),
                                "post_count": posts,
                                "favorites_count": likes,
                                "account_age_days": int(profile.get('account_age_days', 365)),
                                "verified": profile.get('verified', False),
                                "has_bio": profile.get('has_bio', True),
                                "has_url": profile.get('has_url', False),
                                "has_profile_image": True,
                                "bio_length": int(profile.get('bio_length', 0))
                            },
                            timeout=1
                        )
                        if trust_resp.status_code == 200:
                            trust_score = trust_resp.json().get('trust_score', 0)
                    except:
                        # Estimate trust score based on profile quality
                        trust_score = 50 + (25 if profile.get('has_bio') else 0) + (15 if profile.get('has_url') else 0)
                    
                    # Get Success Score from pre-computed ML/sales-based scoring
                    # (Calculated via product data and ML model in load_profiles_to_redis.py)
                    success_score = float(profile.get('success_score', 0))
                    success_method = profile.get('success_score_method', 'unknown')
                    
                    # If no pre-computed score, use fallback based on sold data
                    if success_score == 0 and success_method in ['no_products', 'unknown']:
                        # Fallback: estimate from engagement (less accurate than ML)
                        # This is only used when no product data is available
                        total_sold = float(profile.get('total_sold', 0))
                        if total_sold > 0:
                            # Sales-based estimate
                            if total_sold >= 5000:
                                success_score = 85 + min(15, total_sold / 1000)
                            elif total_sold >= 1000:
                                success_score = 65 + (total_sold - 1000) / 200
                            elif total_sold >= 200:
                                success_score = 50 + (total_sold - 200) / 50
                            else:
                                success_score = 30 + total_sold / 10
                        else:
                            # No sales data - estimate from virality (less reliable)
                            import math
                            if virality_index > 1:  # More than 1x likes per follower
                                success_score = min(50, 25 + math.log10(virality_index) * 15)
                            else:
                                success_score = 20
                    
                    # Final Score (weighted composite)
                    final_score = 0.4 * trending_score + 0.35 * success_score + 0.25 * trust_score
                    
                    # Determine tier
                    if followers >= 1_000_000:
                        tier = "Mega"
                    elif followers >= 500_000:
                        tier = "Macro"
                    elif followers >= 100_000:
                        tier = "Mid"
                    elif followers >= 10_000:
                        tier = "Micro"
                    else:
                        tier = "Nano"
                    
                    data.append({
                        'kol_id': kol_id,
                        'nickname': profile.get('nickname', kol_id),
                        'platform': profile.get('platform', 'tiktok'),
                        'tier': tier,
                        'followers_count': followers,
                        'favorites_count': likes,
                        'post_count': posts,
                        'virality_index': round(virality_index, 1),  # e.g., 39.3x
                        'trending_score': round(trending_score, 1),
                        'trust_score': round(trust_score, 1),
                        'success_score': round(success_score, 1),
                        'final_score': round(final_score, 1),
                        'has_bio': profile.get('has_bio', False),
                        'verified': profile.get('verified', False),
                    })
            else:
                st.warning("⚠️ No Cold Path data in Redis. Run `python scripts/load_profiles_to_redis.py` first.")
                data_source = "none"
        
        if len(data) > 0:
            df = pd.DataFrame(data)
            
            # Apply tier filter
            if tier_filter != "All":
                tier_map = {
                    "Mega (1M+)": "Mega",
                    "Macro (500K-1M)": "Macro",
                    "Mid (100K-500K)": "Mid",
                    "Micro (10K-100K)": "Micro",
                    "Nano (<10K)": "Nano"
                }
                selected_tier = tier_map.get(tier_filter, "All")
                df = df[df['tier'] == selected_tier]
            
            # Apply platform filter
            if batch_platform != "All":
                df = df[df['platform'] == batch_platform.lower()]
            
            # Apply sorting
            if sort_by in df.columns:
                df = df.sort_values(sort_by, ascending=False)
            
            df = df.head(limit).reset_index(drop=True)
            
            # =====================================================================
            # METRICS DASHBOARD
            # =====================================================================
            st.subheader("📈 Cold Path Metrics Overview")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric(
                "Total Profiles", 
                len(df),
                delta=f"of {len(data)} total"
            )
            col2.metric(
                "Avg Followers", 
                f"{df['followers_count'].mean():,.0f}",
                delta=f"Max: {df['followers_count'].max():,.0f}"
            )
            col3.metric(
                "Avg Virality", 
                f"{df['virality_index'].mean():.1f}x",
                delta=f"Max: {df['virality_index'].max():.1f}x"
            )
            col4.metric(
                "Avg Final Score", 
                f"{df['final_score'].mean():.1f}",
                delta=f"Top: {df['final_score'].max():.1f}"
            )
            
            # Data source indicator
            st.caption(f"📂 Data Source: **{data_source}** | Last updated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
            
            # =====================================================================
            # TIER DISTRIBUTION
            # =====================================================================
            st.markdown("---")
            st.subheader("🏆 KOL Tier Distribution")
            
            tier_counts = df['tier'].value_counts()
            tier_col1, tier_col2 = st.columns([2, 3])
            
            with tier_col1:
                for tier_name in ["Mega", "Macro", "Mid", "Micro", "Nano"]:
                    count = tier_counts.get(tier_name, 0)
                    emoji = {"Mega": "👑", "Macro": "⭐", "Mid": "🔥", "Micro": "📈", "Nano": "🌱"}.get(tier_name, "")
                    st.write(f"{emoji} **{tier_name}**: {count} KOLs")
            
            with tier_col2:
                if len(tier_counts) > 0:
                    st.bar_chart(tier_counts)
            
            # =====================================================================
            # DETAILED TABLE
            # =====================================================================
            st.markdown("---")
            st.subheader("📋 KOL Profile Details")
            
            # Prepare display dataframe
            display_cols = ['kol_id', 'nickname', 'tier', 'followers_count', 'favorites_count', 
                           'virality_index', 'trending_score', 'trust_score', 'success_score', 'final_score']
            display_df = df[[c for c in display_cols if c in df.columns]].copy()
            
            # Format numbers for display
            display_df['followers_count'] = display_df['followers_count'].apply(lambda x: f"{x:,}")
            display_df['favorites_count'] = display_df['favorites_count'].apply(lambda x: f"{x:,}")
            display_df['virality_index'] = display_df['virality_index'].apply(lambda x: f"{x:.1f}x")
            
            st.dataframe(display_df, width='stretch', height=500)
            
            # =====================================================================
            # SCORE COMPARISON CHART
            # =====================================================================
            st.markdown("---")
            st.subheader("📊 Top 15 KOLs - Score Breakdown")
            
            chart_df = df.head(15).copy()
            chart_data = chart_df.set_index('kol_id')[['trending_score', 'trust_score', 'success_score']]
            st.bar_chart(chart_data)
            
            # =====================================================================
            # ENGAGEMENT VS FOLLOWERS ANALYSIS
            # =====================================================================
            st.markdown("---")
            st.subheader("🔍 Virality Analysis")
            
            analysis_col1, analysis_col2 = st.columns(2)
            
            with analysis_col1:
                st.markdown("**Top 5 by Virality Index:**")
                top_engagement = df.nlargest(5, 'virality_index')[['kol_id', 'virality_index', 'followers_count']]
                st.dataframe(top_engagement, hide_index=True)
            
            with analysis_col2:
                st.markdown("**Top 5 by Final Score:**")
                top_final = df.nlargest(5, 'final_score')[['kol_id', 'final_score', 'tier']]
                st.dataframe(top_final, hide_index=True)
            
        else:
            st.warning("⚠️ No KOL data available after filtering.")
            st.info("""
            💡 **To populate Cold Path data:**
            1. Run ETL pipeline: `spark-submit batch/etl/bronze_to_silver.py`
            2. Or load profiles to Redis: `python scripts/load_profiles_to_redis.py`
            """)
            
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