"""
LightGBM Training with Optuna Hyperparameter Tuning
====================================================
Production-grade Bayesian optimization for Trust Score prediction.

Key Features:
- TPE (Tree-structured Parzen Estimator) sampler
- Early stopping to prevent overfitting
- Comprehensive hyperparameter search space
- Pruning for faster optimization

Usage:
    docker exec kol-trainer python -m models.trust.train_lgbm_optuna
"""

import os
import sys
import json
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
import lightgbm as lgb
import optuna
from optuna.samplers import TPESampler

from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.metrics import roc_auc_score, f1_score, accuracy_score, precision_score, recall_score

from models.trust.data_loader import load_training_data, FEATURE_COLUMNS

# Suppress warnings
warnings.filterwarnings('ignore')
optuna.logging.set_verbosity(optuna.logging.ERROR)

# ============================================================================
# CONFIGURATION  
# ============================================================================
ARTIFACTS_DIR = Path("models/artifacts/trust")
REPORTS_DIR = Path("models/reports")
OPTUNA_DIR = Path("models/artifacts/optuna")

N_TRIALS = 50           # Number of Optuna trials
N_CV_FOLDS = 5          # Cross-validation folds
EARLY_STOPPING = 30     # Early stopping rounds
NUM_BOOST_ROUND = 500   # Max boosting rounds
RANDOM_STATE = 42
NUM_THREADS = 4         # Threads per model


def main():
    """Main training function with Optuna."""
    
    print("=" * 70)
    print("🎯 LightGBM + Optuna Hyperparameter Tuning (Best Practice)")
    print("=" * 70)
    print(f"   Trials: {N_TRIALS}")
    print(f"   CV Folds: {N_CV_FOLDS}")
    print(f"   Max Rounds: {NUM_BOOST_ROUND}")
    print(f"   Early Stopping: {EARLY_STOPPING}")
    
    start_time = time.time()
    
    # Create directories
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    OPTUNA_DIR.mkdir(parents=True, exist_ok=True)
    
    # =========================================================================
    # Step 1: Load Data
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 Step 1: Loading Data")
    print("=" * 70)
    sys.stdout.flush()
    
    X_train_full, X_test, y_train_full, y_test = load_training_data()
    
    # Convert to numpy for LightGBM
    if hasattr(X_train_full, 'values'):
        X_train_np = X_train_full.values
        X_test_np = X_test.values
    else:
        X_train_np = X_train_full
        X_test_np = X_test
    
    if hasattr(y_train_full, 'values'):
        y_train_np = y_train_full.values
        y_test_np = y_test.values
    else:
        y_train_np = y_train_full
        y_test_np = y_test
    
    print(f"   Training set: {len(X_train_np):,} samples")
    print(f"   Test set: {len(X_test_np):,} samples")
    print(f"   Features: {X_train_np.shape[1]}")
    sys.stdout.flush()
    
    # =========================================================================
    # Step 2: Optuna Hyperparameter Search with Cross-Validation
    # =========================================================================
    print("\n" + "=" * 70)
    print(f"🔍 Step 2: Optuna Search ({N_TRIALS} trials × {N_CV_FOLDS}-fold CV)")
    print("=" * 70)
    sys.stdout.flush()
    
    # Track results
    trial_history = []
    
    def objective(trial):
        """Optuna objective with Stratified K-Fold CV."""
        
        # Hyperparameter search space (comprehensive)
        params = {
            'objective': 'binary',
            'metric': 'auc',
            'verbosity': -1,
            'boosting_type': 'gbdt',
            'num_threads': NUM_THREADS,
            'seed': RANDOM_STATE,
            
            # Tree structure
            'max_depth': trial.suggest_int('max_depth', 3, 12),
            'num_leaves': trial.suggest_int('num_leaves', 20, 256),
            'min_child_samples': trial.suggest_int('min_child_samples', 5, 100),
            
            # Learning
            'learning_rate': trial.suggest_float('learning_rate', 0.005, 0.3, log=True),
            
            # Regularization
            'reg_alpha': trial.suggest_float('reg_alpha', 1e-8, 10.0, log=True),
            'reg_lambda': trial.suggest_float('reg_lambda', 1e-8, 10.0, log=True),
            'min_gain_to_split': trial.suggest_float('min_gain_to_split', 0.0, 1.0),
            
            # Sampling
            'subsample': trial.suggest_float('subsample', 0.5, 1.0),
            'subsample_freq': trial.suggest_int('subsample_freq', 1, 10),
            'colsample_bytree': trial.suggest_float('colsample_bytree', 0.5, 1.0),
        }
        
        # Stratified K-Fold Cross-Validation
        skf = StratifiedKFold(n_splits=N_CV_FOLDS, shuffle=True, random_state=RANDOM_STATE)
        cv_scores = []
        
        for fold, (train_idx, val_idx) in enumerate(skf.split(X_train_np, y_train_np)):
            X_tr, X_val = X_train_np[train_idx], X_train_np[val_idx]
            y_tr, y_val = y_train_np[train_idx], y_train_np[val_idx]
            
            train_data = lgb.Dataset(X_tr, label=y_tr)
            val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
            
            model = lgb.train(
                params,
                train_data,
                num_boost_round=NUM_BOOST_ROUND,
                valid_sets=[val_data],
                callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)]
            )
            
            y_pred = model.predict(X_val)
            auc = roc_auc_score(y_val, y_pred)
            cv_scores.append(auc)
        
        mean_auc = np.mean(cv_scores)
        std_auc = np.std(cv_scores)
        
        # Log progress
        trial_num = trial.number + 1
        trial_history.append({
            'trial': trial_num,
            'mean_auc': mean_auc,
            'std_auc': std_auc,
            'params': params.copy()
        })
        
        if trial_num % 5 == 0 or trial_num <= 3:
            print(f"   Trial {trial_num:2d}/{N_TRIALS}: AUC = {mean_auc:.4f} ± {std_auc:.4f}")
            sys.stdout.flush()
        
        return mean_auc
    
    # Create and run study
    sampler = TPESampler(seed=RANDOM_STATE)
    study = optuna.create_study(
        direction='maximize',
        sampler=sampler,
        study_name='lightgbm_trust_score'
    )
    
    print("-" * 70)
    sys.stdout.flush()
    
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=False)
    
    # =========================================================================
    # Step 3: Results Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("📈 OPTUNA OPTIMIZATION RESULTS")
    print("=" * 70)
    
    print(f"\n🏆 Best Trial: #{study.best_trial.number + 1}")
    print(f"   Best CV ROC-AUC: {study.best_value:.4f}")
    
    print(f"\n📋 Best Hyperparameters:")
    best_params = study.best_params
    for param, value in sorted(best_params.items()):
        if isinstance(value, float):
            print(f"   {param}: {value:.6f}")
        else:
            print(f"   {param}: {value}")
    sys.stdout.flush()
    
    # =========================================================================
    # Step 4: Train Final Model on Full Training Data
    # =========================================================================
    print("\n" + "=" * 70)
    print("🚀 Step 4: Training Final Model")
    print("=" * 70)
    sys.stdout.flush()
    
    final_params = {
        'objective': 'binary',
        'metric': 'auc',
        'verbosity': -1,
        'boosting_type': 'gbdt',
        'num_threads': -1,  # All threads for final
        'seed': RANDOM_STATE,
        **best_params
    }
    
    # Create datasets
    full_train_data = lgb.Dataset(X_train_np, label=y_train_np)
    test_data = lgb.Dataset(X_test_np, label=y_test_np, reference=full_train_data)
    
    final_model = lgb.train(
        final_params,
        full_train_data,
        num_boost_round=NUM_BOOST_ROUND * 2,  # More rounds for final
        valid_sets=[test_data],
        callbacks=[lgb.early_stopping(EARLY_STOPPING * 2, verbose=False)]
    )
    
    print(f"   Final model: {final_model.num_trees()} trees")
    sys.stdout.flush()
    
    # =========================================================================
    # Step 5: Evaluate on Test Set
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 Step 5: Final Evaluation (Test Set)")
    print("=" * 70)
    
    y_proba = final_model.predict(X_test_np)
    y_pred = (y_proba > 0.5).astype(int)
    
    metrics = {
        'model': 'LightGBM-Optuna',
        'roc_auc': float(roc_auc_score(y_test_np, y_proba)),
        'f1': float(f1_score(y_test_np, y_pred)),
        'accuracy': float(accuracy_score(y_test_np, y_pred)),
        'precision': float(precision_score(y_test_np, y_pred)),
        'recall': float(recall_score(y_test_np, y_pred)),
        'n_trials': N_TRIALS,
        'n_cv_folds': N_CV_FOLDS,
        'best_cv_auc': float(study.best_value),
        'best_trial': study.best_trial.number + 1,
        'n_trees': final_model.num_trees(),
        'training_time_minutes': (time.time() - start_time) / 60,
        'best_params': best_params
    }
    
    print(f"\n   ROC-AUC:   {metrics['roc_auc']:.4f}")
    print(f"   F1-Score:  {metrics['f1']:.4f}")
    print(f"   Accuracy:  {metrics['accuracy']:.4f}")
    print(f"   Precision: {metrics['precision']:.4f}")
    print(f"   Recall:    {metrics['recall']:.4f}")
    sys.stdout.flush()
    
    # =========================================================================
    # Step 6: Save Artifacts
    # =========================================================================
    print("\n" + "=" * 70)
    print("💾 Step 6: Saving Artifacts")
    print("=" * 70)
    
    # Save model (native LightGBM format)
    model_path = ARTIFACTS_DIR / "lgbm_optuna_model.txt"
    final_model.save_model(str(model_path))
    print(f"   ✓ Model: {model_path}")
    
    # Also save as pkl for sklearn compatibility
    model_pkl_path = ARTIFACTS_DIR / "lgbm_optuna_model.pkl"
    joblib.dump(final_model, model_pkl_path)
    print(f"   ✓ Model (pkl): {model_pkl_path}")
    
    # Save metrics
    metrics_path = REPORTS_DIR / "lgbm_optuna_metrics.json"
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"   ✓ Metrics: {metrics_path}")
    
    # Save best params
    params_path = OPTUNA_DIR / "lgbm_best_params.json"
    with open(params_path, 'w') as f:
        json.dump(best_params, f, indent=2)
    print(f"   ✓ Best params: {params_path}")
    
    # Save study
    study_path = OPTUNA_DIR / "lgbm_optuna_study.pkl"
    joblib.dump(study, study_path)
    print(f"   ✓ Study: {study_path}")
    
    # Save trials history
    trials_df = pd.DataFrame([
        {'trial': t['trial'], 'mean_auc': t['mean_auc'], 'std_auc': t['std_auc']}
        for t in trial_history
    ])
    trials_path = OPTUNA_DIR / "lgbm_trials_history.csv"
    trials_df.to_csv(trials_path, index=False)
    print(f"   ✓ Trials history: {trials_path}")
    
    # Feature importance
    importance_df = pd.DataFrame({
        'feature': FEATURE_COLUMNS,
        'importance': final_model.feature_importance(importance_type='gain')
    }).sort_values('importance', ascending=False)
    
    importance_path = REPORTS_DIR / "lgbm_optuna_feature_importance.csv"
    importance_df.to_csv(importance_path, index=False)
    print(f"   ✓ Feature importance: {importance_path}")
    
    # =========================================================================
    # Step 7: Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("📊 Top 10 Most Important Features")
    print("=" * 70)
    for i, row in importance_df.head(10).iterrows():
        print(f"   {row['feature']:30s}: {row['importance']:,.0f}")
    
    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print("✅ LightGBM Optuna Training COMPLETE!")
    print("=" * 70)
    print(f"   Total time: {total_time/60:.1f} minutes")
    print(f"   Trials completed: {N_TRIALS}")
    print(f"   Best CV AUC: {study.best_value:.4f}")
    print(f"   Test ROC-AUC: {metrics['roc_auc']:.4f}")
    print(f"   Test F1: {metrics['f1']:.4f}")
    
    # Comparison with baseline
    print("\n📈 Improvement Analysis:")
    baseline_auc = 0.9406  # Previous LightGBM without Optuna
    improvement = (metrics['roc_auc'] - baseline_auc) * 100
    print(f"   Baseline ROC-AUC: {baseline_auc:.4f}")
    print(f"   Optuna ROC-AUC:   {metrics['roc_auc']:.4f}")
    print(f"   Improvement:      {improvement:+.2f}%")
    
    return final_model, study, metrics


if __name__ == "__main__":
    model, study, metrics = main()
