#!/usr/bin/env python3
"""
SuccessScore Model Training V2 - Improved Version
Improvements:
1. Add price features
2. Binary classification (High vs Not-High) for better performance
3. Class weights to handle imbalance
4. Better feature engineering
5. Comparison: 3-class vs 2-class
"""

import json
import warnings
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import (accuracy_score, precision_score, recall_score, 
                            f1_score, roc_auc_score, classification_report,
                            confusion_matrix)
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
EXPERIMENT_NAME = "kol-success-score-v2"


def load_products_data():
    """Load all products data from kafka export."""
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


def analyze_sold_distribution(df):
    """Analyze sold_count distribution for label strategy."""
    print("\n" + "="*50)
    print("SOLD_COUNT DISTRIBUTION ANALYSIS")
    print("="*50)
    
    sold = df["sold_count"].fillna(0)
    
    print(f"\nBasic Stats:")
    print(f"  Count: {len(sold)}")
    print(f"  Mean:  {sold.mean():.2f}")
    print(f"  Std:   {sold.std():.2f}")
    print(f"  Min:   {sold.min()}")
    print(f"  Max:   {sold.max()}")
    
    print(f"\nPercentiles:")
    for p in [25, 50, 75, 90, 95]:
        print(f"  P{p}: {sold.quantile(p/100):.0f}")
    
    # Zero vs Non-zero
    zero_count = (sold == 0).sum()
    print(f"\nZero sold: {zero_count} ({zero_count/len(sold)*100:.1f}%)")
    
    return sold


def create_labels_v2(df, strategy="binary"):
    """
    Create labels with different strategies.
    
    Strategies:
    - binary: High (top 25%) vs Not-High
    - ternary: Low/Medium/High (original)
    - quartile: 4 classes
    """
    print(f"\nCreating labels with strategy: {strategy}")
    df = df.copy()
    df["sold_count"] = pd.to_numeric(df["sold_count"], errors="coerce").fillna(0)
    
    if strategy == "binary":
        # Top 25% = High (1), Rest = Not-High (0)
        threshold = df["sold_count"].quantile(0.75)
        df["success_label"] = (df["sold_count"] > threshold).astype(int)
        
        print(f"  Threshold (P75): {threshold:.0f}")
        counts = df["success_label"].value_counts().sort_index()
        print(f"  Not-High (0): {counts.get(0, 0)} ({counts.get(0, 0)/len(df)*100:.1f}%)")
        print(f"  High (1):     {counts.get(1, 0)} ({counts.get(1, 0)/len(df)*100:.1f}%)")
        
    elif strategy == "ternary":
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


def engineer_features_v2(df):
    """
    Enhanced feature engineering with price and more derived features.
    """
    print("\nEngineering features (V2)...")
    df = df.copy()
    
    # Core numeric columns
    numeric_cols = {
        "video_views": 0,
        "video_likes": 0,
        "video_comments": 0,
        "video_shares": 0,
        "engagement_total": 0,
        "engagement_rate": 0,
        "est_clicks": 0,
        "est_ctr": 0,
        "price": 0,  # NEW: Add price
        "sold_count": 0,
    }
    
    for col, default in numeric_cols.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)
        else:
            df[col] = default
    
    # === ENGAGEMENT RATIOS ===
    df["likes_per_view"] = np.where(
        df["video_views"] > 0, 
        df["video_likes"] / df["video_views"], 
        0
    )
    df["comments_per_view"] = np.where(
        df["video_views"] > 0, 
        df["video_comments"] / df["video_views"], 
        0
    )
    df["shares_per_view"] = np.where(
        df["video_views"] > 0, 
        df["video_shares"] / df["video_views"], 
        0
    )
    
    # === LOG TRANSFORMS (handle skewed distributions) ===
    df["log_views"] = np.log1p(df["video_views"])
    df["log_engagement"] = np.log1p(df["engagement_total"])
    df["log_clicks"] = np.log1p(df["est_clicks"])
    df["log_price"] = np.log1p(df["price"])  # NEW
    
    # === PRICE FEATURES (NEW) ===
    # Price tiers (binned)
    price_bins = [0, 50000, 200000, 500000, 1000000, float('inf')]
    price_labels = [0, 1, 2, 3, 4]  # cheap to expensive
    df["price_tier"] = pd.cut(df["price"], bins=price_bins, labels=price_labels).astype(float).fillna(0)
    
    # === INTERACTION FEATURES ===
    df["engagement_x_ctr"] = df["engagement_rate"] * df["est_ctr"]
    df["views_x_ctr"] = df["video_views"] * df["est_ctr"]
    
    # === VIRAL INDICATORS ===
    df["is_viral_views"] = (df["video_views"] > df["video_views"].quantile(0.9)).astype(int)
    df["is_high_engagement"] = (df["engagement_rate"] > df["engagement_rate"].quantile(0.75)).astype(int)
    
    # Define feature columns
    feature_cols = [
        # Core metrics
        "video_views", "video_likes", "video_comments", "video_shares",
        "engagement_total", "engagement_rate", "est_clicks", "est_ctr",
        # Ratios
        "likes_per_view", "comments_per_view", "shares_per_view",
        # Log transforms
        "log_views", "log_engagement", "log_clicks", "log_price",
        # Price features
        "price", "price_tier",
        # Interactions
        "engagement_x_ctr", "views_x_ctr",
        # Indicators
        "is_viral_views", "is_high_engagement",
    ]
    
    available = [f for f in feature_cols if f in df.columns]
    print(f"  Created {len(available)} features:")
    for f in available:
        print(f"    - {f}")
    
    return df, available


def train_lightgbm_v2(X_train, y_train, X_val, y_val, is_binary=True):
    """Train LightGBM with class weights for imbalance."""
    print("\nTraining LightGBM V2...")
    
    # Calculate class weights
    class_counts = np.bincount(y_train)
    total = len(y_train)
    class_weights = {i: total / (len(class_counts) * count) 
                     for i, count in enumerate(class_counts)}
    print(f"  Class weights: {class_weights}")
    
    if is_binary:
        # Binary classification
        scale_pos_weight = class_counts[0] / class_counts[1] if class_counts[1] > 0 else 1
        print(f"  Scale pos weight: {scale_pos_weight:.2f}")
        
        model = lgb.LGBMClassifier(
            objective="binary",
            num_leaves=15,  # Reduced for small data
            max_depth=4,    # Reduced
            learning_rate=0.1,  # Increased
            n_estimators=100,   # Reduced
            min_child_samples=5,  # Reduced for small data
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.5,   # Increased regularization
            reg_lambda=0.5,  # Increased regularization
            scale_pos_weight=scale_pos_weight,
            random_state=42,
            verbose=-1,
            force_col_wise=True
        )
    else:
        # Multi-class
        model = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=3,
            num_leaves=15,
            max_depth=4,
            learning_rate=0.1,
            n_estimators=100,
            min_child_samples=5,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.5,
            reg_lambda=0.5,
            class_weight="balanced",
            random_state=42,
            verbose=-1,
            force_col_wise=True
        )
    
    # Train without early stopping for small data
    model.fit(X_train, y_train)
    
    print(f"  Training complete, n_estimators: {model.n_estimators}")
    return model


def evaluate_model_v2(model, X_test, y_test, is_binary=True):
    """Comprehensive model evaluation."""
    print("\n" + "="*50)
    print("MODEL EVALUATION")
    print("="*50)
    
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)
    
    metrics = {
        "accuracy": accuracy_score(y_test, y_pred),
        "precision": precision_score(y_test, y_pred, average="binary" if is_binary else "macro"),
        "recall": recall_score(y_test, y_pred, average="binary" if is_binary else "macro"),
        "f1": f1_score(y_test, y_pred, average="binary" if is_binary else "macro"),
    }
    
    if is_binary:
        metrics["roc_auc"] = roc_auc_score(y_test, y_proba[:, 1])
    else:
        try:
            metrics["roc_auc"] = roc_auc_score(y_test, y_proba, multi_class="ovr")
        except:
            metrics["roc_auc"] = None
    
    print(f"\nMetrics:")
    print(f"  Accuracy:  {metrics['accuracy']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  Recall:    {metrics['recall']:.4f}")
    print(f"  F1-Score:  {metrics['f1']:.4f}")
    if metrics.get("roc_auc"):
        print(f"  ROC-AUC:   {metrics['roc_auc']:.4f}")
    
    # Confusion Matrix
    print("\nConfusion Matrix:")
    cm = confusion_matrix(y_test, y_pred)
    print(cm)
    
    # Classification Report
    if is_binary:
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, target_names=["Not-High", "High"]))
    else:
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred, target_names=["Low", "Medium", "High"]))
    
    return metrics, y_pred


def rule_based_score_v2(df):
    """Improved rule-based scoring."""
    print("\nCalculating Rule-based V2 scores...")
    df = df.copy()
    
    # Normalize features to 0-1
    for col in ["video_views", "engagement_rate", "est_ctr", "engagement_total"]:
        if col in df.columns:
            max_val = df[col].max()
            df[f"{col}_norm"] = df[col] / max_val if max_val > 0 else 0
    
    # Weighted score
    df["rule_score"] = (
        0.25 * df.get("video_views_norm", 0) +
        0.30 * df.get("engagement_rate_norm", 0) +
        0.25 * df.get("est_ctr_norm", 0) +
        0.20 * df.get("engagement_total_norm", 0)
    ) * 100
    
    # For binary: top 25% = High
    threshold = df["rule_score"].quantile(0.75)
    df["rule_label_binary"] = (df["rule_score"] > threshold).astype(int)
    
    # For ternary
    df["rule_label_ternary"] = pd.cut(
        df["rule_score"], 
        bins=[-np.inf, 33, 66, np.inf], 
        labels=[0, 1, 2]
    ).astype(int)
    
    return df


def compare_strategies(results_binary, results_ternary):
    """Compare binary vs ternary classification strategies."""
    print("\n" + "="*60)
    print("STRATEGY COMPARISON: Binary vs Ternary")
    print("="*60)
    
    print(f"\n{'Metric':<15} {'Binary (2-class)':<20} {'Ternary (3-class)':<20}")
    print("-"*55)
    
    for metric in ["accuracy", "precision", "recall", "f1", "roc_auc"]:
        b_val = results_binary.get(metric, 0) or 0
        t_val = results_ternary.get(metric, 0) or 0
        winner = "★" if b_val > t_val else ""
        print(f"{metric:<15} {b_val:<20.4f} {t_val:<20.4f} {winner}")
    
    print("\n💡 INSIGHT:")
    if results_binary["f1"] > results_ternary["f1"]:
        improvement = (results_binary["f1"] - results_ternary["f1"]) / results_ternary["f1"] * 100
        print(f"   Binary classification improves F1 by {improvement:.1f}%")
        print("   Recommendation: Use BINARY for production")
    else:
        print("   Ternary still performs better")


def save_model_artifacts(model, scaler, feature_names, is_binary=True, metrics=None):
    """Save model and artifacts."""
    suffix = "_binary" if is_binary else "_ternary"
    
    joblib.dump(model, ARTIFACTS_DIR / f"success_lgbm_model{suffix}.pkl")
    joblib.dump(scaler, ARTIFACTS_DIR / f"success_scaler{suffix}.pkl")
    
    with open(ARTIFACTS_DIR / f"feature_names{suffix}.json", "w") as f:
        json.dump(feature_names, f, indent=2)
    
    if metrics:
        with open(ARTIFACTS_DIR / f"metrics{suffix}.json", "w") as f:
            json.dump({k: float(v) if v else None for k, v in metrics.items()}, f, indent=2)
    
    # Also save as default (overwrite old model)
    if is_binary:
        joblib.dump(model, ARTIFACTS_DIR / "success_lgbm_model.pkl")
        joblib.dump(scaler, ARTIFACTS_DIR / "success_scaler.pkl")
        with open(ARTIFACTS_DIR / "feature_names.json", "w") as f:
            json.dump(feature_names, f, indent=2)
    
    print(f"\n✓ Saved model artifacts to {ARTIFACTS_DIR}")


def log_to_mlflow(model, metrics, feature_names, is_binary=True):
    """Log experiment to MLflow."""
    if not MLFLOW_AVAILABLE:
        print("MLflow not available")
        return
    
    print("\nLogging to MLflow...")
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(EXPERIMENT_NAME)
        
        strategy = "binary" if is_binary else "ternary"
        with mlflow.start_run(run_name=f"success_v2_{strategy}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"):
            mlflow.log_params({
                "model_type": "LightGBM",
                "strategy": strategy,
                "n_features": len(feature_names),
                "num_leaves": 31,
                "max_depth": 6,
                "version": "v2"
            })
            
            for name, value in metrics.items():
                if value is not None:
                    mlflow.log_metric(name, value)
            
            mlflow.sklearn.log_model(model, "model")
            print(f"  ✓ Logged to experiment: {EXPERIMENT_NAME}")
    except Exception as e:
        print(f"  MLflow error: {e}")


def main():
    print("="*60)
    print("  SUCCESS SCORE TRAINING V2 - Improved")
    print("="*60 + "\n")
    
    if not LGBM_AVAILABLE:
        raise RuntimeError("LightGBM required: pip install lightgbm")
    
    # Load data
    df = load_products_data()
    
    # Analyze distribution
    analyze_sold_distribution(df)
    
    # Feature engineering
    df, feature_cols = engineer_features_v2(df)
    
    # ==========================================
    # EXPERIMENT 1: BINARY CLASSIFICATION
    # ==========================================
    print("\n" + "="*60)
    print("EXPERIMENT 1: Binary Classification (High vs Not-High)")
    print("="*60)
    
    df_binary = create_labels_v2(df.copy(), strategy="binary")
    
    X = df_binary[feature_cols].values
    y = df_binary["success_label"].values
    X = np.nan_to_num(X, nan=0.0)
    
    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train, test_size=0.2, random_state=42, stratify=y_train
    )
    
    print(f"\nData split: Train={len(X_train)}, Val={len(X_val)}, Test={len(X_test)}")
    
    # Scale
    scaler_binary = StandardScaler()
    X_train_s = scaler_binary.fit_transform(X_train)
    X_val_s = scaler_binary.transform(X_val)
    X_test_s = scaler_binary.transform(X_test)
    
    # Train
    model_binary = train_lightgbm_v2(X_train_s, y_train, X_val_s, y_val, is_binary=True)
    metrics_binary, pred_binary = evaluate_model_v2(model_binary, X_test_s, y_test, is_binary=True)
    
    # Cross-validation
    print("\n5-Fold Cross Validation (Binary)...")
    cv_scores = cross_val_score(model_binary, X_train_s, y_train, cv=5, scoring="f1")
    print(f"  CV F1: {cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})")
    metrics_binary["cv_f1_mean"] = cv_scores.mean()
    
    # Feature importance
    print("\nFeature Importance (Top 10):")
    importance = sorted(zip(feature_cols, model_binary.feature_importances_), 
                       key=lambda x: x[1], reverse=True)
    for feat, imp in importance[:10]:
        print(f"  {feat:<25} {imp:.4f}")
    
    # Save binary model
    save_model_artifacts(model_binary, scaler_binary, feature_cols, is_binary=True, metrics=metrics_binary)
    log_to_mlflow(model_binary, metrics_binary, feature_cols, is_binary=True)
    
    # ==========================================
    # EXPERIMENT 2: TERNARY CLASSIFICATION
    # ==========================================
    print("\n" + "="*60)
    print("EXPERIMENT 2: Ternary Classification (Low/Medium/High)")
    print("="*60)
    
    df_ternary = create_labels_v2(df.copy(), strategy="ternary")
    
    X_t = df_ternary[feature_cols].values
    y_ternary = df_ternary["success_label"].values
    X_t = np.nan_to_num(X_t, nan=0.0)
    
    # Fresh split for ternary
    X_train_t, X_test_t, y_train_t, y_test_t = train_test_split(
        X_t, y_ternary, test_size=0.2, random_state=42, stratify=y_ternary
    )
    X_train_t, X_val_t, y_train_t, y_val_t = train_test_split(
        X_train_t, y_train_t, test_size=0.2, random_state=42, stratify=y_train_t
    )
    
    # Scale (reuse)
    scaler_ternary = StandardScaler()
    X_train_s_t = scaler_ternary.fit_transform(X_train_t)
    X_val_s_t = scaler_ternary.transform(X_val_t)
    X_test_s_t = scaler_ternary.transform(X_test_t)
    
    # Train
    model_ternary = train_lightgbm_v2(X_train_s_t, y_train_t, X_val_s_t, y_val_t, is_binary=False)
    metrics_ternary, pred_ternary = evaluate_model_v2(model_ternary, X_test_s_t, y_test_t, is_binary=False)
    
    # Save ternary model  
    save_model_artifacts(model_ternary, scaler_ternary, feature_cols, is_binary=False, metrics=metrics_ternary)
    log_to_mlflow(model_ternary, metrics_ternary, feature_cols, is_binary=False)
    
    # ==========================================
    # COMPARE STRATEGIES
    # ==========================================
    compare_strategies(metrics_binary, metrics_ternary)
    
    # ==========================================
    # COMPARE ML vs RULE-BASED
    # ==========================================
    print("\n" + "="*60)
    print("ML vs RULE-BASED COMPARISON")
    print("="*60)
    
    df_rules = rule_based_score_v2(df_binary)
    test_indices = df_binary.index[-len(y_test):]
    
    rule_pred_binary = df_rules.loc[test_indices, "rule_label_binary"].values
    
    ml_f1 = f1_score(y_test, pred_binary)
    rule_f1 = f1_score(y_test, rule_pred_binary)
    ml_acc = accuracy_score(y_test, pred_binary)
    rule_acc = accuracy_score(y_test, rule_pred_binary)
    
    print(f"\n{'Metric':<12} {'ML Model':<12} {'Rule-Based':<12} {'Improvement'}")
    print("-"*50)
    print(f"{'Accuracy':<12} {ml_acc:<12.4f} {rule_acc:<12.4f} {(ml_acc-rule_acc)/rule_acc*100:+.1f}%")
    print(f"{'F1-Score':<12} {ml_f1:<12.4f} {rule_f1:<12.4f} {(ml_f1-rule_f1)/max(rule_f1,0.001)*100:+.1f}%")
    
    print("\n" + "="*60)
    print("  TRAINING V2 COMPLETE!")
    print("="*60)
    
    # Summary
    print("\n📊 SUMMARY:")
    print(f"  • Binary model: F1={metrics_binary['f1']:.4f}, ROC-AUC={metrics_binary['roc_auc']:.4f}")
    print(f"  • Ternary model: F1={metrics_ternary['f1']:.4f}")
    print(f"  • Best model saved to: {ARTIFACTS_DIR}")
    print(f"  • Features used: {len(feature_cols)}")
    
    return {
        "binary": metrics_binary,
        "ternary": metrics_ternary,
        "feature_cols": feature_cols
    }


if __name__ == "__main__":
    results = main()
