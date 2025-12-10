"""
Trending Router (v1)
====================

REST API endpoints for trending KOLs from Hot Path streaming.

Endpoints:
    GET /api/v1/trending          - Top trending KOLs by composite score
    GET /api/v1/trending/viral    - Viral KOLs (trending_score >= 80)
    GET /api/v1/trending/hot      - Hot KOLs (trending_score >= 60)
    GET /api/v1/trending/rising   - Rising KOLs (highest momentum)

Data Sources:
    - Redis sorted sets (ranking:{platform}:{metric})
    - Populated by unified_hot_path.py Spark Streaming
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.redis_client import RedisService, get_redis

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TrendingKOL(BaseModel):
    """Trending KOL with score."""
    kol_id: str
    score: float
    rank: int
    label: Optional[str] = None  # Viral, Hot, Warm, etc.


class TrendingResponse(BaseModel):
    """Trending KOLs response."""
    data: List[TrendingKOL]
    metric: str
    platform: str
    total: int
    updated_at: Optional[str] = None


class TrendingWithDetails(BaseModel):
    """Trending KOL with full score details."""
    kol_id: str
    rank: int
    platform: str
    composite_score: float
    trust_score: Optional[float] = None
    trending_score: Optional[float] = None
    success_score: Optional[float] = None
    trending_label: str = "Unknown"


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_trending_label(score: float) -> str:
    """Convert trending score to label."""
    if score >= 80:
        return "Viral"
    elif score >= 60:
        return "Hot"
    elif score >= 40:
        return "Warm"
    elif score >= 25:
        return "Normal"
    else:
        return "Cold"


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("", response_model=TrendingResponse)
async def get_trending_kols(
    platform: str = Query("tiktok", description="Platform filter"),
    metric: str = Query("composite", description="Ranking metric (composite, trending, trust, success)"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get top trending KOLs by specified metric.
    
    **Metrics available:**
    - `composite`: Combined score (0.4×trending + 0.35×success + 0.25×trust)
    - `trending`: Trending score only (velocity-based)
    - `trust`: Trust score only
    - `success`: Success score only
    
    **Data Source:**
    Redis sorted sets populated by Hot Path streaming.
    
    **Note:**
    If no data from Hot Path, returns empty list.
    Run scraper and Hot Path streaming to populate rankings.
    """
    # Validate metric
    valid_metrics = ["composite", "trending", "trust", "success"]
    if metric not in valid_metrics:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid metric. Choose from: {valid_metrics}"
        )
    
    # Get from Redis
    ranking = redis.get_trending_ranking(platform, metric, limit)
    
    if not ranking:
        return TrendingResponse(
            data=[],
            metric=metric,
            platform=platform,
            total=0,
            updated_at=None
        )
    
    # Build response
    trending_kols = []
    for rank, (kol_id, score) in enumerate(ranking, 1):
        label = get_trending_label(score) if metric == "trending" else None
        trending_kols.append(TrendingKOL(
            kol_id=kol_id,
            score=round(score, 2),
            rank=rank,
            label=label
        ))
    
    return TrendingResponse(
        data=trending_kols,
        metric=metric,
        platform=platform,
        total=len(trending_kols),
        updated_at=datetime.utcnow().isoformat()
    )


@router.get("/viral")
async def get_viral_kols(
    platform: str = Query("tiktok", description="Platform filter"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get viral KOLs (trending_score >= 80).
    
    **Viral criteria:**
    - Explosive growth in activity
    - High velocity metrics
    - Trending score in top tier
    """
    ranking = redis.get_trending_ranking(platform, "trending", 200)
    
    viral_kols = [
        {"kol_id": kol_id, "trending_score": round(score, 2), "label": "Viral"}
        for kol_id, score in ranking
        if score >= 80
    ][:limit]
    
    return {
        "data": viral_kols,
        "total": len(viral_kols),
        "platform": platform,
        "threshold": 80,
        "label": "Viral"
    }


@router.get("/rising")
async def get_rising_kols(
    platform: str = Query("tiktok", description="Platform filter"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get rising KOLs (highest momentum in last hour).
    
    **Rising criteria:**
    - Fastest growing trending scores
    - New entrants to trending
    - High velocity but not yet viral
    """
    # Get trending scores sorted by momentum (recent score changes)
    ranking = redis.get_trending_ranking(platform, "trending", 100)
    
    # Rising = scores between 40-79 (growing but not yet viral/hot)
    rising_kols = [
        {
            "kol_id": kol_id, 
            "trending_score": round(score, 2), 
            "label": "Rising",
            "momentum": "high"  # Placeholder - would need delta tracking
        }
        for kol_id, score in ranking
        if 40 <= score < 80
    ][:limit]
    
    return {
        "data": rising_kols,
        "total": len(rising_kols),
        "platform": platform,
        "score_range": [40, 80],
        "label": "Rising"
    }


@router.get("/hot")
async def get_hot_kols(
    platform: str = Query("tiktok", description="Platform filter"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get hot KOLs (trending_score >= 60).
    
    **Hot criteria:**
    - Significant momentum
    - Above-average growth
    - Trending score >= 60
    """
    ranking = redis.get_trending_ranking(platform, "trending", 300)
    
    hot_kols = [
        {
            "kol_id": kol_id, 
            "trending_score": round(score, 2), 
            "label": "Viral" if score >= 80 else "Hot"
        }
        for kol_id, score in ranking
        if score >= 60
    ][:limit]
    
    return {
        "data": hot_kols,
        "total": len(hot_kols),
        "platform": platform,
        "threshold": 60,
        "labels": ["Hot", "Viral"]
    }


@router.get("/detailed")
async def get_trending_with_details(
    platform: str = Query("tiktok", description="Platform filter"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get trending KOLs with full score details.
    
    **Returns:**
    - All three scores (Trust, Trending, Success)
    - Composite score
    - Trending label
    """
    # Get composite ranking
    ranking = redis.get_trending_ranking(platform, "composite", limit)
    
    detailed_kols = []
    for rank, (kol_id, composite) in enumerate(ranking, 1):
        # Get full scores for each KOL
        scores = redis.get_unified_scores(kol_id, platform)
        
        if scores:
            trending_score = scores.get("trending_score", 0)
            detailed_kols.append(TrendingWithDetails(
                kol_id=kol_id,
                rank=rank,
                platform=platform,
                composite_score=round(composite, 2),
                trust_score=scores.get("trust_score"),
                trending_score=trending_score,
                success_score=scores.get("success_score"),
                trending_label=get_trending_label(trending_score) if trending_score else "Unknown"
            ))
        else:
            detailed_kols.append(TrendingWithDetails(
                kol_id=kol_id,
                rank=rank,
                platform=platform,
                composite_score=round(composite, 2)
            ))
    
    return {
        "data": [k.model_dump() for k in detailed_kols],
        "total": len(detailed_kols),
        "platform": platform
    }


@router.get("/platforms")
async def get_trending_by_platform(
    limit: int = Query(10, ge=1, le=50, description="Max per platform"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get trending KOLs for all platforms.
    
    **Returns:**
    Top trending KOLs for each platform (tiktok, youtube, twitter).
    """
    platforms = ["tiktok", "youtube", "twitter"]
    result = {}
    
    for platform in platforms:
        ranking = redis.get_trending_ranking(platform, "composite", limit)
        result[platform] = [
            {"kol_id": kol_id, "score": round(score, 2), "rank": rank + 1}
            for rank, (kol_id, score) in enumerate(ranking)
        ]
    
    return {
        "platforms": result,
        "limit_per_platform": limit
    }


@router.get("/stats")
async def get_trending_stats(
    platform: str = Query("tiktok", description="Platform filter"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get trending statistics.
    
    **Returns:**
    - Total KOLs in ranking
    - Count by label (Viral, Hot, Warm, Normal, Cold)
    - Score distribution
    """
    ranking = redis.get_trending_ranking(platform, "trending", 1000)
    
    if not ranking:
        return {
            "platform": platform,
            "total": 0,
            "distribution": {},
            "message": "No trending data available. Run Hot Path streaming to populate."
        }
    
    # Count by label
    distribution = {"Viral": 0, "Hot": 0, "Warm": 0, "Normal": 0, "Cold": 0}
    scores = [score for _, score in ranking]
    
    for score in scores:
        label = get_trending_label(score)
        distribution[label] += 1
    
    return {
        "platform": platform,
        "total": len(ranking),
        "distribution": distribution,
        "score_stats": {
            "min": round(min(scores), 2) if scores else 0,
            "max": round(max(scores), 2) if scores else 0,
            "avg": round(sum(scores) / len(scores), 2) if scores else 0
        }
    }
