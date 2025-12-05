"""
KOL Platform - Ingestion Module

Cấu trúc:
---------
ingestion/
├── config.py           # Config chung (Chrome profiles, Kafka, settings)
├── consumers/          # Kafka consumers (chạy song song)
│   ├── base.py         # Base consumer class
│   ├── comment_extractor.py
│   └── product_extractor.py
├── sources/            # Data sources (scrapers)
│   ├── kol_scraper.py  # Main scraper (discovery + videos)
│   └── scraper_utils.py
└── schemas/            # Data schemas/models

Kiến trúc song song:
--------------------
┌─────────────────────────────────────────────────────────────────┐
│  Terminal 1: SCRAPER (Default profile)                         │
│  python -m ingestion.sources.kol_scraper daemon                 │
│  → kol.videos.raw                                               │
├─────────────────────────────────────────────────────────────────┤
│  Terminal 2: COMMENT EXTRACTOR (Profile 1)                      │
│  python -m ingestion.consumers.comment_extractor                │
│  kol.videos.raw → kol.comments.raw                             │
├─────────────────────────────────────────────────────────────────┤
│  Terminal 3: PRODUCT EXTRACTOR (Profile 6)                      │
│  python -m ingestion.consumers.product_extractor                │
│  kol.videos.raw → kol.products.raw                             │
└─────────────────────────────────────────────────────────────────┘
"""

from ingestion.config import (
    KAFKA_BROKER,
    KAFKA_TOPICS,
    CONSUMER_GROUPS,
    CHROME_PROFILES,
    get_chrome_profile,
    get_profile_path,
)

__all__ = [
    "KAFKA_BROKER",
    "KAFKA_TOPICS", 
    "CONSUMER_GROUPS",
    "CHROME_PROFILES",
    "get_chrome_profile",
    "get_profile_path",
]
