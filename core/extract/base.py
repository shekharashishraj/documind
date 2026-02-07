from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class Extractor(ABC):
    """Common interface for PDF extraction (byte, OCR, VLM)."""

    @abstractmethod
    def extract(self, pdf_path: str, output_dir: Path) -> dict[str, Any]:
        """Extract content from PDF and write artifacts under output_dir. Returns summary dict."""
        raise NotImplementedError
