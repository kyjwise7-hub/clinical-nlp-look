> **팀 프로젝트 안내**
> 이 프로젝트는 오라클 아카데미 6인 팀으로 개발한 감염병 모니터링 시스템 **LOOK**입니다.
> 팀 공용 레포는 Private이므로, 본 레포에 제가 담당한 코드·설계문서·실험결과를 별도로 정리했습니다.
>
> - **전체 시스템**: WATCH(위험 필터링) → EXPLAIN(타임라인·AI 요약·Sepsis ML) → ACT(병상배치·체크리스트·RAG·문서자동화)
> - **참여**: AI Researcher · Data Scientist
> - **팀 구성**: 총 6명 (ML/NLP 2명, 기획/Frontend 2명, Backend 1명, 총괄 1명)

---

# LOOK — ICU 감염병 모니터링 시스템

**팀 프로젝트 | 2024**

## 요약

ICU 환자의 감염병 진행 경과를 실시간 모니터링하는 풀스택 시스템입니다. 합성한 558개 임상 문서(5종)에서 52종 슬롯을 추출하는 6단계 NLP 파이프라인, MIMIC-IV 4,713명 코호트 기반 Sepsis 악화 예측 ML 모델(XGBoost AUROC 0.90), 11종 감염병 지침서를 인덱싱한 RAG 검색 시스템을 구현했습니다. 이를 Next.js + Node.js + OracleDB 풀스택에 통합해 Docker Compose로 배포합니다.

---

## 문제 정의

ICU 환자의 감염병 진행 경과를 실시간으로 모니터링하기 위해서는 여러 문서 유형(간호 기록, 의사 기록, 검사 결과, 영상 판독, 미생물 배양)에 분산된 정보를 구조화된 슬롯으로 추출해야 합니다. 이 시스템은 추출된 슬롯을 6개 임상 축으로 분류하고 시계열 이벤트로 변환하여, **WATCH → EXPLAIN → ACT** 3단계 워크플로우로 의료진의 의사결정을 지원합니다.

---

## 시스템 아키텍처

```
WATCH                    EXPLAIN                         ACT
─────────────────────    ──────────────────────────────  ─────────────────────────────
환자 리스트               NLP 타임라인                    병상 배치
감염 위험 필터링    →     AI 요약 (OpenAI)           →   격리 체크리스트
알림 엔진 (Alert)         Sepsis ML 위험 점수             RAG 가이드라인 검색
                          6축 스냅샷 & 궤적 이벤트         자동 문서 작성 (Draft)
```

| 서비스 | 기술 스택 | 포트 |
|--------|-----------|------|
| Frontend | Next.js 16 · React 19 · TypeScript · Tailwind | 3000 |
| Backend | Node.js · Express 5 · OracleDB | 5002 |
| ML API | FastAPI · XGBoost · Python | 8001 |
| RAG API | FastAPI · BM25 · Supabase Vector · Python | 8002 |

---

## 데이터

### 합성 임상 문서

| 구분 | 내용 |
|------|------|
| 총 문서 수 | 558개 |
| 문서 종류 | 5종 (Nursing Note, Physician Note, Lab Report, Radiology, Microbiology) |
| 슬롯 수 | 52종 |
| 환자 수 | 13명 (MIMIC-IV 기반 10명 + 순수 합성 3명) |

| 분류 | 환자 수 | 핵심 서사 |
|------|---------|----------|
| 폐렴 | 3명 | CAP / HAP / 흡인성 폐렴 각 1케이스 |
| UTI | 1명 | 지속 발열 → lactate 상승 직전 개입 |
| MDRO | 3명 | MRSA / CRE 관련 격리·치료 전환점 |
| 수인성 장염 | 3명 | 클러스터 발생, stool culture pending |
| SFTS (합성) | 3명 | 혈소판 급감, WBC 감소, 중증 위험 |

문서는 `emr-generator/`의 GPT 기반 생성기로 제작했으며, 규칙 기반 검증 → AI 교차 검증(GPT·Gemini·Claude) → 의학 전공 팀원 최종 검토 3단계로 품질을 확인했습니다.

자세한 데이터 구성은 [data/data_description.md](data/data_description.md) 참고

### Sepsis ML 코호트

| 구분 | 내용 |
|------|------|
| 출처 | MIMIC-IV ICU |
| 환자 수 | 4,713명 |
| 관측 행 수 | 158,985 (sliding-window) |
| 타겟 | composite_next_24h — 향후 24시간 내 사망 / 기계환기 / 승압제 투여 중 하나 이상 |
| 클래스 분포 | Negative 91.8% / Positive 8.2% |

---

## NLP 파이프라인

```
Phase 1·2  →  Phase 3          →  Phase 4      →  Phase 5       →  Phase 6A·6B
Document       Rule-Based          KM-BERT          Norm &            Axis Snapshot
Parser         Extractor           NER              Validation         & Trajectory Events
```

| 단계 | 내용 |
|------|------|
| Phase 1·2 | 5종 문서 파싱 및 시간순 정렬 → `parsed_documents.jsonl` |
| Phase 3 | `dictionary.yaml` + `slot_definition.yaml` 기반 Regex 수치·패턴 슬롯 추출 |
| Phase 4 | KM-BERT NER로 미탐지 슬롯(culture_ordered, isolation_required 등) 보완 |
| Phase 5 | 정규화(`POSITIVE`→`pos`, `Nasal Cannula`→`NC`) 및 유효성 검증 |
| Phase 6A | 슬롯을 6개 임상 축으로 분류 → Axis Snapshot |
| Phase 6B | `diff_rules.yaml` 기반 시계열 비교 → Trajectory Events (HIGH/MEDIUM/LOW) |

**6개 임상 축**

| 축 | 내용 |
|----|------|
| A. Respiratory | 산소 요구량·포화도 |
| B. Infection Activity | 염증 수치·배양 결과 |
| C. Clinical Action | 의료진 개입·처치 |
| D. Severity Transfer | ICU·RRT 이행 |
| E. Infection Control | 내성균·격리 조치 |
| F. Subjective Symptoms | 환자 보고 증상 |

자세한 설계는 [docs/pipeline_design.md](docs/pipeline_design.md) 참고

---

## Sepsis 악화 예측 ML

MIMIC-IV ICU 코호트에서 향후 24시간 내 중증 이행을 예측하는 이진 분류 모델입니다.

**전처리 & Leakage 방지**
- `icu_mortality` 제거 (미래 정보 포함, temporal leakage)
- 고상관 피처 제거 (r > 0.95): `spo2_min`, `sbp_min`
- GroupKFold — 동일 환자 train/val 동시 포함 방지

**모델 비교 (GroupKFold OOF)**

| 모델 | 피처 수 | OOF AUROC | OOF AUPRC |
|------|---------|-----------|-----------|
| **XGBoost** | **51** | **0.8998 ± 0.0150** | **0.5737 ± 0.0465** |
| LightGBM | 51 | 0.8937 | 0.5426 |

최종 채택: **XGBoost** (AUROC·AUPRC 모두 우세)

**상위 피처 (SHAP 중요도 순)**

| 순위 | 피처 | SHAP | 범주 |
|------|------|------|------|
| 1 | sofa_total | 1.6718 | 중증도 |
| 2 | platelets | 0.2674 | 혈액 |
| 3 | creatinine | 0.2634 | 신기능 |
| 4 | observation_hour | 0.2389 | 시간 |
| 5 | bilirubin | 0.1428 | 간기능 |

자세한 내용은 [ml/docs/MODEL_REPORT.md](ml/docs/MODEL_REPORT.md) 참고

---

## RAG 가이드라인 검색

11종 감염병 관련 지침서(KDCA·KSID 등)를 인덱싱하여 임상 질의에 관련 근거를 반환합니다.

| 단계 | 내용 |
|------|------|
| 문서 파싱 | PDF → 섹션 단위 청크 (`rag/scripts/02~03`) |
| 인덱싱 | BM25 키워드 인덱스 + Supabase pgvector 의미 인덱스 |
| 검색 | Hybrid Retrieval (BM25 + Vector) |
| 재순위 | LLM Reranking (OpenAI) |

---

## 알림 엔진

`backend/services/alert_engine.py`가 Trajectory Events를 `alert_rules.yaml` 기반으로 평가해 알림을 생성합니다.

| 알림 유형 | 예시 메시지 |
|-----------|------------|
| MDRO 격리 미적용 | MDRO 확진 환자에게 격리 미적용 |
| 배양 결과 대기 | 배양 채취 - 결과 대기 중 |
| Sepsis 조기위험 | Sepsis 조기위험: 게이트 충족 |
| 감염 지표 변화 | 감염 지표 변화 감지 |

운영 방법은 [backend/services/STEP7_RUNBOOK.md](backend/services/STEP7_RUNBOOK.md) 참고

---

## 핵심 결과

### NLP 성능 (Silver Standard)

| 문서 타입 | F1 |
|----------|----|
| lab_result | 0.99 |
| nursing_note | 0.88 |
| microbiology | 0.74 |
| physician_note | 0.73 |
| radiology | 0.37 |
| **전체** | **0.86** |

> radiology F1이 낮은 이유: 판독문의 비정형 자연어 서술 구조로 인해 Regex 매칭 실패율이 높음

### ML 성능 (XGBoost, 5-fold OOF)

| 지표 | 값 |
|------|----|
| AUROC | 0.8998 ± 0.0150 |
| AUPRC | 0.5737 ± 0.0465 |

---

## 나의 주요 기여

| 영역 | 상세 |
|------|------|
| NLP 파이프라인 설계 및 구현 | 6단계 전체 (Document Parser → Rule-Based → KM-BERT NER → Norm & Validation → Axis Snapshot → Trajectory Events) |
| 합성데이터 설계 참여 | MIMIC-IV 10명 + 순수합성 3명 = 13명, 558개 문서, 52종 슬롯 |
| Sepsis ML 모델 | MIMIC-IV 4,713명 코호트, XGBoost AUROC 0.90, SHAP 해석 |
| RAG 파이프라인 | PDF 파싱 → BM25 + Vector 하이브리드 검색 → LLM 재순위 |
| 데이터 로딩 파이프라인 | OracleDB 스키마 설계 및 `data/scripts/` 전체 (00~09) |
| NLP 성능 | 전체 F1 0.86 달성 |

---

## 프로젝트 구조

```
clinical-nlp-look/
├── README.md
├── requirements.txt
│
├── nlp/                          # NLP 파이프라인 (Phase 1–6)
│   ├── run_pipeline.py
│   ├── scripts/                  # 01_document_parser ~ 06b_trajectory_event_generator
│   ├── specs/                    # slot_definition.yaml, axis_spec.yml, diff_rules.yaml
│   ├── models/ner/               # KM-BERT NER 모델 가중치
│   └── data/                     # 중간 산출물 (.jsonl)
│
├── ml/                           # Sepsis 악화 예측 ML
│   ├── notebooks/                # 01~14 단계별 노트북
│   ├── models/xgb_final_models.pkl
│   ├── api/                      # FastAPI 추론 서버
│   ├── docs/                     # MODEL_REPORT.md, COHORT_DEFINITION.md 등
│   └── sql/
│
├── rag/                          # 가이드라인 RAG 검색
│   ├── scripts/                  # 01~10 파이프라인 스크립트
│   ├── docs_raw/                 # 원본 PDF 11종
│   ├── chunks/chunks.jsonl
│   └── service/app.py            # FastAPI 서비스
│
├── backend/                      # Node.js API 서버
│   ├── app.js
│   ├── routes/                   # patient, explain, alerts, checklist 등
│   └── services/
│       ├── alert_engine.py       # 알림 융합 엔진
│       └── alert_rules.yaml
│
├── frontend/                     # Next.js 대시보드
│   ├── app/                      # 페이지 라우트
│   └── components/
│       ├── clinical/             # EXPLAIN 뷰 (타임라인, AI 요약)
│       ├── dashboard/            # WATCH 뷰 (환자 목록, KPI)
│       ├── bed-allocation/       # 병상 배치
│       └── auto-draft/           # 자동 문서 작성
│
├── emr-generator/                # 합성 EMR 생성기
│   ├── generator.py
│   ├── patient_scenario/         # 13명 시나리오 (.md)
│   └── schemas.py
│
├── data/
│   ├── scripts/                  # OracleDB 로딩 스크립트 (00~09)
│   ├── outputs/                  # 코호트 CSV/JSON
│   └── data_description.md
│
├── deployment/                   # Docker Compose 배포
│   ├── docker-compose.yml
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   ├── ml-api.Dockerfile
│   └── rag.Dockerfile
│
└── docs/
    └── pipeline_design.md        # NLP 파이프라인 설계 문서
```

---

## 실행 방법

**환경:** Python >= 3.8, Node.js >= 18

### Docker Compose (권장)

```bash
cd deployment
cp .env.docker.example .env.docker   # 환경변수 설정
docker compose build
docker compose up -d

# 헬스 체크
curl http://localhost:3000            # Frontend
curl http://localhost:5002/health     # Backend
curl http://localhost:8001/health     # ML API
curl http://localhost:8002/health     # RAG API
```

### 개별 실행

```bash
# Python 패키지
pip install -r requirements.txt

# NLP 파이프라인
python nlp/run_pipeline.py

# ML API
cd ml && uvicorn api.app:app --port 8001

# RAG API
cd rag && uvicorn service.app:app --port 8002

# Backend
cd backend && npm install && npm start

# Frontend
cd frontend && npm install && npm run dev
```

자세한 배포 설정은 [deployment/README.md](deployment/README.md) 참고

---

## 데이터 보안

MIMIC-IV 기반 데이터는 PhysioNet DUA 계약에 따라 원본 재배포가 불가합니다. 환자 식별 정보를 포함하는 파일은 `.gitignore`로 추적에서 제외되어 있습니다.

---

## Team

**김예지** (정보통계학 전공) — 데이터 합성, NLP 파이프라인, ML 모델, RAG, 데이터 로딩

- GitHub: [kyjwise7-hub](https://github.com/kyjwise7-hub)
- Portfolio: [kyjwise7.oopy.io](https://kyjwise7.oopy.io)

---

## 관련 프로젝트

LOOK의 Sepsis ML 모듈은 아래 미니프로젝트에서 시작되어 발전한 것입니다.
→ [mimic-iv-deterioration-prediction](https://github.com/kyjwise7-hub/mimic-iv-deterioration-prediction)
