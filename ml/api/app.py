from __future__ import annotations

from flask import Flask, jsonify, request

try:
    from .inference import XgbSepsisRuntime
    from .schema import parse_inference_request
except ImportError:  # direct script execution fallback
    import sys
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from ml.api.inference import XgbSepsisRuntime
    from ml.api.schema import parse_inference_request

app = Flask(__name__)
runtime = XgbSepsisRuntime()


def _ensure_loaded() -> None:
    if runtime.models:
        return
    runtime.load()


@app.get("/health")
def health():
    try:
        _ensure_loaded()
    except Exception as exc:  # pragma: no cover - runtime check endpoint
        return jsonify(
            {
                "status": "error",
                "code": "MODEL_NOT_READY",
                "message": str(exc),
            }
        ), 503
    return jsonify(
        {
            "status": "ok",
            "model_version": runtime.model_version,
            "feature_count": len(runtime.features),
        }
    )


@app.post("/v1/sepsis/infer")
def infer_sepsis():
    try:
        _ensure_loaded()
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "code": "MODEL_NOT_READY",
                "message": str(exc),
            }
        ), 503

    payload = request.get_json(silent=True) or {}
    req = parse_inference_request(payload)

    try:
        result = runtime.predict(req.feature_snapshot)
    except Exception as exc:
        return jsonify(
            {
                "status": "error",
                "code": "INFERENCE_FAILED",
                "message": str(exc),
            }
        ), 500

    return jsonify(
        {
            "status": "ok",
            "risk_score": result.risk_score,
            "risk_level": result.risk_level,
            "contributing_factors": result.contributing_factors,
            "recommendations": result.recommendations,
            "predicted_at": result.predicted_at,
            "model_version": result.model_version,
            "meta": {
                "patient_id": req.patient_id,
                "admission_id": req.admission_id,
                "hd": req.hd,
                "d_number": req.d_number,
                "as_of": req.as_of,
            },
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8002, debug=False)
