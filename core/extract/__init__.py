from core.extract.base import Extractor
from core.extract.pymupdf_extractor import PyMuPDFExtractor

try:
    from core.extract.tesseract_extractor import TesseractExtractor
except Exception:  # pragma: no cover - optional dependency
    TesseractExtractor = None  # type: ignore[assignment]

try:
    from core.extract.docling_extractor import DoclingExtractor
except Exception:  # pragma: no cover - optional dependency
    DoclingExtractor = None  # type: ignore[assignment]

try:
    from core.extract.mistral_extractor import MistralExtractor
except Exception:  # pragma: no cover - optional dependency
    MistralExtractor = None  # type: ignore[assignment]

__all__ = [
    "Extractor",
    "PyMuPDFExtractor",
    "TesseractExtractor",
    "DoclingExtractor",
    "MistralExtractor",
]
