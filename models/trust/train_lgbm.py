"""
KOL TRUST SCORE - LIGHTGBM CLASSIFIER
======================================

Train LightGBM model để detect KOL không đáng tin.
- Faster training than XGBoost
- Native categorical feature support
- Built-in early stopping
- Feature importance analysis

Usage:
------
# Train với default params
python models/trust/train_lgbm.py

# Train với Optuna tuning
python models/trust/train_lgbm.py --tune

# Train với custom params  
python models/trust/train_lgbm.py --n-estimators 200 --num-leaves 64
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

from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
    classification_report
)
from sklearn.model_selection import cross_val_score, StratifiedKFold

import lightgbm as lgb

warnings.filterwarnings('ignore')

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models.trust.data_loader import (
    load_training_data,
    get_feature_names,
    get_scale_pos_weight,
    get_class_weights
)


# =============================================================================
# CONFIGURATION
# =============================================================================
MODEL_DIR = PROJECT_ROOT / "models" / "artifacts" / "trust"
MODEL_NAME = "lgbm_trust_classifier"

# Default LightGBM params
DEFAULT_PARAMS = {
    "n_estimators": 150,
    "num_leaves": 31,
    "max_depth": -1,  # No limit
    "learning_rate": 0.1,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_samples": 20,
    "reg_alpha": 0.1,
    "reg_lambda": 0.1,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
    "force_col_wise": True,  # Avoid warning
}


# =============================================================================
# MODEL TRAINING
# =============================================================================

def train_lightgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame = None,
    y_val: pd.Series = None,
    params: dict = None,
    early_stopping_rounds: int = 20
) -> lgb.LGBMClassifier:
    """
    Train LightGBM classifier.
    
    Args:
        X_train: Training features
        y_train: Training labels
        X_val: Validation features (optional, for early stopping)
        y_val: Validation labels
        params: LightGBM parameters
        early_stopping_rounds: Stop if no improvement
        
    Returns:
        Trained LGBMClassifier
    """
    print("\n" + "="*60)
    print("🌿 TRAINING LIGHTGBM CLASSIFIER")
    print("="*60)
    
    # Merge with default params
    model_params = DEFAULT_PARAMS.copy()
    if params:
        model_params.update(params)
    
    # Handle class imbalance
    class_weights = get_class_weights(y_train)
    model_params["class_weight"] = class_weights
    
    print(f"\n📋 Model Parameters:")
    for k, v in model_params.items():
        if k != "class_weight":  # Don't print full dict
            print(f"   {k}: {v}")
    print(f"   class_weight: {class_weights}")
    
    # Create model
    model = lgb.LGBMClassifier(**model_params)
    
    # Fit with early stopping if validation set provided
    fit_params = {}
    if X_val is not None and y_val is not None:
        fit_params["eval_set"] = [(X_val, y_val)]
        fit_params["eval_metric"] = "logloss"
        
        # LightGBM callback for early stopping
        callbacks = [
            lgb.early_stopping(stopping_rounds=early_stopping_rounds, verbose=False),
            lgb.log_evaluation(period=0)  # Suppress iteration logs
        ]
        fit_params["callbacks"] = callbacks
        
        print(f"\n🎯 Training with early stopping (patience={early_stopping_rounds})...")
    else:
        print(f"\n🎯 Training without validation set...")
    
    # Train
    model.fit(X_train, y_train, **fit_params)
    
    # Best iteration info
    if hasattr(model, 'best_iteration_') and model.best_iteration_ > 0:
        print(f"   Best iteration: {model.best_iteration_}")
    
    return model


def tune_with_optuna(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    n_trials: int = 50,
    cv_folds: int = 5
) -> dict:
    """
    Hyperparameter tuning với Optuna.
    """
    try:
        import optuna
        from optuna.samplers import TPESampler
    except ImportError:
        print("⚠️ Optuna not installed. Using default params.")
        return DEFAULT_PARAMS
    
    print("\n" + "="*60)
    print("🔍 HYPERPARAMETER TUNING WITH OPTUNA")
    print("="*60)
    print(f"   Trials: {n_trials}")
    print(f"   CV Folds: {cv_folds}")
    
    class_weights = get_class_weights(y_train)
    
    def objective(trial):
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 50, 300),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "min_child_samples": trial.suggest_int("min_child_samples", 5, 50),
            "reg_alpha": trial.suggest_float("reg_alpha", 0, 1),
            "reg_lambda": trial.suggest_float("reg_lambda", 0, 1),
            "class_weight": class_weights,
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
            "force_col_wise": True,
        }
        
        model = lgb.LGBMClassifier(**params)
        
        # Cross-validation
        cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=42)
        scores = cross_val_score(model, X_train, y_train, cv=cv, scoring='roc_auc', n_jobs=-1)
        
        return scores.mean()
    
    # Suppress Optuna logs
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    
    sampler = TPESampler(seed=42)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    
    print(f"\n✅ Best trial:")
    print(f"   ROC-AUC: {study.best_trial.value:.4f}")
    print(f"   Params: {study.best_trial.params}")
    
    # Return best params merged with defaults
    best_params = DEFAULT_PARAMS.copy()
    best_params.update(study.best_trial.params)
    best_params["class_weight"] = class_weights
    
    return best_params


# =============================================================================
# EVALUATION
# =============================================================================

def evaluate_model(
    model: lgb.LGBMClassifier,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    threshold: float = 0.5
) -> dict:
    """
    Evaluate model performance.
    """
    print("\n" + "="*60)
    print("📊 MODEL EVALUATION")
    print("="*60)
    
    # Predictions
    y_pred_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_pred_proba >= threshold).astype(int)
    
    # Metrics
    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred),
        "f1_score": f1_score(y_test, y_pred),
        "roc_auc": roc_auc_score(y_test, y_pred_proba),
        "pr_auc": average_precision_score(y_test, y_pred_proba),
    }
    
    print(f"\n📈 Metrics (threshold={threshold}):")
    for metric, value in metrics.items():
        status = "✅" if value >= 0.8 else "⚠️" if value >= 0.7 else "❌"
        print(f"   {status} {metric}: {value:.4f}")
    
    # Confusion Matrix
    cm = confusion_matrix(y_test, y_pred)
    print(f"\n📋 Confusion Matrix:")
    print(f"   TN={cm[0,0]:,}  FP={cm[0,1]:,}")
    print(f"   FN={cm[1,0]:,}  TP={cm[1,1]:,}")
    
    # Classification Report
    print(f"\n📊 Classification Report:")
    print(classification_report(y_test, y_pred, 
          target_names=["Trustworthy (0)", "Untrustworthy (1)"]))
    
    return metrics


def get_feature_importance(
    model: lgb.LGBMClassifier,
    feature_names: list[str],
    importance_type: str = "gain",
    top_k: int = 15
) -> pd.DataFrame:
    """
    Get feature importance from trained model.
    
    Args:
        importance_type: "gain" or "split"
    """
    print("\n" + "="*60)
    print(f"🎯 FEATURE IMPORTANCE - {importance_type.upper()} (Top {top_k})")
    print("="*60)
    
    importance = model.booster_.feature_importance(importance_type=importance_type)
    
    df_importance = pd.DataFrame({
        "feature": feature_names,
        "importance": importance
    }).sort_values("importance", ascending=False)
    
    # Normalize for display
    max_imp = df_importance["importance"].max()
    
    # Print top features
    for _, row in df_importance.head(top_k).iterrows():
        bar_len = int((row["importance"] / max_imp) * 30) if max_imp > 0 else 0
        bar = "█" * bar_len
        print(f"   {row['feature']:<35} {row['importance']:>8.1f} {bar}")
    
    return df_importance


# =============================================================================
# MODEL PERSISTENCE
# =============================================================================

def save_model(
    model: lgb.LGBMClassifier,
    metrics: dict,
    params: dict,
    feature_names: list[str]
):
    """
    Save model and metadata.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save model
    model_path = MODEL_DIR / f"{MODEL_NAME}_{timestamp}.joblib"
    joblib.dump(model, model_path)
    print(f"\n💾 Model saved: {model_path}")
    
    # Also save native LightGBM format
    lgb_path = MODEL_DIR / f"{MODEL_NAME}_{timestamp}.lgb"
    model.booster_.save_model(str(lgb_path))
    print(f"💾 Native LGB saved: {lgb_path}")
    
    # Save metadata (convert class_weight dict keys to strings)
    params_serializable = params.copy()
    if "class_weight" in params_serializable:
        params_serializable["class_weight"] = {
            str(k): v for k, v in params_serializable["class_weight"].items()
        }
    
    metadata = {
        "model_name": MODEL_NAME,
        "timestamp": timestamp,
        "metrics": metrics,
        "params": params_serializable,
        "feature_names": feature_names,
        "n_features": len(feature_names),
    }
    
    metadata_path = MODEL_DIR / f"{MODEL_NAME}_{timestamp}_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"📋 Metadata saved: {metadata_path}")
    
    # Also save as "latest"
    latest_model_path = MODEL_DIR / f"{MODEL_NAME}_latest.joblib"
    joblib.dump(model, latest_model_path)
    
    latest_metadata_path = MODEL_DIR / f"{MODEL_NAME}_latest_metadata.json"
    with open(latest_metadata_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    
    print(f"🔗 Latest symlinks updated")
    
    return model_path, metadata_path


def load_model(model_path: str = None) -> tuple[lgb.LGBMClassifier, dict]:
    """
    Load saved model and metadata.
    """
    if model_path is None:
        model_path = MODEL_DIR / f"{MODEL_NAME}_latest.joblib"
    
    model = joblib.load(model_path)
    
    # Load metadata
    metadata_path = str(model_path).replace(".joblib", "_metadata.json")
    with open(metadata_path, "r") as f:
        metadata = json.load(f)
    
    return model, metadata


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Train LightGBM Trust Classifier")
    parser.add_argument("--tune", action="store_true", help="Run Optuna hyperparameter tuning")
    parser.add_argument("--n-trials", type=int, default=50, help="Optuna trials")
    parser.add_argument("--n-estimators", type=int, default=None, help="Number of trees")
    parser.add_argument("--num-leaves", type=int, default=None, help="Number of leaves")
    parser.add_argument("--learning-rate", type=float, default=None, help="Learning rate")
    parser.add_argument("--no-save", action="store_true", help="Don't save model")
    args = parser.parse_args()
    
    print("="*70)
    print("🌿 LIGHTGBM TRUST SCORE CLASSIFIER")
    print("="*70)
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load data
    X_train, X_test, y_train, y_test = load_training_data(test_size=0.2)
    feature_names = list(X_train.columns)
    
    # Split train into train/val for early stopping
    from sklearn.model_selection import train_test_split
    X_train_split, X_val, y_train_split, y_val = train_test_split(
        X_train, y_train, test_size=0.15, random_state=42, stratify=y_train
    )
    
    print(f"\n📊 Data Splits:")
    print(f"   Train: {len(X_train_split):,}")
    print(f"   Val:   {len(X_val):,}")
    print(f"   Test:  {len(X_test):,}")
    
    # Get params
    if args.tune:
        params = tune_with_optuna(X_train, y_train, n_trials=args.n_trials)
    else:
        params = DEFAULT_PARAMS.copy()
        params["class_weight"] = get_class_weights(y_train)
        if args.n_estimators:
            params["n_estimators"] = args.n_estimators
        if args.num_leaves:
            params["num_leaves"] = args.num_leaves
        if args.learning_rate:
            params["learning_rate"] = args.learning_rate
    
    # Train
    model = train_lightgbm(
        X_train_split, y_train_split,
        X_val, y_val,
        params=params,
        early_stopping_rounds=20
    )
    
    # Evaluate
    metrics = evaluate_model(model, X_test, y_test)
    
    # Feature importance (both gain and split)
    importance_gain = get_feature_importance(model, feature_names, importance_type="gain")
    importance_split = get_feature_importance(model, feature_names, importance_type="split")
    
    # Save
    if not args.no_save:
        save_model(model, metrics, params, feature_names)
    
    print("\n" + "="*70)
    print("✅ LIGHTGBM TRAINING COMPLETE!")
    print("="*70)
    
    return model, metrics


if __name__ == "__main__":
    main()
