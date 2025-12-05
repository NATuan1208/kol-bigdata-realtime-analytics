# 🚀 KOL Scraper - Hybrid Architecture Guide

## ⚠️ TL;DR: Why Hybrid?

**TikTok blocks Docker containers.** After extensive testing:
- ❌ Selenium + headless in Docker → 0 results
- ❌ Xvfb virtual display in Docker → 0 results  
- ❌ undetected-chromedriver → Incompatible with Python 3.13
- ❌ Playwright + Stealth in Docker → 0 results
- ✅ **Playwright on Windows host** → **46 creators found!**
- ✅ **Selenium on Windows host** → **53 creators found!**

**Root cause**: TikTok fingerprints Docker container IPs and blocks them.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     WINDOWS HOST (24/7)                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  kol_scraper.py (Selenium) / kol_scraper_playwright.py   │  │
│  │  - Runs via Task Scheduler                                │  │
│  │  - Uses saved Chrome profile (captcha verified once)      │  │
│  │  - Sends data to Kafka via localhost:19092                │  │
│  └────────────────────────────┬─────────────────────────────┘  │
│                               │                                  │
│                               ▼                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Docker Compose                           │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐   │ │
│  │  │  Redpanda   │  │  Cassandra  │  │  Spark + Iceberg │   │ │
│  │  │  (Kafka)    │  │             │  │                   │   │ │
│  │  │  :19092     │  │  :9042      │  │  :7077            │   │ │
│  │  └─────────────┘  └─────────────┘  └──────────────────┘   │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────────┐   │ │
│  │  │   Trino     │  │  Postgres   │  │    Grafana       │   │ │
│  │  │   :8080     │  │  :5432      │  │    :3000         │   │ │
│  │  └─────────────┘  └─────────────┘  └──────────────────┘   │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📦 Setup Instructions

### Step 1: Start Docker Services

```powershell
cd e:\Project\kol-platform

# Start all infrastructure (Kafka, Cassandra, Spark, etc.)
docker-compose -f infra/docker-compose.yml up -d
```

### Step 2: Verify Captcha Once (Required)

```powershell
cd e:\Project\kol-platform

# This opens a Chrome window - complete any captcha that appears
python ingestion/sources/setup_tiktok_session.py

# Wait 30 seconds, interact with TikTok if needed, then close
```

**Important:** This saves session cookies to `data/chrome_profile/` - only needed once unless cookies expire.

### Step 3: Test Scraper Works

```powershell
# Quick test (dry-run, no Kafka needed)
python ingestion/sources/kol_scraper.py discovery --rounds 1 --dry-run

# Test with Kafka
python ingestion/sources/kol_scraper.py discovery --rounds 1 --kafka-broker localhost:19092
```

### Step 4: Setup Windows Task Scheduler (24/7 Operation)

**Option A: Run PowerShell script**

```powershell
# Run the install script (creates scheduled task)
.\install_scraper_service.ps1
```

**Option B: Manual setup**

1. Open Task Scheduler (`taskschd.msc`)
2. Create Basic Task: "KOL Scraper Daemon"
3. Trigger: "At startup"
4. Action: Start a program
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -File "e:\Project\kol-platform\run_scraper_daemon.ps1"`
   - Start in: `e:\Project\kol-platform`
5. Check "Run with highest privileges"
6. Configure: "Run whether user is logged on or not"

---

## 🔧 Scraper Configuration

### File Locations
- `ingestion/sources/kol_scraper.py` - Main Selenium scraper
- `ingestion/sources/kol_scraper_playwright.py` - Playwright alternative
- `ingestion/sources/scraper_utils.py` - Stealth configuration
- `data/chrome_profile/` - Saved browser session
- `data/scrape/` - Output files and checkpoints

### Command Reference

```powershell
# Discovery only (find new KOLs)
python ingestion/sources/kol_scraper.py discovery --rounds 3

# Full pipeline (discovery + profiles + videos + comments)
python ingestion/sources/kol_scraper.py daemon \
    --interval 300 \
    --max-kols-per-round 10 \
    --max-videos-per-kol 20 \
    --with-comments

# Dry run (no Kafka, just test)
python ingestion/sources/kol_scraper.py daemon --dry-run

# Custom Kafka broker
python ingestion/sources/kol_scraper.py daemon --kafka-broker localhost:19092
```

### Environment Variables (Optional)

```powershell
# Add to PowerShell profile or .env
$env:KAFKA_BROKER = "localhost:19092"
$env:CHROME_PROFILE = "e:\Project\kol-platform\data\chrome_profile"
```

---

## 📊 Kafka Topics

| Topic | Description |
|-------|-------------|
| `kol.discovery.raw` | New KOL discoveries (username, video_url, niche) |
| `kol.profiles.raw` | KOL profile stats (followers, following, likes) |
| `kol.videos.raw` | Video metadata (views, comments, shares, caption) |
| `kol.comments.raw` | Video comments (text, username, likes) |
| `kol.products.raw` | Product info from TikTok Shop |

### Consume Topics

```powershell
# Using rpk (Redpanda CLI)
docker exec -it redpanda rpk topic consume kol.discovery.raw --brokers localhost:9092

# Using kafkacat
kafkacat -b localhost:19092 -t kol.discovery.raw -C
```

---

## 🔄 Data Pipeline

```
Scraper (Windows) → Kafka → Spark Jobs → Iceberg Tables → Trino/DuckDB
     │                │
     │                └→ bronze_to_silver.py (clean data)
     │                └→ silver_to_gold.py (aggregations)
     │
     └→ data/scrape/*.json (backup files)
```

---

## ❓ Troubleshooting

### "0 creators found"
- Run `setup_tiktok_session.py` to verify captcha
- Make sure Chrome profile exists in `data/chrome_profile/`
- Check if TikTok is accessible (not blocked by network)

### Kafka connection failed
- Check Docker is running: `docker ps`
- Verify Redpanda: `docker logs redpanda`
- Test connection: `Test-NetConnection localhost -Port 19092`

### Browser crash
- Close other Chrome instances
- Delete `data/chrome_profile/Singleton*` files
- Restart scraper

### Memory issues
- Reduce `--max-kols-per-round`
- Increase `--interval`
- Check Chrome memory usage

---

## 📝 Maintenance

### Clear checkpoint (restart discovery)
```powershell
rm data/scrape/checkpoint_state.json
```

### Check scraper logs
```powershell
Get-Content -Tail 100 data/scrape/scraper.log
```

### Manual Kafka topic management
```powershell
# List topics
docker exec -it redpanda rpk topic list --brokers localhost:9092

# Create topic
docker exec -it redpanda rpk topic create kol.discovery.raw --brokers localhost:9092

# Delete topic (careful!)
docker exec -it redpanda rpk topic delete kol.discovery.raw --brokers localhost:9092
```
