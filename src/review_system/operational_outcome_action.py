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

from .defects import load_defect_registry
from .evaluation import load_evaluation_report
from .github_connector import GitHubCLI
from .identity import canonical_json_sha256, file_sha256
from .io import load_data
from .operational_outcome_context import (
    ORL5_ARTIFACT_PREFIX,
    OperationalOutcomeContextError,
    OperationalOutcomeContextVerificationError,
    _live_target_source,
    load_operational_outcome_context,
    verify_operational_outcome_context_sources,
)
from .operational_review_action import (
    AUTHORITY_REPOSITORY,
    OperationalReviewActionError,
    _download_artifacts,
    _list_authority_artifacts,
    _normalize_repository,
    _path_has_symlink,
    _safe_existing_dir,
    _safe_output,
)
from .paths import asset
from .trust_audit import load_audit_artifact, load_authority_registry
from .trust_outcome_declaration import (
    SUPPORTED_AUTHORITIES,
    SUPPORTED_VERDICTS,
    OutcomeDeclarationError,
    OutcomeDeclarationVerificationError,
    build_outcome_declaration,
    verify_outcome_declaration_data,
)
from .trust_outcome_transport import (
    OutcomeTransportError,
    OutcomeTransportVerificationError,
    transport_declared_outcome,
)

SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_OPERATIONAL_OUTCOME_ACTION_V1"
STATUS = "EXPLICIT_OUTCOME_RECORDED"
ORL6_ARTIFACT_PREFIX = "pie-orl6-"
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SOURCE_FIELDS = {
    "defect_registry_sha256",
    "ledger_sha256",
    "evaluation_id",
    "evaluation_report_sha256",
    "audit_id",
    "audit_artifact_sha256",
    "audit_authority_registry_sha256",
}
_REQUIRED_SOURCE_FIELDS = {
    "PRODUCTION_DEFECT": {"defect_registry_sha256", "ledger_sha256"},
    "CONTROLLED_EVALUATION": {"evaluation_id", "evaluation_report_sha256"},
    "INDEPENDENT_AUDIT": {
        "audit_id",
        "audit_artifact_sha256",
        "audit_authority_registry_sha256",
    },
}
_REQUIRED_FILE_ROLES = {
    "PRODUCTION_DEFECT": {"defect_registry", "ledger"},
    "CONTROLLED_EVALUATION": {"evaluation_report"},
    "INDEPENDENT_AUDIT": {"audit_artifact", "audit_authority_registry"},
}


class OperationalOutcomeActionError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class OperationalOutcomeActionVerificationError(OperationalOutcomeActionError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__(
            "OUTCOME_ACTION_INVALID",
            "invalid operational Outcome action: " + "; ".join(self.errors),
        )


@dataclass(frozen=True)
class OperationalOutcomeContextSource:
    artifact_root: Path
    context_path: Path
    context: dict[str, Any]
    review_action_root: Path

    @property
    def review_action_sha256(self) -> str:
        return self.context["source"]["review_action_sha256"]


@dataclass(frozen=True)
class OperationalOutcomeActionRequest:
    target_repository: str
    pull_request: int
    actor: str
    authority_type: str
    verdict: str
    repository_root: str | Path
    artifact_cache_root: str | Path
    output_root: str | Path
    declared_at: str | None = None
    defect_id: str | None = None
    evidence_refs: Sequence[str] = ()
    defect_registry: str | Path | None = None
    ledger: str | Path | None = None
    evaluation_report: str | Path | None = None
    audit_artifact: str | Path | None = None
    audit_authority_registry: str | Path | None = None


def _schema() -> dict[str, Any]:
    value = load_data(asset("schemas/operational-outcome-action.schema.json"))
    if not isinstance(value, dict):
        raise OperationalOutcomeActionError(
            "CONTRACT_INVALID",
            "operational Outcome action schema must contain an object",
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


def _source_binding_errors(authority_type: str, binding: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if authority_type not in _REQUIRED_SOURCE_FIELDS:
        return ["action.authority_type is unsupported"]
    required = _REQUIRED_SOURCE_FIELDS[authority_type]
    for field in sorted(required):
        if not binding.get(field):
            errors.append(f"action.authority_source.source_binding.{field} is required")
    for field in sorted(_SOURCE_FIELDS - required):
        if binding.get(field) is not None:
            errors.append(
                f"action.authority_source.source_binding.{field} must be null for {authority_type}"
            )
    return errors


def verify_operational_outcome_action_data(value: Any) -> list[str]:
    errors = _schema_errors(value)
    if not isinstance(value, dict):
        return sorted(set(errors or ["action must contain an object"]))
    if value.get("contract_version") != CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    if value.get("status") != STATUS:
        errors.append("status mismatch")

    action = value.get("action") if isinstance(value.get("action"), dict) else {}
    authority_type = action.get("authority_type")
    verdict = action.get("verdict")
    if authority_type not in SUPPORTED_AUTHORITIES:
        errors.append("action.authority_type is unsupported")
    if verdict not in SUPPORTED_VERDICTS:
        errors.append("action.verdict is unsupported")
    if authority_type == "PRODUCTION_DEFECT" and verdict == "SAFE":
        errors.append("PRODUCTION_DEFECT authority cannot prove SAFE")
    if authority_type == "PRODUCTION_DEFECT" and not action.get("defect_id"):
        errors.append("PRODUCTION_DEFECT requires defect_id")
    if authority_type in {"CONTROLLED_EVALUATION", "INDEPENDENT_AUDIT"} and action.get("defect_id") is not None:
        errors.append(f"defect_id must be null for {authority_type}")

    authority_source = (
        action.get("authority_source")
        if isinstance(action.get("authority_source"), dict)
        else {}
    )
    binding = (
        authority_source.get("source_binding")
        if isinstance(authority_source.get("source_binding"), dict)
        else {}
    )
    if isinstance(authority_type, str):
        errors.extend(_source_binding_errors(authority_type, binding))
        files = authority_source.get("files")
        if isinstance(files, list):
            roles = {
                item.get("role")
                for item in files
                if isinstance(item, dict) and isinstance(item.get("role"), str)
            }
            if roles != _REQUIRED_FILE_ROLES.get(authority_type, set()):
                errors.append("action.authority_source.files roles do not match authority_type")

    auto3 = value.get("auto3") if isinstance(value.get("auto3"), dict) else {}
    if auto3.get("reconciliation_status") != "RECONCILED":
        errors.append("AUTO-3B reconciliation must be RECONCILED")
    if auto3.get("idempotent") is not False:
        errors.append("ORL-6 must record a new Outcome, not an idempotent replay")

    authority = value.get("authority") if isinstance(value.get("authority"), dict) else {}
    if authority.get("human_review_recorded") is not True:
        errors.append("authority.human_review_recorded must be true")
    if authority.get("human_outcome_declared") is not True:
        errors.append("authority.human_outcome_declared must be true")
    if authority.get("outcome_recorded") is not True:
        errors.append("authority.outcome_recorded must be true")
    for field in (
        "automatic_outcome_inference",
        "automation_authorized",
        "pilot_authorized",
        "merge_authorized",
        "deploy_authorized",
        "production_effect_authorized",
    ):
        if authority.get(field) is not False:
            errors.append(f"authority.{field} must remain false")

    if value.get("action_sha256") != _action_hash(value):
        errors.append("action_sha256 mismatch")
    return sorted(set(errors))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(dict(value), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_operational_outcome_action(
    path: str | Path,
    value: Mapping[str, Any],
) -> Path:
    errors = verify_operational_outcome_action_data(value)
    if errors:
        raise OperationalOutcomeActionVerificationError(errors)
    target = _safe_output(path, "operational Outcome action output")
    _write_json(target, value)
    return target


def load_operational_outcome_action(path: str | Path) -> tuple[Path, dict[str, Any]]:
    raw = Path(path).expanduser()
    if _path_has_symlink(raw):
        raise OperationalOutcomeActionError(
            "UNSAFE_SOURCE_PATH",
            f"operational Outcome action path must not contain symlinks: {raw}",
        )
    try:
        source = raw.resolve(strict=True)
    except OSError as exc:
        raise OperationalOutcomeActionError(
            "SOURCE_NOT_FOUND",
            f"operational Outcome action not found: {raw}",
        ) from exc
    if not source.is_file():
        raise OperationalOutcomeActionError(
            "SOURCE_NOT_FOUND",
            f"operational Outcome action must be a regular file: {source}",
        )
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OperationalOutcomeActionError(
            "SOURCE_INVALID",
            f"operational Outcome action is invalid JSON: {exc}",
        ) from exc
    errors = verify_operational_outcome_action_data(value)
    if errors:
        raise OperationalOutcomeActionVerificationError(errors)
    assert isinstance(value, dict)
    return source, value


def _safe_source_file(path: str | Path | None, label: str) -> Path:
    if path is None:
        raise OperationalOutcomeActionError("AUTHORITY_SOURCE_MISSING", f"{label} is required")
    raw = Path(path).expanduser()
    if _path_has_symlink(raw):
        raise OperationalOutcomeActionError(
            "UNSAFE_SOURCE_PATH",
            f"{label} must not contain symlinks: {raw}",
        )
    try:
        source = raw.resolve(strict=True)
    except OSError as exc:
        raise OperationalOutcomeActionError(
            "AUTHORITY_SOURCE_MISSING",
            f"{label} not found: {raw}",
        ) from exc
    if not source.is_file():
        raise OperationalOutcomeActionError(
            "AUTHORITY_SOURCE_MISSING",
            f"{label} must be a regular file: {source}",
        )
    return source


def _tree_without_symlinks(root: Path, label: str) -> None:
    if _path_has_symlink(root):
        raise OperationalOutcomeActionError(
            "UNSAFE_SOURCE_PATH",
            f"{label} must not contain symlinks: {root}",
        )
    for path in root.rglob("*"):
        if path.is_symlink():
            raise OperationalOutcomeActionError(
                "UNSAFE_SOURCE_PATH",
                f"{label} must not contain symlinks: {path}",
            )


def _copy_exact(source: Path, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as reader, target.open("xb") as writer:
        shutil.copyfileobj(reader, writer)
        writer.flush()
        os.fsync(writer.fileno())
    return target


def _normalize_inputs(
    *,
    actor: str,
    authority_type: str,
    verdict: str,
    defect_id: str | None,
    evidence_refs: Sequence[str],
) -> tuple[str, str, str, str | None, list[str]]:
    normalized_actor = actor.strip() if isinstance(actor, str) else ""
    if not normalized_actor or _CONTROL.search(normalized_actor):
        raise OperationalOutcomeActionError(
            "INVALID_ACTOR",
            "actor must be a non-empty printable string",
        )
    authority = authority_type.strip().upper() if isinstance(authority_type, str) else ""
    outcome_verdict = verdict.strip().upper() if isinstance(verdict, str) else ""
    if authority not in SUPPORTED_AUTHORITIES:
        raise OperationalOutcomeActionError(
            "INVALID_AUTHORITY_TYPE",
            "authority_type must be PRODUCTION_DEFECT, CONTROLLED_EVALUATION, or INDEPENDENT_AUDIT",
        )
    if outcome_verdict not in SUPPORTED_VERDICTS:
        raise OperationalOutcomeActionError(
            "INVALID_VERDICT",
            "verdict must be SAFE, UNSAFE, or INCONCLUSIVE",
        )
    if authority == "PRODUCTION_DEFECT" and outcome_verdict == "SAFE":
        raise OperationalOutcomeActionError(
            "INVALID_VERDICT",
            "PRODUCTION_DEFECT authority cannot prove SAFE",
        )
    normalized_defect = (
        defect_id.strip()
        if isinstance(defect_id, str) and defect_id.strip()
        else None
    )
    if authority == "PRODUCTION_DEFECT" and normalized_defect is None:
        raise OperationalOutcomeActionError(
            "DEFECT_ID_REQUIRED",
            "PRODUCTION_DEFECT requires defect_id",
        )
    if authority != "PRODUCTION_DEFECT" and normalized_defect is not None:
        raise OperationalOutcomeActionError(
            "UNEXPECTED_DEFECT_ID",
            f"defect_id must be absent for {authority}",
        )
    refs: set[str] = set()
    for value in evidence_refs:
        text = value.strip() if isinstance(value, str) else ""
        if not text or _CONTROL.search(text):
            raise OperationalOutcomeActionError(
                "INVALID_EVIDENCE_REF",
                "evidence references must be non-empty printable strings",
            )
        refs.add(text)
    return normalized_actor, authority, outcome_verdict, normalized_defect, sorted(refs)


def _context_prefix(repository: str, pull_request: int, head_oid: str) -> str:
    safe_repo = repository.replace("/", "-")
    return f"{ORL5_ARTIFACT_PREFIX}{safe_repo}-pr-{pull_request}-{head_oid[:12]}-"


def _outcome_prefix(repository: str, pull_request: int, head_oid: str) -> str:
    safe_repo = repository.replace("/", "-")
    return f"{ORL6_ARTIFACT_PREFIX}{safe_repo}-pr-{pull_request}-{head_oid[:12]}-"


def inspect_operational_outcome_context_artifact(
    artifact_root: str | Path,
    *,
    target_repository: str,
    pull_request: int,
    repository_root: str | Path,
    github_cli: GitHubCLI,
) -> OperationalOutcomeContextSource:
    root = _safe_existing_dir(artifact_root, "ORL-5 artifact")
    context_path, context = load_operational_outcome_context(root / "context.json")
    review_action_root = _safe_existing_dir(
        root / "review-action-source",
        "ORL-5 review-action source",
    )
    source = context["source"]
    repository = _normalize_repository(target_repository)
    pull = source["pull_request"]
    if (
        source["repository"]["name_with_owner"].lower() != repository.lower()
        or pull["number"] != pull_request
    ):
        raise OperationalOutcomeActionError(
            "TARGET_BINDING_FAILED",
            "ORL-5 context does not match requested repository/PR",
        )
    replay_errors = verify_operational_outcome_context_sources(
        context,
        action_artifact_root=review_action_root,
        repository_root=repository_root,
        github_cli=github_cli,
    )
    if replay_errors:
        raise OperationalOutcomeActionVerificationError(
            [f"ORL-5 context: {error}" for error in replay_errors]
        )
    return OperationalOutcomeContextSource(
        artifact_root=root,
        context_path=context_path,
        context=context,
        review_action_root=review_action_root,
    )


def select_operational_outcome_context(
    artifact_roots: Sequence[str | Path],
    *,
    target_repository: str,
    pull_request: int,
    repository_root: str | Path,
    github_cli: GitHubCLI,
) -> OperationalOutcomeContextSource:
    valid: list[OperationalOutcomeContextSource] = []
    failures: list[str] = []
    for raw in artifact_roots:
        try:
            valid.append(
                inspect_operational_outcome_context_artifact(
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
        raise OperationalOutcomeActionError(
            "NO_CURRENT_OUTCOME_CONTEXT",
            "no current ORL-5 context survived exact source replay"
            + (f": {detail}" if detail else ""),
        )
    by_review_action: dict[str, list[OperationalOutcomeContextSource]] = {}
    for item in valid:
        by_review_action.setdefault(item.review_action_sha256, []).append(item)
    if len(by_review_action) != 1:
        raise OperationalOutcomeActionError(
            "AMBIGUOUS_OUTCOME_CONTEXT",
            "multiple distinct review actions have valid ORL-5 contexts for the current PR",
        )
    # Artifact discovery is newest-first. Observation-only refreshes of the same
    # review action are not authority conflicts, so use the newest valid context.
    return next(iter(by_review_action.values()))[0]


def _prior_action_matches(
    action: Mapping[str, Any],
    *,
    repository: str,
    pull_request: int,
    head_oid: str,
    assessment_id: str,
    review_action_sha256: str,
) -> bool:
    source = action.get("source") if isinstance(action.get("source"), dict) else {}
    pull = source.get("pull_request") if isinstance(source.get("pull_request"), dict) else {}
    repo = source.get("repository") if isinstance(source.get("repository"), dict) else {}
    return all(
        (
            str(repo.get("name_with_owner") or "").lower() == repository.lower(),
            pull.get("number") == pull_request,
            pull.get("head_oid") == head_oid,
            source.get("assessment_id") == assessment_id,
            source.get("review_action_sha256") == review_action_sha256,
        )
    )


def reject_prior_operational_outcome_action(
    artifact_roots: Sequence[str | Path],
    *,
    repository: str,
    pull_request: int,
    head_oid: str,
    assessment_id: str,
    review_action_sha256: str,
) -> None:
    for raw in artifact_roots:
        root = _safe_existing_dir(raw, "prior ORL-6 artifact")
        action_path = root / "action.json"
        if not action_path.is_file() or _path_has_symlink(action_path):
            raise OperationalOutcomeActionError(
                "PRIOR_OUTCOME_ACTION_INVALID",
                f"prior ORL-6 artifact does not contain a safe action.json: {root}",
            )
        try:
            _, action = load_operational_outcome_action(action_path)
        except Exception as exc:
            raise OperationalOutcomeActionError(
                "PRIOR_OUTCOME_ACTION_INVALID",
                f"prior ORL-6 artifact failed validation: {root}: {exc}",
            ) from exc
        if _prior_action_matches(
            action,
            repository=repository,
            pull_request=pull_request,
            head_oid=head_oid,
            assessment_id=assessment_id,
            review_action_sha256=review_action_sha256,
        ):
            raise OperationalOutcomeActionError(
                "OUTCOME_ALREADY_RECORDED",
                "a governed ORL-6 Outcome action already exists for this assessment/review action",
            )


def discover_operational_outcome_artifacts(
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
        raise OperationalOutcomeActionError(
            "INVALID_INPUT",
            "pull_request must be at least 1",
        )
    try:
        live = _live_target_source(
            github_cli,
            repository_root=root,
            repository=repository,
            pull_request=pull_request,
        )
    except OperationalOutcomeContextError as exc:
        raise OperationalOutcomeActionError(exc.code, str(exc)) from exc
    head = str(live["pull_request"]["head_oid"]).lower()
    context_prefix = _context_prefix(repository, pull_request, head)
    action_prefix = _outcome_prefix(repository, pull_request, head)
    try:
        artifacts = _list_authority_artifacts(
            github_cli,
            cwd=root,
            prefixes=(context_prefix, action_prefix),
        )
    except OperationalReviewActionError as exc:
        raise OperationalOutcomeActionError(exc.code, str(exc)) from exc
    contexts = [
        item for item in artifacts if str(item["name"]).startswith(context_prefix)
    ]
    actions = [
        item for item in artifacts if str(item["name"]).startswith(action_prefix)
    ]
    cache = _safe_output(cache_root, "ORL-6 artifact cache root")
    if cache.exists():
        shutil.rmtree(cache)
    cache.mkdir(parents=True)
    try:
        context_roots = _download_artifacts(
            github_cli,
            cwd=root,
            artifacts=contexts,
            destination=cache / "orl5",
        )
        action_roots = _download_artifacts(
            github_cli,
            cwd=root,
            artifacts=actions,
            destination=cache / "orl6",
        )
    except OperationalReviewActionError as exc:
        raise OperationalOutcomeActionError(exc.code, str(exc)) from exc
    return live, context_roots, action_roots


def _authority_sources(
    request: OperationalOutcomeActionRequest,
    *,
    authority_type: str,
    actor: str,
    verdict: str,
    defect_id: str | None,
    evidence_refs: Sequence[str],
    destination: Path,
) -> tuple[dict[str, Any], list[dict[str, str]], dict[str, Path], list[str]]:
    supplied = {
        "defect_registry": request.defect_registry,
        "ledger": request.ledger,
        "evaluation_report": request.evaluation_report,
        "audit_artifact": request.audit_artifact,
        "audit_authority_registry": request.audit_authority_registry,
    }
    provided = {role for role, path in supplied.items() if path is not None}
    required = _REQUIRED_FILE_ROLES[authority_type]
    missing = sorted(required - provided)
    unexpected = sorted(provided - required)
    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        raise OperationalOutcomeActionError(
            "AUTHORITY_SOURCE_MISMATCH",
            f"authority source files do not match {authority_type}: " + "; ".join(details),
        )

    source_binding: dict[str, Any] = {field: None for field in sorted(_SOURCE_FIELDS)}
    files: list[dict[str, str]] = []
    transport_sources: dict[str, Path] = {}
    refs = set(evidence_refs)
    destination.mkdir(parents=True, exist_ok=True)

    def preserve(role: str, source_path: str | Path | None) -> Path:
        source = _safe_source_file(source_path, role)
        target = destination / f"{role}.source"
        _copy_exact(source, target)
        files.append({"role": role, "file_sha256": file_sha256(target)})
        transport_sources[role] = target
        return target

    try:
        if authority_type == "PRODUCTION_DEFECT":
            registry_path = preserve("defect_registry", request.defect_registry)
            ledger_path = preserve("ledger", request.ledger)
            _, registry = load_defect_registry(registry_path)
            source_binding["defect_registry_sha256"] = registry["registry_sha256"]
            source_binding["ledger_sha256"] = file_sha256(ledger_path)
            refs.update(
                {
                    str(defect_id),
                    registry["registry_sha256"],
                    source_binding["ledger_sha256"],
                }
            )
        elif authority_type == "CONTROLLED_EVALUATION":
            evaluation_path = preserve("evaluation_report", request.evaluation_report)
            _, evaluation = load_evaluation_report(evaluation_path)
            source_binding["evaluation_id"] = evaluation["evaluation_id"]
            source_binding["evaluation_report_sha256"] = evaluation["report_sha256"]
            refs.update({evaluation["evaluation_id"], evaluation["report_sha256"]})
        elif authority_type == "INDEPENDENT_AUDIT":
            artifact_path = preserve("audit_artifact", request.audit_artifact)
            authority_path = preserve(
                "audit_authority_registry",
                request.audit_authority_registry,
            )
            _, artifact = load_audit_artifact(artifact_path)
            _, authority_registry = load_authority_registry(authority_path)
            source_binding["audit_id"] = artifact["audit_id"]
            source_binding["audit_artifact_sha256"] = artifact["artifact_sha256"]
            source_binding["audit_authority_registry_sha256"] = authority_registry[
                "registry_sha256"
            ]
            if actor != artifact.get("issuer_subject"):
                raise OperationalOutcomeActionError(
                    "AUDIT_ACTOR_MISMATCH",
                    "Independent Audit actor must equal audit issuer_subject",
                )
            if verdict != artifact.get("verdict"):
                raise OperationalOutcomeActionError(
                    "AUDIT_VERDICT_MISMATCH",
                    "Independent Audit verdict must equal audit artifact verdict",
                )
            refs.update(
                {
                    artifact["audit_id"],
                    artifact["artifact_sha256"],
                    authority_registry["registry_sha256"],
                }
            )
    except OperationalOutcomeActionError:
        raise
    except Exception as exc:
        raise OperationalOutcomeActionError(
            "AUTHORITY_SOURCE_INVALID",
            f"authority source validation failed: {exc}",
        ) from exc

    return source_binding, sorted(files, key=lambda item: item["role"]), transport_sources, sorted(refs)


def _declaration_from_context(
    context: Mapping[str, Any],
    *,
    actor: str,
    authority_type: str,
    verdict: str,
    declared_at: str | None,
    defect_id: str | None,
    evidence_refs: Sequence[str],
    source_binding: Mapping[str, Any],
) -> dict[str, Any]:
    auto3 = context["auto3_declaration_context"]
    assessment = auto3["assessment"]
    review = auto3["review"]
    try:
        return build_outcome_declaration(
            actor=actor,
            project_id=auto3["project_id"],
            assessment_id=assessment["assessment_id"],
            source_revision=assessment["source_revision"],
            trust_report_id=assessment["trust_report_id"],
            trust_report_sha256=assessment["trust_report_sha256"],
            review_event_id=review["event_id"],
            review_event_sha256=review["event_sha256"],
            review_level=review["review_level"],
            decision=review["decision"],
            review_packet_id=review["review_packet_id"],
            review_packet_sha256=review["review_packet_sha256"],
            authority_type=authority_type,
            verdict=verdict,
            declared_at=declared_at,
            defect_id=defect_id,
            evidence_refs=evidence_refs,
            defect_registry_sha256=source_binding["defect_registry_sha256"],
            ledger_sha256=source_binding["ledger_sha256"],
            evaluation_id=source_binding["evaluation_id"],
            evaluation_report_sha256=source_binding["evaluation_report_sha256"],
            audit_id=source_binding["audit_id"],
            audit_artifact_sha256=source_binding["audit_artifact_sha256"],
            audit_authority_registry_sha256=source_binding[
                "audit_authority_registry_sha256"
            ],
        )
    except (OutcomeDeclarationError, OutcomeDeclarationVerificationError) as exc:
        raise OperationalOutcomeActionError(
            "AUTO3A_DECLARATION_FAILED",
            str(exc),
        ) from exc


def build_operational_outcome_action(
    *,
    context: Mapping[str, Any],
    declaration: Mapping[str, Any],
    transport: Mapping[str, Any],
    authority_files: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    declaration_errors = verify_outcome_declaration_data(declaration)
    if declaration_errors:
        raise OperationalOutcomeActionVerificationError(
            [f"AUTO-3A declaration: {error}" for error in declaration_errors]
        )
    source = context["source"]
    auto3_context = context["auto3_declaration_context"]
    checks = {
        "project_id": declaration["project_id"] == auto3_context["project_id"],
        "assessment": declaration["assessment"] == auto3_context["assessment"],
        "review_event_id": declaration["review"]["event_id"]
        == auto3_context["review"]["event_id"],
        "review_event_sha256": declaration["review"]["event_sha256"]
        == auto3_context["review"]["event_sha256"],
        "review_level": declaration["review"]["review_level"]
        == auto3_context["review"]["review_level"],
        "decision": declaration["review"]["decision"]
        == auto3_context["review"]["decision"],
        "review_packet_id": declaration["review"]["review_packet_id"]
        == auto3_context["review"]["review_packet_id"],
        "review_packet_sha256": declaration["review"]["review_packet_sha256"]
        == auto3_context["review"]["review_packet_sha256"],
        "transport_declaration_id": transport.get("declaration_id")
        == declaration["declaration_id"],
        "transport_declaration_sha256": transport.get("declaration_sha256")
        == declaration["declaration_sha256"],
        "transport_project": transport.get("project_id") == declaration["project_id"],
        "transport_assessment": transport.get("assessment_id")
        == declaration["assessment"]["assessment_id"],
        "transport_revision": transport.get("source_revision")
        == declaration["assessment"]["source_revision"],
        "transport_review": transport.get("review_event_id")
        == declaration["review"]["event_id"],
        "transport_authority": transport.get("outcome_type")
        == declaration["outcome"]["authority_type"],
        "transport_verdict": transport.get("verdict")
        == declaration["outcome"]["verdict"],
        "transport_reconciled": transport.get("reconciliation_status") == "RECONCILED",
        "transport_recorded": transport.get("outcome_recorded") is True,
        "transport_not_automatic": transport.get("automatic_outcome_inference") is False,
        "transport_not_idempotent": transport.get("idempotent") is False,
    }
    failed = sorted(key for key, ok in checks.items() if not ok)
    if failed:
        raise OperationalOutcomeActionVerificationError(
            ["AUTO-3 transport binding mismatch: " + ", ".join(failed)]
        )

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "status": STATUS,
        "source": {
            "authority_repository": AUTHORITY_REPOSITORY,
            "context_sha256": context["context_sha256"],
            "project_id": source["project_id"],
            "repository": deepcopy(source["repository"]),
            "pull_request": deepcopy(source["pull_request"]),
            "assessment_id": source["assessment"]["assessment_id"],
            "review_event_id": context["review"]["event_id"],
            "review_action_sha256": source["review_action_sha256"],
            "review_packet_id": source["review_packet_id"],
            "review_packet_sha256": source["review_packet_sha256"],
        },
        "action": {
            "actor": declaration["actor"],
            "authority_type": declaration["outcome"]["authority_type"],
            "verdict": declaration["outcome"]["verdict"],
            "defect_id": declaration["outcome"]["defect_id"],
            "evidence_refs": deepcopy(declaration["outcome"]["evidence_refs"]),
            "authority_source": {
                "source_binding": deepcopy(declaration["outcome"]["source_binding"]),
                "files": [dict(item) for item in authority_files],
            },
        },
        "auto3": {
            "declaration_id": declaration["declaration_id"],
            "declaration_sha256": declaration["declaration_sha256"],
            "transport_sha256": transport["transport_sha256"],
            "event_id": transport["event_id"],
            "registry_sha256": transport["registry_sha256"],
            "reconciliation_status": transport["reconciliation_status"],
            "authority_key": transport.get("authority_key"),
            "idempotent": bool(transport.get("idempotent")),
        },
        "authority": {
            "human_review_recorded": True,
            "human_outcome_declared": True,
            "automatic_outcome_inference": False,
            "outcome_recorded": True,
            "automation_authorized": False,
            "pilot_authorized": False,
            "merge_authorized": False,
            "deploy_authorized": False,
            "production_effect_authorized": False,
        },
        "action_sha256": "",
    }
    receipt["action_sha256"] = _action_hash(receipt)
    errors = verify_operational_outcome_action_data(receipt)
    if errors:
        raise OperationalOutcomeActionVerificationError(errors)
    return receipt


def run_operational_outcome_action(
    request: OperationalOutcomeActionRequest,
    *,
    github_cli: GitHubCLI,
) -> dict[str, Any]:
    repository = _normalize_repository(request.target_repository)
    root = _safe_existing_dir(request.repository_root, "target repository root")
    actor, authority_type, verdict, defect_id, evidence_refs = _normalize_inputs(
        actor=request.actor,
        authority_type=request.authority_type,
        verdict=request.verdict,
        defect_id=request.defect_id,
        evidence_refs=request.evidence_refs,
    )
    _live, context_roots, prior_roots = discover_operational_outcome_artifacts(
        github_cli,
        repository_root=root,
        cache_root=request.artifact_cache_root,
        target_repository=repository,
        pull_request=request.pull_request,
    )
    if not context_roots:
        raise OperationalOutcomeActionError(
            "NO_OUTCOME_CONTEXT_ARTIFACT",
            "no non-expired ORL-5 Outcome context artifact exists for the current PR head",
        )
    context_source = select_operational_outcome_context(
        context_roots,
        target_repository=repository,
        pull_request=request.pull_request,
        repository_root=root,
        github_cli=github_cli,
    )
    context = context_source.context
    source = context["source"]
    reject_prior_operational_outcome_action(
        prior_roots,
        repository=repository,
        pull_request=request.pull_request,
        head_oid=source["pull_request"]["head_oid"],
        assessment_id=source["assessment"]["assessment_id"],
        review_action_sha256=source["review_action_sha256"],
    )

    target = _safe_output(request.output_root, "ORL-6 output root")
    if target.exists():
        raise OperationalOutcomeActionError(
            "OUTPUT_EXISTS",
            f"ORL-6 output root already exists: {target}",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    if _path_has_symlink(target.parent):
        raise OperationalOutcomeActionError(
            "UNSAFE_OUTPUT_PATH",
            f"ORL-6 output parent must not contain symlinks: {target.parent}",
        )

    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    )
    committed = False
    try:
        _tree_without_symlinks(
            context_source.review_action_root,
            "ORL-5 review-action source",
        )
        shutil.copy2(context_source.context_path, temporary / "context.json")
        shutil.copytree(
            context_source.review_action_root,
            temporary / "review-action-source",
            copy_function=shutil.copy2,
        )

        source_binding, authority_files, transport_sources, final_refs = _authority_sources(
            request,
            authority_type=authority_type,
            actor=actor,
            verdict=verdict,
            defect_id=defect_id,
            evidence_refs=evidence_refs,
            destination=temporary / "authority-source",
        )
        declaration = _declaration_from_context(
            context,
            actor=actor,
            authority_type=authority_type,
            verdict=verdict,
            declared_at=request.declared_at,
            defect_id=defect_id,
            evidence_refs=final_refs,
            source_binding=source_binding,
        )
        declaration_path = temporary / "declaration.json"
        _write_json(declaration_path, declaration)

        workspace = temporary / "review-action-source" / "bridge" / "workspace"
        try:
            transport = transport_declared_outcome(
                workspace,
                declaration=declaration_path,
                defect_registry=transport_sources.get("defect_registry"),
                ledger=transport_sources.get("ledger"),
                evaluation_report=transport_sources.get("evaluation_report"),
                audit_artifact=transport_sources.get("audit_artifact"),
                audit_authority_registry=transport_sources.get(
                    "audit_authority_registry"
                ),
            )
        except (OutcomeTransportError, OutcomeTransportVerificationError) as exc:
            raise OperationalOutcomeActionError(
                "AUTO3B_TRANSPORT_FAILED",
                str(exc),
            ) from exc
        _write_json(temporary / "transport.json", transport)

        action = build_operational_outcome_action(
            context=context,
            declaration=declaration,
            transport=transport,
            authority_files=authority_files,
        )
        write_operational_outcome_action(temporary / "action.json", action)
        os.replace(temporary, target)
        committed = True
    finally:
        if not committed and temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)

    return {
        **action,
        "output_root": str(target),
        "context_file": str(target / "context.json"),
        "declaration_file": str(target / "declaration.json"),
        "transport_file": str(target / "transport.json"),
        "workspace_root": str(target / "review-action-source" / "bridge" / "workspace"),
        "authority_source_root": str(target / "authority-source"),
    }
