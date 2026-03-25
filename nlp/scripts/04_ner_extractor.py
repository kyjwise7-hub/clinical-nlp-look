
#!/usr/bin/env python3
"""
INFECT-GUARD Phase 4: NER 기반 슬롯 보완

02_rule_extractor.py 결과를 받아 NER 예측으로 빈 슬롯만 채운다.
  - 규칙 기반으로 이미 추출한 슬롯은 유지 (규칙 우선)
  - NER은 규칙이 놓친 슬롯만 추가

실행 방법:
    python scripts/04_ner_extractor.py \\
        --rule-input  tagged_slots_rule.jsonl \\
        --ner-pred    ner_predictions.jsonl \\
        --parsed-docs parsed_documents.jsonl \\
        --output      tagged_slots_merged.jsonl
"""
import argparse
import json
import os
import re
from typing import Any, Optional


# Simple NER adapter:
# - Expects precomputed predictions (JSONL) keyed by document_id.
# - Each line format (recommended):
#   {"document_id": "...", "entities": [{"label": "PAIN_NRS", "text": "NRS 4/10", "value": 4, "start": 10, "end": 16, "score": 0.82}, ...]}
#
# You can also provide entities with "slot_name" directly; then label mapping is skipped.

LABEL_TO_SLOT = {
    "PAIN_NRS": "pain_nrs_value",
    "PAIN_LOCATION": "pain_location_hint",
    "DYSPNEA": "dyspnea",
    "WOB": "work_of_breathing",
    "NAUSEA": "nausea_vomiting",
    "DIARRHEA": "diarrhea",
    "O2_DEVICE": "o2_device",
    "O2_FLOW": "o2_flow_lpm",
    "SPO2": "spo2_value",
    "TEMP": "temp_value",
    "HR": "hr_value",
    "RR": "rr_value",
    "BP_SYS": "bp_sys",
    "BP_DIA": "bp_dia",
    "ISOLATION_REQUIRED": "isolation_required",
    "MDRO_FLAG": "mdro_flag",
    "CULTURE_ORDERED": "culture_ordered",
    "ABX_EVENT": "abx_event",
}

NUMERIC_SLOTS = {
    "pain_nrs_value",
    "o2_flow_lpm",
    "spo2_value",
    "temp_value",
    "hr_value",
    "rr_value",
    "bp_sys",
    "bp_dia",
}

BOOLEAN_SLOTS = {
    "dyspnea",
    "nausea_vomiting",
    "diarrhea",
    "altered_mentation",
}


def load_ner_predictions(path: Optional[str]) -> dict:
    if not path:
        return {}
    if not os.path.exists(path):
        print(f"⚠ NER predictions file not found: {path}")
        return {}
    data = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            doc_id = obj.get("document_id")
            if not doc_id:
                continue
            entities = obj.get("entities") or obj.get("spans") or []
            data[doc_id] = entities
    return data


def extract_from_ner(
    raw_text: str,
    doc_type: str,
    document_id: Optional[str] = None,
    ner_predictions: Optional[dict] = None,
) -> list[dict]:
    if not raw_text:
        return []
    if not ner_predictions or not document_id:
        return []

    entities = ner_predictions.get(document_id) or []
    slots = []

    for ent in entities:
        slot_name = ent.get("slot_name")
        if not slot_name:
            label = (ent.get("label") or ent.get("type") or "").upper()
            slot_name = LABEL_TO_SLOT.get(label)
        if not slot_name:
            continue

        value = ent.get("value")
        text = ent.get("text")
        start = ent.get("start")
        end = ent.get("end")
        score = ent.get("score")

        if value is None:
            value = _coerce_value(slot_name, text)
        if value is None and start is not None and end is not None:
            try:
                text = raw_text[start:end]
                value = _coerce_value(slot_name, text)
            except Exception:
                pass

        if value is None:
            continue

        evidence = text or (raw_text[start:end] if start is not None and end is not None else "")
        slots.append({
            "slot_name": slot_name,
            "value": value,
            "extraction_method": "ner",
            "confidence": float(score) if score is not None else 0.75,
            "evidence_text": (evidence or "")[:120],
        })

    return slots


def _coerce_value(slot_name: str, text: Optional[str]) -> Any:
    if text is None:
        return True if slot_name in BOOLEAN_SLOTS else None

    if slot_name in BOOLEAN_SLOTS:
        return True

    if slot_name in NUMERIC_SLOTS:
        m = re.search(r"(\d+(?:\.\d+)?)", text)
        if not m:
            return None
        num = m.group(1)
        if slot_name in {"spo2_value", "hr_value", "rr_value", "bp_sys", "bp_dia", "pain_nrs_value"}:
            try:
                return int(float(num))
            except ValueError:
                return None
        try:
            return float(num)
        except ValueError:
            return None

    # Categorical heuristics
    lower = text.lower()
    if slot_name == "isolation_required":
        if "contact" in lower:
            return "contact"
        if "droplet" in lower:
            return "droplet"
        if "airborne" in lower:
            return "airborne"
        if "enteric" in lower:
            return "enteric"
    if slot_name == "o2_device":
        if "nasal" in lower or "nc" in lower:
            return "NC"
        if "room air" in lower or lower.strip() == "ra":
            return "RA"
        if "simple mask" in lower:
            return "SM"
        if "venturi" in lower:
            return "VM"
        if "non-rebreather" in lower or "nrm" in lower:
            return "NRM"
        if "hfnc" in lower or "high flow" in lower:
            return "HFNC"

    return text.strip()


# ============================================================
# Phase 4 CLI: Rule 결과 + NER 예측 → 병합
# ============================================================

def merge_ner_into_rule(
    rule_input: str,
    ner_pred_path: str,
    parsed_docs_path: str,
    output_path: str,
) -> None:
    """
    Phase 2 결과(rule_input)에 NER 슬롯을 보완하여 output에 기록.
    Rule이 이미 채운 슬롯은 건드리지 않고, 빈 슬롯만 NER로 채운다.
    """
    # 1) NER predictions 로드
    ner_predictions = load_ner_predictions(ner_pred_path)

    # 2) parsed_documents 로드 (raw_text 필요)
    parsed = {}
    with open(parsed_docs_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            parsed[doc.get("document_id")] = doc

    # 3) Rule 결과 읽으면서 NER merge
    total_ner_added = 0
    ner_slot_counts: dict[str, int] = {}
    results = []

    with open(rule_input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            doc_id = rec.get("document_id")
            doc_type = rec.get("document_type", "")
            raw_text = parsed.get(doc_id, {}).get("raw_text", "")

            # 기존 Rule 슬롯 이름 집합
            existing_slots = {s["slot_name"] for s in rec.get("slots_detail", [])}

            # NER 슬롯 추출
            ner_slots = extract_from_ner(raw_text, doc_type, doc_id, ner_predictions)

            # 빈 슬롯만 추가
            # mdro_flag는 microbiology 문서의 rule 추출만 신뢰 (NER은 단순 언급도 잡아냄)
            MICROBIOLOGY_ONLY_SLOTS = {"mdro_flag"}
            added = 0
            for ns in ner_slots:
                if ns["slot_name"] in MICROBIOLOGY_ONLY_SLOTS and doc_type != "microbiology":
                    continue
                if ns["slot_name"] not in existing_slots:
                    rec["slots_detail"].append(ns)
                    rec[ns["slot_name"]] = ns["value"]
                    existing_slots.add(ns["slot_name"])
                    ner_slot_counts[ns["slot_name"]] = ner_slot_counts.get(ns["slot_name"], 0) + 1
                    added += 1
            total_ner_added += added
            results.append(rec)

    # 4) 출력
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n✅ Phase 4 완료 (NER 보완)")
    print(f"   입력: {rule_input}")
    print(f"   NER predictions: {ner_pred_path}")
    print(f"   출력: {output_path}")
    print(f"   NER 보완 슬롯: {total_ner_added}개")
    if ner_slot_counts:
        for name, cnt in sorted(ner_slot_counts.items(), key=lambda x: -x[1]):
            print(f"     - {name}: {cnt}건")


def main():
    parser = argparse.ArgumentParser(description="Phase 4: NER 보완 — Rule 결과에 NER 슬롯 병합")
    parser.add_argument("--rule-input", required=True, help="Phase 2 Rule 결과 JSONL")
    parser.add_argument("--ner-pred", required=True, help="NER predictions JSONL")
    parser.add_argument("--parsed-docs", required=True, help="parsed_documents.jsonl (raw_text 참조)")
    parser.add_argument("--output", required=True, help="병합 결과 JSONL")
    args = parser.parse_args()

    merge_ner_into_rule(args.rule_input, args.ner_pred, args.parsed_docs, args.output)


if __name__ == "__main__":
    main()
