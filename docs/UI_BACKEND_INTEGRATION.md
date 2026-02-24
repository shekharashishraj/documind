# UI Backend Integration Notes

## Stack

- Frontend: HTML + CSS + JavaScript
- Backend: FastAPI
- Templates/static:
  - `apps/web/templates/index.html`
  - `apps/web/static/styles.css`
  - `apps/web/static/app.js`
- API app: `apps/web/main.py`

Run locally:

```bash
./venv/bin/uvicorn apps.web.main:app --reload --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## API Endpoints Used by Frontend

- `GET /api/health`
- `GET /api/metadata`
- `GET /api/pdfs?base_root=...`
- `GET /api/docs?base_root=...`
- `GET /api/doc/{doc_id}/status?base_root=...`
- `GET /api/doc/{doc_id}/scenario`
- `POST /api/pipeline/run`
- `GET /api/stage5/eligibility?base_dir=...&adv_pdf_override=...`
- `POST /api/stage5/doc`
- `POST /api/stage5/batch`
- `GET /api/runs/docs?base_root=...`
- `GET /api/runs/batch?out_dir=...`

## Backend Service Wiring

FastAPI handlers call `core/demo/service.py` wrappers:

- Stage 1: `run_stage1(...)`
- Stage 2: `run_stage2(...)`
- Stage 3: `run_stage3(...)`
- Stage 4: `run_stage4_with_mechanism(...)`
- Agent-backend eval (single): `run_stage5_doc_eval(...)` (internally calls `core/demo/agent_backend_eval.py`)
- Stage 5 batch: `run_stage5_batch_eval(...)`

## Evaluation Gating Logic

Frontend checks eligibility via `GET /api/stage5/eligibility`.

Evaluation is enabled if:

1. Clean baseline exists: `<doc_id>/byte_extraction/pymupdf/full_text.txt`
2. Adversarial PDF exists: `<doc_id>/stage4/final_overlay.pdf` (or override path)

## Attack Mechanism Selector

UI shows all mechanisms:

- `auto` (recommended; planner strategy decides mechanism)
- `visual_overlay`
- `hidden_text_injection`
- `font_glyph_remapping`

Current backend behavior:

- `auto`: follows planner semantic mapping (`append -> hidden_text_injection`, `update/delete -> visual_overlay or font_glyph_remapping`).
- `hidden_text_injection`: inserts hidden payload text from the Stage 3 plan.
- `visual_overlay`: applies replacements and full-page overlay.
- `font_glyph_remapping`: currently approximated via replacement+overlay fallback.

This keeps planner logic paper-aligned while preserving backward compatibility.

## Stage 2 / Stage 3 Model Defaults (Backend Controlled)

UI does not expose Stage 2 or Stage 3 model pickers.

Backend defaults are set in `apps/web/main.py`:

- `DOCUMIND_STAGE2_MODEL` (default `gpt-5-2025-08-07`)
- `DOCUMIND_STAGE3_MODEL` (default `gpt-5-2025-08-07`)

## Logging

Logging configured by `core/demo/logging_utils.py`.

- FastAPI/service log file: `logs/demo_web.log`
- Includes stage start/end/fail messages and API failures.

## Reviewer-facing Output Behavior

Single-document evaluation responses include machine output and human summary.

Frontend displays first:

- scenario label
- original behavior sentence
- adversarial behavior sentence
- changed targeted fields
- verdict sentence (`COMPROMISED`, `NOT COMPROMISED`, `BASELINE MISMATCH`)
- core failure metrics (`task deviation`, `resource inflation`, `tool misfire`)

Raw JSON is available in expandable technical details.
