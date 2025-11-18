"""
Integration Tests for YouTube Trending Collector - Phase 1B
===========================================================

Tests multi-day and multi-region ingestion capabilities introduced in Phase 1B.

Test Coverage:
- Single region, single day (baseline)
- Single region, multi-day (temporal scaling)
- Multi-region, single day (geographic scaling)
- Multi-region, multi-day (full Phase 1B capability)
- API quota management and rate limiting

Run Tests:
----------
# Run all Phase 1B tests
pytest tests/integration/test_youtube_phase1b.py -v

# Run specific test
pytest tests/integration/test_youtube_phase1b.py::TestYouTubePhase1B::test_single_region_multi_day -v

# Run with output
pytest tests/integration/test_youtube_phase1b.py -v -s

Requirements:
- YOUTUBE_API_KEY environment variable set
- Active internet connection
- pytest installed: pip install pytest
"""

import os
import sys
import logging
from datetime import datetime
from typing import List, Dict, Any

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from ingestion.sources import youtube_trending

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TestYouTubePhase1B:
    """
    Integration tests for Phase 1B YouTube trending collector.
    
    Phase 1B Features:
    - Multi-day ingestion: days_back parameter
    - Multi-region support: region_codes list
    - Deduplication: Unique video_id tracking
    - Rate limiting: Configurable delay between API calls
    """
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup before each test, cleanup after."""
        self.api_key = os.getenv('YOUTUBE_API_KEY')
        
        # Skip tests if no API key
        if not self.api_key:
            pytest.skip("YOUTUBE_API_KEY not found in environment")
        
        logger.info("\n" + "=" * 70)
        logger.info(f"🧪 TEST SETUP: {self._testMethodName}")
        logger.info("=" * 70)
        
        yield  # Run test
        
        logger.info("=" * 70)
        logger.info(f"✅ TEST COMPLETE: {self._testMethodName}")
        logger.info("=" * 70 + "\n")
    
    @property
    def _testMethodName(self):
        """Get current test method name."""
        return self._request.node.name if hasattr(self, '_request') else "unknown"
    
    @pytest.fixture(autouse=True)
    def inject_request(self, request):
        """Inject pytest request fixture."""
        self._request = request
    
    def test_single_region_single_day(self):
        """
        Test 1: Baseline - Single region, today only.
        
        Expected:
        - ~50 videos from VN region
        - 1 API call
        - All records have region_code='VN'
        """
        logger.info("📝 Test Case: Single region (VN), today only")
        logger.info("Expected: ~50 videos, 1 API call")
        
        records = youtube_trending.collect(
            api_key=self.api_key,
            region_codes=['VN'],
            days_back=0,  # Today only
            limit=50,
            rate_limit_delay=0.5
        )
        
        # Assertions
        assert len(records) > 0, "Should collect at least 1 video"
        assert len(records) <= 50, "Should not exceed limit"
        
        # Verify structure
        sample = records[0]
        assert 'kol_id' in sample
        assert 'platform' in sample
        assert sample['platform'] == 'youtube'
        assert 'payload' in sample
        assert 'region_code' in sample['payload']
        assert sample['payload']['region_code'] == 'VN'
        
        logger.info(f"✅ Collected {len(records)} videos from VN")
        logger.info(f"   Sample: {sample['payload']['title'][:60]}...")
    
    def test_single_region_multi_day(self):
        """
        Test 2: Temporal scaling - Single region, multiple days.
        
        Expected:
        - Videos from VN over 2 days
        - 2 API calls (1 per day)
        - Deduplication may reduce total count
        """
        logger.info("📝 Test Case: Single region (VN), 2 days back")
        logger.info("Expected: 2 API calls, potential duplicates removed")
        
        records = youtube_trending.collect(
            api_key=self.api_key,
            region_codes=['VN'],
            days_back=2,  # Past 3 days (0, 1, 2)
            limit=20,
            rate_limit_delay=0.5
        )
        
        # Assertions
        assert len(records) > 0, "Should collect videos"
        assert len(records) <= 60, "Max 20 per day × 3 days"
        
        # Check date variety
        dates = set(r['payload']['trending_date'] for r in records)
        assert len(dates) >= 1, "Should have at least 1 trending date"
        
        logger.info(f"✅ Collected {len(records)} unique videos")
        logger.info(f"   Trending dates: {sorted(dates)}")
    
    def test_multi_region_single_day(self):
        """
        Test 3: Geographic scaling - Multiple regions, today only.
        
        Expected:
        - Videos from VN and US
        - 2 API calls (1 per region)
        - Global trending videos may appear in both regions
        """
        logger.info("📝 Test Case: Multi-region (VN, US), today only")
        logger.info("Expected: 2 API calls, potential cross-region duplicates")
        
        records = youtube_trending.collect(
            api_key=self.api_key,
            region_codes=['VN', 'US'],
            days_back=0,  # Today only
            limit=20,
            rate_limit_delay=0.5
        )
        
        # Assertions
        assert len(records) > 0, "Should collect videos"
        assert len(records) <= 40, "Max 20 per region × 2 regions"
        
        # Check region variety
        regions = set(r['payload']['region_code'] for r in records)
        assert len(regions) >= 1, "Should have at least 1 region"
        
        logger.info(f"✅ Collected {len(records)} unique videos")
        logger.info(f"   Regions covered: {sorted(regions)}")
    
    @pytest.mark.slow
    def test_multi_region_multi_day_large_scale(self):
        """
        Test 4: Full Phase 1B - Multiple regions, multiple days.
        
        WARNING: This test makes 9 API calls (900 quota units).
        
        Expected:
        - Videos from VN, US, KR over 3 days
        - 9 API calls (3 regions × 3 days)
        - 100-150 unique videos after deduplication
        """
        logger.info("📝 Test Case: Multi-region (VN, US, KR), 3 days back")
        logger.info("⚠️  WARNING: This test will use 9 API calls (900 quota units)")
        logger.info("Expected: ~145 unique videos after deduplication")
        
        # User confirmation for large test
        if os.getenv('CI') != 'true':  # Skip confirmation in CI
            response = input("\nProceed with 9 API calls? (y/n): ")
            if response.lower() != 'y':
                pytest.skip("User cancelled large-scale test")
        
        records = youtube_trending.collect(
            api_key=self.api_key,
            region_codes=['VN', 'US', 'KR'],
            days_back=2,  # Past 3 days (0, 1, 2)
            limit=50,
            rate_limit_delay=1.0
        )
        
        # Assertions
        assert len(records) >= 100, "Should collect at least 100 unique videos"
        assert len(records) <= 450, "Max 50 per region per day × 3 × 3"
        
        # Check variety
        regions = set(r['payload']['region_code'] for r in records)
        dates = set(r['payload']['trending_date'] for r in records)
        
        assert len(regions) >= 2, "Should have at least 2 regions"
        assert len(dates) >= 2, "Should have at least 2 trending dates"
        
        logger.info(f"✅ Collected {len(records)} unique videos")
        logger.info(f"   Regions: {sorted(regions)}")
        logger.info(f"   Date range: {min(dates)} to {max(dates)}")
        
        # Show sample
        sample = records[0]
        logger.info(f"\n🎬 Sample Video:")
        logger.info(f"   Title: {sample['payload']['title'][:60]}...")
        logger.info(f"   Region: {sample['payload']['region_code']}")
        logger.info(f"   Views: {sample['payload']['view_count']:,}")
    
    def test_deduplication_logic(self):
        """
        Test 5: Verify deduplication across regions.
        
        Expected:
        - Same popular videos may trend in multiple regions
        - Deduplication should keep only unique video_id
        """
        logger.info("📝 Test Case: Deduplication across regions")
        
        records = youtube_trending.collect(
            api_key=self.api_key,
            region_codes=['US', 'GB'],  # Similar English-speaking markets
            days_back=0,
            limit=30,
            rate_limit_delay=0.5
        )
        
        # Extract video IDs
        video_ids = [r['payload']['video_id'] for r in records]
        unique_video_ids = set(video_ids)
        
        # Assertions
        assert len(video_ids) == len(unique_video_ids), \
            "Deduplication should prevent duplicate video_ids"
        
        logger.info(f"✅ Verified {len(records)} unique videos")
        logger.info(f"   No duplicates found")
    
    def test_rate_limiting(self):
        """
        Test 6: Verify rate limiting delays.
        
        Expected:
        - Multiple API calls should have delays between them
        - Total execution time should reflect rate_limit_delay
        """
        import time
        
        logger.info("📝 Test Case: Rate limiting verification")
        
        start_time = time.time()
        
        records = youtube_trending.collect(
            api_key=self.api_key,
            region_codes=['VN', 'US'],
            days_back=0,
            limit=10,
            rate_limit_delay=1.0  # 1 second delay
        )
        
        elapsed = time.time() - start_time
        
        # Should take at least 1 second (1 delay between 2 calls)
        assert elapsed >= 1.0, "Rate limiting should add delays"
        
        logger.info(f"✅ Rate limiting working")
        logger.info(f"   Execution time: {elapsed:.2f}s")
        logger.info(f"   Expected: ≥1.0s for 2 API calls with 1s delay")


class TestYouTubeDataStructure:
    """
    Unit tests for data structure validation.
    
    Tests the canonical format of normalized records.
    """
    
    def test_canonical_format(self):
        """Verify normalized record has correct structure."""
        sample_video = {
            "video_id": "test123",
            "channel_id": "channel456",
            "channel_title": "Test Channel",
            "title": "Test Video",
            "category_id": "10",
            "publish_time": "2025-11-17T10:00:00Z",
            "trending_date": "2025-11-17",
            "region_code": "VN",
            "view_count": 1000000,
            "likes": 50000,
            "dislikes": 0,
            "comment_count": 5000,
            "tags": "test|video",
            "description": "Test description"
        }
        
        record = youtube_trending.normalize_youtube_record(sample_video)
        
        # Assert canonical structure
        assert 'kol_id' in record
        assert 'platform' in record
        assert 'source' in record
        assert 'payload' in record
        assert 'ingest_ts' in record
        
        assert record['kol_id'] == 'channel456'
        assert record['platform'] == 'youtube'
        assert record['source'] == 'youtube_trending'
        
        # Verify payload
        payload = record['payload']
        assert payload['video_id'] == 'test123'
        assert payload['region_code'] == 'VN'
        assert payload['view_count'] == 1000000
        
        logger.info("✅ Canonical format validated")


# Pytest configuration
@pytest.fixture(scope="session", autouse=True)
def test_session_setup():
    """Setup for entire test session."""
    logger.info("\n" + "=" * 70)
    logger.info("🚀 STARTING PHASE 1B YOUTUBE INTEGRATION TESTS")
    logger.info("=" * 70)
    logger.info(f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    api_key = os.getenv('YOUTUBE_API_KEY')
    if api_key:
        logger.info("✅ YOUTUBE_API_KEY found")
    else:
        logger.warning("⚠️  YOUTUBE_API_KEY not found - tests will be skipped")
    
    logger.info("=" * 70 + "\n")
    
    yield
    
    logger.info("\n" + "=" * 70)
    logger.info("✅ PHASE 1B YOUTUBE INTEGRATION TESTS COMPLETE")
    logger.info("=" * 70 + "\n")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, '-v', '-s'])
