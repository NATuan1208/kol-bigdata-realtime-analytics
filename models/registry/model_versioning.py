"""
MLflow Model Versioning Utilities
==================================
Functions for loading and managing models from MLflow registry.

Usage:
    from models.registry.model_versioning import load_latest, list_models
    
    # Load production model
    model = load_latest("trust-score-lightgbm-optuna", stage="Production")
    
    # List all registered models
    models = list_models()
"""

import os
from typing import Optional, List, Dict, Any

import mlflow
from mlflow.tracking import MlflowClient

# Configuration
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")


def get_client() -> MlflowClient:
    """Get MLflow client."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    return MlflowClient()


def load_latest(model_name: str, stage: str = "Production"):
    """
    Load the latest model from MLflow registry.
    
    Args:
        model_name: Registered model name (e.g., "trust-score-lightgbm-optuna")
        stage: Model stage ("Production", "Staging", "None")
    
    Returns:
        Loaded model object
    """
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    model_uri = f"models:/{model_name}/{stage}"
    
    try:
        model = mlflow.sklearn.load_model(model_uri)
        print(f"✅ Loaded model: {model_uri}")
        return model
    except Exception as e:
        print(f"❌ Failed to load model {model_uri}: {e}")
        return None


def load_by_version(model_name: str, version: int):
    """
    Load a specific model version from MLflow registry.
    
    Args:
        model_name: Registered model name
        version: Model version number
    
    Returns:
        Loaded model object
    """
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    model_uri = f"models:/{model_name}/{version}"
    
    try:
        model = mlflow.sklearn.load_model(model_uri)
        print(f"✅ Loaded model: {model_uri}")
        return model
    except Exception as e:
        print(f"❌ Failed to load model {model_uri}: {e}")
        return None


def list_models() -> List[Dict[str, Any]]:
    """
    List all registered models.
    
    Returns:
        List of model info dictionaries
    """
    client = get_client()
    
    models = []
    for rm in client.search_registered_models():
        model_info = {
            "name": rm.name,
            "description": rm.description,
            "creation_time": rm.creation_timestamp,
            "last_updated": rm.last_updated_timestamp,
            "versions": []
        }
        
        # Get versions
        for version in rm.latest_versions:
            model_info["versions"].append({
                "version": version.version,
                "stage": version.current_stage,
                "status": version.status,
                "run_id": version.run_id
            })
        
        models.append(model_info)
    
    return models


def get_model_info(model_name: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed info about a specific registered model.
    
    Args:
        model_name: Registered model name
    
    Returns:
        Model info dictionary or None
    """
    client = get_client()
    
    try:
        rm = client.get_registered_model(model_name)
        
        versions = []
        for mv in client.search_model_versions(f"name='{model_name}'"):
            # Get run info for metrics
            run = client.get_run(mv.run_id)
            
            versions.append({
                "version": mv.version,
                "stage": mv.current_stage,
                "status": mv.status,
                "run_id": mv.run_id,
                "metrics": run.data.metrics,
                "params": run.data.params,
                "creation_time": mv.creation_timestamp
            })
        
        return {
            "name": rm.name,
            "description": rm.description,
            "versions": versions
        }
        
    except Exception as e:
        print(f"❌ Model not found: {model_name} - {e}")
        return None


def promote_model(model_name: str, version: int, stage: str = "Production"):
    """
    Promote a model version to a new stage.
    
    Args:
        model_name: Registered model name
        version: Version to promote
        stage: Target stage ("Staging" or "Production")
    """
    client = get_client()
    
    client.transition_model_version_stage(
        name=model_name,
        version=version,
        stage=stage,
        archive_existing_versions=True
    )
    
    print(f"✅ {model_name} v{version} → {stage}")


def compare_models(model_name: str) -> List[Dict[str, Any]]:
    """
    Compare all versions of a model.
    
    Args:
        model_name: Registered model name
    
    Returns:
        List of version comparisons
    """
    client = get_client()
    
    versions = []
    for mv in client.search_model_versions(f"name='{model_name}'"):
        run = client.get_run(mv.run_id)
        
        versions.append({
            "version": mv.version,
            "stage": mv.current_stage,
            "roc_auc": run.data.metrics.get("roc_auc", 0),
            "accuracy": run.data.metrics.get("accuracy", 0),
            "f1_score": run.data.metrics.get("f1_score", 0),
            "tuning": run.data.params.get("tuning", "unknown")
        })
    
    # Sort by ROC-AUC descending
    versions.sort(key=lambda x: x["roc_auc"], reverse=True)
    
    return versions

