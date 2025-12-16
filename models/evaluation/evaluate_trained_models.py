"""
ML Model Evaluation - Load Trained Models Only
===============================================
Script đánh giá models đã train sẵn, không cần train lại.

Loads from artifacts:
- Trust: lgbm_trust_classifier_latest.joblib + metadata.json
- Success: success_lgbm_model_ternary.pkl + metrics_ternary.json

Usage:
    python -m models.evaluation.evaluate_trained_models

Author: KOL Analytics Team (IE212 - UIT)
"""

import os
import sys
import json
import warnings
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
import joblib
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.gridspec import GridSpec

from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, roc_curve, precision_recall_curve, average_precision_score,
    confusion_matrix, classification_report
)

# Suppress warnings
warnings.filterwarnings('ignore')

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Directories
ARTIFACTS_DIR = PROJECT_ROOT / "models" / "artifacts"
TRUST_ARTIFACTS = ARTIFACTS_DIR / "trust"
SUCCESS_ARTIFACTS = ARTIFACTS_DIR / "success"
CHARTS_DIR = PROJECT_ROOT / "models" / "reports" / "charts"
REPORTS_DIR = PROJECT_ROOT / "models" / "reports"

# Create output directories
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# Matplotlib style
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams['figure.figsize'] = (12, 8)
plt.rcParams['font.size'] = 11


class TrainedModelEvaluator:
    """Evaluate models from saved artifacts without retraining."""
    
    def __init__(self, output_dir: Path = CHARTS_DIR):
        self.output_dir = output_dir
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.results = {}
        
    def load_trust_model(self) -> Dict:
        """Load Trust model artifacts."""
        print("\n📦 Loading Trust Model artifacts...")
        
        # Load model
        model_path = TRUST_ARTIFACTS / "lgbm_trust_classifier_latest.joblib"
        if not model_path.exists():
            # Try alternative paths
            model_path = TRUST_ARTIFACTS / "lgbm_optuna_model.pkl"
        
        if model_path.exists():
            model = joblib.load(model_path)
            print(f"   ✅ Model: {model_path.name}")
        else:
            print("   ❌ Model not found")
            return {}
        
        # Load metadata
        metadata_path = TRUST_ARTIFACTS / "lgbm_trust_classifier_latest_metadata.json"
        if metadata_path.exists():
            with open(metadata_path) as f:
                metadata = json.load(f)
            print(f"   ✅ Metadata: {metadata_path.name}")
        else:
            metadata = {}
            
        return {
            "model": model,
            "metadata": metadata,
            "model_name": "trust_lgbm",
            "model_type": "binary"
        }
    
    def load_success_model(self) -> Dict:
        """Load Success model artifacts."""
        print("\n📦 Loading Success Model artifacts...")
        
        # Load model
        model_path = SUCCESS_ARTIFACTS / "success_lgbm_model_ternary.pkl"
        if not model_path.exists():
            model_path = SUCCESS_ARTIFACTS / "success_lgbm_model.pkl"
            
        if model_path.exists():
            model = joblib.load(model_path)
            print(f"   ✅ Model: {model_path.name}")
        else:
            print("   ❌ Model not found")
            return {}
        
        # Load scaler
        scaler_path = SUCCESS_ARTIFACTS / "success_scaler_ternary.pkl"
        if not scaler_path.exists():
            scaler_path = SUCCESS_ARTIFACTS / "success_scaler.pkl"
        scaler = joblib.load(scaler_path) if scaler_path.exists() else None
        
        # Load metrics
        metrics_path = SUCCESS_ARTIFACTS / "metrics_ternary.json"
        if metrics_path.exists():
            with open(metrics_path) as f:
                metrics = json.load(f)
            print(f"   ✅ Metrics: {metrics_path.name}")
        else:
            metrics = {}
            
        # Load feature names
        features_path = SUCCESS_ARTIFACTS / "feature_names_ternary.json"
        if features_path.exists():
            with open(features_path) as f:
                feature_names = json.load(f)
        else:
            feature_names = []
            
        return {
            "model": model,
            "scaler": scaler,
            "metrics": metrics,
            "feature_names": feature_names,
            "model_name": "success_lgbm",
            "model_type": "multiclass"
        }
    
    def visualize_trust_model(self, artifacts: Dict) -> Dict[str, plt.Figure]:
        """Generate visualizations for Trust model from metadata."""
        print("\n📊 Generating Trust Model visualizations...")
        
        metadata = artifacts.get("metadata", {})
        metrics = metadata.get("metrics", {})
        feature_names = metadata.get("feature_names", [])
        
        figures = {}
        
        # 1. Metrics bar chart
        fig1, ax = plt.subplots(figsize=(10, 6))
        metric_names = ['accuracy', 'precision', 'recall', 'f1_score', 'roc_auc', 'pr_auc']
        values = [metrics.get(m, 0) for m in metric_names]
        colors = plt.cm.RdYlGn(np.array(values))
        
        bars = ax.bar(range(len(metric_names)), values, color=colors)
        ax.set_xticks(range(len(metric_names)))
        ax.set_xticklabels([m.replace('_', '\n').upper() for m in metric_names], fontsize=10)
        ax.set_ylim(0, 1.1)
        ax.set_ylabel('Score', fontweight='bold')
        ax.set_title('Trust Score Model - Classification Metrics', fontsize=14, fontweight='bold')
        ax.axhline(y=0.8, color='green', linestyle='--', alpha=0.5, label='Good (0.8)')
        ax.axhline(y=0.5, color='red', linestyle='--', alpha=0.5, label='Random (0.5)')
        ax.legend(loc='lower right')
        
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                   f'{val:.3f}', ha='center', va='bottom', fontsize=11, fontweight='bold')
        
        plt.tight_layout()
        figures['trust_metrics'] = fig1
        
        # 2. Feature importance (from model if available)
        model = artifacts.get("model")
        if model and hasattr(model, 'feature_importances_') and feature_names:
            fig2, ax = plt.subplots(figsize=(12, 8))
            importance = model.feature_importances_
            
            # Sort by importance
            indices = np.argsort(importance)[::-1][:20]  # Top 20
            top_features = [feature_names[i] for i in indices]
            top_values = importance[indices]
            
            colors = plt.cm.Blues(np.linspace(0.4, 0.9, len(top_features)))[::-1]
            bars = ax.barh(range(len(top_features)), top_values, color=colors)
            ax.set_yticks(range(len(top_features)))
            ax.set_yticklabels(top_features, fontsize=10)
            ax.invert_yaxis()
            ax.set_xlabel('Feature Importance', fontweight='bold')
            ax.set_title('Trust Model - Top 20 Feature Importance', fontsize=14, fontweight='bold')
            ax.grid(True, axis='x', alpha=0.3)
            
            plt.tight_layout()
            figures['trust_feature_importance'] = fig2
        
        # 3. Model summary dashboard
        fig3 = plt.figure(figsize=(14, 10))
        gs = GridSpec(2, 2, figure=fig3, hspace=0.3, wspace=0.3)
        
        # Metrics radar
        ax1 = fig3.add_subplot(gs[0, 0])
        metric_labels = ['Accuracy', 'Precision', 'Recall', 'F1', 'ROC-AUC']
        metric_values = [metrics.get(m.lower().replace('-', '_'), 0) for m in 
                        ['accuracy', 'precision', 'recall', 'f1_score', 'roc_auc']]
        
        bars = ax1.bar(range(len(metric_labels)), metric_values, 
                       color=plt.cm.RdYlGn(np.array(metric_values)))
        ax1.set_xticks(range(len(metric_labels)))
        ax1.set_xticklabels(metric_labels)
        ax1.set_ylim(0, 1)
        ax1.set_title('Classification Metrics', fontweight='bold')
        for bar, val in zip(bars, metric_values):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                    f'{val:.3f}', ha='center', fontsize=9, fontweight='bold')
        
        # Model info
        ax2 = fig3.add_subplot(gs[0, 1])
        ax2.axis('off')
        params = metadata.get("params", {})
        info_text = f"""
        MODEL INFORMATION
        ─────────────────────────────
        Model: LightGBM Trust Classifier
        Trained: {metadata.get('timestamp', 'N/A')}
        
        HYPERPARAMETERS
        ─────────────────────────────
        n_estimators: {params.get('n_estimators', 'N/A')}
        max_depth: {params.get('max_depth', 'N/A')}
        learning_rate: {params.get('learning_rate', 'N/A')}
        num_leaves: {params.get('num_leaves', 'N/A')}
        subsample: {params.get('subsample', 'N/A')}
        colsample_bytree: {params.get('colsample_bytree', 'N/A')}
        
        DATASET
        ─────────────────────────────
        Features: {len(feature_names)}
        """
        ax2.text(0.1, 0.9, info_text, transform=ax2.transAxes, fontsize=11,
                verticalalignment='top', fontfamily='monospace',
                bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.3))
        ax2.set_title('Model Configuration', fontweight='bold')
        
        # Performance gauge
        ax3 = fig3.add_subplot(gs[1, 0])
        roc_auc = metrics.get('roc_auc', 0)
        gauge_colors = ['red', 'orange', 'yellow', 'lightgreen', 'green']
        thresholds = [0, 0.5, 0.7, 0.8, 0.9, 1.0]
        
        for i, (low, high) in enumerate(zip(thresholds[:-1], thresholds[1:])):
            ax3.barh(0, high - low, left=low, height=0.3, color=gauge_colors[i], alpha=0.6)
        ax3.axvline(x=roc_auc, color='black', linewidth=3, label=f'ROC-AUC: {roc_auc:.4f}')
        ax3.scatter([roc_auc], [0], s=200, c='black', zorder=5, marker='v')
        ax3.set_xlim(0, 1)
        ax3.set_ylim(-0.5, 0.5)
        ax3.set_xlabel('Score', fontweight='bold')
        ax3.set_title('ROC-AUC Performance Gauge', fontweight='bold')
        ax3.legend(loc='upper left')
        ax3.set_yticks([])
        
        # Key metrics table
        ax4 = fig3.add_subplot(gs[1, 1])
        ax4.axis('off')
        table_data = [
            ['Metric', 'Value', 'Rating'],
            ['Accuracy', f"{metrics.get('accuracy', 0):.4f}", self._get_rating(metrics.get('accuracy', 0))],
            ['Precision', f"{metrics.get('precision', 0):.4f}", self._get_rating(metrics.get('precision', 0))],
            ['Recall', f"{metrics.get('recall', 0):.4f}", self._get_rating(metrics.get('recall', 0))],
            ['F1-Score', f"{metrics.get('f1_score', 0):.4f}", self._get_rating(metrics.get('f1_score', 0))],
            ['ROC-AUC', f"{metrics.get('roc_auc', 0):.4f}", self._get_rating(metrics.get('roc_auc', 0))],
            ['PR-AUC', f"{metrics.get('pr_auc', 0):.4f}", self._get_rating(metrics.get('pr_auc', 0))],
        ]
        table = ax4.table(cellText=table_data[1:], colLabels=table_data[0],
                         loc='center', cellLoc='center', colWidths=[0.4, 0.3, 0.3])
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1.2, 1.8)
        
        for (row, col), cell in table.get_celld().items():
            if row == 0:
                cell.set_text_props(fontweight='bold', color='white')
                cell.set_facecolor('#2E86AB')
            elif col == 2:
                rating = table_data[row][2]
                if rating == '⭐⭐⭐':
                    cell.set_facecolor('#90EE90')
                elif rating == '⭐⭐':
                    cell.set_facecolor('#FFFFE0')
                else:
                    cell.set_facecolor('#FFB6C1')
        
        ax4.set_title('Metrics Summary', fontweight='bold')
        
        fig3.suptitle('TRUST SCORE MODEL - EVALUATION DASHBOARD', 
                      fontsize=16, fontweight='bold', y=1.02)
        plt.tight_layout()
        figures['trust_dashboard'] = fig3
        
        # Save figures
        for name, fig in figures.items():
            filepath = self.output_dir / f"{name}_{self.timestamp}.png"
            fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            print(f"   💾 Saved: {filepath.name}")
        
        return figures
    
    def visualize_success_model(self, artifacts: Dict) -> Dict[str, plt.Figure]:
        """Generate visualizations for Success model."""
        print("\n📊 Generating Success Model visualizations...")
        
        metrics = artifacts.get("metrics", {})
        feature_names = artifacts.get("feature_names", [])
        model = artifacts.get("model")
        
        figures = {}
        
        # 1. Metrics bar chart
        fig1, ax = plt.subplots(figsize=(10, 6))
        metric_names = ['accuracy', 'precision', 'recall', 'f1', 'roc_auc']
        values = [metrics.get(m, 0) for m in metric_names]
        colors = plt.cm.RdYlGn(np.array(values))
        
        bars = ax.bar(range(len(metric_names)), values, color=colors)
        ax.set_xticks(range(len(metric_names)))
        ax.set_xticklabels([m.replace('_', '\n').upper() for m in metric_names], fontsize=10)
        ax.set_ylim(0, 1.1)
        ax.set_ylabel('Score', fontweight='bold')
        ax.set_title('Success Score Model - Classification Metrics (Ternary)', 
                     fontsize=14, fontweight='bold')
        ax.axhline(y=0.5, color='red', linestyle='--', alpha=0.5, label='Random (0.5)')
        ax.legend(loc='lower right')
        
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                   f'{val:.3f}', ha='center', va='bottom', fontsize=11, fontweight='bold')
        
        plt.tight_layout()
        figures['success_metrics'] = fig1
        
        # 2. Feature importance
        if model and hasattr(model, 'feature_importances_') and feature_names:
            fig2, ax = plt.subplots(figsize=(10, 8))
            importance = model.feature_importances_
            
            # Sort
            sorted_idx = np.argsort(importance)[::-1]
            sorted_features = [feature_names[i] if i < len(feature_names) else f"feature_{i}" 
                              for i in sorted_idx]
            sorted_values = importance[sorted_idx]
            
            colors = plt.cm.Greens(np.linspace(0.3, 0.9, len(sorted_features)))[::-1]
            bars = ax.barh(range(len(sorted_features)), sorted_values, color=colors)
            ax.set_yticks(range(len(sorted_features)))
            ax.set_yticklabels(sorted_features, fontsize=10)
            ax.invert_yaxis()
            ax.set_xlabel('Feature Importance', fontweight='bold')
            ax.set_title('Success Model - Feature Importance', fontsize=14, fontweight='bold')
            ax.grid(True, axis='x', alpha=0.3)
            
            plt.tight_layout()
            figures['success_feature_importance'] = fig2
        
        # Save
        for name, fig in figures.items():
            filepath = self.output_dir / f"{name}_{self.timestamp}.png"
            fig.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            print(f"   💾 Saved: {filepath.name}")
        
        return figures
    
    def _get_rating(self, value: float) -> str:
        """Get star rating based on metric value."""
        if value >= 0.85:
            return '⭐⭐⭐'
        elif value >= 0.7:
            return '⭐⭐'
        else:
            return '⭐'
    
    def print_summary(self, trust_artifacts: Dict, success_artifacts: Dict):
        """Print evaluation summary."""
        print("\n" + "=" * 80)
        print("📊 MODEL EVALUATION SUMMARY")
        print("=" * 80)
        
        # Trust Model
        trust_metrics = trust_artifacts.get("metadata", {}).get("metrics", {})
        if trust_metrics:
            print("\n🔐 TRUST SCORE MODEL (LightGBM)")
            print("-" * 40)
            print(f"   Accuracy:  {trust_metrics.get('accuracy', 0):.4f}")
            print(f"   Precision: {trust_metrics.get('precision', 0):.4f}")
            print(f"   Recall:    {trust_metrics.get('recall', 0):.4f}")
            print(f"   F1-Score:  {trust_metrics.get('f1_score', 0):.4f}")
            print(f"   ROC-AUC:   {trust_metrics.get('roc_auc', 0):.4f}")
            print(f"   PR-AUC:    {trust_metrics.get('pr_auc', 0):.4f}")
        
        # Success Model
        success_metrics = success_artifacts.get("metrics", {})
        if success_metrics:
            print("\n📈 SUCCESS SCORE MODEL (LightGBM - Ternary)")
            print("-" * 40)
            print(f"   Accuracy:  {success_metrics.get('accuracy', 0):.4f}")
            print(f"   Precision: {success_metrics.get('precision', 0):.4f}")
            print(f"   Recall:    {success_metrics.get('recall', 0):.4f}")
            print(f"   F1-Score:  {success_metrics.get('f1', 0):.4f}")
            print(f"   ROC-AUC:   {success_metrics.get('roc_auc', 0):.4f}")
        
        print("\n" + "=" * 80)
        print(f"📁 Charts saved to: {self.output_dir}")
        print("=" * 80)
    
    def run(self):
        """Run full evaluation."""
        print("\n" + "=" * 80)
        print("🎯 KOL ANALYTICS - MODEL EVALUATION (NO RETRAINING)")
        print("=" * 80)
        print(f"   Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Load models
        trust_artifacts = self.load_trust_model()
        success_artifacts = self.load_success_model()
        
        # Generate visualizations
        if trust_artifacts:
            self.visualize_trust_model(trust_artifacts)
        
        if success_artifacts:
            self.visualize_success_model(success_artifacts)
        
        # Print summary
        self.print_summary(trust_artifacts, success_artifacts)
        
        return {
            "trust": trust_artifacts,
            "success": success_artifacts
        }


def main():
    """Main entry point."""
    evaluator = TrainedModelEvaluator()
    return evaluator.run()


if __name__ == "__main__":
    main()
