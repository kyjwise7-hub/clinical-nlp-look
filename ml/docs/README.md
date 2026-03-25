# Documentation Overview

MIMIC-IV 기반 패혈증(Sepsis) 예측 파이프라인 문서 모음

---

## 문서 목록

### 핵심 참조 문서

| 문서 | 내용 | 사용 시점 |
|-----|------|---------|
| **[COHORT_DEFINITION.md](COHORT_DEFINITION.md)** | Sepsis-3 코호트 정의서 (포함/제외 기준, SOFA, 통계) | 코호트 이해, 논문 작성 시 |
| **[MIMIC_ITEMIDS.md](MIMIC_ITEMIDS.md)** | MIMIC-IV Item ID 매핑 테이블 | 데이터 추출 시 |
| **[CLINICAL_PARAMETERS.md](CLINICAL_PARAMETERS.md)** | 임상 기준값, 정상 범위, SOFA 스코어 | 코호트 정의, 전처리 시 |
| **[AGGREGATION_RULES.md](AGGREGATION_RULES.md)** | 시계열 집계 규칙, 윈도우 설정 | 슬라이딩 윈도우 생성 시 |
| **[PIPELINE_CONFIG.md](PIPELINE_CONFIG.md)** | 파이프라인 구조, 파일 경로, Helper 함수 | 프로젝트 전반 |

### 가이드 문서

| 문서 | 내용 |
|-----|------|
| **[NOTEBOOK_TEMPLATE.md](NOTEBOOK_TEMPLATE.md)** | 노트북별 설정 템플릿 (config.py import) |
| **[CONFIGURATION_MIGRATION.md](CONFIGURATION_MIGRATION.md)** | config.py 및 src/ 모듈 구성 가이드 |
| **[README.md](README.md)** | 이 문서 |

---

## 빠른 시작

### 새 노트북 작성 시

1. **[NOTEBOOK_TEMPLATE.md](NOTEBOOK_TEMPLATE.md)** 에서 해당 단계의 템플릿 복사
2. 노트북 첫 번째 셀에 붙여넣기
3. `src/config.py`에서 필요한 상수 import

```python
import sys; sys.path.append('..')
from src.config import (
    MIN_AGE, SOFA_THRESHOLD,
    ITEM_LACTATE, VASOPRESSOR_ITEMS,
    CLINICAL_RANGES,
)
from src.db import get_connection, run_query, register_df
from src.utils import save_csv, load_cohort
```

---

## 파이프라인 흐름

```
(01)_sepsis_cohort (Sepsis-3 코호트 정의, 18,001명)
    |
    v
02_vital_raw -> 03_lab_raw -> 04_ventilation_raw
    -> 05_pressor_raw -> 06_urine_raw -> 07_gcs_raw
    |
    v
08_sliding_window_merge (6h window, 1h stride, 6-72h)
    |
    v
09_preprocessing / 09-1_preprocessing2 (클리핑, 결측 처리, 스케일링)
    |
    v
10_feature_engineering (레이블 생성, censoring, split)
    |
    v
12_xgboost_lightGBM 비교 (XGBoost / LightGBM 학습 & 비교, 최종 채택: XGBoost)
    |
    v
13_risk_scoring (위험 등급 분류 Low/Medium/High, SHAP 기여 요인)
    |
    v
14_inference_pipeline (실시간 1시간 단위 추론, SepsisRiskEngine)
```

상세: [PIPELINE_CONFIG.md](PIPELINE_CONFIG.md) 참조

---

## 설정 관리

모든 상수는 `src/config.py`에서 중앙 관리합니다:
- **경로**: `DATA_DIR`, `DB_PATH`, `PROCESSED_DIR`
- **코호트 기준**: `MIN_AGE`, `SOFA_THRESHOLD`, `INFECTION_WINDOW_H`
- **슬라이딩 윈도우**: `WINDOW_SIZE_H`, `STRIDE_H`, `MIN_HOUR`, `MAX_HOUR`
- **Item IDs**: `ITEM_HR`, `ITEM_LACTATE`, `VASOPRESSOR_ITEMS`, etc.
- **임상 범위**: `CLINICAL_RANGES`, `NORMAL_DEFAULTS`

상세: [CONFIGURATION_MIGRATION.md](CONFIGURATION_MIGRATION.md) 참조

---

## 빠른 참조

| 목적 | 문서 |
|------|------|
| 코호트 정의 이해 | [COHORT_DEFINITION.md](COHORT_DEFINITION.md) |
| Item ID 찾기 | [MIMIC_ITEMIDS.md](MIMIC_ITEMIDS.md) |
| 임상 기준값 확인 | [CLINICAL_PARAMETERS.md](CLINICAL_PARAMETERS.md) |
| 데이터 집계 방법 | [AGGREGATION_RULES.md](AGGREGATION_RULES.md) |
| 파일 경로/파이프라인 | [PIPELINE_CONFIG.md](PIPELINE_CONFIG.md) |
| 노트북 템플릿 | [NOTEBOOK_TEMPLATE.md](NOTEBOOK_TEMPLATE.md) |
| config/src 구성 | [CONFIGURATION_MIGRATION.md](CONFIGURATION_MIGRATION.md) |

---

## Item ID 검색 팁

```python
# DuckDB에서 직접 검색
from src.db import get_connection, run_query

con = get_connection()
df = run_query(con, """
    SELECT itemid, label, category
    FROM d_items
    WHERE label ILIKE '%lactate%'
""")
print(df)
```

---

## 파일 구조

```
docs/
├── README.md                        # 이 문서
├── COHORT_DEFINITION.md             # 코호트 정의서
├── MIMIC_ITEMIDS.md                 # Item ID 참조
├── CLINICAL_PARAMETERS.md           # 임상 파라미터
├── AGGREGATION_RULES.md             # 집계 규칙
├── PIPELINE_CONFIG.md               # 파이프라인 구조
├── NOTEBOOK_TEMPLATE.md             # 노트북 템플릿
└── CONFIGURATION_MIGRATION.md       # 설정 가이드
```

---

**최종 업데이트**: 2026-02-21
