![MALDOC logo](docs/assets/img/logo.png)

# MALDOC: A Modular Red-Teaming Platform for Document Processing AI Agents

[Project Page](https://shekharashishraj.github.io/MalDoc/) · [Paper](docs/assets/maldoc_paper.pdf) · [Demo](https://maldoc-demo.anonymous-acl.org) · [Video](https://www.youtube.com/watch?v=OLKtiIROjWw) · [Code](https://github.com/shekharashishraj/MalDoc)

**Authors:** Ashish Raj Shekhar*, Priyanuj Bordoloi*, Shiven Agarwal*, Yash Shah, Sandipan De, Vivek Gupta  
**Affiliation:** Arizona State University · *Equal contribution*

## Overview

Document-processing AI agents can be compromised by attacks that exploit discrepancies between rendered PDF content and machine-readable representations. MALDOC is a modular red-teaming system that generates document-layer adversarial PDFs and measures how failures propagate through agent workflows.

Evaluated against GPT-4o, Claude Sonnet, and Grok on finance, healthcare, and education documents, MALDOC induces **72% task degradation** while preserving human-visible fidelity.

## Key Results

- **Attack Success Rate (ASR): 86%** under the default planner.
- **72%** of successful attacks are driven by task degradation.
- **74.5%** of successes involve structured workflow deviation (Tool Misfire or state drift).
- **97%** of document pairs show no visible differences in a human spot-check.

## Figures

**System Overview (Figure 1)**

![MALDOC system overview](docs/assets/img/figure-1.png)

**Demo Walkthrough (Figure 2)**

<table>
  <tr>
    <td><img src="docs/assets/img/demo-home-left.png" alt="Demo: creation view" /></td>
    <td><img src="docs/assets/img/demo-home-right.png" alt="Demo: stage timeline view" /></td>
  </tr>
  <tr>
    <td><img src="docs/assets/img/demo-eval-left.png" alt="Demo: evaluation setup" /></td>
    <td><img src="docs/assets/img/demo-eval-right.png" alt="Demo: propagation metrics" /></td>
  </tr>
</table>

**Selected Tables**

<table>
  <tr>
    <td><img src="docs/assets/img/table-1.png" alt="Table 1: HTI/FGR/VOI evaluation" /></td>
    <td><img src="docs/assets/img/table-2.png" alt="Table 2: Planner-agnostic ASR" /></td>
  </tr>
  <tr>
    <td><img src="docs/assets/img/table-3.png" alt="Table 3: Stealthiness evaluation" /></td>
    <td><img src="docs/assets/img/table-4.png" alt="Table 4: Strategy to injection channel mapping" /></td>
  </tr>
</table>

---

## Technical Documentation

A multi-stage PDF parsing and analysis pipeline:

- **Step 1**: Extract text, layout (bounding boxes), markdown, and images from PDFs using byte-extraction (PyMuPDF), OCR (Tesseract, Docling), and VLM (Mistral). Orchestrated with LangGraph.
- **Stage 2**: Send the byte-extraction outputs plus extracted images to an MLLM (OpenAI GPT) to produce a **vulnerability-focused analysis**: document semantics plus attack surface mapping (exactly 3 sensitive elements with `value_to_replace` and `related_elements`, injectable regions, links, risk profile).
- **Stage 3**: Use Stage 2 analysis and Step 1 structure to produce an **attack-ready manipulation plan**: text/image/structural attacks with paper-aligned `semantic_edit_strategy` (`append|update|delete`) and `injection_mechanism`, plus `scope`, `search_key`, `replacement`, and `consistency_note`. Planning only; no injection is performed.
- **Stage 4**: Execute Stage 3 plan via direct PDF manipulation (replacements + hidden-text insertions) and optional visual overlay. In `auto` mode, mechanism selection follows paper mapping (`append -> hidden_text_injection`, `update/delete -> visual_overlay|font_glyph_remapping`). Writes `stage4/perturbed.pdf`, `stage4/replacements.json`, `stage4/hidden_text.json`, and `stage4/final_overlay.pdf`.
- **Stage 5**: Run post-Stage-4 agentic vulnerability simulation on clean vs adversarial documents using LLM agents + deterministic mock tools, with 3-trial majority scoring and batch metrics/reporting.

Output is written under **one folder per PDF** (named by the PDF stem), with subfolders per run type and, optionally, Stage 2, Stage 3, Stage 4, and Stage 5 results.

---

## Table of contents

- [Overview](#overview)
- [Key Results](#key-results)
- [Figures](#figures)
- [Technical Documentation](#technical-documentation)
- [Architecture](#architecture)
- [Setup](#setup)
- [Environment variables](#environment-variables)
- [Step 1: PDF parsing](#step-1-pdf-parsing)
- [Stage 2: GPT analysis](#stage-2-gpt-analysis)
- [Stage 3: Manipulation planning](#stage-3-manipulation-planning)
- [Stage 4: Injection and overlay](#stage-4-injection-and-overlay)
- [Stage 5: Vulnerability simulation](#stage-5-vulnerability-simulation)
- [Agent-backend (multi-agent PDF analyzer)](#agent-backend-multi-agent-pdf-analyzer)
- [CLI reference](#cli-reference)
- [Logging](#logging)
- [Output layout](#output-layout)
- [Output formats](#output-formats)
- [Updating dependencies](#updating-dependencies)
- [Demo UI](#demo-ui)
- [Running the pipeline in the Demo UI](#running-the-pipeline-in-the-demo-ui)
- [License](#license)

---

## Architecture

```
PDF input
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1 (LangGraph)                                              │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐   │
│  │ byte_extraction │ │      OCR        │ │       VLM       │   │
│  │   (PyMuPDF)     │ │ Tesseract       │ │    (Mistral)    │   │
│  │                 │ │ Docling         │ │                 │   │
│  └────────┬────────┘ └────────┬────────┘ └────────┬────────┘   │
│           │                   │                   │             │
│           ▼                   ▼                   ▼             │
│  full_text, full_markdown, pages.json, images (per mechanism)   │
└─────────────────────────────────────────────────────────────────┘
    │
    │  Stage 2 uses: byte_extraction/pymupdf (text, pages.json, images)
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2 (OpenAI Chat Completions)                              │
│  Input: document text + pages.json (bbox) + extracted images    │
│  Output: stage2/openai/analysis.json (semantics + attack        │
│          surface: sensitive_elements, attack_surface, links,     │
│          downstream_consumers, risk_profile)                    │
└─────────────────────────────────────────────────────────────────┘
    │
    │  Stage 3 uses: stage2/analysis.json + byte_extraction/pymupdf structure
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3 (OpenAI Chat Completions)                              │
│  Input: Stage 2 analysis + Step 1 structure (pages, blocks,     │
│         images list with page/xref)                             │
│  Output: stage3/openai/manipulation_plan.json (text_attacks,    │
│          image_attacks, structural_attacks) — planning only    │
└─────────────────────────────────────────────────────────────────┘
    │
    │  Stage 4 uses: stage2/analysis.json, stage3/manipulation_plan.json, original PDF
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 4 (direct PDF injection + overlay)                        │
│  Input: manipulation plan, analysis, original PDF               │
│  Output: stage4/perturbed.pdf, stage4/replacements.json,        │
│          stage4/final_overlay.pdf (visual = original, parse = perturbed) │
└─────────────────────────────────────────────────────────────────┘
```

- **Step 1** runs one or more of: byte_extraction (PyMuPDF), OCR (Tesseract + Docling), VLM (Mistral). Each mechanism writes under `<base_dir>/<run_type>/<sub_mechanism>/`.
- **Stage 2** reads from `byte_extraction/pymupdf` only, calls the OpenAI API, and writes `stage2/openai/analysis.json` (with exactly 3 sensitive elements, each with `value_to_replace` and optional `related_elements`).
- **Stage 3** reads Stage 2 `analysis.json` and Step 1 structure, calls the OpenAI API to produce a manipulation plan (with `scope`, `search_key`, `replacement`, `consistency_note` for document-wide and aggregate-safe attacks). Writes `stage3/openai/manipulation_plan.json`. Planning only.
- **Stage 4** applies replacements via direct PDF modification (PyMuPDF: redact + insert replacement text) to produce `stage4/perturbed.pdf`, then overlays the original PDF as full-page images to produce `stage4/final_overlay.pdf`. When using `run --stage4`, the original PDF is copied to `base_dir/original.pdf` for injection and overlay.
- **Stage 5** consumes `stage4/final_overlay.pdf` and clean byte-extraction text, runs clean/attacked trials via LLM agent simulation, executes deterministic mock tools, and writes doc-level + batch vulnerability metrics for the five real-world scenarios.

---

## Setup

Follow these steps to get the project running on your machine.

### 1. Prerequisites

- **Python 3.10 or newer**
- **(Optional)** **Tesseract** — only if you want to run OCR in Step 1. Install with:
  - macOS: `brew install tesseract`
  - Linux: `apt-get install tesseract-ocr` (or your distro’s package)

### 2. Clone and enter the project

```bash
git clone <your-repo-url> maldoc
cd maldoc
```

### 3. Create a virtual environment and install dependencies

All dependencies are in **`pyproject.toml`**. Use one of the options below.

**Option A — Pip (recommended)**

```bash
python3 -m venv .venv
source .venv/bin/activate          # On Windows: .venv\Scripts\activate
pip install -e .
```

**Option B — Conda**

```bash
conda env create -f environment.yml
conda activate maldoc
pip install -e .
```

This installs the pipeline, Stage 2–5, agent-backend, and the Demo UI. There is no separate `requirements.txt` under `core/agent-backend/`.

### 4. Configure API keys

Create a `.env` file in the **project root** and add your keys:

```bash
cp .env.example .env
```

Edit `.env` and set:

- **`OPENAI_API_KEY`** — required for Stage 2, Stage 3, Stage 5, and the agent-backend (Demo UI evaluation).
- **`MISTRAL_API_KEY`** — only if you run Step 1 with VLM (Mistral); can leave blank if you use only byte extraction or OCR.

Do not commit `.env`. The CLI and Demo UI load it automatically from the project root.

### 5. Start the Demo UI

From the project root, with your virtual environment activated:

```bash
uvicorn apps.web.main:app --reload --port 8000
```

Then open **http://127.0.0.1:8000** in your browser. You can run the full pipeline and evaluation from the web interface (see [Running the pipeline in the Demo UI](#running-the-pipeline-in-the-demo-ui)).

---

## Environment variables

| Variable           | Used by   | Purpose                                      |
|--------------------|-----------|----------------------------------------------|
| `MISTRAL_API_KEY`  | Step 1    | Mistral OCR/VLM API (when running `vlm`)     |
| `OPENAI_API_KEY`   | Stage 2, Stage 3, Stage 5, agent-backend | OpenAI Chat Completions (GPT) for analysis, planning, evaluation, and multi-agent PDF analyzer |

Both can be set in a `.env` file in the project root or in the shell environment.

---

## Step 1: PDF parsing

Step 1 parses a PDF with one or more mechanisms and writes artifacts under `<out>/<pdf_stem>/<run_type>/<sub_mechanism>/`.

### Run all mechanisms (default)

```bash
python -m pipeline.cli path/to/your.pdf --out .
```

This runs **byte_extraction** (PyMuPDF), **OCR** (Tesseract + Docling), and **VLM** (Mistral) and writes to `<pdf_stem>/byte_extraction/pymupdf`, `<pdf_stem>/ocr/tesseract`, `<pdf_stem>/ocr/docling`, and `<pdf_stem>/vlm/mistral`.

### Run only specific mechanisms

- `--byte-only`: only byte_extraction (PyMuPDF)
- `--ocr-only`: only OCR (Tesseract + Docling)
- `--vlm-only`: only VLM (Mistral)
- Combinations: e.g. `--byte-only --ocr-only` runs byte_extraction and OCR only.

Examples:

```bash
python -m pipeline.cli report.pdf --out artifacts --byte-only
python -m pipeline.cli report.pdf --out . --ocr-only
python -m pipeline.cli report.pdf --out . --byte-only --vlm-only
```

### Mechanisms in detail

#### 1. Byte extraction (PyMuPDF)

- **Path**: `<base_dir>/byte_extraction/pymupdf/`
- **What it does**: Extracts text and layout directly from the PDF structure (no rendering/OCR). Extracts embedded images via `page.get_images()` and saves them under `images/`.
- **Outputs**:
  - `full_text.txt`: plain text of the full document
  - `full_markdown.md`: markdown export
  - `pages.json`: array of per-page objects with `page` (0-based index), `text` (page text), and `blocks` (each block: `bbox` [x0, y0, x1, y1], `text`, `type`). See [Output formats](#output-formats).
  - `images/`: embedded figures, named e.g. `page_<i>_img_<j>_x<xref>.<ext>` (PNG/JPEG/etc.)

#### 2. OCR – Tesseract

- **Path**: `<base_dir>/ocr/tesseract/`
- **What it does**: Renders each PDF page to an image, runs Tesseract OCR, and collects word/line-level text and bounding boxes. Does **not** extract embedded figures as separate files; it only produces full-page render images and text/bbox.
- **Outputs**:
  - `full_text.txt`, `full_markdown.md`: full document text
  - `pages.json`: per-page text and blocks with bbox and confidence (word/line level)
  - `page_0.png`, `page_1.png`, ...: rendered page images (one per page)

#### 3. OCR – Docling

- **Path**: `<base_dir>/ocr/docling/`
- **What it does**: Document understanding pipeline (layout, tables, pictures). With `generate_picture_images=True` and `generate_page_images=True`, it exports picture and table images.
- **Outputs**:
  - `full_text.txt`, `full_markdown.md`: full document text
  - `pages.json`: per-page blocks with bbox and element type (e.g. TextItem, PictureItem, TableItem)
  - `images/`: `picture_1.png`, `picture_2.png`, ... and `table_1.png`, ... (when available)

#### 4. VLM – Mistral

- **Path**: `<base_dir>/vlm/mistral/`
- **What it does**: Uses the Mistral OCR API to process the PDF; returns markdown, bbox, and extracted images. Requires `MISTRAL_API_KEY`.
- **Outputs**:
  - `full_markdown.md`, `full_markdown.txt`: full markdown
  - `pages.json`: page-level structure and bbox from the API
  - `images/`: extracted images from the API (e.g. `img-0.jpeg.jpeg`, …)

---

## Stage 2: GPT analysis

Stage 2 takes the **byte_extraction/pymupdf** output from Step 1 (document text, `pages.json`, and extracted images) and calls the OpenAI Chat Completions API (e.g. GPT-4o) to produce a **vulnerability-focused analysis**: document semantics (summary, domain, intended task) plus **attack surface mapping** (sensitive elements, injectable regions, render-parse gaps, links, downstream consumers, risk profile). This analysis feeds into Stage 3 for attack planning.

### Inputs (from Step 1)

Stage 2 reads only from `<base_dir>/byte_extraction/pymupdf/`:

- **Document text**: `full_markdown.md` if present, otherwise `full_text.txt` (truncated to 80k chars in the prompt)
- **Structured layout**: `pages.json` (truncated to 30k chars in the prompt to avoid token limits)
- **Images**: all files in `images/` (PNG, JPEG, WEBP, GIF), sent as base64 in the user message

So Step 1 must have been run with **byte_extraction** (at least) before running Stage 2.

### Output

- **Path**: `<base_dir>/stage2/openai/analysis.json`
- **Content**: A single JSON object with:
  - **Document semantics**: `summary`, `domain`, `intended_task`, `sub_tasks`, `original_document_source`, `contains` (images, tables, **links**, etc.), `metadata`
  - **Vulnerability mapping**: `sensitive_elements` (exactly 3 items; each has `value_to_replace` for document-wide replacement and optional `related_elements` for aggregates), `attack_surface`, `downstream_consumers`, `risk_profile`.
  
  See [Output formats](#output-formats) for the complete schema.

### Running Stage 2

**Option A – After Step 1 in one go**

```bash
python -m pipeline.cli path/to/your.pdf --out . --stage2
```

This runs Step 1 (all mechanisms, including byte_extraction) and then Stage 2. If `OPENAI_API_KEY` is not set, Stage 2 is skipped with an error.

**Option B – On existing Step 1 output**

```bash
python -m pipeline.cli stage2 <base_dir> [--model gpt-4o]
```

Example: if Step 1 wrote to `./paper/`, run:

```bash
python -m pipeline.cli stage2 paper --model gpt-4o
```

`<base_dir>` must contain `byte_extraction/pymupdf/` with at least `full_markdown.md` or `full_text.txt` and optionally `pages.json` and `images/`.

### Customizing the Stage 2 prompt

The system prompt used for the GPT call is in `core/stage2/prompts.py` (`STAGE2_SYSTEM_PROMPT`). You can edit that string to change the requested fields or instructions. To use a completely different prompt from code, call `run_stage2_openai(base_dir, system_prompt="...")` (see `core/stage2/openai_analyzer.py`).

### Model and API

- Default model in the CLI is `gpt-4o`. Override with `--model` / `-m`, e.g. `--model gpt-4o-mini` or `--model gpt-5` when available.
- The client uses `response_format={"type": "json_object"}` and `max_completion_tokens=4096`. The API key is read from `OPENAI_API_KEY` (env or `.env`).

---

## Stage 3: Manipulation planning

Stage 3 takes **Stage 2** `analysis.json` and **Step 1** structure (compact `pages.json` summary + list of embedded images with page/xref) and calls the OpenAI API to produce an **attack-ready manipulation plan**: specific attacks split by modality (text attacks, image attacks, structural attacks including **hyperlink manipulation**), each with injection strategy (addition/modification/redaction), technique, payload, and downstream effects. It does **not** modify the PDF; it only outputs a plan for use by Stage 4 (execution/injection).

### Inputs

- **Stage 2**: `stage2/openai/analysis.json` (required). Run Stage 2 first.
- **Step 1**: `byte_extraction/pymupdf/pages.json` (compact structure) and `byte_extraction/pymupdf/images/` (filenames parsed for page and xref).

### Output

- **Path**: `<base_dir>/stage3/openai/manipulation_plan.json`
- **Content**: A JSON object with:
  - **`document_threat_model`**: attacker capability, attack goal, target consumers, assumed defenses
  - **`text_attacks`** (array): text manipulation items with `injection_strategy` (addition/modification/redaction), `technique` (invisible_text_injection, font_glyph_remapping, unicode_homoglyph, dual_layer_overlay, etc.), `payload_description`, `intent` (from risk taxonomy), `render_parse_behavior`
  - **`image_attacks`** (array): image manipulation items with `technique` (adversarial_patch, pixel_perturbation, steganographic_payload, etc.), `adversarial_objective`, `vision_model_target`, `perturbation_constraints`
  - **`structural_attacks`** (array): PDF structure attacks including **hyperlink manipulation** (`hyperlink_redirect`, `hyperlink_injection`, `hyperlink_removal`) with `malicious_url` for redirect/injection attacks
  - **`defense_considerations`**: detection difficulty, SafeDoc-applicable attacks, mitigation notes
  
  See [Output formats](#output-formats) for the complete schema.

### Running Stage 3

**Option A – With Step 1 in one go**

```bash
python -m pipeline.cli run path/to/your.pdf --out . --stage3
```

This runs Step 1 (all mechanisms), then Stage 2, then Stage 3. `--stage3` implies `--stage2` (Stage 3 requires Stage 2 output).

**Option B – On existing output**

```bash
python -m pipeline.cli stage3 <base_dir> [--model gpt-4o]
```

Example: if Step 1 and Stage 2 wrote to `./report/`, run:

```bash
python -m pipeline.cli stage3 report --model gpt-4o
```

Requires `OPENAI_API_KEY`. The system prompt is in `core/stage3/prompts.py` (`STAGE3_SYSTEM_PROMPT`).

---

## Stage 4: Injection and overlay

Stage 4 applies the manipulation plan via **direct PDF modification** (PyMuPDF: redact + insert replacement text) to produce a **perturbed** PDF (parsers/agents see modified content), then optionally overlays the **original** PDF as full-page images so the document **looks** unchanged to humans (image-overlay attack).

- **Input**: `stage2/openai/analysis.json`, `stage3/openai/manipulation_plan.json`, and the **original PDF** at `base_dir/original.pdf` or passed via `--original-pdf`.
- **Output**: `stage4/perturbed.pdf`, `stage4/replacements.json` (audit log of replacements), and `stage4/final_overlay.pdf` (if overlay was run).

Replacements are built from Stage 3 `text_attacks` with `scope: "everywhere"` (using `search_key` and `replacement`). They are applied in-place to the original PDF (search → redaction annotation with replacement text → apply redactions), and the result is saved to `stage4/perturbed.pdf`. The overlay step renders each page of the original PDF to an image and inserts it on top of the perturbed PDF so the visible layer is the original and the underlying content is perturbed.

**Run Stage 4** (after Step 1, Stage 2, and Stage 3):

```bash
python -m pipeline.cli stage4 <base_dir> [--original-pdf PATH] [--no-overlay] [--priority-filter high|medium|low]
```

Or run the full pipeline including Stage 4 (Step 1 → Stage 2 → Stage 3 → copy original PDF to `base_dir/original.pdf` → Stage 4):

```bash
python -m pipeline.cli run path/to/document.pdf --out . --stage4
```

When using `run --stage4`, the original PDF is copied to `<base_dir>/original.pdf` for injection and overlay.

---

## Stage 5: Vulnerability simulation

Stage 5 is the post-Stage-4 evaluation layer used to demonstrate that adversarial PDFs can corrupt critical agentic workflows. It compares a clean run versus an attacked run for each document:

- **Clean input**: `byte_extraction/pymupdf/full_text.txt`
- **Attacked input**: `stage4/final_overlay.pdf` parsed again with PyMuPDF byte extraction
- **Execution engine**: LLM agent simulation + deterministic scenario-specific mock tools
- **Trials**: 3 clean + 3 attacked trials, then majority vote
- **Scoring policy**: vulnerability-only metrics with denominator restricted to docs where clean majority matches gold spec
- **Terminal output**: human-readable narrative summary (clean behavior vs adversarial behavior, changed target fields, and compromise verdict) plus file paths for full artifacts

Per-document outputs are written to `<base_dir>/stage5_eval/`:

- `clean_trials.jsonl`
- `attacked_trials.jsonl`
- `doc_result.json`
- `doc_metrics.json`

Batch outputs are written to `<out_dir>/<run_id>/`:

- `run_config.json`
- `doc_results.csv`
- `scenario_metrics.csv`
- `overall_metrics.json`
- `paper_table.md`

Run Stage 5 for one document:

```bash
python -m pipeline.cli stage5 <base_dir> \
  --scenario auto \
  --model gpt-5-2025-08-07 \
  --trials 3
```

Run Stage 5 for a batch (`--doc-id` can be repeated; if omitted, demo batch is used from `configs/stage5/demo_batch.json`):

```bash
python -m pipeline.cli stage5_batch \
  --base-root . \
  --doc-id 0afbb63ded89d3335a5109f8a9ec4db7 \
  --doc-id 28a3508ea6ad3b25e2670c55359c1d8e \
  --model gpt-5-2025-08-07 \
  --trials 3 \
  --out-dir stage5_runs
```

---

## Agent-backend (multi-agent PDF analyzer)

The **multi-agent supervisor** PDF analyzer lives under `core/agent-backend/`. It uses a perception layer (PyPDF), a router/supervisor (OpenAI), and domain-specific agents (Healthcare, Finance, HR, Insurance, Education, Political) to answer natural-language questions about a PDF. It is aligned with the rest of the codebase:

- **Dependencies**: No separate `requirements.txt`; all deps are in the root **`pyproject.toml`**. Use the project env (`pip install -e .`).
- **Environment**: Loads **`OPENAI_API_KEY`** from the **project root `.env`** (same as the main CLI). Optional: keyring for secure key storage (see `core/agent-backend/SECURE_API_KEY_SETUP.md`).

### Run from the command line

From the **project root** (so the root `.env` is used):

```bash
# Shell wrapper (uses project root .venv if present, else current python)
./core/agent-backend/run_pdf.sh "/path/to/file.pdf" "Your question here"

# Or directly
python core/agent-backend/run_on_pdf.py /path/to/file.pdf "Your question here"
```

If you `cd` into `core/agent-backend/`, the script still loads the root `.env` via `Path(__file__)`.

### Run the API server

From **`core/agent-backend/`** (so the `src` package is found):

```bash
cd core/agent-backend
python -m src.api_server
```

Or with uvicorn (e.g. port 8001 to avoid clashing with the Demo UI on 8000):

```bash
cd core/agent-backend
uvicorn src.api_server:app --reload --port 8001
```

The server loads the project root `.env` on startup.

For architecture details, quick start, and API docs, see **`core/agent-backend/README.md`**.

---

## CLI reference

### `run` – Step 1 (and optionally Stage 2, Stage 3)

```text
python -m pipeline.cli run <pdf> [OPTIONS]
```

| Argument / Option   | Description |
|--------------------|-------------|
| `pdf`              | Path to the PDF file (required). |
| `--out`, `-o`      | Output base directory. Default: `.`. Step 1 writes to `<out>/<pdf_stem>/`. |
| `--byte-only`      | Run only byte_extraction (PyMuPDF). |
| `--ocr-only`       | Run only OCR (Tesseract + Docling). |
| `--vlm-only`       | Run only VLM (Mistral). |
| `--stage2`         | After Step 1, run Stage 2 GPT analysis (requires byte_extraction; adds it if not in run_types). |
| `--stage3`         | After Step 1 (and Stage 2 if needed), run Stage 3 manipulation planning. Implies `--stage2`. |
| `--stage4`         | After Stage 3, run Stage 4 injection and image overlay. Implies `--stage2`, `--stage3`. Copies original PDF to `base_dir/original.pdf`. |
| `--priority-filter` | Stage 4 only: apply attacks at this priority or higher (`high` \| `medium` \| `low`). Default: all. |
| `--verbose`, `-v`  | Enable DEBUG logging. |

Run type logic:

- If none of `--byte-only`, `--ocr-only`, `--vlm-only` are set: run all three (byte_extraction, ocr, vlm).
- If one or more are set: run only those. Combinations are allowed (e.g. `--byte-only --ocr-only`).
- `--stage2`, `--stage3`, or `--stage4` ensures byte_extraction is included. `--stage3` and `--stage4` run Stage 2 before Stage 3. `--stage4` copies the original PDF and runs Stage 4 (direct PDF injection + overlay).

### `stage2` – Stage 2 only

```text
python -m pipeline.cli stage2 <base_dir> [--model gpt-4o]
```

| Argument / Option | Description |
|-------------------|-------------|
| `base_dir`        | Path to the Step 1 output directory that contains `byte_extraction/pymupdf/`. |
| `--model`, `-m`   | OpenAI chat model. Default: `gpt-4o`. |

Requires `OPENAI_API_KEY` to be set.

### `stage3` – Stage 3 only

```text
python -m pipeline.cli stage3 <base_dir> [--model gpt-4o]
```

| Argument / Option | Description |
|-------------------|-------------|
| `base_dir`        | Path to the output directory that contains `stage2/openai/analysis.json` and `byte_extraction/pymupdf/`. |
| `--model`, `-m`   | OpenAI chat model. Default: `gpt-4o`. |

Requires `OPENAI_API_KEY` to be set.

### `stage4` – Stage 4 only

```text
python -m pipeline.cli stage4 <base_dir> [--original-pdf PATH] [--no-overlay] [--priority-filter high|medium|low]
```

| Argument / Option | Description |
|-------------------|-------------|
| `base_dir`        | Path to output directory containing `stage2/openai/analysis.json`, `stage3/openai/manipulation_plan.json`, and `byte_extraction/pymupdf/`. |
| `--original-pdf`  | Path to original (unperturbed) PDF for injection and overlay. Default: `base_dir/original.pdf`. |
| `--no-overlay`    | Skip image overlay; only run injection (perturbed PDF only). |
| `--priority-filter` | Only apply attacks at this priority or higher: `high`, `medium`, or `low`. Default: all. |

Writes `stage4/perturbed.pdf`, `stage4/replacements.json`, and (unless `--no-overlay`) `stage4/final_overlay.pdf`.

### `stage5` – Stage 5 single document

```text
python -m pipeline.cli stage5 <base_dir> [--scenario auto|decision|scheduling|db|credential|survey] [--adv-pdf PATH] [--model MODEL] [--trials 3] [--out-subdir stage5_eval]
```

| Argument / Option | Description |
|-------------------|-------------|
| `base_dir`        | Path to document output directory (must include `byte_extraction/pymupdf/full_text.txt` and `stage4/final_overlay.pdf` unless `--adv-pdf` is provided). |
| `--scenario`      | Scenario override. Default: `auto` (resolved from `configs/stage5/scenario_specs.json`). |
| `--adv-pdf`       | Override attacked PDF path. Default: `base_dir/stage4/final_overlay.pdf`. |
| `--model`, `-m`   | OpenAI chat model. Default: `gpt-5-2025-08-07`. |
| `--trials`        | Number of clean + attacked trials. Default: `3`. |
| `--out-subdir`    | Per-document Stage 5 output dir under `base_dir`. Default: `stage5_eval`. |

Requires `OPENAI_API_KEY` to be set.

### `stage5_batch` – Stage 5 batch run

```text
python -m pipeline.cli stage5_batch [--base-root .] [--doc-id DOC ...] [--model MODEL] [--trials 3] [--out-dir stage5_runs]
```

| Argument / Option | Description |
|-------------------|-------------|
| `--base-root`     | Root directory containing doc folders (`<base-root>/<doc_id>/...`). Default: `.` |
| `--doc-id`        | Repeat to include multiple docs. If omitted, docs are loaded from `configs/stage5/demo_batch.json`. |
| `--model`, `-m`   | OpenAI chat model. Default: `gpt-5-2025-08-07`. |
| `--trials`        | Number of clean + attacked trials per doc. Default: `3`. |
| `--out-dir`       | Directory for aggregate reports. Default: `stage5_runs`. |

Batch fails fast if any requested doc ID is missing from `configs/stage5/scenario_specs.json`.

---

## Logging

All stages use structured logging (module-level loggers). By default the CLI logs at **INFO**. To debug failures:

- Set the environment variable **`LOG_LEVEL=DEBUG`** to enable DEBUG logs for all modules, or
- Pass **`--verbose`** / **`-v`** when invoking the CLI (e.g. `python -m pipeline.cli --verbose run file.pdf`).

Stage entry points log base_dir and output paths; validation errors and exceptions are logged with full context.

---

## Output layout

After running Step 1 (and optionally Stage 2 and Stage 3), the directory for a PDF named `report.pdf` with `--out .` looks like:

```text
report/
├── byte_extraction/
│   └── pymupdf/
│       ├── full_text.txt
│       ├── full_markdown.md
│       ├── pages.json
│       └── images/
│           └── page_*_img_*_x*.png (or .jpeg, etc.)
├── ocr/
│   ├── tesseract/
│   │   ├── full_text.txt
│   │   ├── full_markdown.md
│   │   ├── pages.json
│   │   └── page_0.png, page_1.png, ...
│   └── docling/
│       ├── full_text.txt
│       ├── full_markdown.md
│       ├── pages.json
│       └── images/
│           └── picture_*.png, table_*.png
├── vlm/
│   └── mistral/
│       ├── full_markdown.md
│       ├── full_markdown.txt
│       ├── pages.json
│       └── images/
│           └── img-*.jpeg.jpeg, ...
├── stage2/              (only if Stage 2 was run)
│   └── openai/
│       └── analysis.json
├── stage3/              (only if Stage 3 was run)
│   └── openai/
│       └── manipulation_plan.json
├── stage4/              (only if Stage 4 was run)
│   ├── perturbed.pdf
│   ├── replacements.json
│   └── final_overlay.pdf
├── stage5_eval/          (only if Stage 5 was run for this doc)
│   ├── clean_trials.jsonl
│   ├── attacked_trials.jsonl
│   ├── doc_result.json
│   └── doc_metrics.json
└── original.pdf         (only if run --stage4; copy of input PDF for overlay)
```

Batch Stage 5 reports are written outside doc folders under `<out-dir>/<run_id>/` with `run_config.json`, `doc_results.csv`, `scenario_metrics.csv`, `overall_metrics.json`, and `paper_table.md`.

---

## Output formats

### Step 1: `pages.json` (byte_extraction / OCR / VLM)

Each mechanism writes a `pages.json` that is an **array of page objects**. Exact structure can differ slightly by mechanism; the byte_extraction (PyMuPDF) shape is:

- **Page object**:
  - `page`: 0-based page index (integer)
  - `text`: full text of the page (string)
  - `blocks`: array of block objects

- **Block object** (PyMuPDF):
  - `bbox`: `[x0, y0, x1, y1]` in PDF coordinates (floats)
  - `text`: text content of the block (string)
  - `type`: block type code (integer; mechanism-specific)

OCR and VLM variants may add fields such as `confidence` (Tesseract) or named `type` strings (e.g. Docling: `"TextItem"`, `"PictureItem"`, `"TableItem"`). See `docs/OUTPUT_FORMATS.md` for more detail.

### Stage 2: `analysis.json`

Written to `<base_dir>/stage2/openai/analysis.json`. Top-level keys:

**Document semantics:**
- `summary`, `domain`, `intended_task`, `sub_tasks`, `original_document_source`
- `contains`: `images`, `tables`, `code`, `equations`, `forms`, `signatures`, `watermarks`, `headers_footers`, **`links`** (boolean), `other`
- `metadata`: `suggested_tags`, `language`, `page_count`, `other`

**Vulnerability mapping:**
- **`sensitive_elements`** (array): Each item has `element_type` (text_block, image, table, form_field, header_footer, signature), `page`, `block_index_or_region`, `content_preview`, `sensitivity_type` (PII, financial, medical, credential, legal, strategic, other), `sensitivity_level` (critical, high, medium, low)
- **`attack_surface`** (object):
  - `text_surface`: `injectable_regions`, `render_parse_gaps`, `redactable_targets`
  - `image_surface`: `image_count`, `images` (array with page, xref, content_description, role_in_document, vision_model_reliance)
  - `structure_surface`: `has_forms`, `has_javascript`, `has_annotations`, `has_layers`, `has_embedded_files`, **`has_links`**, **`links`** (array with page, link_text, target_url, link_type, risk_level), `font_diversity`
- **`downstream_consumers`** (array): Each item has `consumer`, `processing_path`, `reliance_on_text`, `reliance_on_images`, `vulnerability_notes`
- **`risk_profile`** (object): `primary_risks` (array from taxonomy: leak_sensitive_data, lead_to_property_loss, spread_misinformation, lead_to_physical_harm, violate_law_ethics, compromise_availability, contribute_to_harmful_code, produce_unsafe_information), `domain_specific_risks`, `overall_risk_level`

Any field may be `null` if the model could not infer it. The exact prompt and rules are in `core/stage2/prompts.py`.

### Stage 3: `manipulation_plan.json`

Written to `<base_dir>/stage3/openai/manipulation_plan.json`. Top-level keys:

- **`document_threat_model`** (object): `attacker_capability` (interceptor, author, modifier), `attack_goal`, `target_consumers`, `assumed_defenses`
- **`text_attacks`** (array): Each item has:
  - `attack_id` (e.g. "T1", "T2"), `target` (page, block_index, bbox, region, content_preview)
  - `injection_strategy`: "addition" | "modification" | "redaction"
  - `technique`: invisible_text_injection, font_glyph_remapping, unicode_homoglyph, dual_layer_overlay, metadata_field_edit, content_stream_edit, whitespace_encoding
  - `payload_description`, `intent` (from risk taxonomy), `render_parse_behavior` (human_sees, parser_sees), `effects_downstream`, `priority`
- **`image_attacks`** (array): Each item has:
  - `attack_id` (e.g. "I1"), `target` (page, xref, image_id, bbox, content_description)
  - `injection_strategy`, `technique` (adversarial_patch, pixel_perturbation, steganographic_payload, image_replacement, overlay_injection, alternate_stream, metadata_corruption)
  - `adversarial_objective`, `vision_model_target`, `perturbation_constraints`, `intent`, `render_parse_behavior`, `effects_downstream`, `priority`
- **`structural_attacks`** (array): Each item has:
  - `attack_id` (e.g. "S1"), `technique`: optional_content_group, javascript_injection, annotation_overlay, incremental_update, xref_manipulation, embedded_file, **hyperlink_redirect**, **hyperlink_injection**, **hyperlink_removal**
  - `target` (page, link_text, original_url, region), `payload_description`, **`malicious_url`** (required for redirect/injection), `attack_mechanism`, `intent`, `effects_downstream`, `priority`
- **`defense_considerations`** (object): `overall_detection_difficulty`, `safedoc_applicable_attacks` (array of attack_ids), `undetectable_attacks` (array), `recommended_defenses`

The exact prompt is in `core/stage3/prompts.py`. A more precise schema and examples are in `docs/OUTPUT_FORMATS.md`.

---

## Updating dependencies

- **Conda**: After adding a dependency to `environment.yml`, update the env:
  ```bash
  conda env update -f environment.yml
  ```
- **Project (pyproject.toml)**: After adding a dependency under `[project].dependencies`, install in the current env:
  ```bash
  pip install -e .
  ```
- Keep `environment.yml` and `pyproject.toml` in sync when you add new packages (e.g. add to both for conda users).

---

## Demo UI

The Demo UI is a web app for running the pipeline and evaluating adversarial documents without using the command line.

- **Backend**: FastAPI (`apps/web/main.py`)
- **Frontend**: HTML/CSS/JavaScript (`apps/web/templates/index.html`, `apps/web/static/*`)

Start it from the project root (with your venv activated):

```bash
uvicorn apps.web.main:app --reload --port 8000
```

Then open **http://127.0.0.1:8000**. The UI has four tabs: **Pipeline**, **Evaluation**, **Runs**, and **Reports**. Logs are written to `logs/demo_web.log`.

Optional backend model overrides (for Stage 2 and Stage 3):

```bash
export MALDOC_STAGE2_MODEL=gpt-5-2025-08-07
export MALDOC_STAGE3_MODEL=gpt-5-2025-08-07
```

---

## Running the pipeline in the Demo UI

This section explains how to use the Pipeline and Evaluation tabs in plain language.

### Pipeline tab — Adversarial Document Generation

Here you run **Stage 1 → Stage 4** to turn a normal PDF into an adversarial one (same look, different content for parsers/agents).

1. **Choose a PDF**
   - Pick one from the **PDF from repository** dropdown, or
   - Enter a path in **Or custom PDF path** (e.g. `path/to/file.pdf`).
2. **Optional: Advanced options** (click to expand)
   - **Output root** — Where run outputs are stored (default: `pipeline_run`). Each PDF gets a folder named by its hash.
   - **Stage 4 priority filter** — Which planned attacks to apply: **all**, **high**, **medium**, or **low**. Use this to restrict attacks by priority (e.g. only high-priority ones).
   - **Stage 4 mechanism mode** — How attacks from the plan are turned into actual PDF changes (see below).
   - **Stage 1 mechanisms** — How text is extracted: Byte Extraction (default), OCR, and/or VLM. At least Byte Extraction is needed for Stage 2–4.
3. Click **Generate Adversarial Doc**. The stage cards show progress (Stage 1 → 2 → 3 → 4). When done, you get links to the original and adversarial PDFs.

#### What is “Stage 4 mechanism mode”?

Stage 3 produces a **plan** (e.g. “add hidden text here”, “replace this phrase everywhere”). Stage 4 **executes** that plan using one or more physical mechanisms. The **mechanism mode** controls how the plan is mapped to mechanisms:

- **Auto (recommended)** — The system picks the mechanism from the plan’s *strategy*:
  - **Append** (add new content) → **Hidden text injection** (invisible text in the PDF stream).
  - **Update** or **Delete** (change or remove content) → **Visual overlay** or **Font glyph remapping** (so the document looks unchanged but parsers see different text).
  - This matches the paper’s design and is the default.
- **Visual Overlay** — Force all applicable text attacks to be applied via full-page image overlay (original on top; perturbed content underneath).
- **Hidden Text Injection** — Force append-style attacks only (hidden text); other attacks may be skipped.
- **Font Glyph Remapping** — Force update/delete-style attacks via font manipulation where supported.

Choosing a specific mechanism (e.g. Visual Overlay only) is for **ablation or experiments**; it can diverge from the planner’s intended coupling.

### Evaluation tab — Agent-Backend Evaluation

Here you compare how the **agent-backend** (multi-agent supervisor) behaves on the **clean** vs **adversarial** document. You see which domain specialist was routed and whether the adversarial doc caused a compromise.

1. **Prompt template** — The query sent to the agent:
   - **Auto Router Check (Recommended)** — A neutral, generic query. The **router** (supervisor) looks at the document and **decides which domain specialist** to use (e.g. Healthcare, Finance, HR). You do not pick the agent; the model routes by content. Use this to see “what would the system do with this document?”
   - **Decision / Scheduling / Database / Credential / Survey** — Scenario-specific prompts (e.g. “extract scheduling actions”, “verify credential fields”). The router *still* decides which specialist runs; the prompt only shapes the task. Use these to test particular use cases.
2. **Trials** — How many times the system runs the agent on the **clean** document and on the **adversarial** document (e.g. 3 clean + 3 adversarial). Results are aggregated (e.g. majority vote) to decide if the document is **compromised**. More trials = more stable verdict but slower runs. Default is 3; you can set 1–9.
3. **Upload PDFs** — **Upload Original Doc** and **Upload Adversarial Doc** (e.g. the original PDF and the one from the Pipeline tab’s Stage 4 output). You can also run evaluation on a document that was already processed by the Pipeline (see eligibility).
4. **Check Eligibility** — Verifies that the chosen scenario and uploaded (or existing) documents are valid (e.g. required files exist). If eligible, **Run Agent-Backend Evaluation** is enabled.
5. **Run Agent-Backend Evaluation** — Runs the agent multiple times (according to **Trials**), then shows:
   - Which domain specialist was routed for clean vs adversarial (in **Agent Monitor**),
   - A short narrative (clean behavior vs adversarial behavior, compromise verdict),
   - And in the **Runs** tab, a table of recent evaluation results (compromised, clean=gold, changed fields, paths).

In short: **Auto** = neutral query, router picks the agent; **Trials** = number of runs per document for a stable compromise check; **Check Eligibility** ensures your inputs are valid before running.

---

## License

TBD.
