-- ============================================================================
-- KOL Analytics - Bronze Layer DDL (Trino Compatible)
-- ============================================================================

USE kol_lake.kol_bronze;

-- Table 1: YouTube Trending
CREATE TABLE IF NOT EXISTS raw_youtube_trending (
    kol_id VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    payload VARCHAR,
    ingest_ts TIMESTAMP(6) WITH TIME ZONE,
    dt DATE
)
WITH (
    format = 'PARQUET',
    location = 's3a://kol-platform/bronze/tables/raw_youtube_trending/',
    partitioning = ARRAY['dt']
);

-- Table 2: Wikipedia KOL Rankings
CREATE TABLE IF NOT EXISTS raw_wikipedia_backlinko (
    kol_id VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    payload VARCHAR,
    ingest_ts TIMESTAMP(6) WITH TIME ZONE,
    dt DATE
)
WITH (
    format = 'PARQUET',
    location = 's3a://kol-platform/bronze/tables/raw_wikipedia_backlinko/',
    partitioning = ARRAY['dt']
);

-- Table 3: Weibo Posts
CREATE TABLE IF NOT EXISTS raw_weibo_dataset (
    kol_id VARCHAR,
    platform VARCHAR,
    source VARCHAR,
    payload VARCHAR,
    ingest_ts TIMESTAMP(6) WITH TIME ZONE,
    dt DATE
)
WITH (
    format = 'PARQUET',
    location = 's3a://kol-platform/bronze/tables/raw_weibo_dataset/',
    partitioning = ARRAY['dt']
);

-- Verify
SHOW TABLES;
