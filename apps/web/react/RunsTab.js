import React, { useState, useCallback, useEffect, useRef } from "react";
import { useAppState } from "./AppContext.js";
import { apiGet } from "./api.js";
import { DEFAULT_PIPELINE_RUN_ROOT, AGENT_BACKEND_FALLBACK_CATALOG } from "./constants.js";
import { MetricsChart, FieldDiffSection } from "./EvaluationTab.js";

/* ── Stage metadata ────────────────────────────────────────── */
const STAGE_STEPS = [
  { key: "stage1", label: "Extract",  short: "S1" },
  { key: "stage2", label: "Analyze",  short: "S2" },
  { key: "stage3", label: "Plan",     short: "S3" },
  { key: "stage4", label: "Inject",   short: "S4" },
  { key: "stage5", label: "Eval",     short: "S5" },
];

const h = React.createElement;

/* ── Agent backend icons & colors (matches Evaluation tab) ─── */
const AGENT_ICONS  = { healthcare:"🏥", finance:"💰", hr:"👥", insurance:"🛡️", education:"🎓", political:"🏛️", general:"🤖" };
const AGENT_COLORS = { healthcare:"#ef4444", finance:"#22c55e", hr:"#3b82f6", insurance:"#f59e0b", education:"#a855f7", political:"#a08060", general:"#6b7280" };

/* Map stage2 domain → agent backend key */
const DOMAIN_TO_AGENT_KEY = {
  healthcare:"healthcare", finance:"finance", hr:"hr", insurance:"insurance",
  education:"education", government:"political", political:"political",
  legal:"hr", technology:"general", other:"general",
};

function resolveAgentMeta(doc) {
  const raw = doc.domain ? doc.domain.toLowerCase() : null;
  const key = raw ? (DOMAIN_TO_AGENT_KEY[raw] || "general") : null;
  if (key) {
    const entry = AGENT_BACKEND_FALLBACK_CATALOG[key] || {};
    return { key, label: entry.title || key, icon: AGENT_ICONS[key] || "🤖", color: AGENT_COLORS[key] || "#6b7280" };
  }
  return { key: "general", label: "Pending Analysis", icon: "📋", color: "#6b7280" };
}

/* ── Scenario metadata (Agent Evaluation cards only) ──────── */
const SCENARIO_META = {
  decision:   { label: "Decision-making Agent",          icon: "⚖️",  color: "#6366f1" },
  scheduling: { label: "Scheduling Agent",               icon: "📅",  color: "#06b6d4" },
  credential: { label: "Credential Verification Agent",  icon: "🪪",  color: "#f59e0b" },
  survey:     { label: "Survey / Link Routing Agent",    icon: "🔗",  color: "#10b981" },
  db:         { label: "Database Agent",                 icon: "🗄️",  color: "#a78bfa" },
};

const SEVERITY_STYLE = {
  high:   { bg: "rgba(248,113,113,0.15)", border: "#f87171", text: "#f87171",  label: "HIGH" },
  medium: { bg: "rgba(251,191,36,0.15)",  border: "#fbbf24", text: "#fbbf24",  label: "MED"  },
  low:    { bg: "rgba(52,211,153,0.15)",  border: "#34d399", text: "#34d399",  label: "LOW"  },
};

const VECTOR_LABELS = {
  decision_flip:            { label: "Decision Flip",    icon: "⚖️" },
  tool_parameter_corruption:{ label: "Tool Corruption",  icon: "🔧" },
  unsafe_routing:           { label: "Unsafe Routing",   icon: "🔀" },
  wrong_entity_binding:     { label: "Entity Binding",   icon: "🔗" },
  persistence_poisoning:    { label: "Persistence",      icon: "💾" },
  resource_inflation:       { label: "Resource Inflate", icon: "📈" },
};

/* ── Pipeline Run Card (MalDoc creation) ──────────────────── */
function PipelineRunCard({ doc, onClick }) {
  const status         = doc.stage_status || {};
  const agentMeta      = resolveAgentMeta(doc);
  const docIdShort     = (doc.doc_id || "").slice(0, 8) + "…";
  const completedCount = STAGE_STEPS.filter(s => status[s.key]).length;
  const allDone        = completedCount === STAGE_STEPS.length;

  return h("article", { className: `pipeline-run-card${allDone ? " all-done" : ""}`, onClick },
    /* Top row */
    h("div", { className: "pipeline-run-card-top" },
      h("span", { className: "run-card-icon" }, agentMeta.icon),
      h("span", { className: "pipeline-run-progress-badge" }, `${completedCount}/${STAGE_STEPS.length} stages`),
    ),

    /* Title — matches evaluation screen agent name */
    h("h4", { className: "run-card-title" }, agentMeta.label),

    /* Doc ID */
    h("code", { className: "run-card-docid" }, docIdShort),

    /* Stage pipeline bar */
    h("div", { className: "pipeline-stage-bar" },
      STAGE_STEPS.map(s =>
        h("div", { key: s.key, className: `pipeline-stage-step${status[s.key] ? " done" : " pending"}` },
          h("div", { className: "pipeline-stage-dot" }, status[s.key] ? "✓" : "○"),
          h("div", { className: "pipeline-stage-label" }, s.short),
        ),
      ),
    ),

    /* Footer */
    h("div", { className: "pipeline-run-card-footer" },
      allDone
        ? h("span", { className: "pipeline-run-status done" }, "✓ Complete")
        : h("span", { className: "pipeline-run-status partial" }, `Running stage ${completedCount + 1}…`),
      h("button", { className: "btn-run-detail", onClick: (e) => { e.stopPropagation(); onClick(); } }, "View Details →"),
    ),
  );
}

/* ── Pipeline Detail Drawer ────────────────────────────────── */
function PipelineDetailDrawer({ doc, onClose }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  const agentMeta = resolveAgentMeta(detail || doc);
  const status    = doc.stage_status || {};
  const completedCount = STAGE_STEPS.filter(s => status[s.key]).length;

  useEffect(() => {
    apiGet(`/api/doc/${encodeURIComponent(doc.doc_id)}/detail`)
      .then(d => { setDetail(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [doc.doc_id]);

  const analysis = detail?.analysis;
  const plan     = detail?.plan;
  const risks    = (analysis?.risk_profile?.primary_risks) || [];

  return h("div", { className: "run-detail-overlay", onClick: (e) => { if (e.target.className === "run-detail-overlay") onClose(); } },
    h("div", { className: "run-detail-drawer" },

      /* Header */
      h("div", { className: "run-detail-header" },
        h("div", { className: "run-detail-title-row" },
          h("span", { className: "run-detail-icon" }, agentMeta.icon),
          h("div", null,
            h("h3", null, agentMeta.label),
            h("code", { className: "run-detail-docid" }, doc.doc_id || ""),
          ),
        ),
        h("div", { className: "run-detail-header-right" },
          h("span", { className: "pipeline-run-progress-badge" }, `${completedCount}/${STAGE_STEPS.length} stages`),
          h("button", { className: "run-detail-close", onClick: onClose }, "×"),
        ),
      ),

      /* Body */
      h("div", { className: "run-detail-body" },

        /* Stage status strip */
        h("div", { className: "pipeline-drawer-stage-bar" },
          STAGE_STEPS.map(s =>
            h("div", { key: s.key, className: `pipeline-drawer-stage-step${status[s.key] ? " done" : " pending"}` },
              h("div", { className: "pipeline-drawer-stage-dot" }, status[s.key] ? "✓" : "○"),
              h("div", { className: "pipeline-drawer-stage-label" }, s.label),
            ),
          ),
        ),

        loading && h("div", { className: "pipeline-detail-loading" }, "Loading details…"),

        /* Analysis summary */
        !loading && analysis && h("div", { className: "run-detail-section" },
          h("h4", null, "Vulnerability Analysis"),
          analysis.domain && h("div", { className: "pipeline-detail-meta" },
            h("span", { className: "pipeline-detail-key" }, "Domain"),
            h("span", { className: "pipeline-detail-val" }, analysis.domain),
          ),
          analysis.summary && h("p", { className: "pipeline-detail-summary" }, analysis.summary),
          h("div", { className: "pipeline-detail-meta" },
            h("span", { className: "pipeline-detail-key" }, "Sensitive Elements"),
            h("span", { className: "pipeline-detail-val" }, analysis.sensitive_element_count ?? 0),
          ),
          risks.length > 0 && h("div", { className: "pipeline-risk-tags" },
            risks.map((r, i) => h("span", { key: i, className: "risk-tag" }, r)),
          ),
        ),

        /* Attack plan summary */
        !loading && plan && h("div", { className: "run-detail-section" },
          h("h4", null, "Manipulation Plan"),
          plan.document_threat_model?.attacker_goal && h("p", { className: "pipeline-detail-summary" },
            h("strong", null, "Goal: "), plan.document_threat_model.attacker_goal,
          ),
          h("div", { className: "pipeline-attack-counts" },
            h("div", { className: "pipeline-attack-stat" },
              h("span", { className: "pipeline-attack-val" }, plan.text_attack_count ?? 0),
              h("span", { className: "pipeline-attack-label" }, "Text Attacks"),
            ),
            h("div", { className: "pipeline-attack-stat" },
              h("span", { className: "pipeline-attack-val" }, plan.image_attack_count ?? 0),
              h("span", { className: "pipeline-attack-label" }, "Image Attacks"),
            ),
            h("div", { className: "pipeline-attack-stat" },
              h("span", { className: "pipeline-attack-val" }, plan.structural_attack_count ?? 0),
              h("span", { className: "pipeline-attack-label" }, "Structural Attacks"),
            ),
          ),
        ),

        !loading && !analysis && !plan && h("p", { className: "pipeline-detail-summary", style: { color: "var(--text-secondary)" } },
          "No stage 2 or stage 3 output available yet for this run.",
        ),
      ),
    ),
  );
}

/* ── Run Detail Drawer ─────────────────────────────────────── */
function RunDetailDrawer({ run, onClose }) {
  const doc  = run.raw || run;
  const meta = resolveAgentMeta(run);
  const sev  = SEVERITY_STYLE[run.severity] || SEVERITY_STYLE.medium;

  const changedRows = Object.entries(doc.targeted_field_diffs || {})
    .filter(([, p]) => p && p.changed)
    .map(([field, p]) => ({ field, clean: String(p.clean ?? ""), attacked: String(p.attacked ?? "") }));
  const changedFallback = [];

  return h("div", { className: "run-detail-overlay", onClick: (e) => { if (e.target.className === "run-detail-overlay") onClose(); } },
    h("div", { className: "run-detail-drawer" },

      /* Header */
      h("div", { className: "run-detail-header" },
        h("div", { className: "run-detail-title-row" },
          h("span", { className: "run-detail-icon" }, meta.icon),
          h("div", null,
            h("h3", null, meta.label),
            h("code", { className: "run-detail-docid" }, run.doc_id || ""),
          ),
        ),
        h("div", { className: "run-detail-header-right" },
          h("span", {
            className: "run-sev-badge",
            style: { background: sev.bg, borderColor: sev.border, color: sev.text },
          }, sev.label),
          h("span", {
            className: `run-compromised-badge${run.compromised ? " yes" : " no"}`,
          }, run.compromised ? "⚠ COMPROMISED" : "✓ SAFE"),
          h("button", { className: "run-detail-close", onClick: onClose }, "×"),
        ),
      ),

      /* Scrollable body */
      h("div", { className: "run-detail-body" },

        /* Quick stats strip */
        h("div", { className: "run-stats-strip" },
          h("div", { className: "run-stat-item" },
            h("span", { className: "run-stat-label" }, "Changed Fields"),
            h("span", { className: "run-stat-value" }, run.changed_target_fields ?? 0),
          ),
          h("div", { className: "run-stat-item" },
            h("span", { className: "run-stat-label" }, "Risk Vectors"),
            h("span", { className: "run-stat-value" }, `${run.fired_vector_count ?? 0} / ${Object.keys(VECTOR_LABELS).length}`),
          ),
          h("div", { className: "run-stat-item" },
            h("span", { className: "run-stat-label" }, "Risk Coverage"),
            h("span", { className: `run-stat-value${(run.risk_pct || 0) > 50 ? " danger" : ""}` }, `${run.risk_pct ?? 0}%`),
          ),
          h("div", { className: "run-stat-item" },
            h("span", { className: "run-stat-label" }, "Latency Ratio"),
            h("span", { className: "run-stat-value" }, `${(run.latency_inflation_ratio || 1.0).toFixed(2)}×`),
          ),
          h("div", { className: "run-stat-item" },
            h("span", { className: "run-stat-label" }, "Clean=Gold"),
            h("span", { className: "run-stat-value" }, run.clean_matches_gold ? "Yes" : "No"),
          ),
          h("div", { className: "run-stat-item" },
            h("span", { className: "run-stat-label" }, "Baseline Fail"),
            h("span", { className: "run-stat-value" }, run.baseline_failure ? "Yes" : "No"),
          ),
        ),

        /* Attack vector chips full list */
        h("div", { className: "run-detail-section" },
          h("h4", null, "Attack Vectors"),
          h("div", { className: "run-vectors-full" },
            Object.entries(run.attack_vectors || {}).map(([key, fired]) => {
              const v = VECTOR_LABELS[key] || { label: key, icon: "⚙️" };
              return h("div", { key, className: `run-vector-chip-full${fired ? " fired" : " clear"}` },
                h("span", null, v.icon, " ", v.label),
                h("span", { className: "chip-status" }, fired ? "FIRED" : "CLEAR"),
              );
            }),
          ),
        ),

        /* Metrics chart */
        h("div", { className: "run-detail-section" },
          h(MetricsChart, { doc }),
        ),

        /* Field diffs */
        h("div", { className: "run-detail-section" },
          h(FieldDiffSection, { changedRows, changedFallback, doc, scenario: run.scenario }),
        ),

        /* Raw JSON */
        h("div", { className: "run-detail-section" },
          h("details", { className: "run-raw-json" },
            h("summary", null, "Raw Metrics JSON"),
            h("pre", { className: "inspect-content json" }, JSON.stringify(doc, null, 2)),
          ),
        ),
      ),
    ),
  );
}

/* ── Run Card ──────────────────────────────────────────────── */
function RunCard({ run, onClick }) {
  const meta = resolveAgentMeta(run);
  const sev  = SEVERITY_STYLE[run.severity] || SEVERITY_STYLE.medium;
  const firedVectors = Object.entries(run.attack_vectors || {}).filter(([, v]) => v);
  const docIdShort   = (run.doc_id || "").slice(0, 8) + "…";

  return h("article", { className: `run-card${run.compromised ? " compromised" : ""}`, onClick },
    /* Top row: agent icon + severity tag */
    h("div", { className: "run-card-top" },
      h("span", { className: "run-card-icon" }, meta.icon),
      h("span", {
        className: "run-sev-badge",
        style: { background: sev.bg, borderColor: sev.border, color: sev.text },
      }, sev.label),
    ),

    /* Title — agent backend name matching Evaluation tab */
    h("h4", { className: "run-card-title" }, meta.label),

    /* Doc ID */
    h("code", { className: "run-card-docid" }, docIdShort),

    /* Fired attack vector chips */
    h("div", { className: "run-card-chips" },
      firedVectors.length === 0
        ? h("span", { className: "run-chip clear" }, "✓ No vectors fired")
        : firedVectors.slice(0, 3).map(([key]) => {
            const v = VECTOR_LABELS[key] || { label: key, icon: "⚙️" };
            return h("span", { key, className: "run-chip fired" }, v.icon, " ", v.label);
          }),
      firedVectors.length > 3 && h("span", { className: "run-chip fired" }, `+${firedVectors.length - 3} more`),
    ),

    /* Stats row */
    h("div", { className: "run-card-stats" },
      h("div", { className: "run-card-stat" },
        h("span", { className: "rcs-val" }, run.changed_target_fields ?? 0),
        h("span", { className: "rcs-label" }, "Changed"),
      ),
      h("div", { className: "run-card-stat" },
        h("span", { className: "rcs-val" }, `${run.risk_pct ?? 0}%`),
        h("span", { className: "rcs-label" }, "Risk"),
      ),
      h("div", { className: "run-card-stat" },
        h("span", { className: "rcs-val" }, `${(run.latency_inflation_ratio || 1.0).toFixed(2)}×`),
        h("span", { className: "rcs-label" }, "Latency"),
      ),
    ),

    /* Footer */
    h("div", { className: "run-card-footer" },
      h("span", { className: `run-compromised-badge${run.compromised ? " yes" : " no"}` },
        run.compromised ? "⚠ COMPROMISED" : "✓ SAFE",
      ),
      h("button", { className: "btn-run-detail", onClick: (e) => { e.stopPropagation(); onClick(); } }, "View Details →"),
    ),
  );
}

/* ── RunsTab ───────────────────────────────────────────────── */
export default function RunsTab() {
  const { state, dispatch } = useAppState();
  const evalRuns           = state.runs || [];
  const [pipelineDocs, setPipelineDocs]         = useState([]);
  const [selected, setSelected]                 = useState(null);
  const [selectedPipeline, setSelectedPipeline] = useState(null);

  const refreshAll = useCallback(async () => {
    const root = encodeURIComponent(state.baseRoot || DEFAULT_PIPELINE_RUN_ROOT);

    /* MalDoc creation runs */
    try {
      const payload = await apiGet(`/api/docs?base_root=${root}`);
      setPipelineDocs(payload.items || []);
    } catch (_) {
      setPipelineDocs([]);
    }

    /* Agent evaluation runs */
    try {
      const payload = await apiGet(`/api/runs/docs?base_root=${root}`);
      dispatch({ type: "SET_RUNS", payload: payload.items || [] });
    } catch (_) {
      dispatch({ type: "SET_RUNS", payload: [] });
    }
  }, [state.baseRoot, dispatch]);

  useEffect(() => { refreshAll(); }, []);

  return h("section", { id: "runs", className: "tab-panel active" },
    /* ── Page header ── */
    h("div", { className: "panel-header" },
      h("div", { className: "panel-title-row" },
        h("h2", null, "Runs"),
      ),
    ),

    h("div", { className: "runs-toolbar" },
      h("button", { className: "btn btn-secondary", onClick: refreshAll }, "↺  Refresh"),
    ),

    /* ── Section 1: MalDoc Creation Runs ── */
    h("div", { className: "runs-section" },
      h("div", { className: "runs-section-header" },
        h("h3", null, "🛠 MalDoc Creation Runs"),
        h("span", { className: "runs-count-badge" },
          `${pipelineDocs.length} run${pipelineDocs.length !== 1 ? "s" : ""}`),
      ),
      pipelineDocs.length === 0
        ? h("div", { className: "runs-empty" },
            h("div", { className: "runs-empty-icon" }, "🛠"),
            h("p", null, "No pipeline runs yet."),
            h("p", { className: "hint" }, "Run the pipeline on a PDF to see MalDoc creation progress here."),
          )
        : h("div", { className: "runs-grid" },
            pipelineDocs.map((doc, i) =>
              h(PipelineRunCard, { key: doc.doc_id || i, doc, onClick: () => setSelectedPipeline(doc) }),
            ),
          ),
    ),

    /* ── Section 2: Agent Evaluation Runs ── */
    h("div", { className: "runs-section" },
      h("div", { className: "runs-section-header" },
        h("h3", null, "🔍 Agent Evaluation Runs"),
        h("span", { className: "runs-count-badge" },
          `${evalRuns.length} run${evalRuns.length !== 1 ? "s" : ""}`),
      ),
      evalRuns.length === 0
        ? h("div", { className: "runs-empty" },
            h("div", { className: "runs-empty-icon" }, "🔍"),
            h("p", null, "No evaluation runs yet."),
            h("p", { className: "hint" }, "Run an agent evaluation to see results here."),
          )
        : h("div", { className: "runs-grid" },
            evalRuns.map((run, i) =>
              h(RunCard, {
                key: run.doc_id || i,
                run,
                onClick: () => setSelected(run),
              }),
            ),
          ),
    ),

    selected         && h(RunDetailDrawer,      { run: selected,           onClose: () => setSelected(null) }),
    selectedPipeline && h(PipelineDetailDrawer, { doc: selectedPipeline,   onClose: () => setSelectedPipeline(null) }),
  );
}
