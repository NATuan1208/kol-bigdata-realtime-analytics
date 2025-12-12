"""
Trust Score Prediction Router
==============================
API endpoints for Trust Score inference using MLflow models.

Endpoints:
    POST /predict/trust - Single KOL trust score prediction
    POST /predict/trust/batch - Batch prediction for multiple KOLs

Usage by Streaming Layer:
    When Spark Streaming detects a new KOL, call:
    POST /predict/trust {"kol_id": "abc123", "features": {...}}
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import numpy as np

router = APIRouter()

# Project root - works from any working directory
# In Docker: /app is the root, so we need to detect Docker environment
def _get_project_root():
    """Get project root, handling both local and Docker environments."""
    # Check if running in Docker (PYTHONPATH=/app)
    if os.getenv("PYTHONPATH") == "/app":
        return Path("/app")
    # Local development - traverse from file location
    return Path(__file__).parent.parent.parent.parent.resolve()

PROJECT_ROOT = _get_project_root()

# ============================================================================
# CONFIGURATION
# ============================================================================
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MODEL_NAME = os.getenv("MLFLOW_MODEL_NAME_TRUST", "trust-score-lightgbm-optuna")
MODEL_STAGE = os.getenv("MLFLOW_MODEL_STAGE", "Production")

# Model loading strategy: "local_first" (fast) or "mlflow_first" (requires MLflow)
MODEL_LOAD_STRATEGY = os.getenv("MODEL_LOAD_STRATEGY", "local_first")

# Per-model loading strategy override (trust=mlflow, success=local)
MODEL_STRATEGY_OVERRIDE = {
    "trust": os.getenv("TRUST_MODEL_STRATEGY", "auto"),  # auto = try mlflow, fallback local
    "success": "local",  # Always local (not registered in MLflow yet)
}

# Local model paths - absolute paths based on project root
def _get_local_model_paths():
    """Get absolute model paths that work from any working directory."""
    return {
        "trust": [
            PROJECT_ROOT / "models" / "artifacts" / "trust" / "lgbm_optuna_model.pkl",
            PROJECT_ROOT / "models" / "artifacts" / "trust" / "lgbm_trust_classifier_latest.joblib",
            PROJECT_ROOT / "models" / "artifacts" / "trust" / "xgb_trust_classifier_latest.joblib",
        ],
        "success": [
            PROJECT_ROOT / "models" / "artifacts" / "success" / "success_lgbm_model.pkl",
            PROJECT_ROOT / "models" / "artifacts" / "success" / "success_lgbm_model_binary.pkl",
        ]
    }

LOCAL_MODEL_PATHS = _get_local_model_paths()

# Feature columns expected by the model
FEATURE_COLUMNS = [
    'log_followers', 'log_following', 'log_posts', 'log_favorites', 'log_account_age',
    'followers_following_ratio_capped', 'posts_per_day_capped',
    'engagement_rate', 'activity_score', 'profile_completeness',
    'followers_per_day', 'posts_per_follower', 'following_per_day',
    'high_activity_flag', 'low_engagement_high_posts',
    'default_profile_score', 'suspicious_growth', 'fake_follower_indicator',
    'followers_tier', 'account_age_tier', 'activity_tier',
    'verified_followers_interaction', 'profile_engagement_interaction',
    'age_activity_interaction', 'bio_length_norm',
    'has_bio', 'has_url', 'has_profile_image', 'verified'
]


# ============================================================================
# PYDANTIC MODELS
# ============================================================================
class RawKOLFeatures(BaseModel):
    """Raw KOL features (before engineering) - for simpler API calls."""
    kol_id: str = Field(..., description="Unique KOL identifier")
    followers_count: int = Field(..., ge=0, description="Number of followers")
    following_count: int = Field(..., ge=0, description="Number of following")
    post_count: int = Field(..., ge=0, description="Number of posts")
    favorites_count: int = Field(0, ge=0, description="Total likes received")
    account_age_days: int = Field(..., ge=1, description="Account age in days")
    verified: bool = Field(False, description="Is account verified")
    has_bio: bool = Field(True, description="Has bio text")
    has_url: bool = Field(False, description="Has URL in profile")
    has_profile_image: bool = Field(True, description="Has profile image")
    bio_length: int = Field(0, ge=0, description="Bio text length")


class EngineeredFeatures(BaseModel):
    """Pre-engineered features - for direct model input."""
    kol_id: str = Field(..., description="Unique KOL identifier")
    features: Dict[str, float] = Field(..., description="Engineered feature dict")


class TrustScoreResponse(BaseModel):
    """Trust Score prediction response."""
    kol_id: str
    trust_score: float = Field(..., ge=0, le=100, description="Trust score 0-100")
    is_trustworthy: bool = Field(..., description="Trust classification")
    confidence: float = Field(..., ge=0, le=1, description="Prediction confidence")
    risk_level: str = Field(..., description="Risk level category")
    prediction_source: str = Field("realtime", description="batch or realtime")
    model_version: str = Field(..., description="Model version used")
    timestamp: str = Field(..., description="Prediction timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "kol_id": "user_123",
                "trust_score": 72.5,
                "is_trustworthy": True,
                "confidence": 0.89,
                "risk_level": "moderate",
                "prediction_source": "realtime",
                "model_version": "lgbm-optuna-v1",
                "timestamp": "2025-11-27T10:30:00"
            }
        }


class BatchPredictionRequest(BaseModel):
    """Batch prediction request."""
    kols: List[RawKOLFeatures]


class BatchPredictionResponse(BaseModel):
    """Batch prediction response."""
    predictions: List[TrustScoreResponse]
    total: int
    model_version: str
    processing_time_ms: float


# ============================================================================
# MODEL LOADING (Local-first strategy to avoid MLflow hanging)
# ============================================================================
_model_cache = {}
_model_load_status = {"trust": None, "success": None}


def _load_local_model(model_type: str = "trust"):
    """Load model from local filesystem (fast, no network)."""
    import joblib
    
    paths = LOCAL_MODEL_PATHS.get(model_type, [])
    
    print(f"🔍 Searching for {model_type} model in {len(paths)} paths...")
    
    for path in paths:
        try:
            # Convert Path to string and check existence
            path_str = str(path)
            if Path(path).exists():
                model = joblib.load(path_str)
                print(f"✅ Loaded local {model_type} model: {path}")
                return model, f"local:{Path(path).name}"
            else:
                print(f"   ❌ Not found: {path}")
        except Exception as e:
            print(f"⚠️ Failed to load {path}: {e}")
            continue
    
    print(f"❌ No local model found for {model_type}")
    return None, None


def _load_mlflow_model_with_timeout(model_type: str = "trust", timeout: int = 5):
    """
    Try to load model from MLflow with timeout.
    Returns (model, version) or (None, None) if failed/timeout.
    """
    import threading
    import queue
    
    result_queue = queue.Queue()
    
    def _load():
        try:
            import mlflow
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            
            model_uri = f"models:/{MODEL_NAME}/{MODEL_STAGE}"
            loaded_model = mlflow.pyfunc.load_model(model_uri)
            
            # Try to get underlying model
            try:
                model = loaded_model._model_impl.python_model.lgb_model
            except:
                model = loaded_model
            
            result_queue.put((model, f"mlflow:{MODEL_NAME}/{MODEL_STAGE}"))
        except Exception as e:
            result_queue.put((None, str(e)))
    
    thread = threading.Thread(target=_load)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout)
    
    if thread.is_alive():
        print(f"⚠️ MLflow load timed out after {timeout}s")
        return None, "timeout"
    
    try:
        return result_queue.get_nowait()
    except queue.Empty:
        return None, "empty_result"


def get_model(model_type: str = "trust"):
    """
    Load model with hybrid strategy.
    
    Strategy per model_type:
    - trust: Try MLflow first (if TRUST_MODEL_STRATEGY=auto), fallback to local
    - success: Always local (not in MLflow yet)
    """
    global _model_cache, _model_load_status
    
    cache_key = f"{model_type}_{MODEL_STAGE}"
    
    if cache_key in _model_cache:
        return _model_cache[cache_key], _model_cache.get(f"{cache_key}_version", "cached")
    
    model = None
    version = None
    
    # Get strategy for this model type
    strategy = MODEL_STRATEGY_OVERRIDE.get(model_type, MODEL_LOAD_STRATEGY)
    
    # Success model: Always load from local (not registered in MLflow)
    if strategy == "local" or model_type == "success":
        model, version = _load_local_model(model_type)
        if model is None:
            raise HTTPException(
                status_code=503,
                detail=f"Local model not found for {model_type}. Check models/artifacts/{model_type}/"
            )
    
    # Trust model with auto strategy: Try MLflow first, fallback to local
    elif strategy == "auto":
        print(f"🔄 Loading {model_type} model (auto strategy)...")
        model, version = _load_mlflow_model_with_timeout(model_type, timeout=10)
        
        if model is None:
            print(f"⚠️ MLflow failed for {model_type}, trying local...")
            model, version = _load_local_model(model_type)
    
    # Explicit local_first strategy
    elif MODEL_LOAD_STRATEGY == "local_first":
        model, version = _load_local_model(model_type)
        
        if model is None:
            print("⚠️ No local model found, trying MLflow with 5s timeout...")
            model, version = _load_mlflow_model_with_timeout(model_type, timeout=5)
    
    # Explicit mlflow_first strategy
    elif MODEL_LOAD_STRATEGY == "mlflow_first":
        model, version = _load_mlflow_model_with_timeout(model_type, timeout=10)
        
        if model is None:
            print("⚠️ MLflow failed, falling back to local model...")
            model, version = _load_local_model(model_type)
    
    # Cache result
    if model is not None:
        _model_cache[cache_key] = model
        _model_cache[f"{cache_key}_version"] = version
        _model_load_status[model_type] = {"status": "loaded", "version": version}
        return model, version
    
    # No model available
    _model_load_status[model_type] = {"status": "unavailable", "error": version}
    raise HTTPException(
        status_code=503,
        detail=f"Model not available. Tried local paths and MLflow. Set MODEL_LOAD_STRATEGY=local_first and ensure model files exist."
    )


def get_model_status():
    """Get current model loading status."""
    return {
        "strategy": MODEL_LOAD_STRATEGY,
        "model_strategies": MODEL_STRATEGY_OVERRIDE,
        "mlflow_uri": MLFLOW_TRACKING_URI,
        "local_paths": {k: [str(p) for p in v] for k, v in LOCAL_MODEL_PATHS.items()},
        "status": _model_load_status,
        "cached_models": list(_model_cache.keys()),
    }


# ============================================================================
# FEATURE ENGINEERING
# ============================================================================
def engineer_features(raw: RawKOLFeatures) -> np.ndarray:
    """Convert raw KOL data to engineered features."""
    import math
    
    # Log transforms
    log_followers = math.log(raw.followers_count + 1)
    log_following = math.log(raw.following_count + 1)
    log_posts = math.log(raw.post_count + 1)
    log_favorites = math.log(raw.favorites_count + 1)
    log_account_age = math.log(raw.account_age_days + 1)
    
    # Ratio features
    ff_ratio = raw.followers_count / max(raw.following_count, 1)
    followers_following_ratio_capped = min(ff_ratio, 10000)
    posts_per_day = raw.post_count / max(raw.account_age_days, 1)
    posts_per_day_capped = min(posts_per_day, 50)
    
    # Behavioral scores
    engagement_rate = raw.favorites_count / max(raw.post_count, 1)
    activity_score = (raw.post_count + raw.favorites_count) / max(raw.account_age_days, 1)
    profile_completeness = (int(raw.has_bio) + int(raw.has_url) + int(raw.has_profile_image)) / 3.0
    followers_per_day = raw.followers_count / max(raw.account_age_days, 1)
    posts_per_follower = raw.post_count / max(raw.followers_count, 1)
    following_per_day = raw.following_count / max(raw.account_age_days, 1)
    
    # Untrustworthy indicators
    high_activity_flag = 1.0 if posts_per_day > 20 else 0.0
    low_engagement_high_posts = 1.0 if (raw.post_count > 1000 and engagement_rate < 0.5) else 0.0
    default_profile_score = 1.0 - profile_completeness
    suspicious_growth = 1.0 if (followers_per_day > 100 and raw.account_age_days < 180) else 0.0
    fake_follower_indicator = 1.0 if (raw.followers_count > 10000 and engagement_rate < 0.1) else 0.0
    
    # Categorical tiers
    if raw.followers_count < 1000:
        followers_tier = 0  # Nano
    elif raw.followers_count < 10000:
        followers_tier = 1  # Micro
    elif raw.followers_count < 100000:
        followers_tier = 2  # Mid
    elif raw.followers_count < 1000000:
        followers_tier = 3  # Macro
    else:
        followers_tier = 4  # Mega
    
    if raw.account_age_days < 365:
        account_age_tier = 0
    elif raw.account_age_days < 730:
        account_age_tier = 1
    elif raw.account_age_days < 1825:
        account_age_tier = 2
    else:
        account_age_tier = 3
    
    if posts_per_day < 0.1:
        activity_tier = 0
    elif posts_per_day < 1:
        activity_tier = 1
    elif posts_per_day < 5:
        activity_tier = 2
    else:
        activity_tier = 3
    
    # Interaction features
    verified_followers_interaction = float(raw.verified) * log_followers
    profile_engagement_interaction = profile_completeness * engagement_rate
    age_activity_interaction = log_account_age * activity_score
    bio_length_norm = min(raw.bio_length / 200.0, 1.0)
    
    # Binary features
    has_bio = float(raw.has_bio)
    has_url = float(raw.has_url)
    has_profile_image = float(raw.has_profile_image)
    verified = float(raw.verified)
    
    # Build feature vector in correct order
    features = np.array([
        log_followers, log_following, log_posts, log_favorites, log_account_age,
        followers_following_ratio_capped, posts_per_day_capped,
        engagement_rate, activity_score, profile_completeness,
        followers_per_day, posts_per_follower, following_per_day,
        high_activity_flag, low_engagement_high_posts,
        default_profile_score, suspicious_growth, fake_follower_indicator,
        followers_tier, account_age_tier, activity_tier,
        verified_followers_interaction, profile_engagement_interaction,
        age_activity_interaction, bio_length_norm,
        has_bio, has_url, has_profile_image, verified
    ]).reshape(1, -1)
    
    return features


def get_risk_level(trust_score: float) -> str:
    """Convert trust score to risk level."""
    if trust_score >= 80:
        return "low"
    elif trust_score >= 60:
        return "moderate"
    elif trust_score >= 40:
        return "elevated"
    else:
        return "high"


# ============================================================================
# ENDPOINTS
# ============================================================================
@router.post("/trust", response_model=TrustScoreResponse)
async def predict_trust_score(request: RawKOLFeatures):
    """
    Predict Trust Score for a single KOL.
    
    This endpoint is called by:
    - Spark Streaming (for real-time scoring of new KOLs)
    - Dashboard (for on-demand scoring)
    
    Returns trust score (0-100) where:
    - 80-100: Highly Trustworthy (low risk)
    - 60-79: Moderately Trustworthy (moderate risk)
    - 40-59: Needs Review (elevated risk)
    - 0-39: Likely Untrustworthy (high risk)
    """
    try:
        # Load model (local-first strategy to avoid MLflow hanging)
        model, model_version = get_model("trust")
        
        # Engineer features
        features = engineer_features(request)
        
        # Predict - handle both Booster and Classifier models
        if hasattr(model, 'predict_proba'):
            # sklearn-style classifier (LGBMClassifier, etc.)
            proba = model.predict_proba(features)[0]
            # proba[0] = P(trustworthy), proba[1] = P(untrustworthy)
            trust_proba = float(proba[0])
        else:
            # LightGBM Booster - returns P(fake/bot)
            # Trust score = 1 - P(fake) = P(trustworthy)
            fake_proba = model.predict(features)[0]
            trust_proba = 1.0 - float(fake_proba)
        
        # Trust score = P(trustworthy) * 100
        trust_score = trust_proba * 100
        is_trustworthy = trust_score >= 50
        confidence = max(trust_proba, 1 - trust_proba)
        
        return TrustScoreResponse(
            kol_id=request.kol_id,
            trust_score=round(trust_score, 2),
            is_trustworthy=is_trustworthy,
            confidence=round(confidence, 4),
            risk_level=get_risk_level(trust_score),
            prediction_source="realtime",
            model_version=model_version,
            timestamp=datetime.now().isoformat()
        )
        
    except HTTPException:
        raise  # Re-raise HTTPExceptions as-is
    except ValueError as e:
        # Handle validation/feature engineering errors
        raise HTTPException(
            status_code=400,
            detail={
                "error": "validation_error",
                "message": str(e),
                "kol_id": request.kol_id
            }
        )
    except Exception as e:
        # Log the error for debugging (in production, use structured logging)
        import logging
        logging.error(f"Trust prediction error for {request.kol_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "prediction_error",
                "message": "An error occurred during prediction. Please try again.",
                "error_type": type(e).__name__
            }
        )


@router.post("/trust/batch", response_model=BatchPredictionResponse)
async def predict_trust_score_batch(request: BatchPredictionRequest):
    """
    Batch Trust Score prediction for multiple KOLs.
    
    Used by:
    - Batch Layer (daily scoring of all KOLs)
    - Dashboard (bulk queries)
    """
    import time
    start_time = time.time()
    
    try:
        model, model_version = get_model()
        
        predictions = []
        for kol in request.kols:
            features = engineer_features(kol)
            
            # Handle both Booster and Classifier models
            if hasattr(model, 'predict_proba'):
                proba = model.predict_proba(features)[0]
                trust_proba = float(proba[0])
            else:
                # LightGBM Booster returns P(fake/bot)
                fake_proba = model.predict(features)[0]
                trust_proba = 1.0 - float(fake_proba)
            
            trust_score = trust_proba * 100
            confidence = max(trust_proba, 1 - trust_proba)
            
            predictions.append(TrustScoreResponse(
                kol_id=kol.kol_id,
                trust_score=round(trust_score, 2),
                is_trustworthy=trust_score >= 50,
                confidence=round(confidence, 4),
                risk_level=get_risk_level(trust_score),
                prediction_source="batch",
                model_version=model_version,
                timestamp=datetime.now().isoformat()
            ))
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return BatchPredictionResponse(
            predictions=predictions,
            total=len(predictions),
            model_version=model_version,
            processing_time_ms=round(elapsed_ms, 2)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trust/features", response_model=TrustScoreResponse)
async def predict_from_engineered_features(request: EngineeredFeatures):
    """
    Predict Trust Score from pre-engineered features.
    
    Used when features are already computed (e.g., from batch processing).
    """
    try:
        model, model_version = get_model()
        
        # Build feature vector from dict
        features = np.array([
            request.features.get(col, 0.0) for col in FEATURE_COLUMNS
        ]).reshape(1, -1)
        
        # Handle both Booster and Classifier models
        if hasattr(model, 'predict_proba'):
            proba = model.predict_proba(features)[0]
            trust_proba = float(proba[0])
        else:
            # LightGBM Booster returns P(fake/bot)
            fake_proba = model.predict(features)[0]
            trust_proba = 1.0 - float(fake_proba)
        
        trust_score = trust_proba * 100
        confidence = max(trust_proba, 1 - trust_proba)
        
        return TrustScoreResponse(
            kol_id=request.kol_id,
            trust_score=round(trust_score, 2),
            is_trustworthy=trust_score >= 50,
            confidence=round(confidence, 4),
            risk_level=get_risk_level(trust_score),
            prediction_source="realtime",
            model_version=model_version,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trust/model-info")
async def get_model_info():
    """Get information about the currently loaded model and loading strategy."""
    try:
        # Get model status without triggering a load if not cached
        status = get_model_status()
        
        # Check if model is already cached
        if "trust_Production" in status.get("cached_models", []):
            model, model_version = get_model("trust")
            model_loaded = True
        else:
            model_loaded = False
            model_version = "not_loaded_yet"
        
        return {
            "model_name": MODEL_NAME,
            "model_stage": MODEL_STAGE,
            "model_version": model_version,
            "load_strategy": MODEL_LOAD_STRATEGY,
            "mlflow_uri": MLFLOW_TRACKING_URI,
            "local_paths": LOCAL_MODEL_PATHS.get("trust", []),
            "features_count": len(FEATURE_COLUMNS),
            "feature_names": FEATURE_COLUMNS,
            "status": "loaded" if model_loaded else "ready",
            "load_status": status.get("status", {}),
            "hint": "Call POST /predict/trust to trigger model loading"
        }
    except Exception as e:
        return {
            "model_name": MODEL_NAME,
            "model_stage": MODEL_STAGE,
            "load_strategy": MODEL_LOAD_STRATEGY,
            "status": "error",
            "error": str(e)
        }


@router.get("/health")
async def predict_health():
    """Health check for predict service - shows model availability."""
    trust_local = (PROJECT_ROOT / "models" / "artifacts" / "trust" / "lgbm_optuna_model.pkl").exists()
    success_local = (PROJECT_ROOT / "models" / "artifacts" / "success" / "success_lgbm_model.pkl").exists()
    
    return {
        "service": "predict",
        "status": "ok",
        "model_strategies": {
            "trust": MODEL_STRATEGY_OVERRIDE.get("trust", "auto"),
            "success": MODEL_STRATEGY_OVERRIDE.get("success", "local"),
        },
        "models_available": {
            "trust": {"local": trust_local, "mlflow": "trust-score-lightgbm-optuna"},
            "success": {"local": success_local, "mlflow": "not_registered"},
        },
        "mlflow_uri": MLFLOW_TRACKING_URI,
        "note": "Trust: MLflow→local fallback | Success: local only"
    }

# ============================================================
# SUCCESSSCORE ENDPOINTS (V2 - Binary Classification)
# ============================================================

class SuccessRequest(BaseModel):
    """Request model for SuccessScore prediction V2."""
    kol_id: str = Field(..., description="KOL identifier")
    video_views: float = Field(0, description="Video view count")
    video_likes: float = Field(0, description="Video likes")
    video_comments: float = Field(0, description="Video comments")
    video_shares: float = Field(0, description="Video shares")
    engagement_total: float = Field(0, description="Total engagement (likes+comments+shares)")
    engagement_rate: float = Field(0, description="Engagement rate (engagement/views)")
    est_clicks: float = Field(0, description="Estimated clicks")
    est_ctr: float = Field(0, description="Estimated CTR")
    price: float = Field(0, description="Product price")
    
class SuccessResponse(BaseModel):
    """Response model for SuccessScore prediction."""
    kol_id: str
    success_score: float = Field(..., ge=0, le=100)
    success_label: str = Field(..., description="High or Not-High (binary)")
    confidence: float = Field(..., ge=0, le=1)
    method: str = Field(default="ml", description="ml or rule_based")
    model_version: str = Field(default="v2")
    timestamp: str

# SuccessScore model cache
_success_model = None
_success_scaler = None
_success_features = None

def get_success_model():
    """Load SuccessScore model from artifacts."""
    global _success_model, _success_scaler, _success_features
    
    if _success_model is None:
        import joblib
        import json
        from pathlib import Path
        
        artifacts_dir = Path(__file__).parent.parent.parent.parent / "models" / "artifacts" / "success"
        
        if not artifacts_dir.exists():
            raise FileNotFoundError(f"Artifacts directory not found: {artifacts_dir}")
        
        model_path = artifacts_dir / "success_lgbm_model.pkl"
        scaler_path = artifacts_dir / "success_scaler.pkl"
        features_path = artifacts_dir / "feature_names.json"
        
        _success_model = joblib.load(model_path)
        _success_scaler = joblib.load(scaler_path)
        
        with open(features_path, 'r') as f:
            _success_features = json.load(f)
    
    return _success_model, _success_scaler, _success_features

@router.post("/success", response_model=SuccessResponse)
async def predict_success_score(request: SuccessRequest):
    """
    Predict SuccessScore for a KOL's product promotion (V2 - Binary).
    
    SuccessScore measures the likelihood of successful product sales
    based on KOL engagement metrics and product characteristics.
    
    Labels (Binary Classification):
    - High: Top 25% sales potential (score >= 50)
    - Not-High: Bottom 75% sales potential (score < 50)
    """
    import numpy as np
    import math
    
    try:
        model, scaler, feature_names = get_success_model()
        
        # Auto-calculate derived features if not provided
        views = max(request.video_views, 1)
        engagement = request.engagement_total or (request.video_likes + request.video_comments + request.video_shares)
        eng_rate = request.engagement_rate or (engagement / views)
        
        # Build feature vector matching model V2's feature_names.json (21 features)
        feature_map = {
            # Core metrics
            'video_views': request.video_views,
            'video_likes': request.video_likes,
            'video_comments': request.video_comments,
            'video_shares': request.video_shares,
            'engagement_total': engagement,
            'engagement_rate': eng_rate,
            'est_clicks': request.est_clicks,
            'est_ctr': request.est_ctr,
            # Ratios
            'likes_per_view': request.video_likes / views,
            'comments_per_view': request.video_comments / views,
            'shares_per_view': request.video_shares / views,
            # Log transforms
            'log_views': math.log1p(request.video_views),
            'log_engagement': math.log1p(engagement),
            'log_clicks': math.log1p(request.est_clicks),
            'log_price': math.log1p(request.price),
            # Price features
            'price': request.price,
            'price_tier': min(4, int(request.price / 200000)),  # Simplified binning
            # Interactions
            'engagement_x_ctr': eng_rate * request.est_ctr,
            'views_x_ctr': request.video_views * request.est_ctr,
            # Indicators (thresholds based on training data)
            'is_viral_views': 1 if request.video_views > 500000 else 0,
            'is_high_engagement': 1 if eng_rate > 0.05 else 0,
        }
        
        # Create feature array in correct order
        features = np.array([[feature_map.get(f, 0) for f in feature_names]])
        
        # Scale features
        features_scaled = scaler.transform(features)
        
        # Predict (Binary: 0=Not-High, 1=High)
        if hasattr(model, 'predict_proba'):
            proba = model.predict_proba(features_scaled)[0]
            pred_class = int(np.argmax(proba))
            confidence = float(proba[pred_class])
            # Score = probability of High class * 100
            success_score = float(proba[1]) * 100
        else:
            pred_class = int(model.predict(features_scaled)[0])
            confidence = 0.7
            success_score = 75 if pred_class == 1 else 25
        
        # Map to labels (Binary)
        success_label = 'High' if pred_class == 1 else 'Not-High'
        
        return SuccessResponse(
            kol_id=request.kol_id,
            success_score=round(success_score, 2),
            success_label=success_label,
            confidence=round(confidence, 4),
            method="ml",
            model_version="v2_binary",
            timestamp=datetime.now().isoformat()
        )
        
    except FileNotFoundError as e:
        # Fallback to rule-based
        engagement = request.engagement_total or (request.video_likes + request.video_comments + request.video_shares)
        eng_rate = request.engagement_rate or (engagement / max(request.video_views, 1))
        
        # Rule-based scoring
        score = 0
        score += min(30, request.video_views / 50000 * 30)  # Views contribution
        score += min(30, eng_rate * 300)  # Engagement rate contribution
        score += min(20, request.est_ctr * 200)  # CTR contribution
        score += min(20, engagement / 5000 * 20)  # Total engagement contribution
        
        success_label = 'High' if score >= 50 else 'Not-High'
        
        return SuccessResponse(
            kol_id=request.kol_id,
            success_score=round(score, 2),
            success_label=success_label,
            confidence=0.6,
            method="rule_based",
            model_version="v2_fallback",
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# TRENDINGSCORE ENDPOINTS (V2 - Improved Formula)
# ============================================================

class TrendingRequest(BaseModel):
    """Request model for TrendingScore calculation V2."""
    kol_id: str = Field(..., description="KOL identifier")
    current_velocity: float = Field(..., description="Current weighted event velocity")
    baseline_velocity: float = Field(1.0, description="KOL's historical baseline velocity")
    global_avg_velocity: float = Field(1.0, description="Global average velocity")
    momentum: float = Field(0.0, description="Rate of change (acceleration)")

class TrendingResponse(BaseModel):
    """Response model for TrendingScore V2."""
    kol_id: str
    trending_score: float = Field(..., ge=0, le=100)
    trending_label: str = Field(..., description="Cold/Normal/Warm/Hot/Viral")
    personal_growth: float = Field(..., description="Growth vs own baseline")
    market_position: float = Field(..., description="Position vs market average")
    raw_score: float
    model_version: str = Field(default="v2")
    timestamp: str

@router.post("/trending", response_model=TrendingResponse)
async def calculate_trending_score(request: TrendingRequest):
    """
    Calculate TrendingScore V2 for a KOL based on activity velocity.
    
    Improved formula with:
    - Personal growth (50% weight): current / baseline
    - Market position (30% weight): current / global_avg
    - Momentum (20% weight): acceleration/deceleration
    
    Sigmoid normalization for bounded output.
    
    Labels (score ranges):
    - Cold: 0-25 (declining or inactive)
    - Normal: 25-40 (steady state)
    - Warm: 40-60 (growing interest)
    - Hot: 60-80 (significant momentum)
    - Viral: 80-100 (explosive growth)
    """
    import math
    
    try:
        # Avoid division by zero
        baseline = max(request.baseline_velocity, 0.1)
        global_avg = max(request.global_avg_velocity, 0.1)
        
        # Calculate components
        personal_growth = request.current_velocity / baseline
        market_position = request.current_velocity / global_avg
        
        # Weighted combination (V2 formula)
        # α=0.5 (personal growth), β=0.3 (market), γ=0.2 (momentum)
        raw_score = (
            0.5 * personal_growth +
            0.3 * market_position +
            0.2 * (1 + request.momentum)  # Normalized around 1
        )
        
        # Sigmoid normalization to [0, 100]
        # Tuned: raw_score=1 → ~30, raw_score=2 → ~50, raw_score=5 → ~85
        k = 0.8  # Steepness
        threshold = 2.0  # Center point
        trending_score = 100 / (1 + math.exp(-k * (raw_score - threshold)))
        trending_score = max(0, min(100, trending_score))
        
        # Determine label (adjusted thresholds for V2)
        if trending_score >= 80:
            trending_label = 'Viral'
        elif trending_score >= 60:
            trending_label = 'Hot'
        elif trending_score >= 40:
            trending_label = 'Warm'
        elif trending_score >= 25:
            trending_label = 'Normal'
        else:
            trending_label = 'Cold'
        
        return TrendingResponse(
            kol_id=request.kol_id,
            trending_score=round(trending_score, 2),
            trending_label=trending_label,
            personal_growth=round(personal_growth, 4),
            market_position=round(market_position, 4),
            raw_score=round(raw_score, 4),
            model_version="v2",
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/success/model-info")
async def get_success_model_info():
    """Get information about the SuccessScore model."""
    try:
        model, scaler, feature_names = get_success_model()
        
        return {
            "model_type": "LightGBM Classifier",
            "num_classes": 3,
            "class_labels": ["Low", "Medium", "High"],
            "features_count": len(feature_names),
            "feature_names": feature_names,
            "status": "loaded"
        }
    except Exception as e:
        return {
            "model_type": "LightGBM Classifier",
            "status": "not_loaded",
            "fallback": "rule_based",
            "error": str(e)
        }
