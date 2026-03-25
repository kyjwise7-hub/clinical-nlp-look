from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class InferenceRequest:
    patient_id: str | None
    admission_id: int | None
    as_of: str | None
    hd: int | None
    d_number: int | None
    feature_snapshot: dict[str, Any]


def parse_inference_request(payload: dict[str, Any]) -> InferenceRequest:
    feature_snapshot = payload.get("featureSnapshot")
    if not isinstance(feature_snapshot, dict):
        feature_snapshot = {}

    def _to_int(value: Any) -> int | None:
        try:
            parsed = int(value)
            return parsed
        except (TypeError, ValueError):
            return None

    return InferenceRequest(
        patient_id=str(payload.get("patientId")) if payload.get("patientId") is not None else None,
        admission_id=_to_int(payload.get("admissionId")),
        as_of=str(payload.get("asOf")) if payload.get("asOf") is not None else None,
        hd=_to_int(payload.get("hd")),
        d_number=_to_int(payload.get("dNumber")),
        feature_snapshot=feature_snapshot,
    )

