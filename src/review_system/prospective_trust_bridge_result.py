from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

from .identity import canonical_json_sha256


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ProspectiveTrustBridgeResultError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _semantic_packet_projection(packet: dict[str, Any]) -> dict[str, Any]:
    projection = deepcopy(packet)
    for field in ("generated_at", "packet_id", "packet_sha256", "evidence_snapshot_sha256"):
        projection.pop(field, None)
    github = projection.get("github")
    if isinstance(github, dict):
        github.pop("candidate_evidence_snapshot_sha256", None)
        github.pop("candidate_report_sha256", None)
    return projection


def _semantic_bridge_projection(result: dict[str, Any], semantic_packet_sha256: str) -> dict[str, Any]:
    return {
        "schema_version": result.get("schema_version"),
        "result_contract": result.get("result_contract"),
        "bridge_contract": result.get("bridge_contract"),
        "authority": result.get("authority"),
        "target": result.get("target"),
        "trust_request": result.get("trust_request"),
        "status": result.get("status"),
        "assessment_id": result.get("assessment_id"),
        "semantic_packet_sha256": semantic_packet_sha256,
        "risk_band": result.get("risk_band"),
        "readiness": result.get("readiness"),
        "human_review_recorded": result.get("human_review_recorded"),
        "outcome_recorded": result.get("outcome_recorded"),
        "automation_authorized": result.get("automation_authorized"),
        "pilot_authorized": result.get("pilot_authorized"),
        "merge_authorized": result.get("merge_authorized"),
        "deploy_authorized": result.get("deploy_authorized"),
        "production_effect_authorized": result.get("production_effect_authorized"),
    }


def verify_stabilized_bridge_result(result: Any, packet: Any) -> list[str]:
    if not isinstance(result, dict):
        return ["AUTO-2 bridge result must be an object"]
    if not isinstance(packet, dict):
        return ["AUTO-2 Stage 10K packet must be an object"]
    errors: list[str] = []
    semantic_packet_sha256 = canonical_json_sha256(_semantic_packet_projection(packet))
    if result.get("semantic_packet_sha256") != semantic_packet_sha256:
        errors.append("semantic_packet_sha256 mismatch")
    deterministic_result_sha256 = canonical_json_sha256(
        _semantic_bridge_projection(result, semantic_packet_sha256)
    )
    if result.get("deterministic_result_sha256") != deterministic_result_sha256:
        errors.append("deterministic_result_sha256 mismatch")
    return sorted(set(errors))


def stabilize_trusted_bridge_result(result: dict[str, Any]) -> dict[str, Any]:
    bundle = Path(str(result.get("bundle") or "")).expanduser().resolve()
    packet_path = bundle / "review" / "packet.json"
    try:
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProspectiveTrustBridgeResultError(
            "EVIDENCE_HASH_MISMATCH",
            "AUTO-2 Stage 10K packet is unavailable for semantic replay projection",
        ) from exc
    if not isinstance(packet, dict):
        raise ProspectiveTrustBridgeResultError(
            "EVIDENCE_HASH_MISMATCH",
            "AUTO-2 Stage 10K packet must contain a JSON object",
        )

    semantic_packet_sha256 = canonical_json_sha256(_semantic_packet_projection(packet))
    if _SHA256.fullmatch(semantic_packet_sha256) is None:
        raise ProspectiveTrustBridgeResultError(
            "EVIDENCE_HASH_MISMATCH",
            "AUTO-2 semantic packet hash is invalid",
        )
    deterministic_result_sha256 = canonical_json_sha256(
        _semantic_bridge_projection(result, semantic_packet_sha256)
    )

    stabilized = {
        **result,
        "semantic_packet_sha256": semantic_packet_sha256,
        "deterministic_result_sha256": deterministic_result_sha256,
    }

    result_file_raw = result.get("result_file")
    if isinstance(result_file_raw, str) and result_file_raw:
        result_file = Path(result_file_raw).expanduser().resolve()
        try:
            persisted = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProspectiveTrustBridgeResultError(
                "EVIDENCE_HASH_MISMATCH",
                "AUTO-2 bridge result file is unavailable for semantic replay binding",
            ) from exc
        if not isinstance(persisted, dict):
            raise ProspectiveTrustBridgeResultError(
                "EVIDENCE_HASH_MISMATCH",
                "AUTO-2 bridge result file must contain a JSON object",
            )
        persisted["semantic_packet_sha256"] = semantic_packet_sha256
        persisted["deterministic_result_sha256"] = deterministic_result_sha256
        result_file.write_text(
            json.dumps(persisted, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return stabilized
