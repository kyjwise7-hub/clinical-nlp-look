"""
axis_spec.yml 파서
- axis_spec.yml을 읽어서 슬롯→축 매핑 테이블을 반환
- 6A, 6B 모두에서 재사용
"""

import os

SPECS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'specs')

def load_axis_spec(spec_path=None):
    """axis_spec.yml을 로드하여 원본 dict 반환"""
    if spec_path is None:
        spec_path = os.path.join(SPECS_DIR, 'axis_spec.yml')
    try:
        import yaml
    except ImportError:
        print("⚠ pyyaml 미설치 — axis_spec 로드 비활성화")
        return {}
    with open(spec_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

# def build_slot_to_axis_map(spec=None):
#     """
#     슬롯→축 매핑 테이블 생성
    
#     Returns:
#         {
#             'spo2_value': 'A_respiratory',
#             'temp_value': 'B_infection_activity',
#             'hr_value': '_supplementary',
#             ...
#         }
#     """
#     if spec is None:
#         spec = load_axis_spec()
    
#     slot_map = {}
#     axes = spec.get('axes', {})
    
#     for axis_key, axis_def in axes.items():
#         # Axis D(enabled: false) 스킵
#         if axis_def.get('enabled') is False:
#             continue
        
#         # snapshot_slots 매핑 (A, B, C, F)
#         for slot_name in axis_def.get('snapshot_slots', {}).keys():
#             slot_map[slot_name] = axis_key
        
#         # event_slots 매핑 (E)
#         for slot_name in axis_def.get('event_slots', {}).keys():
#             slot_map[slot_name] = axis_key
    
#     # supplementary_vitals 매핑
#     supp = spec.get('supplementary_vitals', {})
#     for slot_name in supp.get('snapshot_slots', {}).keys():
#         slot_map[slot_name] = '_supplementary'
    
#     return slot_map

def build_slot_to_axis_map(spec=None):
    """
    슬롯→축 매핑 테이블 생성
    """
    if spec is None:
        spec = load_axis_spec()
    
    slot_map = {}
    axes = spec.get('axes', {})
    
    for axis_key, axis_def in axes.items():
        if axis_def.get('enabled') is False:
            continue
        # supplementary_vitals is a helper lane; never override explicit A~F mappings.
        is_supplementary_axis = axis_key == 'supplementary_vitals'
        for slot_name in axis_def.get('snapshot_slots', {}).keys():
            if is_supplementary_axis:
                slot_map.setdefault(slot_name, '_supplementary')
            else:
                slot_map[slot_name] = axis_key
        for slot_name in axis_def.get('event_slots', {}).keys():
            if is_supplementary_axis:
                slot_map.setdefault(slot_name, '_supplementary')
            else:
                slot_map[slot_name] = axis_key
    
    supp = spec.get('supplementary_vitals', {})
    for slot_name in supp.get('snapshot_slots', {}).keys():
        # Do not override explicit axis mappings (e.g., bp_sys in B axis).
        slot_map.setdefault(slot_name, '_supplementary')
    
    # ── BE 후처리 파생 슬롯 매핑 ──
    # snapshot_generator.py의 NLP 이슈 후처리에서 생성되는 슬롯들
    # culture_result(B축) flatten → culture_status, culture_organism
    slot_map['culture_status'] = 'B_infection_activity'
    slot_map['culture_organism'] = 'B_infection_activity'
    # ── 파생 슬롯 매핑 끝 ──
    
    return slot_map

def get_active_axes(spec=None):
    """활성화된 축 목록 반환"""
    if spec is None:
        spec = load_axis_spec()
    
    active = []
    for axis_key, axis_def in spec.get('axes', {}).items():
        if axis_def.get('enabled') is not False:
            active.append(axis_key)
    return active

def is_event_stream_axis(axis_key, spec=None):
    """해당 축이 event_stream인지 확인 (Axis E)"""
    if spec is None:
        spec = load_axis_spec()
    axis_def = spec.get('axes', {}).get(axis_key, {})
    return axis_def.get('event_stream', False)


if __name__ == '__main__':
    # 테스트: 매핑 테이블 출력
    slot_map = build_slot_to_axis_map()
    print(f"총 매핑된 슬롯: {len(slot_map)}개\n")
    
    # 축별로 그룹핑해서 출력
    from collections import defaultdict
    axis_groups = defaultdict(list)
    for slot, axis in sorted(slot_map.items()):
        axis_groups[axis].append(slot)
    
    for axis in sorted(axis_groups.keys()):
        slots = axis_groups[axis]
        print(f"{axis} ({len(slots)}개):")
        for s in slots:
            print(f"  - {s}")
        print()
