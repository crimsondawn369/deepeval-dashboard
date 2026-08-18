# Requirements

Python dependencies needed to run this project — the dashboard server (`dashboard/server.py`)
and the eval scripts it calls into (`tests/evals/`).

## Install

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements/requirements.txt
```

Python 3.9+ required (developed/tested on 3.14).

## Environment variables

The Azure OpenAI-backed judge model in `tests/evals/metrics.py` needs these set before running
the dashboard or any eval script:

```
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...
```

## What's in requirements.txt

| Package | Used for |
|---|---|
| `aiohttp` | `dashboard/server.py` — local dev server (`/api/run`, `/api/status`, `/api/results`) |
| `deepeval` | Core eval framework — metrics, test cases, dataset/golden handling |
| `azure-identity` | Authenticates to Azure OpenAI for the judge model |
| `openai` | OpenAI SDK client used under the hood by DeepEval's Azure model wrapper |
| `python-dotenv` | Loads `.env`/`.env.local` for local credentials |
| `pytest` + plugins (`pytest-asyncio`, `pytest-repeat`, `pytest-rerunfailures`, `pytest-xdist`) | Running `tests/evals/test_golden_table.py` |
