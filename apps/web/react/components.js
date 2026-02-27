import React from "react";
import {
  STAGE_SEQUENCE,
  STAGE5_FLOW_SEQUENCE,
  STAGE5_FLOW_COPY,
  AGENT_DOMAIN_ICONS,
  AGENT_DOMAIN_COLORS,
  formatValue,
} from "./constants.js";

/* ── HealthPill ───────────────────────────────────────────── */
export function HealthPill({ ok, text }) {
  const style = {
    color: ok ? "#34d399" : "#f87171",
    borderColor: ok ? "rgba(52,211,153,0.4)" : "rgba(248,113,113,0.4)",
    background: ok ? "rgba(52,211,153,0.12)" : "rgba(248,113,113,0.12)",
  };
  const dotStyle = {
    display: "inline-block",
    width: 7, height: 7,
    borderRadius: "50%",
    background: ok ? "#34d399" : "#f87171",
    animation: ok ? "pulseGlow 2s ease-in-out infinite" : "none",
    marginRight: 2,
  };
  return React.createElement("span", { className: "pill", style },
    React.createElement("span", { style: dotStyle }),
    text,
  );
}

/* ── StageCard ────────────────────────────────────────────── */
export function StageCard({ stageKey, title, icon, status, runButton }) {
  const cls = ["stage-card"];
  if (status === "done") cls.push("done");
  if (status === "running") cls.push("running");
  if (status === "failed") cls.push("failed");

  const stateIcon = status === "done" ? "\u2713" : status === "running" ? "\u25CB" : status === "failed" ? "\u2717" : "\u2022";
  const stateText = status === "done" ? "Complete" : status === "running" ? "Running\u2026" : status === "failed" ? "Failed" : "Pending";

  return React.createElement("div", { className: cls.join(" "), "data-stage": stageKey },
    React.createElement("span", { className: "stage-icon" }, icon),
    React.createElement("h4", null, title),
    React.createElement("span", { className: "state" }, stateIcon, " ", stateText),
    runButton ? React.createElement("div", { style: { marginLeft: "auto", flexShrink: 0 } }, runButton) : null,
  );
}

/* ── ProgressBar ──────────────────────────────────────────── */
export function ProgressBar({ percent, label, id, labelId }) {
  return React.createElement("div", { className: "progress-wrap" },
    React.createElement("div", { className: "progress-bar" },
      React.createElement("div", { className: "progress-fill", id, style: { width: `${percent}%` } }),
    ),
    React.createElement("span", { id: labelId }, label),
  );
}

/* ── ResultBox ────────────────────────────────────────────── */
export function ResultBox({ message, muted, id }) {
  return React.createElement("div", { className: `result-box${muted ? " muted" : ""}`, id }, message);
}

/* ── AgentCard ────────────────────────────────────────────── */
export function AgentCard({ domainKey, meta, activeClean, activeAttacked }) {
  const isClean = !!activeClean && domainKey === activeClean;
  const isAttacked = !!activeAttacked && domainKey === activeAttacked;
  const cls = ["agent-card"];
  let statusText = "Idle";
  if (isClean && isAttacked) {
    cls.push("active");
    statusText = "Routed for clean + adversarial";
  } else if (isClean) {
    cls.push("active");
    statusText = "Routed for clean document";
  } else if (isAttacked) {
    cls.push("active");
    statusText = "Routed for adversarial document";
  }

  const colors = AGENT_DOMAIN_COLORS[domainKey] || { bg: "#252830", border: "#3d4155" };
  const icon = AGENT_DOMAIN_ICONS[domainKey] || domainKey;

  return React.createElement("article", { className: cls.join(" "), "data-agent": domainKey },
    React.createElement("div", { className: "agent-card-head" },
      React.createElement("h4", null, meta.title || domainKey),
      React.createElement("span", {
        className: "agent-code",
        title: domainKey,
        style: { background: colors.bg, borderColor: colors.border },
      }, icon),
    ),
    React.createElement("p", { className: "agent-focus" }, meta.focus || ""),
    React.createElement("div", { className: "agent-status" }, statusText),
  );
}

/* ── OutcomeCard ──────────────────────────────────────────── */
export function OutcomeCard({ view, variant }) {
  return React.createElement("section", { className: `outcome-card ${variant}` },
    React.createElement("div", { className: "outcome-top" },
      React.createElement("h4", null, view.panelTitle || ""),
      React.createElement("span", { className: `pill outcome-pill ${view.badgeTone || "neutral"}` }, view.badgeText || "Outcome"),
    ),
    React.createElement("div", { className: "action-ticker" },
      React.createElement("span", { className: `action-glyph glyph-${view.glyph || "decision"}`, "aria-hidden": "true" }),
      React.createElement("span", { className: "action-pulse", "aria-hidden": "true" }),
      React.createElement("span", null, view.actionText || ""),
    ),
    React.createElement("dl", { className: "outcome-grid" },
      (view.fields || []).map((field, i) =>
        React.createElement("div", { className: "outcome-item", key: i },
          React.createElement("dt", null, field.label || ""),
          React.createElement("dd", null, formatValue(field.value)),
        )
      ),
    ),
  );
}

/* ── VerdictBox ───────────────────────────────────────────── */
export function VerdictBox({ verdict }) {
  return React.createElement("div", { className: `verdict-box ${verdict.className}` }, verdict.sentence);
}

/* ── MetricCard ───────────────────────────────────────────── */
export function MetricCard({ label, value }) {
  return React.createElement("div", { className: "metric-card" },
    React.createElement("span", null, label),
    React.createElement("strong", null, value),
  );
}

/* ── Pipeline Stage Cards container ───────────────────── */
export function computePipelineProgress(statusByStage) {
  const doneCount = STAGE_SEQUENCE.filter((s) => statusByStage[s] === "done").length;
  const failedStage = STAGE_SEQUENCE.find((s) => statusByStage[s] === "failed");
  const runningStage = STAGE_SEQUENCE.find((s) => statusByStage[s] === "running");

  let progress = doneCount * 25;
  if (runningStage) progress = Math.min(progress + 10, 95);
  if (failedStage) progress = doneCount * 25;
  if (doneCount === STAGE_SEQUENCE.length) progress = 100;

  let label = "Idle";
  if (failedStage) label = `Failed at ${failedStage.toUpperCase()}`;
  else if (runningStage) label = `Processing ${runningStage.toUpperCase()}...`;
  else if (doneCount === STAGE_SEQUENCE.length) label = "Adversarial document generated";

  return { progress, label };
}

export function computeEvalProgress(statusByStage) {
  const doneCount = STAGE5_FLOW_SEQUENCE.filter((s) => statusByStage[s] === "done").length;
  const failedStage = STAGE5_FLOW_SEQUENCE.find((s) => statusByStage[s] === "failed");
  const runningStage = STAGE5_FLOW_SEQUENCE.find((s) => statusByStage[s] === "running");

  let progress = (doneCount / STAGE5_FLOW_SEQUENCE.length) * 100;
  if (runningStage) progress = Math.min(progress + 8, 96);
  if (failedStage) progress = (doneCount / STAGE5_FLOW_SEQUENCE.length) * 100;
  if (doneCount === STAGE5_FLOW_SEQUENCE.length) progress = 100;

  let label = "Idle";
  const flowLabel = (k) => (STAGE5_FLOW_COPY[k] || {}).title || k;
  if (failedStage) label = `Failed at ${flowLabel(failedStage)}`;
  else if (runningStage) label = `Processing ${flowLabel(runningStage)}...`;
  else if (doneCount === STAGE5_FLOW_SEQUENCE.length) label = "Evaluation completed";

  return { progress, label };
}
