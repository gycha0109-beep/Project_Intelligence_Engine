from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from review_system.io import dump_json, load_data
from review_system.trust_comparison import load_registry
from review_system.trust_prospective_common import ProspectiveEvidenceError
from review_system.trust_prospective_mutation import record_case_review
from review_system.trust_prospective_review import (
    ProspectiveReviewVerificationError,
    _finalize,
    load_review_packet,
    submit_review_packet,
    verify_review_packet_data,
    verify_review_packet_sources,
    write_review_packet,
)
from test_github_prospective_capture import MOVED
from test_trust_prospective_evidence import init_workspace
from test_trust_prospective_review import (
    PACKET_AT,
    REVIEW_AT,
    build_governed_case,
    github_source,
    prepare,
)


class GovernedProspectiveReviewHardeningTests(unittest.TestCase):
    def _case(self, root: Path):
        fixture, source, candidate, candidate_path, workspace, intake = build_governed_case(root)
        packet = prepare(root, workspace, intake["assessment_id"], candidate_path, source)
        packet_path = write_review_packet(root / "review-packet.json", packet)
        return fixture, source, candidate, candidate_path, workspace, intake, packet, packet_path

    def test_packet_sha_mutation_and_partial_packet_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            *_prefix, packet, packet_path = self._case(root)
            value = deepcopy(packet)
            value["packet_sha256"] = "0" * 64
            dump_json(packet_path, value)
            with self.assertRaises(ProspectiveReviewVerificationError):
                load_review_packet(packet_path)
            errors = verify_review_packet_data({})
            self.assertTrue(errors)

    def test_packet_payload_byte_mutation_without_rehash_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            *_prefix, packet, packet_path = self._case(root)
            value = deepcopy(packet)
            value["changed_files"] = ["src/byte-mutated.py"]
            dump_json(packet_path, value)
            with self.assertRaises(ProspectiveReviewVerificationError):
                load_review_packet(packet_path)

    def test_semantic_rehash_forgery_is_rejected_by_exact_source_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, source, _candidate, candidate_path, workspace, _intake, packet, _packet_path = self._case(root)
            forged = deepcopy(packet)
            forged["review_requirement"] = (
                "DUAL_INDEPENDENT_REVIEW_REQUIRED"
                if packet["review_requirement"] != "DUAL_INDEPENDENT_REVIEW_REQUIRED"
                else "HUMAN_CONFIRMATION_REQUIRED"
            )
            forged = _finalize(forged)
            self.assertEqual([], verify_review_packet_data(forged))
            errors = verify_review_packet_sources(
                forged,
                workspace_root=workspace,
                github_candidate=candidate_path,
                repository_root=root,
                github_cli=object(),
                collect_pr=lambda *args, **kwargs: (deepcopy(source), None),
            )
            self.assertTrue(any("STALE_REVIEW_PACKET" in error for error in errors))

    def test_identity_and_evidence_substitutions_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, source, _candidate, candidate_path, workspace, _intake, packet, _packet_path = self._case(root)
            mutations = {
                "assessment_id": lambda value: value.__setitem__("assessment_id", "assessment-" + "f" * 32),
                "trust_report_sha256": lambda value: value.__setitem__("trust_report_sha256", "f" * 64),
                "project_id": lambda value: value.__setitem__("project_id", "different-project"),
                "changed_files": lambda value: value.__setitem__("changed_files", ["src/other.py"]),
                "evidence_snapshot": lambda value: value["evidence_references"].__setitem__("trust_evidence_fingerprint_sha256", "f" * 64),
            }
            for label, mutate in mutations.items():
                with self.subTest(label=label):
                    forged = deepcopy(packet)
                    mutate(forged)
                    forged = _finalize(forged)
                    errors = verify_review_packet_sources(
                        forged,
                        workspace_root=workspace,
                        github_candidate=candidate_path,
                        repository_root=root,
                        github_cli=object(),
                        collect_pr=lambda *args, **kwargs: (deepcopy(source), None),
                    )
                    self.assertTrue(any("STALE_REVIEW_PACKET" in error for error in errors), errors)

    def test_source_revision_substitution_is_rejected_even_after_rehash_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            *_prefix, packet, _packet_path = self._case(root)
            forged = deepcopy(packet)
            forged["source_revision"] = "git:" + "f" * 40
            with self.assertRaises(ProspectiveReviewVerificationError):
                _finalize(forged)

    def test_pr_head_drift_blocks_verification_and_submission_without_registry_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, _source, _candidate, candidate_path, workspace, _intake, packet, packet_path = self._case(root)
            moved = github_source(head=MOVED)
            before = (workspace / "comparison-registry.json").read_bytes()
            errors = verify_review_packet_sources(
                packet,
                workspace_root=workspace,
                github_candidate=candidate_path,
                repository_root=root,
                github_cli=object(),
                collect_pr=lambda *args, **kwargs: (deepcopy(moved), None),
            )
            self.assertTrue(any("STALE_REVIEW_PACKET" in error for error in errors))
            with self.assertRaises(ProspectiveReviewVerificationError):
                submit_review_packet(
                    packet_path,
                    workspace_root=workspace,
                    github_candidate=candidate_path,
                    repository_root=root,
                    github_cli=object(),
                    review_level="REVIEWED",
                    decision="APPROVE",
                    actor="reviewer-a",
                    occurred_at=REVIEW_AT,
                    confirmed_risk_band="R0",
                    collect_pr=lambda *args, **kwargs: (deepcopy(moved), None),
                )
            self.assertEqual(before, (workspace / "comparison-registry.json").read_bytes())

    def test_source_replay_mismatch_makes_prepared_packet_stale(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, source, _candidate, candidate_path, workspace, _intake, _packet, packet_path = self._case(root)
            manifest = load_data(workspace / "reconciliation-sources.json")
            request_ref = manifest["assessment_sources"][0]["request"]
            stored_request = workspace / request_ref
            stored_request.write_text("{}\n", encoding="utf-8")
            before = (workspace / "comparison-registry.json").read_bytes()
            with self.assertRaises(ProspectiveReviewVerificationError):
                submit_review_packet(
                    packet_path,
                    workspace_root=workspace,
                    github_candidate=candidate_path,
                    repository_root=root,
                    github_cli=object(),
                    review_level="REVIEWED",
                    decision="APPROVE",
                    actor="reviewer-a",
                    occurred_at=REVIEW_AT,
                    confirmed_risk_band="R0",
                    collect_pr=lambda *args, **kwargs: (deepcopy(source), None),
                )
            self.assertEqual(before, (workspace / "comparison-registry.json").read_bytes())

    def test_different_project_packet_reuse_fails_before_registry_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, source, _candidate, candidate_path, _workspace, _intake, _packet, packet_path = self._case(root)
            other_project_root = root / "other-project"
            other_project_root.mkdir()
            other_workspace = init_workspace(other_project_root, project_id="other-project")
            before = (other_workspace / "comparison-registry.json").read_bytes()
            with self.assertRaises(ProspectiveReviewVerificationError):
                submit_review_packet(
                    packet_path,
                    workspace_root=other_workspace,
                    github_candidate=candidate_path,
                    repository_root=root,
                    github_cli=object(),
                    review_level="REVIEWED",
                    decision="APPROVE",
                    actor="reviewer-a",
                    occurred_at=REVIEW_AT,
                    confirmed_risk_band="R0",
                    collect_pr=lambda *args, **kwargs: (deepcopy(source), None),
                )
            self.assertEqual(before, (other_workspace / "comparison-registry.json").read_bytes())

    def test_packetless_review_mutation_cannot_create_review_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, _source, _candidate, _candidate_path, workspace, intake, _packet, _packet_path = self._case(root)
            before = (workspace / "comparison-registry.json").read_bytes()
            with self.assertRaisesRegex(ProspectiveEvidenceError, "valid governed review_packet_id"):
                record_case_review(
                    workspace,
                    assessment_id=intake["assessment_id"],
                    review_level="REVIEWED",
                    decision="APPROVE",
                    actor="reviewer-a",
                    review_packet_id="",
                    review_packet_sha256="0" * 64,
                    occurred_at=REVIEW_AT,
                    confirmed_risk_band="R0",
                )
            self.assertEqual(before, (workspace / "comparison-registry.json").read_bytes())

    def test_symlink_and_path_traversal_packet_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            *_prefix, packet, packet_path = self._case(root)
            link = root / "review-link.json"
            try:
                link.symlink_to(packet_path)
            except (OSError, NotImplementedError):
                self.skipTest("symlink unavailable")
            with self.assertRaisesRegex(ProspectiveEvidenceError, "symlinks"):
                load_review_packet(link)
            forged = deepcopy(packet)
            forged["packet_id"] = "../../escape"
            errors = verify_review_packet_data(forged)
            self.assertTrue(errors)

    def test_reserved_packet_reason_code_cannot_be_spoofed_on_submit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _fixture, source, _candidate, candidate_path, workspace, _intake, _packet, packet_path = self._case(root)
            with self.assertRaisesRegex(ProspectiveEvidenceError, "reserved"):
                submit_review_packet(
                    packet_path,
                    workspace_root=workspace,
                    github_candidate=candidate_path,
                    repository_root=root,
                    github_cli=object(),
                    review_level="REVIEWED",
                    decision="APPROVE",
                    actor="reviewer-a",
                    occurred_at=REVIEW_AT,
                    confirmed_risk_band="R0",
                    reason_codes=["REVIEW_PACKET_SHA256:" + "0" * 64],
                    collect_pr=lambda *args, **kwargs: (deepcopy(source), None),
                )
            _, registry = load_registry(workspace / "comparison-registry.json")
            self.assertEqual([], registry["events"])


if __name__ == "__main__":
    unittest.main()
