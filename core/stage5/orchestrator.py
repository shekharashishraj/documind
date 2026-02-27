"""Stage 5 orchestration: single-doc and batch vulnerability simulation after Stage 4."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.stage5.agent_runner import run_agent_trials
from core.stage5.evaluator import aggregate_batch_results, evaluate_doc
from core.stage5.input_loader import load_clean_text, parse_attacked_pdf, resolve_attacked_pdf
from core.stage5.reporter import write_batch_outputs, write_doc_outputs
from core.stage5.schemas import BatchEvaluationResult, DocEvaluationResult, ScenarioSpec


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCENARIO_SPECS_PATH = PROJECT_ROOT / "configs" / "stage5" / "scenario_specs.json"
DEFAULT_DEMO_BATCH_PATH = PROJECT_ROOT / "configs" / "stage5" / "demo_batch.json"
DEFAULT_SEVERITY_WEIGHTS_PATH = PROJECT_ROOT / "configs" / "stage5" / "severity_weights.json"
DEFAULT_SEVERITY_WEIGHTS = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Config not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_scenario_specs(path: str | Path | None = None) -> dict[str, ScenarioSpec]:
    """Load per-document scenario specs keyed by doc_id."""
    resolved = Path(path) if path else DEFAULT_SCENARIO_SPECS_PATH
    raw = _load_json(resolved)

    rows: list[dict[str, Any]]
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict) and isinstance(raw.get("specs"), list):
        rows = raw["specs"]
    elif isinstance(raw, dict) and raw.get("doc_id"):
        rows = [raw]
    else:
        raise ValueError(f"Invalid scenario specs format in {resolved}")

    by_doc_id: dict[str, ScenarioSpec] = {}
    for row in rows:
        spec = ScenarioSpec.model_validate(row)
        by_doc_id[spec.doc_id] = spec
    return by_doc_id


def load_demo_doc_ids(path: str | Path | None = None) -> list[str]:
    """Load default one-doc-per-scenario demo batch IDs."""
    resolved = Path(path) if path else DEFAULT_DEMO_BATCH_PATH
    raw = _load_json(resolved)
    if isinstance(raw, dict) and isinstance(raw.get("doc_ids"), list):
        return [str(x) for x in raw["doc_ids"]]
    if isinstance(raw, list):
        return [str(x) for x in raw]
    raise ValueError(f"Invalid demo batch format in {resolved}")


def load_severity_weights(path: str | Path | None = None) -> dict[str, int]:
    """Load severity weights used by weighted vulnerability scoring."""
    weights = dict(DEFAULT_SEVERITY_WEIGHTS)
    resolved = Path(path) if path else DEFAULT_SEVERITY_WEIGHTS_PATH
    if resolved.is_file():
        raw = _load_json(resolved)
        if isinstance(raw, dict):
            for key, value in raw.items():
                try:
                    weights[str(key)] = int(value)
                except Exception:
                    continue
    return weights


def _run_doc_with_spec(
    *,
    base_dir: Path,
    spec: ScenarioSpec,
    adv_pdf: str | None,
    model: str,
    trials: int,
    out_subdir: str,
    api_key: str | None,
    severity_weights: dict[str, int],
) -> tuple[DocEvaluationResult, dict[str, str]]:
    if not base_dir.is_dir():
        raise FileNotFoundError(f"Document base_dir not found: {base_dir}")

    out_dir = base_dir / out_subdir
    out_dir.mkdir(parents=True, exist_ok=True)

    clean_text, clean_source = load_clean_text(base_dir)
    attacked_pdf = resolve_attacked_pdf(base_dir, adv_pdf=adv_pdf)
    attacked_text, attacked_source = parse_attacked_pdf(attacked_pdf, out_dir)

    clean_trials = run_agent_trials(
        doc_id=spec.doc_id,
        variant="clean",
        document_text=clean_text,
        parse_source=clean_source,
        spec=spec,
        model=model,
        trials=trials,
        api_key=api_key,
    )
    attacked_trials = run_agent_trials(
        doc_id=spec.doc_id,
        variant="attacked",
        document_text=attacked_text,
        parse_source=attacked_source,
        spec=spec,
        model=model,
        trials=trials,
        api_key=api_key,
    )

    doc_result = evaluate_doc(
        spec=spec,
        clean_trials=clean_trials,
        attacked_trials=attacked_trials,
        severity_weights=severity_weights,
    )

    output_paths = write_doc_outputs(
        out_dir=out_dir,
        clean_trials=clean_trials,
        attacked_trials=attacked_trials,
        doc_result=doc_result,
    )
    return doc_result, output_paths


def run_stage5_doc(
    base_dir: str | Path,
    *,
    scenario: str = "auto",
    adv_pdf: str | None = None,
    model: str = "gpt-5-2025-08-07",
    trials: int = 3,
    out_subdir: str = "stage5_eval",
    api_key: str | None = None,
    scenario_specs_path: str | Path | None = None,
    severity_weights_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run Stage 5 on one document base directory."""
    base_path = Path(base_dir)
    doc_id = base_path.name

    specs = load_scenario_specs(scenario_specs_path)
    if doc_id not in specs:
        raise ValueError(
            f"Missing scenario spec for doc_id={doc_id}. Add it to {scenario_specs_path or DEFAULT_SCENARIO_SPECS_PATH}."
        )
    spec = specs[doc_id]

    if scenario != "auto" and scenario != spec.scenario:
        raise ValueError(
            f"Scenario mismatch for doc_id={doc_id}: requested={scenario}, spec={spec.scenario}."
        )

    severity_weights = load_severity_weights(severity_weights_path)
    doc_result, output_paths = _run_doc_with_spec(
        base_dir=base_path,
        spec=spec,
        adv_pdf=adv_pdf,
        model=model,
        trials=trials,
        out_subdir=out_subdir,
        api_key=api_key,
        severity_weights=severity_weights,
    )

    return {
        "doc_id": doc_id,
        "scenario": spec.scenario,
        "base_dir": str(base_path),
        "out_dir": str(base_path / out_subdir),
        "doc_result": doc_result.model_dump(),
        "output_paths": output_paths,
    }


def run_stage5_batch(
    *,
    base_root: str | Path,
    doc_ids: list[str] | None = None,
    model: str = "gpt-5-2025-08-07",
    trials: int = 3,
    out_dir: str | Path = "stage5_runs",
    api_key: str | None = None,
    scenario_specs_path: str | Path | None = None,
    demo_batch_path: str | Path | None = None,
    severity_weights_path: str | Path | None = None,
) -> dict[str, Any]:
    """Run Stage 5 for a batch of document IDs and write aggregate reports."""
    root = Path(base_root)
    if not root.is_dir():
        raise FileNotFoundError(f"base_root not found: {root}")

    specs = load_scenario_specs(scenario_specs_path)
    selected_doc_ids = doc_ids or load_demo_doc_ids(demo_batch_path)
    if not selected_doc_ids:
        raise ValueError("No doc IDs provided and demo batch is empty.")

    missing_specs = [doc_id for doc_id in selected_doc_ids if doc_id not in specs]
    if missing_specs:
        raise ValueError(
            "Missing scenario specs for doc IDs: "
            + ", ".join(sorted(missing_specs))
        )

    severity_weights = load_severity_weights(severity_weights_path)

    doc_results: list[DocEvaluationResult] = []
    per_doc_paths: dict[str, dict[str, str]] = {}

    for doc_id in selected_doc_ids:
        base_dir = root / doc_id
        spec = specs[doc_id]
        doc_result, output_paths = _run_doc_with_spec(
            base_dir=base_dir,
            spec=spec,
            adv_pdf=None,
            model=model,
            trials=trials,
            out_subdir="stage5_eval",
            api_key=api_key,
            severity_weights=severity_weights,
        )
        doc_results.append(doc_result)
        per_doc_paths[doc_id] = output_paths

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    batch_result: BatchEvaluationResult = aggregate_batch_results(
        run_id=run_id,
        doc_ids=selected_doc_ids,
        doc_results=doc_results,
    )

    timestamp_utc = datetime.now(timezone.utc).isoformat()
    run_config = {
        "run_id": run_id,
        "timestamp_utc": timestamp_utc,
        "base_root": str(root),
        "doc_ids": selected_doc_ids,
        "model": model,
        "trials": trials,
        "scenario_specs_path": str(Path(scenario_specs_path) if scenario_specs_path else DEFAULT_SCENARIO_SPECS_PATH),
        "severity_weights_path": str(Path(severity_weights_path) if severity_weights_path else DEFAULT_SEVERITY_WEIGHTS_PATH),
    }

    output_root = Path(out_dir)
    run_dir = output_root / run_id
    report_paths = write_batch_outputs(
        run_dir=run_dir,
        run_config=run_config,
        batch_result=batch_result,
    )

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "doc_ids": selected_doc_ids,
        "batch_result": batch_result.model_dump(),
        "report_paths": report_paths,
        "per_doc_paths": per_doc_paths,
    }
