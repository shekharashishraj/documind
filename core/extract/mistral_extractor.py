from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

from core.extract.base import Extractor
from core.extract.models import ExtractionResult

try:
    from mistralai import Mistral
except ImportError:
    Mistral = None


def _pdf_to_base64_url(pdf_path: str) -> str:
    """Read PDF and return data URL for OCR API."""
    raw = Path(pdf_path).read_bytes()
    b64 = base64.standard_b64encode(raw).decode("ascii")
    return f"data:application/pdf;base64,{b64}"


def _get(obj: dict | object, key: str, default=None):
    """Get key from dict or object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _serialize_page(page: dict | object, output_dir: Path) -> dict:
    """Convert OCR page to JSON-serializable dict; save images to disk and reference by path."""
    out = {
        "index": _get(page, "index", 0),
        "markdown": _get(page, "markdown") or "",
        "dimensions": _get(page, "dimensions") or {},
        "hyperlinks": _get(page, "hyperlinks") or [],
        "header": _get(page, "header"),
        "footer": _get(page, "footer"),
        "tables": _get(page, "tables") or [],
        "images": [],
    }
    images = _get(page, "images") or []
    images_dir = output_dir / "images"
    if images:
        images_dir.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(images):
        entry = {
            "id": _get(img, "id", f"img-{i}"),
            "bbox": {
                "top_left_x": _get(img, "top_left_x"),
                "top_left_y": _get(img, "top_left_y"),
                "bottom_right_x": _get(img, "bottom_right_x"),
                "bottom_right_y": _get(img, "bottom_right_y"),
            },
        }
        b64 = _get(img, "image_base64")
        if b64:
            raw = None
            if isinstance(b64, bytes):
                raw = b64
            elif isinstance(b64, str):
                if b64.startswith("data:"):
                    match = re.match(r"data:image/[^;]+;base64,(.+)", b64)
                    if match:
                        raw = base64.standard_b64decode(match.group(1))
                else:
                    raw = base64.standard_b64decode(b64)
            if raw:
                ext = "jpeg" if raw[:2] == b"\xff\xd8" else "png"
                rel_id = _get(img, "id", f"img-{i}")
                safe_id = re.sub(r"[^\w\-.]", "_", str(rel_id))
                img_path = images_dir / f"{safe_id}.{ext}"
                img_path.write_bytes(raw)
                entry["path"] = str(img_path)
        out["images"].append(entry)
    return out


class MistralExtractor(Extractor):
    """VLM extraction via Mistral OCR API. Returns markdown, bounding boxes, and extracted images."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "mistral-ocr-latest",
        include_image_base64: bool = True,
    ):
        self.api_key = api_key or os.environ.get("MISTRAL_API_KEY", "")
        self.model = model
        self.include_image_base64 = include_image_base64

    def extract(self, pdf_path: str, output_dir: Path) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not Mistral:
            summary = ExtractionResult(
                run_type="vlm",
                sub_mechanism="mistral",
                pdf_path=pdf_path,
                output_dir=str(output_dir),
                num_pages=0,
                artifacts=[],
                extra={"error": "mistralai not installed"},
            )
            return summary.model_dump()

        if not self.api_key:
            summary = ExtractionResult(
                run_type="vlm",
                sub_mechanism="mistral",
                pdf_path=pdf_path,
                output_dir=str(output_dir),
                num_pages=0,
                artifacts=[],
                extra={"error": "MISTRAL_API_KEY not set"},
            )
            return summary.model_dump()

        document_url = _pdf_to_base64_url(pdf_path)
        client = Mistral(api_key=self.api_key)

        try:
            response = client.ocr.process(
                model=self.model,
                document={"type": "document_url", "document_url": document_url},
                include_image_base64=self.include_image_base64,
            )
        except Exception as e:
            summary = ExtractionResult(
                run_type="vlm",
                sub_mechanism="mistral",
                pdf_path=pdf_path,
                output_dir=str(output_dir),
                num_pages=0,
                artifacts=[],
                extra={"error": str(e)},
            )
            return summary.model_dump()

        pages_raw = getattr(response, "pages", None) or []
        pages_list = list(pages_raw) if pages_raw else []
        # Normalize to dict if SDK returns Pydantic/objects
        def to_dict(p):
            if isinstance(p, dict):
                return p
            if hasattr(p, "model_dump"):
                return p.model_dump()
            return p
        pages_data = [_serialize_page(to_dict(p), output_dir) for p in pages_list]

        full_markdown_parts = []
        for p in pages_data:
            full_markdown_parts.append(f"--- Page {p['index'] + 1} ---\n{p['markdown']}")
        full_markdown = "\n\n".join(full_markdown_parts)

        full_markdown_txt = output_dir / "full_markdown.txt"
        full_markdown_md = output_dir / "full_markdown.md"
        full_markdown_txt.write_text(full_markdown, encoding="utf-8")
        full_markdown_md.write_text(full_markdown, encoding="utf-8")

        json_path = output_dir / "pages.json"
        json_path.write_text(json.dumps(pages_data, indent=2), encoding="utf-8")

        artifacts = [str(full_markdown_txt), str(full_markdown_md), str(json_path)]
        images_dir = output_dir / "images"
        if images_dir.is_dir():
            artifacts.extend(str(p) for p in images_dir.iterdir() if p.is_file())

        result = ExtractionResult(
            run_type="vlm",
            sub_mechanism="mistral",
            pdf_path=pdf_path,
            output_dir=str(output_dir),
            num_pages=len(pages_data),
            artifacts=artifacts,
            extra={"model": getattr(response, "model", self.model)},
        )
        return result.model_dump()
