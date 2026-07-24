from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import mimetypes
from pathlib import Path
import re
from typing import Any, Iterable

from .io import dump_json, load_data


IDENTITY_FILENAME = "identity.json"
IDENTITY_SCHEMA_VERSION = "1.0"
_RUN_TYPES = {"review", "pull_request"}
_EXCLUDED_MANIFEST_FILES = {"initial-manifest.sha256", "manifest.sha256"}
_HEX_RE = re.compile(r"[0-9a-f]+")


@dataclass(frozen=True)
class RunIdentity:
    run_id: str
    run_key_sha256: str
    project_id: str
    run_type: str
    source_revision: str
    source_identifier: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactIdentity:
    artifact_id: str
    artifact_key_sha256: str
    artifact_type: str
    relative_path: str
    sha256: str
    media_type: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def canonical_json_sha256(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_source_revision(value: str | None) -> str:
    if value is None or not value.strip():
        return "unresolved"
    revision = value.strip().lower()
    if revision == "unresolved":
        return revision
    if revision.startswith("git:"):
        digest = revision[4:]
        if not (7 <= len(digest) <= 64 and _HEX_RE.fullmatch(digest)):
            raise ValueError(f"invalid Git source revision: {value!r}")
        return f"git:{digest}"
    if revision.startswith("sha256:"):
        digest = revision[7:]
        if len(digest) != 64 or not _HEX_RE.fullmatch(digest):
            raise ValueError(f"invalid SHA-256 source revision: {value!r}")
        return f"sha256:{digest}"
    if 7 <= len(revision) <= 64 and _HEX_RE.fullmatch(revision):
        return f"git:{revision}"
    raise ValueError(
        "source revision must be a Git SHA, sha256:<digest>, or 'unresolved'; "
        f"symbolic revision is not stable: {value!r}"
    )


def normalize_source_identifier(value: str) -> str:
    identifier = value.strip().replace("\\", "/")
    if not identifier:
        raise ValueError("source identifier must be a non-empty string")
    if any(ord(character) < 32 for character in identifier):
        raise ValueError("source identifier must not contain control characters")
    return identifier


def derive_run_identity(
    *,
    project_id: str,
    run_type: str,
    source_revision: str | None,
    source_identifier: str,
) -> RunIdentity:
    normalized_project = project_id.strip()
    normalized_type = run_type.strip().lower()
    if not normalized_project:
        raise ValueError("project_id must be a non-empty string")
    if normalized_type not in _RUN_TYPES:
        raise ValueError(f"unsupported run_type: {run_type!r}")
    normalized_revision = normalize_source_revision(source_revision)
    normalized_identifier = normalize_source_identifier(source_identifier)
    natural_key = {
        "project_id": normalized_project,
        "run_type": normalized_type,
        "source_revision": normalized_revision,
        "source_identifier": normalized_identifier,
    }
    digest = canonical_json_sha256(natural_key)
    return RunIdentity(
        run_id=f"run-{digest[:32]}",
        run_key_sha256=digest,
        project_id=normalized_project,
        run_type=normalized_type,
        source_revision=normalized_revision,
        source_identifier=normalized_identifier,
    )


def derive_artifact_identity(
    *,
    run_key_sha256: str,
    relative_path: str,
    sha256: str,
    size_bytes: int,
    artifact_type: str | None = None,
    media_type: str | None = None,
) -> ArtifactIdentity:
    if len(run_key_sha256) != 64 or not _HEX_RE.fullmatch(run_key_sha256):
        raise ValueError("run_key_sha256 must be a lowercase SHA-256 digest")
    if len(sha256) != 64 or not _HEX_RE.fullmatch(sha256):
        raise ValueError("artifact sha256 must be a lowercase SHA-256 digest")
    if size_bytes < 0:
        raise ValueError("artifact size_bytes must be non-negative")
    normalized_path = relative_path.replace("\\", "/").strip("/")
    if not normalized_path or normalized_path != relative_path:
        raise ValueError(f"artifact relative path is not canonical: {relative_path!r}")
    natural_key = {
        "run_key_sha256": run_key_sha256,
        "relative_path": normalized_path,
        "sha256": sha256,
    }
    digest = canonical_json_sha256(natural_key)
    return ArtifactIdentity(
        artifact_id=f"artifact-{digest[:32]}",
        artifact_key_sha256=digest,
        artifact_type=artifact_type or infer_artifact_type(normalized_path),
        relative_path=normalized_path,
        sha256=sha256,
        media_type=media_type or infer_media_type(normalized_path),
        size_bytes=size_bytes,
    )


def normalize_relative_path(root: str | Path, value: str | Path) -> str:
    artifact_root = Path(root).resolve()
    raw = Path(value)
    candidate = raw.resolve() if raw.is_absolute() else (artifact_root / raw).resolve()
    try:
        relative = candidate.relative_to(artifact_root)
    except ValueError as exc:
        raise ValueError(f"artifact path escapes root: {value}") from exc
    if relative == Path(".") or not relative.parts:
        raise ValueError("artifact path must identify a file below the artifact root")
    normalized = relative.as_posix()
    if normalized.startswith("../") or "/../" in normalized:
        raise ValueError(f"unsafe artifact path: {value}")
    return normalized


def infer_artifact_type(relative_path: str) -> str:
    name = Path(relative_path).name
    known = {
        "run.json": "review_run",
        "github-source.json": "github_source",
        "impact.json": "impact",
        "REPORT.md": "report",
        "pull-request.diff": "diff",
        "findings.json": "findings",
        "candidate-findings.json": "candidate_findings",
        "rejected-findings.json": "rejected_findings",
        "gate-result.json": "gate_result",
        "gate-policy.yml": "gate_policy",
        "project-profile.resolved.yml": "project_profile",
        "packs.lock.json": "pack_lock",
        "protected-baseline.json": "protected_baseline",
        "protected-baseline-verification.json": "protected_baseline_verification",
    }
    if name in known:
        return known[name]
    suffix = Path(relative_path).suffix.lower().lstrip(".")
    return suffix or "file"


def infer_media_type(relative_path: str) -> str:
    suffix = Path(relative_path).suffix.lower()
    explicit = {
        ".md": "text/markdown",
        ".diff": "text/x-diff",
        ".patch": "text/x-diff",
        ".yml": "application/yaml",
        ".yaml": "application/yaml",
        ".json": "application/json",
    }
    if suffix in explicit:
        return explicit[suffix]
    guessed, _ = mimetypes.guess_type(relative_path)
    return guessed or "application/octet-stream"


def _excluded_from_identity(relative_path: str) -> bool:
    name = Path(relative_path).name
    return relative_path == IDENTITY_FILENAME or name in _EXCLUDED_MANIFEST_FILES


def _artifact_paths(
    root: Path,
    include_paths: Iterable[str | Path] | None,
) -> list[tuple[str, Path]]:
    candidates = list(include_paths) if include_paths is not None else [path for path in root.rglob("*") if path.is_file()]
    resolved: dict[str, Path] = {}
    for candidate in candidates:
        relative = normalize_relative_path(root, candidate)
        if _excluded_from_identity(relative):
            continue
        path = (root / relative).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"artifact does not exist: {relative}")
        resolved[relative] = path
    return sorted(resolved.items())


def build_identity_manifest(
    root: str | Path,
    run_identity: RunIdentity,
    *,
    include_paths: Iterable[str | Path] | None = None,
) -> dict[str, Any]:
    artifact_root = Path(root).resolve()
    artifacts: list[dict[str, Any]] = []
    for relative, path in _artifact_paths(artifact_root, include_paths):
        identity = derive_artifact_identity(
            run_key_sha256=run_identity.run_key_sha256,
            relative_path=relative,
            sha256=file_sha256(path),
            size_bytes=path.stat().st_size,
        )
        artifacts.append(identity.to_dict())
    manifest: dict[str, Any] = {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "run": run_identity.to_dict(),
        "artifacts": artifacts,
    }
    manifest["manifest_sha256"] = canonical_json_sha256(manifest)
    return manifest


def write_identity_manifest(
    root: str | Path,
    run_identity: RunIdentity,
    *,
    include_paths: Iterable[str | Path] | None = None,
) -> Path:
    artifact_root = Path(root).resolve()
    target = artifact_root / IDENTITY_FILENAME
    dump_json(target, build_identity_manifest(artifact_root, run_identity, include_paths=include_paths))
    return target


def identity_metadata(run_identity: RunIdentity) -> dict[str, Any]:
    return {
        "schema_version": IDENTITY_SCHEMA_VERSION,
        "logical_run_id": run_identity.run_id,
        "run_key_sha256": run_identity.run_key_sha256,
        "run_type": run_identity.run_type,
        "source_revision": run_identity.source_revision,
        "source_identifier": run_identity.source_identifier,
    }


def review_run_identity(
    run: dict[str, Any],
    *,
    source_revision: str | None = None,
) -> RunIdentity:
    project_id = run.get("project_id")
    legacy_run_id = run.get("run_id")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("review run project_id must be a non-empty string")
    if not isinstance(legacy_run_id, str) or not legacy_run_id:
        raise ValueError("review run run_id must be a non-empty string")
    metadata = run.get("identity")
    if isinstance(metadata, dict):
        identity = derive_run_identity(
            project_id=project_id,
            run_type=str(metadata.get("run_type", "review")),
            source_revision=str(metadata.get("source_revision", "unresolved")),
            source_identifier=str(metadata.get("source_identifier", f"review://{project_id}/{legacy_run_id}")),
        )
        if metadata.get("logical_run_id") not in {None, identity.run_id}:
            raise ValueError("review run logical_run_id does not match its natural key")
        if metadata.get("run_key_sha256") not in {None, identity.run_key_sha256}:
            raise ValueError("review run run_key_sha256 does not match its natural key")
        return identity
    return derive_run_identity(
        project_id=project_id,
        run_type="review",
        source_revision=source_revision,
        source_identifier=f"review://{project_id}/{legacy_run_id}",
    )


def pull_request_run_identity(project_id: str, source: dict[str, Any]) -> RunIdentity:
    repository = source.get("repository")
    pull_request = source.get("pull_request")
    if not isinstance(repository, dict) or not isinstance(pull_request, dict):
        raise ValueError("pull request source must contain repository and pull_request objects")
    hostname = repository.get("hostname")
    name_with_owner = repository.get("name_with_owner")
    number = pull_request.get("number")
    if not isinstance(hostname, str) or not hostname:
        raise ValueError("pull request repository hostname must be a non-empty string")
    if not isinstance(name_with_owner, str) or "/" not in name_with_owner:
        raise ValueError("pull request repository name_with_owner must be OWNER/REPO")
    if not isinstance(number, int) or isinstance(number, bool) or number < 1:
        raise ValueError("pull request number must be a positive integer")
    head_oid = pull_request.get("head_oid")
    source_hash = source.get("source_sha256")
    if isinstance(head_oid, str) and head_oid:
        revision = head_oid
    elif isinstance(source_hash, str) and len(source_hash) == 64 and _HEX_RE.fullmatch(source_hash):
        revision = f"sha256:{source_hash}"
    else:
        revision = "unresolved"
    identifier = f"github://{hostname.lower()}/{name_with_owner.lower()}/pull/{number}"
    return derive_run_identity(
        project_id=project_id,
        run_type="pull_request",
        source_revision=revision,
        source_identifier=identifier,
    )


def validate_identity_manifest(
    root: str | Path,
    manifest_path: str | Path | None = None,
    *,
    require_complete: bool = True,
) -> list[str]:
    artifact_root = Path(root).resolve()
    target = Path(manifest_path) if manifest_path is not None else artifact_root / IDENTITY_FILENAME
    if not target.is_absolute():
        target = artifact_root / target
    if not target.is_file():
        return [f"identity manifest not found: {target}"]
    try:
        manifest = load_data(target)
    except Exception as exc:
        return [f"identity manifest could not be read: {exc}"]
    if not isinstance(manifest, dict):
        return ["identity manifest must contain an object"]

    errors: list[str] = []
    if manifest.get("schema_version") != IDENTITY_SCHEMA_VERSION:
        errors.append(f"schema_version must be {IDENTITY_SCHEMA_VERSION!r}")

    run_data = manifest.get("run")
    run_identity: RunIdentity | None = None
    if not isinstance(run_data, dict):
        errors.append("run must be an object")
    else:
        try:
            run_identity = derive_run_identity(
                project_id=str(run_data.get("project_id", "")),
                run_type=str(run_data.get("run_type", "")),
                source_revision=str(run_data.get("source_revision", "")),
                source_identifier=str(run_data.get("source_identifier", "")),
            )
        except ValueError as exc:
            errors.append(f"run identity is invalid: {exc}")
        else:
            for field, expected in run_identity.to_dict().items():
                if run_data.get(field) != expected:
                    errors.append(f"run.{field} does not match the natural key")

    recorded_manifest_hash = manifest.get("manifest_sha256")
    if not isinstance(recorded_manifest_hash, str) or len(recorded_manifest_hash) != 64 or not _HEX_RE.fullmatch(recorded_manifest_hash):
        errors.append("manifest_sha256 must be a lowercase SHA-256 digest")
    else:
        candidate = dict(manifest)
        candidate.pop("manifest_sha256", None)
        if canonical_json_sha256(candidate) != recorded_manifest_hash:
            errors.append("manifest_sha256 mismatch")

    artifact_data = manifest.get("artifacts")
    recorded_paths: set[str] = set()
    recorded_ids: set[str] = set()
    if not isinstance(artifact_data, list):
        errors.append("artifacts must be an array")
        artifact_data = []
    for index, item in enumerate(artifact_data):
        prefix = f"artifacts[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{prefix} must be an object")
            continue
        relative = item.get("relative_path")
        if not isinstance(relative, str) or not relative:
            errors.append(f"{prefix}.relative_path must be a non-empty string")
            continue
        if relative in recorded_paths:
            errors.append(f"duplicate artifact relative_path: {relative}")
        recorded_paths.add(relative)
        artifact_id = item.get("artifact_id")
        if isinstance(artifact_id, str):
            if artifact_id in recorded_ids:
                errors.append(f"duplicate artifact_id: {artifact_id}")
            recorded_ids.add(artifact_id)
        try:
            normalized = normalize_relative_path(artifact_root, relative)
        except ValueError as exc:
            errors.append(f"{prefix}.relative_path is unsafe: {exc}")
            continue
        if normalized != relative:
            errors.append(f"{prefix}.relative_path is not canonical")
            continue
        path = (artifact_root / relative).resolve()
        if not path.is_file():
            errors.append(f"missing artifact: {relative}")
            continue
        digest = file_sha256(path)
        size = path.stat().st_size
        if item.get("sha256") != digest:
            errors.append(f"modified artifact: {relative}")
        if item.get("size_bytes") != size:
            errors.append(f"artifact size mismatch: {relative}")
        if run_identity is not None:
            try:
                expected_identity = derive_artifact_identity(
                    run_key_sha256=run_identity.run_key_sha256,
                    relative_path=relative,
                    sha256=digest,
                    size_bytes=size,
                    artifact_type=str(item.get("artifact_type", "")) or None,
                    media_type=str(item.get("media_type", "")) or None,
                )
            except ValueError as exc:
                errors.append(f"{prefix} identity is invalid: {exc}")
            else:
                for field in ("artifact_id", "artifact_key_sha256", "relative_path", "sha256", "size_bytes"):
                    if item.get(field) != expected_identity.to_dict()[field]:
                        errors.append(f"{prefix}.{field} does not match the natural key")

    if require_complete:
        try:
            current_paths = {relative for relative, _ in _artifact_paths(artifact_root, None)}
        except (ValueError, FileNotFoundError) as exc:
            errors.append(f"current artifact inventory is unsafe: {exc}")
        else:
            for relative in sorted(current_paths - recorded_paths):
                errors.append(f"unexpected artifact: {relative}")
            for relative in sorted(recorded_paths - current_paths):
                if not any(error == f"missing artifact: {relative}" for error in errors):
                    errors.append(f"missing artifact: {relative}")
    return errors
