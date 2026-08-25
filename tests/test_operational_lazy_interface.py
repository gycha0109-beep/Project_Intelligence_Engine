from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from review_system.operational_lazy_interface import (
    BRIEF_CONTRACT_VERSION,
    LEVEL0_MAX_BYTES,
    LEVEL1_MAX_BYTES,
    SIGNAL_CONTRACT_VERSION,
    build_operational_lazy_interface,
    write_operational_lazy_interface,
)


BASE = "b" * 40


def _summary(status: str = "WAITING_FOR_TRUST_INPUT") -> dict:
    return {"status": status}


def _binding(
    *,
    status: str,
    match_status: str,
    selected: str | None = "recommendation-runtime",
    missing: list[str] | None = None,
    supplied: bool = False,
) -> dict:
    return {
        "status": status,
        "match_status": match_status,
        "matched_operational_classes": (
            ["recommendation-runtime", "recommendation-admin"]
            if match_status == "AMBIGUOUS_POLICY_MATCH"
            else ([selected] if selected else [])
        ),
        "selected_operational_class": selected,
        "requirements": {
            "trust_task_class": "routine_code" if selected else None,
            "required_scenarios": ["allocation-boundary", "snapshot-replay"] if selected else [],
            "required_evidence": ["recommendation-ci"] if selected else [],
        },
        "missing_inputs": missing or [],
        "facts": {
            "supplied": supplied,
            "facts_sha256": "f" * 64 if supplied else None,
            "completed_scenarios": ["allocation-boundary"] if supplied else [],
            "verified_evidence": ["recommendation-ci"] if supplied else [],
            "rollback_evidence": True if supplied else None,
            "replay_evidence": False if supplied else None,
        },
        "policy": {
            "policy_revision": "git:" + BASE,
            "policy_sha256": "1" * 64,
        },
        "binding_sha256": "2" * 64,
    }


class OperationalLazyInterfaceTests(unittest.TestCase):
    def test_no_policy_match_is_clear_and_stops_at_level_zero(self):
        interface = build_operational_lazy_interface(
            summary=_summary(),
            operational_binding=_binding(
                status="NO_POLICY_MATCH",
                match_status="NO_POLICY_MATCH",
                selected=None,
                missing=["NO_OPERATIONAL_CLASS_MATCH"],
            ),
        )
        signal = interface["signal"]
        self.assertEqual(SIGNAL_CONTRACT_VERSION, signal["contract_version"])
        self.assertEqual("CLEAR", signal["status"])
        self.assertEqual("NO_POLICY_MATCH", signal["reason"])
        self.assertEqual("NONE", signal["next"])
        self.assertIsNone(interface["brief"])
        self.assertEqual([], interface["targeted_evidence_ids"])
        self.assertLessEqual(
            len(json.dumps(signal, sort_keys=True, separators=(",", ":")).encode()),
            LEVEL0_MAX_BYTES,
        )

    def test_unique_policy_match_surfaces_compact_class_and_task_mapping(self):
        interface = build_operational_lazy_interface(
            summary=_summary(),
            operational_binding=_binding(
                status="TRUST_REQUEST_MATERIALIZED",
                match_status="UNIQUE_POLICY_MATCH",
                missing=[],
                supplied=True,
            ),
        )
        self.assertEqual("ACTION_REQUIRED", interface["signal"]["status"])
        self.assertEqual("UNIQUE_POLICY_MATCH", interface["signal"]["reason"])
        brief = interface["brief"]
        self.assertIsNotNone(brief)
        self.assertEqual(BRIEF_CONTRACT_VERSION, brief["contract_version"])
        self.assertEqual("recommendation-runtime", brief["operational_class"])
        self.assertEqual("routine_code", brief["trust_task_class"])
        self.assertEqual(["allocation-boundary", "snapshot-replay"], brief["required"]["scenarios"])
        self.assertLessEqual(
            len(json.dumps(brief, sort_keys=True, separators=(",", ":")).encode()),
            LEVEL1_MAX_BYTES,
        )
        serialized = json.dumps(brief, sort_keys=True)
        self.assertNotIn("policy_sha256", serialized)
        self.assertNotIn("binding_sha256", serialized)
        self.assertNotIn("provenance", serialized)

    def test_ambiguous_policy_match_fails_closed_without_class_inference(self):
        binding = _binding(
            status="AMBIGUOUS_POLICY_MATCH",
            match_status="AMBIGUOUS_POLICY_MATCH",
            selected=None,
            missing=["AMBIGUOUS_OPERATIONAL_CLASS_MATCH"],
        )
        interface = build_operational_lazy_interface(summary=_summary(), operational_binding=binding)
        self.assertEqual("ACTION_REQUIRED", interface["signal"]["status"])
        self.assertEqual("AMBIGUOUS_POLICY_MATCH", interface["signal"]["reason"])
        self.assertEqual("READ_POLICY_MATCH_DETAILS", interface["signal"]["next"])
        self.assertIsNone(interface["brief"]["operational_class"])
        self.assertIsNone(interface["brief"]["trust_task_class"])
        self.assertEqual("RESOLVE_POLICY_AMBIGUITY", interface["brief"]["next"])
        detail = interface["targeted_evidence"]["policy-match-details"]
        self.assertEqual("AMBIGUOUS", detail["state"])
        self.assertEqual(
            ["recommendation-admin", "recommendation-runtime"],
            detail["matched_operational_classes"],
        )

    def test_missing_trust_fields_are_surface_only_and_not_fabricated_from_ci(self):
        interface = build_operational_lazy_interface(
            summary=_summary(),
            operational_binding=_binding(
                status="MISSING_TRUST_FIELDS",
                match_status="UNIQUE_POLICY_MATCH",
                missing=[
                    "completed_scenarios",
                    "rollback_evidence",
                    "replay_evidence",
                    "required_evidence:recommendation-ci",
                ],
                supplied=False,
            ),
        )
        self.assertEqual("MISSING_TRUST_FIELDS", interface["signal"]["reason"])
        brief = interface["brief"]
        self.assertFalse(brief["human_action_required"])
        self.assertEqual("PROVIDE_TRUST_INPUT", brief["next"])
        self.assertIn("required_evidence:recommendation-ci", brief["missing"])
        self.assertEqual("SURFACE_TRUST_GAP", brief["agent_directive"]["code"])
        scenario = interface["targeted_evidence"]["scenario:snapshot-replay"]
        evidence = interface["targeted_evidence"]["evidence:recommendation-ci"]
        self.assertEqual("MISSING", scenario["state"])
        self.assertIsNone(scenario["observed"])
        self.assertEqual("MISSING", evidence["state"])
        self.assertIsNone(evidence["observed"])

    def test_ready_unique_match_requests_human_action_only_in_level_one(self):
        interface = build_operational_lazy_interface(
            summary=_summary("READY_FOR_HUMAN_REVIEW"),
            operational_binding=_binding(
                status="TRUST_REQUEST_MATERIALIZED",
                match_status="UNIQUE_POLICY_MATCH",
                supplied=True,
            ),
        )
        self.assertEqual("UNIQUE_POLICY_MATCH", interface["signal"]["reason"])
        self.assertEqual("READ_OPERATIONAL_BRIEF", interface["signal"]["next"])
        self.assertTrue(interface["brief"]["human_action_required"])
        self.assertEqual("REQUEST_HUMAN_REVIEW", interface["brief"]["next"])
        self.assertEqual("REQUEST_CANONICAL_HUMAN_REVIEW", interface["brief"]["agent_directive"]["code"])

    def test_explicit_trust_path_without_policy_can_surface_human_review(self):
        interface = build_operational_lazy_interface(
            summary=_summary("READY_FOR_HUMAN_REVIEW"),
            operational_binding=None,
        )
        self.assertEqual("ACTION_REQUIRED", interface["signal"]["status"])
        self.assertEqual("HUMAN_REVIEW_REQUIRED", interface["signal"]["reason"])
        self.assertTrue(interface["brief"]["human_action_required"])

    def test_written_interface_separates_levels_from_full_capsule(self):
        interface = build_operational_lazy_interface(
            summary=_summary(),
            operational_binding=_binding(
                status="MISSING_TRUST_FIELDS",
                match_status="UNIQUE_POLICY_MATCH",
                missing=["replay_evidence"],
            ),
        )
        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_operational_lazy_interface(tmp, interface)
            root = Path(tmp)
            self.assertTrue((root / "signal.json").is_file())
            self.assertTrue((root / "SIGNAL.txt").is_file())
            self.assertTrue((root / "brief.json").is_file())
            self.assertTrue((root / "targeted" / "index.json").is_file())
            self.assertEqual("SEPARATE_ARTIFACT", manifest["level3"]["full_capsule"])
            self.assertNotIn("capsule", (root / "signal.json").read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
