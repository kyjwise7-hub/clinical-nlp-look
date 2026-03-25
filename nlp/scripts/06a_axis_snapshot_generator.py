"""
Phase 6A 실행 엔트리포인트
Usage: python 06a_axis_snapshot_generator.py [--input PATH] [--output PATH] [--spec PATH]
"""

import argparse
import os
import sys

from utils.axis_spec_parser import load_axis_spec, build_slot_to_axis_map
from utils.snapshot_generator import (
    parse_tagged_slots,
    distribute_and_create_snapshots,
    merge_snapshots,
    write_snapshots,
    sanity_check,
)

def main():
    parser = argparse.ArgumentParser(description='Phase 6A: Axis Snapshot Generator')
    
    base_dir = os.path.join(os.path.dirname(__file__), '..')
    
    parser.add_argument(
        '--input',
        default=os.path.join(base_dir, 'data', 'tagged_slots_FINAL.jsonl'),
        help='tagged_slots_FINAL.jsonl 경로'
    )
    parser.add_argument(
        '--output',
        default=os.path.join(base_dir, 'data', 'axis_snapshots.jsonl'),
        help='axis_snapshots.jsonl 출력 경로'
    )
    parser.add_argument(
        '--spec',
        default=None,
        help='axis_spec.yml 경로 (기본: nlp/specs/axis_spec.yml)'
    )
    
    args = parser.parse_args()
    
    # 입력 파일 존재 확인
    if not os.path.exists(args.input):
        print(f"❌ 입력 파일 없음: {args.input}")
        sys.exit(1)
    
    # 출력 디렉토리 생성
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    
    print("=" * 60)
    print("Phase 6A: Axis Snapshot Generator")
    print("=" * 60)
    print(f"입력: {args.input}")
    print(f"출력: {args.output}")
    print()
    
    # Step 0: axis_spec 로드 + 매핑 테이블 구축
    spec = load_axis_spec(args.spec)
    slot_map = build_slot_to_axis_map(spec)
    print(f"[Step 0] 매핑 테이블 구축: {len(slot_map)}개 슬롯\n")
    
    # Step 1: 입력 읽기
    docs = parse_tagged_slots(args.input)
    
    # Step 2-3: 슬롯 분배 + 스냅샷 생성
    snapshots = distribute_and_create_snapshots(docs, slot_map, spec)
    
    # Step 4: 병합
    merged = merge_snapshots(snapshots)
    
    # Step 5: 출력
    write_snapshots(merged, args.output)
    
    # 검증
    sanity_check(merged)
    
    print("\n✅ 6A 완료")


if __name__ == '__main__':
    main()
