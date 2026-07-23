from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .io import load_data
from .paths import asset
from .profile import ProfileResolutionError, resolve_profile_file

EVIDENCE_ORDER = {f"E{i}": i for i in range(6)}


class ValidationFailure(ValueError):
    pass


def _format_errors(errors: Iterable[Any]) -> list[str]:
    output = []
    for error in sorted(errors, key=lambda e: list(e.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        output.append(f"{location}: {error.message}")
    return output


def validate_profile_data(data: dict[str, Any]) -> list[str]:
    schema = load_data(asset("core/project-profile-schema.json"))
    errors = _format_errors(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data))
    if not errors:
        packs = data.get("review", {}).get("packs", [])
        available = discover_pack_ids()
        unknown = sorted(set(packs) - available)
        if unknown:
            errors.append("review.packs: unknown pack IDs: " + ", ".join(unknown))
        commands = data.get("commands", {})
        requirements = data.get("gate", {}).get("require", {})
        if requirements.get("baseline_tests") and not commands.get("baseline"):
            errors.append("commands.baseline: required by gate.require.baseline_tests")
        if requirements.get("integration_tests") and not commands.get("integration"):
            errors.append("commands.integration: required by gate.require.integration_tests")
        block_on = data.get("gate", {}).get("block_on", [])
        if "INFO" in block_on:
            errors.append("gate.block_on: INFO cannot block a gate")
        if "P0" not in block_on:
            errors.append("gate.block_on: P0 must always be blocking")
    return errors


def validate_profile_file(path: str | Path) -> tuple[dict[str, Any], list[str]]:
    try:
        data = resolve_profile_file(path)
    except (ProfileResolutionError, FileNotFoundError, OSError, ValueError) as exc:
        return {}, [f"$: profile resolution failed: {exc}"]
    return data, validate_profile_data(data)


def discover_pack_ids() -> set[str]:
    root = asset("packs")
    result: set[str] = set()
    for manifest in root.glob("**/pack.yml"):
        data = load_data(manifest)
        if isinstance(data, dict) and isinstance(data.get("pack_id"), str):
            result.add(data["pack_id"])
    return result


def validate_finding_data(finding: dict[str, Any]) -> list[str]:
    schema = load_data(asset("core/finding-schema.json"))
    errors = _format_errors(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(finding))
    if not isinstance(finding, dict):
        return errors

    evidence = finding.get("evidence", [])
    max_level = max(
        (EVIDENCE_ORDER.get(item.get("level"), -1) for item in evidence if isinstance(item, dict)),
        default=-1,
    )
    confidence = finding.get("confidence")
    status = finding.get("status")
    severity = finding.get("severity")

    if confidence == "SUPPORTED" and max_level < EVIDENCE_ORDER["E2"]:
        errors.append("evidence: SUPPORTED requires E2 or stronger")
    if confidence == "CONFIRMED" and max_level < EVIDENCE_ORDER["E3"]:
        errors.append("evidence: CONFIRMED requires E3 or stronger")
    if confidence == "RESOLVED" and max_level < EVIDENCE_ORDER["E5"]:
        errors.append("evidence: RESOLVED requires E5")
    if confidence in {"CONFIRMED", "RESOLVED"} and not finding.get("reproduction"):
        errors.append("reproduction: required for CONFIRMED or RESOLVED")
    if severity in {"P0", "P1"} and confidence == "HYPOTHESIS":
        errors.append("confidence: P0/P1 cannot be a blocker while HYPOTHESIS")
    if confidence == "REJECTED" and status != "REJECTED":
        errors.append("status: REJECTED confidence requires REJECTED status")
    if status == "REJECTED" and confidence != "REJECTED":
        errors.append("confidence: REJECTED status requires REJECTED confidence")
    if confidence == "RESOLVED" and status not in {"FIXED", "CLOSED"}:
        errors.append("status: RESOLVED confidence requires FIXED or CLOSED status")
    if status == "FIXED" and confidence not in {"SUPPORTED", "CONFIRMED", "RESOLVED"}:
        errors.append("confidence: FIXED status requires SUPPORTED, CONFIRMED, or RESOLVED confidence")
    if status == "CLOSED" and confidence not in {"RESOLVED", "REJECTED"}:
        errors.append("confidence: CLOSED status requires RESOLVED or REJECTED confidence")
    if status in {"OPEN", "ACCEPTED"} and confidence in {"RESOLVED", "REJECTED"}:
        errors.append("status: OPEN/ACCEPTED cannot be RESOLVED or REJECTED")
    if status == "ACCEPTED" and not finding.get("acceptance"):
        errors.append("acceptance: required when status is ACCEPTED")
    if status == "ACCEPTED" and confidence not in {"SUPPORTED", "CONFIRMED"}:
        errors.append("confidence: ACCEPTED status requires SUPPORTED or CONFIRMED confidence")
    if status == "ACCEPTED" and severity == "P0":
        errors.append("status: P0 findings cannot be accepted as residual risk")
    if severity in {"P0", "P1"} and not finding.get("verification"):
        errors.append("verification: P0/P1 findings require at least one verification step")

    scope = finding.get("scope", {})
    if isinstance(scope, dict) and not scope.get("files") and not scope.get("symbols"):
        errors.append("scope: at least one file or symbol is required")

    for index, item in enumerate(evidence if isinstance(evidence, list) else []):
        if not isinstance(item, dict):
            continue
        level = EVIDENCE_ORDER.get(item.get("level"), -1)
        if level >= EVIDENCE_ORDER["E3"] and not (item.get("command") or item.get("location")):
            errors.append(f"evidence.{index}: E3+ requires command or location")
        if level >= EVIDENCE_ORDER["E3"] and not item.get("result"):
            errors.append(f"evidence.{index}: E3+ requires result")
    return errors


def validate_review_run_data(data: dict[str, Any]) -> list[str]:
    schema = load_data(asset("core/review-run-schema.json"))
    errors = _format_errors(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data))
    for finding in data.get("findings", []) if isinstance(data, dict) else []:
        if isinstance(finding, dict):
            errors.extend(
                f"finding[{finding.get('id', '?')}]: {error}"
                for error in validate_finding_data(finding)
            )
    return errors


def validate_review_run_file(path: str | Path) -> tuple[dict[str, Any], list[str]]:
    data = load_data(path)
    if not isinstance(data, dict):
        return {}, ["$: review run must be an object"]
    return data, validate_review_run_data(data)


def validate_findings_file(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    data = load_data(path)
    if not isinstance(data, list):
        raise ValidationFailure("findings file must contain a JSON/YAML array")
    failures: dict[str, list[str]] = {}
    seen: set[str] = set()
    for index, finding in enumerate(data):
        key = finding.get("id", f"index:{index}") if isinstance(finding, dict) else f"index:{index}"
        errors = validate_finding_data(finding if isinstance(finding, dict) else {})
        if key in seen:
            errors.append("id: duplicate finding ID")
        seen.add(key)
        if errors:
            failures[key] = errors
    return data, failures
