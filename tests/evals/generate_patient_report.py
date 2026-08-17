"""
Generates an LLM-written right-vs-wrong report per question, grounded in the
already-collected per-run/per-metric scores in patient_qa_results.csv (does
not re-judge anything — summarizes what's already there).

Usage:
    python tests/evals/generate_patient_report.py
"""

import re
from collections import defaultdict
from pathlib import Path

from run_patient_qa_eval import RESULTS_CSV_PATH, read_all_rows
from metrics import judge_model

HERE = Path(__file__).parent
REPORT_PATH = HERE / "patient_report.md"


def group_by_patient(rows: list[dict]) -> dict[str, list[dict]]:
    by_patient = defaultdict(list)
    for row in rows:
        by_patient[row["patient_id"]].append(row)
    return dict(by_patient)


def build_prompt(patient_id: str, rows: list[dict]) -> str:
    question = rows[0]["question"]
    expected_output = rows[0]["expected_output"]

    runs = defaultdict(list)
    for row in rows:
        runs[row["run"]].append(row)

    run_sections = []
    for run_index in sorted(runs):
        run_rows = runs[run_index]
        actual_output = run_rows[0]["actual_output"]
        metric_lines = "\n".join(
            f"  - {r['metric_name']}: score={r['score']}, "
            f"{'PASS' if r['success'] else 'FAIL'}, reason: {r['reason']}"
            for r in run_rows
        )
        run_sections.append(
            f"Run {run_index} actual answer: {actual_output}\n"
            f"Run {run_index} metric results:\n{metric_lines}"
        )

    return (
        f"You are writing a short factual analysis for one test case, based "
        f"ONLY on the data below. Do not re-judge or introduce new facts — "
        f"summarize the given scores/reasons.\n\n"
        f"Question: {question}\n"
        f"Expected (ground truth) answer: {expected_output}\n\n"
        + "\n\n".join(run_sections)
        + "\n\n"
        "Write 2-3 short paragraphs covering:\n"
        "1. What the model consistently got right across these runs.\n"
        "2. What the model consistently got wrong across these runs (if anything).\n"
        "3. Any notable run-to-run inconsistency (a metric that passed in some runs "
        "and failed in others) worth flagging.\n"
        "Be concise and specific, referencing metric names."
    )


def build_consistency_table(rows: list[dict]) -> str:
    runs = sorted({row["run"] for row in rows})
    metrics = sorted({row["metric_name"] for row in rows})

    score_by_metric_run = {
        (row["metric_name"], row["run"]): row["score"] for row in rows
    }

    header = "| Metric | " + " | ".join(f"Run {r}" for r in runs) + " |"
    separator = "|---" * (len(runs) + 1) + "|"
    lines = [header, separator]
    for metric_name in metrics:
        cells = []
        for run_index in runs:
            score = score_by_metric_run.get((metric_name, run_index))
            cells.append(f"{score:.2f}" if score is not None else "—")
        lines.append(f"| {metric_name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _question_sort_key(question_id: str):
    match = re.match(r"[A-Za-z]*(\d+)", question_id)
    return int(match.group(1)) if match else question_id


def main() -> None:
    all_rows = read_all_rows(RESULTS_CSV_PATH)
    by_patient = group_by_patient(all_rows)
    print(f"Generating report for {len(by_patient)} questions...")

    sections = ["# CYAB Study QA Right-vs-Wrong Report\n"]
    for patient_id in sorted(by_patient, key=_question_sort_key):
        rows = by_patient[patient_id]
        question = rows[0]["question"]

        prompt = build_prompt(patient_id, rows)
        narrative, _cost = judge_model.generate(prompt)

        table = build_consistency_table(rows)

        sections.append(
            f"## {patient_id}\n\n"
            f"**Question:** {question}\n\n"
            f"{narrative}\n\n"
            f"**Score by metric across runs:**\n\n{table}\n"
        )
        print(f"  -> {patient_id} done")

    REPORT_PATH.write_text("\n".join(sections))
    print(f"Wrote report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
