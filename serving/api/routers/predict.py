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
from typing import Optional, List, Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
import numpy as np

router = APIRouter()

# ============================================================================
# CONFIGURATION
# ============================================================================
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MODEL_NAME = os.getenv("MLFLOW_MODEL_NAME_TRUST", "trust-score-lightgbm-optuna")
MODEL_STAGE = os.getenv("MLFLOW_MODEL_STAGE", "Production")

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
# MODEL LOADING (Lazy loading with caching)
# ============================================================================
_model_cache = {}

def get_model():
    """Load model from MLflow registry (cached)."""
    global _model_cache
    
    cache_key = f"{MODEL_NAME}_{MODEL_STAGE}"
    
    if cache_key not in _model_cache:
        try:
            import mlflow
            mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
            
            # Use pyfunc for generic model loading (works with sklearn, lightgbm, xgboost)
            model_uri = f"models:/{MODEL_NAME}/{MODEL_STAGE}"
            loaded_model = mlflow.pyfunc.load_model(model_uri)
            
            # Get the underlying sklearn/lightgbm model
            _model_cache[cache_key] = loaded_model._model_impl.python_model.lgb_model
            _model_cache[f"{cache_key}_version"] = f"{MODEL_NAME}-{MODEL_STAGE}"
            print(f"✅ Loaded MLflow model: {model_uri}")
        except Exception as e:
            print(f"⚠️ MLflow pyfunc load failed: {e}")
            # Try lightgbm flavor directly
            try:
                import mlflow.lightgbm
                model_uri = f"models:/{MODEL_NAME}/{MODEL_STAGE}"
                _model_cache[cache_key] = mlflow.lightgbm.load_model(model_uri)
                _model_cache[f"{cache_key}_version"] = f"{MODEL_NAME}-{MODEL_STAGE}"
                print(f"✅ Loaded MLflow LightGBM model: {model_uri}")
            except Exception as e2:
                print(f"⚠️ MLflow LightGBM load failed: {e2}")
                # Try sklearn flavor
                try:
                    import mlflow.sklearn
                    model_uri = f"models:/{MODEL_NAME}/{MODEL_STAGE}"
                    _model_cache[cache_key] = mlflow.sklearn.load_model(model_uri)
                    _model_cache[f"{cache_key}_version"] = f"{MODEL_NAME}-{MODEL_STAGE}"
                    print(f"✅ Loaded MLflow sklearn model: {model_uri}")
                except Exception as e3:
                    print(f"⚠️ MLflow sklearn load failed: {e3}")
                    # Last fallback: load from local file
                    try:
                        import joblib
                        model_path = "/app/models/artifacts/trust/lgbm_optuna_model.pkl"
                        _model_cache[cache_key] = joblib.load(model_path)
                        _model_cache[f"{cache_key}_version"] = "local-fallback"
                        print(f"✅ Loaded fallback model from: {model_path}")
                    except Exception as e4:
                        raise HTTPException(
                            status_code=503,
                            detail=f"Model not available: {str(e4)}"
                        )
    
    return _model_cache[cache_key], _model_cache.get(f"{cache_key}_version", "unknown")


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
        # Load model
        model, model_version = get_model()
        
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
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    """Get information about the currently loaded model."""
    try:
        model, model_version = get_model()
        
        return {
            "model_name": MODEL_NAME,
            "model_stage": MODEL_STAGE,
            "model_version": model_version,
            "mlflow_uri": MLFLOW_TRACKING_URI,
            "features_count": len(FEATURE_COLUMNS),
            "feature_names": FEATURE_COLUMNS,
            "status": "loaded"
        }
    except Exception as e:
        return {
            "model_name": MODEL_NAME,
            "model_stage": MODEL_STAGE,
            "status": "error",
            "error": str(e)
        }
