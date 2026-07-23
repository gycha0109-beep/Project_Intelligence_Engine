import tempfile
import unittest
from pathlib import Path

from review_system.validation import validate_finding_data, validate_profile_file
from tests.helpers import finding


class ValidationTests(unittest.TestCase):
    def test_example_profile_is_valid(self):
        _, errors = validate_profile_file("profiles/examples/journey-connect.yml")
        self.assertEqual([], errors)

    def test_confirmed_requires_e3(self):
        item = finding(
            confidence="CONFIRMED",
            evidence=[{"level": "E2", "type": "path", "location": "src/example.py", "summary": "reachable"}],
            reproduction={"steps": ["one"], "observed": "bad", "expected": "good"},
        )
        errors = validate_finding_data(item)
        self.assertTrue(any("CONFIRMED requires E3" in error for error in errors))

    def test_e3_requires_result(self):
        item = finding(
            confidence="CONFIRMED",
            evidence=[{"level": "E3", "type": "test", "command": "pytest", "summary": "reproduced"}],
            reproduction={"steps": ["one"], "observed": "bad", "expected": "good"},
        )
        errors = validate_finding_data(item)
        self.assertTrue(any("E3+ requires result" in error for error in errors))

    def test_accepted_requires_acceptance_record(self):
        item = finding(status="ACCEPTED", confidence="SUPPORTED", evidence=[{
            "level": "E2", "type": "path", "location": "src/example.py", "summary": "reachable"
        }])
        errors = validate_finding_data(item)
        self.assertTrue(any("acceptance: required" in error for error in errors))

    def test_fixed_confirmed_is_valid_intermediate_state(self):
        item = finding(
            severity="P1",
            status="FIXED",
            confidence="CONFIRMED",
            evidence=[{
                "level": "E3", "type": "test", "command": "pytest", "result": "failed before fix", "summary": "reproduced"
            }],
            reproduction={"steps": ["one"], "observed": "bad", "expected": "good"},
            verification=["pytest"],
        )
        self.assertEqual([], validate_finding_data(item))

    def test_resolved_requires_e5(self):
        item = finding(
            status="FIXED",
            confidence="RESOLVED",
            evidence=[{
                "level": "E4", "type": "runtime", "command": "pytest", "result": "passed", "summary": "runtime passed"
            }],
            reproduction={"steps": ["one"], "observed": "bad", "expected": "good"},
        )
        errors = validate_finding_data(item)
        self.assertTrue(any("RESOLVED requires E5" in error for error in errors))

    def test_empty_scope_is_rejected(self):
        errors = validate_finding_data(finding(scope={"files": [], "symbols": []}))
        self.assertTrue(any("at least one file or symbol" in error for error in errors))

    def test_rejected_status_and_confidence_must_match(self):
        errors = validate_finding_data(finding(status="REJECTED", confidence="SUPPORTED", evidence=[{
            "level": "E2", "type": "path", "location": "src/example.py", "summary": "reachable"
        }]))
        self.assertTrue(any("REJECTED status requires REJECTED confidence" in error for error in errors))

    def test_unknown_pack_is_rejected(self):
        data = Path("profiles/examples/journey-connect.yml").read_text(encoding="utf-8")
        data = data.replace("domain.search", "domain.unknown")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.yml"
            path.write_text(data, encoding="utf-8")
            _, errors = validate_profile_file(path)
            self.assertTrue(any("unknown pack IDs" in error for error in errors))

class AdditionalValidationTests(unittest.TestCase):
    def test_p0_cannot_be_accepted(self):
        item = finding(
            severity="P0",
            confidence="CONFIRMED",
            status="ACCEPTED",
            evidence=[{
                "level": "E3", "type": "test", "command": "pytest", "result": "failed", "summary": "reproduced"
            }],
            reproduction={"steps": ["run"], "observed": "bad", "expected": "good"},
            verification=["pytest"],
            acceptance={"reason": "defer", "owner": "team", "review_by": "2026-12-01"},
        )
        self.assertTrue(any("P0 findings cannot be accepted" in e for e in validate_finding_data(item)))

    def test_p0_must_be_in_gate_block_on(self):
        data = Path("profiles/examples/journey-connect.yml").read_text(encoding="utf-8")
        data = data.replace("block_on: [P0, P1]", "block_on: [P1]")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.yml"
            path.write_text(data, encoding="utf-8")
            _, errors = validate_profile_file(path)
            self.assertTrue(any("P0 must always be blocking" in error for error in errors))

if __name__ == "__main__":
    unittest.main()
