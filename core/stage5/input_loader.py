"""Input loading for Stage 5: clean text + attacked text parsed from Stage 4 adversarial PDF."""

from __future__ import annotations

from pathlib import Path

from core.extract.pymupdf_extractor import PyMuPDFExtractor


def load_clean_text(base_dir: Path) -> tuple[str, str]:
    """Load clean baseline text from byte_extraction/pymupdf/full_text.txt."""
    clean_path = base_dir / "byte_extraction" / "pymupdf" / "full_text.txt"
    if not clean_path.is_file():
        raise FileNotFoundError(f"Clean text not found: {clean_path}")
    return clean_path.read_text(encoding="utf-8"), str(clean_path)


def parse_attacked_pdf(attacked_pdf_path: Path, stage5_out_dir: Path) -> tuple[str, str]:
    """Parse attacked PDF using PyMuPDF byte extraction and return extracted text + source path."""
    if not attacked_pdf_path.is_file():
        raise FileNotFoundError(f"Attacked PDF not found: {attacked_pdf_path}")

    parse_dir = stage5_out_dir / "attacked_parse" / "pymupdf"
    extractor = PyMuPDFExtractor()
    extractor.extract(str(attacked_pdf_path), parse_dir)

    attacked_text_path = parse_dir / "full_text.txt"
    if not attacked_text_path.is_file():
        raise FileNotFoundError(f"Attacked parsed text not found: {attacked_text_path}")
    return attacked_text_path.read_text(encoding="utf-8"), str(attacked_text_path)


def resolve_attacked_pdf(base_dir: Path, adv_pdf: str | None = None) -> Path:
    """Resolve attacked PDF path, defaulting to Stage 4 final_overlay.pdf."""
    if adv_pdf:
        resolved = Path(adv_pdf)
    else:
        resolved = base_dir / "stage4" / "final_overlay.pdf"
    return resolved
