"""
KOL Analytics - Configuration Module
======================================

Reads environment variables from .env.kol and provides:
- MinIO/S3 connection settings
- Bucket and path conventions
- Helper functions for building S3 keys

Environment variables (from .env.kol):
- MINIO_ENDPOINT: MinIO server endpoint (e.g., http://localhost:9000)
- MINIO_ROOT_USER: MinIO access key (default: minioadmin)
- MINIO_ROOT_PASSWORD: MinIO secret key
- MINIO_BUCKET: Target bucket (default: kol-platform)
"""

import os
from datetime import datetime
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load .env.kol from project root
env_path = Path(__file__).parent.parent / '.env.kol'
load_dotenv(dotenv_path=env_path)


class Config:
    """Configuration for KOL ingestion pipeline."""
    
    # MinIO/S3 settings
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "http://sme-minio:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "kol-platform")
    
    # Path conventions
    BRONZE_RAW_PREFIX: str = "bronze/raw"
    
    # Supported data sources
    SOURCES = {
        "wikipedia_backlinko": "wikipedia_backlinko",
        "youtube_trending": "youtube_trending",
        "instagram_influencer": "instagram_influencer",  # Phase 1B: Instagram dataset
        "short_video_trends": "short_video_trends",  # Phase 1B: YouTube Shorts + TikTok
    }
    
    @staticmethod
    def validate() -> None:
        """
        Validates that required environment variables are set.
        Raises ValueError if critical configs are missing.
        """
        if not Config.MINIO_ENDPOINT:
            raise ValueError("MINIO_ENDPOINT is not set")
        if not Config.MINIO_ACCESS_KEY:
            raise ValueError("MINIO_ROOT_USER (access key) is not set")
        if not Config.MINIO_SECRET_KEY:
            raise ValueError("MINIO_ROOT_PASSWORD (secret key) is not set")
        if not Config.MINIO_BUCKET:
            raise ValueError("MINIO_BUCKET is not set")
    
    @staticmethod
    def get_minio_endpoint_no_scheme() -> str:
        """Returns MinIO endpoint without http:// or https:// prefix."""
        endpoint = Config.MINIO_ENDPOINT
        endpoint = endpoint.replace("http://", "").replace("https://", "")
        return endpoint


def build_s3_raw_path(
    source: str,
    date: Optional[datetime] = None,
    extension: str = "jsonl"
) -> str:
    """
    Builds S3 key for raw data files following the convention:
    bronze/raw/{source}/dt=YYYY-MM-DD/{source}_HHMMSS.{extension}
    
    Args:
        source: Data source name (e.g., 'youtube_trending')
        date: Date for partitioning (default: current datetime)
        extension: File extension (default: 'jsonl')
    
    Returns:
        S3 key string (e.g., 'bronze/raw/youtube_trending/dt=2025-11-16/youtube_trending_153045.jsonl')
    
    Example:
        >>> build_s3_raw_path("youtube_trending")
        'bronze/raw/youtube_trending/dt=2025-11-16/youtube_trending_153045.jsonl'
    """
    if date is None:
        date = datetime.utcnow()
    
    # Validate source
    if source not in Config.SOURCES:
        raise ValueError(
            f"Invalid source '{source}'. Must be one of: {list(Config.SOURCES.keys())}"
        )
    
    # Build path components
    date_partition = date.strftime("dt=%Y-%m-%d")
    timestamp = date.strftime("%H%M%S")
    filename = f"{source}_{timestamp}.{extension}"
    
    # Combine into full S3 key
    s3_key = f"{Config.BRONZE_RAW_PREFIX}/{source}/{date_partition}/{filename}"
    
    return s3_key


def build_s3_raw_prefix(source: str, date: Optional[datetime] = None) -> str:
    """
    Builds S3 prefix for reading all files from a source on a specific date.
    
    Args:
        source: Data source name
        date: Date for partition (default: current date)
    
    Returns:
        S3 prefix (e.g., 'bronze/raw/youtube_trending/dt=2025-11-16/')
    
    Example:
        >>> build_s3_raw_prefix("youtube_trending")
        'bronze/raw/youtube_trending/dt=2025-11-16/'
    """
    if date is None:
        date = datetime.utcnow()
    
    date_partition = date.strftime("dt=%Y-%m-%d")
    prefix = f"{Config.BRONZE_RAW_PREFIX}/{source}/{date_partition}/"
    
    return prefix


def get_s3_uri(key: str) -> str:
    """
    Converts S3 key to full s3a:// URI for Spark.
    
    Args:
        key: S3 object key
    
    Returns:
        Full s3a:// URI
    
    Example:
        >>> get_s3_uri("bronze/raw/youtube_trending/dt=2025-11-16/file.jsonl")
        's3a://kol-platform/bronze/raw/youtube_trending/dt=2025-11-16/file.jsonl'
    """
    return f"s3a://{Config.MINIO_BUCKET}/{key}"


if __name__ == "__main__":
    # Self-test
    print("=== KOL Ingestion Configuration ===\n")
    
    try:
        Config.validate()
        print("✅ Configuration validated successfully\n")
    except ValueError as e:
        print(f"❌ Configuration error: {e}\n")
    
    print(f"MinIO Endpoint: {Config.MINIO_ENDPOINT}")
    print(f"MinIO Bucket: {Config.MINIO_BUCKET}")
    print(f"Access Key: {Config.MINIO_ACCESS_KEY[:4]}***")
    print(f"\nSupported sources: {list(Config.SOURCES.keys())}\n")
    
    # Test path building
    print("=== Path Building Examples ===\n")
    test_date = datetime(2025, 11, 16, 15, 30, 45)
    
    for source in Config.SOURCES.keys():
        path = build_s3_raw_path(source, date=test_date)
        prefix = build_s3_raw_prefix(source, date=test_date)
        uri = get_s3_uri(path)
        
        print(f"Source: {source}")
        print(f"  Path: {path}")
        print(f"  Prefix: {prefix}")
        print(f"  URI: {uri}")
        print()
