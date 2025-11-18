# Setup Hướng Dẫn Thu Thập Dữ Liệu Thật

## 🎯 Mục Tiêu
Thu thập dữ liệu KOL THẬT từ các nguồn công khai, KHÔNG dùng sample data.

---

## 1. YouTube Trending Data (REAL API)

### Bước 1: Lấy YouTube Data API v3 Key (MIỄN PHÍ)

1. Truy cập: https://console.cloud.google.com/apis/credentials
2. Tạo project mới hoặc chọn project có sẵn
3. Enable **YouTube Data API v3**:
   - APIs & Services > Library
   - Tìm "YouTube Data API v3"
   - Click "Enable"
4. Tạo API Key:
   - APIs & Services > Credentials
   - Click "Create Credentials" > API Key
   - Copy API key (dạng: `AIzaSyBx...`)

### Bước 2: Cấu Hình API Key

Thêm vào file `.env.kol`:
```bash
# YouTube Data API v3 (for real trending videos)
YOUTUBE_API_KEY=AIzaSyBxxxxxxxxxxxxxxxxxxxxxxxxx
```

### Bước 3: Test Thu Thập Dữ Liệu Thật

```bash
cd kol-platform
python -c "
from ingestion.sources.youtube_trending import collect
records = collect(region_codes=['US', 'VN'], limit=10, use_api=True)
print(f'Collected {len(records)} REAL trending videos')
print(f'Sample: {records[0][\"payload\"][\"title\"]}')
"
```

### API Quotas
- **Miễn phí**: 10,000 units/day
- Mỗi request trending videos: ~3 units
- Đủ cho ~3,000 trending videos/day

---

## 2. Weibo Social Data (Public Datasets)

### Dataset Sources

#### Option 1: Chinese NLP Corpus (GitHub)
```python
from ingestion.sources.weibo_dataset import collect

# Tự động download từ GitHub
records = collect(download_public=True, limit=100)
```

URL: https://github.com/SophonPlus/ChineseNlpCorpus/tree/master/datasets/weibo_senti_100k

#### Option 2: Kaggle Weibo Datasets
1. Truy cập: https://www.kaggle.com/datasets?search=weibo
2. Download CSV files
3. Đặt vào `data/weibo/`
4. Run collector:
```python
records = collect(csv_paths=['data/weibo/weibo_posts.csv'], limit=100)
```

#### Option 3: Academic Datasets
- **NLPCC Weibo Dataset**: http://tcci.ccf.org.cn/conference/2013/pages/page04_eva.html
- **SMP Weibo Dataset**: http://smp2020.aconf.cn/

---

## 3. Wikipedia KOL Rankings (Already Real!)

Wikipedia collector ĐÃ thu thập dữ liệu thật từ:
- https://en.wikipedia.org/wiki/List_of_most-subscribed_YouTube_channels
- https://en.wikipedia.org/wiki/List_of_most-followed_Instagram_accounts
- https://en.wikipedia.org/wiki/List_of_most-followed_TikTok_accounts
- https://en.wikipedia.org/wiki/List_of_most-followed_Twitter_accounts

```python
from ingestion.sources.wikipedia_backlinko import collect

# Thu thập top KOLs từ Wikipedia
records = collect(source='wikipedia', limit=50)
```

---

## 4. Full Pipeline với Dữ Liệu Thật

### Bước 1: Setup Environment
```bash
# Add API keys to .env.kol
echo "YOUTUBE_API_KEY=AIzaSyB..." >> .env.kol

# Install dependencies
pip install -r requirements/ingestion.txt
```

### Bước 2: Thu Thập Tất Cả Nguồn Thật
```python
from ingestion.sources import youtube_trending, wikipedia_backlinko, weibo_dataset

# 1. YouTube trending (REAL API)
youtube_records = youtube_trending.collect(
    region_codes=['US', 'VN', 'GB'],  # Multiple regions
    limit=50,
    use_api=True  # Use real API
)
print(f"YouTube: {len(youtube_records)} real trending videos")

# 2. Wikipedia KOL rankings (REAL scraping)
wiki_records = wikipedia_backlinko.collect(
    source='wikipedia',
    limit=100
)
print(f"Wikipedia: {len(wiki_records)} real KOLs")

# 3. Weibo social data (PUBLIC dataset)
weibo_records = weibo_dataset.collect(
    download_public=True,  # Auto-download public dataset
    limit=100
)
print(f"Weibo: {len(weibo_records)} real posts")

# Total real records
total = len(youtube_records) + len(wiki_records) + len(weibo_records)
print(f"\nTotal REAL records collected: {total}")
```

### Bước 3: Upload to MinIO Bronze
```python
from ingestion.minio_client import upload_jsonl_records

# Upload to Bronze layer
upload_jsonl_records('youtube_trending', youtube_records)
upload_jsonl_records('wikipedia_backlinko', wiki_records)
upload_jsonl_records('weibo_dataset', weibo_records)
```

---

## 5. Verification

### Check MinIO Bronze Layer
```bash
# List uploaded files
python -c "
from ingestion.minio_client import list_objects
objects = list_objects('bronze/raw/')
for obj in objects[:10]:
    print(obj.object_name, obj.size)
"
```

### Sample Data Stats
```python
from ingestion.sources.youtube_trending import collect

# Test API connection
records = collect(region_codes=['US'], limit=5, use_api=True)

for rec in records:
    payload = rec['payload']
    print(f"{payload['title']}")
    print(f"  Views: {payload['view_count']:,}")
    print(f"  Channel: {payload['channel_title']}")
    print()
```

---

## 6. Troubleshooting

### YouTube API Issues
```
❌ Error: 403 Forbidden
```
**Fix**: API key quota exceeded. Wait 24h or create new project.

```
❌ Error: Invalid API key
```
**Fix**: Enable YouTube Data API v3 in Google Cloud Console.

### Weibo Dataset Issues
```
⚠️  Failed to download public dataset
```
**Fix**: Check internet connection or use local CSV files.

### Wikipedia Scraping Issues
```
❌ Failed to fetch Wikipedia table
```
**Fix**: Wikipedia might be rate-limiting. Add delay or use VPN.

---

## 7. Data Quality

| Source | Type | Records/Day | Quality |
|--------|------|-------------|---------|
| YouTube API | Real-time | ~3,000 | ⭐⭐⭐⭐⭐ Live data |
| Wikipedia | Real-time | ~500 | ⭐⭐⭐⭐⭐ Official rankings |
| Weibo Public | Static | ~100k | ⭐⭐⭐⭐ Academic quality |

---

## 📝 Summary

✅ **YouTube**: Real API with 10k quota/day  
✅ **Wikipedia**: Real scraping from official pages  
✅ **Weibo**: Public datasets from GitHub/Kaggle  

🚫 **NO MORE SAMPLE DATA** - All sources are real!

---

## Next Steps

1. **Get YouTube API key** (5 phút)
2. **Test collectors** với `use_api=True`
3. **Run batch_ingest.py** để upload vào Bronze
4. **Verify** trong Trino/MinIO

🎉 **Congratulations** - Bạn đang làm việc với dữ liệu THẬT!
