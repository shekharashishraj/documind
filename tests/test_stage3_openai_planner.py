from __future__ import annotations

import unittest

from core.stage3.openai_planner import _canonicalize_text_attack_fields


class Stage3PlannerCanonicalizationTests(unittest.TestCase):
    def test_canonicalizes_missing_semantic_and_mechanism(self) -> None:
        plan = {
            "text_attacks": [
                {
                    "attack_id": "T1",
                    "injection_strategy": "modification",
                    "technique": "font_glyph_remapping",
                }
            ]
        }

        result = _canonicalize_text_attack_fields(plan)
        attack = result["text_attacks"][0]
        self.assertEqual(attack["semantic_edit_strategy"], "update")
        self.assertEqual(attack["injection_strategy"], "modification")
        self.assertEqual(attack["injection_mechanism"], "font_glyph_remapping")

    def test_canonicalizes_mismatch_to_paper_mapping(self) -> None:
        plan = {
            "text_attacks": [
                {
                    "attack_id": "T1",
                    "semantic_edit_strategy": "append",
                    "injection_strategy": "redaction",
                    "injection_mechanism": "visual_overlay",
                    "technique": "dual_layer_overlay",
                }
            ]
        }

        result = _canonicalize_text_attack_fields(plan)
        attack = result["text_attacks"][0]
        self.assertEqual(attack["semantic_edit_strategy"], "append")
        self.assertEqual(attack["injection_strategy"], "addition")
        self.assertEqual(attack["injection_mechanism"], "hidden_text_injection")

    def test_raises_when_semantic_and_legacy_strategy_are_both_missing(self) -> None:
        plan = {
            "text_attacks": [
                {
                    "attack_id": "T1",
                    "technique": "dual_layer_overlay",
                }
            ]
        }
        with self.assertRaises(ValueError):
            _canonicalize_text_attack_fields(plan)

    def test_raises_for_invalid_mechanism(self) -> None:
        plan = {
            "text_attacks": [
                {
                    "attack_id": "T1",
                    "semantic_edit_strategy": "update",
                    "injection_strategy": "modification",
                    "injection_mechanism": "bad_channel",
                }
            ]
        }
        with self.assertRaises(ValueError):
            _canonicalize_text_attack_fields(plan)


if __name__ == "__main__":
    unittest.main()
