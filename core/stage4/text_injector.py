"""Text injection techniques for Stage 4."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

log = logging.getLogger(__name__)

# Unicode homoglyph mappings (visually similar characters)
HOMOGLYPH_MAP = {
    "a": "\u0430",  # Cyrillic 'а'
    "b": "\u044c",  # Cyrillic soft sign (visual approximation)
    "c": "\u0441",  # Cyrillic 'с'
    "d": "\u0501",  # Cyrillic Komi De
    "e": "\u0435",  # Cyrillic 'е'
    "g": "\u0261",  # Latin script g
    "h": "\u04bb",  # Cyrillic shha
    "i": "\u0456",  # Cyrillic 'і'
    "j": "\u0458",  # Cyrillic 'ј'
    "k": "\u043a",  # Cyrillic 'к'
    "m": "\u043c",  # Cyrillic 'м'
    "n": "\u0578",  # Armenian vo
    "o": "\u043e",  # Cyrillic 'о'
    "p": "\u0440",  # Cyrillic 'р'
    "q": "\u051b",  # Cyrillic qa
    "r": "\u0433",  # Cyrillic 'г'
    "s": "\u0455",  # Cyrillic 'ѕ'
    "t": "\u0442",  # Cyrillic 'т'
    "u": "\u057d",  # Armenian se
    "v": "\u03bd",  # Greek nu
    "w": "\u051d",  # Cyrillic we
    "x": "\u0445",  # Cyrillic 'х'
    "y": "\u0443",  # Cyrillic 'у'
    "z": "\u1d22",  # Latin letter small capital z
    "A": "\u0410",  # Cyrillic 'А'
    "B": "\u0412",  # Cyrillic 'В'
    "C": "\u0421",  # Cyrillic 'С'
    "D": "\u13a0",  # Cherokee A
    "E": "\u0415",  # Cyrillic 'Е'
    "F": "\u15b4",  # Canadian syllabics
    "G": "\u050c",  # Cyrillic Komi Sje
    "H": "\u041d",  # Cyrillic 'Н'
    "I": "\u0406",  # Cyrillic 'І'
    "J": "\u0408",  # Cyrillic 'Ј'
    "K": "\u041a",  # Cyrillic 'К'
    "L": "\u216c",  # Roman numeral fifty
    "M": "\u041c",  # Cyrillic 'М'
    "N": "\u039d",  # Greek Nu
    "O": "\u041e",  # Cyrillic 'О'
    "P": "\u0420",  # Cyrillic 'Р'
    "Q": "\u051a",  # Cyrillic QA
    "R": "\u13a1",  # Cherokee E
    "S": "\u0405",  # Cyrillic 'Ѕ'
    "T": "\u0422",  # Cyrillic 'Т'
    "U": "\u054d",  # Armenian Se
    "V": "\u0474",  # Izhitsa
    "W": "\u051c",  # Cyrillic WE
    "X": "\u0425",  # Cyrillic 'Х'
    "Y": "\u03a5",  # Greek Upsilon
    "Z": "\u0396",  # Greek Zeta
    "0": "\u04e8",  # Cyrillic 'Ө' (looks like 0)
    "1": "\u0406",  # Cyrillic 'І' (looks like 1)
    "2": "\u01a7",  # Latin tone two
    "3": "\u0417",  # Cyrillic 'З'
    "4": "\u04b6",  # Cyrillic che with descender
    "5": "\u01bc",  # Latin tone five
    "6": "\u0431",  # Cyrillic 'б'
    "7": "\u03a4",  # Greek Tau
    "8": "\u0222",  # Latin OU
    "9": "\u09ed",  # Bengali digit seven (visual approximation)
}

# Zero-width characters for whitespace encoding
ZERO_WIDTH_CHARS = [
    "\u200b",  # Zero-width space
    "\u200c",  # Zero-width non-joiner
    "\u200d",  # Zero-width joiner
    "\ufeff",  # Zero-width no-break space (BOM)
]


def _to_homoglyphs(payload: str) -> tuple[str, int]:
    """Replace supported characters with homoglyphs and return (text, replacement_count)."""
    out = []
    replaced = 0
    for char in payload:
        mapped = HOMOGLYPH_MAP.get(char)
        if mapped is not None:
            out.append(mapped)
            replaced += 1
        else:
            out.append(char)
    return "".join(out), replaced


def _insert_hidden_text(
    page: fitz.Page,
    payload: str,
    point: fitz.Point,
    *,
    fontsize: float = 10,
) -> str:
    """
    Insert hidden text at on-page coordinates.

    We combine render_mode=3 with white color so even if a renderer ignores render_mode,
    the text is still less likely to be visible.
    """
    try:
        page.insert_text(
            point,
            payload,
            fontsize=fontsize,
            fontname="helv",
            render_mode=3,
            color=(1, 1, 1),
        )
        return "render_mode_3_white"
    except TypeError:
        page.insert_text(
            point,
            payload,
            fontsize=fontsize,
            fontname="helv",
            color=(1, 1, 1),
            fill_opacity=0,
            stroke_opacity=0,
        )
        return "zero_opacity_white"
    except Exception:
        page.insert_text(
            point,
            payload,
            fontsize=fontsize,
            fontname="helv",
            color=(1, 1, 1),
        )
        return "white_fallback"


def apply_text_attack(
    doc: fitz.Document,
    attack: dict[str, Any],
    pages_json: list[dict[str, Any]],
) -> tuple[dict[str, Any], fitz.Document]:
    """
    Apply a single text attack from manipulation plan.

    Returns (result, doc). If a handler needs to reload the PDF, it may
    return a new document instance.
    """
    technique = attack.get("technique", "").lower()
    attack_id = attack.get("attack_id", "unknown")

    technique_handlers = {
        "invisible_text_injection": _inject_invisible_text,
        "font_glyph_remapping": _inject_with_malicious_font,
        "unicode_homoglyph": _inject_homoglyphs,
        "whitespace_encoding": _inject_whitespace_encoded,
        "dual_layer_overlay": _inject_dual_layer,
        "content_stream_edit": _modify_content_stream,
        "metadata_field_edit": _edit_metadata,
    }

    handler = technique_handlers.get(technique)
    if handler is None:
        return {
            "attack_id": attack_id,
            "technique": technique,
            "status": "failed",
            "error": f"Unknown technique: {technique}",
        }

    try:
        result = handler(doc, attack, pages_json)
        if isinstance(result, tuple) and len(result) == 2:
            return result
        return result, doc
    except Exception as e:
        log.error("Text attack %s (%s) failed: %s", attack_id, technique, e)
        return (
            {
                "attack_id": attack_id,
                "technique": technique,
                "status": "failed",
                "error": str(e),
            },
            doc,
        )


def _get_injection_point(attack: dict, pages_json: list) -> tuple[int, fitz.Point, fitz.Rect | None]:
    """
    Determine injection point from attack target.

    Returns (page_num, point, rect or None).
    """
    target = attack.get("target") or {}
    page_num = target.get("page", 0) if target else 0
    bbox = target.get("bbox") if target else None
    region = target.get("region", "body")

    if bbox and len(bbox) == 4:
        # Use bbox center for point, bbox for rect
        x0, y0, x1, y1 = bbox
        point = fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)
        rect = fitz.Rect(x0, y0, x1, y1)
        return page_num, point, rect

    # Default positions by region
    region_positions = {
        "header": fitz.Point(72, 50),
        "footer": fitz.Point(72, 750),
        "margin": fitz.Point(20, 400),
        "between_blocks": fitz.Point(300, 400),
        "body": fitz.Point(72, 200),
    }

    point = region_positions.get(region, fitz.Point(72, 200))
    return page_num, point, None


def _inject_invisible_text(
    doc: fitz.Document,
    attack: dict[str, Any],
    pages_json: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Inject text that is invisible to humans but visible to parsers.

    Uses multiple techniques:
    - render_mode=3 (invisible rendering)
    - White text on white background (color matching)
    - Zero opacity
    - Tiny font size
    """
    attack_id = attack.get("attack_id", "unknown")
    payload = attack.get("payload_description", "INJECTED_TEXT")
    page_num, point, rect = _get_injection_point(attack, pages_json)

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "invisible_text_injection",
            "status": "failed",
            "error": f"Page {page_num} out of range (doc has {len(doc)} pages)",
        }

    page = doc[page_num]

    method_used = _insert_hidden_text(page, payload, point, fontsize=11)

    return {
        "attack_id": attack_id,
        "technique": "invisible_text_injection",
        "status": "success",
        "target": {"page": page_num, "point": [point.x, point.y]},
        "details": f"Injected {len(payload)} chars using {method_used}",
        "method": method_used,
    }


def _inject_with_symbol_or_homoglyph(
    doc: fitz.Document,
    attack: dict[str, Any],
    pages_json: list[dict[str, Any]],
) -> dict[str, Any]:
    """Fallback visible insertion using Symbol font or homoglyph substitutions."""
    attack_id = attack.get("attack_id", "unknown")
    payload = attack.get("payload_description", "INJECTED_TEXT")

    page_num, point, rect = _get_injection_point(attack, pages_json)

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "font_glyph_remapping",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]

    # If a bbox is provided, paint over the original region first to make the replacement clear.
    if rect is not None:
        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), overlay=True)
        insert_point = fitz.Point(rect.x0, rect.y1 - 2)
    else:
        insert_point = point

    method = "symbol_font"
    replaced_count = 0
    try:
        # Built-in Symbol font remaps standard character codes to different glyphs.
        page.insert_text(
            insert_point,
            payload,
            fontsize=11,
            fontname="symbol",
            color=(0, 0, 0),
        )
    except Exception:
        # Fallback: explicit Unicode homoglyph substitution.
        remapped_payload, replaced_count = _to_homoglyphs(payload)
        page.insert_text(
            insert_point,
            remapped_payload,
            fontsize=11,
            fontname="helv",
            color=(0, 0, 0),
        )
        method = "unicode_homoglyph_fallback"

    return {
        "attack_id": attack_id,
        "technique": "font_glyph_remapping",
        "status": "success",
        "target": {"page": page_num, "point": [insert_point.x, insert_point.y]},
        "details": f"Rendered {len(payload)} chars using {method}",
        "method": method,
        "original_length": len(payload),
        "homoglyphs_used": replaced_count,
    }


def _inject_with_malicious_font(
    doc: fitz.Document,
    attack: dict[str, Any],
    pages_json: list[dict[str, Any]],
) -> dict[str, Any] | tuple[dict[str, Any], fitz.Document]:
    """Attempt true font glyph remapping; fall back to visible insertion on failure."""
    attack_id = attack.get("attack_id", "unknown")
    old_word = (attack.get("search_key") or "").strip()
    new_word = (attack.get("replacement") or "").strip()

    if not old_word or not new_word:
        log.warning(
            "Font remap attack %s missing search_key/replacement; using fallback insertion.",
            attack_id,
        )
        result = _inject_with_symbol_or_homoglyph(doc, attack, pages_json)
        result["method"] = "fallback_symbol"
        return result

    try:
        from core.stage4.font_remap import FontRemapUnavailable, attempt_font_remap

        tmp_dir = None
        if getattr(doc, "name", None):
            tmp_dir = str(Path(doc.name).parent)

        fd_in, in_path = tempfile.mkstemp(suffix=".pdf", dir=tmp_dir)
        os.close(fd_in)
        doc.save(in_path)

        fd_out, out_path = tempfile.mkstemp(suffix=".pdf", dir=tmp_dir)
        os.close(fd_out)

        attempt = attempt_font_remap(
            in_path,
            out_path,
            old_word,
            new_word,
            cache_dir=Path(tmp_dir) / "font_cache" if tmp_dir else None,
            allow_space_pad=True,
        )
        if attempt.success:
            try:
                os.remove(in_path)
            except OSError:
                pass
            new_doc = fitz.open(out_path)
            return (
                {
                    "attack_id": attack_id,
                    "technique": "font_glyph_remapping",
                    "status": "success",
                    "details": f"Remapped {attempt.replaced} occurrences",
                    "method": "font_remap",
                    "padding_used": attempt.used_padding,
                },
                new_doc,
            )

        log.warning("Font remap attack %s failed: %s", attack_id, attempt.error)
    except FontRemapUnavailable as e:
        log.warning("Font remap unavailable for attack %s: %s", attack_id, e)
    except Exception as e:
        log.warning("Font remap attack %s errored: %s", attack_id, e)

    result = _inject_with_symbol_or_homoglyph(doc, attack, pages_json)
    result["method"] = "fallback_symbol"
    return result


def _inject_homoglyphs(
    doc: fitz.Document,
    attack: dict[str, Any],
    pages_json: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Inject text with Unicode homoglyphs (visually similar characters).

    Replaces Latin characters with Cyrillic lookalikes.
    """
    attack_id = attack.get("attack_id", "unknown")
    payload = attack.get("payload_description", "INJECTED_TEXT")

    page_num, point, rect = _get_injection_point(attack, pages_json)

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "unicode_homoglyph",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]

    homoglyph_payload, replaced_count = _to_homoglyphs(payload)

    # Insert with normal rendering (homoglyphs are visually similar)
    page.insert_text(
        point,
        homoglyph_payload,
        fontsize=11,
        fontname="helv",
    )

    return {
        "attack_id": attack_id,
        "technique": "unicode_homoglyph",
        "status": "success",
        "target": {"page": page_num, "point": [point.x, point.y]},
        "details": f"Injected {len(payload)} chars with {replaced_count} homoglyph substitutions",
        "original_length": len(payload),
        "homoglyphs_used": replaced_count,
    }


def _inject_whitespace_encoded(
    doc: fitz.Document,
    attack: dict[str, Any],
    pages_json: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Inject hidden information using zero-width characters.

    Encodes payload as sequence of zero-width characters.
    """
    attack_id = attack.get("attack_id", "unknown")
    payload = attack.get("payload_description", "INJECTED_TEXT")

    page_num, point, rect = _get_injection_point(attack, pages_json)

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "whitespace_encoding",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]

    # Encode payload as zero-width characters (binary encoding)
    encoded = ""
    for char in payload:
        # Use 8-bit binary representation
        binary = format(ord(char), "08b")
        for bit in binary:
            # 0 = ZWSP, 1 = ZWNJ
            encoded += ZERO_WIDTH_CHARS[int(bit)]

    method_used = _insert_hidden_text(page, encoded, point, fontsize=11)

    return {
        "attack_id": attack_id,
        "technique": "whitespace_encoding",
        "status": "success",
        "target": {"page": page_num, "point": [point.x, point.y]},
        "details": (
            f"Encoded {len(payload)} chars as {len(encoded)} zero-width characters using {method_used}"
        ),
        "original_length": len(payload),
        "encoded_length": len(encoded),
        "method": method_used,
    }


def _inject_dual_layer(
    doc: fitz.Document,
    attack: dict[str, Any],
    pages_json: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Inject text and cover it with an overlaying shape.

    Text is visible to parsers but hidden by shape for humans.
    """
    attack_id = attack.get("attack_id", "unknown")
    payload = attack.get("payload_description", "INJECTED_TEXT")

    page_num, point, rect = _get_injection_point(attack, pages_json)

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "dual_layer_overlay",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]

    # Calculate text dimensions (approximate)
    text_width = len(payload) * 6  # Rough estimate
    text_height = 14

    # Create covering rectangle
    cover_rect = fitz.Rect(
        point.x - 2,
        point.y - text_height,
        point.x + text_width + 2,
        point.y + 2,
    )

    # Insert text first (will be under the shape)
    page.insert_text(
        point,
        payload,
        fontsize=11,
        fontname="helv",
        color=(0, 0, 0),  # Black text
    )

    # Draw covering rectangle on top (same color as background - white)
    page.draw_rect(
        cover_rect,
        color=(1, 1, 1),  # White border
        fill=(1, 1, 1),   # White fill
        overlay=True,     # Draw on top
    )

    return {
        "attack_id": attack_id,
        "technique": "dual_layer_overlay",
        "status": "success",
        "target": {"page": page_num, "point": [point.x, point.y]},
        "details": f"Injected {len(payload)} chars covered by white rectangle",
        "cover_rect": [cover_rect.x0, cover_rect.y0, cover_rect.x1, cover_rect.y1],
    }


def _modify_content_stream(
    doc: fitz.Document,
    attack: dict[str, Any],
    pages_json: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Directly modify PDF content stream to inject text.

    This is a lower-level approach that manipulates the raw content stream.
    """
    attack_id = attack.get("attack_id", "unknown")
    payload = attack.get("payload_description", "INJECTED_TEXT")

    target = attack.get("target", {})
    page_num = target.get("page", 0)

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "content_stream_edit",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]

    # For content stream editing, use PyMuPDF's clean approach
    # which safely adds content without corrupting existing stream

    # Use a shape to add text (safer than raw stream editing)
    shape = page.new_shape()

    # Position for injection (prefer explicit target if present).
    point = fitz.Point(72, 200)
    bbox = target.get("bbox")
    if bbox and len(bbox) == 4:
        point = fitz.Point(bbox[0], bbox[3])

    # Insert text via shape (appends to content stream) with invisible rendering when available.
    try:
        shape.insert_text(
            point,
            payload,
            fontsize=1,
            fontname="helv",
            render_mode=3,
            color=(1, 1, 1),
        )
    except TypeError:
        # Older PyMuPDF versions may not support render_mode on Shape.insert_text.
        shape.insert_text(
            point,
            payload,
            fontsize=1,
            fontname="helv",
            color=(1, 1, 1),
        )
    shape.commit()

    return {
        "attack_id": attack_id,
        "technique": "content_stream_edit",
        "status": "success",
        "target": {"page": page_num, "point": [point.x, point.y]},
        "details": (
            f"Appended {len(payload)} chars to content stream using hidden text "
            "(render_mode_3 or white fallback)"
        ),
    }


def _edit_metadata(
    doc: fitz.Document,
    attack: dict[str, Any],
    pages_json: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Modify PDF metadata fields to inject hidden information.

    Metadata is often extracted by parsers and can contain hidden payloads.
    """
    attack_id = attack.get("attack_id", "unknown")
    payload = attack.get("payload_description", "INJECTED_METADATA")

    # Get current metadata
    current_metadata = doc.metadata or {}

    # Common metadata fields to modify
    target = attack.get("target", {})
    field = target.get("field", "keywords")

    # Map of modifiable fields
    metadata_fields = {
        "title": "title",
        "author": "author",
        "subject": "subject",
        "keywords": "keywords",
        "creator": "creator",
        "producer": "producer",
    }

    field_key = metadata_fields.get(field, "keywords")

    # Inject payload into metadata
    new_metadata = dict(current_metadata)
    existing_value = new_metadata.get(field_key, "")

    if existing_value:
        new_metadata[field_key] = f"{existing_value} {payload}"
    else:
        new_metadata[field_key] = payload

    # Apply new metadata
    doc.set_metadata(new_metadata)

    return {
        "attack_id": attack_id,
        "technique": "metadata_field_edit",
        "status": "success",
        "target": {"field": field_key},
        "details": f"Injected payload into metadata field '{field_key}'",
        "previous_value": existing_value[:50] if existing_value else None,
        "new_value": new_metadata[field_key][:100],
    }
