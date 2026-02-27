import React, { useEffect, useCallback } from "react";
import { AppProvider, useAppState } from "./AppContext.js";
import { apiGet } from "./api.js";
import { DEFAULT_PIPELINE_RUN_ROOT } from "./constants.js";
import { HealthPill } from "./components.js";
import PipelineTab from "./PipelineTab.js";
import EvaluationTab from "./EvaluationTab.js";
import RunsTab from "./RunsTab.js";
import ReportsTab from "./ReportsTab.js";

const h = React.createElement;

const TABS = [
  { key: "pipeline", icon: "\u{1F527}", label: "Pipeline" },
  { key: "evaluation", icon: "\u{1F50D}", label: "Evaluation" },
  { key: "runs", icon: "\u{1F4CB}", label: "Runs" },
  { key: "reports", icon: "\u{1F4CA}", label: "Reports" },
];

function AppInner() {
  const { state, dispatch } = useAppState();

  /* ── Bootstrap ── */
  const bootstrap = useCallback(async () => {
    // Health check
    try {
      const health = await apiGet("/api/health");
      dispatch({ type: "SET_HEALTH", payload: { ok: health.status === "ok", text: "API online" } });
    } catch (_) {
      dispatch({ type: "SET_HEALTH", payload: { ok: false, text: "API unreachable" } });
      return;
    }

    // Load metadata
    try {
      const meta = await apiGet("/api/metadata");
      dispatch({ type: "SET_METADATA", payload: meta });

      // Attack mechanisms
      const mechanisms = meta.attack_mechanisms || {};
      const ordered = [];
      if (Object.prototype.hasOwnProperty.call(mechanisms, "auto")) {
        ordered.push(["auto", mechanisms.auto]);
      }
      Object.entries(mechanisms).forEach(([key, label]) => {
        if (key !== "auto") ordered.push([key, label]);
      });
      dispatch({ type: "SET_ATTACK_MECHANISMS", payload: ordered });
      if (ordered.some(([k]) => k === "auto")) {
        dispatch({ type: "SET_SELECTED_ATTACK_MECHANISM", payload: "auto" });
      }

      // Default batch doc IDs
      if (meta.default_demo_doc_ids) {
        dispatch({ type: "SET_BATCH_CONFIG", payload: { docIds: meta.default_demo_doc_ids.join(",") } });
      }
    } catch (_) {
      /* metadata fetch failed — non-critical, defaults used */
    }

    // Load PDFs
    try {
      const root = encodeURIComponent(".");
      const payload = await apiGet(`/api/pdfs?base_root=${root}`);
      dispatch({ type: "SET_PDFS", payload: payload.items || [] });
    } catch (_) {}

    // Load runs
    try {
      const root = encodeURIComponent(DEFAULT_PIPELINE_RUN_ROOT);
      const payload = await apiGet(`/api/runs/docs?base_root=${root}`);
      dispatch({ type: "SET_RUNS", payload: payload.items || [] });
    } catch (_) {}

    // Load reports
    try {
      const payload = await apiGet("/api/runs/batch?out_dir=stage5_runs");
      dispatch({ type: "SET_REPORTS", payload: payload.items || [] });
    } catch (_) {}
  }, [dispatch]);

  useEffect(() => { bootstrap(); }, [bootstrap]);

  const activeTab = state.activeTab;

  return h(React.Fragment, null,
    /* ── Topbar ── */
    h("header", { className: "topbar" },
      h("div", { style: { display: "flex", alignItems: "center", gap: "12px" } },
        h("div", {
          style: {
            width: 36, height: 36, borderRadius: "10px",
            background: "linear-gradient(135deg, #6366f1, #7c3aed)",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "#fff", fontWeight: 800, fontSize: 16,
            boxShadow: "0 2px 8px rgba(99,102,241,0.35)",
          },
        }, "M"),
        h("div", null,
          h("h1", null, "MALDOC: A Modular Red-Teaming Platform for Document Processing AI Agents"),
          h("p", null, "Demonstrating indirect prompt injection risks in agentic systems"),
        ),
      ),
      h("div", { className: "topbar-right" },
        h(HealthPill, { ok: state.health.ok, text: state.health.text }),
      ),
    ),

    /* ── Tabs nav ── */
    h("nav", { className: "tabs" },
      TABS.map((t) =>
        h("button", {
          key: t.key,
          className: `tab${activeTab === t.key ? " active" : ""}`,
          "data-target": t.key,
          onClick: () => dispatch({ type: "SET_ACTIVE_TAB", payload: t.key }),
        }, t.icon, " ", t.label),
      ),
    ),

    /* ── Main content ── */
    h("main", null,
      activeTab === "pipeline" && h(PipelineTab),
      activeTab === "evaluation" && h(EvaluationTab),
      activeTab === "runs" && h(RunsTab),
      activeTab === "reports" && h(ReportsTab),
    ),


  );
}

export default function App() {
  return h(AppProvider, null, h(AppInner));
}
