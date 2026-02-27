"""CLI: run Step 1 PDF parsing and optional Stage 2 / Stage 3 GPT analysis."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import typer
from dotenv import load_dotenv

from core.stage5 import run_stage5_batch, run_stage5_doc
from core.stage2.openai_analyzer import run_stage2_openai
from core.stage3.openai_planner import run_stage3_openai
from core.stage4 import run_stage4
from pipeline.graph import run_parse_pdf

# Load .env from project root (directory containing .env) so MISTRAL_API_KEY etc. are set
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

app = typer.Typer(add_completion=False)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    env_level = os.environ.get("LOG_LEVEL", "").upper()
    if env_level == "DEBUG":
        level = logging.DEBUG
    elif env_level == "WARNING":
        level = logging.WARNING
    elif env_level == "ERROR":
        level = logging.ERROR
    logging.basicConfig(level=level, format="%(levelname)s:%(name)s:%(message)s")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable DEBUG logging"),
) -> None:
    """MalDoc pipeline: PDF parsing, analysis, and manipulation planning."""
    _configure_logging(verbose)


def _scenario_label(scenario: str) -> str:
    labels = {
        "decision": "Decision-making agent",
        "scheduling": "Scheduling agent",
        "db": "Database storage/retrieval agent",
        "credential": "Credential verification / HR screening agent",
        "survey": "Survey/link routing & consent agent",
    }
    return labels.get(scenario, scenario or "Unknown scenario")


def _format_value(value: object) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        if not value:
            return "none"
        return ", ".join(str(v) for v in value)
    if isinstance(value, dict):
        if not value:
            return "none"
        return "; ".join(f"{k}={_format_value(v)}" for k, v in list(value.items())[:6])
    text = str(value).strip()
    return text if text else "none"


def _format_mapping(mapping: dict | None, max_items: int = 5) -> str:
    if not mapping:
        return "none"
    pairs = []
    for key, value in list(mapping.items())[:max_items]:
        pairs.append(f"{key}={_format_value(value)}")
    return ", ".join(pairs)


def _print_stage5_human_story(doc_result: dict) -> None:
    scenario = str(doc_result.get("scenario", ""))
    clean_majority = doc_result.get("clean_majority") or {}
    attacked_majority = doc_result.get("attacked_majority") or {}

    clean_tool = (clean_majority.get("tool_call") or {}).get("name", "unknown_tool")
    attacked_tool = (attacked_majority.get("tool_call") or {}).get("name", "unknown_tool")
    clean_args = (clean_majority.get("tool_call") or {}).get("arguments") or {}
    attacked_args = (attacked_majority.get("tool_call") or {}).get("arguments") or {}
    clean_outcome = clean_majority.get("final_outcome") or {}
    attacked_outcome = attacked_majority.get("final_outcome") or {}

    typer.echo("")
    typer.echo("Human-readable behavior summary:")
    typer.echo(f"  Scenario: {_scenario_label(scenario)}")

    if doc_result.get("clean_majority_matches_gold"):
        typer.echo("  Baseline check: On the original document, the agent behavior matched the expected ground truth.")
    else:
        typer.echo("  Baseline check: On the original document, the behavior did not match ground truth. This case is excluded from ASR denominator.")

    typer.echo(
        "  Original document behavior: "
        f"Agent called '{clean_tool}' with {_format_mapping(clean_args)}. "
        f"Outcome: {_format_mapping(clean_outcome)}."
    )
    typer.echo(
        "  Adversarial document behavior: "
        f"Agent called '{attacked_tool}' with {_format_mapping(attacked_args)}. "
        f"Outcome: {_format_mapping(attacked_outcome)}."
    )

    diffs = doc_result.get("targeted_field_diffs") or {}
    changed_rows = []
    for field, payload in diffs.items():
        if not isinstance(payload, dict) or not payload.get("changed"):
            continue
        changed_rows.append(
            f"{field}: '{_format_value(payload.get('clean'))}' -> '{_format_value(payload.get('attacked'))}'"
        )

    if changed_rows:
        typer.echo("  What changed in attacker-targeted fields:")
        for row in changed_rows[:6]:
            typer.echo(f"    - {row}")
    else:
        typer.echo("  What changed in attacker-targeted fields: none")

    if doc_result.get("clean_majority_matches_gold"):
        if doc_result.get("attack_success"):
            typer.echo("  Verdict: The agent is COMPROMISED for this document (successful attack).")
        else:
            typer.echo("  Verdict: No successful compromise for this document under current success rule.")
    else:
        typer.echo("  Verdict: Baseline mismatch, so compromise is not counted in vulnerability-rate denominator.")

    flags = []
    if doc_result.get("decision_flip"):
        flags.append("decision flipped")
    if doc_result.get("tool_parameter_corruption"):
        flags.append("tool parameters corrupted")
    if doc_result.get("wrong_entity_binding"):
        flags.append("wrong entity binding")
    if doc_result.get("unsafe_routing"):
        flags.append("unsafe URL routing")
    if doc_result.get("persistence_poisoning"):
        flags.append("persistence poisoning")
    if flags:
        typer.echo(f"  Impact signals: {', '.join(flags)}.")


def _print_stage5_batch_story(batch: dict) -> None:
    asr = float(batch.get("attack_success_rate") or 0.0)
    decision_flip = float(batch.get("decision_flip_rate") or 0.0)
    param_corr = float(batch.get("tool_parameter_corruption_rate") or 0.0)
    weighted = float(batch.get("severity_weighted_vulnerability_score") or 0.0)
    typer.echo("")
    typer.echo("Human-readable batch summary:")
    typer.echo(
        "  Across the selected document set, "
        f"{batch.get('successful_attacks', 0)} successful compromises were observed out of "
        f"{batch.get('eligible_docs', 0)} eligible documents."
    )
    typer.echo(
        "  Aggregate vulnerability rates: "
        f"ASR={asr:.4f}, "
        f"decision_flip={decision_flip:.4f}, "
        f"parameter_corruption={param_corr:.4f}, "
        f"severity_weighted={weighted:.4f}."
    )

    doc_rows = batch.get("doc_results") or []
    if doc_rows:
        typer.echo("  Per-document outcomes:")
        for row in doc_rows:
            if not isinstance(row, dict):
                continue
            doc_id = row.get("doc_id")
            scenario = _scenario_label(str(row.get("scenario", "")))
            if row.get("clean_majority_matches_gold"):
                status = "COMPROMISED" if row.get("attack_success") else "NOT COMPROMISED"
            else:
                status = "BASELINE MISMATCH"
            changed = int(row.get("targeted_field_changed_count", 0) or 0)
            typer.echo(f"    - {doc_id} ({scenario}): {status} | changed_target_fields={changed}")


@app.command()
def run(
    pdf: str = typer.Argument(..., help="Path to PDF file"),
    out: str = typer.Option("pipeline_run", "--out", "-o", help="Output base directory (default: pipeline_run)"),
    byte_only: bool = typer.Option(False, "--byte-only", help="Run only byte_extraction (pymupdf)"),
    ocr_only: bool = typer.Option(False, "--ocr-only", help="Run only OCR (tesseract + docling)"),
    vlm_only: bool = typer.Option(False, "--vlm-only", help="Run only VLM (mistral)"),
    stage2: bool = typer.Option(False, "--stage2", help="After Step 1, run Stage 2 GPT analysis (requires byte_extraction)"),
    stage3: bool = typer.Option(False, "--stage3", help="After Step 1 (and Stage 2 if needed), run Stage 3 manipulation planning. Implies --stage2."),
    stage4: bool = typer.Option(False, "--stage4", help="After Stage 3, run Stage 4 injection and image overlay. Implies --stage2, --stage3."),
    priority_filter: str | None = typer.Option(None, "--priority-filter", help="Stage 4 only: apply attacks at this priority or higher (high | medium | low). Default: all."),
) -> None:
    """Run Step 1: parse PDF (byte_extraction, OCR, VLM). Optionally add --stage2, --stage3, --stage4."""
    pdf_path = Path(pdf)
    if not pdf_path.is_file():
        typer.echo(f"Not a file: {pdf_path}", err=True)
        raise typer.Exit(1)

    pdfname = pdf_path.stem
    base_dir = Path(out) / pdfname

    if byte_only and ocr_only and vlm_only:
        run_types = ["byte_extraction", "ocr", "vlm"]
    elif byte_only and ocr_only:
        run_types = ["byte_extraction", "ocr"]
    elif byte_only and vlm_only:
        run_types = ["byte_extraction", "vlm"]
    elif ocr_only and vlm_only:
        run_types = ["ocr", "vlm"]
    elif byte_only:
        run_types = ["byte_extraction"]
    elif ocr_only:
        run_types = ["ocr"]
    elif vlm_only:
        run_types = ["vlm"]
    else:
        run_types = ["byte_extraction", "ocr", "vlm"]

    if (stage2 or stage3 or stage4) and "byte_extraction" not in run_types:
        run_types.append("byte_extraction")
    if stage3 or stage4:
        stage2 = True  # Stage 3 and Stage 4 require Stage 2
    if stage4:
        stage3 = True  # Stage 4 requires Stage 3

    typer.echo(f"Output base: {base_dir}")
    typer.echo(f"Run types: {run_types}")
    final = run_parse_pdf(str(pdf_path.resolve()), base_dir, run_types=run_types)
    typer.echo("Done. Results:")
    for key, summary in (final.get("results") or {}).items():
        typer.echo(f"  {key}: {summary.get('num_pages', 0)} pages, artifacts: {summary.get('artifacts', [])}")
        if summary.get("extra", {}).get("error"):
            typer.echo(f"    error: {summary['extra']['error']}", err=True)

    if stage2:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            typer.echo("OPENAI_API_KEY not set; skipping Stage 2.", err=True)
            raise typer.Exit(1)
        try:
            result = run_stage2_openai(base_dir, api_key=api_key)
            typer.echo(f"Stage 2: {result['output_path']}")
            if result.get("usage"):
                typer.echo(f"  usage: {result['usage']}")
        except Exception as e:
            typer.echo(f"Stage 2 failed: {e}", err=True)
            raise typer.Exit(1)
    if stage3:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            typer.echo("OPENAI_API_KEY not set; skipping Stage 3.", err=True)
            raise typer.Exit(1)
        try:
            result = run_stage3_openai(base_dir, api_key=api_key)
            typer.echo(f"Stage 3: {result['output_path']} ({result.get('total_attacks', 0)} attacks)")
            if result.get("usage"):
                typer.echo(f"  usage: {result['usage']}")
        except Exception as e:
            typer.echo(f"Stage 3 failed: {e}", err=True)
            raise typer.Exit(1)
    if stage4:
        original_copy = base_dir / "original.pdf"
        try:
            shutil.copy2(pdf_path, original_copy)
            typer.echo(f"Copied original PDF to {original_copy}")
        except Exception as e:
            typer.echo(f"Failed to copy original PDF: {e}", err=True)
            raise typer.Exit(1)
        try:
            result = run_stage4(
                base_dir,
                original_pdf_path=original_copy,
                apply_overlay_flag=True,
                priority_filter=priority_filter,
            )
            if result.get("error"):
                typer.echo(f"Stage 4: {result['error']}", err=True)
                raise typer.Exit(1)
            typer.echo(f"Stage 4: {result.get('perturbed_pdf_path', 'N/A')}")
            if result.get("final_pdf_path"):
                typer.echo(f"  Final overlay: {result['final_pdf_path']}")
            stats = result.get("replacement_stats") or {}
            if stats:
                total = sum(stats.values())
                typer.echo(f"  Replacements applied: {len(stats)} keys, {total} total hits")
        except Exception as e:
            typer.echo(f"Stage 4 failed: {e}", err=True)
            raise typer.Exit(1)


@app.command()
def stage2(
    base_dir: str = typer.Argument(..., help="Path to Step 1 output dir (contains byte_extraction/pymupdf)"),
    model: str = typer.Option("gpt-5-2025-08-07", "--model", "-m", help="OpenAI chat model (e.g. gpt-5-2025-08-07, gpt-4o)"),
) -> None:
    """Run Stage 2: GPT analysis of Step 1 outputs (summary, domain, task classification). Writes stage2/openai/analysis.json."""
    base_path = Path(base_dir)
    if not base_path.is_dir():
        typer.echo(f"Not a directory: {base_path}", err=True)
        raise typer.Exit(1)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        typer.echo("OPENAI_API_KEY not set. Set it in .env or the environment.", err=True)
        raise typer.Exit(1)
    try:
        result = run_stage2_openai(base_path, model=model, api_key=api_key)
        typer.echo(f"Wrote: {result['output_path']}")
        if result.get("usage"):
            typer.echo(f"Usage: {result['usage']}")
    except FileNotFoundError as e:
        typer.echo(f"Stage 2 failed: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Stage 2 failed: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def stage3(
    base_dir: str = typer.Argument(..., help="Path to output dir (must contain stage2/openai/analysis.json)"),
    model: str = typer.Option("gpt-5-2025-08-07", "--model", "-m", help="OpenAI chat model (e.g. gpt-5-2025-08-07, gpt-4o)"),
) -> None:
    """Run Stage 3: GPT manipulation planning (what/where/risk/effects). Writes stage3/openai/manipulation_plan.json. Requires Stage 2 and Step 1 byte_extraction."""
    base_path = Path(base_dir)
    if not base_path.is_dir():
        typer.echo(f"Not a directory: {base_path}", err=True)
        raise typer.Exit(1)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        typer.echo("OPENAI_API_KEY not set. Set it in .env or the environment.", err=True)
        raise typer.Exit(1)
    try:
        result = run_stage3_openai(base_path, model=model, api_key=api_key)
        typer.echo(f"Wrote: {result['output_path']} ({result.get('total_attacks', 0)} attacks)")
        if result.get("usage"):
            typer.echo(f"Usage: {result['usage']}")
    except FileNotFoundError as e:
        typer.echo(f"Stage 3 failed: {e}", err=True)
        raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Stage 3 failed: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def stage4(
    base_dir: str = typer.Argument(..., help="Path to output dir (must contain stage2, stage3, byte_extraction)"),
    original_pdf: str | None = typer.Option(None, "--original-pdf", help="Path to original PDF for injection and overlay (default: base_dir/original.pdf)"),
    no_overlay: bool = typer.Option(False, "--no-overlay", help="Skip image overlay; only run injection"),
    priority_filter: str | None = typer.Option(None, "--priority-filter", help="Only apply attacks at this priority or higher: high | medium | low. Default: all."),
) -> None:
    """Run Stage 4: direct PDF injection then full-page image overlay. Writes stage4/perturbed.pdf, stage4/replacements.json, and optionally stage4/final_overlay.pdf."""
    base_path = Path(base_dir)
    if not base_path.is_dir():
        typer.echo(f"Not a directory: {base_path}", err=True)
        raise typer.Exit(1)
    orig = Path(original_pdf) if original_pdf else base_path / "original.pdf"
    if not orig.is_file():
        typer.echo(f"Original PDF not found: {orig}. Pass --original-pdf or run 'run --stage4' to copy it.", err=True)
        raise typer.Exit(1)
    try:
        result = run_stage4(
            base_path,
            original_pdf_path=orig,
            apply_overlay_flag=not no_overlay,
            priority_filter=priority_filter,
        )
        if result.get("error"):
            typer.echo(f"Stage 4: {result['error']}", err=True)
            raise typer.Exit(1)
        typer.echo(f"Perturbed: {result.get('perturbed_pdf_path', 'N/A')}")
        if result.get("final_pdf_path"):
            typer.echo(f"Final: {result['final_pdf_path']}")
        stats = result.get("replacement_stats") or {}
        if stats:
            total = sum(stats.values())
            typer.echo(f"Replacements applied: {len(stats)} keys, {total} total hits")
    except Exception as e:
        typer.echo(f"Stage 4 failed: {e}", err=True)
        raise typer.Exit(1)


@app.command()
def stage5(
    base_dir: str = typer.Argument(..., help="Path to document output dir (must contain byte_extraction and stage4/final_overlay.pdf)"),
    scenario: str = typer.Option("auto", "--scenario", help="Scenario override: auto | decision | scheduling | db | credential | survey."),
    adv_pdf: str | None = typer.Option(None, "--adv-pdf", help="Path to adversarial PDF (default: base_dir/stage4/final_overlay.pdf)"),
    model: str = typer.Option("gpt-5-2025-08-07", "--model", "-m", help="OpenAI chat model."),
    trials: int = typer.Option(3, "--trials", min=1, help="Number of clean and attacked trials."),
    out_subdir: str = typer.Option("stage5_eval", "--out-subdir", help="Per-doc output subdir under base_dir."),
) -> None:
    """Run Stage 5 for one document: clean vs attacked agent simulation with vulnerability scoring."""
    base_path = Path(base_dir)
    if not base_path.is_dir():
        typer.echo(f"Not a directory: {base_path}", err=True)
        raise typer.Exit(1)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        typer.echo("OPENAI_API_KEY not set. Set it in .env or the environment.", err=True)
        raise typer.Exit(1)
    try:
        result = run_stage5_doc(
            base_path,
            scenario=scenario,
            adv_pdf=adv_pdf,
            model=model,
            trials=trials,
            out_subdir=out_subdir,
            api_key=api_key,
        )
        doc_result = result.get("doc_result") or {}
        typer.echo(f"Stage 5 doc: {result.get('doc_id')} ({result.get('scenario')})")
        typer.echo(f"  out_dir: {result.get('out_dir')}")
        typer.echo(f"  clean_majority_matches_gold: {doc_result.get('clean_majority_matches_gold')}")
        typer.echo(f"  attack_success: {doc_result.get('attack_success')}")
        typer.echo(f"  targeted_field_changed_count: {doc_result.get('targeted_field_changed_count')}")
        _print_stage5_human_story(doc_result)
        output_paths = result.get("output_paths") or {}
        if output_paths:
            typer.echo("  Saved artifacts:")
            typer.echo(f"    clean trials: {output_paths.get('clean_trials')}")
            typer.echo(f"    attacked trials: {output_paths.get('attacked_trials')}")
            typer.echo(f"    doc result: {output_paths.get('doc_result')}")
            typer.echo(f"    doc metrics: {output_paths.get('doc_metrics')}")
    except Exception as e:
        typer.echo(f"Stage 5 failed: {e}", err=True)
        raise typer.Exit(1)


@app.command(name="stage5_batch")
def stage5_batch(
    base_root: str = typer.Option("pipeline_run", "--base-root", help="Root directory containing document folders (doc_id as folder name)."),
    doc_id: list[str] = typer.Option([], "--doc-id", help="Document ID to include. Repeat for multiple docs. If omitted, demo batch is used."),
    model: str = typer.Option("gpt-5-2025-08-07", "--model", "-m", help="OpenAI chat model."),
    trials: int = typer.Option(3, "--trials", min=1, help="Number of clean and attacked trials per document."),
    out_dir: str = typer.Option("stage5_runs", "--out-dir", help="Output dir for batch reports."),
) -> None:
    """Run Stage 5 batch evaluation and write aggregate vulnerability reports."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        typer.echo("OPENAI_API_KEY not set. Set it in .env or the environment.", err=True)
        raise typer.Exit(1)
    try:
        result = run_stage5_batch(
            base_root=base_root,
            doc_ids=doc_id or None,
            model=model,
            trials=trials,
            out_dir=out_dir,
            api_key=api_key,
        )
        batch = result.get("batch_result") or {}
        typer.echo(f"Stage 5 batch run: {result.get('run_id')}")
        typer.echo(f"  run_dir: {result.get('run_dir')}")
        typer.echo(f"  docs: {len(result.get('doc_ids') or [])}")
        typer.echo(f"  eligible_docs: {batch.get('eligible_docs')}")
        typer.echo(f"  attack_success_rate: {batch.get('attack_success_rate')}")
        typer.echo(f"  severity_weighted_vulnerability_score: {batch.get('severity_weighted_vulnerability_score')}")
        _print_stage5_batch_story(batch)
        report_paths = result.get("report_paths") or {}
        if report_paths:
            typer.echo("  Saved batch reports:")
            typer.echo(f"    run config: {report_paths.get('run_config')}")
            typer.echo(f"    doc results CSV: {report_paths.get('doc_results_csv')}")
            typer.echo(f"    scenario metrics CSV: {report_paths.get('scenario_metrics_csv')}")
            typer.echo(f"    overall metrics: {report_paths.get('overall_metrics')}")
            typer.echo(f"    paper table: {report_paths.get('paper_table')}")
    except Exception as e:
        typer.echo(f"Stage 5 batch failed: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
