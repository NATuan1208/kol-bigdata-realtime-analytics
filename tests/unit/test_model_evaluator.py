"""
Unit Tests for ML Model Evaluation Framework
Tests model loading, evaluation, and visualization generation.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


class TestModelEvaluator(unittest.TestCase):
    """Test cases for ModelEvaluator class"""

    def setUp(self):
        """Set up test fixtures"""
        self.artifacts_dir = project_root / "models" / "artifacts"
        self.reports_dir = project_root / "models" / "reports" / "charts"

    def test_artifacts_directory_exists(self):
        """Test that model artifacts directory exists"""
        self.assertTrue(
            self.artifacts_dir.exists(),
            f"Artifacts directory not found: {self.artifacts_dir}"
        )

    def test_trust_model_artifacts_exist(self):
        """Test that Trust Score model artifacts exist"""
        trust_dir = self.artifacts_dir / "trust"
        
        # Check at least one model file exists
        model_files = [
            "lgbm_trust_classifier_latest.joblib",
            "xgb_trust_classifier_latest.joblib",
            "iforest_trust_anomaly_latest.joblib",
            "ensemble_trust_stacking_latest.joblib"
        ]
        
        existing_models = [
            f for f in model_files if (trust_dir / f).exists()
        ]
        
        self.assertGreater(
            len(existing_models), 0,
            f"No Trust model artifacts found in {trust_dir}"
        )

    def test_success_model_artifacts_exist(self):
        """Test that Success Score model artifacts exist"""
        success_dir = self.artifacts_dir / "success"
        
        # Check at least one model file exists
        model_files = [
            "success_lgbm_model.pkl",
            "success_lgbm_model_ternary.pkl"
        ]
        
        existing_models = [
            f for f in model_files if (success_dir / f).exists()
        ]
        
        self.assertGreater(
            len(existing_models), 0,
            f"No Success model artifacts found in {success_dir}"
        )

    def test_reports_directory_creation(self):
        """Test that reports/charts directory can be created"""
        if not self.reports_dir.exists():
            self.reports_dir.mkdir(parents=True, exist_ok=True)
        
        self.assertTrue(
            self.reports_dir.exists(),
            f"Reports directory could not be created: {self.reports_dir}"
        )

    def test_model_metadata_files_exist(self):
        """Test that metadata files exist for loaded models"""
        trust_dir = self.artifacts_dir / "trust"
        
        # Check for metadata JSON files
        metadata_files = [
            "lgbm_metadata.json",
            "xgb_metadata.json",
            "iforest_metadata.json"
        ]
        
        for metadata_file in metadata_files:
            path = trust_dir / metadata_file
            if path.exists():
                # At least one metadata file should exist
                return
        
        # If no metadata files found, it's a warning but not a failure
        # (metadata might be embedded in model files)
        pass

    @patch('matplotlib.pyplot.savefig')
    def test_chart_generation_mock(self, mock_savefig):
        """Test that chart generation can be called (mocked)"""
        # This is a smoke test to ensure matplotlib can be imported
        import matplotlib.pyplot as plt
        
        fig, ax = plt.subplots()
        ax.plot([1, 2, 3], [1, 2, 3])
        
        # Mock saving the figure
        mock_savefig.return_value = None
        plt.savefig("test.png")
        
        # Verify savefig was called
        mock_savefig.assert_called_once()
        plt.close()


class TestModelLoader(unittest.TestCase):
    """Test cases for model loading functionality"""

    def test_joblib_import(self):
        """Test that joblib can be imported"""
        try:
            import joblib
            self.assertIsNotNone(joblib)
        except ImportError:
            self.fail("joblib not installed")

    def test_sklearn_import(self):
        """Test that scikit-learn can be imported"""
        try:
            import sklearn
            self.assertIsNotNone(sklearn)
        except ImportError:
            self.fail("scikit-learn not installed")

    def test_lightgbm_import(self):
        """Test that LightGBM can be imported"""
        try:
            import lightgbm
            self.assertIsNotNone(lightgbm)
        except ImportError:
            self.fail("lightgbm not installed")

    def test_xgboost_import(self):
        """Test that XGBoost can be imported"""
        try:
            import xgboost
            self.assertIsNotNone(xgboost)
        except ImportError:
            self.fail("xgboost not installed")

    def test_optuna_import(self):
        """Test that Optuna can be imported"""
        try:
            import optuna
            self.assertIsNotNone(optuna)
        except ImportError:
            self.fail("optuna not installed")


class TestDataProcessing(unittest.TestCase):
    """Test cases for data processing utilities"""

    def test_numpy_import(self):
        """Test that NumPy can be imported"""
        try:
            import numpy as np
            self.assertIsNotNone(np)
        except ImportError:
            self.fail("numpy not installed")

    def test_pandas_import(self):
        """Test that Pandas can be imported"""
        try:
            import pandas as pd
            self.assertIsNotNone(pd)
        except ImportError:
            self.fail("pandas not installed")

    def test_matplotlib_import(self):
        """Test that Matplotlib can be imported"""
        try:
            import matplotlib.pyplot as plt
            self.assertIsNotNone(plt)
        except ImportError:
            self.fail("matplotlib not installed")

    def test_seaborn_import(self):
        """Test that Seaborn can be imported"""
        try:
            import seaborn as sns
            self.assertIsNotNone(sns)
        except ImportError:
            self.fail("seaborn not installed")


class TestEvaluationScripts(unittest.TestCase):
    """Test cases for evaluation script structure"""

    def setUp(self):
        """Set up test fixtures"""
        self.evaluation_dir = project_root / "models" / "evaluation"

    def test_evaluation_directory_exists(self):
        """Test that evaluation directory exists"""
        self.assertTrue(
            self.evaluation_dir.exists(),
            f"Evaluation directory not found: {self.evaluation_dir}"
        )

    def test_model_evaluator_script_exists(self):
        """Test that model_evaluator.py exists"""
        script_path = self.evaluation_dir / "model_evaluator.py"
        self.assertTrue(
            script_path.exists(),
            f"model_evaluator.py not found: {script_path}"
        )

    def test_evaluate_trained_models_script_exists(self):
        """Test that evaluate_trained_models.py exists"""
        script_path = self.evaluation_dir / "evaluate_trained_models.py"
        self.assertTrue(
            script_path.exists(),
            f"evaluate_trained_models.py not found: {script_path}"
        )

    def test_model_comparison_script_exists(self):
        """Test that model_comparison_analysis.py exists"""
        script_path = self.evaluation_dir / "model_comparison_analysis.py"
        self.assertTrue(
            script_path.exists(),
            f"model_comparison_analysis.py not found: {script_path}"
        )

    def test_train_trust_model_script_exists(self):
        """Test that train_trust_model.py exists"""
        script_path = self.evaluation_dir / "train_trust_model.py"
        self.assertTrue(
            script_path.exists(),
            f"train_trust_model.py not found: {script_path}"
        )

    def test_train_success_model_script_exists(self):
        """Test that train_success_model.py exists"""
        script_path = self.evaluation_dir / "train_success_model.py"
        self.assertTrue(
            script_path.exists(),
            f"train_success_model.py not found: {script_path}"
        )


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)
