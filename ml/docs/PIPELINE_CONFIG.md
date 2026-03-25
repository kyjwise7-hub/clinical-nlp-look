# Pipeline Configuration & File Paths

프로젝트 경로, 파이프라인 단계, 파일 구조 문서입니다.

---

## Project Directory Structure

```
final-prj/
├── DATA/
│   ├── raw/
│   │   └── mimic_total.duckdb          # Main database
│   └── processed/                       # Processed CSV outputs
│       ├── sepsis_cohort.csv           # Step 01 output
│       ├── vitals_raw.csv              # Step 02 output
│       ├── labs_raw.csv                # Step 03 output
│       ├── ventilation_raw.csv         # Step 04 output
│       ├── pressor_raw.csv            # Step 05 output
│       ├── urine_raw.csv              # Step 06 output
│       ├── gcs_raw.csv                # Step 07 output
│       ├── windowed_features.csv       # Step 08 output
│       ├── preprocessed.csv            # Step 09 output
│       └── final_dataset.csv           # Step 10 output
│
├── notebooks/
│   ├── (01)_sepsis_cohort.ipynb              # Sepsis cohort definition (Sepsis-3, 18,001명)
│   ├── 01_sepsis_cohort_noscr.ipynb          # Sepsis cohort (스크리닝 없음 변형)
│   ├── 02_vital_raw.ipynb                    # Vitals extraction
│   ├── 03_lab_raw.ipynb                      # Labs extraction
│   ├── 04_ventilation_raw.ipynb              # Ventilation extraction
│   ├── 05_pressor_raw.ipynb                  # Vasopressor extraction
│   ├── 06_urine_raw.ipynb                    # Urine output extraction
│   ├── 07_gcs_raw.ipynb                      # GCS extraction
│   ├── 08_sliding_window_merge.ipynb         # Sliding window aggregation
│   ├── 09_preprocessing.ipynb                # Preprocessing
│   ├── 09-1_preprocessing2.ipynb             # Preprocessing (추가 처리)
│   ├── 10_feature_engineering.ipynb          # Feature engineering & labels
│   ├── 12_xgboost_lightGBM 비교.ipynb        # XGBoost / LightGBM 학습 & 비교
│   ├── 13_risk_scoring.ipynb                 # 위험 등급 분류 & SHAP 기여 요인
│   ├── 14_inference_pipeline.ipynb           # 실시간 추론 파이프라인
│   └── trial/                                # 실험용 (미사용)
│       ├── 11_lgbm_baseline.ipynb
│       └── 12_xgboost_trial.ipynb
│
├── src/
│   ├── __init__.py                      # Package init
│   ├── config.py                        # Centralized configuration (경로, 파라미터, Item IDs)
│   ├── db.py                            # DuckDB utilities
│   └── utils.py                         # Helper functions
│
├── docs/
│   ├── README.md                        # Documentation overview
│   ├── COHORT_DEFINITION.md             # Sepsis cohort definition
│   ├── MIMIC_ITEMIDS.md                 # Item ID reference
│   ├── CLINICAL_PARAMETERS.md           # Clinical thresholds
│   ├── AGGREGATION_RULES.md             # Aggregation methods
│   ├── PIPELINE_CONFIG.md               # This file
│   └── NOTEBOOK_TEMPLATE.md             # Notebook templates
│
├── models/                              # Saved models
├── outputs/                             # Plots, reports, logs
│   └── nbexec/                          # Executed notebook outputs
└── EVAL/                                # Evaluation artifacts
```

---

## Configuration (`src/config.py`)

모든 상수(경로, 파라미터, Item ID)는 `src/config.py`에서 중앙 관리합니다.

```python
import sys; sys.path.append('..')
from src.config import (
    DATA_DIR, RAW_DIR, PROCESSED_DIR, DB_PATH,
    MIN_AGE, MIN_LOS_DAYS, SOFA_THRESHOLD, INFECTION_WINDOW_H,
    WINDOW_SIZE_H, STRIDE_H, MIN_HOUR, MAX_HOUR,
    ITEM_HR, ITEM_LACTATE, VASOPRESSOR_ITEMS, ANTIBIOTIC_ITEMS,
    CLINICAL_RANGES, NORMAL_DEFAULTS,
    # ... 필요한 상수만 import
)
from src.db import get_connection, run_query, register_df
from src.utils import save_csv, load_cohort
```

### 주요 파라미터

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `DATA_DIR` | `Path("DATA")` | 데이터 루트 |
| `DB_PATH` | `DATA/raw/mimic_total.duckdb` | DuckDB 파일 경로 |
| `PROCESSED_DIR` | `DATA/processed` | CSV 출력 경로 |
| `MIN_AGE` | 18 | 성인 기준 연령 |
| `MIN_LOS_DAYS` | 1.0 | 최소 ICU 체류일 |
| `SOFA_THRESHOLD` | 2 | Sepsis-3 SOFA 기준 |
| `INFECTION_WINDOW_H` | 24 | 항생제-배양 동시성 윈도우 (시간) |
| `WINDOW_SIZE_H` | 6 | 슬라이딩 윈도우 크기 (시간) |
| `STRIDE_H` | 1 | 슬라이딩 윈도우 이동 간격 (시간) |
| `MIN_HOUR` | 6 | 윈도우 시작 (ICU 입실 후) |
| `MAX_HOUR` | 72 | 윈도우 종료 |

---

## Pipeline Stages

### Stage 01: Cohort Definition
**Notebook**: `(01)_sepsis_cohort.ipynb`
**Output**: `DATA/processed/sepsis_cohort.csv`
**Cohort**: 18,001명 (Sepsis-3 기준)

**Columns** (31개):
- 기본: `stay_id`, `subject_id`, `hadm_id`, `intime`, `outtime`, `los`
- 인구통계: `anchor_age`, `gender`, `dod`
- 입원: `admittime`, `dischtime`, `deathtime`, `hospital_expire_flag`
- ICU: `first_careunit`, `last_careunit`
- 결과: `icu_mortality`, `hospital_mortality`
- 감염: `suspected_infection_time`, `abx_culture_both`
- SOFA: `sofa_resp`, `sofa_coag`, `sofa_liver`, `sofa_cardio`, `sofa_cns`, `sofa_renal`, `sofa_total`
- 이벤트: `septic_shock_time`, `septic_shock_flag`, `dnr_time`, `vent_start_time`, `pressor_start_time`

**Row Definition**: 1 row = 1 sepsis patient (첫 ICU 입실만)

**관련 노트북**:
- `01_sepsis_cohort_noscr.ipynb`: Sepsis 코호트 변형 (스크리닝 없음)

**상세 정의**: [COHORT_DEFINITION.md](COHORT_DEFINITION.md) 참조

---

### Stage 02-07: Raw Data Extraction

각 단계는 **코호트 환자**에 대해 **ICU 체류 기간 전체**의 데이터를 추출합니다.

| Stage | Notebook | Output | Description | Source Table |
|-------|----------|--------|-------------|--------------|
| 02 | `02_vital_raw.ipynb` | `vitals_raw.csv` | HR, RR, SpO2, Temp, BP | chartevents |
| 03 | `03_lab_raw.ipynb` | `labs_raw.csv` | Lactate, Cr, WBC, Plt, etc. | labevents |
| 04 | `04_ventilation_raw.ipynb` | `ventilation_raw.csv` | Ventilation events | procedureevents |
| 05 | `05_pressor_raw.ipynb` | `pressor_raw.csv` | Vasopressor infusions | inputevents |
| 06 | `06_urine_raw.ipynb` | `urine_raw.csv` | Urine output events | outputevents |
| 07 | `07_gcs_raw.ipynb` | `gcs_raw.csv` | GCS Eye, Verbal, Motor | chartevents |

**Common Columns**: `stay_id`, `charttime` (or `starttime`), `itemid`, `value`/`valuenum`

---

### Stage 08: Sliding Window Aggregation
**Notebook**: `08_sliding_window_merge.ipynb`
**Input**: vitals_raw, labs_raw, gcs_raw, urine_raw, pressor_raw, ventilation_raw
**Output**: `windowed_features.csv`

**Window Parameters** (from `config.py`):
```python
WINDOW_SIZE_H = 6    # 윈도우 크기
STRIDE_H = 1         # 이동 간격
MIN_HOUR = 6         # 시작 (ICU 입실 후)
MAX_HOUR = 72        # 종료
```

**Output Structure**:
- 1 row = 1 window (환자당 ~61개 윈도우)
- Columns: `stay_id`, `window_start`, `window_end`, `hr_mean`, `hr_max`, `spo2_min`, ...

---

### Stage 09: Preprocessing
**Notebook**: `09_preprocessing.ipynb`, `09-1_preprocessing2.ipynb`
**Input**: `windowed_features.csv`
**Output**: `preprocessed.csv`

**Operations**:
1. Missing value imputation (forward fill + clinical defaults)
2. Outlier clipping (`CLINICAL_RANGES`)
3. Feature scaling (StandardScaler / MinMaxScaler)
4. Delta feature calculation

---

### Stage 10: Feature Engineering
**Notebook**: `10_feature_engineering.ipynb`
**Input**: `preprocessed.csv`
**Output**: `final_dataset.csv`

**Operations**:
1. Label generation (6h, 12h, 24h horizons)
2. Censoring (DNR, death, event 발생 후 제외)
3. Train/Validation/Test split (시간 기반)
4. Feature selection (optional)

**Label Horizons**: 6h, 12h, 24h
**Label Events**: death, vent, pressor, septic_shock, composite

---

### Stage 12: Model Training & Comparison
**Notebook**: `12_xgboost_lightGBM 비교.ipynb`
**Input**: `features_final.csv`, `labels_final.csv`
**Output**: `DATA/models/xgb_final_models.pkl`, `DATA/models/lgb_final_models.pkl`, `DATA/models/model_comparison.csv`

**Models**:
- XGBoost (5-fold GroupKFold, OOF AUROC 0.8998)
- LightGBM (3-fold GroupKFold, OOF AUROC 0.8937)

**최종 채택**: XGBoost (AUROC·AUPRC 모두 우세)
**피처 수**: 51개 (고상관 제거 후, SHAP 기반 ablation 확인)
**Evaluation Metrics**: AUROC, AUPRC (GroupKFold OOF)

상세 결과: [MODEL_REPORT.md](MODEL_REPORT.md)

---

### Stage 13: Risk Scoring
**Notebook**: `13_risk_scoring.ipynb`
**Input**: `DATA/models/xgb_final_models.pkl`, `DATA/processed/xgb_selected_features.csv`, OOF 확률값
**Output**: `DATA/processed/risk_thresholds.csv`, 위험 등급 분포 시각화

**위험 등급**: Low / Medium / High (Sensitivity ≥ 0.85 기준 threshold 결정)
**SHAP 기여 요인**: 등급별 Top-3 기여 피처 출력 (lactate↑, BP↓, HR↑, WBC↑ 등)

---

### Stage 14: Inference Pipeline
**Notebook**: `14_inference_pipeline.ipynb`
**Input**: `DATA/models/xgb_final_models.pkl`, `DATA/processed/xgb_selected_features.csv`, `DATA/processed/risk_thresholds.csv`
**Output**: `DATA/processed/feature_medians.csv` (누락 피처 대체값)

**주요 기능** (`SepsisRiskEngine` 클래스):
- `predict_single()`: 단일 환자 1시간 데이터 → 위험 등급
- `predict_batch()`: 배치 추론
- `predict_patient_timeline()`: 특정 환자 전체 시간 흐름 추론

---

## Database Configuration

### DuckDB Connection
**Path**: `DATA/raw/mimic_total.duckdb`

```python
from src.db import get_connection, run_query, register_df

con = get_connection()
df = run_query(con, "SELECT * FROM icustays LIMIT 5")
con.close()
```

### Tables Used
| Table | Description | Key Columns | Join Key |
|-------|-------------|-------------|----------|
| `patients` | 환자 인구통계 | `subject_id`, `gender`, `anchor_age`, `dod` | `subject_id` |
| `admissions` | 입원 정보 | `hadm_id`, `admittime`, `dischtime`, `deathtime` | `hadm_id` |
| `icustays` | ICU 입실 정보 | `stay_id`, `intime`, `outtime`, `los` | `stay_id` |
| `chartevents` | Vital signs, GCS | `stay_id`, `charttime`, `itemid`, `valuenum` | `stay_id` |
| `labevents` | Lab results | `subject_id`, `hadm_id`, `charttime`, `itemid`, `valuenum` | `hadm_id` (NOT stay_id) |
| `inputevents` | IV medications | `stay_id`, `starttime`, `itemid`, `rate`, `amount` | `stay_id` |
| `outputevents` | Output (urine) | `stay_id`, `charttime`, `itemid`, `value` | `stay_id` |
| `procedureevents` | Procedures | `stay_id`, `starttime`, `itemid` | `stay_id` |
| `microbiologyevents` | Cultures | `subject_id`, `hadm_id`, `charttime` | `subject_id` + `hadm_id` |
| `d_items` | Item ID dictionary | `itemid`, `label`, `category` | - |

**주의**: `labevents`는 `stay_id`가 없음. 반드시 `hadm_id`로 조인.

---

## Helper Functions

### src/db.py
```python
get_connection(db_path=None, read_only=False)
# DuckDB 연결 생성

run_query(con, query)
# SQL 실행 -> DataFrame 반환

register_df(con, name, df)
# DataFrame을 DuckDB 임시 테이블로 등록 (StringDtype 자동 변환)

load_sql(filename)
# sql/ 폴더에서 .sql 파일 읽기

list_tables(con)
# 테이블 목록 조회
```

### src/utils.py
```python
save_csv(df, filename)
# DataFrame을 DATA/processed/ 폴더에 저장

load_cohort(filename, parse_dates=None)
# DATA/processed/ 폴더에서 CSV 로드

items_to_sql(item_list)
# ['123', '456'] -> "'123','456'" (SQL IN 절용)

clip_clinical(df, col, ranges)
# 임상 범위 밖 -> NaN 처리

print_missing(df, cols=None)
# 피처별 결측률 출력

print_label_dist(df, label_prefix)
# 레이블 분포 출력

check_duplicates(df, key_cols)
# 중복 행 확인

ffill_bfill(df, col, group_col='stay_id')
# 환자별 Forward Fill -> Backward Fill

ffill_with_limit(df, col, limit, group_col='stay_id')
# 환자별 Forward Fill (제한 있음)

impute_pipeline(df, col, strategy, ffill_limit, default_value, group_col)
# 통합 결측 처리 파이프라인
# strategy: 'ffill_bfill_median', 'ffill_limit_median', 'ffill_limit_default', 'median_only'

hours_since_admit(df, time_col, admit_col)
# 입실 시점 대비 경과 시간 계산
```

---

## Output File Specifications

### CSV File Conventions
- **Encoding**: UTF-8
- **Separator**: `,` (comma)
- **Date Format**: ISO 8601 (`YYYY-MM-DD HH:MM:SS`)
- **Missing Values**: Empty string (pandas default)
- **Save Location**: `DATA/processed/`

---

## 참고

- 모든 경로는 `Path("DATA")` 기준
- 모든 상수/파라미터는 `src/config.py`에서 관리
- Item ID 상세: [MIMIC_ITEMIDS.md](MIMIC_ITEMIDS.md)
- 임상 파라미터: [CLINICAL_PARAMETERS.md](CLINICAL_PARAMETERS.md)
- 집계 규칙: [AGGREGATION_RULES.md](AGGREGATION_RULES.md)
- 코호트 정의: [COHORT_DEFINITION.md](COHORT_DEFINITION.md)
