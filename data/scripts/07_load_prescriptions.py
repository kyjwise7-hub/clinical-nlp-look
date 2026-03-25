"""
07_load_prescriptions.py
환자별 prescriptions CSV(10명) -> prescriptions 테이블 적재

입력:
  - data/outputs/prescriptions_by_patient/patient_*_admission_*_prescriptions.csv

출력:
  - prescriptions INSERT (완전 동일 row는 skip)
"""

import csv
import os
import time
from datetime import datetime
from pathlib import Path

import oracledb
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 설정
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # final-prj/
INPUT_DIR = BASE_DIR / "data" / "outputs" / "prescriptions_by_patient"
INPUT_GLOB = "patient_*_admission_*_prescriptions.csv"

DB_USER = os.getenv("ORACLE_USER")
DB_PASSWORD = os.getenv("ORACLE_PASSWORD")
DB_DSN = os.getenv("ORACLE_CONNECTION_STRING")

REQUIRED_COLUMNS = [
    "patient_id",
    "admission_id",
    "starttime",
    "drug",
    "prod_strength",
    "route",
]


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


def _normalize_row(row: dict) -> dict:
    normalized = {}
    for key in REQUIRED_COLUMNS:
        normalized[key] = (row.get(key) or "").strip()
    return normalized


def _validate_row(row: dict) -> tuple[bool, str]:
    for key in REQUIRED_COLUMNS:
        if not row.get(key):
            return False, f"필수값 누락: {key}"

    try:
        datetime.strptime(row["starttime"], "%Y-%m-%d")
    except ValueError:
        return False, f"날짜 형식 오류(starttime): {row['starttime']}"

    return True, ""


def _build_patient_admission_cache(cursor) -> dict:
    """
    patient_id -> [admission_id, ...] 캐시.
    현재 적재 데이터는 환자별 1개 admission이지만,
    다건일 경우 가장 마지막 admission_id를 사용한다.
    """
    cursor.execute("SELECT admission_id, patient_id FROM admissions ORDER BY admission_id")
    patient_to_admissions: dict[str, list[int]] = {}
    for admission_id, patient_id in cursor.fetchall():
        pid = str(patient_id)
        patient_to_admissions.setdefault(pid, []).append(int(admission_id))
    return patient_to_admissions


# ============================================================
# SQL
# ============================================================
INSERT_IF_NOT_EXISTS_SQL = """
INSERT INTO prescriptions (
    patient_id,
    admission_id,
    starttime,
    drug,
    prod_strength,
    route
)
SELECT
    :patient_id,
    :admission_id,
    TO_DATE(:starttime, 'YYYY-MM-DD'),
    :drug,
    :prod_strength,
    :route
FROM dual
WHERE NOT EXISTS (
    SELECT 1
    FROM prescriptions p
    WHERE p.patient_id = :patient_id
      AND p.admission_id = :admission_id
      AND p.starttime = TO_DATE(:starttime, 'YYYY-MM-DD')
      AND p.drug = :drug
      AND p.prod_strength = :prod_strength
      AND p.route = :route
)
"""


# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 60)
    print("07_load_prescriptions.py - 환자별 처방 CSV 적재")
    print("=" * 60)

    if not INPUT_DIR.exists():
        print(f"❌ 입력 디렉토리 없음: {INPUT_DIR}")
        return

    csv_files = sorted(INPUT_DIR.glob(INPUT_GLOB))
    if not csv_files:
        print(f"❌ 입력 CSV 없음: {INPUT_DIR}/{INPUT_GLOB}")
        return

    print(f"\n대상 CSV: {len(csv_files)}개")
    for p in csv_files:
        print(f"  - {p.name}")

    print("\n[1/3] Oracle 연결 중...")
    oracledb.init_oracle_client(lib_dir="/opt/oracle/instantclient_23_3")
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
    cursor = conn.cursor()
    print("  ✓ 연결 성공")

    patient_admission_map = _build_patient_admission_cache(cursor)
    print(f"  ✓ admission 캐시: {len(patient_admission_map)}명")

    total_read = 0
    total_inserted = 0
    total_skipped_duplicate = 0
    total_skipped_invalid = 0
    total_skipped_mismatch = 0
    total_remapped_admission = 0
    total_errors = 0

    started = time.time()
    print("\n[2/3] CSV 적재 중...")

    for csv_path in csv_files:
        file_read = 0
        file_inserted = 0
        file_skipped_duplicate = 0
        file_skipped_invalid = 0
        file_skipped_mismatch = 0
        file_remapped_admission = 0
        file_errors = 0

        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            missing_cols = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
            if missing_cols:
                print(f"  ✗ {csv_path.name}: 컬럼 누락 {missing_cols}")
                total_errors += 1
                continue

            for line_num, raw_row in enumerate(reader, 2):
                file_read += 1
                total_read += 1

                row = _normalize_row(raw_row)
                ok, reason = _validate_row(row)
                if not ok:
                    file_skipped_invalid += 1
                    total_skipped_invalid += 1
                    if file_skipped_invalid <= 3:
                        print(f"    ⚠ {csv_path.name}:{line_num} -> {reason}")
                    continue

                csv_admission_id = row["admission_id"]
                matched_admissions = patient_admission_map.get(row["patient_id"])

                if not matched_admissions:
                    file_skipped_mismatch += 1
                    total_skipped_mismatch += 1
                    if file_skipped_mismatch <= 3:
                        print(
                            f"    ⚠ {csv_path.name}:{line_num} -> admissions에 patient_id 없음: {row['patient_id']}"
                        )
                    continue

                # 환자별 admission이 여러 개면 최신(admission_id 최대) 사용
                db_admission_id = matched_admissions[-1]
                if len(matched_admissions) > 1 and file_read == 1:
                    print(
                        f"    ⚠ {csv_path.name} -> patient_id={row['patient_id']} admission 다건 "
                        f"{matched_admissions} / 사용={db_admission_id}"
                    )

                bind_row = dict(row)
                bind_row["admission_id"] = str(db_admission_id)

                if csv_admission_id != bind_row["admission_id"]:
                    file_remapped_admission += 1
                    total_remapped_admission += 1
                    if file_remapped_admission <= 3:
                        print(
                            f"    ℹ {csv_path.name}:{line_num} -> admission_id remap "
                            f"(csv={csv_admission_id} -> db={bind_row['admission_id']})"
                        )

                try:
                    cursor.execute(INSERT_IF_NOT_EXISTS_SQL, bind_row)
                    if cursor.rowcount == 1:
                        file_inserted += 1
                        total_inserted += 1
                    else:
                        file_skipped_duplicate += 1
                        total_skipped_duplicate += 1
                except Exception as e:
                    file_errors += 1
                    total_errors += 1
                    if file_errors <= 3:
                        print(f"    ✗ {csv_path.name}:{line_num} -> {e}")

        conn.commit()
        print(
            f"  ✓ {csv_path.name}: read={file_read}, inserted={file_inserted}, "
            f"duplicate_skip={file_skipped_duplicate}, invalid_skip={file_skipped_invalid}, "
            f"mismatch_skip={file_skipped_mismatch}, remap={file_remapped_admission}, errors={file_errors}"
        )

    elapsed = _fmt_hms(time.time() - started)

    print("\n[3/3] 결과 요약")
    print("=" * 60)
    print(f"총 읽음:             {total_read}")
    print(f"총 적재:             {total_inserted}")
    print(f"중복 스킵(완전일치): {total_skipped_duplicate}")
    print(f"유효성 스킵:         {total_skipped_invalid}")
    print(f"정합성 스킵:         {total_skipped_mismatch}")
    print(f"admission remap:     {total_remapped_admission}")
    print(f"에러:                {total_errors}")
    print(f"소요:                {elapsed}")

    cursor.execute("SELECT COUNT(*) FROM prescriptions")
    print(f"\nDB 확인: prescriptions = {cursor.fetchone()[0]}건")

    cursor.close()
    conn.close()
    print("\n✅ 완료")


if __name__ == "__main__":
    main()
