from pathlib import Path


run_path = Path("src/review_system/run.py")
run_text = run_path.read_text(encoding="utf-8")

old_imports = '''from .io import dump_json, dump_yaml, load_data
from .packs import lock_packs
from .paths import asset
from .profile import resolve_profile_file
'''
new_imports = '''from .identity import (
    identity_metadata,
    review_run_identity,
    validate_identity_manifest,
    write_identity_manifest,
)
from .intelligence_state import capture_project_state
from .io import dump_json, dump_yaml, load_data
from .packs import lock_packs
from .paths import asset
from .profile import repository_root_for, resolve_profile_file
'''
if old_imports not in run_text:
    raise SystemExit("run import block not found")
run_text = run_text.replace(old_imports, new_imports, 1)

old_now = '''def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


'''
new_now = '''def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _refresh_run_identity(root: Path, run: dict[str, Any], *, source_revision: str | None = None) -> None:
    identity = review_run_identity(run, source_revision=source_revision)
    run["identity"] = identity_metadata(identity)
    dump_json(root / "run.json", run)
    write_identity_manifest(root, identity)


'''
if old_now not in run_text:
    raise SystemExit("run timestamp helper not found")
run_text = run_text.replace(old_now, new_now, 1)

old_init = '''    now = _utc_now()
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
'''
new_init = '''    now = _utc_now()
    run_id = target.name
    identity_root = (
        Path(repository_root).resolve()
        if repository_root is not None
        else repository_root_for(profile_path, profile)
    )
    identity_state = capture_project_state(identity_root, project_id=profile["project"]["id"])
    identity = review_run_identity(
        {"run_id": run_id, "project_id": profile["project"]["id"]},
        source_revision=identity_state["repository"].get("head_revision"),
    )
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
        "identity": identity_metadata(identity),
        "metrics": _default_metrics(profile),
        "findings": [],
    }
'''
if old_init not in run_text:
    raise SystemExit("run initialization block not found")
run_text = run_text.replace(old_init, new_init, 1)

old_initial_manifest = '''    if snapshot_protected and profile.get("protected_paths"):
        write_snapshot(profile_path, target / "protected-baseline.json", repository_root=repository_root)
    write_manifest(target, filename="initial-manifest.sha256")
    return target
'''
new_initial_manifest = '''    if snapshot_protected and profile.get("protected_paths"):
        write_snapshot(profile_path, target / "protected-baseline.json", repository_root=repository_root)
    write_identity_manifest(target, identity)
    write_manifest(target, filename="initial-manifest.sha256")
    return target
'''
if old_initial_manifest not in run_text:
    raise SystemExit("initial manifest block not found")
run_text = run_text.replace(old_initial_manifest, new_initial_manifest, 1)

old_sync = '''    errors = validate_review_run_data(run)
    if errors:
        raise ValueError("invalid synchronized run: " + "; ".join(errors))
    dump_json(run_path, run)
    return run
'''
new_sync = '''    errors = validate_review_run_data(run)
    if errors:
        raise ValueError("invalid synchronized run: " + "; ".join(errors))
    _refresh_run_identity(root, run)
    return run
'''
if old_sync not in run_text:
    raise SystemExit("sync block not found")
run_text = run_text.replace(old_sync, new_sync, 1)

old_gate_write = '''    dump_json(root / "gate-result.json", result)
    (root / "final-gate.md").write_text(_render_gate_markdown(result, run), encoding="utf-8")
    return result
'''
new_gate_write = '''    dump_json(root / "gate-result.json", result)
    (root / "final-gate.md").write_text(_render_gate_markdown(result, run), encoding="utf-8")
    _refresh_run_identity(root, run)
    return result
'''
if old_gate_write not in run_text:
    raise SystemExit("gate write block not found")
run_text = run_text.replace(old_gate_write, new_gate_write, 1)

old_validation_end = '''                if run.get("metrics", {}).get("protected_baseline_modified") != (not live["intact"]):
                    errors.append("run protected_baseline_modified metric is stale")
    return errors


def archive_run(directory: str | Path, output: str | Path) -> Path:
'''
new_validation_end = '''                if run.get("metrics", {}).get("protected_baseline_modified") != (not live["intact"]):
                    errors.append("run protected_baseline_modified metric is stale")
    identity_path = root / "identity.json"
    if identity_path.exists():
        errors.extend(f"identity.json: {error}" for error in validate_identity_manifest(root))
    return errors


def archive_run(directory: str | Path, output: str | Path) -> Path:
'''
if old_validation_end not in run_text:
    raise SystemExit("run validation end block not found")
run_text = run_text.replace(old_validation_end, new_validation_end, 1)

old_archive = '''    errors = validate_run_directory(root, require_gate=True)
    if errors:
        raise ValueError("run directory is not archivable: " + "; ".join(errors))
    write_manifest(root)
'''
new_archive = '''    errors = validate_run_directory(root, require_gate=True)
    if errors:
        raise ValueError("run directory is not archivable: " + "; ".join(errors))
    run = load_data(root / "run.json")
    if not isinstance(run, dict):
        raise ValueError("run.json must contain an object")
    _refresh_run_identity(root, run)
    write_manifest(root)
'''
if old_archive not in run_text:
    raise SystemExit("archive block not found")
run_text = run_text.replace(old_archive, new_archive, 1)
run_path.write_text(run_text, encoding="utf-8")


analyze_path = Path("src/review_system/application/analyze_pr.py")
analyze_text = analyze_path.read_text(encoding="utf-8")
old_analyze_import = '''from ..github_connector import GitHubCLI, collect_pull_request, refresh_source_hash
from ..intelligence_config import load_intelligence_config, load_rules, path_matches
'''
new_analyze_import = '''from ..github_connector import GitHubCLI, collect_pull_request, refresh_source_hash
from ..identity import pull_request_run_identity, write_identity_manifest
from ..intelligence_config import load_intelligence_config, load_rules, path_matches
'''
if old_analyze_import not in analyze_text:
    raise SystemExit("analyze PR import block not found")
analyze_text = analyze_text.replace(old_analyze_import, new_analyze_import, 1)

old_analyze_return = '''    else:
        if diff_file.exists():
            diff_file.unlink()
        diff_path = None

    return AnalyzePullRequestResult(
'''
new_analyze_return = '''    else:
        if diff_file.exists():
            diff_file.unlink()
        diff_path = None

    identity = pull_request_run_identity(profile["project"]["id"], source)
    write_identity_manifest(output_dir, identity)

    return AnalyzePullRequestResult(
'''
if old_analyze_return not in analyze_text:
    raise SystemExit("analyze PR return block not found")
analyze_text = analyze_text.replace(old_analyze_return, new_analyze_return, 1)
analyze_path.write_text(analyze_text, encoding="utf-8")
