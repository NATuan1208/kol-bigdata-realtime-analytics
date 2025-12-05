"""
Cache Warmer Script
===================

Load hot data from Silver layer (via Trino) into Redis cache.

This script should be run:
1. On system startup (initial cache population)
2. Periodically via scheduler (keep cache fresh)
3. After ETL completes (sync new data)

Data Sources:
- Silver kol_profiles → Redis kol:profile:*, kol:top:*
- Silver kol_content → Redis content:*, stats:*

Usage:
------
    # Full cache warm (all data)
    python scripts/cache_warmer.py --full
    
    # Warm specific data types
    python scripts/cache_warmer.py --profiles --stats
    
    # Dry run (no write to Redis)
    python scripts/cache_warmer.py --dry-run

Environment Variables:
    TRINO_HOST: Trino host (default: localhost)
    TRINO_PORT: Trino port (default: 18080)
    REDIS_HOST: Redis host (default: localhost)
    REDIS_PORT: Redis port (default: 16379)
"""

import os
import sys
import asyncio
import argparse
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trino.dbapi import connect as trino_connect
from trino.auth import BasicAuthentication

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TrinoClient:
    """Simple Trino client for querying Silver layer."""
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = "admin",
        catalog: str = "kol_hive",
        schema: str = "kol_silver"
    ):
        self.host = host or os.getenv("TRINO_HOST", "localhost")
        self.port = port or int(os.getenv("TRINO_PORT", "18080"))
        self.user = user
        self.catalog = catalog
        self.schema = schema
        self._conn = None
    
    def connect(self):
        """Establish connection to Trino."""
        self._conn = trino_connect(
            host=self.host,
            port=self.port,
            user=self.user,
            catalog=self.catalog,
            schema=self.schema,
        )
        logger.info(f"✅ Connected to Trino at {self.host}:{self.port}")
        return self._conn
    
    def execute(self, query: str) -> List[tuple]:
        """Execute query and return results."""
        if not self._conn:
            self.connect()
        
        cursor = self._conn.cursor()
        cursor.execute(query)
        results = cursor.fetchall()
        cursor.close()
        return results
    
    def execute_dict(self, query: str) -> List[Dict[str, Any]]:
        """Execute query and return list of dicts."""
        if not self._conn:
            self.connect()
        
        cursor = self._conn.cursor()
        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        cursor.close()
        return results
    
    def close(self):
        """Close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


class CacheWarmer:
    """
    Cache warming utility.
    
    Loads data from Trino (Silver layer) into Redis cache.
    """
    
    def __init__(
        self,
        trino_client: Optional[TrinoClient] = None,
        redis_host: str = None,
        redis_port: int = None,
        dry_run: bool = False
    ):
        self.trino = trino_client or TrinoClient()
        self.redis_host = redis_host or os.getenv("REDIS_HOST", "localhost")
        self.redis_port = redis_port or int(os.getenv("REDIS_PORT", "16379"))
        self.dry_run = dry_run
        self._redis = None
        self._stats = {
            "profiles_cached": 0,
            "content_cached": 0,
            "stats_cached": 0,
            "errors": 0,
            "start_time": None,
            "end_time": None,
        }
    
    async def connect_redis(self):
        """Connect to Redis."""
        # Import here to avoid dependency issues
        from serving.cache.client import CacheClient
        from serving.cache.config import CacheConfig
        
        config = CacheConfig(
            host=self.redis_host,
            port=self.redis_port
        )
        self._redis = CacheClient(config)
        await self._redis.connect()
        logger.info(f"✅ Connected to Redis at {self.redis_host}:{self.redis_port}")
    
    async def close(self):
        """Close all connections."""
        if self._redis:
            await self._redis.close()
        if self.trino:
            self.trino.close()
    
    def _fetch_profiles(self, platform: str = None, limit: int = None) -> List[Dict]:
        """Fetch KOL profiles from Silver layer."""
        query = """
            SELECT 
                kol_id,
                platform,
                username,
                display_name,
                COALESCE(description, '') as bio,
                COALESCE(followers_count, 0) as followers_count,
                COALESCE(following_count, 0) as following_count,
                COALESCE(post_count, 0) as post_count,
                'false' as verified,
                profile_url
            FROM kol_profiles
        """
        
        if platform:
            query += f" WHERE platform = '{platform}'"
        
        query += " ORDER BY followers_count DESC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        return self.trino.execute_dict(query)
    
    def _fetch_platform_stats(self) -> Dict[str, int]:
        """Fetch platform-level statistics."""
        # KOL stats
        kol_query = """
            SELECT platform, COUNT(*) as count
            FROM kol_profiles
            GROUP BY platform
        """
        kol_results = self.trino.execute_dict(kol_query)
        
        # Content stats
        content_query = """
            SELECT platform, COUNT(*) as count
            FROM kol_content
            GROUP BY platform
        """
        content_results = self.trino.execute_dict(content_query)
        
        stats = {
            "total_kols": sum(r["count"] for r in kol_results),
            "total_content": sum(r["count"] for r in content_results),
        }
        
        # Per-platform KOL counts
        for r in kol_results:
            stats[f"kols_{r['platform']}"] = r["count"]
        
        # Per-platform content counts
        for r in content_results:
            stats[f"content_{r['platform']}"] = r["count"]
        
        return stats
    
    def _fetch_top_kols(self, platform: str = "all", limit: int = 100) -> List[Dict]:
        """Fetch top KOLs by followers."""
        query = f"""
            SELECT 
                kol_id,
                platform,
                display_name,
                COALESCE(followers_count, 0) as followers_count
            FROM kol_profiles
        """
        
        if platform != "all":
            query += f" WHERE platform = '{platform}'"
        
        query += f"""
            ORDER BY followers_count DESC
            LIMIT {limit}
        """
        
        return self.trino.execute_dict(query)
    
    def _fetch_trending_content(self, platform: str = "all", limit: int = 50) -> List[Dict]:
        """Fetch trending content (by views/likes)."""
        query = f"""
            SELECT 
                content_id,
                kol_id,
                platform,
                COALESCE(views, 0) as views,
                COALESCE(likes, 0) as likes
            FROM kol_content
        """
        
        if platform != "all":
            query += f" WHERE platform = '{platform}'"
        
        query += f"""
            ORDER BY (COALESCE(views, 0) + COALESCE(likes, 0) * 10) DESC
            LIMIT {limit}
        """
        
        return self.trino.execute_dict(query)
    
    async def warm_profiles(self, limit: int = None) -> int:
        """
        Cache KOL profiles.
        
        Args:
            limit: Max profiles to cache (None = all)
            
        Returns:
            Number of profiles cached
        """
        logger.info("📥 Warming KOL profiles cache...")
        
        profiles = self._fetch_profiles(limit=limit)
        logger.info(f"   Fetched {len(profiles)} profiles from Silver")
        
        if self.dry_run:
            logger.info(f"   [DRY RUN] Would cache {len(profiles)} profiles")
            return len(profiles)
        
        cached = 0
        for profile in profiles:
            try:
                await self._redis.set_kol_profile(profile)
                cached += 1
            except Exception as e:
                logger.error(f"   Failed to cache profile {profile.get('kol_id')}: {e}")
                self._stats["errors"] += 1
        
        self._stats["profiles_cached"] = cached
        logger.info(f"   ✅ Cached {cached} profiles")
        return cached
    
    async def warm_top_kols(self, platforms: List[str] = None, limit: int = 100) -> int:
        """
        Cache top KOLs sorted sets.
        
        Args:
            platforms: List of platforms (None = ["all", "tiktok", "twitter", "youtube"])
            limit: Number of top KOLs per platform
            
        Returns:
            Total entries cached
        """
        logger.info("📊 Warming top KOLs cache...")
        
        platforms = platforms or ["all", "tiktok", "twitter", "youtube"]
        total = 0
        
        for platform in platforms:
            try:
                kols = self._fetch_top_kols(platform, limit)
                
                if self.dry_run:
                    logger.info(f"   [DRY RUN] {platform}: Would cache {len(kols)} top KOLs")
                    total += len(kols)
                    continue
                
                await self._redis.set_top_kols_by_followers(kols, platform, limit)
                total += len(kols)
                logger.info(f"   ✅ {platform}: Cached {len(kols)} top KOLs")
                
            except Exception as e:
                logger.error(f"   Failed to cache top KOLs for {platform}: {e}")
                self._stats["errors"] += 1
        
        return total
    
    async def warm_trending_content(self, platforms: List[str] = None, limit: int = 50) -> int:
        """
        Cache trending content.
        
        Args:
            platforms: List of platforms
            limit: Number of trending items per platform
            
        Returns:
            Total entries cached
        """
        logger.info("🔥 Warming trending content cache...")
        
        platforms = platforms or ["all", "tiktok", "youtube"]
        total = 0
        
        for platform in platforms:
            try:
                content = self._fetch_trending_content(platform, limit)
                content_ids = [c["content_id"] for c in content]
                
                if self.dry_run:
                    logger.info(f"   [DRY RUN] {platform}: Would cache {len(content_ids)} trending items")
                    total += len(content_ids)
                    continue
                
                await self._redis.set_trending_content(content_ids, platform, limit)
                total += len(content_ids)
                logger.info(f"   ✅ {platform}: Cached {len(content_ids)} trending items")
                
            except Exception as e:
                logger.error(f"   Failed to cache trending for {platform}: {e}")
                self._stats["errors"] += 1
        
        self._stats["content_cached"] = total
        return total
    
    async def warm_platform_stats(self) -> bool:
        """Cache platform statistics."""
        logger.info("📈 Warming platform stats cache...")
        
        try:
            stats = self._fetch_platform_stats()
            
            if self.dry_run:
                logger.info(f"   [DRY RUN] Would cache stats: {stats}")
                return True
            
            await self._redis.set_platform_stats(stats)
            self._stats["stats_cached"] = 1
            logger.info(f"   ✅ Cached platform stats: {stats}")
            return True
            
        except Exception as e:
            logger.error(f"   Failed to cache platform stats: {e}")
            self._stats["errors"] += 1
            return False
    
    async def warm_all(self) -> Dict[str, Any]:
        """
        Warm all cache data.
        
        Returns:
            Statistics dict
        """
        self._stats["start_time"] = datetime.utcnow().isoformat()
        
        print("\n" + "=" * 60)
        print("🚀 CACHE WARMER - FULL WARM")
        print("=" * 60)
        print(f"   Trino: {self.trino.host}:{self.trino.port}")
        print(f"   Redis: {self.redis_host}:{self.redis_port}")
        print(f"   Dry Run: {self.dry_run}")
        print("=" * 60)
        
        await self.connect_redis()
        
        # Warm in order of priority
        await self.warm_platform_stats()
        await self.warm_top_kols()
        await self.warm_trending_content()
        await self.warm_profiles(limit=1000)  # Top 1000 profiles
        
        # Update metadata
        if not self.dry_run:
            await self._redis.set_metadata({
                "last_full_warm": datetime.utcnow().isoformat(),
                "profiles_cached": str(self._stats["profiles_cached"]),
                "errors": str(self._stats["errors"]),
            })
        
        self._stats["end_time"] = datetime.utcnow().isoformat()
        
        # Print summary
        print("\n" + "=" * 60)
        print("📋 CACHE WARM SUMMARY")
        print("=" * 60)
        print(f"   Profiles cached: {self._stats['profiles_cached']}")
        print(f"   Content cached: {self._stats['content_cached']}")
        print(f"   Stats cached: {self._stats['stats_cached']}")
        print(f"   Errors: {self._stats['errors']}")
        print(f"   Start: {self._stats['start_time']}")
        print(f"   End: {self._stats['end_time']}")
        
        if not self.dry_run:
            # Show cache info
            cache_info = await self._redis.get_cache_info()
            print(f"\n   Redis Memory: {cache_info.get('used_memory_human')}")
            print(f"   Total Keys: {cache_info.get('total_keys')}")
        
        print("=" * 60)
        
        await self.close()
        return self._stats


async def main():
    parser = argparse.ArgumentParser(description="Cache Warmer for KOL Platform")
    parser.add_argument("--full", action="store_true", help="Full cache warm (all data)")
    parser.add_argument("--profiles", action="store_true", help="Warm profiles cache")
    parser.add_argument("--stats", action="store_true", help="Warm statistics cache")
    parser.add_argument("--top", action="store_true", help="Warm top KOLs cache")
    parser.add_argument("--trending", action="store_true", help="Warm trending content cache")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to Redis")
    parser.add_argument("--limit", type=int, default=1000, help="Limit for profiles")
    parser.add_argument("--trino-host", type=str, help="Trino host")
    parser.add_argument("--trino-port", type=int, help="Trino port")
    parser.add_argument("--redis-host", type=str, help="Redis host")
    parser.add_argument("--redis-port", type=int, help="Redis port")
    
    args = parser.parse_args()
    
    # Create warmer
    trino_client = TrinoClient(
        host=args.trino_host,
        port=args.trino_port
    )
    
    warmer = CacheWarmer(
        trino_client=trino_client,
        redis_host=args.redis_host,
        redis_port=args.redis_port,
        dry_run=args.dry_run
    )
    
    try:
        # Full warm or specific data types
        if args.full or not any([args.profiles, args.stats, args.top, args.trending]):
            await warmer.warm_all()
        else:
            await warmer.connect_redis()
            
            if args.stats:
                await warmer.warm_platform_stats()
            if args.top:
                await warmer.warm_top_kols()
            if args.trending:
                await warmer.warm_trending_content()
            if args.profiles:
                await warmer.warm_profiles(limit=args.limit)
            
            await warmer.close()
    
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Error: {e}")
        raise
    finally:
        await warmer.close()


if __name__ == "__main__":
    asyncio.run(main())
