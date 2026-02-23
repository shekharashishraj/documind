"""CLI: run Step 1 PDF parsing and optional Stage 2 / Stage 3 GPT analysis."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import typer
from dotenv import load_dotenv

from core.stage2.openai_analyzer import run_stage2_openai
from core.stage3.openai_planner import run_stage3_openai
from core.stage4.visible_executor import annotate_pdf
from pipeline.graph import run_parse_pdf

# Load .env from project root (directory containing .env) so MISTRAL_API_KEY etc. are set
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

app = typer.Typer(add_completion=False)


def _generate_hash_for_file(filepath: str) -> str:
    """Generate MD5 hash of file for folder naming."""
    with open(filepath, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


@app.command()
def run(
    pdf: str = typer.Argument(..., help="Path to PDF file"),
    out: str = typer.Option(".", "--out", "-o", help="Output base directory (default: cwd)"),
    byte_only: bool = typer.Option(False, "--byte-only", help="Run only byte_extraction (pymupdf)"),
    ocr_only: bool = typer.Option(False, "--ocr-only", help="Run only OCR (tesseract + docling)"),
    vlm_only: bool = typer.Option(False, "--vlm-only", help="Run only VLM (mistral)"),
    stage2: bool = typer.Option(False, "--stage2", help="After Step 1, run Stage 2 GPT analysis (requires byte_extraction)"),
    stage3: bool = typer.Option(False, "--stage3", help="After Step 1 (and Stage 2 if needed), run Stage 3 manipulation planning. Implies --stage2."),
    stage4: bool = typer.Option(False, "--stage4", help="After Stage 3, run Stage 4 visible executor to annotate PDF with red markers. Implies --stage2 and --stage3."),
) -> None:
    """Run Step 1: parse PDF (byte_extraction, OCR, VLM). Optionally add --stage2, --stage3, and --stage4 for GPT analysis, manipulation planning, and visible PDF annotation."""
    pdf_path = Path(pdf)
    if not pdf_path.is_file():
        typer.echo(f"Not a file: {pdf_path}", err=True)
        raise typer.Exit(1)

    # Generate hash-based folder name from PDF content
    pdf_hash = _generate_hash_for_file(str(pdf_path.resolve()))
    pdfname = pdf_path.stem
    base_dir = Path(out) / pdf_hash

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
        stage2 = True  # Stage 3 requires Stage 2
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
        try:
            plan_path = base_dir / "stage3" / "openai" / "manipulation_plan.json"
            if not plan_path.is_file():
                typer.echo(f"Stage 3 plan not found: {plan_path}", err=True)
                raise typer.Exit(1)
            input_pdf = pdf_path.resolve()
            output_pdf = base_dir / "stage4" / f"{pdfname}_annotated.pdf"
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            annotate_pdf(str(input_pdf), str(plan_path), str(output_pdf))
            typer.echo(f"Stage 4: {output_pdf}")
        except Exception as e:
            typer.echo(f"Stage 4 failed: {e}", err=True)
            raise typer.Exit(1)


@app.command()
def stage2(
    base_dir: str = typer.Argument(..., help="Path to Step 1 output dir (contains byte_extraction/pymupdf)"),
    model: str = typer.Option("gpt-4o", "--model", "-m", help="OpenAI chat model (e.g. gpt-4o, gpt-4o-mini)"),
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
    model: str = typer.Option("gpt-4o", "--model", "-m", help="OpenAI chat model (e.g. gpt-4o)"),
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
    pdf: str = typer.Argument(..., help="Path to source PDF file"),
    base_dir: str = typer.Argument(..., help="Path to output dir (must contain stage3/openai/manipulation_plan.json)"),
) -> None:
    """Run Stage 4: Visible PDF executor. Annotates a copy of the PDF with visible red markers at planned injection targets.
    Writes stage4/{pdf_name}_annotated.pdf. Requires Stage 3 manipulation_plan.json.
    """
    pdf_path = Path(pdf)
    if not pdf_path.is_file():
        typer.echo(f"Not a file: {pdf_path}", err=True)
        raise typer.Exit(1)
    base_path = Path(base_dir)
    if not base_path.is_dir():
        typer.echo(f"Not a directory: {base_path}", err=True)
        raise typer.Exit(1)
    plan_path = base_path / "stage3" / "openai" / "manipulation_plan.json"
    if not plan_path.is_file():
        typer.echo(f"Stage 3 plan not found: {plan_path}", err=True)
        raise typer.Exit(1)
    try:
        pdfname = pdf_path.stem
        output_pdf = base_path / "stage4" / f"{pdfname}_annotated.pdf"
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        annotate_pdf(str(pdf_path.resolve()), str(plan_path), str(output_pdf))
        typer.echo(f"Wrote: {output_pdf}")
    except Exception as e:
        typer.echo(f"Stage 4 failed: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
