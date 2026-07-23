from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import shutil
import zipfile

from .baseline import verify_snapshot_file, write_snapshot
from .gate import calculate_gate_from_run, derive_finding_metrics
from .io import dump_json, dump_yaml, load_data
from .packs import lock_packs
from .paths import asset
from .profile import resolve_profile_file
from .validation import (
    validate_findings_file,
    validate_profile_data,
    validate_review_run_data,
)
from .version import get_version

RUN_FILES = {
    "repository-map.md": "templates/repository-map.md",
    "traceability-matrix.md": "templates/traceability-matrix.md",
    "candidate-findings.json": "templates/findings.json",
    "findings.json": "templates/findings.json",
    "rejected-findings.json": "templates/rejected-findings.json",
    "challenge-log.md": "templates/challenge-log.md",
    "verification-log.md": "templates/verification-log.md",
    "evidence-ledger.md": "templates/evidence-ledger.md",
    "residual-risks.md": "templates/residual-risks.md",
    "final-gate.md": "templates/final-gate.md",
}

COMPANION_INPUTS = (
    "invariants.md",
    "architecture-entrypoints.yml",
    "architecture-entrypoints.yaml",
    "architecture-entrypoints.json",
    "accepted-risks.md",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_metrics(profile: dict[str, Any]) -> dict[str, Any]:
    finding_metrics = derive_finding_metrics([], block_on=profile["gate"]["block_on"])
    requirements = profile.get("gate", {}).get("require", {})
    commands = profile.get("commands", {})
    return {
        **finding_metrics,
        "baseline_test_status": "not_run",
        "protected_baseline_modified": False,
        "required_integration_test_not_run": bool(
            requirements.get("integration_tests", bool(commands.get("integration")))
        ),
        "migration_replay_required": bool(
            requirements.get("migration_replay", bool(commands.get("migration_replay")))
        ),
        "migration_replay_verified": False,
        "required_runtime_evidence_missing": False,
        "required_tests_passed": False,
    }


def _copy_companion_inputs(profile_path: str | Path, target: Path) -> list[str]:
    source_dir = Path(profile_path).resolve().parent
    input_dir = target / "inputs"
    copied: list[str] = []
    for name in COMPANION_INPUTS:
        source = source_dir / name
        if source.is_file():
            input_dir.mkdir(exist_ok=True)
            shutil.copy2(source, input_dir / name)
            copied.append(name)
    return copied


def initialize_run(
    profile_path: str | Path,
    output: str | Path,
    mode: str,
    *,
    snapshot_protected: bool = False,
    repository_root: str | Path | None = None,
) -> Path:
    profile = resolve_profile_file(profile_path)
    profile_errors = validate_profile_data(profile)
    if profile_errors:
        raise ValueError("invalid effective profile: " + "; ".join(profile_errors))

    target = Path(output)
    target.mkdir(parents=True, exist_ok=False)
    now = _utc_now()
    run_id = target.name
    copied_inputs = _copy_companion_inputs(profile_path, target)
    pack_lock = lock_packs(profile["review"]["packs"])
    metadata = {
        "run_id": run_id,
        "created_at": now,
        "updated_at": now,
        "project_id": profile["project"]["id"],
        "mode": mode,
        "profile_path": str(Path(profile_path).resolve()),
        "review_system_version": get_version(),
        "selected_packs": profile["review"]["packs"],
        "gate_config": profile["gate"],
        "constraints": profile.get("constraints", {}),
        "copied_inputs": copied_inputs,
        "metrics": _default_metrics(profile),
        "findings": [],
    }
    dump_json(target / "run.json", metadata)
    shutil.copy2(profile_path, target / f"project-profile.source{Path(profile_path).suffix}")
    dump_yaml(target / "project-profile.resolved.yml", profile)
    dump_json(
        target / "packs.lock.json",
        {
            "review_system_version": get_version(),
            "profile_schema_version": profile["schema_version"],
            "packs": pack_lock,
        },
    )
    for destination, source in RUN_FILES.items():
        shutil.copy2(asset(source), target / destination)
    if snapshot_protected and profile.get("protected_paths"):
        write_snapshot(profile_path, target / "protected-baseline.json", repository_root=repository_root)
    write_manifest(target, filename="initial-manifest.sha256")
    return target


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(directory: str | Path, *, filename: str = "manifest.sha256") -> Path:
    root = Path(directory)
    excluded = {filename, "manifest.sha256"}
    lines = []
    for file in sorted(p for p in root.rglob("*") if p.is_file() and p.name not in excluded):
        lines.append(f"{_sha256(file)}  {file.relative_to(root).as_posix()}")
    target = root / filename
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def verify_manifest(directory: str | Path, manifest: str | Path | None = None) -> dict[str, Any]:
    root = Path(directory)
    if manifest is None:
        manifest_path = root / "manifest.sha256"
    else:
        manifest_path = Path(manifest)
        if not manifest_path.is_absolute():
            manifest_path = root / manifest_path
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")
    expected: dict[str, str] = {}
    malformed: list[str] = []
    for line_number, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            digest, relative = line.split("  ", 1)
        except ValueError:
            malformed.append(f"line {line_number}: {line}")
            continue
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            malformed.append(f"line {line_number}: unsafe path {relative}")
            continue
        expected[relative_path.as_posix()] = digest
    missing: list[str] = []
    modified: list[str] = []
    for relative, digest in expected.items():
        path = root / relative
        if not path.is_file():
            missing.append(relative)
        elif _sha256(path) != digest:
            modified.append(relative)
    current = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and p.resolve() != manifest_path.resolve() and p.name != "manifest.sha256"
    }
    unexpected = sorted(current - set(expected))
    return {
        "valid": not (malformed or missing or modified or unexpected),
        "manifest": str(manifest_path),
        "malformed": malformed,
        "missing": sorted(missing),
        "modified": sorted(modified),
        "unexpected": unexpected,
    }


def sync_run(directory: str | Path) -> dict[str, Any]:
    root = Path(directory)
    run_path = root / "run.json"
    findings_path = root / "findings.json"
    run = load_data(run_path)
    if not isinstance(run, dict):
        raise ValueError("run.json must contain an object")
    findings, failures = validate_findings_file(findings_path)
    if failures:
        details = "; ".join(f"{fid}: {', '.join(errors)}" for fid, errors in failures.items())
        raise ValueError(f"invalid findings: {details}")
    finding_metrics = derive_finding_metrics(
        findings,
        block_on=run.get("gate_config", {}).get("block_on", ["P0", "P1"]),
    )
    run["findings"] = findings
    run.setdefault("metrics", {}).update(finding_metrics)
    run["updated_at"] = _utc_now()
    errors = validate_review_run_data(run)
    if errors:
        raise ValueError("invalid synchronized run: " + "; ".join(errors))
    dump_json(run_path, run)
    return run


def _render_gate_markdown(result: dict[str, Any], run: dict[str, Any]) -> str:
    lines = [
        "# Final Review Gate",
        "",
        f"- Decision: **{result['decision']}**",
        f"- Run: `{run['run_id']}`",
        f"- Project: `{run['project_id']}`",
        f"- Review System: `{run.get('review_system_version', 'unknown')}`",
        f"- Policy version: `{result.get('policy', {}).get('version', 'unknown')}`",
        "",
        "## Triggered Rules",
        "",
    ]
    any_rule = False
    for section in ("fail", "hold", "conditional_pass", "pass"):
        for rule in result["triggered"].get(section, []):
            any_rule = True
            lines.append(f"- `{section.upper()}` `{rule['id']}` — {rule['message']}")
    if not any_rule:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Effective Metrics",
            "",
            "```json",
            json.dumps(result["effective_metrics"], indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def calculate_gate_directory(
    directory: str | Path,
    *,
    policy_path: str | Path | None = None,
    repository_root: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(directory)
    run = sync_run(root)
    snapshot = root / "protected-baseline.json"
    protected_result = None
    if snapshot.exists():
        protected_result = verify_snapshot_file(snapshot, repository_root=repository_root)
        run["metrics"]["protected_baseline_modified"] = not protected_result["intact"]
        dump_json(root / "protected-baseline-verification.json", protected_result)

    run["updated_at"] = _utc_now()
    dump_json(root / "run.json", run)
    selected_policy = Path(policy_path) if policy_path else asset("core/default-gate-policy.yml")
    policy_copy = root / "gate-policy.yml"
    policy_copy.write_bytes(selected_policy.read_bytes())
    policy = load_data(policy_copy)
    result = calculate_gate_from_run(run, policy)
    result["generated_at"] = _utc_now()
    result["policy"] = {
        "version": str(policy.get("version", "unknown")) if isinstance(policy, dict) else "unknown",
        "source": "gate-policy.yml",
        "sha256": _sha256(policy_copy),
    }
    if protected_result is not None:
        result["protected_baseline_verification"] = protected_result
    dump_json(root / "gate-result.json", result)
    (root / "final-gate.md").write_text(_render_gate_markdown(result, run), encoding="utf-8")
    return result


def validate_run_directory(directory: str | Path, *, require_gate: bool = False) -> list[str]:
    root = Path(directory)
    errors: list[str] = []
    required = {"run.json", "findings.json", "project-profile.resolved.yml", "packs.lock.json"}
    if require_gate:
        required.update({"gate-result.json", "gate-policy.yml", "final-gate.md"})
    missing = sorted(name for name in required if not (root / name).is_file())
    errors.extend(f"missing required file: {name}" for name in missing)
    if errors:
        return errors

    run = load_data(root / "run.json")
    profile = load_data(root / "project-profile.resolved.yml")
    pack_lock = load_data(root / "packs.lock.json")
    if not isinstance(run, dict):
        return ["run.json must contain an object"]
    if not isinstance(profile, dict):
        return ["project-profile.resolved.yml must contain an object"]
    if not isinstance(pack_lock, dict):
        return ["packs.lock.json must contain an object"]

    errors.extend(validate_profile_data(profile))
    errors.extend(validate_review_run_data(run))
    findings, failures = validate_findings_file(root / "findings.json")
    for finding_id, finding_errors in failures.items():
        errors.extend(f"findings.json:{finding_id}: {error}" for error in finding_errors)
    if run.get("findings", []) != findings:
        errors.append("run.json findings are not synchronized with findings.json")

    if run.get("project_id") != profile.get("project", {}).get("id"):
        errors.append("run.json project_id does not match resolved profile")
    if run.get("selected_packs") != profile.get("review", {}).get("packs"):
        errors.append("run.json selected_packs do not match resolved profile")
    if run.get("gate_config") != profile.get("gate"):
        errors.append("run.json gate_config does not match resolved profile")
    locked_ids = [item.get("pack_id") for item in pack_lock.get("packs", []) if isinstance(item, dict)]
    if locked_ids != run.get("selected_packs"):
        errors.append("packs.lock.json does not match selected_packs")

    if require_gate:
        gate = load_data(root / "gate-result.json")
        if not isinstance(gate, dict):
            errors.append("gate-result.json must contain an object")
        else:
            policy_path = root / "gate-policy.yml"
            policy = load_data(policy_path)
            current = calculate_gate_from_run(run, policy)
            for field in ("decision", "triggered", "effective_metrics", "block_on"):
                if gate.get(field) != current.get(field):
                    errors.append(f"gate-result.json {field} is stale relative to run.json and gate-policy.yml")
            if gate.get("decision") not in {"FAIL", "HOLD", "CONDITIONAL_PASS", "PASS"}:
                errors.append("gate-result.json has an invalid decision")
            policy_meta = gate.get("policy", {})
            if policy_meta.get("sha256") != _sha256(policy_path):
                errors.append("gate-result.json policy hash does not match gate-policy.yml")
            expected_markdown = _render_gate_markdown(gate, run)
            if (root / "final-gate.md").read_text(encoding="utf-8") != expected_markdown:
                errors.append("final-gate.md is stale relative to gate-result.json")

        snapshot = root / "protected-baseline.json"
        if snapshot.exists():
            verification_path = root / "protected-baseline-verification.json"
            if not verification_path.exists():
                errors.append("protected baseline snapshot exists without verification result")
            else:
                recorded = load_data(verification_path)
                live = verify_snapshot_file(snapshot)
                if recorded != live:
                    errors.append("protected baseline verification is stale")
                if run.get("metrics", {}).get("protected_baseline_modified") != (not live["intact"]):
                    errors.append("run protected_baseline_modified metric is stale")
    return errors


def archive_run(directory: str | Path, output: str | Path) -> Path:
    root = Path(directory).resolve()
    target = Path(output).resolve()
    if target == root or root in target.parents:
        raise ValueError("archive output must be outside the run directory")
    errors = validate_run_directory(root, require_gate=True)
    if errors:
        raise ValueError("run directory is not archivable: " + "; ".join(errors))
    write_manifest(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(p for p in root.rglob("*") if p.is_file()):
            archive.write(file, arcname=f"{root.name}/{file.relative_to(root).as_posix()}")
    return target
