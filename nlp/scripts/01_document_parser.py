"""
INFECT-GUARD Phase 1: 문서 수집 및 파싱
========================================
입력: emr-generator/outputs/patient_*/hd_*.json
출력: nlp/data/parsed_documents.jsonl

실행 방법:
    python scripts/01_document_parser.py

    # 특정 환자만 처리:
    python scripts/01_document_parser.py --patient patient_16836931
"""

import json
import glob
import os
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional


# ============================================================
# 1. 설정
# ============================================================

# 실행 위치와 무관하게 __file__ 기준으로 기본 경로 계산
SCRIPT_DIR = Path(__file__).resolve().parent
NLP_ROOT = SCRIPT_DIR.parent
REPO_ROOT = NLP_ROOT.parent

DEFAULT_SYNTHETIC_DIR = str(REPO_ROOT / "emr-generator" / "outputs")
DEFAULT_OUTPUT_DIR = str(NLP_ROOT / "data")
OUTPUT_FILENAME = "parsed_documents.jsonl"


# ============================================================
# 2. Document ID 생성 규칙
# ============================================================
# {타입약자}_{환자ID}_{날짜}_{시간}_{순번}
# 예: N_16836931_21801021_0930_001 (간호기록)
#     P_16836931_21801021_0900_001 (의사노트)
#     L_16836931_21801021_0600_001 (검사결과)
#     R_16836931_21801021_1000_001 (영상)
#     M_16836931_21801021_1000_001 (미생물)

DOC_TYPE_PREFIX = {
    "nursing_note": "N",
    "physician_note": "P",
    "lab_result": "L",
    "radiology": "R",
    "microbiology": "M",
    "order": "O",
}

# 문서별 시간 필드명 매핑
DATETIME_FIELDS = {
    "nursing_note": "note_datetime",
    "physician_note": "note_datetime",
    "lab_result": "result_datetime",
    "radiology": "study_datetime",
    "microbiology": "collection_datetime",
    "order": "order_datetime",
}


# ============================================================
# 3. 환자 ID 추출
# ============================================================

def extract_patient_id(folder_name: str) -> str:
    """
    폴더명에서 환자 ID 추출.
    patient_16836931 → 16836931
    patient_12356657 → 12356657
    """
    match = re.search(r"patient_(\d+)", folder_name)
    if match:
        return match.group(1)
    return folder_name


# ============================================================
# 4. Document ID 생성
# ============================================================

_doc_id_counter = {}

def generate_doc_id(doc_type: str, patient_id: str, dt_str: str) -> str:
    """
    고유 document_id 생성.
    N_16836931_21801021_0930_001
    """
    prefix = DOC_TYPE_PREFIX.get(doc_type, "X")

    # datetime 파싱
    try:
        dt = datetime.fromisoformat(dt_str)
        date_part = dt.strftime("%Y%m%d").replace("2180", "2180")  # 그대로 유지
        time_part = dt.strftime("%H%M")
    except (ValueError, TypeError):
        date_part = "00000000"
        time_part = "0000"

    base = f"{prefix}_{patient_id}_{date_part}_{time_part}"

    # 같은 base가 여러 번 나오면 순번 증가
    _doc_id_counter[base] = _doc_id_counter.get(base, 0) + 1
    seq = str(_doc_id_counter[base]).zfill(3)

    return f"{base}_{seq}"


# ============================================================
# 5. 문서 타입별 파서
# ============================================================

def parse_nursing_note(doc: dict, patient_id: str, hd: int, d_number: int) -> dict:
    """간호기록 파싱 → 정규화된 문서 구조"""
    dt_str = doc.get("note_datetime", "")
    doc_id = generate_doc_id("nursing_note", patient_id, dt_str)

    return {
        "document_id": doc_id,
        "document_type": "nursing_note",
        "patient_id": patient_id,
        "note_datetime": dt_str,
        "hd": hd,
        "d_number": d_number,
        "shift": doc.get("shift"),
        "note_type": doc.get("note_type"),
        # 구조화된 필드
        "vital_signs": doc.get("vital_signs"),
        "subjective": doc.get("subjective"),
        "objective": doc.get("objective"),
        "assessment": doc.get("assessment"),
        "plan_action": doc.get("plan_action"),
        "o2_device": doc.get("o2_device"),
        "o2_flow": doc.get("o2_flow"),
        "intake": doc.get("intake"),
        "output": doc.get("output"),
        "notify_md": doc.get("notify_md", False),
        # 원문
        "raw_text": doc.get("raw_text", ""),
    }


def parse_physician_note(doc: dict, patient_id: str, hd: int, d_number: int) -> dict:
    """의사 노트 파싱"""
    dt_str = doc.get("note_datetime", "")
    doc_id = generate_doc_id("physician_note", patient_id, dt_str)

    return {
        "document_id": doc_id,
        "document_type": "physician_note",
        "patient_id": patient_id,
        "note_datetime": dt_str,
        "hd": hd,
        "d_number": d_number,
        "note_type": doc.get("note_type"),
        "subject_id": doc.get("subject_id"),
        "hadm_id": doc.get("hadm_id"),
        # 구조화된 필드
        "problem_list": doc.get("problem_list", []),
        "treatment_history": doc.get("treatment_history"),
        "subjective": doc.get("subjective"),
        "objective": doc.get("objective"),      # dict: vital_signs, lab_results, imaging
        "assessment": doc.get("assessment"),     # list
        "plan": doc.get("plan", []),             # list
        # 원문
        "raw_text": doc.get("raw_text", ""),
    }


def parse_lab_result(doc: dict, patient_id: str, hd: int, d_number: int) -> dict:
    """검사결과 파싱"""
    dt_str = doc.get("result_datetime", "")
    doc_id = generate_doc_id("lab_result", patient_id, dt_str)

    # 검사 수치를 labs dict로 통합
    lab_fields = [
        "wbc", "hgb", "plt", "cr", "bun", "na", "k",
        "glucose", "lactate", "crp", "procalcitonin",
        "ast", "alt", "creatinine",
    ]
    labs = {}
    for field in lab_fields:
        val = doc.get(field)
        if val is not None:
            labs[field] = val

    return {
        "document_id": doc_id,
        "document_type": "lab_result",
        "patient_id": patient_id,
        "result_datetime": dt_str,
        "hd": hd,
        "d_number": d_number,
        "subject_id": doc.get("subject_id"),
        # 구조화된 필드
        "labs": labs,
        # 원문
        "raw_text": doc.get("raw_text", ""),
    }


def parse_radiology(doc: dict, patient_id: str, hd: int, d_number: int) -> dict:
    """영상 판독 파싱"""
    dt_str = doc.get("study_datetime", "")
    doc_id = generate_doc_id("radiology", patient_id, dt_str)

    return {
        "document_id": doc_id,
        "document_type": "radiology",
        "patient_id": patient_id,
        "study_datetime": dt_str,
        "hd": hd,
        "d_number": d_number,
        "subject_id": doc.get("subject_id"),
        # 구조화된 필드
        "study_type": doc.get("study_type"),
        "technique": doc.get("technique"),
        "comparison": doc.get("comparison"),
        "findings": doc.get("findings"),
        "impression": doc.get("impression"),
        "severity": doc.get("severity"),
        # 원문
        "raw_text": doc.get("raw_text", ""),
    }


def parse_microbiology(doc: dict, patient_id: str, hd: int, d_number: int) -> dict:
    """미생물 검사 파싱"""
    dt_str = doc.get("collection_datetime", "")
    doc_id = generate_doc_id("microbiology", patient_id, dt_str)

    return {
        "document_id": doc_id,
        "document_type": "microbiology",
        "patient_id": patient_id,
        "collection_datetime": dt_str,
        "result_datetime": doc.get("result_datetime"),
        "hd": hd,
        "d_number": d_number,
        "subject_id": doc.get("subject_id"),
        # 구조화된 필드
        "specimen_type": doc.get("specimen_type"),
        "result_status": doc.get("result_status"),
        "gram_stain": doc.get("gram_stain"),
        "organism": doc.get("organism"),
        "colony_count": doc.get("colony_count"),
        "susceptibility": doc.get("susceptibility", []),
        "is_mdro": doc.get("is_mdro", False),
        "mdro_type": doc.get("mdro_type"),
        "comments": doc.get("comments"),
        # 원문
        "raw_text": doc.get("raw_text", ""),
    }


# 파서 라우터
PARSERS = {
    "nursing_note": parse_nursing_note,
    "physician_note": parse_physician_note,
    "lab_result": parse_lab_result,
    "radiology": parse_radiology,
    "microbiology": parse_microbiology,
}


# ============================================================
# 6. 메인 파서: JSON 파일 1개 → 파싱된 문서 리스트
# ============================================================

def parse_hd_file(filepath: str, patient_id: str) -> list[dict]:
    """
    hd_XX_dYY.json 파일 1개를 읽어서
    내부 documents[] 배열의 각 문서를 파싱.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    hd = data.get("hd", 0)
    d_number = data.get("d_number", 0)
    documents = data.get("documents", [])

    parsed = []
    for doc in documents:
        doc_type = doc.get("document_type", "unknown")
        parser = PARSERS.get(doc_type)

        if parser is None:
            print(f"  ⚠ 알 수 없는 문서 타입: {doc_type} (skip)")
            continue

        parsed_doc = parser(doc, patient_id, hd, d_number)

        # 메타데이터 추가
        parsed_doc["_source_file"] = os.path.basename(filepath)
        parsed_doc["_source_hd"] = hd
        parsed_doc["_source_d_number"] = d_number

        parsed.append(parsed_doc)

    return parsed


# ============================================================
# 7. 전체 파이프라인: 환자 폴더들 순회
# ============================================================

def run_phase1(
    synthetic_dir: str = DEFAULT_SYNTHETIC_DIR,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    patient_filter: Optional[str] = None,
) -> str:
    """
    Phase 1-2 전체 실행.

    1) emr-generator/outputs/patient_*/ 폴더 탐색
    2) 각 폴더 내 hd_*.json 파일 파싱
    3) 시간순 정렬
    4) nlp/data/parsed_documents.jsonl 출력

    Returns:
        출력 파일 경로
    """
    # 환자 폴더 탐색
    if patient_filter:
        patient_dirs = sorted(glob.glob(os.path.join(synthetic_dir, patient_filter)))
    else:
        patient_dirs = sorted(glob.glob(os.path.join(synthetic_dir, "patient_*")))

    if not patient_dirs:
        print(f"❌ 환자 폴더를 찾을 수 없습니다: {synthetic_dir}/patient_*")
        return ""

    print(f"📂 환자 폴더 {len(patient_dirs)}개 발견")

    all_parsed = []

    for patient_dir in patient_dirs:
        folder_name = os.path.basename(patient_dir)
        patient_id = extract_patient_id(folder_name)

        # hd_*.json 파일만 수집 (generation_summary, validation_report 등 제외)
        hd_files = sorted(glob.glob(os.path.join(patient_dir, "hd_*.json")))

        if not hd_files:
            print(f"  ⚠ {folder_name}: hd_*.json 파일 없음 (skip)")
            continue

        print(f"  👤 {folder_name} (ID: {patient_id}) — {len(hd_files)}개 파일")

        patient_docs = []
        for hd_file in hd_files:
            docs = parse_hd_file(hd_file, patient_id)
            patient_docs.extend(docs)
            print(f"     📄 {os.path.basename(hd_file)}: {len(docs)}건")

        # 환자 내 시간순 정렬
        patient_docs.sort(key=_get_sort_datetime)
        all_parsed.extend(patient_docs)

    # 출력
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, OUTPUT_FILENAME)

    with open(output_path, "w", encoding="utf-8") as f:
        for doc in all_parsed:
            f.write(json.dumps(doc, ensure_ascii=False, default=str) + "\n")

    print(f"\n✅ Phase 1-2 완료")
    print(f"   총 문서: {len(all_parsed)}건")
    print(f"   환자 수: {len(patient_dirs)}명")
    print(f"   출력: {output_path}")

    # 문서 타입별 통계
    type_counts = {}
    for doc in all_parsed:
        t = doc.get("document_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    print(f"   문서 타입별:")
    for t, c in sorted(type_counts.items()):
        print(f"     - {t}: {c}건")

    return output_path


def _get_sort_datetime(doc: dict) -> str:
    """정렬용 datetime 추출. 문서 타입에 따라 다른 필드 사용."""
    for field in ["note_datetime", "result_datetime", "study_datetime", "collection_datetime"]:
        val = doc.get(field)
        if val:
            return val
    return "9999-99-99"


# ============================================================
# 8. CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="INFECT-GUARD Phase 1-2: Document Parsing"
    )
    parser.add_argument(
        "--synthetic-dir",
        default=DEFAULT_SYNTHETIC_DIR,
        help=f"합성 데이터 디렉토리 (default: {DEFAULT_SYNTHETIC_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"출력 디렉토리 (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--patient",
        default=None,
        help="특정 환자 폴더만 처리 (예: patient_16836931)",
    )
    args = parser.parse_args()

    run_phase1(
        synthetic_dir=args.synthetic_dir,
        output_dir=args.output_dir,
        patient_filter=args.patient,
    )


if __name__ == "__main__":
    main()
