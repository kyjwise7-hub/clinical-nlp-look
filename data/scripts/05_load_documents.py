"""
05_load_documents.py
원본 문서 테이블 적재 (nursing_notes, physician_notes, lab_results, microbiology_results, radiology_reports)

입력:
  - emr-generator/outputs/patient_*/hd_*.json

출력:
  - nursing_notes INSERT
  - physician_notes INSERT
  - lab_results INSERT
  - microbiology_results INSERT
  - radiology_reports INSERT
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
EMR_OUTPUTS_DIR = BASE_DIR / 'emr-generator' / 'outputs'

DB_USER = os.getenv('ORACLE_USER')
DB_PASSWORD = os.getenv('ORACLE_PASSWORD')
DB_DSN = os.getenv('ORACLE_CONNECTION_STRING')

# Lab 항목 매핑 (JSON 필드 → item_code, item_name, unit)
LAB_ITEMS = {
    'wbc': ('WBC', 'White Blood Cell', 'K/uL'),
    'hgb': ('HGB', 'Hemoglobin', 'g/dL'),
    'plt': ('PLT', 'Platelet', 'K/uL'),
    'cr': ('CR', 'Creatinine', 'mg/dL'),
    'bun': ('BUN', 'Blood Urea Nitrogen', 'mg/dL'),
    'na': ('NA', 'Sodium', 'mEq/L'),
    'k': ('K', 'Potassium', 'mEq/L'),
    'glucose': ('GLU', 'Glucose', 'mg/dL'),
    'lactate': ('LACTATE', 'Lactate', 'mmol/L'),
    'crp': ('CRP', 'C-Reactive Protein', 'mg/L'),
    'procalcitonin': ('PCT', 'Procalcitonin', 'ng/mL'),
}

PAIN_NRS_PATTERNS = [
    re.compile(r"(?:통증|pain)\s*:?\s*(\d{1,2})\s*/\s*10", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*/\s*10\s*(?:\(NRS\)|NRS)", re.IGNORECASE),
    re.compile(r"NRS\s*[:=]?\s*(\d{1,2})", re.IGNORECASE),
]

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


def get_admission_id(cursor, patient_id: str) -> int | None:
    """patient_id로 admission_id 조회"""
    cursor.execute(
        "SELECT admission_id FROM admissions WHERE patient_id = :pid",
        {'pid': patient_id}
    )
    row = cursor.fetchone()
    return row[0] if row else None


def extract_patient_id_from_path(patient_dir: Path) -> str:
    """
    patient_11601773 → "11601773"
    patient_T01 / patient_T01_Patient → "T01"
    """
    dir_name = patient_dir.name
    
    # T0X 패턴 (patient_T01, patient_T01_Patient 모두 허용)
    match = re.search(r'patient_(T\d+)(?:_Patient)?$', dir_name)
    if match:
        return match.group(1)
    
    # 숫자 ID 패턴
    match = re.search(r'patient_(\d+)', dir_name)
    if match:
        return match.group(1)
    
    return dir_name


def extract_pain_nrs(objective: str | None, raw_text: str | None) -> int | None:
    """
    nursing note 텍스트에서 통증 NRS(0~10) 추출.
    objective 우선, 없으면 raw_text에서 보조 추출.
    """
    for text in (objective, raw_text):
        if not text:
            continue
        for pattern in PAIN_NRS_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            try:
                value = int(match.group(1))
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 10:
                return value
    return None


def _safe_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_hd_d_from_filename(path: Path) -> tuple[int | None, int | None]:
    """
    hd_05_d+4.json 형태에서 (hd=5, d_number=4) 추출.
    """
    match = re.match(r"hd_(\d+)_d([+-]?\d+)\.json$", path.name)
    if not match:
        return None, None
    return _safe_int(match.group(1)), _safe_int(match.group(2))


def resolve_file_scope(data: dict, json_path: Path) -> tuple[int | None, int | None]:
    """
    파일 단위 hd/d_number를 확정한다.
    우선순위: JSON 루트 값 -> 파일명 파싱
    """
    hd = _safe_int(data.get('hd'))
    d_number = _safe_int(data.get('d_number'))

    if hd is not None and d_number is not None:
        return hd, d_number

    hd_from_name, d_from_name = _parse_hd_d_from_filename(json_path)
    return hd if hd is not None else hd_from_name, d_number if d_number is not None else d_from_name


# ============================================================
# 문서별 INSERT 함수
# ============================================================
def insert_nursing_note(cursor, admission_id: int, doc: dict):
    """nursing_note INSERT"""
    vital_signs = doc.get('vital_signs', {})
    
    sql = """
    INSERT INTO nursing_notes (
        admission_id, note_datetime, note_type,
        subjective, objective, assessment, plan_action, raw_text,
        temp, hr, rr, bp_sys, bp_dia, spo2,
        o2_device, o2_flow, intake, output, notify_md,
        pain_nrs, hd, d_number
    ) VALUES (
        :admission_id,
        TO_TIMESTAMP(:note_datetime, 'YYYY-MM-DD"T"HH24:MI:SS'),
        :note_type,
        :subjective, :objective, :assessment, :plan_action, :raw_text,
        :temp, :hr, :rr, :bp_sys, :bp_dia, :spo2,
        :o2_device, :o2_flow, :intake, :output, :notify_md,
        :pain_nrs, :hd, :d_number
    )
    """
    
    objective = doc.get('objective')
    raw_text = doc.get('raw_text')

    params = {
        'admission_id': admission_id,
        'note_datetime': doc.get('note_datetime'),
        'note_type': doc.get('note_type'),
        'subjective': doc.get('subjective'),
        'objective': objective,
        'assessment': doc.get('assessment'),
        'plan_action': doc.get('plan_action'),
        'raw_text': raw_text,
        'temp': vital_signs.get('temp'),
        'hr': vital_signs.get('hr'),
        'rr': vital_signs.get('rr'),
        'bp_sys': vital_signs.get('bp_sys'),
        'bp_dia': vital_signs.get('bp_dia'),
        'spo2': vital_signs.get('spo2'),
        'o2_device': doc.get('o2_device'),
        'o2_flow': doc.get('o2_flow'),
        'intake': doc.get('intake'),
        'output': doc.get('output'),
        'notify_md': 1 if doc.get('notify_md') else 0,
        'pain_nrs': extract_pain_nrs(objective, raw_text),
        'hd': doc.get('hd'),
        'd_number': doc.get('d_number'),
    }
    
    cursor.execute(sql, params)


def insert_physician_note(cursor, admission_id: int, doc: dict):
    """physician_note INSERT"""
    
    # 배열/객체 → JSON 문자열 변환
    objective = doc.get('objective', {})
    assessment = doc.get('assessment', [])
    plan = doc.get('plan', [])
    problem_list = doc.get('problem_list', [])
    
    sql = """
    INSERT INTO physician_notes (
        admission_id, note_datetime, note_type,
        subjective, objective_json, diagnosis, assessment_json, plan,
        problem_list_json, treatment_history, raw_text,
        hd, d_number
    ) VALUES (
        :admission_id,
        TO_TIMESTAMP(:note_datetime, 'YYYY-MM-DD"T"HH24:MI:SS'),
        :note_type,
        :subjective, :objective_json, :diagnosis, :assessment_json, :plan,
        :problem_list_json, :treatment_history, :raw_text,
        :hd, :d_number
    )
    """
    
    params = {
        'admission_id': admission_id,
        'note_datetime': doc.get('note_datetime'),
        'note_type': doc.get('note_type'),
        'subjective': doc.get('subjective'),
        'objective_json': json.dumps(objective, ensure_ascii=False) if objective else None,
        'diagnosis': assessment[0] if assessment else None,  # 첫 번째 assessment를 diagnosis로
        'assessment_json': json.dumps(assessment, ensure_ascii=False) if assessment else None,
        'plan': '\n'.join(plan) if plan else None,
        'problem_list_json': json.dumps(problem_list, ensure_ascii=False) if problem_list else None,
        'treatment_history': doc.get('treatment_history'),
        'raw_text': doc.get('raw_text'),
        'hd': doc.get('hd'),
        'd_number': doc.get('d_number'),
    }
    
    cursor.execute(sql, params)


def insert_lab_results(cursor, admission_id: int, doc: dict):
    """lab_result INSERT (1 JSON → N rows)"""
    
    result_datetime = doc.get('result_datetime')
    hd = doc.get('hd')
    d_number = doc.get('d_number')
    
    sql = """
    INSERT INTO lab_results (
        admission_id, result_datetime, item_code, item_name, value, unit,
        hd, d_number
    ) VALUES (
        :admission_id,
        TO_TIMESTAMP(:result_datetime, 'YYYY-MM-DD"T"HH24:MI:SS'),
        :item_code, :item_name, :value, :unit,
        :hd, :d_number
    )
    """
    
    for json_field, (item_code, item_name, unit) in LAB_ITEMS.items():
        value = doc.get(json_field)
        if value is not None:
            params = {
                'admission_id': admission_id,
                'result_datetime': result_datetime,
                'item_code': item_code,
                'item_name': item_name,
                'value': str(value),
                'unit': unit,
                'hd': hd,
                'd_number': d_number,
            }
            cursor.execute(sql, params)


def insert_microbiology_result(cursor, admission_id: int, doc: dict):
    """microbiology_result INSERT"""
    
    susceptibility = doc.get('susceptibility', [])
    
    sql = """
    INSERT INTO microbiology_results (
        admission_id, specimen_type, collection_datetime, result_datetime,
        result_status, gram_stain, organism, colony_count,
        susceptibility_json, is_mdro, mdro_type, comments, raw_text,
        hd, d_number
    ) VALUES (
        :admission_id, :specimen_type,
        TO_TIMESTAMP(:collection_datetime, 'YYYY-MM-DD"T"HH24:MI:SS'),
        TO_TIMESTAMP(:result_datetime, 'YYYY-MM-DD"T"HH24:MI:SS'),
        :result_status, :gram_stain, :organism, :colony_count,
        :susceptibility_json, :is_mdro, :mdro_type, :comments, :raw_text,
        :hd, :d_number
    )
    """
    
    params = {
        'admission_id': admission_id,
        'specimen_type': doc.get('specimen_type'),
        'collection_datetime': doc.get('collection_datetime'),
        'result_datetime': doc.get('result_datetime'),
        'result_status': doc.get('result_status'),
        'gram_stain': doc.get('gram_stain'),
        'organism': doc.get('organism'),
        'colony_count': doc.get('colony_count'),
        'susceptibility_json': json.dumps(susceptibility, ensure_ascii=False) if susceptibility else None,
        'is_mdro': 1 if doc.get('is_mdro') else 0,
        'mdro_type': doc.get('mdro_type'),
        'comments': doc.get('comments'),
        'raw_text': doc.get('raw_text'),
        'hd': doc.get('hd'),
        'd_number': doc.get('d_number'),
    }
    
    cursor.execute(sql, params)


def insert_radiology_report(cursor, admission_id: int, doc: dict):
    """radiology INSERT"""

    sql = """
    INSERT INTO radiology_reports (
        admission_id, study_type, study_datetime,
        technique, comparison, findings, conclusion,
        severity_score, hd, d_number
    ) VALUES (
        :admission_id, :study_type,
        TO_TIMESTAMP(:study_datetime, 'YYYY-MM-DD"T"HH24:MI:SS'),
        :technique, :comparison, :findings, :conclusion,
        :severity_score, :hd, :d_number
    )
    """

    params = {
        'admission_id': admission_id,
        'study_type': doc.get('study_type'),
        'study_datetime': doc.get('study_datetime'),
        'technique': doc.get('technique'),
        'comparison': doc.get('comparison'),
        'findings': doc.get('findings'),
        'conclusion': doc.get('impression'),  # EMR의 impression → DB의 conclusion
        'severity_score': doc.get('severity'),
        'hd': doc.get('hd'),
        'd_number': doc.get('d_number'),
    }

    cursor.execute(sql, params)


# ============================================================
# 메인
# ============================================================
def main():
    print("=" * 60)
    print("05_load_documents.py - 원본 문서 적재")
    print("=" * 60)
    
    # --------------------------------------------------------
    # 1. Oracle 연결
    # --------------------------------------------------------
    print("\n[1/3] Oracle 연결 중...")
    oracledb.init_oracle_client(lib_dir="/opt/oracle/instantclient_23_3")
    conn = oracledb.connect(user=DB_USER, password=DB_PASSWORD, dsn=DB_DSN)
    cursor = conn.cursor()
    print("  ✓ 연결 성공")
    
    # --------------------------------------------------------
    # 2. 기존 데이터 삭제 (재실행 대비)
    # --------------------------------------------------------
    print("\n[2/3] 기존 데이터 삭제 중...")
    cursor.execute("DELETE FROM radiology_reports")
    cursor.execute("DELETE FROM nursing_notes")
    cursor.execute("DELETE FROM physician_notes")
    cursor.execute("DELETE FROM lab_results")
    cursor.execute("DELETE FROM microbiology_results")
    conn.commit()
    print("  ✓ 삭제 완료")
    
    # --------------------------------------------------------
    # 3. 문서 적재
    # --------------------------------------------------------
    print("\n[3/3] 문서 적재 중...")
    
    counts = {
        'nursing_note': 0,
        'physician_note': 0,
        'lab_result': 0,
        'microbiology': 0,
        'radiology': 0,
        'skipped': 0,
        'hd_dnumber_corrected': 0,
    }
    
    start_t = time.time()
    
    # 환자 폴더 순회
    for patient_dir in sorted(EMR_OUTPUTS_DIR.iterdir()):
        if not patient_dir.is_dir():
            continue
        if not patient_dir.name.startswith('patient_'):
            continue
        
        patient_id = extract_patient_id_from_path(patient_dir)
        admission_id = get_admission_id(cursor, patient_id)
        
        if not admission_id:
            print(f"  ⚠ admission_id 없음: {patient_id}")
            counts['skipped'] += 1
            continue
        
        # hd_*.json 파일 순회
        for json_path in sorted(patient_dir.glob('hd_*.json')):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            file_hd, file_d_number = resolve_file_scope(data, json_path)
            documents = data.get('documents', [])
            
            for doc in documents:
                doc_type = doc.get('document_type')
                doc_payload = dict(doc)

                # Night 문서가 다음 d_number로 밀리는 케이스를 포함해
                # 파일 단위 스코프(hd/d_number)로 정규화한다.
                if file_hd is not None:
                    if _safe_int(doc_payload.get('hd')) != file_hd:
                        counts['hd_dnumber_corrected'] += 1
                    doc_payload['hd'] = file_hd
                if file_d_number is not None:
                    if _safe_int(doc_payload.get('d_number')) != file_d_number:
                        counts['hd_dnumber_corrected'] += 1
                    doc_payload['d_number'] = file_d_number
                
                try:
                    if doc_type == 'nursing_note':
                        insert_nursing_note(cursor, admission_id, doc_payload)
                        counts['nursing_note'] += 1
                    
                    elif doc_type == 'physician_note':
                        insert_physician_note(cursor, admission_id, doc_payload)
                        counts['physician_note'] += 1
                    
                    elif doc_type == 'lab_result':
                        insert_lab_results(cursor, admission_id, doc_payload)
                        counts['lab_result'] += 1
                    
                    elif doc_type == 'microbiology':
                        insert_microbiology_result(cursor, admission_id, doc_payload)
                        counts['microbiology'] += 1

                    elif doc_type == 'radiology':
                        insert_radiology_report(cursor, admission_id, doc_payload)
                        counts['radiology'] += 1
                
                except Exception as e:
                    print(f"  ✗ 에러 [{patient_id}/{json_path.name}]: {e}")
        
        print(f"  ✓ {patient_id} 완료")
    
    conn.commit()
    elapsed = time.time() - start_t
    
    # --------------------------------------------------------
    # 결과 출력
    # --------------------------------------------------------
    print("\n" + "=" * 60)
    print("적재 결과")
    print("=" * 60)
    print(f"  nursing_notes:       {counts['nursing_note']}건")
    print(f"  physician_notes:     {counts['physician_note']}건")
    print(f"  lab_results:         {counts['lab_result']}건 (항목별 row)")
    print(f"  microbiology_results:{counts['microbiology']}건")
    print(f"  radiology_reports:   {counts['radiology']}건")
    print(f"  hd/d_number 보정:    {counts['hd_dnumber_corrected']}건")
    print(f"  skipped patients:    {counts['skipped']}명")
    print(f"  소요 시간:           {_fmt_hms(elapsed)}")
    
    # --------------------------------------------------------
    # 정리
    # --------------------------------------------------------
    cursor.close()
    conn.close()
    print("\n✓ 완료")


if __name__ == '__main__':
    main()
