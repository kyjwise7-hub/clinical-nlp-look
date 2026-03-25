# Configuration Guide

`src/config.py`를 통한 중앙 집중 설정 관리 가이드

---

## 설정 구조

모든 상수(경로, 파라미터, Item ID)는 `src/config.py`에서 관리합니다.

```python
# 노트북에서 사용
import sys; sys.path.append('..')
from src.config import (
    MIN_AGE, SOFA_THRESHOLD, ITEM_HR, ITEM_LACTATE,
    CLINICAL_RANGES, VASOPRESSOR_ITEMS, ...
)
```

### config.py 구성

| 섹션 | 내용 | 참조 문서 |
|------|------|-----------|
| **경로** | `DATA_DIR`, `DB_PATH`, `PROCESSED_DIR`, `MODEL_DIR`, `OUTPUT_DIR` | [PIPELINE_CONFIG.md](PIPELINE_CONFIG.md) |
| **슬라이딩 윈도우** | `WINDOW_SIZE_H`, `STRIDE_H`, `MIN_HOUR`, `MAX_HOUR` | [AGGREGATION_RULES.md](AGGREGATION_RULES.md) |
| **코호트 기준** | `MIN_AGE`, `MIN_LOS_DAYS`, `SOFA_THRESHOLD`, `INFECTION_WINDOW_H` | [CLINICAL_PARAMETERS.md](CLINICAL_PARAMETERS.md) |
| **Item IDs** | Vitals, Labs, GCS, Vasopressors, Antibiotics, etc. | [MIMIC_ITEMIDS.md](MIMIC_ITEMIDS.md) |
| **임상 범위** | `CLINICAL_RANGES` (이상치 클리핑) | [CLINICAL_PARAMETERS.md](CLINICAL_PARAMETERS.md) |
| **결측 기본값** | `NORMAL_DEFAULTS` (temp, lactate, fio2) | [CLINICAL_PARAMETERS.md](CLINICAL_PARAMETERS.md) |
| **피처 그룹** | `VITAL_COLS`, `LAB_COLS`, `GCS_COLS`, `URINE_COLS`, `DELTA_FEATURES`, `SLOPE_FEATURES`, etc. | [AGGREGATION_RULES.md](AGGREGATION_RULES.md) |
| **레이블** | `LABEL_HORIZONS`, `LABEL_EVENTS` | [AGGREGATION_RULES.md](AGGREGATION_RULES.md) |

---

## src/ 모듈 구성

### src/config.py
중앙 설정 파일. 모든 노트북에서 import하여 사용.

### src/db.py
DuckDB 연결 및 쿼리 헬퍼.
- `get_connection()`: DuckDB 연결 생성
- `run_query(con, query)`: SQL 실행 -> DataFrame
- `register_df(con, name, df)`: DataFrame -> DuckDB 테이블 등록 (StringDtype 자동 처리)
- `load_sql(filename)`: SQL 파일 로드
- `list_tables(con)`: 테이블 목록

### src/utils.py
공통 유틸리티 함수.
- 로드/저장: `load_cohort()`, `save_csv()`
- 품질: `print_missing()`, `print_label_dist()`, `check_duplicates()`
- 클리핑: `clip_clinical(df, col, ranges)`
- 결측: `ffill_bfill()`, `ffill_with_limit()`, `impute_pipeline()`
- SQL: `items_to_sql()`
- 시간: `hours_since_admit()`

---

## 사용 예시

### 코호트 노트북
```python
import sys; sys.path.append('..')
from src.config import (
    MIN_AGE, MIN_LOS_DAYS, SOFA_THRESHOLD, INFECTION_WINDOW_H,
    ANTIBIOTIC_ITEMS, VASOPRESSOR_ITEMS,
    ITEM_LACTATE, ITEM_CREATININE, ITEM_VENT, ITEM_DNR,
)
from src.db import get_connection, run_query, register_df
from src.utils import save_csv, items_to_sql

con = get_connection()
```

### 전처리 노트북
```python
import sys; sys.path.append('..')
from src.config import CLINICAL_RANGES, NORMAL_DEFAULTS
from src.utils import load_cohort, save_csv, clip_clinical

df = load_cohort('windowed_features.csv')

for col, (lo, hi) in CLINICAL_RANGES.items():
    if col in df.columns:
        df[col] = clip_clinical(df, col, CLINICAL_RANGES)
```

---

## 설정값 변경 시

1. `src/config.py`에서 값 수정
2. 해당 docs/ 문서도 함께 업데이트
3. 노트북 재실행

---

## 문서 참조 가이드

| 목적 | 문서 |
|------|------|
| Item ID 찾기 | [MIMIC_ITEMIDS.md](MIMIC_ITEMIDS.md) |
| 임상 기준값 확인 | [CLINICAL_PARAMETERS.md](CLINICAL_PARAMETERS.md) |
| 집계 방법 확인 | [AGGREGATION_RULES.md](AGGREGATION_RULES.md) |
| 파이프라인/경로 확인 | [PIPELINE_CONFIG.md](PIPELINE_CONFIG.md) |
| 노트북 템플릿 | [NOTEBOOK_TEMPLATE.md](NOTEBOOK_TEMPLATE.md) |
| 코호트 정의 | [COHORT_DEFINITION.md](COHORT_DEFINITION.md) |
