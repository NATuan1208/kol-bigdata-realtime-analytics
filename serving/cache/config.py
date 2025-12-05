"""
Redis Cache Configuration & Key Schema
=======================================

This module defines the Redis cache schema for KOL Platform.

Key Patterns:
-------------
┌─────────────────────────────────────────────────────────────────────────┐
│ KEY PATTERN                    │ TYPE      │ TTL     │ DESCRIPTION     │
├─────────────────────────────────────────────────────────────────────────┤
│ kol:profile:{kol_id}           │ HASH      │ 1 hour  │ KOL profile     │
│ kol:profiles:list:{platform}   │ STRING    │ 15 min  │ Platform KOLs   │
│ kol:top:followers:{platform}   │ ZSET      │ 15 min  │ Top by followers│
│ kol:top:engagement:{platform}  │ ZSET      │ 15 min  │ Top by engage   │
│ content:trending:{platform}    │ LIST      │ 15 min  │ Trending content│
│ content:detail:{content_id}    │ HASH      │ 30 min  │ Content detail  │
│ stats:platform                 │ HASH      │ 5 min   │ Platform stats  │
│ stats:daily:{date}             │ HASH      │ 24 hour │ Daily metrics   │
│ search:autocomplete            │ ZSET      │ 30 min  │ Search suggest  │
│ search:recent:{user_id}        │ LIST      │ 7 days  │ Recent searches │
└─────────────────────────────────────────────────────────────────────────┘

Data Flow:
----------
Silver Layer (Trino) → Cache Warmer → Redis → API → Client

Usage:
------
    from serving.cache import CacheConfig, CacheKeys
    
    config = CacheConfig()
    key = CacheKeys.kol_profile("tiktok_user123")
    # => "kol:profile:tiktok_user123"
"""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CacheConfig:
    """Redis connection configuration."""
    
    # Connection settings
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "16379"))  # External port
    db: int = int(os.getenv("REDIS_DB", "0"))
    password: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    
    # Connection pool settings
    max_connections: int = int(os.getenv("REDIS_MAX_CONNECTIONS", "20"))
    socket_timeout: float = float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0"))
    socket_connect_timeout: float = float(os.getenv("REDIS_CONNECT_TIMEOUT", "5.0"))
    
    # Retry settings
    retry_on_timeout: bool = True
    health_check_interval: int = 30
    
    @property
    def url(self) -> str:
        """Get Redis URL for connection."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"
    
    @classmethod
    def for_docker(cls) -> "CacheConfig":
        """Configuration for Docker internal network."""
        return cls(
            host="redis",  # Docker service name
            port=6379,     # Internal port
        )


class TTL:
    """Cache TTL constants (in seconds)."""
    
    # Profile data - relatively stable
    KOL_PROFILE = 3600          # 1 hour
    KOL_PROFILES_LIST = 900     # 15 minutes
    
    # Rankings - updated frequently
    TOP_FOLLOWERS = 900         # 15 minutes
    TOP_ENGAGEMENT = 900        # 15 minutes
    
    # Content - time-sensitive
    TRENDING_CONTENT = 900      # 15 minutes
    CONTENT_DETAIL = 1800       # 30 minutes
    
    # Statistics - very fresh
    PLATFORM_STATS = 300        # 5 minutes
    DAILY_STATS = 86400         # 24 hours
    
    # Search
    AUTOCOMPLETE = 1800         # 30 minutes
    RECENT_SEARCHES = 604800    # 7 days


class CacheKeys:
    """
    Redis key patterns and generators.
    
    Convention:
    - Use colons (:) as namespace separators
    - Use lowercase and underscores
    - Keep keys descriptive but concise
    """
    
    # === KOL PROFILES ===
    
    @staticmethod
    def kol_profile(kol_id: str) -> str:
        """Single KOL profile hash key."""
        return f"kol:profile:{kol_id}"
    
    @staticmethod
    def kol_profiles_list(platform: str = "all") -> str:
        """List of KOL profiles by platform (JSON string)."""
        return f"kol:profiles:list:{platform}"
    
    @staticmethod
    def kol_top_followers(platform: str = "all", limit: int = 100) -> str:
        """Sorted set of top KOLs by followers."""
        return f"kol:top:followers:{platform}:{limit}"
    
    @staticmethod
    def kol_top_engagement(platform: str = "all", limit: int = 100) -> str:
        """Sorted set of top KOLs by engagement rate."""
        return f"kol:top:engagement:{platform}:{limit}"
    
    # === CONTENT ===
    
    @staticmethod
    def content_detail(content_id: str) -> str:
        """Single content item hash."""
        return f"content:detail:{content_id}"
    
    @staticmethod
    def content_trending(platform: str = "all", limit: int = 50) -> str:
        """List of trending content IDs."""
        return f"content:trending:{platform}:{limit}"
    
    @staticmethod
    def content_by_kol(kol_id: str) -> str:
        """List of content IDs by KOL."""
        return f"content:by_kol:{kol_id}"
    
    # === STATISTICS ===
    
    @staticmethod
    def stats_platform() -> str:
        """Platform-level statistics hash."""
        return "stats:platform"
    
    @staticmethod
    def stats_daily(date: str) -> str:
        """Daily statistics hash (date format: YYYY-MM-DD)."""
        return f"stats:daily:{date}"
    
    @staticmethod
    def stats_kol(kol_id: str) -> str:
        """KOL-specific statistics."""
        return f"stats:kol:{kol_id}"
    
    # === SEARCH ===
    
    @staticmethod
    def search_autocomplete() -> str:
        """Autocomplete suggestions (sorted set by popularity)."""
        return "search:autocomplete"
    
    @staticmethod
    def search_recent(user_id: str = "anonymous") -> str:
        """Recent searches by user."""
        return f"search:recent:{user_id}"
    
    # === SYSTEM ===
    
    @staticmethod
    def cache_metadata() -> str:
        """Cache metadata (last warm time, version, etc.)."""
        return "cache:metadata"
    
    @staticmethod
    def cache_lock(operation: str) -> str:
        """Distributed lock for cache operations."""
        return f"cache:lock:{operation}"


# Key patterns for bulk operations (using wildcards)
KEY_PATTERNS = {
    "all_profiles": "kol:profile:*",
    "all_content": "content:detail:*",
    "all_stats": "stats:*",
    "all_search": "search:*",
}


# Schema documentation for each key type
SCHEMA = {
    "kol:profile:{kol_id}": {
        "type": "HASH",
        "fields": {
            "kol_id": "string",
            "platform": "string",
            "username": "string",
            "display_name": "string",
            "bio": "string",
            "followers_count": "int",
            "following_count": "int",
            "post_count": "int",
            "verified": "bool",
            "profile_url": "string",
            "profile_image_url": "string",
            "cached_at": "timestamp",
        },
        "ttl": TTL.KOL_PROFILE,
    },
    "kol:top:followers:{platform}:{limit}": {
        "type": "ZSET",
        "description": "Sorted set with kol_id as member, followers_count as score",
        "ttl": TTL.TOP_FOLLOWERS,
    },
    "content:trending:{platform}:{limit}": {
        "type": "LIST",
        "description": "List of content_ids ordered by trending score",
        "ttl": TTL.TRENDING_CONTENT,
    },
    "stats:platform": {
        "type": "HASH",
        "fields": {
            "total_kols": "int",
            "total_content": "int",
            "kols_tiktok": "int",
            "kols_twitter": "int",
            "kols_youtube": "int",
            "content_tiktok": "int",
            "content_youtube": "int",
            "last_updated": "timestamp",
        },
        "ttl": TTL.PLATFORM_STATS,
    },
}


if __name__ == "__main__":
    # Test key generation
    print("=== Cache Key Examples ===")
    print(f"KOL Profile: {CacheKeys.kol_profile('tiktok_user123')}")
    print(f"Top Followers: {CacheKeys.kol_top_followers('tiktok', 50)}")
    print(f"Trending: {CacheKeys.content_trending('all', 100)}")
    print(f"Platform Stats: {CacheKeys.stats_platform()}")
    
    print("\n=== Cache Config ===")
    config = CacheConfig()
    print(f"URL: {config.url}")
    
    docker_config = CacheConfig.for_docker()
    print(f"Docker URL: {docker_config.url}")
