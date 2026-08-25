from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .identity import canonical_json_sha256


SIGNAL_CONTRACT_VERSION = "PIE_SIGNAL_V1"
BRIEF_CONTRACT_VERSION = "PIE_OPERATIONAL_BRIEF_V1"
TARGETED_EVIDENCE_CONTRACT_VERSION = "PIE_TARGETED_EVIDENCE_V1"
INTERFACE_CONTRACT_VERSION = "PIE_GPT_OPERATIONAL_INTERFACE_V1"

LEVEL0_MAX_BYTES = 768
LEVEL1_MAX_BYTES = 4096

_ACTION_REQUIRED = "ACTION_REQUIRED"
_CLEAR = "CLEAR"
_NONE = "NONE"

_AUTHORITY_WORDS = {
    "SAFE",
    "UNSAFE",
    "INCONCLUSIVE",
    "APPROVE",
    "REQUEST_CHANGES",
    "HOLD",
    "REJECT",
    "RECLASSIFY",
}
_FORBIDDEN_COMPACT_KEYS = {
    "policy_sha256",
    "binding_sha256",
    "facts_sha256",
    "assessment_sha256",
    "packet_sha256",
    "candidate_sha256",
    "source_revision",
    "pie_revision",
    "provenance",
    "full_evidence",
}
_SAFE_SLUG = re.compile(r"[^a-z0-9._-]+")


class OperationalLazyInterfaceError(RuntimeError):
    pass


def _json_bytes(value: Mapping[str, Any]) -> int:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return len(payload.encode("utf-8"))


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    values = {item for item in value if isinstance(item, str) and item}
    return sorted(values, key=lambda item: item.encode("utf-8"))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _signal(*, summary: Mapping[str, Any], operational_binding: Mapping[str, Any] | None) -> dict[str, Any]:
    if operational_binding is None:
        if summary.get("status") == "READY_FOR_HUMAN_REVIEW":
            return {
                "contract_version": SIGNAL_CONTRACT_VERSION,
                "status": _ACTION_REQUIRED,
                "reason": "HUMAN_REVIEW_REQUIRED",
                "match_status": None,
                "next": "READ_OPERATIONAL_BRIEF",
            }
        return {
            "contract_version": SIGNAL_CONTRACT_VERSION,
            "status": _CLEAR,
            "reason": "OPERATIONAL_POLICY_NOT_ENABLED",
            "match_status": None,
            "next": _NONE,
        }

    binding_status = operational_binding.get("status")
    match_status = operational_binding.get("match_status")
    if binding_status == "NO_POLICY_MATCH":
        status, reason, next_step = _CLEAR, "NO_POLICY_MATCH", _NONE
    elif binding_status == "AMBIGUOUS_POLICY_MATCH" or match_status == "AMBIGUOUS_POLICY_MATCH":
        status, reason, next_step = _ACTION_REQUIRED, "AMBIGUOUS_POLICY_MATCH", "READ_POLICY_MATCH_DETAILS"
    elif binding_status == "MISSING_TRUST_FIELDS":
        status, reason, next_step = _ACTION_REQUIRED, "MISSING_TRUST_FIELDS", "READ_TRUST_GAPS"
    elif match_status == "UNIQUE_POLICY_MATCH":
        status, reason, next_step = _ACTION_REQUIRED, "UNIQUE_POLICY_MATCH", "READ_OPERATIONAL_BRIEF"
    elif summary.get("status") == "READY_FOR_HUMAN_REVIEW":
        status, reason, next_step = _ACTION_REQUIRED, "HUMAN_REVIEW_REQUIRED", "READ_OPERATIONAL_BRIEF"
    else:
        status = _ACTION_REQUIRED
        reason = str(binding_status or "UNKNOWN_OPERATIONAL_STATE")
        next_step = "READ_OPERATIONAL_BRIEF"

    return {
        "contract_version": SIGNAL_CONTRACT_VERSION,
        "status": status,
        "reason": reason,
        "match_status": match_status if isinstance(match_status, str) else None,
        "next": next_step,
    }


def _directive(reason: str, *, human_action_required: bool) -> dict[str, str]:
    if reason == "AMBIGUOUS_POLICY_MATCH":
        return {
            "code": "SURFACE_POLICY_AMBIGUITY",
            "prompt": "Do not choose an operational class. Read the policy-match details and surface the ambiguity.",
        }
    if reason == "MISSING_TRUST_FIELDS":
        return {
            "code": "SURFACE_TRUST_GAP",
            "prompt": "Do not infer Trust Facts from CI success. Read only the listed gaps and source-backed targeted evidence.",
        }
    if human_action_required:
        return {
            "code": "REQUEST_CANONICAL_HUMAN_REVIEW",
            "prompt": "Request one canonical decision: APPROVE, REQUEST_CHANGES, HOLD, REJECT, or RECLASSIFY.",
        }
    return {
        "code": "READ_OPERATIONAL_REQUIREMENTS",
        "prompt": "Read the compact operational requirements and only the targeted evidence needed for the next action.",
    }


def _target_ids(binding: Mapping[str, Any]) -> list[str]:
    requirements = _mapping(binding.get("requirements"))
    output: set[str] = set()
    if binding.get("match_status") == "AMBIGUOUS_POLICY_MATCH":
        output.add("policy-match-details")
    output.update(f"scenario:{item}" for item in _strings(requirements.get("required_scenarios")))
    output.update(f"evidence:{item}" for item in _strings(requirements.get("required_evidence")))
    for item in _strings(binding.get("missing_inputs")):
        if item in {"rollback_evidence", "replay_evidence"}:
            output.add(f"control:{item}")
    return sorted(output, key=lambda item: item.encode("utf-8"))


def _compact_brief(
    *,
    signal: Mapping[str, Any],
    summary: Mapping[str, Any],
    operational_binding: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if signal["status"] == _CLEAR:
        return None

    binding = _mapping(operational_binding)
    requirements = _mapping(binding.get("requirements"))
    required_scenarios = _strings(requirements.get("required_scenarios"))
    required_evidence = _strings(requirements.get("required_evidence"))
    missing = _strings(binding.get("missing_inputs"))
    human_action_required = summary.get("status") == "READY_FOR_HUMAN_REVIEW"
    reason = str(signal["reason"])

    if reason == "MISSING_TRUST_FIELDS":
        next_step = "PROVIDE_TRUST_INPUT"
    elif reason == "AMBIGUOUS_POLICY_MATCH":
        next_step = "RESOLVE_POLICY_AMBIGUITY"
    elif human_action_required:
        next_step = "REQUEST_HUMAN_REVIEW"
    else:
        next_step = "READ_TARGETED_EVIDENCE"

    return {
        "contract_version": BRIEF_CONTRACT_VERSION,
        "signal_reason": reason,
        "match_status": signal.get("match_status"),
        "operational_class": binding.get("selected_operational_class"),
        "trust_task_class": requirements.get("trust_task_class"),
        "required": {"scenarios": required_scenarios, "evidence": required_evidence},
        "missing": missing,
        "read_evidence": _target_ids(binding),
        "next": next_step,
        "human_action_required": human_action_required,
        "agent_directive": _directive(reason, human_action_required=human_action_required),
    }


def _targeted_evidence(operational_binding: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if operational_binding is None:
        return {}

    binding = operational_binding
    requirements = _mapping(binding.get("requirements"))
    facts = _mapping(binding.get("facts"))
    policy = _mapping(binding.get("policy"))
    supplied = facts.get("supplied") is True

    # No supplied Trust Facts means no evidence may be treated as observed or verified,
    # even if a malformed/non-authoritative projection happens to contain fact-like lists.
    completed = set(_strings(facts.get("completed_scenarios"))) if supplied else set()
    verified = set(_strings(facts.get("verified_evidence"))) if supplied else set()

    provenance = {
        "policy_revision": policy.get("policy_revision"),
        "policy_sha256": policy.get("policy_sha256"),
        "binding_sha256": binding.get("binding_sha256"),
        "facts_sha256": facts.get("facts_sha256") if supplied else None,
    }
    output: dict[str, dict[str, Any]] = {}

    if binding.get("match_status") == "AMBIGUOUS_POLICY_MATCH":
        output["policy-match-details"] = {
            "contract_version": TARGETED_EVIDENCE_CONTRACT_VERSION,
            "id": "policy-match-details",
            "kind": "policy_match",
            "state": "AMBIGUOUS",
            "matched_operational_classes": _strings(binding.get("matched_operational_classes")),
            "provenance": deepcopy(provenance),
        }

    for scenario in _strings(requirements.get("required_scenarios")):
        item_id = f"scenario:{scenario}"
        is_verified = supplied and scenario in completed
        output[item_id] = {
            "contract_version": TARGETED_EVIDENCE_CONTRACT_VERSION,
            "id": item_id,
            "kind": "scenario",
            "requirement": scenario,
            "state": "VERIFIED" if is_verified else "MISSING",
            "observed": is_verified if supplied else None,
            "provenance": deepcopy(provenance),
        }

    for evidence in _strings(requirements.get("required_evidence")):
        item_id = f"evidence:{evidence}"
        is_verified = supplied and evidence in verified
        output[item_id] = {
            "contract_version": TARGETED_EVIDENCE_CONTRACT_VERSION,
            "id": item_id,
            "kind": "required_evidence",
            "requirement": evidence,
            "state": "VERIFIED" if is_verified else "MISSING",
            "observed": is_verified if supplied else None,
            "provenance": deepcopy(provenance),
        }

    for field in ("rollback_evidence", "replay_evidence"):
        if field in _strings(binding.get("missing_inputs")) or supplied:
            item_id = f"control:{field}"
            observed = facts.get(field) if supplied else None
            output[item_id] = {
                "contract_version": TARGETED_EVIDENCE_CONTRACT_VERSION,
                "id": item_id,
                "kind": "trust_control",
                "requirement": field,
                "state": "OBSERVED_TRUE" if observed is True else ("OBSERVED_FALSE" if observed is False else "MISSING"),
                "observed": observed,
                "provenance": deepcopy(provenance),
            }

    return output


def _verify_compact_payload(value: Mapping[str, Any], *, max_bytes: int, label: str) -> None:
    size = _json_bytes(value)
    if size > max_bytes:
        raise OperationalLazyInterfaceError(f"{label} exceeds compact size limit: {size} > {max_bytes}")

    stack: list[tuple[str, Any]] = [("", value)]
    while stack:
        path, item = stack.pop()
        if isinstance(item, Mapping):
            for key, child in item.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key in _FORBIDDEN_COMPACT_KEYS or key.endswith("_sha256"):
                    raise OperationalLazyInterfaceError(f"{label} contains deep-evidence field: {child_path}")
                stack.append((child_path, child))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                stack.append((f"{path}[{index}]", child))

    if label == "Level 0 signal":
        serialized = json.dumps(value, ensure_ascii=False)
        for word in _AUTHORITY_WORDS:
            if word in serialized:
                raise OperationalLazyInterfaceError(f"Level 0 signal must not carry authority vocabulary: {word}")


def build_operational_lazy_interface(
    *,
    summary: Mapping[str, Any],
    operational_binding: Mapping[str, Any] | None,
) -> dict[str, Any]:
    signal = _signal(summary=summary, operational_binding=operational_binding)
    brief = _compact_brief(signal=signal, summary=summary, operational_binding=operational_binding)
    targeted = _targeted_evidence(operational_binding)

    _verify_compact_payload(signal, max_bytes=LEVEL0_MAX_BYTES, label="Level 0 signal")
    if brief is not None:
        _verify_compact_payload(brief, max_bytes=LEVEL1_MAX_BYTES, label="Level 1 brief")

    targeted_ids = sorted(targeted, key=lambda item: item.encode("utf-8"))
    body = {
        "contract_version": INTERFACE_CONTRACT_VERSION,
        "signal": signal,
        "brief": brief,
        "targeted_evidence_ids": targeted_ids,
        "targeted_evidence": targeted,
    }
    return {**body, "interface_sha256": canonical_json_sha256(body)}


def _slug(value: str) -> str:
    result = _SAFE_SLUG.sub("-", value.lower()).strip("-")
    return result[:96] or "evidence"


def write_operational_lazy_interface(root: str | Path, interface: Mapping[str, Any]) -> dict[str, Any]:
    target = Path(root).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    signal = _mapping(interface.get("signal"))
    brief = interface.get("brief")
    targeted = _mapping(interface.get("targeted_evidence"))

    (target / "signal.json").write_text(json.dumps(signal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (target / "SIGNAL.txt").write_text(
        "\n".join(
            [
                SIGNAL_CONTRACT_VERSION,
                f"status: {signal.get('status')}",
                f"reason: {signal.get('reason')}",
                f"next: {signal.get('next')}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    brief_path: str | None = None
    if isinstance(brief, Mapping):
        (target / "brief.json").write_text(json.dumps(dict(brief), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        brief_path = "brief.json"

    targeted_dir = target / "targeted"
    targeted_dir.mkdir(exist_ok=True)
    index: dict[str, str] = {}
    for ordinal, item_id in enumerate(sorted(targeted, key=lambda item: item.encode("utf-8")), start=1):
        payload = targeted[item_id]
        if not isinstance(payload, Mapping):
            raise OperationalLazyInterfaceError(f"targeted evidence must be an object: {item_id}")
        filename = f"{ordinal:02d}-{_slug(item_id)}.json"
        (targeted_dir / filename).write_text(json.dumps(dict(payload), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        index[item_id] = f"targeted/{filename}"
    (targeted_dir / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest_body = {
        "contract_version": INTERFACE_CONTRACT_VERSION,
        "level0": {"signal": "signal.json", "text": "SIGNAL.txt"},
        "level1": {"brief": brief_path},
        "level2": {"index": "targeted/index.json", "items": index},
        "level3": {"full_capsule": "SEPARATE_ARTIFACT"},
        "interface_sha256": interface.get("interface_sha256"),
    }
    manifest = {**manifest_body, "manifest_sha256": canonical_json_sha256(manifest_body)}
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest
