"""
Scores Router (v1)
==================

REST API endpoints for KOL scores (Trust, Trending, Success).

Endpoints:
    GET /api/v1/scores/{kol_id}           - Get all scores for KOL
    GET /api/v1/scores/{kol_id}/trust     - Trust score only
    GET /api/v1/scores/{kol_id}/trending  - Trending score only
    GET /api/v1/scores/{kol_id}/success   - Success score only

Data Sources:
    1. Redis (Hot Path real-time scores)
    2. Batch scores from Silver layer
    3. On-demand prediction via /predict endpoints
"""

from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.redis_client import RedisService, get_redis
from ..services.trino_client import TrinoService, get_trino

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class TrustScoreResponse(BaseModel):
    """Trust Score response."""
    kol_id: str
    trust_score: float = Field(..., ge=0, le=100)
    is_trustworthy: bool
    confidence: float = Field(..., ge=0, le=1)
    risk_level: str
    source: str = "cache"
    timestamp: Optional[str] = None


class TrendingScoreResponse(BaseModel):
    """Trending Score response."""
    kol_id: str
    trending_score: float = Field(..., ge=0, le=100)
    trending_label: str  # Cold, Normal, Warm, Hot, Viral
    velocity: Optional[float] = None
    momentum: Optional[float] = None
    source: str = "cache"
    timestamp: Optional[str] = None


class SuccessScoreResponse(BaseModel):
    """Success Score response."""
    kol_id: str
    success_score: float = Field(..., ge=0, le=100)
    success_label: str  # Low, Medium, High
    confidence: float = Field(..., ge=0, le=1)
    source: str = "cache"
    timestamp: Optional[str] = None


class CompositeScoreResponse(BaseModel):
    """Composite score with all three metrics."""
    kol_id: str
    platform: str = "tiktok"
    
    # Individual scores
    trust_score: Optional[float] = None
    trending_score: Optional[float] = None
    success_score: Optional[float] = None
    
    # Composite
    composite_score: Optional[float] = None
    
    # Labels
    trust_level: Optional[str] = None  # low/moderate/elevated/high risk
    trending_label: Optional[str] = None  # Cold/Normal/Warm/Hot/Viral
    success_label: Optional[str] = None  # Low/Medium/High
    
    # Metadata
    source: str = "unknown"
    updated_at: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "kol_id": "user123",
                "platform": "tiktok",
                "trust_score": 75.5,
                "trending_score": 62.3,
                "success_score": 80.1,
                "composite_score": 71.8,
                "trust_level": "moderate",
                "trending_label": "Hot",
                "success_label": "High",
                "source": "hot_path",
                "updated_at": "2025-12-06T10:30:00"
            }
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_trust_level(score: float) -> str:
    """Convert trust score to risk level."""
    if score >= 80:
        return "low"
    elif score >= 60:
        return "moderate"
    elif score >= 40:
        return "elevated"
    else:
        return "high"


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


def get_success_label(score: float) -> str:
    """Convert success score to label."""
    if score >= 70:
        return "High"
    elif score >= 40:
        return "Medium"
    else:
        return "Low"


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("/{kol_id}", response_model=CompositeScoreResponse)
async def get_all_scores(
    kol_id: str,
    platform: str = Query("tiktok", description="Platform (tiktok, youtube, twitter)"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get all scores (Trust, Trending, Success) for a KOL.
    
    **Data Sources (priority order):**
    1. Hot Path real-time scores from Redis (`kol:unified:{platform}:{kol_id}`)
    2. Legacy streaming scores (`streaming_scores:{kol_id}`)
    
    **Composite Score Formula:**
    ```
    composite = 0.4 × trending + 0.35 × success + 0.25 × trust
    ```
    
    **Returns:**
    - Individual scores (0-100 scale)
    - Composite score
    - Labels for each metric
    """
    # Try unified scores from Hot Path
    scores = redis.get_unified_scores(kol_id, platform)
    
    if scores:
        # Data from Hot Path streaming
        trust = scores.get("trust_score")
        trending = scores.get("trending_score")
        success = scores.get("success_score")
        composite = scores.get("composite_score")
        
        # Calculate composite if not present
        if composite is None and all([trust, trending, success]):
            composite = 0.4 * trending + 0.35 * success + 0.25 * trust
        
        return CompositeScoreResponse(
            kol_id=kol_id,
            platform=platform,
            trust_score=trust,
            trending_score=trending,
            success_score=success,
            composite_score=round(composite, 2) if composite else None,
            trust_level=get_trust_level(trust) if trust else None,
            trending_label=get_trending_label(trending) if trending else None,
            success_label=get_success_label(success) if success else None,
            source=scores.get("source", "hot_path"),
            updated_at=scores.get("updated_at") or scores.get("timestamp")
        )
    
    # No scores available - return empty response with null values
    return CompositeScoreResponse(
        kol_id=kol_id,
        platform=platform,
        source="not_found"
    )


@router.get("/{kol_id}/trust", response_model=TrustScoreResponse)
async def get_trust_score(
    kol_id: str,
    platform: str = Query("tiktok", description="Platform"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get Trust Score for a KOL.
    
    **Trust Score (0-100):**
    - 80-100: Highly Trustworthy (low risk)
    - 60-79: Moderately Trustworthy (moderate risk)
    - 40-59: Needs Review (elevated risk)
    - 0-39: Likely Untrustworthy (high risk)
    
    **For real-time prediction, use:**
    `POST /predict/trust` with KOL features
    """
    scores = redis.get_unified_scores(kol_id, platform)
    
    if scores and scores.get("trust_score") is not None:
        trust = scores.get("trust_score")
        return TrustScoreResponse(
            kol_id=kol_id,
            trust_score=trust,
            is_trustworthy=trust >= 50,
            confidence=0.85,  # Default confidence for cached scores
            risk_level=get_trust_level(trust),
            source="hot_path",
            timestamp=scores.get("updated_at")
        )
    
    raise HTTPException(
        status_code=404, 
        detail=f"Trust score not found for {kol_id}. Use POST /predict/trust for on-demand scoring."
    )


@router.get("/{kol_id}/trending", response_model=TrendingScoreResponse)
async def get_trending_score(
    kol_id: str,
    platform: str = Query("tiktok", description="Platform"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get Trending Score for a KOL.
    
    **Trending Score (0-100):**
    - 80-100: Viral (explosive growth)
    - 60-79: Hot (significant momentum)
    - 40-59: Warm (growing interest)
    - 25-39: Normal (steady state)
    - 0-24: Cold (declining/inactive)
    
    **Calculated from:**
    - Activity velocity (posts, interactions)
    - Personal growth vs baseline
    - Market position vs global average
    - Momentum (acceleration)
    """
    scores = redis.get_unified_scores(kol_id, platform)
    
    if scores and scores.get("trending_score") is not None:
        trending = scores.get("trending_score")
        return TrendingScoreResponse(
            kol_id=kol_id,
            trending_score=trending,
            trending_label=get_trending_label(trending),
            velocity=scores.get("velocity"),
            momentum=scores.get("momentum"),
            source="hot_path",
            timestamp=scores.get("updated_at")
        )
    
    raise HTTPException(
        status_code=404,
        detail=f"Trending score not found for {kol_id}. Scores are computed by Hot Path streaming."
    )


@router.get("/{kol_id}/success", response_model=SuccessScoreResponse)
async def get_success_score(
    kol_id: str,
    platform: str = Query("tiktok", description="Platform"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get Success Score for a KOL.
    
    **Success Score (0-100):**
    - 70-100: High success potential
    - 40-69: Medium success potential  
    - 0-39: Low success potential
    
    **Measures likelihood of successful product promotions
    based on engagement, reach, and historical performance.**
    
    **For real-time prediction, use:**
    `POST /predict/success` with content metrics
    """
    scores = redis.get_unified_scores(kol_id, platform)
    
    if scores and scores.get("success_score") is not None:
        success = scores.get("success_score")
        return SuccessScoreResponse(
            kol_id=kol_id,
            success_score=success,
            success_label=get_success_label(success),
            confidence=0.80,
            source="hot_path",
            timestamp=scores.get("updated_at")
        )
    
    raise HTTPException(
        status_code=404,
        detail=f"Success score not found for {kol_id}. Use POST /predict/success for on-demand scoring."
    )


@router.get("/compare")
async def compare_kols(
    kol_ids: str = Query(..., description="Comma-separated KOL IDs (max 10)"),
    platform: str = Query("tiktok", description="Platform"),
    redis: RedisService = Depends(get_redis)
):
    """
    Compare scores of multiple KOLs.
    
    **Parameters:**
    - `kol_ids`: Comma-separated KOL IDs (e.g., "user1,user2,user3")
    - `platform`: Platform filter
    
    **Returns:**
    Scores for all requested KOLs in a single response.
    """
    ids = [id.strip() for id in kol_ids.split(",")][:10]
    
    results = []
    for kol_id in ids:
        scores = redis.get_unified_scores(kol_id, platform)
        
        if scores:
            results.append({
                "kol_id": kol_id,
                "trust_score": scores.get("trust_score"),
                "trending_score": scores.get("trending_score"),
                "success_score": scores.get("success_score"),
                "composite_score": scores.get("composite_score"),
                "available": True
            })
        else:
            results.append({
                "kol_id": kol_id,
                "available": False
            })
    
    return {
        "comparisons": results,
        "total": len(results),
        "available_count": sum(1 for r in results if r.get("available", False))
    }
