"""Stage 3: call OpenAI to produce manipulation plan (what, where, risk, effects)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from core.stage3.prompts import STAGE3_SYSTEM_PROMPT

log = logging.getLogger(__name__)

# Max chars for structure summary in prompt
STRUCTURE_MAX_CHARS = 25_000

# Filename pattern: page_<i>_img_<j>_x<xref>.<ext>
IMAGE_FNAME_PATTERN = re.compile(r"page_(\d+)_img_\d+_x(\d+)\.\w+", re.IGNORECASE)


def _load_stage2_analysis(base_dir: Path) -> dict[str, Any]:
    """Load Stage 2 analysis.json."""
    path = base_dir / "stage2" / "openai" / "analysis.json"
    if not path.is_file():
        raise FileNotFoundError(f"Stage 2 output not found: {path}. Run stage2 first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _compact_structure_from_pages(pages: list[Any]) -> list[dict[str, Any]]:
    """Build a compact per-page structure: page index, block count, and per-block type, bbox, text preview."""
    out = []
    for p in pages:
        page_idx = p.get("page", len(out))
        blocks = p.get("blocks", [])
        block_summaries = []
        for i, b in enumerate(blocks):
            bbox = b.get("bbox")
            text = (b.get("text") or "")[:80].replace("\n", " ")
            block_type = b.get("type", "unknown")
            block_summaries.append({
                "block_index": i,
                "type": block_type,
                "bbox": bbox,
                "text_preview": text.strip() or None,
            })
        out.append({"page": page_idx, "block_count": len(blocks), "blocks": block_summaries})
    return out


def _load_structure_summary(base_dir: Path) -> str:
    """Load pages.json from byte_extraction/pymupdf and return a compact structure summary string."""
    pages_path = base_dir / "byte_extraction" / "pymupdf" / "pages.json"
    if not pages_path.is_file():
        return "Step 1 pages.json not found; no structure summary available."
    pages = json.loads(pages_path.read_text(encoding="utf-8"))
    compact = _compact_structure_from_pages(pages)
    raw = json.dumps(compact, indent=2)
    if len(raw) > STRUCTURE_MAX_CHARS:
        raw = raw[:STRUCTURE_MAX_CHARS] + "\n... (truncated)"
    return raw


def _load_images_list(base_dir: Path) -> list[dict[str, Any]]:
    """List embedded images from byte_extraction/pymupdf/images/ with page and xref from filenames."""
    images_dir = base_dir / "byte_extraction" / "pymupdf" / "images"
    if not images_dir.is_dir():
        return []
    out = []
    for p in sorted(images_dir.iterdir()):
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            m = IMAGE_FNAME_PATTERN.match(p.name)
            if m:
                out.append({"page": int(m.group(1)), "xref": int(m.group(2)), "path": p.name})
            else:
                out.append({"path": p.name, "page": None, "xref": None})
    return out


def _build_user_message(analysis: dict[str, Any], structure_summary: str, images_list: list[dict[str, Any]]) -> str:
    """Build the user message for the planner."""
    parts = [
        "## Stage 2 analysis\n",
        json.dumps(analysis, indent=2),
        "\n\n## Step 1 structure (per-page blocks with bbox, type, text preview)\n",
        structure_summary,
    ]
    if images_list:
        parts.append("\n\n## Embedded images (page, xref from filenames)\n")
        parts.append(json.dumps(images_list, indent=2))
    parts.append("\n\nProduce the attack plan JSON as specified in the system prompt.")
    return "".join(parts)


def run_stage3_openai(
    base_dir: str | Path,
    *,
    model: str = "gpt-4o",
    api_key: str | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """
    Run Stage 3: call OpenAI to produce a manipulation plan from Stage 2 analysis and Step 1 structure.
    Writes base_dir/stage3/openai/manipulation_plan.json and returns the parsed result.
    """
    base_dir = Path(base_dir)
    analysis = _load_stage2_analysis(base_dir)
    structure_summary = _load_structure_summary(base_dir)
    images_list = _load_images_list(base_dir)

    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Stage 3 requires openai: pip install openai") from None

    client = OpenAI(api_key=api_key or None)
    prompt = system_prompt or STAGE3_SYSTEM_PROMPT
    user_content = _build_user_message(analysis, structure_summary, images_list)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]

    log.info("Stage 3: calling OpenAI %s for manipulation plan", model)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        max_completion_tokens=8192,
    )

    raw_content = response.choices[0].message.content
    if not raw_content:
        raise ValueError("OpenAI returned empty content")

    result = json.loads(raw_content)

    # Count total attack items across all categories
    text_attacks = result.get("text_attacks", [])
    image_attacks = result.get("image_attacks", [])
    structural_attacks = result.get("structural_attacks", [])
    total_attacks = len(text_attacks) + len(image_attacks) + len(structural_attacks)

    out_dir = base_dir / "stage3" / "openai"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "manipulation_plan.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    log.info(
        "Stage 3: wrote %s (%s text, %s image, %s structural attacks)",
        out_path, len(text_attacks), len(image_attacks), len(structural_attacks),
    )

    usage = None
    if getattr(response, "usage", None) is not None:
        u = response.usage
        usage = u.model_dump() if hasattr(u, "model_dump") else {"total_tokens": getattr(u, "total_tokens", None)}
    return {
        "manipulation_plan": result,
        "total_attacks": total_attacks,
        "output_path": str(out_path),
        "usage": usage,
    }
