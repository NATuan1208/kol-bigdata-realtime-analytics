"""
KOL TRUST SCORE - ISOLATION FOREST (ANOMALY DETECTION)
=======================================================

Unsupervised anomaly detection để identify KOL patterns bất thường.
- Không cần labels để train
- Output: anomaly score (higher = more anomalous = less trustworthy)
- Complement supervised models (XGBoost, LightGBM)

Use cases:
- Detect novel patterns chưa có trong training data
- Provide additional signal cho ensemble
- Flag extreme outliers

Usage:
------
# Train và score
python models/trust/score_iforest.py

# Score only (load existing model)
python models/trust/score_iforest.py --score-only
"""

import os
import sys
import json
import argparse
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
import joblib

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import (
    precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix
)

warnings.filterwarnings('ignore')

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models.trust.data_loader import (
    load_training_data,
    load_features_dataframe,
    get_feature_names
)


# =============================================================================
# CONFIGURATION
# =============================================================================
MODEL_DIR = PROJECT_ROOT / "models" / "artifacts" / "trust"
MODEL_NAME = "iforest_trust_anomaly"

# Default Isolation Forest params
DEFAULT_PARAMS = {
    "n_estimators": 200,
    "max_samples": "auto",
    "contamination": 0.33,  # ~33% untrustworthy trong data
    "max_features": 1.0,
    "bootstrap": False,
    "n_jobs": -1,
    "random_state": 42,
    "verbose": 0,
}

# Features tốt cho anomaly detection (focus on ratios & behaviors)
ANOMALY_FEATURES = [
    # Ratios (normalized, good for detecting outliers)
    "followers_following_ratio",
    "posts_per_day",
    "followers_per_day",
    "engagement_score",
    
    # Log transforms (better distribution)
    "log_followers_count",
    "log_following_count",
    "log_post_count",
    
    # Categorical indicators
    "ff_ratio_category",
    "suspicious_ff_ratio",
    "posts_per_day_category",
    "account_maturity_category",
    
    # Scores
    "profile_completeness_score",
    "fake_follower_indicator",
    "follower_engagement_ratio",
    
    # Binary features
    "has_profile_image",
    "has_bio",
    "has_url",
    "verified",
    "default_profile",
    "default_profile_image",
]


# =============================================================================
# MODEL TRAINING
# =============================================================================

def train_isolation_forest(
    X: pd.DataFrame,
    params: dict = None,
    feature_subset: list[str] = None
) -> tuple[IsolationForest, StandardScaler]:
    """
    Train Isolation Forest model.
    """
    print("\n" + "="*60)
    print("🌲 TRAINING ISOLATION FOREST (ANOMALY DETECTION)")
    print("="*60)
    
    model_params = DEFAULT_PARAMS.copy()
    if params:
        model_params.update(params)
    
    if feature_subset:
        available = [f for f in feature_subset if f in X.columns]
        print(f"\n📋 Using {len(available)} anomaly-specific features")
        X_train = X[available].copy()
    else:
        print(f"\n📋 Using all {X.shape[1]} features")
        X_train = X.copy()
    
    feature_names = list(X_train.columns)
    X_train = X_train.replace([np.inf, -np.inf], np.nan).fillna(X_train.median())
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    
    print(f"\n📋 Model Parameters:")
    for k, v in model_params.items():
        print(f"   {k}: {v}")
    
    print(f"\n🎯 Training on {X_scaled.shape[0]:,} samples...")
    
    model = IsolationForest(**model_params)
    model.fit(X_scaled)
    model.feature_names_ = feature_names
    
    print(f"   Training complete!")
    return model, scaler


def score_anomalies(
    model: IsolationForest,
    scaler: StandardScaler,
    X: pd.DataFrame,
    feature_names: list[str] = None
) -> np.ndarray:
    """Score samples - higher = more anomalous."""
    if feature_names is None:
        feature_names = model.feature_names_
    
    X_subset = X[feature_names].copy()
    X_subset = X_subset.replace([np.inf, -np.inf], np.nan).fillna(X_subset.median())
    X_scaled = scaler.transform(X_subset)
    
    raw_scores = model.decision_function(X_scaled)
    anomaly_scores = -raw_scores
    
    min_score, max_score = anomaly_scores.min(), anomaly_scores.max()
    if max_score > min_score:
        normalized_scores = (anomaly_scores - min_score) / (max_score - min_score)
    else:
        normalized_scores = np.zeros_like(anomaly_scores)
    
    return normalized_scores


# =============================================================================
# EVALUATION
# =============================================================================

def evaluate_anomaly_model(
    model: IsolationForest,
    scaler: StandardScaler,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    feature_names: list[str] = None
) -> dict:
    """Evaluate using ground truth labels."""
    print("\n" + "="*60)
    print("📊 ANOMALY DETECTION EVALUATION")
    print("="*60)
    
    scores = score_anomalies(model, scaler, X_test, feature_names)
    
    X_subset = X_test[feature_names].copy()
    X_subset = X_subset.replace([np.inf, -np.inf], np.nan).fillna(X_subset.median())
    X_scaled = scaler.transform(X_subset)
    y_pred_raw = model.predict(X_scaled)
    y_pred = (y_pred_raw == -1).astype(int)
    
    metrics = {
        "accuracy": (y_pred == y_test).mean(),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1_score": f1_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, scores),
    }
    
    print(f"\n📈 Metrics:")
    for metric, value in metrics.items():
        status = "✅" if value >= 0.7 else "⚠️" if value >= 0.6 else "❌"
        print(f"   {status} {metric}: {value:.4f}")
    
    cm = confusion_matrix(y_test, y_pred)
    print(f"\n📋 Confusion Matrix:")
    print(f"   TN={cm[0,0]:,}  FP={cm[0,1]:,}")
    print(f"   FN={cm[1,0]:,}  TP={cm[1,1]:,}")
    
    print(f"\n📊 Anomaly Score Distribution:")
    score_df = pd.DataFrame({"score": scores, "label": y_test})
    for label in [0, 1]:
        subset = score_df[score_df["label"] == label]["score"]
        label_name = "Trustworthy" if label == 0 else "Untrustworthy"
        print(f"   {label_name} (n={len(subset):,}): "
              f"mean={subset.mean():.3f}, std={subset.std():.3f}")
    
    return metrics


# =============================================================================
# MODEL PERSISTENCE
# =============================================================================

def save_model(model, scaler, metrics, params, feature_names):
    """Save model, scaler, and metadata."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    model_path = MODEL_DIR / f"{MODEL_NAME}_{timestamp}.joblib"
    joblib.dump(model, model_path)
    print(f"\n💾 Model saved: {model_path}")
    
    scaler_path = MODEL_DIR / f"{MODEL_NAME}_{timestamp}_scaler.joblib"
    joblib.dump(scaler, scaler_path)
    
    metadata = {
        "model_name": MODEL_NAME, "timestamp": timestamp,
        "metrics": metrics, "params": params,
        "feature_names": feature_names, "n_features": len(feature_names),
    }
    
    metadata_path = MODEL_DIR / f"{MODEL_NAME}_{timestamp}_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    
    # Save as latest
    joblib.dump(model, MODEL_DIR / f"{MODEL_NAME}_latest.joblib")
    joblib.dump(scaler, MODEL_DIR / f"{MODEL_NAME}_latest_scaler.joblib")
    with open(MODEL_DIR / f"{MODEL_NAME}_latest_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    
    print(f"🔗 Latest symlinks updated")
    return model_path, metadata_path


def load_model(model_path=None):
    """Load saved model, scaler, and metadata."""
    if model_path is None:
        model_path = MODEL_DIR / f"{MODEL_NAME}_latest.joblib"
    model = joblib.load(model_path)
    scaler = joblib.load(str(model_path).replace(".joblib", "_scaler.joblib"))
    with open(str(model_path).replace(".joblib", "_metadata.json"), "r") as f:
        metadata = json.load(f)
    return model, scaler, metadata


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Train Isolation Forest Anomaly Detector")
    parser.add_argument("--contamination", type=float, default=0.33)
    parser.add_argument("--n-estimators", type=int, default=200)
    parser.add_argument("--use-all-features", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    
    print("="*70)
    print("🌲 ISOLATION FOREST - ANOMALY DETECTION")
    print("="*70)
    
    X_train, X_test, y_train, y_test = load_training_data(test_size=0.2)
    
    feature_subset = None if args.use_all_features else [
        f for f in ANOMALY_FEATURES if f in X_train.columns
    ]
    
    params = DEFAULT_PARAMS.copy()
    params["contamination"] = args.contamination
    params["n_estimators"] = args.n_estimators
    
    X_all = pd.concat([X_train, X_test], ignore_index=True)
    model, scaler = train_isolation_forest(X_all, params, feature_subset)
    
    metrics = evaluate_anomaly_model(model, scaler, X_test, y_test, model.feature_names_)
    
    if not args.no_save:
        save_model(model, scaler, metrics, params, model.feature_names_)
    
    print("\n" + "="*70)
    print("✅ ISOLATION FOREST COMPLETE!")
    print("="*70)
    
    return model, scaler, metrics


if __name__ == "__main__":
    main()
