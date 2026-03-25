"""
Phase 6A: Axis Snapshot Generator
- tagged_slots_FINAL.jsonl → axis_snapshots.jsonl
- 슬롯을 축별로 분배하고, shift 기반 병합 수행
"""

import json
from collections import defaultdict
from datetime import datetime

from utils.axis_spec_parser import (
    build_slot_to_axis_map,
    load_axis_spec,
    is_event_stream_axis,
)

# ──────────────────────────────────────────
# Step 1: 입력 읽기 + 정규화
# ──────────────────────────────────────────

# ──────────────────────────────────────────
# 기존 코드
# ──────────────────────────────────────────
# def parse_tagged_slots(input_path):
#     """tagged_slots_FINAL.jsonl을 읽어서 정규화된 dict 리스트 반환"""
#     docs = []
#     skipped = 0
    
#     with open(input_path, 'r', encoding='utf-8') as f:
#         for line_num, line in enumerate(f, 1):
#             line = line.strip()
#             if not line:
#                 continue
            
#             doc = json.loads(line)
            
#             # 필수 필드 검증
#             patient_id = doc.get('patient_id')
#             doc_datetime = doc.get('doc_datetime')
#             extracted_slots = doc.get('extracted_slots', {})
            
#             if not patient_id or not doc_datetime:
#                 skipped += 1
#                 continue
#             if not extracted_slots:
#                 skipped += 1
#                 continue
            
#             docs.append({
#                 'document_id': doc.get('document_id'),
#                 'patient_id': str(patient_id),
#                 'doc_type': doc.get('document_type'),
#                 'doc_datetime': doc_datetime,
#                 'hd': doc.get('hd'),
#                 'd_number': doc.get('d_number'),
#                 'slots': extracted_slots,
#             })
    
#     print(f"[Step 1] 로드 완료: {len(docs)}건 (스킵: {skipped}건)")
#     return docs

# ──────────────────────────────────────────
# NLP 데이터 이슈 후처리
# 아래 3개 함수는 tagged_slots_FINAL.jsonl의 데이터 이슈를 BE에서 우회 처리함.
# ──────────────────────────────────────────

# [이슈 1] abx_event에 약품명이 혼입되어 있음
# diff_rules.yaml axis_B_infection_activity priority 1 (abx_escalate_or_change)
# 기대값: start, change, escalate, deescalate, stop, none, unknown
# 실제값: Vancomycin(47건), Ampicillin(6건) 등 약품명 혼입
VALID_ABX_EVENTS = {'start', 'change', 'escalate', 'deescalate', 'stop', 'none', 'unknown'}
CHANGE_KEYWORDS = {'변경', 'changed', 'change', 'switched'}

def normalize_abx_event(value):
    """abx_event 값이 유효하지 않으면 약품명으로 간주하고 변환"""
    if value is None:
        return None
    str_val = str(value).strip().lower()
    if str_val in VALID_ABX_EVENTS:
        return str_val
    # "항생제 변경", "Antibiotic changed" 등 → change
    if any(kw in str_val for kw in CHANGE_KEYWORDS):
        return 'change'
    # 그 외 약품명 → start로 간주
    return 'start'


# [이슈 2] culture_result 참조 방식과 값이 diff_rules와 불일치
# diff_rules.yaml axis_B_infection_activity priority 4 (culture_result_arrived)
# 규칙이 culture_status(플랫, 값: positive/negative)를 참조하는데
# 실제 데이터는 culture_result.status(중첩, 값: pos/neg)로 들어옴
STATUS_VALUE_MAP = {
    'pos': 'positive',
    'neg': 'negative',
    'no_growth': 'no_growth',
    'pending': 'pending',
    'preliminary': 'preliminary',
    'contaminated': 'contaminated',
    'unknown': 'unknown',
}

def flatten_culture_result(slots):
    """culture_result 중첩 객체를 플랫 슬롯으로 분리 + 값 정규화"""
    cr = slots.get('culture_result')
    if not isinstance(cr, dict):
        return
    status = cr.get('status')
    if status:
        slots['culture_status'] = STATUS_VALUE_MAP.get(status, status)
    organism = cr.get('organism')
    if organism:
        slots['culture_organism'] = organism


# [이슈 3] mdro_status 슬롯이 한 건도 추출되지 않음
# diff_rules.yaml axis_E_infection_control priority 1 (mdro_confirmed)
# 규칙이 mdro_status == confirmed를 조건으로 하는데 데이터에 mdro_status 0건
# mdro_flag(38건)가 존재하면 confirmed로 파생 생성
MDRO_NONE_VALUES = {'none', 'unknown', '', None}

def derive_mdro_status(slots):
    """mdro_flag가 유효하고 mdro_status가 없으면 confirmed로 파생 생성"""
    if 'mdro_status' in slots:
        return  # 이미 있으면 건드리지 않음
    mdro_flag = slots.get('mdro_flag')
    if mdro_flag and str(mdro_flag).strip().lower() not in MDRO_NONE_VALUES:
        slots['mdro_status'] = 'confirmed'


# ──────────────────────────────────────────
# Step 1: 입력 읽기 + 정규화
# ──────────────────────────────────────────

def parse_tagged_slots(input_path):
    """tagged_slots_FINAL.jsonl을 읽어서 정규화된 dict 리스트 반환"""
    docs = []
    skipped = 0

    with open(input_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            doc = json.loads(line)

            # 필수 필드 검증
            patient_id = doc.get('patient_id')
            doc_datetime = doc.get('doc_datetime')
            extracted_slots = doc.get('extracted_slots', {})

            if not patient_id or not doc_datetime:
                skipped += 1
                continue
            if not extracted_slots:
                skipped += 1
                continue

            # ── NLP 데이터 이슈 후처리 (이슈 1, 2, 3) ──
            if 'abx_event' in extracted_slots:
                extracted_slots['abx_event'] = normalize_abx_event(extracted_slots['abx_event'])
            flatten_culture_result(extracted_slots)
            derive_mdro_status(extracted_slots)
            # ── 후처리 끝 ──

            docs.append({
                'document_id': doc.get('document_id'),
                'patient_id': str(patient_id),
                'doc_type': doc.get('document_type'),
                'doc_datetime': doc_datetime,
                'hd': doc.get('hd'),
                'd_number': doc.get('d_number'),
                'slots': extracted_slots,
            })

    print(f"[Step 1] 로드 완료: {len(docs)}건 (스킵: {skipped}건)")
    return docs

# ──────────────────────────────────────────
# Step 2 & 3: 슬롯 분배 + 스냅샷 생성
# ──────────────────────────────────────────

def determine_shift(doc_datetime_str):
    """시간 기준으로 shift 판별"""
    dt = datetime.fromisoformat(doc_datetime_str)
    hour = dt.hour
    if 6 <= hour < 14:
        return 'Day'
    elif 14 <= hour < 22:
        return 'Evening'
    else:
        return 'Night'

def distribute_and_create_snapshots(docs, slot_map, spec):
    """
    문서별로 슬롯을 축에 분배하고, 스냅샷 객체 생성.
    문서 1건 → 축별 스냅샷 N개 (슬롯이 있는 축만)
    """
    snapshots = []
    
    for doc in docs:
        shift = determine_shift(doc['doc_datetime'])
        
        # 슬롯을 축별로 분배
        axis_slots = defaultdict(dict)       # { 'A_respiratory': { 'spo2_value': 97, ... } }
        supplementary = {}
        unmapped = []
        
        for slot_name, slot_value in doc['slots'].items():
            axis = slot_map.get(slot_name)
            if axis is None:
                unmapped.append(slot_name)
            elif axis == '_supplementary':
                supplementary[slot_name] = slot_value
            else:
                axis_slots[axis][slot_name] = slot_value
        
        # 축별 스냅샷 생성 (슬롯이 1개라도 있는 축만)
        for axis_key, slots in axis_slots.items():
            snapshot = {
                'patient_id': doc['patient_id'],
                'axis': axis_key,
                'doc_datetime': doc['doc_datetime'],
                'shift': shift,
                'hd': doc['hd'],
                'd_number': doc['d_number'],
                'slots': slots,
                'supplementary': supplementary if supplementary else None,
                'source_docs': [doc['document_id']],
                'is_event_stream': is_event_stream_axis(axis_key, spec),
            }
            snapshots.append(snapshot)
        
        if unmapped:
            print(f"  [WARN] 매핑 안 된 슬롯: {unmapped} (doc: {doc['document_id']})")
    
    print(f"[Step 2-3] 스냅샷 생성: {len(snapshots)}개")
    return snapshots


# ──────────────────────────────────────────
# Step 4: 동일 시점 병합
# ──────────────────────────────────────────

def make_merge_key(snapshot):
    """병합 기준 키: 환자 + 축 + HD + D + shift"""
    return (
        snapshot['patient_id'],
        snapshot['axis'],
        snapshot['hd'],
        snapshot['d_number'],
        snapshot['shift'],
    )

def make_snapshot_id(merge_key):
    """snapshot_id 생성: SNAP_{patient}_{axis}_HD{hd}_D{d}_{shift}"""
    patient_id, axis, hd, d_number, shift = merge_key
    # axis에서 접두사 제거 (A_respiratory → A)
    axis_short = axis.split('_')[0]
    return f"SNAP_{patient_id}_{axis_short}_HD{hd}_D{d_number}_{shift}"

def merge_snapshots(snapshots):
    """
    같은 환자+축+HD+D+shift의 스냅샷들을 병합.
    - 슬롯 충돌: doc_datetime이 더 늦은 값 채택
    - 배열 슬롯: 합집합
    - source_docs: 전부 합침
    """
    # merge_key별로 그룹핑
    groups = defaultdict(list)
    for snap in snapshots:
        key = make_merge_key(snap)
        groups[key].append(snap)
    
    merged = []
    
    for merge_key, group in groups.items():
        if len(group) == 1:
            # 병합 불필요
            snap = group[0]
            snap['snapshot_id'] = make_snapshot_id(merge_key)
            merged.append(snap)
            continue
        
        # doc_datetime 기준 정렬 (오래된 것 먼저)
        group.sort(key=lambda s: s['doc_datetime'])
        
        # 베이스: 가장 오래된 스냅샷에서 시작
        base = {
            'snapshot_id': make_snapshot_id(merge_key),
            'patient_id': merge_key[0],
            'axis': merge_key[1],
            'hd': merge_key[2],
            'd_number': merge_key[3],
            'shift': merge_key[4],
            'doc_datetime': group[-1]['doc_datetime'],  # 가장 늦은 시간
            'slots': {},
            'supplementary': {},
            'source_docs': [],
            'is_event_stream': group[0]['is_event_stream'],
        }
        
        # 순서대로 덮어쓰기 (나중 것이 우선)
        for snap in group:
            # source_docs 합치기
            base['source_docs'].extend(snap['source_docs'])
            
            # slots 병합
            for slot_name, slot_value in snap['slots'].items():
                if isinstance(slot_value, list) and slot_name in base['slots']:
                    # 배열 슬롯: 합집합
                    existing = base['slots'][slot_name]
                    if isinstance(existing, list):
                        combined = list(set(existing + slot_value))
                        base['slots'][slot_name] = combined
                    else:
                        base['slots'][slot_name] = slot_value
                else:
                    # 스칼라 슬롯: 최신 값 덮어쓰기
                    base['slots'][slot_name] = slot_value
            
            # supplementary 병합
            if snap.get('supplementary'):
                for slot_name, slot_value in snap['supplementary'].items():
                    base['supplementary'][slot_name] = slot_value
        
        # supplementary가 비었으면 None
        if not base['supplementary']:
            base['supplementary'] = None
        
        # source_docs 중복 제거 + 순서 유지
        seen = set()
        unique_docs = []
        for doc_id in base['source_docs']:
            if doc_id not in seen:
                seen.add(doc_id)
                unique_docs.append(doc_id)
        base['source_docs'] = unique_docs
        
        merged.append(base)
    
    print(f"[Step 4] 병합 완료: {len(snapshots)}개 → {len(merged)}개")
    return merged


# ──────────────────────────────────────────
# Step 5: 출력
# ──────────────────────────────────────────

def sort_snapshots(snapshots):
    """patient_id → axis → hd → d_number → shift 순 정렬"""
    shift_order = {'Day': 0, 'Evening': 1, 'Night': 2}
    return sorted(snapshots, key=lambda s: (
        s['patient_id'],
        s['axis'],
        s.get('hd', 0),
        s.get('d_number', 0),
        shift_order.get(s['shift'], 9),
    ))

def write_snapshots(snapshots, output_path):
    """axis_snapshots.jsonl 출력"""
    sorted_snaps = sort_snapshots(snapshots)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for snap in sorted_snaps:
            f.write(json.dumps(snap, ensure_ascii=False) + '\n')
    
    print(f"[Step 5] 출력 완료: {output_path} ({len(sorted_snaps)}건)")

def sanity_check(snapshots):
    """기본 검증"""
    issues = []
    
    for snap in snapshots:
        if not snap.get('slots'):
            issues.append(f"빈 slots: {snap.get('snapshot_id')}")
        if not snap.get('source_docs'):
            issues.append(f"빈 source_docs: {snap.get('snapshot_id')}")
        if not snap.get('snapshot_id'):
            issues.append(f"snapshot_id 없음: patient={snap.get('patient_id')}, axis={snap.get('axis')}")
    
    # 통계
    patients = set(s['patient_id'] for s in snapshots)
    axes = set(s['axis'] for s in snapshots)
    
    print(f"\n[Sanity Check]")
    print(f"  환자 수: {len(patients)}")
    print(f"  활성 축: {sorted(axes)}")
    print(f"  총 스냅샷: {len(snapshots)}")
    print(f"  이슈: {len(issues)}건")
    
    for issue in issues[:10]:
        print(f"    ⚠️ {issue}")
    
    # 환자별 스냅샷 수
    patient_counts = defaultdict(int)
    for s in snapshots:
        patient_counts[s['patient_id']] += 1
    
    print(f"\n  환자별 스냅샷 수:")
    for pid in sorted(patient_counts.keys()):
        print(f"    {pid}: {patient_counts[pid]}개")
