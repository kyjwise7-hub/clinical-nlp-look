-- ============================================================
-- Step 7: Alert Engine Operational Checks
-- ============================================================

-- 0) Pre-run checks
SELECT COUNT(*) AS trajectory_events_cnt
FROM trajectory_events;

SELECT COUNT(*) AS alerts_total_cnt
FROM alerts;

SELECT COUNT(*) AS sx_alert_cnt
FROM alerts
WHERE message LIKE '[SX]%' OR trigger_json LIKE '%SX_EXT%';


-- 1) Engine output distribution
SELECT severity, alert_type, COUNT(*) AS cnt
FROM alerts
WHERE message IN (
  'MDRO 확진 환자에게 격리 미적용',
  '배양 채취 - 결과 대기 중',
  '감염 지표 변화 감지',
  '운영 조치 필요 이벤트',
  'Sepsis 조기위험: 게이트 충족',
  'Sepsis 위험 상승(게이트 미충족)',
  '의미 있는 변화 없음(직전 슬롯 대비 안정)'
)
GROUP BY severity, alert_type
ORDER BY severity, alert_type;


-- 2) Engine output total
SELECT COUNT(*) AS engine_alert_cnt
FROM alerts
WHERE message IN (
  'MDRO 확진 환자에게 격리 미적용',
  '배양 채취 - 결과 대기 중',
  '감염 지표 변화 감지',
  '운영 조치 필요 이벤트',
  'Sepsis 조기위험: 게이트 충족',
  'Sepsis 위험 상승(게이트 미충족)',
  '의미 있는 변화 없음(직전 슬롯 대비 안정)'
);


-- 3) Recently inserted engine alerts (adjust interval if needed)
SELECT
  alert_id,
  patient_id,
  alert_type,
  severity,
  JSON_VALUE(trigger_json, '$.hd' RETURNING NUMBER NULL ON ERROR) AS hd,
  JSON_VALUE(trigger_json, '$.d_number' RETURNING NUMBER NULL ON ERROR) AS d_number,
  created_at
FROM alerts
WHERE created_at >= SYSTIMESTAMP - INTERVAL '30' MINUTE
  AND message IN (
    'MDRO 확진 환자에게 격리 미적용',
    '배양 채취 - 결과 대기 중',
    '감염 지표 변화 감지',
    '운영 조치 필요 이벤트',
    'Sepsis 조기위험: 게이트 충족',
    'Sepsis 위험 상승(게이트 미충족)',
    '의미 있는 변화 없음(직전 슬롯 대비 안정)'
  )
ORDER BY created_at DESC, alert_id DESC;


-- 4) Guardrail: SX should stay zero
SELECT COUNT(*) AS sx_alert_cnt
FROM alerts
WHERE message LIKE '[SX]%' OR trigger_json LIKE '%SX_EXT%';


-- 5) Rollback helper (uncomment only when needed)
-- DELETE FROM alerts
-- WHERE message IN (
--   'MDRO 확진 환자에게 격리 미적용',
--   '배양 채취 - 결과 대기 중',
--   '감염 지표 변화 감지',
--   '운영 조치 필요 이벤트',
--   'Sepsis 조기위험: 게이트 충족',
--   'Sepsis 위험 상승(게이트 미충족)',
--   '의미 있는 변화 없음(직전 슬롯 대비 안정)'
-- );
-- COMMIT;
