"""
Phase 6B 실행 엔트리포인트
Usage: python 06b_trajectory_event_generator.py [--input PATH] [--output PATH] [--rules PATH]
"""

import argparse
import json
import os
import sys
from collections import defaultdict

from utils.diff_engine import (
    load_diff_rules,
    get_axis_rules,
    get_template_aliases,
    get_axis_priority,
    load_snapshots,
    group_snapshots,
    generate_events,
    sort_events,
)


def write_events(events, output_path):
    """trajectory_events.jsonl 출력"""
    sorted_events = sort_events(events)
    with open(output_path, 'w', encoding='utf-8') as f:
        for event in sorted_events:
            f.write(json.dumps(event, ensure_ascii=False) + '\n')
    print(f"[출력] {output_path} ({len(sorted_events)}건)")


def print_summary(events):
    """이벤트 요약 출력"""
    print(f"\n{'='*60}")
    print("이벤트 생성 요약")
    print(f"{'='*60}")

    # 축별 집계
    axis_counts = defaultdict(int)
    type_counts = defaultdict(int)
    patient_counts = defaultdict(int)

    for e in events:
        axis_counts[e['axis']] += 1
        type_counts[e['event_type']] += 1
        patient_counts[e['patient_id']] += 1

    print(f"\n총 이벤트: {len(events)}개")
    print(f"환자 수: {len(patient_counts)}명")

    print(f"\n축별:")
    for axis in sorted(axis_counts.keys()):
        print(f"  {axis}: {axis_counts[axis]}개")

    print(f"\n이벤트 유형별:")
    for etype in sorted(type_counts.keys(), key=lambda x: -type_counts[x]):
        print(f"  {etype}: {type_counts[etype]}개")

    print(f"\n환자별:")
    for pid in sorted(patient_counts.keys()):
        print(f"  {pid}: {patient_counts[pid]}개")

    # 작동 안 한 규칙 체크
    expected_types = [
        'resp_support_increase', 'resp_support_decrease', 'o2_start_or_increase', 'spo2_drop_same_o2',
        'cxr_severity_up', 'cxr_severity_down',
        'abx_escalation', 'abx_deescalation', 'abx_discontinuation', 'abx_escalate_or_change',
        'culture_ordered_new', 'platelet_drop', 'platelet_recover',
        'culture_result_arrived', 'temp_spike', 'temp_down', 'wbc_rise', 'wbc_down', 'crp_rise', 'crp_down',
        'hemodynamic_instability', 'hemodynamic_recovery', 'lab_worsening', 'lab_improving',
        'monitoring_escalated', 'vitals_frequency_escalated',
        'notify_first_seen', 'prn_increase',
        'new_mdro_detection', 'mdro_confirmed', 'isolation_gap', 'isolation_applied', 'cluster_suspected',
        'mental_status_change', 'pain_escalation', 'pain_relief', 'new_symptom_detected', 'pain_location_change',
    ]

    generated_types = set(type_counts.keys())
    missing = [t for t in expected_types if t not in generated_types]

    if missing:
        print(f"\n⚠️  이벤트 0건인 규칙 ({len(missing)}개):")
        for t in missing:
            print(f"  - {t}")


def main():
    parser = argparse.ArgumentParser(description='Phase 6B: Trajectory Event Generator')

    base_dir = os.path.join(os.path.dirname(__file__), '..')

    parser.add_argument(
        '--input',
        default=os.path.join(base_dir, 'data', 'axis_snapshots.jsonl'),
        help='axis_snapshots.jsonl 경로'
    )
    parser.add_argument(
        '--output',
        default=os.path.join(base_dir, 'data', 'trajectory_events.jsonl'),
        help='trajectory_events.jsonl 출력 경로'
    )
    parser.add_argument(
        '--rules',
        default=None,
        help='diff_rules.yaml 경로 (기본: nlp/specs/diff_rules.yaml)'
    )

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"❌ 입력 파일 없음: {args.input}")
        sys.exit(1)

    os.makedirs(os.path.dirname(args.output), exist_ok=True)

    print("=" * 60)
    print("Phase 6B: Trajectory Event Generator")
    print("=" * 60)
    print(f"입력: {args.input}")
    print(f"출력: {args.output}")
    print()

    # diff_rules 로드
    diff_rules = load_diff_rules(args.rules)
    axis_rules = get_axis_rules(diff_rules)
    aliases = get_template_aliases(diff_rules)
    axis_priority = get_axis_priority(diff_rules)

    active_axes = list(axis_rules.keys())
    total_rules = sum(len(r) for r in axis_rules.values())
    print(f"[규칙 로드] 활성 축: {active_axes}")
    print(f"[규칙 로드] 총 규칙: {total_rules}개\n")

    # 스냅샷 로드 + 그룹핑
    snapshots = load_snapshots(args.input)
    print(f"[스냅샷 로드] {len(snapshots)}건")

    grouped = group_snapshots(snapshots)
    print(f"[그룹핑] {len(grouped)}개 그룹 (환자×축)\n")

    # 이벤트 생성
    events = generate_events(grouped, axis_rules, aliases, axis_priority)

    # 출력
    write_events(events, args.output)

    # 요약
    print_summary(events)

    print(f"\n✅ 6B 완료")


if __name__ == '__main__':
    main()
