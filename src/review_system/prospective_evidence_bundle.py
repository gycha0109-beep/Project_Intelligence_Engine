from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from .identity import canonical_json_sha256, file_sha256
from .operational_policy import OperationalPolicyError, load_operational_policy
from .operational_policy_match_explanation import (
    OperationalPolicyMatchExplanationError,
    explain_operational_policy_matches,
)
from .prospective_replay import verify_deterministic_result


MANIFEST_SCHEMA_VERSION = "PIE_PROSPECTIVE_EVIDENCE_BUNDLE_V1"
_POLICY_MATCH_EXPLANATION_PATH = "operational/policy-match-explanation.json"
_POLICY_SNAPSHOT_PATH = "operational/base-policy.yml"
_POLICY_BINDING_PATH = "operational/binding.json"
_PROSPECTIVE_CANDIDATE_PATH = "prospective/candidate.json"


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _read_json_object(path: str | Path, field: str) -> dict[str, Any]:
    source = Path(path).resolve()
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"{field} must be a regular file: {path}")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{field} must contain valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{field} must contain an object: {path}")
    return value


def _expected_match_status(cardinality: int) -> str:
    if cardinality == 0:
        return "NO_POLICY_MATCH"
    if cardinality == 1:
        return "UNIQUE_POLICY_MATCH"
    return "AMBIGUOUS_POLICY_MATCH"


def _build_policy_match_explanation(
    *,
    policy_source: str | Path,
    candidate_source: str | Path,
    binding_source: str | Path,
) -> dict[str, Any]:
    try:
        _policy_path, policy = load_operational_policy(policy_source)
        candidate = _read_json_object(candidate_source, "prospective candidate")
        binding = _read_json_object(binding_source, "operational binding")
        changed_files = candidate.get("changed_files")
        if not isinstance(changed_files, list) or not all(isinstance(item, str) for item in changed_files):
            raise ValueError("prospective candidate changed_files must be a string list")
        explanation = explain_operational_policy_matches(policy, changed_files)
    except (OperationalPolicyError, OperationalPolicyMatchExplanationError, ValueError) as exc:
        raise ValueError(f"cannot materialize operational policy match explanation: {exc}") from exc

    binding_policy = binding.get("policy")
    if not isinstance(binding_policy, dict):
        raise ValueError("operational binding policy must contain an object")
    if binding_policy.get("policy_sha256") != explanation["policy"]["policy_sha256"]:
        raise ValueError("operational policy match explanation policy_sha256 disagrees with binding")

    binding_changed_files = binding.get("changed_files")
    if binding_changed_files != changed_files:
        raise ValueError("operational policy match explanation changed_files disagree with binding")

    binding_classes = binding.get("matched_operational_classes")
    if not isinstance(binding_classes, list) or not all(isinstance(item, str) for item in binding_classes):
        raise ValueError("operational binding matched_operational_classes must be a string list")
    if sorted(binding_classes) != explanation["matched_operational_classes"]:
        raise ValueError("operational policy match explanation classes disagree with binding")

    expected_status = _expected_match_status(explanation["match_cardinality"])
    if binding.get("match_status") != expected_status:
        raise ValueError(
            "operational policy match explanation match_status disagrees with binding: "
            f"expected {expected_status}, got {binding.get('match_status')!r}"
        )
    return explanation


def _materialize_policy_match_explanation(
    root: Path,
    evidence_files: Mapping[str, str | Path],
) -> Path | None:
    target = (root / _POLICY_MATCH_EXPLANATION_PATH).resolve()
    target.relative_to(root)
    if _POLICY_MATCH_EXPLANATION_PATH in evidence_files:
        raise ValueError(f"reserved generated evidence path: {_POLICY_MATCH_EXPLANATION_PATH}")
    if target.exists():
        if not target.is_file() or target.is_symlink():
            raise ValueError(f"generated evidence target is unsafe: {target}")
        target.unlink()

    policy_source = evidence_files.get(_POLICY_SNAPSHOT_PATH)
    if policy_source is None:
        return None
    candidate_source = evidence_files.get(_PROSPECTIVE_CANDIDATE_PATH)
    binding_source = evidence_files.get(_POLICY_BINDING_PATH)
    if candidate_source is None or binding_source is None:
        raise ValueError(
            "operational base policy evidence requires prospective candidate and operational binding evidence"
        )
    explanation = _build_policy_match_explanation(
        policy_source=policy_source,
        candidate_source=candidate_source,
        binding_source=binding_source,
    )
    return _write_json(target, explanation)


def copy_evidence_file(bundle_root: str | Path, source: str | Path, relative_path: str) -> Path:
    root = Path(bundle_root).resolve()
    target = (root / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"bundle path escapes root: {relative_path}") from exc
    source_path = Path(source).resolve()
    if not source_path.is_file() or source_path.is_symlink():
        raise ValueError(f"evidence source must be a regular file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, target)
    return target


def write_evidence_bundle(
    bundle_root: str | Path,
    *,
    summary: Mapping[str, Any],
    identity: Mapping[str, Any],
    evidence_files: Mapping[str, str | Path],
    deterministic_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(bundle_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    _materialize_policy_match_explanation(root, evidence_files)
    _write_json(root / "summary.json", dict(summary))
    _write_json(root / "source" / "execution-identity.json", dict(identity))
    if deterministic_result is not None:
        errors = verify_deterministic_result(dict(deterministic_result))
        if errors:
            raise ValueError("invalid deterministic result: " + "; ".join(errors))
        _write_json(root / "deterministic-result.json", dict(deterministic_result))
    for relative_path, source in sorted(evidence_files.items()):
        copy_evidence_file(root, source, relative_path)

    artifacts: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        artifacts.append({
            "path": relative,
            "sha256": file_sha256(path),
            "size_bytes": path.stat().st_size,
        })
    manifest_body = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "execution_id": identity["execution_id"],
        "execution_key_sha256": identity["execution_key_sha256"],
        "repository": summary["repository"],
        "pull_request": summary["pull_request"],
        "source_revision": summary["source_revision"],
        "pie_revision": summary["pie_revision"],
        "assessment_id": summary.get("assessment_id"),
        "packet_id": summary.get("packet_id"),
        "deterministic_result_sha256": (
            deterministic_result.get("deterministic_result_sha256")
            if deterministic_result is not None
            else None
        ),
        "artifacts": artifacts,
    }
    manifest = dict(manifest_body)
    manifest["manifest_sha256"] = canonical_json_sha256(manifest_body)
    _write_json(root / "manifest.json", manifest)
    return manifest


def verify_evidence_bundle(bundle_root: str | Path) -> list[str]:
    root = Path(bundle_root).resolve()
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest.json missing"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("manifest schema_version mismatch")
    body = dict(manifest)
    recorded_manifest_hash = body.pop("manifest_sha256", None)
    if recorded_manifest_hash != canonical_json_sha256(body):
        errors.append("manifest_sha256 mismatch")
    for item in manifest.get("artifacts", []):
        relative = item.get("path")
        if not isinstance(relative, str):
            errors.append("artifact path invalid")
            continue
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            errors.append(f"artifact path escapes root: {relative}")
            continue
        if not path.is_file() or path.is_symlink():
            errors.append(f"artifact missing or unsafe: {relative}")
            continue
        if file_sha256(path) != item.get("sha256"):
            errors.append(f"artifact sha256 mismatch: {relative}")
        if path.stat().st_size != item.get("size_bytes"):
            errors.append(f"artifact size mismatch: {relative}")

    recorded_result_hash = manifest.get("deterministic_result_sha256")
    deterministic_path = root / "deterministic-result.json"
    if recorded_result_hash is not None:
        if not deterministic_path.is_file() or deterministic_path.is_symlink():
            errors.append("deterministic-result.json missing or unsafe")
        else:
            try:
                deterministic_result = json.loads(deterministic_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                errors.append("deterministic-result.json invalid JSON")
            else:
                errors.extend(verify_deterministic_result(deterministic_result))
                if deterministic_result.get("deterministic_result_sha256") != recorded_result_hash:
                    errors.append("manifest deterministic_result_sha256 mismatch")
    elif deterministic_path.exists():
        errors.append("deterministic-result.json present without manifest hash")
    return sorted(set(errors))
