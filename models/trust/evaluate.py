"""
KOL TRUST SCORE - MODEL EVALUATION & SHAP ANALYSIS
===================================================

Comprehensive evaluation script cho Trust Score models:
- Classification metrics (Precision, Recall, F1, ROC-AUC, PR-AUC)
- Confusion matrix visualization
- ROC & PR curves
- SHAP values for model interpretability
- Feature importance comparison across models

Usage:
------
# Evaluate all models
python models/trust/evaluate.py

# Evaluate specific model
python models/trust/evaluate.py --model xgboost

# Generate SHAP plots
python models/trust/evaluate.py --shap
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
    roc_auc_score, average_precision_score, brier_score_loss,
    confusion_matrix, classification_report,
    roc_curve, precision_recall_curve
)

warnings.filterwarnings('ignore')

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from models.trust.data_loader import load_training_data

MODEL_DIR = PROJECT_ROOT / "models" / "artifacts" / "trust"
REPORT_DIR = PROJECT_ROOT / "models" / "reports"


# =============================================================================
# LOAD MODELS
# =============================================================================

def load_all_models() -> dict:
    """Load all trained models for evaluation."""
    models = {}
    
    # XGBoost
    try:
        path = MODEL_DIR / "xgb_trust_classifier_latest.joblib"
        model = joblib.load(path)
        with open(str(path).replace(".joblib", "_metadata.json"), "r") as f:
            meta = json.load(f)
        models["XGBoost"] = {"model": model, "meta": meta, "type": "classifier"}
    except FileNotFoundError:
        pass
    
    # LightGBM
    try:
        path = MODEL_DIR / "lgbm_trust_classifier_latest.joblib"
        model = joblib.load(path)
        with open(str(path).replace(".joblib", "_metadata.json"), "r") as f:
            meta = json.load(f)
        models["LightGBM"] = {"model": model, "meta": meta, "type": "classifier"}
    except FileNotFoundError:
        pass
    
    # Isolation Forest
    try:
        path = MODEL_DIR / "iforest_trust_anomaly_latest.joblib"
        model = joblib.load(path)
        scaler = joblib.load(str(path).replace(".joblib", "_scaler.joblib"))
        with open(str(path).replace(".joblib", "_metadata.json"), "r") as f:
            meta = json.load(f)
        models["IsolationForest"] = {
            "model": model, "scaler": scaler, "meta": meta, "type": "anomaly"
        }
    except FileNotFoundError:
        pass
    
    # Ensemble
    try:
        meta_path = MODEL_DIR / "ensemble_trust_score_latest_meta.joblib"
        meta_model = joblib.load(meta_path)
        try:
            calibrator = joblib.load(str(meta_path).replace("_meta.", "_calibrator."))
        except FileNotFoundError:
            calibrator = None
        with open(str(meta_path).replace(".joblib", "data.json").replace("_meta", "_meta"), "r") as f:
            meta = json.load(f)
        models["Ensemble"] = {
            "model": meta_model, "calibrator": calibrator, "meta": meta, "type": "ensemble"
        }
    except FileNotFoundError:
        pass
    
    return models


# =============================================================================
# EVALUATION METRICS
# =============================================================================

def evaluate_classifier(
    model,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    model_name: str
) -> dict:
    """Evaluate a classifier model."""
    
    y_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= 0.5).astype(int)
    
    metrics = {
        "model": model_name,
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred),
        "recall": recall_score(y_test, y_pred),
        "f1_score": f1_score(y_test, y_pred),
        "roc_auc": roc_auc_score(y_test, y_proba),
        "pr_auc": average_precision_score(y_test, y_proba),
        "brier_score": brier_score_loss(y_test, y_proba),
    }
    
    # ROC curve data
    fpr, tpr, _ = roc_curve(y_test, y_proba)
    metrics["roc_curve"] = {"fpr": fpr.tolist(), "tpr": tpr.tolist()}
    
    # PR curve data
    precision, recall, _ = precision_recall_curve(y_test, y_proba)
    metrics["pr_curve"] = {"precision": precision.tolist(), "recall": recall.tolist()}
    
    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    metrics["confusion_matrix"] = cm.tolist()
    
    return metrics


def evaluate_anomaly_detector(
    model,
    scaler,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    feature_names: list,
    model_name: str
) -> dict:
    """Evaluate Isolation Forest."""
    
    X_subset = X_test[[f for f in feature_names if f in X_test.columns]].copy()
    X_subset = X_subset.replace([np.inf, -np.inf], np.nan).fillna(X_subset.median())
    X_scaled = scaler.transform(X_subset)
    
    # Get scores
    raw_scores = -model.decision_function(X_scaled)
    min_s, max_s = raw_scores.min(), raw_scores.max()
    if max_s > min_s:
        scores = (raw_scores - min_s) / (max_s - min_s)
    else:
        scores = np.zeros_like(raw_scores)
    
    # Get predictions
    y_pred_raw = model.predict(X_scaled)
    y_pred = (y_pred_raw == -1).astype(int)
    
    metrics = {
        "model": model_name,
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, zero_division=0),
        "recall": recall_score(y_test, y_pred, zero_division=0),
        "f1_score": f1_score(y_test, y_pred, zero_division=0),
        "roc_auc": roc_auc_score(y_test, scores),
    }
    
    cm = confusion_matrix(y_test, y_pred)
    metrics["confusion_matrix"] = cm.tolist()
    
    return metrics


# =============================================================================
# SHAP ANALYSIS
# =============================================================================

def compute_shap_values(
    model,
    X_test: pd.DataFrame,
    model_name: str,
    max_samples: int = 1000
) -> dict:
    """Compute SHAP values for model interpretability."""
    try:
        import shap
    except ImportError:
        print("⚠️ SHAP not installed. Run: pip install shap")
        return None
    
    print(f"\n🔍 Computing SHAP values for {model_name}...")
    
    # Sample if too large
    if len(X_test) > max_samples:
        X_sample = X_test.sample(n=max_samples, random_state=42)
    else:
        X_sample = X_test
    
    # Create explainer based on model type
    if model_name in ["XGBoost", "LightGBM"]:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample)
        
        # For binary classification, take class 1
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
    else:
        # Generic explainer
        explainer = shap.KernelExplainer(model.predict_proba, X_sample.iloc[:100])
        shap_values = explainer.shap_values(X_sample.iloc[:100])
    
    # Feature importance from SHAP
    feature_importance = np.abs(shap_values).mean(axis=0)
    importance_df = pd.DataFrame({
        "feature": X_sample.columns,
        "importance": feature_importance
    }).sort_values("importance", ascending=False)
    
    return {
        "shap_values": shap_values,
        "feature_importance": importance_df,
        "base_value": explainer.expected_value if hasattr(explainer, 'expected_value') else None
    }


# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_evaluation_report(all_metrics: list, output_dir: Path):
    """Generate comprehensive evaluation report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Summary DataFrame
    summary_cols = ["model", "accuracy", "precision", "recall", "f1_score", "roc_auc", "pr_auc"]
    summary_data = []
    
    for m in all_metrics:
        row = {k: m.get(k, None) for k in summary_cols}
        summary_data.append(row)
    
    summary_df = pd.DataFrame(summary_data)
    
    # Save summary
    summary_path = output_dir / "model_comparison.csv"
    summary_df.to_csv(summary_path, index=False)
    print(f"\n📊 Summary saved: {summary_path}")
    
    # Save full metrics as JSON
    metrics_path = output_dir / "full_metrics.json"
    
    # Convert numpy arrays to lists for JSON serialization
    metrics_json = []
    for m in all_metrics:
        m_clean = {}
        for k, v in m.items():
            if isinstance(v, np.ndarray):
                m_clean[k] = v.tolist()
            elif isinstance(v, (np.float64, np.float32)):
                m_clean[k] = float(v)
            elif isinstance(v, (np.int64, np.int32)):
                m_clean[k] = int(v)
            else:
                m_clean[k] = v
        metrics_json.append(m_clean)
    
    with open(metrics_path, "w") as f:
        json.dump(metrics_json, f, indent=2)
    print(f"📋 Full metrics saved: {metrics_path}")
    
    return summary_df


def print_comparison_table(all_metrics: list):
    """Print comparison table."""
    print("\n" + "="*80)
    print("📊 MODEL COMPARISON")
    print("="*80)
    
    # Header
    print(f"{'Model':<20} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} "
          f"{'F1':>10} {'ROC-AUC':>10}")
    print("-"*80)
    
    for m in all_metrics:
        print(f"{m['model']:<20} "
              f"{m.get('accuracy', 0):>10.4f} "
              f"{m.get('precision', 0):>10.4f} "
              f"{m.get('recall', 0):>10.4f} "
              f"{m.get('f1_score', 0):>10.4f} "
              f"{m.get('roc_auc', 0):>10.4f}")
    
    # Find best model
    best_idx = max(range(len(all_metrics)), key=lambda i: all_metrics[i].get('roc_auc', 0))
    print("-"*80)
    print(f"🏆 Best Model: {all_metrics[best_idx]['model']} "
          f"(ROC-AUC = {all_metrics[best_idx]['roc_auc']:.4f})")


def print_feature_importance(models: dict, X_test: pd.DataFrame, top_k: int = 10):
    """Print feature importance for tree-based models."""
    print("\n" + "="*80)
    print(f"🎯 FEATURE IMPORTANCE (Top {top_k})")
    print("="*80)
    
    for name, data in models.items():
        if name in ["XGBoost", "LightGBM"]:
            model = data["model"]
            importance = model.feature_importances_
            
            imp_df = pd.DataFrame({
                "feature": X_test.columns,
                "importance": importance
            }).sort_values("importance", ascending=False)
            
            print(f"\n📊 {name}:")
            for i, row in imp_df.head(top_k).iterrows():
                bar = "█" * int(row["importance"] / imp_df["importance"].max() * 20)
                print(f"   {row['feature']:<35} {row['importance']:.4f} {bar}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Evaluate Trust Score Models")
    parser.add_argument("--model", type=str, default=None, 
                        help="Evaluate specific model (xgboost, lightgbm, iforest, ensemble)")
    parser.add_argument("--shap", action="store_true", help="Compute SHAP values")
    parser.add_argument("--save-report", action="store_true", help="Save evaluation report")
    args = parser.parse_args()
    
    print("="*80)
    print("📊 TRUST SCORE MODEL EVALUATION")
    print("="*80)
    print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load data
    X_train, X_test, y_train, y_test = load_training_data(test_size=0.2)
    print(f"\n📋 Test set: {len(X_test):,} samples")
    print(f"   Label distribution: {y_test.value_counts().to_dict()}")
    
    # Load models
    models = load_all_models()
    print(f"\n📦 Loaded {len(models)} models: {list(models.keys())}")
    
    # Evaluate each model
    all_metrics = []
    
    for name, data in models.items():
        if args.model and args.model.lower() not in name.lower():
            continue
        
        print(f"\n{'='*60}")
        print(f"📊 Evaluating {name}")
        print("="*60)
        
        if data["type"] == "classifier":
            metrics = evaluate_classifier(data["model"], X_test, y_test, name)
        elif data["type"] == "anomaly":
            metrics = evaluate_anomaly_detector(
                data["model"], data["scaler"], X_test, y_test,
                data["meta"]["feature_names"], name
            )
        else:
            continue
        
        all_metrics.append(metrics)
        
        # Print individual results
        print(f"\n📈 Metrics:")
        for k in ["accuracy", "precision", "recall", "f1_score", "roc_auc"]:
            if k in metrics:
                status = "✅" if metrics[k] >= 0.8 else "⚠️" if metrics[k] >= 0.7 else "❌"
                print(f"   {status} {k}: {metrics[k]:.4f}")
        
        # Confusion matrix
        if "confusion_matrix" in metrics:
            cm = metrics["confusion_matrix"]
            print(f"\n📋 Confusion Matrix:")
            print(f"   TN={cm[0][0]:,}  FP={cm[0][1]:,}")
            print(f"   FN={cm[1][0]:,}  TP={cm[1][1]:,}")
    
    # Print comparison
    if len(all_metrics) > 1:
        print_comparison_table(all_metrics)
    
    # Feature importance
    print_feature_importance(models, X_test)
    
    # SHAP analysis
    if args.shap:
        for name, data in models.items():
            if data["type"] == "classifier" and name in ["XGBoost", "LightGBM"]:
                shap_result = compute_shap_values(data["model"], X_test, name)
                if shap_result:
                    print(f"\n📊 SHAP Feature Importance ({name}):")
                    for _, row in shap_result["feature_importance"].head(10).iterrows():
                        print(f"   {row['feature']:<35} {row['importance']:.4f}")
    
    # Save report
    if args.save_report:
        summary_df = generate_evaluation_report(all_metrics, REPORT_DIR)
        print(f"\n📋 Report saved to: {REPORT_DIR}")
    
    print("\n" + "="*80)
    print("✅ EVALUATION COMPLETE!")
    print("="*80)
    
    return all_metrics


if __name__ == "__main__":
    main()
