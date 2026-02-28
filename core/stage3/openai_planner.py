"""Stage 3: call OpenAI to produce manipulation plan (what, where, risk, effects)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.stage3.prompts import STAGE3_SYSTEM_PROMPT
from core.stage3.schemas import ManipulationPlan

log = logging.getLogger(__name__)

# Max chars for structure summary in prompt
STRUCTURE_MAX_CHARS = 25_000

# Filename pattern: page_<i>_img_<j>_x<xref>.<ext>
IMAGE_FNAME_PATTERN = re.compile(r"page_(\d+)_img_\d+_x(\d+)\.\w+", re.IGNORECASE)

VALID_SEMANTIC_STRATEGIES = {"append", "update", "delete"}
VALID_INJECTION_STRATEGIES = {"addition", "modification", "redaction"}
VALID_INJECTION_MECHANISMS = {"hidden_text_injection", "font_glyph_remapping", "visual_overlay"}

SEMANTIC_BY_INJECTION_STRATEGY = {
    "addition": "append",
    "modification": "update",
    "redaction": "delete",
}

INJECTION_STRATEGY_BY_SEMANTIC = {
    "append": "addition",
    "update": "modification",
    "delete": "redaction",
}

ALLOWED_MECHANISMS_BY_SEMANTIC = {
    "append": {"hidden_text_injection"},
    "update": {"font_glyph_remapping", "visual_overlay"},
    "delete": {"font_glyph_remapping", "visual_overlay"},
}


def _default_mechanism_for_attack(semantic: str, technique: str) -> str:
    if semantic == "append":
        return "hidden_text_injection"
    if semantic in {"update", "delete"} and technique == "font_glyph_remapping":
        return "font_glyph_remapping"
    return "visual_overlay"


def _canonicalize_text_attack_fields(plan: dict[str, Any]) -> dict[str, Any]:
    """
    Canonicalize text attack semantic/mechanism fields so Stage 4 can execute deterministically.

    Requirements:
    - Every text_attack must end with semantic_edit_strategy + injection_mechanism + injection_strategy.
    - semantic_edit_strategy and injection_strategy are always coupled by paper mapping.
    - injection_mechanism is constrained by semantic_edit_strategy.
    """
    text_attacks = plan.get("text_attacks")
    if text_attacks is None:
        return plan
    if not isinstance(text_attacks, list):
        raise ValueError("Stage 3 plan is invalid: 'text_attacks' must be a list.")

    for i, attack in enumerate(text_attacks):
        if not isinstance(attack, dict):
            raise ValueError(f"Stage 3 plan is invalid: text_attacks[{i}] must be an object.")

        attack_id = str(attack.get("attack_id") or f"index_{i + 1}")
        semantic_raw = str(attack.get("semantic_edit_strategy") or "").strip().lower()
        mechanism_raw = str(attack.get("injection_mechanism") or "").strip().lower()
        strategy_raw = str(attack.get("injection_strategy") or "").strip().lower()
        technique = str(attack.get("technique") or "").strip().lower()

        semantic = semantic_raw or None
        if semantic is not None and semantic not in VALID_SEMANTIC_STRATEGIES:
            raise ValueError(
                f"Stage 3 plan is invalid for {attack_id}: semantic_edit_strategy='{semantic_raw}' "
                "must be append|update|delete."
            )

        strategy = strategy_raw or None
        if strategy is not None and strategy not in VALID_INJECTION_STRATEGIES:
            raise ValueError(
                f"Stage 3 plan is invalid for {attack_id}: injection_strategy='{strategy_raw}' "
                "must be addition|modification|redaction."
            )

        if semantic is None:
            if strategy is None:
                raise ValueError(
                    f"Stage 3 plan is invalid for {attack_id}: missing both semantic_edit_strategy "
                    "and injection_strategy."
                )
            semantic = SEMANTIC_BY_INJECTION_STRATEGY[strategy]
            log.warning(
                "Stage 3 planner omitted semantic_edit_strategy for %s; inferred '%s' from injection_strategy.",
                attack_id,
                semantic,
            )

        canonical_strategy = INJECTION_STRATEGY_BY_SEMANTIC[semantic]
        if strategy is not None and strategy != canonical_strategy:
            log.warning(
                "Stage 3 planner mismatch for %s: semantic=%s but injection_strategy=%s. "
                "Canonicalizing injection_strategy to %s.",
                attack_id,
                semantic,
                strategy,
                canonical_strategy,
            )
        strategy = canonical_strategy

        mechanism = mechanism_raw or None
        if mechanism is not None and mechanism not in VALID_INJECTION_MECHANISMS:
            raise ValueError(
                f"Stage 3 plan is invalid for {attack_id}: injection_mechanism='{mechanism_raw}' "
                "must be hidden_text_injection|font_glyph_remapping|visual_overlay."
            )

        allowed = ALLOWED_MECHANISMS_BY_SEMANTIC[semantic]
        if mechanism not in allowed:
            if mechanism is not None:
                log.warning(
                    "Stage 3 planner mismatch for %s: semantic=%s but mechanism=%s. "
                    "Canonicalizing mechanism using paper mapping.",
                    attack_id,
                    semantic,
                    mechanism,
                )
            mechanism = _default_mechanism_for_attack(semantic, technique)

        attack["semantic_edit_strategy"] = semantic
        attack["injection_strategy"] = strategy
        attack["injection_mechanism"] = mechanism

    return plan


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
    model: str = "gpt-5-2025-08-07",
    api_key: str | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """
    Run Stage 3: call OpenAI to produce a manipulation plan from Stage 2 analysis and Step 1 structure.
    Writes base_dir/stage3/openai/manipulation_plan.json and returns the parsed result.
    """
    base_dir = Path(base_dir)
    out_path = base_dir / "stage3" / "openai" / "manipulation_plan.json"
    log.info("Stage 3: base_dir=%s, output path=%s", base_dir, out_path)
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
        max_completion_tokens=16384,
    )

    # Log raw response shape for debugging empty content
    num_choices = len(response.choices) if response.choices else 0
    log.debug("Stage 3: API response id=%s, choices=%s", getattr(response, "id", None), num_choices)
    if response.choices:
        c0 = response.choices[0]
        msg = c0.message
        finish = getattr(c0, "finish_reason", None)
        raw_content = msg.content if msg else None
        log.debug("Stage 3: choice[0] finish_reason=%s, message.content len=%s", finish, len(raw_content) if raw_content else 0)
        if not raw_content:
            log.error(
                "Stage 3: OpenAI returned empty content; finish_reason=%s, message=%s",
                finish,
                msg.model_dump() if hasattr(msg, "model_dump") else str(msg),
            )
    else:
        raw_content = None
        log.error("Stage 3: OpenAI returned no choices; response id=%s", getattr(response, "id", None))

    if not raw_content:
        log.error("Stage 3: OpenAI returned empty content")
        raise ValueError("OpenAI returned empty content")

    result = json.loads(raw_content)
    result = _canonicalize_text_attack_fields(result)
    try:
        ManipulationPlan.model_validate(result)
    except ValidationError as e:
        log.exception("Stage 3 validation failed: %s", e)
        raise

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
        "Stage 3 completed: output_path=%s (%s text, %s image, %s structural attacks)",
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
