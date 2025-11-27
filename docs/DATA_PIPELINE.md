# 📊 KOL Platform - Data Pipeline Documentation

## IE212 - Big Data Analytics | UIT 2025

---

## 🎯 Tổng Quan

Đồ án xây dựng hệ thống **KOL Analytics Platform** với kiến trúc **Medallion Architecture** (Bronze → Silver → Gold) sử dụng **PySpark** trên **Docker cluster** để xử lý dữ liệu Big Data.

### 🎯 Bài Toán Chính: KOL Trust Score

Detect **KOL không đáng tin** - những KOL xây dựng hình ảnh không trung thực:
- Sử dụng **fake followers** (mua followers ảo)
- **Bot-like activity patterns** (hoạt động bất thường)
- **Low engagement with high followers** (nhiều followers nhưng ít tương tác)

### 📊 Data Labeling Approach (Option A+B)

**Dataset gốc**: `twitter_human_bots` - Bot Detection dataset (37,438 labeled records)

**Semantic Re-mapping**:
```
┌─────────────────────────────────────────────────────────────────────────┐
│                     LABEL INTERPRETATION                                │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  Dataset gốc (Bot Detection):     →    Bài toán KOL Trust:              │
│  ──────────────────────────            ─────────────────────            │
│  is_bot = 1 (Tài khoản LÀ bot)   →    is_untrustworthy = 1             │
│                                        (KOL KHÔNG đáng tin)             │
│                                                                         │
│  is_bot = 0 (Tài khoản LÀ human) →    is_untrustworthy = 0             │
│                                        (KOL đáng tin)                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**Lý do features overlap ~80%:**

| Bot Account Patterns | KOL Dùng Fake Followers |
|---------------------|-------------------------|
| followers/following ratio bất thường | followers/following ratio bất thường (fake followers follow) |
| Account age ngắn + followers tăng nhanh | Mua followers → tăng đột biến |
| Default profile, no bio | Focus mua followers hơn build profile |
| Low engagement rate | Fake followers không tương tác |
| High posting frequency | Dùng bot để post |

**Giá trị cho ML**:
- ✅ Có **37,438 labeled records** (ground truth)
- ✅ Supervised Learning: XGBoost, LightGBM, Isolation Forest
- ✅ Model Evaluation: Precision, Recall, F1-score
- ✅ Feature Importance via SHAP values

### Kiến Trúc Tổng Quan

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         KOL ANALYTICS PLATFORM                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────────┐  │
│   │  Data    │    │  Bronze  │    │  Silver  │    │      Gold        │  │
│   │ Sources  │───▶│  (Raw)   │───▶│ (Clean)  │───▶│  (Star Schema)   │  │
│   └──────────┘    └──────────┘    └──────────┘    └──────────────────┘  │
│                        │              │                   │             │
│                        ▼              ▼                   ▼             │
│                   ┌────────────────────────────────────────────┐        │
│                   │              MinIO (S3A)                   │        │
│                   │         kol-platform bucket                │        │
│                   └────────────────────────────────────────────┘        │
│                                       │                                 │
│                                       ▼                                 │
│                   ┌────────────────────────────────────────────┐        │
│                   │         Hive Metastore + Trino             │        │
│                   │         (SQL Query Engine)                 │        │
│                   └────────────────────────────────────────────┘        │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Infrastructure (Docker Containers)

| Service | Container Name | Port | Status |
|---------|---------------|------|--------|
| **Spark Master** | kol-spark-master | 7077, 8080 | ✅ Healthy |
| **Spark Worker 1** | infra-spark-worker-1 | - | ✅ Running |
| **Spark Worker 2** | infra-spark-worker-2 | - | ✅ Running |
| **MinIO** | sme-minio | 9000, 9001 | ✅ Healthy |
| **Hive Metastore** | sme-hive-metastore | 9083 | ✅ Healthy |
| **Trino** | sme-trino | 8080 | ✅ Healthy |

### Spark Cluster Configuration
- **Cores**: 4 cores (2 workers × 2 cores)
- **Memory**: 2GB (1GB per executor)
- **Image**: `apache/spark:3.5.1-scala2.12-java17-python3-ubuntu`

---

## 📦 Data Sources (Bronze Layer)

| Source | Platform | Records | Description |
|--------|----------|---------|-------------|
| `short_video_trends` | TikTok | 48,079 | Short video metrics from HuggingFace dataset |
| `twitter_human_bots` | Twitter | 37,438 | Labeled bot/human accounts with features |
| `wikipedia_backlinko` | YouTube | 213 | Top YouTubers from Wikipedia rankings |
| `youtube_trending` | YouTube | 581 | YouTube trending videos (API) |

**Total Bronze Records**: 86,311

---

## 🔄 ETL Pipeline

### 1️⃣ Bronze → Silver (PySpark)

**Script**: `batch/etl/bronze_to_silver.py`

```bash
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/bronze_to_silver.py
```

| Silver Table | Records | Description |
|--------------|---------|-------------|
| `kol_profiles` | 37,438 | Unified KOL profiles across platforms |
| `kol_content` | 48,658 | Posts/videos with engagement metrics |
| `kol_trust_features` | 37,438 | Features for Trust Score (with labels!) |
| `kol_engagement_metrics` | 1,730 | Aggregated engagement per KOL |

**Total Silver Records**: 125,264

---

## 📋 Chi Tiết Schema Các Bảng

### Silver Layer - Bảng Chi Tiết

#### 📊 `kol_profiles` - Thông tin KOL

| Column | Type | Description |
|--------|------|-------------|
| `kol_id` | VARCHAR | ID định danh KOL (PK) |
| `platform` | VARCHAR | Nền tảng (twitter, youtube, tiktok) |
| `username` | VARCHAR | Tên tài khoản |
| `display_name` | VARCHAR | Tên hiển thị |
| `bio` | VARCHAR | Mô tả cá nhân |
| `followers_count` | BIGINT | Số người theo dõi |
| `following_count` | BIGINT | Số người đang theo dõi |
| `post_count` | BIGINT | Tổng số bài đăng |
| `verified` | BOOLEAN | Đã xác thực chưa |
| `category` | VARCHAR | Danh mục nội dung |
| `profile_url` | VARCHAR | Link profile |
| `account_created_at` | VARCHAR | Ngày tạo tài khoản |
| `source` | VARCHAR | Nguồn dữ liệu |
| `processed_at` | VARCHAR | Thời điểm xử lý |
| `dt` | DATE | Partition key |

#### 📊 `kol_content` - Nội dung/Bài đăng

| Column | Type | Description |
|--------|------|-------------|
| `content_id` | VARCHAR | ID nội dung (PK) |
| `kol_id` | VARCHAR | ID của KOL (FK) |
| `platform` | VARCHAR | Nền tảng |
| `content_type` | VARCHAR | Loại nội dung (video, post) |
| `title` | VARCHAR | Tiêu đề |
| `description` | VARCHAR | Mô tả |
| `views` | BIGINT | Lượt xem |
| `likes` | BIGINT | Lượt thích |
| `comments` | BIGINT | Lượt bình luận |
| `shares` | BIGINT | Lượt chia sẻ |
| `engagement_rate` | DOUBLE | Tỷ lệ tương tác (%) |
| `duration_seconds` | BIGINT | Thời lượng video (giây) |
| `posted_at` | VARCHAR | Thời gian đăng |
| `hashtags` | VARCHAR | Hashtags |
| `source` | VARCHAR | Nguồn dữ liệu |

#### 📊 `kol_trust_features` - Features cho Trust Score ⭐

| Column | Type | Description |
|--------|------|-------------|
| `kol_id` | VARCHAR | ID định danh KOL |
| `platform` | VARCHAR | Nền tảng |
| `followers_count` | BIGINT | Số followers |
| `following_count` | BIGINT | Số following |
| `post_count` | BIGINT | Số bài đăng |
| `favorites_count` | BIGINT | Số favorites |
| `followers_following_ratio` | DOUBLE | Tỷ lệ followers/following |
| `posts_per_day` | DOUBLE | Số bài/ngày |
| `account_age_days` | BIGINT | Tuổi tài khoản (ngày) |
| `bio_length` | BIGINT | Độ dài bio |
| `has_profile_image` | BOOLEAN | Có ảnh đại diện |
| `has_bio` | BOOLEAN | Có bio |
| `has_url` | BOOLEAN | Có URL |
| `verified` | BOOLEAN | Đã xác thực |
| `default_profile` | BOOLEAN | Profile mặc định |
| `default_profile_image` | BOOLEAN | Ảnh mặc định |
| `is_untrustworthy` | BIGINT | **Label: KOL không đáng tin (1) / đáng tin (0)** |
| `is_trustworthy` | BIGINT | Label: KOL đáng tin |
| `account_type` | VARCHAR | Loại tài khoản (bot→untrustworthy/human→trustworthy) |

#### 📊 `kol_engagement_metrics` - Metrics tổng hợp

| Column | Type | Description |
|--------|------|-------------|
| `kol_id` | VARCHAR | ID định danh KOL |
| `platform` | VARCHAR | Nền tảng |
| `total_views` | BIGINT | Tổng lượt xem |
| `total_likes` | BIGINT | Tổng lượt thích |
| `total_comments` | BIGINT | Tổng bình luận |
| `total_shares` | BIGINT | Tổng chia sẻ |
| `total_posts` | BIGINT | Tổng bài đăng |
| `avg_views_per_post` | DOUBLE | Trung bình views/bài |
| `avg_likes_per_post` | DOUBLE | Trung bình likes/bài |
| `avg_engagement_rate` | DOUBLE | Tỷ lệ tương tác TB |
| `max_views` | BIGINT | Views cao nhất |
| `min_views` | BIGINT | Views thấp nhất |

---

### Gold Layer - Star Schema

#### 🌟 Lược đồ Star Schema

```
                          ┌─────────────────┐
                          │   dim_platform  │
                          │─────────────────│
                          │ platform_sk (PK)│
                          │ platform_code   │
                          │ platform_name   │
                          │ category        │
                          └────────┬────────┘
                                   │
┌─────────────────┐               │               ┌─────────────────┐
│    dim_time     │               │               │ dim_content_type│
│─────────────────│               │               │─────────────────│
│ time_sk (PK)    │               │               │content_type_sk  │
│ full_date       │               │               │content_type_code│
│ year, quarter   │               │               │content_type_name│
│ month, week     │               │               └────────┬────────┘
│ day_of_week     │               │                        │
│ is_weekend      │               │                        │
└────────┬────────┘               │                        │
         │                        │                        │
         │         ┌──────────────┴──────────────┐         │
         │         │     fact_kol_performance    │         │
         └─────────┤─────────────────────────────├─────────┘
                   │ perf_sk (PK)                │
                   │ kol_sk (FK) ────────────────┼──────┐
                   │ platform_sk (FK)            │      │
                   │ time_sk (FK)                │      │
                   │ content_type_sk (FK)        │      │
                   │─────────────────────────────│      │
                   │ followers_count             │      │
                   │ following_count             │      │
                   │ total_views, total_likes    │      │
                   │ total_comments, total_shares│      │
                   │ engagement_rate             │      │
                   │ is_verified, is_bot         │      │
                   │ trust_score                 │      │
                   └─────────────────────────────┘      │
                                                        │
                          ┌─────────────────────────────┘
                          │
                   ┌──────┴──────┐
                   │   dim_kol   │
                   │─────────────│
                   │ kol_sk (PK) │
                   │ kol_id      │
                   │ platform    │
                   │ username    │
                   │ display_name│
                   │ bio         │
                   │ category    │
                   │ profile_url │
                   │ is_current  │
                   │ valid_from  │
                   │ valid_to    │
                   └─────────────┘
```

#### 📊 `dim_kol` - Dimension KOL (SCD Type 2)

| Column | Type | Description |
|--------|------|-------------|
| `kol_sk` | BIGINT | Surrogate Key (PK) |
| `kol_id` | VARCHAR | Business Key |
| `platform` | VARCHAR | Nền tảng |
| `username` | VARCHAR | Tên tài khoản |
| `display_name` | VARCHAR | Tên hiển thị |
| `bio` | VARCHAR | Mô tả |
| `category` | VARCHAR | Danh mục |
| `profile_url` | VARCHAR | Link profile |
| `account_created_at` | VARCHAR | Ngày tạo |
| `valid_from` | VARCHAR | Hiệu lực từ |
| `valid_to` | VARCHAR | Hiệu lực đến |
| `is_current` | BOOLEAN | Bản ghi hiện tại |

#### 📊 `dim_platform` - Dimension Nền tảng

| Column | Type | Description |
|--------|------|-------------|
| `platform_sk` | BIGINT | Surrogate Key (PK) |
| `platform_code` | VARCHAR | Mã nền tảng |
| `platform_name` | VARCHAR | Tên nền tảng |
| `category` | VARCHAR | Loại nền tảng |

**Dữ liệu:**
| platform_sk | platform_code | platform_name |
|-------------|---------------|---------------|
| 1 | youtube | YouTube |
| 2 | tiktok | TikTok |
| 3 | twitter | Twitter/X |
| 4 | instagram | Instagram |

#### 📊 `dim_time` - Dimension Thời gian

| Column | Type | Description |
|--------|------|-------------|
| `time_sk` | BIGINT | Surrogate Key (PK) |
| `full_date` | DATE | Ngày đầy đủ |
| `year` | BIGINT | Năm |
| `quarter` | BIGINT | Quý (1-4) |
| `month` | BIGINT | Tháng (1-12) |
| `week` | BIGINT | Tuần trong năm |
| `day_of_week` | BIGINT | Ngày trong tuần (1-7) |
| `day_name` | VARCHAR | Tên ngày (Monday, Tuesday...) |
| `is_weekend` | BOOLEAN | Có phải cuối tuần |

#### 📊 `dim_content_type` - Dimension Loại nội dung

| Column | Type | Description |
|--------|------|-------------|
| `content_type_sk` | BIGINT | Surrogate Key (PK) |
| `content_type_code` | VARCHAR | Mã loại nội dung |
| `content_type_name` | VARCHAR | Tên loại nội dung |

**Dữ liệu:**
| content_type_sk | content_type_code | content_type_name |
|-----------------|-------------------|-------------------|
| 1 | video | Long Video |
| 2 | short | Short Video |
| 3 | reel | Reel |
| 4 | post | Social Post |
| 5 | tweet | Tweet |

#### 📊 `fact_kol_performance` - Fact Table chính

| Column | Type | Description |
|--------|------|-------------|
| `perf_sk` | BIGINT | Surrogate Key (PK) |
| `kol_sk` | BIGINT | FK → dim_kol |
| `platform_sk` | BIGINT | FK → dim_platform |
| `time_sk` | BIGINT | FK → dim_time |
| `content_type_sk` | BIGINT | FK → dim_content_type |
| `followers_count` | BIGINT | Số followers |
| `following_count` | BIGINT | Số following |
| `post_count` | BIGINT | Số bài đăng |
| `total_views` | BIGINT | Tổng lượt xem |
| `total_likes` | BIGINT | Tổng lượt thích |
| `total_comments` | BIGINT | Tổng bình luận |
| `total_shares` | BIGINT | Tổng chia sẻ |
| `engagement_rate` | DOUBLE | Tỷ lệ tương tác (%) |
| `is_verified` | BOOLEAN | Đã xác thực |
| `is_untrustworthy` | BOOLEAN | KOL không đáng tin |
| `trust_score` | DOUBLE | Điểm tin cậy (0-100) |

---

### ML Tables - Bảng cho Machine Learning

#### 📊 `ml_trust_training` - Dataset huấn luyện

| Column | Type | Description |
|--------|------|-------------|
| `kol_id` | VARCHAR | ID định danh |
| `followers_count` | BIGINT | Feature: Số followers |
| `following_count` | BIGINT | Feature: Số following |
| `post_count` | BIGINT | Feature: Số bài đăng |
| `favorites_count` | BIGINT | Feature: Số favorites |
| `followers_following_ratio` | DOUBLE | Feature: Tỷ lệ F/F |
| `posts_per_day` | DOUBLE | Feature: Bài/ngày |
| `account_age_days` | BIGINT | Feature: Tuổi tài khoản |
| `verified` | BOOLEAN | Feature: Xác thực |
| `default_profile` | BOOLEAN | Feature: Profile mặc định |
| `default_profile_image` | BOOLEAN | Feature: Ảnh mặc định |
| `has_url` | BOOLEAN | Feature: Có URL |
| `has_bio` | BOOLEAN | Feature: Có bio |
| `is_untrustworthy` | BIGINT | **Label: 1=Không đáng tin, 0=Đáng tin** |

#### 📊 `ml_trust_features_engineered` - Features đã xử lý (29 features)

| Feature Group | Columns | Description |
|---------------|---------|-------------|
| **Original** | `followers_count`, `following_count`, `post_count`, `favorites_count` | Features gốc |
| **Log Transforms** | `log_followers`, `log_following`, `log_posts`, `log_favorites` | Giảm skewness |
| **Ratio Capping** | `ff_ratio_capped`, `posts_per_day_capped` | Clip outliers |
| **Derived** | `profile_completeness`, `engagement_rate`, `followers_per_day` | Tính toán mới |
| **Untrustworthy Indicators** | `high_activity_flag`, `suspicious_growth`, `fake_follower_indicator` | Dấu hiệu KOL không đáng tin |
| **Binning** | `account_age_tier`, `followers_tier`, `activity_tier` | Phân nhóm |
| **Interactions** | `verified_followers_interaction`, `profile_engagement_interaction` | Tương tác features |

**Chi tiết 29 Features:**

| # | Feature | Type | Description |
|---|---------|------|-------------|
| 1 | `log_followers` | DOUBLE | log(followers + 1) |
| 2 | `log_following` | DOUBLE | log(following + 1) |
| 3 | `log_posts` | DOUBLE | log(posts + 1) |
| 4 | `log_favorites` | DOUBLE | log(favorites + 1) |
| 5 | `log_account_age` | DOUBLE | log(account_age + 1) |
| 6 | `ff_ratio_capped` | DOUBLE | min(followers/following, 10000) |
| 7 | `posts_per_day_capped` | DOUBLE | min(posts_per_day, 50) |
| 8 | `profile_completeness` | DOUBLE | (has_bio + has_url + has_image) / 3 |
| 9 | `engagement_rate` | DOUBLE | favorites / (posts + 1) |
| 10 | `followers_per_day` | DOUBLE | followers / account_age |
| 11 | `high_activity_flag` | INT | posts_per_day > 20 → có thể dùng bot |
| 12 | `low_engagement_high_posts` | INT | Ít engagement + nhiều posts → fake followers |
| 13 | `suspicious_growth` | INT | Tăng followers bất thường → mua followers |
| 14 | `fake_follower_indicator` | INT | Followers nhiều + engagement thấp |
| 15 | `default_profile_score` | INT | Profile mặc định → không customize |
| 16 | `followers_tier` | INT | Nano(0) → Mega(4) |
| 17 | `account_age_tier` | INT | <1y(0) → 5+y(3) |
| 18 | `activity_tier` | INT | Inactive(0) → High(3) |
| 19-29 | ... | ... | Interactions + Binary features |

---

### Aggregate Tables

#### 📊 `agg_platform_kpi` - KPI theo nền tảng

| Column | Type | Description |
|--------|------|-------------|
| `platform` | VARCHAR | Tên nền tảng |
| `total_kols` | BIGINT | Tổng số KOL |
| `total_followers` | BIGINT | Tổng followers |
| `total_posts` | BIGINT | Tổng bài đăng |
| `avg_engagement_rate` | DOUBLE | Tỷ lệ tương tác TB |
| `verified_ratio` | DOUBLE | Tỷ lệ đã xác thực |
| `untrustworthy_ratio` | DOUBLE | Tỷ lệ KOL không đáng tin |
| `report_date` | DATE | Ngày báo cáo |

---

## 🔄 ETL Pipeline Commands

### 2️⃣ Silver → Gold (PySpark)

**Script**: `batch/etl/silver_to_gold.py`

```bash
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/silver_to_gold.py
```

**Output Tables:**

| Table Type | Table Name | Records |
|------------|------------|---------||
| **Dimension** | `dim_kol` | 37,438 |
| **Dimension** | `dim_platform` | 4 |
| **Dimension** | `dim_time` | 266 |
| **Dimension** | `dim_content_type` | 5 |
| **Fact** | `fact_kol_performance` | 48,658 |
| **ML** | `ml_trust_training` | 37,438 |
| **ML** | `ml_trust_features_engineered` | 37,438 |
| **Aggregate** | `agg_platform_kpi` | 2 |

### 3️⃣ Feature Engineering (PySpark)

**Script**: `batch/feature_store/feature_engineering.py`

```bash
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/feature_store/feature_engineering.py
```

| Table | Records | Features |
|-------|---------|----------|
| `ml_trust_features_engineered` | 37,438 | 29 |

**Total Gold Records**: 161,449

---

## 📊 Data Summary

| Layer | Tables | Total Records | Format | Storage |
|-------|--------|---------------|--------|---------||
| **Bronze** | 4 | 86,311 | Parquet | `s3a://kol-platform/bronze/` |
| **Silver** | 4 | 125,264 | Parquet | `s3a://kol-platform/silver/` |
| **Gold** | 8 | 161,449 | Parquet | `s3a://kol-platform/gold/` |

**Total**: 16 tables, 373,024 records

---

## 🔍 Query với Trino

### Kết nối Trino CLI
```bash
docker exec -it sme-trino trino
```

### Sample Queries

```sql
-- 1. Xem tất cả tables
SHOW TABLES FROM minio.kol_gold;

-- 2. KOL count by platform
SELECT platform, COUNT(*) as kol_count,
       SUM(followers_count) as total_followers
FROM minio.kol_silver.kol_profiles
GROUP BY platform;

-- 3. KOL Trust analysis (Untrustworthy ratio)
SELECT 
    SUM(CASE WHEN is_untrustworthy = 1 THEN 1 ELSE 0 END) as untrustworthy_kols,
    SUM(CASE WHEN is_untrustworthy = 0 THEN 1 ELSE 0 END) as trustworthy_kols,
    ROUND(100.0 * SUM(CASE WHEN is_untrustworthy = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) as untrustworthy_pct
FROM minio.kol_silver.kol_trust_features;

-- 4. Top KOLs by tier
SELECT kol_tier, COUNT(*) as count
FROM minio.kol_gold.dim_kol
GROUP BY kol_tier
ORDER BY count DESC;

-- 5. ML training data sample
SELECT kol_id, followers_count, is_untrustworthy, label
FROM minio.kol_gold.ml_trust_training
LIMIT 10;
```

---

## 🔧 Register Tables Script

**Script**: `batch/etl/register_iceberg_tables.py`

```bash
# Convert JSONL → Parquet và register vào Hive Metastore
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/register_iceberg_tables.py
```

---

## 📁 Project Structure

```
kol-platform/
├── batch/
│   ├── etl/
│   │   ├── bronze_to_silver.py         # Bronze → Silver (PySpark)
│   │   ├── silver_to_gold.py           # Silver → Gold (PySpark)
│   │   └── register_iceberg_tables.py  # Register to Hive Metastore
│   └── feature_store/
│       └── feature_engineering.py      # Feature Engineering (PySpark)
├── dwh/
│   ├── ddl/
│   │   └── create_all_tables.sql       # Trino DDL
│   └── infra/
│       └── docker-compose.kol.yml      # Docker services
├── ingestion/
│   └── sources/                         # Data collectors
└── docs/
    └── DATA_PIPELINE.md                 # This document
```

---

## ✅ Checklist Hoàn Thành

- [x] **Bronze Layer**: 4 data sources ingested (86,311 records)
- [x] **Silver Layer**: 4 cleaned tables (125,264 records)
- [x] **Gold Layer**: Star Schema với 4 dims + 1 fact + 2 ML tables (161,449 records)
- [x] **Feature Engineering**: 29 engineered features on Spark cluster
- [x] **Spark Cluster**: 2 workers, 4 cores, chạy ETL thành công
- [x] **MinIO S3A**: Object storage working
- [x] **Hive Metastore**: Tables registered
- [x] **Trino**: 12 tables queryable (Silver + Gold)

---

## 🚀 Quick Start

```bash
# 1. Start infrastructure
cd dwh/infra
docker-compose -f docker-compose.kol.yml up -d

# 2. Run Bronze → Silver ETL
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --conf spark.driver.extraJavaOptions="-Divy.cache.dir=/tmp/.ivy2" \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/bronze_to_silver.py

# 3. Run Silver → Gold ETL  
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --conf spark.driver.extraJavaOptions="-Divy.cache.dir=/tmp/.ivy2" \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/silver_to_gold.py

# 4. Run Feature Engineering
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --conf spark.driver.extraJavaOptions="-Divy.cache.dir=/tmp/.ivy2" \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/feature_store/feature_engineering.py

# 5. Register tables to Trino
docker exec -it kol-spark-master /opt/spark/bin/spark-submit \
    --master spark://spark-master:7077 \
    --conf spark.driver.extraJavaOptions="-Divy.cache.dir=/tmp/.ivy2" \
    --packages org.apache.hadoop:hadoop-aws:3.3.4,com.amazonaws:aws-java-sdk-bundle:1.12.262 \
    /opt/batch/etl/register_iceberg_tables.py

# 6. Query with Trino
docker exec -it sme-trino trino --execute "SELECT * FROM minio.kol_gold.agg_platform_kpi"
```

---

## 📈 Label Distribution (ML Data)

| Label | Count | Percentage | Interpretation |
|-------|-------|------------|----------------|
| **Trustworthy** (is_untrustworthy=0) | 25,013 | 66.8% | KOL đáng tin, authentic engagement |
| **Untrustworthy** (is_untrustworthy=1) | 12,425 | 33.2% | KOL không đáng tin, fake followers patterns |

**Dataset đã có labels sẵn để train model Trust Score!**

### 🎯 Model Output Interpretation

```
Trust Score Prediction:
├── label = 0: KOL đáng tin (authentic followers, organic engagement)
├── label = 1: KOL không đáng tin (fake followers, suspicious patterns)
│
└── Model predicts: P(KOL không đáng tin | features)
    ├── High probability → Flag for review
    └── Low probability → Trustworthy KOL
```

---

## 🤖 ML Pipeline Architecture

### Data Flow cho Machine Learning

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           ML PIPELINE DATA FLOW                                     │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────────────────┐   │
│  │   SILVER LAYER  │     │   GOLD LAYER    │     │      ML LAYER               │   │
│  ├─────────────────┤     ├─────────────────┤     ├─────────────────────────────┤   │
│  │                 │     │                 │     │                             │   │
│  │ kol_trust_      │────▶│ ml_trust_       │────▶│ ml_trust_features_          │   │
│  │ features        │     │ training        │     │ engineered                  │   │
│  │ (37,438 rows)   │     │ (37,438 rows)   │     │ (37,438 rows × 29 features) │   │
│  │                 │     │                 │     │                             │   │
│  │ Raw features:   │     │ Clean features: │     │ Engineered features:        │   │
│  │ • followers     │     │ • 15 base cols  │     │ • Log transforms            │   │
│  │ • following     │     │ • is_untrust-   │     │ • Ratio capping             │   │
│  │ • posts         │     │   worthy label  │     │ • Derived metrics           │   │
│  │ • account_age   │     │ • label (0/1)   │     │ • Interaction terms         │   │
│  │ • has_bio, etc  │     │                 │     │ • Binning categories        │   │
│  │                 │     │                 │     │                             │   │
│  └─────────────────┘     └─────────────────┘     └──────────────┬──────────────┘   │
│                                                                  │                  │
│                                                                  ▼                  │
│                                                  ┌─────────────────────────────┐   │
│                                                  │      MODEL TRAINING         │   │
│                                                  ├─────────────────────────────┤   │
│                                                  │                             │   │
│                                                  │  ┌─────────┐ ┌─────────┐    │   │
│                                                  │  │ XGBoost │ │LightGBM │    │   │
│                                                  │  └────┬────┘ └────┬────┘    │   │
│                                                  │       │           │         │   │
│                                                  │       ▼           ▼         │   │
│                                                  │  ┌─────────────────────┐    │   │
│                                                  │  │  Ensemble Model     │    │   │
│                                                  │  │  (Stacking/Voting)  │    │   │
│                                                  │  └──────────┬──────────┘    │   │
│                                                  │             │               │   │
│                                                  │             ▼               │   │
│                                                  │  ┌─────────────────────┐    │   │
│                                                  │  │   Trust Score       │    │   │
│                                                  │  │   P(untrustworthy)  │    │   │
│                                                  │  │   0.0 ─────── 1.0   │    │   │
│                                                  │  └─────────────────────┘    │   │
│                                                  │                             │   │
│                                                  └─────────────────────────────┘   │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Vai Trò Các Bảng trong ML Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                        TABLE ROLES IN ML PIPELINE                                   │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  📊 DATA PREPARATION                                                                │
│  ├── kol_trust_features (Silver)                                                    │
│  │   └── Raw labeled data với 15+ features gốc                                      │
│  │       • Source of truth cho labels (is_untrustworthy)                            │
│  │       • Input cho Gold layer transformation                                      │
│  │                                                                                  │
│  📊 FEATURE STORE                                                                   │
│  ├── ml_trust_training (Gold)                                                       │
│  │   └── Clean training dataset                                                     │
│  │       • Standardized column names                                                │
│  │       • Ready for feature engineering                                            │
│  │       • 37,438 labeled samples                                                   │
│  │                                                                                  │
│  ├── ml_trust_features_engineered (Gold)                                            │
│  │   └── Production-ready features (29 features)                                    │
│  │       • Log transformations (reduce skewness)                                    │
│  │       • Ratio capping (handle outliers)                                          │
│  │       • Derived features (engagement_rate, profile_completeness)                 │
│  │       • Untrustworthy indicators (suspicious_growth, fake_follower_indicator)    │
│  │       • Feature interactions                                                     │
│  │       • Binned categories (followers_tier, account_age_tier)                     │
│  │                                                                                  │
│  📊 ANALYTICS & REPORTING                                                           │
│  ├── dim_kol (Gold)                                                                 │
│  │   └── KOL dimension với trust_score và is_untrustworthy                          │
│  │       • Join với fact tables cho analysis                                        │
│  │       • SCD Type 2 cho historical tracking                                       │
│  │                                                                                  │
│  ├── fact_kol_performance (Gold)                                                    │
│  │   └── Performance metrics theo thời gian                                         │
│  │       • Track KOL performance changes                                            │
│  │       • Correlation analysis với trust score                                     │
│  │                                                                                  │
│  └── agg_platform_kpi (Gold)                                                        │
│      └── Platform-level KPIs                                                        │
│          • untrustworthy_ratio per platform                                         │
│          • Aggregate statistics                                                     │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### ML Phase Roadmap

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           ML PHASE ROADMAP                                          │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  PHASE 1: DATA PREPARATION ✅ COMPLETED                                             │
│  ────────────────────────────────────────                                           │
│  ✅ Bronze → Silver ETL (37,438 labeled records)                                    │
│  ✅ Silver → Gold ETL (Star Schema)                                                 │
│  ✅ Feature Engineering (29 features)                                               │
│  ✅ Label semantic mapping (is_bot → is_untrustworthy)                              │
│  ✅ Trino tables registered & queryable                                             │
│                                                                                     │
│  PHASE 2: MODEL DEVELOPMENT 🔄 IN PROGRESS                                          │
│  ────────────────────────────────────────                                           │
│  ⬜ Train/Test Split (80/20 stratified)                                             │
│  ⬜ Baseline Models:                                                                │
│     • XGBoost Classifier                                                            │
│     • LightGBM Classifier                                                           │
│     • Isolation Forest (anomaly detection)                                          │
│  ⬜ Hyperparameter Tuning (Optuna/GridSearch)                                       │
│  ⬜ Model Evaluation:                                                               │
│     • Precision, Recall, F1-score                                                   │
│     • ROC-AUC, PR-AUC                                                               │
│     • Confusion Matrix                                                              │
│  ⬜ Feature Importance (SHAP values)                                                │
│                                                                                     │
│  PHASE 3: MODEL SERVING 📋 PLANNED                                                  │
│  ────────────────────────────────────────                                           │
│  ⬜ Model Registry (MLflow)                                                         │
│  ⬜ REST API endpoint (FastAPI)                                                     │
│  ⬜ Batch inference pipeline                                                        │
│  ⬜ Real-time scoring                                                               │
│                                                                                     │
│  PHASE 4: MONITORING & FEEDBACK 📋 PLANNED                                          │
│  ────────────────────────────────────────                                           │
│  ⬜ Model drift detection                                                           │
│  ⬜ Performance monitoring                                                          │
│  ⬜ Feedback loop integration                                                       │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Feature Categories cho ML

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                     FEATURE CATEGORIES (29 FEATURES)                                │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  🔢 LOG TRANSFORMS (5 features)           │  📊 DERIVED METRICS (6 features)        │
│  ─────────────────────────────            │  ────────────────────────────────       │
│  • log_followers                          │  • engagement_rate                      │
│  • log_following                          │  • activity_score                       │
│  • log_posts                              │  • profile_completeness                 │
│  • log_favorites                          │  • followers_per_day                    │
│  • log_account_age                        │  • posts_per_follower                   │
│                                           │  • following_per_day                    │
│  ─────────────────────────────────────────┼──────────────────────────────────────── │
│                                           │                                         │
│  📈 RATIO CAPPING (2 features)            │  🚨 UNTRUSTWORTHY INDICATORS (5)        │
│  ─────────────────────────────            │  ────────────────────────────────       │
│  • followers_following_ratio_capped       │  • high_activity_flag                   │
│  • posts_per_day_capped                   │  • low_engagement_high_posts            │
│                                           │  • default_profile_score                │
│                                           │  • suspicious_growth                    │
│                                           │  • fake_follower_indicator ⭐           │
│  ─────────────────────────────────────────┼──────────────────────────────────────── │
│                                           │                                         │
│  📦 BINNING CATEGORIES (3 features)       │  🔗 FEATURE INTERACTIONS (4 features)   │
│  ─────────────────────────────            │  ────────────────────────────────       │
│  • followers_tier (0-4)                   │  • verified_followers_interaction       │
│  • account_age_tier (0-3)                 │  • profile_engagement_interaction       │
│  • activity_tier (0-3)                    │  • age_activity_interaction             │
│                                           │  • bio_length_norm                      │
│  ─────────────────────────────────────────┼──────────────────────────────────────── │
│                                           │                                         │
│  ✅ BINARY FEATURES (4 features)          │  🎯 TARGET VARIABLE                     │
│  ─────────────────────────────            │  ────────────────────────────────       │
│  • has_bio                                │  • label (0 = trustworthy,              │
│  • has_url                                │           1 = untrustworthy)            │
│  • has_profile_image                      │                                         │
│  • verified                               │  Distribution: 66.8% / 33.2%            │
│                                           │                                         │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Expected Model Performance Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| **Precision** | > 0.85 | Minimize false positives (wrongly flagging good KOLs) |
| **Recall** | > 0.80 | Catch most untrustworthy KOLs |
| **F1-Score** | > 0.82 | Balance precision-recall |
| **ROC-AUC** | > 0.90 | Good discrimination ability |

### Sample ML Training Code (Upcoming)

```python
# Load engineered features from Trino/MinIO
query = """
SELECT * FROM minio.kol_gold.ml_trust_features_engineered
"""
df = spark.sql(query).toPandas()

# Feature columns (29 features)
feature_cols = [
    'log_followers', 'log_following', 'log_posts', 'log_favorites',
    'log_account_age', 'followers_following_ratio_capped', 
    'posts_per_day_capped', 'engagement_rate', 'activity_score',
    'profile_completeness', 'followers_per_day', 'posts_per_follower',
    'following_per_day', 'bio_length_norm', 'high_activity_flag',
    'low_engagement_high_posts', 'default_profile_score',
    'suspicious_growth', 'fake_follower_indicator', 'followers_tier',
    'account_age_tier', 'activity_tier', 'verified_followers_interaction',
    'profile_engagement_interaction', 'age_activity_interaction',
    'has_bio', 'has_url', 'has_profile_image', 'verified'
]

X = df[feature_cols]
y = df['label']

# Train XGBoost
from xgboost import XGBClassifier
model = XGBClassifier(
    n_estimators=100,
    max_depth=6,
    learning_rate=0.1,
    scale_pos_weight=len(y[y==0])/len(y[y==1])  # Handle imbalance
)
model.fit(X_train, y_train)

# Evaluate
from sklearn.metrics import classification_report
y_pred = model.predict(X_test)
print(classification_report(y_test, y_pred))
```

---

## 📊 Current Data Statistics (Updated)

### Trino Tables Summary

#### Silver Layer (4 tables)
| Table | Records | Description |
|-------|---------|-------------|
| `kol_profiles` | 37,438 | Unified KOL profiles |
| `kol_content` | 48,658 | Posts/videos with metrics |
| `kol_trust_features` | 37,438 | Trust features with labels |
| `kol_engagement_metrics` | 1,730 | Engagement aggregations |

#### Gold Layer (8 tables)
| Table | Records | Description |
|-------|---------|-------------|
| `dim_kol` | 37,438 | KOL dimension (SCD Type 2) |
| `dim_platform` | 4 | Platform dimension |
| `dim_time` | 266 | Time dimension |
| `dim_content_type` | 5 | Content type dimension |
| `fact_kol_performance` | 48,658 | Performance fact table |
| `ml_trust_training` | 37,438 | ML training dataset |
| `ml_trust_features_engineered` | 37,438 | 29 engineered features |
| `agg_platform_kpi` | 2 | Platform KPIs |

**Total**: 12 tables, 209,266 queryable records in Trino

---

*Last Updated: November 27, 2025*
*Author: KOL Analytics Team - IE212 UIT*
