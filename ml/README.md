# ML Sepsis Workspace

This folder contains the Sepsis ML pipeline workspace aligned with the project root layout.

## Directory

```text
ml/
├── README.md
├── requirements.txt
├── src/
├── notebooks/
├── docs/
├── sql/
├── data/
│   ├── raw/
│   ├── processed/
│   └── baseline/processed/
├── models/
└── outputs/
```

## Execution Policy

- No `run_pipeline.py` is used.
- Notebook execution is manual.
- DuckDB extraction phase is skipped for now.
- Input baseline is copied from `/Users/iseungmin/Downloads/processed`.

## Manual Notebook Order

Run only:

1. `08_sliding_window_merge.ipynb`
2. `09_preprocessing.ipynb`
3. `09-1_preprocessing2.ipynb`
4. `10_feature_engineering.ipynb`
5. `12_xgboost_lightGBM 비교.ipynb`
6. `13_risk_scoring.ipynb`
7. `14_inference_pipeline.ipynb`

Skip extraction notebooks `01` to `07`.

## Data Validation

Compare regenerated outputs with baseline:

```bash
python3 -m ml.src.verify_processed_equivalence
```

Optional custom paths:

```bash
python3 -m ml.src.verify_processed_equivalence \
  --baseline-dir ml/data/baseline/processed \
  --processed-dir ml/data/processed
```
