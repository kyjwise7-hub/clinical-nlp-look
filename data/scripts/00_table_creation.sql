-- ============================================================
-- patients
-- ============================================================
CREATE TABLE patients (
    patient_id        VARCHAR2(20)   PRIMARY KEY,
    name              VARCHAR2(100)  NOT NULL,
    age               NUMBER         NOT NULL,
    gender            VARCHAR2(1)    NOT NULL,
    date_of_birth     DATE,
    infection_code    VARCHAR2(50),
    created_at        TIMESTAMP      DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE patients IS '환자 기본정보';
COMMENT ON COLUMN patients.patient_id IS '환자 ID';
COMMENT ON COLUMN patients.name IS '환자명';
COMMENT ON COLUMN patients.age IS '나이';
COMMENT ON COLUMN patients.gender IS 'M / F';
COMMENT ON COLUMN patients.date_of_birth IS '생년월일';
COMMENT ON COLUMN patients.infection_code IS '주요 감염 유형 (Pneumonia, UTI 등)';
COMMENT ON COLUMN patients.created_at IS '생성일시';


-- ============================================================
-- admissions
-- ============================================================
CREATE TABLE admissions (
    admission_id       NUMBER         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id         VARCHAR2(20)   NOT NULL,
    admit_date         TIMESTAMP      NOT NULL,
    sim_admit_date     DATE,
    discharge_date     TIMESTAMP,
    status             VARCHAR2(20)   NOT NULL,
    current_hd         NUMBER,
    primary_diagnosis  VARCHAR2(200),
    alert_level        VARCHAR2(20),
    attending_doctor   VARCHAR2(50),
    attending_nurse    VARCHAR2(50),
    created_at         TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_admissions_patient 
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id)
);

CREATE INDEX idx_admissions_patient ON admissions(patient_id);
CREATE INDEX idx_admissions_status ON admissions(status);

COMMENT ON TABLE admissions IS '입원 정보';
COMMENT ON COLUMN admissions.admission_id IS '입원 ID (자동 생성)';
COMMENT ON COLUMN admissions.patient_id IS '환자 ID (FK)';
COMMENT ON COLUMN admissions.admit_date IS '입원일시 (원본)';
COMMENT ON COLUMN admissions.sim_admit_date IS '시뮬레이션용 입원일 (FE 표시용)';
COMMENT ON COLUMN admissions.discharge_date IS '퇴원일시';
COMMENT ON COLUMN admissions.status IS 'active / discharged / transferred';
COMMENT ON COLUMN admissions.current_hd IS 'Hospital Day (캐싱)';
COMMENT ON COLUMN admissions.primary_diagnosis IS '주진단명';
COMMENT ON COLUMN admissions.alert_level IS 'low / moderate / high / critical';
COMMENT ON COLUMN admissions.attending_doctor IS '담당의 (FK → users, 나중에 연결)';
COMMENT ON COLUMN admissions.attending_nurse IS '담당 간호사 (FK → users, 나중에 연결)';
COMMENT ON COLUMN admissions.created_at IS '생성일시';


-- ============================================================
-- nursing_notes
-- ============================================================
CREATE TABLE nursing_notes (
    note_id           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id      NUMBER NOT NULL,
    note_datetime     TIMESTAMP NOT NULL,
    note_type         VARCHAR2(20),
    subjective        CLOB,
    objective         CLOB,
    assessment        VARCHAR2(500),
    plan_action       CLOB,
    raw_text          CLOB,
    alert_level       VARCHAR2(20),
    temp              NUMBER(4,1),
    hr                NUMBER,
    rr                NUMBER,
    bp_sys            NUMBER,
    bp_dia            NUMBER,
    spo2              NUMBER,
    o2_device         VARCHAR2(50),
    o2_flow           VARCHAR2(20),
    intake            NUMBER,
    output            NUMBER,
    notify_md         NUMBER(1) DEFAULT 0,
    pain_nrs          NUMBER(2),
    hd                NUMBER,
    d_number          NUMBER,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_nursing_admission
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id),
    CONSTRAINT chk_nursing_pain_nrs
        CHECK (pain_nrs BETWEEN 0 AND 10)
);

CREATE INDEX idx_nursing_admission ON nursing_notes(admission_id);
CREATE INDEX idx_nursing_datetime ON nursing_notes(note_datetime);
CREATE INDEX idx_nursing_hd ON nursing_notes(hd, d_number);

COMMENT ON TABLE nursing_notes IS '간호기록';
COMMENT ON COLUMN nursing_notes.note_type IS 'PROGRESS, ADMISSION, TRANSFER';
COMMENT ON COLUMN nursing_notes.temp IS '체온';
COMMENT ON COLUMN nursing_notes.hr IS '심박수';
COMMENT ON COLUMN nursing_notes.rr IS '호흡수';
COMMENT ON COLUMN nursing_notes.bp_sys IS '수축기 혈압';
COMMENT ON COLUMN nursing_notes.bp_dia IS '이완기 혈압';
COMMENT ON COLUMN nursing_notes.spo2 IS '산소포화도';
COMMENT ON COLUMN nursing_notes.o2_device IS 'NC, Mask, HFNC 등';
COMMENT ON COLUMN nursing_notes.o2_flow IS '2L/min, 4L/min 등';
COMMENT ON COLUMN nursing_notes.notify_md IS '의사 호출 여부';
COMMENT ON COLUMN nursing_notes.pain_nrs IS '통증 NRS(0~10), objective/raw_text에서 추출';
COMMENT ON COLUMN nursing_notes.hd IS 'Hospital Day';
COMMENT ON COLUMN nursing_notes.d_number IS 'D-number (D0 기준)';



-- ============================================================
-- physician_notes
-- ============================================================
CREATE TABLE physician_notes (
    note_id           NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id      NUMBER NOT NULL,
    note_datetime     TIMESTAMP NOT NULL,
    note_type         VARCHAR2(20),
    raw_text          CLOB,
    subjective        CLOB,
    objective_json    CLOB,
    diagnosis         VARCHAR2(500),
    assessment_json   CLOB,
    plan              CLOB,
    problem_list_json CLOB,
    treatment_history CLOB,
    hd                NUMBER,
    d_number          NUMBER,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_physician_admission 
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id)
);

CREATE INDEX idx_physician_admission ON physician_notes(admission_id);
CREATE INDEX idx_physician_datetime ON physician_notes(note_datetime);
CREATE INDEX idx_physician_hd ON physician_notes(hd, d_number);

COMMENT ON TABLE physician_notes IS '의사 경과기록';
COMMENT ON COLUMN physician_notes.note_type IS 'PROGRESS, ADMISSION, CONSULT, DISCHARGE';
COMMENT ON COLUMN physician_notes.objective_json IS 'O) 부분 (JSON)';
COMMENT ON COLUMN physician_notes.assessment_json IS 'A) 평가 리스트 (JSON)';
COMMENT ON COLUMN physician_notes.problem_list_json IS '문제 목록 (JSON)';


-- ============================================================
-- lab_results
-- ============================================================
CREATE TABLE lab_results (
    result_id         NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id      NUMBER NOT NULL,
    result_datetime   TIMESTAMP NOT NULL,
    item_code         VARCHAR2(20) NOT NULL,
    item_name         VARCHAR2(100) NOT NULL,
    value             VARCHAR2(50),
    unit              VARCHAR2(20),
    reference_range   VARCHAR2(50),
    is_abnormal       NUMBER(1) DEFAULT 0,
    hd                NUMBER,
    d_number          NUMBER,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_lab_admission 
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id)
);

CREATE INDEX idx_lab_admission ON lab_results(admission_id);
CREATE INDEX idx_lab_datetime ON lab_results(result_datetime);
CREATE INDEX idx_lab_item ON lab_results(item_code);
CREATE INDEX idx_lab_hd ON lab_results(hd, d_number);

COMMENT ON TABLE lab_results IS '혈액검사 결과';
COMMENT ON COLUMN lab_results.item_code IS 'WBC, CRP, LACTATE 등';
COMMENT ON COLUMN lab_results.is_abnormal IS '이상치 여부';


-- ============================================================
-- microbiology_results
-- ============================================================
CREATE TABLE microbiology_results (
    result_id             NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id          NUMBER NOT NULL,
    specimen_type         VARCHAR2(50) NOT NULL,
    collection_datetime   TIMESTAMP NOT NULL,
    result_datetime       TIMESTAMP,
    result_status         VARCHAR2(20),
    gram_stain            VARCHAR2(500),
    organism              VARCHAR2(200),
    colony_count          VARCHAR2(100),
    is_mdro               NUMBER(1) DEFAULT 0,
    mdro_type             VARCHAR2(20),
    susceptibility_json   CLOB,
    status                VARCHAR2(20),
    comments              CLOB,
    raw_text              CLOB,
    hd                    NUMBER,
    d_number              NUMBER,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_micro_admission 
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id)
);

CREATE INDEX idx_micro_admission ON microbiology_results(admission_id);
CREATE INDEX idx_micro_collection ON microbiology_results(collection_datetime);
CREATE INDEX idx_micro_organism ON microbiology_results(organism);
CREATE INDEX idx_micro_mdro ON microbiology_results(is_mdro);
CREATE INDEX idx_micro_hd ON microbiology_results(hd, d_number);

COMMENT ON TABLE microbiology_results IS '배양/감수성 결과';
COMMENT ON COLUMN microbiology_results.specimen_type IS 'SPUTUM, BLOOD, URINE, STOOL 등';
COMMENT ON COLUMN microbiology_results.result_status IS 'PENDING, PRELIMINARY, FINAL';
COMMENT ON COLUMN microbiology_results.is_mdro IS '다제내성균 여부';
COMMENT ON COLUMN microbiology_results.mdro_type IS 'MRSA, VRE, CRE, C. difficile 등';


-- ============================================================
-- infection_diagnoses (정규화된 감염 진단 소스)
-- ============================================================
CREATE TABLE infection_diagnoses (
    diagnosis_id      NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id      NUMBER        NOT NULL,
    patient_id        VARCHAR2(20)  NOT NULL,
    diagnosis_code    VARCHAR2(50)  NOT NULL,
    diagnosis_name    VARCHAR2(200),
    diagnosis_group   VARCHAR2(30)  NOT NULL,
    status            VARCHAR2(20)  NOT NULL,
    confirmed_at      TIMESTAMP,
    confirmed_hd      NUMBER,
    confirmed_d_number NUMBER,
    confirmed_shift   VARCHAR2(10),
    source_type       VARCHAR2(30),
    source_ref_id     VARCHAR2(100),
    created_at        TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_infdiag_admission
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id),
    CONSTRAINT fk_infdiag_patient
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
    CONSTRAINT chk_infdiag_group
        CHECK (diagnosis_group IN ('RESP', 'GI', 'MDRO', 'UTI', 'TICK', 'OTHER')),
    CONSTRAINT chk_infdiag_status
        CHECK (status IN ('SUSPECTED', 'CONFIRMED', 'RULED_OUT')),
    CONSTRAINT chk_infdiag_shift
        CHECK (confirmed_shift IS NULL OR confirmed_shift IN ('DAY', 'EVENING', 'NIGHT'))
);

CREATE INDEX idx_infdiag_admission ON infection_diagnoses(admission_id);
CREATE INDEX idx_infdiag_patient ON infection_diagnoses(patient_id);
CREATE INDEX idx_infdiag_group_status ON infection_diagnoses(diagnosis_group, status);
CREATE INDEX idx_infdiag_confirmed_at ON infection_diagnoses(confirmed_at);
CREATE INDEX idx_infdiag_confirmed_slot ON infection_diagnoses(confirmed_d_number, confirmed_shift);

COMMENT ON TABLE infection_diagnoses IS '감염 진단 정규화 테이블 (운영 판정 소스)';
COMMENT ON COLUMN infection_diagnoses.diagnosis_code IS '예: MDRO_MRSA, RESP_PNEUMONIA';
COMMENT ON COLUMN infection_diagnoses.diagnosis_group IS 'RESP, GI, MDRO, UTI, TICK, OTHER';
COMMENT ON COLUMN infection_diagnoses.status IS 'SUSPECTED, CONFIRMED, RULED_OUT';
COMMENT ON COLUMN infection_diagnoses.confirmed_at IS '확진 시각 (미생물/판정 근거 기준)';
COMMENT ON COLUMN infection_diagnoses.confirmed_hd IS '확진 시점 HD';
COMMENT ON COLUMN infection_diagnoses.confirmed_d_number IS '확진 시점 D 번호';
COMMENT ON COLUMN infection_diagnoses.confirmed_shift IS '확진 시점 Shift (DAY/EVENING/NIGHT)';
COMMENT ON COLUMN infection_diagnoses.source_type IS 'MICROBIOLOGY, NLP, MANUAL 등';


-- ============================================================
-- wards
-- ============================================================
CREATE TABLE wards (
    ward_id           VARCHAR2(10)  PRIMARY KEY,
    ward_name         VARCHAR2(100) NOT NULL,
    floor             NUMBER,
    is_isolation_ward NUMBER(1)     DEFAULT 0,
    created_at        TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE wards IS '병동 정보';
COMMENT ON COLUMN wards.ward_id IS '병동 ID (2F, 3F, 5F)';
COMMENT ON COLUMN wards.is_isolation_ward IS '격리 병동 여부';


-- ============================================================
-- rooms
-- ============================================================
CREATE TABLE rooms (
    room_id              VARCHAR2(50) PRIMARY KEY,
    ward_id              VARCHAR2(10) NOT NULL,
    room_number          VARCHAR2(20) NOT NULL,
    room_type            VARCHAR2(10),
    capacity             NUMBER       NOT NULL,
    is_isolation         NUMBER(1)    DEFAULT 0,
    has_aiir             NUMBER(1)    DEFAULT 0,
    has_dedicated_toilet NUMBER(1)    DEFAULT 0,
    isolation_type       VARCHAR2(20),
    tier                 VARCHAR2(2),
    cohort_type          VARCHAR2(50),
    gender_type          VARCHAR2(1),
    needs_cleaning       NUMBER(1)    DEFAULT 0,
    created_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_rooms_ward FOREIGN KEY (ward_id) REFERENCES wards(ward_id)
);

COMMENT ON TABLE rooms IS '병실 정보';
COMMENT ON COLUMN rooms.room_type IS 'SINGLE, DOUBLE, QUAD';
COMMENT ON COLUMN rooms.has_aiir IS '음압실(AIIR) 여부';
COMMENT ON COLUMN rooms.has_dedicated_toilet IS '전용 화장실 여부';
COMMENT ON COLUMN rooms.isolation_type IS 'STANDARD, CONTACT, DROPLET, AIRBORNE';
COMMENT ON COLUMN rooms.tier IS '격리 등급: S, A, B';


-- ============================================================
-- beds
-- ============================================================
CREATE TABLE beds (
    bed_id     VARCHAR2(50) PRIMARY KEY,
    room_id    VARCHAR2(50) NOT NULL,
    bed_number VARCHAR2(10) NOT NULL,
    created_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_beds_room FOREIGN KEY (room_id) REFERENCES rooms(room_id)
);

COMMENT ON TABLE beds IS '병상 정보';

ALTER TABLE beds ADD (
  patient_id VARCHAR2(20) REFERENCES patients(patient_id),
  is_ghost NUMBER(1) DEFAULT 0
);


-- ============================================================
-- bed_assignment_plans
-- ============================================================
CREATE TABLE bed_assignment_plans (
    plan_id           NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_datetime     TIMESTAMP     NOT NULL,
    created_by        VARCHAR2(50),
    created_by_type   VARCHAR2(20),
    floor_scope       VARCHAR2(20),
    patient_count     NUMBER,
    status            VARCHAR2(20)  NOT NULL,
    algorithm_version VARCHAR2(20),
    confirmed_at      TIMESTAMP,
    cancelled_at      TIMESTAMP,
    created_at        TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE bed_assignment_plans IS '병상 배치안';
COMMENT ON COLUMN bed_assignment_plans.created_by_type IS 'auto, manual';
COMMENT ON COLUMN bed_assignment_plans.status IS 'DRAFT, CONFIRMED, CANCELLED';


-- ============================================================
-- bed_assignment_items
-- ============================================================
CREATE TABLE bed_assignment_items (
    item_id       NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    plan_id       NUMBER        NOT NULL,
    admission_id  NUMBER        NOT NULL,
    from_bed_id   VARCHAR2(50),
    to_bed_id     VARCHAR2(50)  NOT NULL,
    reason        VARCHAR2(200),
    infection_tag VARCHAR2(50),
    created_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_bai_plan      FOREIGN KEY (plan_id)      REFERENCES bed_assignment_plans(plan_id),
    CONSTRAINT fk_bai_admission FOREIGN KEY (admission_id)  REFERENCES admissions(admission_id),
    CONSTRAINT fk_bai_from_bed  FOREIGN KEY (from_bed_id)   REFERENCES beds(bed_id),
    CONSTRAINT fk_bai_to_bed    FOREIGN KEY (to_bed_id)     REFERENCES beds(bed_id)
);

COMMENT ON TABLE bed_assignment_items IS '배치안 상세 항목';


-- ============================================================
-- transfer_cases
-- ============================================================
CREATE TABLE transfer_cases (
    case_id          VARCHAR2(50)  PRIMARY KEY,
    patient_id       VARCHAR2(20)  NOT NULL,
    status           VARCHAR2(20)  NOT NULL,
    from_ward_id     VARCHAR2(10),
    from_room_id     VARCHAR2(50),
    to_ward_id       VARCHAR2(10),
    to_room_id       VARCHAR2(50),
    to_bed_id        VARCHAR2(50),
    reason           VARCHAR2(200) NOT NULL,
    priority         VARCHAR2(10)  DEFAULT 'normal',
    exception_reason VARCHAR2(500),
    infection_type   VARCHAR2(50),
    pathogen_flags   VARCHAR2(500),
    clinical_flags   VARCHAR2(500),
    plan_id          NUMBER,
    created_at       TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP,

    CONSTRAINT fk_tc_patient   FOREIGN KEY (patient_id)   REFERENCES patients(patient_id),
    CONSTRAINT fk_tc_from_ward FOREIGN KEY (from_ward_id) REFERENCES wards(ward_id),
    CONSTRAINT fk_tc_from_room FOREIGN KEY (from_room_id) REFERENCES rooms(room_id),
    CONSTRAINT fk_tc_to_ward   FOREIGN KEY (to_ward_id)   REFERENCES wards(ward_id),
    CONSTRAINT fk_tc_to_room   FOREIGN KEY (to_room_id)   REFERENCES rooms(room_id),
    CONSTRAINT fk_tc_to_bed    FOREIGN KEY (to_bed_id)    REFERENCES beds(bed_id),
    CONSTRAINT fk_tc_plan      FOREIGN KEY (plan_id)      REFERENCES bed_assignment_plans(plan_id)
);

CREATE INDEX idx_tc_patient ON transfer_cases(patient_id);
CREATE INDEX idx_tc_status  ON transfer_cases(status);

COMMENT ON TABLE transfer_cases IS '환자 이동/배치 대기 큐';
COMMENT ON COLUMN transfer_cases.status IS 'WAITING, PLANNED, COMMITTED, NEEDS_EXCEPTION';


-- ============================================================
-- radiology_reports
-- ============================================================
CREATE TABLE radiology_reports (
    report_id      NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id   NUMBER        NOT NULL,
    study_type     VARCHAR2(20)  NOT NULL,
    study_datetime TIMESTAMP     NOT NULL,
    technique      VARCHAR2(200),
    comparison     VARCHAR2(200),
    findings       CLOB,
    conclusion     CLOB,
    tags           VARCHAR2(500),
    severity_score VARCHAR2(20),
    hd             NUMBER,
    d_number       NUMBER,
    created_at     TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_radio_admission 
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id)
);

CREATE INDEX idx_radio_admission ON radiology_reports(admission_id);
CREATE INDEX idx_radio_datetime ON radiology_reports(study_datetime);
CREATE INDEX idx_radio_hd ON radiology_reports(hd, d_number);


-- ============================================================
-- trajectory_events (6B 산출물 반영)
-- ============================================================
CREATE TABLE trajectory_events (
    event_id             NUMBER         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id         NUMBER         NOT NULL,
    event_type           VARCHAR2(50)   NOT NULL,
    event_datetime       TIMESTAMP      NOT NULL,
    axis_type            VARCHAR2(30)   NOT NULL,
    priority_rank        NUMBER,
    render_text          VARCHAR2(500),
    evidence_text        VARCHAR2(500),
    severity             VARCHAR2(10),
    supporting_docs_json CLOB,
    hd                   NUMBER,
    d_number             NUMBER,
    shift                VARCHAR2(10),
    created_at           TIMESTAMP      DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_traj_admission
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id),
    CONSTRAINT chk_traj_axis CHECK (axis_type IN (
        'RESPIRATORY',
        'INFECTION_ACTIVITY',
        'CLINICAL_ACTION',
        'INFECTION_CONTROL',
        'SYMPTOM_SUBJECTIVE'
    ))
);

CREATE INDEX idx_traj_admission ON trajectory_events(admission_id);
CREATE INDEX idx_traj_datetime ON trajectory_events(event_datetime);
CREATE INDEX idx_traj_hd ON trajectory_events(hd, d_number);
CREATE INDEX idx_traj_type ON trajectory_events(event_type);

COMMENT ON TABLE trajectory_events IS 'Trajectory 이벤트 (Phase 6B 산출물)';
COMMENT ON COLUMN trajectory_events.priority_rank IS '규칙 우선순위 (1이 가장 높음)';
COMMENT ON COLUMN trajectory_events.evidence_text IS '변화 근거 텍스트 (예: temp_value: 37.5 → 38.0)';
COMMENT ON COLUMN trajectory_events.shift IS 'Day / Evening / Night';


-- ============================================================
-- sepsis_risk_scores
-- ============================================================
CREATE TABLE sepsis_risk_scores (
    score_id                  NUMBER       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id              NUMBER       NOT NULL,
    prediction_datetime       TIMESTAMP    NOT NULL,
    risk_score                NUMBER(4,3),
    risk_level                VARCHAR2(10),
    contributing_factors_json CLOB,
    recommendations_json     CLOB,
    hd                       NUMBER,
    d_number                 NUMBER,
    created_at               TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_sepsis_admission
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id)
);

CREATE INDEX idx_sepsis_admission ON sepsis_risk_scores(admission_id);
CREATE INDEX idx_sepsis_datetime ON sepsis_risk_scores(prediction_datetime);
CREATE INDEX idx_sepsis_hd ON sepsis_risk_scores(hd, d_number);


-- ============================================================
-- saved_drafts  (의무기록 자동초안 저장)
-- ============================================================
CREATE TABLE saved_drafts (
    draft_id                VARCHAR2(50)  PRIMARY KEY,
    doc_type                VARCHAR2(20)  NOT NULL,
    patient_id              VARCHAR2(20)  NOT NULL,
    patient_name            VARCHAR2(100) DEFAULT '',
    status                  VARCHAR2(20)  DEFAULT 'draft' NOT NULL,
    sections_json           CLOB          DEFAULT '[]',
    evidence_json           CLOB          DEFAULT '[]',
    validation_issues_json  CLOB          DEFAULT '[]',
    created_at              TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_sd_patient FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
    CONSTRAINT chk_sd_status CHECK (status IN ('draft','validated','exported'))
);

CREATE INDEX idx_sd_patient ON saved_drafts(patient_id);
CREATE INDEX idx_sd_updated ON saved_drafts(updated_at);

COMMENT ON TABLE saved_drafts IS '의무기록 자동초안 저장';
COMMENT ON COLUMN saved_drafts.draft_id IS 'UUID';
COMMENT ON COLUMN saved_drafts.doc_type IS 'referral, return, summary, discharge, admission, certificate';
COMMENT ON COLUMN saved_drafts.status IS 'draft / validated / exported';
COMMENT ON COLUMN saved_drafts.sections_json IS '섹션 배열 (JSON)';
COMMENT ON COLUMN saved_drafts.evidence_json IS '근거 배열 (JSON)';
COMMENT ON COLUMN saved_drafts.validation_issues_json IS '검증 이슈 배열 (JSON)';


-- ============================================================
-- users (담당의/간호사)
-- ============================================================
CREATE TABLE users (
    user_id       VARCHAR2(50)  PRIMARY KEY,
    username      VARCHAR2(100) NOT NULL UNIQUE,
    name          VARCHAR2(100) NOT NULL,
    role          VARCHAR2(20)  NOT NULL,
    ward_id       VARCHAR2(10),
    email         VARCHAR2(100),
    is_active     NUMBER(1)     DEFAULT 1,
    created_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_users_ward FOREIGN KEY (ward_id) REFERENCES wards(ward_id),
    CONSTRAINT chk_users_role CHECK (role IN ('doctor', 'nurse', 'admin', 'infection_control'))
);

COMMENT ON TABLE users IS '사용자 (의사, 간호사, 관리자)';
COMMENT ON COLUMN users.role IS 'doctor, nurse, admin, infection_control';


-- ============================================================
-- nlp_documents (NLP 처리된 문서 메타)
-- ============================================================
CREATE TABLE nlp_documents (
    document_id              NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id             NUMBER        NOT NULL,
    patient_id               VARCHAR2(20)  NOT NULL,
    document_type            VARCHAR2(30)  NOT NULL,
    source_table             VARCHAR2(50)  NOT NULL,
    source_id                NUMBER        NOT NULL,
    doc_datetime             TIMESTAMP     NOT NULL,
    hd                       NUMBER,
    d_number                 NUMBER,
    context_tags_json        CLOB,
    extraction_version       VARCHAR2(20),
    total_slots              NUMBER,
    mandatory_missing_json   CLOB,
    validation_warnings_json CLOB,
    created_at               TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_nlpdoc_admission FOREIGN KEY (admission_id) REFERENCES admissions(admission_id),
    CONSTRAINT fk_nlpdoc_patient   FOREIGN KEY (patient_id)   REFERENCES patients(patient_id)
);

CREATE INDEX idx_nlpdoc_admission ON nlp_documents(admission_id);
CREATE INDEX idx_nlpdoc_patient ON nlp_documents(patient_id);
CREATE INDEX idx_nlpdoc_type ON nlp_documents(document_type);

COMMENT ON TABLE nlp_documents IS 'NLP 처리된 문서 메타정보';
COMMENT ON COLUMN nlp_documents.document_type IS 'nursing_note, physician_note, lab_result, radiology, microbiology';
COMMENT ON COLUMN nlp_documents.source_table IS '원본 테이블명 (nursing_notes, physician_notes 등)';
COMMENT ON COLUMN nlp_documents.source_id IS '원본 테이블의 PK (note_id, result_id 등)';


-- ============================================================
-- tagged_slots (추출된 슬롯)
-- ============================================================
CREATE TABLE tagged_slots (
    slot_id           NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id       NUMBER        NOT NULL,
    slot_name         VARCHAR2(100) NOT NULL,
    slot_value        VARCHAR2(500),
    slot_value_type   VARCHAR2(20),
    extraction_method VARCHAR2(30),
    confidence        NUMBER(3,2),
    evidence_text     VARCHAR2(1000),
    created_at        TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_slot_document FOREIGN KEY (document_id) REFERENCES nlp_documents(document_id)
);

CREATE INDEX idx_slot_document ON tagged_slots(document_id);
CREATE INDEX idx_slot_name ON tagged_slots(slot_name);

COMMENT ON TABLE tagged_slots IS 'NLP 추출 슬롯';
COMMENT ON COLUMN tagged_slots.extraction_method IS 'regex, dictionary, structured, ner, regex_inferred, inferred';


-- ============================================================
-- evidence_spans (근거 구간)
-- ============================================================
CREATE TABLE evidence_spans (
    span_id     NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slot_id     NUMBER        NOT NULL,
    document_id NUMBER        NOT NULL,
    slot_name   VARCHAR2(100) NOT NULL,
    text        VARCHAR2(1000),
    confidence  NUMBER(3,2),
    method      VARCHAR2(30),
    created_at  TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_span_slot     FOREIGN KEY (slot_id)     REFERENCES tagged_slots(slot_id),
    CONSTRAINT fk_span_document FOREIGN KEY (document_id) REFERENCES nlp_documents(document_id)
);

CREATE INDEX idx_span_slot ON evidence_spans(slot_id);
CREATE INDEX idx_span_document ON evidence_spans(document_id);

COMMENT ON TABLE evidence_spans IS 'NLP 슬롯 근거 구간';


-- ============================================================
-- axis_snapshots (6A 산출물 반영)
-- ============================================================
CREATE TABLE axis_snapshots (
    snapshot_id           NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id          NUMBER        NOT NULL,
    axis_type             VARCHAR2(30)  NOT NULL,
    snapshot_datetime     TIMESTAMP     NOT NULL,
    shift                 VARCHAR2(10),
    trend                 VARCHAR2(20),
    snapshot_json         CLOB,
    supplementary_json    CLOB,
    source_docs_json      CLOB,
    hd                    NUMBER,
    d_number              NUMBER,
    created_at            TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_axis_admission FOREIGN KEY (admission_id) REFERENCES admissions(admission_id),
    CONSTRAINT chk_axis_type CHECK (axis_type IN (
        'RESPIRATORY',
        'INFECTION_ACTIVITY',
        'CLINICAL_ACTION',
        'INFECTION_CONTROL',
        'SYMPTOM_SUBJECTIVE',
        'SUPPLEMENTARY'
    ))
);

CREATE INDEX idx_axis_admission ON axis_snapshots(admission_id);
CREATE INDEX idx_axis_type ON axis_snapshots(axis_type);
CREATE INDEX idx_axis_datetime ON axis_snapshots(snapshot_datetime);
CREATE INDEX idx_axis_hd ON axis_snapshots(hd, d_number);

COMMENT ON TABLE axis_snapshots IS 'Trajectory 축별 스냅샷 (Phase 6A 산출물)';
COMMENT ON COLUMN axis_snapshots.axis_type IS 'RESPIRATORY, INFECTION_ACTIVITY, CLINICAL_ACTION, INFECTION_CONTROL, SYMPTOM_SUBJECTIVE, SUPPLEMENTARY';
COMMENT ON COLUMN axis_snapshots.shift IS 'Day(06-14) / Evening(14-22) / Night(22-06)';
COMMENT ON COLUMN axis_snapshots.trend IS 'stable, worsening, improving';
COMMENT ON COLUMN axis_snapshots.snapshot_json IS '축별 슬롯 key-value (JSON)';
COMMENT ON COLUMN axis_snapshots.supplementary_json IS '보조 바이탈 (JSON)';
COMMENT ON COLUMN axis_snapshots.source_docs_json IS '근거 문서 ID 배열 (JSON)';


-- ============================================================
-- alerts (알림)
-- ============================================================
CREATE TABLE alerts (
    alert_id            NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    admission_id        NUMBER,
    patient_id          VARCHAR2(20),
    alert_type          VARCHAR2(30)  NOT NULL,
    severity            VARCHAR2(10)  NOT NULL,
    is_critical         NUMBER(1)     DEFAULT 0,
    message             VARCHAR2(500),
    trigger_json        CLOB,
    evidence_snippet    VARCHAR2(1000),
    recommended_cta_json CLOB,
    status              VARCHAR2(20)  DEFAULT 'ACTIVE',
    acknowledged_by     VARCHAR2(50),
    acknowledged_at     TIMESTAMP,
    resolved_at         TIMESTAMP,
    created_at          TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_alert_admission FOREIGN KEY (admission_id)    REFERENCES admissions(admission_id),
    CONSTRAINT fk_alert_patient   FOREIGN KEY (patient_id)      REFERENCES patients(patient_id),
    CONSTRAINT fk_alert_ack_user  FOREIGN KEY (acknowledged_by) REFERENCES users(user_id),
    CONSTRAINT chk_alert_type     CHECK (alert_type IN ('ISOLATION', 'DETERIORATION', 'PENDING_RESULT', 'CARE_GAP', 'CLUSTER', 'PLAN_CREATED', 'EXCEPTION_NEEDED', 'SEPSIS', 'NO_MEANINGFUL_CHANGE')),
    CONSTRAINT chk_alert_severity CHECK (severity IN ('INFO', 'ACTION', 'CRITICAL')),
    CONSTRAINT chk_alert_status   CHECK (status IN ('ACTIVE', 'ACKNOWLEDGED', 'RESOLVED', 'DISMISSED'))
);

CREATE INDEX idx_alert_admission ON alerts(admission_id);
CREATE INDEX idx_alert_patient ON alerts(patient_id);
CREATE INDEX idx_alert_status ON alerts(status);
CREATE INDEX idx_alert_type ON alerts(alert_type);

COMMENT ON TABLE alerts IS '알림 (임상 + 배치 관련)';
COMMENT ON COLUMN alerts.alert_type IS 'ISOLATION, DETERIORATION, PENDING_RESULT, CARE_GAP, CLUSTER, PLAN_CREATED, EXCEPTION_NEEDED, SEPSIS, NO_MEANINGFUL_CHANGE';


-- ============================================================
-- patient_status (환자 현재 상태)
-- ============================================================
CREATE TABLE patient_status (
    admission_id          NUMBER        PRIMARY KEY,
    patient_id            VARCHAR2(20)  NOT NULL,
    current_bed_id        VARCHAR2(50),
    ward_id               VARCHAR2(10),
    isolation_required    NUMBER(1)     DEFAULT 0,
    isolation_type        VARCHAR2(20),
    infection_tags_json   CLOB,
    pathogen_flags_json   CLOB,
    clinical_flags_json   CLOB,
    risk_level            VARCHAR2(10),
    last_updated_at       TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_ps_admission FOREIGN KEY (admission_id)   REFERENCES admissions(admission_id),
    CONSTRAINT fk_ps_patient   FOREIGN KEY (patient_id)     REFERENCES patients(patient_id),
    CONSTRAINT fk_ps_bed       FOREIGN KEY (current_bed_id) REFERENCES beds(bed_id),
    CONSTRAINT fk_ps_ward      FOREIGN KEY (ward_id)        REFERENCES wards(ward_id),
    CONSTRAINT chk_ps_isolation CHECK (isolation_type IN ('STANDARD', 'CONTACT', 'DROPLET', 'AIRBORNE')),
    CONSTRAINT chk_ps_risk      CHECK (risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'))
);

CREATE INDEX idx_ps_patient ON patient_status(patient_id);
CREATE INDEX idx_ps_ward ON patient_status(ward_id);
CREATE INDEX idx_ps_bed ON patient_status(current_bed_id);

COMMENT ON TABLE patient_status IS '환자 현재 상태 (실시간 스냅샷)';
COMMENT ON COLUMN patient_status.pathogen_flags_json IS '["mrsa", "vre", "cre"] 등';
COMMENT ON COLUMN patient_status.clinical_flags_json IS '["severe_cough", "diarrhea_profuse"] 등';


-- ============================================================
-- bed_status (병상 현재 상태)
-- ============================================================
CREATE TABLE bed_status (
    bed_id               VARCHAR2(50) PRIMARY KEY,
    status               VARCHAR2(20) DEFAULT 'AVAILABLE',
    current_admission_id NUMBER,
    isolation_type       VARCHAR2(20),
    needs_cleaning       NUMBER(1)    DEFAULT 0,
    last_updated_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_bs_bed       FOREIGN KEY (bed_id)               REFERENCES beds(bed_id),
    CONSTRAINT fk_bs_admission FOREIGN KEY (current_admission_id) REFERENCES admissions(admission_id),
    CONSTRAINT chk_bs_status   CHECK (status IN ('AVAILABLE', 'OCCUPIED', 'CLEANING', 'RESERVED'))
);

CREATE INDEX idx_bs_status ON bed_status(status);
CREATE INDEX idx_bs_admission ON bed_status(current_admission_id);

COMMENT ON TABLE bed_status IS '병상 현재 상태';


-- ============================================================
-- mdro_checklist_logs (MDRO 체크리스트)
-- ============================================================
CREATE TABLE mdro_checklist_logs (
    log_id            NUMBER        GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id        VARCHAR2(20)  NOT NULL,
    patient_name      VARCHAR2(100),
    stage             VARCHAR2(20)  NOT NULL,
    mdro_type         VARCHAR2(20),
    created_by        VARCHAR2(50),
    completed         NUMBER(1)     DEFAULT 0,
    notes             CLOB,
    checklist_payload CLOB,
    created_at        TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_mdro_patient FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
    CONSTRAINT fk_mdro_user    FOREIGN KEY (created_by) REFERENCES users(user_id),
    CONSTRAINT chk_mdro_stage  CHECK (stage IN ('suspected', 'confirmed'))
);

CREATE INDEX idx_mdro_patient ON mdro_checklist_logs(patient_id);
CREATE INDEX idx_mdro_created ON mdro_checklist_logs(created_at);

COMMENT ON TABLE mdro_checklist_logs IS 'MDRO 체크리스트 로그';


-- ============================================================
-- prescriptions (환자별 처방)
-- ============================================================
CREATE TABLE prescriptions (
    prescription_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    patient_id      VARCHAR2(20) NOT NULL,
    admission_id    NUMBER       NOT NULL,
    starttime       DATE         NOT NULL,
    drug            VARCHAR2(300) NOT NULL,
    prod_strength   VARCHAR2(200) NOT NULL,
    route           VARCHAR2(80)  NOT NULL,
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,

    CONSTRAINT fk_presc_patient
        FOREIGN KEY (patient_id) REFERENCES patients(patient_id),
    CONSTRAINT fk_presc_admission
        FOREIGN KEY (admission_id) REFERENCES admissions(admission_id),

    -- 완전 동일 row 중복 방지
    CONSTRAINT uq_presc_row
        UNIQUE (patient_id, admission_id, starttime, drug, prod_strength, route)
);

CREATE INDEX idx_presc_patient   ON prescriptions(patient_id);
CREATE INDEX idx_presc_admission ON prescriptions(admission_id);
CREATE INDEX idx_presc_starttime ON prescriptions(starttime);
