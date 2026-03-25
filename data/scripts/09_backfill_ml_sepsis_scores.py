"""
09_backfill_ml_sepsis_scores.py
Sepsis ML 백필 (13명 코호트 × d_min~d_max × Day/Evening/Night)

기본 모드: DRY-RUN
쓰기 모드: --write
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import oracledb
from dotenv import load_dotenv

# ------------------------------------------------------------
# 경로/환경
# ------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]  # final-prj/
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from ml.api.inference import XgbSepsisRuntime  # noqa: E402

load_dotenv()

DB_USER = os.getenv("ORACLE_USER")
DB_PASSWORD = os.getenv("ORACLE_PASSWORD")
DB_DSN = os.getenv("ORACLE_CONNECTION_STRING")
ORACLE_CLIENT_LIB = os.getenv("ORACLE_CLIENT_LIB", "/opt/oracle/instantclient_23_3")

SHIFT_ORDER = ["Day", "Evening", "Night"]
SHIFT_TO_HOUR = {"Day": 8, "Evening": 16, "Night": 23}
SHIFT_CUTOFF = {
    "Day": (13, 59, 59, 0),
    "Evening": (21, 59, 59, 0),
    "Night": (5, 59, 59, 1),  # 다음날 05:59:59
}

LAB_TOKEN_MAP = {
    "lactate": {"LACTATE", "LAC"},
    "wbc": {"WBC", "WHITEBLOODCELL", "WHITEBLOODCELLS"},
    "creatinine": {"CREATININE", "CREA"},
    "platelets": {"PLATELET", "PLATELETS", "PLT"},
    "bilirubin": {"BILIRUBIN", "TBIL", "TOTALBILIRUBIN"},
    "sodium": {"SODIUM", "NA"},
    "potassium": {"POTASSIUM", "K"},
    "ph": {"PH"},
}


@dataclass
class AdmissionRow:
    admission_id: int
    patient_id: str
    age: int | None
    anchor_datetime: datetime | None
    d_min: int
    d_max: int
    demo_d_offset: int


@dataclass
class PointResult:
    patient_id: str
    admission_id: int
    d_number: int
    shift: str
    hd: int
    risk_score: float
    risk_level: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill sepsis ML scores (shift-aware)")
    parser.add_argument("--write", action="store_true", help="DB write mode (default: dry-run)")
    parser.add_argument(
        "--patient-id",
        action="append",
        default=[],
        help="target patient_id (repeatable or comma-separated)",
    )
    parser.add_argument(
        "--model-version",
        default="xgb_final_models_v1",
        help="model_version value to save",
    )
    parser.add_argument(
        "--source-tag",
        default="ML_BACKFILL",
        help="source tag for ml_sepsis_scores",
    )
    return parser.parse_args()


def normalize_patient_filters(raw_values: list[str]) -> set[str]:
    tokens: set[str] = set()
    for raw in raw_values or []:
        for token in str(raw).split(","):
            val = token.strip()
            if val:
                tokens.add(val)
    return tokens


def to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    matched = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not matched:
        return None

    try:
        return float(matched.group(0))
    except (TypeError, ValueError):
        return None


def normalize_lab_token(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def compute_cutoff(anchor: datetime | None, d_min: int, d_number: int, shift: str) -> datetime:
    base = anchor or datetime.utcnow()
    base_day = datetime(base.year, base.month, base.day)
    offset_days = d_number - d_min
    day = base_day + timedelta(days=offset_days)

    hour, minute, second, plus_day = SHIFT_CUTOFF[shift]
    day = day + timedelta(days=plus_day)
    return day.replace(hour=hour, minute=minute, second=second, microsecond=0)


def include_row(
    row_dt: datetime | None,
    row_d_number: int | None,
    target_d_number: int,
    cutoff: datetime,
) -> bool:
    if row_dt is None:
        return False
    if row_dt > cutoff:
        return False
    if row_d_number is None:
        return True
    return int(row_d_number) <= int(target_d_number)


def pick_latest_vitals(
    nursing_rows: list[dict[str, Any]],
    d_number: int,
    cutoff: datetime,
) -> dict[str, float | None]:
    for row in reversed(nursing_rows):
        if not include_row(row.get("datetime"), row.get("d_number"), d_number, cutoff):
            continue
        return {
            "temp": to_number(row.get("temp")),
            "hr": to_number(row.get("hr")),
            "rr": to_number(row.get("rr")),
            "sbp": to_number(row.get("bp_sys")),
            "dbp": to_number(row.get("bp_dia")),
            "spo2": to_number(row.get("spo2")),
        }

    return {
        "temp": None,
        "hr": None,
        "rr": None,
        "sbp": None,
        "dbp": None,
        "spo2": None,
    }


def pick_latest_lab(
    lab_rows: list[dict[str, Any]],
    d_number: int,
    cutoff: datetime,
    token_candidates: set[str],
) -> float | None:
    for row in reversed(lab_rows):
        if not include_row(row.get("datetime"), row.get("d_number"), d_number, cutoff):
            continue

        code = normalize_lab_token(row.get("item_code"))
        name = normalize_lab_token(row.get("item_name"))
        if code not in token_candidates and name not in token_candidates:
            continue

        value = to_number(row.get("value"))
        if value is not None:
            return value

    return None


def build_feature_snapshot(
    admission: AdmissionRow,
    vitals: dict[str, float | None],
    labs: dict[str, float | None],
    d_number: int,
    shift: str,
) -> tuple[dict[str, float], int]:
    sbp = vitals.get("sbp")
    dbp = vitals.get("dbp")
    hr = vitals.get("hr")
    rr = vitals.get("rr")
    spo2 = vitals.get("spo2")

    mbp = None
    if sbp is not None and dbp is not None:
        mbp = round((sbp + (2 * dbp)) / 3, 6)

    pulse_pressure = None
    if sbp is not None and dbp is not None:
        pulse_pressure = round(sbp - dbp, 6)

    shock_index = None
    if hr is not None and sbp not in (None, 0):
        shock_index = round(hr / sbp, 6)

    hd = int(d_number - admission.d_min + 1)
    if hd < 1:
        hd = 1

    observation_hour = ((hd - 1) * 24) + SHIFT_TO_HOUR[shift]

    snapshot: dict[str, float | None] = {
        "hr": hr,
        "hr_max": hr,
        "sbp": sbp,
        "dbp": dbp,
        "mbp": mbp,
        "rr": rr,
        "rr_max": rr,
        "spo2": spo2,
        "temp": vitals.get("temp"),
        "lactate": labs.get("lactate"),
        "wbc": labs.get("wbc"),
        "creatinine": labs.get("creatinine"),
        "platelets": labs.get("platelets"),
        "bilirubin": labs.get("bilirubin"),
        "sodium": labs.get("sodium"),
        "potassium": labs.get("potassium"),
        "ph": labs.get("ph"),
        "shock_index": shock_index,
        "pulse_pressure": pulse_pressure,
        "anchor_age": to_number(admission.age),
        "observation_hour": float(observation_hour),
        "abga_checked": 1.0 if labs.get("ph") is not None else 0.0,
        "icu_micu": 1.0,
        "icu_micu_sicu": 0.0,
    }

    compact = {
        key: float(value)
        for key, value in snapshot.items()
        if value is not None
    }
    return compact, hd


def ensure_ml_table(cursor) -> None:
    cursor.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM user_tables
        WHERE table_name = 'ML_SEPSIS_SCORES'
        """
    )
    cnt = int(cursor.fetchone()[0] or 0)
    if cnt == 0:
        raise RuntimeError(
            "ML_SEPSIS_SCORES table not found. Run data/scripts/09_ml_sepsis_schema.sql first."
        )


def load_admissions(cursor, patient_filters: set[str]) -> list[AdmissionRow]:
    cursor.execute(
        """
        SELECT
            x.admission_id,
            x.patient_id,
            x.age,
            x.anchor_datetime,
            NVL(x.d_min, 0) AS d_min,
            NVL(x.d_max, NVL(x.d_min, 0)) AS d_max,
            NVL(x.demo_d_offset, 0) AS demo_d_offset
        FROM (
            SELECT
                a.admission_id,
                a.patient_id,
                p.age,
                NVL(a.sim_admit_date, a.admit_date) AS anchor_datetime,
                a.d_min,
                a.d_max,
                a.demo_d_offset,
                ROW_NUMBER() OVER (
                    PARTITION BY a.patient_id
                    ORDER BY NVL(a.sim_admit_date, a.admit_date) DESC NULLS LAST, a.admission_id DESC
                ) AS rn
            FROM admissions a
            JOIN patients p ON p.patient_id = a.patient_id
        ) x
        WHERE x.rn = 1
        ORDER BY x.patient_id
        """
    )

    rows: list[AdmissionRow] = []
    for row in cursor.fetchall():
        patient_id = str(row[1])
        if patient_filters and patient_id not in patient_filters:
            continue

        rows.append(
            AdmissionRow(
                admission_id=int(row[0]),
                patient_id=patient_id,
                age=int(row[2]) if row[2] is not None else None,
                anchor_datetime=row[3],
                d_min=int(row[4]),
                d_max=int(row[5]),
                demo_d_offset=int(row[6]),
            )
        )

    return rows


def load_observations(cursor, admission_id: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cursor.execute(
        """
        SELECT note_datetime, d_number, temp, hr, rr, bp_sys, bp_dia, spo2
        FROM nursing_notes
        WHERE admission_id = :aid
        ORDER BY note_datetime ASC
        """,
        {"aid": admission_id},
    )
    nursing = [
        {
            "datetime": row[0],
            "d_number": row[1],
            "temp": row[2],
            "hr": row[3],
            "rr": row[4],
            "bp_sys": row[5],
            "bp_dia": row[6],
            "spo2": row[7],
        }
        for row in cursor.fetchall()
    ]

    cursor.execute(
        """
        SELECT result_datetime, d_number, item_code, item_name, value
        FROM lab_results
        WHERE admission_id = :aid
        ORDER BY result_datetime ASC
        """,
        {"aid": admission_id},
    )
    labs = [
        {
            "datetime": row[0],
            "d_number": row[1],
            "item_code": row[2],
            "item_name": row[3],
            "value": row[4],
        }
        for row in cursor.fetchall()
    ]

    return nursing, labs


def merge_ml_row(
    cursor,
    *,
    admission_id: int,
    prediction_datetime: datetime,
    hd: int,
    d_number: int,
    shift: str,
    risk_score: float,
    risk_level: str,
    factors: list[dict[str, Any]],
    recommendations: list[str],
    feature_snapshot: dict[str, float],
    model_name: str,
    model_version: str,
    source_tag: str,
) -> None:
    binds = {
        "admission_id": admission_id,
        "prediction_datetime": prediction_datetime,
        "hd": hd,
        "d_number": d_number,
        "shift": shift,
        "risk_score": float(risk_score),
        "risk_level": risk_level,
        "contributing_factors_json": json.dumps(factors, ensure_ascii=False),
        "recommendations_json": json.dumps(recommendations, ensure_ascii=False),
        "feature_snapshot_json": json.dumps(feature_snapshot, ensure_ascii=False),
        "model_name": model_name,
        "model_version": model_version,
        "source_tag": source_tag,
    }

    cursor.execute(
        """
        MERGE INTO ml_sepsis_scores t
        USING (
            SELECT
                :admission_id AS admission_id,
                :d_number AS d_number,
                :shift AS shift,
                :model_version AS model_version
            FROM dual
        ) s
        ON (
            t.admission_id = s.admission_id
            AND t.d_number = s.d_number
            AND t.shift = s.shift
            AND t.model_version = s.model_version
        )
        WHEN MATCHED THEN UPDATE SET
            t.prediction_datetime = :prediction_datetime,
            t.hd = :hd,
            t.risk_score = :risk_score,
            t.risk_level = :risk_level,
            t.contributing_factors_json = :contributing_factors_json,
            t.recommendations_json = :recommendations_json,
            t.feature_snapshot_json = :feature_snapshot_json,
            t.model_name = :model_name,
            t.source_tag = :source_tag
        WHEN NOT MATCHED THEN INSERT (
            admission_id, prediction_datetime, hd, d_number, shift,
            risk_score, risk_level,
            contributing_factors_json, recommendations_json, feature_snapshot_json,
            model_name, model_version, source_tag
        ) VALUES (
            :admission_id, :prediction_datetime, :hd, :d_number, :shift,
            :risk_score, :risk_level,
            :contributing_factors_json, :recommendations_json, :feature_snapshot_json,
            :model_name, :model_version, :source_tag
        )
        """,
        binds,
    )


def main() -> None:
    args = parse_args()
    patient_filters = normalize_patient_filters(args.patient_id)

    print("=" * 72)
    print("09_backfill_ml_sepsis_scores.py - Sepsis ML 백필")
    print("=" * 72)
    print(f"mode: {'WRITE' if args.write else 'DRY-RUN'}")
    print(f"model_version: {args.model_version}")
    print(f"source_tag: {args.source_tag}")
    if patient_filters:
        print(f"patient filter: {sorted(patient_filters)}")

    runtime = XgbSepsisRuntime()
    runtime.load()
    if args.model_version:
        runtime.model_version = args.model_version

    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_LIB)
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
    cursor = conn.cursor()

    try:
        ensure_ml_table(cursor)

        admissions = load_admissions(cursor, patient_filters)
        print(f"admissions loaded: {len(admissions)}")
        if not admissions:
            print("No target admissions. Exit.")
            return

        results: list[PointResult] = []
        risk_counter: Counter[str] = Counter()
        patient_counter: Counter[str] = Counter()

        for admission in admissions:
            nursing_rows, lab_rows = load_observations(cursor, admission.admission_id)

            for d_number in range(admission.d_min, admission.d_max + 1):
                for shift in SHIFT_ORDER:
                    cutoff = compute_cutoff(admission.anchor_datetime, admission.d_min, d_number, shift)
                    vitals = pick_latest_vitals(nursing_rows, d_number, cutoff)
                    labs = {
                        key: pick_latest_lab(lab_rows, d_number, cutoff, tokens)
                        for key, tokens in LAB_TOKEN_MAP.items()
                    }

                    feature_snapshot, hd = build_feature_snapshot(
                        admission=admission,
                        vitals=vitals,
                        labs=labs,
                        d_number=d_number,
                        shift=shift,
                    )

                    inferred = runtime.predict(feature_snapshot)
                    risk_counter[inferred.risk_level] += 1
                    patient_counter[admission.patient_id] += 1

                    results.append(
                        PointResult(
                            patient_id=admission.patient_id,
                            admission_id=admission.admission_id,
                            d_number=d_number,
                            shift=shift,
                            hd=hd,
                            risk_score=inferred.risk_score,
                            risk_level=inferred.risk_level,
                        )
                    )

                    if args.write:
                        merge_ml_row(
                            cursor,
                            admission_id=admission.admission_id,
                            prediction_datetime=cutoff,
                            hd=hd,
                            d_number=d_number,
                            shift=shift,
                            risk_score=inferred.risk_score,
                            risk_level=inferred.risk_level,
                            factors=inferred.contributing_factors,
                            recommendations=inferred.recommendations,
                            feature_snapshot=feature_snapshot,
                            model_name="xgb",
                            model_version=args.model_version,
                            source_tag=args.source_tag,
                        )

        if args.write:
            conn.commit()
        else:
            conn.rollback()

        print("-" * 72)
        print(f"points generated: {len(results)}")
        print(f"patients touched: {len(patient_counter)}")
        print(f"risk distribution: {dict(sorted(risk_counter.items()))}")

        preview = sorted(
            results,
            key=lambda x: (x.patient_id, x.d_number, SHIFT_ORDER.index(x.shift)),
        )[:12]
        print("sample:")
        for idx, row in enumerate(preview, start=1):
            print(
                f"{idx:02d}. patient={row.patient_id} d={row.d_number} {row.shift:<7} "
                f"hd={row.hd} risk={row.risk_score:.4f} level={row.risk_level}"
            )

        if args.write:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM ml_sepsis_scores
                WHERE model_version = :mv
                """,
                {"mv": args.model_version},
            )
            saved = int(cursor.fetchone()[0] or 0)
            print(f"rows in ml_sepsis_scores(model_version={args.model_version}): {saved}")

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
