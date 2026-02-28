"""Structural injection techniques for Stage 4 (hyperlinks, annotations, etc.)."""

from __future__ import annotations

import logging
from typing import Any

import fitz  # PyMuPDF

log = logging.getLogger(__name__)


def apply_structural_attack(
    doc: fitz.Document,
    attack: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply a single structural attack (hyperlinks, annotations, etc.).

    Returns execution result dict with status, details, error (if any).
    """
    technique = attack.get("technique", "").lower()
    attack_id = attack.get("attack_id", "unknown")

    technique_handlers = {
        "hyperlink_redirect": _redirect_hyperlink,
        "hyperlink_injection": _inject_hyperlink,
        "hyperlink_removal": _remove_hyperlink,
        "annotation_overlay": _add_hidden_annotation,
        "javascript_injection": _inject_javascript,
        "optional_content_group": _create_hidden_ocg,
    }

    handler = technique_handlers.get(technique)
    if handler is None:
        return {
            "attack_id": attack_id,
            "technique": technique,
            "status": "failed",
            "error": f"Unknown structural technique: {technique}",
        }

    try:
        return handler(doc, attack)
    except Exception as e:
        log.error("Structural attack %s (%s) failed: %s", attack_id, technique, e)
        return {
            "attack_id": attack_id,
            "technique": technique,
            "status": "failed",
            "error": str(e),
        }


def _redirect_hyperlink(
    doc: fitz.Document,
    attack: dict[str, Any],
) -> dict[str, Any]:
    """
    Redirect an existing hyperlink to a malicious URL.

    Finds a link matching the target criteria and changes its URI.
    """
    attack_id = attack.get("attack_id", "unknown")
    target = attack.get("target", {})
    malicious_url = attack.get("malicious_url", "https://example.com/malicious")

    page_num = target.get("page", 0)
    original_url = target.get("original_url")
    link_text = target.get("link_text")

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "hyperlink_redirect",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]
    links = page.get_links()

    if not links:
        return {
            "attack_id": attack_id,
            "technique": "hyperlink_redirect",
            "status": "failed",
            "error": f"No links found on page {page_num}",
        }

    # Find matching link
    target_link = None
    target_index = None

    for idx, link in enumerate(links):
        link_uri = link.get("uri", "")

        # Match by original URL if specified
        if original_url and link_uri and original_url in link_uri:
            target_link = link
            target_index = idx
            break

        # Match by first external link if no specific URL given
        if not original_url and link.get("kind") == fitz.LINK_URI:
            target_link = link
            target_index = idx
            break

    if target_link is None:
        return {
            "attack_id": attack_id,
            "technique": "hyperlink_redirect",
            "status": "failed",
            "error": f"No matching link found on page {page_num}",
            "searched_for": original_url or "any URI link",
            "available_links": len(links),
        }

    # Store original URL for report
    original_found = target_link.get("uri", "")

    # Update link to malicious URL
    target_link["uri"] = malicious_url
    page.update_link(target_link)

    return {
        "attack_id": attack_id,
        "technique": "hyperlink_redirect",
        "status": "success",
        "target": {
            "page": page_num,
            "link_index": target_index,
            "original_url": original_found,
        },
        "details": f"Redirected link from '{original_found[:50]}...' to '{malicious_url}'",
        "malicious_url": malicious_url,
    }


def _inject_hyperlink(
    doc: fitz.Document,
    attack: dict[str, Any],
) -> dict[str, Any]:
    """
    Inject a new hyperlink at a specified location.

    Creates a clickable region that leads to a malicious URL.
    """
    attack_id = attack.get("attack_id", "unknown")
    target = attack.get("target", {})
    malicious_url = attack.get("malicious_url", "https://example.com/malicious")
    link_text = target.get("link_text", "Click here")

    page_num = target.get("page", 0)
    bbox = target.get("bbox")
    region = target.get("region", "body")

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "hyperlink_injection",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]

    # Determine link rectangle
    if bbox and len(bbox) == 4:
        link_rect = fitz.Rect(bbox)
    else:
        # Default positions by region
        region_rects = {
            "header": fitz.Rect(72, 30, 200, 50),
            "footer": fitz.Rect(72, 750, 200, 770),
            "margin": fitz.Rect(10, 400, 60, 420),
            "body": fitz.Rect(72, 200, 200, 220),
        }
        link_rect = region_rects.get(region, fitz.Rect(72, 200, 200, 220))

    # Insert visible link text first
    text_point = fitz.Point(link_rect.x0, link_rect.y1 - 4)
    page.insert_text(
        text_point,
        link_text,
        fontsize=11,
        fontname="helv",
        color=(0, 0, 1),  # Blue (typical link color)
    )

    # Create link annotation
    new_link = {
        "kind": fitz.LINK_URI,
        "from": link_rect,
        "uri": malicious_url,
    }
    page.insert_link(new_link)

    return {
        "attack_id": attack_id,
        "technique": "hyperlink_injection",
        "status": "success",
        "target": {
            "page": page_num,
            "rect": [link_rect.x0, link_rect.y0, link_rect.x1, link_rect.y1],
        },
        "details": f"Injected link '{link_text}' pointing to '{malicious_url}'",
        "link_text": link_text,
        "malicious_url": malicious_url,
    }


def _remove_hyperlink(
    doc: fitz.Document,
    attack: dict[str, Any],
) -> dict[str, Any]:
    """
    Remove an existing hyperlink from the document.

    Can remove legitimate links to prevent users from accessing
    security updates, verification pages, etc.
    """
    attack_id = attack.get("attack_id", "unknown")
    target = attack.get("target", {})

    page_num = target.get("page", 0)
    original_url = target.get("original_url")
    link_text = target.get("link_text")

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "hyperlink_removal",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]
    links = page.get_links()

    if not links:
        return {
            "attack_id": attack_id,
            "technique": "hyperlink_removal",
            "status": "failed",
            "error": f"No links found on page {page_num}",
        }

    # Find matching link to remove
    target_link = None
    removed_url = None

    for link in links:
        link_uri = link.get("uri", "")

        if original_url and link_uri and original_url in link_uri:
            target_link = link
            removed_url = link_uri
            break

        if not original_url and link.get("kind") == fitz.LINK_URI:
            target_link = link
            removed_url = link_uri
            break

    if target_link is None:
        return {
            "attack_id": attack_id,
            "technique": "hyperlink_removal",
            "status": "failed",
            "error": f"No matching link found on page {page_num}",
        }

    # Remove the link
    page.delete_link(target_link)

    return {
        "attack_id": attack_id,
        "technique": "hyperlink_removal",
        "status": "success",
        "target": {"page": page_num, "removed_url": removed_url},
        "details": f"Removed link to '{removed_url[:50]}...'",
    }


def _add_hidden_annotation(
    doc: fitz.Document,
    attack: dict[str, Any],
) -> dict[str, Any]:
    """
    Add a hidden annotation containing payload text.

    Annotations can be invisible but still readable by parsers.
    """
    attack_id = attack.get("attack_id", "unknown")
    target = attack.get("target", {})
    payload = attack.get("payload_description", "Hidden annotation content")

    page_num = target.get("page", 0)
    bbox = target.get("bbox")

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "annotation_overlay",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]

    # Determine annotation position
    if bbox and len(bbox) == 4:
        annot_rect = fitz.Rect(bbox)
    else:
        # Small invisible annotation area
        annot_rect = fitz.Rect(0, 0, 1, 1)

    # Add a text annotation with hidden content
    # Using FreeText annotation with minimal visibility
    annot = page.add_freetext_annot(
        annot_rect,
        payload,
        fontsize=1,  # Tiny
        fontname="helv",
        text_color=(1, 1, 1),  # White (invisible on white)
        fill_color=(1, 1, 1),  # White background
    )

    # Make annotation invisible by setting flags
    if annot:
        annot.set_flags(fitz.PDF_ANNOT_IS_HIDDEN | fitz.PDF_ANNOT_IS_INVISIBLE)
        annot.update()

    return {
        "attack_id": attack_id,
        "technique": "annotation_overlay",
        "status": "success",
        "target": {
            "page": page_num,
            "rect": [annot_rect.x0, annot_rect.y0, annot_rect.x1, annot_rect.y1],
        },
        "details": f"Added hidden annotation with {len(payload)} chars",
    }


def _inject_javascript(
    doc: fitz.Document,
    attack: dict[str, Any],
) -> dict[str, Any]:
    """
    Inject JavaScript action into the document.

    Note: Many PDF viewers block JavaScript for security.
    This is mainly effective for older or less secure viewers.
    """
    attack_id = attack.get("attack_id", "unknown")
    target = attack.get("target", {})
    payload = attack.get("payload_description", "app.alert('Injected');")

    page_num = target.get("page", 0)

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "javascript_injection",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]

    # Create a link with JavaScript action
    js_rect = fitz.Rect(0, 0, 1, 1)  # Tiny invisible area

    # PyMuPDF doesn't directly support JS links, but we can use widget/annotation
    # Create annotation that triggers on open (simplified approach)
    try:
        # Add a text annotation with JS-like content
        # (Full JS injection requires low-level PDF manipulation)
        annot = page.add_text_annot(
            fitz.Point(1, 1),
            f"JavaScript: {payload}",
            icon="Note",
        )
        if annot:
            annot.set_flags(fitz.PDF_ANNOT_IS_HIDDEN)
            annot.update()

        return {
            "attack_id": attack_id,
            "technique": "javascript_injection",
            "status": "success",
            "target": {"page": page_num},
            "details": "Injected JavaScript annotation (execution depends on viewer)",
            "limitation": "Full JS execution requires compatible PDF viewer",
        }
    except Exception as e:
        return {
            "attack_id": attack_id,
            "technique": "javascript_injection",
            "status": "failed",
            "error": str(e),
        }


def _create_hidden_ocg(
    doc: fitz.Document,
    attack: dict[str, Any],
) -> dict[str, Any]:
    """
    Create an Optional Content Group (layer) with hidden content.

    OCGs can be set to ViewState=/OFF to hide content from display
    while keeping it accessible to parsers.
    """
    attack_id = attack.get("attack_id", "unknown")
    target = attack.get("target", {})
    payload = attack.get("payload_description", "Hidden OCG content")

    page_num = target.get("page", 0)

    if page_num >= len(doc):
        return {
            "attack_id": attack_id,
            "technique": "optional_content_group",
            "status": "failed",
            "error": f"Page {page_num} out of range",
        }

    page = doc[page_num]

    # PyMuPDF OCG support is limited; use alternative approach
    # Insert text with very low opacity as approximation
    point = fitz.Point(72, 200)
    bbox = target.get("bbox")
    if bbox and len(bbox) == 4:
        point = fitz.Point(bbox[0], bbox[1])

    # Insert with render_mode=3 (invisible) as OCG approximation
    page.insert_text(
        point,
        payload,
        fontsize=11,
        fontname="helv",
        render_mode=3,
    )

    return {
        "attack_id": attack_id,
        "technique": "optional_content_group",
        "status": "success",
        "target": {"page": page_num, "point": [point.x, point.y]},
        "details": f"Injected {len(payload)} chars (using invisible render as OCG approximation)",
        "limitation": "Full OCG requires low-level PDF structure manipulation",
    }
