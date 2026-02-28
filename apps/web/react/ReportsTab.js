import React, { useCallback } from "react";
import { useAppState } from "./AppContext.js";
import { apiGet, apiPost } from "./api.js";

const h = React.createElement;

export default function ReportsTab() {
  const { state, dispatch } = useAppState();
  const items = state.reports || [];
  const batch = state.batchConfig;
  const batchSummary = state.batchSummary;
  const batchBusy = state.batchBusy;

  const refreshReports = useCallback(async () => {
    try {
      const outDir = encodeURIComponent(batch.outDir || "stage5_runs");
      const payload = await apiGet(`/api/runs/batch?out_dir=${outDir}`);
      dispatch({ type: "SET_REPORTS", payload: payload.items || [] });
    } catch (_) {
      dispatch({ type: "SET_REPORTS", payload: [] });
    }
  }, [batch.outDir, dispatch]);

  const runBatch = useCallback(async () => {
    const baseRoot = state.baseRoot || "pipeline_run";
    const docIds = batch.docIds ? batch.docIds.split(",").map((x) => x.trim()).filter(Boolean) : null;

    dispatch({ type: "SET_BATCH_BUSY", payload: true });
    dispatch({ type: "SET_BATCH_SUMMARY", payload: { text: "Running batch evaluation...", muted: true } });

    try {
      const payload = {
        base_root: baseRoot,
        doc_ids: docIds,
        model: batch.model,
        trials: batch.trials,
        out_dir: batch.outDir,
      };
      const response = await apiPost("/api/stage5/batch", payload);
      const summary = response.batch_summary || {};
      const lines = [];
      lines.push(`Successful compromises: ${summary.successful_compromises || 0} out of ${summary.eligible_docs || 0} eligible documents.`);
      lines.push(`ASR: ${Number(summary.attack_success_rate || 0).toFixed(4)}`);
      lines.push(`Decision Flip Rate: ${Number(summary.decision_flip_rate || 0).toFixed(4)}`);
      lines.push(`Parameter Corruption Rate: ${Number(summary.tool_parameter_corruption_rate || 0).toFixed(4)}`);
      lines.push(`Severity-Weighted Score: ${Number(summary.severity_weighted_vulnerability_score || 0).toFixed(4)}`);

      const reportPaths = (response.result && response.result.report_paths) || {};
      if (Object.keys(reportPaths).length) {
        lines.push("Reports:");
        Object.entries(reportPaths).forEach(([k, v]) => lines.push(`- ${k}: ${v}`));
      }

      dispatch({ type: "SET_BATCH_SUMMARY", payload: { text: lines.join("\n"), muted: false } });
      await refreshReports();

      // Refresh runs too
      try {
        const root = encodeURIComponent(state.baseRoot || "pipeline_run");
        const runs = await apiGet(`/api/runs/docs?base_root=${root}`);
        dispatch({ type: "SET_RUNS", payload: runs.items || [] });
      } catch (_) {}
    } catch (err) {
      dispatch({ type: "SET_BATCH_SUMMARY", payload: { text: `Batch evaluation failed: ${err.message}`, muted: true } });
    } finally {
      dispatch({ type: "SET_BATCH_BUSY", payload: false });
    }
  }, [state, batch, dispatch, refreshReports]);

  return h("section", { id: "reports", className: "tab-panel active" },
    h("div", { className: "panel-header" },
      h("h2", null, "Reports"),
      h("p", null, "Legacy Stage 5 batch reports (optional)."),
    ),
    h("div", { className: "card fade-in" },
      h("div", { className: "form-grid" },
        h("div", null,
          h("label", { htmlFor: "batch-docs" }, "Batch doc IDs (comma-separated)"),
          h("input", {
            id: "batch-docs",
            type: "text",
            placeholder: "doc_id_1,doc_id_2",
            value: batch.docIds,
            onChange: (e) => dispatch({ type: "SET_BATCH_CONFIG", payload: { docIds: e.target.value } }),
          }),
          h("p", { className: "hint" }, "Leave empty to use demo batch from config."),
        ),
        h("div", null,
          h("label", { htmlFor: "batch-model" }, "Batch model"),
          h("input", {
            id: "batch-model",
            type: "text",
            value: batch.model,
            onChange: (e) => dispatch({ type: "SET_BATCH_CONFIG", payload: { model: e.target.value } }),
          }),
        ),
        h("div", null,
          h("label", { htmlFor: "batch-trials" }, "Batch trials"),
          h("input", {
            id: "batch-trials",
            type: "number",
            min: 1,
            max: 9,
            value: batch.trials,
            onChange: (e) => dispatch({ type: "SET_BATCH_CONFIG", payload: { trials: Number(e.target.value) || 3 } }),
          }),
        ),
        h("div", null,
          h("label", { htmlFor: "batch-out-dir" }, "Batch output directory"),
          h("input", {
            id: "batch-out-dir",
            type: "text",
            value: batch.outDir,
            onChange: (e) => dispatch({ type: "SET_BATCH_CONFIG", payload: { outDir: e.target.value } }),
          }),
        ),
      ),
      h("button", {
        className: "btn btn-primary",
        id: "run-batch",
        disabled: batchBusy,
        onClick: runBatch,
      }, "\u25B6\uFE0E  Run Batch Evaluation"),
      h("div", { className: `result-box${batchSummary.muted ? " muted" : ""}`, id: "batch-summary" }, batchSummary.text),
    ),
    h("div", { className: "card fade-in" },
      h("h3", null, "Existing Batch Reports"),
      h("button", { className: "btn btn-secondary", id: "refresh-reports", onClick: refreshReports }, "\u21BB  Refresh Reports"),
      h("div", { className: "table-wrap" },
        h("table", { id: "reports-table" },
          h("thead", null,
            h("tr", null,
              h("th", null, "Run ID"),
              h("th", null, "Eligible Docs"),
              h("th", null, "ASR"),
              h("th", null, "Severity Weighted"),
              h("th", null, "Path"),
              h("th", null, "Paper Table"),
            ),
          ),
          h("tbody", null,
            items.length === 0
              ? h("tr", null, h("td", { colSpan: 6, style: { textAlign: "center", padding: "32px 16px", color: "#6b7185" } }, "No batch reports yet. Run a batch evaluation to generate reports."))
              : items.map((row, i) =>
              h("tr", { key: i },
                h("td", null, row.run_id || ""),
                h("td", null, String(row.eligible_docs ?? "")),
                h("td", null, row.attack_success_rate !== undefined ? Number(row.attack_success_rate).toFixed(4) : ""),
                h("td", null, row.severity_weighted_vulnerability_score !== undefined ? Number(row.severity_weighted_vulnerability_score).toFixed(4) : ""),
                h("td", null, h("code", null, row.path || "")),
                h("td", null, row.paper_table ? h("code", null, row.paper_table) : ""),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
