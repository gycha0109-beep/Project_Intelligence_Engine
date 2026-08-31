from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from review_system.calibration_backfill import (
    CalibrationBackfillError,
    build_historical_calibration_record,
)
from review_system.calibration_observation import build_calibration_ledger
from review_system.identity import canonical_json_sha256


BACKFILL_MANIFEST_CONTRACT_VERSION = "PIE_CALIBRATION_HISTORICAL_BACKFILL_V1"
_API = "https://api.github.com"


class GitHubBackfillError(RuntimeError):
    pass


class GitHubClient:
    def __init__(self, token: str | None) -> None:
        self._token = token.strip() if isinstance(token, str) and token.strip() else None

    def _request(self, url: str) -> Request:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "pie-calibration-backfill-v1",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return Request(url, headers=headers)

    def json(self, path: str) -> dict[str, Any]:
        url = path if path.startswith("https://") else f"{_API}{path}"
        try:
            with urlopen(self._request(url), timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubBackfillError(f"GitHub API JSON request failed: {url}: {exc}") from exc

    def bytes(self, url: str) -> bytes:
        try:
            with urlopen(self._request(url), timeout=120) as response:
                return response.read()
        except (HTTPError, URLError) as exc:
            raise GitHubBackfillError(f"GitHub artifact download failed: {url}: {exc}") from exc

    def workflow_runs(self, repository: str) -> Iterable[dict[str, Any]]:
        workflow = quote("pie-prospective.yml", safe="")
        page = 1
        while True:
            query = urlencode(
                {
                    "event": "pull_request",
                    "status": "completed",
                    "per_page": 100,
                    "page": page,
                }
            )
            payload = self.json(f"/repos/{repository}/actions/workflows/{workflow}/runs?{query}")
            runs = payload.get("workflow_runs")
            if not isinstance(runs, list):
                raise GitHubBackfillError(f"{repository}: workflow_runs payload is invalid")
            if not runs:
                return
            for run in runs:
                if not isinstance(run, dict):
                    raise GitHubBackfillError(f"{repository}: workflow run entry is invalid")
                yield run
            if len(runs) < 100:
                return
            page += 1

    def run(self, repository: str, run_id: int) -> dict[str, Any]:
        return self.json(f"/repos/{repository}/actions/runs/{run_id}")

    def artifacts(self, repository: str, run_id: int) -> list[dict[str, Any]]:
        payload = self.json(f"/repos/{repository}/actions/runs/{run_id}/artifacts?per_page=100")
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise GitHubBackfillError(f"{repository} run {run_id}: artifacts payload is invalid")
        return [item for item in artifacts if isinstance(item, dict)]


def _references_revision(run: dict[str, Any], pie_revision: str) -> bool:
    refs = run.get("referenced_workflows")
    if not isinstance(refs, list):
        return False
    return any(
        isinstance(item, dict)
        and (
            item.get("sha") == pie_revision
            or (
                isinstance(item.get("path"), str)
                and item["path"].endswith(f"@{pie_revision}")
            )
        )
        for item in refs
    )


def _full_run_if_needed(client: GitHubClient, repository: str, run: dict[str, Any]) -> dict[str, Any]:
    references = run.get("referenced_workflows")
    if isinstance(references, list) and references:
        return run
    run_id = run.get("id")
    if isinstance(run_id, bool) or not isinstance(run_id, int) or run_id <= 0:
        raise GitHubBackfillError(f"{repository}: workflow run id is invalid")
    return client.run(repository, run_id)


def _find_interface_artifact(
    client: GitHubClient,
    repository: str,
    run: dict[str, Any],
) -> dict[str, Any]:
    run_id = run["id"]
    candidates = [
        artifact
        for artifact in client.artifacts(repository, run_id)
        if isinstance(artifact.get("name"), str)
        and artifact["name"].endswith("-interface")
        and artifact.get("expired") is False
    ]
    if len(candidates) != 1:
        raise GitHubBackfillError(
            f"{repository} run {run_id}: expected exactly one unexpired legacy interface artifact, found {len(candidates)}"
        )
    return candidates[0]


def _write_outputs(
    output: Path,
    *,
    pie_revision: str,
    repositories: list[str],
    records: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    ledger: dict[str, Any],
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    records_path = output / "records.ndjson"
    records_path.write_text(
        "".join(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    sources_path = output / "sources.ndjson"
    sources_path.write_text(
        "".join(json.dumps(source, sort_keys=True, ensure_ascii=False) + "\n" for source in sources),
        encoding="utf-8",
    )
    ledger_path = output / "ledger.json"
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest_body = {
        "contract_version": BACKFILL_MANIFEST_CONTRACT_VERSION,
        "source_pie_revision": pie_revision,
        "repositories": sorted(repository.lower() for repository in repositories),
        "input_record_count": len(records),
        "source_artifact_count": len(sources),
        "unique_calibration_count": ledger["unique_calibration_count"],
        "duplicate_observation_count": ledger["duplicate_observation_count"],
        "ledger_sha256": canonical_json_sha256(ledger),
        "outputs": {
            "records": "records.ndjson",
            "sources": "sources.ndjson",
            "ledger": "ledger.json",
        },
        "authority": {
            "historical_observation_only": True,
            "trust_fact_inferred": False,
            "outcome_inferred": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
    }
    manifest = {**manifest_body, "manifest_sha256": canonical_json_sha256(manifest_body)}
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backfill PIE calibration records from legacy compact interface artifacts."
    )
    parser.add_argument("--repository", action="append", required=True)
    parser.add_argument("--pie-revision", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repositories = list(dict.fromkeys(args.repository))
    client = GitHubClient(os.environ.get("GITHUB_TOKEN"))
    records: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []

    try:
        for repository in repositories:
            matched_runs = 0
            for listed_run in client.workflow_runs(repository):
                run = _full_run_if_needed(client, repository, listed_run)
                if run.get("conclusion") != "success" or not _references_revision(run, args.pie_revision):
                    continue
                matched_runs += 1
                artifact = _find_interface_artifact(client, repository, run)
                archive_url = artifact.get("archive_download_url")
                if not isinstance(archive_url, str) or not archive_url:
                    raise GitHubBackfillError(
                        f"{repository} run {run['id']}: artifact archive_download_url is missing"
                    )
                artifact_zip = client.bytes(archive_url)
                record, source = build_historical_calibration_record(
                    repository=repository,
                    pie_revision=args.pie_revision,
                    run=run,
                    artifact=artifact,
                    artifact_zip=artifact_zip,
                )
                records.append(record)
                sources.append(source)
            print(f"{repository}: matched legacy PIE runs={matched_runs}", flush=True)

        if not records:
            raise GitHubBackfillError("no legacy calibration observations matched the requested PIE revision")

        order = sorted(
            range(len(records)),
            key=lambda index: (
                records[index]["identity"]["repository"],
                records[index]["identity"]["pull_request"],
                records[index]["identity"]["source_revision"],
                records[index]["transport"]["workflow_run_id"],
                records[index]["transport"]["workflow_run_attempt"],
            ),
        )
        records = [records[index] for index in order]
        sources = [sources[index] for index in order]
        ledger = build_calibration_ledger(records)
        _write_outputs(
            Path(args.output),
            pie_revision=args.pie_revision,
            repositories=repositories,
            records=records,
            sources=sources,
            ledger=ledger,
        )
    except (CalibrationBackfillError, GitHubBackfillError, RuntimeError) as exc:
        print(f"calibration backfill failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(
        {
            "input_record_count": ledger["input_record_count"],
            "unique_calibration_count": ledger["unique_calibration_count"],
            "duplicate_observation_count": ledger["duplicate_observation_count"],
            "histograms": ledger["histograms"],
            "lazy_interface": ledger["lazy_interface"],
        },
        sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
