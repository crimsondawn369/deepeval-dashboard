# deepeval-dashboard

Local dashboard and eval scripts for running and reviewing DeepEval-based patient QA evaluations.

## Contents

- `dashboard/` — static dashboard (`index.html`, `script.js`, `styles.css`, `data.js`) plus `server.py`, a local aiohttp dev server exposing `/api/run`, `/api/status`, and `/api/results` and triggering real eval runs.
- `tests/evals/` — eval scripts and metric definitions used by the dashboard's "Run Now" flow (`run_patient_qa_eval.py`, `metrics.py`, `cyab_goldens.py`, `generate_patient_report.py`, `test_golden_table.py`).

## Running the dashboard

```
python3 dashboard/server.py
```

Then open http://localhost:8420/

Requires `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` in the environment for the Azure OpenAI-backed judge model used in `tests/evals/metrics.py`.
