import React, { useState, useCallback, useRef, useEffect } from "react";
import { useAppState } from "./AppContext.js";
import { apiGet, apiPost } from "./api.js";
import {
  STAGE_SEQUENCE,
  emptyStageStatus,
  setStageStatus,
  stageLabel,
  docIdFromPdfPath,
  normalizeOutRootForUi,
  DEFAULT_PIPELINE_RUN_ROOT,
} from "./constants.js";
import { StageCard, ProgressBar, ResultBox, computePipelineProgress, InspectDrawer } from "./components.js";

const h = React.createElement;

const PIPELINE_STAGES = [
  { key: "stage1", title: "Stage 1", icon: "\uD83D\uDD0D" },
  { key: "stage2", title: "Stage 2", icon: "\uD83E\uDDE0" },
  { key: "stage3", title: "Stage 3", icon: "\uD83D\uDEE0\uFE0F" },
  { key: "stage4", title: "Stage 4", icon: "\u26A1" },
];

export default function PipelineTab() {
  const { state, dispatch } = useAppState();

  const selectedPdfPath = state.selectedPdfPath;
  const outRoot = state.outRoot;
  const stageStatus = state.pipelineStageStatus;
  const busy = state.pipelineBusy;
  const result = state.pipelineResult;
  const preview = state.pipelinePreview;
  const progressLabel = state.pipelineProgressLabel;

  const getSelectedOutRoot = useCallback(() => {
    return normalizeOutRootForUi(outRoot || DEFAULT_PIPELINE_RUN_ROOT);
  }, [outRoot]);

  const readRunTypes = () => state.runTypes;

  const hasPdf = Boolean(selectedPdfPath);

  /* ── Computed progress ── */
  const { progress: pipelinePercent, label: computedLabel } = computePipelineProgress(stageStatus);
  const displayLabel = progressLabel !== "Idle" ? progressLabel : computedLabel;

  /* ── Helpers ── */
  const markInputsDirty = useCallback(() => {
    dispatch({ type: "MARK_PIPELINE_INPUTS_DIRTY" });
  }, [dispatch]);

  /* ── Upload state ── */
  const [uploadStatus, setUploadStatus] = useState(null);
  const [dragover, setDragover] = useState(false);
  const [pdfSource, setPdfSource] = useState("upload");
  const [repoOpen, setRepoOpen] = useState(false);

  /* ── Stage 3 attack mode ── */
  const [attackMode, setAttackMode] = useState("none");
  /* ── Inspect artifacts ── */
  const [stageArtifacts, setStageArtifacts] = useState({ stage1: null, stage2: null, stage3: null, stage4: null });
  const [inspecting, setInspecting] = useState(null);
  const fileInputRef = useRef(null);
  const dropdownRef = useRef(null);

  /* Close dropdown on outside click */
  useEffect(() => {
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) setRepoOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleFileUpload = useCallback(async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setUploadStatus({ type: "error", text: "Only PDF files are accepted." });
      return;
    }
    setUploadStatus({ type: "uploading", text: `Uploading ${file.name}...` });
    try {
      const formData = new FormData();
      formData.append("file", file);
      const resp = await fetch("/api/pdfs/upload", { method: "POST", body: formData });
      const payload = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(payload.detail || `Upload failed: ${resp.status}`);
      dispatch({ type: "SET_SELECTED_PDF_PATH", payload: payload.path });
      markInputsDirty();
      setUploadStatus({ type: "success", text: `${payload.filename} uploaded successfully` });
    } catch (err) {
      setUploadStatus({ type: "error", text: err.message });
    }
  }, [dispatch, markInputsDirty]);

  const setPipelineBusy = useCallback((v) => {
    dispatch({ type: "SET_PIPELINE_BUSY", payload: v });
  }, [dispatch]);

  const setPipelineResult = useCallback((message, muted) => {
    dispatch({ type: "SET_PIPELINE_RESULT", payload: { message, muted } });
  }, [dispatch]);

  const setStageStatusAction = useCallback((status, label) => {
    dispatch({ type: "SET_PIPELINE_STAGE_STATUS", payload: { status, label: label || "" } });
  }, [dispatch]);

  const showPreview = useCallback((original, adversarial) => {
    dispatch({ type: "SET_PIPELINE_PREVIEW", payload: { original, adversarial } });
  }, [dispatch]);

  const hidePreview = useCallback(() => {
    dispatch({ type: "SET_PIPELINE_PREVIEW", payload: null });
  }, [dispatch]);

  /* ── hydrate pipeline status from disk ── */
  const hydratePipelineStatusFromDisk = useCallback(async (pdfPath, oRoot) => {
    const docId = docIdFromPdfPath(pdfPath);
    if (!docId) return null;
    const query = new URLSearchParams({ base_root: oRoot });
    try {
      const payload = await apiGet(`/api/doc/${encodeURIComponent(docId)}/status?${query.toString()}`);
      const status = emptyStageStatus();
      const server = payload.stage_status || {};
      STAGE_SEQUENCE.forEach((k) => { status[k] = server[k] ? "done" : "pending"; });
      dispatch({ type: "SET_LAST_BASE_DIR", payload: payload.base_dir || `${oRoot}/${docId}` });
      setStageStatusAction(status);
      return payload;
    } catch (_err) {
      return null;
    }
  }, [dispatch, setStageStatusAction]);

  /* ── Run single stage ── */
  const runPipelineStage = useCallback(async (stageKey) => {
    if (!STAGE_SEQUENCE.includes(stageKey) || busy) return;
    if (!selectedPdfPath) {
      window.alert("Please select a PDF first.");
      setPipelineResult("Please provide a PDF path.", true);
      return;
    }
    const currentOutRoot = getSelectedOutRoot();
    const docId = docIdFromPdfPath(selectedPdfPath);
    if (!docId) { window.alert("Unable to derive document ID from selected PDF path."); return; }

    if (!state.lastBaseDir && stageKey !== "stage1") {
      await hydratePipelineStatusFromDisk(selectedPdfPath, currentOutRoot);
    }

    let currentStatus = { ...stageStatus };
    // check prerequisites
    const idx = STAGE_SEQUENCE.indexOf(stageKey);
    for (let i = 0; i < idx; i++) {
      if (currentStatus[STAGE_SEQUENCE[i]] !== "done") {
        window.alert(`Please run ${stageLabel(STAGE_SEQUENCE[i])} first.`);
        return;
      }
    }

    let baseDir = state.lastBaseDir || `${currentOutRoot}/${docId}`;
    const runTypes = readRunTypes();
    const attackMechanism = state.selectedAttackMechanism;

    setPipelineBusy(true);
    try {
      if (stageKey === "stage1") {
        hidePreview();
        currentStatus = emptyStageStatus();
        currentStatus = setStageStatus(currentStatus, "stage1", "running");
        setStageStatusAction(currentStatus, "Running Stage 1...");

        const stage1 = await apiPost("/api/pipeline/stage1", { pdf_path: selectedPdfPath, out_root: currentOutRoot, run_types: runTypes });
        baseDir = stage1.base_dir;
        dispatch({ type: "SET_LAST_BASE_DIR", payload: baseDir });
        dispatch({ type: "SET_BASE_ROOT", payload: stage1.run_root || currentOutRoot });
        currentStatus = setStageStatus(currentStatus, "stage1", "done");
        setStageStatusAction(currentStatus, "Stage 1 completed");
        setStageArtifacts(prev => ({ ...prev, stage1: { label: "Extracted Text", path: `${baseDir}/byte_extraction/pymupdf/full_text.txt`, stage: "stage1" } }));
        setPipelineResult("Stage 1 completed. Run Stage 2 next.", false);
        return;
      }
      if (stageKey === "stage2") {
        currentStatus = setStageStatus(currentStatus, "stage3", "pending");
        currentStatus = setStageStatus(currentStatus, "stage4", "pending");
        currentStatus = setStageStatus(currentStatus, "stage2", "running");
        setStageStatusAction(currentStatus, "Running Stage 2...");
        await apiPost("/api/pipeline/stage2", { base_dir: baseDir });
        currentStatus = setStageStatus(currentStatus, "stage2", "done");
        setStageStatusAction(currentStatus, "Stage 2 completed");
        setStageArtifacts(prev => ({ ...prev, stage2: { label: "Vulnerability Analysis", path: `${baseDir}/stage2/openai/analysis.json`, stage: "stage2" } }));
        setPipelineResult("Stage 2 completed. Run Stage 3 next.", false);
        return;
      }
      if (stageKey === "stage3") {
        currentStatus = setStageStatus(currentStatus, "stage4", "pending");
        currentStatus = setStageStatus(currentStatus, "stage3", "running");
        setStageStatusAction(currentStatus, "Running Stage 3...");
        await apiPost("/api/pipeline/stage3", { base_dir: baseDir });
        currentStatus = setStageStatus(currentStatus, "stage3", "done");
        setStageStatusAction(currentStatus, "Stage 3 completed");
        setStageArtifacts(prev => ({ ...prev, stage3: { label: "Manipulation Plan", path: `${baseDir}/stage3/openai/manipulation_plan.json`, stage: "stage3" } }));
        setPipelineResult("Stage 3 completed. Run Stage 4 to generate adversarial PDF.", false);
        return;
      }
      /* stage4 */
      currentStatus = setStageStatus(currentStatus, "stage4", "running");
      setStageStatusAction(currentStatus, "Running Stage 4...");
      const stage4 = await apiPost("/api/pipeline/stage4", { base_dir: baseDir, source_pdf_path: selectedPdfPath, attack_mechanism: attackMechanism, priority_filter: "all" });
      currentStatus = setStageStatus(currentStatus, "stage4", "done");
      setStageStatusAction(currentStatus);
      const originalPreview = stage4.preview_original_pdf || selectedPdfPath;
      const adversarialPreview = stage4.preview_adversarial_pdf || `${baseDir}/stage4/final_overlay.pdf`;
      showPreview(originalPreview, adversarialPreview);
      setStageArtifacts(prev => ({ ...prev, stage4: { label: "Adversarial PDF", path: adversarialPreview, stage: "stage4" } }));
      setPipelineResult(`Adversarial document generated for ${stage4.doc_id}. Review the Original vs Adversarial previews below, then open Evaluation to run the agent-backend check.`, false);
    } catch (err) {
      currentStatus = setStageStatus(currentStatus, stageKey, "failed");
      setStageStatusAction(currentStatus, "Failed");
      setPipelineResult(`${stageLabel(stageKey)} failed: ${err.message}`, true);
    } finally {
      setPipelineBusy(false);
    }
  }, [state, busy, selectedPdfPath, stageStatus, dispatch, getSelectedOutRoot, setPipelineBusy, setPipelineResult, setStageStatusAction, hidePreview, showPreview, hydratePipelineStatusFromDisk]);

  /* ── Run all pipeline ── */
  const runPipeline = useCallback(async () => {
    if (busy) return;
    if (!selectedPdfPath) {
      setPipelineResult("Please provide a PDF path.", true);
      return;
    }
    const currentOutRoot = getSelectedOutRoot();
    const runTypes = readRunTypes();
    const attackMechanism = state.selectedAttackMechanism;

    hidePreview();
    let currentStatus = emptyStageStatus();
    setStageStatusAction(currentStatus, "Starting pipeline...");
    setPipelineResult("Generating adversarial document (Stage 1 to Stage 4). This can take a while depending on OCR/LLM load.", true);
    setPipelineBusy(true);

    try {
      currentStatus = setStageStatus(currentStatus, "stage1", "running");
      setStageStatusAction(currentStatus);
      const stage1 = await apiPost("/api/pipeline/stage1", { pdf_path: selectedPdfPath, out_root: currentOutRoot, run_types: runTypes });
      currentStatus = setStageStatus(currentStatus, "stage1", "done");
      setStageStatusAction(currentStatus, "Stage 1 completed");

      const baseDir = stage1.base_dir;
      const sourcePdfPath = stage1.source_pdf_path || selectedPdfPath;
      setStageArtifacts(prev => ({ ...prev, stage1: { label: "Extracted Text", path: `${baseDir}/byte_extraction/pymupdf/full_text.txt`, stage: "stage1" } }));

      currentStatus = setStageStatus(currentStatus, "stage2", "running");
      setStageStatusAction(currentStatus);
      await apiPost("/api/pipeline/stage2", { base_dir: baseDir });
      currentStatus = setStageStatus(currentStatus, "stage2", "done");
      setStageStatusAction(currentStatus, "Stage 2 completed");
      setStageArtifacts(prev => ({ ...prev, stage2: { label: "Vulnerability Analysis", path: `${baseDir}/stage2/openai/analysis.json`, stage: "stage2" } }));

      currentStatus = setStageStatus(currentStatus, "stage3", "running");
      setStageStatusAction(currentStatus);
      await apiPost("/api/pipeline/stage3", { base_dir: baseDir });
      currentStatus = setStageStatus(currentStatus, "stage3", "done");
      setStageStatusAction(currentStatus, "Stage 3 completed");
      setStageArtifacts(prev => ({ ...prev, stage3: { label: "Manipulation Plan", path: `${baseDir}/stage3/openai/manipulation_plan.json`, stage: "stage3" } }));

      currentStatus = setStageStatus(currentStatus, "stage4", "running");
      setStageStatusAction(currentStatus);
      const stage4 = await apiPost("/api/pipeline/stage4", { base_dir: baseDir, source_pdf_path: sourcePdfPath, attack_mechanism: attackMechanism, priority_filter: "all" });
      currentStatus = setStageStatus(currentStatus, "stage4", "done");
      setStageStatusAction(currentStatus);

      const originalPreview = stage4.preview_original_pdf || sourcePdfPath;
      const adversarialPreview = stage4.preview_adversarial_pdf || `${baseDir}/stage4/final_overlay.pdf`;
      showPreview(originalPreview, adversarialPreview);
      setStageArtifacts(prev => ({ ...prev, stage4: { label: "Adversarial PDF", path: adversarialPreview, stage: "stage4" } }));
      setPipelineResult(`Adversarial document generated for ${stage4.doc_id}. Review the Original vs Adversarial previews below, then open Evaluation to run the agent-backend check.`, false);

      dispatch({ type: "SET_BASE_ROOT", payload: stage1.run_root || currentOutRoot });
      dispatch({ type: "SET_LAST_BASE_DIR", payload: baseDir });

      // Refresh downstream
      try {
        const root = encodeURIComponent(stage1.run_root || currentOutRoot);
        const runs = await apiGet(`/api/runs/docs?base_root=${root}`);
        dispatch({ type: "SET_RUNS", payload: runs.items || [] });
      } catch (_) {}
      try {
        const outDir = encodeURIComponent(state.batchConfig.outDir || "stage5_runs");
        const reports = await apiGet(`/api/runs/batch?out_dir=${outDir}`);
        dispatch({ type: "SET_REPORTS", payload: reports.items || [] });
      } catch (_) {}
    } catch (err) {
      const running = STAGE_SEQUENCE.find((s) => currentStatus[s] === "running");
      if (running) currentStatus = setStageStatus(currentStatus, running, "failed");
      setStageStatusAction(currentStatus, "Failed");
      hidePreview();
      setPipelineResult(`Pipeline failed: ${err.message}`, true);
    } finally {
      setPipelineBusy(false);
    }
  }, [state, busy, selectedPdfPath, dispatch, getSelectedOutRoot, setPipelineBusy, setPipelineResult, setStageStatusAction, hidePreview, showPreview]);

  /* ── Run type toggle ── */
  const toggleRunType = useCallback((value) => {
    const current = [...state.runTypes];
    const idx = current.indexOf(value);
    if (idx >= 0) current.splice(idx, 1);
    else current.push(value);
    dispatch({ type: "SET_RUN_TYPES", payload: current });
  }, [state.runTypes, dispatch]);

  /* ── Render ── */
  const showWarning = state.selectedAttackMechanism !== "auto";

  return h("section", { id: "pipeline", className: "tab-panel active" },
    h("div", { className: "hero-banner" },
      h("img", { src: "/static/homepage-hero.svg", className: "hero-banner-img", alt: "MALDOC Security Platform" }),
    ),
    h("div", { className: "panel-header" },
      h("div", { className: "panel-title-row" },
        h("h2", null, "Adversarial Document Generation"),
        h("div", { className: "threat-badges" },
          h("span", { className: "threat-badge pdf-badge", title: "PDF Attack Surface" }, "\uD83D\uDCC4"),
          h("span", { className: "threat-badge hacker-badge", title: "Adversary Model" }, "\uD83D\uDC80"),
          h("span", { className: "threat-badge spider-badge", title: "Threat Spider" }, "\uD83D\uDD77\uFE0F"),
        ),
      ),
    ),
    h("div", { className: "two-col" },
      /* Left: Controls */
      h("div", { className: "card fade-in controls-card" },
        h("div", { className: "corner-sticker", title: "Threat Vector" }, "\uD83D\uDD77\uFE0F"),
        h("h3", null, "\u2699\uFE0F  Controls"),

        /* ── PDF source selector: Upload (left) | Repository (right) ── */
        h("div", { className: "pdf-source-row" },

          /* Left: File Upload */
          h("div", {
            className: `pdf-source-option${pdfSource === "upload" ? " active" : ""}`,
            onClick: () => setPdfSource("upload"),
          },
            h("h4", null,
              h("span", { className: "source-icon" }, "\uD83D\uDCC4"),
              "File Upload",
            ),
            h("div", {
              className: `upload-zone${dragover ? " dragover" : ""}`,
              onDragOver: (e) => { e.preventDefault(); setDragover(true); },
              onDragLeave: () => setDragover(false),
              onDrop: (e) => {
                e.preventDefault();
                setDragover(false);
                setPdfSource("upload");
                const file = e.dataTransfer.files && e.dataTransfer.files[0];
                handleFileUpload(file);
              },
              onClick: (e) => {
                e.stopPropagation();
                setPdfSource("upload");
                fileInputRef.current && fileInputRef.current.click();
              },
            },
              h("img", { src: "/static/pdf-cyber.svg", className: "upload-zone-svg", alt: "PDF upload", draggable: false }),
              h("p", { className: "upload-zone-text" },
                "Drag & drop a PDF here or ", h("strong", null, "browse"),
              ),
              h("input", {
                ref: fileInputRef,
                type: "file",
                accept: ".pdf",
                onChange: (e) => {
                  const file = e.target.files && e.target.files[0];
                  handleFileUpload(file);
                  e.target.value = "";
                },
              }),
            ),
            uploadStatus && h("div", { className: `upload-status ${uploadStatus.type}` },
              uploadStatus.type === "uploading" ? "\u23F3" : uploadStatus.type === "success" ? "\u2713" : "\u2717",
              " ", uploadStatus.text,
            ),
            pdfSource === "upload" && selectedPdfPath && h("div", { className: "selected-file-pill" },
              h("span", null, "\u{1F4C4}"),
              h("span", { className: "file-name" }, selectedPdfPath.split("/").pop()),
              h("button", {
                className: "clear-btn",
                onClick: (e) => {
                  e.stopPropagation();
                  dispatch({ type: "SET_SELECTED_PDF_PATH", payload: "" });
                  setUploadStatus(null);
                  markInputsDirty();
                },
              }, "\u2715"),
            ),
          ),

          /* Right: Select from Repository */
          h("div", {
            className: `pdf-source-option${pdfSource === "repo" ? " active" : ""}`,
            onClick: () => setPdfSource("repo"),
          },
            h("h4", null,
              h("span", { className: "source-icon" }, "\u{1F4C2}"),
              "Select from Repository",
            ),
            /* Custom dropdown */
            h("div", { className: "custom-dropdown", ref: dropdownRef, onClick: (e) => e.stopPropagation() },
              h("button", {
                type: "button",
                className: `custom-dropdown-trigger${repoOpen ? " open" : ""}`,
                onClick: () => setRepoOpen((v) => !v),
              },
                h("span", null, (pdfSource === "repo" && selectedPdfPath) ? selectedPdfPath.split("/").pop().replace(/\.pdf$/i, "") : "Choose a PDF\u2026"),
                h("span", { className: "dropdown-chevron" }, "\u25BE"),
              ),
              repoOpen && h("ul", { className: "custom-dropdown-list" },
                state.pdfs.map((p) =>
                  h("li", {
                    key: p,
                    className: `custom-dropdown-item${selectedPdfPath === p ? " selected" : ""}`,
                    onClick: () => {
                      setPdfSource("repo");
                      dispatch({ type: "SET_SELECTED_PDF_PATH", payload: p });
                      markInputsDirty();
                      setUploadStatus(null);
                      setRepoOpen(false);
                    },
                  }, p.split("/").pop().replace(/\.pdf$/i, "")),
                ),
              ),
            ),
            pdfSource === "repo" && selectedPdfPath && h("div", { className: "selected-file-pill" },
              h("span", null, "\u{1F4C4}"),
              h("span", { className: "file-name" }, selectedPdfPath.split("/").pop().replace(/\.pdf$/i, "")),
              h("button", {
                className: "clear-btn",
                onClick: (e) => {
                  e.stopPropagation();
                  dispatch({ type: "SET_SELECTED_PDF_PATH", payload: "" });
                  markInputsDirty();
                },
              }, "\u2715"),
            ),
          ),
        ),
        /* Expert mode / Advanced options */
        h("div", { className: "expert-mode-row" },
          h("span", { className: "expert-mode-badge" }, "Expert mode"),
          h("span", { className: "expert-mode-bracket" }, "(Advanced options)"),
        ),
        h("div", { className: "advanced-block" },
          h("div", { className: "form-grid advanced-grid" },
            h("div", null,
              h("label", { htmlFor: "attack-mechanism" }, "Stage 4 Mechanism Mode"),
              h("select", {
                id: "attack-mechanism",
                value: state.selectedAttackMechanism,
                onChange: (e) => dispatch({ type: "SET_SELECTED_ATTACK_MECHANISM", payload: e.target.value }),
              },
                state.attackMechanisms.map(([key, label]) =>
                  h("option", { key, value: key }, label),
                ),
              ),
              h("p", { className: "hint" }, "Default is ", h("code", null, "auto"), " (planner strategy drives mechanism)."),
              showWarning && h("p", { className: "hint override-warning" },
                "Manual override is enabled. This is an ablation mode and may diverge from paper-aligned planner coupling.",
              ),
            ),
            h("div", null,
              h("label", null, "Stage 1 mechanisms"),
              h("p", { className: "hint" }, "Choose how text is extracted in Stage 1."),
              h("div", { className: "checkbox-row mechanism-list" },
                [
                  { value: "byte_extraction", name: "Byte Extraction", desc: "Extract text directly from PDF bytes (default)." },
                  { value: "ocr", name: "OCR", desc: "Extract text from rendered page images." },
                  { value: "vlm", name: "VLM", desc: "Use vision-language parsing for visual text/context." },
                ].map((m) =>
                  h("label", { key: m.value, className: "mechanism-item" },
                    h("input", {
                      type: "checkbox",
                      value: m.value,
                      checked: state.runTypes.includes(m.value),
                      onChange: () => toggleRunType(m.value),
                    }),
                    h("span", null,
                      h("span", { className: "mechanism-name" }, m.name),
                      h("span", { className: "mechanism-desc" }, m.desc),
                    ),
                  ),
                ),
              ),
            ),
          ),
          /* ── Stage 3 attack mode selector ── */
          h("div", { className: "stage3-box" },
            h("div", { className: "stage3-box-header" },
              h("span", { className: "stage3-icon" }, "\uD83E\uDDE0"),
              h("span", null, "Attack Mode"),
            ),
            h("select", {
              id: "attack-mode",
              className: "stage3-select",
              value: attackMode,
              onChange: (e) => setAttackMode(e.target.value),
            },
              h("option", { value: "none" }, "None (Off)"),
              h("option", { value: "task_degradation" }, "Task Degradation"),
              h("option", { value: "tool_misfire" }, "Tool Misfire"),
              h("option", { value: "resource_inflation" }, "Resource Inflation"),
            ),
          ),
        ),
        h("button", {
          id: "run-pipeline",
          className: "btn btn-auto",
          disabled: busy || !hasPdf,
          onClick: runPipeline,
        }, "\u25B6\uFE0E  Auto"),
      ),

      /* Right: Timeline */
      h("div", { className: "card fade-in", style: { display: "flex", flexDirection: "column" } },
        h("h3", null, "Stage Timeline"),
        h(ProgressBar, { percent: pipelinePercent, label: displayLabel }),
        h("div", { className: "stage-cards", id: "stage-cards" },
          PIPELINE_STAGES.map((s) =>
            h(StageCard, {
              key: s.key,
              stageKey: s.key,
              title: s.title,
              icon: s.icon,
              status: stageStatus[s.key] || "pending",
              runButton: h("button", {
                className: "btn btn-secondary stage-run-btn",
                "data-run-stage": s.key,
                disabled: busy || !hasPdf,
                onClick: () => runPipelineStage(s.key),
              }, `\u25B8 Run ${s.title}`),
              inspectButton: (stageArtifacts[s.key] && stageStatus[s.key] === "done")
                ? h("button", { className: "btn-inspect", onClick: () => setInspecting(stageArtifacts[s.key]) }, "\uD83D\uDC41 Inspect")
                : null,
            }),
          ),
        ),
        h(ResultBox, { message: result.message, muted: result.muted, id: "pipeline-result" }),
      ),
    ),
    preview && h("div", { className: "preview-section", id: "pipeline-preview" },
      h("div", { className: "preview-grid" },
        h("div", { className: "preview-card" },
          h("h4", null, "Original Document"),
          h("iframe", { id: "preview-original", title: "Original document preview", loading: "lazy", src: `/api/files/preview?path=${encodeURIComponent(preview.original)}#toolbar=0` }),
        ),
        h("div", { className: "preview-card" },
          h("h4", null, "Adversarial Document"),
          h("iframe", { id: "preview-adversarial", title: "Adversarial document preview", loading: "lazy", src: `/api/files/preview?path=${encodeURIComponent(preview.adversarial)}#toolbar=0` }),
        ),
      ),
    ),
    inspecting && h(InspectDrawer, { artifact: inspecting, onClose: () => setInspecting(null) }),
  );
}
