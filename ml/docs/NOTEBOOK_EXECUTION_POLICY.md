# Notebook Execution Policy

## Scope

- Manual notebook execution only.
- No automated `run_pipeline.py`.
- DuckDB extraction notebooks are skipped for this rollout.

## Input source

Use `ml/data/processed` copied from `/Users/iseungmin/Downloads/processed`.

Baseline reference is kept in:

- `ml/data/baseline/processed`

## Manual run order

1. `08_sliding_window_merge.ipynb`
2. `09_preprocessing.ipynb`
3. `09-1_preprocessing2.ipynb`
4. `10_feature_engineering.ipynb`
5. `12_xgboost_lightGBM 비교.ipynb`
6. `13_risk_scoring.ipynb`
7. `14_inference_pipeline.ipynb`

## Validation

After notebook runs:

```bash
python3 -m ml.src.verify_processed_equivalence
```

Use the report:

- `ml/outputs/processed_validation_report.json`
