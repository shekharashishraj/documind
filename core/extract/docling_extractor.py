from __future__ import annotations

import json
import logging
from pathlib import Path

from docling.document_converter import DocumentConverter

log = logging.getLogger(__name__)

from core.extract.base import Extractor
from core.extract.models import ExtractionResult

try:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import PdfFormatOption
    from docling_core.types.doc import ImageRefMode, PictureItem, TableItem
    _HAS_PICTURE_EXPORT = True
except ImportError:
    _HAS_PICTURE_EXPORT = False
    PdfFormatOption = InputFormat = PdfPipelineOptions = ImageRefMode = PictureItem = TableItem = None


def _get_text_from_element(element) -> str:
    """Extract text from a Docling element (TextItem, TitleItem, etc.)."""
    if hasattr(element, "text") and element.text is not None:
        return str(element.text).strip()
    if hasattr(element, "label") and element.label is not None:
        return str(element.label)
    return ""


def _get_bbox_from_prov(prov) -> dict | None:
    """Extract bbox dict from Docling ProvenanceItem (l, r, t, b)."""
    if not prov or not hasattr(prov, "bbox"):
        return None
    bbox = prov.bbox
    if bbox is None:
        return None
    l_val = getattr(bbox, "l", None)
    r_val = getattr(bbox, "r", None)
    t_val = getattr(bbox, "t", None)
    b_val = getattr(bbox, "b", None)
    if l_val is None and r_val is None and t_val is None and b_val is None:
        return None
    return {"l": l_val, "r": r_val, "t": t_val, "b": b_val}


def _docling_doc_to_pages_with_bbox(doc) -> list[dict]:
    """Walk document via iterate_items; group by page with text and bbox."""
    from collections import defaultdict
    by_page = defaultdict(list)
    try:
        for element, _level in doc.iterate_items():
            text = _get_text_from_element(element)
            if not text and not getattr(element, "prov", None):
                continue
            prov_list = getattr(element, "prov", None) or []
            for prov in prov_list:
                page_no = getattr(prov, "page_no", None)
                if page_no is None:
                    page_no = 1
                page_index = int(page_no) - 1
                bbox = _get_bbox_from_prov(prov)
                by_page[page_index].append({
                    "text": text,
                    "bbox": bbox,
                    "type": type(element).__name__,
                })
    except Exception:
        pass
    if not by_page:
        return [{"page": 0, "text": "", "blocks": []}]
    pages_data = []
    for page_index in sorted(by_page.keys()):
        items = by_page[page_index]
        full_text = " ".join(i["text"] for i in items if i["text"]).strip()
        blocks = [{"text": i["text"], "bbox": i["bbox"], "type": i["type"]} for i in items]
        pages_data.append({
            "page": page_index,
            "text": full_text,
            "blocks": blocks,
        })
    return pages_data


def _is_table(element) -> bool:
    if TableItem is not None and isinstance(element, TableItem):
        return True
    return type(element).__name__ == "TableItem"


def _is_picture(element) -> bool:
    if PictureItem is not None and isinstance(element, PictureItem):
        return True
    return type(element).__name__ == "PictureItem"


def _save_docling_images(conversion_result, output_dir: Path) -> list[str]:
    """Save PictureItem and TableItem images to output_dir/images. Return list of paths."""
    if not _HAS_PICTURE_EXPORT:
        return []
    doc = conversion_result.document
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    table_count = 0
    picture_count = 0

    def save_table(el, count: int) -> bool:
        nonlocal table_count, paths
        try:
            img = el.get_image(doc)
            if img is None:
                log.warning("Docling table %s: get_image returned None", count)
                return False
            out_path = images_dir / f"table_{count}.png"
            with out_path.open("wb") as fp:
                img.save(fp, "PNG")
            paths.append(str(out_path))
            return True
        except Exception as e:
            log.warning("Docling failed to save table %s: %s", count, e, exc_info=False)
            return False

    def save_picture(el, count: int) -> bool:
        nonlocal picture_count, paths
        try:
            img = el.get_image(doc)
            if img is None:
                log.warning("Docling picture %s: get_image returned None", count)
                return False
            out_path = images_dir / f"picture_{count}.png"
            with out_path.open("wb") as fp:
                img.save(fp, "PNG")
            paths.append(str(out_path))
            return True
        except Exception as e:
            log.warning("Docling failed to save picture %s: %s", count, e, exc_info=False)
            return False

    saved_ids: set[int] = set()  # avoid saving same element twice

    def maybe_save_table(el) -> None:
        nonlocal table_count
        if id(el) in saved_ids:
            return
        table_count += 1
        if save_table(el, table_count):
            saved_ids.add(id(el))

    def maybe_save_picture(el) -> None:
        nonlocal picture_count
        if id(el) in saved_ids:
            return
        picture_count += 1
        if save_picture(el, picture_count):
            saved_ids.add(id(el))

    # Prefer doc.pictures / doc.tables when available (direct lists)
    pictures = getattr(doc, "pictures", None)
    if pictures is not None:
        for el in pictures:
            maybe_save_picture(el)
    tables = getattr(doc, "tables", None)
    if tables is not None:
        for el in tables:
            maybe_save_table(el)

    # Also walk iterate_items so we don't miss any (e.g. if .pictures/.tables are empty)
    for element, _level in doc.iterate_items():
        if _is_table(element):
            maybe_save_table(element)
        elif _is_picture(element):
            maybe_save_picture(element)

    return paths


class DoclingExtractor(Extractor):
    """OCR/document parsing via Docling. Outputs text, bbox, markdown, and extracted images."""

    def extract(self, pdf_path: str, output_dir: Path) -> dict:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if _HAS_PICTURE_EXPORT and PdfPipelineOptions is not None and PdfFormatOption is not None and InputFormat is not None:
            pipeline_options = PdfPipelineOptions()
            pipeline_options.generate_page_images = True
            pipeline_options.generate_picture_images = True
            pipeline_options.images_scale = 2.0
            converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
            )
        else:
            converter = DocumentConverter()
        conversion_result = converter.convert(pdf_path)
        doc = conversion_result.document

        full_text = doc.export_to_markdown() if hasattr(doc, "export_to_markdown") else str(doc)
        full_text_path = output_dir / "full_text.txt"
        full_text_path.write_text(full_text, encoding="utf-8")

        full_markdown_path = output_dir / "full_markdown.md"
        full_markdown_path.write_text(full_text, encoding="utf-8")

        image_paths = _save_docling_images(conversion_result, output_dir)

        pages_data = _docling_doc_to_pages_with_bbox(doc)
        if not pages_data or (len(pages_data) == 1 and not pages_data[0].get("blocks") and not pages_data[0].get("text")):
            if hasattr(doc, "pages") and doc.pages:
                for i, page in enumerate(doc.pages):
                    page_text = getattr(page, "text", None) or str(page)
                    if i < len(pages_data):
                        pages_data[i]["text"] = page_text
                        pages_data[i]["page"] = i
                    else:
                        pages_data.append({"page": i, "text": page_text, "blocks": []})
            else:
                pages_data = [{"page": 0, "text": full_text, "blocks": []}]

        json_path = output_dir / "pages.json"
        json_path.write_text(json.dumps(pages_data, indent=2), encoding="utf-8")

        artifacts = [str(full_text_path), str(full_markdown_path), str(json_path)] + image_paths

        result = ExtractionResult(
            run_type="ocr",
            sub_mechanism="docling",
            pdf_path=pdf_path,
            output_dir=str(output_dir),
            num_pages=len(pages_data),
            artifacts=artifacts,
        )
        return result.model_dump()
