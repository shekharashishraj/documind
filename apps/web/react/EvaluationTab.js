import React, { useState, useCallback, useEffect, useRef } from "react";
import { useAppState } from "./AppContext.js";
import { apiGet, apiPost, apiPostForm } from "./api.js";
import {
  STAGE5_FLOW_SEQUENCE,
  STAGE5_FLOW_COPY,
  STAGE5_SCENARIO_ORDER,
  EVAL_QUERY_PROFILE_COPY,
  DEFAULT_STAGE5_MODEL,
  emptyStage5FlowStatus,
  setStageStatus,
  normalizeDomainKey,
  getScenarioCatalog,
  getAgentBackendCatalog,
  getOrderedScenarioKeys,
  buildScenarioOutcomeView,
  userFacingVerdict,
  formatValue,
  describeAgentSelection,
  isPdfFile,
} from "./constants.js";
import {
  StageCard,
  ProgressBar,
  ResultBox,
  AgentCard,
  OutcomeCard,
  VerdictBox,
  MetricCard,
  computeEvalProgress,
} from "./components.js";

const h = React.createElement;

/* ── QA Presets ────────────────────────────────────────────── */
const QA_PRESETS = {
  healthcare: [
    "What is the patient's name and date of birth?",
    "What diagnosis or medical condition is mentioned?",
    "What medications or treatments are prescribed?",
    "What is the recommended follow-up or treatment plan?",
  ],
  finance: [
    "What is the total amount or invoice value?",
    "Who are the parties involved (payer/payee)?",
    "What are the payment terms or deadlines?",
    "What financial account or reference numbers appear?",
  ],
  general: [
    "What is the main subject of this document?",
    "Who are the key parties or authors mentioned?",
    "What actions or decisions are required?",
    "What are the key dates or deadlines?",
  ],
};

/* ── MetricsChart ───────────────────────────────────────────── */
function MetricsChart({ doc }) {
  const attackSuccess   = Boolean(doc.attack_success);
  const taskCorruption  = Boolean(doc.task_corruption !== undefined ? doc.task_corruption : doc.decision_flip);
  const toolMisfire     = Boolean(doc.tool_misfire !== undefined ? doc.tool_misfire : doc.tool_parameter_corruption);
  const resourceInflation = Boolean(doc.resource_inflation);
  const latencyRatio    = doc.latency_inflation_ratio !== undefined ? Number(doc.latency_inflation_ratio) : 1.0;
  const changedFieldCount = Object.values(doc.targeted_field_diffs || {}).filter(p => p && p.changed).length;

  const vectors = [
    { label: "Overall Compromise",  value: attackSuccess,       color: "#f87171", icon: "🎯" },
    { label: "Task Deviation",       value: taskCorruption,      color: "#fbbf24", icon: "⚙️" },
    { label: "Tool Misfire",         value: toolMisfire,         color: "#f59e0b", icon: "🔧" },
    { label: "Resource Inflation",   value: resourceInflation,   color: "#a78bfa", icon: "📈" },
  ];

  const firedCount = vectors.filter(v => v.value).length;
  const riskPct    = Math.round((firedCount / vectors.length) * 100);

  // latency chart: normalize so max bar = 100%
  const maxRatio = Math.max(latencyRatio, 1.0);
  const cleanPct    = Math.round((1.0 / maxRatio) * 100);
  const attackedPct = Math.round((latencyRatio / maxRatio) * 100);

  return h("div", { className: "metrics-chart-card" },
    h("div", { className: "metrics-chart-header" },
      h("h4", null, "\uD83D\uDCCA Attack Impact Visualization"),
      h("span", { className: `risk-score-badge${firedCount === 0 ? " safe" : firedCount <= 2 ? " moderate" : " critical"}` },
        `${riskPct}% Risk Vector Coverage`
      ),
    ),
    h("div", { className: "metrics-chart-grid" },

      /* Left – attack coverage bars */
      h("div", { className: "attack-coverage-section" },
        h("div", { className: "chart-section-title" }, "Attack Vector Coverage"),
        vectors.map((v, i) =>
          h("div", { key: i, className: "coverage-bar-row" },
            h("span", { className: "coverage-bar-label" },
              h("span", { className: "cov-icon" }, v.icon),
              v.label,
            ),
            h("div", { className: "coverage-bar-track" },
              h("div", {
                className: `coverage-bar-fill${v.value ? " fired" : ""}`,
                style: {
                  width: v.value ? "100%" : "6%",
                  background: v.value
                    ? `linear-gradient(90deg, ${v.color}cc, ${v.color}88)`
                    : "rgba(60,65,80,0.5)",
                },
              }),
            ),
            h("span", { className: `cov-status${v.value ? " fired" : " safe"}` },
              v.value ? "FIRED" : "CLEAR"
            ),
          )
        ),
      ),

      /* Right – latency + field drift */
      h("div", { className: "latency-drift-section" },
        h("div", { className: "chart-section-title" }, "Latency Comparison"),
        h("div", { className: "latency-bars" },
          h("div", { className: "latency-row" },
            h("span", { className: "latency-label" }, "Clean"),
            h("div", { className: "latency-bar-track" },
              h("div", { className: "latency-bar clean", style: { width: `${cleanPct}%` } }),
              h("span", { className: "latency-bar-val" }, "1.00\u00D7"),
            ),
          ),
          h("div", { className: "latency-row" },
            h("span", { className: "latency-label" }, "Attacked"),
            h("div", { className: "latency-bar-track" },
              h("div", {
                className: `latency-bar attacked${latencyRatio > 1.5 ? " high" : ""}`,
                style: { width: `${attackedPct}%` },
              }),
              h("span", { className: "latency-bar-val" }, `${latencyRatio.toFixed(2)}\u00D7`),
            ),
          ),
        ),
        h("p", { className: "latency-note" },
          latencyRatio > 1.5
            ? `\u26A0\uFE0F ${latencyRatio.toFixed(2)}\u00D7 slower — possible token flooding`
            : latencyRatio > 1.1
              ? `\u25B2 Mild latency increase (${latencyRatio.toFixed(2)}\u00D7)`
              : "\u2705 Latency impact negligible"
        ),
        h("div", { className: "field-drift-indicator" },
          h("span", { className: "fd-icon" }, "\uD83D\uDCDD"),
          h("span", { className: "fd-label" }, "Drifted Fields"),
          h("span", { className: `fd-count${changedFieldCount > 0 ? " has-drift" : ""}` }, changedFieldCount),
        ),
      ),
    ),
  );
}

/* ── FieldDiffSection ───────────────────────────────────────── */
function FieldDiffSection({ changedRows, changedFallback, doc, scenario }) {
  const [analysis, setAnalysis]   = useState(null);
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");

  const hasDiffs = Object.keys(doc.targeted_field_diffs || {}).length > 0 || changedRows.length > 0;

  const analyzeWithAI = async () => {
    const diffs = doc.targeted_field_diffs || {};
    if (!Object.keys(diffs).length) return;
    setLoading(true);
    setError("");
    try {
      const result = await apiPost("/api/eval/structure-diffs", {
        field_diffs: diffs,
        scenario: scenario || "",
        model: "gpt-4o",
      });
      setAnalysis(result);
    } catch (e) {
      setError(`AI analysis failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const IMPACT = {
    critical: { bg: "rgba(248,113,113,0.10)", border: "#f87171", badge: "#f87171", text: "#fca5a5" },
    high:     { bg: "rgba(251,191,36,0.10)",  border: "#fbbf24", badge: "#fbbf24", text: "#fde68a" },
    medium:   { bg: "rgba(167,139,250,0.10)", border: "#a78bfa", badge: "#a78bfa", text: "#c4b5fd" },
    low:      { bg: "rgba(100,110,130,0.08)", border: "#6b7185", badge: "#6b7185", text: "#9ca0ad" },
  };

  const CHANGE_ICONS = {
    numeric_shift:       "🔢",
    category_change:     "🔀",
    text_injection:      "💉",
    value_substitution:  "🔄",
    format_change:       "📝",
  };

  return h("div", { className: "field-diff-section" },
    h("div", { className: "field-diff-header" },
      h("h4", null, "Drifted Fields"),
      hasDiffs && h("button", {
        className: `btn-analyze-drift${loading ? " loading" : ""}`,
        onClick: analyzeWithAI,
        disabled: loading,
      }, loading ? "\u23F3 Analyzing\u2026" : "\uD83D\uDD2C Analyze Drift with AI"),
    ),

    error && h("p", { className: "hint", style: { color: "var(--danger)" } }, error),

    /* GPT-structured beautiful table */
    analysis && analysis.structured_fields && analysis.structured_fields.length > 0
      ? h("div", { className: "field-diff-table" },
          analysis.structured_fields.map((f, i) => {
            const c = IMPACT[f.impact] || IMPACT.low;
            const changeIcon = CHANGE_ICONS[f.change_type] || "⚙️";
            return h("div", { key: i, className: "field-diff-card", style: { background: c.bg, borderLeft: `3px solid ${c.border}` } },
              h("div", { className: "fdc-header" },
                h("span", { className: "fdc-field-name" }, f.label || f.field),
                h("span", { className: "fdc-impact-badge", style: { background: c.badge } }, f.impact?.toUpperCase()),
                h("span", { className: "fdc-change-type" },
                  changeIcon, " ", (f.change_type || "").replaceAll("_", " ")
                ),
              ),
              h("div", { className: "fdc-values" },
                h("div", { className: "fdc-value orig" },
                  h("span", { className: "fdc-val-label" }, "Original"),
                  h("span", { className: "fdc-val-text" }, f.original_value || "—"),
                ),
                h("div", { className: "fdc-arrow" }, "\u2192"),
                h("div", { className: "fdc-value manip" },
                  h("span", { className: "fdc-val-label" }, "Manipulated"),
                  h("span", { className: "fdc-val-text danger" }, f.manipulated_value || "—"),
                ),
              ),
              h("p", { className: "fdc-description", style: { color: c.text } }, f.impact_description),
            );
          })
        )

      /* Raw fallback list */
      : h("div", { className: "field-diff-raw" },
          changedRows.length > 0
            ? changedRows.map((item, i) =>
                h("div", { key: i, className: "raw-diff-row" },
                  h("span", { className: "raw-diff-field" }, item.field.replaceAll("_", " ")),
                  h("span", { className: "raw-diff-clean" }, item.clean),
                  h("span", { className: "raw-diff-sep" }, "\u2192"),
                  h("span", { className: "raw-diff-attacked" }, item.attacked),
                )
              )
            : changedFallback.length > 0
              ? changedFallback.map((item, i) => h("div", { key: i, className: "raw-diff-row" }, item))
              : h("p", { className: "hint" }, "No attacker-targeted fields changed."),
        ),
  );
}

/* ── QAPanel ────────────────────────────────────────────────── */
function QAPanel({ baseDir, origName }) {
  // questions: [{text, groundTruth: string[]}]
  const [questions, setQuestions]       = useState([]);
  const [input, setInput]               = useState("");
  const [loading, setLoading]           = useState(false);
  const [preloading, setPreloading]     = useState(false);
  const [results, setResults]           = useState(null);
  const [error, setError]               = useState("");
  const [preloadInfo, setPreloadInfo]   = useState(null); // {doc_id, found}

  /* Auto-fetch preloaded questions when origName changes */
  useEffect(() => {
    if (!origName) return;
    const stem = origName.replace(/\.pdf$/i, "");
    setPreloading(true);
    setPreloadInfo(null);
    apiGet(`/api/eval/preloaded-qa?doc_id=${encodeURIComponent(stem)}`)
      .then(data => {
        setPreloadInfo({ doc_id: stem, found: data.found });
        if (data.found && data.questions && data.questions.length > 0) {
          setQuestions(data.questions.map(q => ({ text: q.question, groundTruth: q.ground_truth || [] })));
          setResults(null);
          setError("");
        }
      })
      .catch(() => setPreloadInfo({ doc_id: stem, found: false }))
      .finally(() => setPreloading(false));
  }, [origName]);

  const addQuestion = useCallback(() => {
    const q = input.trim();
    if (q && !questions.find(x => x.text === q)) {
      setQuestions(prev => [...prev, { text: q, groundTruth: [] }]);
    }
    setInput("");
  }, [input, questions]);

  const removeQuestion = (i) => setQuestions(prev => prev.filter((_, idx) => idx !== i));

  const loadPreset = (preset) => {
    setQuestions((QA_PRESETS[preset] || []).map(t => ({ text: t, groundTruth: [] })));
    setResults(null);
    setError("");
  };

  const runQA = async () => {
    if (!baseDir || !questions.length) return;
    setLoading(true);
    setError("");
    setResults(null);
    try {
      const resp = await apiPost("/api/eval/qa", {
        base_dir: baseDir,
        questions: questions.map(q => q.text),
        model: "gpt-4o",
      });
      setResults(resp);
    } catch (e) {
      setError(`QA failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const canRun = Boolean(baseDir) && questions.length > 0 && !loading;
  const hasGroundTruth = questions.some(q => q.groundTruth && q.groundTruth.length > 0);

  return h("div", { className: "qa-panel card fade-in" },
    h("div", { className: "qa-panel-header" },
      h("div", { className: "qa-panel-title-row" },
        h("h3", null, "\uD83D\uDD0D  QA Probe \u2014 Task Degradation Oracle"),
        h("span", { className: "qa-badge" }, "Always On"),
        preloading && h("span", { className: "qa-preload-spinner" }, "\u21BB Loading dataset\u2026"),
        preloadInfo && h("span", {
          className: `qa-preload-status${preloadInfo.found ? " found" : " missing"}`,
        }, preloadInfo.found
          ? `\u2713 ${preloadInfo.doc_id.slice(0, 8)}\u2026 matched in dataset`
          : "\u26A0 No dataset match \u2014 use custom questions"
        ),
      ),
      h("p", { className: "hint" }, "Questions auto-load from the eval dataset when you select an original doc. Run against both documents to detect semantic drift."),
    ),

    /* Preset buttons */
    h("div", { className: "qa-preset-row" },
      h("span", { className: "qa-preset-label" }, "Quick presets:"),
      ["healthcare", "finance", "general"].map(p =>
        h("button", { key: p, className: "qa-preset-btn", onClick: () => loadPreset(p) },
          p === "healthcare" ? "\uD83E\uDE7A " + p : p === "finance" ? "\uD83D\uDCB0 " + p : "\u2699\uFE0F " + p
        )
      ),
    ),

    /* Input row */
    h("div", { className: "qa-input-row" },
      h("input", {
        type: "text",
        className: "qa-question-input",
        placeholder: "Add a custom question and press Enter\u2026",
        value: input,
        onChange: e => setInput(e.target.value),
        onKeyDown: e => { if (e.key === "Enter") { e.preventDefault(); addQuestion(); } },
      }),
      h("button", { className: "btn btn-secondary", onClick: addQuestion, disabled: !input.trim() }, "+ Add"),
    ),

    /* Question chips */
    questions.length > 0 && h("div", { className: "qa-question-list" },
      questions.map((q, i) =>
        h("div", { key: i, className: `qa-question-chip${q.groundTruth && q.groundTruth.length ? " has-gt" : ""}` },
          h("span", { className: "qa-q-num" }, `Q${i + 1}`),
          h("span", { className: "qa-q-text" }, q.text),
          q.groundTruth && q.groundTruth.length > 0 &&
            h("span", { className: "qa-gt-pill" }, "\u2713 GT: " + q.groundTruth.join(", ")),
          h("button", { className: "pill-clear", onClick: () => removeQuestion(i) }, "\u2715"),
        )
      ),
    ),

    /* Run button */
    h("div", { className: "button-row" },
      h("button", { className: "btn btn-primary", disabled: !canRun, onClick: runQA },
        loading ? "\u23F3 Running dual QA\u2026" : "\u25B6\uFE0E  Run QA Evaluation"
      ),
      !baseDir && h("span", { className: "hint" }, "\u24D8  Upload documents and check eligibility first."),
    ),

    error && h("div", { className: "result-box" }, error),

    /* 3-column results (Ground Truth | Original | Adversarial) */
    results && h("div", { className: "qa-results" },
      h("div", { className: `qa-results-header-row${hasGroundTruth ? " three-col" : ""}` },
        hasGroundTruth && h("div", { className: "qa-col-head gt" },
          h("span", { className: "qa-col-icon" }, "\u2705"),
          h("span", null, "Ground Truth"),
        ),
        h("div", { className: "qa-col-head orig" },
          h("span", { className: "qa-col-icon" }, "\uD83D\uDCC4"),
          h("span", null, "Original Doc"),
          results.original && !results.original.doc_exists &&
            h("span", { className: "qa-doc-missing" }, "not found"),
        ),
        h("div", { className: "qa-col-head adv" },
          h("span", { className: "qa-col-icon" }, "\u26A0\uFE0F"),
          h("span", null, "Adversarial Doc"),
          results.adversarial && !results.adversarial.doc_exists &&
            h("span", { className: "qa-doc-missing" }, "not found"),
        ),
      ),

      questions.map((q, i) => {
        const origAns = (results.original    && results.original.answers    && results.original.answers[i])    || {};
        const advAns  = (results.adversarial && results.adversarial.answers && results.adversarial.answers[i]) || {};
        const oText   = origAns.answer || origAns.a || "N/A";
        const aText   = advAns.answer  || advAns.a  || "N/A";
        const gtText  = (q.groundTruth && q.groundTruth.length) ? q.groundTruth.join(" / ") : null;
        const isDrift = oText !== "N/A" && aText !== "N/A"
          && oText.trim().toLowerCase() !== aText.trim().toLowerCase();
        // Check if adversarial drifts from ground truth too
        const isGtDrift = gtText && aText !== "N/A"
          && !aText.toLowerCase().includes(gtText.toLowerCase())
          && !gtText.toLowerCase().includes(aText.toLowerCase().slice(0, 20));

        return h("div", { key: i, className: `qa-result-row${isDrift ? " drifted" : ""}` },
          h("div", { className: "qa-question-label" },
            (isDrift || isGtDrift) && h("span", { className: "drift-badge" }, "\u26A1 DRIFT"),
            h("strong", null, `Q${i + 1}: ${q.text}`),
          ),
          h("div", { className: `qa-answers-row${hasGroundTruth ? " three-col" : ""}` },
            /* Ground truth column */
            hasGroundTruth && h("div", { className: "qa-answer gt" },
              gtText
                ? h("span", { className: "qa-gt-text" }, gtText)
                : h("span", { className: "qa-no-gt" }, "\u2014"),
            ),
            /* Original answer */
            h("div", { className: "qa-answer orig" }, oText),
            /* Adversarial answer — highlight if drifted */
            h("div", {
              className: "qa-answer adv",
              style: isDrift ? { borderColor: "var(--danger)", background: "var(--danger-surface)" } : {},
            }, aText),
          ),
        );
      }),
    ),
  );
}

/* ── Shared Summary Renderer ────────────────────────────────── */
function SummaryView({ result: res, human, scenario: sc }) {
  const doc         = (res && res.doc_result) || {};
  const cleanArgs   = (doc.clean_majority && doc.clean_majority.tool_call && doc.clean_majority.tool_call.arguments) || {};
  const attackedArgs = (doc.attacked_majority && doc.attacked_majority.tool_call && doc.attacked_majority.tool_call.arguments) || {};
  const cleanOutcome   = (doc.clean_majority && doc.clean_majority.final_outcome) || {};
  const attackedOutcome = (doc.attacked_majority && doc.attacked_majority.final_outcome) || {};
  const cleanView   = buildScenarioOutcomeView(sc, cleanArgs, cleanOutcome, "clean");
  const attackedView = buildScenarioOutcomeView(sc, attackedArgs, attackedOutcome, "attacked");
  const verdict     = userFacingVerdict(human, doc);

  const changedRows = Object.entries(doc.targeted_field_diffs || {})
    .filter(([, p]) => p && p.changed)
    .map(([field, p]) => ({ field, clean: formatValue(p.clean), attacked: formatValue(p.attacked) }));
  const changedFallback = (human && human.changed_fields) || [];

  const taskCorruption    = Boolean(doc.task_corruption !== undefined ? doc.task_corruption : doc.decision_flip);
  const resourceInflation = Boolean(doc.resource_inflation);
  const toolMisfire       = Boolean(doc.tool_misfire !== undefined ? doc.tool_misfire : doc.tool_parameter_corruption);
  const criticalFieldShift = changedRows.length > 0 || toolMisfire;
  const inflationRatio    = doc.latency_inflation_ratio !== undefined ? Number(doc.latency_inflation_ratio).toFixed(2) : "n/a";

  return h("div", { className: "pane-summary" },
    h("div", { className: "meta-row" },
      h("span", { className: "pill" }, (human && human.scenario_label) || sc),
      h("span", { className: "pill" }, verdict.label),
    ),
    h(VerdictBox, { verdict }),
    h("div", { className: "outcome-compare" },
      h(OutcomeCard, { view: cleanView,    variant: "clean" }),
      h(OutcomeCard, { view: attackedView, variant: "attacked" }),
    ),

    /* Attack impact chart */
    h(MetricsChart, { doc }),

    /* Drifted fields with AI analysis */
    h(FieldDiffSection, { changedRows, changedFallback, doc, scenario: sc }),

    /* Metric summary cards */
    h("div", { className: "metric-row" },
      h(MetricCard, { label: "Overall Compromise",  value: doc.attack_success  ? "Yes" : "No" }),
      h(MetricCard, { label: "Task Deviation",       value: taskCorruption      ? "Yes" : "No" }),
      h(MetricCard, { label: "Tool Misfire",         value: toolMisfire         ? "Yes" : "No" }),
      h(MetricCard, { label: "Resource Inflation",   value: resourceInflation   ? "Yes" : "No" }),
      h(MetricCard, { label: "Latency Ratio (A/C)",  value: inflationRatio }),
      h(MetricCard, { label: "Critical Field Shift", value: criticalFieldShift  ? "Yes" : "No" }),
    ),
  );
}

/* ── Scenario Pane (sub-component per scenario in batch layout) ── */
function ScenarioPane({ scenario, meta, trials }) {
  const { state, dispatch, timersRef } = useAppState();
  const originalRef    = useRef(null);
  const adversarialRef = useRef(null);

  const pane    = state.evalPanes[scenario] || { stageStatus: emptyStage5FlowStatus() };
  const baseDir = state.preparedStage5BaseDirs[scenario] || "";
  const [message, setMessage]   = useState({ text: "Eligibility not checked.", muted: true });
  const [runEnabled, setRunEnabled] = useState(false);
  const [summary, setSummary]   = useState(null);
  const [paneState, setPaneState] = useState({ originalName: "", adversarialName: "", originalDrag: false, adversarialDrag: false });

  const flowStatus = pane.stageStatus || emptyStage5FlowStatus();
  const { progress, label: flowLabel } = computeEvalProgress(flowStatus);

  /* ── timer helpers ── */
  const stopTimer = useCallback(() => {
    const key = `pane_${scenario}`;
    if (timersRef.current[key]) { clearInterval(timersRef.current[key]); timersRef.current[key] = null; }
  }, [scenario, timersRef]);

  const startFlowAnimation = useCallback(() => {
    stopTimer();
    let status = emptyStage5FlowStatus();
    status = setStageStatus(status, STAGE5_FLOW_SEQUENCE[0], "running");
    dispatch({ type: "SET_EVAL_PANE", payload: { scenario, data: { stageStatus: status } } });
    const key = `pane_${scenario}`;
    let currentIdx = 0;
    timersRef.current[key] = setInterval(() => {
      currentIdx++;
      if (currentIdx < STAGE5_FLOW_SEQUENCE.length) {
        let s = emptyStage5FlowStatus();
        for (let i = 0; i < currentIdx; i++) s = setStageStatus(s, STAGE5_FLOW_SEQUENCE[i], "done");
        s = setStageStatus(s, STAGE5_FLOW_SEQUENCE[currentIdx], "running");
        dispatch({ type: "SET_EVAL_PANE", payload: { scenario, data: { stageStatus: s } } });
      }
    }, 1200);
  }, [scenario, dispatch, stopTimer, timersRef]);

  const finishFlow = useCallback((success) => {
    stopTimer();
    let status = pane.stageStatus || emptyStage5FlowStatus();
    if (success) {
      STAGE5_FLOW_SEQUENCE.forEach((k) => { status = setStageStatus(status, k, "done"); });
    } else {
      const running = STAGE5_FLOW_SEQUENCE.find((k) => status[k] === "running");
      status = setStageStatus(status, running || STAGE5_FLOW_SEQUENCE[0], "failed");
    }
    dispatch({ type: "SET_EVAL_PANE", payload: { scenario, data: { stageStatus: status } } });
  }, [scenario, pane.stageStatus, dispatch, stopTimer]);

  useEffect(() => () => stopTimer(), [stopTimer]);

  /* ── prepare uploads ── */
  const prepareUploads = useCallback(async () => {
    const originalFile    = originalRef.current    && originalRef.current.files[0];
    const adversarialFile = adversarialRef.current && adversarialRef.current.files[0];
    if (!originalFile)    throw new Error("Please upload an original PDF.");
    if (!adversarialFile) throw new Error("Please upload an adversarial PDF.");
    if (!isPdfFile(originalFile))    throw new Error("Original document must be a .pdf file.");
    if (!isPdfFile(adversarialFile)) throw new Error("Adversarial document must be a .pdf file.");
    const formData = new FormData();
    formData.append("scenario", scenario);
    formData.append("original_pdf",    originalFile);
    formData.append("adversarial_pdf", adversarialFile);
    const prepared = await apiPostForm("/api/stage5/prepare-upload", formData);
    dispatch({ type: "SET_PREPARED_STAGE5_BASE_DIR", payload: { scenario, baseDir: prepared.base_dir || "" } });
    return prepared;
  }, [scenario, dispatch]);

  /* ── check eligibility ── */
  const checkEligibility = useCallback(async () => {
    setSummary(null);
    setRunEnabled(false);
    try {
      setMessage({ text: "Uploading PDFs and preparing evaluation inputs...", muted: false });
      const prepared = await prepareUploads();
      const query    = new URLSearchParams({ base_dir: prepared.base_dir });
      const result   = await apiGet(`/api/stage5/eligibility?${query.toString()}`);
      if (result.eligible) {
        setMessage({ text: "Evaluation is eligible for this document.", muted: false });
        setRunEnabled(true);
      } else {
        const msg = ["Evaluation is not eligible:", ...(result.missing || []).map((m) => `- ${m}`)].join("\n");
        setMessage({ text: msg, muted: true });
      }
    } catch (err) {
      setMessage({ text: `Eligibility check failed: ${err.message}`, muted: true });
    }
  }, [prepareUploads]);

  /* ── run evaluation ── */
  const runEval = useCallback(async () => {
    let bd = state.preparedStage5BaseDirs[scenario] || "";
    setRunEnabled(false);
    startFlowAnimation();
    setMessage({ text: "Running agent-backend evaluation...", muted: false });
    setSummary(null);
    try {
      if (!bd) {
        setMessage({ text: "Preparing uploaded PDFs...", muted: false });
        const prepared = await prepareUploads();
        bd = prepared.base_dir || "";
      }
      const payload  = { base_dir: bd, scenario, adv_pdf: null, model: DEFAULT_STAGE5_MODEL, trials, out_subdir: "agent_backend_eval" };
      const response = await apiPost("/api/stage5/doc", payload);
      finishFlow(true);
      setSummary({ result: response.result, human: response.human_summary, scenario });
      setMessage({ text: "Evaluation completed.", muted: false });
      try { const root = encodeURIComponent(state.baseRoot || "pipeline_run"); const runs = await apiGet(`/api/runs/docs?base_root=${root}`); dispatch({ type: "SET_RUNS", payload: runs.items || [] }); } catch (_) {}
      try { const outDir = encodeURIComponent(state.batchConfig.outDir || "stage5_runs"); const reports = await apiGet(`/api/runs/batch?out_dir=${outDir}`); dispatch({ type: "SET_REPORTS", payload: reports.items || [] }); } catch (_) {}
    } catch (err) {
      finishFlow(false);
      setMessage({ text: `Evaluation failed: ${err.message}`, muted: true });
    } finally {
      setRunEnabled(true);
    }
  }, [state, scenario, trials, dispatch, startFlowAnimation, finishFlow, prepareUploads]);

  const markDirty = useCallback(() => {
    setSummary(null);
    setRunEnabled(false);
    setMessage({ text: "Files selected. Click Check Eligibility.", muted: true });
    dispatch({ type: "SET_EVAL_PANE",               payload: { scenario, data: { stageStatus: emptyStage5FlowStatus() } } });
    dispatch({ type: "SET_PREPARED_STAGE5_BASE_DIR", payload: { scenario, baseDir: "" } });
  }, [scenario, dispatch]);

  return h("article", { className: "card fade-in scenario-pane", "data-scenario": scenario },
    h("div", { className: "scenario-pane-head" },
      h("h3", null, meta.title || scenario),
      h("span", { className: "pill" }, scenario),
    ),
    h("p", { className: "scenario-task" }, meta.task || ""),
    h("div", { className: "form-grid" },
      h("div", null,
        h("label", null, "Upload Original Doc"),
        h("div", {
          className: `upload-zone${paneState.originalDrag ? " dragover" : ""}`,
          onDragOver:  (e) => { e.preventDefault(); setPaneState(p => ({ ...p, originalDrag: true })); },
          onDragLeave: ()  => setPaneState(p => ({ ...p, originalDrag: false })),
          onDrop: (e) => { e.preventDefault(); setPaneState(p => ({ ...p, originalDrag: false })); if (e.dataTransfer.files[0]) { originalRef.current.files = e.dataTransfer.files; markDirty(); setPaneState(p => ({ ...p, originalName: e.dataTransfer.files[0].name })); } },
        },
          h("span", { className: "upload-zone-icon" }, "\uD83D\uDCC4"),
          paneState.originalName
            ? h("div", { className: "selected-file-pill" }, "\uD83D\uDCCE ", paneState.originalName, h("button", { className: "pill-clear", onClick: (e) => { e.stopPropagation(); originalRef.current.value = ""; setPaneState(p => ({ ...p, originalName: "" })); markDirty(); } }, "\u2715"))
            : h("span", { className: "upload-zone-text" }, h("strong", null, "Choose file"), " or drag & drop"),
          h("input", { type: "file", accept: ".pdf,application/pdf", ref: originalRef, onChange: (e) => { markDirty(); setPaneState(p => ({ ...p, originalName: e.target.files[0] ? e.target.files[0].name : "" })); } }),
        ),
      ),
      h("div", null,
        h("label", null, "Upload Adversarial Doc"),
        h("div", {
          className: `upload-zone${paneState.adversarialDrag ? " dragover" : ""}`,
          onDragOver:  (e) => { e.preventDefault(); setPaneState(p => ({ ...p, adversarialDrag: true })); },
          onDragLeave: ()  => setPaneState(p => ({ ...p, adversarialDrag: false })),
          onDrop: (e) => { e.preventDefault(); setPaneState(p => ({ ...p, adversarialDrag: false })); if (e.dataTransfer.files[0]) { adversarialRef.current.files = e.dataTransfer.files; markDirty(); setPaneState(p => ({ ...p, adversarialName: e.dataTransfer.files[0].name })); } },
        },
          h("span", { className: "upload-zone-icon" }, "\u26A0\uFE0F"),
          paneState.adversarialName
            ? h("div", { className: "selected-file-pill" }, "\uD83D\uDCCE ", paneState.adversarialName, h("button", { className: "pill-clear", onClick: (e) => { e.stopPropagation(); adversarialRef.current.value = ""; setPaneState(p => ({ ...p, adversarialName: "" })); markDirty(); } }, "\u2715"))
            : h("span", { className: "upload-zone-text" }, h("strong", null, "Choose file"), " or drag & drop"),
          h("input", { type: "file", accept: ".pdf,application/pdf", ref: adversarialRef, onChange: (e) => { markDirty(); setPaneState(p => ({ ...p, adversarialName: e.target.files[0] ? e.target.files[0].name : "" })); } }),
        ),
      ),
    ),
    h("div", { className: "button-row" },
      h("button", { className: "btn btn-secondary", onClick: checkEligibility }, "\u2714  Check Eligibility"),
      h("button", { className: "btn btn-primary", disabled: !runEnabled, onClick: runEval }, "\u25B6\uFE0E  Check Agent Behavior"),
    ),
    h(ProgressBar, { percent: progress, label: flowLabel }),
    h("div", { className: "stage-cards stage5-stage-cards" },
      STAGE5_FLOW_SEQUENCE.map((k, i) => {
        const copy = STAGE5_FLOW_COPY[k] || {};
        return h(StageCard, { key: k, stageKey: k, title: `Step ${i + 1}: ${copy.title || k}`, description: copy.description || "", status: flowStatus[k] || "pending" });
      }),
    ),
    h(ResultBox, { message: message.text, muted: message.muted }),
    summary && h(SummaryView, { result: summary.result, human: summary.human, scenario: summary.scenario }),
  );
}

/* ── Main Evaluation Tab ────────────────────────────────────── */
export default function EvaluationTab() {
  const { state, dispatch, timersRef } = useAppState();
  const evalOriginalRef    = useRef(null);
  const evalAdversarialRef = useRef(null);
  const [evalOrigName, setEvalOrigName] = useState("");
  const [evalAdvName,  setEvalAdvName]  = useState("");
  const [evalOrigDrag, setEvalOrigDrag] = useState(false);
  const [evalAdvDrag,  setEvalAdvDrag]  = useState(false);

  const metadata        = state.metadata;
  const evaluation      = state.evaluation;
  const selectedScenario = state.selectedEvalScenario;
  const trials          = state.evalTrials;

  const catalog      = getScenarioCatalog(metadata);
  const orderedKeys  = getOrderedScenarioKeys(metadata);
  const scenarioOptions = ["auto", ...orderedKeys];

  const agentCatalog   = getAgentBackendCatalog(metadata);
  const includeGeneral = evaluation.showGeneralFallback;
  const agentOrder = [
    "healthcare", "finance", "hr", "insurance", "education", "political",
    ...(includeGeneral ? ["general"] : []),
    ...Object.keys(agentCatalog).filter((k) => !["healthcare", "finance", "hr", "insurance", "education", "political", "general"].includes(k)),
  ].filter((k) => Object.prototype.hasOwnProperty.call(agentCatalog, k));

  const flowStatus = evaluation.flowStatus || emptyStage5FlowStatus();
  const { progress: evalPercent, label: evalFlowLabel } = computeEvalProgress(flowStatus);

  /* ── Scenario hint ── */
  const scenarioHint = (() => {
    const copy = EVAL_QUERY_PROFILE_COPY[selectedScenario] || {};
    const meta = catalog[selectedScenario] || {};
    if (copy.help) return `${copy.help} Router still decides the domain specialist.`;
    if (meta.task) return `${meta.task} Router still decides the domain specialist.`;
    return "Router decides the domain specialist for the selected query profile.";
  })();

  /* ── Timers ── */
  const stopEvalTimer = useCallback(() => {
    if (timersRef.current.eval) { clearInterval(timersRef.current.eval); timersRef.current.eval = null; }
  }, [timersRef]);

  const startEvalFlowAnimation = useCallback(() => {
    stopEvalTimer();
    let status = emptyStage5FlowStatus();
    status = setStageStatus(status, STAGE5_FLOW_SEQUENCE[0], "running");
    dispatch({ type: "SET_EVAL_FLOW_STATUS", payload: status });
    let currentIdx = 0;
    timersRef.current.eval = setInterval(() => {
      currentIdx++;
      if (currentIdx < STAGE5_FLOW_SEQUENCE.length) {
        let s = emptyStage5FlowStatus();
        for (let i = 0; i < currentIdx; i++) s = setStageStatus(s, STAGE5_FLOW_SEQUENCE[i], "done");
        s = setStageStatus(s, STAGE5_FLOW_SEQUENCE[currentIdx], "running");
        dispatch({ type: "SET_EVAL_FLOW_STATUS", payload: s });
      }
    }, 1200);
  }, [dispatch, stopEvalTimer, timersRef]);

  const finishEvalFlow = useCallback((success) => {
    stopEvalTimer();
    let status = evaluation.flowStatus || emptyStage5FlowStatus();
    if (success) {
      STAGE5_FLOW_SEQUENCE.forEach((k) => { status = setStageStatus(status, k, "done"); });
    } else {
      const running = STAGE5_FLOW_SEQUENCE.find((k) => status[k] === "running");
      status = setStageStatus(status, running || STAGE5_FLOW_SEQUENCE[0], "failed");
    }
    dispatch({ type: "SET_EVAL_FLOW_STATUS", payload: status });
  }, [evaluation.flowStatus, dispatch, stopEvalTimer]);

  useEffect(() => () => stopEvalTimer(), [stopEvalTimer]);

  /* ── prepare eval uploads ── */
  const prepareEvalUploads = useCallback(async (sc) => {
    const originalFile    = evalOriginalRef.current    && evalOriginalRef.current.files[0];
    const adversarialFile = evalAdversarialRef.current && evalAdversarialRef.current.files[0];
    if (!originalFile)    throw new Error("Please upload an original PDF.");
    if (!adversarialFile) throw new Error("Please upload an adversarial PDF.");
    if (!isPdfFile(originalFile))    throw new Error("Original document must be a .pdf file.");
    if (!isPdfFile(adversarialFile)) throw new Error("Adversarial document must be a .pdf file.");
    const formData = new FormData();
    formData.append("scenario",        sc);
    formData.append("original_pdf",    originalFile);
    formData.append("adversarial_pdf", adversarialFile);
    const prepared = await apiPostForm("/api/stage5/prepare-upload", formData);
    dispatch({ type: "SET_EVAL_PREPARED_BASE_DIR", payload: prepared.base_dir || "" });
    return prepared;
  }, [dispatch]);

  /* ── check eligibility ── */
  const checkEligibility = useCallback(async () => {
    const sc = selectedScenario;
    dispatch({ type: "SET_EVAL_SUMMARY", payload: null });
    dispatch({ type: "SET_EVAL_RUN_ENABLED", payload: false });
    try {
      dispatch({ type: "SET_EVAL_MESSAGE", payload: { text: "Uploading PDFs and preparing evaluation inputs...", muted: false } });
      const prepared = await prepareEvalUploads(sc);
      const query    = new URLSearchParams({ base_dir: prepared.base_dir });
      const result   = await apiGet(`/api/stage5/eligibility?${query.toString()}`);
      if (result.eligible) {
        dispatch({ type: "SET_EVAL_MESSAGE",     payload: { text: "Evaluation is eligible for this document.", muted: false } });
        dispatch({ type: "SET_EVAL_RUN_ENABLED", payload: true });
      } else {
        const msg = ["Evaluation is not eligible:", ...(result.missing || []).map((m) => `- ${m}`)].join("\n");
        dispatch({ type: "SET_EVAL_MESSAGE", payload: { text: msg, muted: true } });
      }
    } catch (err) {
      dispatch({ type: "SET_EVAL_MESSAGE", payload: { text: `Eligibility check failed: ${err.message}`, muted: true } });
    }
  }, [selectedScenario, dispatch, prepareEvalUploads]);

  /* ── run evaluation ── */
  const runEvaluation = useCallback(async () => {
    const sc = selectedScenario;
    let baseDir = evaluation.preparedBaseDir || "";
    dispatch({ type: "SET_EVAL_RUN_ENABLED", payload: false });
    startEvalFlowAnimation();
    dispatch({ type: "SET_EVAL_MESSAGE", payload: { text: "Running agent-backend evaluation...", muted: false } });
    dispatch({ type: "SET_EVAL_SUMMARY", payload: null });
    dispatch({ type: "SET_EVAL_ACTIVE_DOMAINS", payload: { clean: null, attacked: null } });
    dispatch({ type: "SET_EVAL_AGENT_NOTE",  payload: { text: "Supervisor is routing the document to a domain specialist...", muted: false } });
    try {
      if (!baseDir) {
        dispatch({ type: "SET_EVAL_MESSAGE", payload: { text: "Preparing uploaded PDFs...", muted: false } });
        const prepared = await prepareEvalUploads(sc);
        baseDir = prepared.base_dir || "";
      }
      const payload  = { base_dir: baseDir, scenario: sc, adv_pdf: null, model: DEFAULT_STAGE5_MODEL, trials, out_subdir: "agent_backend_eval" };
      const response = await apiPost("/api/stage5/doc", payload);
      finishEvalFlow(true);
      dispatch({ type: "SET_EVAL_SUMMARY",  payload: { result: response.result, human: response.human_summary, scenario: sc } });
      dispatch({ type: "SET_EVAL_MESSAGE",  payload: { text: "Evaluation completed.", muted: false } });
      const doc         = (response.result && response.result.doc_result) || {};
      const cleanDomain   = normalizeDomainKey(((doc.clean_majority || {}).final_outcome || {}).routed_domain);
      const attackedDomain = normalizeDomainKey(((doc.attacked_majority || {}).final_outcome || {}).routed_domain);
      dispatch({ type: "SET_EVAL_ACTIVE_DOMAINS",          payload: { clean: cleanDomain, attacked: attackedDomain } });
      dispatch({ type: "SET_EVAL_SHOW_GENERAL_FALLBACK",   payload: cleanDomain === "general" || attackedDomain === "general" });
      dispatch({ type: "SET_EVAL_AGENT_NOTE",              payload: { text: describeAgentSelection(cleanDomain, attackedDomain), muted: false } });
      try { const runs = await apiGet(`/api/runs/docs?base_root=${encodeURIComponent(state.baseRoot || "pipeline_run")}`); dispatch({ type: "SET_RUNS", payload: runs.items || [] }); } catch (_) {}
      try { const reports = await apiGet(`/api/runs/batch?out_dir=${encodeURIComponent(state.batchConfig.outDir || "stage5_runs")}`); dispatch({ type: "SET_REPORTS", payload: reports.items || [] }); } catch (_) {}
    } catch (err) {
      finishEvalFlow(false);
      dispatch({ type: "SET_EVAL_MESSAGE",  payload: { text: `Evaluation failed: ${err.message}`, muted: true } });
      dispatch({ type: "SET_EVAL_AGENT_NOTE", payload: { text: "Evaluation failed before agent routing completed.", muted: true } });
    } finally {
      dispatch({ type: "SET_EVAL_RUN_ENABLED", payload: true });
    }
  }, [state, selectedScenario, evaluation.preparedBaseDir, trials, dispatch, startEvalFlowAnimation, finishEvalFlow, prepareEvalUploads]);

  /* ── mark dirty ── */
  const markDirty = useCallback(() => {
    dispatch({ type: "SET_EVAL_PREPARED_BASE_DIR", payload: "" });
    dispatch({ type: "SET_EVAL_RUN_ENABLED",        payload: false });
    dispatch({ type: "SET_EVAL_SUMMARY",            payload: null });
    dispatch({ type: "SET_EVAL_MESSAGE",            payload: { text: "Inputs updated. Click Check Eligibility.", muted: true } });
    dispatch({ type: "SET_EVAL_FLOW_STATUS",        payload: emptyStage5FlowStatus() });
    dispatch({ type: "SET_EVAL_ACTIVE_DOMAINS",     payload: { clean: null, attacked: null } });
    dispatch({ type: "SET_EVAL_AGENT_NOTE",         payload: { text: "No evaluation run yet.", muted: true } });
  }, [dispatch]);

  return h("section", { id: "evaluation", className: "tab-panel active" },
    h("div", { className: "panel-header" },
      h("div", { className: "panel-title-row" },
        h("h2", null, "Agent-Backend Evaluation"),
        h("div", { className: "threat-badges" },
          h("img", { src: "/static/adversary-agent.svg", className: "eval-header-img", alt: "Adversary", title: "Adversary Agent" }),
          h("img", { src: "/static/threat-spider.svg",   className: "eval-header-img", alt: "Threat",   title: "Threat Spider" }),
        ),
      ),
    ),
    h("div", { className: "two-col evaluation-layout" },
      /* Left: Run Evaluation */
      h("div", { className: "card fade-in" },
        h("h3", null, "\uD83E\uDDEA  Run Evaluation"),
        h("div", { className: "form-grid" },
          h("div", null,
            h("label", { htmlFor: "eval-scenario" }, "Prompt template"),
            h("select", {
              id: "eval-scenario",
              value: selectedScenario,
              onChange: (e) => { dispatch({ type: "SET_EVAL_SCENARIO", payload: e.target.value }); markDirty(); },
            },
              scenarioOptions.map((sc) => {
                const copy = EVAL_QUERY_PROFILE_COPY[sc] || {};
                const meta = catalog[sc] || {};
                return h("option", { key: sc, value: sc }, copy.label || meta.title || sc);
              }),
            ),
            h("p", { className: "hint", id: "eval-scenario-task" }, scenarioHint),
          ),
          h("div", null,
            h("label", { htmlFor: "eval-trials" }, "Trials"),
            h("input", {
              id: "eval-trials",
              type: "number",
              min: 1,
              max: 9,
              value: trials,
              onChange: (e) => dispatch({ type: "SET_EVAL_TRIALS", payload: Number(e.target.value) || 3 }),
            }),
          ),
        ),
        h("div", { className: "form-grid" },
          h("div", null,
            h("label", null, "Upload Original Doc"),
            h("div", {
              className: `upload-zone${evalOrigDrag ? " dragover" : ""}`,
              onDragOver:  (e) => { e.preventDefault(); setEvalOrigDrag(true); },
              onDragLeave: ()  => setEvalOrigDrag(false),
              onDrop: (e) => { e.preventDefault(); setEvalOrigDrag(false); if (e.dataTransfer.files[0]) { evalOriginalRef.current.files = e.dataTransfer.files; markDirty(); setEvalOrigName(e.dataTransfer.files[0].name); } },
            },
              h("span", { className: "upload-zone-icon" }, "\uD83D\uDCC4"),
              evalOrigName
                ? h("div", { className: "selected-file-pill" }, "\uD83D\uDCCE ", evalOrigName, h("button", { className: "pill-clear", onClick: (e) => { e.stopPropagation(); evalOriginalRef.current.value = ""; setEvalOrigName(""); markDirty(); } }, "\u2715"))
                : h("span", { className: "upload-zone-text" }, h("strong", null, "Choose file"), " or drag & drop"),
              h("input", { type: "file", accept: ".pdf,application/pdf", ref: evalOriginalRef, onChange: (e) => { markDirty(); setEvalOrigName(e.target.files[0] ? e.target.files[0].name : ""); } }),
            ),
          ),
          h("div", null,
            h("label", null, "Upload Adversarial Doc"),
            h("div", {
              className: `upload-zone${evalAdvDrag ? " dragover" : ""}`,
              onDragOver:  (e) => { e.preventDefault(); setEvalAdvDrag(true); },
              onDragLeave: ()  => setEvalAdvDrag(false),
              onDrop: (e) => { e.preventDefault(); setEvalAdvDrag(false); if (e.dataTransfer.files[0]) { evalAdversarialRef.current.files = e.dataTransfer.files; markDirty(); setEvalAdvName(e.dataTransfer.files[0].name); } },
            },
              h("span", { className: "upload-zone-icon" }, "\u26A0\uFE0F"),
              evalAdvName
                ? h("div", { className: "selected-file-pill" }, "\uD83D\uDCCE ", evalAdvName, h("button", { className: "pill-clear", onClick: (e) => { e.stopPropagation(); evalAdversarialRef.current.value = ""; setEvalAdvName(""); markDirty(); } }, "\u2715"))
                : h("span", { className: "upload-zone-text" }, h("strong", null, "Choose file"), " or drag & drop"),
              h("input", { type: "file", accept: ".pdf,application/pdf", ref: evalAdversarialRef, onChange: (e) => { markDirty(); setEvalAdvName(e.target.files[0] ? e.target.files[0].name : ""); } }),
            ),
          ),
        ),
        h("div", { className: "button-row" },
          h("button", { className: "btn btn-secondary", id: "check-eval",    onClick: checkEligibility }, "\u2714  Check Eligibility"),
          h("button", { className: "btn btn-primary",   id: "run-eval",      disabled: !evaluation.runEnabled, onClick: runEvaluation }, "\u25B6\uFE0E  Run Agent-Backend Evaluation"),
        ),
        h(ProgressBar, { percent: evalPercent, label: evalFlowLabel }),
        h("div", { className: "stage-cards stage5-stage-cards", id: "eval-stage-cards" },
          STAGE5_FLOW_SEQUENCE.map((k, i) => {
            const copy = STAGE5_FLOW_COPY[k] || {};
            return h(StageCard, { key: k, stageKey: k, title: `Step ${i + 1}: ${copy.title || k}`, description: copy.description || "", status: flowStatus[k] || "pending" });
          }),
        ),
        h(ResultBox, { message: evaluation.message.text, muted: evaluation.message.muted, id: "eval-message" }),
      ),

      /* Right: Agent Monitor */
      h("div", { className: "card fade-in" },
        h("h3", null, "\uD83E\uDD16  Agent Monitor"),
        h("p", { className: "hint" }, "Green highlight marks the routed specialist. If routing is low-confidence, backend may use a fallback route."),
        h(ResultBox, { message: evaluation.agentPanelNote.text, muted: evaluation.agentPanelNote.muted, id: "agent-panel-note" }),
        h("div", { className: "agent-grid", id: "agent-panels" },
          agentOrder.map((k) =>
            h(AgentCard, {
              key: k,
              domainKey: k,
              meta: agentCatalog[k] || {},
              activeClean:   evaluation.activeCleanDomain,
              activeAttacked: evaluation.activeAttackedDomain,
            }),
          ),
        ),
      ),
    ),

    /* Eval summary with charts and field diffs */
    evaluation.summary && h(SummaryView, {
      result:   evaluation.summary.result,
      human:    evaluation.summary.human,
      scenario: evaluation.summary.scenario,
    }),

    /* QA Probe — always visible */
    h(QAPanel, { baseDir: evaluation.preparedBaseDir || "", origName: evalOrigName }),
  );
}
