"""
08_load_synthetic_extensions.py
합성 환자(8자리 숫자 + T01~T03)용 확장 mock 데이터 적재

적재 대상 테이블:
  - wards, rooms, beds
  - transfer_cases
  - patient_status
  - bed_status

원칙:
  - 합성 환자 코호트만 처리 (FE display-only ID 제외)
  - 재실행 가능(idempotent)하도록 대상 테이블 정리 후 재삽입
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, time as dtime
from pathlib import Path

from dotenv import load_dotenv
import oracledb


ROOT_DIR = Path(__file__).resolve().parents[2]  # final-prj/
load_dotenv(ROOT_DIR / ".env")

DB_USER = os.getenv("ORACLE_USER")
DB_PASSWORD = os.getenv("ORACLE_PASSWORD")
DB_DSN = os.getenv("ORACLE_CONNECTION_STRING")

INFECTION_MAP = {
    "P": "Pneumonia",
    "U": "UTI",
    "G": "Waterborne",
    "M": "MDRO",
    "T": "Tick-borne",
}

ROOM_SPECS = [
    # 2F - 일반/호흡기
    {
        "room_id": "SX-2F-201",
        "ward_id": "2F",
        "room_number": "201",
        "room_type": "QUAD",
        "capacity": 4,
        "is_isolation": 0,
        "has_aiir": 0,
        "has_dedicated_toilet": 0,
        "isolation_type": None,
        "tier": None,
        "needs_cleaning": 0,
    },
    {
        "room_id": "SX-2F-202",
        "ward_id": "2F",
        "room_number": "202",
        "room_type": "QUAD",
        "capacity": 4,
        "is_isolation": 0,
        "has_aiir": 0,
        "has_dedicated_toilet": 0,
        "isolation_type": None,
        "tier": None,
        "needs_cleaning": 0,
    },
    {
        "room_id": "SX-2F-203",
        "ward_id": "2F",
        "room_number": "203",
        "room_type": "QUAD",
        "capacity": 4,
        "is_isolation": 0,
        "has_aiir": 0,
        "has_dedicated_toilet": 0,
        "isolation_type": None,
        "tier": None,
        "needs_cleaning": 0,
    },
    # 3F - UTI/GI
    {
        "room_id": "SX-3F-301",
        "ward_id": "3F",
        "room_number": "301",
        "room_type": "QUAD",
        "capacity": 4,
        "is_isolation": 0,
        "has_aiir": 0,
        "has_dedicated_toilet": 0,
        "isolation_type": None,
        "tier": None,
        "needs_cleaning": 0,
    },
    {
        "room_id": "SX-3F-302",
        "ward_id": "3F",
        "room_number": "302",
        "room_type": "QUAD",
        "capacity": 4,
        "is_isolation": 0,
        "has_aiir": 0,
        "has_dedicated_toilet": 0,
        "isolation_type": None,
        "tier": None,
        "needs_cleaning": 0,
    },
    {
        "room_id": "SX-3F-303",
        "ward_id": "3F",
        "room_number": "303",
        "room_type": "QUAD",
        "capacity": 4,
        "is_isolation": 0,
        "has_aiir": 0,
        "has_dedicated_toilet": 0,
        "isolation_type": None,
        "tier": None,
        "needs_cleaning": 0,
    },
    # 5F - 격리
    {
        "room_id": "SX-5F-501",
        "ward_id": "5F",
        "room_number": "501",
        "room_type": "SINGLE",
        "capacity": 1,
        "is_isolation": 1,
        "has_aiir": 1,
        "has_dedicated_toilet": 1,
        "isolation_type": "CONTACT",
        "tier": "S",
        "needs_cleaning": 0,
    },
    {
        "room_id": "SX-5F-502",
        "ward_id": "5F",
        "room_number": "502",
        "room_type": "SINGLE",
        "capacity": 1,
        "is_isolation": 1,
        "has_aiir": 1,
        "has_dedicated_toilet": 1,
        "isolation_type": "CONTACT",
        "tier": "S",
        "needs_cleaning": 0,
    },
    {
        "room_id": "SX-5F-503",
        "ward_id": "5F",
        "room_number": "503",
        "room_type": "SINGLE",
        "capacity": 1,
        "is_isolation": 1,
        "has_aiir": 1,
        "has_dedicated_toilet": 1,
        "isolation_type": "CONTACT",
        "tier": "S",
        "needs_cleaning": 0,
    },
    {
        "room_id": "SX-5F-504",
        "ward_id": "5F",
        "room_number": "504",
        "room_type": "DOUBLE",
        "capacity": 2,
        "is_isolation": 1,
        "has_aiir": 0,
        "has_dedicated_toilet": 1,
        "isolation_type": "CONTACT",
        "tier": "A",
        "needs_cleaning": 0,
    },
    {
        "room_id": "SX-5F-505",
        "ward_id": "5F",
        "room_number": "505",
        "room_type": "DOUBLE",
        "capacity": 2,
        "is_isolation": 1,
        "has_aiir": 0,
        "has_dedicated_toilet": 0,
        "isolation_type": "DROPLET",
        "tier": "B",
        "needs_cleaning": 0,
    },
    {
        "room_id": "SX-5F-506",
        "ward_id": "5F",
        "room_number": "506",
        "room_type": "DOUBLE",
        "capacity": 2,
        "is_isolation": 1,
        "has_aiir": 0,
        "has_dedicated_toilet": 0,
        "isolation_type": "DROPLET",
        "tier": "B",
        "needs_cleaning": 1,
    },
]

WARD_SPECS = [
    {"ward_id": "2F", "ward_name": "일반 병동", "floor": 2, "is_isolation_ward": 0},
    {"ward_id": "3F", "ward_name": "수술 후 병동", "floor": 3, "is_isolation_ward": 0},
    {"ward_id": "5F", "ward_name": "격리 병동", "floor": 5, "is_isolation_ward": 1},
]


def _fmt_hms(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def bind_list(prefix: str, values: list[str | int]) -> tuple[str, dict]:
    placeholders = ", ".join(f":{prefix}{i}" for i in range(len(values)))
    binds = {f"{prefix}{i}": v for i, v in enumerate(values)}
    return placeholders, binds


def infection_type_from_code(code: str | None) -> str:
    if not code:
        return "Pneumonia"
    prefix = code[0].upper()
    return INFECTION_MAP.get(prefix, "Pneumonia")


def build_room_beds() -> tuple[list[dict], dict[str, dict]]:
    beds = []
    bed_catalog: dict[str, dict] = {}
    for room in ROOM_SPECS:
        for i in range(1, room["capacity"] + 1):
            bed_id = f"{room['room_id']}-{i}"
            bed = {
                "bed_id": bed_id,
                "room_id": room["room_id"],
                "bed_number": str(i),
            }
            beds.append(bed)
            bed_catalog[bed_id] = {
                "room_id": room["room_id"],
                "ward_id": room["ward_id"],
            }
    return beds, bed_catalog


def choose_mdro_type(infection_code: str | None) -> str | None:
    if not infection_code:
        return None
    code = infection_code.upper()
    if code.startswith("M03"):
        return "CRE"
    if code.startswith("M"):
        return "MRSA"
    return None


def get_isolation_type(infection_type: str) -> str:
    if infection_type == "MDRO":
        return "CONTACT"
    if infection_type == "Tick-borne":
        return "DROPLET"
    if infection_type == "Pneumonia":
        return "DROPLET"
    if infection_type == "Waterborne":
        return "CONTACT"
    return "STANDARD"


def derive_flags(patient: dict) -> tuple[list[str], list[str]]:
    infection_type = patient["infection_type"]
    pid = patient["patient_id"]
    if infection_type == "MDRO":
        mdro_type = choose_mdro_type(patient.get("infection_code"))
        pathogen = [mdro_type.lower() if mdro_type else "mdro", "contact_precaution"]
        clinical = ["isolation_required", "cohort_consideration"]
        return pathogen, clinical
    if infection_type == "Tick-borne":
        pathogen = ["sfts_suspected", "tick_borne_pattern"]
        clinical = ["high_fever", "thrombocytopenia"]
        if pid == "T03":
            clinical.extend(["mental_change", "icu_consideration"])
        return pathogen, clinical
    if infection_type == "Pneumonia":
        return ["respiratory_infection"], ["cough", "oxygen_support"]
    if infection_type == "UTI":
        return ["urinary_source"], ["dysuria", "fever"]
    if infection_type == "Waterborne":
        return ["gastrointestinal_source"], ["diarrhea", "dehydration_risk"]
    return ["infection_unknown"], ["monitoring"]


def risk_series_for_patient(patient: dict) -> list[float]:
    pid = patient["patient_id"]
    infection = patient["infection_type"]
    code = (patient.get("infection_code") or "").upper()

    if pid == "T03":
        return [0.72, 0.84, 0.91]
    if pid in {"T01", "T02"}:
        return [0.46, 0.60, 0.74]
    if code == "M03":
        return [0.66, 0.79, 0.88]
    if infection == "MDRO":
        return [0.54, 0.66, 0.77]
    if infection == "Pneumonia":
        return [0.34, 0.45, 0.56]
    if infection == "UTI":
        return [0.31, 0.41, 0.50]
    if infection == "Waterborne":
        return [0.25, 0.34, 0.43]
    return [0.22, 0.30, 0.38]


def score_to_risk_level(score: float) -> str:
    if score >= 0.8:
        return "CRITICAL"
    if score >= 0.6:
        return "HIGH"
    if score >= 0.35:
        return "MEDIUM"
    return "LOW"


def dt_at(base: datetime | None, day_offset: int, hour: int) -> datetime:
    base_date = (base.date() if base else datetime.utcnow().date()) + timedelta(days=day_offset)
    return datetime.combine(base_date, dtime(hour=hour, minute=0, second=0))


def transfer_status_for_patient(patient: dict) -> str:
    pid = patient["patient_id"]
    infection = patient["infection_type"]
    if pid in {"T03", "18294629"}:
        return "NEEDS_EXCEPTION"
    if infection in {"Pneumonia", "UTI"} or pid == "T02":
        return "PLANNED"
    return "WAITING"


def transfer_reason_for_patient(infection_type: str) -> str:
    if infection_type in {"MDRO", "Tick-borne"}:
        return "격리"
    if infection_type in {"UTI", "Waterborne"}:
        return "격리 해제"
    return "신규 입원"


def target_ward_for_reason(reason: str, default_ward: str) -> str:
    if reason == "격리":
        return "5F"
    if reason == "격리 해제":
        return "3F"
    return default_ward


def room_preferences(patient: dict) -> list[str]:
    infection = patient["infection_type"]
    pid = patient["patient_id"]

    # Snapshot policy: keep this patient in a general ward bed at seed time.
    if pid == "18294629":
        general_first = [
            "SX-3F-301",
            "SX-3F-302",
            "SX-3F-303",
            "SX-2F-201",
            "SX-2F-202",
            "SX-2F-203",
        ]
        return general_first + [r["room_id"] for r in ROOM_SPECS if r["room_id"] not in general_first]

    if infection == "Pneumonia":
        return ["SX-2F-201", "SX-2F-202", "SX-3F-301", "SX-3F-302"]
    if infection in {"UTI", "Waterborne"}:
        return ["SX-3F-301", "SX-3F-302", "SX-2F-201", "SX-2F-202"]
    if infection == "MDRO":
        return ["SX-5F-501", "SX-5F-502", "SX-5F-503", "SX-5F-504"]
    if infection == "Tick-borne":
        return ["SX-5F-503", "SX-5F-504", "SX-5F-502", "SX-3F-301"]
    return [r["room_id"] for r in ROOM_SPECS]


def insert_wards(cursor, created_at: datetime) -> int:
    count = 0
    for w in WARD_SPECS:
        cursor.execute(
            """
            INSERT INTO wards (
              ward_id, ward_name, floor, is_isolation_ward, created_at
            ) VALUES (
              :ward_id, :ward_name, :floor, :is_isolation_ward, :created_at
            )
            """,
            {
                **w,
                "created_at": created_at,
            },
        )
        count += 1
    return count


def insert_rooms(cursor, created_at: datetime) -> int:
    count = 0
    for r in ROOM_SPECS:
        params = {
            **r,
            "cohort_type": None,
            "gender_type": None,
            "created_at": created_at,
        }
        cursor.execute(
            """
            INSERT INTO rooms (
              room_id, ward_id, room_number, room_type, capacity,
              is_isolation, has_aiir, has_dedicated_toilet, isolation_type, tier,
              cohort_type, gender_type, needs_cleaning, created_at
            ) VALUES (
              :room_id, :ward_id, :room_number, :room_type, :capacity,
              :is_isolation, :has_aiir, :has_dedicated_toilet, :isolation_type, :tier,
              :cohort_type, :gender_type, :needs_cleaning, :created_at
            )
            """,
            params,
        )
        count += 1
    return count


def insert_beds(cursor, beds: list[dict], created_at: datetime) -> int:
    count = 0
    for b in beds:
        cursor.execute(
            """
            INSERT INTO beds (
              bed_id, room_id, bed_number, created_at, patient_id, is_ghost
            ) VALUES (
              :bed_id, :room_id, :bed_number, :created_at, NULL, 0
            )
            """,
            {
                **b,
                "created_at": created_at,
            },
        )
        count += 1
    return count


def fetch_target_patients(cursor) -> list[dict]:
    cursor.execute(
        """
        SELECT patient_id, name, age, gender, infection_code,
               admission_id, admit_date, primary_diagnosis
        FROM (
            SELECT
              p.patient_id, p.name, p.age, p.gender, p.infection_code,
              a.admission_id, a.admit_date, a.primary_diagnosis,
              ROW_NUMBER() OVER (
                PARTITION BY p.patient_id
                ORDER BY
                  CASE WHEN LOWER(NVL(a.status, 'active')) = 'active' THEN 0 ELSE 1 END,
                  NVL(a.admit_date, CAST(a.created_at AS DATE)) DESC,
                  a.admission_id DESC
              ) AS rn
            FROM patients p
            JOIN admissions a ON a.patient_id = p.patient_id
            WHERE REGEXP_LIKE(p.patient_id, '^[0-9]{8}$')
               OR p.patient_id IN ('T01', 'T02', 'T03')
        )
        WHERE rn = 1
        ORDER BY patient_id
        """
    )
    rows = []
    for r in cursor.fetchall():
        row = {
            "patient_id": r[0],
            "name": r[1],
            "age": r[2],
            "gender": r[3],
            "infection_code": r[4],
            "admission_id": r[5],
            "admit_date": r[6],
            "primary_diagnosis": r[7],
        }
        row["infection_type"] = infection_type_from_code(row["infection_code"])
        rows.append(row)
    return rows


def cleanup_previous_rows(
    cursor,
    patients: list[dict],
    synthetic_bed_ids: list[str],
    synthetic_room_ids: list[str],
    synthetic_ward_ids: list[str],
) -> list[tuple[str, str]]:
    patient_ids = [p["patient_id"] for p in patients]
    detached_user_wards: list[tuple[str, str]] = []

    if patient_ids:
        placeholders, binds = bind_list("p", patient_ids)
        cursor.execute(f"DELETE FROM transfer_cases WHERE patient_id IN ({placeholders})", binds)
        cursor.execute(f"DELETE FROM patient_status WHERE patient_id IN ({placeholders})", binds)
        cursor.execute(f"UPDATE beds SET patient_id = NULL WHERE patient_id IN ({placeholders})", binds)

    if synthetic_room_ids:
        placeholders, binds = bind_list("r", synthetic_room_ids)
        cursor.execute(
            f"""
            DELETE FROM transfer_cases
             WHERE from_room_id IN ({placeholders})
                OR to_room_id IN ({placeholders})
            """,
            binds,
        )

    if synthetic_ward_ids:
        placeholders, binds = bind_list("w", synthetic_ward_ids)
        cursor.execute(
            f"""
            DELETE FROM transfer_cases
             WHERE from_ward_id IN ({placeholders})
                OR to_ward_id IN ({placeholders})
            """,
            binds,
        )
        cursor.execute(f"DELETE FROM patient_status WHERE ward_id IN ({placeholders})", binds)
        cursor.execute(
            f"""
            SELECT user_id, ward_id
              FROM users
             WHERE ward_id IN ({placeholders})
            """,
            binds,
        )
        detached_user_wards = [(str(row[0]), str(row[1])) for row in cursor.fetchall()]
        if detached_user_wards:
            cursor.execute(f"UPDATE users SET ward_id = NULL WHERE ward_id IN ({placeholders})", binds)

    if synthetic_bed_ids:
        placeholders, binds = bind_list("b", synthetic_bed_ids)
        cursor.execute(f"DELETE FROM transfer_cases WHERE to_bed_id IN ({placeholders})", binds)
        cursor.execute(f"DELETE FROM patient_status WHERE current_bed_id IN ({placeholders})", binds)
        cursor.execute(f"DELETE FROM bed_status WHERE bed_id IN ({placeholders})", binds)
        cursor.execute(
            f"""
            DELETE FROM bed_assignment_items
             WHERE from_bed_id IN ({placeholders})
                OR to_bed_id IN ({placeholders})
            """,
            binds,
        )
        cursor.execute(f"UPDATE beds SET patient_id = NULL WHERE bed_id IN ({placeholders})", binds)
        cursor.execute(f"DELETE FROM beds WHERE bed_id IN ({placeholders})", binds)

    if synthetic_room_ids:
        placeholders, binds = bind_list("r", synthetic_room_ids)
        cursor.execute(f"DELETE FROM rooms WHERE room_id IN ({placeholders})", binds)

    if synthetic_ward_ids:
        placeholders, binds = bind_list("w", synthetic_ward_ids)
        cursor.execute(f"DELETE FROM wards WHERE ward_id IN ({placeholders})", binds)

    return detached_user_wards


def restore_user_wards(cursor, user_wards: list[tuple[str, str]]) -> None:
    for user_id, ward_id in user_wards:
        cursor.execute(
            """
            UPDATE users
               SET ward_id = :ward_id
             WHERE user_id = :user_id
            """,
            {"ward_id": ward_id, "user_id": user_id},
        )


def assign_patients_to_beds(
    patients: list[dict],
    beds: list[dict],
) -> tuple[dict[str, dict], dict[str, dict], list[str]]:
    room_capacity = {r["room_id"]: r["capacity"] for r in ROOM_SPECS}
    all_rooms = [r["room_id"] for r in ROOM_SPECS]
    available_by_room: dict[str, list[str]] = {}
    for room_id in all_rooms:
        room_beds = [b["bed_id"] for b in beds if b["room_id"] == room_id]
        available_by_room[room_id] = sorted(room_beds)

    room_gender: dict[str, set[str]] = {room_id: set() for room_id in all_rooms}
    room_infection: dict[str, set[str]] = {room_id: set() for room_id in all_rooms}
    assignments: dict[str, dict] = {}

    priority_rank = {
        "MDRO": 0,
        "Tick-borne": 1,
        "Pneumonia": 2,
        "UTI": 3,
        "Waterborne": 4,
    }
    ordered = sorted(
        patients,
        key=lambda p: (priority_rank.get(p["infection_type"], 9), p["patient_id"]),
    )

    for p in ordered:
        pid = p["patient_id"]
        pref = room_preferences(p)
        candidates = pref + [r for r in all_rooms if r not in pref]
        placed = False

        for room_id in candidates:
            if not available_by_room[room_id]:
                continue
            cap = room_capacity[room_id]
            genders = room_gender[room_id]
            if cap > 1 and genders and p["gender"] not in genders:
                continue

            bed_id = available_by_room[room_id].pop(0)
            room_gender[room_id].add(p["gender"])
            room_infection[room_id].add(p["infection_type"])
            assignments[pid] = {
                "bed_id": bed_id,
                "room_id": room_id,
                "ward_id": room_id.split("-")[1],  # SX-2F-201 -> 2F
            }
            placed = True
            break

        if not placed:
            raise RuntimeError(f"병상 배정 실패: {pid}")

    room_meta = {}
    for room in ROOM_SPECS:
        rid = room["room_id"]
        infections = room_infection[rid]
        genders = room_gender[rid]
        cohort_type = next(iter(infections)) if len(infections) == 1 else None
        gender_type = next(iter(genders)) if (room["capacity"] > 1 and len(genders) == 1) else None
        room_meta[rid] = {
            "cohort_type": cohort_type,
            "gender_type": gender_type,
        }

    occupied_beds = {a["bed_id"] for a in assignments.values()}
    empty_beds = [b["bed_id"] for b in beds if b["bed_id"] not in occupied_beds]
    return assignments, room_meta, empty_beds


def persist_bed_assignments(cursor, beds: list[dict], assignments: dict[str, dict]) -> None:
    patient_by_bed = {v["bed_id"]: pid for pid, v in assignments.items()}

    for b in beds:
        cursor.execute(
            "UPDATE beds SET patient_id = :patient_id, is_ghost = 0 WHERE bed_id = :bed_id",
            {
                "patient_id": patient_by_bed.get(b["bed_id"]),
                "bed_id": b["bed_id"],
            },
        )


def persist_room_meta(cursor, room_meta: dict[str, dict]) -> None:
    for room_id, meta in room_meta.items():
        cursor.execute(
            """
            UPDATE rooms
               SET cohort_type = :cohort_type,
                   gender_type = :gender_type
             WHERE room_id = :room_id
            """,
            {
                "cohort_type": meta["cohort_type"],
                "gender_type": meta["gender_type"],
                "room_id": room_id,
            },
        )


def insert_transfer_cases(
    cursor,
    patients: list[dict],
    assignments: dict[str, dict],
    bed_catalog: dict[str, dict],
    empty_beds: list[str],
) -> tuple[int, int, dict[int, float], dict[str, list[str]], dict[str, list[str]]]:

    # destination bed pool by ward
    empty_by_ward: dict[str, list[str]] = {"2F": [], "3F": [], "5F": []}
    for bed_id in empty_beds:
        ward = bed_catalog[bed_id]["ward_id"]
        empty_by_ward[ward].append(bed_id)
    for ward in empty_by_ward:
        empty_by_ward[ward].sort()

    planned_count = 0
    case_count = 0
    latest_scores: dict[int, float] = {}
    pathogen_by_patient: dict[str, list[str]] = {}
    clinical_by_patient: dict[str, list[str]] = {}

    now = datetime.utcnow().replace(microsecond=0)

    ordered_patients = sorted(patients, key=lambda x: x["patient_id"])
    for idx, p in enumerate(ordered_patients, start=1):
        pid = p["patient_id"]
        aid = p["admission_id"]
        from_room = assignments[pid]["room_id"]
        from_ward = assignments[pid]["ward_id"]
        infection_type = p["infection_type"]
        status = transfer_status_for_patient(p)
        reason = transfer_reason_for_patient(infection_type)
        to_ward = target_ward_for_reason(reason, from_ward)
        priority = "urgent" if status == "NEEDS_EXCEPTION" else "normal"

        pathogen_flags, clinical_flags = derive_flags(p)
        pathogen_by_patient[pid] = pathogen_flags
        clinical_by_patient[pid] = clinical_flags

        to_room = None
        to_bed = None
        plan_id = None

        if status == "PLANNED":
            bed_pool = empty_by_ward.get(to_ward, [])
            if not bed_pool:
                # fallback: 아무 빈 병상
                for ward in ("5F", "3F", "2F"):
                    if empty_by_ward[ward]:
                        bed_pool = empty_by_ward[ward]
                        to_ward = ward
                        break
            if bed_pool:
                to_bed = bed_pool.pop(0)
                to_room = bed_catalog[to_bed]["room_id"]
                planned_count += 1
            else:
                status = "NEEDS_EXCEPTION"
                priority = "urgent"

        case_id = f"SX-CASE-{pid}"
        exception_reason = None
        if status == "NEEDS_EXCEPTION":
            exception_reason = "적합한 빈 병상 부족 또는 격리 요구 충돌"

        cursor.execute(
            """
            INSERT INTO transfer_cases (
              case_id, patient_id, status,
              from_ward_id, from_room_id,
              to_ward_id, to_room_id, to_bed_id,
              reason, priority, exception_reason,
              infection_type, pathogen_flags, clinical_flags, plan_id,
              created_at, updated_at
            ) VALUES (
              :case_id, :patient_id, :status,
              :from_ward_id, :from_room_id,
              :to_ward_id, :to_room_id, :to_bed_id,
              :reason, :priority, :exception_reason,
              :infection_type, :pathogen_flags, :clinical_flags, :plan_id,
              :created_at, :updated_at
            )
            """,
            {
                "case_id": case_id,
                "patient_id": pid,
                "status": status,
                "from_ward_id": from_ward,
                "from_room_id": from_room,
                "to_ward_id": to_ward,
                "to_room_id": to_room,
                "to_bed_id": to_bed,
                "reason": reason,
                "priority": priority,
                "exception_reason": exception_reason,
                "infection_type": infection_type,
                "pathogen_flags": ",".join(pathogen_flags),
                "clinical_flags": ",".join(clinical_flags),
                "plan_id": plan_id,
                "created_at": now - timedelta(minutes=idx * 3),
                "updated_at": now - timedelta(minutes=idx * 2),
            },
        )
        case_count += 1

        # sepsis latest score cache
        latest_scores[aid] = risk_series_for_patient(p)[-1]

    return (
        case_count,
        planned_count,
        latest_scores,
        pathogen_by_patient,
        clinical_by_patient,
    )


def insert_patient_status(
    cursor,
    patients: list[dict],
    assignments: dict[str, dict],
    latest_scores: dict[int, float],
    pathogen_by_patient: dict[str, list[str]],
    clinical_by_patient: dict[str, list[str]],
) -> int:
    count = 0

    for p in patients:
        pid = p["patient_id"]
        aid = p["admission_id"]
        inf = p["infection_type"]
        risk_score = latest_scores.get(aid, 0.3)
        isolation_type = get_isolation_type(inf)
        isolation_required = 1 if isolation_type != "STANDARD" else 0
        assn = assignments[pid]

        infection_tags = [inf]
        if p.get("infection_code"):
            infection_tags.append(p["infection_code"])

        cursor.execute(
            """
            INSERT INTO patient_status (
              admission_id, patient_id, current_bed_id, ward_id,
              isolation_required, isolation_type,
              infection_tags_json, pathogen_flags_json, clinical_flags_json,
              risk_level, last_updated_at
            ) VALUES (
              :admission_id, :patient_id, :current_bed_id, :ward_id,
              :isolation_required, :isolation_type,
              :infection_tags_json, :pathogen_flags_json, :clinical_flags_json,
              :risk_level, :last_updated_at
            )
            """,
            {
                "admission_id": aid,
                "patient_id": pid,
                "current_bed_id": assn["bed_id"],
                "ward_id": assn["ward_id"],
                "isolation_required": isolation_required,
                "isolation_type": isolation_type,
                "infection_tags_json": json.dumps(infection_tags, ensure_ascii=False),
                "pathogen_flags_json": json.dumps(pathogen_by_patient.get(pid, []), ensure_ascii=False),
                "clinical_flags_json": json.dumps(clinical_by_patient.get(pid, []), ensure_ascii=False),
                "risk_level": score_to_risk_level(risk_score),
                "last_updated_at": datetime.utcnow(),
            },
        )
        count += 1

    return count


def insert_bed_status(
    cursor,
    beds: list[dict],
    assignments: dict[str, dict],
    patients: list[dict],
) -> int:
    count = 0
    admission_by_patient = {p["patient_id"]: p["admission_id"] for p in patients}
    patient_by_bed = {v["bed_id"]: pid for pid, v in assignments.items()}
    room_by_id = {r["room_id"]: r for r in ROOM_SPECS}

    for bed in beds:
        bed_id = bed["bed_id"]
        room = room_by_id[bed["room_id"]]
        pid = patient_by_bed.get(bed_id)
        if pid:
            status = "OCCUPIED"
            admission_id = admission_by_patient.get(pid)
        elif room["needs_cleaning"] == 1:
            status = "CLEANING"
            admission_id = None
        else:
            status = "AVAILABLE"
            admission_id = None

        cursor.execute(
            """
            INSERT INTO bed_status (
              bed_id, status, current_admission_id, isolation_type, needs_cleaning, last_updated_at
            ) VALUES (
              :bed_id, :status, :current_admission_id, :isolation_type, :needs_cleaning, :last_updated_at
            )
            """,
            {
                "bed_id": bed_id,
                "status": status,
                "current_admission_id": admission_id,
                "isolation_type": room["isolation_type"],
                "needs_cleaning": room["needs_cleaning"],
                "last_updated_at": datetime.utcnow(),
            },
        )
        count += 1

    return count


def main() -> None:
    start_all = time.time()
    print("=" * 72)
    print("08_load_synthetic_extensions.py - 합성 환자 확장 데이터 적재")
    print("=" * 72)

    if not DB_USER or not DB_PASSWORD or not DB_DSN:
        raise RuntimeError("ORACLE_USER / ORACLE_PASSWORD / ORACLE_CONNECTION_STRING 환경변수를 확인하세요.")

    print("\n[1/6] Oracle 연결 중...")
    try:
        oracledb.init_oracle_client(lib_dir="/opt/oracle/instantclient_23_3")
    except Exception:
        # 이미 초기화된 경우 재초기화 예외는 무시
        pass
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
    cursor = conn.cursor()
    print("  ✓ 연결 성공")

    try:
        print("\n[2/6] 대상 환자 코호트 조회 중...")
        patients = fetch_target_patients(cursor)
        if not patients:
            print("  ⚠ 대상 합성 환자가 없습니다. 작업을 종료합니다.")
            return
        print(f"  ✓ 대상 {len(patients)}명")

        print("\n[3/6] 기존 대상 데이터 정리 후 기준 구조 재삽입 중...")
        beds, bed_catalog = build_room_beds()
        room_ids = [r["room_id"] for r in ROOM_SPECS]
        ward_ids = [w["ward_id"] for w in WARD_SPECS]
        seed_now = datetime.utcnow().replace(microsecond=0)

        detached_user_wards = cleanup_previous_rows(
            cursor,
            patients,
            [b["bed_id"] for b in beds],
            room_ids,
            ward_ids,
        )
        n_wards = insert_wards(cursor, created_at=seed_now)
        if detached_user_wards:
            restore_user_wards(cursor, detached_user_wards)
        n_rooms = insert_rooms(cursor, created_at=seed_now)
        n_beds = insert_beds(cursor, beds, created_at=seed_now)
        print(f"  ✓ wards={n_wards}, rooms={n_rooms}, beds={n_beds}")

        print("\n[4/6] 환자 배정/이동 케이스 생성 중...")
        assignments, room_meta, empty_beds = assign_patients_to_beds(patients, beds)
        persist_bed_assignments(cursor, beds, assignments)
        persist_room_meta(cursor, room_meta)

        (
            case_count,
            planned_count,
            latest_scores_from_cases,
            pathogen_by_patient,
            clinical_by_patient,
        ) = insert_transfer_cases(
            cursor,
            patients,
            assignments,
            bed_catalog,
            empty_beds,
        )
        print(f"  ✓ transfer_cases={case_count} (planned={planned_count})")

        print("\n[5/6] 상태 스냅샷(patient_status/bed_status) 적재 중...")
        latest_scores = latest_scores_from_cases.copy()
        ps_count = insert_patient_status(
            cursor,
            patients,
            assignments,
            latest_scores,
            pathogen_by_patient,
            clinical_by_patient,
        )
        bs_count = insert_bed_status(cursor, beds, assignments, patients)
        print(f"  ✓ patient_status={ps_count}, bed_status={bs_count}")

        print("\n[6/6] 커밋 중...")
        conn.commit()
        print("  ✓ 커밋 완료")

        elapsed = time.time() - start_all
        print("\n" + "=" * 72)
        print("완료 요약")
        print("=" * 72)
        print(f"  대상 환자:                {len(patients)}명")
        print(f"  transfer_cases:           {case_count}건")
        print(f"  patient_status:           {ps_count}건")
        print(f"  bed_status:               {bs_count}건")
        print(f"  소요 시간:                {_fmt_hms(elapsed)}")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
