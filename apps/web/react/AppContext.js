import React, { createContext, useContext, useReducer, useRef, useCallback } from "react";
import { emptyStageStatus, emptyStage5FlowStatus, DEFAULT_PIPELINE_RUN_ROOT } from "./constants.js";

/* ── Initial State ────────────────────────────────────────────── */
export const INITIAL_STATE = {
  baseRoot: DEFAULT_PIPELINE_RUN_ROOT,
  pdfs: [],
  metadata: null,
  lastBaseDir: "",
  pipelineStageStatus: emptyStageStatus(),
  pipelineBusy: false,
  pipelineResult: { message: "No pipeline run yet.", muted: true },
  pipelineProgressLabel: "Idle",
  pipelinePreview: null, // { original, adversarial } or null
  evalPanes: {},
  preparedStage5BaseDirs: {},
  evaluation: {
    preparedBaseDir: "",
    flowStatus: emptyStage5FlowStatus(),
    activeCleanDomain: null,
    activeAttackedDomain: null,
    showGeneralFallback: false,
    message: { text: "Eligibility not checked.", muted: true },
    agentPanelNote: { text: "No evaluation run yet.", muted: true },
    runEnabled: false,
    summary: null,
  },
  runs: [],
  reports: [],
  health: { ok: false, text: "Checking API..." },
  activeTab: "pipeline",
  attackMechanisms: [],
  selectedAttackMechanism: "auto",
  selectedPdfPath: "",
  outRoot: DEFAULT_PIPELINE_RUN_ROOT,
  selectedEvalScenario: "auto",
  evalTrials: 3,
  batchConfig: {
    docIds: "",
    model: "gpt-5-2025-08-07",
    trials: 3,
    outDir: "stage5_runs",
  },
  batchSummary: { text: "No batch run yet.", muted: true },
  batchBusy: false,
  runTypes: ["byte_extraction"],
};

/* ── Reducer ──────────────────────────────────────────────────── */
export function appReducer(state, action) {
  switch (action.type) {
    case "SET_HEALTH":
      return { ...state, health: action.payload };

    case "SET_ACTIVE_TAB":
      return { ...state, activeTab: action.payload };

    case "SET_PDFS":
      return { ...state, pdfs: action.payload };

    case "SET_METADATA": {
      const meta = action.payload;
      const newState = { ...state, metadata: meta };
      if (meta.pipeline_run_root) {
        newState.baseRoot = String(meta.pipeline_run_root);
        if (!state.outRoot || state.outRoot === DEFAULT_PIPELINE_RUN_ROOT) {
          newState.outRoot = String(meta.pipeline_run_root);
        }
      }
      return newState;
    }

    case "SET_ATTACK_MECHANISMS":
      return { ...state, attackMechanisms: action.payload };

    case "SET_SELECTED_ATTACK_MECHANISM":
      return { ...state, selectedAttackMechanism: action.payload };

    case "SET_SELECTED_PDF_PATH":
      return { ...state, selectedPdfPath: action.payload };

    case "SET_PIPELINE_STAGE_STATUS":
      return {
        ...state,
        pipelineStageStatus: { ...action.payload.status },
        pipelineProgressLabel: action.payload.label || state.pipelineProgressLabel,
      };

    case "SET_PIPELINE_BUSY":
      return { ...state, pipelineBusy: action.payload };

    case "SET_PIPELINE_RESULT":
      return { ...state, pipelineResult: action.payload };

    case "SET_PIPELINE_PROGRESS_LABEL":
      return { ...state, pipelineProgressLabel: action.payload };

    case "SET_PIPELINE_PREVIEW":
      return { ...state, pipelinePreview: action.payload };

    case "SET_LAST_BASE_DIR":
      return { ...state, lastBaseDir: action.payload };

    case "SET_BASE_ROOT":
      return { ...state, baseRoot: action.payload };

    case "SET_RUNS":
      return { ...state, runs: action.payload };

    case "SET_REPORTS":
      return { ...state, reports: action.payload };

    case "SET_RUN_TYPES":
      return { ...state, runTypes: action.payload };

    case "SET_EVAL_SCENARIO":
      return { ...state, selectedEvalScenario: action.payload };

    case "SET_EVAL_TRIALS":
      return { ...state, evalTrials: action.payload };

    case "SET_EVAL_RUN_ENABLED":
      return { ...state, evaluation: { ...state.evaluation, runEnabled: action.payload } };

    case "SET_EVAL_MESSAGE":
      return { ...state, evaluation: { ...state.evaluation, message: action.payload } };

    case "SET_EVAL_AGENT_NOTE":
      return { ...state, evaluation: { ...state.evaluation, agentPanelNote: action.payload } };

    case "SET_EVAL_FLOW_STATUS":
      return { ...state, evaluation: { ...state.evaluation, flowStatus: action.payload } };

    case "SET_EVAL_PREPARED_BASE_DIR":
      return { ...state, evaluation: { ...state.evaluation, preparedBaseDir: action.payload } };

    case "SET_EVAL_ACTIVE_DOMAINS":
      return {
        ...state,
        evaluation: {
          ...state.evaluation,
          activeCleanDomain: action.payload.clean,
          activeAttackedDomain: action.payload.attacked,
        },
      };

    case "SET_EVAL_SHOW_GENERAL_FALLBACK":
      return { ...state, evaluation: { ...state.evaluation, showGeneralFallback: action.payload } };

    case "SET_EVAL_SUMMARY":
      return { ...state, evaluation: { ...state.evaluation, summary: action.payload } };

    case "RESET_EVALUATION":
      return {
        ...state,
        evaluation: {
          ...INITIAL_STATE.evaluation,
          flowStatus: emptyStage5FlowStatus(),
        },
        evalPanes: {},
        preparedStage5BaseDirs: {},
      };

    case "SET_EVAL_PANE": {
      const { scenario, data } = action.payload;
      return { ...state, evalPanes: { ...state.evalPanes, [scenario]: data } };
    }

    case "SET_PREPARED_STAGE5_BASE_DIR": {
      const { scenario, baseDir } = action.payload;
      return { ...state, preparedStage5BaseDirs: { ...state.preparedStage5BaseDirs, [scenario]: baseDir } };
    }

    case "SET_BATCH_CONFIG":
      return { ...state, batchConfig: { ...state.batchConfig, ...action.payload } };

    case "SET_BATCH_SUMMARY":
      return { ...state, batchSummary: action.payload };

    case "SET_BATCH_BUSY":
      return { ...state, batchBusy: action.payload };

    case "MARK_PIPELINE_INPUTS_DIRTY":
      return {
        ...state,
        lastBaseDir: "",
        pipelinePreview: null,
        pipelineStageStatus: emptyStageStatus(),
        pipelineProgressLabel: "Idle",
        pipelineResult: { message: "No pipeline run yet.", muted: true },
      };

    default:
      return state;
  }
}

/* ── Context ──────────────────────────────────────────────────── */
const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [state, dispatch] = useReducer(appReducer, INITIAL_STATE);
  const timersRef = useRef({});

  const value = React.useMemo(() => ({ state, dispatch, timersRef }), [state]);

  return React.createElement(AppContext.Provider, { value }, children);
}

export function useAppState() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useAppState must be inside AppProvider");
  return ctx;
}
