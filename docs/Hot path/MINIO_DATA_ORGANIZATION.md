# MinIO Data Organization - KOL Platform

## 📦 Bucket Structure

```
MinIO (localhost:9002)
│
├── kol-bronze/          ← Raw data từ scrapers (Iceberg format)
│   └── iceberg/
│       └── bronze/
│           ├── discovery/
│           ├── profiles/
│           ├── videos/
│           ├── comments/
│           └── products/
│
├── kol-silver/          ← Cleaned & enriched data
│   └── iceberg/
│       └── silver/
│           ├── kol_profiles/           (deduplicated profiles)
│           ├── kol_videos/             (with engagement metrics)
│           ├── kol_comments/           (spam filtered)
│           ├── kol_products/           (with seller info)
│           └── product_sold_timeseries/ (sold_count tracking)
│
├── kol-gold/            ← Analytics & aggregated data
│   └── iceberg/
│       └── gold/
│           ├── kol_trust_scores/       (trust model output)
│           ├── kol_rankings/           (daily rankings)
│           ├── product_performance/    (sales velocity)
│           └── campaign_predictions/   (forecast output)
│
└── kol-mlflow/          ← MLflow artifacts
    └── artifacts/
        ├── trust-model/
        ├── success-model/
        └── sentiment-model/
```

---

## 🔄 Data Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DATA PIPELINE                                  │
│                                                                          │
│   SCRAPER              KAFKA              SPARK              MINIO       │
│   ───────              ─────              ─────              ─────       │
│                                                                          │
│   discovery ──────► kol.discovery.raw ──────► bronze/discovery          │
│   profile   ──────► kol.profiles.raw  ──────► bronze/profiles           │
│   videos    ──────► kol.videos.raw    ──────► bronze/videos             │
│   comments  ──────► kol.comments.raw  ──────► bronze/comments           │
│   products  ──────► kol.products.raw  ──────► bronze/products           │
│                                                                          │
│                           │                                              │
│                           ▼                                              │
│                    SPARK ETL (Bronze → Silver)                           │
│                           │                                              │
│                           ▼                                              │
│                    silver/kol_profiles                                   │
│                    silver/kol_videos                                     │
│                    silver/product_sold_timeseries                        │
│                           │                                              │
│                           ▼                                              │
│                    SPARK ETL (Silver → Gold)                             │
│                           │                                              │
│                           ▼                                              │
│                    gold/kol_trust_scores                                 │
│                    gold/kol_rankings                                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Bronze Layer (Raw Data)

### Schema: `kol-bronze/iceberg/bronze/`

| Table | Source | Schema |
|-------|--------|--------|
| `discovery` | `kol.discovery.raw` | event_id, username, video_url, source, keyword, niche_hint |
| `profiles` | `kol.profiles.raw` | event_id, username, followers_raw, likes_raw, bio, verified |
| `videos` | `kol.videos.raw` | event_id, video_id, username, view_count, like_count, comment_count |
| `comments` | `kol.comments.raw` | event_id, video_id, username, comment_text |
| `products` | `kol.products.raw` | event_id, product_id, username, video_id, price, sold_count |

### File Format
- **Format:** Apache Iceberg (Parquet underneath)
- **Partitioning:** By `event_date` (yyyy-MM-dd)
- **Compression:** Snappy

### Example Path
```
s3a://kol-bronze/iceberg/bronze/videos/
├── metadata/
│   ├── v1.metadata.json
│   └── version-hint.text
└── data/
    └── event_date=2025-12-02/
        ├── 00000-0-abc123.parquet
        └── 00001-0-def456.parquet
```

---

## 📁 Silver Layer (Cleaned Data)

### Schema: `kol-silver/iceberg/silver/`

| Table | Purpose | Key Transformations |
|-------|---------|---------------------|
| `kol_profiles` | Deduplicated profiles | Latest record per username |
| `kol_videos` | Enriched videos | Engagement rate calculated |
| `kol_comments` | Spam-filtered | Spam detection applied |
| `kol_products` | With seller info | Joined with seller data |
| `product_sold_timeseries` | Sales tracking | sold_delta calculated |

### product_sold_timeseries Schema
```sql
CREATE TABLE silver.product_sold_timeseries (
    product_id      STRING,
    scraped_at      TIMESTAMP,
    sold_count      INT,
    sold_delta      INT,      -- Change since last scrape
    seller_id       STRING,
    username        STRING    -- KOL promoting this product
);
```

---

## 📁 Gold Layer (Analytics)

### Schema: `kol-gold/iceberg/gold/`

| Table | Purpose | Update Frequency |
|-------|---------|------------------|
| `kol_trust_scores` | Trust model predictions | Daily |
| `kol_rankings` | Daily KOL rankings by niche | Daily |
| `product_performance` | Sales velocity metrics | 2-3x daily |
| `campaign_predictions` | Campaign success forecast | On-demand |

### kol_trust_scores Schema
```sql
CREATE TABLE gold.kol_trust_scores (
    username        STRING,
    trust_score     FLOAT,      -- 0.0 to 1.0
    risk_level      STRING,     -- 'low', 'medium', 'high'
    fake_followers  FLOAT,      -- Estimated % fake followers
    engagement_quality FLOAT,   -- Comment quality score
    model_version   STRING,
    scored_at       TIMESTAMP
);
```

---

## 🛠️ Access Methods

### 1. Via Spark (Recommended for ETL)
```python
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .config("spark.sql.catalog.kol", "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.kol.type", "hadoop") \
    .config("spark.sql.catalog.kol.warehouse", "s3a://kol-bronze/iceberg") \
    .config("spark.hadoop.fs.s3a.endpoint", "http://sme-minio:9000") \
    .config("spark.hadoop.fs.s3a.access.key", "minio") \
    .config("spark.hadoop.fs.s3a.secret.key", "minio123") \
    .getOrCreate()

# Read Bronze
df = spark.read.format("iceberg").load("kol.bronze.videos")

# Read Silver
df = spark.read.parquet("s3a://kol-silver/iceberg/silver/product_sold_timeseries")
```

### 2. Via Trino (Recommended for Analytics)
```sql
-- Connect to Trino: localhost:8080

-- Query Bronze
SELECT * FROM iceberg.kol_bronze.videos LIMIT 10;

-- Query Silver
SELECT * FROM iceberg.kol_silver.kol_profiles LIMIT 10;

-- Query Gold
SELECT username, trust_score 
FROM iceberg.kol_gold.kol_trust_scores 
ORDER BY trust_score DESC LIMIT 20;
```

### 3. Via MinIO Console (Browse Files)
```
URL: http://localhost:9001
Username: minioadmin (or minio)
Password: minioadmin (or minio123)
```

---

## 📊 Data Retention

| Layer | Retention | Reason |
|-------|-----------|--------|
| Bronze | 90 days | Raw data for reprocessing |
| Silver | 1 year | Cleaned data for analysis |
| Gold | Forever | Aggregated metrics |
| MLflow | Forever | Model artifacts |

### Cleanup Command (Optional)
```bash
# Delete Bronze data older than 90 days (run in Spark)
spark.sql("""
    DELETE FROM kol.bronze.discovery 
    WHERE event_date < current_date() - INTERVAL 90 DAYS
""")
```

---

## 🔧 Create Buckets (First Time Setup)

```bash
# Via MinIO Console or mc CLI
docker exec sme-minio mc mb local/kol-bronze
docker exec sme-minio mc mb local/kol-silver
docker exec sme-minio mc mb local/kol-gold
docker exec sme-minio mc mb local/kol-mlflow
```

---

## 📝 Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Bucket | `kol-{layer}` | `kol-bronze`, `kol-silver` |
| Table | `{entity}` (singular) | `profiles`, `videos` |
| Column | `snake_case` | `sold_count`, `event_time` |
| Partition | `{column}={value}` | `event_date=2025-12-02` |

---

## 🔗 Related Documents

- **QUICK_COMMANDS.md** - Spark ETL commands
- **DOMAIN_SEPARATION.md** - KOL vs SME separation
- **PARALLEL_SCRAPING_GUIDE.md** - Data sources

---

**Last Updated:** December 2, 2025
