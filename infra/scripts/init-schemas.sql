-- ============================================================================
-- Database Schema Initialization
-- ============================================================================
-- This script initializes the necessary database schemas for the KOL platform
-- Run with: docker exec -i base-postgres psql -U admin -d metastore < init-schemas.sql
-- ============================================================================

-- Switch to metastore database
\c metastore;

-- Create schema for Hive Metastore (if not exists)
CREATE SCHEMA IF NOT EXISTS hive;

-- Switch to airflow database
\c airflow;

-- Airflow schema is created automatically by airflow-init container
-- This is just for reference

-- Switch to mlflow database
\c mlflow;

-- MLflow schema is created automatically by MLflow server
-- This is just for reference

-- Create extensions if needed
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

\echo 'Database schemas initialized successfully'
