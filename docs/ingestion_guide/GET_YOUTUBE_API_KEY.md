# 🔑 How to Get YouTube API Key (5 Minutes)

## Why You Need This
- ✅ Collect REAL trending videos from YouTube
- ✅ 10,000 units/day FREE quota (~3,000 videos)
- ✅ Real-time data with views, likes, comments

Without API key: Falls back to sample data ❌

---

## Step-by-Step Guide

### 1. Go to Google Cloud Console
Open: https://console.cloud.google.com/

### 2. Create or Select Project
- Click **"Select a project"** at top
- Click **"NEW PROJECT"**
- Name: `kol-analytics` (or any name)
- Click **"CREATE"**
- Wait ~10 seconds for project creation

### 3. Enable YouTube Data API v3
- Go to: https://console.cloud.google.com/apis/library
- Search: `YouTube Data API v3`
- Click on **"YouTube Data API v3"**
- Click **"ENABLE"**
- Wait ~5 seconds for activation

### 4. Create API Key
- Go to: https://console.cloud.google.com/apis/credentials
- Click **"+ CREATE CREDENTIALS"**
- Select **"API key"**
- Copy the API key (looks like: `AIzaSyBxxxxxxxxxxxxxxxxxxxxxxx`)

### 5. (Optional) Restrict API Key
For security, click **"RESTRICT KEY"**:
- **Application restrictions**: None (or HTTP referrers if hosting on web)
- **API restrictions**: Select "Restrict key"
  - Check ✅ **YouTube Data API v3**
- Click **"SAVE"**

### 6. Add to .env.kol
```bash
cd kol-platform

# Edit .env.kol
nano .env.kol
# or
notepad .env.kol
```

Add your API key:
```bash
YOUTUBE_API_KEY=AIzaSyBxxxxxxxxxxxxxxxxxxxxxxx
```

Save and close.

---

## Test Your API Key

### Option 1: Python Script
```bash
python -c "
import os
os.environ['YOUTUBE_API_KEY'] = 'AIzaSyBxxxxxxx'  # Your key here
from ingestion.sources.youtube_trending import collect
records = collect(region_codes=['US'], limit=5, use_api=True)
print(f'✅ SUCCESS: Collected {len(records)} real videos')
print(f'Sample: {records[0][\"payload\"][\"title\"]}')
"
```

### Option 2: Direct Module Test
```bash
# Set env variable first (PowerShell)
$env:YOUTUBE_API_KEY="AIzaSyBxxxxxxx"

# Run test
python ingestion/sources/youtube_trending.py
```

### Option 3: Quick cURL Test
```bash
curl "https://www.googleapis.com/youtube/v3/videos?part=snippet&chart=mostPopular&regionCode=US&maxResults=1&key=AIzaSyBxxxxxxx"
```

---

## Expected Output (Success)
```
🔴 Fetching REAL trending videos from YouTube API (region=US)...
✅ Successfully fetched 5 REAL trending videos
✅ SUCCESS: Collected 5 REAL YouTube trending videos
📊 Regions: US
🎬 Sample: MrBeast - I Spent 7 Days In The World's Most Dangerous Jungle
```

---

## Troubleshooting

### Error: "API key not valid"
```
❌ 403 Forbidden: API key not valid
```
**Fix:**
1. Check if API key is correct (no spaces, full key copied)
2. Make sure YouTube Data API v3 is ENABLED
3. Wait 1-2 minutes after enabling API

### Error: "Quota exceeded"
```
❌ 403 Forbidden: Quota exceeded
```
**Fix:**
- You've used all 10,000 units for today
- Wait 24 hours for quota reset (resets at midnight Pacific Time)
- OR create a new project with a new API key

### Error: "API not enabled"
```
❌ YouTube Data API v3 has not been used in project
```
**Fix:**
1. Go to: https://console.cloud.google.com/apis/library
2. Search: `YouTube Data API v3`
3. Click **ENABLE**

### Error: "Invalid project"
```
❌ Project does not exist
```
**Fix:**
1. Make sure you selected the correct project in console
2. Go to: https://console.cloud.google.com/home/dashboard
3. Check project name at top

---

## API Quota Management

### Free Tier Limits
- **Daily quota**: 10,000 units
- **Cost per request**:
  - List trending videos: 3 units
  - Search videos: 100 units
  - Get video details: 3 units

### How Many Videos Can I Fetch?
```
10,000 units / 3 units per request = ~3,333 trending videos per day
```

### Monitor Your Quota
1. Go to: https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas
2. Check "Queries per day" usage

---

## Alternative: Without API Key

If you can't get API key, collectors will automatically:
1. Try to download public datasets (Weibo) ✅
2. Scrape Wikipedia rankings ✅
3. Use local CSV files
4. Generate sample data (last resort)

But you'll miss real-time YouTube trending data! 😢

---

## Security Best Practices

### ✅ DO:
- Keep API key in `.env.kol` (not in code)
- Add `.env.kol` to `.gitignore`
- Restrict API key to YouTube Data API v3 only
- Use separate API keys for dev/prod

### ❌ DON'T:
- Commit API key to Git
- Share API key publicly
- Use production API key in dev environment
- Expose API key in frontend code

---

## Cost (Spoiler: It's FREE!)

YouTube Data API v3 is **100% FREE** for:
- ✅ Up to 10,000 units/day
- ✅ ~3,000 trending videos/day
- ✅ No credit card required
- ✅ No time limit

If you need MORE quota:
- Request quota increase: https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas
- Or create multiple projects (each gets 10k/day)

---

## Summary Checklist

- [ ] Go to Google Cloud Console
- [ ] Create project `kol-analytics`
- [ ] Enable YouTube Data API v3
- [ ] Create API key
- [ ] Copy key to `.env.kol`
- [ ] Test with `python ingestion/sources/youtube_trending.py`
- [ ] See real trending videos! 🎉

**Time required**: ~5 minutes

---

## Need Help?

- Official docs: https://developers.google.com/youtube/v3/getting-started
- API Explorer: https://developers.google.com/youtube/v3/docs/videos/list
- Stack Overflow: https://stackoverflow.com/questions/tagged/youtube-api

**Happy data collecting!** 🚀
