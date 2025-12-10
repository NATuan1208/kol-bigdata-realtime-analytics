"""
Redis Service for API
=====================

Wrapper around serving.cache.CacheClient for API usage.
Provides sync/async interface for FastAPI.
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional

import redis

logger = logging.getLogger(__name__)


class RedisConfig:
    """Redis connection configuration."""
    
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "16379"))  # External port
    db: int = int(os.getenv("REDIS_DB", "0"))
    password: Optional[str] = os.getenv("REDIS_PASSWORD", None)


class RedisService:
    """
    Synchronous Redis client for API.
    
    Uses sync redis-py for simpler integration with FastAPI endpoints.
    For high-performance async, use serving.cache.CacheClient directly.
    """
    
    def __init__(self, config: Optional[RedisConfig] = None):
        self.config = config or RedisConfig()
        self._client: Optional[redis.Redis] = None
    
    def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.Redis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
            )
        return self._client
    
    def ping(self) -> bool:
        """Check Redis connection."""
        try:
            return self._get_client().ping()
        except Exception:
            return False
    
    # =========================================================================
    # KOL PROFILE OPERATIONS
    # =========================================================================
    
    def get_kol_profile(self, kol_id: str) -> Optional[Dict[str, Any]]:
        """Get cached KOL profile by ID."""
        try:
            client = self._get_client()
            key = f"kol:profile:{kol_id}"
            data = client.hgetall(key)
            
            if not data:
                return None
            
            # Convert types
            for field in ["followers_count", "following_count", "post_count", "favorites_count"]:
                if field in data:
                    try:
                        data[field] = int(data[field])
                    except (ValueError, TypeError):
                        data[field] = 0
            
            if "verified" in data:
                data["verified"] = data["verified"].lower() in ("true", "1", "yes")
            
            return data
        except Exception as e:
            logger.error(f"Redis get_kol_profile error: {e}")
            return None
    
    def get_kol_profiles_list(self, platform: str = "all") -> Optional[List[Dict[str, Any]]]:
        """Get cached list of KOL profiles."""
        try:
            client = self._get_client()
            key = f"kol:profiles:list:{platform}"
            data = client.get(key)
            
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            logger.error(f"Redis get_kol_profiles_list error: {e}")
            return None
    
    def set_kol_profile(self, profile: Dict[str, Any], ttl: int = 3600) -> bool:
        """Cache KOL profile."""
        try:
            client = self._get_client()
            kol_id = profile.get("kol_id")
            if not kol_id:
                return False
            
            key = f"kol:profile:{kol_id}"
            # Convert to strings for Redis hash
            str_data = {k: str(v) if v is not None else "" for k, v in profile.items()}
            
            pipe = client.pipeline()
            pipe.hset(key, mapping=str_data)
            pipe.expire(key, ttl)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Redis set_kol_profile error: {e}")
            return False
    
    # =========================================================================
    # TOP KOLS (SORTED SETS)
    # =========================================================================
    
    def get_top_kols_by_followers(
        self, 
        platform: str = "all", 
        limit: int = 100
    ) -> List[tuple]:
        """Get top KOLs by followers from sorted set."""
        try:
            client = self._get_client()
            key = f"kol:top:followers:{platform}:{limit}"
            return client.zrevrange(key, 0, limit - 1, withscores=True)
        except Exception as e:
            logger.error(f"Redis get_top_kols error: {e}")
            return []
    
    def get_top_kols_by_engagement(
        self, 
        platform: str = "all", 
        limit: int = 100
    ) -> List[tuple]:
        """Get top KOLs by engagement from sorted set."""
        try:
            client = self._get_client()
            key = f"kol:top:engagement:{platform}:{limit}"
            return client.zrevrange(key, 0, limit - 1, withscores=True)
        except Exception as e:
            logger.error(f"Redis get_top_kols_by_engagement error: {e}")
            return []
    
    # =========================================================================
    # UNIFIED SCORES (From Hot Path)
    # =========================================================================
    
    def get_unified_scores(self, kol_id: str, platform: str = "tiktok") -> Optional[Dict[str, Any]]:
        """
        Get unified scores from Hot Path streaming.
        
        Keys written by unified_hot_path.py:
        - kol:unified:{platform}:{kol_id} (JSON)
        - streaming_scores:{username} (legacy format)
        """
        try:
            client = self._get_client()
            
            # Try new format first
            key = f"kol:unified:{platform}:{kol_id}"
            data = client.get(key)
            if data:
                return json.loads(data)
            
            # Fallback to legacy format (streaming_scores:{username})
            key_legacy = f"streaming_scores:{kol_id}"
            data_legacy = client.hgetall(key_legacy)
            if data_legacy:
                return {
                    "kol_id": kol_id,
                    "trust_score": float(data_legacy.get("trust_score", 0)),
                    "trending_score": float(data_legacy.get("trending_score", 0)),
                    "success_score": float(data_legacy.get("success_score", 0)),
                    "composite_score": float(data_legacy.get("composite_score", 0)),
                    "source": "streaming_legacy"
                }
            
            return None
        except Exception as e:
            logger.error(f"Redis get_unified_scores error: {e}")
            return None
    
    def get_trending_ranking(
        self, 
        platform: str = "tiktok", 
        metric: str = "composite",
        limit: int = 50
    ) -> List[tuple]:
        """
        Get trending ranking from Hot Path.
        
        Keys: ranking:{platform}:composite, ranking:{platform}:trending
        """
        try:
            client = self._get_client()
            key = f"ranking:{platform}:{metric}"
            return client.zrevrange(key, 0, limit - 1, withscores=True)
        except Exception as e:
            logger.error(f"Redis get_trending_ranking error: {e}")
            return []
    
    # =========================================================================
    # PLATFORM STATISTICS
    # =========================================================================
    
    def get_platform_stats(self) -> Optional[Dict[str, Any]]:
        """Get cached platform statistics."""
        try:
            client = self._get_client()
            key = "stats:platform"
            data = client.hgetall(key)
            
            if not data:
                return None
            
            # Convert numeric fields
            for field in data:
                if field != "last_updated":
                    try:
                        if "." in str(data[field]):
                            data[field] = float(data[field])
                        else:
                            data[field] = int(data[field])
                    except (ValueError, TypeError):
                        pass
            
            return data
        except Exception as e:
            logger.error(f"Redis get_platform_stats error: {e}")
            return None
    
    def set_platform_stats(self, stats: Dict[str, Any], ttl: int = 300) -> bool:
        """Cache platform statistics."""
        try:
            client = self._get_client()
            key = "stats:platform"
            str_data = {k: str(v) for k, v in stats.items()}
            
            pipe = client.pipeline()
            pipe.hset(key, mapping=str_data)
            pipe.expire(key, ttl)
            pipe.execute()
            return True
        except Exception as e:
            logger.error(f"Redis set_platform_stats error: {e}")
            return False
    
    # =========================================================================
    # SEARCH / AUTOCOMPLETE
    # =========================================================================
    
    def get_search_suggestions(self, prefix: str, limit: int = 10) -> List[str]:
        """Get autocomplete suggestions."""
        try:
            client = self._get_client()
            key = "search:autocomplete"
            # Use ZRANGEBYLEX for prefix search
            min_range = f"[{prefix.lower()}"
            max_range = f"[{prefix.lower()}\xff"
            results = client.zrangebylex(key, min_range, max_range, 0, limit)
            return results
        except Exception as e:
            logger.error(f"Redis search suggestions error: {e}")
            return []
    
    # =========================================================================
    # CACHE INFO
    # =========================================================================
    
    def get_cache_info(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            client = self._get_client()
            info = client.info()
            dbsize = client.dbsize()
            
            return {
                "connected": True,
                "total_keys": dbsize,
                "used_memory": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_seconds": info.get("uptime_in_seconds", 0),
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e)
            }
    
    def close(self):
        """Close connection."""
        if self._client:
            self._client.close()
            self._client = None


# Singleton instance
_redis_service: Optional[RedisService] = None


def get_redis_service() -> RedisService:
    """Get or create Redis service singleton."""
    global _redis_service
    if _redis_service is None:
        _redis_service = RedisService()
    return _redis_service


# FastAPI dependency
def get_redis() -> RedisService:
    """FastAPI dependency for Redis service."""
    return get_redis_service()


# Legacy function for backward compatibility
def publish_alert(message: str):
    """Publish alert message to Redis (legacy)."""
    try:
        service = get_redis_service()
        client = service._get_client()
        client.publish("alerts", message)
    except Exception as e:
        logger.error(f"Failed to publish alert: {e}")
