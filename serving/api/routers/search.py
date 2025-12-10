"""
Search Router (v1)
==================

REST API endpoints for searching KOLs.

Endpoints:
    GET /api/v1/search        - Search KOLs by username/name
    GET /api/v1/search/suggest - Autocomplete suggestions
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

class SearchResult(BaseModel):
    """Single search result."""
    kol_id: str
    platform: str
    username: str
    display_name: Optional[str] = None
    followers_count: int = 0
    verified: bool = False
    profile_image_url: Optional[str] = None
    match_type: str = "username"  # username, display_name


class SearchResponse(BaseModel):
    """Search response with results."""
    query: str
    results: List[SearchResult]
    total: int
    platform_filter: str
    search_time_ms: float


class SuggestionResponse(BaseModel):
    """Autocomplete suggestions response."""
    prefix: str
    suggestions: List[str]
    total: int


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.get("", response_model=SearchResponse)
async def search_kols(
    q: str = Query(..., min_length=2, max_length=100, description="Search query"),
    platform: str = Query("all", description="Platform filter (all, tiktok, youtube, twitter)"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    redis: RedisService = Depends(get_redis),
    trino: TrinoService = Depends(get_trino)
):
    """
    Search KOLs by username or display name.
    
    **Search features:**
    - Partial matching (username contains query)
    - Case-insensitive
    - Platform filtering
    
    **Parameters:**
    - `q`: Search query (min 2 characters)
    - `platform`: Filter by platform (all, tiktok, youtube, twitter)
    - `limit`: Max results (default 20)
    
    **Note:**
    For best performance, searches are done against Trino Silver layer.
    Consider implementing Elasticsearch for production-grade search.
    """
    import time
    start_time = time.time()
    
    # Search via Trino
    results = await trino.search_kols(q, platform, limit)
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    # Build response
    search_results = []
    for r in results:
        # Determine match type
        username = r.get("username", "")
        display_name = r.get("display_name", "")
        
        if q.lower() in username.lower():
            match_type = "username"
        elif display_name and q.lower() in display_name.lower():
            match_type = "display_name"
        else:
            match_type = "other"
        
        search_results.append(SearchResult(
            kol_id=r.get("kol_id", ""),
            platform=r.get("platform", "unknown"),
            username=username,
            display_name=display_name,
            followers_count=r.get("followers_count", 0),
            verified=r.get("verified", False),
            profile_image_url=r.get("profile_image_url"),
            match_type=match_type
        ))
    
    return SearchResponse(
        query=q,
        results=search_results,
        total=len(search_results),
        platform_filter=platform,
        search_time_ms=round(elapsed_ms, 2)
    )


@router.get("/suggest", response_model=SuggestionResponse)
async def search_suggestions(
    prefix: str = Query(..., min_length=1, max_length=50, description="Prefix for autocomplete"),
    limit: int = Query(10, ge=1, le=20, description="Max suggestions"),
    redis: RedisService = Depends(get_redis)
):
    """
    Get autocomplete suggestions for search.
    
    **Parameters:**
    - `prefix`: Start of username/name to autocomplete
    - `limit`: Max suggestions (default 10)
    
    **Note:**
    Suggestions come from Redis sorted set (search:autocomplete).
    This needs to be populated by cache_warmer.py.
    """
    suggestions = redis.get_search_suggestions(prefix, limit)
    
    return SuggestionResponse(
        prefix=prefix,
        suggestions=suggestions,
        total=len(suggestions)
    )


@router.get("/advanced")
async def advanced_search(
    q: Optional[str] = Query(None, description="Text search query"),
    platform: str = Query("all", description="Platform filter"),
    min_followers: Optional[int] = Query(None, ge=0, description="Minimum followers"),
    max_followers: Optional[int] = Query(None, description="Maximum followers"),
    verified_only: bool = Query(False, description="Only verified accounts"),
    order_by: str = Query("followers_count", description="Sort field"),
    order_dir: str = Query("desc", description="Sort direction"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    trino: TrinoService = Depends(get_trino)
):
    """
    Advanced search with filters.
    
    **Filters:**
    - `q`: Text search (username, display_name)
    - `platform`: Platform filter
    - `min_followers`: Minimum follower count
    - `max_followers`: Maximum follower count
    - `verified_only`: Only verified accounts
    
    **Sorting:**
    - `order_by`: followers_count, post_count, created_at
    - `order_dir`: asc, desc
    
    **Note:**
    This endpoint queries Trino directly and may be slower.
    Use pagination for large result sets.
    """
    # Build dynamic query
    where_parts = []
    
    if q:
        where_parts.append(
            f"(LOWER(username) LIKE '%{q.lower()}%' OR LOWER(display_name) LIKE '%{q.lower()}%')"
        )
    
    if platform != "all":
        where_parts.append(f"platform = '{platform}'")
    
    if min_followers is not None:
        where_parts.append(f"followers_count >= {min_followers}")
    
    if max_followers is not None:
        where_parts.append(f"followers_count <= {max_followers}")
    
    if verified_only:
        where_parts.append("verified = true")
    
    where_clause = " AND ".join(where_parts) if where_parts else "1=1"
    
    # Sanitize order_by
    valid_order_fields = ["followers_count", "following_count", "post_count", "created_at", "username"]
    order_by = order_by if order_by in valid_order_fields else "followers_count"
    order_dir = "DESC" if order_dir.lower() == "desc" else "ASC"
    
    query = f"""
    SELECT 
        kol_id,
        platform,
        username,
        display_name,
        followers_count,
        following_count,
        post_count,
        verified,
        profile_image_url
    FROM kol_profiles
    WHERE {where_clause}
    ORDER BY {order_by} {order_dir}
    LIMIT {min(limit, 200)}
    """
    
    import time
    start_time = time.time()
    
    try:
        results = await trino.execute(query)
        elapsed_ms = (time.time() - start_time) * 1000
        
        return {
            "filters": {
                "q": q,
                "platform": platform,
                "min_followers": min_followers,
                "max_followers": max_followers,
                "verified_only": verified_only,
            },
            "sort": {
                "order_by": order_by,
                "order_dir": order_dir
            },
            "results": results,
            "total": len(results),
            "search_time_ms": round(elapsed_ms, 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/filters")
async def get_search_filters(
    trino: TrinoService = Depends(get_trino)
):
    """
    Get available search filters and their options.
    
    **Returns:**
    - Available platforms
    - Follower ranges
    - Post count ranges
    """
    # Get platform options
    platform_stats = await trino.get_stats_by_platform()
    
    platforms = [
        {
            "value": p.get("platform"),
            "label": p.get("platform", "").title(),
            "count": p.get("kol_count", 0)
        }
        for p in platform_stats
    ]
    
    return {
        "platforms": [{"value": "all", "label": "All Platforms"}] + platforms,
        "follower_ranges": [
            {"value": [0, 1000], "label": "< 1K (Nano)"},
            {"value": [1000, 10000], "label": "1K - 10K (Micro)"},
            {"value": [10000, 100000], "label": "10K - 100K (Mid)"},
            {"value": [100000, 1000000], "label": "100K - 1M (Macro)"},
            {"value": [1000000, None], "label": "> 1M (Mega)"},
        ],
        "sort_options": [
            {"value": "followers_count", "label": "Followers"},
            {"value": "post_count", "label": "Posts"},
            {"value": "created_at", "label": "Newest"},
            {"value": "username", "label": "Username (A-Z)"},
        ]
    }
