# Clinical Parameters & Thresholds

임상적 파라미터, 정상 범위, 이상치 처리 기준 문서입니다.

---

## 🎯 Cohort Inclusion Criteria

### 기본 포함 기준
| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Minimum Age** | ≥18세 | 성인 환자만 포함 |
| **ICU Length of Stay** | ≥24시간 | 충분한 관찰 시간 확보 |
| **ICU Stay Order** | 첫 번째 입실만 | 독립성 보장 |

### Sepsis-3 정의 기준
| Criterion | Threshold | Description |
|-----------|-----------|-------------|
| **SOFA Score** | ≥2 | 장기부전 기준 |
| **Suspected Infection** | 항생제 + 배양 | ±24h 이내 동시 발생 |

**Infection Window**: 항생제 투여와 배양검사가 **24시간** 이내 발생 시 감염 의심으로 판정

---

## 🏥 Clinical Value Ranges (이상치 클리핑)

데이터 추출 시 임상적으로 불가능한 값을 제거하기 위한 범위입니다.

### Vital Signs
| Variable | Min | Max | Unit | Note |
|----------|-----|-----|------|------|
| Heart Rate | 20 | 300 | bpm | |
| Respiratory Rate | 4 | 60 | breaths/min | |
| SpO2 | 50 | 100 | % | |
| Temperature | 30 | 45 | °C | |
| Systolic BP | 40 | 300 | mmHg | |
| Diastolic BP | 20 | 200 | mmHg | |
| Mean BP | 30 | 250 | mmHg | |

### Laboratory Values
| Variable | Min | Max | Unit | Note |
|----------|-----|-----|------|------|
| SaO2 | 50 | 100 | % | |
| pH | 6.8 | 7.8 | - | |
| Lactate | 0.1 | 30 | mmol/L | |
| Creatinine | 0.1 | 30 | mg/dL | |
| Bilirubin | 0.1 | 50 | mg/dL | |
| WBC | 0.1 | 100 | K/uL | |
| Platelets | 5 | 1000 | K/uL | |
| Potassium | 1.5 | 10 | mEq/L | |
| Sodium | 110 | 170 | mEq/L | |
| Weight | 1 | 500 | kg | |

---

## 🔧 Missing Value Imputation

결측값 대체에 사용하는 **임상적 정상값**입니다.

| Variable | Default Value | Rationale |
|----------|---------------|-----------|
| **Temperature** | 36.8°C | 정상 체온 |
| **Lactate** | 1.2 mmol/L | 정상 상한 |
| **FiO2** | 0.21 (21%) | Room air (측정 없으면 일반 공기 흡입으로 간주) |

### Imputation Strategy
1. **Forward Fill**: 마지막 관찰값 유지 (LOCF)
2. **Clinical Normal**: 결측이 지속되면 위 정상값으로 대체
3. **Carry Forward**: 윈도우 내 이전 값 사용

---

## 📊 SOFA Score Calculation

### Component Scoring Criteria

#### 1. Respiration (PaO2/FiO2)
| PaO2/FiO2 | SOFA Score |
|-----------|------------|
| ≥400 | 0 |
| <400 | 1 |
| <300 | 2 |
| <200 | 3 |
| <100 | 4 |

#### 2. Coagulation (Platelets)
| Platelets (K/uL) | SOFA Score |
|------------------|------------|
| ≥150 | 0 |
| <150 | 1 |
| <100 | 2 |
| <50 | 3 |
| <20 | 4 |

#### 3. Liver (Bilirubin)
| Bilirubin (mg/dL) | SOFA Score |
|-------------------|------------|
| <1.2 | 0 |
| 1.2-1.9 | 1 |
| 2.0-5.9 | 2 |
| 6.0-11.9 | 3 |
| ≥12.0 | 4 |

#### 4. Cardiovascular (MAP + Vasopressors)
| Condition | SOFA Score |
|-----------|------------|
| MAP ≥70 mmHg | 0 |
| MAP <70 mmHg | 1 |
| Dopamine ≤5 or Dobutamine (any) | 2 |
| Dopamine >5 or Epi ≤0.1 or NE ≤0.1 | 3 |
| Dopamine >15 or Epi >0.1 or NE >0.1 | 4 |

*승압제 용량 단위: μg/kg/min*

#### 5. CNS (Glasgow Coma Scale)
| GCS | SOFA Score |
|-----|------------|
| 15 | 0 |
| 13-14 | 1 |
| 10-12 | 2 |
| 6-9 | 3 |
| <6 | 4 |

#### 6. Renal (Creatinine)
| Creatinine (mg/dL) | SOFA Score |
|--------------------|------------|
| <1.2 | 0 |
| 1.2-1.9 | 1 |
| 2.0-3.4 | 2 |
| 3.5-4.9 | 3 |
| ≥5.0 | 4 |

**Total SOFA** = Sum of 6 components (0-24)

---

## 💉 Septic Shock Definition

**Sepsis 환자 중** 다음 두 조건을 **동시 충족** (±24h 이내):

1. **Vasopressor 사용** (Norepinephrine, Epinephrine, Vasopressin, Dopamine)
2. **Lactate >2.0 mmol/L**

→ 판정 시점: 두 조건이 모두 만족된 **늦은 시점**

---

## ⏱️ Time Windows

### SOFA Calculation Window
- **기준 시점**: Suspected Infection Time
- **윈도우**: ±48시간
- **집계**: Worst value (장기별 최악의 값)

### Infection Suspicion Window
- **항생제 - 배양 동시성**: ±24시간
- **우선순위**: 먼저 발생한 시점을 suspected_infection_time으로 설정

### Sliding Window (Feature Extraction)
- **Window Size**: 6시간
- **Stride**: 1시간
- **Start**: ICU 입실 후 6시간
- **End**: ICU 입실 후 72시간

---

## 🩺 Oliguria (핍뇨) 정의

| Criterion | Threshold |
|-----------|-----------|
| **Urine Output** | <0.5 mL/kg/hr |
| **Measurement Period** | 6시간 |

**계산 예시**:
- 환자 체중: 70kg
- 6시간 동안 소변량: 150mL
- 시간당 체중 보정: 150 / (70 × 6) = 0.36 mL/kg/hr
- → Oliguria flag = 1

---

## 🎯 Prediction Horizons

모델이 예측할 미래 시점:

| Horizon | Description |
|---------|-------------|
| **6시간** | 초단기 악화 예측 |
| **12시간** | 단기 악화 예측 |
| **24시간** | 중기 악화 예측 |

---

## 사용 예시

### 이상치 클리핑
```python
from src.config import CLINICAL_RANGES
from src.utils import clip_clinical

# 개별 컬럼
df['hr'] = clip_clinical(df, 'hr', CLINICAL_RANGES)

# 전체 컬럼 일괄
for col in CLINICAL_RANGES:
    if col in df.columns:
        df[col] = clip_clinical(df, col, CLINICAL_RANGES)
```

### 결측값 대체
```python
from src.config import NORMAL_DEFAULTS

# FiO2 결측 시 room air로 대체
df['fio2'] = df['fio2'].fillna(NORMAL_DEFAULTS['fio2'])  # 0.21

# Lactate 결측 시 정상 상한값으로 대체
df['lactate'] = df['lactate'].fillna(NORMAL_DEFAULTS['lactate'])  # 1.2
```

---

## 참고

- 모든 파라미터는 `src/config.py`에서 관리 (`CLINICAL_RANGES`, `NORMAL_DEFAULTS`, `SOFA_THRESHOLD` 등)
- 관련 문서: [COHORT_DEFINITION.md](COHORT_DEFINITION.md), [AGGREGATION_RULES.md](AGGREGATION_RULES.md)

## 참고 문헌

- Singer M, et al. The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3). JAMA. 2016.
- Vincent JL, et al. The SOFA (Sepsis-related Organ Failure Assessment) score to describe organ dysfunction/failure. Intensive Care Med. 1996.
