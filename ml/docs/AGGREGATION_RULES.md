# Data Aggregation Rules

시계열 데이터를 슬라이딩 윈도우로 집계하는 규칙 문서입니다.

---

## 🪟 Sliding Window Configuration

### Window Parameters
| Parameter | Value | Description |
|-----------|-------|-------------|
| **Window Size** | 6시간 | 한 윈도우가 커버하는 시간 범위 |
| **Stride** | 1시간 | 윈도우 이동 간격 |
| **Start Time** | ICU 입실 후 6시간 | 첫 윈도우 시작점 |
| **End Time** | ICU 입실 후 72시간 | 마지막 윈도우 종료점 |

### Window Timeline
```
ICU Admission (t=0)
    │
    ├─ t=6h  ───┬──── Window 1 ────┬─ t=12h
    │           └─ 6h 데이터 집계 ─┘
    │
    ├─ t=7h  ───┬──── Window 2 ────┬─ t=13h
    │           └─ 6h 데이터 집계 ─┘
    │
    ⋮
    │
    └─ t=72h (종료)
```

**총 윈도우 개수**: (72 - 6 - 6) / 1 + 1 = **61개** (환자당)

---

## 📊 Aggregation Methods by Variable Type

### 1. Vital Signs (연속 측정값)

#### High-Frequency Variables
- **Source**: chartevents
- **Typical Frequency**: 1-5분마다 측정

| Variable | Aggregation | Rationale |
|----------|-------------|-----------|
| Heart Rate | `mean`, `max`, `std` | 평균/최고값/변동성 |
| Respiratory Rate | `mean`, `max` | 평균/최고값 |
| SpO2 | `mean`, `min` | 평균/최저값 (저산소증 감지) |
| Temperature | `mean`, `max` | 평균/최고값 (발열) |
| SBP | `mean`, `min`, `std` | 평균/최저값/변동성 (쇼크) |
| DBP | `mean`, `min` | 평균/최저값 |
| MBP | `mean`, `min` | 평균/최저값 |

**Aggregation SQL Example**:
```sql
SELECT
    stay_id,
    window_start,
    AVG(hr) as hr_mean,
    MAX(hr) as hr_max,
    STDDEV(hr) as hr_std,
    MIN(spo2) as spo2_min,
    AVG(spo2) as spo2_mean
FROM chartevents_cleaned
WHERE charttime >= window_start
  AND charttime < window_end
GROUP BY stay_id, window_start
```

---

### 2. Laboratory Values (간헐적 측정)

#### Low-Frequency Variables
- **Source**: labevents
- **Typical Frequency**: 수시간~하루 단위

| Variable | Aggregation | Strategy |
|----------|-------------|----------|
| Lactate | `max`, `last` | 최고값/최근값 (악화 감지) |
| Creatinine | `max`, `last` | 최고값/최근값 (신부전) |
| WBC | `max`, `last` | 최고값/최근값 (감염) |
| Platelets | `min`, `last` | 최저값/최근값 (응고) |
| Bilirubin | `max`, `last` | 최고값/최근값 (간부전) |
| Potassium | `mean`, `max`, `min` | 평균/최고/최저 (전해질 이상) |
| Sodium | `mean`, `max`, `min` | 평균/최고/최저 |

**Forward Fill Strategy**:
- 윈도우 내 측정값이 없으면 **이전 윈도우의 last 값** 사용
- 최대 24시간까지 carry forward

**Aggregation with Forward Fill**:
```sql
WITH lab_with_window AS (
    SELECT
        stay_id,
        window_start,
        MAX(lactate) as lactate_max,
        MAX(charttime) as last_measurement
    FROM labevents_cleaned
    WHERE charttime >= window_start
      AND charttime < window_end
    GROUP BY stay_id, window_start
),
filled AS (
    SELECT
        stay_id,
        window_start,
        COALESCE(
            lactate_max,
            LAG(lactate_max) OVER (PARTITION BY stay_id ORDER BY window_start)
        ) as lactate_max
    FROM lab_with_window
)
SELECT * FROM filled
```

---

### 3. Glasgow Coma Scale (GCS)

| Component | Aggregation | Note |
|-----------|-------------|------|
| GCS Eye | `min` | 최악의 상태 |
| GCS Verbal | `min` | 최악의 상태 |
| GCS Motor | `min` | 최악의 상태 |
| **GCS Total** | `min` | Eye + Verbal + Motor의 최소값 |

**Missing Component Handling**:
- Eye 결측 → 4 (정상)
- Verbal 결측 → 5 (정상)
- Motor 결측 → 6 (정상)

---

### 4. Urine Output (누적값 → 시간당 변환)

#### Calculation Steps
1. **윈도우 내 총 소변량 집계** (outputevents)
2. **체중 보정** (mL/kg)
3. **시간당 변환** (mL/kg/hr)

| Variable | Aggregation | Formula |
|----------|-------------|---------|
| Urine (6h total) | `sum` | ∑(윈도우 내 output) |
| Urine (per kg per hr) | `mean` | total_ml / (weight_kg × 6h) |
| Oliguria Flag | `binary` | 1 if <0.5 mL/kg/hr else 0 |

**SQL Example**:
```sql
WITH urine_6h AS (
    SELECT
        o.stay_id,
        window_start,
        SUM(o.value) as total_ml,
        AVG(c.weight) as weight_kg
    FROM outputevents o
    JOIN cohort c ON o.stay_id = c.stay_id
    WHERE o.charttime >= window_start
      AND o.charttime < window_end
      AND o.itemid IN ('226559', '226560')
    GROUP BY o.stay_id, window_start
)
SELECT
    stay_id,
    window_start,
    total_ml,
    total_ml / (weight_kg * 6) as ml_kg_hr,
    CASE WHEN total_ml / (weight_kg * 6) < 0.5 THEN 1 ELSE 0 END as oliguria_flag
FROM urine_6h
```

---

### 5. Medications (Binary Flags)

#### Vasopressors & Antibiotics
- **Aggregation**: `any()` - 윈도우 내 한 번이라도 투여 여부

| Variable | Aggregation | Value |
|----------|-------------|-------|
| Norepinephrine | `binary` | 1 if any rate >0 else 0 |
| Epinephrine | `binary` | 1 if any rate >0 else 0 |
| Dopamine | `binary` | 1 if any rate >0 else 0 |
| Vasopressin | `binary` | 1 if any rate >0 else 0 |
| **Any Vasopressor** | `binary` | OR of above |

**SQL Example**:
```sql
SELECT
    stay_id,
    window_start,
    MAX(CASE WHEN itemid = '221906' AND rate > 0 THEN 1 ELSE 0 END) as norepi_flag,
    MAX(CASE WHEN itemid = '221289' AND rate > 0 THEN 1 ELSE 0 END) as epi_flag,
    -- OR condition
    CASE WHEN MAX(CASE WHEN itemid IN ('221906','221289','221662','222315')
                        AND rate > 0 THEN 1 ELSE 0 END) = 1
         THEN 1 ELSE 0 END as any_vasopressor
FROM inputevents
WHERE starttime >= window_start AND starttime < window_end
GROUP BY stay_id, window_start
```

---

### 6. Ventilation (Binary Flag)

| Variable | Aggregation | Value |
|----------|-------------|-------|
| Mechanical Ventilation | `binary` | 1 if vent event exists in window else 0 |

---

## 🔄 Temporal Features (Delta / Slope)

### Delta Features (변화량)
**이전 윈도우 대비 변화**를 계산하여 악화/호전 추세 파악

| Variable | Delta Formula |
|----------|---------------|
| HR Delta | `hr_mean(t) - hr_mean(t-1)` |
| SBP Delta | `sbp_mean(t) - sbp_mean(t-1)` |
| SpO2 Delta | `spo2_mean(t) - spo2_mean(t-1)` |
| Lactate Delta | `lactate_max(t) - lactate_max(t-1)` |
| GCS Delta | `gcs_total(t) - gcs_total(t-1)` |

**Interpretation**:
- Negative delta → 악화 (HR 증가, SBP/SpO2/GCS 감소 등)
- Positive delta → 호전

**SQL Example**:
```sql
WITH agg AS (
    SELECT stay_id, window_start,
           AVG(hr) as hr_mean,
           AVG(sbp) as sbp_mean
    FROM vitals
    GROUP BY stay_id, window_start
)
SELECT
    stay_id,
    window_start,
    hr_mean,
    hr_mean - LAG(hr_mean) OVER (PARTITION BY stay_id ORDER BY window_start) as hr_delta,
    sbp_mean,
    sbp_mean - LAG(sbp_mean) OVER (PARTITION BY stay_id ORDER BY window_start) as sbp_delta
FROM agg
```

### Slope Features (추세 기울기)
**윈도우 내부에서의 시간-값 선형 기울기**로 추세를 포착합니다.

| Variable | Slope Formula (OLS) |
|----------|----------------------|
| HR Slope | `slope(hr, t)` |
| SBP Slope | `slope(sbp, t)` |
| SpO2 Slope | `slope(spo2, t)` |
| Lactate Slope | `slope(lactate, t)` |
| GCS Total Slope | `slope(gcs_total, t)` |

**정의**:
- `t` = window 내 측정 시각 (hours since admit, 연속값)
- `slope(x, t) = Σ((t - t_bar)(x - x_bar)) / Σ((t - t_bar)^2)`
- 단위: `value / hour`

**결측/측정 부족 처리**:
- window 내 유효 측정값이 2개 미만이면 `0`으로 설정 (이후 전처리/모델에서 안정적으로 처리)

**Python Example**:
```python
def slope_in_window(t, x):
    mask = ~np.isnan(t) & ~np.isnan(x)
    t = t[mask]; x = x[mask]
    if len(t) < 2:
        return 0.0
    t_mean = t.mean()
    x_mean = x.mean()
    denom = ((t - t_mean) ** 2).sum()
    return 0.0 if denom == 0 else ((t - t_mean) * (x - x_mean)).sum() / denom
```

---

## 🏷️ Label Generation (Prediction Targets)

### Label Horizons: 6h, 12h, 24h

각 윈도우 종료 시점(`window_end`)으로부터 **N시간 후 발생 여부**

#### 1. Death (ICU Mortality)
```sql
CASE WHEN deathtime IS NOT NULL
          AND deathtime > window_end
          AND deathtime <= window_end + INTERVAL '6' HOUR
     THEN 1 ELSE 0 END as death_6h
```

#### 2. Ventilation Initiation
```sql
CASE WHEN vent_start_time IS NOT NULL
          AND vent_start_time > window_end
          AND vent_start_time <= window_end + INTERVAL '6' HOUR
     THEN 1 ELSE 0 END as vent_6h
```

#### 3. Vasopressor Initiation
```sql
CASE WHEN pressor_start_time IS NOT NULL
          AND pressor_start_time > window_end
          AND pressor_start_time <= window_end + INTERVAL '6' HOUR
     THEN 1 ELSE 0 END as pressor_6h
```

#### 4. Septic Shock
```sql
CASE WHEN septic_shock_time IS NOT NULL
          AND septic_shock_time > window_end
          AND septic_shock_time <= window_end + INTERVAL '6' HOUR
     THEN 1 ELSE 0 END as shock_6h
```

#### 5. Composite Outcome (Any of Above)
```sql
CASE WHEN death_6h = 1 OR vent_6h = 1 OR pressor_6h = 1 OR shock_6h = 1
     THEN 1 ELSE 0 END as composite_6h
```

---

## 🚫 Censoring Rules (윈도우 제외 규칙)

아래 조건을 만족하면 해당 윈도우는 **제외**:

| Event | Censoring Rule | Rationale |
|-------|----------------|-----------|
| **Death** | `deathtime <= window_end` | 이미 사망 |
| **DNR Order** | `dnr_time <= window_end` | 적극 치료 중단 |
| **Ventilation** | `vent_start_time <= window_end` | 이미 기계환기 중 (vent 예측 시) |
| **Vasopressor** | `pressor_start_time <= window_end` | 이미 승압제 사용 중 (pressor 예측 시) |
| **Septic Shock** | `septic_shock_time <= window_end` | 이미 쇼크 상태 (shock 예측 시) |

**Censoring SQL**:
```sql
WHERE 1=1
  AND (deathtime IS NULL OR deathtime > window_end)
  AND (dnr_time IS NULL OR dnr_time > window_end)
  -- outcome별 추가 조건
  AND (vent_start_time IS NULL OR vent_start_time > window_end)  -- for vent prediction
```

---

## Final Feature Set Summary

### Feature Groups (`src/config.py` 참조)
| Group | Config 변수 | Aggregation Types |
|-------|------------|-------------------|
| **Vitals** | `VITAL_COLS` = hr, rr, spo2, sbp, dbp, mbp, temp | mean, max, min, std |
| **Vital Stats** | `VITAL_STAT_COLS` = hr_max, rr_max, spo2_min, sbp_min | derived |
| **Labs** | `LAB_COLS` = creatinine, wbc, platelets, potassium, sodium, lactate | max, min, last, (forward-filled) |
| **GCS** | `GCS_COLS` = gcs_eye, gcs_verbal, gcs_motor, gcs_total | min (worst value) |
| **Urine** | `URINE_COLS` = urine_ml_6h, urine_ml_kg_hr_avg, oliguria_flag | sum, rate, flag |
| **Flags** | `FLAG_COLS` = lactate_missing, abga_checked | binary |
| **Delta** | `DELTA_FEATURES` = hr, sbp, spo2, lactate, gcs_total | t - (t-1) |
| **Slope** | `SLOPE_FEATURES` = hr, sbp, spo2, lactate, gcs_total | window 내 OLS slope |
| **Static** | - | age, gender, weight |

**Total**: ~50+ features per window (delta + slope 포함)

---

## 📝 Example Pipeline

```python
# Step 1: Raw data extraction
vitals = extract_vitals(stay_id, window_start, window_end)
labs = extract_labs(stay_id, window_start, window_end)

# Step 2: Aggregation
vitals_agg = vitals.groupby(['stay_id','window_start']).agg({
    'hr': ['mean', 'max', 'std'],
    'spo2': ['mean', 'min'],
    'sbp': ['mean', 'min', 'std']
})

labs_agg = labs.groupby(['stay_id','window_start']).agg({
    'lactate': ['max', 'last'],
    'creatinine': ['max', 'last']
})

# Step 3: Forward fill
labs_filled = labs_agg.groupby('stay_id').ffill(limit=24)

# Step 4: Delta features
vitals_agg['hr_delta'] = vitals_agg.groupby('stay_id')['hr_mean'].diff()

# Step 5: Label generation
labels = generate_labels(window_end, events, horizons=[6,12,24])

# Step 6: Censoring
final_data = final_data[
    (final_data['deathtime'].isna() | (final_data['deathtime'] > final_data['window_end']))
]
```

---

## 참고

- 본 규칙은 MIMIC-IV 데이터 특성에 최적화되어 있습니다
- 집계 방법은 임상적 의미를 반영하여 설계되었습니다
- 윈도우 파라미터는 `src/config.py`에서 관리 (`WINDOW_SIZE_H`, `STRIDE_H`, `MIN_HOUR`, `MAX_HOUR`)
- 피처 그룹 정의도 `src/config.py`에서 관리 (`VITAL_COLS`, `LAB_COLS`, etc.)
- 관련 문서: [CLINICAL_PARAMETERS.md](CLINICAL_PARAMETERS.md), [PIPELINE_CONFIG.md](PIPELINE_CONFIG.md)
