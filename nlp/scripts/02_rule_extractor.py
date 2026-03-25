"""
INFECT-GUARD Phase 2: 규칙 기반 슬롯 추출 (raw_text 전용)
==========================================================
입력: nlp/data/parsed_documents.jsonl
설정: nlp/specs/dictionary.yaml, nlp/specs/slot_definition.yaml, nlp/specs/axis_spec.yml
출력: nlp/data/tagged_slots_v4_1.jsonl

실행 방법:
    python scripts/02_rule_extractor.py
    python scripts/02_rule_extractor.py \
      --dict nlp/specs/dictionary.yaml \
      --slot-def nlp/specs/slot_definition.yaml \
      --axis-spec nlp/specs/axis_spec.yml

처리 구조:
    raw_text 정규식/사전 추출 → confidence=0.85~0.95
    NER 모델 (선택)          → confidence=모델 출력값 사용
    Context Tagging           → 모든 슬롯에 부정/불확실/계획/시제 태그 적용
    Slot Validation           → slot_definition.yaml 기반 검증 (타입/범위/허용값)
    Axis Filter               → axis_spec.yml enabled=false 축 슬롯 제거

    참고: 대부분 raw_text 기반. nursing_note의 notify_mentioned는 notify_md(구조화 필드) 사용.
"""

import json
import re
import os
import argparse
from typing import Any, Optional
from pathlib import Path

# NER은 04_ner_extractor.py에서 별도 처리
extract_from_ner = None
load_ner_predictions = None

SCRIPT_DIR = Path(__file__).resolve().parent
NLP_ROOT = SCRIPT_DIR.parent

DEFAULT_INPUT_PATH = str(NLP_ROOT / "data" / "parsed_documents.jsonl")
DEFAULT_OUTPUT_PATH = str(NLP_ROOT / "data" / "tagged_slots_v4_1.jsonl")
DEFAULT_DICT_PATH = str(NLP_ROOT / "specs" / "dictionary.yaml")
DEFAULT_SLOT_DEF_PATH = str(NLP_ROOT / "specs" / "slot_definition.yaml")
DEFAULT_AXIS_SPEC_PATH = str(NLP_ROOT / "specs" / "axis_spec.yml")


# ============================================================
# 1. Dictionary 로더 (YAML 대신 내장 — yaml 없는 환경 대응)
# ============================================================

def load_dictionary(path: Optional[str] = None) -> dict:
    """
    specs/dictionary_v1_2.yaml을 로드.
    yaml 모듈이 없으면 내장 사전 사용.
    """
    if path and os.path.exists(path):
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except ImportError:
            print("⚠ pyyaml 미설치 — 내장 사전 사용")

    return _builtin_dictionary()


def _builtin_dictionary() -> dict:
    """dictionary_v1_2.yaml의 핵심 내용을 내장"""
    return {
        "common_context": {
            "negation": {
                "en": ["no", "not", "without", "denies", "negative", "absent", "none"],
                "kr": ["없음", "아님", "부인", "음성", "(-)"],
                "patterns": [
                    r"(?i)no\s+(fever|cough|dyspnea|rash|diarrhea|vomiting|edema)",
                    r"(발열|기침|호흡곤란|설사|구토|부종)\s*없",
                    r"(?i)(deny|denied|denies)\s+\w+",
                ],
            },
            "uncertainty": {
                "en": ["possible", "probable", "suspect", "concern for", "rule out", "r/o", "likely"],
                "kr": ["의심", "가능성", "배제 필요", "추정"],
                "patterns": [
                    r"(?i)(possible|probable|r/o|rule\s*out|suspect|likely)",
                    r"(의심|가능성|추정|배제)",
                ],
            },
            "plan": {
                "en": ["plan", "planned", "recommend", "will", "consider", "pending"],
                "kr": ["예정", "권고", "고려", "계획"],
                "patterns": [
                    r"(?i)(plan|will|consider)\s+to",
                    r"(예정|고려|계획)",
                ],
            },
            "temporality": {
                "patterns": [
                    r"(?i)(today|yesterday|since\s+\w+)",
                    r"D\s*[+-]?\s*[0-9]+",
                    r"(입원|오늘|어제|이전)",
                ],
            },
        },
    }


# ============================================================
# 1b. Slot Definition 로더 + 검증기
# ============================================================

def load_slot_definition(path: Optional[str] = None) -> dict:
    """SPECS/slot_definition.yaml 로드. 없으면 빈 dict 반환."""
    if path and os.path.exists(path):
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except ImportError:
            print("⚠ pyyaml 미설치 — slot_definition 검증 비활성화")
    return {}


def load_axis_spec(path: Optional[str] = None) -> dict:
    """SPECS/axis_spec.yml 로드. 없으면 빈 dict 반환."""
    if path and os.path.exists(path):
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except ImportError:
            print("⚠ pyyaml 미설치 — axis_spec 로드 비활성화")
    return {}


def collect_disabled_slots(axis_spec: dict) -> set[str]:
    """axis_spec.yml에서 enabled=false 축의 슬롯을 수집."""
    disabled: set[str] = set()
    axes = axis_spec.get("axes") or {}
    for _, axis in axes.items():
        if axis.get("enabled") is False:
            for slot_name in (axis.get("snapshot_slots") or {}).keys():
                disabled.add(slot_name)
            for slot_name in (axis.get("event_slots") or {}).keys():
                disabled.add(slot_name)
    return disabled


class SlotDefinition:
    """
    slot_definition.yaml 기반 슬롯 레지스트리 & 검증기.
    추출 후 슬롯 이름/값 검증, 범위 체크, 문서타입별 필터링에 사용.
    """

    def __init__(self, spec: dict):
        self.spec = spec
        self.slots: dict[str, dict] = {}
        self.doc_mapping: dict[str, dict] = {}
        self._build_registry()

    def _build_registry(self):
        if not self.spec:
            return
        for key, section in self.spec.items():
            if not isinstance(section, dict):
                continue
            if key.startswith("axis_") or key == "supplementary_vitals":
                for slot_name, slot_def in section.get("slots", {}).items():
                    if isinstance(slot_def, dict):
                        self.slots[slot_name] = slot_def
        mapping = self.spec.get("document_slot_mapping", {})
        for doc_type, doc_def in mapping.items():
            if isinstance(doc_def, dict):
                self.doc_mapping[doc_type] = {
                    "mandatory": doc_def.get("mandatory", []),
                    "recommended": doc_def.get("recommended", []),
                    "optional": doc_def.get("optional", []),
                }

    @property
    def enabled(self) -> bool:
        return len(self.slots) > 0

    def is_valid_slot(self, name: str) -> bool:
        return name in self.slots

    def validate_value(self, name: str, value) -> tuple:
        """(is_valid: bool, reason: str) 반환."""
        if name not in self.slots:
            return False, f"unknown_slot"
        slot_def = self.slots[name]
        val_range = slot_def.get("range")
        if val_range and isinstance(value, (int, float)):
            lo, hi = val_range
            if not (lo <= value <= hi):
                return False, f"out_of_range [{lo},{hi}]"
        allowed = slot_def.get("allowed_values")
        if allowed and not isinstance(value, (bool, list, dict)):
            str_allowed = [str(a).lower() for a in allowed]
            if str(value).lower() not in str_allowed:
                return False, f"invalid_value"
        return True, "ok"

    def get_mandatory_slots(self, doc_type: str) -> list:
        return self.doc_mapping.get(doc_type, {}).get("mandatory", [])

    def get_all_defined_slots(self, doc_type: str) -> set:
        if doc_type not in self.doc_mapping:
            return set(self.slots.keys())
        m = self.doc_mapping[doc_type]
        return set(m.get("mandatory", []) + m.get("recommended", []) + m.get("optional", []))


# ============================================================
# 2. Context Tagger (부정/불확실/계획/시제)
# ============================================================

class ContextTagger:
    """raw_text에서 부정/불확실/계획/시제 태그 추출"""

    def __init__(self, common_context: dict):
        self.negation_patterns = self._compile(common_context.get("negation", {}).get("patterns", []))
        self.negation_keywords_kr = common_context.get("negation", {}).get("kr", [])
        self.negation_keywords_en = common_context.get("negation", {}).get("en", [])

        self.uncertainty_patterns = self._compile(common_context.get("uncertainty", {}).get("patterns", []))
        self.uncertainty_keywords_kr = common_context.get("uncertainty", {}).get("kr", [])

        self.plan_patterns = self._compile(common_context.get("plan", {}).get("patterns", []))
        self.plan_keywords_kr = common_context.get("plan", {}).get("kr", [])

        self.temporality_patterns = self._compile(common_context.get("temporality", {}).get("patterns", []))

    def _compile(self, patterns: list) -> list:
        compiled = []
        for p in patterns:
            try:
                compiled.append(re.compile(p))
            except re.error:
                pass
        return compiled

    def tag(self, raw_text: str) -> dict:
        return {
            "negation": self._find_matches(raw_text, self.negation_patterns, self.negation_keywords_kr + self.negation_keywords_en),
            "uncertainty": self._find_matches(raw_text, self.uncertainty_patterns, self.uncertainty_keywords_kr),
            "plan": self._find_matches(raw_text, self.plan_patterns, self.plan_keywords_kr),
            "temporality": self._find_temporality(raw_text),
        }

    def _find_matches(self, text: str, patterns: list, keywords: list) -> list:
        matches = []
        for p in patterns:
            for m in p.finditer(text):
                matches.append(m.group(0))
        for kw in keywords:
            if kw in text:
                if kw not in " ".join(matches):
                    matches.append(kw)
        return list(set(matches))

    def _find_temporality(self, text: str) -> dict:
        result = {"past": [], "present": [], "future": []}
        for p in self.temporality_patterns:
            for m in p.finditer(text):
                token = m.group(0)
                if any(w in token.lower() for w in ["yesterday", "어제", "이전"]):
                    result["past"].append(token)
                elif any(w in token.lower() for w in ["today", "오늘"]):
                    result["present"].append(token)
                elif any(w in token.lower() for w in ["예정", "계획", "will"]):
                    result["future"].append(token)
                else:
                    result["present"].append(token)
        return result


# ============================================================
# 3. 정규식 패턴 정의
# ============================================================

# --- Vital Signs 패턴 ---
RE_VS_LINE = re.compile(
    r"V/S\s*\)?\s*:?\s*(\d{2,3})/(\d{2,3})\s*-\s*(\d{2,3})\s*-\s*(\d{2,3})\s*-\s*([\d.]+)\s*-?\s*(\d{2,3})%?"
)
RE_SPO2 = re.compile(r"(?i)sp\s*o\s*2?\s*:?\s*(\d{2,3})\s*%?")
RE_TEMP = re.compile(r"(?i)(?:temp|bt|체온)\s*:?\s*(\d{2}\.?\d?)\s*(?:도|℃)?")

# --- O2 관련 ---
RE_O2_DEVICE = re.compile(r"(?i)\b(RA|NC|VM|SM|NRM|HFNC|room\s*air|nasal\s*cannula|simple\s*mask|venturi\s*mask)\b")
RE_O2_FLOW = re.compile(r"(?i)(?:NC|VM|SM|NRM|HFNC|O2)\s*(\d{1,2}(?:\.\d+)?)\s*L")
RE_O2_CHANGE = re.compile(r"(\d+)\s*L\s*→\s*(\d+)\s*L")
RE_O2_ACTION = re.compile(r"(?i)(?:O2|산소)\s*(apply|start|시작|적용|증량|감량|중단|off)")

# --- 항생제 이벤트 ---
RE_ABX_START = re.compile(r"(?i)(start|initiate|begin|시작)\s*.{0,20}?(ceftriaxone|piperacillin|tazobactam|vancomycin|meropenem|ciprofloxacin|augmentin|metronidazole|fluconazole|levofloxacin)")
RE_ABX_START_R = re.compile(r"(?i)(ceftriaxone|piperacillin|tazobactam|vancomycin|meropenem|ciprofloxacin|augmentin|metronidazole|fluconazole|levofloxacin)\s*.{0,15}?(시작|start|투여)")
RE_ABX_CHANGE = re.compile(r"(?i)(switch|change|변경|→)\s*.{0,20}?(ceftriaxone|piperacillin|tazobactam|vancomycin|meropenem|ciprofloxacin)")
RE_ABX_ESCALATE = re.compile(r"(?i)(escalat|broaden|강화|광범위)")

# --- 임상 행동 ---
RE_NOTIFY = re.compile(r"(?i)(?:Dr\.?\s*)?(?:notify|noti|노티|보고)\s*(?:함|완료|했음)?(?:\s*(\d+)\s*(?:회|번))?")
RE_NOTIFY_STAR = re.compile(r"\*\*\s*담당의\s*notify\s*함?\s*\*\*")
RE_MONITORING = re.compile(r"(?i)q\s*([12468])\s*h")
RE_PRN = re.compile(
    r"(?i)(suction|nebulizer|neb|antipyretic|antiemetic|antidiarrheal|analgesic|oxygen(?:\s*prn)?|iv\s*fluid|fluid|bolus|"
    r"해열제|수액|석션|네뷸라이저|진통제|진통|지사제|오심|구토|산소).{0,10}(시행|투여|함|applied|given)?"
)

# --- 증상 ---
RE_DYSPNEA = re.compile(r"(?i)(dyspnea|호흡곤란|숨.{0,4}가[쁜빠빰빡]|숨.{0,4}차|SOB|breathless|labored\s*breathing)")
RE_WOB = re.compile(r"(?i)(accessory\s*muscle|노력호흡|비익호흡|nasal\s*flaring|tachypnea|빈호흡)")
RE_FEVER = re.compile(r"(?i)(fever|febrile|chills|rigors|발열|고열|오한)")
RE_DIARRHEA = re.compile(r"(?i)(diarrhea|loose\s*stool|watery|설사|물변)")
RE_NAUSEA = re.compile(r"(?i)(vomiting|nausea|구토|오심|구역)")
RE_AMS = re.compile(r"(?i)(AMS|confusion|drowsy|stupor|의식저하|혼미|기면)")
RE_PAIN_NRS = re.compile(
    r"(?:NRS|pain\s*(?:score|scale)?|통증)\s*:?\s*(\d{1,2})\s*/\s*10|"
    r"(\d{1,2})\s*/\s*10\s*(?:\(NRS\)|\(VAS\))?|"
    r"통증\s*(\d{1,2})\s*점|"
    r"NRS\s*(\d{1,2})",
    re.I,
)
RE_PAIN_LOCATION = re.compile(
    r"(abdominal|flank|back|chest|suprapubic|epigastric|RLQ|LLQ|RUQ|LUQ)\s*pain|"
    r"(복통|옆구리|허리|두통|흉통|하복부|상복부)\s*(통증|아파|쑤시|불편)",
    re.I,
)

# --- 집단 감염 의심 (epidemiological cluster, gram stain "cocci in clusters" 제외) ---
RE_CLUSTER = re.compile(
    r"(?i)"
    r"(cluster\s+(?:infection|outbreak|case|event|suspected|signal|alert|surveillance|발생|감염)"
    r"|outbreak"
    r"|집단\s*발생"
    r"|동일\s*균\s*(?:검출|확인|분리|발생)"
    r"|same\s*organism.{0,40}(?:another|ward|patient|room|병동)"
    r"|another\s*patient.{0,40}(?:same|VRE|MRSA|MSSA|CRE|ESBL|CPE)"
    r"|(?:VRE|MRSA|MSSA|CRE|ESBL|CPE).{0,40}another\s*patient"
    r"|병동\s*내\s*(?:동일|집단|전파|감염)"
    r")"
)

# --- 격리/MDRO (raw_text에서 감지) ---
RE_ISOLATION_REQ = re.compile(r"(?i)(contact|droplet|airborne)\s*(isolation|precaution|격리)")
RE_ISOLATION_APPLIED = re.compile(r"(?i)(isolation\s*(?:applied|시행|적용))|격리\s*(?:시행|적용)")
RE_ISOLATION_GAP = re.compile(r"(?i)격리\s*(아직|안\s*됨|미시행)")
RE_MDRO_ALERT = re.compile(r"(?i)MDRO\s+ALERT\s*:\s*(MRSA|VRE|CRE|ESBL|CPE|VRSA)")

# --- Escalation ---
RE_ICU = re.compile(r"(?i)ICU\s*(eval|transfer|consult|평가|전실)|중환자실")
RE_TRANSFER = re.compile(r"(?i)(transfer|전원|refer|의뢰)\s*.{0,10}(고려|필요|예정|consider)?")
RE_RRT = re.compile(r"(?i)(RRT|rapid\s*response|code\s*blue|응급\s*호출)")
RE_SEPSIS_BUNDLE = re.compile(r"(?i)(sepsis\s*bundle|패혈증\s*번들|sepsis\s*pathway|패혈증\s*프로토콜)")
RE_VASOPRESSOR = re.compile(r"(?i)(vasopressor|승압제|norepinephrine|dopamine|levophed)")

# --- Culture ordered (from text) ---
RE_CULTURE_ORDER = re.compile(r"(?i)(blood|urine|sputum|stool|wound)\s*(?:culture|Cx|배양)")

# --- CXR findings from text ---
RE_CXR_FINDING = re.compile(r"(?i)(consolidation|opacit(?:y|ies)|infiltrat(?:e|ion)|effusion|atelectasis|edema|침윤|경화|흉수|무기폐)")
RE_CXR_LOCATION = re.compile(r"(?i)\b(RUL|RML|RLL|LUL|LLL|lingula|bilateral|both|양측)\b")
RE_CXR_WORSENING = re.compile(r"(?i)(worsening|increased|aggravated|progressed|new\s+lesion|악화|증가|신규)")
RE_CXR_IMPROVING = re.compile(r"(?i)(improved|decreased|resolved|clearing|호전|감소)")

# --- Lab values (raw_text의 "WBC: 6.5 K/uL" 형태) ---
RE_LAB_WBC = re.compile(r"(?i)\bWBC\s*:\s*(\d+\.?\d*)")
RE_LAB_HGB = re.compile(r"(?i)\b(?:Hgb|Hemoglobin|Hb)\s*:\s*(\d+\.?\d*)")
RE_LAB_PLT = re.compile(r"(?i)\b(?:Plt|Platelet)\s*:\s*(\d+\.?\d*)")
RE_LAB_BUN = re.compile(r"(?i)\bBUN\s*:\s*(\d+\.?\d*)")
RE_LAB_CR = re.compile(r"(?i)\bCr(?:eatinine)?\s*:\s*(\d+\.?\d*)")
RE_LAB_NA = re.compile(r"(?i)\bNa\s*:\s*(\d+\.?\d*)")
RE_LAB_K = re.compile(r"(?i)\bK\s*:\s*(\d+\.?\d*)")
RE_LAB_GLUCOSE = re.compile(r"(?i)\bGlucose\s*:\s*(\d+\.?\d*)")
RE_LAB_LACTATE = re.compile(r"(?i)\bLactate\s*:\s*(\d+\.?\d*)")
RE_LAB_CRP = re.compile(r"(?i)\bCRP\s*:\s*(\d+\.?\d*)")
RE_LAB_PCT = re.compile(r"(?i)\b(?:Procalcitonin|PCT)\s*:\s*(\d+\.?\d*)")
RE_LAB_AST = re.compile(r"(?i)\b(?:AST|SGOT)\s*:\s*(\d+\.?\d*)")
RE_LAB_ALT = re.compile(r"(?i)\b(?:ALT|SGPT)\s*:\s*(\d+\.?\d*)")

# --- Microbiology (raw_text의 structured report 형태) ---
RE_MICRO_SPECIMEN = re.compile(r"(?i)Specimen\s*:\s*(\w+)")
RE_MICRO_STATUS = re.compile(r"(?i)Status\s*:\s*(\w+)")
RE_MICRO_ORGANISM = re.compile(r"(?i)Organism\s*:\s*(.+?)(?:\n|$)")
RE_MICRO_GRAM = re.compile(r"(?i)Gram\s+Stain\s*:\s*(.+?)(?:\n|$)")
RE_MICRO_SUSCEPT = re.compile(r"^\s+([\w/\-]+)\s*:\s*([SIR])\s*$", re.MULTILINE)
RE_MICRO_MDRO_ALERT = re.compile(r"(?i)MDRO\s+ALERT\s*:\s*(MRSA|VRE|CRE|ESBL|CPE|VRSA)")
RE_MICRO_COLONY = re.compile(r"(?i)Colony\s+Count\s*:\s*(.+?)(?:\n|$)")

# --- Radiology severity (text keywords) ---
RE_RAD_SEVERITY = re.compile(r"(?i)\b(minimal|mild|moderate|severe|marked|extensive)\b")
RE_RAD_NORMAL = re.compile(
    r"(?i)(no\s+(?:active|acute)\s+(?:lung\s+)?(?:lesion|infiltrate|effusion|abnormality)|"
    r"(?:lung\s+(?:fields?\s+)?(?:are\s+)?clear|clear\s+lung|both\s+.*?clear)|"
    r"no\s+(?:active|acute)\s+(?:cardiopulmonary|pulmonary)\s+(?:abnormality|lesion)|"
    r"unremarkable|정상|no\s+gross\s+consolidation)"
)

# Radiology detail slots (lesion/location/change) are extracted by default.
ENABLE_CXR_DETAIL = True

# --- Foley/Tick (Axis F) ---
RE_FOLEY = re.compile(r"(?i)(foley|catheter|소변줄|유치도뇨관)")
RE_TICK_ESCHAR = re.compile(
    r"(?i)(inoculation\s+eschar|eschar|가피|검은\s*딱지|물린\s*자국|bite\s*mark|black\s*crust|"
    r"(?:crust).{0,10}(?:tick|bite|물린|자국)|(?:tick|bite|물린|자국).{0,10}crust)"
)
RE_TICK_EXPOSURE = re.compile(
    r"(?i)(밭일|농사|야외활동|야외\s*작업|등산|진드기|풀숲|tick[- ]?borne|tick\s*bite|hiking|outdoor\s*farming)"
)

# --- Breath sounds / Sputum ---
RE_BREATH_SOUNDS = re.compile(r"(?i)(crackles?|rales?|rhonchi|wheezing|diminished|수포음|천명음|호흡음\s*감소)")
RE_SPUTUM = re.compile(r"(?i)(purulent|yellowish|greenish|blood[- ]?tinged|thick\s*sputum|농성\s*객담|누런\s*가래|혈담)")

# --- I/O monitoring ---
RE_IO_MONITORING = re.compile(r"(?i)(I/O|intake.{0,5}output|섭취량.{0,3}배설량)")


# ============================================================
# 4. raw_text 추출 메인 함수
# ============================================================

def extract_from_text(raw_text: str, doc_type: str) -> list[dict]:
    """raw_text에서 정규식 기반 슬롯 추출"""
    if not raw_text:
        return []

    slots = []

    # --- V/S 라인 파싱 ---
    m = RE_VS_LINE.search(raw_text)
    if m:
        slots.append(_slot("bp_sys", int(m.group(1)), "regex", 0.95, m.group(0)[:60]))
        slots.append(_slot("bp_dia", int(m.group(2)), "regex", 0.95, m.group(0)[:60]))
        slots.append(_slot("hr_value", int(m.group(3)), "regex", 0.95, m.group(0)[:60]))
        slots.append(_slot("rr_value", int(m.group(4)), "regex", 0.95, m.group(0)[:60]))
        slots.append(_slot("temp_value", float(m.group(5)), "regex", 0.95, m.group(0)[:60]))
        if m.group(6):
            slots.append(_slot("spo2_value", int(m.group(6)), "regex", 0.95, m.group(0)[:60]))

    # --- SpO2 (단독 언급) ---
    for m in RE_SPO2.finditer(raw_text):
        val = int(m.group(1))
        if 50 <= val <= 100:
            slots.append(_slot("spo2_value", val, "regex", 0.9, m.group(0)))

    # --- Temp (단독 언급, V/S 라인 밖) ---
    if not RE_VS_LINE.search(raw_text):
        m = RE_TEMP.search(raw_text)
        if m:
            try:
                temp = float(m.group(1))
                if 35.0 <= temp <= 42.0:
                    slots.append(_slot("temp_value", temp, "regex", 0.9, m.group(0)))
            except ValueError:
                pass

    # --- O2 device ---
    m = RE_O2_DEVICE.search(raw_text)
    if m:
        device = _normalize_o2_device(m.group(1))
        slots.append(_slot("o2_device", device, "regex", 0.9, m.group(0)))

    # --- O2 flow ---
    m = RE_O2_FLOW.search(raw_text)
    if m:
        flow = _parse_o2_flow(m.group(1))
        if flow is not None:
            slots.append(_slot("o2_flow_lpm", flow, "regex", 0.9, m.group(0)))

    # --- O2 변화 이벤트 ---
    m = RE_O2_CHANGE.search(raw_text)
    if m:
        prev, new = int(m.group(1)), int(m.group(2))
        event = "increase" if new > prev else "decrease" if new < prev else "none"
        slots.append(_slot("resp_support_event", event, "regex", 0.9, m.group(0)))

    m = RE_O2_ACTION.search(raw_text)
    if m:
        action_map = {"apply": "start", "start": "start", "시작": "start", "적용": "start",
                       "증량": "increase", "감량": "decrease", "중단": "stop", "off": "stop"}
        action = action_map.get(m.group(1).lower(), m.group(1).lower())
        slots.append(_slot("resp_support_event", action, "regex", 0.9, m.group(0)))

    # --- 항생제 이벤트 ---
    if RE_ABX_START.search(raw_text) or RE_ABX_START_R.search(raw_text):
        matched = RE_ABX_START.search(raw_text) or RE_ABX_START_R.search(raw_text)
        slots.append(_slot("abx_event", "start", "regex", 0.9, matched.group(0)[:60]))
    if RE_ABX_CHANGE.search(raw_text):
        m = RE_ABX_CHANGE.search(raw_text)
        slots.append(_slot("abx_event", "change", "regex", 0.9, m.group(0)[:60]))
    if RE_ABX_ESCALATE.search(raw_text):
        m = RE_ABX_ESCALATE.search(raw_text)
        slots.append(_slot("abx_event", "escalate", "regex", 0.9, m.group(0)[:60]))

    # --- Notify (여부만 기록) ---
    notify_mentioned = False
    if RE_NOTIFY_STAR.search(raw_text) or RE_NOTIFY.search(raw_text):
        notify_mentioned = True
    if notify_mentioned:
        slots.append(_slot("notify_mentioned", True, "regex", 0.9, "notify mentioned"))

    # --- Monitoring frequency ---
    m = RE_MONITORING.search(raw_text)
    if m:
        freq = f"q{m.group(1)}h"
        slots.append(_slot("vitals_frequency", freq, "regex", 0.9, m.group(0)))

    # --- PRN interventions ---
    prns = []
    for m in RE_PRN.finditer(raw_text):
        normalized = _normalize_prn(m.group(1))
        prns.append(normalized)
    if prns:
        slots.append(_slot("prn_interventions", list(set(prns)), "regex", 0.9, ", ".join(prns)))

    # --- 증상 ---
    if RE_DYSPNEA.search(raw_text):
        slots.append(_slot("dyspnea", True, "regex", 0.9, RE_DYSPNEA.search(raw_text).group(0)))
    if RE_WOB.search(raw_text):
        m = RE_WOB.search(raw_text)
        severity = "severe" if any(w in m.group(0).lower() for w in ["accessory", "노력호흡", "비익호흡", "flaring"]) \
                   else "moderate" if any(w in m.group(0).lower() for w in ["tachypnea", "빈호흡"]) \
                   else "mild"
        slots.append(_slot("work_of_breathing", severity, "regex", 0.9, m.group(0)))
    if RE_AMS.search(raw_text):
        slots.append(_slot("altered_mentation", True, "regex", 0.9, RE_AMS.search(raw_text).group(0)))
    if RE_DIARRHEA.search(raw_text):
        slots.append(_slot("diarrhea", True, "regex", 0.9, RE_DIARRHEA.search(raw_text).group(0)))
    if RE_NAUSEA.search(raw_text):
        slots.append(_slot("nausea_vomiting", True, "regex", 0.9, RE_NAUSEA.search(raw_text).group(0)))
    for m in RE_PAIN_NRS.finditer(raw_text):
        val = next((g for g in m.groups() if g), None)
        if val is not None:
            try:
                nrs = int(val)
                if 0 <= nrs <= 10:
                    slots.append(_slot("pain_nrs_value", nrs, "regex", 0.9, m.group(0)))
            except ValueError:
                pass
    m = RE_PAIN_LOCATION.search(raw_text)
    if m:
        loc = next((g for g in m.groups() if g), None)
        if loc:
            normalized = _normalize_pain_location(loc)
            slots.append(_slot("pain_location_hint", normalized, "regex", 0.9, m.group(0)))

    # --- Breath sounds / Sputum ---
    m = RE_BREATH_SOUNDS.search(raw_text)
    if m:
        slots.append(_slot("breath_sounds", m.group(1).lower(), "regex", 0.9, m.group(0)))
    m = RE_SPUTUM.search(raw_text)
    if m:
        slots.append(_slot("sputum_character", m.group(1).lower(), "regex", 0.9, m.group(0)))

    # --- Foley / Tick ---
    if RE_FOLEY.search(raw_text):
        slots.append(_slot("foley_catheter", True, "regex", 0.9, RE_FOLEY.search(raw_text).group(0)))
    if RE_TICK_ESCHAR.search(raw_text):
        slots.append(_slot("tick_eschar", True, "regex", 0.9, RE_TICK_ESCHAR.search(raw_text).group(0)))
    if RE_TICK_EXPOSURE.search(raw_text):
        slots.append(_slot("tick_exposure", True, "regex", 0.9, RE_TICK_EXPOSURE.search(raw_text).group(0)))

    # --- I/O monitoring ---
    if RE_IO_MONITORING.search(raw_text):
        slots.append(_slot("intake_output_monitoring", True, "regex", 0.9, RE_IO_MONITORING.search(raw_text).group(0)))

    # --- 격리/MDRO ---
    if RE_ISOLATION_REQ.search(raw_text):
        m = RE_ISOLATION_REQ.search(raw_text)
        iso_type = m.group(1).lower()
        slots.append(_slot("isolation_required", iso_type, "regex", 0.9, m.group(0)))
    if RE_ISOLATION_APPLIED.search(raw_text):
        slots.append(_slot("isolation_applied", True, "regex", 0.9, RE_ISOLATION_APPLIED.search(raw_text).group(0)))
    if RE_ISOLATION_GAP.search(raw_text):
        slots.append(_slot("isolation_applied", False, "regex", 0.9, RE_ISOLATION_GAP.search(raw_text).group(0)))
    if doc_type == "microbiology":
        m = RE_MDRO_ALERT.search(raw_text)
        if m:
            slots.append(_slot("mdro_flag", m.group(1).upper(), "regex", 0.95, m.group(0)))
    m = RE_CLUSTER.search(raw_text)
    if m:
        slots.append(_slot("cluster_suspected", True, "regex", 0.85, m.group(0)[:80]))

    # --- Escalation ---
    if RE_ICU.search(raw_text):
        slots.append(_slot("icu_eval_mentioned", True, "regex", 0.9, RE_ICU.search(raw_text).group(0)))
    if RE_TRANSFER.search(raw_text):
        slots.append(_slot("transfer_consideration", True, "regex", 0.9, RE_TRANSFER.search(raw_text).group(0)))
    if RE_RRT.search(raw_text):
        slots.append(_slot("rapid_response", True, "regex", 0.9, RE_RRT.search(raw_text).group(0)))
    if RE_SEPSIS_BUNDLE.search(raw_text):
        slots.append(_slot("sepsis_bundle_mentioned", True, "regex", 0.9, RE_SEPSIS_BUNDLE.search(raw_text).group(0)))
    if RE_VASOPRESSOR.search(raw_text):
        slots.append(_slot("vasopressor_mentioned", True, "regex", 0.9, RE_VASOPRESSOR.search(raw_text).group(0)))

    # --- Culture ordered (from text) ---
    for m in RE_CULTURE_ORDER.finditer(raw_text):
        specimen = m.group(1).lower()
        slots.append(_slot("culture_ordered", specimen, "regex", 0.9, m.group(0)))

    # --- Lab values (raw text에서 추출) ---
    _extract_lab_values(raw_text, slots)

    # --- Microbiology (raw text에서 추출) ---
    if doc_type == "microbiology":
        _extract_microbiology(raw_text, slots)

    # --- CXR / Radiology (raw text에서 추출) ---
    if doc_type == "radiology":
        _extract_radiology(raw_text, slots)

    return slots


# ============================================================
# 4a. Lab values 추출 (raw_text)
# ============================================================

def _extract_lab_values(raw_text: str, slots: list) -> None:
    """raw_text에서 Lab 수치 추출 (WBC: 6.5 K/uL 형태)"""
    LAB_PATTERNS = {
        "wbc_value":          (RE_LAB_WBC,     lambda v: round(v / 1000, 1) if v > 100 else round(v, 1)),
        "hgb_value":          (RE_LAB_HGB,     lambda v: round(v, 1)),
        "platelet_value":     (RE_LAB_PLT,     lambda v: int(v / 1000) if v > 1000 else int(v)),
        "bun_value":          (RE_LAB_BUN,     lambda v: round(v, 1)),
        "creatinine_value":   (RE_LAB_CR,      lambda v: round(v, 1)),
        "na_value":           (RE_LAB_NA,      lambda v: round(v, 1)),
        "k_value":            (RE_LAB_K,       lambda v: round(v, 1)),
        "glucose_value":      (RE_LAB_GLUCOSE, lambda v: int(v)),
        "lactate_value":      (RE_LAB_LACTATE, lambda v: round(v, 1)),
        "crp_value":          (RE_LAB_CRP,     lambda v: round(v, 1)),
        "procalcitonin_value":(RE_LAB_PCT,     lambda v: round(v, 2)),
        "ast_value":          (RE_LAB_AST,     lambda v: int(v)),
        "alt_value":          (RE_LAB_ALT,     lambda v: int(v)),
    }
    for slot_name, (pattern, transform) in LAB_PATTERNS.items():
        m = pattern.search(raw_text)
        if m:
            try:
                val = float(m.group(1))
                slots.append(_slot(slot_name, transform(val), "regex", 0.95, m.group(0).strip()))
            except ValueError:
                pass


# ============================================================
# 4b. Microbiology 추출 (raw_text)
# ============================================================

def _extract_microbiology(raw_text: str, slots: list) -> None:
    """raw_text에서 미생물 검사 정보 추출"""
    # Specimen type
    m = RE_MICRO_SPECIMEN.search(raw_text)
    if m:
        slots.append(_slot("specimen_type", m.group(1).lower(), "regex", 0.95, m.group(0).strip()))

    # Organism
    organism_val = None
    org_m = RE_MICRO_ORGANISM.search(raw_text)
    if org_m:
        org_text = org_m.group(1).strip()
        if org_text.lower() not in ("none", "pending", "n/a", "-", ""):
            organism_val = org_text
            slots.append(_slot("organism", org_text, "regex", 0.95, org_m.group(0).strip()))

    # Status → culture_result
    m = RE_MICRO_STATUS.search(raw_text)
    if m:
        normalized = _normalize_culture_status(m.group(1), organism_val)
        culture_result = {"status": normalized, "organism": organism_val}
        slots.append(_slot("culture_result", culture_result, "regex", 0.95, m.group(0).strip()))

    # Gram stain
    m = RE_MICRO_GRAM.search(raw_text)
    if m:
        slots.append(_slot("gram_stain", m.group(1).strip(), "regex", 0.9, m.group(0).strip()))

    # Colony count
    m = RE_MICRO_COLONY.search(raw_text)
    if m:
        colony_val = m.group(1).strip()
        if colony_val.lower() not in ("pending", "none", "n/a", "-", ""):
            slots.append(_slot("colony_count", colony_val, "regex", 0.9, m.group(0).strip()))

    # Susceptibility → resistance_detected: R 해석된 항생제 전체를 리스트로 수집 (slot_definition: list[string])
    r_antibiotics = []
    r_evidence_parts = []
    for sm in RE_MICRO_SUSCEPT.finditer(raw_text):
        if sm.group(2) == "R":
            r_antibiotics.append(sm.group(1).strip())
            r_evidence_parts.append(sm.group(0).strip())
    if r_antibiotics:
        evidence = " | ".join(r_evidence_parts[:3])  # evidence 최대 3개까지 표시
        slots.append(_slot("resistance_detected", sorted(set(r_antibiotics)), "regex", 0.95, evidence))

    # MDRO alert (*** MDRO ALERT: MRSA ***)
    m = RE_MICRO_MDRO_ALERT.search(raw_text)
    if m:
        slots.append(_slot("mdro_flag", m.group(1).upper(), "regex", 0.95, m.group(0).strip()))


# ============================================================
# 4c. Radiology 추출 (raw_text)
# ============================================================

def _extract_radiology(raw_text: str, slots: list) -> None:
    """raw_text에서 CXR 판독 정보 추출"""
    # Lesion/Location/Change (optional; off by default for precision vs gold)
    _FINDING_NORM = {
        "opacities": "opacity", "infiltrate": "infiltration",
        "침윤": "infiltration", "경화": "consolidation", "흉수": "effusion", "무기폐": "atelectasis",
    }
    findings = []
    if ENABLE_CXR_DETAIL:
        for m in RE_CXR_FINDING.finditer(raw_text):
            raw = m.group(1).lower()
            findings.append(_FINDING_NORM.get(raw, raw))
        if findings:
            slots.append(_slot("cxr_lesion_type", list(set(findings)), "regex", 0.9, ", ".join(findings)))

        # Location
        locations = []
        for m in RE_CXR_LOCATION.finditer(raw_text):
            loc = m.group(1).upper()
            if loc == "BOTH":
                loc = "bilateral"
            locations.append(loc)
        if locations:
            slots.append(_slot("cxr_location", list(set(locations)), "regex", 0.9, ", ".join(locations)))

        # Change direction
        if RE_CXR_WORSENING.search(raw_text):
            slots.append(_slot("cxr_change_direction", "worsening", "regex", 0.9, RE_CXR_WORSENING.search(raw_text).group(0)))
        elif RE_CXR_IMPROVING.search(raw_text):
            slots.append(_slot("cxr_change_direction", "improving", "regex", 0.9, RE_CXR_IMPROVING.search(raw_text).group(0)))
    else:
        for m in RE_CXR_FINDING.finditer(raw_text):
            raw = m.group(1).lower()
            findings.append(_FINDING_NORM.get(raw, raw))

    # Severity (explicit keywords → normal check → heuristic inference)
    severity_found = None
    for m in RE_RAD_SEVERITY.finditer(raw_text):
        kw = m.group(1).lower()
        if kw in ("marked", "extensive"):
            kw = "severe"
        if severity_found is None or _severity_rank(kw) > _severity_rank(severity_found):
            severity_found = kw
    if severity_found:
        slots.append(_slot("cxr_severity", severity_found, "regex", 0.85, f"severity: {severity_found}"))
    elif RE_RAD_NORMAL.search(raw_text):
        slots.append(_slot("cxr_severity", "normal", "regex", 0.85, "no active findings"))
    elif findings:
        # Findings 있는데 severity keyword 없으면 → worsening/findings 수 기반 추론
        has_worsening = bool(RE_CXR_WORSENING.search(raw_text))
        has_improving = bool(RE_CXR_IMPROVING.search(raw_text))
        if has_worsening and len(findings) >= 2:
            inferred = "severe"
        elif has_worsening:
            inferred = "moderate"
        elif has_improving:
            inferred = "mild"
        else:
            inferred = "moderate" if len(findings) >= 2 else "mild"
        slots.append(_slot("cxr_severity", inferred, "regex_inferred", 0.7,
                           f"inferred from findings={len(findings)}, worsening={has_worsening}"))


# ============================================================
# 5. 슬롯 헬퍼
# ============================================================

def _slot(name: str, value: Any, method: str, confidence: float, evidence: str) -> dict:
    return {
        "slot_name": name,
        "value": value,
        "extraction_method": method,
        "confidence": confidence,
        "evidence_text": evidence[:120],
    }


def _severity_rank(s: str) -> int:
    """radiology severity 비교용 순위"""
    return {"normal": 0, "minimal": 1, "mild": 2, "moderate": 3, "severe": 4}.get(s, -1)


def _normalize_o2_device(value: Any) -> str:
    if value is None:
        return "RA"
    text = str(value).strip().lower()
    mapping = {
        "room air": "RA",
        "ra": "RA",
        "nasal cannula": "NC",
        "nasal_cannula": "NC",
        "nc": "NC",
        "venturi mask": "VM",
        "vm": "VM",
        "simple mask": "SM",
        "sm": "SM",
        "non-rebreather mask": "NRM",
        "non rebreather mask": "NRM",
        "nrm": "NRM",
        "hf nc": "HFNC",
        "hfnc": "HFNC",
        "high flow nasal cannula": "HFNC",
    }
    for key, normalized in mapping.items():
        if key in text:
            return normalized
    return text.upper()


def _parse_o2_flow(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _normalize_culture_status(raw_status: Any, organism: Any) -> str:
    if raw_status is None:
        return "unknown"
    status = str(raw_status).strip().upper()
    if status in {"COLLECTED", "PENDING"}:
        return "pending"
    if status == "PRELIMINARY":
        return "preliminary"
    if status in {"POSITIVE", "POS"}:
        return "pos"
    if status in {"NEGATIVE", "NEG", "NO GROWTH"}:
        return "neg"
    if status == "FINAL":
        return "pos" if organism else "neg"
    return status.lower()


def _normalize_prn(value: str) -> str:
    text = str(value).strip().lower()
    mapping = {
        "suction": "suction",
        "석션": "suction",
        "nebulizer": "neb",
        "neb": "neb",
        "네뷸라이저": "neb",
        "antipyretic": "antipyretic",
        "해열제": "antipyretic",
        "iv fluid": "iv_fluid",
        "fluid": "iv_fluid",
        "bolus": "iv_fluid",
        "수액": "iv_fluid",
        "antiemetic": "antiemetic",
        "오심": "antiemetic",
        "구토": "antiemetic",
        "antidiarrheal": "antidiarrheal",
        "지사제": "antidiarrheal",
        "analgesic": "analgesic",
        "진통제": "analgesic",
        "진통": "analgesic",
        "oxygen": "oxygen_prn",
        "산소": "oxygen_prn",
    }
    for key, normalized in mapping.items():
        if key in text:
            return normalized
    return "unknown"


def _normalize_pain_location(value: str) -> str:
    text = str(value).strip().lower()
    mapping = {
        "abdominal": "abdomen",
        "flank": "flank",
        "back": "back",
        "chest": "chest",
        "suprapubic": "suprapubic",
        "epigastric": "epigastric",
        "rlq": "abdomen",
        "llq": "abdomen",
        "ruq": "abdomen",
        "luq": "abdomen",
        "복통": "abdomen",
        "옆구리": "flank",
        "허리": "back",
        "두통": "head",
        "흉통": "chest",
        "하복부": "suprapubic",
        "상복부": "epigastric",
    }
    for key, normalized in mapping.items():
        if key in text:
            return normalized
    return "unknown"


# ============================================================
# 6. 슬롯 병합 + 후처리
# ============================================================

def merge_slots(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """
    슬롯 병합 — 동일 슬롯은 confidence 높은 쪽 우선.
    primary에서 confidence 높은 것 유지, secondary는 빈 슬롯만 채움.
    """
    merged = {}
    for s in primary:
        key = s["slot_name"]
        if key not in merged or s["confidence"] > merged[key]["confidence"]:
            merged[key] = s

    for s in secondary:
        key = s["slot_name"]
        if key not in merged:
            merged[key] = s

    return list(merged.values())


def _infer_defaults(slots: list[dict]) -> list[dict]:
    """추출 후 기본값 추론 (예: SpO2 있으나 O2 device 언급 없으면 RA)"""
    slot_names = {s["slot_name"] for s in slots}
    if "spo2_value" in slot_names and "o2_device" not in slot_names:
        slots.append(_slot("o2_device", "RA", "inferred", 0.8, "o2_device not mentioned, assume RA"))
    return slots


# ============================================================
# 7. 메인: 문서 1건 → tagged_slots 레코드
# ============================================================

def extract_document(
    doc: dict,
    context_tagger: ContextTagger,
    use_ner: bool = False,
    ner_predictions: Optional[dict] = None,
    slot_def: Optional[SlotDefinition] = None,
    disabled_slots: Optional[set[str]] = None,
) -> dict:
    """
    parsed_documents.jsonl의 한 줄(문서 1건)을 받아서
    tagged_slots.jsonl의 한 줄로 변환.

    모든 추출은 raw_text 기반 (구조화 필드 사용 안 함).
    slot_def가 주어지면 slot_definition.yaml 기반 검증 수행.
    """
    doc_type = doc.get("document_type", "unknown")
    raw_text = doc.get("raw_text", "")

    # raw_text 정규식 추출
    text_slots = extract_from_text(raw_text, doc_type)

    # 기본값 추론 (SpO2 있으나 O2 device 없으면 RA)
    text_slots = _infer_defaults(text_slots)

    # notify_mentioned는 nursing_note에서만 notify_md(bool)로 결정 — 항상 출력
    if doc_type == "nursing_note":
        text_slots = [s for s in text_slots if s["slot_name"] != "notify_mentioned"]
        if doc.get("notify_md") is True:
            text_slots.append(_slot("notify_mentioned", True, "structured", 0.99, "notify_md=true"))
        else:
            text_slots.append(_slot("notify_mentioned", False, "structured", 0.99, "notify_md=false/null"))
    else:
        text_slots = [s for s in text_slots if s["slot_name"] != "notify_mentioned"]

    # NER (optional): only fill missing slots
    ner_slots = []
    if use_ner and extract_from_ner is not None:
        ner_slots = extract_from_ner(raw_text, doc_type, doc.get("document_id"), ner_predictions)

    # 병합 (regex > ner)
    all_slots = merge_slots(text_slots, ner_slots)

    # axis_spec 기반 비활성 슬롯 제거
    if disabled_slots:
        all_slots = [s for s in all_slots if s["slot_name"] not in disabled_slots]

    # ── slot_definition 기반 검증 ──
    validation_warnings = []
    if slot_def and slot_def.enabled:
        validated_slots = []
        for s in all_slots:
            name = s["slot_name"]
            value = s["value"]

            # 1) 슬롯 이름 검증
            if not slot_def.is_valid_slot(name):
                validation_warnings.append({"slot": name, "issue": "unknown_slot"})
                validated_slots.append(s)  # 일단 유지, 경고만
                continue

            # 2) 값 범위/허용값 검증
            is_valid, reason = slot_def.validate_value(name, value)
            if not is_valid:
                validation_warnings.append({"slot": name, "value": value, "issue": reason})
                # out_of_range는 제거, invalid_value는 유지 (경고만)
                if reason.startswith("out_of_range"):
                    continue  # 범위 밖 값은 제거
            validated_slots.append(s)
        all_slots = validated_slots

    # Context tagging
    context_tags = context_tagger.tag(raw_text)

    # datetime 필드 결정
    dt = (doc.get("note_datetime") or doc.get("result_datetime")
          or doc.get("study_datetime") or doc.get("collection_datetime") or "")

    # mandatory 슬롯 누락 체크
    mandatory_missing = []
    if slot_def and slot_def.enabled:
        extracted_names = {s["slot_name"] for s in all_slots}
        for m_slot in slot_def.get_mandatory_slots(doc_type):
            if m_slot not in extracted_names:
                mandatory_missing.append(m_slot)

    result = {
        "document_id": doc.get("document_id"),
        "patient_id": doc.get("patient_id"),
        "document_type": doc_type,
        "doc_datetime": dt,
        "hd": doc.get("hd"),
        "d_number": doc.get("d_number"),
        "extracted_slots": {s["slot_name"]: s["value"] for s in all_slots},
        "slots_detail": all_slots,
        "context_tags": context_tags,
        "evidence_spans": [
            {"slot": s["slot_name"], "text": s["evidence_text"],
             "confidence": s["confidence"], "method": s["extraction_method"]}
            for s in all_slots
        ],
        "_extraction_version": "rule_v4.1",
        "_total_slots": len(all_slots),
    }
    if validation_warnings:
        result["_validation_warnings"] = validation_warnings
    if mandatory_missing:
        result["_mandatory_missing"] = mandatory_missing

    return result


# ============================================================
# 8. 파이프라인 실행
# ============================================================

def run_phase2(
    input_path: str = DEFAULT_INPUT_PATH,
    output_path: str = DEFAULT_OUTPUT_PATH,
    dict_path: str = DEFAULT_DICT_PATH,
    slot_def_path: Optional[str] = DEFAULT_SLOT_DEF_PATH,
    axis_spec_path: Optional[str] = DEFAULT_AXIS_SPEC_PATH,
    use_ner: bool = False,
    ner_predictions_path: Optional[str] = None,
):
    """Phase 2 전체 실행"""

    dictionary = load_dictionary(dict_path)
    tagger = ContextTagger(dictionary.get("common_context", {}))
    ner_predictions = load_ner_predictions(ner_predictions_path) if (use_ner and load_ner_predictions) else None

    # slot_definition 로드
    slot_def = SlotDefinition(load_slot_definition(slot_def_path))
    if slot_def.enabled:
        print(f"📋 slot_definition 로드: {len(slot_def.slots)}개 슬롯 정의")
    else:
        print("⚠ slot_definition 미로드 — 검증 비활성화")

    axis_spec = load_axis_spec(axis_spec_path)
    disabled_slots = collect_disabled_slots(axis_spec)
    if disabled_slots:
        print(f"🚫 비활성 슬롯: {len(disabled_slots)}개 (axis_spec enabled=false)")

    if not os.path.exists(input_path):
        print(f"❌ 입력 파일 없음: {input_path}")
        return

    results = []
    skipped = 0
    with open(input_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            # Phase 1 출력에 ".367" 같은 invalid JSON number가 있을 수 있음
            fixed = re.sub(r':\s*\.(\d)', r': 0.\1', line)
            try:
                doc = json.loads(fixed)
            except json.JSONDecodeError as e:
                print(f"⚠ Line {line_no} JSON 파싱 실패, skip: {e}")
                skipped += 1
                continue
            tagged = extract_document(
                doc,
                tagger,
                use_ner=use_ner,
                ner_predictions=ner_predictions,
                slot_def=slot_def,
                disabled_slots=disabled_slots,
            )
            results.append(tagged)
    if skipped:
        print(f"⚠ {skipped}건 JSON 오류로 skip됨")

    # 출력
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    print(f"\n✅ Phase 2 완료 (raw_text only extraction, validated by slot_definition)")
    print(f"   입력 문서: {len(results)}건")
    print(f"   출력: {output_path}")

    # 통계
    total_slots = sum(r["_total_slots"] for r in results)
    print(f"   총 슬롯: {total_slots}개 (평균 {total_slots / max(len(results), 1):.1f}개/문서)")

    # 문서 타입별
    type_stats = {}
    for r in results:
        t = r["document_type"]
        type_stats[t] = type_stats.get(t, {"count": 0, "slots": 0})
        type_stats[t]["count"] += 1
        type_stats[t]["slots"] += r["_total_slots"]
    print(f"   문서 타입별:")
    for t, s in sorted(type_stats.items()):
        avg = s["slots"] / max(s["count"], 1)
        print(f"     - {t}: {s['count']}건, {s['slots']}슬롯 (avg {avg:.1f})")

    # Context tag 통계
    neg_count = sum(1 for r in results if r["context_tags"]["negation"])
    unc_count = sum(1 for r in results if r["context_tags"]["uncertainty"])
    plan_count = sum(1 for r in results if r["context_tags"]["plan"])
    print(f"   Context tags: negation={neg_count}, uncertainty={unc_count}, plan={plan_count}")

    # extraction method 통계
    method_stats = {}
    for r in results:
        for s in r["slots_detail"]:
            method = s["extraction_method"]
            method_stats[method] = method_stats.get(method, 0) + 1
    print(f"   추출 방법별: {method_stats}")

    # ── slot_definition 검증 통계 ──
    if slot_def.enabled:
        warn_counter: dict[str, int] = {}
        mandatory_counter: dict[str, int] = {}
        for r in results:
            for w in r.get("_validation_warnings", []):
                key = f"{w['slot']}:{w['issue']}"
                warn_counter[key] = warn_counter.get(key, 0) + 1
            for m in r.get("_mandatory_missing", []):
                mandatory_counter[m] = mandatory_counter.get(m, 0) + 1

        if warn_counter:
            print(f"\n   ⚠ 검증 경고 ({sum(warn_counter.values())}건):")
            for key, cnt in sorted(warn_counter.items(), key=lambda x: -x[1]):
                print(f"     - {key}: {cnt}건")
        else:
            print(f"\n   ✅ 검증 경고 없음")

        if mandatory_counter:
            print(f"   📌 필수 슬롯 누락:")
            for slot, cnt in sorted(mandatory_counter.items(), key=lambda x: -x[1]):
                total_docs = sum(1 for r in results if r["document_type"] in
                                 [dt for dt, m in slot_def.doc_mapping.items()
                                  if slot in m.get("mandatory", [])])
                rate = cnt / max(total_docs, 1) * 100
                print(f"     - {slot}: {cnt}/{total_docs}건 누락 ({rate:.1f}%)")


# ============================================================
# 9. CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="INFECT-GUARD Phase 2: Rule-based Slot Extraction (raw_text only)"
    )
    parser.add_argument("--input", default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--dict", default=DEFAULT_DICT_PATH)
    parser.add_argument(
        "--slot-def",
        default=DEFAULT_SLOT_DEF_PATH,
        help="Slot definition YAML for validation (optional)",
    )
    parser.add_argument(
        "--axis-spec",
        default=DEFAULT_AXIS_SPEC_PATH,
        help="Axis spec YAML for enabled/disabled axes (optional)",
    )
    parser.add_argument("--use-ner", action="store_true", help="Enable NER-based slot fill for missing rule slots")
    parser.add_argument("--ner-predictions", default=None, help="NER predictions JSONL (document_id keyed)")
    args = parser.parse_args()

    run_phase2(
        args.input,
        args.output,
        args.dict,
        slot_def_path=args.slot_def,
        axis_spec_path=args.axis_spec,
        use_ner=args.use_ner,
        ner_predictions_path=args.ner_predictions,
    )


if __name__ == "__main__":
    main()
