"""CLI: run Step 1 PDF parsing and optional Stage 2 GPT analysis."""

from __future__ import annotations

import os
from pathlib import Path

import typer
from dotenv import load_dotenv

from core.stage2.openai_analyzer import run_stage2_openai
from pipeline.graph import run_parse_pdf

# Load .env from project root (directory containing .env) so MISTRAL_API_KEY etc. are set
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")

app = typer.Typer(add_completion=False)


@app.command()
def run(
    pdf: str = typer.Argument(..., help="Path to PDF file"),
    out: str = typer.Option(".", "--out", "-o", help="Output base directory (default: cwd)"),
    byte_only: bool = typer.Option(False, "--byte-only", help="Run only byte_extraction (pymupdf)"),
    ocr_only: bool = typer.Option(False, "--ocr-only", help="Run only OCR (tesseract + docling)"),
    vlm_only: bool = typer.Option(False, "--vlm-only", help="Run only VLM (mistral)"),
    stage2: bool = typer.Option(False, "--stage2", help="After Step 1, run Stage 2 GPT analysis (requires byte_extraction)"),
) -> None:
    """Run Step 1: parse PDF with byte_extraction, OCR, and VLM. Output under <pdfname>/run_type/sub_mechanism/."""
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

    if stage2 and "byte_extraction" not in run_types:
        run_types.append("byte_extraction")

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


if __name__ == "__main__":
    app()
