# Sepsis Cohort Definition (패혈증 코호트 정의서)

## 1. 개요

| 항목 | 내용 |
|------|------|
| **데이터 소스** | MIMIC-IV (DuckDB: `mimic_total.duckdb`) |
| **정의 기준** | Sepsis-3 (Singer et al., JAMA 2016) |
| **최종 코호트 규모** | **18,001명** (기본 코호트 54,551명 중 33.0%) |
| **분석 단위** | 1 row = 1 patient (첫 ICU 입실 기준) |
| **출력 파일** | `data/processed/sepsis_cohort.csv` (31개 컬럼) |

---

## 2. 포함/제외 기준

### 2.1 기본 포함 기준 (Base Cohort)

| 기준 | 조건 | 비고 |
|------|------|------|
| **연령** | >= 18세 | `patients.anchor_age` |
| **ICU 입실 순서** | 첫 번째 ICU 입실만 | `ROW_NUMBER() OVER (PARTITION BY subject_id ORDER BY intime)` |
| **ICU 체류 기간** | >= 24시간 (LOS >= 1.0일) | `icustays.los` |

- 기본 코호트: **54,551명**

### 2.2 Sepsis-3 포함 기준

Sepsis-3 = **감염 의심 (Suspected Infection)** + **SOFA >= 2**

#### 감염 의심 판정 (Suspected Infection)

| 조건 | 설명 |
|------|------|
| **항생제 투여** | `inputevents`에서 IV 항생제 최초 투여 시점 (`abx_start`) |
| **미생물 배양** | `microbiologyevents`에서 배양 최초 채취 시점 (`culture_time`) |
| **동시성 윈도우** | 항생제 투여와 배양 검사가 **+-24시간** 이내 동시 발생 |

**판정 로직:**
1. 항생제 + 배양 동시 (+-24h) -> `suspected_infection_time = min(abx_start, culture_time)`
2. 항생제만 있음 (경험적 투여) -> `suspected_infection_time = abx_start`
3. 배양만 있음 (항생제 없음) -> **제외**

- 감염 의심 판정: **18,842명** (34.5%)
  - 항생제 + 배양 동시: 16,151명
  - 항생제만 (경험적): 2,691명

#### SOFA Score 기준

- 감염 의심 시점 **+-48시간** 윈도우 내 worst value 기준
- **SOFA Total >= 2** -> Sepsis 판정
- SOFA >= 2 충족: **18,001명** (감염 의심자 중 95.5%)

### 2.3 제외 기준

| 제외 사유 | 인원 |
|-----------|------|
| 18세 미만 | 사전 제외 |
| 재입실 (첫 ICU 아님) | 사전 제외 |
| ICU 체류 < 24시간 | 사전 제외 |
| 감염 의심 미충족 | 35,709명 |
| SOFA < 2 | 841명 |

---

## 3. SOFA Score 산출 기준

감염 의심 시점 +-48h 윈도우 내 **worst value** 사용.

### 3.1 장기별 점수 기준

| 장기 | 지표 | 0점 | 1점 | 2점 | 3점 | 4점 | 소스 테이블 |
|------|------|-----|-----|-----|-----|-----|-------------|
| **호흡** | PaO2/FiO2 | >= 400 | < 400 | < 300 | < 200 | < 100 | `labevents` (PaO2) + `chartevents` (FiO2) |
| **응고** | Platelets (x10^3/uL) | >= 150 | < 150 | < 100 | < 50 | < 20 | `labevents` |
| **간** | Bilirubin (mg/dL) | < 1.2 | >= 1.2 | >= 2.0 | >= 6.0 | >= 12.0 | `labevents` |
| **순환** | MAP / 승압제 | MAP>=70 | MAP<70 | Dopa<=5 | Dopa>5 or NE<=0.1 | Dopa>15 or NE>0.1 | `chartevents` (MAP) + `inputevents` (승압제) |
| **신경** | GCS | 15 | 13-14 | 10-12 | 6-9 | < 6 | `chartevents` |
| **신장** | Creatinine (mg/dL) | < 1.2 | >= 1.2 | >= 2.0 | >= 3.5 | >= 5.0 | `labevents` |

### 3.2 SOFA Item IDs

| 지표 | Item ID | 테이블 |
|------|---------|--------|
| PaO2 | 50821 | labevents |
| FiO2 | 223835 | chartevents |
| Platelets | 51265 | labevents |
| Bilirubin | 50885 | labevents |
| ABP Mean | 220052 | chartevents |
| NBP Mean | 220181 | chartevents |
| Norepinephrine | 221906 | inputevents |
| Epinephrine | 221289 | inputevents |
| Dopamine | 221662 | inputevents |
| GCS Eye | 220739 | chartevents |
| GCS Verbal | 223900 | chartevents |
| GCS Motor | 223901 | chartevents |
| Creatinine | 50912 | labevents |

### 3.3 SOFA 분포 (코호트 내)

| 장기 | 평균 점수 |
|------|-----------|
| 호흡 (sofa_resp) | 2.71 |
| 응고 (sofa_coag) | 0.84 |
| 간 (sofa_liver) | 0.41 |
| 순환 (sofa_cardio) | 1.83 |
| 신경 (sofa_cns) | 2.68 |
| 신장 (sofa_renal) | 0.86 |
| **Total** | **9.3 (중앙값 9.0)** |

---

## 4. Septic Shock 판정

Sepsis 환자 중 추가 하위분류:

| 조건 | 설명 |
|------|------|
| **승압제 투여** | `inputevents`에서 승압제 사용 (rate > 0) |
| **Lactate > 2 mmol/L** | `labevents`에서 ICU 체류 중 lactate > 2.0 |
| **동시성** | 승압제 시작과 고유산혈 시점이 **+-24시간** 이내 |

- Septic Shock: **3,756명** (Sepsis 코호트의 20.9%)

---

## 5. 항생제 목록 (Antibiotics)

`inputevents` 기반 IV 항생제 11종:

| Item ID | 약물명 |
|---------|--------|
| 225798 | Vancomycin |
| 225893 | Piperacillin/Tazobactam (Zosyn) |
| 225842 | Ampicillin |
| 225850 | Cefazolin |
| 225853 | Ceftazidime |
| 225899 | Bactrim (SMX/TMP) |
| 225851 | Cefepime |
| 225859 | Ciprofloxacin |
| 225883 | Meropenem |
| 225837 | Acyclovir |
| 225847 | Aztreonam |

---

## 6. 코호트 인구통계 요약

| 항목 | 값 |
|------|-----|
| **총 환자 수** | 18,001명 |
| **나이** | 64.1 +/- 16.2세 |
| **성별** | 남 10,771 (59.8%) / 여 7,230 (40.2%) |
| **ICU 체류일** | 2.7일 (중앙값) |
| **ICU 사망** | 1,787명 (9.9%) |
| **병원 사망** | 2,484명 (13.8%) |
| **Septic Shock** | 3,756명 (20.9%) |
| **DNR** | 9,696명 (53.9%) |
| **기계 환기** | 11,426명 (63.5%) |
| **승압제 사용** | 6,556명 (36.4%) |

### Sepsis vs Non-Sepsis 비교

| 지표 | Sepsis (n=18,001) | Non-Sepsis (n=36,550) |
|------|-------------------|----------------------|
| ICU 사망률 | 9.9% | 5.6% |
| 병원 사망률 | 13.8% | 9.3% |

---

## 7. 감염 의심 시간 분포

ICU 입실 시점 기준:

| 구간 | 인원 |
|------|------|
| 입실 전 감염 의심 | 2,031명 |
| 입실 후 24h 이내 | 15,281명 |
| **평균** | 4.6시간 |
| **중앙값** | 2.2시간 |

---

## 8. 출력 컬럼 명세 (31개)

### 8.1 환자 기본 정보

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `subject_id` | int | 환자 고유 ID |
| `hadm_id` | int | 입원 ID |
| `stay_id` | int | ICU 체류 ID |
| `intime` | timestamp | ICU 입실 시각 |
| `outtime` | timestamp | ICU 퇴실 시각 |
| `los` | float | ICU 체류일 |
| `first_careunit` | str | 첫 ICU 부서 |
| `last_careunit` | str | 마지막 ICU 부서 |
| `anchor_age` | int | 나이 |
| `gender` | str | 성별 (M/F) |
| `dod` | timestamp | 사망일 |
| `admittime` | timestamp | 병원 입원 시각 |
| `dischtime` | timestamp | 병원 퇴원 시각 |
| `deathtime` | timestamp | 사망 시각 |
| `hospital_expire_flag` | str | 병원 사망 플래그 (원본) |

### 8.2 결과 변수

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `icu_mortality` | int (0/1) | ICU 사망 여부 (deathtime <= outtime) |
| `hospital_mortality` | int (0/1) | 병원 사망 여부 |

### 8.3 감염/Sepsis 관련

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `suspected_infection_time` | timestamp | 감염 의심 시점 |
| `abx_culture_both` | int (0/1) | 항생제+배양 동시 여부 |

### 8.4 SOFA 점수

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `sofa_resp` | float | 호흡 SOFA (0-4) |
| `sofa_coag` | float | 응고 SOFA (0-4) |
| `sofa_liver` | float | 간 SOFA (0-4) |
| `sofa_cardio` | float | 순환 SOFA (0-4) |
| `sofa_cns` | float | 신경 SOFA (0-4) |
| `sofa_renal` | float | 신장 SOFA (0-4) |
| `sofa_total` | float | SOFA 총점 (0-24) |

### 8.5 이벤트 시간

| 컬럼명 | 타입 | 설명 |
|--------|------|------|
| `septic_shock_time` | timestamp | Septic Shock 판정 시점 |
| `septic_shock_flag` | int (0/1) | Septic Shock 여부 |
| `dnr_time` | timestamp | DNR 최초 기록 시점 |
| `vent_start_time` | timestamp | 기계 환기 시작 시점 |
| `pressor_start_time` | timestamp | 승압제 투여 시작 시점 |

---

## 9. 파이프라인 위치

```
01_sepsis_cohort.ipynb  <-- 본 정의서 대상
    |
    v
02_vital_raw -> 03_lab_raw -> 04_ventilation_raw -> 05_pressor_raw -> 06_urine_raw -> 07_gcs_raw
    |
    v
08_sliding_window_merge  (6h 윈도우, 1h stride, 6-72h 범위)
    |
    v
09_preprocessing -> 10_feature_engineering -> 11_model_selection
```

---

## 10. 주요 설정 파라미터 (`src/config.py`)

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `MIN_AGE` | 18 | 성인 기준 연령 |
| `MIN_LOS_DAYS` | 1.0 | 최소 ICU 체류일 |
| `SOFA_THRESHOLD` | 2 | Sepsis-3 SOFA 기준 |
| `INFECTION_WINDOW_H` | 24 | 항생제-배양 동시성 판정 윈도우 (시간) |
| `WINDOW_SIZE_H` | 6 | 슬라이딩 윈도우 크기 (시간) |
| `STRIDE_H` | 1 | 슬라이딩 윈도우 이동 간격 (시간) |
| `MIN_HOUR` | 6 | 윈도우 시작 시점 (ICU 입실 후) |
| `MAX_HOUR` | 72 | 윈도우 종료 시점 |

---

## 11. 참고문헌

- Singer M, et al. **The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3)**. JAMA. 2016;315(8):801-810.
- Johnson AEW, et al. **MIMIC-IV, a freely accessible electronic health record dataset**. Sci Data. 2023;10(1):1.
