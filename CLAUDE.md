# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**documind** is a multi-stage PDF vulnerability analysis pipeline designed for security research. It extracts content from PDFs using multiple techniques, analyzes attack surfaces, and plans potential PDF manipulation attacks (for research/testing purposes only).

**Three main stages:**
- **Step 1**: Extract text, layout (bounding boxes), markdown, and images using byte-extraction (PyMuPDF), OCR (Tesseract, Docling), and VLM (Mistral). Orchestrated with LangGraph.
- **Stage 2**: Analyze extracted content with OpenAI GPT to produce vulnerability-focused analysis: document semantics + attack surface mapping (sensitive elements, injectable regions, render-parse gaps, links, downstream consumers, risk profile).
- **Stage 3**: Generate attack-ready manipulation plan based on Stage 2 analysis: specific attacks by modality (text, image, structural including hyperlink manipulation) with injection strategies, techniques, payloads, and downstream effects. Planning only; no actual PDF modification.

## Development Commands

### Environment Setup

**Using Conda (recommended):**
```bash
conda env create -f environment.yml
conda activate documind
```

**Using pip:**
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

**System dependencies:**
- Tesseract OCR: `brew install tesseract` (macOS) or `apt-get install tesseract-ocr` (Linux)

### Running the Pipeline

**Step 1 - Parse PDF (all mechanisms):**
```bash
python -m pipeline.cli run path/to/file.pdf --out .
```

**Step 1 - Specific mechanisms only:**
```bash
python -m pipeline.cli run file.pdf --byte-only           # PyMuPDF only
python -m pipeline.cli run file.pdf --ocr-only            # Tesseract + Docling
python -m pipeline.cli run file.pdf --vlm-only            # Mistral VLM
python -m pipeline.cli run file.pdf --byte-only --ocr-only  # Combinations allowed
```

**Step 1 + Stage 2 (with GPT analysis):**
```bash
python -m pipeline.cli run file.pdf --out . --stage2
```

**Step 1 + Stage 2 + Stage 3 (full pipeline):**
```bash
python -m pipeline.cli run file.pdf --out . --stage3
```

**Run Stage 2 on existing Step 1 output:**
```bash
python -m pipeline.cli stage2 <base_dir> [--model gpt-4o]
```

**Run Stage 3 on existing output:**
```bash
python -m pipeline.cli stage3 <base_dir> [--model gpt-4o]
```

### Updating Dependencies

**Conda:**
```bash
conda env update -f environment.yml
```

**Pip (after editing pyproject.toml):**
```bash
pip install -e .
```

Keep both `environment.yml` and `pyproject.toml` in sync when adding dependencies.

## Architecture

### Code Organization

```
core/
├── extract/               # Step 1: PDF extraction mechanisms
│   ├── base.py           # Abstract Extractor interface
│   ├── models.py         # Shared data models
│   ├── pymupdf_extractor.py    # Byte-extraction (direct PDF parsing)
│   ├── tesseract_extractor.py  # OCR with Tesseract
│   ├── docling_extractor.py    # OCR with Docling
│   └── mistral_extractor.py    # VLM using Mistral API
├── stage2/               # Stage 2: GPT vulnerability analysis
│   ├── openai_analyzer.py      # Loads Step 1 outputs, calls OpenAI API
│   └── prompts.py              # STAGE2_SYSTEM_PROMPT
└── stage3/               # Stage 3: GPT manipulation planning
    ├── openai_planner.py       # Loads Stage 2 + Step 1, calls OpenAI API
    └── prompts.py              # STAGE3_SYSTEM_PROMPT

pipeline/
├── graph.py              # LangGraph workflow for Step 1 (parse_pdf_node)
└── cli.py                # Typer CLI: run, stage2, stage3 commands
```

### Extractor Pattern

All Step 1 extractors inherit from `core.extract.base.Extractor` with a single abstract method:
```python
def extract(self, pdf_path: str, output_dir: Path) -> dict[str, Any]:
    """Extract content from PDF and write artifacts under output_dir. Returns summary dict."""
```

Extractors write standardized artifacts:
- `full_text.txt` - plain text
- `full_markdown.md` - markdown export
- `pages.json` - array of page objects with `page` (0-based index), `text`, and `blocks` (each block has `bbox`, `text`, `type`)
- `images/` - extracted images (naming varies by mechanism)

### LangGraph Pipeline Flow

Step 1 uses LangGraph to orchestrate extractors in `pipeline/graph.py`:
1. `parse_pdf_node` receives state with `pdf_path`, `base_dir`, `run_types`
2. For each run_type in ["byte_extraction", "ocr", "vlm"], instantiate corresponding extractors
3. Each extractor writes to `<base_dir>/<run_type>/<sub_mechanism>/`
4. Returns state with `results` dict keyed by `run_type/sub_mechanism`

### Stage 2 & 3 Flow

**Stage 2** (`core/stage2/openai_analyzer.py`):
1. Load from `byte_extraction/pymupdf/`: document text (markdown or txt), `pages.json`, and images
2. Build OpenAI Chat Completions messages with system prompt + user content (text + base64 images)
3. Request JSON response format, max_completion_tokens=4096
4. Write `stage2/openai/analysis.json` with vulnerability mapping

**Stage 3** (`core/stage3/openai_planner.py`):
1. Load Stage 2 `analysis.json`
2. Load Step 1 structure: compact `pages.json` summary + image list with page/xref from filenames
3. Build messages with system prompt + analysis + structure
4. Request JSON response, max_completion_tokens=8192
5. Write `stage3/openai/manipulation_plan.json` with attack plan (text_attacks, image_attacks, structural_attacks)

### Output Directory Structure

For `report.pdf` with `--out .`:
```
report/
├── byte_extraction/pymupdf/
│   ├── full_text.txt
│   ├── full_markdown.md
│   ├── pages.json
│   └── images/page_<i>_img_<j>_x<xref>.<ext>
├── ocr/tesseract/
│   ├── full_text.txt
│   ├── full_markdown.md
│   ├── pages.json
│   └── page_0.png, page_1.png, ...
├── ocr/docling/
│   ├── full_text.txt
│   ├── full_markdown.md
│   ├── pages.json
│   └── images/picture_*.png, table_*.png
├── vlm/mistral/
│   ├── full_markdown.md
│   ├── full_markdown.txt
│   ├── pages.json
│   └── images/img-*.jpeg.jpeg
├── stage2/openai/analysis.json        # If --stage2 used
└── stage3/openai/manipulation_plan.json  # If --stage3 used
```

## Important Constraints

### Environment Variables

Required API keys (set in `.env` or shell):
- `MISTRAL_API_KEY` - for Step 1 VLM (Mistral)
- `OPENAI_API_KEY` - for Stage 2 & Stage 3 (GPT)

`.env` is loaded automatically by `pipeline/cli.py` using `python-dotenv`.

### Token Limits

To avoid OpenAI API token overflow:
- **Stage 2** truncates `pages.json` to 30k chars and document text to 80k chars
- **Stage 3** truncates structure summary to 25k chars

### Output Format Schemas

Detailed schemas for `pages.json`, `analysis.json`, and `manipulation_plan.json` are in `docs/OUTPUT_FORMATS.md`. Key points:

**pages.json** (Step 1): Array of page objects, each with `page`, `text`, `blocks` (blocks have `bbox`, `text`, `type`)

**analysis.json** (Stage 2): Document semantics + vulnerability mapping with:
- `sensitive_elements` - PII, financial, medical data with locations
- `attack_surface` - text/image/structure surfaces with injectable regions, render-parse gaps, links
- `downstream_consumers` - who processes this document
- `risk_profile` - primary risks from taxonomy (leak_sensitive_data, lead_to_property_loss, spread_misinformation, etc.)

**manipulation_plan.json** (Stage 3): Attack plan with:
- `document_threat_model` - attacker capability, goal, target consumers
- `text_attacks` - injection_strategy, technique, payload, intent, render_parse_behavior
- `image_attacks` - adversarial techniques, vision_model_target, perturbation_constraints
- `structural_attacks` - includes hyperlink_redirect, hyperlink_injection, hyperlink_removal with `malicious_url` for redirect/injection

### Modifying Prompts

**Stage 2 system prompt:** `core/stage2/prompts.py` → `STAGE2_SYSTEM_PROMPT`
**Stage 3 system prompt:** `core/stage3/prompts.py` → `STAGE3_SYSTEM_PROMPT`

After editing prompts, re-run stage2/stage3 commands to regenerate outputs with new instructions.

## Security Research Context

This tool is designed for **authorized PDF vulnerability research and defensive security testing only**. The manipulation plans generated in Stage 3 are for understanding attack surfaces and developing defenses. No actual PDF modification occurs in Stages 1-3. Stage 4 (execution/injection) is not yet implemented.

When working on this codebase, ensure code changes maintain the research-only focus and do not enable malicious use.
