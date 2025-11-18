"""
KOL Analytics - Data Ingestion Package
========================================

Phase 1: Raw data ingestion into Bronze layer.

Modules:
- config: Environment configuration and path builders
- minio_client: MinIO/S3 client utilities
- batch_ingest: CLI for batch ingestion jobs
- sources/: Data source collectors (Wikipedia, YouTube, Weibo)
"""

__version__ = "1.0.0"
