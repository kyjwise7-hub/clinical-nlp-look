"""
06_load_axis_snapshots.py
6A 산출물(axis_snapshots.jsonl) → axis_snapshots 테이블 적재

입력:
  - nlp/data/axis_snapshots.jsonl

출력:
  - axis_snapshots INSERT
"""

import json
import os
import re
import time
from pathlib import Path
from dotenv import load_dotenv
import oracledb

load_dotenv()

# ============================================================
# 설정
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # final-prj/
INPUT_PATH = BASE_DIR / 'nlp' / 'data' / 'axis_snapshots.jsonl'

DB_USER = os.getenv('ORACLE_USER')
DB_PASSWORD = os.getenv('ORACLE_PASSWORD')
DB_DSN = os.getenv('ORACLE_CONNECTION_STRING')

# 6A axis → DB axis_type 매핑
AXIS_TYPE_MAP = {
    'A_respiratory': 'RESPIRATORY',
    'B_infection_activity': 'INFECTION_ACTIVITY',
    'C_clinical_action': 'CLINICAL_ACTION',
    'E_infection_control': 'INFECTION_CONTROL',
    'F_symptom_subjective': 'SYMPTOM_SUBJECTIVE',
    'supplementary_vitals': 'SUPPLEMENTARY',
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


def get_admission_id(cursor, patient_id: str) -> int | None:
    """patient_id로 admission_id 조회"""
    cursor.execute(
        "SELECT admission_id FROM admissions WHERE patient_id = :pid",
        {'pid': patient_id}
    )
    row = cursor.fetchone()
    return row[0] if row else None


def build_admission_cache(cursor) -> dict:
    """전체 patient_id → admission_id 캐시 구축"""
    cursor.execute("SELECT patient_id, admission_id FROM admissions")
    return {row[0]: row[1] for row in cursor.fetchall()}


def normalize_patient_id(raw_patient_id: str | None) -> str | None:
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


# ============================================================
# INSERT
# ============================================================
def insert_snapshot(cursor, admission_id: int, snap: dict):
    """axis_snapshot 1건 INSERT"""

    sql = """
    INSERT INTO axis_snapshots (
        admission_id, axis_type, snapshot_datetime, shift,
        snapshot_json, supplementary_json, source_docs_json,
        hd, d_number
    ) VALUES (
        :admission_id, :axis_type,
        TO_TIMESTAMP(:snapshot_datetime, 'YYYY-MM-DD"T"HH24:MI:SS'),
        :shift,
        :snapshot_json, :supplementary_json, :source_docs_json,
        :hd, :d_number
    )
    """

    params = {
        'admission_id': admission_id,
        'axis_type': AXIS_TYPE_MAP.get(snap['axis'], snap['axis']),
        'snapshot_datetime': snap.get('doc_datetime'),
        'shift': snap.get('shift'),
        'snapshot_json': json.dumps(snap.get('slots', {}), ensure_ascii=False),
        'supplementary_json': json.dumps(snap['supplementary'], ensure_ascii=False) if snap.get('supplementary') else None,
        'source_docs_json': json.dumps(snap.get('source_docs', []), ensure_ascii=False),
        'hd': snap.get('hd'),
        'd_number': snap.get('d_number'),
    }

    cursor.execute(sql, params)


# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 60)
    print("06_load_axis_snapshots.py - 6A 산출물 적재")
    print("=" * 60)

    # 입력 파일 확인
    if not INPUT_PATH.exists():
        print(f"❌ 입력 파일 없음: {INPUT_PATH}")
        return

    # --------------------------------------------------------
    # 1. Oracle 연결
    # --------------------------------------------------------
    print("\n[1/3] Oracle 연결 중...")
    oracledb.init_oracle_client(lib_dir="/opt/oracle/instantclient_23_3")
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
    cursor = conn.cursor()
    print("  ✓ 연결 성공")

    # admission_id 캐시
    admission_cache = build_admission_cache(cursor)
    print(f"  ✓ admission 캐시: {len(admission_cache)}명")

    # --------------------------------------------------------
    # 2. 기존 데이터 삭제 (재실행 대비)
    # --------------------------------------------------------
    print("\n[2/3] 기존 데이터 삭제 중...")
    cursor.execute("DELETE FROM axis_snapshots")
    conn.commit()
    print("  ✓ 삭제 완료")

    # --------------------------------------------------------
    # 3. 적재
    # --------------------------------------------------------
    print("\n[3/3] 적재 중...")
    start_t = time.time()

    inserted = 0
    skipped = 0
    errors = 0

    with open(INPUT_PATH, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            snap = json.loads(line)
            raw_patient_id = snap.get('patient_id')
            patient_id = normalize_patient_id(raw_patient_id)
            admission_id = admission_cache.get(patient_id)

            if not admission_id:
                if skipped == 0:
                    if raw_patient_id != patient_id:
                        print(f"  ⚠ admission_id 없음: {raw_patient_id} (normalized: {patient_id})")
                    else:
                        print(f"  ⚠ admission_id 없음: {patient_id}")
                skipped += 1
                continue

            try:
                insert_snapshot(cursor, admission_id, snap)
                inserted += 1
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  ✗ 에러 [line {line_num}]: {e}")

    conn.commit()
    elapsed = time.time() - start_t

    # --------------------------------------------------------
    # 결과
    # --------------------------------------------------------
    print("\n" + "=" * 60)
    print("적재 결과")
    print("=" * 60)
    print(f"  적재:    {inserted}건")
    print(f"  스킵:    {skipped}건 (admission_id 없음)")
    print(f"  에러:    {errors}건")
    print(f"  소요:    {_fmt_hms(elapsed)}")

    # 검증
    cursor.execute("SELECT COUNT(*) FROM axis_snapshots")
    db_count = cursor.fetchone()[0]
    print(f"\n  DB 확인:  axis_snapshots = {db_count}건")

    cursor.execute("""
        SELECT axis_type, COUNT(*) 
        FROM axis_snapshots 
        GROUP BY axis_type 
        ORDER BY axis_type
    """)
    print("  축별:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]}건")

    cursor.close()
    conn.close()
    print("\n✅ 완료")


if __name__ == '__main__':
    main()
