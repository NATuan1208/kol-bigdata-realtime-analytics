"""
KOL Analytics - MinIO Client Module
=====================================

Provides reusable MinIO/S3 client utilities for uploading raw data files.

Key functions:
- get_minio_client(): Creates configured MinIO client
- upload_jsonl_records(): Uploads list of dicts as JSONL to MinIO
- upload_csv(): Uploads pandas DataFrame as CSV to MinIO
- list_objects(): Lists objects under a prefix
"""

import io
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

import pandas as pd
from minio import Minio
from minio.error import S3Error

# Handle both package import and direct execution
try:
    from .config import Config, build_s3_raw_path
except ImportError:
    from config import Config, build_s3_raw_path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_minio_client() -> Minio:
    """
    Creates and returns a configured MinIO client.
    
    Returns:
        Minio client instance
    
    Raises:
        ValueError: If configuration is invalid
    
    Example:
        >>> client = get_minio_client()
        >>> client.bucket_exists("kol-platform")
        True
    """
    Config.validate()
    
    # Extract endpoint without scheme
    endpoint = Config.get_minio_endpoint_no_scheme()
    
    # Determine if using secure connection (https)
    secure = Config.MINIO_ENDPOINT.startswith("https://")
    
    client = Minio(
        endpoint,
        access_key=Config.MINIO_ACCESS_KEY,
        secret_key=Config.MINIO_SECRET_KEY,
        secure=secure
    )
    
    logger.info(f"MinIO client created: endpoint={endpoint}, secure={secure}")
    
    return client


def upload_jsonl_records(
    source: str,
    records: List[Dict[str, Any]],
    date: Optional[datetime] = None
) -> str:
    """
    Uploads a list of records as JSONL (JSON Lines) to MinIO.
    
    Each record is written as one JSON object per line.
    Path follows convention: bronze/raw/{source}/dt=YYYY-MM-DD/{source}_HHMMSS.jsonl
    
    Args:
        source: Data source name (e.g., 'youtube_trending')
        records: List of dictionaries to upload
        date: Date for partitioning (default: current datetime)
    
    Returns:
        S3 key where the file was uploaded
    
    Raises:
        S3Error: If upload fails
    
    Example:
        >>> records = [
        ...     {"kol_id": "UC123", "platform": "youtube", "payload": {...}},
        ...     {"kol_id": "UC456", "platform": "youtube", "payload": {...}}
        ... ]
        >>> key = upload_jsonl_records("youtube_trending", records)
        >>> print(f"Uploaded {len(records)} records to {key}")
    """
    if not records:
        logger.warning(f"No records to upload for source: {source}")
        return ""
    
    # Build S3 key
    s3_key = build_s3_raw_path(source, date=date, extension="jsonl")
    
    # Convert records to JSONL format
    jsonl_content = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    jsonl_bytes = jsonl_content.encode("utf-8")
    
    # Upload to MinIO
    client = get_minio_client()
    
    try:
        # Ensure bucket exists
        if not client.bucket_exists(Config.MINIO_BUCKET):
            logger.error(f"Bucket '{Config.MINIO_BUCKET}' does not exist!")
            raise ValueError(f"Bucket '{Config.MINIO_BUCKET}' not found")
        
        # Upload object
        client.put_object(
            bucket_name=Config.MINIO_BUCKET,
            object_name=s3_key,
            data=io.BytesIO(jsonl_bytes),
            length=len(jsonl_bytes),
            content_type="application/x-ndjson"
        )
        
        logger.info(
            f"✅ Uploaded {len(records)} records to s3://{Config.MINIO_BUCKET}/{s3_key} "
            f"({len(jsonl_bytes)} bytes)"
        )
        
        # Return metadata dict for CLI
        return {
            's3_path': f"s3://{Config.MINIO_BUCKET}/{s3_key}",
            's3_key': s3_key,
            'records_count': len(records),
            'file_size_bytes': len(jsonl_bytes)
        }
        
    except S3Error as e:
        logger.error(f"Failed to upload to MinIO: {e}")
        raise


def upload_csv(
    source: str,
    df: pd.DataFrame,
    date: Optional[datetime] = None
) -> str:
    """
    Uploads a pandas DataFrame as CSV to MinIO.
    
    Path follows convention: bronze/raw/{source}/dt=YYYY-MM-DD/{source}_HHMMSS.csv
    
    Args:
        source: Data source name
        df: pandas DataFrame to upload
        date: Date for partitioning (default: current datetime)
    
    Returns:
        S3 key where the file was uploaded
    
    Raises:
        S3Error: If upload fails
    
    Example:
        >>> df = pd.DataFrame({"col1": [1, 2], "col2": ["a", "b"]})
        >>> key = upload_csv("youtube_trending", df)
    """
    if df.empty:
        logger.warning(f"Empty DataFrame for source: {source}")
        return ""
    
    # Build S3 key
    s3_key = build_s3_raw_path(source, date=date, extension="csv")
    
    # Convert DataFrame to CSV bytes
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_bytes = csv_buffer.getvalue().encode("utf-8")
    
    # Upload to MinIO
    client = get_minio_client()
    
    try:
        if not client.bucket_exists(Config.MINIO_BUCKET):
            raise ValueError(f"Bucket '{Config.MINIO_BUCKET}' not found")
        
        client.put_object(
            bucket_name=Config.MINIO_BUCKET,
            object_name=s3_key,
            data=io.BytesIO(csv_bytes),
            length=len(csv_bytes),
            content_type="text/csv"
        )
        
        logger.info(
            f"✅ Uploaded CSV with {len(df)} rows to s3://{Config.MINIO_BUCKET}/{s3_key} "
            f"({len(csv_bytes)} bytes)"
        )
        
        return s3_key
        
    except S3Error as e:
        logger.error(f"Failed to upload CSV to MinIO: {e}")
        raise


def list_objects(prefix: str, max_objects: int = 100) -> List[str]:
    """
    Lists objects in MinIO under a given prefix.
    
    Args:
        prefix: S3 prefix to list (e.g., 'bronze/raw/youtube_trending/')
        max_objects: Maximum number of objects to return
    
    Returns:
        List of object keys
    
    Example:
        >>> keys = list_objects("bronze/raw/youtube_trending/dt=2025-11-16/")
        >>> for key in keys:
        ...     print(key)
    """
    client = get_minio_client()
    
    try:
        objects = client.list_objects(
            bucket_name=Config.MINIO_BUCKET,
            prefix=prefix,
            recursive=True
        )
        
        keys = [obj.object_name for obj in objects][:max_objects]
        logger.info(f"Found {len(keys)} objects under prefix: {prefix}")
        
        return keys
        
    except S3Error as e:
        logger.error(f"Failed to list objects: {e}")
        return []


def get_object_size(key: str) -> int:
    """
    Gets the size of an object in bytes.
    
    Args:
        key: S3 object key
    
    Returns:
        Size in bytes, or -1 if object doesn't exist
    """
    client = get_minio_client()
    
    try:
        stat = client.stat_object(Config.MINIO_BUCKET, key)
        return stat.size
    except S3Error:
        return -1


if __name__ == "__main__":
    # Self-test
    print("=== MinIO Client Test ===\n")
    
    try:
        # Test client creation
        client = get_minio_client()
        print(f"✅ MinIO client created\n")
        
        # Test bucket existence
        exists = client.bucket_exists(Config.MINIO_BUCKET)
        print(f"Bucket '{Config.MINIO_BUCKET}' exists: {exists}\n")
        
        # Test upload with sample data
        test_records = [
            {
                "kol_id": "test_001",
                "platform": "youtube",
                "source": "test",
                "payload": {"name": "Test KOL 1", "followers": 10000},
                "ingest_ts": datetime.utcnow().isoformat()
            },
            {
                "kol_id": "test_002",
                "platform": "youtube",
                "source": "test",
                "payload": {"name": "Test KOL 2", "followers": 20000},
                "ingest_ts": datetime.utcnow().isoformat()
            }
        ]
        
        print("Testing JSONL upload...")
        key = upload_jsonl_records("youtube_trending", test_records)
        print(f"Uploaded to: {key}\n")
        
        # Verify size
        size = get_object_size(key)
        print(f"Object size: {size} bytes\n")
        
        print("✅ All tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
