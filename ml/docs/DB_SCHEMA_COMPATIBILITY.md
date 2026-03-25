# DB Schema Compatibility Check (Sepsis Integration)

This checklist is for the next step: wiring `/patients/[id]` Sepsis tab to BE/DB.

## Current expectation

No schema change is required to start integration if these fields already exist.

### `sepsis_risk_scores`

- `risk_score`
- `risk_level`
- `contributing_factors_json`
- `prediction_datetime`
- `hd`
- `d_number`

### `trajectory_events`

- `severity`
- `event_datetime`
- `axis_type`
- `event_type`
- `shift`

## Verification SQL

```sql
SELECT table_name, column_name, data_type
FROM user_tab_columns
WHERE table_name IN ('SEPSIS_RISK_SCORES', 'TRAJECTORY_EVENTS')
ORDER BY table_name, column_id;
```

```sql
SELECT constraint_name, table_name, status, search_condition
FROM user_constraints
WHERE table_name IN ('SEPSIS_RISK_SCORES', 'TRAJECTORY_EVENTS')
  AND constraint_type = 'C'
ORDER BY table_name, constraint_name;
```

## Decision rule

- If all required columns are present: proceed with BE route integration.
- If missing columns are found: create a separate minimal ALTER script before integration.
