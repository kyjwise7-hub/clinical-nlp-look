"""
Phase 6B diff engine.
- Parse diff_rules.yaml
- Compare axis snapshots over time
- Emit trajectory events
"""

import os
from collections import defaultdict
from datetime import datetime

SPECS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "specs")

SHIFT_ORDER = {"Day": 0, "Evening": 1, "Night": 2}
VALID_RISK_SEVERITY = {"critical", "high", "medium", "low", "info"}

DEFAULT_EVENT_SEVERITY = {
    "resp_support_increase": "high",
    "o2_start_or_increase": "high",
    "spo2_drop_same_o2": "medium",
    "cxr_severity_up": "medium",
    "resp_support_decrease": "low",
    "cxr_severity_down": "low",
    "hemodynamic_instability": "critical",
    "lab_worsening": "medium",
    "lab_improving": "low",
    "abx_escalation": "high",
    "abx_deescalation": "low",
    "abx_discontinuation": "low",
    "new_mdro_detection": "high",
    "isolation_gap": "high",
    "isolation_applied": "low",
}


def parse_iso_datetime(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def normalize_severity(raw, event_type):
    if raw is None:
        return DEFAULT_EVENT_SEVERITY.get(event_type, "info")
    sev = str(raw).strip().lower()
    if sev in VALID_RISK_SEVERITY:
        return sev
    return DEFAULT_EVENT_SEVERITY.get(event_type, "info")


def safe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def unique_keep_order(items):
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


# ------------------------------------------------------------------
# Rules loader
# ------------------------------------------------------------------


def load_diff_rules(rules_path=None):
    if rules_path is None:
        rules_path = os.path.join(SPECS_DIR, "diff_rules.yaml")
    try:
        import yaml
    except ImportError:
        print("⚠ pyyaml 미설치 — diff_rules 로드 비활성화")
        return {}
    with open(rules_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_axis_rules(diff_rules):
    axis_rules = {}
    for key, section in diff_rules.items():
        if not key.startswith("axis_"):
            continue
        if not isinstance(section, dict) or "rules" not in section:
            continue
        axis_key = key[len("axis_") :]
        rules = section["rules"]
        axis_rules[axis_key] = sorted(rules, key=lambda r: r.get("priority", 999))
    return axis_rules


def get_template_aliases(diff_rules):
    return diff_rules.get("template_aliases", {})


def get_axis_priority(diff_rules):
    return diff_rules.get("axis_priority", {})


# ------------------------------------------------------------------
# Snapshot loader / grouping
# ------------------------------------------------------------------


def load_snapshots(snapshots_path):
    import json

    snapshots = []
    with open(snapshots_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                snapshots.append(json.loads(line))
    return snapshots


def group_snapshots(snapshots):
    groups = defaultdict(list)
    for snap in snapshots:
        groups[(snap["patient_id"], snap["axis"])].append(snap)

    for key in groups:
        groups[key].sort(
            key=lambda s: (
                parse_iso_datetime(s.get("doc_datetime")) or datetime.max,
                SHIFT_ORDER.get(s.get("shift"), 9),
                s.get("hd", 0),
                s.get("d_number", 0),
            )
        )
    return dict(groups)


# ------------------------------------------------------------------
# Condition engine
# ------------------------------------------------------------------

ORDERED_SLOT_RANKS = {
    "cxr_severity": {
        "unknown": 0,
        "normal": 1,
        "minimal": 2,
        "mild": 3,
        "moderate": 4,
        "severe": 5,
    },
    "monitoring_level": {"unknown": 0, "standard": 1, "enhanced": 2, "intensive": 3},
    "vitals_frequency": {"unknown": 0, "q8h": 1, "q6h": 2, "q4h": 3, "q2h": 4, "continuous": 5},
}


def ordered_rank(slot_name, value):
    if slot_name is None or value is None:
        return None
    rank_map = ORDERED_SLOT_RANKS.get(str(slot_name).strip().lower())
    if not rank_map:
        return None
    return rank_map.get(str(value).strip().lower())


def collect_condition_slots(condition):
    slots = set()
    if not isinstance(condition, dict):
        return slots
    if "slot" in condition:
        slots.add(condition["slot"])
    for key in ("any", "all"):
        if key in condition and isinstance(condition[key], list):
            for sub in condition[key]:
                slots.update(collect_condition_slots(sub))
    return slots


def derive_map_mmhg(slots):
    sbp = safe_float(slots.get("sbp_mmhg"))
    dbp = safe_float(slots.get("dbp_mmhg"))
    if sbp is None:
        sbp = safe_float(slots.get("bp_sys"))
    if dbp is None:
        dbp = safe_float(slots.get("bp_dia"))
    if sbp is None or dbp is None:
        return None
    return round((sbp + (2 * dbp)) / 3.0, 1)


def get_slot_value(slots, slot_name):
    if slot_name == "map_mmhg":
        direct = safe_float(slots.get("map_mmhg"))
        return direct if direct is not None else derive_map_mmhg(slots)
    if slot_name == "sbp_mmhg":
        direct = safe_float(slots.get("sbp_mmhg"))
        return direct if direct is not None else safe_float(slots.get("bp_sys"))
    if slot_name == "dbp_mmhg":
        direct = safe_float(slots.get("dbp_mmhg"))
        return direct if direct is not None else safe_float(slots.get("bp_dia"))
    if slot_name == "hr_bpm":
        direct = safe_float(slots.get("hr_bpm"))
        return direct if direct is not None else safe_float(slots.get("hr_value"))
    return slots.get(slot_name)


def _within_hours_ok(cond, prev_dt, curr_dt):
    hours = cond.get("within_hours")
    if hours is None:
        return True
    if prev_dt is None or curr_dt is None:
        return False
    delta = (curr_dt - prev_dt).total_seconds() / 3600.0
    if delta < 0:
        return False
    return delta <= float(hours)


def _finalize_match(matched, detail, cond, prev_dt, curr_dt):
    if not matched:
        return False, {}
    if not _within_hours_ok(cond, prev_dt, curr_dt):
        return False, {}
    return True, detail


def evaluate_condition(condition, prev_slots, curr_slots, history_slots=None, prev_dt=None, curr_dt=None):
    if history_slots is None:
        history_slots = []

    if "any" in condition:
        for sub_cond in condition["any"]:
            matched, detail = evaluate_condition(
                sub_cond,
                prev_slots,
                curr_slots,
                history_slots=history_slots,
                prev_dt=prev_dt,
                curr_dt=curr_dt,
            )
            if matched:
                return True, detail
        return False, {}

    if "all" in condition:
        combined = {}
        for sub_cond in condition["all"]:
            matched, detail = evaluate_condition(
                sub_cond,
                prev_slots,
                curr_slots,
                history_slots=history_slots,
                prev_dt=prev_dt,
                curr_dt=curr_dt,
            )
            if not matched:
                return False, {}
            combined.update(detail)
        return True, combined

    return evaluate_single_condition(condition, prev_slots, curr_slots, history_slots, prev_dt, curr_dt)


def evaluate_single_condition(cond, prev_slots, curr_slots, history_slots, prev_dt, curr_dt):
    slot_name = cond.get("slot")
    if not slot_name:
        return False, {}

    curr_val = get_slot_value(curr_slots, slot_name)
    prev_val = get_slot_value(prev_slots, slot_name)

    detail = {"slot": slot_name, "prev": prev_val, "curr": curr_val}

    if slot_name == "isolation_applied" and curr_val is None:
        curr_val = False
        detail["curr"] = False

    if "equals" in cond:
        expected = cond["equals"]
        if cond.get("first_seen"):
            if curr_val == expected:
                seen_before = any(get_slot_value(h, slot_name) == expected for h in history_slots)
                return _finalize_match(not seen_before, detail, cond, prev_dt, curr_dt)
            return False, {}
        return _finalize_match(curr_val == expected, detail, cond, prev_dt, curr_dt)

    if "not_equals" in cond:
        matched = curr_val is not None and curr_val != cond["not_equals"]
        return _finalize_match(matched, detail, cond, prev_dt, curr_dt)

    if "in" in cond:
        return _finalize_match(curr_val in cond["in"], detail, cond, prev_dt, curr_dt)

    for cmp_key in ("lt", "lte", "gt", "gte"):
        if cmp_key in cond:
            curr_num = safe_float(curr_val)
            threshold = safe_float(cond.get(cmp_key))
            if curr_num is None or threshold is None:
                return False, {}
            if cmp_key == "lt":
                ok = curr_num < threshold
            elif cmp_key == "lte":
                ok = curr_num <= threshold
            elif cmp_key == "gt":
                ok = curr_num > threshold
            else:
                ok = curr_num >= threshold
            return _finalize_match(ok, detail, cond, prev_dt, curr_dt)

    if "direction" in cond:
        direction = cond["direction"]
        threshold_abs = safe_float(cond.get("threshold_abs"))
        threshold_pct = safe_float(cond.get("threshold_pct"))

        if cond.get("condition") == "same_o2_if_possible":
            prev_device = get_slot_value(prev_slots, "o2_device")
            curr_device = get_slot_value(curr_slots, "o2_device")
            prev_flow = safe_float(get_slot_value(prev_slots, "o2_flow_lpm"))
            curr_flow = safe_float(get_slot_value(curr_slots, "o2_flow_lpm"))
            if prev_device and curr_device and prev_device != curr_device:
                return False, {}
            if prev_flow is not None and curr_flow is not None and abs(curr_flow - prev_flow) > 1e-6:
                return False, {}

        curr_num = safe_float(curr_val)
        prev_num = safe_float(prev_val)
        if curr_num is not None and prev_num is not None:
            if direction == "up":
                delta = curr_num - prev_num
            else:
                delta = prev_num - curr_num

            if threshold_pct is not None:
                if prev_num == 0:
                    pct = 100.0 if delta > 0 else 0.0
                else:
                    pct = (delta / abs(prev_num)) * 100.0
                detail["delta_pct"] = pct
                detail["delta"] = delta
                return _finalize_match(delta > 0 and pct >= threshold_pct, detail, cond, prev_dt, curr_dt)

            min_delta = threshold_abs if threshold_abs is not None else 0.01
            if min_delta <= 0:
                min_delta = 1e-9
            detail["delta"] = delta
            return _finalize_match(delta >= min_delta, detail, cond, prev_dt, curr_dt)

        prev_rank = ordered_rank(slot_name, prev_val)
        curr_rank = ordered_rank(slot_name, curr_val)
        if prev_rank is None or curr_rank is None:
            return False, {}
        if direction == "up":
            delta = curr_rank - prev_rank
        else:
            delta = prev_rank - curr_rank
        min_delta = threshold_abs if threshold_abs is not None else 1
        if min_delta <= 0:
            min_delta = 1
        detail["delta"] = delta
        return _finalize_match(delta >= min_delta, detail, cond, prev_dt, curr_dt)

    if "from" in cond and "to" in cond:
        from_vals = cond["from"] if isinstance(cond["from"], list) else [cond["from"]]
        to_val = cond["to"]
        effective_prev = prev_val if prev_val is not None else "unknown"
        matched = effective_prev in from_vals and curr_val == to_val
        return _finalize_match(matched, detail, cond, prev_dt, curr_dt)

    if "delta_gte" in cond:
        curr_num = safe_float(curr_val)
        prev_num = safe_float(prev_val)
        if curr_num is None or prev_num is None:
            return False, {}
        delta = curr_num - prev_num
        detail["delta"] = delta
        return _finalize_match(delta >= float(cond["delta_gte"]), detail, cond, prev_dt, curr_dt)

    if cond.get("list_grew") or cond.get("new_item"):
        prev_list = prev_val if isinstance(prev_val, list) else []
        curr_list = curr_val if isinstance(curr_val, list) else []
        new_items = sorted(set(curr_list) - set(prev_list))
        detail["new_items"] = new_items
        return _finalize_match(bool(new_items), detail, cond, prev_dt, curr_dt)

    if cond.get("changed"):
        not_from = cond.get("not_from")
        require_both = cond.get("require_both", False)
        if require_both and (prev_val is None or curr_val is None):
            return False, {}
        if prev_val != curr_val:
            if not_from is not None and prev_val == not_from:
                return False, {}
            return _finalize_match(True, detail, cond, prev_dt, curr_dt)
        return False, {}

    return False, {}


# ------------------------------------------------------------------
# Event text rendering
# ------------------------------------------------------------------


def render_event_text(template, prev_snap, curr_snap, detail, aliases=None):
    if aliases is None:
        aliases = {}

    prev_slots = prev_snap.get("slots", {}) if prev_snap else {}
    curr_slots = curr_snap.get("slots", {})

    hd = curr_snap.get("hd", "?")
    d_number = curr_snap.get("d_number", "?")
    day_str = f"HD{hd} D+{d_number}"

    var_map = {"day": day_str}

    for k, v in curr_slots.items():
        val = v if v is not None else "N/A"
        var_map[k] = val
        var_map[f"{k}_new"] = val

    for k, v in prev_slots.items():
        var_map[f"{k}_prev"] = v if v is not None else "N/A"

    if "new_items" in detail:
        joined = ", ".join(str(i) for i in detail["new_items"])
        var_map["new_prn_items"] = joined
        var_map["symptom_name"] = joined
        var_map["culture_type"] = joined

    slot_name = detail.get("slot")
    if slot_name:
        var_map["prev"] = prev_slots.get(slot_name, "N/A")
        var_map["new"] = curr_slots.get(slot_name, "N/A")
        var_map[f"{slot_name}_prev"] = prev_slots.get(slot_name, "N/A")
        var_map[f"{slot_name}_new"] = curr_slots.get(slot_name, "N/A")
        for suffix in ("_value", "_percent", "_lpm"):
            if slot_name.endswith(suffix):
                short = slot_name[: -len(suffix)]
                var_map[f"{short}_prev"] = prev_slots.get(slot_name, "N/A")
                var_map[f"{short}_new"] = curr_slots.get(slot_name, "N/A")
                break

    var_map["prev_loc"] = prev_slots.get("pain_location_hint", "N/A")
    var_map["new_loc"] = curr_slots.get("pain_location_hint", "N/A")
    var_map["location"] = curr_slots.get("pain_location_hint", "N/A")
    var_map["cxr_severity_prev"] = prev_slots.get("cxr_severity", "N/A")
    var_map["cxr_severity_new"] = curr_slots.get("cxr_severity", "N/A")
    var_map["mdro_flag"] = curr_slots.get("mdro_flag", "N/A")
    var_map["isolation_required"] = curr_slots.get("isolation_required", "N/A")
    var_map["cluster_reason"] = ""

    cluster_ev = curr_slots.get("cluster_evidence")
    if isinstance(cluster_ev, dict):
        var_map["cluster_reason"] = cluster_ev.get("reason", "")

    var_map["monitoring_prev"] = prev_slots.get("monitoring_level", "N/A")
    var_map["monitoring_new"] = curr_slots.get("monitoring_level", "N/A")
    var_map["freq_prev"] = prev_slots.get("vitals_frequency", "N/A")
    var_map["freq_new"] = curr_slots.get("vitals_frequency", "N/A")
    var_map["map_mmhg"] = get_slot_value(curr_slots, "map_mmhg")
    var_map["sbp_mmhg"] = get_slot_value(curr_slots, "sbp_mmhg")

    status = curr_slots.get("culture_status")
    organism = curr_slots.get("culture_organism")
    if status:
        var_map["culture_result_text"] = f"{status} ({organism})" if organism else status
    else:
        cr = curr_slots.get("culture_result")
        if isinstance(cr, dict):
            st = cr.get("status", "unknown")
            org = cr.get("organism", "")
            var_map["culture_result_text"] = f"{st} ({org})" if org else st
        else:
            var_map["culture_result_text"] = str(cr) if cr else "N/A"

    rendered = template
    for alias_key, alias_target in aliases.items():
        rendered = rendered.replace(f"{{{alias_key}}}", f"{{{alias_target}}}")
    for var_name, var_value in var_map.items():
        rendered = rendered.replace(f"{{{var_name}}}", str(var_value))
    return rendered


# ------------------------------------------------------------------
# Event generation
# ------------------------------------------------------------------


def generate_events(grouped_snapshots, axis_rules, aliases=None, axis_priority=None):
    if aliases is None:
        aliases = {}
    if axis_priority is None:
        axis_priority = {}

    all_events = []
    event_counter = defaultdict(int)
    generate_events._state_seen = {}

    for (patient_id, axis), snapshots in grouped_snapshots.items():
        rules = axis_rules.get(axis, [])
        if not rules:
            continue

        history_slots = []
        last_known = {}

        for i, curr_snap in enumerate(snapshots):
            prev_snap = snapshots[i - 1] if i > 0 else None
            prev_slots = prev_snap.get("slots", {}) if prev_snap else {}
            curr_slots = curr_snap.get("slots", {})

            render_prev_slots = dict(prev_slots)
            for slot_name, known in last_known.items():
                render_prev_slots.setdefault(slot_name, known["value"])

            curr_dt = parse_iso_datetime(curr_snap.get("doc_datetime"))

            for rule in rules:
                condition = rule.get("if", {})
                ref_slots = collect_condition_slots(condition)

                compare_prev_slots = dict(prev_slots)
                compare_prev_docs = []
                compare_prev_dt_candidates = []

                if prev_snap:
                    prev_dt_raw = prev_snap.get("doc_datetime")
                    if prev_dt_raw:
                        compare_prev_dt_candidates.append(prev_dt_raw)
                    compare_prev_docs.extend(prev_snap.get("source_docs", []))

                for slot_name in ref_slots:
                    prev_has_val = slot_name in compare_prev_slots and compare_prev_slots.get(slot_name) is not None
                    if prev_has_val:
                        continue
                    known = last_known.get(slot_name)
                    if not known:
                        continue
                    compare_prev_slots[slot_name] = known["value"]
                    known_snap = known.get("snapshot") or {}
                    known_dt_raw = known_snap.get("doc_datetime")
                    if known_dt_raw:
                        compare_prev_dt_candidates.append(known_dt_raw)
                    compare_prev_docs.extend(known_snap.get("source_docs", []))

                compare_prev_raw = None
                if compare_prev_dt_candidates:
                    compare_prev_raw = min(compare_prev_dt_candidates, key=lambda d: parse_iso_datetime(d) or datetime.max)
                elif prev_snap:
                    compare_prev_raw = prev_snap.get("doc_datetime")

                compare_prev_dt = parse_iso_datetime(compare_prev_raw)

                matched, detail = evaluate_condition(
                    condition,
                    compare_prev_slots,
                    curr_slots,
                    history_slots=history_slots,
                    prev_dt=compare_prev_dt,
                    curr_dt=curr_dt,
                )

                if not matched:
                    continue
                if compare_prev_dt and curr_dt and compare_prev_dt > curr_dt:
                    continue

                event_type = rule.get("event_type")

                if event_type in ("mdro_confirmed", "new_mdro_detection"):
                    curr_mdro = curr_slots.get("mdro_flag")
                    seen_key = (patient_id, event_type)
                    if seen_key in generate_events._state_seen and generate_events._state_seen[seen_key] == curr_mdro:
                        continue
                    generate_events._state_seen[seen_key] = curr_mdro

                if event_type == "isolation_gap":
                    curr_iso = curr_slots.get("isolation_required")
                    seen_key = (patient_id, "isolation_gap")
                    if seen_key in generate_events._state_seen and generate_events._state_seen[seen_key] == curr_iso:
                        continue
                    generate_events._state_seen[seen_key] = curr_iso

                event_counter[(patient_id, axis)] += 1
                seq = event_counter[(patient_id, axis)]
                axis_short = axis.split("_")[0]
                event_id = f"EVT_{patient_id}_{axis_short}_{seq:03d}"

                render_prev_snap = None
                if render_prev_slots:
                    render_prev_snap = {
                        "slots": render_prev_slots,
                        "doc_datetime": compare_prev_raw,
                        "source_docs": unique_keep_order(compare_prev_docs),
                    }

                render_text = render_event_text(
                    rule.get("render_template", ""),
                    render_prev_snap,
                    curr_snap,
                    detail,
                    aliases,
                )

                slot_name = detail.get("slot", "")
                evidence_parts = []
                if detail.get("prev") is not None:
                    evidence_parts.append(f"{slot_name}: {detail['prev']} → {detail['curr']}")
                elif detail.get("curr") is not None:
                    evidence_parts.append(f"{slot_name}: {detail['curr']}")
                if detail.get("delta") is not None:
                    evidence_parts.append(f"delta: {detail['delta']}")
                if detail.get("delta_pct") is not None:
                    evidence_parts.append(f"delta_pct: {round(detail['delta_pct'], 2)}")
                if detail.get("new_items"):
                    evidence_parts.append(f"new: {detail['new_items']}")
                evidence_text = "; ".join(evidence_parts) if evidence_parts else render_text

                supporting_docs = []
                if render_prev_snap:
                    supporting_docs.extend(render_prev_snap.get("source_docs", []))
                supporting_docs.extend(curr_snap.get("source_docs", []))
                supporting_docs = unique_keep_order(supporting_docs)

                event = {
                    "event_id": event_id,
                    "patient_id": patient_id,
                    "axis": axis,
                    "event_type": event_type,
                    "severity": normalize_severity(rule.get("severity"), event_type),
                    "priority_rank": rule.get("priority", 999),
                    "axis_priority": axis_priority.get(f"axis_{axis}", 0),
                    "doc_datetime": curr_snap.get("doc_datetime"),
                    "prev_doc_datetime": compare_prev_raw,
                    "hd": curr_snap.get("hd"),
                    "d_number": curr_snap.get("d_number"),
                    "shift": curr_snap.get("shift"),
                    "render_text": render_text,
                    "evidence_text": evidence_text,
                    "supporting_docs": supporting_docs,
                    "is_carried_forward": False,
                }
                all_events.append(event)

            for slot_name, slot_value in curr_slots.items():
                if slot_value is not None:
                    last_known[slot_name] = {"value": slot_value, "snapshot": curr_snap}
            history_slots.append(curr_slots)

    print(f"[이벤트 생성] 총 {len(all_events)}개 이벤트")
    return all_events


def sort_events(events):
    return sorted(
        events,
        key=lambda e: (
            e["patient_id"],
            parse_iso_datetime(e.get("doc_datetime")) or datetime.max,
            SHIFT_ORDER.get(e.get("shift"), 9),
            -e.get("axis_priority", 0),
            e.get("priority_rank", 999),
            e.get("event_type", ""),
        ),
    )
