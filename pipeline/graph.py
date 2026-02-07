"""LangGraph pipeline: parse PDF with byte_extraction, ocr, and vlm mechanisms."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from core.extract.docling_extractor import DoclingExtractor
from core.extract.mistral_extractor import MistralExtractor
from core.extract.pymupdf_extractor import PyMuPDFExtractor
from core.extract.tesseract_extractor import TesseractExtractor


def _run_type_key(run_type: str, sub_mechanism: str) -> str:
    return f"{run_type}/{sub_mechanism}"


def parse_pdf_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run all extractors and write under base_dir/run_type/sub_mechanism."""
    pdf_path = state["pdf_path"]
    base_dir = Path(state["base_dir"])
    run_types = state.get("run_types") or ["byte_extraction", "ocr", "vlm"]
    results: dict[str, dict] = state.get("results") or {}

    # Byte-extraction: pymupdf
    if "byte_extraction" in run_types:
        out_pymupdf = base_dir / "byte_extraction" / "pymupdf"
        ext = PyMuPDFExtractor()
        results[_run_type_key("byte_extraction", "pymupdf")] = ext.extract(pdf_path, out_pymupdf)

    # OCR: tesseract, docling
    if "ocr" in run_types:
        out_tesseract = base_dir / "ocr" / "tesseract"
        ext_t = TesseractExtractor()
        results[_run_type_key("ocr", "tesseract")] = ext_t.extract(pdf_path, out_tesseract)

        out_docling = base_dir / "ocr" / "docling"
        ext_d = DoclingExtractor()
        results[_run_type_key("ocr", "docling")] = ext_d.extract(pdf_path, out_docling)

    # VLM: mistral
    if "vlm" in run_types:
        out_mistral = base_dir / "vlm" / "mistral"
        ext_m = MistralExtractor()
        results[_run_type_key("vlm", "mistral")] = ext_m.extract(pdf_path, out_mistral)

    return {"results": results}


def build_parse_graph():
    """Build and return compiled LangGraph for PDF parsing."""
    workflow = StateGraph(dict)

    workflow.add_node("parse_pdf", parse_pdf_node)
    workflow.set_entry_point("parse_pdf")
    workflow.add_edge("parse_pdf", END)

    return workflow.compile()


def run_parse_pdf(
    pdf_path: str,
    base_dir: str | Path,
    run_types: list[Literal["byte_extraction", "ocr", "vlm"]] | None = None,
) -> dict[str, Any]:
    """Run the parse-PDF pipeline and return state with results."""
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    run_types = run_types or ["byte_extraction", "ocr", "vlm"]
    graph = build_parse_graph()
    initial = {
        "pdf_path": pdf_path,
        "base_dir": str(base_dir),
        "run_types": run_types,
        "results": {},
    }
    final = graph.invoke(initial)
    return final
