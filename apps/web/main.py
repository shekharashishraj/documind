"""FastAPI app for reviewer-facing Documind demo UI (HTML/CSS/JS frontend)."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from core.demo.logging_utils import configure_demo_logging
from core.demo.service import (
    AGENT_BACKEND_AGENT_CATALOG,
    ATTACK_MECHANISMS,
    PIPELINE_RUN_ROOT,
    SCENARIO_CATALOG,
    SCENARIO_LABELS,
    check_stage5_eligibility,
    collect_stage5_doc_runs,
    get_doc_stage_status,
    get_scenario_for_doc,
    list_pdf_candidates,
    list_processed_doc_dirs,
    list_stage5_batch_reports,
    load_default_demo_doc_ids,
    prepare_stage5_uploaded_docs,
    run_stage1,
    run_stage2,
    run_stage3,
    run_stage4_with_mechanism,
    run_stage5_batch_eval,
    run_stage5_doc_eval,
    summarize_doc_run_for_humans,
)

logger = configure_demo_logging("logs/demo_web.log")
log = logging.getLogger("documind.demo.api")

ROOT_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(ROOT_DIR / "templates"))
DEFAULT_STAGE2_MODEL = os.environ.get("DOCUMIND_STAGE2_MODEL", "gpt-5-2025-08-07")
DEFAULT_STAGE3_MODEL = os.environ.get("DOCUMIND_STAGE3_MODEL", "gpt-5-2025-08-07")

app = FastAPI(title="Documind Vulnerability Evaluation API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(ROOT_DIR / "static")), name="static")


class PipelineRunRequest(BaseModel):
    pdf_path: str
    out_root: str = str(PIPELINE_RUN_ROOT)
    run_types: list[str] = Field(default_factory=lambda: ["byte_extraction"])
    stage2_model: str = DEFAULT_STAGE2_MODEL
    stage3_model: str = DEFAULT_STAGE3_MODEL
    attack_mechanism: str = "auto"
    priority_filter: str = "all"


class PipelineStage1Request(BaseModel):
    pdf_path: str
    out_root: str = str(PIPELINE_RUN_ROOT)
    run_types: list[str] = Field(default_factory=lambda: ["byte_extraction"])


class PipelineStage2Request(BaseModel):
    base_dir: str
    stage2_model: str = DEFAULT_STAGE2_MODEL


class PipelineStage3Request(BaseModel):
    base_dir: str
    stage3_model: str = DEFAULT_STAGE3_MODEL


class PipelineStage4Request(BaseModel):
    base_dir: str
    source_pdf_path: str
    attack_mechanism: str = "auto"
    priority_filter: str = "all"


class Stage5DocRequest(BaseModel):
    base_dir: str
    scenario: str = "auto"
    adv_pdf: str | None = None
    model: str = "gpt-4o"
    trials: int = Field(default=3, ge=1, le=9)
    out_subdir: str = "agent_backend_eval"


class Stage5BatchRequest(BaseModel):
    base_root: str = str(PIPELINE_RUN_ROOT)
    doc_ids: list[str] | None = None
    model: str = "gpt-5-2025-08-07"
    trials: int = Field(default=3, ge=1, le=9)
    out_dir: str = "stage5_runs"


def _require_openai_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY is not set in environment.")
    return key


def _stage_to_dict(stage_obj: Any) -> dict[str, Any]:
    return {
        "stage": getattr(stage_obj, "stage", "unknown"),
        "status": getattr(stage_obj, "status", "unknown"),
        "message": getattr(stage_obj, "message", ""),
        "artifacts": list(getattr(stage_obj, "artifacts", []) or []),
    }


def _normalize_run_types(run_types: list[str] | None) -> list[str]:
    final = list(run_types or ["byte_extraction"])
    if "byte_extraction" not in final:
        final.append("byte_extraction")
    return final


def _resolve_local_file(path_text: str) -> Path:
    raw = Path(path_text).expanduser()
    target = raw if raw.is_absolute() else (Path.cwd() / raw)
    return target.resolve()


def _require_pdf_upload(upload: Any, label: str) -> None:
    filename = (upload.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail=f"{label} filename is missing.")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail=f"{label} must be a PDF file.")


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/metadata")
def metadata() -> dict[str, Any]:
    return {
        "attack_mechanisms": ATTACK_MECHANISMS,
        "scenario_labels": SCENARIO_LABELS,
        "scenario_catalog": SCENARIO_CATALOG,
        "agent_backend_agents": AGENT_BACKEND_AGENT_CATALOG,
        "pipeline_run_root": str(PIPELINE_RUN_ROOT),
        "default_demo_doc_ids": load_default_demo_doc_ids(),
    }


@app.get("/api/pdfs")
def pdf_candidates(base_root: str = Query(".")) -> dict[str, Any]:
    try:
        pdfs = list_pdf_candidates(base_root)
        return {"items": pdfs, "count": len(pdfs)}
    except Exception as exc:
        log.exception("Failed listing PDFs: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/docs")
def docs(base_root: str = Query(str(PIPELINE_RUN_ROOT))) -> dict[str, Any]:
    try:
        items = []
        for doc_dir in list_processed_doc_dirs(base_root):
            doc_id = doc_dir.name
            spec = get_scenario_for_doc(doc_id)
            items.append(
                {
                    "doc_id": doc_id,
                    "base_dir": str(doc_dir.resolve()),
                    "stage_status": get_doc_stage_status(doc_dir),
                    "scenario": spec,
                }
            )
        return {"items": items, "count": len(items)}
    except Exception as exc:
        log.exception("Failed listing docs: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/doc/{doc_id}/status")
def doc_status(doc_id: str, base_root: str = Query(str(PIPELINE_RUN_ROOT))) -> dict[str, Any]:
    base_dir = Path(base_root) / doc_id
    if not base_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Document directory not found: {base_dir}")
    return {
        "doc_id": doc_id,
        "base_dir": str(base_dir.resolve()),
        "stage_status": get_doc_stage_status(base_dir),
    }


@app.get("/api/doc/{doc_id}/scenario")
def doc_scenario(doc_id: str) -> dict[str, Any]:
    spec = get_scenario_for_doc(doc_id)
    if not spec:
        raise HTTPException(status_code=404, detail=f"No scenario spec found for doc_id={doc_id}")
    return {"doc_id": doc_id, "scenario": spec}


@app.post("/api/pipeline/run")
def run_pipeline(payload: PipelineRunRequest) -> dict[str, Any]:
    api_key = _require_openai_api_key()
    try:
        pdf_path = Path(payload.pdf_path)
        if not pdf_path.is_file():
            raise HTTPException(status_code=400, detail=f"PDF not found: {pdf_path}")

        run_types = _normalize_run_types(payload.run_types)

        base_dir, stage1 = run_stage1(pdf_path=pdf_path, out_root=payload.out_root, run_types=run_types)
        stage2 = run_stage2(base_dir=base_dir, model=payload.stage2_model, api_key=api_key)
        stage3 = run_stage3(base_dir=base_dir, model=payload.stage3_model, api_key=api_key)
        stage4 = run_stage4_with_mechanism(
            base_dir=base_dir,
            source_pdf_path=pdf_path,
            attack_mechanism=payload.attack_mechanism,
            priority_filter=None if payload.priority_filter == "all" else payload.priority_filter,
        )

        return {
            "doc_id": base_dir.name,
            "base_dir": str(base_dir.resolve()),
            "run_root": str(base_dir.parent.resolve()),
            "stages": [_stage_to_dict(stage1), _stage_to_dict(stage2), _stage_to_dict(stage3), _stage_to_dict(stage4)],
            "stage_status": get_doc_stage_status(base_dir),
        }
    except HTTPException:
        raise
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.exception("Pipeline run failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/pipeline/stage1")
def run_pipeline_stage1(payload: PipelineStage1Request) -> dict[str, Any]:
    try:
        pdf_path = Path(payload.pdf_path)
        if not pdf_path.is_file():
            raise HTTPException(status_code=400, detail=f"PDF not found: {pdf_path}")

        run_types = _normalize_run_types(payload.run_types)
        base_dir, stage1 = run_stage1(pdf_path=pdf_path, out_root=payload.out_root, run_types=run_types)
        return {
            "doc_id": base_dir.name,
            "base_dir": str(base_dir.resolve()),
            "run_root": str(base_dir.parent.resolve()),
            "source_pdf_path": str(pdf_path.resolve()),
            "stage": _stage_to_dict(stage1),
            "stage_status": get_doc_stage_status(base_dir),
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Pipeline stage1 failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/pipeline/stage2")
def run_pipeline_stage2(payload: PipelineStage2Request) -> dict[str, Any]:
    api_key = _require_openai_api_key()
    try:
        base_dir = Path(payload.base_dir)
        if not base_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"Base directory not found: {base_dir}")
        stage2 = run_stage2(base_dir=base_dir, model=payload.stage2_model, api_key=api_key)
        return {
            "doc_id": base_dir.name,
            "base_dir": str(base_dir.resolve()),
            "stage": _stage_to_dict(stage2),
            "stage_status": get_doc_stage_status(base_dir),
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Pipeline stage2 failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/pipeline/stage3")
def run_pipeline_stage3(payload: PipelineStage3Request) -> dict[str, Any]:
    api_key = _require_openai_api_key()
    try:
        base_dir = Path(payload.base_dir)
        if not base_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"Base directory not found: {base_dir}")
        stage3 = run_stage3(base_dir=base_dir, model=payload.stage3_model, api_key=api_key)
        return {
            "doc_id": base_dir.name,
            "base_dir": str(base_dir.resolve()),
            "stage": _stage_to_dict(stage3),
            "stage_status": get_doc_stage_status(base_dir),
        }
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Pipeline stage3 failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/pipeline/stage4")
def run_pipeline_stage4(payload: PipelineStage4Request) -> dict[str, Any]:
    try:
        base_dir = Path(payload.base_dir)
        source_pdf_path = Path(payload.source_pdf_path)
        if not base_dir.is_dir():
            raise HTTPException(status_code=400, detail=f"Base directory not found: {base_dir}")
        if not source_pdf_path.is_file():
            raise HTTPException(status_code=400, detail=f"Source PDF not found: {source_pdf_path}")

        stage4 = run_stage4_with_mechanism(
            base_dir=base_dir,
            source_pdf_path=source_pdf_path,
            attack_mechanism=payload.attack_mechanism,
            priority_filter=None if payload.priority_filter == "all" else payload.priority_filter,
        )
        final_overlay = base_dir / "stage4" / "final_overlay.pdf"
        original_for_preview = base_dir / "original.pdf"
        return {
            "doc_id": base_dir.name,
            "base_dir": str(base_dir.resolve()),
            "source_pdf_path": str(source_pdf_path.resolve()),
            "preview_original_pdf": str(original_for_preview.resolve() if original_for_preview.is_file() else source_pdf_path.resolve()),
            "preview_adversarial_pdf": str(final_overlay.resolve()) if final_overlay.is_file() else None,
            "stage": _stage_to_dict(stage4),
            "stage_status": get_doc_stage_status(base_dir),
        }
    except HTTPException:
        raise
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.exception("Pipeline stage4 failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/files/preview")
def preview_file(path: str = Query(...)) -> FileResponse:
    try:
        target = _resolve_local_file(path)
        if not target.is_file():
            raise HTTPException(status_code=404, detail=f"File not found: {target}")
        if target.suffix.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="Only PDF preview is supported.")
        return FileResponse(
            path=target,
            media_type="application/pdf",
            filename=target.name,
            headers={"Content-Disposition": f'inline; filename="{target.name}"'},
        )
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Failed to preview file '%s': %s", path, exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stage5/eligibility")
def stage5_eligibility(base_dir: str = Query(...), adv_pdf_override: str | None = Query(default=None)) -> dict[str, Any]:
    try:
        target = Path(base_dir)
        eligible, missing = check_stage5_eligibility(target, adv_pdf_override)
        return {
            "base_dir": str(target.resolve()),
            "eligible": eligible,
            "missing": missing,
        }
    except Exception as exc:
        log.exception("Stage 5 eligibility check failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/stage5/prepare-upload")
async def stage5_prepare_upload(
    request: Request,
) -> dict[str, Any]:
    incoming_root = Path(".stage5_uploads") / "_incoming"
    incoming_root.mkdir(parents=True, exist_ok=True)
    request_id = uuid.uuid4().hex
    original_tmp = incoming_root / f"{request_id}_original.pdf"
    adversarial_tmp = incoming_root / f"{request_id}_adversarial.pdf"
    original_pdf = None
    adversarial_pdf = None

    try:
        try:
            form = await request.form()
        except Exception as exc:
            detail = str(exc)
            if "python-multipart" in detail.lower() or "multipart" in detail.lower():
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "File upload support requires 'python-multipart' in the active environment. "
                        "Install it with './venv/bin/python -m pip install python-multipart' and restart the web server."
                    ),
                ) from exc
            raise

        scenario = str(form.get("scenario") or "").strip()
        if not scenario:
            raise HTTPException(status_code=400, detail="Scenario is required.")

        original_pdf = form.get("original_pdf")
        adversarial_pdf = form.get("adversarial_pdf")
        if original_pdf is None:
            raise HTTPException(status_code=400, detail="Original document upload is required.")
        if adversarial_pdf is None:
            raise HTTPException(status_code=400, detail="Adversarial document upload is required.")

        _require_pdf_upload(original_pdf, "Original document")
        _require_pdf_upload(adversarial_pdf, "Adversarial document")

        original_bytes = await original_pdf.read()
        adversarial_bytes = await adversarial_pdf.read()
        if not original_bytes:
            raise HTTPException(status_code=400, detail="Original document is empty.")
        if not adversarial_bytes:
            raise HTTPException(status_code=400, detail="Adversarial document is empty.")

        original_tmp.write_bytes(original_bytes)
        adversarial_tmp.write_bytes(adversarial_bytes)

        return prepare_stage5_uploaded_docs(
            scenario=scenario,
            original_pdf_path=original_tmp,
            adversarial_pdf_path=adversarial_tmp,
            upload_root=".stage5_uploads",
        )
    except HTTPException:
        raise
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.exception("Stage 5 upload preparation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        try:
            if original_pdf is not None:
                await original_pdf.close()
        except Exception:
            pass
        try:
            if adversarial_pdf is not None:
                await adversarial_pdf.close()
        except Exception:
            pass
        for tmp in [original_tmp, adversarial_tmp]:
            try:
                if tmp.exists():
                    tmp.unlink()
            except Exception:
                pass


@app.post("/api/stage5/doc")
def stage5_doc(payload: Stage5DocRequest) -> dict[str, Any]:
    api_key = _require_openai_api_key()
    try:
        base_dir = Path(payload.base_dir)
        result = run_stage5_doc_eval(
            base_dir=base_dir,
            scenario=payload.scenario,
            adv_pdf=payload.adv_pdf,
            model=payload.model,
            trials=payload.trials,
            out_subdir=payload.out_subdir,
            api_key=api_key,
        )
        human_summary = summarize_doc_run_for_humans(result.get("doc_result") or {})
        return {
            "result": result,
            "human_summary": human_summary,
        }
    except Exception as exc:
        log.exception("Stage 5 doc evaluation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/stage5/batch")
def stage5_batch(payload: Stage5BatchRequest) -> dict[str, Any]:
    api_key = _require_openai_api_key()
    try:
        result = run_stage5_batch_eval(
            base_root=payload.base_root,
            doc_ids=payload.doc_ids,
            model=payload.model,
            trials=payload.trials,
            out_dir=payload.out_dir,
            api_key=api_key,
        )
        batch = result.get("batch_result") or {}
        summary = {
            "successful_compromises": batch.get("successful_attacks", 0),
            "eligible_docs": batch.get("eligible_docs", 0),
            "attack_success_rate": batch.get("attack_success_rate", 0.0),
            "decision_flip_rate": batch.get("decision_flip_rate", 0.0),
            "tool_parameter_corruption_rate": batch.get("tool_parameter_corruption_rate", 0.0),
            "severity_weighted_vulnerability_score": batch.get("severity_weighted_vulnerability_score", 0.0),
        }
        return {"result": result, "batch_summary": summary}
    except Exception as exc:
        log.exception("Stage 5 batch evaluation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/runs/docs")
def runs_docs(base_root: str = Query(str(PIPELINE_RUN_ROOT))) -> dict[str, Any]:
    try:
        rows = collect_stage5_doc_runs(base_root)
        return {"items": rows, "count": len(rows)}
    except Exception as exc:
        log.exception("Failed loading doc runs: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/runs/batch")
def runs_batch(out_dir: str = Query("stage5_runs")) -> dict[str, Any]:
    try:
        rows = list_stage5_batch_reports(out_dir)
        return {"items": rows, "count": len(rows)}
    except Exception as exc:
        log.exception("Failed loading batch reports: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
