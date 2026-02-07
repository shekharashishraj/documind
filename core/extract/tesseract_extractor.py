from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytesseract
from pytesseract import Output

from core.extract.base import Extractor
from core.extract.models import ExtractionResult

# Tesseract level: 5=word, 4=line
LEVEL_WORD = 5


def _tesseract_page_to_blocks_and_words(img_path: str) -> tuple[list, list]:
    """Run image_to_data and return lines (with bbox) and words (with bbox and confidence)."""
    data = pytesseract.image_to_data(img_path, output_type=Output.DICT)
    n = len(data["text"])
    words_list = []
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        level = int(data["level"][i])
        if level != LEVEL_WORD:
            continue
        left = int(data["left"][i])
        top = int(data["top"][i])
        width = int(data["width"][i])
        height = int(data["height"][i])
        conf = int(data["conf"][i]) if data["conf"][i] != "-1" else None
        block_num = int(data["block_num"][i])
        line_num = int(data["line_num"][i])
        word_num = int(data["word_num"][i])
        words_list.append({
            "text": text,
            "bbox": {"left": left, "top": top, "width": width, "height": height},
            "conf": conf,
            "block_num": block_num,
            "line_num": line_num,
            "word_num": word_num,
        })

    # Build line-level blocks from words (text + bbox as union of word bboxes)
    lines_map = {}
    for w in words_list:
        key = (w["block_num"], w["line_num"])
        if key not in lines_map:
            lines_map[key] = {"words": [], "texts": []}
        lines_map[key]["words"].append(w)
        lines_map[key]["texts"].append(w["text"])
    blocks_list = []
    for (block_num, line_num) in sorted(lines_map.keys()):
        words_in_line = lines_map[(block_num, line_num)]["words"]
        texts = [x["text"] for x in words_in_line]
        boxes = [x["bbox"] for x in words_in_line]
        left = min(b["left"] for b in boxes)
        top = min(b["top"] for b in boxes)
        right = max(b["left"] + b["width"] for b in boxes)
        bottom = max(b["top"] + b["height"] for b in boxes)
        blocks_list.append({
            "level": "line",
            "text": " ".join(texts),
            "bbox": {"left": left, "top": top, "width": right - left, "height": bottom - top},
            "block_num": block_num,
            "line_num": line_num,
        })
    return blocks_list, words_list


class TesseractExtractor(Extractor):
    """OCR extraction via Tesseract (PDF pages rendered to images). Outputs text, bbox, confidence, blocks and words."""

    def extract(self, pdf_path: str, output_dir: Path) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(pdf_path)
        pages_data = []
        full_text_lines = []

        for page_index in range(len(doc)):
            page = doc[page_index]
            pix = page.get_pixmap(dpi=150)
            img_path = output_dir / f"page_{page_index}.png"
            pix.save(str(img_path))

            blocks, words = _tesseract_page_to_blocks_and_words(str(img_path))
            full_text = " ".join(w["text"] for w in words) if words else ""
            full_text_lines.append(f"--- Page {page_index + 1} ---\n{full_text}")
            pages_data.append({
                "page": page_index,
                "text": full_text,
                "blocks": blocks,
                "words": words,
                "dimensions": {"width": pix.width, "height": pix.height},
            })

        doc.close()

        full_text_path = output_dir / "full_text.txt"
        full_text_path.write_text("\n\n".join(full_text_lines), encoding="utf-8")

        markdown_parts = [f"## Page {i + 1}\n\n{pages_data[i]['text'].strip()}\n" for i in range(len(pages_data))]
        full_markdown_path = output_dir / "full_markdown.md"
        full_markdown_path.write_text("\n\n".join(markdown_parts), encoding="utf-8")

        json_path = output_dir / "pages.json"
        json_path.write_text(json.dumps(pages_data, indent=2), encoding="utf-8")

        result = ExtractionResult(
            run_type="ocr",
            sub_mechanism="tesseract",
            pdf_path=pdf_path,
            output_dir=str(output_dir),
            num_pages=len(pages_data),
            artifacts=[str(full_text_path), str(full_markdown_path), str(json_path)],
        )
        return result.model_dump()
