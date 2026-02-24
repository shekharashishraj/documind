"""Stage 4: injection and image overlay."""

from pathlib import Path

from core.stage4.injector import run_injection
from core.stage4.overlay import apply_overlay

__all__ = ["run_injection", "apply_overlay", "run_stage4"]


def run_stage4(
    base_dir: str | Path,
    *,
    original_pdf_path: str | Path | None = None,
    apply_overlay_flag: bool = True,
    priority_filter: str | None = None,
    mechanism_mode: str = "auto",
) -> dict:
    """
    Run Stage 4: injection (direct PDF modification) then optional full-page image overlay.
    mechanism_mode:
      - "auto": follow planner semantic strategy mapping
      - "visual_overlay" | "hidden_text_injection" | "font_glyph_remapping": force channel

    Returns dict with perturbed_pdf_path, final_pdf_path (if overlay), replacements, replacement_stats, error.
    """
    base_dir = Path(base_dir)
    result = run_injection(
        base_dir,
        original_pdf_path=original_pdf_path,
        priority_filter=priority_filter,
        mechanism_mode=mechanism_mode,
    )
    if result.get("error"):
        return result
    perturbed = result.get("perturbed_pdf_path")
    if not perturbed or not apply_overlay_flag:
        result["final_pdf_path"] = None
        return result
    original = Path(original_pdf_path) if original_pdf_path else base_dir / "original.pdf"
    if not original.is_file():
        result["error"] = "original.pdf not found in base_dir; pass --original-pdf or run with run --stage4 to copy it."
        result["final_pdf_path"] = None
        return result
    out_pdf = base_dir / "stage4" / "final_overlay.pdf"
    mappings = [{"original": r.get("search_key"), "replacement": r.get("replacement")} for r in result.get("replacements", [])]
    if apply_overlay(base_dir, original, Path(perturbed), out_pdf, mappings):
        result["final_pdf_path"] = str(out_pdf)
    else:
        result["final_pdf_path"] = None
        result["error"] = result.get("error") or "Overlay failed"
    return result
