"""Stage 2: call OpenAI Chat Completions (GPT) with Step 1 outputs and extracted images."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from core.stage2.prompts import STAGE2_SYSTEM_PROMPT
from core.stage2.schemas import Stage2Analysis

log = logging.getLogger(__name__)

# Max characters of pages.json to include in the prompt (avoid token overflow)
PAGES_JSON_MAX_CHARS = 30_000


def _load_step1_artifacts(base_dir: Path) -> tuple[str, str, list[Path]]:
    """Load document text, pages.json summary, and image paths from byte_extraction/pymupdf."""
    pymupdf_dir = base_dir / "byte_extraction" / "pymupdf"
    if not pymupdf_dir.is_dir():
        raise FileNotFoundError(f"Step 1 output not found: {pymupdf_dir}")

    # Document text: prefer full_markdown.md, else full_text.txt
    doc_text = ""
    md_path = pymupdf_dir / "full_markdown.md"
    txt_path = pymupdf_dir / "full_text.txt"
    if md_path.is_file():
        doc_text = md_path.read_text(encoding="utf-8")
    elif txt_path.is_file():
        doc_text = txt_path.read_text(encoding="utf-8")
    else:
        raise FileNotFoundError(f"No full_markdown.md or full_text.txt in {pymupdf_dir}")

    # pages.json: include truncated so we stay within context
    pages_summary = ""
    pages_path = pymupdf_dir / "pages.json"
    if pages_path.is_file():
        raw = pages_path.read_text(encoding="utf-8")
        if len(raw) > PAGES_JSON_MAX_CHARS:
            pages_summary = raw[:PAGES_JSON_MAX_CHARS] + "\n... (truncated)"
        else:
            pages_summary = raw

    # Images from byte_extraction/pymupdf/images/
    images_dir = pymupdf_dir / "images"
    image_paths: list[Path] = []
    if images_dir.is_dir():
        for p in sorted(images_dir.iterdir()):
            if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                image_paths.append(p)

    return doc_text, pages_summary, image_paths


def _build_user_content(
    doc_text: str,
    pages_summary: str,
    image_paths: list[Path],
) -> list[dict[str, Any]]:
    """Build Chat Completions user message content: text parts + image_url parts."""
    text_block = (
        "## Document text (from Step 1)\n\n"
        f"{doc_text[:80_000]}\n\n"
        "## Structured pages with bounding boxes (from Step 1 pages.json)\n\n"
        f"{pages_summary}"
    )
    if len(doc_text) > 80_000:
        text_block += "\n\n(Document text was truncated for length.)"

    content: list[dict[str, Any]] = [{"type": "text", "text": text_block}]

    for img_path in image_paths:
        try:
            raw = img_path.read_bytes()
            b64 = base64.standard_b64encode(raw).decode("ascii")
            # Infer media type from extension
            ext = img_path.suffix.lower()
            if ext == ".png":
                mime = "image/png"
            elif ext in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ext == ".webp":
                mime = "image/webp"
            elif ext == ".gif":
                mime = "image/gif"
            else:
                mime = "image/png"
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "auto"},
            })
        except Exception as e:
            log.warning("Skip image %s: %s", img_path, e)

    return content


def run_stage2_openai(
    base_dir: str | Path,
    *,
    model: str = "gpt-5-2025-08-07",
    api_key: str | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """
    Run Stage 2: call OpenAI Chat Completions with Step 1 outputs and images.
    Writes base_dir/stage2/openai/analysis.json and returns the parsed result + paths.
    """
    base_dir = Path(base_dir)
    out_path = base_dir / "stage2" / "openai" / "analysis.json"
    log.info("Stage 2: base_dir=%s, output path=%s", base_dir, out_path)
    doc_text, pages_summary, image_paths = _load_step1_artifacts(base_dir)

    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("Stage 2 requires openai: pip install openai") from None

    client = OpenAI(api_key=api_key or None)  # None => env OPENAI_API_KEY
    prompt = system_prompt or STAGE2_SYSTEM_PROMPT
    user_content = _build_user_content(doc_text, pages_summary, image_paths)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_content},
    ]

    log.info("Stage 2: calling OpenAI %s with %s pages text and %s images", model, "pages.json", len(image_paths))
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        max_completion_tokens=16384,
    )

    # Log raw response shape for debugging empty content
    num_choices = len(response.choices) if response.choices else 0
    log.debug("Stage 2: API response id=%s, choices=%s", getattr(response, "id", None), num_choices)
    if response.choices:
        c0 = response.choices[0]
        msg = c0.message
        finish = getattr(c0, "finish_reason", None)
        raw_content = msg.content if msg else None
        log.debug("Stage 2: choice[0] finish_reason=%s, message.content len=%s", finish, len(raw_content) if raw_content else 0)
        if not raw_content:
            log.error(
                "Stage 2: OpenAI returned empty content; finish_reason=%s, message=%s",
                finish,
                msg.model_dump() if hasattr(msg, "model_dump") else str(msg),
            )
    else:
        raw_content = None
        log.error("Stage 2: OpenAI returned no choices; response id=%s", getattr(response, "id", None))

    if not raw_content:
        log.error("Stage 2: OpenAI returned empty content")
        raise ValueError("OpenAI returned empty content")

    analysis = json.loads(raw_content)
    try:
        Stage2Analysis.model_validate(analysis)
    except ValidationError as e:
        log.exception("Stage 2 validation failed: %s", e)
        raise

    out_dir = base_dir / "stage2" / "openai"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "analysis.json"
    out_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    log.info("Stage 2 completed: output_path=%s", out_path)

    usage = None
    if getattr(response, "usage", None) is not None:
        u = response.usage
        usage = u.model_dump() if hasattr(u, "model_dump") else {"total_tokens": getattr(u, "total_tokens", None)}
    return {
        "analysis": analysis,
        "output_path": str(out_path),
        "usage": usage,
    }
