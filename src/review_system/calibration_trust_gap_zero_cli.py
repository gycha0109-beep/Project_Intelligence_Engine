from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any

from .calibration_backfill_cli import (
    GitHubBackfillError,
    GitHubClient,
    _find_interface_artifact,
    _full_run_if_needed,
    _references_revision,
)
from .calibration_trust_gap import (
    TRUST_GAP_DIAGNOSTIC_CONTRACT_VERSION,
    TrustGapDiagnosticError,
    build_historical_trust_gap_observation,
    build_trust_gap_diagnostic,
)
from .calibration_trust_gap_cli import _parser, _write_outputs
from .identity import canonical_json_sha256


def _empty_diagnostic() -> dict[str, Any]:
    body = {
        "contract_version": TRUST_GAP_DIAGNOSTIC_CONTRACT_VERSION,
        "input_observation_count": 0,
        "unique_calibration_count": 0,
        "duplicate_observation_count": 0,
        "histograms": {
            "missing_field": {},
            "missing_set": {},
            "operational_class": {},
            "trust_task_class": {},
            "targeted_gap_id": {},
            "targeted_kind": {},
            "policy_sha256": {},
            "facts_provenance": {},
        },
        "breakdowns": {
            "repository_missing_field": {},
            "trust_task_class_missing_field": {},
            "operational_class_missing_field": {},
            "policy_missing_field": {},
        },
        "targeted": {
            "missing_item_total": 0,
            "all_missing_items_lack_facts_observation_count": 0,
        },
        "authority": {
            "calibration_only": True,
            "trust_fact_inferred": False,
            "human_review_inferred": False,
            "outcome_inferred": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
    }
    return {**body, "diagnostic_sha256": canonical_json_sha256(body)}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repositories = list(dict.fromkeys(args.repository))
    client = GitHubClient(os.environ.get("GITHUB_TOKEN"))
    observations: list[dict[str, Any]] = []
    excluded_runs: list[dict[str, Any]] = []
    semantic_artifact_count = 0

    try:
        for repository in repositories:
            matched_runs = 0
            repository_semantic = 0
            repository_trust_gap = 0
            repository_excluded = 0
            for listed_run in client.workflow_runs(repository):
                run = _full_run_if_needed(client, repository, listed_run)
                if run.get("conclusion") != "success" or not _references_revision(
                    run, args.pie_revision
                ):
                    continue
                matched_runs += 1
                artifact = _find_interface_artifact(client, repository, run)
                if artifact is None:
                    excluded_runs.append(
                        {
                            "repository": repository.lower(),
                            "workflow_run_id": run["id"],
                            "workflow_run_attempt": run.get("run_attempt"),
                            "head_sha": run.get("head_sha"),
                            "pie_revision": args.pie_revision.lower(),
                            "reason": "NO_LEGACY_INTERFACE_ARTIFACT",
                        }
                    )
                    repository_excluded += 1
                    continue

                archive_url = artifact.get("archive_download_url")
                if not isinstance(archive_url, str) or not archive_url:
                    raise GitHubBackfillError(
                        f"{repository} run {run['id']}: artifact archive_download_url is missing"
                    )
                artifact_zip = client.bytes(archive_url)
                semantic_artifact_count += 1
                repository_semantic += 1
                observation = build_historical_trust_gap_observation(
                    repository=repository,
                    pie_revision=args.pie_revision,
                    run=run,
                    artifact=artifact,
                    artifact_zip=artifact_zip,
                )
                if observation is not None:
                    observations.append(observation)
                    repository_trust_gap += 1

            print(
                (
                    f"{repository}: matched legacy PIE runs={matched_runs} "
                    f"semantic={repository_semantic} "
                    f"trust_gap={repository_trust_gap} excluded={repository_excluded}"
                ),
                flush=True,
            )

        observations.sort(
            key=lambda item: (
                item["identity"]["repository"],
                item["identity"]["pull_request"],
                item["identity"]["source_revision"],
                item["transport"]["workflow_run_id"],
                item["transport"]["workflow_run_attempt"],
            )
        )
        diagnostic = (
            build_trust_gap_diagnostic(observations)
            if observations
            else _empty_diagnostic()
        )
        _write_outputs(
            Path(args.output),
            pie_revision=args.pie_revision,
            repositories=repositories,
            observations=observations,
            diagnostic=diagnostic,
            excluded_runs=excluded_runs,
            semantic_artifact_count=semantic_artifact_count,
        )
    except (TrustGapDiagnosticError, GitHubBackfillError, RuntimeError) as exc:
        print(f"historical trust-gap diagnostic failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "semantic_artifact_count": semantic_artifact_count,
                "trust_gap_observation_count": len(observations),
                "non_trust_gap_semantic_count": semantic_artifact_count - len(observations),
                "excluded_nonsemantic_run_count": len(excluded_runs),
                "unique_calibration_count": diagnostic["unique_calibration_count"],
                "duplicate_observation_count": diagnostic["duplicate_observation_count"],
                "histograms": diagnostic["histograms"],
                "targeted": diagnostic["targeted"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
