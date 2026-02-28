import React, { useEffect, useCallback, useState } from "react";
import { AppProvider, useAppState } from "./AppContext.js";
import { apiGet, getStoredApiKey, setStoredApiKey, clearStoredApiKey } from "./api.js";
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
  const [showKeyModal, setShowKeyModal] = useState(() => !getStoredApiKey());
  const [apiKeyInput, setApiKeyInput] = useState("");
  const [rememberKey, setRememberKey] = useState(false);
  const [keyError, setKeyError] = useState("");
  const [hasApiKey, setHasApiKey] = useState(() => Boolean(getStoredApiKey()));

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
  const keyLabel = hasApiKey ? "API Key: Set" : "API Key: Required";

  const saveApiKey = () => {
    const trimmed = apiKeyInput.trim();
    if (!trimmed) {
      setKeyError("Please enter your OpenAI API key to continue.");
      return;
    }
    setStoredApiKey(trimmed, rememberKey);
    setApiKeyInput("");
    setKeyError("");
    setHasApiKey(true);
    setShowKeyModal(false);
  };

  const clearApiKey = () => {
    clearStoredApiKey();
    setHasApiKey(false);
    setShowKeyModal(true);
  };

  return h(React.Fragment, null,
    /* ── Topbar ── */
    h("header", { className: "topbar" },
      h("div", { style: { display: "flex", alignItems: "center", gap: "16px" } },
        h("img", { src: "/static/maldoc-logo.png", className: "topbar-logo", alt: "MalDoc" }),
        h("div", { className: "topbar-tagline" },
          h("p", null, "Modular Red-Teaming Platform for Document Processing AI Agents"),
        ),
      ),
      h("div", { className: "topbar-right" },
        h(HealthPill, { ok: state.health.ok, text: state.health.text }),
        h("button", {
          className: `api-key-pill${hasApiKey ? " ok" : ""}`,
          onClick: () => setShowKeyModal(true),
          title: "Set or update your OpenAI API key",
        }, "\uD83D\uDD11 ", keyLabel),
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

    showKeyModal && h("div", { className: "api-key-overlay" },
      h("div", { className: "api-key-modal" },
        h("div", { className: "api-key-header" },
          h("div", null,
            h("h3", null, "Enter Your OpenAI API Key"),
            h("p", { className: "hint" },
              "Your key stays in your browser and is sent with API requests. It is not stored on the server."
            ),
          ),
          hasApiKey && h("button", { className: "api-key-close", onClick: () => setShowKeyModal(false) }, "\u00D7"),
        ),
        h("div", { className: "api-key-body" },
          h("label", { className: "api-key-label" }, "OpenAI API Key"),
          h("input", {
            className: "api-key-input",
            type: "password",
            placeholder: "sk-...",
            value: apiKeyInput,
            onChange: (e) => setApiKeyInput(e.target.value),
          }),
          h("label", { className: "api-key-remember" },
            h("input", {
              type: "checkbox",
              checked: rememberKey,
              onChange: (e) => setRememberKey(e.target.checked),
            }),
            h("span", null, "Remember on this device"),
          ),
          keyError && h("div", { className: "api-key-error" }, keyError),
        ),
        h("div", { className: "api-key-actions" },
          hasApiKey && h("button", { className: "btn btn-secondary", onClick: clearApiKey }, "Clear Key"),
          h("button", { className: "btn btn-primary", onClick: saveApiKey }, "Save Key"),
        ),
      ),
    ),

  );
}

export default function App() {
  return h(AppProvider, null, h(AppInner));
}
