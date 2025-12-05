"""
Product Tracker - Batch Job (MinIO/Iceberg Version)

Chức năng:
- Load products đã biết từ Bronze layer (MinIO Iceberg)
- Re-scrape sold_count cho từng product
- Tính sold_delta = sold_count_now - sold_count_last
- Lưu timeseries vào Silver layer (MinIO Iceberg)

Chạy trong Docker:
    docker exec -it kol-spark-master spark-submit \
        --master spark://spark-master:7077 \
        /opt/spark/work-dir/batch/feature_store/product_tracker.py
    
Chạy local (cần mount MinIO):
    python -m batch.feature_store.product_tracker --local
    
Schedule:
    - Recommend: 2-3 lần/ngày (6h, 14h, 22h)
    - Vì sold_count không cần real-time

Data flow:
    ┌─────────────────────────────────────────────────────────────────┐
    │                   PRODUCT TRACKER (MinIO)                        │
    │                                                                  │
    │  1. Load products từ Bronze (MinIO Iceberg)                      │
    │     SELECT DISTINCT product_id, product_url, seller_id, username │
    │     FROM kol.bronze.products                                     │
    │                                                                  │
    │  2. Load last sold_count từ Silver timeseries                    │
    │     SELECT product_id, sold_count, scraped_at                    │
    │     FROM kol.silver.product_sold_timeseries                      │
    │     WHERE rn = 1 (latest per product)                            │
    │                                                                  │
    │  3. Re-scrape sold_count từ TikTok Shop (Selenium)               │
    │                                                                  │
    │  4. Calculate delta                                              │
    │     sold_delta = sold_count_now - sold_count_last                │
    │                                                                  │
    │  5. Write to Silver (MinIO Iceberg)                              │
    │     INSERT INTO kol.silver.product_sold_timeseries               │
    └─────────────────────────────────────────────────────────────────┘

MinIO Buckets:
    - kol-bronze/iceberg/bronze/products     → Source products
    - kol-silver/iceberg/silver/product_sold_timeseries → Output timeseries
"""

import argparse
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Spark imports
try:
    from pyspark.sql import SparkSession, DataFrame
    from pyspark.sql.functions import (
        col, lit, current_timestamp, row_number
    )
    from pyspark.sql.window import Window
    from pyspark.sql.types import (
        StructType, StructField, StringType, IntegerType
    )
    SPARK_AVAILABLE = True
except ImportError:
    SPARK_AVAILABLE = False

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Auto-download ChromeDriver
try:
    from webdriver_manager.chrome import ChromeDriverManager
    from selenium.webdriver.chrome.service import Service
    USE_WEBDRIVER_MANAGER = True
except ImportError:
    USE_WEBDRIVER_MANAGER = False


# ============================================================================
# CONFIGURATION
# ============================================================================

# MinIO configuration
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://sme-minio:9000")
MINIO_ENDPOINT_LOCAL = os.getenv("MINIO_ENDPOINT_LOCAL", "http://localhost:9002")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minio")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minio123")

# Iceberg warehouse paths
BRONZE_WAREHOUSE = "s3a://kol-bronze/iceberg"
SILVER_WAREHOUSE = "s3a://kol-silver/iceberg"

# Table names (using Hadoop catalog)
BRONZE_PRODUCTS_TABLE = "kol.bronze.products"
SILVER_TIMESERIES_TABLE = "kol.silver.product_sold_timeseries"

# Local paths for Chrome profile
PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Timeseries schema
TIMESERIES_SCHEMA = StructType([
    StructField("product_id", StringType(), False),
    StructField("scraped_at", StringType(), False),
    StructField("sold_count", IntegerType(), True),
    StructField("sold_delta", IntegerType(), True),
    StructField("seller_id", StringType(), True),
    StructField("username", StringType(), True),
])


# ============================================================================
# SPARK SESSION
# ============================================================================

def create_spark_session(local_mode: bool = False) -> SparkSession:
    """
    Create Spark session with Iceberg + MinIO support
    
    Args:
        local_mode: If True, connect to MinIO via localhost:9002
    """
    minio_endpoint = MINIO_ENDPOINT_LOCAL if local_mode else MINIO_ENDPOINT
    
    print(f"🔌 Connecting to MinIO at {minio_endpoint}")
    
    spark = SparkSession.builder \
        .appName("KOL-Product-Tracker") \
        .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
        .config("spark.sql.catalog.kol", "org.apache.iceberg.spark.SparkCatalog") \
        .config("spark.sql.catalog.kol.type", "hadoop") \
        .config("spark.sql.catalog.kol.warehouse", BRONZE_WAREHOUSE) \
        .config("spark.hadoop.fs.s3a.endpoint", minio_endpoint) \
        .config("spark.hadoop.fs.s3a.access.key", MINIO_ACCESS_KEY) \
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_SECRET_KEY) \
        .config("spark.hadoop.fs.s3a.path.style.access", "true") \
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem") \
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false") \
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")
    return spark


# ============================================================================
# PRODUCT TRACKER CLASS
# ============================================================================

class ProductTracker:
    """
    Batch job để track sold_count changes cho products
    
    Usage:
        tracker = ProductTracker(local_mode=True)
        tracker.run()
    """
    
    def __init__(self, dry_run: bool = False, local_mode: bool = False, headless: bool = True):
        self.dry_run = dry_run
        self.local_mode = local_mode
        self.headless = headless
        
        self.spark: Optional[SparkSession] = None
        self.driver = None
        
        # Cache for last sold counts
        self.last_sold_cache: Dict[str, int] = {}
    
    def _init_spark(self):
        """Initialize Spark session"""
        if not SPARK_AVAILABLE:
            raise RuntimeError("PySpark not available. Install with: pip install pyspark")
        
        print("🚀 Initializing Spark session...")
        self.spark = create_spark_session(local_mode=self.local_mode)
        print("   ✅ Spark ready")
    
    def _init_driver(self):
        """Initialize Selenium driver"""
        if not SELENIUM_AVAILABLE:
            raise RuntimeError("Selenium not available. Install with: pip install selenium")
        
        print("🌐 Initializing Chrome browser...")
        
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        
        # Use dedicated profile
        profile_dir = DATA_DIR / "chrome_profiles" / "product_tracker"
        profile_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_dir}")
        
        if USE_WEBDRIVER_MANAGER:
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
        else:
            self.driver = webdriver.Chrome(options=options)
        
        print("   ✅ Browser ready")
    
    def _load_products_from_bronze(self) -> List[dict]:
        """
        Load unique products từ Bronze layer (MinIO Iceberg)
        
        Returns:
            List of dicts with product_id, product_url, seller_id, username
        """
        print("\n📦 Loading products from Bronze layer...")
        
        try:
            # Read from Iceberg table
            df = self.spark.read.format("iceberg").load(BRONZE_PRODUCTS_TABLE)
            
            # Select distinct products with required fields
            products_df = df.select(
                col("product_id"),
                col("product_url"),
                col("seller_id"),
                col("username")
            ).filter(
                col("product_id").isNotNull() & 
                col("product_url").isNotNull()
            ).dropDuplicates(["product_id"])
            
            # Collect to driver
            products = [row.asDict() for row in products_df.collect()]
            
            print(f"   ✅ Found {len(products)} unique products")
            return products
        
        except Exception as e:
            print(f"   ❌ Error loading from Bronze: {e}")
            
            # Try reading from parquet directly if table doesn't exist
            try:
                parquet_path = f"{BRONZE_WAREHOUSE}/bronze/products"
                print(f"   🔄 Trying parquet path: {parquet_path}")
                
                df = self.spark.read.parquet(parquet_path)
                products_df = df.select(
                    col("product_id"),
                    col("product_url"),
                    col("seller_id"),
                    col("username")
                ).filter(
                    col("product_id").isNotNull() & 
                    col("product_url").isNotNull()
                ).dropDuplicates(["product_id"])
                
                products = [row.asDict() for row in products_df.collect()]
                print(f"   ✅ Found {len(products)} unique products (from parquet)")
                return products
            
            except Exception as e2:
                print(f"   ❌ Parquet fallback also failed: {e2}")
                return []
    
    def _load_last_sold_counts(self) -> Dict[str, int]:
        """
        Load last known sold_count for each product từ Silver timeseries
        
        Returns:
            Dict mapping product_id -> last_sold_count
        """
        print("\n📊 Loading last sold counts from Silver layer...")
        
        try:
            # Read from Iceberg table
            df = self.spark.read.format("iceberg").load(SILVER_TIMESERIES_TABLE)
            
            # Get latest record for each product
            window = Window.partitionBy("product_id").orderBy(col("scraped_at").desc())
            
            latest_df = df.withColumn("rn", row_number().over(window)) \
                .filter(col("rn") == 1) \
                .select("product_id", "sold_count")
            
            # Collect to dict
            result = {row.product_id: row.sold_count for row in latest_df.collect() if row.sold_count}
            
            print(f"   ✅ Loaded {len(result)} previous records")
            return result
        
        except Exception as e:
            print(f"   ⚠️ No previous timeseries data (first run?): {e}")
            return {}
    
    def _scrape_sold_count(self, product_url: str) -> Optional[int]:
        """Scrape sold_count từ product page"""
        if not product_url or not self.driver:
            return None
        
        try:
            self.driver.get(product_url)
            time.sleep(3)
            
            page_source = self.driver.page_source
            
            # Find sold count patterns
            sold_patterns = [
                r'([\d,.]+[KkMm]?)\s*(?:đã bán|sold)',
                r'"sold_count"[:\s]*["\s]*(\d+)',
            ]
            
            for pattern in sold_patterns:
                matches = re.findall(pattern, page_source, re.IGNORECASE)
                if matches:
                    for m in matches:
                        result = self._parse_sold_count(m)
                        if result:
                            return result
        except Exception as e:
            pass  # Silent fail
        
        return None
    
    def _parse_sold_count(self, sold_text: str) -> Optional[int]:
        """Convert '188.5K' → 188500"""
        if not sold_text:
            return None
        
        text = sold_text.strip().upper().replace(',', '')
        multipliers = {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}
        
        for suffix, mult in multipliers.items():
            if suffix in text:
                try:
                    num = float(text.replace(suffix, ''))
                    return int(num * mult)
                except:
                    pass
        
        try:
            return int(float(text.replace('.', '')))
        except:
            return None
    
    def _save_timeseries_to_silver(self, records: List[dict]):
        """
        Append new records to Silver timeseries table
        
        Args:
            records: List of timeseries records
        """
        if not records:
            print("   ⚠️ No records to save")
            return
        
        print(f"\n💾 Saving {len(records)} records to Silver layer...")
        
        try:
            # Create DataFrame from records
            df = self.spark.createDataFrame(records, schema=TIMESERIES_SCHEMA)
            
            # Write to Silver (Parquet in MinIO)
            silver_path = f"{SILVER_WAREHOUSE}/silver/product_sold_timeseries"
            
            df.write.mode("append").parquet(silver_path)
            
            print(f"   ✅ Saved to {silver_path}")
        
        except Exception as e:
            print(f"   ❌ Error saving to Silver: {e}")
    
    def run(self):
        """Main entry point"""
        print("=" * 60)
        print("  PRODUCT TRACKER - Batch Job (MinIO/Iceberg)")
        print("=" * 60)
        print(f"  Mode: {'LOCAL' if self.local_mode else 'CLUSTER'}")
        print(f"  Dry Run: {self.dry_run}")
        print(f"  Headless: {self.headless}")
        print("=" * 60)
        print()
        
        try:
            # 1. Init Spark
            self._init_spark()
            
            # 2. Load products from Bronze
            products = self._load_products_from_bronze()
            
            if not products:
                print("\n⚠️ No products to track. Exiting.")
                return
            
            # 3. Load last sold counts from Silver
            self.last_sold_cache = self._load_last_sold_counts()
            
            if self.dry_run:
                print(f"\n🏃 DRY RUN - Would track {len(products)} products")
                for p in products[:5]:
                    print(f"   - {p['product_id']}: {p.get('product_url', 'N/A')[:50]}...")
                return
            
            # 4. Init browser
            self._init_driver()
            
            # 5. Scrape each product
            new_records = []
            scraped_at = datetime.now(timezone.utc).isoformat()
            
            print(f"\n🔍 Scraping {len(products)} products...")
            
            for i, product in enumerate(products):
                product_id = product["product_id"]
                product_url = product.get("product_url")
                
                print(f"[{i+1}/{len(products)}] {product_id[:20]}...", end="")
                
                if not product_url:
                    print(" ⏭️ no URL")
                    continue
                
                # Scrape current sold_count
                sold_count = self._scrape_sold_count(product_url)
                
                if sold_count is None:
                    print(" ⏭️ failed")
                    continue
                
                # Get last known sold_count
                last_sold = self.last_sold_cache.get(product_id)
                sold_delta = sold_count - last_sold if last_sold is not None else 0
                
                # Create record
                record = {
                    "product_id": product_id,
                    "scraped_at": scraped_at,
                    "sold_count": sold_count,
                    "sold_delta": sold_delta,
                    "seller_id": product.get("seller_id"),
                    "username": product.get("username"),
                }
                new_records.append(record)
                
                if sold_delta > 0:
                    print(f" ✅ {sold_count} (+{sold_delta})")
                else:
                    print(f" ✅ {sold_count}")
                
                time.sleep(1)  # Rate limit
            
            # 6. Save results to Silver
            if new_records:
                self._save_timeseries_to_silver(new_records)
            
            print()
            print("=" * 60)
            print(f"  ✅ Done! Tracked {len(new_records)}/{len(products)} products")
            print("=" * 60)
        
        finally:
            # Cleanup
            if self.driver:
                print("\n🔒 Closing browser...")
                self.driver.quit()
            
            if self.spark:
                print("🔒 Stopping Spark...")
                self.spark.stop()


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Product Tracker Batch Job - Track sold_count changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run in local mode (connect to MinIO via localhost)
    python -m batch.feature_store.product_tracker --local
    
    # Dry run to see products
    python -m batch.feature_store.product_tracker --local --dry-run
    
    # Run with visible browser
    python -m batch.feature_store.product_tracker --local --no-headless
        """
    )
    parser.add_argument("--dry-run", action="store_true", help="Don't actually scrape")
    parser.add_argument("--local", action="store_true", help="Use localhost MinIO (port 9002)")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser headless")
    parser.add_argument("--no-headless", action="store_true", help="Show browser window")
    
    args = parser.parse_args()
    
    headless = not args.no_headless
    
    tracker = ProductTracker(
        dry_run=args.dry_run,
        local_mode=args.local,
        headless=headless,
    )
    tracker.run()


if __name__ == "__main__":
    main()
