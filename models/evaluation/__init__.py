# Models Evaluation Package
# =========================
# Professional ML training and evaluation framework.

from pathlib import Path

# Package info
__version__ = "1.0.0"
__author__ = "KOL Analytics Team (IE212 - UIT)"

# Paths
PACKAGE_DIR = Path(__file__).parent
PROJECT_ROOT = PACKAGE_DIR.parent.parent

# Exports
__all__ = [
    "ModelEvaluator",
    "train_trust_model",
    "train_success_model", 
    "run_full_pipeline"
]

# Lazy imports
def __getattr__(name):
    if name == "ModelEvaluator":
        from .model_evaluator import ModelEvaluator
        return ModelEvaluator
    elif name == "train_trust_model":
        from .train_trust_model import run_training
        return run_training
    elif name == "train_success_model":
        from .train_success_model import run_training
        return run_training
    elif name == "run_full_pipeline":
        from .run_pipeline import run_full_pipeline
        return run_full_pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
