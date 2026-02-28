"""Stage 4: Execute manipulation plan - inject attacks into PDF."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from core.stage4.image_injector import apply_image_attack
from core.stage4.structural_injector import apply_structural_attack
from core.stage4.text_injector import apply_text_attack

log = logging.getLogger(__name__)


def _load_source_metadata(base_dir: Path) -> dict[str, Any]:
    """Load source_metadata.json to find original PDF path."""
    metadata_path = base_dir / "source_metadata.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(
            f"source_metadata.json not found at {metadata_path}. "
            "Run Step 1 extraction first or use --pdf to specify PDF path."
        )
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _load_manipulation_plan(base_dir: Path) -> dict[str, Any]:
    """Load Stage 3 manipulation plan."""
    plan_path = base_dir / "stage3" / "openai" / "manipulation_plan.json"
    if not plan_path.is_file():
        raise FileNotFoundError(
            f"Stage 3 output not found: {plan_path}. Run stage3 first."
        )
    return json.loads(plan_path.read_text(encoding="utf-8"))


def _load_pages_json(base_dir: Path) -> list[dict[str, Any]]:
    """Load pages.json for document structure reference."""
    pages_path = base_dir / "byte_extraction" / "pymupdf" / "pages.json"
    if not pages_path.is_file():
        log.warning("pages.json not found at %s", pages_path)
        return []
    return json.loads(pages_path.read_text(encoding="utf-8"))


def _normalize_plan(plan: dict[str, Any]) -> dict[str, list]:
    """
    Normalize manipulation plan to consistent format.

    Handles both old format (manipulation_plan array) and new format
    (text_attacks, image_attacks, structural_attacks arrays).
    """
    # New format: already has text_attacks, image_attacks, structural_attacks
    if "text_attacks" in plan or "image_attacks" in plan or "structural_attacks" in plan:
        return {
            "text_attacks": plan.get("text_attacks", []),
            "image_attacks": plan.get("image_attacks", []),
            "structural_attacks": plan.get("structural_attacks", []),
            "document_threat_model": plan.get("document_threat_model", {}),
            "defense_considerations": plan.get("defense_considerations", {}),
        }

    # Old format: manipulation_plan array with 'what' field
    if "manipulation_plan" in plan:
        text_attacks = []
        image_attacks = []
        structural_attacks = []

        for idx, item in enumerate(plan["manipulation_plan"]):
            what = item.get("what", "")
            attack_base = {
                "attack_id": f"L{idx + 1}",  # Legacy ID
                "target": item.get("where", {}),
                "payload_description": item.get("rationale", ""),
                "priority": item.get("priority", "medium"),
                "effects_downstream": item.get("effects_downstream", ""),
            }

            if what in ("text_block", "header_footer", "metadata"):
                attack_base["technique"] = "invisible_text_injection"
                attack_base["injection_strategy"] = "modification"
                text_attacks.append(attack_base)
            elif what == "image":
                attack_base["technique"] = "image_replacement"
                image_attacks.append(attack_base)
            elif what == "structure":
                attack_base["technique"] = "annotation_overlay"
                structural_attacks.append(attack_base)

        return {
            "text_attacks": text_attacks,
            "image_attacks": image_attacks,
            "structural_attacks": structural_attacks,
            "document_threat_model": {},
            "defense_considerations": {},
        }

    # Empty plan
    return {
        "text_attacks": [],
        "image_attacks": [],
        "structural_attacks": [],
        "document_threat_model": {},
        "defense_considerations": {},
    }


def run_stage4_executor(
    base_dir: str | Path,
    *,
    pdf_path: str | Path | None = None,
    output_name: str = "injected.pdf",
) -> dict[str, Any]:
    """
    Execute Stage 4: apply manipulation plan to PDF.

    Reads:
    - stage3/openai/manipulation_plan.json
    - byte_extraction/pymupdf/pages.json
    - source_metadata.json (or pdf_path override)

    Writes:
    - stage4/injected.pdf
    - stage4/execution_report.json

    Returns dict with output_path, attacks_applied, attacks_failed, attacks_skipped.
    """
    base_dir = Path(base_dir)

    # Load manipulation plan
    raw_plan = _load_manipulation_plan(base_dir)
    plan = _normalize_plan(raw_plan)

    # Load pages.json for structure reference
    pages_json = _load_pages_json(base_dir)

    # Determine PDF path
    if pdf_path is None:
        metadata = _load_source_metadata(base_dir)
        pdf_path = metadata.get("source_pdf")
        if not pdf_path:
            raise ValueError("No source_pdf in source_metadata.json and no --pdf provided")

    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    log.info("Stage 4: Opening PDF %s", pdf_path)
    doc = fitz.open(str(pdf_path))

    # Execution tracking
    text_results = []
    image_results = []
    structural_results = []

    applied = 0
    failed = 0
    skipped = 0

    # Apply text attacks
    for attack in plan["text_attacks"]:
        attack_id = attack.get("attack_id", "?")
        technique = attack.get("technique", "unknown")
        log.info("Stage 4: applying text attack %s (%s)", attack_id, technique)
        try:
            result, updated_doc = apply_text_attack(doc, attack, pages_json)
            text_results.append(result)
            if updated_doc is not doc:
                doc.close()
                doc = updated_doc
            if result.get("status") == "success":
                applied += 1
            elif result.get("status") == "failed":
                failed += 1
            else:
                skipped += 1
            log.info(
                "Stage 4: text attack %s status=%s",
                attack_id,
                result.get("status", "unknown"),
            )
        except Exception as e:
            log.error("Text attack %s failed: %s", attack.get("attack_id", "?"), e)
            text_results.append({
                "attack_id": attack.get("attack_id", "unknown"),
                "technique": attack.get("technique", "unknown"),
                "status": "failed",
                "error": str(e),
            })
            failed += 1

    # Apply structural attacks
    for attack in plan["structural_attacks"]:
        attack_id = attack.get("attack_id", "?")
        technique = attack.get("technique", "unknown")
        log.info("Stage 4: applying structural attack %s (%s)", attack_id, technique)
        try:
            result = apply_structural_attack(doc, attack)
            structural_results.append(result)
            if result.get("status") == "success":
                applied += 1
            elif result.get("status") == "failed":
                failed += 1
            else:
                skipped += 1
            log.info(
                "Stage 4: structural attack %s status=%s",
                attack_id,
                result.get("status", "unknown"),
            )
        except Exception as e:
            log.error("Structural attack %s failed: %s", attack.get("attack_id", "?"), e)
            structural_results.append({
                "attack_id": attack.get("attack_id", "unknown"),
                "technique": attack.get("technique", "unknown"),
                "status": "failed",
                "error": str(e),
            })
            failed += 1

    # Apply image attacks (stub - all will be skipped)
    for attack in plan["image_attacks"]:
        attack_id = attack.get("attack_id", "?")
        technique = attack.get("technique", "unknown")
        log.info("Stage 4: applying image attack %s (%s)", attack_id, technique)
        result = apply_image_attack(doc, attack)
        image_results.append(result)
        skipped += 1
        log.info("Stage 4: image attack %s status=%s", attack_id, result.get("status", "skipped"))

    # Save modified PDF
    out_dir = base_dir / "stage4"
    out_dir.mkdir(parents=True, exist_ok=True)
    output_pdf_path = out_dir / output_name
    doc.save(str(output_pdf_path))
    doc.close()
    log.info("Stage 4: Saved injected PDF to %s", output_pdf_path)

    # Build execution report
    total_attacks = len(plan["text_attacks"]) + len(plan["image_attacks"]) + len(plan["structural_attacks"])

    report = {
        "input_pdf": str(pdf_path),
        "output_pdf": str(output_pdf_path),
        "timestamp": datetime.utcnow().isoformat(),
        "summary": {
            "total_attacks": total_attacks,
            "applied": applied,
            "failed": failed,
            "skipped": skipped,
        },
        "document_threat_model": plan.get("document_threat_model", {}),
        "text_attacks": text_results,
        "image_attacks": image_results,
        "structural_attacks": structural_results,
        "defense_considerations": plan.get("defense_considerations", {}),
    }

    report_path = out_dir / "execution_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info("Stage 4: Wrote execution report to %s", report_path)

    return {
        "output_path": str(output_pdf_path),
        "report_path": str(report_path),
        "attacks_applied": applied,
        "attacks_failed": failed,
        "attacks_skipped": skipped,
        "report": report,
    }
