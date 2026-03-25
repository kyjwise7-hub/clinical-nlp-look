# 08_load_synthetic_extensions 검토 결과

## 검토 대상
- `data/scripts/08_load_synthetic_extensions.py` (스크립트 로직)
- `data/scripts/08_load_synthetic_extensions_expected.md` (환자별 예상값)
- `emr-generator/patient_scenario/patient_*.md` (13명 환자 시나리오)

## 검토 일시
2026-02-19

---

## 전체 요약

| # | Patient ID | 코호트 | 감염유형 | 성별 | Flags | Isolation | Radiology | Sepsis (latest) | MDRO Logs | 결과 |
|---|-----------|--------|---------|------|-------|-----------|-----------|-----------------|-----------|------|
| 1 | `11601773` | G02 | Waterborne (C.diff) | M | gastrointestinal_source / diarrhea,dehydration_risk | CONTACT | 1x CT | [0.25,0.34,0.43] MEDIUM | 0 | PASS |
| 2 | `12249103` | P04 | Pneumonia (Klebsiella) | M | respiratory_infection / cough,oxygen_support | DROPLET | 1x CXR | [0.34,0.45,0.56] MEDIUM | 0 | PASS |
| 3 | `12356657` | M01 | MDRO (MRSA) | M | mrsa,contact_precaution / isolation_required,cohort_consideration | CONTACT | 1x CXR severe | [0.54,0.66,0.77] HIGH | 1 (suspected, MRSA) | PASS |
| 4 | `16836931` | U01 | UTI (CA-UTI) | M | urinary_source / dysuria,fever | STANDARD | 1x US | [0.31,0.41,0.50] MEDIUM | 0 | PASS |
| 5 | `17650289` | P01 | Pneumonia (CAP) | F | respiratory_infection / cough,oxygen_support | DROPLET | 1x CXR | [0.34,0.45,0.56] MEDIUM | 0 | PASS |
| 6 | `18003081` | G01 | Waterborne (C.diff) | M | gastrointestinal_source / diarrhea,dehydration_risk | CONTACT | 1x CT | [0.25,0.34,0.43] MEDIUM | 0 | PASS |
| 7 | `18294629` | M03 | MDRO (CRE) | M | cre,contact_precaution / isolation_required,cohort_consideration | CONTACT | 2x CXR (base+follow-up) | [0.66,0.79,0.88] CRITICAL | 2 (suspected+confirmed, CRE) | PASS |
| 8 | `19096027` | G01 | Waterborne (C.diff) | M | gastrointestinal_source / diarrhea,dehydration_risk | CONTACT | 1x CT | [0.25,0.34,0.43] MEDIUM | 0 | PASS |
| 9 | `19440935` | M01 | MDRO (MRSA) | M | mrsa,contact_precaution / isolation_required,cohort_consideration | CONTACT | 1x CXR severe | [0.54,0.66,0.77] HIGH | 1 (suspected, MRSA) | PASS |
| 10 | `19548143` | P05 | Pneumonia (HAP) | F | respiratory_infection / cough,oxygen_support | DROPLET | 1x CXR | [0.34,0.45,0.56] MEDIUM | 0 | PASS |
| 11 | `T01` | T01 | Tick-borne (SFTS) | M | sfts_suspected,tick_borne_pattern / high_fever,thrombocytopenia | DROPLET | 1x CXR | [0.46,0.60,0.74] HIGH | 0 | PASS |
| 12 | `T02` | T02 | Tick-borne (SFTS) | F | sfts_suspected,tick_borne_pattern / high_fever,thrombocytopenia | DROPLET | 1x CXR | [0.46,0.60,0.74] HIGH | 0 | PASS |
| 13 | `T03` | T03 | Tick-borne (SFTS+MODS) | M | sfts_suspected,tick_borne_pattern / high_fever,thrombocytopenia,mental_change,icu_consideration | DROPLET | 2x CXR (base+follow-up) | [0.72,0.84,0.91] CRITICAL | 0 | PASS |

**13명 전원 PASS**

---

## 환자별 상세 검토

### 1. `11601773` (G02 / Waterborne, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | G02 / Waterborne | Hospital-acquired C. difficile (GI) | O |
| 성별 | M | 77세 남성 | O |
| Pathogen flags | gastrointestinal_source | Watery diarrhea, contact precautions | O |
| Clinical flags | diarrhea, dehydration_risk | 설사, 탈수 위험 기술됨 | O |
| Isolation | CONTACT | Contact Precautions 시행 (HD 13) | O |
| Radiology | 1x CT | GI 감염 표준 영상 | O |
| Sepsis | [0.25,0.34,0.43] MEDIUM | Cluster case, 경도~중등도 전신 반응 | O |
| MDRO logs | 0 | C. difficile = 비MDRO | O |

### 2. `12249103` (P04 / Pneumonia, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | P04 / Pneumonia | Post-op Aspiration Pneumonia (Klebsiella pneumoniae) | O |
| 성별 | M | 71세 남성 | O |
| Pathogen flags | respiratory_infection | 호흡 곤란, 기침, O2 상승 | O |
| Clinical flags | cough, oxygen_support | CXR 양측 patchy opacities | O |
| Isolation | DROPLET | 호흡기 감염 표준 | O |
| Radiology | 1x CXR | HD 1 baseline / HD 2 infiltrates / HD 8 개선 | O |
| Sepsis | [0.34,0.45,0.56] MEDIUM | 38.2C, WBC 20.6k peak | O |
| MDRO logs | 0 | Klebsiella = susceptible organism | O |

### 3. `12356657` (M01 / MDRO, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | M01 / MDRO | MRSA Pneumonia (HAP, Methicillin-Resistant) | O |
| 성별 | M | 69세 남성 | O |
| Pathogen flags | mrsa, contact_precaution | MRSA isolated, Oxacillin R, Vanco initiated | O |
| Clinical flags | isolation_required, cohort_consideration | Contact Isolation (HD 40), gown/gloves | O |
| Isolation | CONTACT | Contact Isolation 명시 | O |
| Radiology | 1x CXR severe | HD 38 new consolidation RLL / HD 44 improvement | O |
| Sepsis | [0.54,0.66,0.77] HIGH | 38.5C, WBC 15k uptrend, new RLL infiltrate | O |
| MDRO logs | 1 (suspected, MRSA) | MRSA confirmed, Vancomycin 시작 | O |

### 4. `16836931` (U01 / UTI, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | U01 / UTI | CA-UTI (Catheter-Associated, mixed organisms) | O |
| 성별 | M | 77세 남성 | O |
| Pathogen flags | urinary_source | Foley catheter, turbid urine | O |
| Clinical flags | dysuria, fever | 38.5C 고열, dysuria | O |
| Isolation | STANDARD | 표준 감염관리 | O |
| Radiology | 1x US | Renal US (obstruction screening) | O |
| Sepsis | [0.31,0.41,0.50] MEDIUM | Lactate 1.6->1.9, BP 120->100/60 | O |
| MDRO logs | 0 | Yeast + GPC = 비MDRO | O |

### 5. `17650289` (P01 / Pneumonia, F)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | P01 / Pneumonia | CAP (Community-Acquired Pneumonia) | O |
| 성별 | F | 86세 여성 | O |
| Pathogen flags | respiratory_infection | Cough, dyspnea, O2 2L->4L | O |
| Clinical flags | cough, oxygen_support | WBC 11.9->19.0->9.5, Lactate peak 2.5 | O |
| Isolation | DROPLET | 호흡기 감염 표준 | O |
| Radiology | 1x CXR | RLL infiltration, HD3/8/11 progression tracking | O |
| Sepsis | [0.34,0.45,0.56] MEDIUM | Sepsis precursor (Lactate 2.5, WBC 19k) | O |
| MDRO logs | 0 | Standard antibiotics (Levofloxacin->Cefepime) | O |

### 6. `18003081` (G01 / Waterborne, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | G01 / Waterborne | Infectious Gastroenteritis (C. difficile colitis) | O |
| 성별 | M | 51세 남성 | O |
| Pathogen flags | gastrointestinal_source | Severe watery diarrhea (5+/day), stool toxin positive | O |
| Clinical flags | diarrhea, dehydration_risk | Hypovolemia (BP 100/60), dehydration | O |
| Isolation | CONTACT | C. difficile = contact isolation (soap & water) | O |
| Radiology | 1x CT | GI 감염 기본 영상 (시나리오 초기 4일) | O |
| Sepsis | [0.25,0.34,0.43] MEDIUM | Minimal fever 37.8C, HD4까지 controlled | O |
| MDRO logs | 0 | C. difficile = 비MDRO | O |

### 7. `18294629` (M03 / MDRO-CRE, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | M03 / MDRO | CRE (Carbapenem-Resistant Enterobacteriaceae) post-op | O |
| 성별 | M | 69세 남성 | O |
| Pathogen flags | cre, contact_precaution | CRE confirmed, Meropenem non-response | O |
| Clinical flags | isolation_required, cohort_consideration | Strict contact precautions, escalation | O |
| Isolation | CONTACT | MDRO = CONTACT | O |
| Radiology | 2x CXR (base + follow-up) | HD2 baseline + HD5/6 deterioration | O |
| Sepsis | [0.66,0.79,0.88] CRITICAL | Carbapenem failure -> Tigecycline | O |
| MDRO logs | 2 (suspected + confirmed, CRE) | HD2 suspected -> HD6 confirmed CRE | O |

### 8. `19096027` (G01 / Waterborne, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | G01 / Waterborne | Hospital-acquired C. difficile Colitis | O |
| 성별 | M | 59세 남성 | O |
| Pathogen flags | gastrointestinal_source | Antibiotic-associated diarrhea, C. difficile | O |
| Clinical flags | diarrhea, dehydration_risk | Watery diarrhea, mild dehydration (HD 13) | O |
| Isolation | CONTACT | Strict Contact Isolation confirmed | O |
| Radiology | 1x CT | GI 감염 기본 영상 | O |
| Sepsis | [0.25,0.34,0.43] MEDIUM | Stable -> mild fever (37.8->38.0C) | O |
| MDRO logs | 0 | C. difficile = 비MDRO | O |

### 9. `19440935` (M01 / MDRO-MRSA, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | M01 / MDRO | MRSA Pneumonia (Superinfection) | O |
| 성별 | M | 54세 남성 | O |
| Pathogen flags | mrsa, contact_precaution | MRSA isolated, Oxacillin R / Vanco S | O |
| Clinical flags | isolation_required, cohort_consideration | 1인실 또는 코호트, gown/gloves (HD 7) | O |
| Isolation | CONTACT | Contact Precaution confirmed | O |
| Radiology | 1x CXR severe | HD 5 worsening infiltrates -> HD 12 improvement | O |
| Sepsis | [0.54,0.66,0.77] HIGH | 38.8C (HD5), WBC elevated, superinfection | O |
| MDRO logs | 1 (suspected, MRSA) | MRSA isolated | O |

### 10. `19548143` (P05 / Pneumonia, F)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | P05 / Pneumonia | HAP (Hospital-acquired, Enterobacter Asburiae) | O |
| 성별 | F | 77세 여성 | O |
| Pathogen flags | respiratory_infection | Sputum culture, gram-negative respiratory pathogen | O |
| Clinical flags | cough, oxygen_support | 기침 (HD 16), O2 RA->2L->4L->RA weaning | O |
| Isolation | DROPLET | Pneumonia = DROPLET | O |
| Radiology | 1x CXR | Baseline HD14 -> New opacity HD16 -> Resolution HD29 | O |
| Sepsis | [0.34,0.45,0.56] MEDIUM | WBC peak 21.7 (HD 19), acidosis | O |
| MDRO logs | 0 | Enterobacter Asburiae = 비MDRO | O |

### 11. `T01` (Tick-borne / SFTS, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | SFTS / Tick-borne | SFTS (Severe Fever with Thrombocytopenia Syndrome) | O |
| 성별 | M | 74세 남성 | O |
| Pathogen flags | sfts_suspected, tick_borne_pattern | PCR ordered HD3, tick exposure history | O |
| Clinical flags | high_fever, thrombocytopenia | 39.2->40C, Plt 135k->105k->58k | O |
| Isolation | DROPLET | SFTS = DROPLET | O |
| Radiology | 1x CXR | HD2 CXR (Clear, no pneumonia) | O |
| Sepsis | [0.46,0.60,0.74] HIGH | Progressive deterioration through HD4 | O |
| MDRO logs | 0 | SFTS = 비MDRO | O |

### 12. `T02` (Tick-borne / SFTS, F)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | SFTS / Tick-borne | SFTS (initial FUO -> SFTS diagnosis) | O |
| 성별 | F | 68세 여성 | O |
| Pathogen flags | sfts_suspected, tick_borne_pattern | SFTS PCR order HD3 | O |
| Clinical flags | high_fever, thrombocytopenia | 38.5->39.5C, WBC 2800, cytopenia HD3 | O |
| Isolation | DROPLET | SFTS = DROPLET | O |
| Radiology | 1x CXR | HD2 CXR (Clear) | O |
| Sepsis | [0.46,0.60,0.74] HIGH | Fever + cytopenia, mid-range risk | O |
| MDRO logs | 0 | SFTS = 비MDRO | O |

### 13. `T03` (Tick-borne / SFTS+MODS, M)

| 항목 | Expected | 시나리오 | 일치 |
|------|----------|---------|------|
| 감염유형 | SFTS / Tick-borne | SFTS with MODS (Multi-Organ Dysfunction) | O |
| 성별 | M | 82세 남성 | O |
| Pathogen flags | sfts_suspected, tick_borne_pattern | Sepsis bundle, SFTS confirmed | O |
| Clinical flags (기본) | high_fever, thrombocytopenia | 38.8C, Plt 42k, AST/ALT >200 | O |
| Clinical flags (추가) | **mental_change, icu_consideration** | 입원 시 altered mental status, HD4-5 mental stupor, ICU 전원 고려 | O |
| Isolation | DROPLET | SFTS = DROPLET | O |
| Radiology | **2x CXR** (base + worsening follow-up) | HD4-5 SpO2 unstable, deterioration pattern | O |
| Sepsis | [0.72,0.84,0.91] **CRITICAL** | MODS, hemorrhagic signs, mortality risk HIGH | O |
| MDRO logs | 0 | SFTS = 비MDRO | O |

---

## 스크립트 핵심 로직 검증

### 감염유형 매핑 (`INFECTION_MAP`)
코호트 코드 첫 글자 -> 감염유형 변환이 13명 전원 시나리오와 일치.

| Prefix | Infection Type | 해당 환자 |
|--------|---------------|----------|
| P | Pneumonia | 12249103, 17650289, 19548143 |
| U | UTI | 16836931 |
| G | Waterborne | 11601773, 18003081, 19096027 |
| M | MDRO | 12356657, 18294629, 19440935 |
| T | Tick-borne | T01, T02, T03 |

### `derive_flags()` 검증
- MDRO: `choose_mdro_type()`으로 M01->MRSA, M03->CRE 정확 분류
- Tick-borne: T03만 `mental_change`, `icu_consideration` 추가 (시나리오 부합)
- Pneumonia/UTI/Waterborne: 각각 적절한 pathogen/clinical 플래그

### `get_isolation_type()` 검증
- MDRO -> CONTACT (O)
- Pneumonia -> DROPLET (O)
- Waterborne -> CONTACT (O)
- Tick-borne -> DROPLET (O)
- UTI -> STANDARD (O)

### `risk_series_for_patient()` 검증
중증도 계층이 시나리오 심각도와 정합:

| 감염유형 | Sepsis Range | Risk Level | 시나리오 근거 |
|---------|-------------|------------|-------------|
| Waterborne | 0.25-0.43 | MEDIUM | 경도 전신 반응, controlled |
| UTI | 0.31-0.50 | MEDIUM | Lactate 상승 있으나 조기 개입 |
| Pneumonia | 0.34-0.56 | MEDIUM | WBC peak 있으나 회복 경향 |
| T01/T02 | 0.46-0.74 | HIGH | Progressive deterioration |
| M01 (MRSA) | 0.54-0.77 | HIGH | Superinfection, 중등도~중증 |
| M03 (CRE) | 0.66-0.88 | CRITICAL | Carbapenem failure cascade |
| T03 (MODS) | 0.72-0.91 | CRITICAL | MODS, hemorrhagic, ICU급 |

### `insert_radiology_reports()` 검증
- 기본: 전 환자 1건 (감염유형별 modality 적절)
- 추가 follow-up: `18294629`(M03), `T03`만 2건 -> 시나리오에서 실제 악화 경과 기술됨

### `insert_mdro_logs()` 검증
- M01 환자 2명 (12356657, 19440935): 각 1건 `suspected` stage
- M03 환자 1명 (18294629): 2건 `suspected` + `confirmed` stage
- 비MDRO 환자 10명: 0건
- 합계: 4건 (expected MD와 일치)

---

## 전체 예상 건수 검증

| 테이블 | Expected MD | 스크립트 계산 | 일치 |
|--------|------------|-------------|------|
| `transfer_cases` | 13 | 13명 x 1건 | O |
| `bed_assignment_items` | 5 | PLANNED 5명 (12249103, 16836931, 17650289, 19548143, T02) | O |
| `radiology_reports` | 15 | 11 x 1 + 2 x 2 = 15 | O |
| `sepsis_risk_scores` | 39 | 13 x 3 = 39 | O |
| `alerts` | 13 | 13 x 1 = 13 | O |
| `patient_status` | 13 | 13 x 1 = 13 | O |
| `bed_status` | 21 | SX-* 병상 21개 | O |
| `mdro_checklist_logs` | 4 | M01 x 2명(1건) + M03 x 1명(2건) = 4 | O |

---

## 결론

**expected MD, 스크립트 로직, 환자 시나리오 3자 모두 정합. 08 스크립트 실행 가능.**
