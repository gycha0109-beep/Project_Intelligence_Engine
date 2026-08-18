from __future__ import annotations

from pathlib import Path
from typing import Any

from .trust_comparison import TrustComparisonError, TrustComparisonVerificationError, load_registry
from .trust_observation import (
    TrustObservationError,
    TrustObservationVerificationError,
    load_report as load_observation_report,
    verify_report_sources as verify_observation_report_sources,
)
from .trust_reconciliation_authority import (
    TrustReconciliationError,
    TrustReconciliationVerificationError,
    load_reconciliation_report,
    verify_reconciliation_report_sources,
)
from . import trust_pilot_review as legacy


PilotSafetyReviewError = legacy.PilotSafetyReviewError
PilotSafetyReviewVerificationError = legacy.PilotSafetyReviewVerificationError
verify_pilot_review_report_data = legacy.verify_pilot_review_report_data
load_pilot_review_report = legacy.load_pilot_review_report
write_pilot_review_report = legacy.write_pilot_review_report


def review_r0_pilot(
    *,
    registry_path: str | Path,
    reconciliation_report_path: str | Path,
    reconciliation_sources_path: str | Path,
    observation_report_path: str | Path,
    observation_policy_path: str | Path,
    generated_at: str | None = None,
) -> dict[str, Any]:
    try:
        registry_source, registry = load_registry(registry_path)
        reconciliation_source, reconciliation_report = load_reconciliation_report(reconciliation_report_path)
        observation_source, observation_report = load_observation_report(observation_report_path)
    except (
        TrustComparisonError,
        TrustComparisonVerificationError,
        TrustReconciliationError,
        TrustReconciliationVerificationError,
        TrustObservationError,
        TrustObservationVerificationError,
        OSError,
        ValueError,
    ) as exc:
        raise PilotSafetyReviewError(str(exc)) from exc

    reconciliation_replay_errors = verify_reconciliation_report_sources(
        reconciliation_report,
        registry_path=registry_source,
        source_manifest_path=reconciliation_sources_path,
    )
    observation_replay_errors = verify_observation_report_sources(
        observation_report,
        registry_path=registry_source,
        policy_path=observation_policy_path,
    )

    sources = {
        "registry": {
            "source": registry_source.name,
            "project_id": registry["project_id"],
            "registry_id": registry["registry_id"],
            "registry_sha256": registry["registry_sha256"],
        },
        "reconciliation_report": {
            "source": reconciliation_source.name,
            "project_id": reconciliation_report["project_id"],
            "report_id": reconciliation_report["report_id"],
            "report_sha256": reconciliation_report["report_sha256"],
            "evidence_snapshot_sha256": reconciliation_report["evidence_snapshot_sha256"],
            "registry_id": reconciliation_report["comparison_registry"]["registry_id"],
            "registry_sha256": reconciliation_report["comparison_registry"]["registry_sha256"],
        },
        "reconciliation_sources": {
            "source": Path(reconciliation_sources_path).name,
            "manifest_sha256": reconciliation_report["source_manifest"]["manifest_sha256"],
        },
        "observation_report": {
            "source": observation_source.name,
            "project_id": observation_report["project_id"],
            "report_id": observation_report["report_id"],
            "report_sha256": observation_report["report_sha256"],
            "registry_id": observation_report["registry"]["registry_id"],
            "registry_sha256": observation_report["registry"]["registry_sha256"],
        },
        "observation_policy": {
            "source": Path(observation_policy_path).name,
            "policy_id": observation_report["policy"]["policy_id"],
            "policy_sha256": observation_report["policy"]["policy_sha256"],
        },
    }
    source_replay = {
        "reconciliation_verified": not reconciliation_replay_errors,
        "observation_verified": not observation_replay_errors,
    }
    return legacy.evaluate_pilot_review_data(
        project_id=registry["project_id"],
        sources=sources,
        source_replay=source_replay,
        reconciliation=legacy._reconciliation_projection(reconciliation_report, registry),
        observation=legacy._observation_projection(observation_report, registry),
        generated_at=generated_at,
    )


def verify_pilot_review_report_sources(
    report: dict[str, Any],
    *,
    registry_path: str | Path,
    reconciliation_report_path: str | Path,
    reconciliation_sources_path: str | Path,
    observation_report_path: str | Path,
    observation_policy_path: str | Path,
) -> list[str]:
    errors = verify_pilot_review_report_data(report)
    if errors:
        return errors
    try:
        replay = review_r0_pilot(
            registry_path=registry_path,
            reconciliation_report_path=reconciliation_report_path,
            reconciliation_sources_path=reconciliation_sources_path,
            observation_report_path=observation_report_path,
            observation_policy_path=observation_policy_path,
            generated_at=report["generated_at"],
        )
    except (PilotSafetyReviewError, OSError, ValueError) as exc:
        return [f"source replay failed: {exc}"]
    fields = (
        "project_id", "sources", "source_replay", "reconciliation", "observation", "checks",
        "blockers", "status", "next_step", "evidence_snapshot_sha256", "review_id", "report_sha256",
    )
    return [f"source replay {field} mismatch" for field in fields if replay.get(field) != report.get(field)]
