from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TRUST = ROOT / "src" / "review_system" / "trust.py"
SCHEMAS = (
    ROOT / "schemas" / "trust-report.schema.json",
    ROOT / "src" / "review_system" / "assets" / "schemas" / "trust-report.schema.json",
)
TEMP_FILES = (
    ".github/_bootstrap_task_class_corroboration.py",
    ".github/_bootstrap_task_class_corroboration_v2.py",
)


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def replace_block(text: str, start: str, end: str, replacement: str, label: str) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{label}: start anchor missing")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{label}: end anchor missing")
    return text[:start_index] + replacement.rstrip() + text[end_index:]


def patch_trust() -> None:
    text = TRUST.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from .path_globs import expand_trailing_recursive_glob\nfrom .paths import asset\n",
        "from .path_globs import expand_trailing_recursive_glob\nfrom .packs import select_packs_with_reasons\nfrom .paths import asset\n",
        "review-pack import",
    )

    profile_replacement = '''def _profile_descriptor(
    path: str | Path,
    *,
    include_corroboration: bool = True,
) -> tuple[Path, dict[str, Any]]:
    source = _safe_input_file(path, "Project Profile")
    profile = resolve_profile_file(source)
    errors = validate_profile_data(profile)
    if errors:
        raise TrustError("invalid Project Profile: " + "; ".join(errors))
    project = profile.get("project")
    if not isinstance(project, dict) or not isinstance(project.get("id"), str) or not project["id"].strip():
        raise TrustError("Project Profile project.id is required")
    patterns = sorted(
        {
            _normalize_glob(value, f"protected_paths[{index}]")
            for index, value in enumerate(profile.get("protected_paths", []))
        }
    )
    descriptor = {
        "source": source.name,
        "project_id": project["id"].strip(),
        "profile_sha256": canonical_json_sha256(profile),
        "protected_paths": patterns,
    }
    if include_corroboration:
        review = profile.get("review")
        packs = review.get("packs", []) if isinstance(review, dict) else []
        descriptor["configured_review_packs"] = sorted(
            {value.strip() for value in packs if isinstance(value, str) and value.strip()}
        )
    return source, descriptor
'''
    text = replace_block(
        text,
        "def _profile_descriptor(",
        "\n\ndef _band_max",
        profile_replacement,
        "profile descriptor",
    )

    risk_replacement = '''def _is_documentation_path(path: str) -> bool:
    lowered = path.lower()
    return (
        lowered.startswith("docs/")
        or "/docs/" in f"/{lowered}"
        or PurePosixPath(lowered).suffix in {".md", ".rst", ".adoc"}
    )


def _review_pack_corroboration(
    profile: dict[str, Any],
    changed_files: list[str],
) -> dict[str, Any] | None:
    configured = profile.get("configured_review_packs")
    if not isinstance(configured, list):
        return None
    selection = select_packs_with_reasons(changed_files, configured)
    non_documentation = {
        pack: sorted(path for path in paths if not _is_documentation_path(path))
        for pack, paths in selection.items()
    }
    reasons: list[dict[str, Any]] = []

    def add_reason(rule_id: str, paths: list[str]) -> None:
        if not paths:
            return
        reasons.append(
            {
                "reason_id": f"REVIEW_PACK_CORROBORATION:{rule_id}",
                "band": "R3",
                "paths": sorted(set(paths)),
            }
        )

    add_reason(
        "AUTHENTICATION",
        non_documentation.get("application.authentication", []),
    )
    add_reason(
        "MIGRATION_SAFETY",
        [
            *non_documentation.get("application.migration-safety", []),
            *non_documentation.get("data.migration-safety", []),
        ],
    )
    authorization_paths = non_documentation.get("application.authorization", [])
    rls_paths = non_documentation.get("data.rls", [])
    if authorization_paths and rls_paths:
        add_reason("AUTHORIZATION_RLS", [*authorization_paths, *rls_paths])

    floor = _band_max("R0", *[item["band"] for item in reasons])
    return {
        "floor_band": floor,
        "selected_review_packs": sorted(selection),
        "reasons": reasons,
    }


def _risk_projection(request: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    base_band = TASK_CLASS_BANDS[request["task_class"]]
    grouped: dict[tuple[str, str], set[str]] = {}
    path_bands: list[str] = []
    for path in request["changed_files"]:
        band, reason_id = _path_classification(path)
        path_bands.append(band)
        grouped.setdefault((reason_id, band), set()).add(path)
    protected = sorted(
        path
        for path in request["changed_files"]
        if any(_matches_pattern(path, pattern) for pattern in profile["protected_paths"])
    )
    if protected:
        path_bands.append("R3")
        grouped.setdefault(("PROFILE_PROTECTED_PATH", "R3"), set()).update(protected)
    path_floor = _band_max(*path_bands)
    reasons = [
        {
            "reason_id": f"TASK_CLASS:{request['task_class']}",
            "band": base_band,
            "paths": [],
        },
        *[
            {"reason_id": reason_id, "band": band, "paths": sorted(paths)}
            for (reason_id, band), paths in sorted(
                grouped.items(),
                key=lambda item: (BAND_ORDER[item[0][1]], item[0][0]),
            )
        ],
    ]
    output = {
        "base_band": base_band,
        "path_floor_band": path_floor,
        "effective_band": _band_max(base_band, path_floor),
        "protected_files": protected,
        "reasons": reasons,
    }
    corroboration = _review_pack_corroboration(profile, request["changed_files"])
    if corroboration is None:
        return output

    corroborated_floor = corroboration["floor_band"]
    semantic_floor = _band_max(path_floor, corroborated_floor)
    underdeclared = BAND_ORDER[base_band] < BAND_ORDER[semantic_floor]
    reasons.extend(corroboration["reasons"])
    if underdeclared:
        reasons.append(
            {
                "reason_id": "TASK_CLASS_UNDERDECLARED",
                "band": semantic_floor,
                "paths": [],
            }
        )
    output.update(
        {
            "corroborated_semantic_floor_band": corroborated_floor,
            "selected_review_packs": corroboration["selected_review_packs"],
            "task_class_underdeclared": underdeclared,
            "effective_band": _band_max(base_band, path_floor, corroborated_floor),
            "reasons": reasons,
        }
    )
    return output
'''
    text = replace_block(
        text,
        "def _risk_projection(",
        "\n\ndef _empty_ledger_evidence",
        risk_replacement,
        "risk projection",
    )

    text = replace_once(
        text,
        '    high_risk_path = "HIGH_RISK_PATH" in risk_reason_ids\n    verifier_changed = (\n',
        '    high_risk_path = "HIGH_RISK_PATH" in risk_reason_ids\n    corroborated_high_risk = any(\n        reason_id.startswith("REVIEW_PACK_CORROBORATION:")\n        for reason_id in risk_reason_ids\n    )\n    verifier_changed = (\n',
        "corroborated hard-gate signal",
    )

    old_gate = '''        "AUTHORIZATION_OR_MIGRATION_CHANGE": (
            high_risk_task or high_risk_path,
            "TASK",
            sorted(
                {
                    request["task_class"],
                    *[
                        path
                        for item in risk["reasons"]
                        if item["reason_id"] == "HIGH_RISK_PATH"
                        for path in item["paths"]
                    ],
                }
            )
            if high_risk_task or high_risk_path
            else [],
        ),
'''
    new_gate = '''        "AUTHORIZATION_OR_MIGRATION_CHANGE": (
            high_risk_task or high_risk_path or corroborated_high_risk,
            "TASK",
            sorted(
                {
                    request["task_class"],
                    *[
                        path
                        for item in risk["reasons"]
                        if (
                            item["reason_id"] == "HIGH_RISK_PATH"
                            or item["reason_id"].startswith("REVIEW_PACK_CORROBORATION:")
                        )
                        for path in item["paths"]
                    ],
                }
            )
            if high_risk_task or high_risk_path or corroborated_high_risk
            else [],
        ),
'''
    text = replace_once(text, old_gate, new_gate, "authorization hard gate")

    text = replace_once(
        text,
        '    reground_observations: str | Path | None = None,\n    generated_at: str | None = None,\n) -> dict[str, Any]:\n    _, request_data = load_trust_request(request)\n    _, profile_data = _profile_descriptor(profile)\n',
        '    reground_observations: str | Path | None = None,\n    generated_at: str | None = None,\n    _include_corroboration: bool = True,\n) -> dict[str, Any]:\n    _, request_data = load_trust_request(request)\n    _, profile_data = _profile_descriptor(\n        profile, include_corroboration=_include_corroboration\n    )\n',
        "assess signature",
    )

    profile_verification = '''            if profile.get("protected_paths") != normalized_patterns:
                errors.append("profile.protected_paths canonical projection mismatch")
'''
    profile_verification_with_packs = profile_verification + '''            if "configured_review_packs" in profile:
                configured_packs = profile.get("configured_review_packs")
                if not isinstance(configured_packs, list):
                    errors.append("profile.configured_review_packs must be an array")
                else:
                    normalized_packs = sorted(
                        {
                            value.strip()
                            for value in configured_packs
                            if isinstance(value, str) and value.strip()
                        }
                    )
                    if configured_packs != normalized_packs:
                        errors.append(
                            "profile.configured_review_packs canonical projection mismatch"
                        )
'''
    text = replace_once(
        text,
        profile_verification,
        profile_verification_with_packs,
        "profile pack verification",
    )

    text = replace_once(
        text,
        '            reground_observations=reground_observations,\n            generated_at=report["generated_at"],\n        )\n',
        '            reground_observations=reground_observations,\n            generated_at=report["generated_at"],\n            _include_corroboration=(\n                "configured_review_packs" in report.get("profile", {})\n            ),\n        )\n',
        "legacy source replay",
    )
    TRUST.write_text(text, encoding="utf-8")


def patch_schemas() -> None:
    bands = ["R0", "R1", "R2", "R3", "R4"]
    for path in SCHEMAS:
        schema = json.loads(path.read_text(encoding="utf-8"))
        profile_properties = schema["$defs"]["profile"]["properties"]
        profile_properties["configured_review_packs"] = {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        }
        risk_properties = schema["$defs"]["risk"]["properties"]
        risk_properties["corroborated_semantic_floor_band"] = {"enum": bands}
        risk_properties["selected_review_packs"] = {
            "type": "array",
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        }
        risk_properties["task_class_underdeclared"] = {"type": "boolean"}
        path.write_text(
            json.dumps(schema, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


def run_checks() -> None:
    subprocess.run([sys.executable, "scripts/sync_package_assets.py"], cwd=ROOT, check=True)
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        check=True,
    )


def main() -> None:
    patch_trust()
    patch_schemas()
    run_checks()
    subprocess.run(["git", "rm", "--", *TEMP_FILES], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
