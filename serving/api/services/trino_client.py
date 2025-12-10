"""
Trino Client Service
====================

Async-compatible Trino client for querying Silver/Gold layers.
Used as fallback when Redis cache misses.

Usage:
------
    from serving.api.services.trino_client import TrinoService
    
    trino = TrinoService()
    profiles = await trino.get_kol_profiles(limit=100)
    profile = await trino.get_kol_by_id("user123")
"""

import os
import asyncio
import logging
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from functools import partial

logger = logging.getLogger(__name__)

# Thread pool for running sync Trino queries
_executor = ThreadPoolExecutor(max_workers=5)


class TrinoConfig:
    """Trino connection configuration."""
    
    host: str = os.getenv("TRINO_HOST", "localhost")
    port: int = int(os.getenv("TRINO_PORT", "8081"))  # External port
    user: str = os.getenv("TRINO_USER", "admin")
    catalog: str = os.getenv("TRINO_CATALOG", "kol_hive")
    schema: str = os.getenv("TRINO_SCHEMA", "kol_silver")


class TrinoService:
    """
    Trino client service for querying Lakehouse.
    
    Wraps sync trino-python client in async interface.
    """
    
    def __init__(self, config: Optional[TrinoConfig] = None):
        self.config = config or TrinoConfig()
        self._conn = None
    
    def _get_connection(self):
        """Get or create Trino connection (sync)."""
        if self._conn is None:
            try:
                from trino.dbapi import connect as trino_connect
                self._conn = trino_connect(
                    host=self.config.host,
                    port=self.config.port,
                    user=self.config.user,
                    catalog=self.config.catalog,
                    schema=self.config.schema,
                )
                logger.info(f"✅ Connected to Trino at {self.config.host}:{self.config.port}")
            except ImportError:
                logger.warning("⚠️ trino package not installed. Install with: pip install trino")
                raise
            except Exception as e:
                logger.error(f"❌ Failed to connect to Trino: {e}")
                raise
        return self._conn
    
    def _execute_sync(self, query: str) -> List[Dict[str, Any]]:
        """Execute query synchronously and return list of dicts."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cursor.close()
    
    async def execute(self, query: str) -> List[Dict[str, Any]]:
        """Execute query asynchronously."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, partial(self._execute_sync, query))
    
    # =========================================================================
    # KOL PROFILE QUERIES
    # =========================================================================
    
    async def get_kol_profiles(
        self,
        platform: str = "all",
        limit: int = 100,
        offset: int = 0,
        order_by: str = "followers_count",
        order_dir: str = "DESC"
    ) -> List[Dict[str, Any]]:
        """
        Get list of KOL profiles from Silver layer.
        
        Args:
            platform: Filter by platform (all, tiktok, youtube, twitter)
            limit: Max results (default 100, max 1000)
            offset: Pagination offset
            order_by: Sort field (followers_count, post_count, created_at)
            order_dir: Sort direction (ASC, DESC)
        """
        # Sanitize inputs
        limit = min(max(1, limit), 1000)
        offset = max(0, offset)
        order_by = order_by if order_by in ["followers_count", "post_count", "following_count", "created_at", "username"] else "followers_count"
        order_dir = "DESC" if order_dir.upper() == "DESC" else "ASC"
        
        where_clause = ""
        if platform != "all":
            where_clause = f"WHERE platform = '{platform}'"
        
        query = f"""
        SELECT 
            kol_id,
            platform,
            username,
            display_name,
            bio,
            followers_count,
            following_count,
            post_count,
            verified,
            profile_image_url,
            created_at
        FROM kol_profiles
        {where_clause}
        ORDER BY {order_by} {order_dir}
        LIMIT {limit}
        OFFSET {offset}
        """
        
        try:
            return await self.execute(query)
        except Exception as e:
            logger.error(f"Failed to query kol_profiles: {e}")
            return []
    
    async def get_kol_by_id(self, kol_id: str) -> Optional[Dict[str, Any]]:
        """Get single KOL profile by ID."""
        query = f"""
        SELECT 
            kol_id,
            platform,
            username,
            display_name,
            bio,
            followers_count,
            following_count,
            post_count,
            favorites_count,
            verified,
            profile_image_url,
            external_url,
            created_at,
            updated_at
        FROM kol_profiles
        WHERE kol_id = '{kol_id}'
        LIMIT 1
        """
        
        try:
            results = await self.execute(query)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Failed to get KOL {kol_id}: {e}")
            return None
    
    async def get_kol_by_username(self, username: str, platform: str = None) -> Optional[Dict[str, Any]]:
        """Get KOL profile by username."""
        where = f"WHERE username = '{username}'"
        if platform:
            where += f" AND platform = '{platform}'"
        
        query = f"""
        SELECT 
            kol_id,
            platform,
            username,
            display_name,
            bio,
            followers_count,
            following_count,
            post_count,
            verified,
            profile_image_url,
            created_at
        FROM kol_profiles
        {where}
        LIMIT 1
        """
        
        try:
            results = await self.execute(query)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Failed to get KOL by username {username}: {e}")
            return None
    
    async def search_kols(
        self,
        query_str: str,
        platform: str = "all",
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search KOLs by username or display name.
        
        Args:
            query_str: Search query (partial match)
            platform: Filter by platform
            limit: Max results
        """
        limit = min(max(1, limit), 100)
        
        where_parts = [
            f"(LOWER(username) LIKE '%{query_str.lower()}%' OR LOWER(display_name) LIKE '%{query_str.lower()}%')"
        ]
        
        if platform != "all":
            where_parts.append(f"platform = '{platform}'")
        
        where_clause = " AND ".join(where_parts)
        
        query = f"""
        SELECT 
            kol_id,
            platform,
            username,
            display_name,
            followers_count,
            verified,
            profile_image_url
        FROM kol_profiles
        WHERE {where_clause}
        ORDER BY followers_count DESC
        LIMIT {limit}
        """
        
        try:
            return await self.execute(query)
        except Exception as e:
            logger.error(f"Search failed for '{query_str}': {e}")
            return []
    
    # =========================================================================
    # STATISTICS QUERIES
    # =========================================================================
    
    async def get_platform_stats(self) -> Dict[str, Any]:
        """Get platform-wide statistics."""
        query = """
        SELECT
            COUNT(*) as total_kols,
            COUNT(DISTINCT platform) as platforms_count,
            SUM(followers_count) as total_followers,
            AVG(followers_count) as avg_followers,
            SUM(post_count) as total_posts,
            AVG(post_count) as avg_posts,
            SUM(CASE WHEN verified = true THEN 1 ELSE 0 END) as verified_count
        FROM kol_profiles
        """
        
        try:
            results = await self.execute(query)
            if results:
                stats = results[0]
                # Clean up numeric types
                return {
                    "total_kols": int(stats.get("total_kols", 0) or 0),
                    "platforms_count": int(stats.get("platforms_count", 0) or 0),
                    "total_followers": int(stats.get("total_followers", 0) or 0),
                    "avg_followers": round(float(stats.get("avg_followers", 0) or 0), 2),
                    "total_posts": int(stats.get("total_posts", 0) or 0),
                    "avg_posts": round(float(stats.get("avg_posts", 0) or 0), 2),
                    "verified_count": int(stats.get("verified_count", 0) or 0),
                }
            return {}
        except Exception as e:
            logger.error(f"Failed to get platform stats: {e}")
            return {}
    
    async def get_stats_by_platform(self) -> List[Dict[str, Any]]:
        """Get statistics grouped by platform."""
        query = """
        SELECT
            platform,
            COUNT(*) as kol_count,
            SUM(followers_count) as total_followers,
            AVG(followers_count) as avg_followers,
            MAX(followers_count) as max_followers,
            SUM(post_count) as total_posts
        FROM kol_profiles
        GROUP BY platform
        ORDER BY kol_count DESC
        """
        
        try:
            results = await self.execute(query)
            return [
                {
                    "platform": r.get("platform", "unknown"),
                    "kol_count": int(r.get("kol_count", 0) or 0),
                    "total_followers": int(r.get("total_followers", 0) or 0),
                    "avg_followers": round(float(r.get("avg_followers", 0) or 0), 2),
                    "max_followers": int(r.get("max_followers", 0) or 0),
                    "total_posts": int(r.get("total_posts", 0) or 0),
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to get stats by platform: {e}")
            return []
    
    async def get_top_kols(
        self,
        metric: str = "followers_count",
        platform: str = "all",
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get top KOLs by specific metric.
        
        Args:
            metric: Ranking metric (followers_count, post_count)
            platform: Filter by platform
            limit: Max results
        """
        metric = metric if metric in ["followers_count", "post_count", "following_count"] else "followers_count"
        limit = min(max(1, limit), 200)
        
        where_clause = ""
        if platform != "all":
            where_clause = f"WHERE platform = '{platform}'"
        
        query = f"""
        SELECT 
            kol_id,
            platform,
            username,
            display_name,
            followers_count,
            post_count,
            verified,
            profile_image_url
        FROM kol_profiles
        {where_clause}
        ORDER BY {metric} DESC
        LIMIT {limit}
        """
        
        try:
            return await self.execute(query)
        except Exception as e:
            logger.error(f"Failed to get top KOLs by {metric}: {e}")
            return []
    
    # =========================================================================
    # CONTENT QUERIES
    # =========================================================================
    
    async def get_kol_content(
        self,
        kol_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get content/videos by KOL."""
        query = f"""
        SELECT 
            content_id,
            kol_id,
            title,
            description,
            view_count,
            like_count,
            comment_count,
            share_count,
            created_at
        FROM kol_content
        WHERE kol_id = '{kol_id}'
        ORDER BY created_at DESC
        LIMIT {min(limit, 100)}
        """
        
        try:
            return await self.execute(query)
        except Exception as e:
            logger.error(f"Failed to get content for KOL {kol_id}: {e}")
            return []
    
    async def health_check(self) -> bool:
        """Check Trino connection health."""
        try:
            results = await self.execute("SELECT 1 as health")
            return len(results) > 0
        except Exception:
            return False
    
    def close(self):
        """Close connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("Trino connection closed")


# Singleton instance
_trino_service: Optional[TrinoService] = None


def get_trino_service() -> TrinoService:
    """Get or create Trino service singleton."""
    global _trino_service
    if _trino_service is None:
        _trino_service = TrinoService()
    return _trino_service


# FastAPI dependency
async def get_trino() -> TrinoService:
    """FastAPI dependency for Trino service."""
    return get_trino_service()
