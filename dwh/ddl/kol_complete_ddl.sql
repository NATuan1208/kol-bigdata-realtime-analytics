-- ============================================================================
-- KOL Platform - Complete DDL for All Layers
-- ============================================================================
-- Updated: 2025-11-27
-- Compatible with: Trino + Hive Metastore + MinIO
-- 
-- Usage:
--   docker exec -it sme-trino trino
--   Then run each statement manually or use the helper script
-- ============================================================================

-- ============================================================================
-- CREATE SCHEMAS (IF NOT EXISTS)
-- ============================================================================
CREATE SCHEMA IF NOT EXISTS minio.kol_bronze WITH (location = 's3a://kol-platform/bronze/');
CREATE SCHEMA IF NOT EXISTS minio.kol_silver WITH (location = 's3a://kol-platform/silver/');
CREATE SCHEMA IF NOT EXISTS minio.kol_gold WITH (location = 's3a://kol-platform/gold/');


-- ============================================================================
-- BRONZE LAYER - Raw Data Tables
-- ============================================================================
-- Data ingested from various sources, stored as-is with minimal transformation

-- 1. Twitter Human Bots Dataset (37,438 records)
-- Main dataset for Trust Score ML training
DROP TABLE IF EXISTS minio.kol_bronze.twitter_human_bots;
CREATE TABLE minio.kol_bronze.twitter_human_bots (
    ingest_ts VARCHAR,
    kol_id VARCHAR,
    payload VARCHAR,          -- JSON payload with all original fields
    platform VARCHAR,
    source VARCHAR,
    dt DATE                   -- Partition key
) WITH (
    format = 'PARQUET',
    partitioned_by = ARRAY['dt'],
    external_location = 's3a://kol-platform/bronze/tables/twitter_human_bots/'
);

-- 2. Short Video Trends Dataset (48,079 records)
-- TikTok trending videos from HuggingFace
DROP TABLE IF EXISTS minio.kol_bronze.short_video_trends;
CREATE TABLE minio.kol_bronze.short_video_trends (
    ingest_ts VARCHAR,
    kol_id VARCHAR,
    payload VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    partitioned_by = ARRAY['dt'],
    external_location = 's3a://kol-platform/bronze/tables/short_video_trends/'
);

-- 3. Wikipedia Backlinko (213 records)
-- Top YouTubers rankings
DROP TABLE IF EXISTS minio.kol_bronze.wikipedia_backlinko;
CREATE TABLE minio.kol_bronze.wikipedia_backlinko (
    ingest_ts VARCHAR,
    kol_id VARCHAR,
    payload VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    partitioned_by = ARRAY['dt'],
    external_location = 's3a://kol-platform/bronze/tables/wikipedia_backlinko/'
);

-- 4. YouTube Trending (581 records)
-- YouTube trending videos via API
DROP TABLE IF EXISTS minio.kol_bronze.youtube_trending;
CREATE TABLE minio.kol_bronze.youtube_trending (
    ingest_ts VARCHAR,
    kol_id VARCHAR,
    payload VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    dt DATE
) WITH (
    format = 'PARQUET',
    partitioned_by = ARRAY['dt'],
    external_location = 's3a://kol-platform/bronze/tables/youtube_trending/'
);


-- ============================================================================
-- SILVER LAYER - Cleaned & Standardized Data
-- ============================================================================
-- Data cleaned, deduplicated, and standardized schema

-- 1. KOL Profiles (37,438 records)
-- Unified KOL profile information across platforms
DROP TABLE IF EXISTS minio.kol_silver.kol_profiles;
CREATE TABLE minio.kol_silver.kol_profiles (
    kol_id VARCHAR,
    platform VARCHAR,
    username VARCHAR,
    display_name VARCHAR,
    bio VARCHAR,
    followers_count BIGINT,
    following_count BIGINT,
    post_count BIGINT,
    verified BOOLEAN,
    category VARCHAR,
    profile_url VARCHAR,
    account_created_at VARCHAR,
    source VARCHAR,
    processed_at VARCHAR
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/silver/kol_profiles/'
);

-- 2. KOL Content (48,658 records)
-- Posts/videos with engagement metrics
DROP TABLE IF EXISTS minio.kol_silver.kol_content;
CREATE TABLE minio.kol_silver.kol_content (
    content_id VARCHAR,
    kol_id VARCHAR,
    platform VARCHAR,
    content_type VARCHAR,
    title VARCHAR,
    description VARCHAR,
    views BIGINT,
    likes BIGINT,
    comments BIGINT,
    shares BIGINT,
    engagement_rate DOUBLE,
    duration_seconds BIGINT,
    posted_at VARCHAR,
    hashtags VARCHAR,
    source VARCHAR,
    processed_at VARCHAR
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/silver/kol_content/'
);

-- 3. KOL Trust Features (37,438 records)
-- Features for Trust Score ML with labels
DROP TABLE IF EXISTS minio.kol_silver.kol_trust_features;
CREATE TABLE minio.kol_silver.kol_trust_features (
    kol_id VARCHAR,
    platform VARCHAR,
    username VARCHAR,
    has_profile_image BOOLEAN,
    has_bio BOOLEAN,
    bio_length BIGINT,
    has_url BOOLEAN,
    verified BOOLEAN,
    followers_count BIGINT,
    following_count BIGINT,
    post_count BIGINT,
    favorites_count BIGINT,
    followers_following_ratio DOUBLE,
    account_created_at VARCHAR,
    default_profile BOOLEAN,
    default_profile_image BOOLEAN,
    is_untrustworthy BIGINT,      -- Label: 1 = untrustworthy, 0 = trustworthy
    is_trustworthy BIGINT,        -- Inverse label
    account_type VARCHAR,         -- 'bot' or 'human' (semantic: untrustworthy/trustworthy)
    source VARCHAR,
    processed_at VARCHAR,
    account_age_days BIGINT,
    posts_per_day DOUBLE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/silver/kol_trust_features/'
);

-- 4. KOL Engagement Metrics (1,730 records)
-- Aggregated engagement statistics per KOL
DROP TABLE IF EXISTS minio.kol_silver.kol_engagement_metrics;
CREATE TABLE minio.kol_silver.kol_engagement_metrics (
    kol_id VARCHAR,
    platform VARCHAR,
    total_views BIGINT,
    total_likes BIGINT,
    total_comments BIGINT,
    total_shares BIGINT,
    total_posts BIGINT,
    avg_views_per_post DOUBLE,
    avg_likes_per_post DOUBLE,
    avg_engagement_rate DOUBLE,
    max_views BIGINT,
    min_views BIGINT,
    source VARCHAR,
    processed_at VARCHAR
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/silver/kol_engagement_metrics/'
);


-- ============================================================================
-- GOLD LAYER - Star Schema (Analytics Ready)
-- ============================================================================

-- DIMENSION TABLES
-- ================

-- 1. dim_kol (37,438 records)
-- SCD Type 2 dimension for KOL tracking
DROP TABLE IF EXISTS minio.kol_gold.dim_kol;
CREATE TABLE minio.kol_gold.dim_kol (
    kol_sk BIGINT,                -- Surrogate key
    kol_id VARCHAR,               -- Business key
    platform VARCHAR,
    username VARCHAR,
    display_name VARCHAR,
    bio VARCHAR,
    category VARCHAR,
    profile_url VARCHAR,
    account_created_at VARCHAR,
    valid_from VARCHAR,
    valid_to VARCHAR,
    is_current BOOLEAN
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/dim_kol/'
);

-- 2. dim_platform (4 records)
DROP TABLE IF EXISTS minio.kol_gold.dim_platform;
CREATE TABLE minio.kol_gold.dim_platform (
    platform_sk BIGINT,
    platform_code VARCHAR,
    platform_name VARCHAR,
    category VARCHAR
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/dim_platform/'
);

-- 3. dim_time (366 records)
-- Date dimension for time-based analysis
DROP TABLE IF EXISTS minio.kol_gold.dim_time;
CREATE TABLE minio.kol_gold.dim_time (
    time_sk BIGINT,
    full_date DATE,
    year INTEGER,
    quarter INTEGER,
    month INTEGER,
    week INTEGER,
    day_of_week INTEGER,
    day_name VARCHAR,
    is_weekend BOOLEAN
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/dim_time/'
);

-- 4. dim_content_type (5 records)
DROP TABLE IF EXISTS minio.kol_gold.dim_content_type;
CREATE TABLE minio.kol_gold.dim_content_type (
    content_type_sk BIGINT,
    content_type_code VARCHAR,
    content_type_name VARCHAR
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/dim_content_type/'
);


-- FACT TABLES
-- ===========

-- 5. fact_kol_performance (48,658 records)
-- Main fact table for KOL performance analysis
DROP TABLE IF EXISTS minio.kol_gold.fact_kol_performance;
CREATE TABLE minio.kol_gold.fact_kol_performance (
    perf_sk BIGINT,
    kol_sk BIGINT,                -- FK -> dim_kol
    platform_sk BIGINT,           -- FK -> dim_platform
    time_sk BIGINT,               -- FK -> dim_time
    content_type_sk BIGINT,       -- FK -> dim_content_type
    followers_count BIGINT,
    following_count BIGINT,
    post_count BIGINT,
    total_views BIGINT,
    total_likes BIGINT,
    total_comments BIGINT,
    total_shares BIGINT,
    engagement_rate DOUBLE,
    is_verified BOOLEAN,
    is_untrustworthy BOOLEAN,
    trust_score DOUBLE
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/fact_kol_performance/'
);


-- ML TABLES
-- =========

-- 6. ml_trust_training (37,438 records)
-- Clean dataset for ML training
DROP TABLE IF EXISTS minio.kol_gold.ml_trust_training;
CREATE TABLE minio.kol_gold.ml_trust_training (
    kol_id VARCHAR,
    platform VARCHAR,
    followers_count BIGINT,
    following_count BIGINT,
    post_count BIGINT,
    favorites_count BIGINT,
    verified BOOLEAN,
    default_profile BOOLEAN,
    default_profile_image BOOLEAN,
    has_url BOOLEAN,
    has_bio BOOLEAN,
    account_age_days BIGINT,
    followers_following_ratio DOUBLE,
    posts_per_day DOUBLE,
    label BIGINT                  -- 0=trustworthy, 1=untrustworthy
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/ml_trust_training/'
);

-- 7. ml_trust_features_engineered (37,438 records × 29 features)
-- Engineered features ready for ML model training
DROP TABLE IF EXISTS minio.kol_gold.ml_trust_features_engineered;
CREATE TABLE minio.kol_gold.ml_trust_features_engineered (
    -- ID
    kol_id VARCHAR,
    
    -- Original metrics
    followers_count BIGINT,
    following_count BIGINT,
    post_count BIGINT,
    favorites_count BIGINT,
    followers_following_ratio DOUBLE,
    posts_per_day DOUBLE,
    account_age_days BIGINT,
    bio_length BIGINT,
    
    -- Binary features (as INTEGER for ML)
    has_profile_image INTEGER,
    has_bio INTEGER,
    has_url INTEGER,
    verified INTEGER,
    default_profile INTEGER,
    default_profile_image INTEGER,
    
    -- Log transforms
    log_followers_count DOUBLE,
    log_following_count DOUBLE,
    log_post_count DOUBLE,
    
    -- Derived metrics
    followers_per_day DOUBLE,
    engagement_score DOUBLE,
    
    -- Category encodings
    ff_ratio_category INTEGER,
    suspicious_ff_ratio INTEGER,
    posts_per_day_category INTEGER,
    account_maturity_category INTEGER,
    
    -- Scores
    profile_completeness_score DOUBLE,
    fake_follower_indicator DOUBLE,
    follower_engagement_ratio DOUBLE,
    
    -- Interaction features
    followers_squared DOUBLE,
    following_followers_interaction DOUBLE,
    posts_followers_interaction DOUBLE,
    
    -- Target label
    label INTEGER,                -- 0=trustworthy, 1=untrustworthy
    
    -- Metadata
    _source VARCHAR,
    _processed_at VARCHAR
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/ml_trust_features_engineered/'
);


-- AGGREGATE TABLES
-- ================

-- 8. agg_platform_kpi (2 records)
-- Platform-level KPIs
DROP TABLE IF EXISTS minio.kol_gold.agg_platform_kpi;
CREATE TABLE minio.kol_gold.agg_platform_kpi (
    platform VARCHAR,
    total_kols BIGINT,
    total_followers BIGINT,
    total_posts BIGINT,
    avg_engagement_rate DOUBLE,
    verified_ratio DOUBLE,
    untrustworthy_ratio DOUBLE,
    report_date VARCHAR
) WITH (
    format = 'PARQUET',
    external_location = 's3a://kol-platform/gold/agg_platform_kpi/'
);


-- ============================================================================
-- VERIFICATION QUERIES
-- ============================================================================
-- Run these to verify tables are created and accessible:

-- SHOW SCHEMAS FROM minio;
-- SHOW TABLES FROM minio.kol_bronze;
-- SHOW TABLES FROM minio.kol_silver;
-- SHOW TABLES FROM minio.kol_gold;

-- SELECT COUNT(*) FROM minio.kol_bronze.twitter_human_bots;
-- SELECT COUNT(*) FROM minio.kol_silver.kol_trust_features;
-- SELECT COUNT(*) FROM minio.kol_gold.ml_trust_features_engineered;
