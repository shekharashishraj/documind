from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fitz

from core.stage4.injector import run_injection


class Stage4StrategyMappingTests(unittest.TestCase):
    def _make_pdf(self, path: Path) -> None:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 120), "Decision: TARGET")
        doc.save(path)
        doc.close()

    def _write_stage2(self, base_dir: Path) -> None:
        stage2_dir = base_dir / "stage2" / "openai"
        stage2_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": "test",
            "sensitive_elements": [
                {
                    "value_to_replace": "TARGET",
                    "related_elements": [],
                }
            ],
        }
        (stage2_dir / "analysis.json").write_text(json.dumps(payload), encoding="utf-8")

    def _write_stage3(self, base_dir: Path) -> None:
        stage3_dir = base_dir / "stage3" / "openai"
        stage3_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "document_threat_model": {},
            "text_attacks": [
                {
                    "attack_id": "T1",
                    "semantic_edit_strategy": "update",
                    "injection_mechanism": "visual_overlay",
                    "injection_strategy": "modification",
                    "priority": "high",
                    "scope": "everywhere",
                    "search_key": "TARGET",
                    "replacement": "CHANGED",
                    "target": {"page": 0},
                    "payload_description": "replace TARGET with CHANGED",
                    "render_parse_behavior": {"human_sees": "same", "parser_sees": "changed"},
                },
                {
                    "attack_id": "T2",
                    "semantic_edit_strategy": "append",
                    "injection_mechanism": "hidden_text_injection",
                    "injection_strategy": "addition",
                    "priority": "high",
                    "scope": "single_block",
                    "target": {"page": 0},
                    "payload_description": "Inject hidden text: \"HIDDEN PAYLOAD\"",
                    "render_parse_behavior": {"human_sees": "same", "parser_sees": "extra"},
                },
            ],
            "image_attacks": [],
            "structural_attacks": [],
            "defense_considerations": {},
        }
        (stage3_dir / "manipulation_plan.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_auto_mapping_applies_replacement_and_hidden_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            original_pdf = base / "original.pdf"
            self._make_pdf(original_pdf)
            self._write_stage2(base)
            self._write_stage3(base)

            result = run_injection(
                base,
                original_pdf_path=original_pdf,
                mechanism_mode="auto",
            )

            self.assertIsNone(result.get("error"))
            self.assertEqual(len(result.get("replacements") or []), 1)
            self.assertEqual(len(result.get("hidden_text_insertions") or []), 1)
            self.assertEqual((result.get("hidden_text_stats") or {}).get("applied"), 1)
            self.assertTrue(Path(result.get("perturbed_pdf_path") or "").is_file())


if __name__ == "__main__":
    unittest.main()
