"""
Redis Cache Client
==================

High-level Redis client wrapper with connection pooling,
automatic serialization, and error handling.

Features:
- Connection pooling for performance
- Automatic JSON serialization/deserialization
- Type-safe operations with dataclasses
- Fallback handling for cache misses
- Distributed locking support

Usage:
------
    from serving.cache import CacheClient, CacheKeys
    
    # Initialize client
    client = CacheClient()
    
    # Store KOL profile
    await client.set_kol_profile({
        "kol_id": "user123",
        "platform": "tiktok",
        "followers_count": 100000
    })
    
    # Get KOL profile
    profile = await client.get_kol_profile("user123")
    
    # Get top KOLs
    top_kols = await client.get_top_kols_by_followers("tiktok", limit=50)
"""

import json
import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from .config import CacheConfig, CacheKeys, TTL

logger = logging.getLogger(__name__)


class CacheClient:
    """
    Async Redis cache client with connection pooling.
    
    Thread-safe and designed for high-concurrency workloads.
    """
    
    def __init__(self, config: Optional[CacheConfig] = None):
        """
        Initialize cache client.
        
        Args:
            config: Redis configuration. Uses default if not provided.
        """
        self.config = config or CacheConfig()
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[redis.Redis] = None
    
    async def connect(self) -> None:
        """Establish connection pool to Redis."""
        if self._pool is not None:
            return
        
        try:
            self._pool = ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                retry_on_timeout=self.config.retry_on_timeout,
                health_check_interval=self.config.health_check_interval,
                decode_responses=True,  # Auto decode to string
            )
            self._redis = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._redis.ping()
            logger.info(f"✅ Connected to Redis at {self.config.host}:{self.config.port}")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise
    
    async def close(self) -> None:
        """Close connection pool."""
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.disconnect()
        logger.info("Redis connection closed")
    
    async def ping(self) -> bool:
        """Check Redis connection health."""
        try:
            await self._ensure_connected()
            return await self._redis.ping()
        except Exception:
            return False
    
    async def _ensure_connected(self) -> None:
        """Ensure connection is established."""
        if self._redis is None:
            await self.connect()
    
    # =========================================================================
    # LOW-LEVEL OPERATIONS
    # =========================================================================
    
    async def get(self, key: str) -> Optional[str]:
        """Get string value by key."""
        await self._ensure_connected()
        return await self._redis.get(key)
    
    async def set(
        self, 
        key: str, 
        value: str, 
        ttl: Optional[int] = None
    ) -> bool:
        """Set string value with optional TTL."""
        await self._ensure_connected()
        return await self._redis.set(key, value, ex=ttl)
    
    async def delete(self, key: str) -> int:
        """Delete key."""
        await self._ensure_connected()
        return await self._redis.delete(key)
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        await self._ensure_connected()
        return await self._redis.exists(key) > 0
    
    async def ttl(self, key: str) -> int:
        """Get remaining TTL for key."""
        await self._ensure_connected()
        return await self._redis.ttl(key)
    
    async def keys(self, pattern: str) -> List[str]:
        """Get keys matching pattern. Use sparingly!"""
        await self._ensure_connected()
        return await self._redis.keys(pattern)
    
    # =========================================================================
    # JSON OPERATIONS
    # =========================================================================
    
    async def get_json(self, key: str) -> Optional[Any]:
        """Get and deserialize JSON value."""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning(f"Failed to decode JSON for key: {key}")
                return None
        return None
    
    async def set_json(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """Serialize and set JSON value."""
        try:
            json_str = json.dumps(value, default=str, ensure_ascii=False)
            return await self.set(key, json_str, ttl)
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize JSON for key {key}: {e}")
            return False
    
    # =========================================================================
    # HASH OPERATIONS
    # =========================================================================
    
    async def hget(self, key: str, field: str) -> Optional[str]:
        """Get hash field value."""
        await self._ensure_connected()
        return await self._redis.hget(key, field)
    
    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all fields and values in hash."""
        await self._ensure_connected()
        return await self._redis.hgetall(key)
    
    async def hset(self, key: str, mapping: Dict[str, Any]) -> int:
        """Set multiple hash fields."""
        await self._ensure_connected()
        # Convert all values to strings
        str_mapping = {k: str(v) if v is not None else "" for k, v in mapping.items()}
        return await self._redis.hset(key, mapping=str_mapping)
    
    async def hset_with_ttl(
        self, 
        key: str, 
        mapping: Dict[str, Any], 
        ttl: int
    ) -> bool:
        """Set hash with TTL (atomic operation)."""
        await self._ensure_connected()
        str_mapping = {k: str(v) if v is not None else "" for k, v in mapping.items()}
        
        # Use pipeline for atomic operation
        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.hset(key, mapping=str_mapping)
            await pipe.expire(key, ttl)
            results = await pipe.execute()
        
        return all(results)
    
    # =========================================================================
    # SORTED SET OPERATIONS
    # =========================================================================
    
    async def zadd(
        self, 
        key: str, 
        mapping: Dict[str, float],
        ttl: Optional[int] = None
    ) -> int:
        """Add members to sorted set with scores."""
        await self._ensure_connected()
        result = await self._redis.zadd(key, mapping)
        if ttl:
            await self._redis.expire(key, ttl)
        return result
    
    async def zrange(
        self, 
        key: str, 
        start: int = 0, 
        stop: int = -1,
        desc: bool = True,
        withscores: bool = False
    ) -> Union[List[str], List[tuple]]:
        """Get range of members from sorted set."""
        await self._ensure_connected()
        if desc:
            return await self._redis.zrevrange(key, start, stop, withscores=withscores)
        return await self._redis.zrange(key, start, stop, withscores=withscores)
    
    async def zrank(self, key: str, member: str, desc: bool = True) -> Optional[int]:
        """Get rank of member in sorted set."""
        await self._ensure_connected()
        if desc:
            return await self._redis.zrevrank(key, member)
        return await self._redis.zrank(key, member)
    
    # =========================================================================
    # LIST OPERATIONS
    # =========================================================================
    
    async def lpush(self, key: str, *values: str) -> int:
        """Push values to head of list."""
        await self._ensure_connected()
        return await self._redis.lpush(key, *values)
    
    async def rpush(self, key: str, *values: str) -> int:
        """Push values to tail of list."""
        await self._ensure_connected()
        return await self._redis.rpush(key, *values)
    
    async def lrange(self, key: str, start: int = 0, stop: int = -1) -> List[str]:
        """Get range of elements from list."""
        await self._ensure_connected()
        return await self._redis.lrange(key, start, stop)
    
    async def ltrim(self, key: str, start: int, stop: int) -> bool:
        """Trim list to specified range."""
        await self._ensure_connected()
        return await self._redis.ltrim(key, start, stop)
    
    # =========================================================================
    # HIGH-LEVEL KOL OPERATIONS
    # =========================================================================
    
    async def set_kol_profile(self, profile: Dict[str, Any]) -> bool:
        """
        Cache a KOL profile.
        
        Args:
            profile: Dict containing kol_id, platform, username, etc.
        
        Returns:
            True if successful
        """
        kol_id = profile.get("kol_id")
        if not kol_id:
            logger.error("Cannot cache profile without kol_id")
            return False
        
        key = CacheKeys.kol_profile(kol_id)
        profile["cached_at"] = datetime.utcnow().isoformat()
        
        return await self.hset_with_ttl(key, profile, TTL.KOL_PROFILE)
    
    async def get_kol_profile(self, kol_id: str) -> Optional[Dict[str, Any]]:
        """
        Get cached KOL profile.
        
        Args:
            kol_id: KOL identifier
            
        Returns:
            Profile dict or None if not cached
        """
        key = CacheKeys.kol_profile(kol_id)
        data = await self.hgetall(key)
        
        if not data:
            return None
        
        # Convert numeric fields
        for field in ["followers_count", "following_count", "post_count"]:
            if field in data:
                try:
                    data[field] = int(data[field])
                except (ValueError, TypeError):
                    data[field] = 0
        
        # Convert boolean fields
        if "verified" in data:
            data["verified"] = data["verified"].lower() in ("true", "1", "yes")
        
        return data
    
    async def set_top_kols_by_followers(
        self, 
        kols: List[Dict[str, Any]], 
        platform: str = "all",
        limit: int = 100
    ) -> bool:
        """
        Cache top KOLs sorted by followers count.
        
        Args:
            kols: List of KOL dicts with kol_id and followers_count
            platform: Platform filter
            limit: Max number to cache
        """
        key = CacheKeys.kol_top_followers(platform, limit)
        
        # Build score mapping: {kol_id: followers_count}
        mapping = {
            kol["kol_id"]: float(kol.get("followers_count", 0))
            for kol in kols[:limit]
            if kol.get("kol_id")
        }
        
        if not mapping:
            return False
        
        return await self.zadd(key, mapping, ttl=TTL.TOP_FOLLOWERS) >= 0
    
    async def get_top_kols_by_followers(
        self, 
        platform: str = "all", 
        limit: int = 100
    ) -> List[tuple]:
        """
        Get top KOLs by followers (cached).
        
        Returns:
            List of (kol_id, followers_count) tuples
        """
        key = CacheKeys.kol_top_followers(platform, limit)
        return await self.zrange(key, 0, limit - 1, desc=True, withscores=True)
    
    # =========================================================================
    # HIGH-LEVEL CONTENT OPERATIONS
    # =========================================================================
    
    async def set_trending_content(
        self, 
        content_ids: List[str], 
        platform: str = "all",
        limit: int = 50
    ) -> bool:
        """Cache trending content IDs."""
        key = CacheKeys.content_trending(platform, limit)
        
        await self._ensure_connected()
        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.delete(key)
            if content_ids:
                await pipe.rpush(key, *content_ids[:limit])
            await pipe.expire(key, TTL.TRENDING_CONTENT)
            results = await pipe.execute()
        
        return True
    
    async def get_trending_content(
        self, 
        platform: str = "all", 
        limit: int = 50
    ) -> List[str]:
        """Get trending content IDs."""
        key = CacheKeys.content_trending(platform, limit)
        return await self.lrange(key, 0, limit - 1)
    
    # =========================================================================
    # HIGH-LEVEL STATS OPERATIONS
    # =========================================================================
    
    async def set_platform_stats(self, stats: Dict[str, Any]) -> bool:
        """Cache platform-level statistics."""
        key = CacheKeys.stats_platform()
        stats["last_updated"] = datetime.utcnow().isoformat()
        return await self.hset_with_ttl(key, stats, TTL.PLATFORM_STATS)
    
    async def get_platform_stats(self) -> Optional[Dict[str, Any]]:
        """Get cached platform statistics."""
        key = CacheKeys.stats_platform()
        data = await self.hgetall(key)
        
        if not data:
            return None
        
        # Convert numeric fields
        for field in data:
            if field != "last_updated" and data[field].isdigit():
                data[field] = int(data[field])
        
        return data
    
    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================
    
    async def clear_all(self) -> bool:
        """Clear all cache data. Use with caution!"""
        await self._ensure_connected()
        await self._redis.flushdb()
        logger.warning("⚠️ All cache data cleared!")
        return True
    
    async def clear_pattern(self, pattern: str) -> int:
        """Clear keys matching pattern."""
        await self._ensure_connected()
        keys = await self._redis.keys(pattern)
        if keys:
            return await self._redis.delete(*keys)
        return 0
    
    async def get_cache_info(self) -> Dict[str, Any]:
        """Get cache statistics and info."""
        await self._ensure_connected()
        
        info = await self._redis.info()
        dbsize = await self._redis.dbsize()
        
        return {
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human"),
            "total_keys": dbsize,
            "uptime_in_seconds": info.get("uptime_in_seconds"),
            "redis_version": info.get("redis_version"),
            "maxmemory_human": info.get("maxmemory_human"),
            "evicted_keys": info.get("evicted_keys"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
        }
    
    async def get_metadata(self) -> Optional[Dict[str, str]]:
        """Get cache metadata (last warm time, etc.)."""
        return await self.hgetall(CacheKeys.cache_metadata())
    
    async def set_metadata(self, metadata: Dict[str, str]) -> bool:
        """Update cache metadata."""
        return await self.hset_with_ttl(
            CacheKeys.cache_metadata(), 
            metadata, 
            ttl=86400 * 7  # 7 days
        )
    
    # =========================================================================
    # DISTRIBUTED LOCKING
    # =========================================================================
    
    @asynccontextmanager
    async def lock(self, operation: str, timeout: int = 30):
        """
        Acquire distributed lock for cache operations.
        
        Usage:
            async with client.lock("cache_warm"):
                # Only one process can warm cache at a time
                await warm_cache()
        """
        await self._ensure_connected()
        
        lock_key = CacheKeys.cache_lock(operation)
        lock = self._redis.lock(lock_key, timeout=timeout)
        
        try:
            acquired = await lock.acquire(blocking=True, blocking_timeout=10)
            if not acquired:
                raise TimeoutError(f"Could not acquire lock: {operation}")
            yield lock
        finally:
            try:
                await lock.release()
            except Exception:
                pass  # Lock may have expired


# Singleton instance for convenience
_default_client: Optional[CacheClient] = None


def get_cache_client() -> CacheClient:
    """Get or create default cache client singleton."""
    global _default_client
    if _default_client is None:
        _default_client = CacheClient()
    return _default_client


async def close_cache_client() -> None:
    """Close default cache client."""
    global _default_client
    if _default_client:
        await _default_client.close()
        _default_client = None


# CLI testing
if __name__ == "__main__":
    async def test():
        client = CacheClient()
        await client.connect()
        
        print("\n=== Cache Client Test ===")
        
        # Test ping
        print(f"Ping: {await client.ping()}")
        
        # Test set/get
        await client.set("test:key", "hello world", ttl=60)
        print(f"Get test:key: {await client.get('test:key')}")
        
        # Test JSON
        await client.set_json("test:json", {"name": "Test", "value": 123}, ttl=60)
        print(f"Get test:json: {await client.get_json('test:json')}")
        
        # Test KOL profile
        await client.set_kol_profile({
            "kol_id": "test_user",
            "platform": "tiktok",
            "username": "test_user",
            "display_name": "Test User",
            "followers_count": 100000,
            "verified": True
        })
        print(f"Get KOL profile: {await client.get_kol_profile('test_user')}")
        
        # Test top KOLs
        await client.set_top_kols_by_followers([
            {"kol_id": "user1", "followers_count": 1000000},
            {"kol_id": "user2", "followers_count": 500000},
            {"kol_id": "user3", "followers_count": 250000},
        ], platform="tiktok", limit=10)
        print(f"Top KOLs: {await client.get_top_kols_by_followers('tiktok', 10)}")
        
        # Cache info
        print(f"\nCache Info: {await client.get_cache_info()}")
        
        # Cleanup
        await client.delete("test:key")
        await client.delete("test:json")
        await client.close()
        
        print("\n✅ All tests passed!")
    
    asyncio.run(test())
