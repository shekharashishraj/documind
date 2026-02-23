"""Test Stage 4 visible executor output creation and page-count integrity."""

import tempfile
from pathlib import Path

import pytest

from core.stage4.visible_executor import annotate_pdf


def test_annotate_creates_file_and_pagecount_matches():
    """Test that annotate_pdf creates an output file with the same page count."""
    # Find test.pdf
    test_pdf = Path("test.pdf")
    if not test_pdf.exists():
        pytest.skip("test.pdf not found in repo root")

    # Find a manipulation_plan.json
    import glob
    plan_files = glob.glob("**/stage3/openai/manipulation_plan.json", recursive=True)
    if not plan_files:
        pytest.skip("No stage3/openai/manipulation_plan.json found")
    
    plan_file = plan_files[0]

    # Create temporary output file
    with tempfile.TemporaryDirectory() as tmpdir:
        output_pdf = Path(tmpdir) / "annotated.pdf"

        # Call annotate_pdf
        annotate_pdf(str(test_pdf), plan_file, str(output_pdf))

        # Verify output file exists and is non-empty
        assert output_pdf.exists(), "Output PDF was not created"
        assert output_pdf.stat().st_size > 100, "Output PDF is too small"

        # Verify page count matches using PyMuPDF
        import fitz

        original_doc = fitz.open(str(test_pdf))
        output_doc = fitz.open(str(output_pdf))

        assert (
            output_doc.page_count == original_doc.page_count
        ), "Page count mismatch between original and output"

        original_doc.close()
        output_doc.close()
