"""
KOL Trust Score Models
======================

Ensemble model để detect KOL không đáng tin (fake followers, suspicious patterns).

Models:
- XGBoost Classifier (main)
- LightGBM Classifier (secondary)
- Isolation Forest (anomaly detection)
- Stacking Ensemble (meta-learner)

Usage:
------
from models.trust import train_xgb, train_lgbm, score_iforest
from models.trust.data_loader import load_training_data

X_train, X_test, y_train, y_test = load_training_data()
model = train_xgb.train(X_train, y_train)
"""

from .data_loader import (
    load_training_data,
    load_features_dataframe,
    get_feature_names,
    get_class_weights,
    get_scale_pos_weight,
)

__all__ = [
    "load_training_data",
    "load_features_dataframe", 
    "get_feature_names",
    "get_class_weights",
    "get_scale_pos_weight",
]
