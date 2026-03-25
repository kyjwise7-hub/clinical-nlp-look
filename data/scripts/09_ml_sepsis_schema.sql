-- ============================================================
-- 09_ml_sepsis_schema.sql
-- Sepsis ML 전용 저장소 + 호환 뷰
-- 실행: 수동(SQL 클라이언트)
-- ============================================================

-- 1) 신규 테이블
CREATE TABLE ml_sepsis_scores (
    score_id                  NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id              NUMBER        NOT NULL,
    prediction_datetime       TIMESTAMP     NOT NULL,
    hd                        NUMBER,
    d_number                  NUMBER        NOT NULL,
    shift                     VARCHAR2(10)  NOT NULL,
    risk_score                NUMBER(6,5),
    risk_level                VARCHAR2(10)  NOT NULL,
    contributing_factors_json CLOB,
    recommendations_json      CLOB,
    feature_snapshot_json     CLOB,
    model_name                VARCHAR2(100) DEFAULT 'xgb',
    model_version             VARCHAR2(100) NOT NULL,
    source_tag                VARCHAR2(50)  DEFAULT 'ML_BACKFILL',
    created_at                TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_ml_sepsis_admission
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id),
    CONSTRAINT chk_ml_sepsis_shift
        CHECK (shift IN ('Day', 'Evening', 'Night')),
    CONSTRAINT chk_ml_sepsis_level
        CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT uq_ml_sepsis_point
        UNIQUE (admission_id, d_number, shift, model_version)
);

-- 2) 인덱스
CREATE INDEX idx_ml_sepsis_admission_dt
    ON ml_sepsis_scores(admission_id, prediction_datetime DESC);

CREATE INDEX idx_ml_sepsis_demo
    ON ml_sepsis_scores(admission_id, d_number, shift);

CREATE INDEX idx_ml_sepsis_model
    ON ml_sepsis_scores(model_version);

-- 3) 호환 뷰
-- 기존 sepsis_risk_scores 계약 컬럼 유지
CREATE OR REPLACE VIEW vw_sepsis_risk_scores_compat AS
SELECT
    admission_id,
    prediction_datetime,
    risk_score,
    risk_level,
    contributing_factors_json,
    recommendations_json,
    hd,
    d_number,
    created_at
FROM (
    SELECT
        m.*,
        ROW_NUMBER() OVER (
            PARTITION BY m.admission_id, m.d_number, m.shift
            ORDER BY m.created_at DESC, m.score_id DESC
        ) AS rn
    FROM ml_sepsis_scores m
)
WHERE rn = 1;

COMMENT ON TABLE ml_sepsis_scores IS 'Sepsis ML 백필/배치 결과 저장소';
COMMENT ON COLUMN ml_sepsis_scores.shift IS 'Day / Evening / Night';
COMMENT ON COLUMN ml_sepsis_scores.feature_snapshot_json IS '추론 입력 피처 스냅샷(JSON)';
COMMENT ON COLUMN ml_sepsis_scores.source_tag IS 'ML_BACKFILL / FLASK_FALLBACK 등 소스 태그';

COMMIT;


DROP TABLE sepsis_risk_scores CASCADE CONSTRAINTS;
COMMIT;
