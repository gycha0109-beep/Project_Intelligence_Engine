from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.operational_review_action import (
    AUTHORITY_REPOSITORY,
    BRIDGE_CONTRACT,
    CONTRACT_VERSION,
    OperationalReviewActionError,
    OperationalReviewActionRequest,
    OperationalReviewSource,
    _action_hash,
    _normalize_review_input,
    _reject_prior_action,
    _verify_binding_readback,
    run_operational_review_action,
    select_operational_review_source,
    submit_operational_review_action_from_sources,
    verify_operational_review_action_data,
    write_operational_review_action,
)


HEAD = "a" * 40
BASE = "b" * 40
HASH1 = "1" * 64
HASH2 = "2" * 64
PACKET_ID = "prospective-review-packet-" + "c" * 32
ASSESSMENT_ID = "assessment-" + "d" * 32
EVENT_ID = "event-" + "e" * 32


class _CLI:
    pass


def _source(*, packet_id: str = PACKET_ID, packet_sha: str = HASH1) -> OperationalReviewSource:
    candidate = {
        "project_id": "demo",
        "candidate_id": "github-capture-demo",
        "task_id": "github-pr:demo",
        "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
        "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
        "changed_files": ["src/core.py"],
    }
    packet = {
        "packet_id": packet_id,
        "packet_sha256": packet_sha,
        "assessment_id": ASSESSMENT_ID,
    }
    return OperationalReviewSource(
        bridge_root=Path("/tmp/bridge"),
        bundle_root=Path("/tmp/bridge/bundle"),
        workspace_root=Path("/tmp/bridge/workspace"),
        result={
            "bridge_contract": BRIDGE_CONTRACT,
            "deterministic_result_sha256": HASH1,
            "semantic_packet_sha256": HASH2,
        },
        summary={},
        candidate_path=Path("/tmp/bridge/candidate.json"),
        candidate=candidate,
        packet_path=Path("/tmp/bridge/packet.json"),
        packet=packet,
        brief={"brief_sha256": "3" * 64},
        impact={},
        binding=None,
    )


def _action(*, decision: str = "APPROVE", band: str | None = None) -> dict:
    value = {
        "schema_version": "1.0",
        "contract_version": CONTRACT_VERSION,
        "status": "HUMAN_REVIEW_RECORDED",
        "source": {
            "authority_repository": AUTHORITY_REPOSITORY,
            "bridge_contract": BRIDGE_CONTRACT,
            "bridge_deterministic_result_sha256": HASH1,
            "semantic_packet_sha256": HASH2,
            "project_id": "demo",
            "repository": {"hostname": "github.com", "name_with_owner": "demo/repo"},
            "pull_request": {"number": 7, "base_oid": BASE, "head_oid": HEAD},
            "assessment_id": ASSESSMENT_ID,
            "review_packet_id": PACKET_ID,
            "review_packet_sha256": HASH1,
            "review_brief_sha256": "3" * 64,
            "operational_binding_sha256": None,
        },
        "review": {
            "review_level": "REVIEWED",
            "decision": decision,
            "reason": "explicit operator decision",
            "confirmed_risk_band": band,
            "actor": "reviewer",
        },
        "event": {
            "event_id": EVENT_ID,
            "event_sha256": "4" * 64,
            "occurred_at": "2026-08-25T00:00:00Z",
            "registry_sha256": "5" * 64,
            "reason_codes": [
                "explicit operator decision",
                f"REVIEW_PACKET_ID:{PACKET_ID}",
                f"REVIEW_PACKET_SHA256:{HASH1}",
            ],
        },
        "authority": {
            "human_review_recorded": True,
            "outcome_recorded": False,
            "automation_authorized": False,
            "pilot_authorized": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
        "action_sha256": "",
    }
    value["action_sha256"] = _action_hash(value)
    return value


class OperationalReviewActionTests(unittest.TestCase):
    def test_canonical_decisions_are_accepted_without_inventing_risk(self):
        for decision in ("APPROVE", "REQUEST_CHANGES", "HOLD", "REJECT"):
            normalized = _normalize_review_input(
                decision=decision,
                reason="reviewed explicitly",
                actor="alice",
                confirmed_risk_band=None,
            )
            self.assertEqual(decision, normalized[0])
            self.assertIsNone(normalized[3])

    def test_reclassify_requires_explicit_confirmed_risk_band(self):
        with self.assertRaises(OperationalReviewActionError) as caught:
            _normalize_review_input(
                decision="RECLASSIFY",
                reason="risk changed",
                actor="alice",
                confirmed_risk_band=None,
            )
        self.assertEqual("RECLASSIFY_RISK_REQUIRED", caught.exception.code)
        normalized = _normalize_review_input(
            decision="RECLASSIFY",
            reason="risk changed",
            actor="alice",
            confirmed_risk_band="R3",
        )
        self.assertEqual("R3", normalized[3])

    def test_non_reclassify_rejects_confirmed_risk_band(self):
        with self.assertRaises(OperationalReviewActionError) as caught:
            _normalize_review_input(
                decision="APPROVE",
                reason="reviewed",
                actor="alice",
                confirmed_risk_band="R1",
            )
        self.assertEqual("UNEXPECTED_CONFIRMED_RISK", caught.exception.code)

    def test_reason_cannot_forge_packet_binding_reason_code(self):
        with self.assertRaises(OperationalReviewActionError) as caught:
            _normalize_review_input(
                decision="HOLD",
                reason="REVIEW_PACKET_ID:forged",
                actor="alice",
                confirmed_risk_band=None,
            )
        self.assertEqual("INVALID_REASON", caught.exception.code)

    def test_action_contract_records_only_human_review_authority(self):
        value = _action()
        self.assertEqual([], verify_operational_review_action_data(value))
        self.assertTrue(value["authority"]["human_review_recorded"])
        for field in (
            "outcome_recorded",
            "automation_authorized",
            "pilot_authorized",
            "merge_authorized",
            "deploy_authorized",
            "production_effect_authorized",
        ):
            self.assertFalse(value["authority"][field])

    def test_action_authority_or_payload_tamper_is_detected(self):
        forged = deepcopy(_action())
        forged["authority"]["merge_authorized"] = True
        errors = verify_operational_review_action_data(forged)
        self.assertTrue(any("merge_authorized" in error for error in errors))
        self.assertIn("action_sha256 mismatch", errors)

    def test_same_packet_copies_are_deduplicated(self):
        source = _source()
        with patch(
            "review_system.operational_review_action.inspect_operational_review_source",
            return_value=source,
        ):
            selected = select_operational_review_source(
                ["/tmp/a", "/tmp/b"],
                target_repository="demo/repo",
                pull_request=7,
                repository_root="/tmp",
                github_cli=_CLI(),
            )
        self.assertEqual(PACKET_ID, selected.packet["packet_id"])

    def test_distinct_current_packets_fail_closed_as_ambiguous(self):
        other = _source(
            packet_id="prospective-review-packet-" + "f" * 32,
            packet_sha="6" * 64,
        )
        with patch(
            "review_system.operational_review_action.inspect_operational_review_source",
            side_effect=[_source(), other],
        ):
            with self.assertRaises(OperationalReviewActionError) as caught:
                select_operational_review_source(
                    ["/tmp/a", "/tmp/b"],
                    target_repository="demo/repo",
                    pull_request=7,
                    repository_root="/tmp",
                    github_cli=_CLI(),
                )
        self.assertEqual("AMBIGUOUS_REVIEW_PACKET", caught.exception.code)

    def test_prior_action_for_same_assessment_blocks_repeat_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prior = root / "prior"
            prior.mkdir()
            write_operational_review_action(prior / "action.json", _action())
            with self.assertRaises(OperationalReviewActionError) as caught:
                _reject_prior_action([prior], source=_source())
        self.assertEqual("REVIEW_ALREADY_RECORDED", caught.exception.code)

    def test_submit_reuses_existing_submit_review_packet_with_reviewed_level(self):
        source = _source()
        source = OperationalReviewSource(
            **{
                **source.__dict__,
                "workspace_root": Path("/tmp/workspace"),
                "packet_path": Path("/tmp/packet.json"),
                "candidate_path": Path("/tmp/candidate.json"),
            }
        )
        registry = {"registry_sha256": "5" * 64}
        event = {
            "event_id": EVENT_ID,
            "event_sha256": "4" * 64,
            "event_type": "HUMAN_DECISION",
            "occurred_at": "2026-08-25T00:00:00Z",
            "actor": "alice",
            "payload": {
                "review_level": "REVIEWED",
                "decision": "APPROVE",
                "confirmed_risk_band": None,
                "reason_codes": [
                    "reviewed explicitly",
                    f"REVIEW_PACKET_ID:{PACKET_ID}",
                    f"REVIEW_PACKET_SHA256:{HASH1}",
                ],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "action.json"
            with (
                patch(
                    "review_system.operational_review_action.select_operational_review_source",
                    return_value=source,
                ),
                patch("review_system.operational_review_action._reject_prior_action"),
                patch(
                    "review_system.operational_review_action.submit_review_packet",
                    return_value={
                        "event_id": EVENT_ID,
                        "review_packet_archive": "/tmp/archive",
                    },
                ) as submit,
                patch(
                    "review_system.operational_review_action._event_from_registry",
                    return_value=(registry, event),
                ),
            ):
                result = submit_operational_review_action_from_sources(
                    bridge_roots=["/tmp/a"],
                    prior_action_roots=[],
                    target_repository="demo/repo",
                    pull_request=7,
                    repository_root="/tmp",
                    github_cli=_CLI(),
                    decision="APPROVE",
                    reason="reviewed explicitly",
                    actor="alice",
                    output=output,
                )
        kwargs = submit.call_args.kwargs
        self.assertEqual("REVIEWED", kwargs["review_level"])
        self.assertEqual("APPROVE", kwargs["decision"])
        self.assertEqual("alice", kwargs["actor"])
        self.assertEqual(["reviewed explicitly"], kwargs["reason_codes"])
        self.assertEqual("HUMAN_REVIEW_RECORDED", result["status"])
        self.assertTrue(result["authority"]["human_review_recorded"])
        self.assertFalse(result["authority"]["outcome_recorded"])

    def test_base_policy_readback_mismatch_fails_closed(self):
        binding = {"policy": {"path": ".review/operational/policy.yml"}}
        candidate = _source().candidate
        descriptor = {
            "policy_revision": "git:" + BASE,
            "policy_blob_sha": "1" * 40,
            "policy_content_sha256": "2" * 64,
            "policy_sha256": "3" * 64,
        }
        binding["policy"].update(descriptor)
        with (
            patch(
                "review_system.operational_review_action.verify_operational_policy_binding_data",
                return_value=[],
            ),
            patch(
                "review_system.operational_review_action.fetch_base_operational_policy",
                return_value={**descriptor, "policy_sha256": "9" * 64},
            ),
        ):
            with self.assertRaises(OperationalReviewActionError) as caught:
                _verify_binding_readback(
                    binding,
                    candidate=candidate,
                    github_cli=_CLI(),
                    repository_root=Path("/tmp"),
                )
        self.assertEqual("STALE_OPERATIONAL_BINDING", caught.exception.code)

    def test_head_move_after_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initial = {"pull_request": {"head_oid": HEAD, "base_oid": BASE}}
            result = _action()
            result.update({
                "action_file": str(root / "action.json"),
                "bridge_root": str(root / "bridge"),
                "workspace_root": str(root / "workspace"),
                "review_packet_archive": str(root / "archive"),
            })
            moved = {
                "pull_request": {
                    "head_oid": "9" * 40,
                    "base_oid": BASE,
                }
            }
            with (
                patch(
                    "review_system.operational_review_action.discover_operational_review_artifacts",
                    return_value=(initial, [root / "auto2"], []),
                ),
                patch(
                    "review_system.operational_review_action.submit_operational_review_action_from_sources",
                    return_value=result,
                ),
                patch(
                    "review_system.operational_review_action._live_target",
                    return_value=moved,
                ),
            ):
                with self.assertRaises(OperationalReviewActionError) as caught:
                    run_operational_review_action(
                        OperationalReviewActionRequest(
                            target_repository="demo/repo",
                            pull_request=7,
                            decision="APPROVE",
                            reason="reviewed",
                            actor="alice",
                            repository_root=root,
                            artifact_cache_root=root / "cache",
                            output=root / "out.json",
                        ),
                        github_cli=_CLI(),
                    )
        self.assertEqual("STALE_SOURCE_REVISION", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
