# 📊 Datasets cho KOL Analytics Platform

## Tổng quan

Tài liệu này tổng hợp các datasets từ **HuggingFace** và **Kaggle** phù hợp cho việc phát triển KOL Analytics Platform, bao gồm Trust Score model và Fake Follower Detection.

---

## 🏆 TOP RECOMMENDED DATASETS

### 1. Twitter Human vs Bot Detection (HuggingFace)
| Thuộc tính | Chi tiết |
|------------|----------|
| **Tên** | `airt-ml/twitter-human-bots` |
| **URL** | https://huggingface.co/datasets/airt-ml/twitter-human-bots |
| **Size** | ~37,400 records |
| **Downloads** | 99/month |
| **Format** | Parquet/CSV |

**Columns quan trọng:**
- `created_at` - Account creation date
- `default_profile` - Using default profile (boolean)
- `description` - Bio description
- `favourites_count` - Number of likes
- `followers_count` - Number of followers
- `friends_count` - Number of following
- `verified` - Verified status
- `screen_name` - Username
- `statuses_count` - Total tweets
- `average_tweets_per_day` - Activity metric
- `account_age_days` - Account age
- **`account_type`** - **Label: "bot" hoặc "human"** ⭐

**Đánh giá:**
- ✅ **Rất phù hợp** cho Trust Score model
- ✅ Có labeled data (bot/human)
- ✅ Đầy đủ engagement metrics
- ✅ Profile completeness features
- ✅ Account age information
- **Phù hợp: 9.5/10**

---

### 2. Fake Profile Social Media (HuggingFace)
| Thuộc tính | Chi tiết |
|------------|----------|
| **Tên** | `nahiar/fake_profile_social_media` |
| **URL** | https://huggingface.co/datasets/nahiar/fake_profile_social_media |
| **Size** | 3,351 records (~1.89 MB) |
| **Downloads** | 21/month |
| **Format** | CSV |

**Columns quan trọng (38 features):**
- `id`, `name`, `screen_name` - Identity
- `description` - Profile bio
- `statuses_count` - Tweet count (0-33,128)
- `followers_count` - Followers (0-1,624)
- `friends_count` - Following (0-2,004)
- `favourites_count` - Likes given
- `listed_count` - Times added to lists
- `default_profile` - Default settings (9.5%)
- `default_profile_image` - Default avatar (99.8%)
- `geo_enabled` - Location enabled
- `verified` - Verification status
- `created_at` - Account creation
- Profile customization colors

**Đánh giá:**
- ✅ Thiết kế cho fake profile detection
- ✅ Nhiều behavioral features
- ✅ Profile completeness metrics
- ⚠️ Dữ liệu từ 2009-2013 (hơi cũ)
- **Phù hợp: 8.5/10**

---

### 3. Instagram Fake Spammer Genuine Accounts (Kaggle)
| Thuộc tính | Chi tiết |
|------------|----------|
| **Tên** | Instagram fake spammer genuine accounts |
| **URL** | https://www.kaggle.com/datasets/free4ever1/instagram-fake-spammer-genuine-accounts |
| **Size** | ~700 records (train + test) |
| **Downloads** | 10,300+ |
| **License** | CC BY 3.0 |

**Columns quan trọng (12 features):**
- `profile_pic` - Has profile picture (boolean)
- `nums/length_username` - Username characteristics
- `full_name_words` - Name word count
- `nums/length_fullname` - Full name characteristics
- `name==username` - Name matches username
- `description_length` - Bio length
- `external_URL` - Has external URL
- `private` - Private account
- `#posts` - Post count
- `#followers` - Follower count
- `#follows` - Following count
- **`fake`** - **Label: 0 (genuine) or 1 (fake/spammer)** ⭐

**Đánh giá:**
- ✅ **REAL Instagram data** (thu thập 2019)
- ✅ Đã labeled (fake/genuine)
- ✅ Cao trong community (111 upvotes)
- ✅ Có train/test split sẵn
- ⚠️ Dataset nhỏ
- **Phù hợp: 9/10** (cho Instagram)

---

### 4. Top 100 Social Media Influencers 2024 (Kaggle)
| Thuộc tính | Chi tiết |
|------------|----------|
| **Tên** | Top 100 Social Media Influencers 2024 Countrywise |
| **URL** | https://www.kaggle.com/datasets/bhavyadhingra00020/top-100-social-media-influencers-2024-countrywise |
| **Size** | ~909 KB (243 files across 61 countries) |
| **Downloads** | 5,500+ |
| **License** | Apache 2.0 |

**Columns quan trọng:**
- `Rank` - Ranking position
- `Name` - Influencer name
- `Follower Count` - Total followers
- `Engagement Rate` - Engagement percentage ⭐
- `Country` - Location
- `Topic Of Influence` - Niche/category
- `Reach` - Platform (Instagram, YouTube, TikTok, Twitter)

**Platforms covered:**
- Instagram
- YouTube  
- TikTok
- Twitter/X

**Đánh giá:**
- ✅ Multi-platform data
- ✅ Có engagement rate
- ✅ Data mới (2024)
- ✅ 61 countries
- ⚠️ Chỉ top influencers (không có small KOLs)
- **Phù hợp: 8/10**

---

### 5. Users vs Bots Classification - VK (Kaggle)
| Thuộc tính | Chi tiết |
|------------|----------|
| **Tên** | Users vs bots classification |
| **URL** | https://www.kaggle.com/datasets/juice0lover/users-vs-bots-classification |
| **Size** | 5,874 records (~1.77 MB) |
| **Downloads** | 4,358 |
| **License** | MIT |

**Columns quan trọng (60 features):**
- Activity metrics (average posts/week, hashtag usage)
- Friend/follower counts
- Profile completeness (has_photo, has_mobile)
- Privacy settings (is_closed_profile)
- Binary flags (can_post, can_message)
- **`is_bot`** - **Label: user vs bot** ⭐

**Đánh giá:**
- ✅ 60 comprehensive features
- ✅ Balanced dataset (50/50)
- ✅ 97% accuracy đạt được trong research
- ✅ Profile completeness features
- ⚠️ Platform: VK (Russia) - khác ecosystem
- **Phù hợp: 7.5/10**

---

### 6. Viral Social Media Trends & Engagement (Kaggle)
| Thuộc tính | Chi tiết |
|------------|----------|
| **Tên** | Viral Social Media Trends & Engagement Analysis |
| **URL** | https://www.kaggle.com/datasets/atharvasoundankar/viral-social-media-trends-and-engagement-analysis |
| **Size** | 5,000 records (~410 KB) |
| **Downloads** | 8,419 |
| **License** | CC0 Public Domain |

**Columns quan trọng (11 features):**
- `Platform` - TikTok, Instagram, Twitter, YouTube
- `Views` - View count
- `Likes` - Like count
- `Shares` - Share count
- `Comments` - Comment count
- `Hashtags` - Trending hashtags
- `Content Type` - Type of content
- `Post Date` - Timestamp
- `Region` - Geographic region
- `Engagement Score` ⭐

**Đánh giá:**
- ✅ Multi-platform (4 platforms)
- ✅ Full engagement metrics
- ✅ Public domain license
- ⚠️ Synthetic/simulated data
- **Phù hợp: 7/10**

---

### 7. Instagram Influencer and Brand Dataset (HuggingFace)
| Thuộc tính | Chi tiết |
|------------|----------|
| **Tên** | `AzrilFahmiardi/instagram_influencer_and_brand` |
| **URL** | https://huggingface.co/datasets/AzrilFahmiardi/instagram_influencer_and_brand |
| **Size** | 3,808 rows (~667 KB) |
| **Downloads** | 51/month |
| **License** | MIT |

**Subsets:**
- `instagram_influencers.csv` - Influencer profiles
- `brands.csv` - Brand data
- `captions.csv` - Post captions
- `comments.csv` - Comments với likes
- `labeled_caption.csv` - Labeled captions
- `labeled_comment.csv` - Labeled comments
- `bio.csv` - Bio data

**Columns quan trọng:**
- `username` - Instagram handle
- `followers_tier` - Follower tier
- `engagement_rate` - Engagement rate ⭐
- `rate_card` - Pricing
- `bidang_keahlian` - Expertise area
- `demografi` - Demographics
- `psikografi` - Psychographics

**Đánh giá:**
- ✅ Có labeled data cho classification
- ✅ Comments có likes
- ✅ Caption analysis ready
- ⚠️ Focus Indonesia market
- **Phù hợp: 7.5/10**

---

### 8. Top 200 Instagram Accounts (Kaggle)
| Thuộc tính | Chi tiết |
|------------|----------|
| **Tên** | Top Instagram Accounts Data (Cleaned) |
| **URL** | https://www.kaggle.com/datasets/faisaljanjua0555/top-200-most-followed-instagram-accounts-2023 |
| **Size** | 200 records (~15 KB) |
| **Downloads** | 2,931 |

**Columns quan trọng:**
- `rank` - Position ranking
- `name` - Instagram handle
- `channel_info` - Account description
- `Category` - Content category
- `posts` - Total posts
- `followers` - Follower count
- `avg likes` - Average likes per post ⭐
- `eng rate` - Engagement rate (%) ⭐

**Đánh giá:**
- ✅ Clean engagement metrics
- ✅ Category classification
- ⚠️ Chỉ 200 records
- ⚠️ Top accounts only
- **Phù hợp: 6/10**

---

## 📈 DATASETS CHO TRUST SCORE MODEL

### Primary Recommendations:

| Priority | Dataset | Use Case | Key Features |
|----------|---------|----------|--------------|
| 1️⃣ | `airt-ml/twitter-human-bots` | Bot detection baseline | 37K labeled bot/human |
| 2️⃣ | Instagram Fake Spammer | Fake account detection | Real IG data, labeled |
| 3️⃣ | Users vs Bots (VK) | Feature engineering | 60 behavioral features |
| 4️⃣ | Fake Profile Social Media | Profile analysis | 38 profile features |

### Feature Engineering từ datasets:

```python
# Trust Score Features có thể extract:
trust_features = {
    # Account Quality
    'profile_completeness': 'bio + avatar + external_url',
    'account_age_days': 'created_at calculation',
    'verified_status': 'boolean',
    
    # Activity Patterns
    'avg_posts_per_day': 'statuses_count / account_age',
    'posting_consistency': 'variance in posting times',
    
    # Engagement Quality
    'follower_following_ratio': 'followers / (following + 1)',
    'engagement_rate': '(likes + comments) / followers',
    'avg_likes_per_post': 'total_likes / post_count',
    
    # Bot Indicators
    'default_profile': 'using default settings',
    'default_profile_image': 'using default avatar',
    'suspicious_patterns': 'automated behavior signals'
}
```

---

## 🔧 HƯỚNG DẪN SỬ DỤNG

### Download từ HuggingFace:

```python
from datasets import load_dataset

# Twitter Human vs Bot
twitter_bot = load_dataset("airt-ml/twitter-human-bots")

# Fake Profile
fake_profile = load_dataset("nahiar/fake_profile_social_media")

# Instagram Influencer
ig_influencer = load_dataset("AzrilFahmiardi/instagram_influencer_and_brand")
```

### Download từ Kaggle:

```bash
# Install kaggle CLI
pip install kaggle

# Set up credentials (~/.kaggle/kaggle.json)

# Download datasets
kaggle datasets download -d free4ever1/instagram-fake-spammer-genuine-accounts
kaggle datasets download -d bhavyadhingra00020/top-100-social-media-influencers-2024-countrywise
kaggle datasets download -d juice0lover/users-vs-bots-classification
kaggle datasets download -d atharvasoundankar/viral-social-media-trends-and-engagement-analysis
```

---

## 📊 SO SÁNH TỔNG HỢP

| Dataset | Size | Platform | Has Labels | Engagement | Trust Features | Score |
|---------|------|----------|------------|------------|----------------|-------|
| Twitter Human-Bots | 37.4K | Twitter | ✅ bot/human | ✅ | ✅ | 9.5/10 |
| IG Fake Spammer | 700 | Instagram | ✅ fake/genuine | ⚠️ | ✅ | 9/10 |
| Fake Profile SM | 3.3K | Twitter | ❌ | ⚠️ | ✅ | 8.5/10 |
| Top 100 Influencers | 6K+ | Multi | ❌ | ✅ | ⚠️ | 8/10 |
| Users vs Bots VK | 5.8K | VK | ✅ bot/user | ✅ | ✅ | 7.5/10 |
| IG Influencer & Brand | 3.8K | Instagram | ✅ | ✅ | ⚠️ | 7.5/10 |
| Viral SM Trends | 5K | Multi | ❌ | ✅ | ❌ | 7/10 |
| Top 200 IG | 200 | Instagram | ❌ | ✅ | ❌ | 6/10 |

---

## 🎯 RECOMMENDED PIPELINE

### Phase 1: Trust Score Model Training
1. **Primary**: `airt-ml/twitter-human-bots` (bot detection baseline)
2. **Augment**: Instagram Fake Spammer (cross-platform validation)
3. **Feature extraction**: Users vs Bots VK (60 behavioral features)

### Phase 2: Engagement Analytics
1. Top 100 Influencers 2024 (engagement benchmarks)
2. Viral Social Media Trends (cross-platform patterns)
3. Instagram Influencer & Brand (engagement + captions)

### Phase 3: Cross-Platform KOL Analytics
1. Combine all datasets với common schema
2. Build unified feature store
3. Train ensemble models

---

## 📝 NOTES

### Limitations:
- Hầu hết datasets là Twitter-focused
- Instagram REAL data rất limited
- YouTube và TikTok data thiếu
- Some datasets synthetic/simulated

### Recommendations:
1. **Combine multiple datasets** để có đủ coverage
2. **Focus on labeled datasets** cho supervised learning
3. **Use engagement metrics** từ Top Influencer datasets làm benchmarks
4. **Build custom crawler** cho REAL data bổ sung

---

*Last Updated: November 26, 2025*
