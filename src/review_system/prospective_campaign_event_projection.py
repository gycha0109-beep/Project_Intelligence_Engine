from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

from .identity import canonical_json_sha256, file_sha256
from .trust_comparison import load_registry, record_decision
from .trust_outcome_declaration import verify_outcome_declaration_file
from .trust_outcome_transport import transport_declared_outcome
from .trust_prospective_evidence import campaign_progress
from .trust_prospective_mutation import _load_review_packet_archive, record_case_review
from .trust_reconciliation_authority import load_source_manifest, manifest_sha256


PROJECTION_SCHEMA_VERSION = "PIE_AUTO4_GOVERNED_EVENT_PROJECTION_V1"
STAGE = "AUTO-4C"
STATUS = "GOVERNED_EVENTS_PROJECTED"
_REVIEW_LEVELS = {"REVIEWED", "AUDITED"}
_PACKET_ID_PREFIX = "REVIEW_PACKET_ID:"
_PACKET_SHA_PREFIX = "REVIEW_PACKET_SHA256:"
_OUTCOME_SOURCE_KEYS = {
    "PRODUCTION_DEFECT": ("defect_registry", "ledger"),
    "CONTROLLED_EVALUATION": ("evaluation_report",),
    "INDEPENDENT_AUDIT": ("audit_artifact", "audit_authority_registry"),
}


class ProspectiveCampaignEventProjectionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _workspace(value: str | Path, label: str) -> Path:
    path = Path(value).expanduser()
    if _path_has_symlink(path):
        raise ProspectiveCampaignEventProjectionError("INVALID_INPUT", f"{label} must not contain symlinks: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ProspectiveCampaignEventProjectionError("INVALID_INPUT", f"{label} does not exist: {path}") from exc
    if not resolved.is_dir():
        raise ProspectiveCampaignEventProjectionError("INVALID_INPUT", f"{label} must be a directory: {resolved}")
    for child in resolved.rglob("*"):
        if child.is_symlink():
            raise ProspectiveCampaignEventProjectionError("INVALID_INPUT", f"{label} contains a symlink: {child}")
    return resolved


def _safe_manifest_file(root: Path, relative: Any, field: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ProspectiveCampaignEventProjectionError("SOURCE_RECONCILIATION_FAILED", f"{field} source path is missing")
    raw = Path(relative)
    if raw.is_absolute() or ".." in raw.parts:
        raise ProspectiveCampaignEventProjectionError("SOURCE_RECONCILIATION_FAILED", f"{field} source path escapes source workspace")
    candidate = root / raw
    if _path_has_symlink(candidate):
        raise ProspectiveCampaignEventProjectionError("SOURCE_RECONCILIATION_FAILED", f"{field} source path contains a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise ProspectiveCampaignEventProjectionError("SOURCE_RECONCILIATION_FAILED", f"{field} source is unavailable") from exc
    if not resolved.is_file():
        raise ProspectiveCampaignEventProjectionError("SOURCE_RECONCILIATION_FAILED", f"{field} source must be a regular file")
    return resolved


def _latest_registry_time(registry: dict[str, Any]) -> str:
    values = [registry["created_at"]]
    values.extend(item["captured_at"] for item in registry.get("assessments", []))
    values.extend(item["occurred_at"] for item in registry.get("events", []))
    return max(values)


def _progress(root: Path, generated_at: str | None = None) -> dict[str, Any]:
    _, registry = load_registry(root / "comparison-registry.json")
    return campaign_progress(root, generated_at=generated_at or _latest_registry_time(registry))


def _require_reconciled(root: Path, label: str) -> dict[str, Any]:
    progress = _progress(root)
    reconciliation = progress.get("reconciliation") if isinstance(progress.get("reconciliation"), dict) else {}
    if reconciliation.get("source_reconciliation_complete") is not True:
        raise ProspectiveCampaignEventProjectionError("SOURCE_RECONCILIATION_FAILED", f"{label} source reconciliation is incomplete")
    if progress.get("automation_authorized") is not False or progress.get("pilot_authorized") is not False:
        raise ProspectiveCampaignEventProjectionError("AUTHORITY_VIOLATION", f"{label} campaign elevated automation/pilot authority")
    return progress


def _review_packet_binding(event: dict[str, Any]) -> tuple[str, str, list[str]]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if payload.get("review_level") not in _REVIEW_LEVELS:
        raise ProspectiveCampaignEventProjectionError(
            "UNSUPPORTED_EVENT",
            f"AUTO-4C accepts only REVIEWED/AUDITED HUMAN_DECISION events: {event.get('event_id')}",
        )
    reasons = payload.get("reason_codes")
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        raise ProspectiveCampaignEventProjectionError("GOVERNED_REVIEW_INVALID", "review reason_codes are invalid")
    ids = [item[len(_PACKET_ID_PREFIX):] for item in reasons if item.startswith(_PACKET_ID_PREFIX)]
    hashes = [item[len(_PACKET_SHA_PREFIX):] for item in reasons if item.startswith(_PACKET_SHA_PREFIX)]
    if len(ids) != 1 or len(hashes) != 1:
        raise ProspectiveCampaignEventProjectionError(
            "GOVERNED_REVIEW_INVALID",
            f"review event must bind exactly one governed packet id/hash: {event.get('event_id')}",
        )
    extra = [
        item for item in reasons
        if not item.startswith(_PACKET_ID_PREFIX) and not item.startswith(_PACKET_SHA_PREFIX)
    ]
    return ids[0], hashes[0], extra


def _tree_digest(root: Path) -> str:
    if not root.is_dir():
        raise ProspectiveCampaignEventProjectionError("GOVERNED_REVIEW_INVALID", f"review archive directory is missing: {root}")
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ProspectiveCampaignEventProjectionError("GOVERNED_REVIEW_INVALID", f"review archive contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ProspectiveCampaignEventProjectionError("GOVERNED_REVIEW_INVALID", f"review archive contains a non-file entry: {path}")
        entries.append({"path": path.relative_to(root).as_posix(), "sha256": file_sha256(path)})
    if not entries:
        raise ProspectiveCampaignEventProjectionError("GOVERNED_REVIEW_INVALID", f"review archive is empty: {root}")
    return canonical_json_sha256(entries)


def _source_assessment(source_registry: dict[str, Any], assessment_id: str) -> dict[str, Any]:
    assessment = next(
        (item for item in source_registry.get("assessments", []) if item.get("assessment_id") == assessment_id),
        None,
    )
    if assessment is None:
        raise ProspectiveCampaignEventProjectionError("SOURCE_EVENT_INVALID", f"source event references unknown assessment: {assessment_id}")
    return assessment


def _require_destination_assessment(
    source_registry: dict[str, Any],
    destination_registry: dict[str, Any],
    assessment_id: str,
) -> None:
    source_assessment = _source_assessment(source_registry, assessment_id)
    destination = next(
        (item for item in destination_registry.get("assessments", []) if item.get("assessment_id") == assessment_id),
        None,
    )
    if destination is None:
        raise ProspectiveCampaignEventProjectionError(
            "ASSESSMENT_REQUIRED",
            f"AUTO-4B assessment projection must precede AUTO-4C: {assessment_id}",
        )
    if destination != source_assessment:
        raise ProspectiveCampaignEventProjectionError(
            "ASSESSMENT_MISMATCH",
            f"destination assessment differs from governed source assessment: {assessment_id}",
        )


def _outcome_source_files(
    source_root: Path,
    source_manifest: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Path]:
    event_id = event["event_id"]
    entries = [
        item for item in source_manifest.get("outcome_sources", [])
        if isinstance(item, dict) and item.get("event_id") == event_id
    ]
    if len(entries) != 1:
        raise ProspectiveCampaignEventProjectionError(
            "SOURCE_RECONCILIATION_FAILED",
            f"source Outcome mapping is missing or ambiguous: {event_id}",
        )
    entry = entries[0]
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    authority = payload.get("outcome_type")
    if authority not in _OUTCOME_SOURCE_KEYS or entry.get("authority_type") != authority:
        raise ProspectiveCampaignEventProjectionError("SOURCE_RECONCILIATION_FAILED", f"source Outcome authority mismatch: {event_id}")
    return {
        key: _safe_manifest_file(source_root, entry.get(key), key)
        for key in _OUTCOME_SOURCE_KEYS[authority]
    }


def _outcome_candidate(source_registry: dict[str, Any], declaration: dict[str, Any]) -> dict[str, Any]:
    outcome = declaration["outcome"]
    candidates = []
    for event in source_registry.get("events", []):
        if event.get("event_type") != "OUTCOME":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        checks = (
            event.get("assessment_id") == declaration["assessment"]["assessment_id"],
            event.get("actor") == declaration["actor"],
            event.get("occurred_at") == declaration["declared_at"],
            payload.get("outcome_type") == outcome["authority_type"],
            payload.get("verdict") == outcome["verdict"],
            payload.get("defect_id") == outcome.get("defect_id"),
        )
        if all(checks):
            candidates.append(event)
    if len(candidates) != 1:
        raise ProspectiveCampaignEventProjectionError(
            "DECLARATION_MISMATCH",
            f"Outcome declaration must identify exactly one source event; found {len(candidates)} for {declaration.get('declaration_id')}",
        )
    return candidates[0]


def _transport_args(sources: dict[str, Path]) -> dict[str, Path | None]:
    return {
        "defect_registry": sources.get("defect_registry"),
        "ledger": sources.get("ledger"),
        "evaluation_report": sources.get("evaluation_report"),
        "audit_artifact": sources.get("audit_artifact"),
        "audit_authority_registry": sources.get("audit_authority_registry"),
    }


def _prepare_outcomes(
    source_root: Path,
    source_registry: dict[str, Any],
    source_manifest: dict[str, Any],
    declarations: Iterable[str | Path],
) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    declaration_paths = [Path(value).expanduser().resolve(strict=True) for value in declarations]
    for path in declaration_paths:
        if path.is_symlink() or not path.is_file():
            raise ProspectiveCampaignEventProjectionError("INVALID_INPUT", f"Outcome declaration must be a regular file: {path}")
        try:
            declaration = verify_outcome_declaration_file(str(path))
        except Exception as exc:
            raise ProspectiveCampaignEventProjectionError("DECLARATION_INVALID", str(exc)) from exc
        if declaration.get("project_id") != source_registry.get("project_id"):
            raise ProspectiveCampaignEventProjectionError("PROJECT_SCOPE_MISMATCH", "Outcome declaration project_id differs from source campaign")
        event = _outcome_candidate(source_registry, declaration)
        if event["event_id"] in specs:
            raise ProspectiveCampaignEventProjectionError("DECLARATION_MISMATCH", f"multiple declarations bind source event: {event['event_id']}")
        sources = _outcome_source_files(source_root, source_manifest, event)
        specs[event["event_id"]] = {"path": path, "declaration": declaration, "sources": sources}

    source_outcomes = [event for event in source_registry.get("events", []) if event.get("event_type") == "OUTCOME"]
    missing = [event["event_id"] for event in source_outcomes if event["event_id"] not in specs]
    if missing:
        raise ProspectiveCampaignEventProjectionError(
            "DECLARATION_REQUIRED",
            "AUTO-4C will not project/infer Outcome events without explicit AUTO-3A declarations: " + ", ".join(missing),
        )
    if len(specs) != len(source_outcomes):
        raise ProspectiveCampaignEventProjectionError("DECLARATION_MISMATCH", "Outcome declaration/source event cardinality mismatch")

    if specs:
        with tempfile.TemporaryDirectory(prefix="pie-auto4c-source-verify-") as temporary:
            verification_root = Path(temporary) / "workspace"
            shutil.copytree(source_root, verification_root, copy_function=shutil.copy2)
            for event in source_outcomes:
                spec = specs[event["event_id"]]
                try:
                    result = transport_declared_outcome(
                        verification_root,
                        declaration=spec["path"],
                        **_transport_args(spec["sources"]),
                    )
                except Exception as exc:
                    raise ProspectiveCampaignEventProjectionError(
                        "DECLARATION_MISMATCH",
                        f"source declaration-bound Outcome verification failed for {event['event_id']}: {exc}",
                    ) from exc
                if result.get("event_id") != event["event_id"] or result.get("idempotent") is not True:
                    raise ProspectiveCampaignEventProjectionError(
                        "DECLARATION_MISMATCH",
                        f"declaration did not reproduce the existing source Outcome authority: {event['event_id']}",
                    )
                if result.get("automatic_outcome_inference") is not False:
                    raise ProspectiveCampaignEventProjectionError("AUTHORITY_VIOLATION", "source Outcome transport enabled automatic inference")
    return specs


def _verify_source_reviews(source_root: Path, source_registry: dict[str, Any]) -> None:
    for event in source_registry.get("events", []):
        if event.get("event_type") == "OUTCOME":
            continue
        if event.get("event_type") != "HUMAN_DECISION":
            raise ProspectiveCampaignEventProjectionError("UNSUPPORTED_EVENT", f"unsupported source event type: {event.get('event_type')}")
        packet_id, packet_sha, _ = _review_packet_binding(event)
        try:
            _load_review_packet_archive(
                source_root,
                project_id=source_registry["project_id"],
                assessment_id=event["assessment_id"],
                review_packet_id=packet_id,
                review_packet_sha256=packet_sha,
            )
        except Exception as exc:
            raise ProspectiveCampaignEventProjectionError(
                "GOVERNED_REVIEW_INVALID",
                f"source governed review packet verification failed for {event['event_id']}: {exc}",
            ) from exc
        review_root = source_root / "cases" / event["assessment_id"] / "reviews" / packet_id
        _tree_digest(review_root)


def _event_prefix(source_registry: dict[str, Any], destination_registry: dict[str, Any]) -> int:
    if source_registry.get("registry_id") != destination_registry.get("registry_id"):
        raise ProspectiveCampaignEventProjectionError(
            "LINEAGE_MISMATCH",
            "source and destination registry_id differ; governed event identifiers cannot be re-authored across campaign lineages",
        )
    source_events = source_registry.get("events", [])
    destination_events = destination_registry.get("events", [])
    shared = min(len(source_events), len(destination_events))
    for index in range(shared):
        if destination_events[index] != source_events[index]:
            raise ProspectiveCampaignEventProjectionError(
                "LINEAGE_MISMATCH",
                f"destination event chain diverges from source at sequence {index + 1}",
            )
    if len(destination_events) > len(source_events):
        return len(source_events)
    return len(destination_events)


def _copy_review_archive(
    source_root: Path,
    destination_root: Path,
    event: dict[str, Any],
    packet_id: str,
    packet_sha: str,
) -> tuple[Path, bool]:
    source_archive = source_root / "cases" / event["assessment_id"] / "reviews" / packet_id
    destination_archive = destination_root / "cases" / event["assessment_id"] / "reviews" / packet_id
    source_digest = _tree_digest(source_archive)
    if destination_archive.exists():
        if _tree_digest(destination_archive) != source_digest:
            raise ProspectiveCampaignEventProjectionError(
                "GOVERNED_REVIEW_CONFLICT",
                f"destination review archive differs from governed source: {packet_id}",
            )
        _load_review_packet_archive(
            destination_root,
            project_id=event.get("project_id") or load_registry(destination_root / "comparison-registry.json")[1]["project_id"],
            assessment_id=event["assessment_id"],
            review_packet_id=packet_id,
            review_packet_sha256=packet_sha,
        )
        return destination_archive, False
    destination_archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_archive, destination_archive, copy_function=shutil.copy2)
    return destination_archive, True


def _project_review(
    source_root: Path,
    destination_root: Path,
    source_registry: dict[str, Any],
    event: dict[str, Any],
) -> None:
    packet_id, packet_sha, extra_reasons = _review_packet_binding(event)
    _, destination_registry = load_registry(destination_root / "comparison-registry.json")
    _require_destination_assessment(source_registry, destination_registry, event["assessment_id"])
    payload = event["payload"]
    candidate = record_decision(
        destination_registry,
        assessment_id=event["assessment_id"],
        review_level=payload["review_level"],
        decision=payload["decision"],
        actor=event["actor"],
        occurred_at=event["occurred_at"],
        confirmed_risk_band=payload.get("confirmed_risk_band"),
        reason_codes=[*extra_reasons, f"{_PACKET_ID_PREFIX}{packet_id}", f"{_PACKET_SHA_PREFIX}{packet_sha}"],
    )
    if candidate["events"][-1] != event:
        raise ProspectiveCampaignEventProjectionError(
            "LINEAGE_MISMATCH",
            f"governed review event cannot be reproduced exactly in destination lineage: {event['event_id']}",
        )

    archive, created = _copy_review_archive(source_root, destination_root, event, packet_id, packet_sha)
    try:
        record_case_review(
            destination_root,
            assessment_id=event["assessment_id"],
            review_level=payload["review_level"],
            decision=payload["decision"],
            actor=event["actor"],
            review_packet_id=packet_id,
            review_packet_sha256=packet_sha,
            occurred_at=event["occurred_at"],
            confirmed_risk_band=payload.get("confirmed_risk_band"),
            reason_codes=extra_reasons,
        )
    except Exception:
        if created:
            shutil.rmtree(archive, ignore_errors=True)
        raise
    _, updated = load_registry(destination_root / "comparison-registry.json")
    if updated["events"][-1] != event:
        raise ProspectiveCampaignEventProjectionError(
            "PROJECTION_COMMIT_MISMATCH",
            f"recorded review event differs from governed source: {event['event_id']}",
        )


def _verify_existing_review_archive(
    source_root: Path,
    destination_root: Path,
    source_registry: dict[str, Any],
    event: dict[str, Any],
) -> None:
    packet_id, packet_sha, _ = _review_packet_binding(event)
    _require_destination_assessment(
        source_registry,
        load_registry(destination_root / "comparison-registry.json")[1],
        event["assessment_id"],
    )
    source_archive = source_root / "cases" / event["assessment_id"] / "reviews" / packet_id
    destination_archive = destination_root / "cases" / event["assessment_id"] / "reviews" / packet_id
    if not destination_archive.exists() or _tree_digest(source_archive) != _tree_digest(destination_archive):
        raise ProspectiveCampaignEventProjectionError(
            "GOVERNED_REVIEW_CONFLICT",
            f"existing destination review event lacks the exact governed source archive: {event['event_id']}",
        )
    _load_review_packet_archive(
        destination_root,
        project_id=source_registry["project_id"],
        assessment_id=event["assessment_id"],
        review_packet_id=packet_id,
        review_packet_sha256=packet_sha,
    )


def _project_once(
    destination_root: Path,
    source_root: Path,
    source_registry: dict[str, Any],
    outcome_specs: dict[str, dict[str, Any]],
) -> dict[str, int]:
    _, destination_registry = load_registry(destination_root / "comparison-registry.json")
    prefix = _event_prefix(source_registry, destination_registry)
    source_events = source_registry.get("events", [])
    counts = {
        "projected_review_count": 0,
        "idempotent_review_count": 0,
        "projected_outcome_count": 0,
        "idempotent_outcome_count": 0,
    }

    for index, event in enumerate(source_events):
        if event.get("event_type") == "HUMAN_DECISION":
            if index < prefix:
                _verify_existing_review_archive(source_root, destination_root, source_registry, event)
                counts["idempotent_review_count"] += 1
                continue
            _project_review(source_root, destination_root, source_registry, event)
            counts["projected_review_count"] += 1
        elif event.get("event_type") == "OUTCOME":
            spec = outcome_specs.get(event["event_id"])
            if spec is None:
                raise ProspectiveCampaignEventProjectionError("DECLARATION_REQUIRED", f"missing declaration for source Outcome: {event['event_id']}")
            _require_destination_assessment(
                source_registry,
                load_registry(destination_root / "comparison-registry.json")[1],
                event["assessment_id"],
            )
            try:
                result = transport_declared_outcome(
                    destination_root,
                    declaration=spec["path"],
                    **_transport_args(spec["sources"]),
                )
            except Exception as exc:
                raise ProspectiveCampaignEventProjectionError(
                    "OUTCOME_TRANSPORT_FAILED",
                    f"declaration-bound Outcome transport failed for {event['event_id']}: {exc}",
                ) from exc
            if result.get("event_id") != event["event_id"]:
                raise ProspectiveCampaignEventProjectionError(
                    "LINEAGE_MISMATCH",
                    f"Outcome transport did not reproduce governed source event id: {event['event_id']}",
                )
            _, updated = load_registry(destination_root / "comparison-registry.json")
            matched = next((item for item in updated["events"] if item["event_id"] == event["event_id"]), None)
            if matched != event:
                raise ProspectiveCampaignEventProjectionError(
                    "PROJECTION_COMMIT_MISMATCH",
                    f"Outcome event differs from governed source: {event['event_id']}",
                )
            if bool(result.get("idempotent")):
                counts["idempotent_outcome_count"] += 1
            else:
                counts["projected_outcome_count"] += 1
        else:
            raise ProspectiveCampaignEventProjectionError("UNSUPPORTED_EVENT", f"unsupported source event type: {event.get('event_type')}")
    return counts


def _projection_hash(report: dict[str, Any]) -> str:
    payload = {
        "schema_version": report["schema_version"],
        "stage": report["stage"],
        "project_id": report["project_id"],
        "source_registry_id": report["source_registry_id"],
        "source_event_count": report["source_event_count"],
        "registry_sha256": report["registry_sha256"],
        "source_manifest_sha256": report["source_manifest_sha256"],
        "campaign_evidence_snapshot_sha256": report["campaign_evidence_snapshot_sha256"],
        "projected_review_count": report["projected_review_count"],
        "idempotent_review_count": report["idempotent_review_count"],
        "projected_outcome_count": report["projected_outcome_count"],
        "idempotent_outcome_count": report["idempotent_outcome_count"],
        "automatic_human_review_inference": report["automatic_human_review_inference"],
        "automatic_outcome_inference": report["automatic_outcome_inference"],
        "automation_authorized": report["automation_authorized"],
        "pilot_authorized": report["pilot_authorized"],
        "merge_authorized": report["merge_authorized"],
        "deploy_authorized": report["deploy_authorized"],
        "production_effect_authorized": report["production_effect_authorized"],
    }
    return canonical_json_sha256(payload)


def project_governed_campaign_events(
    workspace_root: str | Path,
    *,
    source_workspace: str | Path,
    declarations: Iterable[str | Path] = (),
    generated_at: str | None = None,
) -> dict[str, Any]:
    destination = _workspace(workspace_root, "destination campaign workspace")
    source = _workspace(source_workspace, "source campaign workspace")
    if destination == source:
        raise ProspectiveCampaignEventProjectionError("INVALID_INPUT", "source and destination campaign workspaces must differ")

    _, source_registry = load_registry(source / "comparison-registry.json")
    _, source_manifest = load_source_manifest(source / "reconciliation-sources.json")
    _, destination_registry = load_registry(destination / "comparison-registry.json")
    _, destination_manifest = load_source_manifest(destination / "reconciliation-sources.json")
    if source_registry["project_id"] != destination_registry["project_id"]:
        raise ProspectiveCampaignEventProjectionError("PROJECT_SCOPE_MISMATCH", "source and destination project_id differ")

    _require_reconciled(source, "source")
    _require_reconciled(destination, "destination")
    _verify_source_reviews(source, source_registry)
    outcome_specs = _prepare_outcomes(source, source_registry, source_manifest, declarations)

    base_registry_sha = destination_registry["registry_sha256"]
    base_manifest_sha = manifest_sha256(destination_manifest)
    with tempfile.TemporaryDirectory(prefix="pie-auto4c-") as temporary:
        preflight = Path(temporary) / "workspace"
        shutil.copytree(destination, preflight, copy_function=shutil.copy2)
        preflight_counts = _project_once(preflight, source, source_registry, outcome_specs)
        preflight_progress = _require_reconciled(preflight, "preflight")
        _, preflight_registry = load_registry(preflight / "comparison-registry.json")
        _, preflight_manifest = load_source_manifest(preflight / "reconciliation-sources.json")

    _, current_registry = load_registry(destination / "comparison-registry.json")
    _, current_manifest = load_source_manifest(destination / "reconciliation-sources.json")
    if current_registry["registry_sha256"] != base_registry_sha or manifest_sha256(current_manifest) != base_manifest_sha:
        raise ProspectiveCampaignEventProjectionError("CONCURRENT_MUTATION", "destination campaign changed during AUTO-4C preflight")

    actual_counts = _project_once(destination, source, source_registry, outcome_specs)
    actual_progress = _require_reconciled(destination, "destination")
    _, actual_registry = load_registry(destination / "comparison-registry.json")
    _, actual_manifest = load_source_manifest(destination / "reconciliation-sources.json")
    consistency = {
        "counts": actual_counts == preflight_counts,
        "registry_sha256": actual_registry["registry_sha256"] == preflight_registry["registry_sha256"],
        "manifest_sha256": manifest_sha256(actual_manifest) == manifest_sha256(preflight_manifest),
        "evidence_snapshot_sha256": actual_progress["evidence_snapshot_sha256"] == preflight_progress["evidence_snapshot_sha256"],
    }
    failed = sorted(key for key, value in consistency.items() if not value)
    if failed:
        raise ProspectiveCampaignEventProjectionError(
            "PROJECTION_COMMIT_MISMATCH",
            "preflight/commit divergence: " + ", ".join(failed),
        )

    report: dict[str, Any] = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "stage": STAGE,
        "status": STATUS,
        "project_id": actual_registry["project_id"],
        "source_registry_id": source_registry["registry_id"],
        "source_event_count": len(source_registry.get("events", [])),
        **actual_counts,
        "registry_sha256": actual_registry["registry_sha256"],
        "source_manifest_sha256": manifest_sha256(actual_manifest),
        "campaign_id": actual_progress["campaign_id"],
        "campaign_status": actual_progress["status"],
        "campaign_evidence_snapshot_sha256": actual_progress["evidence_snapshot_sha256"],
        "source_reconciliation_complete": actual_progress["reconciliation"]["source_reconciliation_complete"],
        "r0_assessment_count": actual_progress["observation"]["r0_assessment_count"],
        "r0_reviewed_count": actual_progress["observation"]["r0_reviewed_count"],
        "r0_conclusive_outcome_count": actual_progress["observation"]["r0_conclusive_outcome_count"],
        "workspace_mutation_performed": (actual_counts["projected_review_count"] + actual_counts["projected_outcome_count"]) > 0,
        "campaign_thresholds_evaluated": True,
        "human_review_projected": actual_counts["projected_review_count"] > 0,
        "outcome_projected": actual_counts["projected_outcome_count"] > 0,
        "automatic_human_review_inference": False,
        "automatic_outcome_inference": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
        "next_step": "CONTINUE_PROJECT_LOCAL_PROSPECTIVE_EVIDENCE_COLLECTION",
        "projection_sha256": "0" * 64,
    }
    report["projection_sha256"] = _projection_hash(report)
    return report


def write_event_projection_report(path: str | Path, report: dict[str, Any]) -> Path:
    target = Path(path).expanduser()
    if _path_has_symlink(target):
        raise ProspectiveCampaignEventProjectionError("INVALID_INPUT", f"output path must not contain symlinks: {target}")
    target = target.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target
