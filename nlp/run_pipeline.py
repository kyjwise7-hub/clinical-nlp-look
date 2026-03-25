#!/usr/bin/env python3
"""
INFECT-GUARD 파이프라인 실행 스크립트
=======================================
실행 순서:
  01_document_parser.py
  02_rule_extractor.py
  03_ner_train.py (predict; 가능 시)
  04_ner_extractor.py
  05_normalizer.py
  utils/slot_schema_validator.py
  06a_axis_snapshot_generator.py
  06b_trajectory_event_generator.py

실행:
    python run_pipeline.py

특정 환자만:
    python run_pipeline.py --patient patient_19548143
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
DATA = ROOT / "data"
SPECS = ROOT / "specs"


def _run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(ROOT))


def _has_modules(names: list[str]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for name in names:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    return len(missing) == 0, missing


def _looks_like_hf_model_dir(path: Path) -> bool:
    weight_files = [
        "pytorch_model.bin",
        "model.safetensors",
        "tf_model.h5",
        "model.ckpt.index",
        "flax_model.msgpack",
    ]
    return any((path / name).exists() for name in weight_files)


def _write_empty_jsonl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="INFECT-GUARD full pipeline runner")
    parser.add_argument("--patient", default=None, help="특정 환자만 처리 (예: patient_19548143)")
    parser.add_argument(
        "--disable-ner",
        action="store_true",
        help="Phase 3(predict)/Phase 4 NER 보완을 비활성화하고 rule 결과만 사용",
    )
    args = parser.parse_args()

    DATA.mkdir(parents=True, exist_ok=True)

    parsed_docs = DATA / "parsed_documents.jsonl"
    rule_out = DATA / "tagged_slots_rule.jsonl"
    ner_pred = DATA / "ner_predictions.jsonl"
    merged_out = DATA / "tagged_slots_v4_1.jsonl"
    final_out = DATA / "tagged_slots_FINAL.jsonl"
    validated_out = DATA / "tagged_slots_validated.jsonl"
    snapshots_out = DATA / "axis_snapshots.jsonl"
    events_out = DATA / "trajectory_events.jsonl"

    # 01
    print("\n" + "=" * 60)
    print("Phase 1: 문서 파싱 (01_document_parser.py)")
    print("=" * 60)
    cmd_phase1 = [
        sys.executable,
        "scripts/01_document_parser.py",
        "--output-dir", str(DATA),
    ]
    if args.patient:
        cmd_phase1.extend(["--patient", args.patient])
    _run(cmd_phase1)

    # 02
    print("\n" + "=" * 60)
    print("Phase 2: 규칙 기반 추출 (02_rule_extractor.py)")
    print("=" * 60)
    _run([
        sys.executable,
        "scripts/02_rule_extractor.py",
        "--input", str(parsed_docs),
        "--output", str(rule_out),
        "--dict", str(SPECS / "dictionary.yaml"),
        "--slot-def", str(SPECS / "slot_definition.yaml"),
        "--axis-spec", str(SPECS / "axis_spec.yml"),
    ])

    # 03 / 04
    print("\n" + "=" * 60)
    print("Phase 3-4: NER 예측 및 병합 (03_ner_train.py / 04_ner_extractor.py)")
    print("=" * 60)

    run_ner = not args.disable_ner
    model_dir = ROOT / "models" / "ner"
    model_predict_dir = model_dir
    best_dir = model_dir / "best"
    if not _looks_like_hf_model_dir(model_predict_dir) and _looks_like_hf_model_dir(best_dir):
        model_predict_dir = best_dir
        print(f"ℹ Phase 3 모델 경로 보정: {model_dir} -> {model_predict_dir}")

    ok_ner_runtime, missing = _has_modules(["numpy", "torch", "transformers", "seqeval"])
    has_model_files = _looks_like_hf_model_dir(model_predict_dir)

    if run_ner and ok_ner_runtime and has_model_files:
        try:
            _run([
                sys.executable,
                "scripts/03_ner_train.py",
                "predict",
                "--input", str(parsed_docs),
                "--model", str(model_predict_dir),
                "--output", str(ner_pred),
            ])
        except subprocess.CalledProcessError as e:
            print(f"⚠ Phase 3 실행 실패로 skip: {e}")
            _write_empty_jsonl(ner_pred)
    else:
        reasons: list[str] = []
        if args.disable_ner:
            reasons.append("--disable-ner 지정")
        if not ok_ner_runtime:
            reasons.append(f"필수 패키지 누락: {', '.join(missing)}")
        if not model_dir.exists():
            reasons.append(f"모델 디렉토리 없음: {model_dir}")
        elif not has_model_files:
            reasons.append(
                f"모델 파일 없음: {model_dir} (또는 {best_dir})에 "
                "pytorch_model.bin/model.safetensors 필요"
            )
        print(f"⚠ Phase 3 skip ({'; '.join(reasons)})")
        _write_empty_jsonl(ner_pred)

    _run([
        sys.executable,
        "scripts/04_ner_extractor.py",
        "--rule-input", str(rule_out),
        "--ner-pred", str(ner_pred),
        "--parsed-docs", str(parsed_docs),
        "--output", str(merged_out),
    ])

    # 05
    print("\n" + "=" * 60)
    print("Phase 5: 정규화 + 검증 (05_normalizer.py)")
    print("=" * 60)
    _run([
        sys.executable,
        "scripts/05_normalizer.py",
        "--input", str(merged_out),
        "--output", str(final_out),
        "--slot-def", str(SPECS / "slot_definition.yaml"),
    ])

    # standalone validator
    print("\n" + "=" * 60)
    print("Standalone Validator: Slot Schema 검증 (utils/slot_schema_validator.py)")
    print("=" * 60)
    _run([
        sys.executable,
        "scripts/utils/slot_schema_validator.py",
        "--input", str(final_out),
        "--output", str(validated_out),
        "--slot-def", str(SPECS / "slot_definition.yaml"),
    ])

    # 06a
    print("\n" + "=" * 60)
    print("Phase 6A: Axis Snapshot 생성 (06a_axis_snapshot_generator.py)")
    print("=" * 60)
    _run([
        sys.executable,
        "scripts/06a_axis_snapshot_generator.py",
        "--input", str(final_out),
        "--output", str(snapshots_out),
        "--spec", str(SPECS / "axis_spec.yml"),
    ])

    # 06b
    print("\n" + "=" * 60)
    print("Phase 6B: Trajectory Event 생성 (06b_trajectory_event_generator.py)")
    print("=" * 60)
    _run([
        sys.executable,
        "scripts/06b_trajectory_event_generator.py",
        "--input", str(snapshots_out),
        "--output", str(events_out),
        "--rules", str(SPECS / "diff_rules.yaml"),
    ])

    print(f"\n✅ Final outputs:")
    print(f"   - {final_out}")
    print(f"   - {validated_out}")
    print(f"   - {snapshots_out}")
    print(f"   - {events_out}")


if __name__ == "__main__":
    main()
