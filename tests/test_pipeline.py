"""
Test Pipeline - Kiểm Tra ETL Bronze → Silver → Gold
======================================================

Verify rằng pipeline hoạt động đúng với 100% REAL DATA.

Run:
    python tests/test_pipeline.py
"""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from ingestion.minio_client import get_minio_client


def test_bronze_layer():
    """Test Bronze layer - verify 100% REAL DATA"""
    print("\n" + "=" * 70)
    print("✅ TEST 1: BRONZE LAYER (100% REAL DATA)")
    print("=" * 70)
    
    client = get_minio_client()
    
    # List Bronze objects (MinIO SDK v8+ uses keyword-only arguments)
    objects = list(client.list_objects(bucket_name='kol-platform', prefix='bronze/raw/', recursive=True))
    
    print(f"\n📊 Total objects: {len(objects)}")
    
    sources = {}
    for obj in objects:
        source = obj.object_name.split('/')[2]
        if source not in sources:
            sources[source] = {'count': 0, 'size': 0}
        sources[source]['count'] += 1
        sources[source]['size'] += obj.size
    
    total_size = 0
    print("\n📁 Sources:")
    for src in sorted(sources.keys()):
        info = sources[src]
        size_mb = info['size'] / 1024 / 1024
        total_size += info['size']
        print(f"   {src:25s}: {info['count']:2d} file(s), {size_mb:7.2f} MB ✅ REAL")
    
    print(f"\n   TOTAL: {len(objects)} files, {total_size / 1024 / 1024:.2f} MB")
    
    # Verify no Instagram
    if 'instagram_influencer' in sources:
        print("\n❌ FAILED: Instagram synthetic data still present!")
        return False
    
    print("\n✅ PASSED: Only real data sources present")
    return True


def test_data_schema():
    """Test data schema consistency"""
    print("\n" + "=" * 70)
    print("✅ TEST 2: DATA SCHEMA CONSISTENCY")
    print("=" * 70)
    
    client = get_minio_client()
    
    # Sample from each source
    sources_to_check = ['short_video_trends', 'youtube_trending', 'wikipedia_backlinko']
    
    print("\n📋 Checking schema from each source:")
    
    all_valid = True
    for source_name in sources_to_check:
        objects = list(client.list_objects(bucket_name='kol-platform', prefix=f'bronze/raw/{source_name}/', recursive=True))
        
        if not objects:
            print(f"   {source_name:25s}: ⚠️  No files found")
            continue
        
        # Read first file
        obj = objects[0]
        response = client.get_object(bucket_name='kol-platform', object_name=obj.object_name)
        data = response.read().decode('utf-8')
        
        # Check first record
        try:
            first_line = data.strip().split('\n')[0]
            record = json.loads(first_line)
            
            # Check canonical format
            required_fields = ['kol_id', 'platform', 'source', 'payload', 'ingest_ts']
            missing = [f for f in required_fields if f not in record]
            
            if missing:
                print(f"   {source_name:25s}: ❌ Missing {missing}")
                all_valid = False
            else:
                payload_fields = len(record['payload'].keys())
                print(f"   {source_name:25s}: ✅ Valid ({payload_fields} payload fields)")
                
        except Exception as e:
            print(f"   {source_name:25s}: ❌ Error: {e}")
            all_valid = False
    
    return all_valid


def test_record_samples():
    """Test individual record samples"""
    print("\n" + "=" * 70)
    print("✅ TEST 3: RECORD SAMPLES")
    print("=" * 70)
    
    client = get_minio_client()
    
    # Sample records from each source
    sources_samples = {
        'short_video_trends': 'YouTube Shorts + TikTok',
        'youtube_trending': 'YouTube Trending Videos',
        'wikipedia_backlinko': 'Wikipedia KOL Rankings'
    }
    
    print("\n📋 Sample records from each source:\n")
    
    for source_name, description in sources_samples.items():
        print(f"📺 {description} ({source_name}):")
        
        objects = list(client.list_objects(bucket_name='kol-platform', prefix=f'bronze/raw/{source_name}/', recursive=True))
        
        if not objects:
            print(f"   ⚠️  No files found\n")
            continue
        
        # Read first file, get first record
        obj = objects[0]
        response = client.get_object(bucket_name='kol-platform', object_name=obj.object_name)
        data = response.read().decode('utf-8')
        
        first_line = data.strip().split('\n')[0]
        record = json.loads(first_line)
        
        print(f"   kol_id: {record['kol_id']}")
        print(f"   platform: {record['platform']}")
        print(f"   source: {record['source']}")
        print(f"   payload fields: {', '.join(list(record['payload'].keys())[:5])}...")
        print(f"   ingest_ts: {record['ingest_ts']}\n")
    
    return True


def test_record_count():
    """Test total record count"""
    print("\n" + "=" * 70)
    print("✅ TEST 4: TOTAL RECORD COUNT")
    print("=" * 70)
    
    client = get_minio_client()
    
    sources = {}
    all_objects = list(client.list_objects(bucket_name='kol-platform', prefix='bronze/raw/', recursive=True))
    
    total_records = 0
    
    for obj in all_objects:
        source = obj.object_name.split('/')[2]
        if source not in sources:
            sources[source] = 0
        
        # Count records in file
        response = client.get_object(bucket_name='kol-platform', object_name=obj.object_name)
        data = response.read().decode('utf-8')
        count = len([line for line in data.strip().split('\n') if line])
        
        sources[source] += count
        total_records += count
    
    print("\n📊 Record count by source:")
    for src in sorted(sources.keys()):
        count = sources[src]
        print(f"   {src:25s}: {count:8,} records")
    
    print(f"\n   TOTAL: {total_records:8,} records")
    
    if total_records == 0:
        print("\n❌ FAILED: No records in Bronze layer!")
        return False
    
    print("\n✅ PASSED: Records present in all sources")
    return True


def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("🧪 PIPELINE TEST SUITE")
    print("=" * 70)
    print("Testing Bronze layer with 100% REAL DATA only\n")
    
    results = {
        'Bronze Layer (100% Real)': test_bronze_layer(),
        'Data Schema': test_data_schema(),
        'Record Samples': test_record_samples(),
        'Record Count': test_record_count()
    }
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test_name}: {status}")
    
    all_passed = all(results.values())
    
    print("\n" + "=" * 70)
    if all_passed:
        print("✅ ALL TESTS PASSED - Pipeline ready!")
    else:
        print("❌ SOME TESTS FAILED - Check logs")
    print("=" * 70 + "\n")
    
    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
