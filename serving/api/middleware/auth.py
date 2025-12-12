"""
API Authentication Middleware
=============================

Provides API key authentication for the KOL Platform API.

SECURITY NOTES:
- API keys should be stored securely (environment variables or secrets manager)
- In production, use proper OAuth2/JWT authentication
- This is a basic implementation for MVP/development

Usage:
    from serving.api.middleware.auth import get_api_key, require_api_key
    
    # Optional API key (bypass in development)
    @router.get("/endpoint")
    async def endpoint(api_key: str = Depends(get_api_key)):
        pass
    
    # Required API key
    @router.get("/secure-endpoint")
    async def secure_endpoint(api_key: str = Depends(require_api_key)):
        pass
"""

import os
import secrets
import logging
from typing import Optional
from datetime import datetime

from fastapi import HTTPException, Security, Depends
from fastapi.security import APIKeyHeader, APIKeyQuery

logger = logging.getLogger(__name__)

# Configuration
API_KEY_NAME = "X-API-Key"
API_KEY_QUERY_NAME = "api_key"

# SECURITY: API keys should be loaded from environment/secrets manager
# Multiple keys can be comma-separated for key rotation
VALID_API_KEYS = set(
    key.strip() 
    for key in os.getenv("API_KEYS", "").split(",") 
    if key.strip()
)

# Environment flag to enable/disable auth
AUTH_ENABLED = os.getenv("API_AUTH_ENABLED", "false").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# API Key security schemes
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
api_key_query = APIKeyQuery(name=API_KEY_QUERY_NAME, auto_error=False)


def generate_api_key() -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(32)


async def get_api_key(
    api_key_header: Optional[str] = Security(api_key_header),
    api_key_query: Optional[str] = Security(api_key_query),
) -> Optional[str]:
    """
    Extract API key from header or query parameter.
    
    Does NOT enforce authentication - use require_api_key for that.
    """
    return api_key_header or api_key_query


async def verify_api_key(api_key: Optional[str]) -> bool:
    """
    Verify if the provided API key is valid.
    
    Returns True if:
    - Auth is disabled (development mode)
    - Valid API key provided
    - No API keys configured (fallback to open access)
    """
    # Skip auth in development mode if not explicitly enabled
    if not AUTH_ENABLED and ENVIRONMENT == "development":
        return True
    
    # If no API keys configured, allow access (but log warning)
    if not VALID_API_KEYS:
        logger.warning(
            "No API keys configured. Set API_KEYS environment variable "
            "and API_AUTH_ENABLED=true for production."
        )
        return True
    
    # Verify the key
    if api_key and api_key in VALID_API_KEYS:
        return True
    
    return False


async def require_api_key(
    api_key: Optional[str] = Depends(get_api_key),
) -> str:
    """
    Dependency that requires a valid API key.
    
    Raises HTTPException 401 if key is invalid.
    """
    if await verify_api_key(api_key):
        return api_key or "anonymous"
    
    logger.warning(f"Invalid API key attempt: {api_key[:8] if api_key else 'None'}...")
    raise HTTPException(
        status_code=401,
        detail={
            "error": "unauthorized",
            "message": "Invalid or missing API key",
            "hint": f"Provide API key via '{API_KEY_NAME}' header or '{API_KEY_QUERY_NAME}' query parameter"
        }
    )


async def optional_api_key(
    api_key: Optional[str] = Depends(get_api_key),
) -> Optional[str]:
    """
    Dependency that accepts but doesn't require API key.
    
    Logs the key for audit purposes if provided.
    """
    if api_key and await verify_api_key(api_key):
        return api_key
    return None


class APIKeyAuditLog:
    """
    Simple API key usage audit log.
    
    In production, replace with proper audit logging system.
    """
    
    @staticmethod
    def log_request(api_key: Optional[str], endpoint: str, method: str):
        """Log API request for audit."""
        key_prefix = api_key[:8] if api_key else "anonymous"
        logger.info(f"API Request: key={key_prefix}... endpoint={endpoint} method={method}")
    
    @staticmethod
    def log_failed_auth(api_key: Optional[str], endpoint: str, reason: str):
        """Log failed authentication attempt."""
        key_prefix = api_key[:8] if api_key else "None"
        logger.warning(f"Auth Failed: key={key_prefix}... endpoint={endpoint} reason={reason}")


# Export for easy access
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
