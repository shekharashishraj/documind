"""Build layout-preserving LaTeX from Step 1 byte_extraction/pymupdf output."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# Relative path from reconstructed/original.tex to byte_extraction/pymupdf/images/
IMAGES_REL_PATH = "../../byte_extraction/pymupdf/images"

DUALLAYERBOX_MACRO = r"""
% --- latex-dual-layer macros (auto-generated) ---
\newlength{\dlboxwidth}
\newlength{\dlboxheight}
\newlength{\dlboxdepth}
\newcommand{\duallayerbox}[2]{%
  \begingroup
  \settowidth{\dlboxwidth}{\strut #1}%
  \settoheight{\dlboxheight}{\strut #1}%
  \settodepth{\dlboxdepth}{\strut #1}%
  \ifdim\dlboxwidth=0pt
    \settowidth{\dlboxwidth}{#2}%
  \fi
  \raisebox{0pt}[\dlboxheight][\dlboxdepth]{%
    \makebox[\dlboxwidth][l]{\resizebox{\dlboxwidth}{!}{\strut #2}}%
  }%
  \endgroup
}
% --- end latex-dual-layer macros ---
"""


def _escape_tex(s: str) -> str:
    """Escape LaTeX special characters."""
    if not s:
        return ""
    replacements = [
        ("\\", "\\textbackslash{}"),
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ]
    for a, b in replacements:
        s = s.replace(a, b)
    return s


def _load_pages(base_dir: Path) -> list[dict]:
    """Load pages.json from byte_extraction/pymupdf."""
    pymupdf_dir = base_dir / "byte_extraction" / "pymupdf"
    pages_path = pymupdf_dir / "pages.json"
    if not pages_path.is_file():
        raise FileNotFoundError(f"pages.json not found: {pages_path}")
    log.debug("Loading pages.json from %s", pages_path)
    raw = pages_path.read_text(encoding="utf-8")
    return json.loads(raw)


def _list_images_for_page(base_dir: Path, page_index: int) -> list[Path]:
    """List image files for a given page (page_N_img_*)."""
    images_dir = base_dir / "byte_extraction" / "pymupdf" / "images"
    if not images_dir.is_dir():
        return []
    out = []
    for p in sorted(images_dir.iterdir()):
        if p.suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
            continue
        if p.stem.startswith(f"page_{page_index}_img_"):
            out.append(p)
    return out


def _build_tex_content(base_dir: Path, pages: list[dict], include_duallayer_macro: bool = True) -> str:
    """Build full LaTeX document body from pages data."""
    parts = [
        r"\documentclass[11pt]{article}",
        r"\usepackage{graphicx}",
        r"\usepackage{geometry}",
        r"\geometry{margin=1in}",
    ]
    if include_duallayer_macro:
        parts.append(r"\usepackage{calc}")
        parts.append(r"\usepackage{xcolor}")
        parts.append("")
        parts.append(DUALLAYERBOX_MACRO)
    parts.append(r"\begin{document}")
    parts.append("")

    for page_idx, page_data in enumerate(pages):
        if page_idx > 0:
            parts.append(r"\newpage")
            parts.append("")
        blocks = page_data.get("blocks") or []
        image_paths = _list_images_for_page(base_dir, page_idx)
        image_index = 0
        for block in blocks:
            bbox = block.get("bbox")
            text = (block.get("text") or "").strip()
            block_type = block.get("type", 0)
            if block_type == 1 and image_index < len(image_paths):
                img_path = image_paths[image_index]
                rel = f"{IMAGES_REL_PATH}/{img_path.name}"
                w = ""
                if bbox and len(bbox) >= 4:
                    w_pt = bbox[2] - bbox[0]
                    w = f"width={w_pt}pt"
                parts.append(f"\\includegraphics[{w}]{{{rel}}}")
                parts.append("")
                image_index += 1
            elif text:
                escaped = _escape_tex(text)
                parts.append(escaped)
                parts.append("")
        if image_index < len(image_paths):
            for img_path in image_paths[image_index:]:
                rel = f"{IMAGES_REL_PATH}/{img_path.name}"
                parts.append(f"\\includegraphics{{{rel}}}")
                parts.append("")
        parts.append("")

    parts.append(r"\end{document}")
    return "\n".join(parts)


def _run_pdflatex(tex_path: Path, cwd: Path) -> bool:
    """Run pdflatex in cwd; return True if success."""
    exe = shutil.which("pdflatex")
    if not exe:
        log.warning("pdflatex not found in PATH; skipping PDF compilation")
        return False
    log.info("Running pdflatex in %s", cwd)
    try:
        subprocess.run(
            [exe, "-interaction=nonstopmode", tex_path.name],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        out_pdf = cwd / tex_path.with_suffix(".pdf").name
        if out_pdf.is_file():
            log.info("PDF compiled: %s", out_pdf)
            return True
        log.warning("pdflatex did not produce PDF")
        return False
    except subprocess.TimeoutExpired:
        log.error("pdflatex timed out")
        return False
    except Exception as e:
        log.exception("pdflatex failed: %s", e)
        return False


def run_reconstruct_latex(base_dir: str | Path) -> dict:
    """
    Build layout-preserving LaTeX from Step 1 byte_extraction/pymupdf output.

    Reads pages.json, full text, and images; writes <base_dir>/reconstructed/original.tex.
    Optionally compiles to PDF if pdflatex is available.

    Returns:
        dict with keys: output_tex_path (str), output_pdf_path (str | None), success (bool).
    """
    base_dir = Path(base_dir)
    out_dir = base_dir / "reconstructed"
    out_tex = out_dir / "original.tex"
    log.info("LaTeX reconstruction: base_dir=%s, output_tex=%s", base_dir, out_tex)

    pymupdf_dir = base_dir / "byte_extraction" / "pymupdf"
    if not pymupdf_dir.is_dir():
        log.error("Step 1 output not found: %s", pymupdf_dir)
        return {
            "output_tex_path": str(out_tex),
            "output_pdf_path": None,
            "success": False,
        }

    try:
        pages = _load_pages(base_dir)
        log.debug("Loaded %s pages", len(pages))
    except Exception as e:
        log.exception("Failed to load pages.json: %s", e)
        return {
            "output_tex_path": str(out_tex),
            "output_pdf_path": None,
            "success": False,
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    tex_content = _build_tex_content(base_dir, pages)
    try:
        out_tex.write_text(tex_content, encoding="utf-8")
        log.info("Wrote %s", out_tex)
    except Exception as e:
        log.exception("Failed to write .tex: %s", e)
        return {
            "output_tex_path": str(out_tex),
            "output_pdf_path": None,
            "success": False,
        }

    pdf_path = out_dir / "original.pdf"
    if _run_pdflatex(out_tex, out_dir):
        log.info("LaTeX reconstruction completed: tex=%s, pdf=%s", out_tex, pdf_path)
        return {
            "output_tex_path": str(out_tex),
            "output_pdf_path": str(pdf_path),
            "success": True,
        }
    log.info("LaTeX reconstruction completed (tex only): %s", out_tex)
    return {
        "output_tex_path": str(out_tex),
        "output_pdf_path": None,
        "success": True,
    }
