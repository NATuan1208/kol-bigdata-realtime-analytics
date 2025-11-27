"""
KOL TRUST SCORE - ENSEMBLE STACKING & CALIBRATION
==================================================

Combine predictions từ multiple models:
- XGBoost Classifier (supervised)
- LightGBM Classifier (supervised)  
- Isolation Forest (unsupervised anomaly)

Meta-learner: Calibrated Logistic Regression
Output: Trust Score 0-100 (0 = untrustworthy, 100 = trustworthy)

Usage:
------
# Train ensemble (requires base models already trained)
python models/trust/stack_calibrate.py

# Score new data
python models/trust/stack_calibrate.py --score-only
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

from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibratedClassifierCV
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, brier_score_loss,
    confusion_matrix, classification_report
)

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models.trust.data_loader import load_training_data

MODEL_DIR = PROJECT_ROOT / "models" / "artifacts" / "trust"
ENSEMBLE_NAME = "ensemble_trust_score"


def load_base_models() -> dict:
    """Load all trained base models."""
    print("\n" + "="*60)
    print("📦 LOADING BASE MODELS")
    print("="*60)
    
    models = {}
    
    # XGBoost
    try:
        xgb_path = MODEL_DIR / "xgb_trust_classifier_latest.joblib"
        xgb_model = joblib.load(xgb_path)
        with open(str(xgb_path).replace(".joblib", "_metadata.json"), "r") as f:
            xgb_meta = json.load(f)
        models["xgboost"] = (xgb_model, xgb_meta)
        print(f"   ✅ XGBoost: ROC-AUC={xgb_meta['metrics']['roc_auc']:.4f}")
    except FileNotFoundError:
        print(f"   ⚠️ XGBoost model not found")
    
    # LightGBM
    try:
        lgbm_path = MODEL_DIR / "lgbm_trust_classifier_latest.joblib"
        lgbm_model = joblib.load(lgbm_path)
        with open(str(lgbm_path).replace(".joblib", "_metadata.json"), "r") as f:
            lgbm_meta = json.load(f)
        models["lightgbm"] = (lgbm_model, lgbm_meta)
        print(f"   ✅ LightGBM: ROC-AUC={lgbm_meta['metrics']['roc_auc']:.4f}")
    except FileNotFoundError:
        print(f"   ⚠️ LightGBM model not found")
    
    # Isolation Forest
    try:
        iforest_path = MODEL_DIR / "iforest_trust_anomaly_latest.joblib"
        iforest_model = joblib.load(iforest_path)
        iforest_scaler = joblib.load(str(iforest_path).replace(".joblib", "_scaler.joblib"))
        with open(str(iforest_path).replace(".joblib", "_metadata.json"), "r") as f:
            iforest_meta = json.load(f)
        models["iforest"] = (iforest_model, iforest_scaler, iforest_meta)
        print(f"   ✅ IForest: ROC-AUC={iforest_meta['metrics']['roc_auc']:.4f}")
    except FileNotFoundError:
        print(f"   ⚠️ Isolation Forest not found")
    
    if len(models) < 2:
        raise RuntimeError("Need at least 2 base models for ensemble!")
    return models


def get_base_predictions(models: dict, X: pd.DataFrame) -> pd.DataFrame:
    """Get probability predictions from all base models."""
    predictions = {}
    
    if "xgboost" in models:
        xgb_model, _ = models["xgboost"]
        predictions["xgb_prob"] = xgb_model.predict_proba(X)[:, 1]
    
    if "lightgbm" in models:
        lgbm_model, _ = models["lightgbm"]
        predictions["lgbm_prob"] = lgbm_model.predict_proba(X)[:, 1]
    
    if "iforest" in models:
        iforest_model, iforest_scaler, iforest_meta = models["iforest"]
        feature_names = iforest_meta["feature_names"]
        X_iforest = X[[f for f in feature_names if f in X.columns]].copy()
        X_iforest = X_iforest.replace([np.inf, -np.inf], np.nan).fillna(X_iforest.median())
        X_scaled = iforest_scaler.transform(X_iforest)
        raw_scores = -iforest_model.decision_function(X_scaled)
        min_s, max_s = raw_scores.min(), raw_scores.max()
        if max_s > min_s:
            predictions["iforest_score"] = (raw_scores - min_s) / (max_s - min_s)
        else:
            predictions["iforest_score"] = np.zeros(len(X))
    
    return pd.DataFrame(predictions)


def train_stacking_ensemble(base_predictions: pd.DataFrame, y_train: pd.Series, calibrate: bool = True):
    """Train stacking meta-learner (Logistic Regression)."""
    print("\n" + "="*60)
    print("🎯 TRAINING STACKING META-LEARNER")
    print("="*60)
    
    print(f"\n📋 Base model features:")
    for col in base_predictions.columns:
        print(f"   {col}: mean={base_predictions[col].mean():.3f}")
    
    meta_model = LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000, random_state=42)
    meta_model.fit(base_predictions, y_train)
    
    print(f"\n🔧 Meta-learner coefficients:")
    for feat, coef in zip(base_predictions.columns, meta_model.coef_[0]):
        print(f"   {feat}: {coef:.4f}")
    
    calibrator = None
    if calibrate:
        print(f"\n🎚️ Calibrating probabilities...")
        calibrator = CalibratedClassifierCV(meta_model, method="isotonic", cv=5)
        calibrator.fit(base_predictions, y_train)
    
    return meta_model, calibrator


def compute_trust_score(proba_untrustworthy: np.ndarray) -> np.ndarray:
    """Convert P(untrustworthy) to Trust Score 0-100."""
    return np.clip(100 - (proba_untrustworthy * 100), 0, 100)


def evaluate_ensemble(meta_model, calibrator, base_predictions: pd.DataFrame, y_test: pd.Series) -> dict:
    """Evaluate ensemble model performance."""
    print("\n" + "="*60)
    print("📊 ENSEMBLE EVALUATION")
    print("="*60)
    
    if calibrator is not None:
        y_proba = calibrator.predict_proba(base_predictions)[:, 1]
    else:
        y_proba = meta_model.predict_proba(base_predictions)[:, 1]
    
    y_pred = (y_proba >= 0.5).astype(int)
    trust_scores = compute_trust_score(y_proba)
    
    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred),
        "f1_score": f1_score(y_test, y_pred),
        "roc_auc": roc_auc_score(y_test, y_proba),
        "pr_auc": average_precision_score(y_test, y_proba),
        "brier_score": brier_score_loss(y_test, y_proba),
    }
    
    print(f"\n📈 Metrics:")
    for metric, value in metrics.items():
        status = "✅" if value >= 0.8 or (metric == "brier_score" and value <= 0.15) else "⚠️"
        print(f"   {status} {metric}: {value:.4f}")
    
    cm = confusion_matrix(y_test, y_pred)
    print(f"\n📋 Confusion Matrix:")
    print(f"   TN={cm[0,0]:,}  FP={cm[0,1]:,}")
    print(f"   FN={cm[1,0]:,}  TP={cm[1,1]:,}")
    
    print(f"\n📊 Trust Score Distribution:")
    score_df = pd.DataFrame({"trust_score": trust_scores, "label": y_test})
    for label in [0, 1]:
        subset = score_df[score_df["label"] == label]["trust_score"]
        name = "Trustworthy" if label == 0 else "Untrustworthy"
        print(f"   {name}: mean={subset.mean():.1f}, std={subset.std():.1f}")
    
    return metrics


def save_ensemble(meta_model, calibrator, base_models: dict, metrics: dict):
    """Save ensemble model."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    meta_path = MODEL_DIR / f"{ENSEMBLE_NAME}_{timestamp}_meta.joblib"
    joblib.dump(meta_model, meta_path)
    print(f"\n💾 Meta-learner saved: {meta_path}")
    
    if calibrator:
        cal_path = MODEL_DIR / f"{ENSEMBLE_NAME}_{timestamp}_calibrator.joblib"
        joblib.dump(calibrator, cal_path)
    
    metadata = {
        "ensemble_name": ENSEMBLE_NAME, "timestamp": timestamp,
        "metrics": metrics, "base_models": list(base_models.keys()),
    }
    with open(MODEL_DIR / f"{ENSEMBLE_NAME}_{timestamp}_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    
    # Save as latest
    joblib.dump(meta_model, MODEL_DIR / f"{ENSEMBLE_NAME}_latest_meta.joblib")
    if calibrator:
        joblib.dump(calibrator, MODEL_DIR / f"{ENSEMBLE_NAME}_latest_calibrator.joblib")
    with open(MODEL_DIR / f"{ENSEMBLE_NAME}_latest_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    
    print(f"🔗 Latest symlinks updated")


def main():
    parser = argparse.ArgumentParser(description="Train Ensemble Stacking")
    parser.add_argument("--no-calibrate", action="store_true")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    
    print("="*70)
    print("🎯 ENSEMBLE STACKING - TRUST SCORE")
    print("="*70)
    
    X_train, X_test, y_train, y_test = load_training_data(test_size=0.2)
    base_models = load_base_models()
    
    train_preds = get_base_predictions(base_models, X_train)
    test_preds = get_base_predictions(base_models, X_test)
    
    meta_model, calibrator = train_stacking_ensemble(train_preds, y_train, not args.no_calibrate)
    metrics = evaluate_ensemble(meta_model, calibrator, test_preds, y_test)
    
    if not args.no_save:
        save_ensemble(meta_model, calibrator, base_models, metrics)
    
    print("\n" + "="*70)
    print("✅ ENSEMBLE STACKING COMPLETE!")
    print("="*70)
    
    return meta_model, calibrator, metrics


if __name__ == "__main__":
    main()
