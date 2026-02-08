# documind

A multi-stage PDF parsing and analysis pipeline:

- **Step 1**: Extract text, layout (bounding boxes), markdown, and images from PDFs using byte-extraction (PyMuPDF), OCR (Tesseract, Docling), and VLM (Mistral). Orchestrated with LangGraph.
- **Stage 2**: Send the byte-extraction outputs plus extracted images to an MLLM (OpenAI GPT) to produce a **vulnerability-focused analysis**: document semantics (summary, domain, intended task) plus attack surface mapping (sensitive elements, injectable regions, render-parse gaps, links, downstream consumers, risk profile).
- **Stage 3**: Use Stage 2 analysis and Step 1 structure to produce an **attack-ready manipulation plan**: specific attacks split by modality (text attacks, image attacks, structural attacks including hyperlink manipulation), each with injection strategy, technique, payload, and downstream effects. Planning only; no injection is performed.

Output is written under **one folder per PDF** (named by the PDF stem), with subfolders per run type and, optionally, Stage 2 and Stage 3 results.

---

## Table of contents

- [Architecture](#architecture)
- [Setup](#setup)
- [Environment variables](#environment-variables)
- [Step 1: PDF parsing](#step-1-pdf-parsing)
- [Stage 2: GPT analysis](#stage-2-gpt-analysis)
- [Stage 3: Manipulation planning](#stage-3-manipulation-planning)
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
│          image_attacks, structural_attacks including hyperlink   │
│          manipulation, defense_considerations) — planning only │
└─────────────────────────────────────────────────────────────────┘
```

- **Step 1** runs one or more of: byte_extraction (PyMuPDF), OCR (Tesseract + Docling), VLM (Mistral). Each mechanism writes under `<base_dir>/<run_type>/<sub_mechanism>/`.
- **Stage 2** reads from `byte_extraction/pymupdf` only (full text or markdown, `pages.json`, and `images/`), calls the OpenAI API with a system prompt and the document + images, and writes `stage2/openai/analysis.json`.
- **Stage 3** reads Stage 2 `analysis.json` and Step 1 structure (compact `pages.json` summary + image list with page/xref from filenames), calls the OpenAI API to produce a manipulation plan (what to manipulate, where, risk category, downstream effects). Writes `stage3/openai/manipulation_plan.json`. No actual PDF manipulation is performed; injection mechanisms are planned for a later stage.

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
| `OPENAI_API_KEY`   | Stage 2, Stage 3 | OpenAI Chat Completions (GPT) for analysis and manipulation planning |

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
  - **Vulnerability mapping**: `sensitive_elements` (PII, financial, medical data with locations), `attack_surface` (text/image/structure surfaces with injectable regions, render-parse gaps, **links**), `downstream_consumers` (who processes this document), `risk_profile` (primary risks from taxonomy: leak_sensitive_data, lead_to_property_loss, spread_misinformation, etc.)
  
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

Run type logic:

- If none of `--byte-only`, `--ocr-only`, `--vlm-only` are set: run all three (byte_extraction, ocr, vlm).
- If one or more are set: run only those. Combinations are allowed (e.g. `--byte-only --ocr-only`).
- `--stage2` or `--stage3` ensures byte_extraction is included. `--stage3` also runs Stage 2 before Stage 3.

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
└── stage3/              (only if Stage 3 was run)
    └── openai/
        └── manipulation_plan.json
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

## License

TBD.
