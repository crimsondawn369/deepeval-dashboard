"""
Ad hoc multi-run eval harness: answer the static CYAB study golden Q&A pairs
(tests/evals/cyab_goldens.py) with the judge model, score answers on the
rubric in tests/evals/metrics.py, and repeat NUM_RUNS times to compare
run-to-run consistency. Results are written to CSV, not run through pytest.

No source data exists for CYAB (unlike the earlier Alzheimer's patient-chart
dataset), so there is no retrieval context to answer from or score against.
Only metrics that need input/actual_output/expected_output run here —
Faithfulness and the Contextual* metrics require non-empty retrieval_context
and are excluded (see RUN_METRICS below).

Usage:
    python tests/evals/run_patient_qa_eval.py
"""

import asyncio
import csv
import statistics
from pathlib import Path

from deepeval.test_case import LLMTestCase

from cyab_goldens import CYAB_GOLDENS
from metrics import GOLDEN_TABLE_METRICS, judge_model

HERE = Path(__file__).parent
RESULTS_CSV_PATH = HERE / "patient_qa_results.csv"
SUMMARY_CSV_PATH = HERE / "patient_qa_summary.csv"

NUM_RUNS = 5

# Bounded concurrency for metric calls per question. Deliberately not using
# deepeval's own evaluate() (default max_concurrent=20 sharing one batch-level
# deadline) — that combination caused unreliable timeouts against this Azure
# deployment. A small per-question semaphore with each metric's own generous
# per-task timeout (set via DEEPEVAL_PER_TASK_TIMEOUT_SECONDS_OVERRIDE in
# .env.local) avoids that.
METRIC_CONCURRENCY = 4

# No retrieval context exists for CYAB: Faithfulness, Contextual Precision,
# Contextual Recall, and Contextual Relevancy all require non-empty
# retrieval_context and would error on every row. Only run metrics that
# score from input/actual_output/expected_output alone.
_ALLOWED_METRIC_NAMES = {
    "Answer Relevancy",
    "Accuracy [GEval]",
    "Completeness [GEval]",
    "Hallucination Rate [GEval]",
}
RUN_METRICS = [m for m in GOLDEN_TABLE_METRICS if m.__name__ in _ALLOWED_METRIC_NAMES]


async def _score_one_metric(metric, test_case, semaphore) -> dict:
    async with semaphore:
        try:
            await metric.a_measure(test_case)
            score, success, reason = metric.score, metric.success, metric.reason
        except Exception as exc:
            score, success, reason = None, False, f"ERROR: {exc}"
    return {"metric_name": metric.__name__, "score": score, "success": success, "reason": reason}


async def _score_all_metrics(test_case) -> list[dict]:
    semaphore = asyncio.Semaphore(METRIC_CONCURRENCY)
    tasks = [_score_one_metric(metric, test_case, semaphore) for metric in RUN_METRICS]
    return await asyncio.gather(*tasks)


async def _answer_and_score(run_index: int, golden: dict) -> list[dict]:
    try:
        actual_output, _cost = await judge_model.a_generate(golden["input"])
    except Exception as exc:
        # A single dropped connection shouldn't lose the rest of a multi-run
        # job. Record the failure for all metrics and move on, matching how
        # a single metric's own exception is handled below.
        error_reason = f"ERROR generating answer: {exc}"
        return [
            {
                "run": run_index,
                "patient_id": golden["patient_id"],
                "question": golden["input"],
                "expected_output": golden["expected_output"],
                "actual_output": None,
                "metric_name": metric.__name__,
                "score": None,
                "success": False,
                "reason": error_reason,
            }
            for metric in RUN_METRICS
        ]

    test_case = LLMTestCase(
        input=golden["input"],
        actual_output=actual_output,
        expected_output=golden["expected_output"],
    )

    metric_results = await _score_all_metrics(test_case)

    return [
        {
            "run": run_index,
            "patient_id": golden["patient_id"],
            "question": golden["input"],
            "expected_output": golden["expected_output"],
            "actual_output": actual_output,
            **metric_result,
        }
        for metric_result in metric_results
    ]


async def _run_once_async(run_index: int, goldens: list[dict]) -> list[dict]:
    rows = []
    for golden in goldens:
        rows.extend(await _answer_and_score(run_index, golden))
    return rows


def run_once(run_index: int, goldens: list[dict]) -> list[dict]:
    return asyncio.run(_run_once_async(run_index, goldens))


def read_completed_runs(csv_path: Path) -> set[int]:
    if not csv_path.exists():
        return set()
    with open(csv_path, newline="") as f:
        return {int(row["run"]) for row in csv.DictReader(f)}


def append_results_csv(rows: list[dict], csv_path: Path) -> None:
    fieldnames = [
        "run",
        "patient_id",
        "question",
        "expected_output",
        "actual_output",
        "metric_name",
        "score",
        "success",
        "reason",
    ]
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def read_all_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row["run"] = int(row["run"])
        row["score"] = float(row["score"]) if row["score"] else None
        row["success"] = row["success"] == "True"
    return rows


def write_summary_csv(rows: list[dict]) -> None:
    by_run_metric: dict[tuple[int, str], list[float]] = {}
    for row in rows:
        if row["score"] is None:
            continue
        key = (row["run"], row["metric_name"])
        by_run_metric.setdefault(key, []).append(row["score"])

    fieldnames = ["run", "metric_name", "n", "mean_score", "stdev_score", "pass_rate"]
    with open(SUMMARY_CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for (run_index, metric_name), scores in sorted(by_run_metric.items()):
            successes = [
                row["success"]
                for row in rows
                if row["run"] == run_index and row["metric_name"] == metric_name
            ]
            writer.writerow(
                {
                    "run": run_index,
                    "metric_name": metric_name,
                    "n": len(scores),
                    "mean_score": round(statistics.mean(scores), 4),
                    "stdev_score": round(statistics.stdev(scores), 4)
                    if len(scores) > 1
                    else 0.0,
                    "pass_rate": round(sum(successes) / len(successes), 4)
                    if successes
                    else None,
                }
            )


def main() -> None:
    goldens = CYAB_GOLDENS
    print(f"Loaded {len(goldens)} static CYAB goldens")

    all_rows = []
    completed_runs = read_completed_runs(RESULTS_CSV_PATH)
    for run_index in range(1, NUM_RUNS + 1):
        if run_index in completed_runs:
            print(f"Skipping run {run_index}/{NUM_RUNS} (already in {RESULTS_CSV_PATH.name})")
            continue
        print(f"Running evaluation pass {run_index}/{NUM_RUNS}...")
        rows = run_once(run_index, goldens)
        append_results_csv(rows, RESULTS_CSV_PATH)
        all_rows.extend(rows)
        print(f"  -> {len(rows)} metric results collected")

    all_rows = read_all_rows(RESULTS_CSV_PATH)
    write_summary_csv(all_rows)
    print(f"Results CSV has {len(all_rows)} rows total: {RESULTS_CSV_PATH}")
    print(f"Wrote run-comparison summary to {SUMMARY_CSV_PATH}")


if __name__ == "__main__":
    main()
