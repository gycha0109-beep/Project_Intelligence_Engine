import copy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout

from review_system.defects import (
    create_defect,
    link_defect_artifact,
    link_finding,
    transition_defect,
)
from review_system.evaluation import run_evaluation, write_evaluation_report
from review_system.identity import canonical_json_sha256
from review_system.io import dump_json, dump_yaml, load_data
from review_system.ledger import import_artifact_directory
from review_system.trust import write_trust_report
from review_system.trust_cli import main as trust_main
from review_system.trust_comparison import (
    capture_assessment,
    new_registry,
    record_outcome,
    write_registry,
)
from review_system.trust_reconciliation import (
    load_reconciliation_report,
    reconcile_sources,
    verify_reconciliation_report_data,
    verify_reconciliation_report_sources,
    write_reconciliation_report,
)
from review_system.trust_reconciliation_cli import main as reconciliation_main
from test_defects import DefectFixture
from test_evaluation import EvaluationFixture
from test_trust_gate import TrustReadinessFixture


class ReconciliationFixture:
    def __init__(self, root: Path):
        self.root = root
        self.trust = TrustReadinessFixture(root)
        self.registry = new_registry("demo", created_at="2026-08-01T00:00:00Z")
        self.registry_path = root / "trust-comparison.json"
        self.sources_path = root / "reconciliation-sources.json"
        self.assessment_sources = []
        self.outcome_sources = []
        self.counter = 0

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def capture(
        self,
        *,
        task_class: str = "routine_code",
        changed_file: str = "src/service.py",
        source_revision: str = "git:" + "a" * 40,
        evaluation_report: Path | None = None,
        generated_at: str = "2026-08-01T01:00:00Z",
    ) -> str:
        self.counter += 1
        self.trust.write_request(task_class=task_class, changed_files=[changed_file])
        request = load_data(self.trust.request)
        request["task_id"] = f"TASK-10C-{self.counter:03d}"
        request["source_revision"] = source_revision
        request_path = self.root / f"trust-request-{self.counter}.json"
        dump_json(request_path, request)
        evaluation = evaluation_report or self.trust.evaluation_report
        report = self.trust.assess(
            generated_at=generated_at,
            request=request_path,
            evaluation_report=evaluation,
        )
        report_path = self.root / f"trust-report-{self.counter}.json"
        write_trust_report(report_path, report)
        self.registry = capture_assessment(
            self.registry,
            report_path,
            captured_at="2026-08-02T00:00:00Z",
        )
        assessment = next(
            item for item in self.registry["assessments"]
            if item["trust_report_id"] == report["report_id"]
            and item["trust_report_sha256"] == report["report_sha256"]
        )
        self.assessment_sources.append({
            "assessment_id": assessment["assessment_id"],
            "trust_report": self.rel(report_path),
            "request": self.rel(request_path),
            "profile": self.rel(self.trust.profile),
            "ledger": self.rel(self.trust.reground_fixture.ledger),
            "policy_registry": self.rel(self.trust.policy_registry),
            "evaluation_report": self.rel(evaluation),
            "reground_report": self.rel(self.trust.reground_report),
            "reground_observations": self.rel(self.trust.observations),
        })
        return assessment["assessment_id"]

    def add_outcome(
        self,
        *,
        assessment_id: str,
        outcome_type: str,
        verdict: str,
        evidence_refs: list[str] | None = None,
        defect_id: str | None = None,
        actor: str = "outcome-authority",
        occurred_at: str = "2026-08-05T00:00:00Z",
    ) -> str:
        self.registry = record_outcome(
            self.registry,
            assessment_id=assessment_id,
            outcome_type=outcome_type,
            verdict=verdict,
            actor=actor,
            occurred_at=occurred_at,
            defect_id=defect_id,
            evidence_refs=evidence_refs or [],
        )
        return self.registry["events"][-1]["event_id"]

    def persist(self) -> None:
        write_registry(self.registry_path, self.registry)
        dump_json(self.sources_path, {
            "schema_version": "1.0",
            "project_id": "demo",
            "assessment_sources": self.assessment_sources,
            "outcome_sources": self.outcome_sources,
        })

    def add_valid_defect_authority(self) -> tuple[str, Path, Path]:
        directory, _ = DefectFixture.run(self.root, "stage10c-defect-run")
        ledger = self.trust.reground_fixture.ledger
        import_artifact_directory(ledger, directory)
        with sqlite3.connect(ledger) as connection:
            finding_id = connection.execute(
                """
                SELECT f.finding_id
                FROM findings f JOIN runs r ON r.run_id = f.run_id
                WHERE r.source_identifier = 'review://demo/stage10c-defect-run'
                """
            ).fetchone()[0]
            artifact_id = connection.execute(
                """
                SELECT a.artifact_id
                FROM artifacts a JOIN runs r ON r.run_id = a.run_id
                WHERE r.source_identifier = 'review://demo/stage10c-defect-run'
                  AND a.relative_path = 'evidence.txt'
                """
            ).fetchone()[0]
        defect = create_defect(
            self.trust.defect_registry,
            ledger,
            signature="stage10c-production-defect",
            title="Stage 10C production defect",
            category="trust.reconciliation",
            actor="defect-owner",
            occurred_at="2026-07-26T00:00:00Z",
        )
        link_finding(
            self.trust.defect_registry,
            ledger,
            finding_id=finding_id,
            defect_id=defect["defect_id"],
            match_method="deterministic_signature",
            confidence=1.0,
            approved_by="defect-reviewer",
            occurred_at="2026-07-27T00:00:00Z",
        )
        link_defect_artifact(
            self.trust.defect_registry,
            ledger,
            defect_id=defect["defect_id"],
            artifact_id=artifact_id,
            relation="reproducer",
            linked_by="defect-reviewer",
            occurred_at="2026-07-28T00:00:00Z",
        )
        transition_defect(
            self.trust.defect_registry,
            ledger,
            defect_id=defect["defect_id"],
            target_status="REPRODUCED",
            actor="defect-owner",
            reason="Reproduced against the assessment revision",
            occurred_at="2026-07-29T00:00:00Z",
        )
        return defect["defect_id"], self.trust.defect_registry, ledger

    def evaluation(self, *, unsafe: bool) -> tuple[Path, dict, str]:
        eval_root = self.root / ("evaluation-unsafe" if unsafe else "evaluation-safe")
        eval_root.mkdir()
        fixture = EvaluationFixture(eval_root)
        dataset = load_data(fixture.dataset)
        revisions = {
            "development": "git:" + "2" * 40,
            "validation": "git:" + "3" * 40,
            "holdout": "git:" + "1" * 40,
        }
        for case in dataset["cases"]:
            case["source_revision"] = revisions[case["split"]]
            if unsafe:
                case["configured_packs"] = []
                case["expected_changed_scope"] = ["src/a.py", "src/b.py"]
                case["expected_packs"] = []
                case["expected_tests"] = []
        dump_yaml(fixture.dataset, dataset)
        report = run_evaluation(
            fixture.dataset,
            fixture.baseline,
            fixture.bad_challenger if unsafe else fixture.challenger,
        )
        write_evaluation_report(fixture.report, report)
        return fixture.report, report, revisions["holdout"]


class TrustReconciliationTests(unittest.TestCase):
    def test_assessment_exact_source_replay_reconciles_report_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            fixture.capture()
            fixture.persist()
            report = reconcile_sources(
                fixture.registry_path,
                fixture.sources_path,
                generated_at="2026-08-18T00:00:00Z",
            )
            self.assertEqual("RECONCILED", report["status"])
            self.assertTrue(report["summary"]["source_reconciliation_complete"])
            self.assertEqual("RECONCILED", report["assessment_reconciliation"][0]["status"])
            self.assertFalse(report["automation_authorized"])
            self.assertFalse(report["pilot_authorized"])
            self.assertEqual([], verify_reconciliation_report_data(report))
            self.assertEqual([], verify_reconciliation_report_sources(
                report,
                registry_path=fixture.registry_path,
                source_manifest_path=fixture.sources_path,
            ))
            payload = json.dumps(report, sort_keys=True)
            self.assertNotIn(str(Path(tmp)), payload)
            self.assertNotIn("outcome-authority", payload)

    def test_same_report_id_with_different_generated_at_detects_report_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            assessment_id = fixture.capture(generated_at="2026-08-01T01:00:00Z")
            source = fixture.assessment_sources[0]
            original_request = root / source["request"]
            alternate = fixture.trust.assess(
                generated_at="2026-08-01T02:00:00Z",
                request=original_request,
            )
            alternate_path = root / "alternate-trust-report.json"
            write_trust_report(alternate_path, alternate)
            self.assertEqual(
                fixture.registry["assessments"][0]["trust_report_id"],
                alternate["report_id"],
            )
            source["trust_report"] = fixture.rel(alternate_path)
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            result = next(item for item in report["assessment_reconciliation"] if item["assessment_id"] == assessment_id)
            self.assertFalse(result["checks"]["report_hash_match"])
            self.assertEqual("SOURCE_HASH_MISMATCH", result["status"])

    def test_request_source_mutation_is_detected_by_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            fixture.capture()
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            request_path = root / fixture.assessment_sources[0]["request"]
            request = load_data(request_path)
            request["changed_files"] = ["src/changed-after-report.py"]
            dump_json(request_path, request)
            errors = verify_reconciliation_report_sources(
                report,
                registry_path=fixture.registry_path,
                source_manifest_path=fixture.sources_path,
            )
            self.assertTrue(errors)

    def test_valid_production_defect_unsafe_reconciles_with_same_revision_reproducer(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            defect_id, registry, ledger = fixture.add_valid_defect_authority()
            assessment_id = fixture.capture()
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="UNSAFE",
                defect_id=defect_id,
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "PRODUCTION_DEFECT",
                "defect_registry": fixture.rel(registry),
                "ledger": fixture.rel(ledger),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            outcome = report["outcome_reconciliation"][0]
            self.assertEqual("RECONCILED", outcome["status"])
            self.assertTrue(outcome["checks"]["revision_relation_match"])
            self.assertTrue(outcome["checks"]["supporting_artifact_present"])
            self.assertEqual("RECONCILED", report["status"])

    def test_production_defect_missing_reference_or_safe_verdict_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            defect_id, registry, ledger = fixture.add_valid_defect_authority()
            assessment_id = fixture.capture()
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="PRODUCTION_DEFECT",
                verdict="SAFE",
                defect_id=defect_id,
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "PRODUCTION_DEFECT",
                "defect_registry": fixture.rel(registry),
                "ledger": fixture.rel(ledger),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            self.assertEqual("OUTCOME_VERDICT_MISMATCH", report["outcome_reconciliation"][0]["status"])
            self.assertEqual("UNRECONCILED", report["status"])

    def test_controlled_evaluation_safe_requires_exact_trust_bound_holdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            evaluation_path, evaluation, revision = fixture.evaluation(unsafe=False)
            assessment_id = fixture.capture(source_revision=revision, evaluation_report=evaluation_path)
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="CONTROLLED_EVALUATION",
                verdict="SAFE",
                evidence_refs=[evaluation["evaluation_id"]],
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "CONTROLLED_EVALUATION",
                "evaluation_report": fixture.rel(evaluation_path),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            outcome = report["outcome_reconciliation"][0]
            self.assertEqual("RECONCILED", outcome["status"])
            self.assertTrue(outcome["checks"]["trust_evaluation_match"])
            self.assertTrue(outcome["checks"]["holdout_match"])
            self.assertTrue(outcome["checks"]["gate_pass"])

    def test_controlled_evaluation_unsafe_requires_matching_protected_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            evaluation_path, evaluation, revision = fixture.evaluation(unsafe=True)
            assessment_id = fixture.capture(source_revision=revision, evaluation_report=evaluation_path)
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="CONTROLLED_EVALUATION",
                verdict="UNSAFE",
                evidence_refs=[evaluation["report_sha256"]],
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "CONTROLLED_EVALUATION",
                "evaluation_report": fixture.rel(evaluation_path),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            outcome = report["outcome_reconciliation"][0]
            self.assertEqual("RECONCILED", outcome["status"])
            self.assertTrue(outcome["checks"]["protected_negative_match"])
            self.assertFalse(outcome["checks"]["gate_pass"])

    def test_evaluation_without_exact_evidence_ref_is_not_reconciled(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            evaluation_path, _, revision = fixture.evaluation(unsafe=False)
            assessment_id = fixture.capture(source_revision=revision, evaluation_report=evaluation_path)
            event_id = fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="CONTROLLED_EVALUATION",
                verdict="SAFE",
                evidence_refs=["pie://evaluation/string-only"],
            )
            fixture.outcome_sources.append({
                "event_id": event_id,
                "authority_type": "CONTROLLED_EVALUATION",
                "evaluation_report": fixture.rel(evaluation_path),
            })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            self.assertEqual("OUTCOME_REFERENCE_MISMATCH", report["outcome_reconciliation"][0]["status"])

    def test_independent_audit_is_provenance_unverified_not_self_asserted(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            assessment_id = fixture.capture()
            fixture.add_outcome(
                assessment_id=assessment_id,
                outcome_type="INDEPENDENT_AUDIT",
                verdict="SAFE",
                evidence_refs=["pie://audit/non-empty"],
                actor="independent-auditor",
            )
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            outcome = report["outcome_reconciliation"][0]
            self.assertEqual("PROVENANCE_UNVERIFIED", outcome["status"])
            self.assertFalse(outcome["reconciled"])
            self.assertEqual("UNRECONCILED", report["status"])

    def test_duplicate_conclusive_authority_is_not_counted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            evaluation_path, evaluation, revision = fixture.evaluation(unsafe=False)
            assessment_id = fixture.capture(source_revision=revision, evaluation_report=evaluation_path)
            for actor in ("eval-a", "eval-b"):
                event_id = fixture.add_outcome(
                    assessment_id=assessment_id,
                    outcome_type="CONTROLLED_EVALUATION",
                    verdict="SAFE",
                    evidence_refs=[evaluation["evaluation_id"]],
                    actor=actor,
                )
                fixture.outcome_sources.append({
                    "event_id": event_id,
                    "authority_type": "CONTROLLED_EVALUATION",
                    "evaluation_report": fixture.rel(evaluation_path),
                })
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            self.assertEqual(2, report["summary"]["duplicate_authority_count"])
            self.assertTrue(all(item["status"] == "DUPLICATE_AUTHORITY" for item in report["outcome_reconciliation"]))
            self.assertEqual(0, report["summary"]["conclusive_outcome_reconciled_count"])

    def test_generated_at_does_not_change_evidence_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            fixture.capture()
            fixture.persist()
            first = reconcile_sources(fixture.registry_path, fixture.sources_path, generated_at="2026-08-18T00:00:00Z")
            second = reconcile_sources(fixture.registry_path, fixture.sources_path, generated_at="2027-08-18T00:00:00Z")
            self.assertEqual(first["report_id"], second["report_id"])
            self.assertEqual(first["evidence_snapshot_sha256"], second["evidence_snapshot_sha256"])
            self.assertNotEqual(first["report_sha256"], second["report_sha256"])

    def test_outer_rehash_cannot_hide_semantic_status_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = ReconciliationFixture(Path(tmp))
            fixture.capture()
            fixture.persist()
            report = reconcile_sources(fixture.registry_path, fixture.sources_path)
            tampered = copy.deepcopy(report)
            tampered["assessment_reconciliation"][0]["status"] = "SOURCE_MISSING"
            payload = copy.deepcopy(tampered)
            payload.pop("report_sha256")
            tampered["report_sha256"] = canonical_json_sha256(payload)
            errors = verify_reconciliation_report_data(tampered)
            self.assertTrue(any("status projection mismatch" in item for item in errors))

    def test_report_round_trip_and_cli_delegation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = ReconciliationFixture(root)
            fixture.capture()
            fixture.persist()
            report_path = root / "reconciliation-report.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, trust_main([
                    "verify-reconciliation-sources", "--sources", str(fixture.sources_path),
                ]))
                self.assertEqual(0, trust_main([
                    "reconcile-sources",
                    "--registry", str(fixture.registry_path),
                    "--sources", str(fixture.sources_path),
                    "--output", str(report_path),
                    "--generated-at", "2026-08-18T00:00:00Z",
                ]))
                self.assertEqual(0, trust_main([
                    "verify-reconciliation-report",
                    "--report", str(report_path),
                    "--registry", str(fixture.registry_path),
                    "--sources", str(fixture.sources_path),
                ]))
                self.assertEqual(0, reconciliation_main([
                    "verify-reconciliation-report", "--report", str(report_path),
                ]))
            source, loaded = load_reconciliation_report(report_path)
            self.assertEqual(report_path.resolve(), source)
            self.assertEqual("RECONCILED", loaded["status"])


if __name__ == "__main__":
    unittest.main()
