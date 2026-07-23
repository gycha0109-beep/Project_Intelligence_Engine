import unittest

from review_system.gate import calculate_gate_from_run, derive_finding_metrics
from review_system.io import load_data
from review_system.paths import asset
from review_system.validation import validate_review_run_file


class ReviewRunTests(unittest.TestCase):
    def test_sample_run_validates(self):
        _, errors = validate_review_run_file("examples/review-run.sample.json")
        self.assertEqual([], errors)

    def test_finding_metrics_are_derived(self):
        run = load_data("examples/review-run.sample.json")
        run["metrics"]["open_confirmed_p1"] = 0
        policy = load_data(asset("core/default-gate-policy.yml"))
        result = calculate_gate_from_run(run, policy)
        self.assertEqual("HOLD", result["decision"])
        self.assertEqual(1, result["effective_metrics"]["open_confirmed_p1"])
        self.assertIn("open_confirmed_p1", result["metric_discrepancies"])

    def test_closed_finding_not_counted(self):
        finding = load_data("examples/findings.sample.json")[0]
        finding["status"] = "CLOSED"
        finding["confidence"] = "RESOLVED"
        finding["evidence"].append({
            "level": "E5", "type": "test", "command": "./gradlew test",
            "result": "passed after remediation", "summary": "Regression passed."
        })
        self.assertEqual(0, derive_finding_metrics([finding])["open_confirmed_p1"])

if __name__ == "__main__":
    unittest.main()
