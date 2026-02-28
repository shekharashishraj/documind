"""Stage 4a: execute minimal edit plan and generate per-strategy PDFs."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

log = logging.getLogger(__name__)


def _load_source_metadata(base_dir: Path) -> dict[str, Any]:
    """Load source_metadata.json to find original PDF path."""
    metadata_path = base_dir / "source_metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"source_metadata.json not found at {metadata_path}. "
            "Run Step 1 extraction first or use --pdf to specify PDF path."
        )
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _load_edit_plan(base_dir: Path, edit_plan_path: str | Path | None) -> dict[str, Any]:
    """Load Stage 4a edit plan."""
    if edit_plan_path:
        path = Path(edit_plan_path)
    else:
        path = base_dir / "stage4a" / "openai" / "edit_plan.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"Stage 4a edit plan not found: {path}. Run stage4a first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_pages_json(base_dir: Path) -> list[dict[str, Any]]:
    """Load pages.json for document structure reference."""
    pages_path = base_dir / "byte_extraction" / "pymupdf" / "pages.json"
    if not pages_path.is_file():
        log.warning("pages.json not found at %s", pages_path)
        return []
    return json.loads(pages_path.read_text(encoding="utf-8"))


def _safe_name(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw or "").strip("_")
    return cleaned or "variant"


def _find_page_entry(pages_json: list[dict[str, Any]], page_num: int) -> dict[str, Any] | None:
    for p in pages_json:
        if p.get("page") == page_num:
            return p
    if 0 <= page_num < len(pages_json):
        return pages_json[page_num]
    return None


def _resolve_target_rect(
    doc: fitz.Document,
    pages_json: list[dict[str, Any]],
    target: dict[str, Any],
) -> tuple[int, fitz.Rect | None, str | None]:
    """
    Resolve a target rectangle for text edits.

    Returns (page_num, rect, resolution_notes).
    """
    page_num = int(target.get("page", 0) or 0)
    notes = None

    bbox = target.get("bbox")
    if bbox and len(bbox) == 4:
        try:
            rect = fitz.Rect(bbox)
            return page_num, rect, notes
        except Exception:
            notes = "invalid_bbox"

    block_index = target.get("block_index")
    if block_index is not None:
        page_entry = _find_page_entry(pages_json, page_num)
        if page_entry:
            blocks = page_entry.get("blocks") or []
            if 0 <= int(block_index) < len(blocks):
                b = blocks[int(block_index)]
                bb = b.get("bbox")
                if bb and len(bb) == 4:
                    return page_num, fitz.Rect(bb), notes or "bbox_from_block_index"

    search_text = (
        target.get("original_text")
        or target.get("text_preview")
        or target.get("content_preview")
    )
    if search_text and page_num < len(doc):
        page = doc[page_num]
        query = search_text.strip()
        if len(query) > 80:
            query = query[:80]
        if query:
            rects = page.search_for(query)
            if rects:
                return page_num, rects[0], notes or "bbox_from_search"

    return page_num, None, notes or "no_bbox"


def _region_rect(region: str | None) -> fitz.Rect:
    region_rects = {
        "header": fitz.Rect(72, 30, 300, 70),
        "footer": fitz.Rect(72, 740, 300, 770),
        "margin": fitz.Rect(20, 400, 160, 430),
        "between_blocks": fitz.Rect(200, 400, 400, 430),
        "body": fitz.Rect(72, 200, 400, 240),
    }
    return region_rects.get(region or "body", fitz.Rect(72, 200, 400, 240))


def _apply_replace_text(
    doc: fitz.Document,
    pages_json: list[dict[str, Any]],
    edit: dict[str, Any],
) -> dict[str, Any]:
    target = edit.get("target") or {}
    replacement_text = edit.get("replacement_text") or "PLACEHOLDER"

    page_num, rect, notes = _resolve_target_rect(doc, pages_json, target)
    if page_num >= len(doc):
        return {
            "edit_id": edit.get("edit_id", "unknown"),
            "edit_type": "replace_text",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }
    if rect is None:
        return {
            "edit_id": edit.get("edit_id", "unknown"),
            "edit_type": "replace_text",
            "status": "failed",
            "error": "No target bbox found",
            "notes": notes,
        }

    page = doc[page_num]
    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

    fontsize = max(6, min(24, rect.height * 0.8))
    fit_result = page.insert_textbox(
        rect,
        replacement_text,
        fontsize=fontsize,
        fontname="helv",
        color=(0, 0, 0),
        align=fitz.TEXT_ALIGN_LEFT,
    )

    status = "success" if fit_result >= 0 else "warning"
    return {
        "edit_id": edit.get("edit_id", "unknown"),
        "edit_type": "replace_text",
        "status": status,
        "page": page_num,
        "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
        "notes": notes,
        "details": f"Inserted {len(replacement_text)} chars (fit_result={fit_result})",
    }


def _apply_insert_text(
    doc: fitz.Document,
    pages_json: list[dict[str, Any]],
    edit: dict[str, Any],
) -> dict[str, Any]:
    target = edit.get("target") or {}
    text = edit.get("replacement_text") or "PLACEHOLDER"
    page_num = int(target.get("page", 0) or 0)

    if page_num >= len(doc):
        return {
            "edit_id": edit.get("edit_id", "unknown"),
            "edit_type": "insert_text",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]
    bbox = target.get("bbox")
    if bbox and len(bbox) == 4:
        rect = fitz.Rect(bbox)
    else:
        rect = _region_rect(target.get("region"))

    fontsize = max(6, min(24, rect.height * 0.8))
    fit_result = page.insert_textbox(
        rect,
        text,
        fontsize=fontsize,
        fontname="helv",
        color=(0, 0, 0),
        align=fitz.TEXT_ALIGN_LEFT,
    )

    status = "success" if fit_result >= 0 else "warning"
    return {
        "edit_id": edit.get("edit_id", "unknown"),
        "edit_type": "insert_text",
        "status": status,
        "page": page_num,
        "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
        "details": f"Inserted {len(text)} chars (fit_result={fit_result})",
    }


def _apply_redact_text(
    doc: fitz.Document,
    pages_json: list[dict[str, Any]],
    edit: dict[str, Any],
) -> dict[str, Any]:
    target = edit.get("target") or {}
    page_num, rect, notes = _resolve_target_rect(doc, pages_json, target)

    if page_num >= len(doc):
        return {
            "edit_id": edit.get("edit_id", "unknown"),
            "edit_type": "redact_text",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }
    if rect is None:
        return {
            "edit_id": edit.get("edit_id", "unknown"),
            "edit_type": "redact_text",
            "status": "failed",
            "error": "No target bbox found",
            "notes": notes,
        }

    page = doc[page_num]
    page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)

    return {
        "edit_id": edit.get("edit_id", "unknown"),
        "edit_type": "redact_text",
        "status": "success",
        "page": page_num,
        "rect": [rect.x0, rect.y0, rect.x1, rect.y1],
        "notes": notes,
        "details": "Redacted with white overlay",
    }


def _apply_replace_link(
    doc: fitz.Document,
    edit: dict[str, Any],
) -> dict[str, Any]:
    target = edit.get("target") or {}
    new_url = edit.get("new_url") or "https://www.123.com"
    page_num = int(target.get("page", 0) or 0)
    original_url = target.get("original_url")
    link_index = target.get("link_index")

    if page_num >= len(doc):
        return {
            "edit_id": edit.get("edit_id", "unknown"),
            "edit_type": "replace_link",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]
    links = page.get_links() or []
    if not links:
        return {
            "edit_id": edit.get("edit_id", "unknown"),
            "edit_type": "replace_link",
            "status": "failed",
            "error": f"No links found on page {page_num}",
        }

    target_link = None
    target_idx = None

    if link_index is not None and 0 <= int(link_index) < len(links):
        target_link = links[int(link_index)]
        target_idx = int(link_index)
    else:
        for idx, link in enumerate(links):
            link_uri = link.get("uri", "")
            if original_url and link_uri and original_url in link_uri:
                target_link = link
                target_idx = idx
                break
            if not original_url and link.get("kind") == fitz.LINK_URI:
                target_link = link
                target_idx = idx
                break

    if target_link is None:
        return {
            "edit_id": edit.get("edit_id", "unknown"),
            "edit_type": "replace_link",
            "status": "failed",
            "error": "No matching link found",
            "searched_for": original_url or "any URI link",
        }

    original_found = target_link.get("uri", "")
    target_link["uri"] = new_url
    page.update_link(target_link)

    return {
        "edit_id": edit.get("edit_id", "unknown"),
        "edit_type": "replace_link",
        "status": "success",
        "page": page_num,
        "link_index": target_idx,
        "original_url": original_found,
        "new_url": new_url,
        "details": f"Replaced link URI with {new_url}",
    }


def _apply_edit(
    doc: fitz.Document,
    pages_json: list[dict[str, Any]],
    edit: dict[str, Any],
) -> dict[str, Any]:
    edit_type = (edit.get("edit_type") or "").lower()

    if edit_type == "replace_text":
        return _apply_replace_text(doc, pages_json, edit)
    if edit_type == "insert_text":
        return _apply_insert_text(doc, pages_json, edit)
    if edit_type == "redact_text":
        return _apply_redact_text(doc, pages_json, edit)
    if edit_type == "replace_link":
        return _apply_replace_link(doc, edit)

    return {
        "edit_id": edit.get("edit_id", "unknown"),
        "edit_type": edit_type,
        "status": "failed",
        "error": f"Unknown edit_type: {edit_type}",
    }


def run_stage4a_executor(
    base_dir: str | Path,
    *,
    pdf_path: str | Path | None = None,
    edit_plan_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Execute Stage 4a: apply minimal edit plan and produce one PDF per variant.

    Reads:
    - stage4a/openai/edit_plan.json (or edit_plan_path override)
    - byte_extraction/pymupdf/pages.json
    - source_metadata.json (or pdf_path override)

    Writes:
    - stage4a/variants/<variant_id>.pdf
    - stage4a/execution_report.json
    """
    base_dir = Path(base_dir)

    edit_plan = _load_edit_plan(base_dir, edit_plan_path)
    pages_json = _load_pages_json(base_dir)

    if pdf_path is None:
        metadata = _load_source_metadata(base_dir)
        pdf_path = metadata.get("source_pdf")
        if not pdf_path:
            raise ValueError("No source_pdf in source_metadata.json and no --pdf provided")

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    variants = edit_plan.get("variants") or []
    out_dir = base_dir / "stage4a" / "variants"
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    total_applied = 0
    total_failed = 0
    total_warning = 0

    log.info("Stage 4a: applying %s variants to %s", len(variants), pdf_path)

    for idx, variant in enumerate(variants):
        variant_id = str(variant.get("variant_id") or f"V{idx + 1}")
        safe_variant_id = _safe_name(variant_id)
        edits = variant.get("edits") or []

        log.info("Stage 4a: variant %s with %s edits", variant_id, len(edits))
        doc = fitz.open(str(pdf_path))

        edit_results = []
        applied = 0
        failed = 0
        warning = 0

        for edit in edits:
            edit_id = edit.get("edit_id", "unknown")
            edit_type = edit.get("edit_type", "unknown")
            log.info("Stage 4a: variant %s applying edit %s (%s)", variant_id, edit_id, edit_type)
            try:
                result = _apply_edit(doc, pages_json, edit)
                edit_results.append(result)
                status = result.get("status")
                if status == "success":
                    applied += 1
                elif status == "warning":
                    warning += 1
                else:
                    failed += 1
                log.info(
                    "Stage 4a: variant %s edit %s status=%s",
                    variant_id,
                    edit_id,
                    status,
                )
            except Exception as e:
                log.error("Stage 4a: edit failed in %s: %s", variant_id, e)
                edit_results.append({
                    "edit_id": edit.get("edit_id", "unknown"),
                    "edit_type": edit.get("edit_type", "unknown"),
                    "status": "failed",
                    "error": str(e),
                })
                failed += 1

        output_pdf_path = out_dir / f"{safe_variant_id}.pdf"
        doc.save(str(output_pdf_path))
        doc.close()

        log.info("Stage 4a: saved %s", output_pdf_path)
        log.info(
            "Stage 4a: variant %s summary applied=%s failed=%s warning=%s",
            variant_id,
            applied,
            failed,
            warning,
        )

        total_applied += applied
        total_failed += failed
        total_warning += warning

        results.append({
            "variant_id": variant_id,
            "source_attack_id": variant.get("source_attack_id"),
            "output_pdf": str(output_pdf_path),
            "applied": applied,
            "failed": failed,
            "warning": warning,
            "edits": edit_results,
        })

    report = {
        "input_pdf": str(pdf_path),
        "edit_plan_path": str((Path(edit_plan_path) if edit_plan_path else (base_dir / "stage4a" / "openai" / "edit_plan.json")).resolve()),
        "timestamp": datetime.utcnow().isoformat(),
        "summary": {
            "variants": len(variants),
            "applied": total_applied,
            "failed": total_failed,
            "warning": total_warning,
        },
        "variants": results,
    }

    report_path = base_dir / "stage4a" / "execution_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Stage 4a: wrote execution report to %s", report_path)

    return {
        "report_path": str(report_path),
        "variants": results,
        "summary": report["summary"],
    }
