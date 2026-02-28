"""Stage 4: full-page image overlay (original on perturbed) for dual-layer effect."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

log = logging.getLogger(__name__)


def apply_overlay(
    base_dir: Path,
    original_pdf_path: Path,
    compiled_pdf_path: Path,
    output_pdf_path: Path,
    mappings: list[dict[str, Any]],
) -> bool:
    """
    Apply full-page image overlay: render each page of original PDF and overlay on compiled (perturbed) PDF.
    Result: human sees original; parser sees perturbed content.

    Args:
        base_dir: Base output directory (for logging).
        original_pdf_path: Original (unperturbed) PDF - source for overlay images.
        compiled_pdf_path: Perturbed PDF - target to overlay onto.
        output_pdf_path: Where to write the final PDF.
        mappings: List of dicts with 'original', 'replacement' (used for logging; overlay is full-page).

    Returns:
        True if successful, False otherwise.
    """
    log.info("Stage 4 overlay: base_dir=%s, original=%s, compiled=%s, output=%s", base_dir, original_pdf_path, compiled_pdf_path, output_pdf_path)
    log.debug("Mappings count: %s", len(mappings))

    if not FITZ_AVAILABLE:
        log.error("PyMuPDF (fitz) not available; overlay skipped")
        return False

    if not compiled_pdf_path.exists():
        log.error("Compiled PDF not found: %s", compiled_pdf_path)
        return False

    try:
        compiled_doc = fitz.open(str(compiled_pdf_path))
        log.info("Compiled PDF opened: %s pages", len(compiled_doc))
    except Exception as e:
        log.exception("Failed to open compiled PDF: %s", e)
        return False

    if not original_pdf_path.exists():
        log.warning("Original PDF not found: %s; saving compiled without overlay", original_pdf_path)
        output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        compiled_doc.save(str(output_pdf_path))
        compiled_doc.close()
        return True

    try:
        original_doc = fitz.open(str(original_pdf_path))
        log.info("Original PDF opened: %s pages", len(original_doc))
    except Exception as e:
        log.exception("Failed to open original PDF: %s", e)
        compiled_doc.close()
        return False

    overlays_applied = 0
    try:
        for page_index in range(len(compiled_doc)):
            page = compiled_doc[page_index]
            original_page = original_doc[page_index] if page_index < len(original_doc) else None
            if not original_page:
                log.warning("Page %s: no corresponding page in original PDF", page_index + 1)
                continue
            try:
                log.debug("Page %s: extracting pixmap and overlaying", page_index + 1)
                pix = original_page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                page.insert_image(
                    page.rect,
                    stream=pix.tobytes("png"),
                    keep_proportion=True,
                    overlay=True,
                )
                overlays_applied += 1
            except Exception as e:
                log.error("Page %s: overlay failed: %s", page_index + 1, e, exc_info=True)
        log.info("Overlays applied: %s/%s pages", overlays_applied, len(compiled_doc))
        output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
        compiled_doc.save(str(output_pdf_path))
        log.info("Stage 4 overlay completed: %s", output_pdf_path)
        return True
    except Exception as e:
        log.exception("Overlay process failed: %s", e)
        return False
    finally:
        compiled_doc.close()
        original_doc.close()
