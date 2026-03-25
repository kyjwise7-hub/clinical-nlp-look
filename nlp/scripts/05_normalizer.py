"""
INFECT-GUARD Phase 5: 정규화 + 검증
=====================================
02_rule_extractor.py 출력을 받아 최종 정규화 + 검증을 수행한다.

──────────────────────────────────────────────────────────────────────
02_rule_extractor.py에서 이미 수행한 정규화:
  - O2 device  : room air→RA, nasal cannula→NC 등  (_normalize_o2_device)
  - O2 flow    : "2L/min"→2.0                      (_parse_o2_flow)
  - Culture    : COLLECTED→pending 등               (_normalize_culture_status)
  - PRN        : 해열제→antipyretic 등              (_normalize_prn)
  - Pain loc   : 복통→abdomen, 옆구리→flank 등      (_normalize_pain_location)
  - 기본값 추론 : SpO2 존재 + O2 device 미언급 → RA  (_infer_defaults)
  - Axis D     : enabled=false 축 슬롯 제거
  - 범위 검증   : slot_definition range 밖이면 제거
──────────────────────────────────────────────────────────────────────

Phase 5에서 추가로 수행하는 정규화:
  1. 타입 강제 (type coercion)
     - integer 슬롯 → int 변환 (36.0 → 36)
     - float   슬롯 → float 변환
     - boolean 슬롯 → bool 변환 (문자열 "true"/"false" 포함)
     - tri_bool     → true/false/unknown
  2. 단위 보정
     - WBC      : >100 이면 /1000 (예: 14000 → 14.0)
     - Platelet : >1000 이면 /1000 (예: 250000 → 250)
  3. Enum 정규화
     - allowed_values에 대소문자 무시 매칭 → 정확한 값으로 교정
  4. 리스트 정리
     - list[enum] 중복 제거, 정렬
  5. Null/빈값 정리
     - value가 None이거나 빈 문자열이면 슬롯 제거
  6. specimen_type 소문자 정규화
     - "URINE" → "urine", "BLOOD" → "blood" 등
  7. normalize 맵 적용
     - slot_definition.yaml 내 normalize 테이블 적용
  8. 최종 검증
     - 범위 재검증 (단위 보정 후 범위 벗어나면 제거)
     - 필수 슬롯 누락 추적
     - 검증 경고 기록

입력:  nlp/data/tagged_slots_v4_1.jsonl
출력:  nlp/data/tagged_slots_FINAL.jsonl

실행:
  python scripts/05_normalizer.py
  python scripts/05_normalizer.py \\
    --input  nlp/data/tagged_slots_v4_1.jsonl \\
    --output nlp/data/tagged_slots_FINAL.jsonl \\
    --slot-def nlp/specs/slot_definition.yaml
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter
from typing import Any, Optional
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
NLP_ROOT = SCRIPT_DIR.parent
REPO_ROOT = NLP_ROOT.parent

DEFAULT_INPUT_PATH = str(NLP_ROOT / "data" / "tagged_slots_v4_1.jsonl")
DEFAULT_OUTPUT_PATH = str(NLP_ROOT / "data" / "tagged_slots_FINAL.jsonl")
DEFAULT_SLOT_DEF_PATH = str(NLP_ROOT / "specs" / "slot_definition.yaml")


# ============================================================
# 1. SlotDefinition 로더
#    slot_definition.yaml에서 슬롯별 type, range, allowed_values,
#    normalize 맵, document_slot_mapping을 파싱한다.
# ============================================================

def _resolve_slot_def_path(path: Optional[str]) -> Optional[str]:
    """slot_definition 경로를 실행 위치와 무관하게 해석한다."""
    if not path:
        return None

    raw = Path(path)
    candidates = [raw]
    if not raw.is_absolute():
        candidates.extend([NLP_ROOT / raw, REPO_ROOT / raw])
    candidates.append(NLP_ROOT / "specs" / "slot_definition.yaml")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def load_slot_definition(path: Optional[str] = None) -> dict:
    """slot_definition.yaml 로드. pyyaml 미설치 시 빈 dict 반환."""
    resolved = _resolve_slot_def_path(path)
    if resolved and os.path.exists(resolved):
        try:
            import yaml
            with open(resolved, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except ImportError:
            print("⚠ pyyaml 미설치 — slot_definition 정규화 비활성화")
    return {}


class SlotDefinition:
    """
    slot_definition.yaml 파서.
    - slots: {slot_name: {type, range, allowed_values, normalize, ...}}
    - doc_mapping: {doc_type: {mandatory: [...], recommended: [...], optional: [...]}}
    """

    def __init__(self, spec: dict):
        self.spec = spec or {}
        self.slots: dict[str, dict] = {}
        self.doc_mapping: dict[str, dict] = {}
        self._build_registry()

    @property
    def enabled(self) -> bool:
        """슬롯 정의가 로드되었는지 여부"""
        return len(self.slots) > 0

    def _build_registry(self) -> None:
        """axis_* 및 supplementary_vitals 섹션에서 슬롯 정의를 수집"""
        for key, section in self.spec.items():
            if not isinstance(section, dict):
                continue
            # axis_a_respiratory, axis_b_infection_activity, ..., supplementary_vitals
            if key.startswith("axis_") or key == "supplementary_vitals":
                for slot_name, slot_def in section.get("slots", {}).items():
                    if isinstance(slot_def, dict):
                        self.slots[slot_name] = slot_def

        # document_slot_mapping: 문서 타입별 mandatory/recommended/optional 슬롯
        mapping = self.spec.get("document_slot_mapping", {})
        for doc_type, doc_def in mapping.items():
            if isinstance(doc_def, dict):
                self.doc_mapping[doc_type] = {
                    "mandatory": doc_def.get("mandatory", []),
                    "recommended": doc_def.get("recommended", []),
                    "optional": doc_def.get("optional", []),
                }

    def get_slot_def(self, name: str) -> dict:
        """슬롯 정의 반환 (없으면 빈 dict)"""
        return self.slots.get(name, {})

    def get_type(self, name: str) -> str:
        """슬롯의 타입 반환 (integer, float, boolean, tri_bool, enum, list[enum], object, string)"""
        return self.slots.get(name, {}).get("type", "string")

    def get_range(self, name: str) -> Optional[list]:
        """슬롯의 값 범위 [min, max] 반환"""
        return self.slots.get(name, {}).get("range")

    def get_allowed_values(self, name: str) -> Optional[list]:
        """슬롯의 허용 값 목록 반환"""
        return self.slots.get(name, {}).get("allowed_values")

    def get_normalize_map(self, name: str) -> Optional[dict]:
        """슬롯의 normalize 맵 반환 (예: {"URINE": "urine"})"""
        nm = self.slots.get(name, {}).get("normalize")
        return nm if isinstance(nm, dict) else None

    def get_mandatory_slots(self, doc_type: str) -> list:
        """해당 문서 타입의 필수 슬롯 목록"""
        return self.doc_mapping.get(doc_type, {}).get("mandatory", [])

    def is_valid_slot(self, name: str) -> bool:
        """정의된 슬롯인지 확인"""
        return name in self.slots


# ============================================================
# 2. 단위 보정 함수
#    이전 추출 단계(Phase 2/4)에서 나온 수치 중 단위가 잘못된 경우를 보정한다.
#    예: WBC 14000 → 14.0 (x10³/μL), Platelet 250000 → 250
# ============================================================

def _correct_wbc_unit(value: Any) -> Optional[float]:
    """
    WBC 단위 보정.
    - >100 이면 x10³ 단위가 아니라 /μL 단위로 입력된 것으로 간주 → /1000
    - slot_definition range: [0, 100]
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 100:
        return round(v / 1000, 2)
    return v


def _correct_platelet_unit(value: Any) -> Optional[float]:
    """
    Platelet 단위 보정.
    - >1000 이면 절대 수치로 입력된 것으로 간주 → /1000
    - slot_definition range: [0, 1000]
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v > 1000:
        return round(v / 1000, 1)
    return v


# ============================================================
# 3. 타입 강제 변환 함수
#    slot_definition의 type에 따라 값을 올바른 Python 타입으로 변환.
# ============================================================

def _coerce_integer(value: Any) -> Optional[int]:
    """integer 타입 슬롯 값을 int로 변환"""
    if value is None:
        return None
    try:
        v = float(value)
        # NaN/Inf 체크
        if math.isnan(v) or math.isinf(v):
            return None
        return int(round(v))
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> Optional[float]:
    """float 타입 슬롯 값을 float로 변환"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if math.isnan(value) or math.isinf(value):
            return None
        return float(value)
    # 문자열에서 숫자 추출 시도
    m = re.search(r"(-?\d+(?:\.\d+)?)", str(value))
    if m:
        return float(m.group(1))
    return None


def _coerce_boolean(value: Any) -> Optional[bool]:
    """boolean 타입 슬롯 값을 bool로 변환"""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "yes", "1", "t"}:
            return True
        if low in {"false", "no", "0", "f"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _coerce_tri_bool(value: Any) -> Any:
    """
    tri_bool 타입: true / false / "unknown"
    - boolean이면 그대로
    - "unknown" 문자열이면 그대로
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "yes", "1"}:
            return True
        if low in {"false", "no", "0"}:
            return False
        if low == "unknown":
            return "unknown"
    if isinstance(value, (int, float)):
        return bool(value)
    return value


# ============================================================
# 4. Enum 정규화
#    allowed_values에 대소문자 무시 매칭 → 정확한 값으로 교정
# ============================================================

def _normalize_enum(value: Any, allowed_values: list) -> Any:
    """
    enum 값을 allowed_values에 맞춰 정규화.
    대소문자 무시 매칭을 수행하여 allowed_values의 정확한 형태로 반환.
    """
    if value is None or allowed_values is None:
        return value

    # 정확한 매칭
    if value in allowed_values:
        return value

    # 대소문자 무시 매칭
    if isinstance(value, str):
        low = value.strip().lower()
        for av in allowed_values:
            if str(av).lower() == low:
                return av

    return value


def _normalize_list_enum(value: Any, allowed_values: Optional[list]) -> Any:
    """
    list[enum] 슬롯 값 정규화.
    - 리스트가 아니면 단일 값을 리스트로 래핑
    - 각 요소를 enum 정규화
    - 중복 제거 + 정렬
    """
    if value is None:
        return None

    # 단일 값 → 리스트 래핑
    if not isinstance(value, list):
        value = [value]

    normalized = []
    seen = set()
    for item in value:
        if allowed_values:
            item = _normalize_enum(item, allowed_values)
        # 중복 제거 (대소문자 무시)
        key = str(item).lower() if isinstance(item, str) else str(item)
        if key not in seen:
            seen.add(key)
            normalized.append(item)

    return sorted(normalized, key=lambda x: str(x).lower()) if normalized else None


# ============================================================
# 5. Normalize 맵 적용
#    slot_definition.yaml의 normalize 테이블을 적용한다.
#    예: o2_device의 "Nasal Cannula" → "NC"
# ============================================================

def _apply_normalize_map(value: Any, normalize_map: dict) -> Any:
    """
    slot_definition의 normalize 맵을 적용.
    - null/None 키 지원
    - 리스트 값은 각 요소에 재귀 적용
    - 대소문자 무시 매칭
    """
    if value is None:
        # null 키 체크 (예: o2_device normalize의 null: "RA")
        if "null" in normalize_map:
            return normalize_map["null"]
        if None in normalize_map:
            return normalize_map[None]
        return value

    if isinstance(value, list):
        return [_apply_normalize_map(v, normalize_map) for v in value]

    if isinstance(value, str):
        # 정확한 매칭
        if value in normalize_map:
            return normalize_map[value]
        # 대소문자 무시 매칭
        low = value.lower()
        for k, v in normalize_map.items():
            if isinstance(k, str) and k.lower() == low:
                return v

    return value


# ============================================================
# 6. 특수 슬롯 정규화
#    slot_definition이나 일반 규칙으로 커버되지 않는 슬롯별 로직
# ============================================================

def _normalize_culture_result(value: Any) -> Any:
    """
    culture_result 슬롯 정규화.
    이전 추출 단계에서 status를 정규화했더라도 누락 케이스를 한 번 더 보정한다.
    형태: {"status": "pos"/"neg"/"pending"/..., "organism": "..."} 또는 문자열
    """
    if not isinstance(value, dict):
        return value

    status = value.get("status")
    organism = value.get("organism")

    if isinstance(status, str):
        key = status.strip().upper()
        status_map = {
            "COLLECTED": "pending",
            "PENDING": "pending",
            "PRELIMINARY": "preliminary",
            "POSITIVE": "pos",
            "POS": "pos",
            "NEGATIVE": "neg",
            "NEG": "neg",
            "NO GROWTH": "neg",
        }
        if key in status_map:
            value["status"] = status_map[key]
        elif key == "FINAL":
            value["status"] = "pos" if organism else "neg"
        else:
            # 이미 정규화된 값 (pos, neg, pending 등) → 소문자 보정만
            value["status"] = status.strip().lower()

    return value


def _normalize_specimen_type(value: Any) -> Any:
    """
    specimen_type 슬롯: 대문자 → 소문자 정규화.
    예: "URINE" → "urine", "BLOOD" → "blood"
    """
    if isinstance(value, str):
        return value.strip().lower()
    return value


# ============================================================
# 7. 범위 검증
#    단위 보정 후 다시 한번 범위를 확인한다.
# ============================================================

def _validate_range(value: Any, slot_range: Optional[list]) -> tuple[bool, str]:
    """
    범위 검증. 수치형 값이 [min, max] 범위 내인지 확인.
    반환: (is_valid, reason)
    """
    if slot_range is None or value is None:
        return True, "ok"
    if not isinstance(value, (int, float)):
        return True, "ok"  # 수치가 아니면 범위 검증 불가 → pass
    lo, hi = slot_range
    if lo <= value <= hi:
        return True, "ok"
    return False, f"out_of_range [{lo},{hi}], got {value}"


def _validate_enum(value: Any, allowed_values: Optional[list]) -> tuple[bool, str]:
    """
    Enum 검증. 값이 allowed_values에 포함되는지 확인.
    """
    if allowed_values is None or value is None:
        return True, "ok"
    # bool은 enum 검증 대상이 아님
    if isinstance(value, (bool, list, dict)):
        return True, "ok"
    # 대소문자 무시 매칭
    str_allowed = [str(a).lower() for a in allowed_values]
    if str(value).lower() in str_allowed:
        return True, "ok"
    return False, f"invalid_value: {value} not in {allowed_values}"


# ============================================================
# 8. 레코드 단위 정규화 + 검증 (핵심 함수)
# ============================================================

def normalize_and_validate_record(
    record: dict,
    slot_def: SlotDefinition,
    drop_out_of_range: bool = True,
) -> dict:
    """
    단일 레코드(문서 1건)에 대해 정규화 + 검증을 수행한다.

    처리 순서:
      1) normalize 맵 적용 (slot_definition.yaml)
      2) 특수 슬롯 정규화 (culture_result, specimen_type)
      3) 단위 보정 (WBC, Platelet)
      4) 타입 강제 변환 (int, float, bool, tri_bool, enum, list)
      5) Enum 정규화 (allowed_values 매칭)
      6) Null/빈값 제거
      7) 범위 + Enum 최종 검증
      8) 필수 슬롯 누락 추적
    """
    slots_detail = record.get("slots_detail", [])
    doc_type = record.get("document_type", "")

    normalized = []          # 정규화된 슬롯 리스트
    warnings = []            # 검증 경고
    norm_applied = []        # 정규화 적용 기록

    for s in slots_detail:
        name = s.get("slot_name")
        value = s.get("value")
        original_value = value  # 변경 추적용

        sd = slot_def.get_slot_def(name)
        slot_type = slot_def.get_type(name) if slot_def.is_valid_slot(name) else "string"
        slot_range = slot_def.get_range(name)
        allowed = slot_def.get_allowed_values(name)
        normalize_map = slot_def.get_normalize_map(name)

        # ── Step 1: normalize 맵 적용 ──
        if normalize_map:
            value = _apply_normalize_map(value, normalize_map)

        # ── Step 2: 특수 슬롯 정규화 ──
        if name == "culture_result":
            value = _normalize_culture_result(value)
        elif name == "specimen_type":
            value = _normalize_specimen_type(value)

        # ── Step 3: 단위 보정 ──
        if name == "wbc_value":
            value = _correct_wbc_unit(value)
        elif name == "platelet_value":
            value = _correct_platelet_unit(value)

        # ── Step 4: 타입 강제 변환 ──
        if slot_type == "integer":
            value = _coerce_integer(value)
        elif slot_type == "float":
            value = _coerce_float(value)
        elif slot_type == "boolean":
            value = _coerce_boolean(value)
        elif slot_type == "tri_bool":
            value = _coerce_tri_bool(value)
        elif slot_type == "enum":
            value = _normalize_enum(value, allowed)
        elif slot_type.startswith("list"):
            value = _normalize_list_enum(value, allowed)

        # ── Step 5: Null/빈값 제거 ──
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        if isinstance(value, list) and len(value) == 0:
            continue

        # ── Step 6: 범위 검증 ──
        is_valid, reason = _validate_range(value, slot_range)
        if not is_valid:
            warnings.append({"slot": name, "value": value, "issue": reason})
            if drop_out_of_range:
                continue  # 범위 밖 값은 출력에서 제거

        # ── Step 7: Enum 검증 (list가 아닌 enum만) ──
        if slot_type == "enum" and allowed:
            is_valid, reason = _validate_enum(value, allowed)
            if not is_valid:
                warnings.append({"slot": name, "value": value, "issue": reason})
                # enum 불일치는 경고만, 제거하지 않음

        # ── 변경 추적 ──
        if value != original_value:
            norm_applied.append({
                "slot": name,
                "before": original_value,
                "after": value,
            })

        # ── 정규화된 슬롯 저장 ──
        new_s = dict(s)
        new_s["value"] = value
        normalized.append(new_s)

    # ── extracted_slots 재구성 ──
    record["slots_detail"] = normalized
    record["extracted_slots"] = {s["slot_name"]: s["value"] for s in normalized}

    # ── evidence_spans도 정규화된 슬롯에 맞춰 필터링 ──
    valid_slot_names = {s["slot_name"] for s in normalized}
    if "evidence_spans" in record:
        record["evidence_spans"] = [
            e for e in record["evidence_spans"]
            if e.get("slot") in valid_slot_names
        ]

    # ── 필수 슬롯 누락 추적 ──
    extracted_names = {s["slot_name"] for s in normalized}
    mandatory_missing = [
        m for m in slot_def.get_mandatory_slots(doc_type)
        if m not in extracted_names
    ]

    # ── 메타데이터 업데이트 ──
    record["_total_slots"] = len(normalized)
    record["_normalization_version"] = "norm_v4.1"

    if warnings:
        record["_validation_warnings"] = warnings
    elif "_validation_warnings" in record:
        del record["_validation_warnings"]

    if mandatory_missing:
        record["_mandatory_missing"] = mandatory_missing
    elif "_mandatory_missing" in record:
        del record["_mandatory_missing"]

    if norm_applied:
        record["_normalization_applied"] = norm_applied

    return record


# ============================================================
# 8-b. Risk / Severity 산출
#      문서 1건의 extracted_slots로부터 clinical_severity, ic_risk를 판정한다.
#      axis_spec risk_states 정의 기반:
#        clinical_severity : high / medium / low
#        ic_risk           : high / medium / low
# ============================================================

def _compute_risk(record: dict) -> dict:
    """
    문서 단위 risk level 산출.
    extracted_slots를 읽어 clinical_severity, ic_risk를 판정하고
    record에 추가한다.
    """
    slots = record.get("extracted_slots", {})

    # ── clinical_severity ──
    high_flags = []
    medium_flags = []

    # Vitals
    temp = slots.get("temp_value")
    if temp is not None:
        if temp >= 38.3 or temp <= 36.0:
            high_flags.append(f"temp={temp}")
        elif temp >= 38.0:
            medium_flags.append(f"temp={temp}")

    hr = slots.get("hr_value")
    if hr is not None:
        if hr >= 120:
            high_flags.append(f"hr={hr}")
        elif hr >= 100:
            medium_flags.append(f"hr={hr}")

    rr = slots.get("rr_value")
    if rr is not None:
        if rr >= 24:
            high_flags.append(f"rr={rr}")
        elif rr >= 20:
            medium_flags.append(f"rr={rr}")

    spo2 = slots.get("spo2_value")
    if spo2 is not None:
        if spo2 <= 92:
            high_flags.append(f"spo2={spo2}")
        elif spo2 <= 95:
            medium_flags.append(f"spo2={spo2}")

    sbp = slots.get("bp_sys")
    if sbp is not None:
        if sbp <= 90:
            high_flags.append(f"sbp={sbp}")
        elif sbp <= 100:
            medium_flags.append(f"sbp={sbp}")

    lactate = slots.get("lactate_value")
    if lactate is not None:
        if lactate >= 2.0:
            high_flags.append(f"lactate={lactate}")

    wbc = slots.get("wbc_value")
    if wbc is not None:
        if wbc >= 15 or wbc <= 4:
            high_flags.append(f"wbc={wbc}")

    # Events / findings
    if slots.get("altered_mentation") is True:
        high_flags.append("altered_mentation")

    if slots.get("notify_mentioned") is True:
        medium_flags.append("notify_mentioned")

    resp_event = slots.get("resp_support_event")
    if resp_event in ("start", "increase"):
        high_flags.append(f"resp_support={resp_event}")

    abx = slots.get("abx_event")
    if abx in ("escalate", "start", "change"):
        medium_flags.append(f"abx={abx}")

    if slots.get("dyspnea") is True:
        medium_flags.append("dyspnea")

    if slots.get("diarrhea") is True:
        medium_flags.append("diarrhea")

    pain = slots.get("pain_nrs_value")
    if pain is not None and pain >= 7:
        medium_flags.append(f"pain_nrs={pain}")

    if high_flags:
        clinical_severity = "high"
    elif medium_flags:
        clinical_severity = "medium"
    else:
        clinical_severity = "low"

    # ── ic_risk (infection control) ──
    ic_flags = []

    mdro = slots.get("mdro_flag")
    iso_req = slots.get("isolation_required")
    iso_applied = slots.get("isolation_applied")

    if mdro is True and iso_req and iso_req != "none" and not iso_applied:
        ic_flags.append("isolation_gap")
    if mdro is True:
        ic_flags.append("mdro_confirmed")
    if iso_req and iso_req not in ("none", "unknown"):
        ic_flags.append(f"isolation={iso_req}")

    if "isolation_gap" in ic_flags:
        ic_risk = "high"
    elif "mdro_confirmed" in ic_flags:
        ic_risk = "medium"
    elif ic_flags:
        ic_risk = "medium"
    else:
        ic_risk = "low"

    # ── record에 추가 ──
    record["clinical_severity"] = clinical_severity
    record["ic_risk"] = ic_risk
    record["_risk_evidence"] = {
        "clinical_high": high_flags,
        "clinical_medium": medium_flags,
        "ic_flags": ic_flags,
    }

    return record


# ============================================================
# 9. 파이프라인 실행
# ============================================================

def run_normalizer(
    input_path: str,
    output_path: str,
    slot_def_path: Optional[str],
) -> None:
    """
    Phase 5 전체 실행.
    tagged_slots_v4_1.jsonl → 정규화 + 검증 → tagged_slots_normalized.jsonl
    """
    # ── slot_definition 로드 ──
    slot_def = SlotDefinition(load_slot_definition(slot_def_path))
    if slot_def.enabled:
        print(f"📋 slot_definition 로드: {len(slot_def.slots)}개 슬롯 정의")
    else:
        print("⚠ slot_definition 미로드 — 최소 정규화만 수행")

    # ── 입력 파일 확인 ──
    if not os.path.exists(input_path):
        print(f"❌ 입력 파일 없음: {input_path}")
        return

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # ── 레코드별 정규화 + 검증 ──
    results = []
    with open(input_path, "r", encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            record = normalize_and_validate_record(record, slot_def)
            results.append(record)

    # ── 출력 ──
    with open(output_path, "w", encoding="utf-8") as fout:
        for record in results:
            fout.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # ────────────────────────────────────────────
    # 통계 출력
    # ────────────────────────────────────────────
    total_docs = len(results)
    total_slots = sum(r["_total_slots"] for r in results)

    print(f"\n✅ Phase 5 정규화 + 검증 완료")
    print(f"   입력: {input_path}")
    print(f"   출력: {output_path}")
    print(f"   문서: {total_docs}건, 슬롯: {total_slots}개 (avg {total_slots / max(total_docs, 1):.1f})")

    # ── 문서 타입별 통계 ──
    type_stats: dict[str, dict] = {}
    for r in results:
        t = r["document_type"]
        if t not in type_stats:
            type_stats[t] = {"count": 0, "slots": 0}
        type_stats[t]["count"] += 1
        type_stats[t]["slots"] += r["_total_slots"]
    print(f"   문서 타입별:")
    for t, s in sorted(type_stats.items()):
        avg = s["slots"] / max(s["count"], 1)
        print(f"     - {t}: {s['count']}건, {s['slots']}슬롯 (avg {avg:.1f})")

    # ── 정규화 적용 통계 ──
    norm_counter: Counter = Counter()
    for r in results:
        for n in r.get("_normalization_applied", []):
            norm_counter[n["slot"]] += 1
    if norm_counter:
        print(f"\n   🔄 정규화 적용 ({sum(norm_counter.values())}건):")
        for slot, cnt in norm_counter.most_common(20):
            print(f"     - {slot}: {cnt}건")
    else:
        print(f"\n   ✅ 추가 정규화 없음 (이전 단계에서 충분히 정규화됨)")

    # ── 검증 경고 통계 ──
    warn_counter: Counter = Counter()
    for r in results:
        for w in r.get("_validation_warnings", []):
            key = f"{w['slot']}:{w['issue']}"
            warn_counter[key] += 1
    if warn_counter:
        print(f"\n   ⚠ 검증 경고 ({sum(warn_counter.values())}건):")
        for key, cnt in warn_counter.most_common(20):
            print(f"     - {key}: {cnt}건")
    else:
        print(f"\n   ✅ 검증 경고 없음")

    # ── 필수 슬롯 누락 통계 ──
    mandatory_counter: Counter = Counter()
    for r in results:
        for m in r.get("_mandatory_missing", []):
            mandatory_counter[m] += 1
    if mandatory_counter:
        print(f"   📌 필수 슬롯 누락:")
        for slot, cnt in mandatory_counter.most_common():
            # 해당 슬롯이 mandatory인 문서 타입의 총 문서 수 계산
            total_relevant = sum(
                1 for r in results
                if slot in slot_def.get_mandatory_slots(r["document_type"])
            )
            rate = cnt / max(total_relevant, 1) * 100
            print(f"     - {slot}: {cnt}/{total_relevant}건 누락 ({rate:.1f}%)")


# ============================================================
# 10. CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="INFECT-GUARD Phase 5: Normalizer + Validator (v4.1)"
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT_PATH,
        help=f"Phase 2/4 출력 JSONL (기본: {DEFAULT_INPUT_PATH})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help=f"정규화 출력 JSONL (기본: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--slot-def",
        default=DEFAULT_SLOT_DEF_PATH,
        help=f"슬롯 정의 YAML (기본: {DEFAULT_SLOT_DEF_PATH})",
    )
    args = parser.parse_args()
    run_normalizer(args.input, args.output, getattr(args, "slot_def"))


if __name__ == "__main__":
    main()
