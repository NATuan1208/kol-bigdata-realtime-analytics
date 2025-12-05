"""
KOL Platform - Cache Layer
==========================

Redis-based caching for high-performance data serving.

Modules:
- config: Redis configuration and key patterns
- client: Redis client wrapper with connection pooling
- warmer: Cache warming utilities
"""

from .config import CacheConfig, CacheKeys
from .client import CacheClient

__all__ = ["CacheConfig", "CacheKeys", "CacheClient"]
