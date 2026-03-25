# MIMIC-IV Item IDs Reference

본 프로젝트에서 사용하는 MIMIC-IV 데이터의 Item ID 매핑 정보입니다.

---

## 📊 Vital Signs (chartevents)

### 기본 활력징후
| Variable | Item ID | Description |
|----------|---------|-------------|
| Heart Rate | `220045` | 심박수 (bpm) |
| Respiratory Rate | `220210`, `224690` | 호흡수 (breaths/min) |
| SpO2 | `220277` | 산소포화도 (%) |
| Temperature (F) | `223761` | 체온 - 화씨 |
| Temperature (C) | `223762` | 체온 - 섭씨 |

### 혈압 (Blood Pressure)
| Variable | Item ID | Description |
|----------|---------|-------------|
| NBP Systolic | `220179` | 비침습 수축기 혈압 |
| NBP Diastolic | `220180` | 비침습 이완기 혈압 |
| NBP Mean | `220181` | 비침습 평균 혈압 |
| ABP Systolic | `220050` | 동맥 수축기 혈압 |
| ABP Diastolic | `220051` | 동맥 이완기 혈압 |
| ABP Mean | `220052` | 동맥 평균 혈압 |

### 호흡 관련
| Variable | Item ID | Description |
|----------|---------|-------------|
| FiO2 | `223835` | 흡입산소농도 (%) |

### 기타
| Variable | Item ID | Description |
|----------|---------|-------------|
| Weight | `226512` | 입원 시 체중 (kg) |

---

## 🔬 Laboratory Tests (labevents)

### 혈액가스분석 (ABG)
| Variable | Item ID | Description |
|----------|---------|-------------|
| SaO2 | `50817` | 동맥혈 산소포화도 (%) |
| pH | `50820` | 혈액 pH |
| PaO2 | `50821` | 동맥혈 산소분압 (mmHg) |

### 대사 지표
| Variable | Item ID | Description |
|----------|---------|-------------|
| Lactate | `50813` | 젖산 (mmol/L) |
| Creatinine | `50912` | 크레아티닌 (mg/dL) |
| Bilirubin | `50885` | 빌리루빈 (mg/dL) |

### 혈액검사
| Variable | Item ID | Description |
|----------|---------|-------------|
| WBC | `51301` | 백혈구 (K/uL) |
| Platelets | `51265` | 혈소판 (K/uL) |
| Potassium | `50971` | 칼륨 (mEq/L) |
| Sodium | `50983` | 나트륨 (mEq/L) |

---

## 🧠 Glasgow Coma Scale (chartevents)

| Component | Item ID | Description | Range |
|-----------|---------|-------------|-------|
| Eye Opening | `220739` | 눈뜨기 반응 | 1-4 |
| Verbal Response | `223900` | 언어 반응 | 1-5 |
| Motor Response | `223901` | 운동 반응 | 1-6 |

**Total GCS = Eye + Verbal + Motor (3-15)**

---

## 💊 Medications (inputevents)

### Vasopressors (승압제)
| Drug | Item ID | Description |
|------|---------|-------------|
| Norepinephrine | `221906` | 노르에피네프린 |
| Epinephrine | `221289` | 에피네프린 |
| Vasopressin | `222315` | 바소프레신 |
| Dopamine | `221662` | 도파민 |

### Antibiotics (항생제)
| Drug | Item ID | Common Use |
|------|---------|------------|
| Vancomycin | `225798` | 그람양성균 |
| Piperacillin/Tazobactam (Zosyn) | `225893` | 광범위 항생제 |
| Ampicillin | `225842` | 그람양성/음성균 |
| Cefazolin | `225850` | 1세대 세팔로스포린 |
| Ceftazidime | `225853` | 3세대 세팔로스포린 |
| Bactrim (SMX/TMP) | `225899` | 폐렴, 요로감염 |
| Cefepime | `225851` | 4세대 세팔로스포린 |
| Ciprofloxacin | `225859` | 플루오로퀴놀론 |
| Meropenem | `225883` | 카바페넴계 |
| Acyclovir | `225837` | 항바이러스제 |
| Aztreonam | `225847` | 모노박탐계 |

---

## 🫁 Procedures (procedureevents)

| Procedure | Item ID | Description |
|-----------|---------|-------------|
| Invasive Mechanical Ventilation | `225792` | 침습적 기계환기 |

---

## 💧 Output Events (outputevents)

| Type | Item ID | Description |
|------|---------|-------------|
| Foley Catheter | `226559` | 유치도뇨관 소변량 |
| Void | `226560` | 자가배뇨량 |

---

## 🚨 Clinical Events (chartevents)

| Event | Item ID | Description |
|-------|---------|-------------|
| Code Status (DNR) | `223758` | DNR/DNI 상태 |

---

## 📝 사용 예시

```python
# Vital signs 추출
ITEM_HR = '220045'
ITEM_SPO2 = '220277'

query = f"""
SELECT charttime, valuenum
FROM chartevents
WHERE itemid = '{ITEM_HR}'
"""
```

## 📚 참고 자료

- MIMIC-IV 공식 문서: https://mimic.mit.edu/docs/iv/
- d_items 테이블: 전체 Item ID 조회 가능
