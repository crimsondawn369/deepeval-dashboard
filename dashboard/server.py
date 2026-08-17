"""
Local dev server for the eval dashboard.

Serves the static dashboard files and exposes a small API that triggers real
DeepEval runs against the Azure OpenAI-backed judge model defined in
tests/evals/metrics.py, reusing tests/evals/run_patient_qa_eval.py directly
(no duplicated eval logic). Results accumulate in dashboard/results.json,
which is separate from that script's own tests/evals/*.csv output — running
this server never touches or interferes with the standalone script.

Usage:
    <venv-python> dashboard/server.py

Then open http://localhost:8420/
"""

import asyncio
import json
import statistics
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web

HERE = Path(__file__).parent
EVALS_DIR = HERE.parent / "tests" / "evals"
RESULTS_JSON_PATH = HERE / "results.json"

QUICK_RUN_NUM_PATIENTS = 10
CATEGORY = "CYAB study QA"
ADAPTER = "DeepEval"

sys.path.insert(0, str(EVALS_DIR))
import run_patient_qa_eval as eval_mod  # noqa: E402

# ---------------------------------------------------------------------------
# In-memory run state
# ---------------------------------------------------------------------------

STATE = {"running": False, "last_error": None}


def empty_results():
    return {"runs": [], "results": []}


def load_results():
    if not RESULTS_JSON_PATH.exists():
        return empty_results()
    return json.loads(RESULTS_JSON_PATH.read_text())


def save_results(data):
    RESULTS_JSON_PATH.write_text(json.dumps(data, indent=2))


def rows_to_variant(rows, pass_score=None):
    scores = [r["score"] for r in rows if r["score"] is not None]
    mean_score = statistics.mean(scores) if scores else 0.0
    if pass_score is not None:
        status = "pass" if mean_score >= pass_score else "fail"
    else:
        status = "pass" if all(r["success"] for r in rows) else "fail"
    return {
        "actual_answer": rows[0]["actual_output"],
        "score": mean_score,
        "status": status,
        "latency": rows[0].get("latency_ms", 0),
        "metrics": [
            {
                "name": r["metric_name"],
                "score": r["score"],
                "success": r["success"],
                "reason": r["reason"],
            }
            for r in rows
        ],
    }


def merge_run_into_results(data, run_id, run_label, timestamp, goldens_by_patient, rows):
    data["runs"].append({"run_id": run_id, "label": run_label, "timestamp": timestamp})

    rows_by_patient = {}
    for row in rows:
        rows_by_patient.setdefault(row["patient_id"], []).append(row)

    for patient_id, patient_rows in rows_by_patient.items():
        golden = goldens_by_patient[patient_id]
        entry = next((r for r in data["results"] if r["test_id"] == patient_id), None)
        if entry is None:
            entry = {
                "test_id": patient_id,
                "category": golden.get("category", CATEGORY),
                "adapter": ADAPTER,
                "gold_question": golden["input"],
                "expected_answer": golden["expected_output"],
                "variants": {},
            }
            data["results"].append(entry)
        entry["category"] = golden.get("category", CATEGORY)
        entry["pass_score"] = golden.get("pass_score")
        entry["variants"][run_id] = rows_to_variant(patient_rows, golden.get("pass_score"))

    return data


async def execute_real_run(custom_goldens=None):
    """Runs one real quick eval pass; reused by both /api/run and the
    (client-triggered) schedule endpoint, since both just POST /api/run."""
    STATE["running"] = True
    STATE["last_error"] = None
    try:
        loop = asyncio.get_event_loop()

        def blocking_work():
            normalized_custom = [
                {
                    "patient_id": g["patient_id"],
                    "context": "",
                    "input": g["input"],
                    "expected_output": g["expected_output"],
                    "pass_score": g.get("pass_score"),
                    "category": g.get("category") or CATEGORY,
                }
                for g in (custom_goldens or [])
            ]
            goldens = eval_mod.CYAB_GOLDENS[:QUICK_RUN_NUM_PATIENTS] + normalized_custom
            goldens_by_patient = {g["patient_id"]: g for g in goldens}

            timestamp = datetime.now(timezone.utc).isoformat()
            run_id = f"run-{timestamp}-{uuid.uuid4().hex[:6]}"
            run_label = datetime.now().strftime("Manual run %b %d, %H:%M")

            rows = []
            for golden in goldens:
                t0 = time.perf_counter()
                single_patient_rows = eval_mod.run_once(run_id, [golden])
                elapsed_ms = (time.perf_counter() - t0) * 1000
                for row in single_patient_rows:
                    row["latency_ms"] = elapsed_ms
                rows.extend(single_patient_rows)

            data = load_results()
            merge_run_into_results(data, run_id, run_label, timestamp, goldens_by_patient, rows)
            save_results(data)

        # eval_mod.run_once makes real, blocking network calls (the judge
        # model's SDK client is synchronous) — run it off the event loop so
        # the aiohttp server keeps answering /api/status while it works.
        await loop.run_in_executor(None, blocking_work)
    except Exception:
        STATE["last_error"] = traceback.format_exc(limit=5)
    finally:
        STATE["running"] = False


# ---------------------------------------------------------------------------
# HTTP handlers
# ---------------------------------------------------------------------------


async def handle_run(request):
    if STATE["running"]:
        return web.json_response({"error": "A run is already in progress."}, status=409)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    custom_goldens = body.get("custom_goldens") or []
    asyncio.ensure_future(execute_real_run(custom_goldens))
    return web.json_response({"started": True})


async def handle_status(request):
    return web.json_response(STATE)


async def handle_results(request):
    return web.json_response(load_results())


async def handle_index(request):
    return web.FileResponse(HERE / "index.html")


def build_app():
    app = web.Application()
    app.router.add_post("/api/run", handle_run)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/results", handle_results)
    app.router.add_get("/", handle_index)
    app.router.add_static("/", HERE, show_index=False)
    return app


if __name__ == "__main__":
    web.run_app(build_app(), host="localhost", port=8420)
