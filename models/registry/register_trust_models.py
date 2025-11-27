"""
Register Trust Score Models to MLflow Registry
==============================================
Register best models to MLflow for production deployment.

Models registered:
- trust-score-lightgbm-optuna (Best - Production)
- trust-score-ensemble (Backup - Staging)

Usage:
    docker exec kol-trainer python -m models.registry.register_trust_models
"""

import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

import mlflow
from mlflow.tracking import MlflowClient
import joblib

# ============================================================================
# CONFIGURATION
# ============================================================================
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
EXPERIMENT_NAME = "KOL-Trust-Score"

ARTIFACTS_DIR = Path("models/artifacts/trust")
OPTUNA_DIR = Path("models/artifacts/optuna")
REPORTS_DIR = Path("models/reports")


def setup_mlflow():
    """Setup MLflow connection."""
    print("=" * 60)
    print("🔧 Connecting to MLflow...")
    print("=" * 60)
    
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    print(f"   URI: {MLFLOW_TRACKING_URI}")
    
    # Create experiment if not exists
    experiment = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
    if experiment is None:
        mlflow.create_experiment(EXPERIMENT_NAME)
        print(f"   Created experiment: {EXPERIMENT_NAME}")
    else:
        print(f"   Using experiment: {EXPERIMENT_NAME}")
    
    mlflow.set_experiment(EXPERIMENT_NAME)


def register_lgbm_optuna():
    """Register LightGBM Optuna model (Best Model)."""
    print("\n" + "-" * 60)
    print("📦 Registering LightGBM + Optuna (Best Model 🏆)")
    print("-" * 60)
    
    model_path = ARTIFACTS_DIR / "lgbm_optuna_model.pkl"
    if not model_path.exists():
        print(f"   ❌ Model not found: {model_path}")
        return None
    
    model = joblib.load(model_path)
    
    # Load metrics
    metrics = {}
    metrics_path = REPORTS_DIR / "lgbm_optuna_metrics.json"
    if metrics_path.exists():
        with open(metrics_path) as f:
            metrics = json.load(f)
    
    # Load best params
    best_params = {}
    params_path = OPTUNA_DIR / "lgbm_best_params.json"
    if params_path.exists():
        with open(params_path) as f:
            best_params = json.load(f)
    
    model_name = "trust-score-lightgbm-optuna"
    
    with mlflow.start_run(run_name="lgbm-optuna-production") as run:
        # Log params
        mlflow.log_param("model_type", "LightGBM")
        mlflow.log_param("tuning", "Optuna (50 trials × 5-fold CV)")
        mlflow.log_param("best_max_depth", best_params.get("max_depth", "N/A"))
        mlflow.log_param("best_num_leaves", best_params.get("num_leaves", "N/A"))
        mlflow.log_param("best_learning_rate", best_params.get("learning_rate", "N/A"))
        
        # Log metrics
        mlflow.log_metric("roc_auc", metrics.get("roc_auc", 0))
        mlflow.log_metric("accuracy", metrics.get("accuracy", 0))
        mlflow.log_metric("f1_score", metrics.get("f1", 0))
        mlflow.log_metric("precision", metrics.get("precision", 0))
        mlflow.log_metric("recall", metrics.get("recall", 0))
        
        # Log model
        mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            registered_model_name=model_name
        )
        
        print(f"   ✅ Registered: {model_name}")
        print(f"   📊 ROC-AUC: {metrics.get('roc_auc', 'N/A')}")
        print(f"   📊 Accuracy: {metrics.get('accuracy', 'N/A')}")
        
        return run.info.run_id, model_name


def register_ensemble():
    """Register Ensemble model (Backup)."""
    print("\n" + "-" * 60)
    print("📦 Registering Ensemble (Backup)")
    print("-" * 60)
    
    # Find ensemble model
    models = list(ARTIFACTS_DIR.glob("ensemble_trust_score_*_meta.joblib"))
    if not models:
        print("   ⚠️ Ensemble model not found. Skipping.")
        return None
    
    model_path = max(models, key=lambda p: p.stat().st_mtime)
    model = joblib.load(model_path)
    
    model_name = "trust-score-ensemble"
    
    with mlflow.start_run(run_name="ensemble-backup") as run:
        mlflow.log_param("model_type", "Ensemble (XGB + LGBM + IForest)")
        mlflow.log_param("meta_learner", "LogisticRegression")
        
        mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            registered_model_name=model_name
        )
        
        print(f"   ✅ Registered: {model_name}")
        
        return run.info.run_id, model_name


def promote_to_production(model_name: str):
    """Promote latest version to Production."""
    client = MlflowClient()
    
    versions = client.get_latest_versions(model_name)
    if versions:
        version = versions[0].version
        client.transition_model_version_stage(
            name=model_name,
            version=version,
            stage="Production",
            archive_existing_versions=True
        )
        print(f"   🚀 {model_name} v{version} → Production")


def promote_to_staging(model_name: str):
    """Promote latest version to Staging."""
    client = MlflowClient()
    
    versions = client.get_latest_versions(model_name)
    if versions:
        version = versions[0].version
        client.transition_model_version_stage(
            name=model_name,
            version=version,
            stage="Staging"
        )
        print(f"   📋 {model_name} v{version} → Staging")


def main():
    print("=" * 60)
    print("🚀 MLflow Model Registration")
    print("=" * 60)
    
    start = time.time()
    
    setup_mlflow()
    
    # Register models
    lgbm_result = register_lgbm_optuna()
    ensemble_result = register_ensemble()
    
    # Promote to stages
    print("\n" + "=" * 60)
    print("🏆 Promoting Models")
    print("=" * 60)
    
    if lgbm_result:
        promote_to_production(lgbm_result[1])
    
    if ensemble_result:
        promote_to_staging(ensemble_result[1])
    
    # Summary
    elapsed = time.time() - start
    print("\n" + "=" * 60)
    print("✅ Registration Complete!")
    print("=" * 60)
    print(f"   Time: {elapsed:.1f}s")
    print(f"   MLflow UI: http://localhost:5000")
    print("\n   Models:")
    print("   - trust-score-lightgbm-optuna → Production 🏆")
    print("   - trust-score-ensemble → Staging")


if __name__ == "__main__":
    main()
