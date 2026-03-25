"""
INFECT-GUARD Slot Schema Validator (Standalone)
================================================
슬롯 JSONL을 slot_definition 기준으로 독립 검증한다.
주요 목적은 파이프라인 결과의 스키마/값 일관성 점검이다.

검증 항목:
  1. 슬롯명 유효성 — slot_definition에 정의된 슬롯인지
  2. 값 범위 검증 — numeric 슬롯의 [min, max] 범위 확인
  3. 허용값 검증 — enum 슬롯의 allowed_values 포함 여부
  4. 필수 슬롯 누락 — 문서 타입별 mandatory 슬롯 확인
  5. 범위 초과 값 제거 — drop_out_of_range=True 시 자동 제거

입력:  JSONL (예: tagged_slots_FINAL.jsonl)
출력:  JSONL (검증 경고/필수 누락 필드가 추가된 레코드)

실행:
  python scripts/utils/slot_schema_validator.py
  python scripts/utils/slot_schema_validator.py \\
    --input  nlp/data/tagged_slots_FINAL.jsonl \\
    --output nlp/data/tagged_slots_validated.jsonl \\
    --slot-def nlp/specs/slot_definition.yaml
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from typing import Any, Optional
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = SCRIPT_DIR.parent
NLP_ROOT = SCRIPTS_DIR.parent
REPO_ROOT = NLP_ROOT.parent

DEFAULT_INPUT_PATH = str(NLP_ROOT / "data" / "tagged_slots_FINAL.jsonl")
DEFAULT_OUTPUT_PATH = str(NLP_ROOT / "data" / "tagged_slots_validated.jsonl")
DEFAULT_SLOT_DEF_PATH = str(NLP_ROOT / "specs" / "slot_definition.yaml")


# ============================================================
# 1. SlotDefinition 로더
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
            print("⚠ pyyaml 미설치 — 검증 비활성화")
    return {}


class SlotDefinition:
    """
    slot_definition.yaml 파서.
    검증에 필요한 슬롯 정의와 문서 타입별 매핑을 관리한다.
    """

    def __init__(self, spec: dict):
        self.spec = spec or {}
        self.slots: dict[str, dict] = {}
        self.doc_mapping: dict[str, dict] = {}
        self._build_registry()

    @property
    def enabled(self) -> bool:
        return len(self.slots) > 0

    def _build_registry(self) -> None:
        """axis_* 및 supplementary_vitals 섹션에서 슬롯 정의를 수집"""
        for key, section in self.spec.items():
            if not isinstance(section, dict):
                continue
            if key.startswith("axis_") or key == "supplementary_vitals":
                for slot_name, slot_def in section.get("slots", {}).items():
                    if isinstance(slot_def, dict):
                        self.slots[slot_name] = slot_def

        # 문서 타입별 필수/권장/선택 슬롯 매핑
        mapping = self.spec.get("document_slot_mapping", {})
        for doc_type, doc_def in mapping.items():
            if isinstance(doc_def, dict):
                self.doc_mapping[doc_type] = {
                    "mandatory": doc_def.get("mandatory", []),
                    "recommended": doc_def.get("recommended", []),
                    "optional": doc_def.get("optional", []),
                }

    def validate_value(self, name: str, value: Any) -> tuple[bool, str]:
        """
        슬롯 값 검증.
        반환: (is_valid, reason)
        - "ok": 유효
        - "unknown_slot": 정의되지 않은 슬롯
        - "out_of_range [lo,hi]": 범위 초과
        - "invalid_value": 허용값 불일치
        """
        if name not in self.slots:
            return False, "unknown_slot"

        slot_def = self.slots[name]

        # 범위 검증 (수치형만)
        val_range = slot_def.get("range")
        if val_range and isinstance(value, (int, float)):
            lo, hi = val_range
            if not (lo <= value <= hi):
                return False, f"out_of_range [{lo},{hi}]"

        # 허용값 검증 (bool/list/dict 제외)
        allowed = slot_def.get("allowed_values")
        if allowed and not isinstance(value, (bool, list, dict)):
            str_allowed = [str(a).lower() for a in allowed]
            if str(value).lower() not in str_allowed:
                return False, "invalid_value"

        return True, "ok"

    def get_mandatory_slots(self, doc_type: str) -> list:
        """해당 문서 타입의 필수 슬롯 목록"""
        return self.doc_mapping.get(doc_type, {}).get("mandatory", [])


# ============================================================
# 2. 레코드 검증
# ============================================================

def validate_record(
    record: dict,
    slot_def: SlotDefinition,
    drop_out_of_range: bool = True,
) -> dict:
    """
    단일 레코드에 대해 검증을 수행한다.

    처리 순서:
      1) 각 슬롯의 이름/값을 slot_definition 대비 검증
      2) out_of_range 값은 제거 (drop_out_of_range=True 시)
      3) invalid_value/unknown_slot은 경고만 기록
      4) 필수 슬롯 누락 추적
    """
    slots_detail = record.get("slots_detail", [])
    warnings = []
    validated = []

    for s in slots_detail:
        name = s.get("slot_name")
        value = s.get("value")
        ok, reason = slot_def.validate_value(name, value)

        if not ok:
            warnings.append({"slot": name, "value": value, "issue": reason})
            # 범위 초과 값은 제거, 나머지는 경고만
            if drop_out_of_range and reason.startswith("out_of_range"):
                continue
        validated.append(s)

    # 경고 기록
    if warnings:
        record["_validation_warnings"] = warnings
    elif "_validation_warnings" in record:
        del record["_validation_warnings"]

    # 슬롯 업데이트
    record["slots_detail"] = validated
    record["extracted_slots"] = {s["slot_name"]: s["value"] for s in validated}
    record["_total_slots"] = len(validated)

    # evidence_spans 필터링 (제거된 슬롯에 대응하는 span도 제거)
    valid_slot_names = {s["slot_name"] for s in validated}
    if "evidence_spans" in record:
        record["evidence_spans"] = [
            e for e in record["evidence_spans"]
            if e.get("slot") in valid_slot_names
        ]

    # 필수 슬롯 누락 추적
    doc_type = record.get("document_type", "")
    extracted_names = {s.get("slot_name") for s in validated}
    missing = [
        m for m in slot_def.get_mandatory_slots(doc_type)
        if m not in extracted_names
    ]
    if missing:
        record["_mandatory_missing"] = missing
    elif "_mandatory_missing" in record:
        del record["_mandatory_missing"]

    return record


# ============================================================
# 3. 파이프라인 실행
# ============================================================

def run_validator(
    input_path: str,
    output_path: str,
    slot_def_path: Optional[str],
) -> None:
    """
    Standalone 검증 실행.
    정규화된 JSONL을 읽어 검증 후 결과를 출력한다.
    """
    slot_def = SlotDefinition(load_slot_definition(slot_def_path))
    if slot_def.enabled:
        print(f"📋 slot_definition 로드: {len(slot_def.slots)}개 슬롯 정의")
    else:
        print("⚠ slot_definition 미로드 — 검증 비활성화")

    if not os.path.exists(input_path):
        print(f"❌ 입력 파일 없음: {input_path}")
        return

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    results = []
    with open(input_path, "r", encoding="utf-8") as fin:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            record = validate_record(record, slot_def)
            results.append(record)

    with open(output_path, "w", encoding="utf-8") as fout:
        for record in results:
            fout.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    # ── 통계 ──
    total_docs = len(results)
    total_slots = sum(r["_total_slots"] for r in results)
    print(f"\n✅ Slot Schema 검증 완료")
    print(f"   입력: {input_path}")
    print(f"   출력: {output_path}")
    print(f"   문서: {total_docs}건, 슬롯: {total_slots}개")

    # 검증 경고 통계
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

    # 필수 슬롯 누락 통계
    mandatory_counter: Counter = Counter()
    for r in results:
        for m in r.get("_mandatory_missing", []):
            mandatory_counter[m] += 1
    if mandatory_counter:
        print(f"   📌 필수 슬롯 누락:")
        for slot, cnt in mandatory_counter.most_common():
            total_relevant = sum(
                1 for r in results
                if slot in slot_def.get_mandatory_slots(r["document_type"])
            )
            rate = cnt / max(total_relevant, 1) * 100
            print(f"     - {slot}: {cnt}/{total_relevant}건 누락 ({rate:.1f}%)")


# ============================================================
# 4. CLI
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="INFECT-GUARD Slot Schema Validator (Standalone)"
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT_PATH,
        help=f"검증 대상 JSONL (기본: {DEFAULT_INPUT_PATH})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_PATH,
        help=f"검증 결과 JSONL (기본: {DEFAULT_OUTPUT_PATH})",
    )
    parser.add_argument(
        "--slot-def",
        default=DEFAULT_SLOT_DEF_PATH,
        help=f"슬롯 정의 YAML (기본: {DEFAULT_SLOT_DEF_PATH})",
    )
    args = parser.parse_args()
    run_validator(args.input, args.output, getattr(args, "slot_def"))


if __name__ == "__main__":
    main()
