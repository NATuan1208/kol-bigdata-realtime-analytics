"""
API Middleware Package
======================

Contains authentication and other middleware components.
"""

from .auth import (
    get_api_key,
    require_api_key,
    optional_api_key,
    verify_api_key,
    generate_api_key,
    APIKeyAuditLog,
    AUTH_ENABLED,
    ENVIRONMENT,
)

__all__ = [
    "get_api_key",
    "require_api_key",
    "optional_api_key", 
    "verify_api_key",
    "generate_api_key",
    "APIKeyAuditLog",
    "AUTH_ENABLED",
    "ENVIRONMENT",
]
