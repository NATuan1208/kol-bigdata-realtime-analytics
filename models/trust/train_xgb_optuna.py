"""
XGBoost Training with Optuna Hyperparameter Tuning
===================================================
Bayesian optimization for finding optimal hyperparameters.

Usage:
    docker exec -it kol-trainer python -m models.trust.train_xgb_optuna
"""

import os
import json
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
import optuna
from optuna.samplers import TPESampler
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import (
    roc_auc_score, f1_score, accuracy_score, 
    precision_score, recall_score, classification_report
)
from xgboost import XGBClassifier

from models.trust.data_loader import load_training_data, FEATURE_COLUMNS

warnings.filterwarnings('ignore')

# ============================================================================
# CONFIGURATION
# ============================================================================
ARTIFACTS_DIR = Path("models/artifacts/trust")
REPORTS_DIR = Path("models/reports")
OPTUNA_DIR = Path("models/artifacts/optuna")

N_TRIALS = 50  # Number of Optuna trials
CV_FOLDS = 5   # Cross-validation folds
RANDOM_STATE = 42

# ============================================================================
# OPTUNA OBJECTIVE FUNCTION
# ============================================================================
def create_objective(X_train, y_train):
    """Create Optuna objective function for XGBoost."""
    
    def objective(trial):
        # Hyperparameter search space
        params = {
            'n_estimators': trial.suggest_int('n_estimators', 100, 1000),
            'max_depth': trial.suggest_int('max_depth', 3, 12),
            'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
            'min_child_weight': trial.suggest_int('min_child_weight', 1, 10),
            'subsample': trial.suggest_float('subsample', 0.5, 1.0),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 10.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 10.0, log=True),
            'gamma': trial.suggest_float('gamma', 1e-8, 5.0, log=True),
            'scale_pos_weight': trial.suggest_float('scale_pos_weight', 0.5, 3.0),
            
            # Fixed params
            'objective': 'binary:logistic',
            'eval_metric': 'auc',
            'random_state': RANDOM_STATE,
            'n_jobs': -1,
            'verbosity': 0,
        }
        
        # Create model
        model = XGBClassifier(**params)
        
        # 5-Fold Stratified Cross Validation
        cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
        scores = cross_val_score(
            model, X_train, y_train, 
            cv=cv, 
            scoring='roc_auc',
            n_jobs=-1
        )
        
        return scores.mean()
    
    return objective


# ============================================================================
# MAIN TRAINING FUNCTION
# ============================================================================
def train_xgb_with_optuna():
    """Train XGBoost with Optuna hyperparameter tuning."""
    
    print("=" * 70)
    print("🎯 XGBoost Training with Optuna Hyperparameter Tuning")
    print("=" * 70)
    
    start_time = time.time()
    
    # Create directories
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OPTUNA_DIR.mkdir(parents=True, exist_ok=True)
    
    # -------------------------------------------------------------------------
    # Step 1: Load Data
    # -------------------------------------------------------------------------
    print("\n📊 Step 1: Loading training data...")
    X_train, X_test, y_train, y_test = load_training_data()
    
    print(f"   Training set: {X_train.shape[0]:,} samples")
    print(f"   Test set: {X_test.shape[0]:,} samples")
    print(f"   Features: {X_train.shape[1]}")
    
    # -------------------------------------------------------------------------
    # Step 2: Optuna Hyperparameter Search
    # -------------------------------------------------------------------------
    print(f"\n🔍 Step 2: Optuna Hyperparameter Search ({N_TRIALS} trials)...")
    print(f"   Cross-validation: {CV_FOLDS}-fold Stratified")
    print(f"   Optimization metric: ROC-AUC")
    print("-" * 70)
    
    # Create Optuna study
    sampler = TPESampler(seed=RANDOM_STATE)
    study = optuna.create_study(
        direction='maximize',
        sampler=sampler,
        study_name='xgboost_trust_score'
    )
    
    # Optimize
    objective = create_objective(X_train, y_train)
    
    study.optimize(
        objective, 
        n_trials=N_TRIALS,
        show_progress_bar=True,
        n_jobs=1  # Sequential for stability
    )
    
    # -------------------------------------------------------------------------
    # Step 3: Results Summary
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("📈 OPTUNA RESULTS")
    print("=" * 70)
    
    print(f"\n🏆 Best Trial: #{study.best_trial.number}")
    print(f"   Best CV ROC-AUC: {study.best_value:.4f}")
    
    print(f"\n📋 Best Hyperparameters:")
    best_params = study.best_params
    for param, value in best_params.items():
        if isinstance(value, float):
            print(f"   {param}: {value:.6f}")
        else:
            print(f"   {param}: {value}")
    
    # -------------------------------------------------------------------------
    # Step 4: Train Final Model with Best Params
    # -------------------------------------------------------------------------
    print(f"\n🚀 Step 4: Training final model with best params...")
    
    final_params = {
        **best_params,
        'objective': 'binary:logistic',
        'eval_metric': 'auc',
        'random_state': RANDOM_STATE,
        'n_jobs': -1,
        'verbosity': 0,
    }
    
    final_model = XGBClassifier(**final_params)
    final_model.fit(X_train, y_train)
    
    # -------------------------------------------------------------------------
    # Step 5: Evaluate on Test Set
    # -------------------------------------------------------------------------
    print(f"\n📊 Step 5: Evaluating on test set...")
    
    y_pred = final_model.predict(X_test)
    y_proba = final_model.predict_proba(X_test)[:, 1]
    
    metrics = {
        'model': 'XGBoost-Optuna',
        'roc_auc': roc_auc_score(y_test, y_proba),
        'f1': f1_score(y_test, y_pred),
        'accuracy': accuracy_score(y_test, y_pred),
        'precision': precision_score(y_test, y_pred),
        'recall': recall_score(y_test, y_pred),
        'n_trials': N_TRIALS,
        'cv_folds': CV_FOLDS,
        'best_cv_score': study.best_value,
        'training_time_seconds': time.time() - start_time,
    }
    
    print("\n" + "=" * 70)
    print("🎯 FINAL MODEL PERFORMANCE (Test Set)")
    print("=" * 70)
    print(f"   ROC-AUC:   {metrics['roc_auc']:.4f}")
    print(f"   F1-Score:  {metrics['f1']:.4f}")
    print(f"   Accuracy:  {metrics['accuracy']:.4f}")
    print(f"   Precision: {metrics['precision']:.4f}")
    print(f"   Recall:    {metrics['recall']:.4f}")
    
    # -------------------------------------------------------------------------
    # Step 6: Save Artifacts
    # -------------------------------------------------------------------------
    print(f"\n💾 Step 6: Saving artifacts...")
    
    # Save model
    model_path = ARTIFACTS_DIR / "xgb_optuna_model.pkl"
    joblib.dump(final_model, model_path)
    print(f"   ✓ Model saved: {model_path}")
    
    # Save best params
    params_path = OPTUNA_DIR / "xgb_best_params.json"
    with open(params_path, 'w') as f:
        json.dump(best_params, f, indent=2)
    print(f"   ✓ Best params saved: {params_path}")
    
    # Save metrics
    metrics_path = REPORTS_DIR / "xgb_optuna_metrics.json"
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"   ✓ Metrics saved: {metrics_path}")
    
    # Save study (for visualization)
    study_path = OPTUNA_DIR / "xgb_optuna_study.pkl"
    joblib.dump(study, study_path)
    print(f"   ✓ Study saved: {study_path}")
    
    # Save trials history
    trials_df = study.trials_dataframe()
    trials_path = OPTUNA_DIR / "xgb_trials_history.csv"
    trials_df.to_csv(trials_path, index=False)
    print(f"   ✓ Trials history saved: {trials_path}")
    
    # -------------------------------------------------------------------------
    # Step 7: Feature Importance
    # -------------------------------------------------------------------------
    print(f"\n📊 Top 10 Feature Importances:")
    importance_df = pd.DataFrame({
        'feature': FEATURE_COLUMNS,
        'importance': final_model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    for i, row in importance_df.head(10).iterrows():
        print(f"   {row['feature']}: {row['importance']:.4f}")
    
    importance_path = REPORTS_DIR / "xgb_optuna_feature_importance.csv"
    importance_df.to_csv(importance_path, index=False)
    
    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("✅ XGBoost Optuna Training Complete!")
    print("=" * 70)
    print(f"   Total time: {total_time/60:.1f} minutes")
    print(f"   Best CV ROC-AUC: {study.best_value:.4f}")
    print(f"   Test ROC-AUC: {metrics['roc_auc']:.4f}")
    print(f"   Improvement potential: Tuned params vs default")
    
    return final_model, study, metrics


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    model, study, metrics = train_xgb_with_optuna()
