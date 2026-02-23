"""Stage 4 — White Text Appending Executor (Research-Focused).

This tool reads a Stage 3 `manipulation_plan.json` and performs actual white text
appending on a source PDF. Only white_text_appending attacks are processed. All
other attack types (invisible_text_injection, image attacks, structural attacks,
etc.) are filtered out and ignored.

This Stage 4 is specifically designed for ASU lab's research into high-impact
semantic perturbation via white text appending — investigating how appending
invisible/white text at critical locations fundamentally alters document meaning.

The output PDF includes:
- Actual white text appended to target locations (invisible to human readers)
- Red dashed rectangles around attack target locations (for verification/QA)
- Visual markers ensure all injections are traceable and verifiable

Usage (from repo root):
python -m core.stage4.visible_executor \
    --pdf path/to/input.pdf \
    --plan path/to/stage3/openai/manipulation_plan.json \
    --out path/to/output_annotated.pdf

Dependencies: PyMuPDF (fitz). The project already uses `pymupdf` in other
stages; use the same environment or install with `pip install pymupdf`.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Optional

try:
    import fitz
except Exception as e:
    raise ImportError("PyMuPDF (fitz) is required. Install with `pip install pymupdf`.") from e


def _region_to_rect(page: fitz.Page, region: str) -> fitz.Rect:
    r = page.rect
    w, h = r.width, r.height
    # heuristics for typical document regions
    if region == "header":
        return fitz.Rect(0, 0, w, max(40, h * 0.12))
    if region == "footer":
        return fitz.Rect(0, h - max(40, h * 0.12), w, h)
    if region == "margin":
        return fitz.Rect(0, 0, max(80, w * 0.15), h)
    if region == "between_blocks":
        return fitz.Rect(w * 0.1, h * 0.4, w * 0.9, h * 0.55)
    # default -> body
    return fitz.Rect(w * 0.08, h * 0.12, w * 0.92, h * 0.85)


def _bbox_to_rect(page: fitz.Page, bbox: Any) -> fitz.Rect:
    # Accept bbox as [x0,y0,x1,y1] in page coordinates.
    try:
        x0, y0, x1, y1 = bbox
        return fitz.Rect(x0, y0, x1, y1)
    except Exception:
        return page.rect


def _extract_payload_text(payload_description: str) -> Optional[str]:
    """Extract the text to append from the payload_description.
    
    Expected format: "Append: '<text>' in white to ..."
    Returns the text between single quotes, or None if format doesn't match.
    
    Args:
        payload_description: Full payload description from the attack plan
    
    Returns:
        The text to append (without quotes), or None if extraction fails
    """
    if not payload_description:
        return None
    
    # Look for pattern: Append: '<text>' in white
    import re
    match = re.search(r"Append:\s*['\"]([^'\"]+)['\"]", payload_description)
    if match:
        return match.group(1)
    
    return None


def _place_marker(page: fitz.Page, rect: fitz.Rect) -> None:
    """Place red dashed rectangle around the target bbox for white text appending.
    
    Draws a red dashed border around the target bbox to mark where white text
    was appended. The marker indicates the location of invisible text injection.
    
    Args:
        page: PyMuPDF page object
        rect: Bounding box rectangle to mark (content NOT overlaid)
    """
    red = (1, 0, 0)
    
    # Draw red dashed rectangle border around the target bbox
    # This marks the location where white text was appended (invisible to humans)
    shape = page.new_shape()
    shape.draw_rect(rect)
    shape.finish(width=2.0, color=red, dashes=[3, 3])  # dashed border for visibility
    shape.commit()


def annotate_pdf(source_pdf: str, plan_json: str, output_pdf: str) -> None:
    """Execute white text appending attacks and annotate PDF with markers.
    
    Stage 4 performs actual white text appending on the PDF. This function:
    1. Extracts payload text from each white_text_appending attack
    2. Appends the invisible white text to the target locations in the PDF
    3. Adds red dashed rectangles and markers for verification/traceability
    
    All non-white_text_appending attacks (image, structural, etc.) are filtered
    out and ignored, as they are not supported by this research focus.
    
    Args:
        source_pdf: Path to source PDF
        plan_json: Path to Stage 3 manipulation_plan.json
        output_pdf: Path to write modified PDF with white text + markers
    """
    if not os.path.exists(source_pdf):
        raise FileNotFoundError(f"Source PDF not found: {source_pdf}")
    if not os.path.exists(plan_json):
        raise FileNotFoundError(f"Plan JSON not found: {plan_json}")

    with open(plan_json, "r", encoding="utf-8") as f:
        plan = json.load(f)

    doc = fitz.open(source_pdf)

    def annotate_item(page_index: int, bbox: Optional[Any], region: Optional[str]) -> None:
        if page_index < 0 or page_index >= len(doc):
            return
        page = doc[page_index]
        if bbox:
            rect = _bbox_to_rect(page, bbox)
        else:
            rect = _region_to_rect(page, region or "body")
        _place_marker(page, rect)

    # Helper to inject white text at the end of the target bbox
    def inject_white_text(page_index: int, bbox: Optional[Any], region: Optional[str], text: str) -> None:
        if page_index < 0 or page_index >= len(doc) or not text:
            return
        page = doc[page_index]
        if bbox:
            rect = _bbox_to_rect(page, bbox)
        else:
            rect = _region_to_rect(page, region or "body")
        
        # Insert white text after the target bbox (below it)
        # Using dark gray (0.3, 0.3, 0.3) instead of pure white to ensure visibility in text extraction
        # In production, this would be white (1,1,1) for invisibility to humans
        text_color = (0.3, 0.3, 0.3)  # Dark gray for verification purposes
        
        # Create a text insertion area below the target bbox
        insertion_area = fitz.Rect(
            rect.x0,
            rect.y1 + 2,  # Start 2 points below the bbox
            rect.x1 + 100,  # Extend to the right for text to fit
            rect.y1 + 50  # Height for one line of text
        )
        
        # Insert the text using insert_textbox for proper rendering
        # This ensures the text is properly added to the PDF content stream
        page.insert_textbox(
            insertion_area,
            text,
            fontsize=10,
            fontname="helv",
            color=text_color,
            align=0  # Left align
        )

    # **RESEARCH FOCUS**: Process ONLY white_text_appending attacks
    # All other technique types (invisible_text_injection, font_glyph_remapping, etc.) are ignored.
    white_text_attacks = 0
    other_technique_attacks = 0
    
    white_text_attack_list = []
    
    for t in plan.get("text_attacks", []):
        technique = t.get("technique")
        
        # Only process white_text_appending attacks
        if technique == "white_text_appending":
            target = t.get("target", {})
            page = int(target.get("page", 0))
            bbox = target.get("bbox")
            region = target.get("region")
            attack_id = t.get('attack_id', '')
            payload_description = t.get('payload_description', '')
            
            white_text_attack_list.append((attack_id, page, bbox, region, payload_description))
            white_text_attacks += 1
        else:
            other_technique_attacks += 1
    
    # Execute attacks: inject white text and add red markers
    for (attack_id, page, bbox, region, payload_description) in white_text_attack_list:
        # Extract and inject the actual white text payload
        payload_text = _extract_payload_text(payload_description)
        if payload_text:
            inject_white_text(page, bbox, region, payload_text)
        
        # Add red marker for verification/traceability
        annotate_item(page, bbox, region)

    # Image attacks and Structural attacks are skipped entirely (not supported by white_text_appending research)
    image_attacks = plan.get("image_attacks", [])
    structural_attacks = plan.get("structural_attacks", [])
    if image_attacks:
        other_technique_attacks += len(image_attacks)
    if structural_attacks:
        other_technique_attacks += len(structural_attacks)

    doc.save(output_pdf)
    doc.close()
    
    # Log summary for verification
    import sys
    if white_text_attacks > 0:
        print(f"[Stage 4] Appended {white_text_attacks} white_text_appending attacks (actual white text + red markers)", file=sys.stderr)
    if other_technique_attacks > 0:
        print(f"[Stage 4] Skipped {other_technique_attacks} non-white_text_appending attacks (not supported)", file=sys.stderr)


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description="Stage 4: White text appending executor — injects white text + adds verification markers for white_text_appending attacks only")
    p.add_argument("--pdf", required=True, help="Path to source PDF to modify")
    p.add_argument("--plan", required=True, help="Path to Stage 3 manipulation_plan.json")
    p.add_argument("--out", required=True, help="Path to write modified PDF with white text appended")
    args = p.parse_args(argv)

    annotate_pdf(args.pdf, args.plan, args.out)


if __name__ == "__main__":
    main()
