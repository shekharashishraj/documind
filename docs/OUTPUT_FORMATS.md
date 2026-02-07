# Output formats

This document describes the structure of the main JSON and text outputs produced by the documind pipeline.

---

## Step 1: `pages.json`

Every run type (byte_extraction/pymupdf, ocr/tesseract, ocr/docling, vlm/mistral) writes a `pages.json` file. It is an **array of page objects**, one per page (0-based index).

### Common shape

```json
[
  {
    "page": 0,
    "text": "Full text of page 0...",
    "blocks": [ ... ]
  },
  {
    "page": 1,
    "text": "Full text of page 1...",
    "blocks": [ ... ]
  }
]
```

- **`page`** (integer): 0-based page index.
- **`text`** (string): Concatenated or full text for that page.
- **`blocks`** (array): List of block objects with at least `text` and usually `bbox` and a type indicator.

### Byte extraction (PyMuPDF) blocks

Each block has:

- **`bbox`** (array of 4 numbers): `[x0, y0, x1, y1]` in PDF coordinates (points).
- **`text`** (string): Text content of the block.
- **`type`** (integer): PyMuPDF block type code (e.g. 0 = text, 1 = image block, etc.).

Example:

```json
{
  "bbox": [211.48, 99.83, 399.89, 117.04],
  "text": "Attention Is All You Need",
  "type": 0
}
```

### OCR (Tesseract) blocks

Blocks typically include word- or line-level items with:

- **`bbox`**: Bounding box (format may be object or array depending on implementation).
- **`text`**: Word or line text.
- **`confidence`** (optional): OCR confidence score.
- **`type`** or block level: line/word.

### OCR (Docling) blocks

Blocks have:

- **`bbox`** (object): Often `{ "l", "r", "t", "b" }` (left, right, top, bottom).
- **`text`**: Text content.
- **`type`** (string): Element type name, e.g. `"TextItem"`, `"PictureItem"`, `"TableItem"`, `"TitleItem"`.

### VLM (Mistral) pages.json

Structure follows the Mistral OCR API response: page-level entries with text and optional bbox/layout information. Exact keys depend on the API version.

---

## Step 1: Image filenames

### Byte extraction (PyMuPDF) – `byte_extraction/pymupdf/images/`

- Pattern: `page_<page_index>_img_<image_index>_x<xref>.<ext>`
- Example: `page_2_img_0_x94.png` = page 2, first image, internal xref 94, PNG.
- `<ext>` can be `png`, `jpeg`, etc., depending on the embedded image format.

### OCR (Docling) – `ocr/docling/images/`

- Pictures: `picture_1.png`, `picture_2.png`, …
- Tables: `table_1.png`, `table_2.png`, …

### VLM (Mistral) – `vlm/mistral/images/`

- Names follow the API (e.g. `img-0.jpeg.jpeg`, `img-1.jpeg.jpeg`).

---

## Stage 2: `analysis.json`

Written to `<base_dir>/stage2/openai/analysis.json`. The model returns a single JSON object with the following top-level keys. All fields may be `null` if not inferred.

### Schema (logical)

| Key | Type | Description |
|-----|------|-------------|
| `summary` | string | 2–4 sentence summary of the document. |
| `domain` | string | Primary domain (e.g. ML, medicine, legal, education). |
| `intended_task` | string | Main task or purpose the document supports. |
| `sub_tasks` | array of strings | List of sub-tasks. |
| `evidence_for_task` | string | How the document and figures support the intended task. |
| `preconditions` | string | What must be true or available before using the document. |
| `effects` | string | Outcomes or outputs the document enables. |
| `field_information` | string | Field-specific metadata. |
| `contains` | object | See below. |
| `bbox_refs` | string | Note that bbox details are in Step 1 pages.json; optionally which blocks/pages are most relevant. |
| `original_document_source` | string | Inferred source: ARXIV, PPT, SLIDES, REPORT, WEB, UNKNOWN. |
| `task_classification` | object | See below. |
| `metadata` | object | See below. |

### `contains` object

- **`images`** (boolean): Document contains figures/images.
- **`tables`** (boolean): Document contains tables.
- **`code`** (boolean): Document contains code.
- **`equations`** (boolean): Document contains equations.
- **`other`** (array): Other content types (strings).

### `task_classification` object

- **`primary`** (string): `"CLASSIFICATION"` or `"GENERATION"`.
- **`reasoning`** (string): If reasoning-based, brief description.
- **`notes`** (string): Any clarification for downstream use.

### `metadata` object

- **`suggested_tags`** (array of strings): Suggested tags for the document.
- **`language`** (string): e.g. `"en"`.
- **`page_count`** (integer or null): Number of pages if evident.
- **`other`** (object): Arbitrary key-value pairs for downstream use.

### Example `analysis.json`

```json
{
  "summary": "The document introduces the Transformer architecture, which relies entirely on attention mechanisms rather than recurrent or convolutional neural networks. It demonstrates superior quality in machine translation tasks.",
  "domain": "machine learning",
  "intended_task": "To describe and promote the Transformer model for translation tasks.",
  "sub_tasks": ["Machine translation", "Sequence transduction"],
  "evidence_for_task": "The document shows improvements in BLEU scores on translation tasks and discusses the benefits of attention mechanisms.",
  "preconditions": "Familiarity with neural networks and attention mechanisms is needed.",
  "effects": "Enables faster and more efficient translation models with improved accuracy.",
  "field_information": "The document relates to neural machine translation focusing on new architectures.",
  "contains": {
    "images": true,
    "tables": true,
    "code": false,
    "equations": false,
    "other": []
  },
  "bbox_refs": "Details in Step 1 pages.json; figures on architecture and tables with results are most relevant.",
  "original_document_source": "ARXIV",
  "task_classification": {
    "primary": "CLASSIFICATION",
    "reasoning": "The document analyzes and classifies improvements in neural network architecture for translation tasks.",
    "notes": "Focus is on explaining a new model architecture for classification tasks."
  },
  "metadata": {
    "suggested_tags": ["Transformer", "Attention", "Machine Translation", "Neural Networks"],
    "language": "en",
    "page_count": 11,
    "other": {}
  }
}
```

---

## Other Step 1 artifacts

- **`full_text.txt`**: Plain UTF-8 text of the full document (all mechanisms that produce text).
- **`full_markdown.md`**: Markdown export of the full document (all mechanisms).
- **VLM Mistral** also writes **`full_markdown.txt`** with the same markdown content.

Encoding for all text files is UTF-8.
