from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ExtractionResult(BaseModel):
    """Summary of extraction for one run_type/sub_mechanism."""

    run_type: str
    sub_mechanism: str
    pdf_path: str
    output_dir: str
    num_pages: int = 0
    artifacts: list[str] = []
    extra: dict[str, Any] = {}
