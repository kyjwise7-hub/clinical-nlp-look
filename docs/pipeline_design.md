# NLP 파이프라인 설계 문서

## 파이프라인 개요

558개 의료 문서(5종)에서 52종 슬롯을 추출하는 5단계(+후처리 1단계) 파이프라인

## Phase 1·2 — Document Parser
- 입력: 5종 문서 (nursing_note, physician_note, lab_result, radiology, microbiology)
- 처리: 시간순 정렬, 문서 ID 부여
- 출력: `parsed_documents.jsonl`

## Phase 3 — Rule-Based Extractor
- 입력: `parsed_documents.jsonl` + `dictionary.yaml` + `slot_definition.yaml`
- 처리: Regex 기반 수치·패턴 슬롯 추출
- 추출 예시: bp=118/74, temp=37.5°C, hr=82, spo2=96, diarrhea=True
- 미탐지 슬롯: culture_ordered, isolation_required 등 → Phase 4로 전달

## Phase 4 — KM-BERT NER
- 처리: 이전 단계에서 미탐지된 슬롯을 span·score 기반 NER로 보완
- 추출 예시: culture_ordered="C.diff toxin", isolation_required="Strict Isolation"
- 출력: `ner_predictions.jsonl`

## Phase 5 — Norm & Validation
- 처리: 정규화 및 검증
  - "POSITIVE" → "pos"
  - "Nasal Cannula" → "NC"
  - "quarantine" → ⚠ invalid_value (유효하지 않은 값 플래그)
- 출력: `tagged_slots_FINAL.jsonl`

## Phase 6A — Axis Snapshot
슬롯을 6개 임상 축으로 분류:
- A. 호흡기 (Respiratory) — 산소 요구량·포화도
- B. 감염 활성도 (Infection Activity) — 염증 수치·배양 결과
- C. 임상 행위 (Clinical Action) — 의료진 개입·처치
- D. 중증 이행 (Severity Transfer) — ICU·RRT
- E. 감염관리 (Infection Control) — 내성균·격리 조치
- F. 주관적 증상 (Subjective Symptoms) — 환자 보고 증상

## Phase 6B — Trajectory Events
- `diff_rules.yaml` 기반으로 축별 스냅샷을 시간순 비교
- 중요도: HIGH / MEDIUM / LOW
- 이벤트 구성: render_text(사람이 읽는 문장) + evidence_text(변화 근거) + event_type + severity

## 성능 (Silver Standard)
| 문서 타입 | F1 |
|----------|----|
| lab_result | 0.99 |
| nursing_note | 0.88 |
| microbiology | 0.74 |
| physician_note | 0.73 |
| radiology | 0.37 |
| **전체** | **0.86** |

## 의학 용어 특수성 반영
전처리 파이프라인을 3차례 이상 재설계한 이유:
- 의학 약어 (NC, BiPAP, ABX 등)
- 수치 표현 다양성 (118/74, 37.5°C, 96%)
- 부정 표현 ("no fever", "culture negative")
- 문서 타입별 다른 구조 (간호기록 vs 판독문)
