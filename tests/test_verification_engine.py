"""Unit tests for verification_service.py."""

import os
import sys
import unittest

# Ensure the parent directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import verification_service as VERIFICATION


class TestVerificationEngine(unittest.TestCase):
    def setUp(self):
        # Force re-load
        VERIFICATION.get_data(force=True)

    def test_health(self):
        h = VERIFICATION.health()
        self.assertTrue(h["loaded"])
        self.assertIsNone(h["error"])
        self.assertTrue(h["data_exists"])
        self.assertEqual(h["schema_version"], "4a.2")

    def test_data_contract(self):
        d = VERIFICATION.get_data()
        self.assertIn("mode_a", d)
        self.assertIn("mode_b", d)
        self.assertEqual(len(d["mode_a"]["records"]), 37)
        self.assertEqual(len(d["mode_b"]["scenarios"]), 28)

    def test_summary_metrics(self):
        s = VERIFICATION.get_summary(force=True)
        self.assertTrue(s["ok"])
        totals = s["totals"]
        self.assertEqual(totals["total_evaluated_alarms"], 65)
        self.assertEqual(totals["mode_b_scenarios"], 28)
        self.assertEqual(totals["mode_a_records"], 37)
        self.assertEqual(totals["true_alarms"], 4)
        self.assertEqual(totals["false_alarms"], 1)
        self.assertEqual(totals["context_only"], 11)
        self.assertEqual(totals["insufficient_evidence"], 9)
        self.assertEqual(totals["conflicting_evidence"], 1)

    def test_plotly_structure(self):
        s = VERIFICATION.get_summary()
        self.assertIn("plotly", s)
        p = s["plotly"]
        self.assertIn("breakdown", p)
        self.assertIn("dispatch_comparison", p)
        self.assertEqual(len(p["breakdown"]["labels"]), 6)
        self.assertEqual(sum(p["breakdown"]["values"]), 28)

    def test_dispatch(self):
        code, data = VERIFICATION.dispatch("GET", "/api/verification/summary", {}, "")
        self.assertEqual(code, 200)
        self.assertTrue(data["ok"])

        code, _ = VERIFICATION.dispatch("OPTIONS", "/api/verification/summary", {}, "")
        self.assertEqual(code, 204)

        res = VERIFICATION.dispatch("GET", "/api/nonexistent", {}, "")
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
