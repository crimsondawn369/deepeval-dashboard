# deepeval-dashboard

Local dashboard and eval scripts for running and reviewing DeepEval-based patient QA evaluations.

## Contents

- `dashboard/` — static dashboard (`index.html`, `script.js`, `styles.css`, `data.js`) plus `server.py`, a local aiohttp dev server exposing `/api/run`, `/api/status`, `/api/results`, and the Magnolai endpoints below, triggering real eval runs.
- `tests/evals/` — eval scripts and metric definitions used by the dashboard's "Run Now" flow (`run_patient_qa_eval.py`, `metrics.py`, `cyab_goldens.py`, `generate_patient_report.py`, `test_golden_table.py`).
- `auth/`, `connectors/`, `connectors.yaml` — the Magnolai chat connector: interactive SSO login (`auth/cookie_manager.py`) plus the chat-stream API client (`connectors/magnolai_stream.py`), used by the dashboard's "Run via Magnolai" flow (see below).

## Setup

```
pip install -r requirements.txt
playwright install msedge
cp .env.example .env   # then fill in the real values
```

`playwright install msedge` downloads the Microsoft Edge binary Playwright drives for the Magnolai SSO login step — only needed once per machine. No virtual environment is required; everything installs into your regular Python environment.

## Running the dashboard

```
python3 dashboard/server.py
```

Then open http://localhost:8420/

Requires `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` in the environment for the Azure OpenAI-backed judge model used in `tests/evals/metrics.py`. `dashboard/server.py` loads `.env` automatically on startup.

## Magnolai chat connector

The Overview tab has a "Magnolai stream" control group: pick a stream (DBM, Data Engineering, AI Query, or CGM), click **Connect**, and a visible browser window opens for you to complete Lilly SSO login. Once connected, **Run via Magnolai** sends the same golden questions used by "Run Now" to that Magnolai stream instead of the judge model — Magnolai's answer is scored as the `actual_output` against each golden's existing `expected_output`, using the same DeepEval metrics, and the results show up in the same tables tagged with a `Magnolai` adapter.

Config (in `.env`, both already filled in with sensible defaults):

```
MAGNOLAI_ENV=dev
MAGNOLAI_MODEL=gpt-5.4
```

Notes:
- The SSO login requires network access to `*.magnolai.lilly.com` and a Lilly account that can complete SSO against Magnolai — this only works from a machine with that access, not in a sandboxed environment.
- The captured session token is cached in memory for 55 minutes and never written to disk; after that, the next run re-triggers the browser login.

