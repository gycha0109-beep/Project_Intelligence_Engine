from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

from .defects import load_defect_registry
from .evaluation import load_evaluation_report
from .identity import canonical_json_sha256, file_sha256
from .trust_audit import load_audit_artifact, load_authority_registry
from .trust_comparison import load_registry
from .trust_outcome_declaration import verify_outcome_declaration_file
from .trust_prospective_common import _required_workspace
from .trust_prospective_mutation import _load_review_packet_archive, record_case_outcome
from .trust_reconciliation_authority import manifest_sha256, reconcile_sources


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_AUTO3_DECLARED_OUTCOME_TRANSPORT_V1"
STAGE = "AUTO-3B"
MODE = "EXPLICIT_HUMAN_OUTCOME_TRANSPORT"
STATUS = "DECLARED_OUTCOME_RECORDED_AND_RECONCILED"
NEXT_STEP = "AUTO3C_CONTROLLED_CALIBRATION_REQUIRED"


class OutcomeTransportError(RuntimeError):
    pass


class OutcomeTransportVerificationError(OutcomeTransportError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid declared Outcome transport: " + "; ".join(self.errors))


def _timestamp(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutcomeTransportError(f"{field} must be a non-empty timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise OutcomeTransportError(f"{field} is invalid: {value}") from exc
    if parsed.tzinfo is None:
        raise OutcomeTransportError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_file(path: str | Path | None, field: str) -> Path:
    if path is None:
        raise OutcomeTransportError(f"{field} is required")
    source = Path(path).expanduser()
    if _path_has_symlink(source):
        raise OutcomeTransportError(f"{field} must not contain symlinks: {source}")
    try:
        resolved = source.resolve(strict=True)
    except OSError as exc:
        raise OutcomeTransportError(f"{field} not found: {source}") from exc
    if not resolved.is_file():
        raise OutcomeTransportError(f"{field} must be a regular file: {resolved}")
    return resolved


def _workspace_without_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise OutcomeTransportError(f"campaign workspace must not contain symlinks: {path}")


def _assessment_binding(registry: dict[str, Any], declaration: dict[str, Any]) -> dict[str, Any]:
    assessment_id = declaration["assessment"]["assessment_id"]
    assessment = next(
        (item for item in registry.get("assessments", []) if item.get("assessment_id") == assessment_id),
        None,
    )
    if assessment is None:
        raise OutcomeTransportError(f"declaration references unknown assessment: {assessment_id}")
    expected = declaration["assessment"]
    checks = {
        "source_revision": assessment.get("source_revision") == expected["source_revision"],
        "trust_report_id": assessment.get("trust_report_id") == expected["trust_report_id"],
        "trust_report_sha256": assessment.get("trust_report_sha256") == expected["trust_report_sha256"],
    }
    failed = sorted(key for key, value in checks.items() if not value)
    if failed:
        raise OutcomeTransportError("assessment binding mismatch: " + ", ".join(failed))
    return assessment


def _review_binding(root: Path, registry: dict[str, Any], declaration: dict[str, Any]) -> dict[str, Any]:
    expected = declaration["review"]
    assessment_id = declaration["assessment"]["assessment_id"]
    event = next(
        (item for item in registry.get("events", []) if item.get("event_id") == expected["event_id"]),
        None,
    )
    if event is None:
        raise OutcomeTransportError(f"declaration references unknown review event: {expected['event_id']}")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    reasons = set(payload.get("reason_codes", []))
    checks = {
        "event_sha256": event.get("event_sha256") == expected["event_sha256"],
        "event_type": event.get("event_type") == "HUMAN_DECISION",
        "assessment_id": event.get("assessment_id") == assessment_id,
        "review_level": payload.get("review_level") == expected["review_level"],
        "decision": payload.get("decision") == expected["decision"],
        "review_packet_id": f"REVIEW_PACKET_ID:{expected['review_packet_id']}" in reasons,
        "review_packet_sha256": f"REVIEW_PACKET_SHA256:{expected['review_packet_sha256']}" in reasons,
    }
    failed = sorted(key for key, value in checks.items() if not value)
    if failed:
        raise OutcomeTransportError("prior governed review binding mismatch: " + ", ".join(failed))

    packet = _load_review_packet_archive(
        root,
        project_id=registry["project_id"],
        assessment_id=assessment_id,
        review_packet_id=expected["review_packet_id"],
        review_packet_sha256=expected["review_packet_sha256"],
    )
    declared_at = _timestamp(declaration["declared_at"], "declaration.declared_at")
    reviewed_at = _timestamp(event["occurred_at"], "review event occurred_at")
    if declared_at < reviewed_at:
        raise OutcomeTransportError("Outcome declaration must not precede the bound human review")
    return {"event": event, "packet": packet}


def _source_binding(
    declaration: dict[str, Any],
    *,
    defect_registry: str | Path | None,
    ledger: str | Path | None,
    evaluation_report: str | Path | None,
    audit_artifact: str | Path | None,
    audit_authority_registry: str | Path | None,
) -> dict[str, Path]:
    outcome = declaration["outcome"]
    authority = outcome["authority_type"]
    expected = outcome["source_binding"]
    sources: dict[str, Path] = {}

    if authority == "PRODUCTION_DEFECT":
        registry_path = _safe_file(defect_registry, "defect_registry")
        ledger_path = _safe_file(ledger, "ledger")
        _, registry = load_defect_registry(registry_path)
        if registry.get("registry_sha256") != expected["defect_registry_sha256"]:
            raise OutcomeTransportError("defect registry semantic SHA-256 does not match declaration")
        if file_sha256(ledger_path) != expected["ledger_sha256"]:
            raise OutcomeTransportError("defect ledger file SHA-256 does not match declaration")
        sources.update(defect_registry=registry_path, ledger=ledger_path)
    elif authority == "CONTROLLED_EVALUATION":
        evaluation_path = _safe_file(evaluation_report, "evaluation_report")
        _, evaluation = load_evaluation_report(evaluation_path)
        if evaluation.get("evaluation_id") != expected["evaluation_id"]:
            raise OutcomeTransportError("evaluation_id does not match declaration")
        if evaluation.get("report_sha256") != expected["evaluation_report_sha256"]:
            raise OutcomeTransportError("evaluation report semantic SHA-256 does not match declaration")
        sources["evaluation_report"] = evaluation_path
    elif authority == "INDEPENDENT_AUDIT":
        artifact_path = _safe_file(audit_artifact, "audit_artifact")
        authority_path = _safe_file(audit_authority_registry, "audit_authority_registry")
        _, artifact = load_audit_artifact(artifact_path)
        _, authority_registry = load_authority_registry(authority_path)
        if artifact.get("audit_id") != expected["audit_id"]:
            raise OutcomeTransportError("audit_id does not match declaration")
        if artifact.get("artifact_sha256") != expected["audit_artifact_sha256"]:
            raise OutcomeTransportError("audit artifact semantic SHA-256 does not match declaration")
        if authority_registry.get("registry_sha256") != expected["audit_authority_registry_sha256"]:
            raise OutcomeTransportError("audit authority registry semantic SHA-256 does not match declaration")
        if declaration["actor"] != artifact.get("issuer_subject"):
            raise OutcomeTransportError("Independent Audit declaration actor must equal audit issuer_subject")
        if declaration["outcome"]["verdict"] != artifact.get("verdict"):
            raise OutcomeTransportError("Independent Audit declaration verdict must equal audit artifact verdict")
        sources.update(audit_artifact=artifact_path, audit_authority_registry=authority_path)
    else:
        raise OutcomeTransportError(f"unsupported declaration authority: {authority}")

    return sources


def _record(
    root: Path,
    declaration: dict[str, Any],
    sources: dict[str, Path],
) -> dict[str, Any]:
    outcome = declaration["outcome"]
    return record_case_outcome(
        root,
        assessment_id=declaration["assessment"]["assessment_id"],
        outcome_type=outcome["authority_type"],
        verdict=outcome["verdict"],
        actor=declaration["actor"],
        occurred_at=declaration["declared_at"],
        defect_id=outcome.get("defect_id"),
        evidence_refs=outcome.get("evidence_refs", []),
        defect_registry=sources.get("defect_registry"),
        ledger=sources.get("ledger"),
        evaluation_report=sources.get("evaluation_report"),
        audit_artifact=sources.get("audit_artifact"),
        audit_authority_registry=sources.get("audit_authority_registry"),
    )


def _reconciliation(root: Path, event_id: str, declared_at: str) -> dict[str, Any]:
    report = reconcile_sources(
        root / "comparison-registry.json",
        root / "reconciliation-sources.json",
        generated_at=declared_at,
    )
    item = next(
        (value for value in report.get("outcome_reconciliation", []) if value.get("event_id") == event_id),
        None,
    )
    if item is None:
        raise OutcomeTransportError(f"Outcome reconciliation did not contain event: {event_id}")
    if item.get("status") != "RECONCILED" or item.get("reconciled") is not True:
        raise OutcomeTransportError(
            f"declared Outcome authority did not reconcile: {item.get('status', 'UNKNOWN')}"
        )
    return item


def _transport_projection(
    *,
    declaration: dict[str, Any],
    base_registry_sha256: str,
    base_manifest_sha256: str,
    result: dict[str, Any],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "stage": STAGE,
        "mode": MODE,
        "declaration_id": declaration["declaration_id"],
        "declaration_sha256": declaration["declaration_sha256"],
        "project_id": declaration["project_id"],
        "assessment_id": declaration["assessment"]["assessment_id"],
        "source_revision": declaration["assessment"]["source_revision"],
        "review_event_id": declaration["review"]["event_id"],
        "outcome_type": declaration["outcome"]["authority_type"],
        "verdict": declaration["outcome"]["verdict"],
        "base_registry_sha256": base_registry_sha256,
        "base_manifest_sha256": base_manifest_sha256,
        "event_id": result["event_id"],
        "registry_sha256": result["registry_sha256"],
        "idempotent": bool(result.get("idempotent")),
        "reconciliation_status": reconciliation["status"],
        "authority_key": reconciliation.get("authority_key"),
        "human_outcome_declared": True,
        "automatic_outcome_inference": False,
        "outcome_recorded": True,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
        "status": STATUS,
        "next_step": NEXT_STEP,
    }


def transport_declared_outcome(
    workspace_root: str | Path,
    *,
    declaration: str | Path,
    defect_registry: str | Path | None = None,
    ledger: str | Path | None = None,
    evaluation_report: str | Path | None = None,
    audit_artifact: str | Path | None = None,
    audit_authority_registry: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(workspace_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise OutcomeTransportError(f"campaign workspace must be a directory: {root}")
    _workspace_without_symlinks(root)
    declared = verify_outcome_declaration_file(str(declaration))

    _registry_path, _manifest_path, _policy_path, registry, manifest, _policy = _required_workspace(root)
    if registry["project_id"] != declared["project_id"]:
        raise OutcomeTransportError("declaration project_id does not match campaign workspace")
    _assessment_binding(registry, declared)
    _review_binding(root, registry, declared)
    sources = _source_binding(
        declared,
        defect_registry=defect_registry,
        ledger=ledger,
        evaluation_report=evaluation_report,
        audit_artifact=audit_artifact,
        audit_authority_registry=audit_authority_registry,
    )

    base_registry_sha = registry["registry_sha256"]
    base_manifest_sha = manifest_sha256(manifest)

    with tempfile.TemporaryDirectory(prefix="pie-auto3b-") as temporary:
        preflight_root = Path(temporary) / "workspace"
        shutil.copytree(root, preflight_root, copy_function=shutil.copy2)
        preflight_result = _record(preflight_root, declared, sources)
        preflight_reconciliation = _reconciliation(
            preflight_root,
            preflight_result["event_id"],
            declared["declared_at"],
        )

    _, current_registry = load_registry(root / "comparison-registry.json")
    from .trust_reconciliation_authority import load_source_manifest
    _, current_manifest = load_source_manifest(root / "reconciliation-sources.json")
    if current_registry["registry_sha256"] != base_registry_sha:
        raise OutcomeTransportError("campaign registry changed during AUTO-3B preflight")
    if manifest_sha256(current_manifest) != base_manifest_sha:
        raise OutcomeTransportError("campaign source manifest changed during AUTO-3B preflight")

    actual_result = _record(root, declared, sources)
    actual_reconciliation = _reconciliation(root, actual_result["event_id"], declared["declared_at"])
    consistency = {
        "event_id": actual_result["event_id"] == preflight_result["event_id"],
        "registry_sha256": actual_result["registry_sha256"] == preflight_result["registry_sha256"],
        "idempotent": bool(actual_result.get("idempotent")) == bool(preflight_result.get("idempotent")),
        "reconciliation_status": actual_reconciliation["status"] == preflight_reconciliation["status"],
        "authority_key": actual_reconciliation.get("authority_key") == preflight_reconciliation.get("authority_key"),
    }
    failed = sorted(key for key, value in consistency.items() if not value)
    if failed:
        raise OutcomeTransportVerificationError(
            ["preflight/commit divergence: " + ", ".join(failed)]
        )

    projection = _transport_projection(
        declaration=declared,
        base_registry_sha256=base_registry_sha,
        base_manifest_sha256=base_manifest_sha,
        result=actual_result,
        reconciliation=actual_reconciliation,
    )
    projection["transport_sha256"] = canonical_json_sha256(projection)
    return deepcopy(projection)
