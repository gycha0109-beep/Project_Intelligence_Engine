from __future__ import annotations

from typing import Any


def impact_markdown(result: dict[str, Any]) -> str:
    change = result.get("change", {})
    direct = result.get("direct", {})
    impact = result.get("impact", {})
    review = result.get("review", {})
    lines = [
        "# Change Impact Report",
        "",
        f"- Change ID: `{change.get('id') or 'unspecified'}`",
        f"- Base: `{change.get('base_revision') or 'unknown'}`",
        f"- Head: `{change.get('head_revision') or 'unknown'}`",
        f"- Graph: `{result.get('graph_sha256') or 'unknown'}`",
        "",
        "## Direct Change",
        "",
    ]
    changed_files = change.get("changed_files", [])
    lines.extend([f"- `{path}`" for path in changed_files] or ["- None"])
    if direct.get("files_missing_from_graph"):
        lines.extend(["", "### Missing from graph", ""])
        lines.extend(f"- `{path}`" for path in direct["files_missing_from_graph"])
    lines.extend(["", "## Impacted Files", ""])
    for item in impact.get("dependent_files", []):
        lines.append(f"- `{item['path']}` — {item['source']}, confidence {item['confidence']}")
    if not impact.get("dependent_files"):
        lines.append("- None detected")
    lines.extend(["", "## Approved Rules", ""])
    for item in impact.get("matched_rules", []):
        lines.append(f"- `{item['rule_id']}` — {item['title']}")
    if not impact.get("matched_rules"):
        lines.append("- None matched")
    lines.extend(["", "## Recommended Review Packs", ""])
    for pack in review.get("selected_packs", []):
        reasons = ", ".join(review.get("pack_reasons", {}).get(pack, []))
        lines.append(f"- `{pack}` — {reasons}")
    if not review.get("selected_packs"):
        lines.append("- None selected")
    lines.extend(["", "## Required Tests", ""])
    lines.extend(f"- `{test}`" for test in review.get("required_tests", []))
    if not review.get("required_tests"):
        lines.append("- None inferred")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result.get("limitations", []))
    return "\n".join(lines) + "\n"


def comparison_markdown(result: dict[str, Any]) -> str:
    lines = ["# Parallel Change Comparison", "", "| Left | Right | Risk | Score | Reasons |", "|---|---|---:|---:|---|"]
    for item in result.get("comparisons", []):
        reasons = "; ".join(item.get("reasons", [])) or "None"
        lines.append(f"| {item['left']} | {item['right']} | {item['risk_level']} | {item['risk_score']} | {reasons} |")
    if not result.get("comparisons"):
        lines.append("| - | - | none | 0 | Fewer than two change sets |")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in result.get("limitations", []))
    return "\n".join(lines) + "\n"


def pull_request_markdown(source: dict[str, Any], impact: dict[str, Any]) -> str:
    repository = source.get("repository", {})
    pull_request = source.get("pull_request", {})
    direct = impact.get("direct", {})
    impacted = impact.get("impact", {})
    review = impact.get("review", {})
    checks = pull_request.get("checks", [])
    statuses = [
        str(item.get("conclusion") or item.get("state") or "").upper()
        for item in checks
        if isinstance(item, dict)
    ]
    successful = sum(1 for status in statuses if status == "SUCCESS")
    failed = sum(1 for status in statuses if status in {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"})
    pending = max(len(checks) - successful - failed, 0)
    lines = [
        "# PIE Pull Request Analysis",
        "",
        f"- Repository: `{repository.get('name_with_owner') or 'unknown'}`",
        f"- Pull request: `#{pull_request.get('number') or 'unknown'}` — {pull_request.get('title') or 'Untitled'}",
        f"- URL: {pull_request.get('url') or 'unknown'}",
        f"- State: `{pull_request.get('state') or 'unknown'}` / Review: `{pull_request.get('review_decision') or 'unknown'}`",
        f"- Base → Head: `{pull_request.get('base_ref') or 'unknown'}` → `{pull_request.get('head_ref') or 'unknown'}`",
        f"- Changed files: `{len(pull_request.get('changed_files', []))}`",
        f"- CI checks: `{successful} success / {failed} failed / {pending} pending-or-neutral`",
        f"- Source evidence hash: `{source.get('source_sha256') or 'unknown'}`",
        f"- Repository verification: `{source.get('local_repository_verification', {}).get('status') or 'unknown'}`",
        f"- Diff evidence: `{'available' if source.get('diff', {}).get('available') else 'unavailable'}`",
        f"- Discussion evidence: `{'complete' if source.get('discussion', {}).get('complete') else 'incomplete-or-skipped'}`",
        "",
        "## Direct Change",
        "",
    ]
    lines.extend(f"- `{item['path']}`" for item in pull_request.get("changed_files", []) if isinstance(item, dict) and item.get("path"))
    if not pull_request.get("changed_files"):
        lines.append("- None returned by GitHub")
    if direct.get("files_missing_from_graph"):
        lines.extend(["", "### Files missing from the local graph", ""])
        lines.extend(f"- `{path}`" for path in direct["files_missing_from_graph"])
    lines.extend(["", "## Components", ""])
    lines.extend(f"- `{component}`" for component in direct.get("components", []))
    if not direct.get("components"):
        lines.append("- None detected")
    lines.extend(["", "## Impacted Files", ""])
    for item in impacted.get("dependent_files", []):
        lines.append(f"- `{item['path']}` — {item['source']}, confidence {item['confidence']}")
    if not impacted.get("dependent_files"):
        lines.append("- None detected")
    lines.extend(["", "## Recommended Review Packs", ""])
    for pack in review.get("selected_packs", []):
        reasons = ", ".join(review.get("pack_reasons", {}).get(pack, []))
        lines.append(f"- `{pack}` — {reasons}")
    if not review.get("selected_packs"):
        lines.append("- None selected")
    lines.extend(["", "## Required Tests", ""])
    lines.extend(f"- `{test}`" for test in review.get("required_tests", []))
    if not review.get("required_tests"):
        lines.append("- None inferred")
    evidence = impact.get("evidence", [])
    confirmed = sum(1 for item in evidence if isinstance(item, dict) and item.get("classification") == "confirmed_change")
    unknown = sum(1 for item in evidence if isinstance(item, dict) and item.get("classification") == "unknown")
    lines.extend(["", "## Evidence Summary", "", f"- Confirmed changed files in graph: `{confirmed}`", f"- Files not represented in graph: `{unknown}`"])
    lines.extend(["", "## Collection Warnings", ""])
    lines.extend(f"- {warning}" for warning in source.get("warnings", []))
    if not source.get("warnings"):
        lines.append("- None")
    lines.extend(["", "## Analysis Limitations", ""])
    lines.extend(f"- {item}" for item in impact.get("limitations", []))
    return "\n".join(lines) + "\n"
