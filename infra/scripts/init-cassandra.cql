-- ============================================================================
-- Cassandra Keyspace and Tables Initialization
-- ============================================================================
-- This script creates the Cassandra keyspace and tables for KOL metrics
-- Run with: docker exec -i kol-cassandra cqlsh < init-cassandra.cql
-- ============================================================================

-- Create keyspace
CREATE KEYSPACE IF NOT EXISTS kol_metrics
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE kol_metrics;

-- Table: kol_realtime_metrics
-- Stores real-time windowed metrics for KOLs
CREATE TABLE IF NOT EXISTS kol_realtime_metrics (
    kol_id text,
    bucket_ts timestamp,
    window_duration int,
    metric_type text,
    metric_value double,
    metadata map<text, text>,
    updated_at timestamp,
    PRIMARY KEY ((kol_id), bucket_ts, metric_type)
) WITH CLUSTERING ORDER BY (bucket_ts DESC, metric_type ASC)
  AND compaction = {'class': 'TimeWindowCompactionStrategy'}
  AND default_time_to_live = 2592000;  -- 30 days

-- Table: campaign_performance
-- Stores campaign performance metrics
CREATE TABLE IF NOT EXISTS campaign_performance (
    campaign_id text,
    kol_id text,
    bucket_ts timestamp,
    impressions bigint,
    clicks bigint,
    conversions bigint,
    revenue double,
    ctr double,
    cvr double,
    roas double,
    updated_at timestamp,
    PRIMARY KEY ((campaign_id), bucket_ts, kol_id)
) WITH CLUSTERING ORDER BY (bucket_ts DESC, kol_id ASC)
  AND compaction = {'class': 'TimeWindowCompactionStrategy'}
  AND default_time_to_live = 7776000;  -- 90 days

-- Table: trust_scores
-- Stores trust score history
CREATE TABLE IF NOT EXISTS trust_scores (
    kol_id text,
    scored_at timestamp,
    trust_score double,
    score_components map<text, double>,
    anomaly_flags set<text>,
    model_version text,
    PRIMARY KEY ((kol_id), scored_at)
) WITH CLUSTERING ORDER BY (scored_at DESC)
  AND default_time_to_live = 31536000;  -- 365 days

-- Table: success_predictions
-- Stores success forecast predictions
CREATE TABLE IF NOT EXISTS success_predictions (
    kol_id text,
    campaign_id text,
    predicted_at timestamp,
    forecast_horizon int,  -- hours ahead
    predicted_value double,
    prediction_type text,  -- 'clicks', 'conversions', 'revenue'
    confidence_lower double,
    confidence_upper double,
    model_version text,
    PRIMARY KEY ((kol_id, campaign_id), predicted_at, prediction_type)
) WITH CLUSTERING ORDER BY (predicted_at DESC, prediction_type ASC)
  AND default_time_to_live = 7776000;  -- 90 days

-- Table: alerts
-- Stores alert events
CREATE TABLE IF NOT EXISTS alerts (
    alert_id uuid,
    kol_id text,
    alert_type text,
    severity text,  -- 'low', 'medium', 'high', 'critical'
    message text,
    metadata map<text, text>,
    triggered_at timestamp,
    acknowledged boolean,
    acknowledged_at timestamp,
    PRIMARY KEY ((kol_id), triggered_at, alert_id)
) WITH CLUSTERING ORDER BY (triggered_at DESC, alert_id ASC)
  AND default_time_to_live = 7776000;  -- 90 days

-- Create secondary indexes
CREATE INDEX IF NOT EXISTS idx_alerts_type ON alerts (alert_type);
CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts (severity);
CREATE INDEX IF NOT EXISTS idx_trust_model ON trust_scores (model_version);
CREATE INDEX IF NOT EXISTS idx_pred_model ON success_predictions (model_version);

-- Display created tables
DESCRIBE TABLES;

-- Display schema
DESCRIBE KEYSPACE kol_metrics;
