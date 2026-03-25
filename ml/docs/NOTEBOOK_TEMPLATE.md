# Notebook Configuration Template

노트북 시작 부분에 사용할 설정 템플릿입니다.
모든 상수는 `src/config.py`에서 중앙 관리하며, 각 노트북에서 필요한 것만 import합니다.

---

## 기본 템플릿

모든 노트북의 첫 번째 셀에 다음 코드를 사용하세요:

```python
import sys; sys.path.append('..')

from src.config import DATA_DIR, PROCESSED_DIR, DB_PATH
from src.db import get_connection, run_query, register_df
from src.utils import save_csv, load_cohort

con = get_connection()
print("=== [노트북 제목] 시작 ===")
```

---

## 01. Sepsis Cohort 노트북

```python
import sys; sys.path.append('..')

from src.config import (
    DATA_DIR, MIN_AGE, MIN_LOS_DAYS, SOFA_THRESHOLD, INFECTION_WINDOW_H,
    ANTIBIOTIC_ITEMS, VASOPRESSOR_ITEMS,
    ITEM_PAO2, ITEM_FIO2, ITEM_PLATELETS, ITEM_BILIRUBIN,
    ITEM_ABP_MEAN, ITEM_NBP_MEAN,
    ITEM_NOREPINEPHRINE, ITEM_EPINEPHRINE, ITEM_DOPAMINE,
    ITEM_GCS_EYE, ITEM_GCS_VERBAL, ITEM_GCS_MOTOR,
    ITEM_CREATININE, ITEM_LACTATE,
    ITEM_VENT, ITEM_DNR,
)
from src.db import get_connection, run_query, register_df
from src.utils import save_csv, items_to_sql

con = get_connection()
print("=== 01. Sepsis Cohort 생성 시작 ===")
```

---

## 02-07. Raw Data Extraction 노트북

각 단계에서 필요한 Item ID만 import합니다:

```python
import sys; sys.path.append('..')

# 02: Vitals
from src.config import (
    ITEM_HR, ITEM_RR, ITEM_SPO2, ITEM_TEMP_C, ITEM_TEMP_F,
    ITEM_NBP_SYS, ITEM_NBP_DIA, ITEM_NBP_MEAN,
    ITEM_ABP_SYS, ITEM_ABP_DIA, ITEM_ABP_MEAN,
    ITEM_FIO2, ITEM_WEIGHT,
    CLINICAL_RANGES,
)

# 03: Labs
from src.config import (
    ITEM_LACTATE, ITEM_CREATININE, ITEM_WBC, ITEM_PLATELETS,
    ITEM_POTASSIUM, ITEM_SODIUM, ITEM_BILIRUBIN,
    ITEM_SAO2, ITEM_PH, ITEM_PAO2,
    CLINICAL_RANGES,
)

# 04: Ventilation -> ITEM_VENT
# 05: Pressor -> VASOPRESSOR_ITEMS
# 06: Urine -> URINE_ITEMS
# 07: GCS -> ITEM_GCS_EYE, ITEM_GCS_VERBAL, ITEM_GCS_MOTOR

from src.db import get_connection, run_query, register_df
from src.utils import save_csv, load_cohort, items_to_sql

con = get_connection()
df_cohort = load_cohort('sepsis_cohort.csv')

print(f"=== [데이터 추출] 시작 ===")
print(f"  코호트: {len(df_cohort):,}명")
```

---

## 08. Sliding Window 노트북

```python
import sys; sys.path.append('..')

from src.config import WINDOW_SIZE_H, STRIDE_H, MIN_HOUR, MAX_HOUR
from src.utils import load_cohort, save_csv

print("=== 08. Sliding Window Aggregation 시작 ===")

df_cohort = load_cohort('sepsis_cohort.csv', parse_dates=['intime', 'outtime'])
df_vitals = load_cohort('vitals_raw.csv', parse_dates=['charttime'])
df_labs = load_cohort('labs_raw.csv', parse_dates=['charttime'])
# ... 필요한 raw 데이터 추가 로드

print(f"  윈도우 설정: {WINDOW_SIZE_H}h 크기, {STRIDE_H}h stride")
print(f"  시간 범위: {MIN_HOUR}h ~ {MAX_HOUR}h")
```

---

## 09. Preprocessing 노트북

```python
import sys; sys.path.append('..')

from src.config import CLINICAL_RANGES, NORMAL_DEFAULTS
from src.utils import (
    load_cohort, save_csv, print_missing,
    clip_clinical, impute_pipeline,
)

print("=== 09. Preprocessing 시작 ===")

df = load_cohort('windowed_features.csv')
print_missing(df)
```

---

## 10. Feature Engineering & Label Generation

```python
import sys; sys.path.append('..')

from src.config import LABEL_HORIZONS, LABEL_EVENTS, DELTA_FEATURES
from src.utils import load_cohort, save_csv, print_label_dist

print("=== 10. Feature Engineering & Label Generation 시작 ===")

df = load_cohort('preprocessed.csv', parse_dates=['window_start', 'window_end'])
df_cohort = load_cohort('sepsis_cohort.csv', parse_dates=[
    'intime', 'outtime', 'deathtime', 'dnr_time',
    'vent_start_time', 'pressor_start_time', 'septic_shock_time'
])

print(f"  Horizons: {LABEL_HORIZONS}")
print(f"  Events: {LABEL_EVENTS}")
```

---

## 12. XGBoost vs LightGBM 비교

```python
import sys; sys.path.append('..')

import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
import shap
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, average_precision_score
from pathlib import Path

DATA_DIR      = Path('DATA')
PROCESSED_DIR = DATA_DIR / 'processed'
MODEL_DIR     = DATA_DIR / 'models'

TARGET_LABEL = 'composite_next_24h'
RANDOM_STATE = 42

print("=== 12. XGBoost vs LightGBM 비교 시작 ===")

df_features = pd.read_csv(PROCESSED_DIR / 'features_final.csv')
df_labels   = pd.read_csv(PROCESSED_DIR / 'labels_final.csv')
```

---

## 13. Risk Scoring

```python
import sys; sys.path.append('..')

import pickle
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import shap
from pathlib import Path

DATA_DIR      = Path('DATA')
PROCESSED_DIR = DATA_DIR / 'processed'
MODEL_DIR     = DATA_DIR / 'models'

print("=== 13. Risk Scoring 시작 ===")

df_features  = pd.read_csv(PROCESSED_DIR / 'features_final.csv')
df_labels    = pd.read_csv(PROCESSED_DIR / 'labels_final.csv')
feat_cols    = pd.read_csv(PROCESSED_DIR / 'xgb_selected_features.csv')['feature'].tolist()
models       = pickle.load(open(MODEL_DIR / 'xgb_final_models.pkl', 'rb'))
oof_prob     = np.load(MODEL_DIR / 'xgb_oof_prob.npy')
```

---

## 14. Inference Pipeline

```python
import sys; sys.path.append('..')

import pickle
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR      = Path('DATA')
PROCESSED_DIR = DATA_DIR / 'processed'
MODEL_DIR     = DATA_DIR / 'models'

print("=== 14. Inference Pipeline 시작 ===")

# SepsisRiskEngine 사용 예시
# engine = SepsisRiskEngine(
#     model_path     = MODEL_DIR / 'xgb_final_models.pkl',
#     feature_path   = PROCESSED_DIR / 'xgb_selected_features.csv',
#     threshold_path = PROCESSED_DIR / 'risk_thresholds.csv',
# )
# result = engine.predict_single(patient_features_df)
```

---

## 참고

- 모든 상수/파라미터: `src/config.py`
- Item IDs: [MIMIC_ITEMIDS.md](MIMIC_ITEMIDS.md)
- Clinical Parameters: [CLINICAL_PARAMETERS.md](CLINICAL_PARAMETERS.md)
- Aggregation Rules: [AGGREGATION_RULES.md](AGGREGATION_RULES.md)
- Pipeline Config: [PIPELINE_CONFIG.md](PIPELINE_CONFIG.md)
