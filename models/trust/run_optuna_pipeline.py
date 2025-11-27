"""
Run Full Optuna Training Pipeline
=================================
Runs XGBoost and LightGBM with Optuna tuning sequentially,
then generates comparison report.

Usage:
    docker exec -it kol-trainer python -m models.trust.run_optuna_pipeline
"""

import os
import json
import time
import warnings
from datetime import datetime
from pathlib import Path

import pandas as pd

warnings.filterwarnings('ignore')

# ============================================================================
# MAIN PIPELINE
# ============================================================================
def run_full_optuna_pipeline():
    """Run complete Optuna tuning pipeline for all models."""
    
    print("=" * 70)
    print("🚀 KOL Trust Score - Full Optuna Training Pipeline")
    print("=" * 70)
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("   Models: XGBoost, LightGBM")
    print("   Trials per model: 50")
    print("   Cross-validation: 5-fold Stratified")
    print("=" * 70)
    
    pipeline_start = time.time()
    results = {}
    
    # -------------------------------------------------------------------------
    # Step 1: XGBoost with Optuna
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("📦 [1/2] Running XGBoost Optuna Tuning...")
    print("=" * 70)
    
    from models.trust.train_xgb_optuna import train_xgb_with_optuna
    xgb_model, xgb_study, xgb_metrics = train_xgb_with_optuna()
    results['xgboost'] = xgb_metrics
    
    # -------------------------------------------------------------------------
    # Step 2: LightGBM with Optuna
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("📦 [2/2] Running LightGBM Optuna Tuning...")
    print("=" * 70)
    
    from models.trust.train_lgbm_optuna import train_lgbm_with_optuna
    lgbm_model, lgbm_study, lgbm_metrics = train_lgbm_with_optuna()
    results['lightgbm'] = lgbm_metrics
    
    # -------------------------------------------------------------------------
    # Step 3: Generate Comparison Report
    # -------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("📊 OPTUNA TUNING COMPARISON REPORT")
    print("=" * 70)
    
    # Create comparison table
    comparison_df = pd.DataFrame([
        {
            'Model': 'XGBoost-Optuna',
            'ROC-AUC': xgb_metrics['roc_auc'],
            'F1-Score': xgb_metrics['f1'],
            'Accuracy': xgb_metrics['accuracy'],
            'Precision': xgb_metrics['precision'],
            'Recall': xgb_metrics['recall'],
            'Best CV Score': xgb_metrics['best_cv_score'],
            'Training Time (min)': xgb_metrics['training_time_seconds'] / 60,
        },
        {
            'Model': 'LightGBM-Optuna',
            'ROC-AUC': lgbm_metrics['roc_auc'],
            'F1-Score': lgbm_metrics['f1'],
            'Accuracy': lgbm_metrics['accuracy'],
            'Precision': lgbm_metrics['precision'],
            'Recall': lgbm_metrics['recall'],
            'Best CV Score': lgbm_metrics['best_cv_score'],
            'Training Time (min)': lgbm_metrics['training_time_seconds'] / 60,
        }
    ])
    
    print("\n📈 Performance Comparison:")
    print("-" * 70)
    print(comparison_df.to_string(index=False))
    
    # Find best model
    best_model = 'XGBoost' if xgb_metrics['roc_auc'] > lgbm_metrics['roc_auc'] else 'LightGBM'
    best_roc = max(xgb_metrics['roc_auc'], lgbm_metrics['roc_auc'])
    
    print(f"\n🏆 Best Model: {best_model}-Optuna (ROC-AUC: {best_roc:.4f})")
    
    # Save comparison report
    reports_dir = Path("models/reports")
    reports_dir.mkdir(parents=True, exist_ok=True)
    
    comparison_path = reports_dir / "optuna_comparison.csv"
    comparison_df.to_csv(comparison_path, index=False)
    print(f"\n💾 Comparison saved: {comparison_path}")
    
    # Save full results
    full_results = {
        'timestamp': datetime.now().isoformat(),
        'pipeline_duration_minutes': (time.time() - pipeline_start) / 60,
        'xgboost': xgb_metrics,
        'lightgbm': lgbm_metrics,
        'best_model': best_model,
        'best_roc_auc': best_roc,
    }
    
    results_path = reports_dir / "optuna_full_results.json"
    with open(results_path, 'w') as f:
        json.dump(full_results, f, indent=2)
    print(f"💾 Full results saved: {results_path}")
    
    # -------------------------------------------------------------------------
    # Final Summary
    # -------------------------------------------------------------------------
    total_time = time.time() - pipeline_start
    print("\n" + "=" * 70)
    print("✅ OPTUNA PIPELINE COMPLETE!")
    print("=" * 70)
    print(f"   Total pipeline time: {total_time/60:.1f} minutes")
    print(f"   XGBoost ROC-AUC: {xgb_metrics['roc_auc']:.4f}")
    print(f"   LightGBM ROC-AUC: {lgbm_metrics['roc_auc']:.4f}")
    print(f"   Best Model: {best_model}")
    print("=" * 70)
    
    print("\n📁 Artifacts saved:")
    print("   models/artifacts/trust/xgb_optuna_model.pkl")
    print("   models/artifacts/trust/lgbm_optuna_model.pkl")
    print("   models/artifacts/optuna/xgb_best_params.json")
    print("   models/artifacts/optuna/lgbm_best_params.json")
    print("   models/reports/optuna_comparison.csv")
    print("   models/reports/optuna_full_results.json")
    
    return results


# ============================================================================
# ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    results = run_full_optuna_pipeline()
