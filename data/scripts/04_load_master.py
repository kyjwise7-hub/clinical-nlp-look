"""
04_load_master.py
patients + admissions 테이블 적재

입력:
  - 타입 A (MIMIC 기반): data/outputs/patient_timelines/*.json + patient_scenario/*.md
  - 타입 B (T0X 합성): emr-generator/outputs/patient_T0X*/hd_*.json + patient_scenario/*.md

출력:
  - patients 테이블 INSERT
  - admissions 테이블 INSERT
"""

import json
import os
import re
import time
from pathlib import Path
from dotenv import load_dotenv
import oracledb
from faker import Faker

load_dotenv()

# ============================================================
# 설정
# ============================================================
BASE_DIR = Path(__file__).resolve().parent.parent  # data/
TIMELINES_DIR = BASE_DIR / 'outputs' / 'patient_timelines'
SCENARIO_DIR = BASE_DIR.parent / 'emr-generator' / 'patient_scenario'
EMR_OUTPUTS_DIR = BASE_DIR.parent / 'emr-generator' / 'outputs'

DB_USER = os.getenv('ORACLE_USER')
DB_PASSWORD = os.getenv('ORACLE_PASSWORD')
DB_DSN = os.getenv('ORACLE_CONNECTION_STRING')

fake = Faker('ko_KR')

# ============================================================
# 헬퍼 함수
# ============================================================
def _fmt_hms(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def generate_korean_name(gender: str) -> str:
    """gender: 'M' or 'F'"""
    if gender == 'M':
        return fake.name_male()
    else:
        return fake.name_female()


def parse_gender(gender_str: str) -> str:
    """'남성' -> 'M', '여성' -> 'F', 'M' -> 'M'"""
    if not gender_str:
        return 'M'
    if '남' in gender_str:
        return 'M'
    elif '여' in gender_str:
        return 'F'
    return gender_str  # 이미 'M' or 'F'면 그대로


def get_primary_diagnosis(diagnoses: list) -> str | None:
    """seq_num=1인 진단명 찾기"""
    if not diagnoses:
        return None
    
    for diag in diagnoses:
        if str(diag.get('seq_num')) == '1':
            return diag.get('description')
    
    return diagnoses[0].get('description') if diagnoses else None


def parse_md_for_infection_code(md_path: Path) -> str | None:
    """md 파일 제목에서 감염 코드 추출 (G02, P01, T01 등)"""
    if not md_path.exists():
        return None
    
    content = md_path.read_text(encoding='utf-8')
    
    # "# G02 - xxx" 또는 "# P05 v5 - xxx" 또는 "# T02 - xxx"
    match = re.search(r'^#\s*([A-Z]\d+)', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    
    return None


def parse_md_for_diagnosis(md_path: Path) -> str | None:
    """md 파일에서 입원 사유 추출"""
    if not md_path.exists():
        return None
    
    content = md_path.read_text(encoding='utf-8')
    
    # "입원 사유: **xxx**" 패턴
    match = re.search(r'입원 사유[:\s]*\*\*([^*]+)\*\*', content)
    if match:
        return match.group(1).strip()
    
    return None


def parse_admit_date_from_summary(admission_reason: str) -> str | None:
    """'Date: 2168-03-09' -> '2168-03-09'"""
    if not admission_reason:
        return None
    match = re.search(r'(\d{4}-\d{2}-\d{2})', admission_reason)
    if match:
        return match.group(1)
    return None


def parse_md_profile(md_path: Path) -> dict:
    """
    patient_scenario md에서 T0X 환자 프로필 파싱.
    반환 키: age, gender, admit_date, primary_diagnosis
    """
    if not md_path.exists():
        return {
            'age': None,
            'gender': 'M',
            'admit_date': None,
            'primary_diagnosis': None,
        }

    content = md_path.read_text(encoding='utf-8')

    age = None
    gender = 'M'
    admit_date = None
    primary_diagnosis = None

    # 예: **74세 남성**
    m = re.search(r'\*\*(\d{1,3})세\s*(남성|여성)\*\*', content)
    if m:
        age = int(m.group(1))
        gender = parse_gender(m.group(2))

    # 예: Admission Date: 2181-06-15
    m = re.search(r'Admission Date\s*:\s*(\d{4}-\d{2}-\d{2})', content, re.IGNORECASE)
    if m:
        admit_date = m.group(1)

    # 예: 입원 사유: **High Fever, Generalized Weakness, Diarrhea**
    m = re.search(r'입원 사유[:\s]*\*\*([^*]+)\*\*', content)
    if m:
        primary_diagnosis = m.group(1).strip()

    return {
        'age': age,
        'gender': gender,
        'admit_date': admit_date,
        'primary_diagnosis': primary_diagnosis,
    }


def infer_admit_date_from_hd_files(patient_dir: Path) -> str | None:
    """
    patient_T0X 폴더의 hd_*.json에서 가장 이른 date를 입원일로 사용.
    """
    dates = []
    for hd_path in patient_dir.glob('hd_*.json'):
        try:
            with open(hd_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            date_str = payload.get('date')
            if isinstance(date_str, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
                dates.append(date_str)
        except Exception:
            continue

    if not dates:
        return None
    return min(dates)


# ============================================================
# 타입 A: MIMIC 기반 환자 로드
# ============================================================
def load_mimic_patients() -> list[dict]:
    """patient_timelines/*.json에서 로드"""
    patients = []
    
    for json_path in TIMELINES_DIR.glob('patient_*.json'):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        subject_id = data.get('subject_id')
        if not subject_id:
            continue
        
        patient_id = str(subject_id)
        patient_summary = data.get('patient_summary', {})
        admissions_list = data.get('admissions', [])
        admission = admissions_list[0] if admissions_list else {}
        
        gender = patient_summary.get('gender', 'M')
        
        # md 파일에서 infection_code 추출
        md_path = SCENARIO_DIR / f'patient_{patient_id}.md'
        infection_code = parse_md_for_infection_code(md_path)
        
        patient_data = {
            'patient_id': patient_id,
            'name': generate_korean_name(gender),
            'age': int(patient_summary.get('age', 0)) if patient_summary.get('age') else None,
            'gender': gender,
            'infection_code': infection_code,
            'admit_date': admission.get('admit_date'),
            'discharge_date': admission.get('discharge_date'),
            'primary_diagnosis': get_primary_diagnosis(admission.get('diagnoses', [])),
        }
        
        patients.append(patient_data)
        print(f"  [MIMIC] {patient_id}: {patient_data['name']}, {patient_data['age']}세, {gender}, {infection_code}")
    
    return patients


# ============================================================
# 타입 B: T0X 합성 환자 로드
# ============================================================
def load_synthetic_patients() -> list[dict]:
    """T0X 환자들: generation_summary.json + md 파일에서 로드"""
    patients = []

    seen_ids = set()

    # patient_T01, patient_T01_Patient 모두 허용
    for patient_dir in sorted(EMR_OUTPUTS_DIR.glob('patient_T*')):
        if not patient_dir.is_dir():
            continue

        match = re.search(r'(T\d+)', patient_dir.name)
        if not match:
            continue
        patient_id = match.group(1)
        if patient_id in seen_ids:
            continue

        # 최소 1개 이상의 hd_*.json이 있어야 합성 환자로 인정
        has_hd_json = any(patient_dir.glob('hd_*.json'))
        if not has_hd_json:
            continue

        md_path = SCENARIO_DIR / f'patient_{patient_id}.md'
        profile = parse_md_profile(md_path)

        # generation_summary.json이 있으면 우선 사용, 없으면 md 파싱값 사용
        summary_path = patient_dir / 'generation_summary.json'
        summary = {}
        if summary_path.exists():
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary = json.load(f)

        gender = parse_gender(summary.get('gender', profile.get('gender', 'M')))
        age = summary.get('age', profile.get('age'))

        infection_code = parse_md_for_infection_code(md_path)
        primary_diagnosis = (
            parse_md_for_diagnosis(md_path)
            or profile.get('primary_diagnosis')
        )
        admit_date = (
            parse_admit_date_from_summary(summary.get('admission_reason', ''))
            or profile.get('admit_date')
            or infer_admit_date_from_hd_files(patient_dir)
        )

        patient_data = {
            'patient_id': patient_id,
            'name': generate_korean_name(gender),
            'age': age,
            'gender': gender,
            'infection_code': infection_code,
            'admit_date': admit_date,
            'discharge_date': None,  # 합성 데이터는 퇴원 정보 없음
            'primary_diagnosis': primary_diagnosis,
        }

        patients.append(patient_data)
        seen_ids.add(patient_id)
        print(f"  [SYNTH] {patient_id}: {patient_data['name']}, {patient_data['age']}세, {gender}, {infection_code}")
    
    return patients


# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 60)
    print("04_load_master.py - patients + admissions 적재")
    print("=" * 60)
    
    # --------------------------------------------------------
    # 1. 데이터 로드
    # --------------------------------------------------------
    print(f"\n[1/4] 환자 데이터 로드 중...")
    
    print(f"\n  --- MIMIC 기반 환자 ({TIMELINES_DIR}) ---")
    mimic_patients = load_mimic_patients()
    
    print(f"\n  --- T0X 합성 환자 ({EMR_OUTPUTS_DIR}) ---")
    synthetic_patients = load_synthetic_patients()
    
    patients = mimic_patients + synthetic_patients
    print(f"\n  ✓ 총 {len(patients)}명 로드 완료 (MIMIC: {len(mimic_patients)}, SYNTH: {len(synthetic_patients)})")
    
    if not patients:
        print("  ✗ 로드된 환자가 없습니다. 경로를 확인하세요.")
        return
    
    # --------------------------------------------------------
    # 2. Oracle 연결
    # --------------------------------------------------------
    print("\n[2/4] Oracle 연결 중...")
    oracledb.init_oracle_client(lib_dir="/opt/oracle/instantclient_23_3")
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
    cursor = conn.cursor()
    print("  ✓ 연결 성공")
    
    # --------------------------------------------------------
    # 3. patients 테이블 적재
    # --------------------------------------------------------
    print("\n[3/4] patients 테이블 적재 중...")
    
    # 기존 데이터 삭제 (재실행 대비)
    cursor.execute("DELETE FROM admissions")
    cursor.execute("DELETE FROM patients")
    conn.commit()
    print("  ✓ 기존 데이터 삭제")
    
    insert_patient_sql = """
    INSERT INTO patients (
        patient_id, name, age, gender, date_of_birth, infection_code
    ) VALUES (
        :patient_id, :name, :age, :gender, :date_of_birth, :infection_code
    )
    """
    
    patient_rows = [
        {
            'patient_id': p['patient_id'],
            'name': p['name'],
            'age': p['age'],
            'gender': p['gender'],
            'date_of_birth': None,
            'infection_code': p['infection_code'],
        }
        for p in patients
    ]
    
    start_t = time.time()
    
    for row in patient_rows:
        try:
            cursor.execute(insert_patient_sql, row)
        except oracledb.IntegrityError as e:
            if 'ORA-00001' in str(e):
                print(f"  ⚠ 중복 스킵: {row['patient_id']}")
            else:
                raise
    
    conn.commit()
    elapsed = time.time() - start_t
    print(f"  ✓ {len(patient_rows)}명 적재 완료 ({_fmt_hms(elapsed)})")
    
    # --------------------------------------------------------
    # 4. admissions 테이블 적재
    # --------------------------------------------------------
    print("\n[4/4] admissions 테이블 적재 중...")
    
    insert_admission_sql = """
    INSERT INTO admissions (
        patient_id, admit_date, sim_admit_date, discharge_date,
        status, current_hd, primary_diagnosis, alert_level,
        attending_doctor, attending_nurse
    ) VALUES (
        :patient_id,
        TO_TIMESTAMP(:admit_date, 'YYYY-MM-DD'),
        :sim_admit_date,
        TO_TIMESTAMP(:discharge_date, 'YYYY-MM-DD'),
        :status,
        :current_hd,
        :primary_diagnosis,
        :alert_level,
        :attending_doctor,
        :attending_nurse
    )
    """
    
    admission_rows = [
        {
            'patient_id': p['patient_id'],
            'admit_date': p['admit_date'],
            'sim_admit_date': None,
            'discharge_date': p['discharge_date'],
            'status': 'active',
            'current_hd': None,
            'primary_diagnosis': p['primary_diagnosis'],
            'alert_level': None,
            'attending_doctor': None,
            'attending_nurse': None,
        }
        for p in patients
    ]
    
    start_t = time.time()
    
    for row in admission_rows:
        try:
            cursor.execute(insert_admission_sql, row)
        except oracledb.IntegrityError as e:
            print(f"  ⚠ 에러: {row['patient_id']} - {e}")
    
    conn.commit()
    elapsed = time.time() - start_t
    print(f"  ✓ {len(admission_rows)}건 적재 완료 ({_fmt_hms(elapsed)})")
    
    # --------------------------------------------------------
    # 결과 확인
    # --------------------------------------------------------
    print("\n[결과 확인]")
    cursor.execute("SELECT patient_id, name, age, gender, infection_code FROM patients ORDER BY patient_id")
    print("\n  patients:")
    for row in cursor.fetchall():
        print(f"    {row}")
    
    cursor.execute("SELECT patient_id, admit_date, primary_diagnosis FROM admissions ORDER BY patient_id")
    print("\n  admissions:")
    for row in cursor.fetchall():
        print(f"    {row}")
    
    # --------------------------------------------------------
    # 정리
    # --------------------------------------------------------
    cursor.close()
    conn.close()
    print("\n" + "=" * 60)
    print("✓ 적재 완료")
    print("=" * 60)


if __name__ == '__main__':
    main()
