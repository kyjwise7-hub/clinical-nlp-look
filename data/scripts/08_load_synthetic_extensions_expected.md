# 08_load_synthetic_extensions.py 환자별 적재 예상값

## 기준
- 스크립트: `data/scripts/08_load_synthetic_extensions.py`
- 코호트: 8자리 숫자 환자 + `T01~T03` (총 13명 기준)
- 목적: **08 실행 전에** 환자별로 어떤 레코드가 생성되는지 확인

## 공통 적재 규칙
- 환자당 공통 생성
1. `transfer_cases` 1건
2. `patient_status` 1건
3. `alerts` 1건(`status='ACTIVE'`)
4. `sepsis_risk_scores` 3건
5. `radiology_reports` 최소 1건
- 예외
1. `18294629`, `T03`은 radiology 2건
2. `M01/M03` 환자는 `mdro_checklist_logs` 생성
3. `PLANNED` 상태 환자만 `bed_assignment_items` 생성

## 환자별 상세
1. `11601773` (`G02` / Waterborne, M)
- 배정: `SX-3F-901-2` (`SX-3F-901`, `3F`)
- 이동: `WAITING`, reason=`격리 해제`, to_ward=`3F`, to_room/to_bed=`NULL`
- plan item: 없음
- flags: pathogen=`gastrointestinal_source`, clinical=`diarrhea,dehydration_risk`
- sepsis: `[0.25, 0.34, 0.43]` (latest `MEDIUM`)
- isolation_type: `CONTACT`
- radiology: 1건 (`CT`)
- mdro logs: 0

2. `12249103` (`P04` / Pneumonia, M)
- 배정: `SX-2F-901-1` (`SX-2F-901`, `2F`)
- 이동: `PLANNED`, reason=`신규 입원`, to=`SX-2F-901-2`
- plan item: 있음
- flags: pathogen=`respiratory_infection`, clinical=`cough,oxygen_support`
- sepsis: `[0.34, 0.45, 0.56]` (latest `MEDIUM`)
- isolation_type: `DROPLET`
- radiology: 1건 (`CXR`)
- mdro logs: 0

3. `12356657` (`M01` / MDRO, M)
- 배정: `SX-5F-901-1` (`SX-5F-901`, `5F`)
- 이동: `WAITING`, reason=`격리`, to_ward=`5F`, to_room/to_bed=`NULL`
- plan item: 없음
- flags: pathogen=`mrsa,contact_precaution`, clinical=`isolation_required,cohort_consideration`
- sepsis: `[0.54, 0.66, 0.77]` (latest `HIGH`)
- isolation_type: `CONTACT`
- radiology: 1건 (`CXR`, severe)
- mdro logs: 1 (`suspected`, `MRSA`)

4. `16836931` (`U01` / UTI, M)
- 배정: `SX-3F-901-1` (`SX-3F-901`, `3F`)
- 이동: `PLANNED`, reason=`격리 해제`, to=`SX-3F-902-1`
- plan item: 있음
- flags: pathogen=`urinary_source`, clinical=`dysuria,fever`
- sepsis: `[0.31, 0.41, 0.50]` (latest `MEDIUM`)
- isolation_type: `STANDARD`
- radiology: 1건 (`US`)
- mdro logs: 0

5. `17650289` (`P01` / Pneumonia, F)
- 배정: `SX-2F-902-1` (`SX-2F-902`, `2F`)
- 이동: `PLANNED`, reason=`신규 입원`, to=`SX-2F-901-3`
- plan item: 있음
- flags: pathogen=`respiratory_infection`, clinical=`cough,oxygen_support`
- sepsis: `[0.34, 0.45, 0.56]` (latest `MEDIUM`)
- isolation_type: `DROPLET`
- radiology: 1건 (`CXR`)
- mdro logs: 0

6. `18003081` (`G01` / Waterborne, M)
- 배정: `SX-3F-901-3` (`SX-3F-901`, `3F`)
- 이동: `WAITING`, reason=`격리 해제`, to_ward=`3F`, to_room/to_bed=`NULL`
- plan item: 없음
- flags: pathogen=`gastrointestinal_source`, clinical=`diarrhea,dehydration_risk`
- sepsis: `[0.25, 0.34, 0.43]` (latest `MEDIUM`)
- isolation_type: `CONTACT`
- radiology: 1건 (`CT`)
- mdro logs: 0

7. `18294629` (`M03` / MDRO, M)
- 배정: `SX-5F-902-1` (`SX-5F-902`, `5F`)
- 이동: `NEEDS_EXCEPTION`, reason=`격리`, priority=`urgent`, to_room/to_bed=`NULL`
- plan item: 없음
- flags: pathogen=`cre,contact_precaution`, clinical=`isolation_required,cohort_consideration`
- sepsis: `[0.66, 0.79, 0.88]` (latest `CRITICAL`)
- isolation_type: `CONTACT`
- radiology: 2건 (`CXR` 기본 + 악화 follow-up)
- mdro logs: 2 (`suspected`, `confirmed`, `CRE`)

8. `19096027` (`G01` / Waterborne, M)
- 배정: `SX-3F-901-4` (`SX-3F-901`, `3F`)
- 이동: `WAITING`, reason=`격리 해제`, to_ward=`3F`, to_room/to_bed=`NULL`
- plan item: 없음
- flags: pathogen=`gastrointestinal_source`, clinical=`diarrhea,dehydration_risk`
- sepsis: `[0.25, 0.34, 0.43]` (latest `MEDIUM`)
- isolation_type: `CONTACT`
- radiology: 1건 (`CT`)
- mdro logs: 0

9. `19440935` (`M01` / MDRO, M)
- 배정: `SX-5F-902-2` (`SX-5F-902`, `5F`)
- 이동: `WAITING`, reason=`격리`, to_ward=`5F`, to_room/to_bed=`NULL`
- plan item: 없음
- flags: pathogen=`mrsa,contact_precaution`, clinical=`isolation_required,cohort_consideration`
- sepsis: `[0.54, 0.66, 0.77]` (latest `HIGH`)
- isolation_type: `CONTACT`
- radiology: 1건 (`CXR`, severe)
- mdro logs: 1 (`suspected`, `MRSA`)

10. `19548143` (`P05` / Pneumonia, F)
- 배정: `SX-2F-902-2` (`SX-2F-902`, `2F`)
- 이동: `PLANNED`, reason=`신규 입원`, to=`SX-2F-901-4`
- plan item: 있음
- flags: pathogen=`respiratory_infection`, clinical=`cough,oxygen_support`
- sepsis: `[0.34, 0.45, 0.56]` (latest `MEDIUM`)
- isolation_type: `DROPLET`
- radiology: 1건 (`CXR`)
- mdro logs: 0

11. `T01` (`T01` / Tick-borne, M)
- 배정: `SX-5F-903-1` (`SX-5F-903`, `5F`)
- 이동: `WAITING`, reason=`격리`, to_ward=`5F`, to_room/to_bed=`NULL`
- plan item: 없음
- flags: pathogen=`sfts_suspected,tick_borne_pattern`, clinical=`high_fever,thrombocytopenia`
- sepsis: `[0.46, 0.60, 0.74]` (latest `HIGH`)
- isolation_type: `DROPLET`
- radiology: 1건 (`CXR`)
- mdro logs: 0

12. `T02` (`T02` / Tick-borne, F)
- 배정: `SX-5F-904-1` (`SX-5F-904`, `5F`)
- 이동: `PLANNED`, reason=`격리`, to=`SX-5F-904-2`
- plan item: 있음
- flags: pathogen=`sfts_suspected,tick_borne_pattern`, clinical=`high_fever,thrombocytopenia`
- sepsis: `[0.46, 0.60, 0.74]` (latest `HIGH`)
- isolation_type: `DROPLET`
- radiology: 1건 (`CXR`)
- mdro logs: 0

13. `T03` (`T03` / Tick-borne, M)
- 배정: `SX-5F-903-2` (`SX-5F-903`, `5F`)
- 이동: `NEEDS_EXCEPTION`, reason=`격리`, priority=`urgent`, to_room/to_bed=`NULL`
- plan item: 없음
- flags: pathogen=`sfts_suspected,tick_borne_pattern`, clinical=`high_fever,thrombocytopenia,mental_change,icu_consideration`
- sepsis: `[0.72, 0.84, 0.91]` (latest `CRITICAL`)
- isolation_type: `DROPLET`
- radiology: 2건 (`CXR` 기본 + 악화 follow-up)
- mdro logs: 0

## 전체 예상 건수(13명 기준)
- `transfer_cases`: 13
- `bed_assignment_items`: 5
- `radiology_reports`: 15
- `sepsis_risk_scores`: 39
- `alerts`: 13
- `patient_status`: 13
- `bed_status`: `SX-*` 병상 21개 기준 21건
- `mdro_checklist_logs`: 4
