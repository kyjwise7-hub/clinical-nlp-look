# 모델 보고서: Sepsis 악화 예측 (composite_next_24h)

> 작성일: 2026-02-20
> 노트북: `notebooks/12_xgboost_lightGBM 비교.ipynb`

---

## 1. 과제 정의

| 항목 | 내용 |
|------|------|
| 타겟 | `composite_next_24h` — 향후 24시간 내 사망 / 기계환기 / 승압제 투여 중 하나 이상 |
| 데이터 | MIMIC-IV ICU 패혈증 코호트 (`features_final.csv`) |
| 행 수 | 158,985 (sliding-window observation) |
| 환자 수 | 4,713명 |
| 클래스 분포 | Negative 145,985 (91.8%) / Positive 13,000 (8.2%) |

---

## 2. 전처리 & Leakage 방지

| 처리 | 내용 |
|------|------|
| `icu_mortality` 제거 | ICU 최종 사망 여부 → 미래 정보 포함, temporal leakage |
| 고상관 제거 (r > 0.95) | `spo2_min` (spo2와 r=1.00), `sbp_min` (sbp와 r=1.00) |
| GroupKFold | 환자 단위 분할 → 동일 환자 train/val 동시 포함 방지 |

초기 53개 → 고상관 제거 후 **51개** 최종 피처

---

## 3. 최종 피처 목록 (51개, SHAP 중요도 순)

| 순위 | 피처 | Mean \|SHAP\| | 범주 |
|------|------|--------------|------|
| 1 | sofa_total | 1.6718 | 중증도 |
| 2 | platelets | 0.2674 | 혈액 |
| 3 | creatinine | 0.2634 | 신기능 |
| 4 | observation_hour | 0.2389 | 시간 |
| 5 | bilirubin | 0.1428 | 간기능 |
| 6 | icu_micu | 0.1015 | ICU 유형 |
| 7 | spo2 | 0.0890 | 활력징후 |
| 8 | urine_ml_kg_hr_avg | 0.0755 | 신기능 |
| 9 | anchor_age | 0.0702 | 환자 특성 |
| 10 | icu_micu_sicu | 0.0658 | ICU 유형 |
| 11 | lactate | 0.0603 | 대사 |
| 12 | ph | 0.0566 | 산염기 |
| 13 | news_score | 0.0541 | 임상점수 |
| 14 | sodium | 0.0524 | 전해질 |
| 15 | mews_score | 0.0511 | 임상점수 |
| 16 | potassium | 0.0486 | 전해질 |
| 17 | shock_index | 0.0486 | 활력징후 |
| 18 | abga_checked | 0.0436 | 검사 여부 |
| 19 | wbc | 0.0424 | 혈액 |
| 20 | sbp | 0.0413 | 활력징후 |
| 21 | rr_max | 0.0386 | 활력징후 |
| 22 | dbp | 0.0356 | 활력징후 |
| 23 | rr | 0.0346 | 활력징후 |
| 24 | gcs_total_slope | 0.0340 | 추세 |
| 25 | hr | 0.0339 | 활력징후 |
| 26 | pulse_pressure | 0.0298 | 활력징후 |
| 27 | lactate_slope | 0.0293 | 추세 |
| 28 | urine_ml_6h | 0.0257 | 신기능 |
| 29 | mbp | 0.0243 | 활력징후 |
| 30 | hr_max | 0.0240 | 활력징후 |
| 31 | temp | 0.0215 | 활력징후 |
| 32 | gcs_eye | 0.0209 | 신경 |
| 33 | gcs_verbal | 0.0185 | 신경 |
| 34 | icu_sicu | 0.0180 | ICU 유형 |
| 35 | gcs_total | 0.0136 | 신경 |
| 36 | gender | 0.0135 | 환자 특성 |
| 37 | gcs_motor | 0.0086 | 신경 |
| 38 | bilirubin_missing | 0.0084 | 결측 flag |
| 39 | ph_slope | 0.0081 | 추세 |
| 40 | temp_slope | 0.0076 | 추세 |
| 41 | lactate_missing | 0.0062 | 결측 flag |
| 42 | hr_slope | 0.0040 | 추세 |
| 43 | urine_missing | 0.0039 | 결측 flag |
| 44 | icu_ccu | 0.0034 | ICU 유형 |
| 45 | spo2_slope | 0.0026 | 추세 |
| 46 | icu_tsicu | 0.0022 | ICU 유형 |
| 47 | oliguria_flag | 0.0017 | 임상 flag |
| 48 | rr_slope | 0.0016 | 추세 |
| 49 | creatinine_slope | 0.0015 | 추세 |
| 50 | sbp_slope | 0.0010 | 추세 |
| 51 | map_below_65 | 0.0010 | 임상 flag |

> **SHAP 해석**: `sofa_total`이 압도적으로 중요 (1.67). 이후 `platelets`, `creatinine`, `observation_hour` 순.
> 37번 이후(gcs_motor~) SHAP < 0.009으로 기여도 급락.

---

## 4. 모델 하이퍼파라미터

### XGBoost

| 파라미터 | 값 |
|----------|----|
| objective | binary:logistic |
| tree_method | hist |
| learning_rate | 0.05 |
| max_depth | 7 |
| min_child_weight | 50 |
| subsample | 0.8 |
| colsample_bytree | 0.8 |
| reg_alpha | 0.1 |
| reg_lambda | 1.0 |
| scale_pos_weight | ~11.2 (클래스 불균형 보정) |
| num_boost_round | 1000 (early stopping=50) |

### LightGBM

| 파라미터 | 값 |
|----------|----|
| objective | binary |
| boosting_type | gbdt |
| learning_rate | 0.05 |
| num_leaves | 63 |
| max_depth | 7 |
| min_child_samples | 50 |
| subsample | 0.8 |
| colsample_bytree | 0.8 |
| reg_alpha / reg_lambda | 0.1 / 1.0 |
| scale_pos_weight | ~11.2 |
| num_boost_round | 400 (early stopping=30) |

---

## 5. 성능 결과

### XGBoost — 51 Features, 5-fold GroupKFold (OOF)

| Fold | AUROC | AUPRC | Best Iter |
|------|-------|-------|-----------|
| 0 | 0.9157 | 0.6176 | 162 |
| 1 | 0.9154 | 0.6215 | 254 |
| 2 | 0.8865 | 0.5279 | 84 |
| 3 | 0.8965 | 0.5763 | 182 |
| 4 | 0.8851 | 0.5252 | 88 |
| **OOF** | **0.8998 ± 0.0150** | **0.5737 ± 0.0465** | — |

### LightGBM — 51 Features, 3-fold GroupKFold (OOF)

| Fold | AUROC | AUPRC | Best Iter |
|------|-------|-------|-----------|
| 0 | 0.8971 | 0.5546 | 213 |
| 1 | 0.8801 | 0.5217 | 38 |
| 2 | 0.9134 | 0.6039 | 132 |
| **OOF** | **0.8937** | **0.5426** | — |

### 모델 비교 요약

| 모델 | 피처 수 | Fold | OOF AUROC | OOF AUPRC |
|------|---------|------|-----------|-----------|
| XGBoost | 51 | 5 | **0.8998** | **0.5737** |
| LightGBM | 51 | 3 | 0.8937 | 0.5426 |

> **최종 채택: XGBoost** (AUROC, AUPRC 모두 우세)

---

## 6. Feature Selection Trial (SHAP Ablation)

SHAP 기반 피처 제거 효과를 3-fold ablation으로 확인:

| 피처 수 | OOF AUROC | OOF AUPRC | Δ AUROC |
|---------|-----------|-----------|---------|
| 51 (전체) | 0.8992 | 0.5718 | — |
| 41 | 0.8965 | 0.5572 | -0.0027 |
| 31 | 0.8984 | 0.5598 | -0.0008 |
| 21 | 0.8870 | 0.5312 | -0.0122 |

> **결론**: 51개 전체 사용이 최선. XGBoost/LightGBM은 트리 구조상 저중요 피처를 자동 무시하므로 강제 제거 시 오히려 AUPRC 하락.

---

## 7. 저장 파일

| 파일 | 내용 |
|------|------|
| `DATA/models/xgb_final_models.pkl` | XGBoost 5-fold 모델 리스트 |
| `DATA/models/xgb_oof_prob.npy` | XGBoost OOF 확률값 |
| `DATA/models/lgb_final_models.pkl` | LightGBM 3-fold 모델 리스트 |
| `DATA/models/lgb_oof_prob.npy` | LightGBM OOF 확률값 |
| `DATA/models/model_comparison.csv` | 모델 성능 비교 |
| `DATA/models/best_model.txt` | 최종 채택 모델명 (`XGBoost`) |
| `DATA/processed/xgb_selected_features.csv` | 최종 피처 리스트 (51개) |
