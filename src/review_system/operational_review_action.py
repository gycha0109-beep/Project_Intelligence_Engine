from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from .github_connector import GitHubCLI, collect_pull_request
from .github_prospective_capture import load_github_prospective_capture_candidate
from .identity import canonical_json_sha256, file_sha256
from .io import load_data
from .operational_policy_binder import (
    fetch_base_operational_policy,
    verify_operational_policy_binding_data,
)
from .operational_review_brief import verify_operational_review_brief_sources
from .paths import asset
from .prospective_evidence_bundle import verify_evidence_bundle
from .prospective_trust_bridge import (
    AUTHORITY_REPOSITORY,
    BRIDGE_CONTRACT,
    RESULT_CONTRACT,
)
from .prospective_trust_bridge_result import verify_stabilized_bridge_result
from .trust_comparison import BANDS, DECISIONS, load_registry
from .trust_prospective_review import (
    load_review_packet,
    submit_review_packet,
    verify_review_packet_sources,
)


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_OPERATIONAL_REVIEW_ACTION_V1"
STATUS = "HUMAN_REVIEW_RECORDED"
REVIEW_LEVEL = "REVIEWED"
AUTO2_ARTIFACT_PREFIX = "pie-auto2-"
ORL4_ARTIFACT_PREFIX = "pie-orl4-"
_SHA40 = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PACKET_REASON_PREFIXES = ("REVIEW_PACKET_ID:", "REVIEW_PACKET_SHA256:")
_AUTHORITY_FIELDS = (
    "outcome_recorded",
    "automation_authorized",
    "pilot_authorized",
    "merge_authorized",
    "deploy_authorized",
    "production_effect_authorized",
)


class OperationalReviewActionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class OperationalReviewActionVerificationError(OperationalReviewActionError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__(
            "REVIEW_ACTION_INVALID",
            "invalid operational review action: " + "; ".join(self.errors),
        )


@dataclass(frozen=True)
class OperationalReviewSource:
    bridge_root: Path
    bundle_root: Path
    workspace_root: Path
    result: dict[str, Any]
    summary: dict[str, Any]
    candidate_path: Path
    candidate: dict[str, Any]
    packet_path: Path
    packet: dict[str, Any]
    brief: dict[str, Any]
    impact: dict[str, Any]
    binding: dict[str, Any] | None

    @property
    def packet_key(self) -> tuple[str, str]:
        return (self.packet["packet_id"], self.packet["packet_sha256"])


@dataclass(frozen=True)
class OperationalReviewActionRequest:
    target_repository: str
    pull_request: int
    decision: str
    reason: str
    actor: str
    repository_root: str | Path
    artifact_cache_root: str | Path
    confirmed_risk_band: str | None = None
    occurred_at: str | None = None
    output: str | Path | None = None


def _path_has_symlink(path: Path) -> bool:
    absolute = path.expanduser().absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_existing_dir(path: str | Path, label: str) -> Path:
    raw = Path(path).expanduser()
    if _path_has_symlink(raw):
        raise OperationalReviewActionError(
            "UNSAFE_SOURCE_PATH",
            f"{label} must not contain symlinks: {raw}",
        )
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise OperationalReviewActionError(
            "SOURCE_NOT_FOUND",
            f"{label} not found: {raw}",
        ) from exc
    if not resolved.is_dir():
        raise OperationalReviewActionError(
            "SOURCE_NOT_FOUND",
            f"{label} must be a directory: {resolved}",
        )
    return resolved


def _safe_output(path: str | Path, label: str) -> Path:
    raw = Path(path).expanduser()
    if _path_has_symlink(raw):
        raise OperationalReviewActionError(
            "UNSAFE_OUTPUT_PATH",
            f"{label} must not contain symlinks: {raw}",
        )
    return raw.resolve()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if _path_has_symlink(path):
        raise OperationalReviewActionError(
            "UNSAFE_SOURCE_PATH",
            f"{label} must not contain symlinks: {path}",
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise OperationalReviewActionError(
            "SOURCE_NOT_FOUND",
            f"{label} not found: {path}",
        ) from exc
    if not resolved.is_file():
        raise OperationalReviewActionError(
            "SOURCE_NOT_FOUND",
            f"{label} must be a regular file: {resolved}",
        )
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperationalReviewActionError(
            "SOURCE_INVALID",
            f"{label} is not valid UTF-8 JSON: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise OperationalReviewActionError(
            "SOURCE_INVALID",
            f"{label} must contain a JSON object",
        )
    return value


def _schema() -> dict[str, Any]:
    value = load_data(asset("schemas/operational-review-action.schema.json"))
    if not isinstance(value, dict):
        raise OperationalReviewActionError(
            "CONTRACT_INVALID",
            "operational review action schema must contain an object",
        )
    return value


def _schema_errors(value: Any) -> list[str]:
    validator = Draft202012Validator(_schema(), format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(
        validator.iter_errors(value),
        key=lambda item: list(item.absolute_path),
    ):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _action_hash(value: Mapping[str, Any]) -> str:
    payload = deepcopy(dict(value))
    payload.pop("action_sha256", None)
    return canonical_json_sha256(payload)


def verify_operational_review_action_data(value: Any) -> list[str]:
    errors = _schema_errors(value)
    if not isinstance(value, dict):
        return sorted(set(errors or ["action must contain an object"]))
    review = value.get("review", {})
    authority = value.get("authority", {})
    if review.get("review_level") != REVIEW_LEVEL:
        errors.append("review.review_level must remain REVIEWED")
    decision = review.get("decision")
    confirmed = review.get("confirmed_risk_band")
    if decision == "RECLASSIFY" and confirmed is None:
        errors.append("RECLASSIFY requires confirmed_risk_band")
    if decision != "RECLASSIFY" and confirmed is not None:
        errors.append("confirmed_risk_band is only valid for RECLASSIFY")
    if authority.get("human_review_recorded") is not True:
        errors.append("authority.human_review_recorded must be true")
    for field in _AUTHORITY_FIELDS:
        if authority.get(field) is not False:
            errors.append(f"authority.{field} must remain false")
    if value.get("action_sha256") != _action_hash(value):
        errors.append("action_sha256 mismatch")
    return sorted(set(errors))


def write_operational_review_action(
    path: str | Path,
    value: Mapping[str, Any],
) -> Path:
    errors = verify_operational_review_action_data(value)
    if errors:
        raise OperationalReviewActionVerificationError(errors)
    target = _safe_output(path, "operational review action output")
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(dict(value), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor, name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".tmp",
        dir=target.parent,
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _normalize_repository(value: str) -> str:
    repository = value.strip()
    if (
        repository.count("/") != 1
        or repository.startswith("/")
        or repository.endswith("/")
        or any(not part for part in repository.split("/"))
    ):
        raise OperationalReviewActionError(
            "INVALID_INPUT",
            "target_repository must be owner/name",
        )
    return repository


def _normalize_review_input(
    *,
    decision: str,
    reason: str,
    actor: str,
    confirmed_risk_band: str | None,
) -> tuple[str, str, str, str | None]:
    normalized_decision = decision.strip().upper()
    if normalized_decision not in DECISIONS:
        raise OperationalReviewActionError(
            "INVALID_DECISION",
            "decision must be one of APPROVE, REQUEST_CHANGES, HOLD, REJECT, RECLASSIFY",
        )
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise OperationalReviewActionError(
            "INVALID_REASON",
            "reason must be a non-empty string",
        )
    if len(normalized_reason) > 1000 or _CONTROL.search(normalized_reason):
        raise OperationalReviewActionError(
            "INVALID_REASON",
            "reason must be at most 1000 characters and contain no control characters",
        )
    if normalized_reason.startswith(_PACKET_REASON_PREFIXES):
        raise OperationalReviewActionError(
            "INVALID_REASON",
            "reason must not use reserved review-packet binding prefixes",
        )
    normalized_actor = actor.strip()
    if not normalized_actor or _CONTROL.search(normalized_actor):
        raise OperationalReviewActionError(
            "INVALID_ACTOR",
            "actor must be a non-empty printable string",
        )
    band = (
        confirmed_risk_band.strip().upper()
        if isinstance(confirmed_risk_band, str) and confirmed_risk_band.strip()
        else None
    )
    if normalized_decision == "RECLASSIFY":
        if band not in BANDS:
            raise OperationalReviewActionError(
                "RECLASSIFY_RISK_REQUIRED",
                "RECLASSIFY requires confirmed_risk_band R0-R4",
            )
    elif band is not None:
        raise OperationalReviewActionError(
            "UNEXPECTED_CONFIRMED_RISK",
            "confirmed_risk_band is only valid for RECLASSIFY",
        )
    return normalized_decision, normalized_reason, normalized_actor, band


def _artifact_prefix(
    repository: str,
    pull_request: int,
    head_oid: str,
    *,
    orl4: bool,
) -> str:
    safe_repo = repository.replace("/", "-")
    prefix = ORL4_ARTIFACT_PREFIX if orl4 else AUTO2_ARTIFACT_PREFIX
    return f"{prefix}{safe_repo}-pr-{pull_request}-{head_oid[:12]}-"


def _github_json(
    github_cli: GitHubCLI,
    args: Sequence[str],
    *,
    cwd: Path,
) -> dict[str, Any]:
    result = github_cli.run(list(args), cwd=cwd)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OperationalReviewActionError(
            "GITHUB_READBACK_FAILED",
            f"GitHub command returned invalid JSON: {' '.join(args)}",
        ) from exc
    if not isinstance(value, dict):
        raise OperationalReviewActionError(
            "GITHUB_READBACK_FAILED",
            f"GitHub command must return an object: {' '.join(args)}",
        )
    return value


def _live_target(
    github_cli: GitHubCLI,
    *,
    repository_root: Path,
    repository: str,
    pull_request: int,
) -> dict[str, Any]:
    source, _ = collect_pull_request(
        github_cli,
        str(pull_request),
        cwd=repository_root,
        repository=repository,
        include_diff=False,
        include_discussion=False,
    )
    live_repository = source.get("repository", {})
    live_pr = source.get("pull_request", {})
    if (
        str(live_repository.get("name_with_owner") or "").lower()
        != repository.lower()
    ):
        raise OperationalReviewActionError(
            "TARGET_BINDING_FAILED",
            "live GitHub repository does not match target_repository",
        )
    if live_pr.get("number") != pull_request:
        raise OperationalReviewActionError(
            "TARGET_BINDING_FAILED",
            "live GitHub pull request number does not match",
        )
    if str(live_pr.get("state") or "").upper() != "OPEN":
        raise OperationalReviewActionError(
            "TARGET_BINDING_FAILED",
            "target pull request must remain open",
        )
    head = str(live_pr.get("head_oid") or "").lower()
    base = str(live_pr.get("base_oid") or "").lower()
    if _SHA40.fullmatch(head) is None or _SHA40.fullmatch(base) is None:
        raise OperationalReviewActionError(
            "TARGET_BINDING_FAILED",
            "live GitHub pull request must expose exact head and base SHAs",
        )
    return source


def _list_authority_artifacts(
    github_cli: GitHubCLI,
    *,
    cwd: Path,
    prefixes: Sequence[str],
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        payload = _github_json(
            github_cli,
            [
                "api",
                f"repos/{AUTHORITY_REPOSITORY}/actions/artifacts?per_page=100&page={page}",
            ],
            cwd=cwd,
        )
        artifacts = payload.get("artifacts", [])
        if not isinstance(artifacts, list):
            raise OperationalReviewActionError(
                "GITHUB_READBACK_FAILED",
                "GitHub artifact listing is invalid",
            )
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            name = artifact.get("name")
            if not isinstance(name, str):
                continue
            if not any(name.startswith(prefix) for prefix in prefixes):
                continue
            if artifact.get("expired") is True:
                continue
            workflow_run = artifact.get("workflow_run")
            run_id = workflow_run.get("id") if isinstance(workflow_run, dict) else None
            artifact_id = artifact.get("id")
            if not isinstance(run_id, int) or not isinstance(artifact_id, int):
                continue
            output.append(
                {
                    "id": artifact_id,
                    "name": name,
                    "run_id": run_id,
                    "created_at": artifact.get("created_at"),
                }
            )
        if len(artifacts) < 100:
            break
    output.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            int(item["id"]),
        ),
        reverse=True,
    )
    return output


def _download_artifacts(
    github_cli: GitHubCLI,
    *,
    cwd: Path,
    artifacts: Sequence[Mapping[str, Any]],
    destination: Path,
) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=True)
    roots: list[Path] = []
    for item in artifacts:
        artifact_id = int(item["id"])
        run_id = int(item["run_id"])
        name = str(item["name"])
        target = destination / str(artifact_id)
        if target.exists():
            shutil.rmtree(target)
        github_cli.run(
            [
                "run",
                "download",
                str(run_id),
                "--repo",
                AUTHORITY_REPOSITORY,
                "--name",
                name,
                "--dir",
                str(target),
            ],
            cwd=cwd,
        )
        roots.append(target)
    return roots


def discover_operational_review_artifacts(
    github_cli: GitHubCLI,
    *,
    repository_root: str | Path,
    cache_root: str | Path,
    target_repository: str,
    pull_request: int,
) -> tuple[dict[str, Any], list[Path], list[Path]]:
    root = _safe_existing_dir(repository_root, "target repository root")
    repository = _normalize_repository(target_repository)
    if pull_request < 1:
        raise OperationalReviewActionError(
            "INVALID_INPUT",
            "pull_request must be at least 1",
        )
    source = _live_target(
        github_cli,
        repository_root=root,
        repository=repository,
        pull_request=pull_request,
    )
    head = str(source["pull_request"]["head_oid"]).lower()
    auto2_prefix = _artifact_prefix(repository, pull_request, head, orl4=False)
    orl4_prefix = _artifact_prefix(repository, pull_request, head, orl4=True)
    artifacts = _list_authority_artifacts(
        github_cli,
        cwd=root,
        prefixes=(auto2_prefix, orl4_prefix),
    )
    auto2 = [item for item in artifacts if str(item["name"]).startswith(auto2_prefix)]
    prior = [item for item in artifacts if str(item["name"]).startswith(orl4_prefix)]
    cache = _safe_output(cache_root, "artifact cache root")
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)
    auto2_roots = _download_artifacts(
        github_cli,
        cwd=root,
        artifacts=auto2,
        destination=cache / "auto2",
    )
    prior_roots = _download_artifacts(
        github_cli,
        cwd=root,
        artifacts=prior,
        destination=cache / "orl4",
    )
    return source, auto2_roots, prior_roots


def _find_single_bundle(bridge_root: Path) -> Path:
    bundle_parent = bridge_root / "automation" / "bundles"
    if not bundle_parent.is_dir() or _path_has_symlink(bundle_parent):
        raise OperationalReviewActionError(
            "BRIDGE_SOURCE_INVALID",
            f"AUTO-2 bridge bundles directory is missing or unsafe: {bundle_parent}",
        )
    packets = sorted(bundle_parent.glob("*/review/packet.json"))
    safe_packets = [path for path in packets if not _path_has_symlink(path)]
    if len(safe_packets) != 1:
        raise OperationalReviewActionError(
            "BRIDGE_SOURCE_INVALID",
            f"AUTO-2 bridge must contain exactly one governed packet bundle; found {len(safe_packets)}",
        )
    return safe_packets[0].parent.parent.resolve()


def _verify_binding_readback(
    binding: dict[str, Any],
    *,
    candidate: dict[str, Any],
    github_cli: GitHubCLI,
    repository_root: Path,
) -> None:
    errors = verify_operational_policy_binding_data(binding)
    if errors:
        raise OperationalReviewActionVerificationError(
            [f"operational binding: {error}" for error in errors]
        )
    policy = binding.get("policy", {})
    descriptor = fetch_base_operational_policy(
        github_cli,
        repository=candidate["repository"]["name_with_owner"],
        base_revision=candidate["pull_request"]["base_oid"],
        project_id=candidate["project_id"],
        policy_path=policy["path"],
        cwd=repository_root,
    )
    if descriptor is None:
        raise OperationalReviewActionError(
            "STALE_OPERATIONAL_BINDING",
            "operational policy is no longer readable from the exact PR base revision",
        )
    expected = {
        "policy_revision": descriptor["policy_revision"],
        "policy_blob_sha": descriptor["policy_blob_sha"],
        "policy_content_sha256": descriptor["policy_content_sha256"],
        "policy_sha256": descriptor["policy_sha256"],
    }
    actual = {field: policy.get(field) for field in expected}
    if actual != expected:
        raise OperationalReviewActionError(
            "STALE_OPERATIONAL_BINDING",
            "operational binding no longer matches exact base-revision policy readback",
        )


def inspect_operational_review_source(
    bridge_root: str | Path,
    *,
    target_repository: str,
    pull_request: int,
    repository_root: str | Path,
    github_cli: GitHubCLI,
) -> OperationalReviewSource:
    root = _safe_existing_dir(bridge_root, "AUTO-2 bridge artifact")
    target_root = _safe_existing_dir(repository_root, "target repository root")
    repository = _normalize_repository(target_repository)
    result = _load_json_object(root / "result.json", "AUTO-2 bridge result")
    if result.get("result_contract") != RESULT_CONTRACT:
        raise OperationalReviewActionError(
            "BRIDGE_SOURCE_INVALID",
            "AUTO-2 bridge result contract mismatch",
        )
    if result.get("bridge_contract") != BRIDGE_CONTRACT:
        raise OperationalReviewActionError(
            "BRIDGE_SOURCE_INVALID",
            "AUTO-2 bridge contract mismatch",
        )
    if result.get("status") != "READY_FOR_HUMAN_REVIEW":
        raise OperationalReviewActionError(
            "BRIDGE_SOURCE_INVALID",
            "AUTO-2 bridge source is not READY_FOR_HUMAN_REVIEW",
        )
    for field in (
        "human_review_recorded",
        "outcome_recorded",
        "automation_authorized",
        "pilot_authorized",
        "merge_authorized",
        "deploy_authorized",
        "production_effect_authorized",
    ):
        if result.get(field) is not False:
            raise OperationalReviewActionError(
                "AUTHORITY_BOUNDARY_VIOLATION",
                f"AUTO-2 bridge {field} must remain false",
            )
    target = result.get("target", {})
    if (
        not isinstance(target, dict)
        or str(target.get("repository") or "").lower() != repository.lower()
        or target.get("pull_request") != pull_request
    ):
        raise OperationalReviewActionError(
            "TARGET_BINDING_FAILED",
            "AUTO-2 bridge target does not match requested repository/PR",
        )

    bundle_root = _find_single_bundle(root)
    bundle_errors = verify_evidence_bundle(bundle_root)
    if bundle_errors:
        raise OperationalReviewActionVerificationError(
            [f"evidence bundle: {error}" for error in bundle_errors]
        )

    packet_path = bundle_root / "review" / "packet.json"
    _packet_source, packet = load_review_packet(packet_path)
    stabilized_errors = verify_stabilized_bridge_result(result, packet)
    if stabilized_errors:
        raise OperationalReviewActionVerificationError(
            [f"AUTO-2 stabilized result: {error}" for error in stabilized_errors]
        )

    candidate_path = bundle_root / "prospective" / "candidate.json"
    _candidate_source, candidate = load_github_prospective_capture_candidate(
        candidate_path
    )
    if (
        candidate["repository"]["name_with_owner"].lower() != repository.lower()
        or candidate["pull_request"]["number"] != pull_request
    ):
        raise OperationalReviewActionError(
            "TARGET_BINDING_FAILED",
            "governed packet candidate does not match requested repository/PR",
        )
    if (
        target.get("head_sha") != candidate["pull_request"]["head_oid"]
        or target.get("base_sha") != candidate["pull_request"]["base_oid"]
    ):
        raise OperationalReviewActionError(
            "BRIDGE_SOURCE_INVALID",
            "AUTO-2 bridge target head/base does not match governed candidate",
        )
    packet_errors = verify_review_packet_sources(
        packet,
        workspace_root=root / "workspace",
        github_candidate=candidate_path,
        repository_root=target_root,
        github_cli=github_cli,
        repository=repository,
    )
    if packet_errors:
        raise OperationalReviewActionVerificationError(packet_errors)

    summary = _load_json_object(bundle_root / "summary.json", "prospective summary")
    impact = _load_json_object(
        bundle_root / "analysis" / "impact.json",
        "prospective impact",
    )
    brief = _load_json_object(
        bundle_root / "review" / "brief.json",
        "ORL-3 review brief",
    )
    binding_path = bundle_root / "operational" / "binding.json"
    binding = (
        _load_json_object(binding_path, "ORL-2 operational binding")
        if binding_path.exists()
        else None
    )
    brief_errors = verify_operational_review_brief_sources(
        brief,
        summary=summary,
        candidate=candidate,
        candidate_sha256=file_sha256(candidate_path),
        impact=impact,
        operational_binding=binding,
        review_packet=packet,
    )
    if brief_errors:
        raise OperationalReviewActionVerificationError(
            [f"ORL-3 review brief: {error}" for error in brief_errors]
        )

    policy_projection = (
        brief.get("trust", {}).get("operational_policy", {})
        if isinstance(brief.get("trust"), dict)
        else {}
    )
    policy_enabled = (
        isinstance(policy_projection, dict)
        and policy_projection.get("enabled") is True
    )
    if policy_enabled and binding is None:
        raise OperationalReviewActionError(
            "STALE_OPERATIONAL_BINDING",
            "ORL-3 brief requires an ORL-2 binding that is absent",
        )
    if binding is not None:
        if not policy_enabled:
            raise OperationalReviewActionError(
                "STALE_OPERATIONAL_BINDING",
                "ORL-2 binding is present but ORL-3 policy projection is disabled",
            )
        _verify_binding_readback(
            binding,
            candidate=candidate,
            github_cli=github_cli,
            repository_root=target_root,
        )
        if policy_projection.get("binding_sha256") != binding.get("binding_sha256"):
            raise OperationalReviewActionError(
                "STALE_OPERATIONAL_BINDING",
                "ORL-3 review brief binding hash does not match ORL-2 binding",
            )

    if result.get("assessment_id") != packet.get("assessment_id"):
        raise OperationalReviewActionError(
            "BRIDGE_SOURCE_INVALID",
            "AUTO-2 result assessment_id does not match governed packet",
        )
    if result.get("packet_id") != packet.get("packet_id"):
        raise OperationalReviewActionError(
            "BRIDGE_SOURCE_INVALID",
            "AUTO-2 result packet_id does not match governed packet",
        )
    return OperationalReviewSource(
        bridge_root=root,
        bundle_root=bundle_root,
        workspace_root=_safe_existing_dir(root / "workspace", "campaign workspace"),
        result=result,
        summary=summary,
        candidate_path=candidate_path,
        candidate=candidate,
        packet_path=packet_path,
        packet=packet,
        brief=brief,
        impact=impact,
        binding=binding,
    )


def select_operational_review_source(
    bridge_roots: Sequence[str | Path],
    *,
    target_repository: str,
    pull_request: int,
    repository_root: str | Path,
    github_cli: GitHubCLI,
) -> OperationalReviewSource:
    valid: list[OperationalReviewSource] = []
    failures: list[str] = []
    for raw in sorted({str(Path(value).expanduser()) for value in bridge_roots}):
        try:
            valid.append(
                inspect_operational_review_source(
                    raw,
                    target_repository=target_repository,
                    pull_request=pull_request,
                    repository_root=repository_root,
                    github_cli=github_cli,
                )
            )
        except Exception as exc:
            failures.append(f"{raw}: {exc}")
    if not valid:
        detail = "; ".join(failures[:5])
        if len(failures) > 5:
            detail += f"; ... {len(failures) - 5} more"
        raise OperationalReviewActionError(
            "NO_CURRENT_REVIEW_PACKET",
            "no current governed review packet survived exact source replay"
            + (f": {detail}" if detail else ""),
        )
    by_packet: dict[tuple[str, str], list[OperationalReviewSource]] = {}
    for source in valid:
        by_packet.setdefault(source.packet_key, []).append(source)
    if len(by_packet) != 1:
        identifiers = sorted(packet_id for packet_id, _ in by_packet)
        raise OperationalReviewActionError(
            "AMBIGUOUS_REVIEW_PACKET",
            "multiple distinct governed review packets are valid for the current PR: "
            + ", ".join(identifiers),
        )
    sources = next(iter(by_packet.values()))
    sources.sort(
        key=lambda item: (
            str(item.result.get("deterministic_result_sha256") or ""),
            str(item.bridge_root),
        )
    )
    return sources[0]


def _load_prior_action(path: Path) -> dict[str, Any] | None:
    candidate = path / "action.json"
    if not candidate.is_file() or _path_has_symlink(candidate):
        return None
    value = _load_json_object(candidate, "prior ORL-4 action")
    errors = verify_operational_review_action_data(value)
    if errors:
        raise OperationalReviewActionVerificationError(
            [f"prior ORL-4 action: {error}" for error in errors]
        )
    return value


def _reject_prior_action(
    prior_action_roots: Sequence[str | Path],
    *,
    source: OperationalReviewSource,
) -> None:
    for raw in sorted({str(Path(value).expanduser()) for value in prior_action_roots}):
        root = _safe_existing_dir(raw, "prior ORL-4 artifact")
        action = _load_prior_action(root)
        if action is None:
            continue
        action_source = action["source"]
        action_pr = action_source["pull_request"]
        if (
            action_source["assessment_id"] == source.packet["assessment_id"]
            and action_source["repository"]["name_with_owner"].lower()
            == source.candidate["repository"]["name_with_owner"].lower()
            and action_pr["number"] == source.candidate["pull_request"]["number"]
            and action_pr["head_oid"] == source.candidate["pull_request"]["head_oid"]
        ):
            raise OperationalReviewActionError(
                "REVIEW_ALREADY_RECORDED",
                "a prior ORL-4 artifact already records human review for this assessment",
            )


def _event_from_registry(
    workspace_root: Path,
    *,
    event_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _registry_path, registry = load_registry(
        workspace_root / "comparison-registry.json"
    )
    event = next(
        (item for item in registry["events"] if item.get("event_id") == event_id),
        None,
    )
    if event is None:
        raise OperationalReviewActionError(
            "REVIEW_EVENT_MISSING",
            f"recorded review event is absent from comparison registry: {event_id}",
        )
    if event.get("event_type") != "HUMAN_DECISION":
        raise OperationalReviewActionError(
            "REVIEW_EVENT_INVALID",
            "recorded event is not HUMAN_DECISION",
        )
    return registry, event


def _build_action(
    *,
    source: OperationalReviewSource,
    decision: str,
    reason: str,
    actor: str,
    confirmed_risk_band: str | None,
    registry: dict[str, Any],
    event: dict[str, Any],
) -> dict[str, Any]:
    payload = event.get("payload", {})
    if payload.get("review_level") != REVIEW_LEVEL:
        raise OperationalReviewActionError(
            "REVIEW_EVENT_INVALID",
            "governed event review_level is not REVIEWED",
        )
    if payload.get("decision") != decision:
        raise OperationalReviewActionError(
            "REVIEW_EVENT_INVALID",
            "governed event decision does not match explicit action",
        )
    if payload.get("confirmed_risk_band") != confirmed_risk_band:
        raise OperationalReviewActionError(
            "REVIEW_EVENT_INVALID",
            "governed event confirmed_risk_band does not match explicit action",
        )
    if event.get("actor") != actor:
        raise OperationalReviewActionError(
            "REVIEW_EVENT_INVALID",
            "governed event actor does not match explicit action",
        )
    reason_codes = payload.get("reason_codes", [])
    if reason not in reason_codes:
        raise OperationalReviewActionError(
            "REVIEW_EVENT_INVALID",
            "governed event does not preserve the explicit reason",
        )
    candidate = source.candidate
    packet = source.packet
    binding_sha = source.binding.get("binding_sha256") if source.binding else None
    action = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "status": STATUS,
        "source": {
            "authority_repository": AUTHORITY_REPOSITORY,
            "bridge_contract": source.result["bridge_contract"],
            "bridge_deterministic_result_sha256": source.result[
                "deterministic_result_sha256"
            ],
            "semantic_packet_sha256": source.result["semantic_packet_sha256"],
            "project_id": candidate["project_id"],
            "repository": {
                "hostname": candidate["repository"]["hostname"],
                "name_with_owner": candidate["repository"]["name_with_owner"],
            },
            "pull_request": {
                "number": candidate["pull_request"]["number"],
                "base_oid": candidate["pull_request"]["base_oid"],
                "head_oid": candidate["pull_request"]["head_oid"],
            },
            "assessment_id": packet["assessment_id"],
            "review_packet_id": packet["packet_id"],
            "review_packet_sha256": packet["packet_sha256"],
            "review_brief_sha256": source.brief["brief_sha256"],
            "operational_binding_sha256": binding_sha,
        },
        "review": {
            "review_level": REVIEW_LEVEL,
            "decision": decision,
            "reason": reason,
            "confirmed_risk_band": confirmed_risk_band,
            "actor": actor,
        },
        "event": {
            "event_id": event["event_id"],
            "event_sha256": event["event_sha256"],
            "occurred_at": event["occurred_at"],
            "registry_sha256": registry["registry_sha256"],
            "reason_codes": sorted(set(reason_codes)),
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
    action["action_sha256"] = _action_hash(action)
    errors = verify_operational_review_action_data(action)
    if errors:
        raise OperationalReviewActionVerificationError(errors)
    return action


def submit_operational_review_action_from_sources(
    *,
    bridge_roots: Sequence[str | Path],
    prior_action_roots: Sequence[str | Path],
    target_repository: str,
    pull_request: int,
    repository_root: str | Path,
    github_cli: GitHubCLI,
    decision: str,
    reason: str,
    actor: str,
    confirmed_risk_band: str | None = None,
    occurred_at: str | None = None,
    output: str | Path | None = None,
) -> dict[str, Any]:
    repository = _normalize_repository(target_repository)
    normalized_decision, normalized_reason, normalized_actor, band = (
        _normalize_review_input(
            decision=decision,
            reason=reason,
            actor=actor,
            confirmed_risk_band=confirmed_risk_band,
        )
    )
    source = select_operational_review_source(
        bridge_roots,
        target_repository=repository,
        pull_request=pull_request,
        repository_root=repository_root,
        github_cli=github_cli,
    )
    _reject_prior_action(prior_action_roots, source=source)
    result = submit_review_packet(
        source.packet_path,
        workspace_root=source.workspace_root,
        github_candidate=source.candidate_path,
        repository_root=repository_root,
        github_cli=github_cli,
        repository=repository,
        review_level=REVIEW_LEVEL,
        decision=normalized_decision,
        actor=normalized_actor,
        occurred_at=occurred_at,
        confirmed_risk_band=band,
        reason_codes=[normalized_reason],
    )
    registry, event = _event_from_registry(
        source.workspace_root,
        event_id=result["event_id"],
    )
    action = _build_action(
        source=source,
        decision=normalized_decision,
        reason=normalized_reason,
        actor=normalized_actor,
        confirmed_risk_band=band,
        registry=registry,
        event=event,
    )
    output_path = (
        _safe_output(output, "operational review action output")
        if output is not None
        else source.bridge_root / "operational-review-action.json"
    )
    written = write_operational_review_action(output_path, action)
    return {
        **action,
        "action_file": str(written),
        "bridge_root": str(source.bridge_root),
        "workspace_root": str(source.workspace_root),
        "review_packet_archive": result["review_packet_archive"],
    }


def run_operational_review_action(
    request: OperationalReviewActionRequest,
    *,
    github_cli: GitHubCLI,
) -> dict[str, Any]:
    repository = _normalize_repository(request.target_repository)
    root = _safe_existing_dir(request.repository_root, "target repository root")
    _initial_source, auto2_roots, prior_roots = discover_operational_review_artifacts(
        github_cli,
        repository_root=root,
        cache_root=request.artifact_cache_root,
        target_repository=repository,
        pull_request=request.pull_request,
    )
    if not auto2_roots:
        raise OperationalReviewActionError(
            "NO_REVIEW_ARTIFACT",
            "no non-expired AUTO-2 human-review artifact exists for the current PR head",
        )
    result = submit_operational_review_action_from_sources(
        bridge_roots=auto2_roots,
        prior_action_roots=prior_roots,
        target_repository=repository,
        pull_request=request.pull_request,
        repository_root=root,
        github_cli=github_cli,
        decision=request.decision,
        reason=request.reason,
        actor=request.actor,
        confirmed_risk_band=request.confirmed_risk_band,
        occurred_at=request.occurred_at,
        output=request.output,
    )
    final_source = _live_target(
        github_cli,
        repository_root=root,
        repository=repository,
        pull_request=request.pull_request,
    )
    live_pr = final_source["pull_request"]
    action_pr = result["source"]["pull_request"]
    if (
        action_pr["head_oid"] != str(live_pr["head_oid"]).lower()
        or action_pr["base_oid"] != str(live_pr["base_oid"]).lower()
    ):
        raise OperationalReviewActionError(
            "STALE_SOURCE_REVISION",
            "target PR head/base moved during explicit review submission",
        )
    return result
