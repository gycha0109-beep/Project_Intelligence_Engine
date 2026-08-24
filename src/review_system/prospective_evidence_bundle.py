from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any, Mapping

from .identity import canonical_json_sha256, file_sha256
from .prospective_replay import verify_deterministic_result


MANIFEST_SCHEMA_VERSION = "PIE_PROSPECTIVE_EVIDENCE_BUNDLE_V1"


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


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
