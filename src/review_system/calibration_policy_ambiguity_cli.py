from __future__ import annotations

import argparse
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
from .calibration_policy_ambiguity import (
    PolicyAmbiguityDiagnosticError,
    build_historical_policy_ambiguity_observation,
    build_policy_ambiguity_diagnostic,
)
from .identity import canonical_json_sha256


POLICY_AMBIGUITY_MANIFEST_CONTRACT_VERSION = "PIE_HISTORICAL_POLICY_AMBIGUITY_DIAGNOSTIC_MANIFEST_V1"


def _write_outputs(
    output: Path,
    *,
    pie_revision: str,
    repositories: list[str],
    observations: list[dict[str, Any]],
    diagnostic: dict[str, Any],
    excluded_runs: list[dict[str, Any]],
    semantic_artifact_count: int,
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "observations.ndjson").write_text(
        "".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in observations),
        encoding="utf-8",
    )
    (output / "diagnostic.json").write_text(
        json.dumps(diagnostic, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "excluded-runs.ndjson").write_text(
        "".join(json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n" for item in excluded_runs),
        encoding="utf-8",
    )
    manifest_body = {
        "contract_version": POLICY_AMBIGUITY_MANIFEST_CONTRACT_VERSION,
        "source_pie_revision": pie_revision.lower(),
        "repositories": sorted(repository.lower() for repository in repositories),
        "semantic_artifact_count": semantic_artifact_count,
        "policy_ambiguity_observation_count": len(observations),
        "non_policy_ambiguity_semantic_count": semantic_artifact_count - len(observations),
        "excluded_nonsemantic_run_count": len(excluded_runs),
        "unique_calibration_count": diagnostic["unique_calibration_count"],
        "duplicate_observation_count": diagnostic["duplicate_observation_count"],
        "diagnostic_sha256": diagnostic["diagnostic_sha256"],
        "outputs": {
            "observations": "observations.ndjson",
            "diagnostic": "diagnostic.json",
            "excluded_runs": "excluded-runs.ndjson",
        },
        "authority": {
            "historical_observation_only": True,
            "policy_resolution_inferred": False,
            "operational_class_selected": False,
            "trust_fact_inferred": False,
            "human_review_inferred": False,
            "outcome_inferred": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
    }
    manifest = {**manifest_body, "manifest_sha256": canonical_json_sha256(manifest_body)}
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Extract historical AMBIGUOUS_POLICY_MATCH diagnostics from legacy PIE compact "
            "interface artifacts without rerunning evaluation or selecting a policy class."
        )
    )
    parser.add_argument("--repository", action="append", required=True)
    parser.add_argument("--pie-revision", required=True)
    parser.add_argument("--output", required=True)
    return parser


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
            repository_ambiguity = 0
            repository_excluded = 0
            for listed_run in client.workflow_runs(repository):
                run = _full_run_if_needed(client, repository, listed_run)
                if run.get("conclusion") != "success" or not _references_revision(run, args.pie_revision):
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
                observation = build_historical_policy_ambiguity_observation(
                    repository=repository,
                    pie_revision=args.pie_revision,
                    run=run,
                    artifact=artifact,
                    artifact_zip=artifact_zip,
                )
                if observation is not None:
                    observations.append(observation)
                    repository_ambiguity += 1

            print(
                f"{repository}: matched legacy PIE runs={matched_runs} semantic={repository_semantic} "
                f"policy_ambiguity={repository_ambiguity} excluded={repository_excluded}",
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
        diagnostic = build_policy_ambiguity_diagnostic(observations)
        _write_outputs(
            Path(args.output),
            pie_revision=args.pie_revision,
            repositories=repositories,
            observations=observations,
            diagnostic=diagnostic,
            excluded_runs=excluded_runs,
            semantic_artifact_count=semantic_artifact_count,
        )
    except (PolicyAmbiguityDiagnosticError, GitHubBackfillError, RuntimeError) as exc:
        print(f"historical policy-ambiguity diagnostic failed: {exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            {
                "semantic_artifact_count": semantic_artifact_count,
                "policy_ambiguity_observation_count": len(observations),
                "non_policy_ambiguity_semantic_count": semantic_artifact_count - len(observations),
                "excluded_nonsemantic_run_count": len(excluded_runs),
                "unique_calibration_count": diagnostic["unique_calibration_count"],
                "duplicate_observation_count": diagnostic["duplicate_observation_count"],
                "histograms": diagnostic["histograms"],
                "ambiguity": diagnostic["ambiguity"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
