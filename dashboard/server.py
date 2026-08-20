"""
Local dev server for the eval dashboard.

Serves the static dashboard files and exposes a small API that triggers real
DeepEval runs against the Azure OpenAI-backed judge model defined in
tests/evals/metrics.py, reusing tests/evals/run_patient_qa_eval.py directly
(no duplicated eval logic). Results accumulate as one JSON file per run in dashboard/results/,
which is separate from that script's own tests/evals/*.csv output — running
this server never touches or interferes with the standalone script.

Usage:
    <venv-python> dashboard/server.py

Then open http://localhost:8420/
"""

import asyncio
import json
import logging
import os
import statistics
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from aiohttp import web
from dotenv import load_dotenv

# LOG_LEVEL=DEBUG shows every parsed frame from the Magnolai stream (see
# connectors/magnolai_stream.py) — useful when answers come back empty and
# you need to see the raw frames to tell whether Magnolai sent nothing or
# sent something the parser is dropping.
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)

HERE = Path(__file__).parent
EVALS_DIR = HERE.parent / "tests" / "evals"
RESULTS_DIR = HERE / "results"

QUICK_RUN_NUM_PATIENTS = 10
CATEGORY = "CYAB study QA"
ADAPTER = "DeepEval"

load_dotenv(REPO_ROOT / ".env")

sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(EVALS_DIR))
import run_patient_qa_eval as eval_mod  # noqa: E402
import magnolai_bridge  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory run state
# ---------------------------------------------------------------------------

STATE = {"running": False, "last_error": None}


def run_id_to_filename(run_id):
    return run_id.replace(":", "-") + ".json"


def rows_to_variant(rows, pass_score=None, adapter=ADAPTER):
    scores = [r["score"] for r in rows if r["score"] is not None]
    mean_score = statistics.mean(scores) if scores else 0.0
    if pass_score is not None:
        status = "pass" if mean_score >= pass_score else "fail"
    else:
        status = "pass" if all(r["success"] for r in rows) else "fail"
    return {
        "actual_answer": rows[0]["actual_output"],
        "adapter": adapter,
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


def merge_run_into_results(data, run_id, run_label, timestamp, goldens_by_patient, rows, adapter=ADAPTER):
    """Adapter lives per-variant (per run), since the same test_id can be answered
    by different adapters (DeepEval's judge model, Magnolai) across different runs."""
    data["runs"].append({"run_id": run_id, "label": run_label, "timestamp": timestamp})

def save_run(run_id, run_label, timestamp, goldens_by_patient, rows):
    """Writes one new file per run — no read-modify-write of prior history."""
    rows_by_patient = {}
    for row in rows:
        rows_by_patient.setdefault(row["patient_id"], []).append(row)

    entries = []
    for patient_id, patient_rows in rows_by_patient.items():
        golden = goldens_by_patient[patient_id]
        entries.append(
            {
                "test_id": patient_id,
                "category": golden.get("category", CATEGORY),
                "gold_question": golden["input"],
                "expected_answer": golden["expected_output"],
                "expected_format": golden.get("expected_format"),
                "pass_score": golden.get("pass_score"),
                "variant": rows_to_variant(patient_rows, golden.get("pass_score")),
            }
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    run_file = {"run_id": run_id, "label": run_label, "timestamp": timestamp, "entries": entries}
    (RESULTS_DIR / run_id_to_filename(run_id)).write_text(json.dumps(run_file, indent=2))


def load_all_results():
    """Reads every per-run file in RESULTS_DIR and rebuilds the {runs, results}
    aggregate shape the frontend expects, pivoting from run-centric storage to
    test-case-centric variants keyed by run_id."""
    if not RESULTS_DIR.exists():
        return {"runs": [], "results": []}

    run_files = []
    for path in RESULTS_DIR.glob("*.json"):
        run_files.append(json.loads(path.read_text()))
    run_files.sort(key=lambda r: r["timestamp"])

    runs = []
    results_by_test_id = {}
    for run_file in run_files:
        runs.append(
            {
                "run_id": run_file["run_id"],
                "label": run_file["label"],
                "timestamp": run_file["timestamp"],
            }
        )
        for entry in run_file["entries"]:
            test_id = entry["test_id"]
            result_entry = results_by_test_id.get(test_id)
            if result_entry is None:
                result_entry = {
                    "test_id": test_id,
                    "category": entry["category"],
                    "adapter": entry["adapter"],
                    "gold_question": entry["gold_question"],
                    "expected_answer": entry["expected_answer"],
                    "expected_format": entry["expected_format"],
                    "variants": {},
                }
                results_by_test_id[test_id] = result_entry
            result_entry["category"] = entry["category"]
            result_entry["expected_format"] = entry["expected_format"]
            result_entry["expected_answer"] = entry["expected_answer"]
            result_entry["pass_score"] = entry["pass_score"]
            result_entry["variants"][run_file["run_id"]] = entry["variant"]

    return {"runs": runs, "results": list(results_by_test_id.values())}


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

            save_run(run_id, run_label, timestamp, goldens_by_patient, rows)

        # eval_mod.run_once makes real, blocking network calls (the judge
        # model's SDK client is synchronous) — run it off the event loop so
        # the aiohttp server keeps answering /api/status while it works.
        await loop.run_in_executor(None, blocking_work)
    except Exception:
        STATE["last_error"] = traceback.format_exc(limit=5)
        logger.exception("[run] failed")
    finally:
        STATE["running"] = False


# ---------------------------------------------------------------------------
# Magnolai run state
# ---------------------------------------------------------------------------

MAGNOLAI_RUN_STATE = {"running": False, "last_error": None}


async def execute_magnolai_run(stream_id, custom_goldens=None):
    """Sends the same goldens used by /api/run to the connected Magnolai
    stream instead of the judge model, scoring Magnolai's answer as the
    actual_output — mirrors execute_real_run's shape so both merge into
    results.json the same way, just tagged with a different adapter."""
    MAGNOLAI_RUN_STATE["running"] = True
    MAGNOLAI_RUN_STATE["last_error"] = None
    try:
        normalized_custom = [
            {
                "patient_id": g["patient_id"],
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
        run_label = datetime.now().strftime("Magnolai run %b %d, %H:%M")

        rows = await magnolai_bridge.answer_goldens(stream_id, goldens, eval_mod)

        empty_count = sum(1 for r in rows if not r.get("actual_output"))
        if empty_count:
            logger.warning(
                "[magnolai-run] %d/%d row(s) had an empty actual_output — "
                "the connected stream returned nothing for those questions.",
                empty_count, len(rows),
            )

        data = load_results()
        merge_run_into_results(
            data, run_id, run_label, timestamp, goldens_by_patient, rows,
            adapter=magnolai_bridge.ADAPTER_NAME,
        )
        save_results(data)
        logger.info("[magnolai-run] wrote %d row(s) to %s", len(rows), RESULTS_JSON_PATH)
    except Exception:
        MAGNOLAI_RUN_STATE["last_error"] = traceback.format_exc(limit=5)
        logger.exception("[magnolai-run] failed")
    finally:
        MAGNOLAI_RUN_STATE["running"] = False


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
    return web.json_response(load_all_results())


async def handle_magnolai_streams(request):
    return web.json_response({"streams": magnolai_bridge.list_streams()})


async def handle_magnolai_connect(request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    stream_id = body.get("stream_id")
    if stream_id not in magnolai_bridge.VALID_STREAM_IDS:
        return web.json_response({"error": f"Unknown stream id '{stream_id}'."}, status=400)
    state = magnolai_bridge.get_state(stream_id)
    if state["connecting"]:
        return web.json_response({"error": "Already connecting to this stream."}, status=409)
    logger.info("[api] POST /api/magnolai/connect stream_id=%s", stream_id)
    try:
        await magnolai_bridge.connect_stream(stream_id)
    except Exception as exc:
        logger.exception("[api] /api/magnolai/connect failed for stream_id=%s", stream_id)
        return web.json_response({"error": str(exc)}, status=502)
    return web.json_response(magnolai_bridge.get_state(stream_id))


async def handle_magnolai_run(request):
    if MAGNOLAI_RUN_STATE["running"]:
        return web.json_response({"error": "A Magnolai run is already in progress."}, status=409)
    try:
        body = await request.json()
    except json.JSONDecodeError:
        body = {}
    stream_id = body.get("stream_id")
    if stream_id not in magnolai_bridge.VALID_STREAM_IDS:
        return web.json_response({"error": f"Unknown stream id '{stream_id}'."}, status=400)
    if not magnolai_bridge.get_state(stream_id)["connected"]:
        return web.json_response({"error": "Stream is not connected yet."}, status=409)
    custom_goldens = body.get("custom_goldens") or []
    logger.info(
        "[api] POST /api/magnolai/run stream_id=%s custom_goldens=%d",
        stream_id, len(custom_goldens),
    )
    asyncio.ensure_future(execute_magnolai_run(stream_id, custom_goldens))
    return web.json_response({"started": True})


async def handle_magnolai_status(request):
    return web.json_response(MAGNOLAI_RUN_STATE)


async def handle_index(request):
    return web.FileResponse(HERE / "index.html")


def build_app():
    app = web.Application()
    app.router.add_post("/api/run", handle_run)
    app.router.add_get("/api/status", handle_status)
    app.router.add_get("/api/results", handle_results)
    app.router.add_get("/api/magnolai/streams", handle_magnolai_streams)
    app.router.add_post("/api/magnolai/connect", handle_magnolai_connect)
    app.router.add_post("/api/magnolai/run", handle_magnolai_run)
    app.router.add_get("/api/magnolai/status", handle_magnolai_status)
    app.router.add_get("/", handle_index)
    app.router.add_static("/", HERE, show_index=False)
    return app


if __name__ == "__main__":
    logger.info(
        "Starting dashboard server on http://localhost:8420/ "
        "(set LOG_LEVEL=DEBUG for raw Magnolai frame-level logs)"
    )
    web.run_app(build_app(), host="localhost", port=8420)
