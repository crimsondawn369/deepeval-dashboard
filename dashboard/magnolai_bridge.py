"""
Bridge between the dashboard's aiohttp server and the Magnolai chat connector
(connectors/magnolai_stream.py, connectors/registry.py).

Handles connecting to a Magnolai stream (interactive SSO login via Playwright,
see auth/cookie_manager.py) and running the dashboard's existing golden
questions through it. Magnolai's answer becomes the actual_output, scored
against each golden's existing expected_output using the same DeepEval
metrics tests/evals/run_patient_qa_eval.py already scores the judge model
with — Magnolai is a system under test here, not an oracle.
"""
import asyncio
import logging
import time

from connectors.registry import CONNECTORS, get_connector

logger = logging.getLogger(__name__)

ADAPTER_NAME = "Magnolai"

VALID_STREAM_IDS = set(CONNECTORS.keys())

_STREAM_STATE: dict[str, dict] = {
    stream_id: {"connected": False, "connecting": False, "error": None}
    for stream_id in CONNECTORS
}


def get_state(stream_id: str) -> dict:
    return _STREAM_STATE[stream_id]


def list_streams() -> list[dict]:
    return [
        {"id": stream_id, "display_name": connector.display_name, **_STREAM_STATE[stream_id]}
        for stream_id, connector in CONNECTORS.items()
    ]


async def connect_stream(stream_id: str) -> dict:
    connector = get_connector(stream_id)
    state = _STREAM_STATE[stream_id]
    state["connecting"] = True
    state["error"] = None
    logger.info("[connect] stream=%s — launching browser for SSO login...", stream_id)
    try:
        loop = asyncio.get_event_loop()
        # Playwright's sync API blocks the calling thread for the whole SSO
        # flow (browser launch through login redirect, up to ~2 min with
        # MFA) — keep it off the event loop so /api/magnolai/streams keeps
        # answering while the browser is open.
        auth_value = await loop.run_in_executor(
            None, connector.cookie_manager.get_cookie_header, True
        )
        state["connected"] = True
        auth_kind = "Bearer" if auth_value.startswith("Bearer ") else auth_value.split("=", 1)[0]
        logger.info("[connect] stream=%s — connected, auth kind=%s", stream_id, auth_kind)
    except Exception as exc:
        state["connected"] = False
        state["error"] = str(exc)
        logger.warning("[connect] stream=%s — failed: %s", stream_id, exc)
        raise
    finally:
        state["connecting"] = False
    return state


async def answer_goldens(stream_id: str, goldens: list[dict], eval_mod) -> list[dict]:
    """Send each golden's question to the connected Magnolai stream and score
    the answer against the golden's existing expected_output. Row shape
    matches eval_mod.run_once()'s output so it merges into results.json the
    same way real DeepEval runs do.
    """
    connector = get_connector(stream_id)
    loop = asyncio.get_event_loop()
    rows = []
    logger.info("[run] stream=%s — answering %d golden question(s)", stream_id, len(goldens))
    for i, golden in enumerate(goldens, 1):
        t0 = time.perf_counter()
        logger.info(
            "[run] (%d/%d) stream=%s patient_id=%s question=%r",
            i, len(goldens), stream_id, golden["patient_id"], golden["input"][:200],
        )
        try:
            actual_output, sources = await loop.run_in_executor(
                None, connector.query, golden["input"]
            )
        except Exception as exc:
            logger.warning(
                "[run] (%d/%d) patient_id=%s — Magnolai query FAILED: %s",
                i, len(goldens), golden["patient_id"], exc,
            )
            error_reason = f"ERROR querying Magnolai: {exc}"
            elapsed_ms = (time.perf_counter() - t0) * 1000
            rows.extend(
                {
                    "patient_id": golden["patient_id"],
                    "question": golden["input"],
                    "expected_output": golden["expected_output"],
                    "actual_output": None,
                    "latency_ms": elapsed_ms,
                    "metric_name": metric.__name__,
                    "score": None,
                    "success": False,
                    "reason": error_reason,
                }
                for metric in eval_mod.RUN_METRICS
            )
            continue

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[run] (%d/%d) patient_id=%s — got answer (%d chars, %d source(s), %dms): %r",
            i, len(goldens), golden["patient_id"], len(actual_output), len(sources),
            elapsed_ms, actual_output[:200],
        )
        if not actual_output:
            logger.warning(
                "[run] (%d/%d) patient_id=%s — Magnolai returned an EMPTY answer. "
                "This will score as a fail against expected_output=%r.",
                i, len(goldens), golden["patient_id"], golden["expected_output"][:200],
            )
        test_case = eval_mod.LLMTestCase(
            input=golden["input"],
            actual_output=actual_output,
            expected_output=golden["expected_output"],
        )
        metric_results = await eval_mod._score_all_metrics(test_case)
        rows.extend(
            {
                "patient_id": golden["patient_id"],
                "question": golden["input"],
                "expected_output": golden["expected_output"],
                "actual_output": actual_output,
                "latency_ms": elapsed_ms,
                **metric_result,
            }
            for metric_result in metric_results
        )
    logger.info("[run] stream=%s — done, %d row(s) produced", stream_id, len(rows))
    return rows
