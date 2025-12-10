"""
Statistics Router (v1)
======================

REST API endpoints for platform statistics.

Endpoints:
    GET /api/v1/stats           - Overall platform statistics
    GET /api/v1/stats/platforms - Stats grouped by platform
    GET /api/v1/stats/cache     - Cache statistics
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..services.redis_client import RedisService, get_redis
from ..services.trino_client import TrinoService, get_trino

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class PlatformStats(BaseModel):
    """Overall platform statistics."""
    total_kols: int = 0
    platforms_count: int = 0
    total_followers: int = 0
    avg_followers: float = 0.0
    total_posts: int = 0
    avg_posts: float = 0.0
    verified_count: int = 0
    last_updated: Optional[str] = None
    data_source: str = "unknown"


class PlatformBreakdown(BaseModel):
    """Statistics for a single platform."""
    platform: str
    kol_count: int = 0
    total_followers: int = 0
    avg_followers: float = 0.0
    max_followers: int = 0
    total_posts: int = 0


class PlatformBreakdownResponse(BaseModel):
    """Response with stats for all platforms."""
    platforms: List[PlatformBreakdown]
    total_kols: int
    data_source: str = "unknown"


class CacheStats(BaseModel):
    """Redis cache statistics."""
    connected: bool
    total_keys: int = 0
    used_memory: str = "N/A"
    connected_clients: int = 0
    uptime_seconds: int = 0
    hit_rate: Optional[float] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str = "1.0.0"
    services: Dict[str, bool]
    timestamp: str


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("", response_model=PlatformStats)
async def get_platform_stats(
    redis: RedisService = Depends(get_redis),
    trino: TrinoService = Depends(get_trino)
):
    """
    Get overall platform statistics.
    
    **Cache-first pattern:**
    1. Check Redis cache (`stats:platform` hash)
    2. If miss, query Trino Silver layer
    3. Cache result for 5 minutes
    
    **Returns:**
    - Total KOLs count
    - Platform count
    - Follower statistics (total, average)
    - Post statistics (total, average)
    - Verified accounts count
    """
    # Try cache first
    cached_stats = redis.get_platform_stats()
    
    if cached_stats:
        return PlatformStats(
            **cached_stats,
            data_source="cache"
        )
    
    # Cache miss - query Trino
    stats = await trino.get_platform_stats()
    
    if stats:
        # Cache for 5 minutes
        stats["last_updated"] = datetime.utcnow().isoformat()
        redis.set_platform_stats(stats, ttl=300)
        
        return PlatformStats(
            **stats,
            data_source="database"
        )
    
    return PlatformStats(data_source="unavailable")


@router.get("/platforms", response_model=PlatformBreakdownResponse)
async def get_stats_by_platform(
    trino: TrinoService = Depends(get_trino)
):
    """
    Get statistics grouped by platform.
    
    **Returns:**
    Statistics for each platform (tiktok, youtube, twitter, etc.):
    - KOL count
    - Total followers
    - Average followers
    - Max followers
    - Total posts
    """
    platform_stats = await trino.get_stats_by_platform()
    
    total_kols = sum(p.get("kol_count", 0) for p in platform_stats)
    
    return PlatformBreakdownResponse(
        platforms=[PlatformBreakdown(**p) for p in platform_stats],
        total_kols=total_kols,
        data_source="database"
    )


@router.get("/cache", response_model=CacheStats)
async def get_cache_stats(
    redis: RedisService = Depends(get_redis)
):
    """
    Get Redis cache statistics.
    
    **Returns:**
    - Connection status
    - Total keys in cache
    - Memory usage
    - Connected clients
    - Uptime
    """
    info = redis.get_cache_info()
    
    return CacheStats(
        connected=info.get("connected", False),
        total_keys=info.get("total_keys", 0),
        used_memory=info.get("used_memory", "N/A"),
        connected_clients=info.get("connected_clients", 0),
        uptime_seconds=info.get("uptime_seconds", 0)
    )


@router.get("/health", response_model=HealthResponse)
async def health_check(
    redis: RedisService = Depends(get_redis),
    trino: TrinoService = Depends(get_trino)
):
    """
    Comprehensive health check for all services.
    
    **Checks:**
    - Redis connection
    - Trino connection
    
    **Returns:**
    - Overall status (healthy/degraded/unhealthy)
    - Individual service status
    """
    redis_ok = redis.ping()
    trino_ok = await trino.health_check()
    
    all_ok = redis_ok and trino_ok
    any_ok = redis_ok or trino_ok
    
    if all_ok:
        status = "healthy"
    elif any_ok:
        status = "degraded"
    else:
        status = "unhealthy"
    
    return HealthResponse(
        status=status,
        services={
            "redis": redis_ok,
            "trino": trino_ok
        },
        timestamp=datetime.utcnow().isoformat()
    )


@router.get("/summary")
async def get_summary(
    redis: RedisService = Depends(get_redis),
    trino: TrinoService = Depends(get_trino)
):
    """
    Get comprehensive summary for dashboard.
    
    **Returns combined data:**
    - Platform stats
    - Cache stats
    - Service health
    - Top KOLs preview
    """
    # Platform stats
    cached_stats = redis.get_platform_stats()
    if not cached_stats:
        cached_stats = await trino.get_platform_stats()
    
    # Cache stats
    cache_info = redis.get_cache_info()
    
    # Service health
    redis_ok = redis.ping()
    trino_ok = await trino.health_check()
    
    # Top 5 KOLs
    top_kols = redis.get_top_kols_by_followers("all", 5)
    
    return {
        "platform_stats": cached_stats or {},
        "cache_stats": {
            "total_keys": cache_info.get("total_keys", 0),
            "used_memory": cache_info.get("used_memory", "N/A"),
        },
        "services": {
            "redis": "online" if redis_ok else "offline",
            "trino": "online" if trino_ok else "offline",
        },
        "top_5_kols": [
            {"kol_id": kol_id, "followers": int(score)} 
            for kol_id, score in (top_kols or [])
        ],
        "timestamp": datetime.utcnow().isoformat()
    }
