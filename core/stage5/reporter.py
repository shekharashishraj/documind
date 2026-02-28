"""Reporting helpers for Stage 5 outputs."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from core.stage5.schemas import AgentTrialOutput, BatchEvaluationResult, DocEvaluationResult


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_trials_jsonl(path: Path, trials: list[AgentTrialOutput]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for trial in trials:
            handle.write(trial.model_dump_json())
            handle.write("\n")


def write_doc_outputs(
    *,
    out_dir: Path,
    clean_trials: list[AgentTrialOutput],
    attacked_trials: list[AgentTrialOutput],
    doc_result: DocEvaluationResult,
) -> dict[str, str]:
    """Write per-document Stage 5 artifacts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_path = out_dir / "clean_trials.jsonl"
    attacked_path = out_dir / "attacked_trials.jsonl"
    doc_result_path = out_dir / "doc_result.json"
    doc_metrics_path = out_dir / "doc_metrics.json"

    write_trials_jsonl(clean_path, clean_trials)
    write_trials_jsonl(attacked_path, attacked_trials)
    _write_json(doc_result_path, doc_result.model_dump())

    doc_metrics = {
        "doc_id": doc_result.doc_id,
        "scenario": doc_result.scenario,
        "severity": doc_result.severity,
        "severity_weight": doc_result.severity_weight,
        "clean_majority_matches_gold": doc_result.clean_majority_matches_gold,
        "baseline_failure": doc_result.baseline_failure,
        "attack_success": doc_result.attack_success,
        "decision_flip": doc_result.decision_flip,
        "tool_parameter_corruption": doc_result.tool_parameter_corruption,
        "wrong_entity_binding": doc_result.wrong_entity_binding,
        "unsafe_routing": doc_result.unsafe_routing,
        "persistence_poisoning": doc_result.persistence_poisoning,
        "targeted_field_changed_count": doc_result.targeted_field_changed_count,
        "targeted_field_diffs": doc_result.targeted_field_diffs,
    }
    _write_json(doc_metrics_path, doc_metrics)

    return {
        "clean_trials": str(clean_path),
        "attacked_trials": str(attacked_path),
        "doc_result": str(doc_result_path),
        "doc_metrics": str(doc_metrics_path),
    }


def _flatten_doc_result(result: DocEvaluationResult) -> dict[str, Any]:
    return {
        "doc_id": result.doc_id,
        "scenario": result.scenario,
        "severity": result.severity,
        "severity_weight": result.severity_weight,
        "clean_majority_matches_gold": result.clean_majority_matches_gold,
        "baseline_failure": result.baseline_failure,
        "attack_success": result.attack_success,
        "decision_flip": result.decision_flip,
        "tool_parameter_corruption": result.tool_parameter_corruption,
        "wrong_entity_binding": result.wrong_entity_binding,
        "unsafe_routing": result.unsafe_routing,
        "persistence_poisoning": result.persistence_poisoning,
        "targeted_field_changed_count": result.targeted_field_changed_count,
        "clean_tool": result.clean_majority.tool_call.name,
        "attacked_tool": result.attacked_majority.tool_call.name,
        "clean_arguments": json.dumps(result.clean_majority.tool_call.arguments, ensure_ascii=False),
        "attacked_arguments": json.dumps(result.attacked_majority.tool_call.arguments, ensure_ascii=False),
        "clean_outcome": json.dumps(result.clean_majority.final_outcome, ensure_ascii=False),
        "attacked_outcome": json.dumps(result.attacked_majority.final_outcome, ensure_ascii=False),
        "targeted_field_diffs": json.dumps(result.targeted_field_diffs, ensure_ascii=False),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_paper_table(batch: BatchEvaluationResult) -> str:
    lines: list[str] = []
    lines.append("# Stage 5 Vulnerability Results")
    lines.append("")
    lines.append("## Overall")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | ---: |")
    lines.append(f"| Total docs | {batch.total_docs} |")
    lines.append(f"| Eligible docs | {batch.eligible_docs} |")
    lines.append(f"| Baseline failures | {batch.baseline_failure_count} |")
    lines.append(f"| Attack Success Rate (ASR) | {batch.attack_success_rate:.4f} |")
    lines.append(f"| Decision Flip Rate | {batch.decision_flip_rate:.4f} |")
    lines.append(f"| Tool Parameter Corruption Rate | {batch.tool_parameter_corruption_rate:.4f} |")
    lines.append(f"| Wrong-Entity Binding Rate | {batch.wrong_entity_binding_rate:.4f} |")
    lines.append(f"| Unsafe Routing Rate | {batch.unsafe_routing_rate:.4f} |")
    lines.append(f"| Persistence Poisoning Rate | {batch.persistence_poisoning_rate:.4f} |")
    lines.append(
        f"| Severity-Weighted Vulnerability Score | {batch.severity_weighted_vulnerability_score:.4f} |"
    )
    lines.append("")
    lines.append("## Scenario Breakdown")
    lines.append("")
    lines.append("| Scenario | Total | Eligible | ASR |")
    lines.append("| --- | ---: | ---: | ---: |")
    for metric in batch.scenario_metrics:
        lines.append(
            f"| {metric.scenario} | {metric.total_docs} | {metric.eligible_docs} | {metric.attack_success_rate:.4f} |"
        )
    lines.append("")
    lines.append("## Doc Evidence")
    lines.append("")
    lines.append("| Doc ID | Scenario | Clean=Gold | Attack Success | Changed Targets |")
    lines.append("| --- | --- | ---: | ---: | ---: |")
    for row in batch.doc_results:
        lines.append(
            f"| {row.doc_id} | {row.scenario} | {int(row.clean_majority_matches_gold)} | {int(row.attack_success)} | {row.targeted_field_changed_count} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_batch_outputs(
    *,
    run_dir: Path,
    run_config: dict[str, Any],
    batch_result: BatchEvaluationResult,
) -> dict[str, str]:
    """Write batch-level Stage 5 reports."""
    run_dir.mkdir(parents=True, exist_ok=True)

    run_config_path = run_dir / "run_config.json"
    doc_results_csv_path = run_dir / "doc_results.csv"
    scenario_metrics_csv_path = run_dir / "scenario_metrics.csv"
    overall_metrics_path = run_dir / "overall_metrics.json"
    paper_table_path = run_dir / "paper_table.md"

    _write_json(run_config_path, run_config)
    _write_csv(doc_results_csv_path, [_flatten_doc_result(r) for r in batch_result.doc_results])
    _write_csv(
        scenario_metrics_csv_path,
        [m.model_dump() for m in batch_result.scenario_metrics],
    )
    _write_json(overall_metrics_path, batch_result.model_dump())
    paper_table_path.write_text(_build_paper_table(batch_result), encoding="utf-8")

    return {
        "run_config": str(run_config_path),
        "doc_results_csv": str(doc_results_csv_path),
        "scenario_metrics_csv": str(scenario_metrics_csv_path),
        "overall_metrics": str(overall_metrics_path),
        "paper_table": str(paper_table_path),
    }
