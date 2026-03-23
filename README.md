> ** 팀 프로젝트 안내**
> 이 프로젝트는 오라클 아카데미 6인 팀으로 개발한 감염병 모니터링 시스템 **LOOK**의 NLP 모듈입니다.
> 팀 공용 레포는 Private이므로, 본 레포에 제가 담당한 코드·설계문서·실험결과를 별도로 정리했습니다.
>
> - **전체 시스템**: WATCH(위험 필터링) → EXPLAIN(타임라인·AI 요약·Sepsis ML) → ACT(병상배치·체크리스트·RAG·문서자동화)
> -  **참여**: AI Researcher · Data Scientist
> -  **팀 구성**: 총 6명 (ML/NLP 2명, 기획/Frontend 2명, Backend 1명, 총괄 1명)

---

# LOOK — 의료 문서 기반 감염병 모니터링 NLP 파이프라인

**팀 프로젝트 | 2024**

## 요약

합성한 데이터인 558개 임상 문서(5종)에서 52종 슬롯을 추출하는 6단계 NLP 파이프라인을 개발했습니다. Rule-Based Extractor와 KM-BERT NER을 결합한 하이브리드 방식으로, 전체 F1 0.86을 달성했습니다. 의학 약어·수치 다양성·부정 표현 등 의료 텍스트 특수성을 반영하기 위해 전처리 파이프라인을 3차례 이상 재설계했습니다.

---

##  문제 정의

ICU 환자의 감염병 진행 경과를 실시간으로 모니터링하기 위해서는 여러 문서 유형(간호 기록, 의사 기록, 검사 결과, 영상 판독, 미생물 배양)에 분산된 정보를 구조화된 슬롯으로 추출해야 합니다. 이 파이프라인은 추출된 슬롯을 6개 임상 축으로 분류하고 시계열 이벤트로 변환하여 환자 악화 궤적을 자동으로 요약하는 시스텡을 위한 설계입니다.

---

## 데이터

| 구분 | 내용 |
|------|------|
| 총 문서 수 | 558개 |
| 문서 종류 | 5종 (Nursing Note, Physician Note, Lab Report, Radiology, Microbiology) |
| 슬롯 수 | 52종 |
| 환자 수 | 13명 (MIMIC-IV 기반 10명 + 순수 합성 3명) |

자세한 데이터 구성은 [data/data_description.md](data/data_description.md) 참고

---

##  파이프라인 구조

```
Phase 1·2  →  Phase 3        →  Phase 4    →  Phase 5      →  Phase 6A·6B
Document       Rule-Based        KM-BERT       Norm &           Axis Snapshot
Parser         Extractor         NER           Validation       & Trajectory Events
```

| 단계 | 내용 |
|------|------|
| Phase 1·2 | 문서 파싱 및 시간순 정렬 |
| Phase 3 | Regex 기반 수치·패턴 슬롯 추출 |
| Phase 4 | KM-BERT NER로 미탐지 슬롯 보완 |
| Phase 5 | 정규화 및 유효성 검증 |
| Phase 6A | 슬롯을 6개 임상 축으로 분류 |
| Phase 6B | 시계열 비교를 통한 이벤트 생성 |

자세한 설계는 [docs/pipeline_design.md](docs/pipeline_design.md) 참고

---

## 핵심 결과

### 성능 (Silver Standard)

| 문서 타입 | F1 |
|----------|----|
| lab_result | 0.99 |
| nursing_note | 0.88 |
| microbiology | 0.74 |
| physician_note | 0.73 |
| radiology | 0.37 |
| **전체** | **0.86** |

<!-- 👉 outputs/ 에 이미지 추가 후 아래 주석을 교체:
![Pipeline Overview](outputs/pipeline_overview.png)
![F1 by Document Type](outputs/f1_by_doctype.png)
-->

---

##  나의 주요 기여

| 영역 | 상세 |
|------|------|
| NLP 파이프라인 설계 | 5단계 구조 (Document Parser → Rule-Based Extractor → KM-BERT NER → Norm & Validation → Axis Snapshot & Trajectory) |
| 합성데이터 설계 참여 | MIMIC-IV 10명 + 순수합성 3명 = 13명, 558개 문서, 52종 슬롯 |
| 정보추출 로직 | KM-BERT NER + Rule-Based 하이브리드 방식 구현 |
| 성능 | 전체 F1 0.86 달성 |

---

## 프로젝트 구조

```
clinical-nlp-look/
├── README.md
├── .gitignore
├── data/
│   └── data_description.md      # 합성데이터 구성 (원본 미포함)
├── src/
│   └── (파이프라인 코드)
└── docs/
    └── pipeline_design.md       # NLP 파이프라인 설계 문서
```

---

## ▶ 실행 방법

**환경:** Python >= 3.8

**필요 패키지:**
```bash
pip install transformers torch pandas numpy pyyaml
```

**실행:**
1. 이 레포를 클론합니다
2. `src/` 내 파이프라인을 Phase 순서대로 실행합니다

---

## 데이터 보안

MIMIC-IV 기반 데이터는 PhysioNet DUA 계약에 따라 원본 재배포가 불가합니다. 환자 식별 정보를 포함하는 파일은 `.gitignore`로 추적에서 제외되어 있습니다.

---

##  Team

**김예지** (강원대학교 정보통계학과) — 데이터 합성, 파이프라인 설계 및 구현, 성능 평가

- GitHub: [kyjwise7-hub](https://github.com/kyjwise7-hub)
- Portfolio: [kyjwise7.oopy.io](https://kyjwise7.oopy.io)

---

##  관련 프로젝트

LOOK의 Sepsis ML 모듈은 아래 미니프로젝트에서 시작되어 발전한 것입니다.
→ [mimic-iv-deterioration-prediction](https://github.com/kyjwise7-hub/mimic-iv-deterioration-prediction)
