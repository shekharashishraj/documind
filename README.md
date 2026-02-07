# documind

A two-stage PDF parsing and analysis pipeline:

- **Step 1**: Extract text, layout (bounding boxes), markdown, and images from PDFs using byte-extraction (PyMuPDF), OCR (Tesseract, Docling), and VLM (Mistral). Orchestrated with LangGraph.
- **Step 2**: Send the byte-extraction outputs plus extracted images to an MLLM (OpenAI GPT) to produce a structured analysis: summary, domain, intended task, task classification, and metadata for downstream use.

Output is written under **one folder per PDF** (named by the PDF stem), with subfolders per run type and, optionally, Stage 2 results.

---

## Table of contents

- [Architecture](#architecture)
- [Setup](#setup)
- [Environment variables](#environment-variables)
- [Step 1: PDF parsing](#step-1-pdf-parsing)
- [Stage 2: GPT analysis](#stage-2-gpt-analysis)
- [CLI reference](#cli-reference)
- [Output layout](#output-layout)
- [Output formats](#output-formats)
- [Updating dependencies](#updating-dependencies)
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
    │  Stage 2 uses only: byte_extraction/pymupdf (text, pages.json, images)
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2 (OpenAI Chat Completions)                              │
│  Input: document text + pages.json (bbox) + extracted images    │
│  Output: stage2/openai/analysis.json (summary, domain, etc.)   │
└─────────────────────────────────────────────────────────────────┘
```

- **Step 1** runs one or more of: byte_extraction (PyMuPDF), OCR (Tesseract + Docling), VLM (Mistral). Each mechanism writes under `<base_dir>/<run_type>/<sub_mechanism>/`.
- **Stage 2** reads from `byte_extraction/pymupdf` only (full text or markdown, `pages.json`, and `images/`), calls the OpenAI API with a system prompt and the document + images, and writes `stage2/openai/analysis.json`.

---

## Setup

### Conda (recommended)

```bash
conda env create -f environment.yml
conda activate documind
```

### Pip

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

### System dependencies

- **Tesseract** (for OCR): e.g. `brew install tesseract` (macOS), `apt-get install tesseract-ocr` (Linux).

### API keys

Copy `.env.example` to `.env` in the project root and set the keys you need:

- **Step 1 VLM (Mistral)**: `MISTRAL_API_KEY`
- **Stage 2 (OpenAI)**: `OPENAI_API_KEY`

The CLI loads `.env` automatically. Do not commit `.env`.

---

## Environment variables

| Variable           | Used by   | Purpose                                      |
|--------------------|-----------|----------------------------------------------|
| `MISTRAL_API_KEY`  | Step 1    | Mistral OCR/VLM API (when running `vlm`)     |
| `OPENAI_API_KEY`   | Stage 2   | OpenAI Chat Completions (GPT) for analysis    |

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

Stage 2 takes the **byte_extraction/pymupdf** output from Step 1 (document text, `pages.json`, and extracted images) and calls the OpenAI Chat Completions API (e.g. GPT-4o) to produce a single structured JSON file: summary, domain, intended task, task classification, and metadata.

### Inputs (from Step 1)

Stage 2 reads only from `<base_dir>/byte_extraction/pymupdf/`:

- **Document text**: `full_markdown.md` if present, otherwise `full_text.txt` (truncated to 80k chars in the prompt)
- **Structured layout**: `pages.json` (truncated to 30k chars in the prompt to avoid token limits)
- **Images**: all files in `images/` (PNG, JPEG, WEBP, GIF), sent as base64 in the user message

So Step 1 must have been run with **byte_extraction** (at least) before running Stage 2.

### Output

- **Path**: `<base_dir>/stage2/openai/analysis.json`
- **Content**: A single JSON object with the keys described in [Output formats](#output-formats) (summary, domain, intended_task, sub_tasks, evidence_for_task, preconditions, effects, field_information, contains, bbox_refs, original_document_source, task_classification, metadata).

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

## CLI reference

### `run` – Step 1 (and optionally Stage 2)

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

Run type logic:

- If none of `--byte-only`, `--ocr-only`, `--vlm-only` are set: run all three (byte_extraction, ocr, vlm).
- If one or more are set: run only those. Combinations are allowed (e.g. `--byte-only --ocr-only`).
- `--stage2` ensures byte_extraction is included so Stage 2 can run.

### `stage2` – Stage 2 only

```text
python -m pipeline.cli stage2 <base_dir> [--model gpt-4o]
```

| Argument / Option | Description |
|-------------------|-------------|
| `base_dir`        | Path to the Step 1 output directory that contains `byte_extraction/pymupdf/`. |
| `--model`, `-m`   | OpenAI chat model. Default: `gpt-4o`. |

Requires `OPENAI_API_KEY` to be set.

---

## Output layout

After running Step 1 (and optionally Stage 2), the directory for a PDF named `report.pdf` with `--out .` looks like:

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
└── stage2/              (only if Stage 2 was run)
    └── openai/
        └── analysis.json
```

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

| Key                     | Type   | Description |
|-------------------------|--------|-------------|
| `summary`               | string | 2–4 sentence summary of the document. |
| `domain`                | string | Primary domain (e.g. ML, medicine, legal). |
| `intended_task`         | string | Main task or purpose the document supports. |
| `sub_tasks`             | array  | List of sub-tasks (strings). |
| `evidence_for_task`     | string | How the document and figures support the intended task. |
| `preconditions`         | string | What must be true before using the document. |
| `effects`               | string | Outcomes or outputs the document enables. |
| `field_information`     | string | Field-specific metadata. |
| `contains`              | object | `images`, `tables`, `code`, `equations` (booleans), `other` (array). |
| `bbox_refs`             | string | Note that bbox details are in Step 1 pages.json. |
| `original_document_source` | string | Inferred source: e.g. ARXIV, PPT, REPORT, WEB, UNKNOWN. |
| `task_classification`   | object | `primary` (CLASSIFICATION or GENERATION), `reasoning`, `notes`. |
| `metadata`              | object | `suggested_tags`, `language`, `page_count`, `other`. |

Any field may be `null` if the model could not infer it. The exact prompt and rules are in `core/stage2/prompts.py`.

A more precise schema and examples are in `docs/OUTPUT_FORMATS.md`.

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

## License

TBD.
