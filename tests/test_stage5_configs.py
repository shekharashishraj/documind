from __future__ import annotations

import unittest

from core.stage5.orchestrator import load_demo_doc_ids, load_scenario_specs, load_severity_weights


class Stage5ConfigTests(unittest.TestCase):
    def test_load_scenario_specs(self) -> None:
        specs = load_scenario_specs()
        self.assertGreaterEqual(len(specs), 5)
        self.assertIn("0afbb63ded89d3335a5109f8a9ec4db7", specs)
        self.assertEqual(specs["0afbb63ded89d3335a5109f8a9ec4db7"].scenario, "decision")

    def test_load_demo_doc_ids(self) -> None:
        doc_ids = load_demo_doc_ids()
        self.assertEqual(len(doc_ids), 5)
        self.assertIn("8ee0590e9d4ca0a599fc8ccf1553fc4e", doc_ids)

    def test_load_severity_weights(self) -> None:
        weights = load_severity_weights()
        self.assertEqual(weights["critical"], 4)
        self.assertEqual(weights["high"], 3)
        self.assertEqual(weights["medium"], 2)
        self.assertEqual(weights["low"], 1)


if __name__ == "__main__":
    unittest.main()
