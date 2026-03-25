"""
09_load_nlp_slots.py
tagged_slots_FINAL.jsonl -> nlp_documents / tagged_slots / evidence_spans 적재

입력:
  - nlp/data/tagged_slots_FINAL.jsonl

출력:
  - nlp_documents INSERT
  - tagged_slots INSERT
  - evidence_spans INSERT
"""

import json
import os
import re
import time
from collections import defaultdict
from pathlib import Path

import oracledb
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 설정
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # final-prj/
INPUT_PATH = BASE_DIR / "nlp" / "data" / "tagged_slots_FINAL.jsonl"

DB_USER = os.getenv("ORACLE_USER")
DB_PASSWORD = os.getenv("ORACLE_PASSWORD")
DB_DSN = os.getenv("ORACLE_CONNECTION_STRING")

# 재실행 편의를 위해 기본값은 전체 재적재
RESET_TARGET_TABLES = True

DOC_TYPE_TO_SOURCE = {
    "nursing_note": ("nursing_notes", "note_id", "note_datetime"),
    "physician_note": ("physician_notes", "note_id", "note_datetime"),
    "lab_result": ("lab_results", "result_id", "result_datetime"),
    "radiology": ("radiology_reports", "report_id", "study_datetime"),
    "microbiology": ("microbiology_results", "result_id", "collection_datetime"),
}


# ============================================================
# 헬퍼
# ============================================================
def _fmt_hms(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def normalize_patient_id(raw_patient_id):
    """
    NLP/EMR 포맷 patient_id를 admissions 키 포맷으로 정규화.
    - patient_T01 -> T01
    - T01_Patient -> T01
    - T01 -> T01
    - 8자리 숫자 -> 그대로
    """
    if raw_patient_id is None:
        return None

    patient_id = str(raw_patient_id).strip()
    if not patient_id:
        return None

    if re.fullmatch(r"\d{8}", patient_id):
        return patient_id

    match = re.fullmatch(r"patient_(T\d+)", patient_id, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()

    match = re.fullmatch(r"(T\d+)_Patient", patient_id, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()

    if re.fullmatch(r"T\d+", patient_id, flags=re.IGNORECASE):
        return patient_id.upper()

    return patient_id


def to_iso_second(dt_obj):
    if dt_obj is None:
        return None
    return dt_obj.strftime("%Y-%m-%dT%H:%M:%S")


def parse_doc_seq(document_id):
    if not document_id:
        return 1
    match = re.search(r"_(\d{3})$", str(document_id))
    if not match:
        return 1
    return int(match.group(1))


def parse_doc_datetime_from_document_id(document_id):
    """
    document_id 우측 패턴(_YYYYMMDD_HHMM_SEQ)에서 datetime 추출.
    - M_11601773_21680321_0900_001
    - M_patient_T01_21810615_1130_001
    """
    if not document_id:
        return None

    text = str(document_id)
    match = re.search(r"_(\d{8})_(\d{4})_(\d{3})$", text)
    if not match:
        return None

    date_part = match.group(1)
    time_part = match.group(2)
    return (
        f"{date_part[0:4]}-{date_part[4:6]}-{date_part[6:8]}"
        f"T{time_part[0:2]}:{time_part[2:4]}:00"
    )


def infer_value_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def serialize_slot_value(value):
    if value is None:
        return None
    if isinstance(value, (dict, list, bool)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def build_admission_cache(cursor):
    cursor.execute("SELECT patient_id, admission_id FROM admissions")
    return {row[0]: row[1] for row in cursor.fetchall()}


def build_source_cache(cursor):
    """
    문서 타입별 source_id 캐시 구축.
    key: (doc_type, admission_id, iso_datetime, seq)
    value: source_id
    """
    cache = {}

    # nursing_note / physician_note / microbiology / radiology:
    # 동일 timestamp 다건을 seq로 구분 가능.
    sequential_doc_types = [
        "nursing_note",
        "physician_note",
        "microbiology",
        "radiology",
    ]
    for doc_type in sequential_doc_types:
        table_name, pk_col, dt_col = DOC_TYPE_TO_SOURCE[doc_type]
        sql = f"""
            SELECT {pk_col}, admission_id, {dt_col}
            FROM {table_name}
            ORDER BY {pk_col}
        """
        cursor.execute(sql)

        grouped = defaultdict(list)
        for source_id, admission_id, dt_val in cursor.fetchall():
            grouped[(admission_id, to_iso_second(dt_val))].append(source_id)

        for (admission_id, dt_iso), source_ids in grouped.items():
            for idx, source_id in enumerate(source_ids, start=1):
                cache[(doc_type, admission_id, dt_iso, idx)] = source_id

    # lab_result:
    # 1 JSON 문서가 N개의 lab row가 되므로 source_id는 동일 시각 묶음의 MIN(result_id)로 대표 저장.
    cursor.execute(
        """
        SELECT admission_id, result_datetime, MIN(result_id) AS source_id
        FROM lab_results
        GROUP BY admission_id, result_datetime
        """
    )
    for admission_id, dt_val, source_id in cursor.fetchall():
        cache[("lab_result", admission_id, to_iso_second(dt_val), 1)] = source_id

    return cache


def resolve_source_id(
    source_cache,
    doc_type,
    admission_id,
    doc_datetime_iso,
    seq,
    doc_id_datetime_iso=None,
):
    if doc_type == "lab_result":
        # lab은 seq 구분이 어려워 대표 row(min result_id)를 사용
        return source_cache.get((doc_type, admission_id, doc_datetime_iso, 1))

    if doc_type == "microbiology":
        # microbiology는 doc_datetime이 result_datetime 성격일 수 있어,
        # document_id의 시간(생성 시 collection_datetime 기준)도 fallback으로 사용한다.
        candidate_datetimes = [doc_datetime_iso]
        if doc_id_datetime_iso and doc_id_datetime_iso not in candidate_datetimes:
            candidate_datetimes.append(doc_id_datetime_iso)

        for dt_iso in candidate_datetimes:
            source_id = source_cache.get((doc_type, admission_id, dt_iso, seq))
            if source_id:
                return source_id
            source_id = source_cache.get((doc_type, admission_id, dt_iso, 1))
            if source_id:
                return source_id
        return None

    return (
        source_cache.get((doc_type, admission_id, doc_datetime_iso, seq))
        or source_cache.get((doc_type, admission_id, doc_datetime_iso, 1))
    )


def insert_nlp_document(cursor, row):
    sql = """
    INSERT INTO nlp_documents (
        admission_id, patient_id, document_type, source_table, source_id,
        doc_datetime, hd, d_number, context_tags_json,
        extraction_version, total_slots, mandatory_missing_json, validation_warnings_json
    ) VALUES (
        :admission_id, :patient_id, :document_type, :source_table, :source_id,
        TO_TIMESTAMP(:doc_datetime, 'YYYY-MM-DD"T"HH24:MI:SS'),
        :hd, :d_number, :context_tags_json,
        :extraction_version, :total_slots, :mandatory_missing_json, :validation_warnings_json
    )
    RETURNING document_id INTO :new_document_id
    """

    out_id = cursor.var(oracledb.NUMBER)
    params = dict(row)
    params["new_document_id"] = out_id
    cursor.execute(sql, params)
    return int(out_id.getvalue()[0])


def insert_tagged_slot(cursor, row):
    sql = """
    INSERT INTO tagged_slots (
        document_id, slot_name, slot_value, slot_value_type,
        extraction_method, confidence, evidence_text
    ) VALUES (
        :document_id, :slot_name, :slot_value, :slot_value_type,
        :extraction_method, :confidence, :evidence_text
    )
    RETURNING slot_id INTO :new_slot_id
    """
    out_id = cursor.var(oracledb.NUMBER)
    params = dict(row)
    params["new_slot_id"] = out_id
    cursor.execute(sql, params)
    return int(out_id.getvalue()[0])


def insert_evidence_span(cursor, row):
    sql = """
    INSERT INTO evidence_spans (
        slot_id, document_id, slot_name, text, confidence, method
    ) VALUES (
        :slot_id, :document_id, :slot_name, :text, :confidence, :method
    )
    """
    cursor.execute(sql, row)


def main():
    print("=" * 60)
    print("09_load_nlp_slots.py - NLP 슬롯/근거 적재")
    print("=" * 60)

    if not INPUT_PATH.exists():
        print(f"❌ 입력 파일 없음: {INPUT_PATH}")
        return

    print("\n[1/5] Oracle 연결 중...")
    oracledb.init_oracle_client(lib_dir="/opt/oracle/instantclient_23_3")
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
    cursor = conn.cursor()
    print("  ✓ 연결 성공")

    print("\n[2/5] admission/source 캐시 구축 중...")
    admission_cache = build_admission_cache(cursor)
    source_cache = build_source_cache(cursor)
    print(f"  ✓ admission 캐시: {len(admission_cache)}명")
    print(f"  ✓ source 캐시: {len(source_cache)}개")

    if RESET_TARGET_TABLES:
        print("\n[3/5] 대상 테이블 초기화 중...")
        cursor.execute("DELETE FROM evidence_spans")
        cursor.execute("DELETE FROM tagged_slots")
        cursor.execute("DELETE FROM nlp_documents")
        conn.commit()
        print("  ✓ 초기화 완료")
    else:
        print("\n[3/5] 대상 테이블 초기화 생략")

    print("\n[4/5] 적재 중...")
    start_t = time.time()

    counts = {
        "documents_inserted": 0,
        "slots_inserted": 0,
        "spans_inserted": 0,
        "skipped_no_admission": 0,
        "skipped_no_source": 0,
        "errors": 0,
    }

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            raw_line = line.strip()
            if not raw_line:
                continue

            try:
                rec = json.loads(raw_line)

                raw_patient_id = rec.get("patient_id")
                patient_id = normalize_patient_id(raw_patient_id)
                admission_id = admission_cache.get(patient_id)
                if not admission_id:
                    counts["skipped_no_admission"] += 1
                    continue

                doc_type = rec.get("document_type")
                if doc_type not in DOC_TYPE_TO_SOURCE:
                    counts["skipped_no_source"] += 1
                    continue

                source_table, _, _ = DOC_TYPE_TO_SOURCE[doc_type]
                doc_datetime = rec.get("doc_datetime")
                if not doc_datetime:
                    counts["skipped_no_source"] += 1
                    continue

                doc_datetime_iso = str(doc_datetime)[:19]
                seq = parse_doc_seq(rec.get("document_id"))
                doc_id_datetime_iso = parse_doc_datetime_from_document_id(rec.get("document_id"))
                source_id = resolve_source_id(
                    source_cache,
                    doc_type,
                    admission_id,
                    doc_datetime_iso,
                    seq,
                    doc_id_datetime_iso=doc_id_datetime_iso,
                )
                if not source_id:
                    counts["skipped_no_source"] += 1
                    continue

                nlp_doc_id = insert_nlp_document(
                    cursor,
                    {
                        "admission_id": admission_id,
                        "patient_id": patient_id,
                        "document_type": doc_type,
                        "source_table": source_table,
                        "source_id": source_id,
                        "doc_datetime": doc_datetime_iso,
                        "hd": rec.get("hd"),
                        "d_number": rec.get("d_number"),
                        "context_tags_json": json.dumps(rec.get("context_tags", {}), ensure_ascii=False),
                        "extraction_version": rec.get("_extraction_version"),
                        "total_slots": rec.get("_total_slots"),
                        "mandatory_missing_json": json.dumps(rec.get("_mandatory_missing", []), ensure_ascii=False),
                        "validation_warnings_json": json.dumps(rec.get("_validation_warnings", []), ensure_ascii=False),
                    },
                )
                counts["documents_inserted"] += 1

                slot_ids_by_name = defaultdict(list)
                for slot in rec.get("slots_detail", []):
                    slot_name = slot.get("slot_name")
                    if not slot_name:
                        continue

                    slot_id = insert_tagged_slot(
                        cursor,
                        {
                            "document_id": nlp_doc_id,
                            "slot_name": slot_name,
                            "slot_value": serialize_slot_value(slot.get("value")),
                            "slot_value_type": infer_value_type(slot.get("value")),
                            "extraction_method": slot.get("extraction_method"),
                            "confidence": slot.get("confidence"),
                            "evidence_text": slot.get("evidence_text"),
                        },
                    )
                    slot_ids_by_name[slot_name].append(slot_id)
                    counts["slots_inserted"] += 1

                span_slot_cursor = defaultdict(int)
                for span in rec.get("evidence_spans", []):
                    slot_name = span.get("slot")
                    if not slot_name:
                        continue

                    slot_candidates = slot_ids_by_name.get(slot_name, [])
                    slot_idx = span_slot_cursor[slot_name]
                    if not slot_candidates:
                        continue

                    if slot_idx >= len(slot_candidates):
                        slot_id = slot_candidates[-1]
                    else:
                        slot_id = slot_candidates[slot_idx]
                        span_slot_cursor[slot_name] += 1

                    insert_evidence_span(
                        cursor,
                        {
                            "slot_id": slot_id,
                            "document_id": nlp_doc_id,
                            "slot_name": slot_name,
                            "text": span.get("text"),
                            "confidence": span.get("confidence"),
                            "method": span.get("method"),
                        },
                    )
                    counts["spans_inserted"] += 1

            except Exception as e:  # noqa: BLE001
                counts["errors"] += 1
                if counts["errors"] <= 5:
                    print(f"  ✗ 에러 [line {line_num}]: {e}")

    conn.commit()
    elapsed = time.time() - start_t

    print("\n[5/5] 결과 확인")
    cursor.execute("SELECT COUNT(*) FROM nlp_documents")
    nlp_documents_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM tagged_slots")
    tagged_slots_cnt = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM evidence_spans")
    evidence_spans_cnt = cursor.fetchone()[0]

    print("\n" + "=" * 60)
    print("적재 결과")
    print("=" * 60)
    print(f"  nlp_documents:        {counts['documents_inserted']}건")
    print(f"  tagged_slots:         {counts['slots_inserted']}건")
    print(f"  evidence_spans:       {counts['spans_inserted']}건")
    print(f"  skipped(no admission):{counts['skipped_no_admission']}건")
    print(f"  skipped(no source):   {counts['skipped_no_source']}건")
    print(f"  errors:               {counts['errors']}건")
    print(f"  소요:                 {_fmt_hms(elapsed)}")

    print("\nDB row count")
    print(f"  nlp_documents: {nlp_documents_cnt}")
    print(f"  tagged_slots:  {tagged_slots_cnt}")
    print(f"  evidence_spans:{evidence_spans_cnt}")

    cursor.close()
    conn.close()
    print("\n✓ 완료")


if __name__ == "__main__":
    main()
