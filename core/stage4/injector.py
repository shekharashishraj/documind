"""Stage 4 injection: apply replacements to PDF (redact + insert + reading-order fix).

Reading-order problem with the naive redact + insert_text approach:
  - apply_redactions() removes original text, leaving a gap
  - insert_text() creates a NEW content stream appended to /Contents array
  - PDF text extraction reads content streams IN ORDER
  - So replacement text appears AFTER all original text (at the bottom)

Fix applied here:
  1. Redact to remove original text
  2. insert_text to place replacement at correct visual (x,y)
  3. clean_contents() to merge all streams into one
  4. _sort_content_stream_blocks() to reorder the q...Q blocks by Y position
  5. This restores correct top-to-bottom reading order

Additionally, Stage 1 byte extraction MUST use get_text("text", sort=True)
for robust text extraction that respects visual position over stream order.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

import fitz

from core.stage2.schemas import Stage2Analysis
from core.stage3.schemas import ManipulationPlan
from core.stage4.schemas import (
    HiddenTextItem,
    HiddenTextManifest,
    ReplacementItem,
    ReplacementsManifest,
)

log = logging.getLogger(__name__)

# Priority ordering for filtering/sorting attacks
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# Default page height (A4). Used for Y-coordinate conversion.
DEFAULT_PAGE_HEIGHT = 842.0

# Paper-aligned semantic strategy defaults.
SEMANTIC_EDIT_BY_INJECTION_STRATEGY = {
    "addition": "append",
    "modification": "update",
    "redaction": "delete",
}

# Planner → physical channel mapping from the paper.
DEFAULT_MECHANISM_BY_STRATEGY = {
    "append": "hidden_text_injection",
    "update": "visual_overlay",
    "delete": "visual_overlay",
}

ALLOWED_MECHANISMS_BY_STRATEGY = {
    "append": {"hidden_text_injection"},
    "update": {"font_glyph_remapping", "visual_overlay"},
    "delete": {"font_glyph_remapping", "visual_overlay"},
}


# ---------------------------------------------------------------------------
# Content stream reading-order fix
# ---------------------------------------------------------------------------


def _sort_content_stream_blocks(doc: fitz.Document, page: fitz.Page) -> None:
    """
    Sort the top-level ``q...Q`` blocks in the page's (merged) content stream
    by their Y position so that text extraction follows top-to-bottom
    reading order.

    Must be called AFTER ``page.clean_contents()`` has merged all content
    streams into a single xref.
    """
    xrefs = page.get_contents()
    if len(xrefs) != 1:
        log.debug("_sort_content_stream_blocks: expected 1 xref, got %s", len(xrefs))
        return

    xref = xrefs[0]
    stream = doc.xref_stream(xref).decode("latin-1", errors="replace")

    # Split into top-level q...Q blocks
    blocks: list[str] = []
    depth = 0
    current_start = 0
    preamble = ""
    i = 0

    while i < len(stream):
        ch = stream[i]

        if ch == "q" and (i == 0 or stream[i - 1] in " \n\r\t"):
            if i + 1 >= len(stream) or stream[i + 1] in " \n\r\t":
                if depth == 0:
                    if not blocks and not preamble:
                        preamble = stream[:i]
                    current_start = i
                depth += 1

        elif ch == "Q" and (i == 0 or stream[i - 1] in " \n\r\t"):
            if i + 1 >= len(stream) or stream[i + 1] in " \n\r\t":
                depth -= 1
                if depth == 0:
                    blocks.append(stream[current_start : i + 1])
        i += 1

    if len(blocks) < 2:
        return  # nothing to sort

    page_height = page.rect.height or DEFAULT_PAGE_HEIGHT

    def _get_block_y(block: str) -> float | None:
        # insert_text blocks use absolute page coords: "1 0 0 1 X Y Tm"
        tm_abs = re.search(r"1\s+0\s+0\s+1\s+[\d.]+\s+([\d.]+)\s+Tm", block)
        if tm_abs:
            return page_height - float(tm_abs.group(1))

        # Main-content blocks have a CTM then relative positioning
        cm = re.search(
            r"([\d.]+)\s+0\s+0\s+([\d.-]+)\s+([\d.]+)\s+([\d.]+)\s+cm", block
        )
        if not cm:
            return None

        d = float(cm.group(2))
        f_val = float(cm.group(4))

        # First text position via Td
        td = re.search(r"([\d.-]+)\s+([\d.-]+)\s+Td", block)
        if td:
            return f_val + float(td.group(2)) * d

        # Or via 6-element Tm
        tm6 = re.search(
            r"[\d.-]+\s+[\d.-]+\s+[\d.-]+\s+[\d.-]+\s+[\d.-]+\s+([\d.-]+)\s+Tm",
            block,
        )
        if tm6:
            return f_val + float(tm6.group(1)) * d

        return None

    annotated = []
    for idx, block in enumerate(blocks):
        y = _get_block_y(block)
        annotated.append({"idx": idx, "y": y, "block": block})

    with_y = [b for b in annotated if b["y"] is not None]
    without_y = [b for b in annotated if b["y"] is None]

    with_y.sort(key=lambda b: b["y"])

    new_stream = preamble + "\n".join(b["block"] for b in without_y + with_y) + "\n"
    doc.update_stream(xref, new_stream.encode("latin-1"))
    log.debug("Sorted %d content blocks by Y position", len(with_y))


def _load_analysis(base_dir: Path) -> dict[str, Any]:
    path = base_dir / "stage2" / "openai" / "analysis.json"
    if not path.is_file():
        raise FileNotFoundError(f"Stage 2 output not found: {path}. Run stage2 first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_plan(base_dir: Path) -> dict[str, Any]:
    path = base_dir / "stage3" / "openai" / "manipulation_plan.json"
    if not path.is_file():
        raise FileNotFoundError(f"Stage 3 output not found: {path}. Run stage3 first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_search_key_in_pdf(pdf_path: Path, search_key: str) -> bool:
    """Check if a search_key actually exists in the PDF text (pre-flight validation)."""
    try:
        doc = fitz.open(pdf_path)
        for page_num in range(len(doc)):
            page = doc[page_num]
            if page.search_for(search_key, quads=False):
                doc.close()
                return True
        doc.close()
        return False
    except Exception:
        return False


def _normalize_semantic_edit_strategy(attack: dict[str, Any]) -> str | None:
    raw = str(attack.get("semantic_edit_strategy") or "").strip().lower()
    if raw in {"append", "update", "delete"}:
        return raw
    legacy = str(attack.get("injection_strategy") or "").strip().lower()
    return SEMANTIC_EDIT_BY_INJECTION_STRATEGY.get(legacy)


def _select_injection_mechanism(attack: dict[str, Any], semantic_strategy: str | None) -> str | None:
    raw = str(attack.get("injection_mechanism") or "").strip().lower()
    if semantic_strategy:
        allowed = ALLOWED_MECHANISMS_BY_STRATEGY.get(semantic_strategy, set())
        if raw:
            if raw in allowed:
                return raw
            log.warning(
                "Attack %s has invalid mechanism '%s' for semantic strategy '%s'; using mapped default.",
                attack.get("attack_id", "?"),
                raw,
                semantic_strategy,
            )
        # Technique-level hint when strategy allows two mechanisms.
        tech = str(attack.get("technique") or "").strip().lower()
        if semantic_strategy in {"update", "delete"} and tech == "font_glyph_remapping":
            return "font_glyph_remapping"
        return DEFAULT_MECHANISM_BY_STRATEGY.get(semantic_strategy)
    return raw or None


def _extract_hidden_payload_text(attack: dict[str, Any]) -> str:
    payload = str(attack.get("payload_description") or "").strip()
    if not payload:
        return ""
    quoted = re.findall(r"[\"']([^\"']{6,})[\"']", payload)
    if quoted:
        return quoted[0].strip()
    return payload[:600]


def _build_hidden_text_insertions(
    plan: dict[str, Any],
    *,
    mechanism_mode: str,
    priority_filter: str | None,
) -> list[HiddenTextItem]:
    insertions: list[HiddenTextItem] = []
    text_attacks = plan.get("text_attacks") or []
    text_attacks_sorted = sorted(
        text_attacks,
        key=lambda a: PRIORITY_ORDER.get((a.get("priority") or "low").lower(), 99),
    )
    if priority_filter:
        filter_level = PRIORITY_ORDER.get(priority_filter.lower(), 99)
        text_attacks_sorted = [
            a
            for a in text_attacks_sorted
            if PRIORITY_ORDER.get((a.get("priority") or "low").lower(), 99) <= filter_level
        ]

    for attack in text_attacks_sorted:
        semantic = _normalize_semantic_edit_strategy(attack)
        mechanism = _select_injection_mechanism(attack, semantic)
        if mechanism != "hidden_text_injection":
            continue
        if mechanism_mode not in {"auto", "hidden_text_injection"}:
            continue

        page = attack.get("target", {}).get("page")
        if page is None:
            page = 0
        try:
            page_num = max(0, int(page))
        except Exception:
            page_num = 0

        payload = _extract_hidden_payload_text(attack)
        if not payload:
            log.warning("Skipping hidden-text attack %s: empty payload_description", attack.get("attack_id", "?"))
            continue

        target_bbox = attack.get("target", {}).get("bbox")
        bbox_list = None
        if isinstance(target_bbox, list):
            try:
                bbox_list = [float(x) for x in target_bbox[:8]]
            except Exception:
                bbox_list = None

        insertions.append(
            HiddenTextItem(
                page=page_num,
                payload=payload,
                attack_id=attack.get("attack_id"),
                target_bbox=bbox_list,
            )
        )
        log.info(
            "Hidden-text insertion queued: [%s] page=%s chars=%s",
            attack.get("attack_id", "?"),
            page_num,
            len(payload),
        )

    return insertions


def _build_replacements(
    analysis: dict[str, Any],
    plan: dict[str, Any],
    pdf_path: Path | None = None,
    priority_filter: str | None = None,
    mechanism_mode: str = "auto",
) -> list[ReplacementItem]:
    """
    Build list of replacements from Stage 3 text_attacks, ordered by priority.

    Args:
        analysis: Stage 2 analysis dict.
        plan: Stage 3 manipulation plan dict.
        pdf_path: Optional path to original PDF for search_key validation.
        priority_filter: If set, only include attacks at this priority level or higher.
                         E.g. "high" = only high; "medium" = high + medium; None = all.
        mechanism_mode: "auto" uses planner mapping; otherwise force one mechanism
                        ("visual_overlay", "font_glyph_remapping", "hidden_text_injection").
    """
    items: list[ReplacementItem] = []
    seen_keys: set[str] = set()

    # Collect text_attacks with scope=everywhere, sorted by priority (high first)
    text_attacks = plan.get("text_attacks") or []
    text_attacks_sorted = sorted(
        text_attacks,
        key=lambda a: PRIORITY_ORDER.get((a.get("priority") or "low").lower(), 99),
    )

    # Determine which priority levels to include
    if priority_filter:
        filter_level = PRIORITY_ORDER.get(priority_filter.lower(), 99)
        text_attacks_sorted = [
            a for a in text_attacks_sorted
            if PRIORITY_ORDER.get((a.get("priority") or "low").lower(), 99) <= filter_level
        ]

    # Build Stage 2 sensitive_elements lookup for cross-referencing
    sensitive_values = set()
    for elem in analysis.get("sensitive_elements") or []:
        val = elem.get("value_to_replace")
        if val:
            sensitive_values.add(val)

    # Optional: T1 ↔ #1 alignment check (diagnostic only)
    first_everywhere = next((a for a in text_attacks_sorted if a.get("scope") == "everywhere"), None)
    first_value = None
    if analysis.get("sensitive_elements"):
        first_value = (analysis["sensitive_elements"][0].get("value_to_replace") or "").strip()
    if first_everywhere and first_value:
        first_key = (first_everywhere.get("search_key") or "").strip()
        if first_key != first_value:
            log.warning(
                "T1 / first everywhere attack search_key does not match Stage 2 #1 value_to_replace; check Stage 3 alignment."
            )

    for attack in text_attacks_sorted:
        semantic = _normalize_semantic_edit_strategy(attack)
        mechanism = _select_injection_mechanism(attack, semantic)
        if mechanism is None:
            log.debug("Skipping attack %s: missing semantic/mechanism data", attack.get("attack_id", "?"))
            continue
        if mechanism_mode != "auto" and mechanism != mechanism_mode:
            continue
        if mechanism == "hidden_text_injection":
            # Append attacks are handled by hidden text insertion, not replacement.
            continue
        if mechanism == "font_glyph_remapping":
            log.info(
                "Attack %s requests font_glyph_remapping; applying text replacement fallback in current implementation.",
                attack.get("attack_id", "?"),
            )

        if attack.get("scope") != "everywhere":
            continue
        search_key = (attack.get("search_key") or "").strip()
        replacement = (attack.get("replacement") or "").strip()
        if not search_key:
            log.warning(
                "Skipping attack %s: empty search_key",
                attack.get("attack_id", "?"),
            )
            continue
        if not replacement:
            log.warning(
                "Skipping attack %s: empty replacement for search_key=%s",
                attack.get("attack_id", "?"),
                search_key[:50],
            )
            continue
        if search_key == replacement:
            log.warning(
                "Skipping attack %s: search_key equals replacement (%s)",
                attack.get("attack_id", "?"),
                search_key[:50],
            )
            continue
        if search_key in seen_keys:
            log.debug("Skipping duplicate search_key: %s", search_key[:50])
            continue

        # Pre-flight: validate that search_key exists in the PDF
        if pdf_path and pdf_path.is_file():
            if not _validate_search_key_in_pdf(pdf_path, search_key):
                log.warning(
                    "Attack %s: search_key '%s' NOT FOUND in PDF — skipping. "
                    "This often means Stage 2 value_to_replace doesn't exactly match PDF text.",
                    attack.get("attack_id", "?"),
                    search_key[:80],
                )
                continue

        # Cross-reference: warn if search_key isn't from Stage 2 sensitive_elements
        if search_key not in sensitive_values:
            log.info(
                "Attack %s: search_key '%s' is not from Stage 2 sensitive_elements "
                "(may be a Stage 3-generated target)",
                attack.get("attack_id", "?"),
                search_key[:50],
            )

        seen_keys.add(search_key)
        items.append(
            ReplacementItem(
                search_key=search_key,
                replacement=replacement,
                scope="everywhere",
                consistency_note=attack.get("consistency_note"),
                semantic_edit_strategy=semantic,
                injection_mechanism=mechanism,
            )
        )
        log.info(
            "Replacement queued: [%s] '%s' → '%s' (priority=%s, semantic=%s, mechanism=%s)",
            attack.get("attack_id", "?"),
            search_key[:50],
            replacement[:50],
            attack.get("priority", "?"),
            semantic or "?",
            mechanism,
        )

    # Handle consistency: if an attack has related replacements in consistency_note,
    # try to parse and add them as additional replacements
    for attack in text_attacks_sorted:
        consistency = attack.get("consistency_note")
        if not consistency:
            continue
        # Look for related_elements from Stage 2 that match this attack's search_key
        for elem in analysis.get("sensitive_elements") or []:
            if elem.get("value_to_replace") != attack.get("search_key"):
                continue
            for related in elem.get("related_elements") or []:
                related_preview = related.get("content_preview") or ""
                # related_elements don't have their own replacement — they're informational
                # The consistency_note in the attack should have specified them
                if related_preview:
                    log.debug(
                        "Consistency note for %s references related element: %s",
                        attack.get("attack_id", "?"),
                        related_preview[:60],
                    )

    return items


def _apply_replacements_to_pdf(
    original_pdf_path: Path,
    out_pdf_path: Path,
    replacements: list[ReplacementItem],
) -> dict[str, int]:
    """
    Apply text replacements to the PDF using redact + insert_text,
    then fix reading order by sorting content stream blocks.

    Does NOT modify the original file.
    Returns per-key hit count stats.
    """
    log.info("PDF injection: %s, %d replacements", original_pdf_path, len(replacements))
    stats: dict[str, int] = {}
    doc = fitz.open(original_pdf_path)

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_insertions: list[tuple[fitz.Rect, str]] = []

            # Find hits and add redaction annotations
            for item in replacements:
                if not item.search_key:
                    continue
                hits = page.search_for(item.search_key, quads=False)
                if hits:
                    stats[item.search_key] = stats.get(item.search_key, 0) + len(hits)
                    log.debug(
                        "'%s': %d hits on page %d",
                        item.search_key[:50],
                        len(hits),
                        page_num + 1,
                    )
                for rect in hits:
                    page.add_redact_annot(rect)
                    page_insertions.append((rect, item.replacement))

            if not page_insertions:
                continue

            # Step 1: Apply redactions (removes original text)
            page.apply_redactions()

            # Step 2: Insert replacement text at original positions (baseline)
            for rect, repl_text in page_insertions:
                page.insert_text(
                    (rect.x0, rect.y1 - 3),
                    repl_text,
                    fontsize=11,
                    fontname="helv",
                    overlay=True,
                )

            # Step 3: Merge all content streams into one
            page.clean_contents()

            # Step 4: Sort content stream blocks by Y position (reading-order fix)
            _sort_content_stream_blocks(doc, page)

        total = sum(stats.values())
        if total == 0:
            log.warning(
                "NO replacements matched! Check search_key accuracy."
            )
        else:
            log.info("Applied %d replacements across %d keys", total, len(stats))

        doc.save(out_pdf_path, garbage=4, deflate=True)
        log.info("Saved perturbed PDF: %s", out_pdf_path)
        return stats
    finally:
        doc.close()


def _apply_hidden_text_insertions_to_pdf(
    pdf_path: Path,
    insertions: list[HiddenTextItem],
) -> int:
    """Insert hidden text payloads into the PDF in-place."""
    if not insertions:
        return 0

    doc = fitz.open(pdf_path)
    applied = 0
    try:
        for item in insertions:
            if item.page >= len(doc):
                log.warning(
                    "Skipping hidden-text insertion %s: page %s out of range (pages=%s)",
                    item.attack_id or "?",
                    item.page,
                    len(doc),
                )
                continue

            page = doc[item.page]
            x = 24.0
            y = max(20.0, page.rect.height - 18.0)
            if item.target_bbox and len(item.target_bbox) >= 4:
                x = float(item.target_bbox[0])
                y = float(item.target_bbox[1]) + 2.0

            # Keep payload machine-readable but visually imperceptible.
            page.insert_text(
                (x, y),
                item.payload,
                fontsize=9.0,
                fontname="helv",
                color=(1, 1, 1),
                overlay=True,
            )
            applied += 1

        if applied:
            tmp_path = pdf_path.with_suffix(".tmp.pdf")
            doc.save(tmp_path, garbage=4, deflate=True)
            tmp_path.replace(pdf_path)
            log.info("Applied %s hidden-text insertions to %s", applied, pdf_path)
        return applied
    finally:
        doc.close()


def run_injection(
    base_dir: Path,
    original_pdf_path: Path | None = None,
    priority_filter: str | None = None,
    mechanism_mode: str = "auto",
) -> dict[str, Any]:
    """
    Run Stage 4 injection:
    - apply replacements for update/delete attacks
    - optionally add hidden-text insertions for append attacks
    and write stage4/perturbed.pdf. Requires original PDF path (or base_dir/original.pdf).

    Args:
        base_dir: Base output directory.
        original_pdf_path: Path to original PDF. Default: base_dir/original.pdf.
        priority_filter: Only apply attacks at this priority or higher.
                         "high" = only high-priority (most decision-critical).
                         "medium" = high + medium.
                         None = all priorities.
        mechanism_mode: "auto" (paper mapping), or force a specific mechanism
                        ("visual_overlay", "font_glyph_remapping", "hidden_text_injection").

    Returns:
        dict with perturbed_pdf_path, replacements, hidden_text_insertions,
        replacement_stats, hidden_text_stats, and error (if any).
    """
    base_dir = Path(base_dir)
    stage4_dir = base_dir / "stage4"
    stage4_dir.mkdir(parents=True, exist_ok=True)
    perturbed_pdf = stage4_dir / "perturbed.pdf"
    replacements_path = stage4_dir / "replacements.json"
    hidden_text_path = stage4_dir / "hidden_text.json"

    resolved_original = original_pdf_path if original_pdf_path is not None else base_dir / "original.pdf"
    if not resolved_original.is_file():
        log.error("Stage 4: original PDF not found: %s", resolved_original)
        return {
            "perturbed_pdf_path": None,
            "replacements": [],
            "hidden_text_insertions": [],
            "replacement_stats": {},
            "hidden_text_stats": {"applied": 0},
            "error": f"original.pdf not found at {resolved_original}; pass --original-pdf or run with run --stage4.",
        }

    log.info(
        "Stage 4 injection: base_dir=%s, original_pdf=%s, priority_filter=%s, mechanism_mode=%s",
        base_dir,
        resolved_original,
        priority_filter or "all",
        mechanism_mode,
    )

    try:
        analysis_raw = _load_analysis(base_dir)
        Stage2Analysis.model_validate(analysis_raw)
        plan_raw = _load_plan(base_dir)
        ManipulationPlan.model_validate(plan_raw)
    except Exception as e:
        log.exception("Stage 4: validation failed loading analysis/plan: %s", e)
        return {
            "perturbed_pdf_path": None,
            "replacements": [],
            "hidden_text_insertions": [],
            "replacement_stats": {},
            "hidden_text_stats": {"applied": 0},
            "error": str(e),
        }

    replacements = _build_replacements(
        analysis_raw,
        plan_raw,
        pdf_path=resolved_original,
        priority_filter=priority_filter,
        mechanism_mode=mechanism_mode,
    )
    hidden_text_insertions = _build_hidden_text_insertions(
        plan_raw,
        mechanism_mode=mechanism_mode,
        priority_filter=priority_filter,
    )
    if not replacements:
        log.warning(
            "Stage 4: no valid replacements found. Possible causes: "
            "(1) No text_attacks with supported mechanism + scope=everywhere in Stage 3 plan, "
            "(2) search_key values don't match PDF text exactly, "
            "(3) priority_filter=%s excluded all attacks. "
            "Copying original to perturbed.",
            priority_filter or "none",
        )
    else:
        log.info("Stage 4: applying %s replacements (priority_filter=%s)",
                 len(replacements), priority_filter or "all")

    manifest = ReplacementsManifest(replacements=replacements)
    try:
        replacements_path.write_text(json.dumps(manifest.model_dump(), indent=2), encoding="utf-8")
        log.debug("Wrote %s", replacements_path)
    except Exception as e:
        log.exception("Failed to write replacements.json: %s", e)
        return {
            "perturbed_pdf_path": None,
            "replacements": [r.model_dump() for r in replacements],
            "hidden_text_insertions": [i.model_dump() for i in hidden_text_insertions],
            "replacement_stats": {},
            "hidden_text_stats": {"applied": 0},
            "error": str(e),
        }

    hidden_manifest = HiddenTextManifest(insertions=hidden_text_insertions)
    try:
        hidden_text_path.write_text(json.dumps(hidden_manifest.model_dump(), indent=2), encoding="utf-8")
        log.debug("Wrote %s", hidden_text_path)
    except Exception as e:
        log.exception("Failed to write hidden_text.json: %s", e)
        return {
            "perturbed_pdf_path": None,
            "replacements": [r.model_dump() for r in replacements],
            "hidden_text_insertions": [i.model_dump() for i in hidden_text_insertions],
            "replacement_stats": {},
            "hidden_text_stats": {"applied": 0},
            "error": str(e),
        }

    try:
        if replacements:
            stats = _apply_replacements_to_pdf(resolved_original, perturbed_pdf, replacements)
        else:
            shutil.copy2(resolved_original, perturbed_pdf)
            stats = {}
            log.info("Saved perturbed PDF (copy): %s", perturbed_pdf)

        hidden_applied = _apply_hidden_text_insertions_to_pdf(perturbed_pdf, hidden_text_insertions)
        return {
            "perturbed_pdf_path": str(perturbed_pdf),
            "replacements": [r.model_dump() for r in replacements],
            "hidden_text_insertions": [i.model_dump() for i in hidden_text_insertions],
            "replacement_stats": stats,
            "hidden_text_stats": {"applied": hidden_applied},
            "resolved_mechanism_mode": mechanism_mode,
            "error": None,
        }
    except Exception as e:
        log.exception("Stage 4: direct PDF injection failed: %s", e)
        return {
            "perturbed_pdf_path": None,
            "replacements": [r.model_dump() for r in replacements],
            "hidden_text_insertions": [i.model_dump() for i in hidden_text_insertions],
            "replacement_stats": {},
            "hidden_text_stats": {"applied": 0},
            "resolved_mechanism_mode": mechanism_mode,
            "error": str(e),
        }
