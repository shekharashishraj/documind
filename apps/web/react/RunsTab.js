import React, { useCallback } from "react";
import { useAppState } from "./AppContext.js";
import { apiGet } from "./api.js";
import { DEFAULT_PIPELINE_RUN_ROOT } from "./constants.js";

const h = React.createElement;

export default function RunsTab() {
  const { state, dispatch } = useAppState();
  const items = state.runs || [];
  const labels = (state.metadata && state.metadata.scenario_labels) || {};

  const refreshRuns = useCallback(async () => {
    try {
      const root = encodeURIComponent(state.baseRoot || DEFAULT_PIPELINE_RUN_ROOT);
      const payload = await apiGet(`/api/runs/docs?base_root=${root}`);
      dispatch({ type: "SET_RUNS", payload: payload.items || [] });
    } catch (_) {
      dispatch({ type: "SET_RUNS", payload: [] });
    }
  }, [state.baseRoot, dispatch]);

  return h("section", { id: "runs", className: "tab-panel active" },
    h("div", { className: "panel-header" },
      h("h2", null, "Runs"),
    ),
    h("div", { className: "card fade-in" },
      h("button", { className: "btn btn-secondary", id: "refresh-runs", onClick: refreshRuns }, "\u21BB  Refresh Runs"),
      h("div", { className: "table-wrap" },
        h("table", { id: "runs-table" },
          h("thead", null,
            h("tr", null,
              h("th", null, "Doc ID"),
              h("th", null, "Scenario"),
              h("th", null, "Compromised"),
              h("th", null, "Clean=Gold"),
              h("th", null, "Changed Fields"),
              h("th", null, "Path"),
            ),
          ),
          h("tbody", null,
            items.length === 0
              ? h("tr", null, h("td", { colSpan: 6, style: { textAlign: "center", padding: "32px 16px", color: "#6b7185" } }, "No evaluation runs yet. Run a pipeline then evaluate to see results here."))
              : items.map((row, i) =>
                  h("tr", { key: i },
                    h("td", null, row.doc_id || ""),
                    h("td", null, labels[row.scenario] || row.scenario || ""),
                    h("td", null,
                      h("span", {
                        style: {
                          display: "inline-flex", alignItems: "center", gap: "4px",
                          padding: "2px 8px", borderRadius: "999px", fontSize: "12px", fontWeight: 700,
                          background: row.compromised ? "rgba(248,113,113,0.12)" : "rgba(52,211,153,0.12)",
                          color: row.compromised ? "#f87171" : "#34d399",
                          border: `1px solid ${row.compromised ? "rgba(248,113,113,0.4)" : "rgba(52,211,153,0.4)"}`,
                        },
                      }, row.compromised ? "Yes" : "No"),
                    ),
                    h("td", null, row.clean_matches_gold ? "Yes" : "No"),
                    h("td", null, String(row.changed_target_fields ?? 0)),
                    h("td", null, h("code", null, row.path || "")),
                  ),
                ),
          ),
        ),
      ),
    ),
  );
}
