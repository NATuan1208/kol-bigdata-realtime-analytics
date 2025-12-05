#!/usr/bin/env python3
"""
SuccessScore Model Training - Hybrid Approach
Train LightGBM + Rule-based comparison
"""

import json
import warnings
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, classification_report
import joblib

try:
    import lightgbm as lgb
    LGBM_AVAILABLE = True
except ImportError:
    LGBM_AVAILABLE = False

try:
    import mlflow
    import mlflow.sklearn
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "kafka_export"
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts" / "success"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

MLFLOW_TRACKING_URI = "http://localhost:5000"
EXPERIMENT_NAME = "kol-success-score"


def load_products_data():
    print("Loading products data...")
    products_files = list(DATA_DIR.glob("kol_products_raw_*.json"))
    if not products_files:
        raise FileNotFoundError(f"No products files in {DATA_DIR}")
    
    all_products = []
    for fp in products_files:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        for record in data:
            product = record.get("data", record)
            all_products.append(product)
    
    df = pd.DataFrame(all_products)
    print(f"  Loaded {len(df)} products")
    return df


def create_success_labels(df):
    print("Creating success labels...")
    df = df.copy()
    df["sold_count"] = pd.to_numeric(df["sold_count"], errors="coerce").fillna(0)
    
    p25 = df["sold_count"].quantile(0.25)
    p75 = df["sold_count"].quantile(0.75)
    print(f"  Thresholds: P25={p25:.0f}, P75={p75:.0f}")
    
    df["success_label"] = df["sold_count"].apply(
        lambda x: 0 if x <= p25 else (2 if x > p75 else 1)
    )
    
    counts = df["success_label"].value_counts().sort_index()
    for label, count in counts.items():
        name = {0: "Low", 1: "Medium", 2: "High"}[label]
        print(f"    {name}: {count} ({count/len(df)*100:.1f}%)")
    
    return df


def engineer_features(df):
    print("Engineering features...")
    df = df.copy()
    
    numeric_cols = ["video_views", "video_likes", "video_comments", "video_shares",
                    "engagement_total", "engagement_rate", "est_clicks", "est_ctr"]
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    
    df["likes_per_view"] = np.where(df["video_views"] > 0, df["video_likes"] / df["video_views"], 0)
    df["comments_per_view"] = np.where(df["video_views"] > 0, df["video_comments"] / df["video_views"], 0)
    df["shares_per_view"] = np.where(df["video_views"] > 0, df["video_shares"] / df["video_views"], 0)
    df["log_views"] = np.log1p(df["video_views"])
    df["log_engagement"] = np.log1p(df["engagement_total"])
    
    feature_cols = ["video_views", "video_likes", "video_comments", "video_shares",
                    "engagement_total", "engagement_rate", "est_clicks", "est_ctr",
                    "likes_per_view", "comments_per_view", "shares_per_view",
                    "log_views", "log_engagement"]
    
    available = [f for f in feature_cols if f in df.columns]
    print(f"  Created {len(available)} features")
    return df, available


def train_lightgbm(X_train, y_train, X_val, y_val):
    print("Training LightGBM...")
    
    model = lgb.LGBMClassifier(
        objective="multiclass",
        num_class=3,
        num_leaves=15,
        max_depth=5,
        learning_rate=0.05,
        n_estimators=200,
        min_child_samples=10,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=0.1,
        random_state=42,
        verbose=-1
    )
    
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)],
              callbacks=[lgb.early_stopping(50, verbose=False)])
    
    print(f"  Best iteration: {model.best_iteration_}")
    return model


def evaluate_model(model, X_test, y_test):
    print("\n" + "="*50)
    print("MODEL EVALUATION")
    print("="*50)
    
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)
    
    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision_macro": precision_score(y_test, y_pred, average="macro"),
        "recall_macro": recall_score(y_test, y_pred, average="macro"),
        "f1_macro": f1_score(y_test, y_pred, average="macro"),
    }
    
    try:
        metrics["roc_auc_ovr"] = roc_auc_score(y_test, y_proba, multi_class="ovr")
    except:
        metrics["roc_auc_ovr"] = None
    
    print(f"  Accuracy:  {metrics['accuracy']:.4f}")
    print(f"  Precision: {metrics['precision_macro']:.4f}")
    print(f"  Recall:    {metrics['recall_macro']:.4f}")
    print(f"  F1-Score:  {metrics['f1_macro']:.4f}")
    if metrics["roc_auc_ovr"]:
        print(f"  ROC-AUC:   {metrics['roc_auc_ovr']:.4f}")
    
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["Low", "Medium", "High"]))
    
    return metrics, y_pred


def rule_based_score(df):
    print("\nCalculating Rule-based scores...")
    df = df.copy()
    
    for col in ["video_views", "engagement_rate", "est_ctr", "engagement_total"]:
        if col in df.columns:
            max_val = df[col].max()
            df[f"{col}_norm"] = df[col] / max_val if max_val > 0 else 0
    
    df["rule_score"] = (
        0.25 * df.get("video_views_norm", 0) +
        0.30 * df.get("engagement_rate_norm", 0) +
        0.25 * df.get("est_ctr_norm", 0) +
        0.20 * df.get("engagement_total_norm", 0)
    ) * 100
    
    df["rule_label"] = pd.cut(df["rule_score"], bins=[-np.inf, 33, 66, np.inf], labels=[0, 1, 2]).astype(int)
    
    return df


def compare_approaches(y_true, ml_pred, rule_pred):
    print("\n" + "="*50)
    print("ML vs RULE-BASED COMPARISON")
    print("="*50)
    
    ml_f1 = f1_score(y_true, ml_pred, average="macro")
    rule_f1 = f1_score(y_true, rule_pred, average="macro")
    ml_acc = accuracy_score(y_true, ml_pred)
    rule_acc = accuracy_score(y_true, rule_pred)
    
    print(f"  {'Metric':<12} {'ML Model':<12} {'Rule-Based':<12} {'Winner'}")
    print("-"*50)
    print(f"  {'Accuracy':<12} {ml_acc:<12.4f} {rule_acc:<12.4f} {'ML' if ml_acc > rule_acc else 'Rule'}")
    print(f"  {'F1-Score':<12} {ml_f1:<12.4f} {rule_f1:<12.4f} {'ML' if ml_f1 > rule_f1 else 'Rule'}")
    
    if ml_f1 > rule_f1:
        print("\n  RECOMMENDATION: Use ML Model")
    else:
        print("\n  RECOMMENDATION: Use Rule-Based (simpler)")
    
    return {"ml_f1": ml_f1, "rule_f1": rule_f1, "ml_acc": ml_acc, "rule_acc": rule_acc}


def log_to_mlflow(model, metrics, feature_names):
    if not MLFLOW_AVAILABLE:
        print("MLflow not available")
        return
    
    print("\nLogging to MLflow...")
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(EXPERIMENT_NAME)
        
        with mlflow.start_run(run_name=f"success_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
            mlflow.log_params({
                "model_type": "LightGBM",
                "n_features": len(feature_names),
                "num_leaves": 15,
                "max_depth": 5
            })
            
            for name, value in metrics.items():
                if value is not None:
                    mlflow.log_metric(name, value)
            
            mlflow.sklearn.log_model(model, "model")
            print(f"  Logged to experiment: {EXPERIMENT_NAME}")
    except Exception as e:
        print(f"  MLflow error: {e}")


def main():
    print("="*60)
    print("  SUCCESS SCORE TRAINING - Hybrid Approach")
    print("="*60 + "\n")
    
    if not LGBM_AVAILABLE:
        raise RuntimeError("LightGBM required: pip install lightgbm")
    
    # Load and prepare data
    df = load_products_data()
    df = create_success_labels(df)
    df, feature_cols = engineer_features(df)
    
    X = df[feature_cols].values
    y = df["success_label"].values
    X = np.nan_to_num(X, nan=0.0)
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    X_train, X_val, y_train, y_val = train_test_split(X_train, y_train, test_size=0.2, random_state=42, stratify=y_train)
    
    print(f"\nData split: Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}")
    
    # Scale
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_val_s = scaler.transform(X_val)
    X_test_s = scaler.transform(X_test)
    
    # Train ML
    model = train_lightgbm(X_train_s, y_train, X_val_s, y_val)
    metrics, ml_pred = evaluate_model(model, X_test_s, y_test)
    
    # Cross-validation
    print("\n5-Fold Cross Validation...")
    cv_scores = cross_val_score(model, X_train_s, y_train, cv=5, scoring="f1_macro")
    print(f"  CV F1: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")
    metrics["cv_f1_mean"] = cv_scores.mean()
    metrics["cv_f1_std"] = cv_scores.std()
    
    # Rule-based comparison
    test_indices = df.index[-len(y_test):]
    df_with_rules = rule_based_score(df)
    rule_pred = df_with_rules.loc[test_indices, "rule_label"].values
    
    comparison = compare_approaches(y_test, ml_pred, rule_pred)
    
    # Feature importance
    print("\nFeature Importance (Top 10):")
    importance = sorted(zip(feature_cols, model.feature_importances_), key=lambda x: x[1], reverse=True)
    for feat, imp in importance[:10]:
        print(f"  {feat:<25} {imp:.4f}")
    
    # Save artifacts
    joblib.dump(model, ARTIFACTS_DIR / "success_lgbm_model.pkl")
    joblib.dump(scaler, ARTIFACTS_DIR / "success_scaler.pkl")
    with open(ARTIFACTS_DIR / "feature_names.json", "w") as f:
        json.dump(feature_cols, f)
    
    print(f"\nModel saved to {ARTIFACTS_DIR}")
    
    # Log to MLflow
    log_to_mlflow(model, metrics, feature_cols)
    
    print("\n" + "="*60)
    print("  TRAINING COMPLETE!")
    print("="*60)


if __name__ == "__main__":
    main()
