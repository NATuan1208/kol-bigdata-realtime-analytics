"""
KOL Data Router (v1)
====================

REST API endpoints for KOL profile data.

Endpoints:
    GET /api/v1/kols              - List KOLs with pagination
    GET /api/v1/kols/{kol_id}     - Get single KOL details
    GET /api/v1/kols/{kol_id}/content - Get KOL's content/videos

Data Sources:
    1. Redis cache (primary, fast)
    2. Trino/Silver layer (fallback, slow)
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..services.redis_client import RedisService, get_redis
from ..services.trino_client import TrinoService, get_trino

router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class KOLProfileBasic(BaseModel):
    """Basic KOL profile for list views."""
    kol_id: str
    platform: str = "tiktok"
    username: str
    display_name: Optional[str] = None
    followers_count: int = 0
    following_count: int = 0
    post_count: int = 0
    verified: bool = False
    profile_image_url: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "kol_id": "tiktok_user123",
                "platform": "tiktok",
                "username": "creator_abc",
                "display_name": "Creative ABC",
                "followers_count": 150000,
                "following_count": 500,
                "post_count": 250,
                "verified": True,
                "profile_image_url": "https://example.com/avatar.jpg"
            }
        }


class KOLProfileFull(KOLProfileBasic):
    """Full KOL profile with all details."""
    bio: Optional[str] = None
    external_url: Optional[str] = None
    favorites_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    cached_at: Optional[str] = None
    data_source: str = "cache"  # cache or database


class KOLListResponse(BaseModel):
    """Paginated KOL list response."""
    data: List[KOLProfileBasic]
    total: int
    page: int
    page_size: int
    has_more: bool
    data_source: str = "cache"


class ContentItem(BaseModel):
    """KOL content/video item."""
    content_id: str
    kol_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    share_count: int = 0
    created_at: Optional[str] = None


class KOLContentResponse(BaseModel):
    """KOL content list response."""
    kol_id: str
    content: List[ContentItem]
    total: int


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("", response_model=KOLListResponse)
async def list_kols(
    platform: str = Query("all", description="Filter by platform (all, tiktok, youtube, twitter)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    order_by: str = Query("followers_count", description="Sort field"),
    order_dir: str = Query("desc", description="Sort direction (asc, desc)"),
    redis: RedisService = Depends(get_redis),
    trino: TrinoService = Depends(get_trino)
):
    """
    Get list of KOL profiles with pagination.
    
    **Cache-first pattern:**
    1. Try Redis cache first (fast, ~1ms)
    2. Fallback to Trino/Silver layer if cache miss (~200ms)
    
    **Parameters:**
    - `platform`: Filter by platform (all, tiktok, youtube, twitter)
    - `page`: Page number (1-based)
    - `page_size`: Items per page (max 100)
    - `order_by`: Sort field (followers_count, post_count, created_at)
    - `order_dir`: Sort direction (asc, desc)
    """
    offset = (page - 1) * page_size
    data_source = "cache"
    
    # Try cache first
    cached_list = redis.get_kol_profiles_list(platform)
    
    if cached_list:
        # Sort and paginate from cache
        reverse = order_dir.lower() == "desc"
        
        # Sort by field
        if order_by in ["followers_count", "following_count", "post_count"]:
            sorted_list = sorted(
                cached_list, 
                key=lambda x: x.get(order_by, 0) or 0,
                reverse=reverse
            )
        else:
            sorted_list = cached_list
        
        total = len(sorted_list)
        paginated = sorted_list[offset:offset + page_size]
        
        return KOLListResponse(
            data=[KOLProfileBasic(**item) for item in paginated],
            total=total,
            page=page,
            page_size=page_size,
            has_more=(offset + page_size) < total,
            data_source="cache"
        )
    
    # Cache miss - query Trino
    data_source = "database"
    kols = await trino.get_kol_profiles(
        platform=platform,
        limit=page_size,
        offset=offset,
        order_by=order_by,
        order_dir=order_dir.upper()
    )
    
    # Get total count (simplified - could be slow for large datasets)
    all_kols = await trino.get_kol_profiles(platform=platform, limit=10000, offset=0)
    total = len(all_kols)
    
    return KOLListResponse(
        data=[KOLProfileBasic(**kol) for kol in kols],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + page_size) < total,
        data_source=data_source
    )


@router.get("/{kol_id}", response_model=KOLProfileFull)
async def get_kol(
    kol_id: str,
    redis: RedisService = Depends(get_redis),
    trino: TrinoService = Depends(get_trino)
):
    """
    Get single KOL profile by ID.
    
    **Cache-first pattern:**
    1. Check Redis cache (hash: kol:profile:{kol_id})
    2. If miss, query Trino Silver layer
    3. Cache result for future requests
    
    **Returns:**
    Full KOL profile with all available fields.
    
    **Raises:**
    - 404: KOL not found
    """
    # Try cache first
    cached_profile = redis.get_kol_profile(kol_id)
    
    if cached_profile:
        return KOLProfileFull(**cached_profile, data_source="cache")
    
    # Cache miss - query Trino
    profile = await trino.get_kol_by_id(kol_id)
    
    if not profile:
        raise HTTPException(status_code=404, detail=f"KOL not found: {kol_id}")
    
    # Cache for future requests
    redis.set_kol_profile(profile, ttl=3600)
    
    return KOLProfileFull(**profile, data_source="database")


@router.get("/{kol_id}/content", response_model=KOLContentResponse)
async def get_kol_content(
    kol_id: str,
    limit: int = Query(20, ge=1, le=100, description="Max items to return"),
    trino: TrinoService = Depends(get_trino)
):
    """
    Get content/videos by KOL.
    
    **Note:** Content is fetched from Trino (not cached).
    
    **Parameters:**
    - `kol_id`: KOL identifier
    - `limit`: Max items to return (default 20)
    """
    content = await trino.get_kol_content(kol_id, limit=limit)
    
    return KOLContentResponse(
        kol_id=kol_id,
        content=[ContentItem(**item) for item in content],
        total=len(content)
    )


@router.get("/username/{username}")
async def get_kol_by_username(
    username: str,
    platform: str = Query(None, description="Platform filter (optional)"),
    redis: RedisService = Depends(get_redis),
    trino: TrinoService = Depends(get_trino)
):
    """
    Get KOL profile by username.
    
    **Parameters:**
    - `username`: KOL username
    - `platform`: Platform filter (optional)
    """
    profile = await trino.get_kol_by_username(username, platform)
    
    if not profile:
        raise HTTPException(status_code=404, detail=f"KOL not found: {username}")
    
    return KOLProfileFull(**profile, data_source="database")


@router.get("/top/followers")
async def get_top_kols_by_followers(
    platform: str = Query("all", description="Platform filter"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    redis: RedisService = Depends(get_redis),
    trino: TrinoService = Depends(get_trino)
):
    """
    Get top KOLs ranked by followers count.
    
    **Cache-first pattern:**
    1. Check Redis sorted set (kol:top:followers:{platform})
    2. Fallback to Trino query
    """
    # Try cache
    cached = redis.get_top_kols_by_followers(platform, limit)
    
    if cached:
        return {
            "data": [{"kol_id": kol_id, "followers_count": int(score)} for kol_id, score in cached],
            "total": len(cached),
            "data_source": "cache"
        }
    
    # Fallback to Trino
    kols = await trino.get_top_kols("followers_count", platform, limit)
    
    return {
        "data": [
            {
                "kol_id": k.get("kol_id"),
                "username": k.get("username"),
                "display_name": k.get("display_name"),
                "followers_count": k.get("followers_count", 0),
                "verified": k.get("verified", False)
            }
            for k in kols
        ],
        "total": len(kols),
        "data_source": "database"
    }
