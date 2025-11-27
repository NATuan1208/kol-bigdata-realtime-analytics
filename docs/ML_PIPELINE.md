# 🤖 KOL Trust Score - Machine Learning Pipeline

## IE212 - Big Data Analytics | UIT 2025

---

## 📋 Mục Lục

1. [Tổng Quan Bài Toán](#-tổng-quan-bài-toán)
2. [Kiến Trúc ML Pipeline](#-kiến-trúc-ml-pipeline)
3. [Dataset & Features](#-dataset--features)
4. [Model Architecture](#-model-architecture)
5. [Training Results](#-training-results)
6. [Model Evaluation](#-model-evaluation)
7. [Feature Importance](#-feature-importance)
8. [Hướng Dẫn Sử Dụng](#-hướng-dẫn-sử-dụng)
9. [Model Serving](#-model-serving)

---

## 🎯 Tổng Quan Bài Toán

### Business Problem

Detect **KOL không đáng tin (Untrustworthy KOLs)** - những người có hành vi:
- 🤖 Sử dụng **fake followers** (mua followers ảo)
- 📈 **Suspicious growth patterns** (tăng followers bất thường)
- 📉 **Low engagement với high followers** (nhiều followers nhưng ít tương tác)
- ⚙️ **Bot-like activity** (hoạt động như bot)

### ML Task Definition

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    BINARY CLASSIFICATION TASK                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   Input:  29 engineered features từ KOL profile & activity              │
│                                                                         │
│   Output: Trust Score (0-100)                                           │
│           ├── 80-100: Highly Trustworthy ✅                             │
│           ├── 60-79:  Moderately Trustworthy                            │
│           ├── 40-59:  Needs Review ⚠️                                   │
│           └── 0-39:   Likely Untrustworthy ❌                           │
│                                                                         │
│   Label:  is_untrustworthy                                              │
│           ├── 0 = Trustworthy KOL (authentic, organic engagement)       │
│           └── 1 = Untrustworthy KOL (fake followers, bot patterns)      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Dataset Origin

**Source**: Twitter Human-Bot Detection Dataset (Kaggle)

**Semantic Re-mapping cho bài toán KOL Trust:**

| Original Label | Re-mapped Label | Interpretation |
|----------------|-----------------|----------------|
| `is_bot = 1` | `is_untrustworthy = 1` | KOL không đáng tin |
| `is_bot = 0` | `is_untrustworthy = 0` | KOL đáng tin |

**Lý do features overlap (~80%):**

| Bot Patterns | Untrustworthy KOL Patterns |
|--------------|---------------------------|
| F/F ratio bất thường | Fake followers follow ratio |
| Account age ngắn + followers tăng nhanh | Mua followers → tăng đột biến |
| Default profile, no bio | Focus mua followers hơn build profile |
| Low engagement rate | Fake followers không tương tác |
| High posting frequency | Dùng bot để post |

---

## 🏗️ Kiến Trúc ML Pipeline

### End-to-End Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           ML PIPELINE ARCHITECTURE                                  │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │   MinIO     │    │   Feature   │    │   Model     │    │     Ensemble        │  │
│  │  (Parquet)  │───▶│ Engineering │───▶│  Training   │───▶│    Stacking         │  │
│  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────────────┘  │
│        │                   │                  │                      │             │
│        ▼                   ▼                  ▼                      ▼             │
│   37,438 records     29 features      3 base models         Calibrated Score      │
│                                                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                         TRAINING INFRASTRUCTURE                              │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │  │
│  │  │kol-trainer  │  │   MLflow    │  │   MinIO     │  │    kol-api          │  │  │
│  │  │ (Training)  │  │ (Registry)  │  │ (Artifacts) │  │   (Serving)         │  │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────────────┘  │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Docker Services

| Container | Role | Image | Port |
|-----------|------|-------|------|
| **kol-trainer** | ML Training | `infra-trainer:latest` | - |
| **kol-api** | Model Serving | `infra-api:latest` | 8000 |
| **mlflow** | Model Registry | `mlflow:latest` | 5000 |
| **sme-minio** | Data & Artifacts | `minio:latest` | 9000 |

### Pre-installed ML Libraries (kol-trainer)

```
✅ XGBoost 3.1.1
✅ LightGBM 4.6.0
✅ scikit-learn 1.7.2
✅ PyTorch 2.1+ (for PhoBERT)
✅ Transformers (HuggingFace)
✅ MLflow 2.9+
✅ SHAP
✅ Optuna
```

---

## 📊 Dataset & Features

### Dataset Statistics

| Metric | Value |
|--------|-------|
| **Total Records** | 37,438 |
| **Training Set** | 29,950 (80%) |
| **Test Set** | 7,488 (20%) |
| **Features** | 29 |
| **Target** | Binary (0/1) |

### Label Distribution

```
┌────────────────────────────────────────────────────────────┐
│                   LABEL DISTRIBUTION                        │
├────────────────────────────────────────────────────────────┤
│                                                             │
│  Trustworthy (label=0)     ████████████████████  66.8%     │
│  25,013 samples                                             │
│                                                             │
│  Untrustworthy (label=1)   ██████████           33.2%      │
│  12,425 samples                                             │
│                                                             │
│  Class Imbalance Ratio: 2.01:1                              │
│  scale_pos_weight (XGBoost): 2.013                          │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

### Feature Categories (29 Features)

#### 1️⃣ Log Transforms (5 features)
| Feature | Description | Formula |
|---------|-------------|---------|
| `log_followers` | Log của followers | log(followers + 1) |
| `log_following` | Log của following | log(following + 1) |
| `log_posts` | Log của posts | log(posts + 1) |
| `log_favorites` | Log của favorites | log(favorites + 1) |
| `log_account_age` | Log của tuổi account | log(account_age + 1) |

#### 2️⃣ Ratio Features (2 features)
| Feature | Description | Range |
|---------|-------------|-------|
| `followers_following_ratio_capped` | F/F ratio (capped) | [0, 10000] |
| `posts_per_day_capped` | Posts/day (capped) | [0, 50] |

#### 3️⃣ Behavioral Scores (6 features)
| Feature | Description |
|---------|-------------|
| `engagement_rate` | favorites / (posts + 1) |
| `activity_score` | Composite activity metric |
| `profile_completeness` | (has_bio + has_url + has_image) / 3 |
| `followers_per_day` | Growth rate |
| `posts_per_follower` | Content density |
| `following_per_day` | Following behavior |

#### 4️⃣ Untrustworthy Indicators (5 features) ⭐
| Feature | Description | Trigger |
|---------|-------------|---------|
| `high_activity_flag` | Bot-like posting | posts_per_day > 20 |
| `low_engagement_high_posts` | Fake followers pattern | High posts, low engagement |
| `default_profile_score` | No customization | Default settings |
| `suspicious_growth` | Unnatural growth | followers_per_day anomaly |
| `fake_follower_indicator` | Likely fake followers | High F, low engagement |

#### 5️⃣ Categorical Tiers (3 features)
| Feature | Categories |
|---------|------------|
| `followers_tier` | Nano(0), Micro(1), Mid(2), Macro(3), Mega(4) |
| `account_age_tier` | <1y(0), 1-2y(1), 2-5y(2), 5+y(3) |
| `activity_tier` | Inactive(0), Low(1), Medium(2), High(3) |

#### 6️⃣ Interaction Features (4 features)
| Feature | Formula |
|---------|---------|
| `verified_followers_interaction` | verified × log_followers |
| `profile_engagement_interaction` | profile_completeness × engagement_rate |
| `age_activity_interaction` | log_account_age × activity_score |
| `bio_length_norm` | Normalized bio length |

#### 7️⃣ Binary Features (4 features)
| Feature | Type |
|---------|------|
| `has_bio` | Boolean |
| `has_url` | Boolean |
| `has_profile_image` | Boolean |
| `verified` | Boolean |

---

## 🧠 Model Architecture

### Ensemble Stacking Design

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         ENSEMBLE STACKING ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                     │
│                              INPUT: 29 Features                                     │
│                                      │                                              │
│                    ┌─────────────────┼─────────────────┐                            │
│                    │                 │                 │                            │
│                    ▼                 ▼                 ▼                            │
│           ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                       │
│           │   XGBoost   │   │  LightGBM   │   │ Isolation   │                       │
│           │ Classifier  │   │ Classifier  │   │   Forest    │                       │
│           └──────┬──────┘   └──────┬──────┘   └──────┬──────┘                       │
│                  │                 │                 │                              │
│             P(untrust)        P(untrust)       Anomaly Score                        │
│                  │                 │                 │                              │
│                  └────────────┬────┴─────────────────┘                              │
│                               │                                                     │
│                               ▼                                                     │
│                    ┌─────────────────────┐                                          │
│                    │   META-LEARNER      │                                          │
│                    │ Logistic Regression │                                          │
│                    │                     │                                          │
│                    │ Weights:            │                                          │
│                    │ • XGB:    6.79 ⭐   │                                          │
│                    │ • LGBM:   1.18      │                                          │
│                    │ • IForest: -0.38    │                                          │
│                    └──────────┬──────────┘                                          │
│                               │                                                     │
│                               ▼                                                     │
│                    ┌─────────────────────┐                                          │
│                    │   CALIBRATION       │                                          │
│                    │ Isotonic Regression │                                          │
│                    └──────────┬──────────┘                                          │
│                               │                                                     │
│                               ▼                                                     │
│                    ┌─────────────────────┐                                          │
│                    │   TRUST SCORE       │                                          │
│                    │     (0 - 100)       │                                          │
│                    │                     │                                          │
│                    │ 100 = Trustworthy   │                                          │
│                    │   0 = Untrustworthy │                                          │
│                    └─────────────────────┘                                          │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### Model Descriptions

#### 1️⃣ XGBoost Classifier
```python
XGBClassifier(
    n_estimators=150,
    max_depth=6,
    learning_rate=0.1,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=3,
    gamma=0.1,
    reg_alpha=0.1,
    reg_lambda=1.0,
    scale_pos_weight=2.013,  # Handle class imbalance
    early_stopping_rounds=20
)
```

**Đặc điểm:**
- Gradient Boosting với regularization mạnh
- **Level-wise tree growth** (grow theo từng level)
- Xử lý tốt missing values
- **Primary contributor** trong ensemble (weight = 6.79)

#### 2️⃣ LightGBM Classifier
```python
LGBMClassifier(
    n_estimators=150,
    num_leaves=31,
    learning_rate=0.1,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_samples=20,
    reg_alpha=0.1,
    reg_lambda=0.1,
    class_weight='balanced'
)
```

**Đặc điểm:**
- **Leaf-wise tree growth** (grow leaf có loss reduction lớn nhất)
- Histogram-based (nhanh hơn XGBoost)
- Xử lý categorical features tốt
- **Diverse patterns** so với XGBoost → Ensemble diversity

#### 3️⃣ Isolation Forest (Unsupervised)
```python
IsolationForest(
    n_estimators=200,
    contamination=0.33,
    max_features=1.0,
    bootstrap=False,
    random_state=42
)
```

**Đặc điểm:**
- **Unsupervised anomaly detection**
- Không dùng labels khi training
- Detect **novel patterns** mà supervised models có thể miss
- Output: Anomaly score (0-1)
- **Negative contribution** trong ensemble (weight = -0.38)
  - Penalize các patterns anomaly mà không match với labels

#### 4️⃣ Meta-Learner: Logistic Regression
```python
LogisticRegression(
    C=1.0,
    max_iter=1000,
    random_state=42
)
```

**Role**: Combine predictions từ 3 base models

**Learned Weights:**
| Model | Weight | Interpretation |
|-------|--------|----------------|
| XGBoost | **6.79** | Main predictor |
| LightGBM | 1.18 | Supporting predictor |
| IsolationForest | -0.38 | Anomaly penalty |

---

## 📈 Training Results

### Model Performance Summary

| Model | Accuracy | Precision | Recall | F1-Score | ROC-AUC | PR-AUC |
|-------|----------|-----------|--------|----------|---------|--------|
| **XGBoost (Baseline)** | 87.42% | 79.57% | 83.54% | 0.8151 | 0.9403 | 0.9091 |
| **XGBoost + Optuna** | 87.62% | 85.97% | 76.26% | 0.8081 | **0.9418** | - |
| **LightGBM (Baseline)** | 87.66% | 79.89% | 83.94% | 0.8187 | 0.9406 | 0.9094 |
| **🏆 LightGBM + Optuna** | **88.39%** | **86.10%** | 77.55% | 0.8160 | **0.9423** | - |
| **IsolationForest** | 43.96% | 15.18% | 15.01% | 0.1510 | 0.4012 | - |
| **Ensemble (Baseline)** | 88.21% | 83.29% | 80.64% | 0.8195 | 0.9403 | 0.9069 |

> **🎯 Best Model: LightGBM + Optuna** với ROC-AUC = 0.9423, Accuracy = 88.39%

### Performance Visualization

```
┌────────────────────────────────────────────────────────────────────────┐
│                      ROC-AUC COMPARISON                                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  LGBM+Optuna  █████████████████████████████████████████████ 0.9423 🏆 │
│  XGB+Optuna   ████████████████████████████████████████████  0.9418    │
│  LightGBM     ████████████████████████████████████████████  0.9406    │
│  XGBoost      ████████████████████████████████████████████  0.9403    │
│  Ensemble     ████████████████████████████████████████████  0.9403    │
│  IForest      ████████████████                              0.4012    │
│                                                                        │
│               0.0    0.2    0.4    0.6    0.8    1.0                   │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Confusion Matrix (Ensemble)

```
                      Predicted
                 ┌─────────┬─────────┐
                 │ Trust=0 │ Trust=1 │
     ┌───────────┼─────────┼─────────┤
     │ Actual=0  │  4,601  │   402   │  → True Negatives / False Positives
True │           │  (TN)   │  (FP)   │
     ├───────────┼─────────┼─────────┤
     │ Actual=1  │   481   │  2,004  │  → False Negatives / True Positives
     │           │  (FN)   │  (TP)   │
     └───────────┴─────────┴─────────┘

Metrics:
├── Precision = TP/(TP+FP) = 2,004/(2,004+402) = 83.29%
├── Recall    = TP/(TP+FN) = 2,004/(2,004+481) = 80.64%
├── Accuracy  = (TN+TP)/Total = (4,601+2,004)/7,488 = 88.21%
└── F1-Score  = 2×P×R/(P+R) = 81.95%
```

### Trust Score Distribution

```
┌────────────────────────────────────────────────────────────────────────┐
│                    TRUST SCORE DISTRIBUTION                            │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  Trustworthy KOLs (n=5,003):                                           │
│  ├── Mean Score: 88.8 / 100                                            │
│  ├── Std Dev: 21.1                                                     │
│  └── Distribution: ████████████████████████████░░  (skew right)        │
│                                                                        │
│  Untrustworthy KOLs (n=2,485):                                         │
│  ├── Mean Score: 22.2 / 100                                            │
│  ├── Std Dev: 31.6                                                     │
│  └── Distribution: ████████░░░░░░░░░░░░░░░░░░░░░░  (skew left)         │
│                                                                        │
│  Score Interpretation:                                                 │
│  ├── 80-100: Highly Trustworthy ✅ (recommend for campaigns)           │
│  ├── 60-79:  Moderately Trustworthy (proceed with caution)             │
│  ├── 40-59:  Needs Review ⚠️ (manual verification required)            │
│  └── 0-39:   Likely Untrustworthy ❌ (avoid for campaigns)             │
│                                                                        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 Optuna Hyperparameter Tuning

### Tại sao dùng Optuna?

**Optuna** là framework Bayesian Optimization hiện đại, được sử dụng rộng rãi:
- ✅ **5000+ citations** trong research papers
- ✅ Dùng bởi **Toyota, Sony, Preferred Networks**
- ✅ Top choice của **Kaggle Grandmasters**

### So sánh với Manual Tuning

| Approach | Cách hoạt động | Hiệu quả |
|----------|---------------|----------|
| **Manual** | Đoán params, thử sai | ❌ Chủ quan, không tối ưu |
| **Grid Search** | Thử TẤT CẢ combinations | ⚠️ Tốn thời gian (O(n^k)) |
| **Random Search** | Random sampling | ⚠️ May rủi |
| **Optuna (Bayesian)** | Học từ trials trước | ✅ Thông minh, nhanh 10x |

### Optuna Configuration

```python
# Configuration used:
N_TRIALS = 50           # Số trials optimization
N_CV_FOLDS = 5          # Stratified K-Fold Cross-Validation
EARLY_STOPPING = 30     # Rounds for early stopping
NUM_BOOST_ROUND = 500   # Max boosting iterations

# Hyperparameter Search Space:
search_space = {
    'max_depth': [3, 10],           # Tree depth
    'learning_rate': [0.01, 0.2],   # Learning rate (log scale)
    'num_leaves': [20, 150],        # LightGBM leaf nodes
    'min_child_samples': [10, 100], # Min samples per leaf
    'subsample': [0.6, 1.0],        # Row sampling
    'colsample_bytree': [0.6, 1.0], # Column sampling
    'reg_alpha': [1e-6, 5.0],       # L1 regularization
    'reg_lambda': [1e-6, 5.0],      # L2 regularization
}
```

### LightGBM Optuna Results

```
======================================================================
📈 OPTUNA OPTIMIZATION RESULTS
======================================================================

🏆 Best Trial: #35/50
   Best CV ROC-AUC: 0.9414

📋 Best Hyperparameters Found:
   colsample_bytree:   0.846971
   learning_rate:      0.019015
   max_depth:          7
   min_child_samples:  28
   min_gain_to_split:  0.262514
   num_leaves:         124
   reg_alpha:          1.445124
   reg_lambda:         0.002523
   subsample:          0.797141
   subsample_freq:     2

📊 Final Test Performance:
   ROC-AUC:   0.9423 (+0.17% vs baseline)
   F1-Score:  0.8160
   Accuracy:  88.39% (+0.73% vs baseline)
   Precision: 86.10%
   Recall:    77.55%

⏱️ Training Time: 5.6 minutes (50 trials × 5-fold CV)
```

### XGBoost Optuna Results

```
======================================================================
📈 OPTUNA OPTIMIZATION RESULTS
======================================================================

🏆 Best Trial: #46/50
   Best CV ROC-AUC: 0.9413

📋 Best Hyperparameters Found:
   colsample_bytree:  0.743243
   gamma:             0.072098
   learning_rate:     0.024657
   max_depth:         5
   min_child_weight:  8
   reg_alpha:         4.091159
   reg_lambda:        0.006699
   subsample:         0.704304

📊 Final Test Performance:
   ROC-AUC:   0.9418 (+0.15% vs baseline)
   F1-Score:  0.8081
   Accuracy:  87.62%
   Precision: 85.97%
   Recall:    76.26%

⏱️ Training Time: 10.9 minutes (50 trials × 5-fold CV)
```

### Optuna Trials Visualization

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    OPTUNA OPTIMIZATION HISTORY                          │
├─────────────────────────────────────────────────────────────────────────┤
│  AUC                                                                    │
│  0.945│                                                                 │
│       │                                    ┌─────Best: 0.9414           │
│  0.942│       ●    ●  ●●    ●  ●● ●  ●●   ●● ●●                         │
│       │     ●  ●●●● ●   ●●●● ●●    ●●  ●●●    ●●●                       │
│  0.939│    ●●                                                           │
│       │   ●                                                             │
│  0.936│  ●                                                              │
│       │ ●                                                               │
│  0.933│●                                                                │
│       │                                                                 │
│  0.920│  ●  (Trial 2: Bad params)                                       │
│       └─────────────────────────────────────────────────────────────    │
│        0    5    10   15   20   25   30   35   40   45   50  Trial      │
│                                                                         │
│  Observation: Optuna nhanh chóng tìm được vùng params tốt sau ~10       │
│  trials, sau đó tinh chỉnh để đạt optimum tại trial 35.                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Improvement Analysis

| Metric | Baseline | + Optuna | Improvement |
|--------|----------|----------|-------------|
| **LightGBM ROC-AUC** | 0.9406 | **0.9423** | +0.17% |
| **LightGBM Accuracy** | 87.66% | **88.39%** | +0.73% |
| **XGBoost ROC-AUC** | 0.9403 | **0.9418** | +0.15% |
| **XGBoost Accuracy** | 87.42% | **87.62%** | +0.20% |

> **Kết luận:** Optuna cải thiện performance một cách nhất quán. Dù improvement nhỏ (~0.2%), nhưng với bài toán classification này, mỗi 0.1% đều có ý nghĩa cho việc detect untrustworthy KOLs.

---

## 🎯 Feature Importance

### XGBoost Feature Importance (Top 15)

| Rank | Feature | Importance | Visual |
|------|---------|------------|--------|
| 1 | `verified` | 0.1895 | █████████ |
| 2 | `log_followers` | 0.1565 | ███████ |
| 3 | `followers_tier` | 0.0820 | ████ |
| 4 | `activity_tier` | 0.0786 | ███ |
| 5 | `following_per_day` | 0.0482 | ██ |
| 6 | `engagement_rate` | 0.0395 | █ |
| 7 | `followers_per_day` | 0.0375 | █ |
| 8 | `verified_followers_interaction` | 0.0348 | █ |
| 9 | `log_favorites` | 0.0337 | █ |
| 10 | `profile_engagement_interaction` | 0.0309 | █ |
| 11 | `age_activity_interaction` | 0.0276 | █ |
| 12 | `posts_per_day_capped` | 0.0253 | █ |
| 13 | `log_account_age` | 0.0252 | █ |
| 14 | `followers_following_ratio_capped` | 0.0227 | █ |
| 15 | `log_following` | 0.0215 | █ |

### LightGBM Feature Importance - Gain (Top 15)

| Rank | Feature | Gain | Visual |
|------|---------|------|--------|
| 1 | `log_followers` | 31,439 | ██████████████████████████████ |
| 2 | `followers_per_day` | 14,549 | █████████████ |
| 3 | `engagement_rate` | 10,647 | ██████████ |
| 4 | `log_account_age` | 10,221 | █████████ |
| 5 | `log_favorites` | 8,774 | ████████ |
| 6 | `log_following` | 7,273 | ██████ |
| 7 | `profile_engagement_interaction` | 6,707 | ██████ |
| 8 | `posts_per_follower` | 5,297 | █████ |
| 9 | `verified_followers_interaction` | 4,591 | ████ |
| 10 | `following_per_day` | 4,374 | ████ |

### Key Insights từ Feature Importance

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    KEY INSIGHTS                                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  🎯 TOP PREDICTORS:                                                     │
│  ─────────────────                                                      │
│  1. verified - Verification status là strong indicator                  │
│     → Unverified accounts more likely to be untrustworthy               │
│                                                                         │
│  2. log_followers - Follower count (log-transformed)                    │
│     → Extreme values indicate suspicious patterns                       │
│                                                                         │
│  3. followers_per_day - Growth rate                                     │
│     → Rapid growth suggests purchased followers                         │
│                                                                         │
│  4. engagement_rate - Engagement per post                               │
│     → Low engagement with high followers = fake followers               │
│                                                                         │
│  📊 MODEL AGREEMENT:                                                    │
│  ────────────────────                                                   │
│  • Both XGBoost và LightGBM agree on top features                       │
│  • log_followers, engagement_rate, followers_per_day                    │
│  • verified status crucial for prediction                               │
│                                                                         │
│  🔍 DIFFERENT PERSPECTIVES:                                             │
│  ───────────────────────────                                            │
│  • XGBoost: Focus on verified, followers_tier (categorical)             │
│  • LightGBM: Focus on continuous metrics (growth rates)                 │
│  • Ensemble captures BOTH perspectives                                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📖 Hướng Dẫn Sử Dụng

### 1. Training Pipeline

```bash
# Step 1: Vào container trainer
docker exec -it kol-trainer bash

# Step 2a: Train baseline models
python -m models.trust.train_xgb      # Train XGBoost
python -m models.trust.train_lgbm     # Train LightGBM  
python -m models.trust.score_iforest  # Train Isolation Forest
python -m models.trust.stack_calibrate # Build Ensemble

# Step 2b: Train với Optuna tuning (Recommended ⭐)
python -m models.trust.train_xgb_optuna   # XGBoost + Optuna (~11 min)
python -m models.trust.train_lgbm_optuna  # LightGBM + Optuna (~6 min)

# Step 3: Evaluate tất cả models
python -m models.trust.evaluate --save-report

# Step 4: View reports
cat /app/models/reports/model_comparison.csv
cat /app/models/reports/lgbm_optuna_metrics.json
cat /app/models/reports/xgb_optuna_metrics.json
```

### 2. Quick Commands (từ host)

```bash
# Train all models (one-liner)
docker exec kol-trainer python -m models.trust.train_xgb && \
docker exec kol-trainer python -m models.trust.train_lgbm && \
docker exec kol-trainer python -m models.trust.score_iforest && \
docker exec kol-trainer python -m models.trust.stack_calibrate

# Evaluate with reports
docker exec kol-trainer python -m models.trust.evaluate --save-report
```

### 3. Using Makefile

```bash
# Train XGBoost
make train-xgb

# Train LightGBM  
make train-lgbm

# Full pipeline
make train-trust-models
```

### 4. Python API Usage

```python
# Load trained model
import joblib
from models.trust.data_loader import load_training_data, FEATURE_COLUMNS

# Load data
X_train, X_test, y_train, y_test = load_training_data()

# Load XGBoost model
xgb_model = joblib.load('models/artifacts/trust/xgb_trust_classifier_latest.joblib')

# Predict
y_pred = xgb_model.predict(X_test)
y_proba = xgb_model.predict_proba(X_test)[:, 1]

# Trust Score (using ensemble)
from models.trust.stack_calibrate import compute_trust_score
trust_scores = compute_trust_score(X_test)  # 0-100 scale
```

---

## 🌐 Model Serving

### API Endpoints (kol-api container)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/healthz` | GET | Health check |
| `/predict/trust` | POST | Predict Trust Score |
| `/predict/batch` | POST | Batch prediction |
| `/models/info` | GET | Model metadata |

### Sample API Request

```bash
curl -X POST http://localhost:8000/predict/trust \
  -H "Content-Type: application/json" \
  -d '{
    "kol_id": "user_123",
    "followers_count": 50000,
    "following_count": 1000,
    "post_count": 500,
    "favorites_count": 25000,
    "account_age_days": 730,
    "verified": false,
    "has_bio": true,
    "has_url": true,
    "has_profile_image": true
  }'
```

### Sample Response

```json
{
  "kol_id": "user_123",
  "trust_score": 72.5,
  "is_untrustworthy": false,
  "confidence": 0.89,
  "risk_level": "moderate",
  "top_risk_factors": [
    "high_followers_following_ratio",
    "suspicious_growth_pattern"
  ],
  "recommendation": "Proceed with caution. Manual review recommended."
}
```

---

## 📁 File Structure

```
models/
├── trust/
│   ├── __init__.py
│   ├── data_loader.py           # Load data từ MinIO
│   ├── train_xgb.py             # XGBoost baseline training
│   ├── train_xgb_optuna.py      # XGBoost + Optuna tuning ⭐
│   ├── train_lgbm.py            # LightGBM baseline training
│   ├── train_lgbm_optuna.py     # LightGBM + Optuna tuning ⭐
│   ├── score_iforest.py         # Isolation Forest
│   ├── stack_calibrate.py       # Ensemble stacking
│   ├── evaluate.py              # Model evaluation
│   └── run_optuna_pipeline.py   # Run full Optuna pipeline
├── artifacts/
│   ├── trust/
│   │   ├── xgb_trust_classifier_latest.joblib
│   │   ├── xgb_optuna_model.pkl          # Optuna-tuned XGBoost ⭐
│   │   ├── lgbm_trust_classifier_latest.joblib
│   │   ├── lgbm_optuna_model.pkl         # Optuna-tuned LightGBM ⭐
│   │   ├── lgbm_optuna_model.txt         # Native LightGBM format
│   │   ├── iforest_trust_anomaly_latest.joblib
│   │   ├── ensemble_trust_score_latest_meta.joblib
│   │   └── *_metadata.json
│   └── optuna/
│       ├── xgb_best_params.json          # Best XGBoost params
│       ├── xgb_optuna_study.pkl          # Optuna study object
│       ├── xgb_trials_history.csv        # All trials history
│       ├── lgbm_best_params.json         # Best LightGBM params
│       ├── lgbm_optuna_study.pkl         # Optuna study object
│       └── lgbm_trials_history.csv       # All trials history
└── reports/
    ├── model_comparison.csv
    ├── full_metrics.json
    ├── xgb_optuna_metrics.json           # XGBoost Optuna results
    ├── xgb_optuna_feature_importance.csv
    ├── lgbm_optuna_metrics.json          # LightGBM Optuna results
    └── lgbm_optuna_feature_importance.csv
```

---

## 📊 Model Artifacts

### Saved Files

| File | Size | Description |
|------|------|-------------|
| `xgb_trust_classifier_*.joblib` | ~2MB | XGBoost model |
| `lgbm_trust_classifier_*.joblib` | ~1MB | LightGBM model |
| `lgbm_trust_classifier_*.lgb` | ~500KB | Native LightGBM format |
| `iforest_trust_anomaly_*.joblib` | ~5MB | Isolation Forest |
| `iforest_trust_anomaly_*_scaler.joblib` | ~10KB | StandardScaler |
| `ensemble_trust_score_*_meta.joblib` | ~50KB | Meta-learner |
| `*_metadata.json` | ~5KB | Training metadata |

### Metadata Example

```json
{
  "model_name": "xgb_trust_classifier",
  "version": "20251127_021048",
  "training_date": "2025-11-27T02:10:48",
  "metrics": {
    "accuracy": 0.8742,
    "precision": 0.7957,
    "recall": 0.8354,
    "f1_score": 0.8151,
    "roc_auc": 0.9403
  },
  "feature_count": 29,
  "training_samples": 29950,
  "test_samples": 7488,
  "hyperparameters": {
    "n_estimators": 150,
    "max_depth": 6,
    "learning_rate": 0.1
  }
}
```

---

## 🔮 Future Improvements

### Phase 3: Model Enhancements

- [x] **Hyperparameter Tuning với Optuna** ✅ COMPLETED
  - ✅ 50 trials × 5-fold Stratified CV
  - ✅ TPE (Tree-structured Parzen Estimator) sampler
  - ✅ XGBoost: ROC-AUC 0.9403 → 0.9418 (+0.15%)
  - ✅ LightGBM: ROC-AUC 0.9406 → 0.9423 (+0.17%)

- [ ] **SHAP Analysis**
  - Feature importance visualization
  - Individual prediction explanations

- [ ] **PhoBERT Integration**
  - NLP analysis của bio/content
  - Text-based untrustworthy detection

### Phase 4: MLOps

- [ ] **MLflow Integration**
  - Model versioning
  - Experiment tracking
  - Model registry

- [ ] **Model Monitoring**
  - Drift detection
  - Performance tracking
  - Automated retraining

- [ ] **A/B Testing**
  - Compare model versions
  - Gradual rollout

---

## 📚 References

### Papers & Resources

1. **XGBoost**: Chen & Guestrin (2016). "XGBoost: A Scalable Tree Boosting System"
2. **LightGBM**: Ke et al. (2017). "LightGBM: A Highly Efficient Gradient Boosting Decision Tree"
3. **Isolation Forest**: Liu et al. (2008). "Isolation Forest"
4. **Bot Detection**: Cresci et al. (2020). "A Decade of Social Bot Detection"

### Dataset

- Twitter Human-Bot Detection Dataset (Kaggle)
- Re-mapped for KOL Trust Score prediction

---

*Last Updated: November 27, 2025*
*Author: KOL Analytics Team - IE212 UIT*
*Models trained on: kol-trainer container*
