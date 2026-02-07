from __future__ import annotations

import json
from pathlib import Path

import fitz

from core.extract.base import Extractor
from core.extract.models import ExtractionResult


def _extract_images_from_page(doc: fitz.Document, page_index: int, images_dir: Path) -> list[dict]:
    """Extract embedded images from a page and save to images_dir. Return list of {path, bbox?, xref}."""
    page = doc[page_index]
    image_list = page.get_images(full=True)
    saved = []
    for img_index, img_info in enumerate(image_list):
        xref = img_info[0]
        try:
            base = doc.extract_image(xref)
            raw = base.get("image")
            ext = base.get("ext", "png") or "png"
            if raw is None:
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                img_path = images_dir / f"page_{page_index}_img_{img_index}_x{xref}.png"
                pix.save(str(img_path))
                pix = None
            else:
                img_path = images_dir / f"page_{page_index}_img_{img_index}_x{xref}.{ext}"
                img_path.write_bytes(raw)
            saved.append({"path": str(img_path), "page": page_index, "xref": xref})
        except Exception:
            continue
    return saved


class PyMuPDFExtractor(Extractor):
    """Byte-level extraction via PyMuPDF. Outputs text, blocks, markdown, and extracted images."""

    def extract(self, pdf_path: str, output_dir: Path) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(pdf_path)
        pages_data = []
        full_text_lines = []
        markdown_lines = []
        all_images = []

        for page_index in range(len(doc)):
            page = doc[page_index]
            text = page.get_text()
            full_text_lines.append(f"--- Page {page_index + 1} ---\n{text}")

            blocks = page.get_text("blocks")
            block_data = [
                {"bbox": list(b[:4]), "text": (b[4] or "").strip(), "type": b[5]}
                for b in blocks
                if (b[4] or "").strip()
            ]
            page_images = _extract_images_from_page(doc, page_index, images_dir)
            all_images.extend(page_images)

            pages_data.append({
                "page": page_index,
                "text": text,
                "blocks": block_data,
                "images": [{"path": im["path"], "xref": im["xref"]} for im in page_images],
            })

            markdown_lines.append(f"## Page {page_index + 1}\n\n{text.strip()}\n")

        doc.close()

        full_text_path = output_dir / "full_text.txt"
        full_text_path.write_text("\n\n".join(full_text_lines), encoding="utf-8")

        full_markdown = "\n\n".join(markdown_lines)
        full_markdown_path = output_dir / "full_markdown.md"
        full_markdown_path.write_text(full_markdown, encoding="utf-8")

        json_path = output_dir / "pages.json"
        json_path.write_text(json.dumps(pages_data, indent=2), encoding="utf-8")

        artifacts = [str(full_text_path), str(full_markdown_path), str(json_path)]
        artifacts.extend(im["path"] for im in all_images)

        result = ExtractionResult(
            run_type="byte_extraction",
            sub_mechanism="pymupdf",
            pdf_path=pdf_path,
            output_dir=str(output_dir),
            num_pages=len(pages_data),
            artifacts=artifacts,
        )
        return result.model_dump()
