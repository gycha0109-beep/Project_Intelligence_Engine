from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from .validation import EVIDENCE_ORDER

_CONFIDENCE_ORDER = {
    "HYPOTHESIS": 0,
    "SUPPORTED": 1,
    "CONFIRMED": 2,
    "RESOLVED": 3,
    "REJECTED": -1,
}
_STATUS_ORDER = {
    "OPEN": 0,
    "ACCEPTED": 0,
    "FIXED": 1,
    "CLOSED": 2,
    "REJECTED": -1,
}


def _max_evidence(finding: dict[str, Any]) -> int:
    return max(
        (
            EVIDENCE_ORDER.get(e.get("level"), -1)
            for e in finding.get("evidence", [])
            if isinstance(e, dict)
        ),
        default=-1,
    )


def _quality(finding: dict[str, Any]) -> tuple[int, int, int]:
    return (
        _max_evidence(finding),
        _CONFIDENCE_ORDER.get(finding.get("confidence"), -2),
        _STATUS_ORDER.get(finding.get("status"), -2),
    )


def merge_findings(groups: Iterable[list[dict[str, Any]]]) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []
    for group_index, group in enumerate(groups):
        for finding in group:
            fid = finding["id"]
            if fid not in merged:
                merged[fid] = deepcopy(finding)
                continue
            current = merged[fid]
            identity_fields = ("title", "category", "severity")
            if any(current.get(field) != finding.get(field) for field in identity_fields):
                conflicts.append(
                    {
                        "id": fid,
                        "reason": "identity_mismatch",
                        "source_index": group_index,
                        "existing": current,
                        "incoming": finding,
                    }
                )
                continue
            if {current.get("confidence"), finding.get("confidence")} & {"REJECTED"} and current.get("confidence") != finding.get("confidence"):
                conflicts.append(
                    {
                        "id": fid,
                        "reason": "rejected_vs_active",
                        "source_index": group_index,
                        "existing": current,
                        "incoming": finding,
                    }
                )
                continue

            evidence_by_key = {
                (
                    item.get("level"), item.get("type"), item.get("location"),
                    item.get("command"), item.get("result"), item.get("summary"),
                ): item
                for item in current.get("evidence", [])
            }
            for item in finding.get("evidence", []):
                key = (
                    item.get("level"), item.get("type"), item.get("location"),
                    item.get("command"), item.get("result"), item.get("summary"),
                )
                evidence_by_key[key] = deepcopy(item)
            current["evidence"] = list(evidence_by_key.values())

            if _quality(finding) > _quality(current):
                for field in (
                    "confidence", "status", "reproduction", "impact",
                    "recommended_action", "verification", "acceptance",
                    "source_pack", "check_id",
                ):
                    if field in finding:
                        current[field] = deepcopy(finding[field])
    return {
        "findings": sorted(merged.values(), key=lambda item: item["id"]),
        "merge_conflicts": conflicts,
    }
