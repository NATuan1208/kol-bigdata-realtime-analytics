"""
Integration Tests for Batch Ingestion CLI - Phase 1B
====================================================

Tests the batch_ingest.py CLI tool with Phase 1B multi-day/multi-region parameters.

Test Coverage:
- CLI argument parsing (--days-back, --regions)
- Multi-day ingestion orchestration
- Multi-region collection
- MinIO upload functionality
- Dry-run mode

Run Tests:
----------
# Run all batch ingestion tests
pytest tests/integration/test_batch_ingestion.py -v

# Run with output
pytest tests/integration/test_batch_ingestion.py -v -s

Requirements:
- YOUTUBE_API_KEY environment variable
- MinIO running on localhost:9000
- pytest installed
"""

import os
import sys
import subprocess
from datetime import datetime

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


class TestBatchIngestionCLI:
    """
    Integration tests for batch_ingest.py CLI tool.
    
    Tests the command-line interface with Phase 1B parameters.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup before each test."""
        self.api_key = os.getenv('YOUTUBE_API_KEY')
        if not self.api_key:
            pytest.skip("YOUTUBE_API_KEY not found in environment")
        
        self.cli_path = "ingestion/batch_ingest.py"
    
    def run_cli(self, args: list) -> subprocess.CompletedProcess:
        """
        Run batch_ingest.py with given arguments.
        
        Args:
            args: List of CLI arguments
            
        Returns:
            CompletedProcess with stdout/stderr
        """
        env = os.environ.copy()
        env['YOUTUBE_API_KEY'] = self.api_key
        env['PYTHONIOENCODING'] = 'utf-8'  # Fix Windows encoding
        
        cmd = ["python", self.cli_path] + args
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',  # Force UTF-8
            errors='replace',  # Replace unmappable chars
            env=env
        )
        
        return result
    
    def test_list_sources(self):
        """Test --list-sources command."""
        result = self.run_cli(["--list-sources"])
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "youtube_trending" in result.stdout
        assert "wikipedia_backlinko" in result.stdout
        assert "weibo_dataset" in result.stdout
        assert "AVAILABLE DATA SOURCES" in result.stdout
    
    def test_dry_run_mode(self):
        """Test --dry-run mode (no upload)."""
        result = self.run_cli([
            "--source", "youtube_trending",
            "--days-back", "0",
            "--regions", "VN",
            "--limit", "5",
            "--dry-run"
        ])
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "DRY RUN" in result.stdout
        assert "Would upload" in result.stdout
        assert "✅ Batch ingestion complete" in result.stdout
    
    def test_phase1b_multi_day_parameter(self):
        """Test --days-back parameter."""
        result = self.run_cli([
            "--source", "youtube_trending",
            "--days-back", "1",  # 2 days total (today + yesterday)
            "--regions", "VN",
            "--limit", "5",
            "--dry-run"
        ])
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "Days back: 1" in result.stdout
        assert "Estimated API calls: 2" in result.stdout
    
    def test_phase1b_multi_region_parameter(self):
        """Test --regions parameter with multiple regions."""
        result = self.run_cli([
            "--source", "youtube_trending",
            "--days-back", "0",
            "--regions", "VN", "US", "KR",  # 3 regions
            "--limit", "5",
            "--dry-run"
        ])
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "Regions: VN, US, KR" in result.stdout
        assert "Estimated API calls: 3" in result.stdout
    
    def test_phase1b_combined_parameters(self):
        """Test combined --days-back and --regions."""
        result = self.run_cli([
            "--source", "youtube_trending",
            "--days-back", "2",  # 3 days
            "--regions", "VN", "US",  # 2 regions
            "--limit", "10",
            "--dry-run"
        ])
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "Days back: 2" in result.stdout
        assert "Regions: VN, US" in result.stdout
        assert "Estimated API calls: 6" in result.stdout  # 3 days × 2 regions
        
        # Check deduplication
        stdout_lines = result.stdout.split('\n')
        success_line = [l for l in stdout_lines if "SUCCESS: Collected" in l][0]
        # Should have some records (may be less than 60 due to dedup)
        assert "Collected" in success_line
    
    @pytest.mark.slow
    def test_phase1b_with_upload(self):
        """
        Test actual upload to MinIO (Phase 1B).
        
        WARNING: Makes 2 API calls and uploads to MinIO.
        """
        result = self.run_cli([
            "--source", "youtube_trending",
            "--days-back", "0",
            "--regions", "VN",
            "--limit", "10",
            "--upload"  # Real upload
        ])
        
        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "✅ Successfully uploaded youtube_trending" in result.stdout
        assert "s3://kol-platform/bronze/raw/youtube_trending" in result.stdout
        assert "Records: 10" in result.stdout
        assert "Size:" in result.stdout
    
    def test_invalid_source(self):
        """Test with invalid source name."""
        result = self.run_cli([
            "--source", "invalid_source",
            "--limit", "5"
        ])
        
        # Should exit with error
        assert result.returncode != 0


class TestBatchIngestionConfiguration:
    """
    Tests for CLI configuration display.
    """
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup before each test."""
        self.api_key = os.getenv('YOUTUBE_API_KEY')
        if not self.api_key:
            pytest.skip("YOUTUBE_API_KEY not found")
    
    def test_configuration_display(self):
        """Verify configuration section displays correctly."""
        env = os.environ.copy()
        env['YOUTUBE_API_KEY'] = self.api_key
        env['PYTHONIOENCODING'] = 'utf-8'
        
        result = subprocess.run(
            ["python", "ingestion/batch_ingest.py",
             "--source", "youtube_trending",
             "--days-back", "7",
             "--regions", "VN", "US", "KR", "JP", "BR",
             "--limit", "20",
             "--dry-run"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env
        )
        
        assert result.returncode == 0
        assert "⚙️  CONFIGURATION" in result.stdout
        assert "MinIO Endpoint: http://localhost:9000" in result.stdout
        assert "MinIO Bucket: kol-platform" in result.stdout
        assert "Days back: 7 days" in result.stdout
        assert "Regions: VN, US, KR, JP, BR" in result.stdout


if __name__ == "__main__":
    pytest.main([__file__, '-v', '-s'])
