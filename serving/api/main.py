"""
KOL Platform API
================

FastAPI-based REST API for KOL Analytics Platform.

Endpoints Overview:
- /api/v1/kols     - KOL profile data
- /api/v1/scores   - Trust/Trending/Success scores
- /api/v1/stats    - Platform statistics
- /api/v1/trending - Trending KOLs from Hot Path
- /api/v1/search   - Search KOLs
- /predict/*       - ML prediction endpoints (real-time inference)
- /forecast/*      - Forecasting endpoints

Data Sources:
- Redis cache (primary, fast)
- Trino/Silver layer (fallback, slow)
- Hot Path streaming (real-time scores)
- MLflow models (on-demand inference)

Usage:
------
    # Start server
    uvicorn serving.api.main:app --host 0.0.0.0 --port 8000 --reload
    
    # Or with Python
    python -m uvicorn serving.api.main:app --port 8000
"""

from datetime import datetime
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Legacy routers
from .routers import kol, forecast, predict

# New v1 routers
from .routers import kols, scores, stats, trending, search


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("🚀 KOL Platform API starting up...")
    yield
    # Shutdown
    print("👋 KOL Platform API shutting down...")


app = FastAPI(
    title="KOL Platform API",
    description="""
## KOL Analytics Platform - Comprehensive API

This API provides access to KOL (Key Opinion Leader) analytics data including:
- **Profile Data**: KOL profiles from TikTok, YouTube, Twitter
- **Trust Scores**: ML-based trustworthiness assessment
- **Trending Scores**: Real-time velocity-based trending metrics
- **Success Scores**: Product promotion success prediction

### Data Sources
- **Redis Cache**: Fast access to cached data (~1ms latency)
- **Trino/Lakehouse**: Fallback to Silver layer (~200ms latency)
- **Hot Path Streaming**: Real-time scores from Spark Streaming

### Authentication
Currently no authentication required (development mode).
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_tags=[
        {"name": "kols", "description": "KOL profile data operations"},
        {"name": "scores", "description": "Trust/Trending/Success scores"},
        {"name": "stats", "description": "Platform statistics"},
        {"name": "trending", "description": "Trending KOLs from Hot Path"},
        {"name": "search", "description": "Search KOLs"},
        {"name": "predict", "description": "ML prediction endpoints"},
        {"name": "legacy", "description": "Legacy endpoints (deprecated)"},
    ],
    lifespan=lifespan
)

# CORS middleware for frontend access
# SECURITY: In production, remove wildcard and specify exact origins
ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if os.getenv("CORS_ALLOWED_ORIGINS") else [
    "http://localhost:3000",       # Next.js dev
    "http://localhost:8501",       # Streamlit
    "http://localhost:8080",       # Other frontends
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8501",
]

# SECURITY WARNING: Remove "*" in production - it allows any origin
if os.getenv("ENVIRONMENT", "development") == "development":
    ALLOWED_ORIGINS.append("*")  # Only for development

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # Restrict to needed methods
    allow_headers=["*"],
)


# ============================================================================
# HEALTH CHECKS
# ============================================================================

@app.get("/healthz", tags=["health"])
def health():
    """Simple health check."""
    return {
        "ok": True, 
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/", tags=["health"])
def root():
    """API root - provides basic info and links."""
    return {
        "name": "KOL Platform API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/healthz",
        "endpoints": {
            "kols": "/api/v1/kols",
            "scores": "/api/v1/scores/{kol_id}",
            "stats": "/api/v1/stats",
            "trending": "/api/v1/trending",
            "search": "/api/v1/search?q=query",
            "predict_trust": "/predict/trust",
            "predict_success": "/predict/success",
            "predict_trending": "/predict/trending"
        }
    }


# ============================================================================
# V1 API ROUTERS (New)
# ============================================================================

app.include_router(
    kols.router, 
    prefix="/api/v1/kols", 
    tags=["kols"]
)

app.include_router(
    scores.router, 
    prefix="/api/v1/scores", 
    tags=["scores"]
)

app.include_router(
    stats.router, 
    prefix="/api/v1/stats", 
    tags=["stats"]
)

app.include_router(
    trending.router, 
    prefix="/api/v1/trending", 
    tags=["trending"]
)

app.include_router(
    search.router, 
    prefix="/api/v1/search", 
    tags=["search"]
)


# ============================================================================
# PREDICTION ROUTERS (ML)
# ============================================================================

app.include_router(
    predict.router, 
    prefix="/predict", 
    tags=["predict"]
)

app.include_router(
    forecast.router, 
    prefix="/forecast", 
    tags=["forecast"]
)


# ============================================================================
# LEGACY ROUTERS (Deprecated)
# ============================================================================

app.include_router(
    kol.router, 
    prefix="/kol", 
    tags=["legacy"],
    deprecated=True
)

