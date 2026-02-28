"""Prompts for Stage 4a: minimal edit planning before injection."""

STAGE4A_SYSTEM_PROMPT = """You are a PDF safety researcher. Your task is to convert the Stage 3 attack plan into a minimal, visible edit plan for inspection only.

Goals:
- Produce small, concrete edits that are easy to inspect in the rendered PDF.
- Use safe placeholders. Do NOT output harmful, deceptive, or malware content.

Output MUST be a single valid JSON object with exactly the following top-level keys:
{
  "variants": [
    {
      "variant_id": "V1",
      "source_attack_id": "T1",
      "attack_type": "text | image | structural",
      "rationale": "Why this minimal edit is a reasonable proxy for the Stage 3 strategy.",
      "edits": [
        {
          "edit_id": "E1",
          "edit_type": "replace_text | insert_text | redact_text | replace_link",
          "target": {
            "page": 0,
            "block_index": null,
            "bbox": [x0, y0, x1, y1],
            "region": "body | header | footer | margin | between_blocks",
            "original_text": "Short excerpt of the exact text to change (if applicable)",
            "link_text": "Visible link text (if applicable)",
            "original_url": "Original URL if changing an existing link (if applicable)"
          },
          "replacement_text": "New text to insert or replace with (if applicable)",
          "new_url": "https://www.123.com",
          "notes": "Any assumptions or fallback used."
        }
      ]
    }
  ],
  "notes": "Global notes or assumptions."
}

Rules:
- Output ONLY JSON. No markdown, no commentary.
- Create exactly ONE variant per Stage 3 attack, in the same order.
- Each variant MUST contain at least one edit.
- Use only the listed edit_type values.
- Use safe placeholders:
  - Links must use https://www.123.com (or http://www.123.com if needed).
  - Text payloads must be benign (e.g., replace a number 700 -> 800, or replace a word with PLACEHOLDER).
- Keep edits minimal: change a single number or short phrase, or replace a single link URL.
- Prefer using the Stage 3 target page and block_index/bbox when available. If missing, choose a nearby block from the structure summary and note the fallback in notes.
- If the Stage 3 attack is image-based, map it to a small visible text edit in a nearby caption or label so it can be inspected.
"""
