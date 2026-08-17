// Eval Dashboard — view logic. No framework, no build step.
// Single data-access point is `loadData()` — fetches real results from the
// local server's /api/results when reachable, falling back to MOCK_DATA
// (dashboard/data.js) so the file still renders something over `file://`.

(function () {
  "use strict";

  async function loadData() {
    try {
      const res = await fetch("/api/results");
      if (!res.ok) return MOCK_DATA;
      const data = await res.json();
      if (!data.runs || !data.runs.length) return MOCK_DATA;
      return data;
    } catch (err) {
      return MOCK_DATA;
    }
  }

  let DATA = MOCK_DATA;

  // ------------------------------------------------------------------
  // Data helpers
  // ------------------------------------------------------------------

  // Find a named metric's score within a variant's metrics breakdown.
  function metricScore(metrics, metricName) {
    if (!metrics) return null;
    const m = metrics.find((x) => x.name === metricName);
    return m && typeof m.score === "number" ? m.score : null;
  }

  // The Hallucination Rate [GEval] metric is scored on GEval's fixed
  // high-is-good convention (it really measures groundedness) — invert it
  // here so the dashboard shows a "rate" where low = good, matching its name.
  function hallucinationRate(metrics) {
    const groundedness = metricScore(metrics, "Hallucination Rate [GEval]");
    return groundedness === null ? null : 1 - groundedness;
  }

  function stdev(nums) {
    if (nums.length < 2) return null;
    const avg = mean(nums);
    const variance = mean(nums.map((n) => (n - avg) ** 2));
    return Math.sqrt(variance);
  }

  // Consistency of a test case's score across all historical runs (not just
  // the run being viewed) — reads variants directly rather than going
  // through toRow()/historyForTestId() to avoid recursing back into itself.
  function repeatabilityForTestCase(testCase) {
    const scores = Object.values(testCase.variants)
      .map((v) => v.score)
      .filter((s) => typeof s === "number");
    const sd = stdev(scores);
    if (sd === null) return null;
    return Math.max(0, 1 - sd);
  }

  // Flatten one test case + one run's variant into a single row object.
  function toRow(testCase, runId) {
    const variant = testCase.variants[runId];
    if (!variant) return null;
    return {
      test_id: testCase.test_id,
      category: testCase.category,
      adapter: testCase.adapter,
      gold_question: testCase.gold_question,
      expected_answer: testCase.expected_answer,
      actual_answer: variant.actual_answer,
      score: variant.score,
      status: variant.status,
      latency: variant.latency,
      metrics: variant.metrics || null,
      accuracy: metricScore(variant.metrics, "Accuracy [GEval]"),
      hallucination_rate: hallucinationRate(variant.metrics),
      completeness: metricScore(variant.metrics, "Completeness [GEval]"),
      repeatability: repeatabilityForTestCase(testCase),
      run_id: runId,
    };
  }

  function rowsForRun(runId) {
    return DATA.results
      .map((tc) => toRow(tc, runId))
      .filter(Boolean);
  }

  function historyForTestId(testId) {
    const testCase = DATA.results.find((tc) => tc.test_id === testId);
    if (!testCase) return [];
    return DATA.runs
      .filter((run) => testCase.variants[run.run_id])
      .map((run) => ({ run, ...toRow(testCase, run.run_id) }));
  }

  function runLabel(runId) {
    const run = DATA.runs.find((r) => r.run_id === runId);
    return run ? run.label : runId;
  }

  function uniqueSorted(values) {
    return Array.from(new Set(values)).sort();
  }

  // Format is never declared explicitly in the data — infer it from the
  // expected answer's shape so the Test Table tab has something to show.
  function inferExpectedFormat(text) {
    const trimmed = (text || "").trim();
    if (/^[[{]/.test(trimmed)) {
      try {
        JSON.parse(trimmed);
        return "JSON";
      } catch (err) {
        // fall through — looked like JSON but didn't parse
      }
    }
    if (/\|.+\|/.test(trimmed) && /\|[\s-]*-{2,}[\s-]*\|/.test(trimmed)) return "Markdown table";
    if (/^\s*[-*]\s+\S/m.test(trimmed) || /^\s*\d+\.\s+\S/m.test(trimmed)) return "List";
    if (!/[.!?](\s|$)/.test(trimmed) && trimmed.includes(",") && !trimmed.includes("\n")) return "Comma-separated";
    return "Plain text";
  }

  function mean(nums) {
    if (!nums.length) return 0;
    return nums.reduce((a, b) => a + b, 0) / nums.length;
  }

  function passRate(rows) {
    if (!rows.length) return 0;
    return rows.filter((r) => r.status === "pass").length / rows.length;
  }

  function pct(n) {
    return `${Math.round(n * 100)}%`;
  }

  // Renders a 0-1 metric value, or an em dash placeholder when not computed.
  function metricCellText(value) {
    return typeof value === "number" ? value.toFixed(2) : "—";
  }

  function ms(n) {
    return `${Math.round(n)}ms`;
  }

  // ------------------------------------------------------------------
  // Tabs
  // ------------------------------------------------------------------

  function initTabs() {
    const tabs = document.querySelectorAll(".tab");
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.forEach((t) => {
          t.classList.toggle("is-active", t === tab);
          t.setAttribute("aria-selected", t === tab ? "true" : "false");
        });
        document.querySelectorAll(".view").forEach((panel) => {
          panel.hidden = panel.dataset.viewPanel !== tab.dataset.view;
        });
      });
    });
  }

  // ------------------------------------------------------------------
  // Overview — stat tiles
  // ------------------------------------------------------------------

  function renderStatTiles(runId) {
    const rows = rowsForRun(runId);
    const grid = document.getElementById("stat-grid");
    grid.textContent = "";

    const tiles = [
      { label: "Total tests", value: String(rows.length) },
      { label: "Pass rate", value: pct(passRate(rows)), accent: true },
      { label: "Avg score", value: mean(rows.map((r) => r.score)).toFixed(2) },
      { label: "Avg latency", value: ms(mean(rows.map((r) => r.latency))) },
    ];

    tiles.forEach((tile) => {
      const el = document.createElement("div");
      el.className = "stat-tile";
      const label = document.createElement("span");
      label.className = "stat-label";
      label.textContent = tile.label;
      const value = document.createElement("div");
      value.className = "stat-value" + (tile.accent ? " is-accent" : "");
      value.textContent = tile.value;
      el.append(label, value);
      grid.appendChild(el);
    });
  }

  // ------------------------------------------------------------------
  // Overview — filters + table
  // ------------------------------------------------------------------

  const overviewState = {
    runId: null,
    category: "",
    status: "",
    adapter: "",
    search: "",
    sortKey: "test_id",
    sortDir: 1,
  };

  function populateOverviewControls() {
    const runSelect = document.getElementById("overview-run-select");
    runSelect.textContent = "";
    DATA.runs.forEach((run) => {
      const opt = document.createElement("option");
      opt.value = run.run_id;
      opt.textContent = `${run.label} · ${run.run_id}`;
      runSelect.appendChild(opt);
    });
    const latestRun = DATA.runs[DATA.runs.length - 1];
    runSelect.value = latestRun.run_id;
    overviewState.runId = latestRun.run_id;

    const categories = uniqueSorted(DATA.results.map((r) => r.category));
    const categorySelect = document.getElementById("filter-category");
    categories.forEach((c) => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      categorySelect.appendChild(opt);
    });

    const adapters = uniqueSorted(DATA.results.map((r) => r.adapter));
    const adapterSelect = document.getElementById("filter-adapter");
    adapters.forEach((a) => {
      const opt = document.createElement("option");
      opt.value = a;
      opt.textContent = a;
      adapterSelect.appendChild(opt);
    });

    runSelect.addEventListener("change", () => {
      overviewState.runId = runSelect.value;
      renderStatTiles(overviewState.runId);
      renderResultsTable();
    });
    categorySelect.addEventListener("change", () => {
      overviewState.category = categorySelect.value;
      renderResultsTable();
    });
    document.getElementById("filter-status").addEventListener("change", (e) => {
      overviewState.status = e.target.value;
      renderResultsTable();
    });
    adapterSelect.addEventListener("change", () => {
      overviewState.adapter = adapterSelect.value;
      renderResultsTable();
    });
    document.getElementById("filter-search").addEventListener("input", (e) => {
      overviewState.search = e.target.value.trim().toLowerCase();
      renderResultsTable();
    });

    document.querySelectorAll("#results-table th[data-sort]").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (overviewState.sortKey === key) {
          overviewState.sortDir *= -1;
        } else {
          overviewState.sortKey = key;
          overviewState.sortDir = 1;
        }
        renderResultsTable();
      });
    });
  }

  function filteredSortedRows() {
    let rows = rowsForRun(overviewState.runId);

    if (overviewState.category) {
      rows = rows.filter((r) => r.category === overviewState.category);
    }
    if (overviewState.status) {
      rows = rows.filter((r) => r.status === overviewState.status);
    }
    if (overviewState.adapter) {
      rows = rows.filter((r) => r.adapter === overviewState.adapter);
    }
    if (overviewState.search) {
      rows = rows.filter((r) =>
        r.gold_question.toLowerCase().includes(overviewState.search)
      );
    }

    const { sortKey, sortDir } = overviewState;
    rows = rows.slice().sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === "number" && typeof bv === "number") {
        return (av - bv) * sortDir;
      }
      return String(av).localeCompare(String(bv)) * sortDir;
    });

    return rows;
  }

  function statusBadge(status) {
    const span = document.createElement("span");
    span.className = `badge badge-status badge-status-${status}`;
    span.textContent = status;
    return span;
  }

  function adapterBadge(adapter) {
    const span = document.createElement("span");
    span.className = "badge badge-adapter";
    span.textContent = adapter;
    return span;
  }

  function renderResultsTable() {
    const tbody = document.getElementById("results-tbody");
    const emptyEl = document.getElementById("results-empty");
    tbody.textContent = "";

    // Reflect active sort column with a caret.
    document.querySelectorAll("#results-table th[data-sort]").forEach((th) => {
      const caret = th.querySelector(".sort-caret");
      if (th.dataset.sort === overviewState.sortKey) {
        caret.textContent = overviewState.sortDir === 1 ? "▲" : "▼";
      } else {
        caret.textContent = "";
      }
    });

    const rows = filteredSortedRows();
    emptyEl.hidden = rows.length !== 0;

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.className = "results-row";

      const idTd = document.createElement("td");
      const idBtn = document.createElement("button");
      idBtn.className = "test-id-link";
      idBtn.textContent = row.test_id;
      idBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openDrawer(row.test_id, overviewState.runId);
      });
      idTd.appendChild(idBtn);

      const categoryTd = document.createElement("td");
      categoryTd.textContent = row.category;

      const adapterTd = document.createElement("td");
      adapterTd.appendChild(adapterBadge(row.adapter));

      const scoreTd = document.createElement("td");
      scoreTd.className = "score-cell";
      scoreTd.textContent = row.score.toFixed(2);

      const accuracyTd = document.createElement("td");
      accuracyTd.textContent = metricCellText(row.accuracy);

      const hallucinationTd = document.createElement("td");
      hallucinationTd.textContent = metricCellText(row.hallucination_rate);

      const completenessTd = document.createElement("td");
      completenessTd.textContent = metricCellText(row.completeness);

      const repeatabilityTd = document.createElement("td");
      repeatabilityTd.textContent = metricCellText(row.repeatability);

      const statusTd = document.createElement("td");
      statusTd.appendChild(statusBadge(row.status));

      const latencyTd = document.createElement("td");
      latencyTd.textContent = ms(row.latency);

      tr.append(
        idTd,
        categoryTd,
        adapterTd,
        scoreTd,
        accuracyTd,
        hallucinationTd,
        completenessTd,
        repeatabilityTd,
        statusTd,
        latencyTd
      );
      tr.addEventListener("click", () => openDrawer(row.test_id, overviewState.runId));
      tbody.appendChild(tr);
    });
  }

  // ------------------------------------------------------------------
  // Compare Runs
  // ------------------------------------------------------------------

  const compareState = { selectedRunIds: [] };

  function populateRunPicker() {
    const picker = document.getElementById("run-picker");
    picker.textContent = "";

    // Default: last two runs selected, so there's something to compare on load.
    compareState.selectedRunIds = DATA.runs.slice(-2).map((r) => r.run_id);

    DATA.runs.forEach((run) => {
      const label = document.createElement("label");
      label.className = "run-picker-item";

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = run.run_id;
      checkbox.checked = compareState.selectedRunIds.includes(run.run_id);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          compareState.selectedRunIds.push(run.run_id);
        } else {
          compareState.selectedRunIds = compareState.selectedRunIds.filter(
            (id) => id !== run.run_id
          );
        }
        // Keep chronological order regardless of click order.
        compareState.selectedRunIds.sort(
          (a, b) => DATA.runs.findIndex((r) => r.run_id === a) -
            DATA.runs.findIndex((r) => r.run_id === b)
        );
        renderCompareTable();
      });

      const text = document.createElement("span");
      const textLabel = document.createElement("span");
      textLabel.textContent = run.label;
      const textId = document.createElement("span");
      textId.className = "run-id-tag";
      textId.textContent = run.run_id;
      text.append(textLabel, textId);

      label.append(checkbox, text);
      picker.appendChild(label);
    });
  }

  function deltaSpan(current, baseline, higherIsBetter) {
    const span = document.createElement("span");
    const diff = current - baseline;
    if (Math.abs(diff) < 1e-9) {
      span.className = "delta delta-flat";
      span.textContent = "±0";
      return span;
    }
    const isImprovement = higherIsBetter ? diff > 0 : diff < 0;
    span.className = "delta " + (isImprovement ? "delta-up" : "delta-down");
    const sign = diff > 0 ? "+" : "";
    span.textContent = `${sign}${diff.toFixed(2)}`;
    return span;
  }

  function renderCompareTable() {
    const head = document.getElementById("compare-table-head");
    const tbody = document.getElementById("compare-tbody");
    const emptyEl = document.getElementById("compare-empty");
    const card = document.querySelector("#view-compare .table-card");
    head.textContent = "";
    tbody.textContent = "";

    const runIds = compareState.selectedRunIds;
    if (runIds.length < 2) {
      card.hidden = true;
      emptyEl.hidden = false;
      return;
    }
    card.hidden = false;
    emptyEl.hidden = true;

    // Header row: Category, then one group of 3 metric columns per run.
    const categoryTh = document.createElement("th");
    categoryTh.scope = "col";
    categoryTh.textContent = "Category";
    head.appendChild(categoryTh);

    runIds.forEach((runId) => {
      ["Pass rate", "Avg score", "Avg latency"].forEach((metric, i) => {
        const th = document.createElement("th");
        th.scope = "col";
        if (i === 0) {
          const strong = document.createElement("span");
          strong.className = "compare-run-group-label";
          strong.textContent = runLabel(runId);
          const sub = document.createElement("span");
          sub.className = "compare-metric-sub";
          sub.textContent = metric;
          th.append(strong, sub);
        } else {
          const sub = document.createElement("span");
          sub.className = "compare-metric-sub";
          sub.textContent = metric;
          th.appendChild(sub);
        }
        head.appendChild(th);
      });
    });

    const categories = uniqueSorted(DATA.results.map((r) => r.category));
    const baselineRunId = runIds[0];

    function buildRow(label, rows, isOverall) {
      const tr = document.createElement("tr");
      if (isOverall) tr.className = "compare-row-overall";

      const labelTd = document.createElement("td");
      labelTd.textContent = label;
      tr.appendChild(labelTd);

      let baselinePassRate, baselineScore, baselineLatency;

      runIds.forEach((runId, idx) => {
        const runRows = rows.filter((r) => r.run_id === runId);
        const pr = passRate(runRows);
        const avgScore = mean(runRows.map((r) => r.score));
        const avgLatency = mean(runRows.map((r) => r.latency));

        if (idx === 0) {
          baselinePassRate = pr;
          baselineScore = avgScore;
          baselineLatency = avgLatency;
        }

        const prTd = document.createElement("td");
        prTd.textContent = pct(pr);
        if (idx > 0) prTd.appendChild(deltaSpan(pr, baselinePassRate, true));

        const scoreTd = document.createElement("td");
        scoreTd.textContent = avgScore.toFixed(2);
        if (idx > 0) scoreTd.appendChild(deltaSpan(avgScore, baselineScore, true));

        const latencyTd = document.createElement("td");
        latencyTd.textContent = ms(avgLatency);
        if (idx > 0) latencyTd.appendChild(deltaSpan(avgLatency, baselineLatency, false));

        tr.append(prTd, scoreTd, latencyTd);
      });

      return tr;
    }

    categories.forEach((category) => {
      const rows = runIds.flatMap((runId) =>
        rowsForRun(runId).filter((r) => r.category === category)
      );
      tbody.appendChild(buildRow(category, rows, false));
    });

    const allRows = runIds.flatMap((runId) => rowsForRun(runId));
    tbody.appendChild(buildRow("Overall", allRows, true));
  }

  // ------------------------------------------------------------------
  // Test Table — one row per test case, one column per run
  // ------------------------------------------------------------------

  const testTableState = { selectedRunIds: [] };

  function selectedTestTableRuns() {
    return DATA.runs.filter((r) => testTableState.selectedRunIds.includes(r.run_id));
  }

  function updateTestTableRunBtnLabel() {
    const label = document.getElementById("test-table-run-btn-label");
    const n = testTableState.selectedRunIds.length;
    if (n === 0) label.textContent = "Select runs";
    else if (n === DATA.runs.length) label.textContent = "All runs";
    else if (n === 1) label.textContent = runLabel(testTableState.selectedRunIds[0]);
    else label.textContent = `${n} runs selected`;
  }

  function populateTestTableRunSelect() {
    const panel = document.getElementById("test-table-run-panel");
    panel.textContent = "";

    // Default: every run selected, so the tab starts showing everything.
    testTableState.selectedRunIds = DATA.runs.map((r) => r.run_id);

    DATA.runs.forEach((run) => {
      const label = document.createElement("label");
      label.className = "run-picker-item";

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = run.run_id;
      checkbox.checked = true;
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) {
          testTableState.selectedRunIds.push(run.run_id);
        } else {
          testTableState.selectedRunIds = testTableState.selectedRunIds.filter(
            (id) => id !== run.run_id
          );
        }
        testTableState.selectedRunIds.sort(
          (a, b) => DATA.runs.findIndex((r) => r.run_id === a) -
            DATA.runs.findIndex((r) => r.run_id === b)
        );
        updateTestTableRunBtnLabel();
        renderTestTable();
      });

      const text = document.createElement("span");
      const textLabel = document.createElement("span");
      textLabel.textContent = run.label;
      const textId = document.createElement("span");
      textId.className = "run-id-tag";
      textId.textContent = run.run_id;
      text.append(textLabel, textId);

      label.append(checkbox, text);
      panel.appendChild(label);
    });

    updateTestTableRunBtnLabel();
  }

  function initTestTableRunSelect() {
    const btn = document.getElementById("test-table-run-btn");
    const panel = document.getElementById("test-table-run-panel");

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const isOpen = !panel.hidden;
      panel.hidden = isOpen;
      btn.setAttribute("aria-expanded", isOpen ? "false" : "true");
    });

    document.addEventListener("click", (e) => {
      if (!panel.hidden && !e.target.closest("#test-table-run-select")) {
        panel.hidden = true;
        btn.setAttribute("aria-expanded", "false");
      }
    });
  }

  function formatBadge(format) {
    const span = document.createElement("span");
    span.className = "badge badge-format";
    span.textContent = format;
    return span;
  }

  function wrapCell(content, extraClass) {
    const td = document.createElement("td");
    td.className = "wrap-cell" + (extraClass ? ` ${extraClass}` : "");
    td.appendChild(content);
    return td;
  }

  function answerButton(text, onClick) {
    const btn = document.createElement("button");
    btn.className = "answer-btn clamp-text";
    btn.textContent = text;
    btn.addEventListener("click", onClick);
    return btn;
  }

  function renderTestTable() {
    const head = document.getElementById("test-table-head");
    const tbody = document.getElementById("test-table-tbody");
    const emptyEl = document.getElementById("test-table-empty");
    const card = document.querySelector("#view-testtable .table-card");
    head.textContent = "";
    tbody.textContent = "";

    const runs = selectedTestTableRuns();

    if (!DATA.runs.length || !DATA.results.length || !runs.length) {
      card.hidden = true;
      emptyEl.hidden = false;
      emptyEl.textContent = DATA.runs.length
        ? "Select at least one run to populate this table."
        : "No runs yet — run the eval to populate this table.";
      return;
    }
    card.hidden = false;
    emptyEl.hidden = true;

    // Header: fixed metadata columns, then one column per selected run.
    [["Question", "test-table-question"], ["Expected Answer", "test-table-expected"],
      ["Category", "test-table-category"], ["Expected Format", "test-table-format"]].forEach(
      ([label]) => {
        const th = document.createElement("th");
        th.scope = "col";
        th.textContent = label;
        head.appendChild(th);
      }
    );
    runs.forEach((run) => {
      const th = document.createElement("th");
      th.scope = "col";
      const label = document.createElement("span");
      label.textContent = run.label;
      const idTag = document.createElement("span");
      idTag.className = "run-id-tag";
      idTag.textContent = run.run_id;
      th.append(label, idTag);
      head.appendChild(th);
    });

    const latestRunId = runs[runs.length - 1].run_id;

    DATA.results.forEach((testCase) => {
      const tr = document.createElement("tr");

      const questionBtn = answerButton(testCase.gold_question, () =>
        openDrawer(testCase.test_id, latestRunId)
      );
      questionBtn.classList.add("test-id-link");
      tr.appendChild(wrapCell(questionBtn));

      const expectedSpan = document.createElement("span");
      expectedSpan.className = "clamp-text";
      expectedSpan.textContent = testCase.expected_answer;
      tr.appendChild(wrapCell(expectedSpan));

      const categoryTd = document.createElement("td");
      categoryTd.textContent = testCase.category;
      tr.appendChild(categoryTd);

      const formatTd = document.createElement("td");
      formatTd.appendChild(formatBadge(inferExpectedFormat(testCase.expected_answer)));
      tr.appendChild(formatTd);

      runs.forEach((run) => {
        const variant = testCase.variants[run.run_id];
        if (!variant) {
          const emptyTd = document.createElement("td");
          emptyTd.textContent = "—";
          tr.appendChild(emptyTd);
          return;
        }
        const wrap = document.createElement("div");
        wrap.className = "run-answer-cell";
        wrap.appendChild(
          answerButton(variant.actual_answer, () => openDrawer(testCase.test_id, run.run_id))
        );
        wrap.appendChild(statusBadge(variant.status));
        tr.appendChild(wrapCell(wrap));
      });

      tbody.appendChild(tr);
    });
  }

  // ------------------------------------------------------------------
  // Questions — catalog of built-in + custom questions
  // ------------------------------------------------------------------

  const CUSTOM_QUESTIONS_KEY = "evalDashboard.customQuestions";
  const DEFAULT_PASS_SCORE = 0.5;

  function readCustomQuestions() {
    try {
      const raw = localStorage.getItem(CUSTOM_QUESTIONS_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }

  function writeCustomQuestions(list) {
    localStorage.setItem(CUSTOM_QUESTIONS_KEY, JSON.stringify(list));
  }

  function allQuestionRows() {
    const builtIn = DATA.results.map((tc) => ({
      id: tc.test_id,
      question: tc.gold_question,
      expected_answer: tc.expected_answer,
      category: tc.category,
      pass_score: typeof tc.pass_score === "number" ? tc.pass_score : DEFAULT_PASS_SCORE,
      source: "built-in",
    }));
    const custom = readCustomQuestions().map((q) => ({ ...q, source: "custom" }));
    return builtIn.concat(custom);
  }

  const questionFormState = { editingId: null };

  function openQuestionForm(row) {
    questionFormState.editingId = row ? row.id : null;
    document.getElementById("question-form-title").textContent = row ? "Edit question" : "Add question";
    document.getElementById("question-form-question").value = row ? row.question : "";
    document.getElementById("question-form-expected").value = row ? row.expected_answer : "";
    document.getElementById("question-form-category").value = row ? row.category : "";
    document.getElementById("question-form-pass-score").value = row ? row.pass_score : "";
    showQuestionFormError(null);
    document.getElementById("question-form-card").hidden = false;
    document.getElementById("question-form-question").focus();
  }

  function closeQuestionForm() {
    document.getElementById("question-form-card").hidden = true;
    questionFormState.editingId = null;
  }

  function showQuestionFormError(message) {
    const el = document.getElementById("question-form-error");
    if (!message) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = message;
  }

  function saveQuestionForm() {
    const question = document.getElementById("question-form-question").value.trim();
    const expectedAnswer = document.getElementById("question-form-expected").value.trim();
    const category = document.getElementById("question-form-category").value.trim() || "Custom";
    const passScoreRaw = document.getElementById("question-form-pass-score").value.trim();
    const passScore = passScoreRaw === "" ? DEFAULT_PASS_SCORE : Number(passScoreRaw);

    if (!question) return showQuestionFormError("Question is required.");
    if (!expectedAnswer) return showQuestionFormError("Expected answer is required.");
    if (Number.isNaN(passScore) || passScore < 0 || passScore > 1) {
      return showQuestionFormError("Pass score must be a number between 0 and 1.");
    }

    const list = readCustomQuestions();
    if (questionFormState.editingId) {
      const existing = list.find((q) => q.id === questionFormState.editingId);
      if (existing) {
        existing.question = question;
        existing.expected_answer = expectedAnswer;
        existing.category = category;
        existing.pass_score = passScore;
      }
    } else {
      list.push({
        id: `custom-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        question,
        expected_answer: expectedAnswer,
        category,
        pass_score: passScore,
      });
    }
    writeCustomQuestions(list);
    closeQuestionForm();
    renderQuestionsTable();
  }

  function deleteCustomQuestion(id) {
    if (!window.confirm("Delete this question?")) return;
    writeCustomQuestions(readCustomQuestions().filter((q) => q.id !== id));
    renderQuestionsTable();
  }

  function renderQuestionsTable() {
    const tbody = document.getElementById("questions-tbody");
    const emptyEl = document.getElementById("questions-empty");
    const card = document.querySelector("#view-questions .table-card");
    tbody.textContent = "";

    const rows = allQuestionRows();
    if (!rows.length) {
      card.hidden = true;
      emptyEl.hidden = false;
      return;
    }
    card.hidden = false;
    emptyEl.hidden = true;

    rows.forEach((row) => {
      const tr = document.createElement("tr");

      const questionSpan = document.createElement("span");
      questionSpan.className = "clamp-text";
      questionSpan.textContent = row.question;
      tr.appendChild(wrapCell(questionSpan));

      const expectedSpan = document.createElement("span");
      expectedSpan.className = "clamp-text";
      expectedSpan.textContent = row.expected_answer;
      tr.appendChild(wrapCell(expectedSpan));

      const categoryTd = document.createElement("td");
      const categoryBadge = document.createElement("span");
      categoryBadge.className = "badge badge-category";
      categoryBadge.textContent = row.category;
      categoryTd.appendChild(categoryBadge);
      tr.appendChild(categoryTd);

      const passScoreTd = document.createElement("td");
      const passScoreBadge = document.createElement("span");
      passScoreBadge.className = "badge badge-pass-score";
      passScoreBadge.textContent = row.pass_score.toFixed(2);
      passScoreTd.appendChild(passScoreBadge);
      tr.appendChild(passScoreTd);

      const sourceTd = document.createElement("td");
      sourceTd.textContent = row.source === "built-in" ? "Built-in" : "Custom";
      tr.appendChild(sourceTd);

      const actionsTd = document.createElement("td");
      if (row.source === "custom") {
        const actions = document.createElement("div");
        actions.className = "row-actions";

        const editBtn = document.createElement("button");
        editBtn.className = "link-btn";
        editBtn.textContent = "Edit";
        editBtn.addEventListener("click", () => openQuestionForm(row));

        const deleteBtn = document.createElement("button");
        deleteBtn.className = "link-btn";
        deleteBtn.textContent = "Delete";
        deleteBtn.addEventListener("click", () => deleteCustomQuestion(row.id));

        actions.append(editBtn, deleteBtn);
        actionsTd.appendChild(actions);
      } else {
        actionsTd.textContent = "—";
      }
      tr.appendChild(actionsTd);

      tbody.appendChild(tr);
    });
  }

  function initQuestionsTab() {
    document.getElementById("add-question-btn").addEventListener("click", () => openQuestionForm(null));
    document.getElementById("question-form-save-btn").addEventListener("click", saveQuestionForm);
    document.getElementById("question-form-cancel-btn").addEventListener("click", closeQuestionForm);
  }

  // ------------------------------------------------------------------
  // Trends — each metric plotted across all historical runs
  // ------------------------------------------------------------------

  // Repeatability has no per-run value of its own (it's already an
  // all-runs consistency score) — approximate a trend by recomputing it
  // using only the runs seen up through each point, so it fills in as
  // more history accumulates.
  function cumulativeRepeatabilityPerRun() {
    const runIds = DATA.runs.map((r) => r.run_id);
    return runIds.map((_, i) => {
      const seenRunIds = runIds.slice(0, i + 1);
      const perTestCase = DATA.results
        .map((tc) => {
          const scores = seenRunIds
            .map((rid) => tc.variants[rid])
            .filter(Boolean)
            .map((v) => v.score);
          const sd = stdev(scores);
          return sd === null ? null : Math.max(0, 1 - sd);
        })
        .filter((v) => v !== null);
      return perTestCase.length ? mean(perTestCase) : null;
    });
  }

  function trendValuesForRunMetric(selector) {
    return DATA.runs.map((run) => {
      const vals = rowsForRun(run.run_id).map(selector).filter((v) => typeof v === "number");
      return vals.length ? mean(vals) : null;
    });
  }

  const TREND_METRICS = [
    {
      key: "accuracy",
      label: "Accuracy [GEval]",
      hint: "Mean across all questions per run — higher is better.",
      higherIsBetter: true,
      values: () => trendValuesForRunMetric((r) => r.accuracy),
    },
    {
      key: "hallucination-rate",
      label: "Hallucination Rate",
      hint: "Mean across all questions per run — lower is better.",
      higherIsBetter: false,
      values: () => trendValuesForRunMetric((r) => r.hallucination_rate),
    },
    {
      key: "completeness",
      label: "Completeness [GEval]",
      hint: "Mean across all questions per run — higher is better.",
      higherIsBetter: true,
      values: () => trendValuesForRunMetric((r) => r.completeness),
    },
    {
      key: "repeatability",
      label: "Repeatability",
      hint: "Consistency of scores across runs seen so far — higher is better.",
      higherIsBetter: true,
      values: cumulativeRepeatabilityPerRun,
    },
  ];

  function buildTrendChart(runs, values) {
    const width = 480;
    const height = 170;
    const padX = 14;
    const padY = 18;
    const plotW = width - padX * 2;
    const plotH = height - padY * 2;

    const points = [];
    runs.forEach((run, i) => {
      const v = values[i];
      if (typeof v !== "number") return;
      points.push({
        x: padX + (runs.length === 1 ? plotW / 2 : (i / (runs.length - 1)) * plotW),
        y: padY + (1 - v) * plotH,
        run,
        value: v,
      });
    });

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", height);
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      points.length
        ? `${points.length} runs: ` + points.map((p) => `${p.run.label} ${p.value.toFixed(2)}`).join(", ")
        : "No data yet"
    );

    [0, 0.5, 1].forEach((v) => {
      const y = padY + (1 - v) * plotH;
      const line = document.createElementNS(svgNS, "line");
      line.setAttribute("x1", padX);
      line.setAttribute("x2", width - padX);
      line.setAttribute("y1", y);
      line.setAttribute("y2", y);
      line.setAttribute("stroke", "var(--border-hairline)");
      line.setAttribute("stroke-width", "1");
      svg.appendChild(line);

      const tick = document.createElementNS(svgNS, "text");
      tick.setAttribute("x", 2);
      tick.setAttribute("y", y - 3);
      tick.setAttribute("fill", "var(--text-muted)");
      tick.setAttribute("font-family", "var(--font-mono)");
      tick.setAttribute("font-size", "9");
      tick.textContent = v.toFixed(1);
      svg.appendChild(tick);
    });

    if (!points.length) {
      const note = document.createElementNS(svgNS, "text");
      note.setAttribute("x", width / 2);
      note.setAttribute("y", height / 2);
      note.setAttribute("text-anchor", "middle");
      note.setAttribute("fill", "var(--text-muted)");
      note.setAttribute("font-family", "var(--font-mono)");
      note.setAttribute("font-size", "12");
      note.textContent = "No data yet";
      svg.appendChild(note);
      return svg;
    }

    if (points.length >= 2) {
      const pathD = points
        .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
        .join(" ");
      const path = document.createElementNS(svgNS, "path");
      path.setAttribute("d", pathD);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", "var(--accent)");
      path.setAttribute("stroke-width", "2");
      path.setAttribute("stroke-linecap", "round");
      path.setAttribute("stroke-linejoin", "round");
      svg.appendChild(path);
    }

    points.forEach((p) => {
      const ring = document.createElementNS(svgNS, "circle");
      ring.setAttribute("cx", p.x);
      ring.setAttribute("cy", p.y);
      ring.setAttribute("r", "5");
      ring.setAttribute("fill", "var(--surface-2)");
      svg.appendChild(ring);

      const dot = document.createElementNS(svgNS, "circle");
      dot.setAttribute("cx", p.x);
      dot.setAttribute("cy", p.y);
      dot.setAttribute("r", "3.5");
      dot.setAttribute("fill", "var(--accent)");
      svg.appendChild(dot);

      const hit = document.createElementNS(svgNS, "circle");
      hit.setAttribute("cx", p.x);
      hit.setAttribute("cy", p.y);
      hit.setAttribute("r", "12");
      hit.setAttribute("fill", "transparent");
      const title = document.createElementNS(svgNS, "title");
      title.textContent = `${p.run.label} (${p.run.run_id}): ${p.value.toFixed(2)}`;
      hit.appendChild(title);
      svg.appendChild(hit);
    });

    if (points.length === 1) {
      const label = document.createElementNS(svgNS, "text");
      label.setAttribute("x", points[0].x);
      label.setAttribute("y", points[0].y - 10);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("fill", "var(--text-secondary)");
      label.setAttribute("font-family", "var(--font-mono)");
      label.setAttribute("font-size", "11");
      label.textContent = points[0].value.toFixed(2);
      svg.appendChild(label);
    } else {
      [
        { p: points[0], anchor: "start", dx: 6 },
        { p: points[points.length - 1], anchor: "end", dx: -6 },
      ].forEach(({ p, anchor, dx }) => {
        const label = document.createElementNS(svgNS, "text");
        label.setAttribute("x", p.x + dx);
        label.setAttribute("y", p.y - 10);
        label.setAttribute("text-anchor", anchor);
        label.setAttribute("fill", "var(--text-secondary)");
        label.setAttribute("font-family", "var(--font-mono)");
        label.setAttribute("font-size", "11");
        label.textContent = p.value.toFixed(2);
        svg.appendChild(label);
      });
    }

    return svg;
  }

  // ---- PNG export (CSS custom properties don't resolve inside a
  // standalone <img>-rendered SVG, so colors are resolved to concrete
  // values on a clone before serializing) --------------------------------

  function resolveCssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function resolveCssVarsInSvg(svgEl) {
    svgEl.querySelectorAll("*").forEach((el) => {
      ["stroke", "fill"].forEach((attr) => {
        const v = el.getAttribute(attr);
        const m = v && v.match(/^var\((--[\w-]+)\)$/);
        if (m) el.setAttribute(attr, resolveCssVar(m[1]) || v);
      });
    });
  }

  function svgToPngBlob(svg, scale) {
    return new Promise((resolve, reject) => {
      const vb = svg.viewBox.baseVal;
      const w = Math.round(vb.width * scale);
      const h = Math.round(vb.height * scale);

      const clone = svg.cloneNode(true);
      resolveCssVarsInSvg(clone);
      clone.setAttribute("width", w);
      clone.setAttribute("height", h);

      const svgNS = "http://www.w3.org/2000/svg";
      const bg = document.createElementNS(svgNS, "rect");
      bg.setAttribute("x", "0");
      bg.setAttribute("y", "0");
      bg.setAttribute("width", vb.width);
      bg.setAttribute("height", vb.height);
      bg.setAttribute("fill", resolveCssVar("--surface-2"));
      clone.insertBefore(bg, clone.firstChild);

      const xml = new XMLSerializer().serializeToString(clone);
      const svgBlob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(svgBlob);

      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        canvas.getContext("2d").drawImage(img, 0, 0, w, h);
        URL.revokeObjectURL(url);
        canvas.toBlob(
          (blob) => (blob ? resolve(blob) : reject(new Error("toBlob failed"))),
          "image/png"
        );
      };
      img.onerror = (err) => {
        URL.revokeObjectURL(url);
        reject(err);
      };
      img.src = url;
    });
  }

  function blobToImage(blob) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        resolve(img);
      };
      img.onerror = (err) => {
        URL.revokeObjectURL(url);
        reject(err);
      };
      img.src = url;
    });
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function downloadTrendChart(svg, filenameBase) {
    try {
      const blob = await svgToPngBlob(svg, 2);
      downloadBlob(blob, `${filenameBase}.png`);
    } catch (err) {
      window.alert("Could not export this chart as a PNG.");
    }
  }

  async function downloadAllTrendCharts(svgs) {
    try {
      const blobs = await Promise.all(svgs.map((svg) => svgToPngBlob(svg, 2)));
      const images = await Promise.all(blobs.map(blobToImage));

      const cols = 2;
      const rows = Math.ceil(images.length / cols);
      const cellW = Math.max(...images.map((img) => img.width));
      const cellH = Math.max(...images.map((img) => img.height));
      const gap = 32;

      const canvas = document.createElement("canvas");
      canvas.width = cols * cellW + (cols - 1) * gap;
      canvas.height = rows * cellH + (rows - 1) * gap;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = resolveCssVar("--page-plane") || "#0b1214";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      images.forEach((img, i) => {
        const col = i % cols;
        const row = Math.floor(i / cols);
        ctx.drawImage(img, col * (cellW + gap), row * (cellH + gap));
      });

      canvas.toBlob((blob) => {
        if (blob) downloadBlob(blob, "trends-all.png");
      }, "image/png");
    } catch (err) {
      window.alert("Could not export the combined trends image.");
    }
  }

  function renderTrendsGrid() {
    const grid = document.getElementById("trends-grid");
    const emptyEl = document.getElementById("trends-empty");
    grid.textContent = "";

    if (!DATA.runs.length) {
      grid.hidden = true;
      emptyEl.hidden = false;
      return;
    }
    grid.hidden = false;
    emptyEl.hidden = true;

    const svgs = [];

    TREND_METRICS.forEach((metric) => {
      const values = metric.values();

      const card = document.createElement("div");
      card.className = "trend-card";

      const header = document.createElement("div");
      header.className = "trend-card-header";

      const titleWrap = document.createElement("div");
      const title = document.createElement("h3");
      title.className = "card-title";
      title.textContent = metric.label;
      const hint = document.createElement("p");
      hint.className = "card-hint card-hint-flush";
      hint.textContent = metric.hint;
      titleWrap.append(title, hint);

      const actions = document.createElement("div");
      actions.className = "trend-card-actions";

      const validPairs = DATA.runs
        .map((run, i) => ({ run, value: values[i] }))
        .filter((pair) => typeof pair.value === "number");
      if (validPairs.length >= 2) {
        const first = validPairs[0].value;
        const last = validPairs[validPairs.length - 1].value;
        actions.appendChild(deltaSpan(last, first, metric.higherIsBetter));
      }

      const downloadBtn = document.createElement("button");
      downloadBtn.className = "link-btn";
      downloadBtn.textContent = "Download PNG";
      actions.appendChild(downloadBtn);

      header.append(titleWrap, actions);

      const figure = document.createElement("figure");
      figure.className = "trend-figure";
      const svg = buildTrendChart(DATA.runs, values);
      figure.appendChild(svg);
      svgs.push(svg);

      downloadBtn.addEventListener("click", () => downloadTrendChart(svg, `trend-${metric.key}`));

      card.append(header, figure);
      grid.appendChild(card);
    });

    document.getElementById("trends-download-all-btn").onclick = () => downloadAllTrendCharts(svgs);
  }

  // ------------------------------------------------------------------
  // Detail drawer
  // ------------------------------------------------------------------

  let lastFocusedElement = null;

  function buildSparkline(history) {
    // Single-series sparkline: one accent hue, no legend needed (one series).
    const width = 420;
    const height = 100;
    const padX = 10;
    const padY = 14;
    const plotW = width - padX * 2;
    const plotH = height - padY * 2;

    const points = history.map((h, i) => {
      const x = padX + (history.length === 1 ? plotW / 2 : (i / (history.length - 1)) * plotW);
      const y = padY + (1 - h.score) * plotH;
      return { x, y, h };
    });

    const pathD = points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`)
      .join(" ");

    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", "100%");
    svg.setAttribute("height", height);
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      `Score across ${history.length} runs: ` +
        history.map((h) => `${h.run.label} ${h.score.toFixed(2)}`).join(", ")
    );

    // Recessive baseline grid at score = 1.0 and 0.0.
    [0, 1].forEach((v) => {
      const y = padY + (1 - v) * plotH;
      const line = document.createElementNS(svgNS, "line");
      line.setAttribute("x1", padX);
      line.setAttribute("x2", width - padX);
      line.setAttribute("y1", y);
      line.setAttribute("y2", y);
      line.setAttribute("stroke", "var(--border-hairline)");
      line.setAttribute("stroke-width", "1");
      svg.appendChild(line);
    });

    const path = document.createElementNS(svgNS, "path");
    path.setAttribute("d", pathD);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", "var(--accent)");
    path.setAttribute("stroke-width", "2");
    path.setAttribute("stroke-linecap", "round");
    path.setAttribute("stroke-linejoin", "round");
    svg.appendChild(path);

    points.forEach((p) => {
      // Surface ring behind each marker so it stays legible on the line.
      const ring = document.createElementNS(svgNS, "circle");
      ring.setAttribute("cx", p.x);
      ring.setAttribute("cy", p.y);
      ring.setAttribute("r", "6");
      ring.setAttribute("fill", "var(--surface-2)");
      svg.appendChild(ring);

      const dot = document.createElementNS(svgNS, "circle");
      dot.setAttribute("cx", p.x);
      dot.setAttribute("cy", p.y);
      dot.setAttribute("r", "4");
      dot.setAttribute("fill", "var(--accent)");
      svg.appendChild(dot);

      // Enlarged transparent hit target + native tooltip (title) per point.
      const hit = document.createElementNS(svgNS, "circle");
      hit.setAttribute("cx", p.x);
      hit.setAttribute("cy", p.y);
      hit.setAttribute("r", "14");
      hit.setAttribute("fill", "transparent");
      const title = document.createElementNS(svgNS, "title");
      title.textContent = `${p.h.run.label} (${p.h.run.run_id}): ${p.h.score.toFixed(2)} (${p.h.status})`;
      hit.appendChild(title);
      svg.appendChild(hit);
    });

    // Direct label on the endpoint only (selective labeling, not every point).
    const last = points[points.length - 1];
    const label = document.createElementNS(svgNS, "text");
    label.setAttribute("x", last.x - 6);
    label.setAttribute("y", last.y - 10);
    label.setAttribute("text-anchor", "end");
    label.setAttribute("fill", "var(--text-secondary)");
    label.setAttribute("font-family", "var(--font-mono)");
    label.setAttribute("font-size", "11");
    label.textContent = last.h.score.toFixed(2);
    svg.appendChild(label);

    return svg;
  }

  function renderDrawerMetrics(metrics) {
    const section = document.getElementById("drawer-metrics-section");
    const tbody = document.getElementById("drawer-metrics-tbody");
    tbody.textContent = "";

    if (!metrics || !metrics.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;

    metrics.forEach((m) => {
      const tr = document.createElement("tr");

      const nameTd = document.createElement("td");
      nameTd.textContent = m.name;

      const scoreTd = document.createElement("td");
      scoreTd.textContent = m.score === null || m.score === undefined ? "—" : m.score.toFixed(2);

      const resultTd = document.createElement("td");
      resultTd.appendChild(statusBadge(m.success ? "pass" : "fail"));

      const reasonTd = document.createElement("td");
      reasonTd.textContent = m.reason || "—";

      tr.append(nameTd, scoreTd, resultTd, reasonTd);
      tbody.appendChild(tr);
    });
  }

  function renderDrawerHistory(history) {
    const figure = document.getElementById("drawer-sparkline-figure");
    figure.textContent = "";
    figure.appendChild(buildSparkline(history));

    const tbody = document.getElementById("drawer-history-tbody");
    tbody.textContent = "";
    history.forEach((h) => {
      const tr = document.createElement("tr");
      const runTd = document.createElement("td");
      const runLabelSpan = document.createElement("span");
      runLabelSpan.textContent = h.run.label;
      const runIdSpan = document.createElement("span");
      runIdSpan.className = "run-id-tag";
      runIdSpan.textContent = h.run.run_id;
      runTd.append(runLabelSpan, runIdSpan);
      const scoreTd = document.createElement("td");
      scoreTd.textContent = h.score.toFixed(2);
      const statusTd = document.createElement("td");
      statusTd.appendChild(statusBadge(h.status));
      const latencyTd = document.createElement("td");
      latencyTd.textContent = ms(h.latency);
      tr.append(runTd, scoreTd, statusTd, latencyTd);
      tbody.appendChild(tr);
    });
  }

  function openDrawer(testId, contextRunId) {
    const history = historyForTestId(testId);
    const current =
      history.find((h) => h.run_id === contextRunId) || history[history.length - 1];
    if (!current) return;

    lastFocusedElement = document.activeElement;

    document.getElementById("drawer-category").textContent = current.category;
    document.getElementById("drawer-title").textContent = current.test_id;
    document.getElementById("drawer-question").textContent = current.gold_question;
    document.getElementById("drawer-expected").textContent = current.expected_answer;
    document.getElementById("drawer-actual").textContent = current.actual_answer;

    const adapterEl = document.getElementById("drawer-adapter");
    adapterEl.textContent = current.adapter;
    adapterEl.className = "badge badge-adapter";

    document.getElementById("drawer-score").textContent = current.score.toFixed(2);

    const statusEl = document.getElementById("drawer-status");
    statusEl.textContent = current.status;
    statusEl.className = `badge badge-status badge-status-${current.status}`;

    document.getElementById("drawer-latency").textContent = ms(current.latency);

    renderDrawerMetrics(current.metrics);

    renderDrawerHistory(history);
    document.getElementById("drawer-history-table-wrap").hidden = true;
    document.getElementById("drawer-toggle-table").textContent = "View as table";

    const drawer = document.getElementById("drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    backdrop.hidden = false;
    requestAnimationFrame(() => {
      backdrop.classList.add("is-visible");
      drawer.classList.add("is-open");
    });
    drawer.setAttribute("aria-hidden", "false");
    document.getElementById("drawer-close").focus();
  }

  function closeDrawer() {
    const drawer = document.getElementById("drawer");
    const backdrop = document.getElementById("drawer-backdrop");
    drawer.classList.remove("is-open");
    backdrop.classList.remove("is-visible");
    drawer.setAttribute("aria-hidden", "true");
    setTimeout(() => {
      backdrop.hidden = true;
    }, 220);
    if (lastFocusedElement && document.body.contains(lastFocusedElement)) {
      lastFocusedElement.focus();
    }
  }

  function initDrawer() {
    document.getElementById("drawer-close").addEventListener("click", closeDrawer);
    document.getElementById("drawer-backdrop").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && document.getElementById("drawer").classList.contains("is-open")) {
        closeDrawer();
      }
    });
    document.getElementById("drawer-toggle-table").addEventListener("click", (e) => {
      const wrap = document.getElementById("drawer-history-table-wrap");
      wrap.hidden = !wrap.hidden;
      e.target.textContent = wrap.hidden ? "View as table" : "Hide table";
    });
  }

  // ------------------------------------------------------------------
  // Run Now + daily schedule (client-side; requires dashboard/server.py)
  // ------------------------------------------------------------------

  const SCHEDULE_KEY = "evalDashboard.schedule";
  const DAY_MS = 24 * 60 * 60 * 1000;
  const POLL_INTERVAL_MS = 3000;
  const SCHEDULE_CHECK_INTERVAL_MS = 60_000;

  let isRunTriggering = false;

  function readSchedule() {
    try {
      const raw = localStorage.getItem(SCHEDULE_KEY);
      if (!raw) return { enabled: false, nextRunAt: null };
      return JSON.parse(raw);
    } catch (err) {
      return { enabled: false, nextRunAt: null };
    }
  }

  function writeSchedule(schedule) {
    localStorage.setItem(SCHEDULE_KEY, JSON.stringify(schedule));
  }

  function formatNextRun(nextRunAt) {
    if (!nextRunAt) return "";
    return `Next run: ${new Date(nextRunAt).toLocaleString()}`;
  }

  function renderScheduleHint() {
    const schedule = readSchedule();
    const hint = document.getElementById("schedule-hint");
    const toggle = document.getElementById("schedule-toggle");
    toggle.checked = schedule.enabled;
    hint.textContent = schedule.enabled ? formatNextRun(schedule.nextRunAt) : "";
  }

  function setRunButtonRunning(running) {
    const btn = document.getElementById("run-now-btn");
    btn.disabled = running;
    btn.classList.toggle("is-running", running);
    btn.textContent = running ? "Running…" : "Run Now";
  }

  function showRunError(message) {
    const el = document.getElementById("run-error");
    if (!message) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = message;
  }

  async function refreshAfterRun() {
    DATA = await loadData();
    populateOverviewControls();
    renderStatTiles(overviewState.runId);
    renderResultsTable();
    populateRunPicker();
    renderCompareTable();
    populateTestTableRunSelect();
    renderTestTable();
    renderQuestionsTable();
    renderTrendsGrid();
  }

  function pollStatusUntilDone() {
    return new Promise((resolve) => {
      const interval = setInterval(async () => {
        let status;
        try {
          const res = await fetch("/api/status");
          status = await res.json();
        } catch (err) {
          clearInterval(interval);
          resolve({ running: false, last_error: "Lost connection to dashboard/server.py." });
          return;
        }
        if (!status.running) {
          clearInterval(interval);
          resolve(status);
        }
      }, POLL_INTERVAL_MS);
    });
  }

  async function triggerRun() {
    if (isRunTriggering) return;
    isRunTriggering = true;
    setRunButtonRunning(true);
    showRunError(null);

    try {
      const customGoldens = readCustomQuestions().map((q) => ({
        patient_id: q.id,
        input: q.question,
        expected_output: q.expected_answer,
        pass_score: q.pass_score,
        category: q.category,
      }));

      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ custom_goldens: customGoldens }),
      });
      if (res.status === 409) {
        showRunError("A run is already in progress.");
        isRunTriggering = false;
        setRunButtonRunning(false);
        return;
      }
      if (!res.ok) {
        showRunError("Could not start a run. Is dashboard/server.py running?");
        isRunTriggering = false;
        setRunButtonRunning(false);
        return;
      }

      const status = await pollStatusUntilDone();
      if (status.last_error) {
        showRunError(`Run failed: ${status.last_error.split("\n").pop()}`);
      } else {
        await refreshAfterRun();
      }
    } catch (err) {
      showRunError("Could not reach dashboard/server.py. Start it and reload this page.");
    } finally {
      isRunTriggering = false;
      setRunButtonRunning(false);
    }
  }

  function checkSchedule() {
    const schedule = readSchedule();
    if (!schedule.enabled || isRunTriggering) return;
    if (Date.now() >= schedule.nextRunAt) {
      writeSchedule({ enabled: true, nextRunAt: Date.now() + DAY_MS });
      renderScheduleHint();
      triggerRun();
    }
  }

  function initRunControls() {
    document.getElementById("run-now-btn").addEventListener("click", triggerRun);

    document.getElementById("schedule-toggle").addEventListener("change", (e) => {
      if (e.target.checked) {
        writeSchedule({ enabled: true, nextRunAt: Date.now() + DAY_MS });
      } else {
        writeSchedule({ enabled: false, nextRunAt: null });
      }
      renderScheduleHint();
    });

    renderScheduleHint();
    checkSchedule(); // catch-up: runs immediately if overdue from a closed tab
    setInterval(checkSchedule, SCHEDULE_CHECK_INTERVAL_MS);
    setInterval(renderScheduleHint, SCHEDULE_CHECK_INTERVAL_MS);
  }

  // ------------------------------------------------------------------
  // Boot
  // ------------------------------------------------------------------

  async function init() {
    DATA = await loadData();

    initTabs();
    initDrawer();
    initRunControls();
    initTestTableRunSelect();
    initQuestionsTab();

    populateOverviewControls();
    renderStatTiles(overviewState.runId);
    renderResultsTable();

    populateRunPicker();
    renderCompareTable();
    populateTestTableRunSelect();
    renderTestTable();
    renderQuestionsTable();
    renderTrendsGrid();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
