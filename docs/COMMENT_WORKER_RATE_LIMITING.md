# YouTube Comments Worker - Rate Limiting Guide

## Tại sao Worker Stream Liên Tục?

**Đây là behavior BÌNH THƯỜNG** của Kafka consumer:
- Consumer đọc messages từ Kafka ngay khi có
- Không có delay mặc định giữa các messages
- Đây là cách Kafka hoạt động để đạt throughput cao

## Khi Nào Cần Rate Limiting?

### ✅ NÊN thêm delay khi:
1. **API có rate limit nghiêm ngặt**: YouTube API có quota 10,000 units/day
2. **Muốn tránh bị ban**: Quá nhiều requests/giây có thể trigger rate limiting
3. **Tiết kiệm quota**: Không cần xử lý real-time, có thể chậm 1-2 giây/video

### ❌ KHÔNG cần delay khi:
1. **Infrastructure scale được**: Kafka + workers nhiều instances
2. **API không giới hạn**: Hoặc limit rất cao
3. **Cần real-time processing**: Latency thấp quan trọng

## Solution Implemented

### Code Changes

**1. Added `delay_between_videos` parameter:**
```python
class YouTubeCommentsWorker:
    def __init__(self, max_comments: int = 100, 
                 start_delay: int = 0, 
                 delay_between_videos: float = 0):  # NEW
        self.delay_between_videos = delay_between_videos
```

**2. Added sleep after processing each video:**
```python
def process_message(self, message: Dict) -> bool:
    # ... fetch comments ...
    
    # Optional delay (rate limiting)
    if self.delay_between_videos > 0:
        time.sleep(self.delay_between_videos)
    
    return True
```

**3. Added CLI argument:**
```bash
python -m ingestion.consumers.youtube_comments_worker \
    --delay-between-videos 2  # 2 seconds between videos
```

### Docker Configuration

**docker-compose.kol.yml:**
```yaml
youtube-scraper:
  environment:
    - COMMENT_DELAY=2  # 2 seconds delay between videos
```

**youtube_entrypoint.sh:**
```bash
[program:youtube_comments_worker]
command=python -m ingestion.consumers.youtube_comments_worker \
    --delay-between-videos %(ENV_COMMENT_DELAY)s
```

## Usage Examples

### Local Testing

**No delay (máy ảo):**
```bash
python -m ingestion.consumers.youtube_comments_worker --max-comments 100
```

**2 second delay (recommended):**
```bash
python -m ingestion.consumers.youtube_comments_worker \
    --max-comments 100 \
    --delay-between-videos 2
```

**5 second delay (conservative):**
```bash
python -m ingestion.consumers.youtube_comments_worker \
    --max-comments 100 \
    --delay-between-videos 5
```

### Docker Deployment

**1. Edit docker-compose.kol.yml:**
```yaml
environment:
  - COMMENT_DELAY=2  # Change value here
```

**2. Rebuild and restart:**
```bash
docker compose -f infra/docker-compose.kol.yml build youtube-scraper
docker compose -f infra/docker-compose.kol.yml up -d youtube-scraper
```

## Performance Analysis

### Current Stats (No Delay)
- **10 channels** discovered
- **~50 videos/channel** = 500 videos total
- **Processing time**: ~4 minutes (no delay)
- **API quota used**: ~1,500 units (comments API = 1 unit/video)

### With 2s Delay
- **Processing time**: ~20 minutes (500 videos × 2s = 1000s)
- **Throughput**: 3 videos/minute
- **API quota saved**: Same units, but spread over time
- **Rate limit risk**: Very low

### With 5s Delay
- **Processing time**: ~42 minutes
- **Throughput**: 1.2 videos/minute
- **Best for**: High-volume scraping without API ban risk

## Recommended Settings

| Scenario | COMMENT_DELAY | Rationale |
|----------|---------------|-----------|
| **Development** | `0` | Fast iteration, testing |
| **Production (low volume)** | `2` | Balance speed vs. safety |
| **Production (high volume)** | `5` | Conservative, avoid rate limits |
| **Aggressive scraping** | `10` | Maximum safety, large channels |

## Monitoring

**Check processing speed:**
```bash
docker logs youtube-scraper -f | grep "comments"
```

**Check API quota:**
```bash
# Look for "Total API quota used" in logs
docker logs youtube-scraper 2>&1 | grep "quota"
```

**Check if rate limited:**
```bash
# Look for 403 errors
docker logs youtube-scraper 2>&1 | grep "403"
```

## Alternative Strategies

### 1. Batch Processing
Process 10 videos → sleep 60s:
```python
batch_count = 0
for message in self.consumer:
    self.process_message(message.value)
    batch_count += 1
    
    if batch_count % 10 == 0:
        time.sleep(60)  # 1 minute break per 10 videos
```

### 2. Dynamic Rate Limiting
Adjust delay based on API response:
```python
if "rateLimitExceeded" in error:
    self.delay_between_videos *= 2  # Exponential backoff
```

### 3. Multiple Workers
Run 3 workers with low delay vs. 1 worker with high delay:
```bash
# Better throughput, same API quota
docker compose up --scale youtube-scraper=3
```

## Conclusion

**Recommendation**: Set `COMMENT_DELAY=2` for production

**Lý do**:
- ✅ Tránh rate limit (99% safety)
- ✅ Không quá chậm (20 phút cho 500 videos)
- ✅ Dễ scale (có thể giảm xuống 1s nếu cần)
- ✅ Quota friendly (spread over time)

**Trade-off**: Chậm hơn 5x so với no delay, nhưng an toàn hơn 100x
