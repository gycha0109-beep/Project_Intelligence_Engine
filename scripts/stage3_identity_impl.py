from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"{label} not found")
    return text.replace(old, new, 1)


run_path = Path("src/review_system/run.py")
text = run_path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from .io import dump_json, dump_yaml, load_data\nfrom .packs import lock_packs\nfrom .paths import asset\nfrom .profile import resolve_profile_file\n",
    "from .identity import (\n    identity_metadata,\n    review_run_identity,\n    validate_identity_manifest,\n    write_identity_manifest,\n)\nfrom .intelligence_state import capture_project_state\nfrom .io import dump_json, dump_yaml, load_data\nfrom .packs import lock_packs\nfrom .paths import asset\nfrom .profile import repository_root_for, resolve_profile_file\n",
    "run imports",
)
text = replace_once(
    text,
    "def _utc_now() -> str:\n    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()\n\n\n",
    "def _utc_now() -> str:\n    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()\n\n\ndef _refresh_run_identity(root: Path, run: dict[str, Any], *, source_revision: str | None = None) -> None:\n    identity = review_run_identity(run, source_revision=source_revision)\n    run[\"identity\"] = identity_metadata(identity)\n    dump_json(root / \"run.json\", run)\n    write_identity_manifest(root, identity)\n\n\n",
    "identity helper",
)
text = replace_once(
    text,
    "    now = _utc_now()\n    run_id = target.name\n    copied_inputs = _copy_companion_inputs(profile_path, target)\n",
    "    now = _utc_now()\n    run_id = target.name\n    identity_root = (\n        Path(repository_root).resolve()\n        if repository_root is not None\n        else repository_root_for(profile_path, profile)\n    )\n    identity_state = capture_project_state(identity_root, project_id=profile[\"project\"][\"id\"])\n    identity = review_run_identity(\n        {\"run_id\": run_id, \"project_id\": profile[\"project\"][\"id\"]},\n        source_revision=identity_state[\"repository\"].get(\"head_revision\"),\n    )\n    copied_inputs = _copy_companion_inputs(profile_path, target)\n",
    "run initialization",
)
text = replace_once(
    text,
    "        \"copied_inputs\": copied_inputs,\n        \"metrics\": _default_metrics(profile),\n",
    "        \"copied_inputs\": copied_inputs,\n        \"identity\": identity_metadata(identity),\n        \"metrics\": _default_metrics(profile),\n",
    "identity metadata",
)
text = replace_once(
    text,
    "    if snapshot_protected and profile.get(\"protected_paths\"):\n        write_snapshot(profile_path, target / \"protected-baseline.json\", repository_root=repository_root)\n    write_manifest(target, filename=\"initial-manifest.sha256\")\n",
    "    if snapshot_protected and profile.get(\"protected_paths\"):\n        write_snapshot(profile_path, target / \"protected-baseline.json\", repository_root=repository_root)\n    write_identity_manifest(target, identity)\n    write_manifest(target, filename=\"initial-manifest.sha256\")\n",
    "initial identity manifest",
)
text = replace_once(
    text,
    "    errors = validate_review_run_data(run)\n    if errors:\n        raise ValueError(\"invalid synchronized run: \" + \"; \".join(errors))\n    dump_json(run_path, run)\n    return run\n",
    "    errors = validate_review_run_data(run)\n    if errors:\n        raise ValueError(\"invalid synchronized run: \" + \"; \".join(errors))\n    _refresh_run_identity(root, run)\n    return run\n",
    "sync identity",
)
text = replace_once(
    text,
    "    dump_json(root / \"gate-result.json\", result)\n    (root / \"final-gate.md\").write_text(_render_gate_markdown(result, run), encoding=\"utf-8\")\n    return result\n",
    "    dump_json(root / \"gate-result.json\", result)\n    (root / \"final-gate.md\").write_text(_render_gate_markdown(result, run), encoding=\"utf-8\")\n    _refresh_run_identity(root, run)\n    return result\n",
    "gate identity",
)
text = replace_once(
    text,
    "                if run.get(\"metrics\", {}).get(\"protected_baseline_modified\") != (not live[\"intact\"]):\n                    errors.append(\"run protected_baseline_modified metric is stale\")\n    return errors\n\n\ndef archive_run",
    "                if run.get(\"metrics\", {}).get(\"protected_baseline_modified\") != (not live[\"intact\"]):\n                    errors.append(\"run protected_baseline_modified metric is stale\")\n    identity_path = root / \"identity.json\"\n    if identity_path.exists():\n        errors.extend(f\"identity.json: {error}\" for error in validate_identity_manifest(root))\n    return errors\n\n\ndef archive_run",
    "identity validation",
)
text = replace_once(
    text,
    "    errors = validate_run_directory(root, require_gate=True)\n    if errors:\n        raise ValueError(\"run directory is not archivable: \" + \"; \".join(errors))\n    write_manifest(root)\n",
    "    errors = validate_run_directory(root, require_gate=True)\n    if errors:\n        raise ValueError(\"run directory is not archivable: \" + \"; \".join(errors))\n    run = load_data(root / \"run.json\")\n    if not isinstance(run, dict):\n        raise ValueError(\"run.json must contain an object\")\n    _refresh_run_identity(root, run)\n    write_manifest(root)\n",
    "archive identity",
)
run_path.write_text(text, encoding="utf-8")

analyze_path = Path("src/review_system/application/analyze_pr.py")
text = analyze_path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "from ..github_connector import GitHubCLI, collect_pull_request, refresh_source_hash\nfrom ..intelligence_config import load_intelligence_config, load_rules, path_matches\n",
    "from ..github_connector import GitHubCLI, collect_pull_request, refresh_source_hash\nfrom ..identity import pull_request_run_identity, write_identity_manifest\nfrom ..intelligence_config import load_intelligence_config, load_rules, path_matches\n",
    "analyze imports",
)
text = replace_once(
    text,
    "        diff_path = None\n\n    return AnalyzePullRequestResult(\n",
    "        diff_path = None\n\n    identity = pull_request_run_identity(profile[\"project\"][\"id\"], source)\n    write_identity_manifest(output_dir, identity)\n\n    return AnalyzePullRequestResult(\n",
    "PR identity",
)
analyze_path.write_text(text, encoding="utf-8")
