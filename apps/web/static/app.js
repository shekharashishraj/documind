const state = {
  baseRoot: "pipeline_run",
  pdfs: [],
  metadata: null,
  lastBaseDir: "",
  pipelineStageStatus: null,
  pipelineBusy: false,
  evalPanes: {},
  preparedStage5BaseDirs: {},
  evaluation: {
    preparedBaseDir: "",
    flowStatus: null,
    timer: null,
    activeCleanDomain: null,
    activeAttackedDomain: null,
    showGeneralFallback: false,
  },
};

const STAGE_SEQUENCE = ["stage1", "stage2", "stage3", "stage4"];
const DEFAULT_PIPELINE_RUN_ROOT = "pipeline_run";
const PDF_LISTING_ROOT = ".";
const DEFAULT_STAGE5_MODEL = "gpt-4o";
const STAGE5_SCENARIO_ORDER = ["decision", "scheduling", "db", "credential", "survey"];
const STAGE5_FLOW_SEQUENCE = ["ingest", "route", "execute", "trace", "score"];

const STAGE5_FLOW_COPY = {
  ingest: {
    title: "Ingest",
    description: "Load clean and attacked document text.",
  },
  route: {
    title: "Route",
    description: "Supervisor selects domain specialist.",
  },
  execute: {
    title: "Execute",
    description: "Domain agent answers scenario query.",
  },
  trace: {
    title: "Trace",
    description: "Capture routed domain and execution trace.",
  },
  score: {
    title: "Score",
    description: "Score task deviation, resource inflation, and tool misfire.",
  },
};

const STAGE5_FALLBACK_CATALOG = {
  decision: {
    title: "Decision/Compliance Query",
    task: "Multi-agent supervisor evaluates policy-style documents for final decision outcomes.",
  },
  scheduling: {
    title: "Scheduling Query",
    task: "Multi-agent supervisor extracts scheduling actions (what, when, who, channel).",
  },
  db: {
    title: "Database Query",
    task: "Multi-agent supervisor extracts identifiers for lookup/store style workflows.",
  },
  credential: {
    title: "Credential Verification Query",
    task: "Multi-agent supervisor verifies identity, institution, degree, and date ranges.",
  },
  survey: {
    title: "Survey Routing Query",
    task: "Multi-agent supervisor evaluates URL routing and consent semantics from documents.",
  },
};

const EVAL_QUERY_PROFILE_COPY = {
  auto: {
    label: "Auto Router Check (Recommended)",
    help: "Uses a neutral query and lets the supervisor route by document content.",
  },
  decision: {
    label: "Decision Prompt",
    help: "Asks for final decision/compliance outcome and key decision fields.",
  },
  scheduling: {
    label: "Scheduling Prompt",
    help: "Asks for scheduling actions: what, when, who, and channel.",
  },
  db: {
    label: "Database Prompt",
    help: "Asks for identifier + attributes for lookup/store workflows.",
  },
  credential: {
    label: "Credential Prompt",
    help: "Asks for credential verification fields (holder, institution, degree, date range).",
  },
  survey: {
    label: "Survey Prompt",
    help: "Asks for URL routing + optional/mandatory consent behavior.",
  },
};

const AGENT_BACKEND_FALLBACK_CATALOG = {
  healthcare: {
    title: "Healthcare Agent",
    focus: "Medical records, prescriptions, labs, and clinical context.",
  },
  finance: {
    title: "Finance Agent",
    focus: "Financial statements, invoices, accounting values, and tax context.",
  },
  hr: {
    title: "HR Agent",
    focus: "Resumes, credentials, employment terms, and workforce records.",
  },
  insurance: {
    title: "Insurance Agent",
    focus: "Coverage documents, claims, policies, and benefit constraints.",
  },
  education: {
    title: "Education Agent",
    focus: "Transcripts, diplomas, student records, and academic content.",
  },
  political: {
    title: "Political Agent",
    focus: "Government policies, regulations, and legislative text.",
  },
  general: {
    title: "Fallback Route (General)",
    focus: "Used when router confidence is low or the document spans multiple domains.",
  },
};

function qs(selector) {
  return document.querySelector(selector);
}

function qsa(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function apiGet(path) {
  const resp = await fetch(path);
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(payload.detail || `Request failed: ${resp.status}`);
  }
  return payload;
}

async function apiPost(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(payload.detail || `Request failed: ${resp.status}`);
  }
  return payload;
}

async function apiPostForm(path, formData) {
  const resp = await fetch(path, {
    method: "POST",
    body: formData,
  });
  const payload = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(payload.detail || `Request failed: ${resp.status}`);
  }
  return payload;
}

function setHealth(ok, text) {
  const pill = qs("#health-indicator");
  pill.textContent = text;
  pill.style.color = ok ? "#067647" : "#b42318";
  pill.style.borderColor = ok ? "#a6f4c5" : "#fecdca";
  pill.style.background = ok ? "#ecfdf3" : "#fef3f2";
}

function activateTab(target) {
  qsa(".tab").forEach((btn) => btn.classList.toggle("active", btn.dataset.target === target));
  qsa(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === target));
}

function applyStageCardState(card, stateValue) {
  card.classList.remove("done", "running", "failed");
  if (stateValue === "done") {
    card.classList.add("done");
  }
  if (stateValue === "running") {
    card.classList.add("running");
  }
  if (stateValue === "failed") {
    card.classList.add("failed");
  }

  const stateEl = card.querySelector(".state");
  if (!stateEl) {
    return;
  }
  if (stateValue === "done") {
    stateEl.textContent = "Complete";
    return;
  }
  if (stateValue === "running") {
    stateEl.textContent = "Running";
    return;
  }
  if (stateValue === "failed") {
    stateEl.textContent = "Failed";
    return;
  }
  stateEl.textContent = "Pending";
}

function renderStageCards(statusByStage) {
  qsa("#stage-cards .stage-card").forEach((card) => {
    const stage = card.dataset.stage;
    const stateValue = statusByStage[stage] || "pending";
    applyStageCardState(card, stateValue);
  });
}

function emptyStageStatus() {
  return { stage1: "pending", stage2: "pending", stage3: "pending", stage4: "pending" };
}

function emptyStage5FlowStatus() {
  return { ingest: "pending", route: "pending", execute: "pending", trace: "pending", score: "pending" };
}

function setStageStatus(stageStatus, stageKey, value) {
  const next = { ...stageStatus };
  next[stageKey] = value;
  return next;
}

function updatePipelineProgress(statusByStage, labelOverride = "") {
  const doneCount = STAGE_SEQUENCE.filter((s) => statusByStage[s] === "done").length;
  const failedStage = STAGE_SEQUENCE.find((s) => statusByStage[s] === "failed");
  const runningStage = STAGE_SEQUENCE.find((s) => statusByStage[s] === "running");

  let progress = doneCount * 25;
  if (runningStage) {
    progress = Math.min(progress + 10, 95);
  }
  if (failedStage) {
    progress = doneCount * 25;
  }
  if (doneCount === STAGE_SEQUENCE.length) {
    progress = 100;
  }

  qs("#pipeline-progress").style.width = `${progress}%`;

  if (labelOverride) {
    qs("#pipeline-progress-label").textContent = labelOverride;
    return;
  }
  if (failedStage) {
    qs("#pipeline-progress-label").textContent = `Failed at ${failedStage.toUpperCase()}`;
    return;
  }
  if (runningStage) {
    qs("#pipeline-progress-label").textContent = `Processing ${runningStage.toUpperCase()}...`;
    return;
  }
  if (doneCount === STAGE_SEQUENCE.length) {
    qs("#pipeline-progress-label").textContent = "Adversarial document generated";
    return;
  }
  qs("#pipeline-progress-label").textContent = "Idle";
}

function renderPipelineState(statusByStage, labelOverride = "") {
  renderStageCards(statusByStage);
  updatePipelineProgress(statusByStage, labelOverride);
  refreshStageRunButtons();
}

function hidePipelinePreview() {
  qs("#pipeline-preview").classList.add("hidden");
  qs("#preview-original").src = "about:blank";
  qs("#preview-adversarial").src = "about:blank";
}

function showPipelinePreview(originalPath, adversarialPath) {
  if (!originalPath || !adversarialPath) {
    return;
  }
  qs("#preview-original").src = `/api/files/preview?path=${encodeURIComponent(originalPath)}#toolbar=0`;
  qs("#preview-adversarial").src = `/api/files/preview?path=${encodeURIComponent(adversarialPath)}#toolbar=0`;
  qs("#pipeline-preview").classList.remove("hidden");
}

function setPipelineResult(message, muted = true) {
  const el = qs("#pipeline-result");
  el.classList.toggle("muted", muted);
  el.textContent = message;
}

function getSelectedPdfPath() {
  const pathInput = qs("#pdf-path");
  const selectInput = qs("#pdf-select");
  return (pathInput && pathInput.value.trim()) || (selectInput && selectInput.value) || "";
}

function normalizeOutRootForUi(value) {
  const raw = String(value || "").trim();
  if (!raw || raw === ".") {
    return DEFAULT_PIPELINE_RUN_ROOT;
  }
  const normalized = raw.replaceAll("\\", "/");
  let parts = normalized.split("/").filter((part) => part && part !== "." && part !== "..");
  if (parts.length && parts[0] === DEFAULT_PIPELINE_RUN_ROOT) {
    parts = parts.slice(1);
  }

  const isAbsolute = normalized.startsWith("/") || /^[A-Za-z]:\//.test(normalized);
  if (isAbsolute && parts.length) {
    parts = [parts[parts.length - 1]];
  }

  if (!parts.length) {
    return DEFAULT_PIPELINE_RUN_ROOT;
  }
  return `${DEFAULT_PIPELINE_RUN_ROOT}/${parts.join("/")}`;
}

function getSelectedOutRoot() {
  const outRootInput = qs("#out-root");
  return normalizeOutRootForUi((outRootInput && outRootInput.value) || DEFAULT_PIPELINE_RUN_ROOT);
}

function docIdFromPdfPath(pdfPath) {
  if (!pdfPath) {
    return "";
  }
  const fileName = pdfPath.split(/[\\/]/).pop() || "";
  if (!fileName) {
    return "";
  }
  if (fileName.toLowerCase().endsWith(".pdf")) {
    return fileName.slice(0, -4);
  }
  return fileName;
}

function stageLabel(stageKey) {
  const index = STAGE_SEQUENCE.indexOf(stageKey);
  return index >= 0 ? `Stage ${index + 1}` : stageKey;
}

function setPipelineBusy(isBusy) {
  state.pipelineBusy = Boolean(isBusy);
  refreshStageRunButtons();
}

function setPipelineStageStatus(statusByStage, labelOverride = "") {
  state.pipelineStageStatus = { ...statusByStage };
  renderPipelineState(state.pipelineStageStatus, labelOverride);
}

function getCurrentPipelineStageStatus() {
  return { ...(state.pipelineStageStatus || emptyStageStatus()) };
}

function refreshStageRunButtons() {
  const hasPdf = Boolean(getSelectedPdfPath());
  const busy = Boolean(state.pipelineBusy);
  const runAllBtn = qs("#run-pipeline");
  if (runAllBtn) {
    runAllBtn.disabled = busy || !hasPdf;
  }

  const canRunByStage = {
    stage1: hasPdf,
    stage2: hasPdf,
    stage3: hasPdf,
    stage4: hasPdf,
  };

  qsa(".stage-run-btn").forEach((btn) => {
    const stageKey = btn.dataset.runStage;
    const enabled = Boolean(canRunByStage[stageKey]) && !busy;
    btn.disabled = !enabled;
  });
}

function markPipelineInputsDirty() {
  state.lastBaseDir = "";
  hidePipelinePreview();
  setPipelineStageStatus(emptyStageStatus(), "Idle");
  setPipelineResult("No pipeline run yet.", true);
  refreshStageRunButtons();
}

async function hydratePipelineStatusFromDisk(pdfPath, outRoot) {
  const docId = docIdFromPdfPath(pdfPath);
  if (!docId) {
    return null;
  }
  const query = new URLSearchParams({ base_root: outRoot });
  try {
    const payload = await apiGet(`/api/doc/${encodeURIComponent(docId)}/status?${query.toString()}`);
    const status = emptyStageStatus();
    const server = payload.stage_status || {};
    STAGE_SEQUENCE.forEach((stageKey) => {
      status[stageKey] = server[stageKey] ? "done" : "pending";
    });
    state.lastBaseDir = payload.base_dir || `${outRoot}/${docId}`;
    setPipelineStageStatus(status);
    return payload;
  } catch (_err) {
    return null;
  }
}

function ensureStagePrerequisites(stageKey, statusByStage) {
  const index = STAGE_SEQUENCE.indexOf(stageKey);
  if (index <= 0) {
    return true;
  }
  for (let i = 0; i < index; i += 1) {
    const requiredStage = STAGE_SEQUENCE[i];
    if (statusByStage[requiredStage] !== "done") {
      window.alert(`Please run ${stageLabel(requiredStage)} first.`);
      return false;
    }
  }
  return true;
}

function updateAttackMechanismHint() {
  const mechSelect = qs("#attack-mechanism");
  const warning = qs("#attack-mechanism-warning");
  if (!mechSelect || !warning) {
    return;
  }
  warning.classList.toggle("hidden", (mechSelect.value || "auto") === "auto");
}

function readRunTypes() {
  return qsa(".checkbox-row input[type='checkbox']")
    .filter((cb) => cb.checked)
    .map((cb) => cb.value);
}

function renderRunsTable(items) {
  const tbody = qs("#runs-table tbody");
  tbody.innerHTML = "";
  const labels = (state.metadata && state.metadata.scenario_labels) || {};

  items.forEach((row) => {
    const tr = document.createElement("tr");
    const scenarioLabel = labels[row.scenario] || row.scenario || "";
    tr.innerHTML = `
      <td>${escapeHtml(row.doc_id || "")}</td>
      <td>${escapeHtml(scenarioLabel)}</td>
      <td>${row.compromised ? "Yes" : "No"}</td>
      <td>${row.clean_matches_gold ? "Yes" : "No"}</td>
      <td>${escapeHtml(row.changed_target_fields ?? 0)}</td>
      <td><code>${escapeHtml(row.path || "")}</code></td>
    `;
    tbody.appendChild(tr);
  });
}

function renderReportsTable(items) {
  const tbody = qs("#reports-table tbody");
  tbody.innerHTML = "";
  items.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(row.run_id || "")}</td>
      <td>${escapeHtml(row.eligible_docs ?? "")}</td>
      <td>${row.attack_success_rate !== undefined ? Number(row.attack_success_rate).toFixed(4) : ""}</td>
      <td>${row.severity_weighted_vulnerability_score !== undefined ? Number(row.severity_weighted_vulnerability_score).toFixed(4) : ""}</td>
      <td><code>${escapeHtml(row.path || "")}</code></td>
      <td>${row.paper_table ? `<code>${escapeHtml(row.paper_table)}</code>` : ""}</td>
    `;
    tbody.appendChild(tr);
  });
}

function getScenarioCatalog() {
  const catalog = (state.metadata && state.metadata.scenario_catalog) || {};
  const merged = {};

  STAGE5_SCENARIO_ORDER.forEach((key) => {
    merged[key] = {
      ...(STAGE5_FALLBACK_CATALOG[key] || {}),
      ...(catalog[key] || {}),
    };
  });

  Object.entries(catalog).forEach(([key, value]) => {
    if (!merged[key]) {
      merged[key] = {
        title: key,
        task: "",
      };
    }
    merged[key] = {
      ...merged[key],
      ...(value || {}),
    };
  });

  return merged;
}

function getAgentBackendCatalog() {
  const fromApi = (state.metadata && state.metadata.agent_backend_agents) || {};
  const merged = {};
  Object.entries(AGENT_BACKEND_FALLBACK_CATALOG).forEach(([key, value]) => {
    merged[key] = {
      ...value,
      ...(fromApi[key] || {}),
    };
  });
  Object.entries(fromApi).forEach(([key, value]) => {
    if (!merged[key]) {
      merged[key] = {
        title: key,
        focus: "",
      };
    }
    merged[key] = {
      ...merged[key],
      ...(value || {}),
    };
  });
  return merged;
}

function getOrderedScenarioKeys() {
  const catalog = getScenarioCatalog();
  return [
    ...STAGE5_SCENARIO_ORDER.filter((key) => Object.prototype.hasOwnProperty.call(catalog, key)),
    ...Object.keys(catalog).filter((key) => !STAGE5_SCENARIO_ORDER.includes(key)),
  ];
}

function getSelectedEvaluationScenario() {
  const select = qs("#eval-scenario");
  if (!select || !select.value) {
    return STAGE5_SCENARIO_ORDER[0];
  }
  return select.value;
}

function populateEvaluationScenarioSelect() {
  const select = qs("#eval-scenario");
  if (!select) {
    return;
  }
  const existing = select.value;
  const catalog = getScenarioCatalog();
  const keys = ["auto", ...getOrderedScenarioKeys()];
  select.innerHTML = "";
  keys.forEach((scenario) => {
    const meta = catalog[scenario] || {};
    const copy = EVAL_QUERY_PROFILE_COPY[scenario] || {};
    const opt = document.createElement("option");
    opt.value = scenario;
    opt.textContent = copy.label || meta.title || scenario;
    select.appendChild(opt);
  });
  if (existing && keys.includes(existing)) {
    select.value = existing;
  } else if (keys.includes("auto")) {
    select.value = "auto";
  } else if (keys.length) {
    select.value = keys[0];
  }
  updateEvaluationScenarioHint();
}

function updateEvaluationScenarioHint() {
  const hint = qs("#eval-scenario-task");
  if (!hint) {
    return;
  }
  const scenario = getSelectedEvaluationScenario();
  const catalog = getScenarioCatalog();
  const meta = catalog[scenario] || {};
  const copy = EVAL_QUERY_PROFILE_COPY[scenario] || {};
  if (copy.help) {
    hint.textContent = `${copy.help} Router still decides the domain specialist.`;
    return;
  }
  hint.textContent = meta.task
    ? `${meta.task} Router still decides the domain specialist.`
    : "Router decides the domain specialist for the selected query profile.";
}

function setEvaluationRunEnabled(enabled) {
  const btn = qs("#run-eval");
  if (!btn) {
    return;
  }
  btn.disabled = !enabled;
}

function setEvaluationMessage(message, muted = true) {
  const el = qs("#eval-message");
  if (!el) {
    return;
  }
  el.classList.toggle("muted", muted);
  el.textContent = message;
}

function setAgentPanelNote(message, muted = true) {
  const el = qs("#agent-panel-note");
  if (!el) {
    return;
  }
  el.classList.toggle("muted", muted);
  el.textContent = message;
}

function normalizeDomainKey(value) {
  if (value === undefined || value === null) {
    return null;
  }
  const normalized = String(value).trim().toLowerCase();
  return normalized || null;
}

function clearEvaluationTimer() {
  if (state.evaluation && state.evaluation.timer) {
    clearInterval(state.evaluation.timer);
    state.evaluation.timer = null;
  }
}

function renderEvaluationFlowState(statusByStage, labelOverride = "") {
  qsa("#eval-stage-cards .stage-card").forEach((card) => {
    const stage = card.dataset.stage;
    const stateValue = statusByStage[stage] || "pending";
    applyStageCardState(card, stateValue);
  });

  const progressEl = qs("#eval-progress");
  const labelEl = qs("#eval-progress-label");
  if (!progressEl || !labelEl) {
    return;
  }

  const doneCount = STAGE5_FLOW_SEQUENCE.filter((s) => statusByStage[s] === "done").length;
  const failedStage = STAGE5_FLOW_SEQUENCE.find((s) => statusByStage[s] === "failed");
  const runningStage = STAGE5_FLOW_SEQUENCE.find((s) => statusByStage[s] === "running");

  let progress = (doneCount / STAGE5_FLOW_SEQUENCE.length) * 100;
  if (runningStage) {
    progress = Math.min(progress + 8, 96);
  }
  if (failedStage) {
    progress = (doneCount / STAGE5_FLOW_SEQUENCE.length) * 100;
  }
  if (doneCount === STAGE5_FLOW_SEQUENCE.length) {
    progress = 100;
  }
  progressEl.style.width = `${progress}%`;

  if (labelOverride) {
    labelEl.textContent = labelOverride;
    return;
  }
  if (failedStage) {
    labelEl.textContent = `Failed at ${stage5FlowStageLabel(failedStage)}`;
    return;
  }
  if (runningStage) {
    labelEl.textContent = `Processing ${stage5FlowStageLabel(runningStage)}...`;
    return;
  }
  if (doneCount === STAGE5_FLOW_SEQUENCE.length) {
    labelEl.textContent = "Evaluation completed";
    return;
  }
  labelEl.textContent = "Idle";
}

function resetEvaluationFlow(label = "Idle") {
  const status = emptyStage5FlowStatus();
  state.evaluation.flowStatus = status;
  clearEvaluationTimer();
  renderEvaluationFlowState(status, label);
}

function startEvaluationFlowAnimation() {
  clearEvaluationTimer();
  let status = emptyStage5FlowStatus();
  status = setStageStatus(status, STAGE5_FLOW_SEQUENCE[0], "running");
  state.evaluation.flowStatus = status;
  renderEvaluationFlowState(status, "Running agent-backend evaluation...");

  state.evaluation.timer = setInterval(() => {
    let current = state.evaluation.flowStatus || emptyStage5FlowStatus();
    const running = STAGE5_FLOW_SEQUENCE.find((step) => current[step] === "running");
    if (!running) {
      return;
    }
    const idx = STAGE5_FLOW_SEQUENCE.indexOf(running);
    if (idx < STAGE5_FLOW_SEQUENCE.length - 1) {
      current = setStageStatus(current, running, "done");
      current = setStageStatus(current, STAGE5_FLOW_SEQUENCE[idx + 1], "running");
      state.evaluation.flowStatus = current;
      renderEvaluationFlowState(current);
    }
  }, 1200);
}

function finishEvaluationFlow(success) {
  clearEvaluationTimer();
  let status = state.evaluation.flowStatus || emptyStage5FlowStatus();
  if (success) {
    STAGE5_FLOW_SEQUENCE.forEach((stageKey) => {
      status = setStageStatus(status, stageKey, "done");
    });
    renderEvaluationFlowState(status, "Evaluation completed");
  } else {
    const running = STAGE5_FLOW_SEQUENCE.find((stageKey) => status[stageKey] === "running");
    status = setStageStatus(status, running || STAGE5_FLOW_SEQUENCE[0], "failed");
    renderEvaluationFlowState(status, "Failed");
  }
  state.evaluation.flowStatus = status;
}

function renderAgentPanels() {
  const container = qs("#agent-panels");
  if (!container) {
    return;
  }
  const catalog = getAgentBackendCatalog();
  const includeGeneral = Boolean(state.evaluation.showGeneralFallback);
  const ordered = [
    "healthcare",
    "finance",
    "hr",
    "insurance",
    "education",
    "political",
    ...(includeGeneral ? ["general"] : []),
    ...Object.keys(catalog).filter(
      (key) => !["healthcare", "finance", "hr", "insurance", "education", "political", "general"].includes(key)
    ),
  ];
  container.innerHTML = ordered
    .filter((key) => Object.prototype.hasOwnProperty.call(catalog, key))
    .map((key) => {
      const meta = catalog[key] || {};
      return `
        <article class="agent-card" data-agent="${escapeHtml(key)}">
          <div class="agent-card-head">
            <h4>${escapeHtml(meta.title || key)}</h4>
            <span class="agent-code">${escapeHtml(key)}</span>
          </div>
          <p class="agent-focus">${escapeHtml(meta.focus || "")}</p>
          <div class="agent-status">Idle</div>
        </article>
      `;
    })
    .join("");
}

function updateActiveAgentPanels(cleanDomain, attackedDomain) {
  const cleanKey = normalizeDomainKey(cleanDomain);
  const attackedKey = normalizeDomainKey(attackedDomain);
  const showGeneralFallback = cleanKey === "general" || attackedKey === "general";

  if (state.evaluation.showGeneralFallback !== showGeneralFallback) {
    state.evaluation.showGeneralFallback = showGeneralFallback;
    renderAgentPanels();
  }

  state.evaluation.activeCleanDomain = cleanKey;
  state.evaluation.activeAttackedDomain = attackedKey;

  qsa("#agent-panels .agent-card").forEach((card) => {
    const domain = normalizeDomainKey(card.dataset.agent || "");
    const isClean = !!cleanKey && domain === cleanKey;
    const isAttacked = !!attackedKey && domain === attackedKey;
    const status = card.querySelector(".agent-status");

    card.classList.remove("active", "attacked-only");
    if (!status) {
      return;
    }
    if (isClean && isAttacked) {
      card.classList.add("active");
      status.textContent = "Routed for clean + adversarial";
      return;
    }
    if (isClean) {
      card.classList.add("active");
      status.textContent = "Routed for clean document";
      return;
    }
    if (isAttacked) {
      card.classList.add("active");
      status.textContent = "Routed for adversarial document";
      return;
    }
    status.textContent = "Idle";
  });
}

function hideEvaluationSummary() {
  const summary = qs("#eval-summary");
  if (!summary) {
    return;
  }
  summary.classList.add("hidden");
  summary.innerHTML = "";
}

function markEvaluationInputsDirty() {
  state.evaluation.preparedBaseDir = "";
  setEvaluationRunEnabled(false);
  hideEvaluationSummary();
  setEvaluationMessage("Inputs updated. Click Check Eligibility.", true);
  resetEvaluationFlow("Idle");
  updateActiveAgentPanels(null, null);
  setAgentPanelNote("No evaluation run yet.", true);
}

async function prepareEvaluationUploads(scenario) {
  const originalInput = qs("#eval-original-upload");
  const adversarialInput = qs("#eval-adversarial-upload");
  const originalFile = originalInput && originalInput.files ? originalInput.files[0] : null;
  const adversarialFile = adversarialInput && adversarialInput.files ? adversarialInput.files[0] : null;

  if (!originalFile) {
    throw new Error("Please upload an original PDF.");
  }
  if (!adversarialFile) {
    throw new Error("Please upload an adversarial PDF.");
  }
  if (!isPdfFile(originalFile)) {
    throw new Error("Original document must be a .pdf file.");
  }
  if (!isPdfFile(adversarialFile)) {
    throw new Error("Adversarial document must be a .pdf file.");
  }

  const formData = new FormData();
  formData.append("scenario", scenario);
  formData.append("original_pdf", originalFile);
  formData.append("adversarial_pdf", adversarialFile);

  const prepared = await apiPostForm("/api/stage5/prepare-upload", formData);
  state.evaluation.preparedBaseDir = prepared.base_dir || "";
  return prepared;
}

async function checkEvaluationEligibility() {
  const scenario = getSelectedEvaluationScenario();
  hideEvaluationSummary();
  setEvaluationRunEnabled(false);
  try {
    setEvaluationMessage("Uploading PDFs and preparing evaluation inputs...", false);
    const prepared = await prepareEvaluationUploads(scenario);
    const query = new URLSearchParams({ base_dir: prepared.base_dir });
    const result = await apiGet(`/api/stage5/eligibility?${query.toString()}`);
    if (result.eligible) {
      setEvaluationMessage("Evaluation is eligible for this document.", false);
      setEvaluationRunEnabled(true);
    } else {
      const msg = ["Evaluation is not eligible:", ...(result.missing || []).map((m) => `- ${m}`)].join("\n");
      setEvaluationMessage(msg, true);
      setEvaluationRunEnabled(false);
    }
  } catch (err) {
    setEvaluationMessage(`Eligibility check failed: ${err.message}`, true);
    setEvaluationRunEnabled(false);
  }
}

function renderEvaluationSummary(result, human, scenario) {
  const summary = qs("#eval-summary");
  if (!summary) {
    return;
  }

  const doc = (result && result.doc_result) || {};
  const cleanArgs = (doc.clean_majority && doc.clean_majority.tool_call && doc.clean_majority.tool_call.arguments) || {};
  const attackedArgs = (doc.attacked_majority && doc.attacked_majority.tool_call && doc.attacked_majority.tool_call.arguments) || {};
  const cleanOutcome = (doc.clean_majority && doc.clean_majority.final_outcome) || {};
  const attackedOutcome = (doc.attacked_majority && doc.attacked_majority.final_outcome) || {};
  const cleanView = buildScenarioOutcomeView(scenario, cleanArgs, cleanOutcome, "clean");
  const attackedView = buildScenarioOutcomeView(scenario, attackedArgs, attackedOutcome, "attacked");
  const verdict = userFacingVerdict(human, doc);
  const changedRows = Object.entries(doc.targeted_field_diffs || {})
    .filter(([, payload]) => payload && payload.changed)
    .map(([field, payload]) => ({
      field,
      clean: formatValue(payload.clean),
      attacked: formatValue(payload.attacked),
    }));
  const changedFallback = human.changed_fields || [];
  const changedHtml = changedRows.length
    ? changedRows
      .map((item) => `<li><strong>${escapeHtml(item.field.replaceAll("_", " "))}</strong>: ${escapeHtml(item.clean)} -> ${escapeHtml(item.attacked)}</li>`)
      .join("")
    : (changedFallback.length
      ? changedFallback.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
      : "<li>No attacker-targeted fields changed.</li>");

  const taskCorruption = Boolean(doc.task_corruption !== undefined ? doc.task_corruption : doc.decision_flip);
  const resourceInflation = Boolean(doc.resource_inflation);
  const toolMisfire = Boolean(doc.tool_misfire !== undefined ? doc.tool_misfire : doc.tool_parameter_corruption);
  const criticalFieldShift = changedRows.length > 0 || toolMisfire;
  const inflationRatio = doc.latency_inflation_ratio !== undefined
    ? Number(doc.latency_inflation_ratio).toFixed(2)
    : "n/a";

  summary.innerHTML = `
    <div class="meta-row">
      <span class="pill">${escapeHtml(human.scenario_label || scenario)}</span>
      <span class="pill">${escapeHtml(verdict.label)}</span>
    </div>
    <div class="verdict-box ${verdict.className}">${escapeHtml(verdict.sentence)}</div>

    <div class="outcome-compare">
      ${renderOutcomeCard(cleanView, "clean")}
      ${renderOutcomeCard(attackedView, "attacked")}
    </div>

    <h4>What Changed</h4>
    <ul>${changedHtml}</ul>

    <div class="metric-row">
      <div class="metric-card"><span>Overall Compromise</span><strong>${doc.attack_success ? "Yes" : "No"}</strong></div>
      <div class="metric-card"><span>Task Deviation</span><strong>${taskCorruption ? "Yes" : "No"}</strong></div>
      <div class="metric-card"><span>Tool Misfire</span><strong>${toolMisfire ? "Yes" : "No"}</strong></div>
      <div class="metric-card"><span>Resource Inflation</span><strong>${resourceInflation ? "Yes" : "No"}</strong></div>
      <div class="metric-card"><span>Latency Ratio (A/C)</span><strong>${inflationRatio}</strong></div>
      <div class="metric-card"><span>Critical Field Shift</span><strong>${criticalFieldShift ? "Yes" : "No"}</strong></div>
    </div>
  `;
  summary.classList.remove("hidden");
}

function describeAgentSelection(cleanDomain, attackedDomain) {
  const cleanKey = normalizeDomainKey(cleanDomain);
  const attackedKey = normalizeDomainKey(attackedDomain);
  if (!cleanKey && !attackedKey) {
    return "No routed domain returned.";
  }
  if (cleanKey === "general" || attackedKey === "general") {
    return "Router entered fallback route (GENERAL) for at least one run, which means routing confidence was low or context was cross-domain.";
  }
  if (cleanKey && attackedKey && cleanKey === attackedKey) {
    return `Router selected '${cleanKey}' for both clean and adversarial runs.`;
  }
  return `Router selected clean='${cleanKey || "n/a"}', adversarial='${attackedKey || "n/a"}'.`;
}

async function runEvaluation() {
  const scenario = getSelectedEvaluationScenario();
  let baseDir = state.evaluation.preparedBaseDir || "";
  const trials = Number(qs("#eval-trials").value || 3);
  const model = DEFAULT_STAGE5_MODEL;
  const runBtn = qs("#run-eval");
  const checkBtn = qs("#check-eval");

  if (runBtn) {
    runBtn.disabled = true;
  }
  if (checkBtn) {
    checkBtn.disabled = true;
  }

  startEvaluationFlowAnimation();
  setEvaluationMessage("Running agent-backend evaluation...", false);
  hideEvaluationSummary();
  updateActiveAgentPanels(null, null);
  setAgentPanelNote("Supervisor is routing the document to a domain specialist...", false);

  try {
    if (!baseDir) {
      setEvaluationMessage("Preparing uploaded PDFs...", false);
      const prepared = await prepareEvaluationUploads(scenario);
      baseDir = prepared.base_dir || "";
    }

    const payload = {
      base_dir: baseDir,
      scenario,
      adv_pdf: null,
      model,
      trials,
      out_subdir: "agent_backend_eval",
    };
    const response = await apiPost("/api/stage5/doc", payload);
    finishEvaluationFlow(true);
    renderEvaluationSummary(response.result, response.human_summary, scenario);
    setEvaluationMessage("Evaluation completed.", false);

    const doc = (response.result && response.result.doc_result) || {};
    const cleanDomain = ((doc.clean_majority || {}).final_outcome || {}).routed_domain || null;
    const attackedDomain = ((doc.attacked_majority || {}).final_outcome || {}).routed_domain || null;
    updateActiveAgentPanels(cleanDomain, attackedDomain);
    setAgentPanelNote(describeAgentSelection(cleanDomain, attackedDomain), false);

    await refreshRuns();
    await refreshReports();
  } catch (err) {
    finishEvaluationFlow(false);
    setEvaluationMessage(`Evaluation failed: ${err.message}`, true);
    setAgentPanelNote("Evaluation failed before agent routing completed.", true);
  } finally {
    if (runBtn) {
      runBtn.disabled = false;
    }
    if (checkBtn) {
      checkBtn.disabled = false;
    }
  }
}

function resetEvaluationWorkspace() {
  populateEvaluationScenarioSelect();
  state.evaluation.showGeneralFallback = false;
  renderAgentPanels();
  updateActiveAgentPanels(null, null);
  state.evaluation.preparedBaseDir = "";
  hideEvaluationSummary();
  resetEvaluationFlow("Idle");
  setEvaluationRunEnabled(false);
  setEvaluationMessage("Eligibility not checked.", true);
  setAgentPanelNote("No evaluation run yet.", true);
}

function stage5FlowStageLabel(stageKey) {
  const copy = STAGE5_FLOW_COPY[stageKey] || {};
  return copy.title || stageKey;
}

function updatePaneProgress(scenario, statusByStage, labelOverride = "") {
  const progressEl = qs(`#pane-progress-${scenario}`);
  const labelEl = qs(`#pane-progress-label-${scenario}`);
  if (!progressEl || !labelEl) {
    return;
  }

  const doneCount = STAGE5_FLOW_SEQUENCE.filter((s) => statusByStage[s] === "done").length;
  const failedStage = STAGE5_FLOW_SEQUENCE.find((s) => statusByStage[s] === "failed");
  const runningStage = STAGE5_FLOW_SEQUENCE.find((s) => statusByStage[s] === "running");

  let progress = (doneCount / STAGE5_FLOW_SEQUENCE.length) * 100;
  if (runningStage) {
    progress = Math.min(progress + 8, 96);
  }
  if (failedStage) {
    progress = (doneCount / STAGE5_FLOW_SEQUENCE.length) * 100;
  }
  if (doneCount === STAGE5_FLOW_SEQUENCE.length) {
    progress = 100;
  }

  progressEl.style.width = `${progress}%`;

  if (labelOverride) {
    labelEl.textContent = labelOverride;
    return;
  }
  if (failedStage) {
    labelEl.textContent = `Failed at ${stage5FlowStageLabel(failedStage)}`;
    return;
  }
  if (runningStage) {
    labelEl.textContent = `Processing ${stage5FlowStageLabel(runningStage)}...`;
    return;
  }
  if (doneCount === STAGE5_FLOW_SEQUENCE.length) {
    labelEl.textContent = "Evaluation completed";
    return;
  }
  labelEl.textContent = "Idle";
}

function renderPaneFlowState(scenario, statusByStage, labelOverride = "") {
  qsa(`#pane-stage-cards-${scenario} .stage-card`).forEach((card) => {
    const stage = card.dataset.stage;
    const stateValue = statusByStage[stage] || "pending";
    applyStageCardState(card, stateValue);
  });
  updatePaneProgress(scenario, statusByStage, labelOverride);
}

function stopPaneFlowTimer(scenario) {
  const pane = state.evalPanes[scenario];
  if (!pane || !pane.timer) {
    return;
  }
  clearInterval(pane.timer);
  pane.timer = null;
}

function stopAllPaneTimers() {
  Object.keys(state.evalPanes || {}).forEach((scenario) => stopPaneFlowTimer(scenario));
}

function startPaneFlowAnimation(scenario) {
  stopPaneFlowTimer(scenario);

  let status = emptyStage5FlowStatus();
  status = setStageStatus(status, STAGE5_FLOW_SEQUENCE[0], "running");
  state.evalPanes[scenario] = {
    stageStatus: status,
    timer: null,
  };
  renderPaneFlowState(scenario, status, "Running agent-backend evaluation...");

  state.evalPanes[scenario].timer = setInterval(() => {
    let current = state.evalPanes[scenario].stageStatus || emptyStage5FlowStatus();
    const running = STAGE5_FLOW_SEQUENCE.find((step) => current[step] === "running");
    if (!running) {
      return;
    }

    const idx = STAGE5_FLOW_SEQUENCE.indexOf(running);
    if (idx < STAGE5_FLOW_SEQUENCE.length - 1) {
      current = setStageStatus(current, running, "done");
      current = setStageStatus(current, STAGE5_FLOW_SEQUENCE[idx + 1], "running");
      state.evalPanes[scenario].stageStatus = current;
      renderPaneFlowState(scenario, current);
    }
  }, 1200);
}

function finishPaneFlow(scenario, success) {
  stopPaneFlowTimer(scenario);

  let status = (state.evalPanes[scenario] && state.evalPanes[scenario].stageStatus) || emptyStage5FlowStatus();
  if (success) {
    STAGE5_FLOW_SEQUENCE.forEach((stageKey) => {
      status = setStageStatus(status, stageKey, "done");
    });
    renderPaneFlowState(scenario, status, "Evaluation completed");
  } else {
    const running = STAGE5_FLOW_SEQUENCE.find((stageKey) => status[stageKey] === "running");
    if (running) {
      status = setStageStatus(status, running, "failed");
    } else {
      status = setStageStatus(status, STAGE5_FLOW_SEQUENCE[0], "failed");
    }
    renderPaneFlowState(scenario, status, "Failed");
  }

  state.evalPanes[scenario] = {
    stageStatus: status,
    timer: null,
  };
}

function setPaneMessage(scenario, message, muted = true) {
  const el = qs(`#pane-eligibility-${scenario}`);
  if (!el) {
    return;
  }
  el.classList.toggle("muted", muted);
  el.textContent = message;
}

function setPaneRunEnabled(scenario, enabled) {
  const runBtn = qs(`button[data-action='run-pane'][data-scenario='${scenario}']`);
  if (!runBtn) {
    return;
  }
  runBtn.disabled = !enabled;
}

function hidePaneSummary(scenario) {
  const summary = qs(`#pane-summary-${scenario}`);
  if (!summary) {
    return;
  }
  summary.classList.add("hidden");
  summary.innerHTML = "";
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "Not provided";
  }
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => formatValue(item)).join(", ") : "None";
  }
  if (typeof value === "object") {
    const entries = Object.entries(value);
    if (!entries.length) {
      return "Not provided";
    }
    return entries.map(([k, v]) => `${k.replaceAll("_", " ")}: ${formatValue(v)}`).join(", ");
  }
  return String(value);
}

function toneForStatus(statusText) {
  const value = String(statusText || "").toLowerCase();
  if (!value) {
    return "neutral";
  }
  if (value.includes("safe") || value.includes("verified") || value.includes("eligible") || value.includes("scheduled")) {
    return "safe";
  }
  if (value.includes("unsafe") || value.includes("wrong") || value.includes("not eligible") || value.includes("misconfigured")) {
    return "risk";
  }
  if (value.includes("review") || value.includes("mismatch") || value.includes("different")) {
    return "warn";
  }
  return "neutral";
}

function normalizedScenarioKey(scenario) {
  return String(scenario || "").trim().toLowerCase();
}

function pickPrimaryKey(argumentsPayload) {
  const args = argumentsPayload || {};
  const keyFields = [
    "cas_number",
    "student_id",
    "roll_no",
    "patient_id",
    "assignment_id",
    "attempt_id",
    "holder_name",
    "program",
    "url",
  ];
  for (const key of keyFields) {
    if (args[key] !== undefined && args[key] !== null && String(args[key]).trim() !== "") {
      return `${key.replaceAll("_", " ")}: ${formatValue(args[key])}`;
    }
  }
  return "Not provided";
}

function buildScenarioOutcomeView(scenario, argumentsPayload, outcomePayload, variant) {
  const args = argumentsPayload || {};
  const outcome = outcomePayload || {};
  const key = normalizedScenarioKey(scenario);

  const fallback = {
    panelTitle: variant === "clean" ? "Original Document Behavior" : "Adversarial Document Behavior",
    actionText: "Agent produced a simulated action outcome.",
    badgeText: "Outcome",
    badgeTone: "neutral",
    glyph: key || "decision",
    fields: [
      { label: "Primary Result", value: formatValue(outcome.status || outcome.decision || outcome.verified || outcome.shortlisted) },
      { label: "Important Detail", value: pickPrimaryKey(args) },
      { label: "Summary", value: formatValue(outcome) },
      { label: "Confidence", value: "Simulated" },
    ],
  };

  if (key === "decision") {
    const decision = formatValue(outcome.decision || "needs_review");
    return {
      panelTitle: fallback.panelTitle,
      actionText: "Eligibility decision generated from document policy details.",
      badgeText: decision,
      badgeTone: toneForStatus(decision),
      glyph: "decision",
      fields: [
        { label: "Program", value: formatValue(args.program) },
        { label: "Region", value: formatValue(args.region) },
        { label: "Decision", value: decision },
        { label: "Reasoning Basis", value: formatValue(args.criteria_summary) },
      ],
    };
  }

  if (key === "scheduling") {
    const status = formatValue(outcome.status || "pending");
    return {
      panelTitle: fallback.panelTitle,
      actionText: "Calendar/assignment action prepared for execution.",
      badgeText: status,
      badgeTone: toneForStatus(status),
      glyph: "scheduling",
      fields: [
        { label: "Event", value: formatValue(args.title) },
        { label: "Date", value: formatValue(outcome.scheduled_date || args.date || args.deadline) },
        { label: "Assignees", value: formatValue(outcome.assignees || args.assignees || args.assignee) },
        { label: "Channel", value: formatValue(outcome.channel || args.channel || args.communication_channel) },
      ],
    };
  }

  if (key === "db") {
    const status = formatValue(outcome.status || "unknown");
    return {
      panelTitle: fallback.panelTitle,
      actionText: "Database lookup/store result simulated.",
      badgeText: status,
      badgeTone: toneForStatus(status),
      glyph: "db",
      fields: [
        { label: "Lookup/Store Key", value: formatValue(outcome.lookup_key || outcome.stored_key || pickPrimaryKey(args)) },
        { label: "Record", value: formatValue(args.compound || args.student_name || args.procedure_name) },
        { label: "Status", value: status },
        { label: "Result Detail", value: formatValue(outcome) },
      ],
    };
  }

  if (key === "credential") {
    const verification = outcome.verified !== undefined
      ? (outcome.verified ? "verified" : "not verified")
      : (outcome.shortlisted ? "shortlisted" : "not shortlisted");
    return {
      panelTitle: fallback.panelTitle,
      actionText: "Credential screening outcome generated.",
      badgeText: verification,
      badgeTone: toneForStatus(verification),
      glyph: "credential",
      fields: [
        { label: "Candidate", value: formatValue(args.holder_name || args.candidate_name) },
        { label: "Institution", value: formatValue(args.institution) },
        { label: "Credential", value: formatValue(args.degree || args.skill || args.certification) },
        { label: "Date Range", value: formatValue(args.date_range) },
      ],
    };
  }

  if (key === "survey") {
    const safety = outcome.safe_domain === undefined
      ? "unknown safety"
      : (outcome.safe_domain ? "safe destination" : "unsafe destination");
    return {
      panelTitle: fallback.panelTitle,
      actionText: "Survey/link routing decision generated.",
      badgeText: safety,
      badgeTone: toneForStatus(safety),
      glyph: "survey",
      fields: [
        { label: "Destination URL", value: formatValue(outcome.url || args.url || args.link) },
        { label: "Consent Type", value: formatValue(args.optional !== undefined ? (args.optional ? "optional" : "mandatory") : outcome.optional) },
        { label: "Routing Safety", value: safety },
        { label: "Status", value: formatValue(outcome.status || "opened") },
      ],
    };
  }

  return fallback;
}

function renderOutcomeCard(view, variant) {
  const fieldsHtml = (view.fields || []).map((field) => `
    <div class="outcome-item">
      <dt>${escapeHtml(field.label || "")}</dt>
      <dd>${escapeHtml(formatValue(field.value))}</dd>
    </div>
  `).join("");

  return `
    <section class="outcome-card ${escapeHtml(variant)}">
      <div class="outcome-top">
        <h4>${escapeHtml(view.panelTitle || "")}</h4>
        <span class="pill outcome-pill ${escapeHtml(view.badgeTone || "neutral")}">${escapeHtml(view.badgeText || "Outcome")}</span>
      </div>
      <div class="action-ticker">
        <span class="action-glyph glyph-${escapeHtml(view.glyph || "decision")}" aria-hidden="true"></span>
        <span class="action-pulse" aria-hidden="true"></span>
        <span>${escapeHtml(view.actionText || "")}</span>
      </div>
      <dl class="outcome-grid">
        ${fieldsHtml}
      </dl>
    </section>
  `;
}

function userFacingVerdict(human, doc) {
  const verdict = String((human && human.verdict) || "").toUpperCase();
  if (verdict === "COMPROMISED") {
    return {
      label: "Compromise Detected",
      className: "compromised",
      sentence: "Adversarial content changed the final simulated outcome compared with the original document.",
    };
  }
  if (verdict === "NOT COMPROMISED") {
    return {
      label: "No Compromise Detected",
      className: "safe",
      sentence: "Original and adversarial documents produced equivalent simulated outcomes.",
    };
  }
  if (verdict === "BASELINE MISMATCH") {
    return {
      label: "Inconclusive (Baseline Failed)",
      className: "baseline",
      sentence: "The clean baseline did not produce a valid outcome, so this run cannot confirm compromise reliably.",
    };
  }
  return {
    label: "Outcome Ready",
    className: "baseline",
    sentence: "Simulation completed.",
  };
}

function renderPaneSummary(scenario, result, human) {
  const summary = qs(`#pane-summary-${scenario}`);
  if (!summary) {
    return;
  }

  const doc = (result && result.doc_result) || {};
  const cleanArgs = (doc.clean_majority && doc.clean_majority.tool_call && doc.clean_majority.tool_call.arguments) || {};
  const attackedArgs = (doc.attacked_majority && doc.attacked_majority.tool_call && doc.attacked_majority.tool_call.arguments) || {};
  const cleanOutcome = (doc.clean_majority && doc.clean_majority.final_outcome) || {};
  const attackedOutcome = (doc.attacked_majority && doc.attacked_majority.final_outcome) || {};
  const cleanView = buildScenarioOutcomeView(scenario, cleanArgs, cleanOutcome, "clean");
  const attackedView = buildScenarioOutcomeView(scenario, attackedArgs, attackedOutcome, "attacked");
  const verdict = userFacingVerdict(human, doc);
  const changedRows = Object.entries(doc.targeted_field_diffs || {})
    .filter(([, payload]) => payload && payload.changed)
    .map(([field, payload]) => ({
      field,
      clean: formatValue(payload.clean),
      attacked: formatValue(payload.attacked),
    }));

  const changedFallback = human.changed_fields || [];
  const changedHtml = changedRows.length
    ? changedRows
      .map((item) => `<li><strong>${escapeHtml(item.field.replaceAll("_", " "))}</strong>: ${escapeHtml(item.clean)} -> ${escapeHtml(item.attacked)}</li>`)
      .join("")
    : (changedFallback.length
      ? changedFallback.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
      : "<li>No attacker-targeted fields changed.</li>");

  const taskCorruption = Boolean(doc.task_corruption !== undefined ? doc.task_corruption : doc.decision_flip);
  const resourceInflation = Boolean(doc.resource_inflation);
  const toolMisfire = Boolean(doc.tool_misfire !== undefined ? doc.tool_misfire : doc.tool_parameter_corruption);
  const criticalFieldShift = changedRows.length > 0 || toolMisfire;
  const inflationRatio = doc.latency_inflation_ratio !== undefined
    ? Number(doc.latency_inflation_ratio).toFixed(2)
    : "n/a";
  summary.innerHTML = `
    <div class="meta-row">
      <span class="pill">${escapeHtml(human.scenario_label || scenario)}</span>
      <span class="pill">${escapeHtml(verdict.label)}</span>
    </div>
    <div class="verdict-box ${verdict.className}">${escapeHtml(verdict.sentence)}</div>

    <div class="outcome-compare">
      ${renderOutcomeCard(cleanView, "clean")}
      ${renderOutcomeCard(attackedView, "attacked")}
    </div>

    <h4>What Changed</h4>
    <ul>${changedHtml}</ul>

    <div class="metric-row">
      <div class="metric-card"><span>Overall Compromise</span><strong>${doc.attack_success ? "Yes" : "No"}</strong></div>
      <div class="metric-card"><span>Task Deviation</span><strong>${taskCorruption ? "Yes" : "No"}</strong></div>
      <div class="metric-card"><span>Tool Misfire</span><strong>${toolMisfire ? "Yes" : "No"}</strong></div>
      <div class="metric-card"><span>Resource Inflation</span><strong>${resourceInflation ? "Yes" : "No"}</strong></div>
      <div class="metric-card"><span>Latency Ratio (A/C)</span><strong>${inflationRatio}</strong></div>
      <div class="metric-card"><span>Critical Field Shift</span><strong>${criticalFieldShift ? "Yes" : "No"}</strong></div>
    </div>
  `;

  summary.classList.remove("hidden");
}

function paneOriginalUploadInput(scenario) {
  return qs(`#pane-original-upload-${scenario}`);
}

function paneAdversarialUploadInput(scenario) {
  return qs(`#pane-adversarial-upload-${scenario}`);
}

function isPdfFile(file) {
  if (!file || !file.name) {
    return false;
  }
  return String(file.name).toLowerCase().endsWith(".pdf");
}

function markPaneInputsDirty(scenario) {
  state.preparedStage5BaseDirs[scenario] = "";
  hidePaneSummary(scenario);
  setPaneRunEnabled(scenario, false);
  setPaneMessage(scenario, "Files selected. Click Check Eligibility.", true);

  stopPaneFlowTimer(scenario);
  const status = emptyStage5FlowStatus();
  state.evalPanes[scenario] = { stageStatus: status, timer: null };
  renderPaneFlowState(scenario, status, "Idle");
}

async function preparePaneUploads(scenario) {
  const originalInput = paneOriginalUploadInput(scenario);
  const adversarialInput = paneAdversarialUploadInput(scenario);
  const originalFile = originalInput && originalInput.files ? originalInput.files[0] : null;
  const adversarialFile = adversarialInput && adversarialInput.files ? adversarialInput.files[0] : null;

  if (!originalFile) {
    throw new Error("Please upload an original PDF.");
  }
  if (!adversarialFile) {
    throw new Error("Please upload an adversarial PDF.");
  }
  if (!isPdfFile(originalFile)) {
    throw new Error("Original document must be a .pdf file.");
  }
  if (!isPdfFile(adversarialFile)) {
    throw new Error("Adversarial document must be a .pdf file.");
  }

  const formData = new FormData();
  formData.append("scenario", scenario);
  formData.append("original_pdf", originalFile);
  formData.append("adversarial_pdf", adversarialFile);

  const prepared = await apiPostForm("/api/stage5/prepare-upload", formData);
  state.preparedStage5BaseDirs[scenario] = prepared.base_dir || "";
  return prepared;
}

function paneButtons(scenario) {
  return {
    check: qs(`button[data-action='check-pane'][data-scenario='${scenario}']`),
    run: qs(`button[data-action='run-pane'][data-scenario='${scenario}']`),
  };
}

async function checkPaneEligibility(scenario) {
  hidePaneSummary(scenario);
  setPaneRunEnabled(scenario, false);

  try {
    setPaneMessage(scenario, "Uploading PDFs and preparing evaluation inputs...", false);
    const prepared = await preparePaneUploads(scenario);
    const query = new URLSearchParams({ base_dir: prepared.base_dir });

    const result = await apiGet(`/api/stage5/eligibility?${query.toString()}`);
    if (result.eligible) {
      setPaneMessage(scenario, "Evaluation is eligible for this document.", false);
      setPaneRunEnabled(scenario, true);
    } else {
      const msg = ["Evaluation is not eligible:", ...(result.missing || []).map((m) => `- ${m}`)].join("\n");
      setPaneMessage(scenario, msg, true);
      setPaneRunEnabled(scenario, false);
    }
  } catch (err) {
    setPaneMessage(scenario, `Eligibility check failed: ${err.message}`, true);
    setPaneRunEnabled(scenario, false);
  }
}

async function runPaneEvaluation(scenario) {
  let baseDir = state.preparedStage5BaseDirs[scenario] || "";
  const trials = Number(qs("#eval-trials").value || 3);
  const model = DEFAULT_STAGE5_MODEL;

  const buttons = paneButtons(scenario);
  if (buttons.run) {
    buttons.run.disabled = true;
  }
  if (buttons.check) {
    buttons.check.disabled = true;
  }

  startPaneFlowAnimation(scenario);
  setPaneMessage(scenario, "Running agent-backend evaluation...", false);
  hidePaneSummary(scenario);

  try {
    if (!baseDir) {
      setPaneMessage(scenario, "Preparing uploaded PDFs...", false);
      const prepared = await preparePaneUploads(scenario);
      baseDir = prepared.base_dir || "";
    }

    const payload = {
      base_dir: baseDir,
      scenario,
      adv_pdf: null,
      model,
      trials,
      out_subdir: "agent_backend_eval",
    };

    const response = await apiPost("/api/stage5/doc", payload);
    finishPaneFlow(scenario, true);
    renderPaneSummary(scenario, response.result, response.human_summary);
    setPaneMessage(scenario, "Evaluation completed.", false);

    await refreshRuns();
    await refreshReports();
  } catch (err) {
    finishPaneFlow(scenario, false);
    setPaneMessage(scenario, `Evaluation failed: ${err.message}`, true);
  } finally {
    if (buttons.run) {
      buttons.run.disabled = false;
    }
    if (buttons.check) {
      buttons.check.disabled = false;
    }
  }
}

function scenarioPaneHtml(scenario, meta) {
  const flowCards = STAGE5_FLOW_SEQUENCE.map((stageKey, idx) => {
    const copy = STAGE5_FLOW_COPY[stageKey] || {};
    return `
      <div class="stage-card" data-stage="${stageKey}">
        <h4>Step ${idx + 1}: ${escapeHtml(copy.title || stageKey)}</h4>
        <p>${escapeHtml(copy.description || "")}</p>
        <span class="state">Pending</span>
      </div>
    `;
  }).join("");

  return `
    <article class="card fade-in scenario-pane" data-scenario="${scenario}">
      <div class="scenario-pane-head">
        <h3>${escapeHtml(meta.title || scenario)}</h3>
        <span class="pill">${escapeHtml(scenario)}</span>
      </div>
      <p class="scenario-task">${escapeHtml(meta.task || "")}</p>

      <div class="form-grid">
        <div>
          <label for="pane-original-upload-${scenario}">Upload Original Doc</label>
          <input id="pane-original-upload-${scenario}" type="file" accept=".pdf,application/pdf" data-action="pane-original-upload" data-scenario="${scenario}" />
        </div>
        <div>
          <label for="pane-adversarial-upload-${scenario}">Upload Adversarial Doc</label>
          <input id="pane-adversarial-upload-${scenario}" type="file" accept=".pdf,application/pdf" data-action="pane-adversarial-upload" data-scenario="${scenario}" />
        </div>
      </div>

      <div class="button-row">
        <button class="btn btn-secondary" data-action="check-pane" data-scenario="${scenario}">Check Eligibility</button>
        <button class="btn btn-primary" data-action="run-pane" data-scenario="${scenario}" disabled>Check Agent Behavior</button>
      </div>

      <div class="progress-wrap">
        <div class="progress-bar"><div id="pane-progress-${scenario}" class="progress-fill"></div></div>
        <span id="pane-progress-label-${scenario}">Idle</span>
      </div>

      <div class="stage-cards stage5-stage-cards" id="pane-stage-cards-${scenario}">
        ${flowCards}
      </div>

      <div id="pane-eligibility-${scenario}" class="result-box muted">Eligibility not checked.</div>
      <div id="pane-summary-${scenario}" class="pane-summary hidden"></div>
    </article>
  `;
}

function renderScenarioPanes() {
  const container = qs("#scenario-panes");
  if (!container) {
    return;
  }

  stopAllPaneTimers();
  state.evalPanes = {};
  state.preparedStage5BaseDirs = {};

  const catalog = getScenarioCatalog();
  const keys = [
    ...STAGE5_SCENARIO_ORDER.filter((key) => Object.prototype.hasOwnProperty.call(catalog, key)),
    ...Object.keys(catalog).filter((key) => !STAGE5_SCENARIO_ORDER.includes(key)),
  ];

  container.innerHTML = keys.map((scenario) => scenarioPaneHtml(scenario, catalog[scenario])).join("");

  keys.forEach((scenario) => {
    const status = emptyStage5FlowStatus();
    state.evalPanes[scenario] = { stageStatus: status, timer: null };
    state.preparedStage5BaseDirs[scenario] = "";
    renderPaneFlowState(scenario, status, "Idle");
  });
}

async function loadMetadata() {
  const payload = await apiGet("/api/metadata");
  state.metadata = payload;
  if (payload.pipeline_run_root) {
    state.baseRoot = String(payload.pipeline_run_root);
    const outRootInput = qs("#out-root");
    if (outRootInput && !outRootInput.value.trim()) {
      outRootInput.value = state.baseRoot;
    }
  }

  const mechSelect = qs("#attack-mechanism");
  mechSelect.innerHTML = "";
  const mechanisms = payload.attack_mechanisms || {};
  const orderedMechanisms = [];
  if (Object.prototype.hasOwnProperty.call(mechanisms, "auto")) {
    orderedMechanisms.push(["auto", mechanisms.auto]);
  }
  Object.entries(mechanisms).forEach(([key, label]) => {
    if (key === "auto") {
      return;
    }
    orderedMechanisms.push([key, label]);
  });

  orderedMechanisms.forEach(([key, label]) => {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = label;
    mechSelect.appendChild(opt);
  });
  if (orderedMechanisms.some(([key]) => key === "auto")) {
    mechSelect.value = "auto";
  }
  updateAttackMechanismHint();

  const batchInput = qs("#batch-docs");
  if (!batchInput.value && payload.default_demo_doc_ids) {
    batchInput.value = payload.default_demo_doc_ids.join(",");
  }
}

async function loadPdfs() {
  const root = encodeURIComponent(PDF_LISTING_ROOT);
  const payload = await apiGet(`/api/pdfs?base_root=${root}`);
  state.pdfs = payload.items || [];
  const select = qs("#pdf-select");
  select.innerHTML = '<option value="">(none)</option>';
  state.pdfs.forEach((path) => {
    const opt = document.createElement("option");
    opt.value = path;
    opt.textContent = path;
    select.appendChild(opt);
  });
}

async function refreshScenarioPanes() {
  resetEvaluationWorkspace();
}

async function runPipelineStage(stageKey) {
  if (!STAGE_SEQUENCE.includes(stageKey) || state.pipelineBusy) {
    return;
  }

  const pdfPath = getSelectedPdfPath();
  if (!pdfPath) {
    window.alert("Please select a PDF first.");
    setPipelineResult("Please provide a PDF path.", true);
    refreshStageRunButtons();
    return;
  }

  const outRoot = getSelectedOutRoot();
  const docId = docIdFromPdfPath(pdfPath);
  if (!docId) {
    window.alert("Unable to derive document ID from selected PDF path.");
    return;
  }

  if (!state.lastBaseDir && stageKey !== "stage1") {
    await hydratePipelineStatusFromDisk(pdfPath, outRoot);
  }

  let stageStatus = getCurrentPipelineStageStatus();
  if (!ensureStagePrerequisites(stageKey, stageStatus)) {
    return;
  }

  let baseDir = state.lastBaseDir || `${outRoot}/${docId}`;
  const runTypes = readRunTypes();
  const attackMechanism = qs("#attack-mechanism").value || "auto";
  const priorityFilter = qs("#priority-filter").value;

  setPipelineBusy(true);
  try {
    if (stageKey === "stage1") {
      hidePipelinePreview();
      stageStatus = emptyStageStatus();
      stageStatus = setStageStatus(stageStatus, "stage1", "running");
      setPipelineStageStatus(stageStatus, "Running Stage 1...");

      const stage1 = await apiPost("/api/pipeline/stage1", {
        pdf_path: pdfPath,
        out_root: outRoot,
        run_types: runTypes,
      });
      baseDir = stage1.base_dir;
      state.lastBaseDir = baseDir;
      state.baseRoot = stage1.run_root || outRoot;

      stageStatus = setStageStatus(stageStatus, "stage1", "done");
      setPipelineStageStatus(stageStatus, "Stage 1 completed");
      setPipelineResult("Stage 1 completed. Run Stage 2 next.", false);
      return;
    }

    if (stageKey === "stage2") {
      stageStatus = setStageStatus(stageStatus, "stage3", "pending");
      stageStatus = setStageStatus(stageStatus, "stage4", "pending");
      stageStatus = setStageStatus(stageStatus, "stage2", "running");
      setPipelineStageStatus(stageStatus, "Running Stage 2...");
      await apiPost("/api/pipeline/stage2", { base_dir: baseDir });
      stageStatus = setStageStatus(stageStatus, "stage2", "done");
      setPipelineStageStatus(stageStatus, "Stage 2 completed");
      setPipelineResult("Stage 2 completed. Run Stage 3 next.", false);
      return;
    }

    if (stageKey === "stage3") {
      stageStatus = setStageStatus(stageStatus, "stage4", "pending");
      stageStatus = setStageStatus(stageStatus, "stage3", "running");
      setPipelineStageStatus(stageStatus, "Running Stage 3...");
      await apiPost("/api/pipeline/stage3", { base_dir: baseDir });
      stageStatus = setStageStatus(stageStatus, "stage3", "done");
      setPipelineStageStatus(stageStatus, "Stage 3 completed");
      setPipelineResult("Stage 3 completed. Run Stage 4 to generate adversarial PDF.", false);
      return;
    }

    stageStatus = setStageStatus(stageStatus, "stage4", "running");
    setPipelineStageStatus(stageStatus, "Running Stage 4...");
    const stage4 = await apiPost("/api/pipeline/stage4", {
      base_dir: baseDir,
      source_pdf_path: pdfPath,
      attack_mechanism: attackMechanism,
      priority_filter: priorityFilter,
    });
    stageStatus = setStageStatus(stageStatus, "stage4", "done");
    setPipelineStageStatus(stageStatus);

    const originalPreview = stage4.preview_original_pdf || pdfPath;
    const adversarialPreview = stage4.preview_adversarial_pdf || `${baseDir}/stage4/final_overlay.pdf`;
    showPipelinePreview(originalPreview, adversarialPreview);

    setPipelineResult(
      `Adversarial document generated for ${stage4.doc_id}. Review the Original vs Adversarial previews below, then open Evaluation to run the agent-backend check.`,
      false,
    );
    await refreshScenarioPanes();
    await refreshRuns();
    await refreshReports();
  } catch (err) {
    stageStatus = setStageStatus(stageStatus, stageKey, "failed");
    setPipelineStageStatus(stageStatus, "Failed");
    setPipelineResult(`${stageLabel(stageKey)} failed: ${err.message}`, true);
  } finally {
    setPipelineBusy(false);
  }
}

async function runPipeline() {
  if (state.pipelineBusy) {
    return;
  }

  const pdfPath = getSelectedPdfPath();
  const outRoot = getSelectedOutRoot();
  const runTypes = readRunTypes();
  const attackMechanism = qs("#attack-mechanism").value || "auto";
  const priorityFilter = qs("#priority-filter").value;

  if (!pdfPath) {
    setPipelineResult("Please provide a PDF path.", true);
    refreshStageRunButtons();
    return;
  }

  hidePipelinePreview();
  let stageStatus = emptyStageStatus();
  setPipelineStageStatus(stageStatus, "Starting pipeline...");
  setPipelineResult("Generating adversarial document (Stage 1 to Stage 4). This can take a while depending on OCR/LLM load.", true);
  setPipelineBusy(true);

  try {
    stageStatus = setStageStatus(stageStatus, "stage1", "running");
    setPipelineStageStatus(stageStatus);
    const stage1 = await apiPost("/api/pipeline/stage1", {
      pdf_path: pdfPath,
      out_root: outRoot,
      run_types: runTypes,
    });
    stageStatus = setStageStatus(stageStatus, "stage1", "done");
    setPipelineStageStatus(stageStatus, "Stage 1 completed");

    const baseDir = stage1.base_dir;
    const sourcePdfPath = stage1.source_pdf_path || pdfPath;

    stageStatus = setStageStatus(stageStatus, "stage2", "running");
    setPipelineStageStatus(stageStatus);
    await apiPost("/api/pipeline/stage2", {
      base_dir: baseDir,
    });
    stageStatus = setStageStatus(stageStatus, "stage2", "done");
    setPipelineStageStatus(stageStatus, "Stage 2 completed");

    stageStatus = setStageStatus(stageStatus, "stage3", "running");
    setPipelineStageStatus(stageStatus);
    await apiPost("/api/pipeline/stage3", {
      base_dir: baseDir,
    });
    stageStatus = setStageStatus(stageStatus, "stage3", "done");
    setPipelineStageStatus(stageStatus, "Stage 3 completed");

    stageStatus = setStageStatus(stageStatus, "stage4", "running");
    setPipelineStageStatus(stageStatus);
    const stage4 = await apiPost("/api/pipeline/stage4", {
      base_dir: baseDir,
      source_pdf_path: sourcePdfPath,
      attack_mechanism: attackMechanism,
      priority_filter: priorityFilter,
    });
    stageStatus = setStageStatus(stageStatus, "stage4", "done");
    setPipelineStageStatus(stageStatus);

    const originalPreview = stage4.preview_original_pdf || sourcePdfPath;
    const adversarialPreview = stage4.preview_adversarial_pdf || `${baseDir}/stage4/final_overlay.pdf`;
    showPipelinePreview(originalPreview, adversarialPreview);

    setPipelineResult(
      `Adversarial document generated for ${stage4.doc_id}. Review the Original vs Adversarial previews below, then open Evaluation to run the agent-backend check.`,
      false,
    );

    state.baseRoot = stage1.run_root || outRoot;
    state.lastBaseDir = baseDir;

    await loadPdfs();
    await refreshScenarioPanes();
    await refreshRuns();
    await refreshReports();
  } catch (err) {
    const running = STAGE_SEQUENCE.find((stage) => stageStatus[stage] === "running");
    if (running) {
      stageStatus = setStageStatus(stageStatus, running, "failed");
    }
    setPipelineStageStatus(stageStatus, "Failed");
    hidePipelinePreview();
    setPipelineResult(`Pipeline failed: ${err.message}`, true);
  } finally {
    setPipelineBusy(false);
  }
}

async function refreshRuns() {
  try {
    const root = encodeURIComponent(state.baseRoot || DEFAULT_PIPELINE_RUN_ROOT);
    const payload = await apiGet(`/api/runs/docs?base_root=${root}`);
    renderRunsTable(payload.items || []);
  } catch (_err) {
    renderRunsTable([]);
  }
}

async function runBatch() {
  const baseRoot = state.baseRoot || DEFAULT_PIPELINE_RUN_ROOT;
  const docIdsRaw = qs("#batch-docs").value.trim();
  const docIds = docIdsRaw ? docIdsRaw.split(",").map((x) => x.trim()).filter(Boolean) : null;
  const model = qs("#batch-model").value.trim() || "gpt-5-2025-08-07";
  const trials = Number(qs("#batch-trials").value || 3);
  const outDir = qs("#batch-out-dir").value.trim() || "stage5_runs";

  const btn = qs("#run-batch");
  btn.disabled = true;
  qs("#batch-summary").textContent = "Running batch evaluation...";
  qs("#batch-summary").classList.add("muted");

  try {
    const payload = {
      base_root: baseRoot,
      doc_ids: docIds,
      model,
      trials,
      out_dir: outDir,
    };
    const response = await apiPost("/api/stage5/batch", payload);
    const summary = response.batch_summary || {};
    const lines = [];
    lines.push(
      `Successful compromises: ${summary.successful_compromises || 0} out of ${summary.eligible_docs || 0} eligible documents.`
    );
    lines.push(`ASR: ${Number(summary.attack_success_rate || 0).toFixed(4)}`);
    lines.push(`Decision Flip Rate: ${Number(summary.decision_flip_rate || 0).toFixed(4)}`);
    lines.push(`Parameter Corruption Rate: ${Number(summary.tool_parameter_corruption_rate || 0).toFixed(4)}`);
    lines.push(`Severity-Weighted Score: ${Number(summary.severity_weighted_vulnerability_score || 0).toFixed(4)}`);

    const reportPaths = (response.result && response.result.report_paths) || {};
    if (Object.keys(reportPaths).length) {
      lines.push("Reports:");
      Object.entries(reportPaths).forEach(([k, v]) => lines.push(`- ${k}: ${v}`));
    }

    qs("#batch-summary").textContent = lines.join("\n");
    qs("#batch-summary").classList.remove("muted");

    await refreshReports();
    await refreshRuns();
  } catch (err) {
    qs("#batch-summary").textContent = `Batch evaluation failed: ${err.message}`;
    qs("#batch-summary").classList.add("muted");
  } finally {
    btn.disabled = false;
  }
}

async function refreshReports() {
  try {
    const outDir = encodeURIComponent(qs("#batch-out-dir").value || "stage5_runs");
    const payload = await apiGet(`/api/runs/batch?out_dir=${outDir}`);
    renderReportsTable(payload.items || []);
  } catch (_err) {
    renderReportsTable([]);
  }
}

function wireEvents() {
  qsa(".tab").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const target = btn.dataset.target;
      activateTab(target);
      if (target === "evaluation") {
        await refreshScenarioPanes();
      }
    });
  });

  qs("#pdf-select").addEventListener("change", (e) => {
    if (e.target.value) {
      qs("#pdf-path").value = e.target.value;
    }
    markPipelineInputsDirty();
  });

  qs("#pdf-path").addEventListener("change", () => {
    markPipelineInputsDirty();
  });

  qs("#out-root").addEventListener("change", async () => {
    state.baseRoot = getSelectedOutRoot();
    markPipelineInputsDirty();
    await loadPdfs();
    await refreshScenarioPanes();
    await refreshRuns();
    await refreshReports();
  });

  qs("#attack-mechanism").addEventListener("change", () => {
    updateAttackMechanismHint();
  });

  const evalScenario = qs("#eval-scenario");
  if (evalScenario) {
    evalScenario.addEventListener("change", () => {
      updateEvaluationScenarioHint();
      markEvaluationInputsDirty();
    });
  }

  const evalOriginal = qs("#eval-original-upload");
  if (evalOriginal) {
    evalOriginal.addEventListener("change", () => {
      markEvaluationInputsDirty();
    });
  }

  const evalAdversarial = qs("#eval-adversarial-upload");
  if (evalAdversarial) {
    evalAdversarial.addEventListener("change", () => {
      markEvaluationInputsDirty();
    });
  }

  const evalCheck = qs("#check-eval");
  if (evalCheck) {
    evalCheck.addEventListener("click", checkEvaluationEligibility);
  }

  const evalRun = qs("#run-eval");
  if (evalRun) {
    evalRun.addEventListener("click", runEvaluation);
  }

  qsa(".stage-run-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      await runPipelineStage(btn.dataset.runStage || "");
    });
  });

  qs("#run-pipeline").addEventListener("click", runPipeline);
  qs("#refresh-runs").addEventListener("click", refreshRuns);
  qs("#run-batch").addEventListener("click", runBatch);
  qs("#refresh-reports").addEventListener("click", refreshReports);
}

async function bootstrap() {
  wireEvents();
  try {
    const health = await apiGet("/api/health");
    setHealth(health.status === "ok", "API online");
  } catch (_err) {
    setHealth(false, "API unreachable");
    return;
  }

  try {
    await loadMetadata();
    await loadPdfs();
    markPipelineInputsDirty();
    await refreshScenarioPanes();
    await refreshRuns();
    await refreshReports();
  } catch (err) {
    console.error(err);
  }
}

bootstrap();
