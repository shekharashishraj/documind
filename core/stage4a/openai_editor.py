"""Stage 4a: call OpenAI to produce minimal edit plan from Stage 3 strategy."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.stage4a.prompts import STAGE4A_SYSTEM_PROMPT

log = logging.getLogger(__name__)

STRUCTURE_MAX_CHARS = 25_000


def _load_stage3_plan(base_dir: Path) -> dict[str, Any]:
    """Load Stage 3 manipulation_plan.json."""
    plan_path = base_dir / "stage3" / "openai" / "manipulation_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(f"Stage 3 output not found: {plan_path}. Run stage3 first.")
    return json.loads(plan_path.read_text(encoding="utf-8"))


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


def _build_user_message(stage3_plan: dict[str, Any], structure_summary: str) -> str:
    """Build the user message for Stage 4a editor."""
    parts = [
        "## Stage 3 manipulation plan\n\n",
        json.dumps(stage3_plan, indent=2),
        "\n\n## Step 1 structure (per-page blocks with bbox, type, text preview)\n\n",
        structure_summary,
        "\n\nProduce the minimal edit plan JSON as specified in the system prompt.",
    ]
    return "".join(parts)


def _count_stage3_attacks(stage3_plan: dict[str, Any]) -> int:
    """Count total attacks from Stage 3 across text/image/structural categories."""
    return (
        len(stage3_plan.get("text_attacks") or [])
        + len(stage3_plan.get("image_attacks") or [])
        + len(stage3_plan.get("structural_attacks") or [])
    )


def run_stage4a_openai(
    base_dir: str | Path,
    *,
    model: str = "gpt-4o",
    api_key: str | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """
    Run Stage 4a: call OpenAI to produce minimal edit plan from Stage 3 strategy.
    Writes base_dir/stage4a/openai/edit_plan.json and returns the parsed result.
    """
    base_dir = Path(base_dir)
    stage3_plan = _load_stage3_plan(base_dir)
    structure_summary = _load_structure_summary(base_dir)

    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Stage 4a requires openai: pip install openai") from None

    client = OpenAI(api_key=api_key or None)
    prompt = system_prompt or STAGE4A_SYSTEM_PROMPT
    user_content = _build_user_message(stage3_plan, structure_summary)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]

    log.info("Stage 4a: calling OpenAI %s for minimal edit plan", model)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        max_completion_tokens=4096,
    )

    raw_content = response.choices[0].message.content
    if not raw_content:
        raise ValueError("OpenAI returned empty content")

    edit_plan = json.loads(raw_content)
    expected_variants = _count_stage3_attacks(stage3_plan)
    actual_variants = len(edit_plan.get("variants") or [])
    if actual_variants != expected_variants:
        log.error(
            "Stage 4a: variant count mismatch expected=%s actual=%s",
            expected_variants,
            actual_variants,
        )
        raise ValueError(
            f"Stage 4a expected {expected_variants} variants (one per Stage 3 attack) "
            f"but got {actual_variants}"
        )
    else:
        log.info("Stage 4a: generated %s variants (one per Stage 3 attack)", actual_variants)

    out_dir = base_dir / "stage4a" / "openai"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "edit_plan.json"
    out_path.write_text(json.dumps(edit_plan, indent=2), encoding="utf-8")
    log.info("Stage 4a: wrote %s", out_path)

    usage = None
    if getattr(response, "usage", None) is not None:
        u = response.usage
        usage = u.model_dump() if hasattr(u, "model_dump") else {"total_tokens": getattr(u, "total_tokens", None)}

    return {
        "edit_plan": edit_plan,
        "output_path": str(out_path),
        "expected_variants": expected_variants,
        "variants": actual_variants,
        "usage": usage,
    }
