from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Iterable

from jsonschema import Draft202012Validator, FormatChecker

from .identity import canonical_json_sha256
from .io import load_data
from .paths import asset


SCHEMA_VERSION = "1.0"
CONTRACT_VERSION = "PIE_AUTO3_EXPLICIT_OUTCOME_DECLARATION_V1"
STAGE = "AUTO-3A"
MODE = "EXPLICIT_HUMAN_OUTCOME_DECLARATION"
STATUS = "EXPLICIT_OUTCOME_DECLARATION_VALIDATED"
NEXT_STEP = "AUTO3B_VERIFY_AUTHORITY_SOURCE_AND_RECORD"

SUPPORTED_AUTHORITIES = {
    "PRODUCTION_DEFECT",
    "CONTROLLED_EVALUATION",
    "INDEPENDENT_AUDIT",
}
SUPPORTED_VERDICTS = {"SAFE", "UNSAFE", "INCONCLUSIVE"}
SUPPORTED_REVIEW_LEVELS = {"REVIEWED", "AUDITED"}
SUPPORTED_DECISIONS = {"APPROVE", "REQUEST_CHANGES", "HOLD", "REJECT", "RECLASSIFY"}

_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ASSESSMENT_ID = re.compile(r"^assessment-[0-9a-f]{32}$")
_EVENT_ID = re.compile(r"^event-[0-9a-f]{32}$")
_PACKET_ID = re.compile(r"^prospective-review-packet-[0-9a-f]{32}$")


class OutcomeDeclarationError(RuntimeError):
    pass


class OutcomeDeclarationVerificationError(OutcomeDeclarationError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(sorted(set(errors)))
        super().__init__("invalid explicit Outcome declaration: " + "; ".join(self.errors))


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OutcomeDeclarationError(f"{field} must be a non-empty string")
    return value.strip()


def _timestamp(value: Any, field: str) -> str:
    text = _text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OutcomeDeclarationError(f"{field} is invalid: {text}") from exc
    if parsed.tzinfo is None:
        raise OutcomeDeclarationError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(value: Any, field: str) -> str:
    text = _text(value, field).lower()
    if _SHA256.fullmatch(text) is None:
        raise OutcomeDeclarationError(f"{field} must be a lowercase SHA-256")
    return text


def _source_revision(value: Any) -> str:
    text = _text(value, "source_revision").lower()
    if text.startswith("git:"):
        sha = text[4:]
    else:
        sha = text
    if _SHA40.fullmatch(sha) is None:
        raise OutcomeDeclarationError("source_revision must bind an exact 40-character Git SHA")
    return f"git:{sha}"


def _optional_text(value: Any, field: str) -> str | None:
    return None if value is None else _text(value, field)


def _optional_sha256(value: Any, field: str) -> str | None:
    return None if value is None else _sha256(value, field)


def _schema_errors(value: Any) -> list[str]:
    schema = load_data(asset("schemas/explicit-outcome-declaration.schema.json"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for error in sorted(validator.iter_errors(value), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append(f"{location}: {error.message}")
    return errors


def _payload(value: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(value)
    output.pop("declaration_id", None)
    output.pop("declaration_sha256", None)
    return output


def _expected_source_binding(authority_type: str, source: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fields = {
        "defect_registry_sha256",
        "ledger_sha256",
        "evaluation_id",
        "evaluation_report_sha256",
        "audit_id",
        "audit_artifact_sha256",
        "audit_authority_registry_sha256",
    }
    required = {
        "PRODUCTION_DEFECT": {"defect_registry_sha256", "ledger_sha256"},
        "CONTROLLED_EVALUATION": {"evaluation_id", "evaluation_report_sha256"},
        "INDEPENDENT_AUDIT": {"audit_id", "audit_artifact_sha256", "audit_authority_registry_sha256"},
    }[authority_type]
    for field in sorted(required):
        if not source.get(field):
            errors.append(f"outcome.source_binding.{field} is required for {authority_type}")
    for field in sorted(fields - required):
        if source.get(field) is not None:
            errors.append(f"outcome.source_binding.{field} must be null for {authority_type}")
    return errors


def build_outcome_declaration(
    *,
    actor: str,
    project_id: str,
    assessment_id: str,
    source_revision: str,
    trust_report_id: str,
    trust_report_sha256: str,
    review_event_id: str,
    review_event_sha256: str,
    review_level: str,
    decision: str,
    review_packet_id: str,
    review_packet_sha256: str,
    authority_type: str,
    verdict: str,
    declared_at: str | None = None,
    defect_id: str | None = None,
    evidence_refs: Iterable[str] = (),
    defect_registry_sha256: str | None = None,
    ledger_sha256: str | None = None,
    evaluation_id: str | None = None,
    evaluation_report_sha256: str | None = None,
    audit_id: str | None = None,
    audit_artifact_sha256: str | None = None,
    audit_authority_registry_sha256: str | None = None,
) -> dict[str, Any]:
    assessment = _text(assessment_id, "assessment_id").lower()
    if _ASSESSMENT_ID.fullmatch(assessment) is None:
        raise OutcomeDeclarationError("assessment_id must be an exact assessment identifier")
    review_event = _text(review_event_id, "review_event_id").lower()
    if _EVENT_ID.fullmatch(review_event) is None:
        raise OutcomeDeclarationError("review_event_id must be an exact event identifier")
    packet_id = _text(review_packet_id, "review_packet_id").lower()
    if _PACKET_ID.fullmatch(packet_id) is None:
        raise OutcomeDeclarationError("review_packet_id must be an exact governed review packet identifier")

    level = _text(review_level, "review_level").upper()
    if level not in SUPPORTED_REVIEW_LEVELS:
        raise OutcomeDeclarationError("AUTO-3 requires a prior REVIEWED or AUDITED human decision")
    review_decision = _text(decision, "decision").upper()
    if review_decision not in SUPPORTED_DECISIONS:
        raise OutcomeDeclarationError("decision is invalid")

    authority = _text(authority_type, "authority_type").upper()
    if authority not in SUPPORTED_AUTHORITIES:
        raise OutcomeDeclarationError("authority_type is not source-reconcilable in AUTO-3")
    outcome_verdict = _text(verdict, "verdict").upper()
    if outcome_verdict not in SUPPORTED_VERDICTS:
        raise OutcomeDeclarationError("verdict must be SAFE, UNSAFE, or INCONCLUSIVE")
    if authority == "PRODUCTION_DEFECT" and outcome_verdict == "SAFE":
        raise OutcomeDeclarationError("PRODUCTION_DEFECT authority cannot prove SAFE")
    normalized_defect_id = _optional_text(defect_id, "defect_id")
    if authority == "PRODUCTION_DEFECT" and normalized_defect_id is None:
        raise OutcomeDeclarationError("PRODUCTION_DEFECT requires defect_id")
    if authority != "PRODUCTION_DEFECT" and normalized_defect_id is not None:
        raise OutcomeDeclarationError(f"defect_id must be null for {authority}")

    refs = sorted({_text(value, "evidence_ref") for value in evidence_refs})
    source_binding = {
        "defect_registry_sha256": _optional_sha256(defect_registry_sha256, "defect_registry_sha256"),
        "ledger_sha256": _optional_sha256(ledger_sha256, "ledger_sha256"),
        "evaluation_id": _optional_text(evaluation_id, "evaluation_id"),
        "evaluation_report_sha256": _optional_sha256(evaluation_report_sha256, "evaluation_report_sha256"),
        "audit_id": _optional_text(audit_id, "audit_id"),
        "audit_artifact_sha256": _optional_sha256(audit_artifact_sha256, "audit_artifact_sha256"),
        "audit_authority_registry_sha256": _optional_sha256(
            audit_authority_registry_sha256,
            "audit_authority_registry_sha256",
        ),
    }
    source_errors = _expected_source_binding(authority, source_binding)
    if source_errors:
        raise OutcomeDeclarationVerificationError(source_errors)

    value: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "stage": STAGE,
        "mode": MODE,
        "declaration_id": "",
        "declared_at": _timestamp(declared_at or utc_now(), "declared_at"),
        "actor": _text(actor, "actor"),
        "project_id": _text(project_id, "project_id"),
        "assessment": {
            "assessment_id": assessment,
            "source_revision": _source_revision(source_revision),
            "trust_report_id": _text(trust_report_id, "trust_report_id"),
            "trust_report_sha256": _sha256(trust_report_sha256, "trust_report_sha256"),
        },
        "review": {
            "event_id": review_event,
            "event_sha256": _sha256(review_event_sha256, "review_event_sha256"),
            "review_level": level,
            "decision": review_decision,
            "review_packet_id": packet_id,
            "review_packet_sha256": _sha256(review_packet_sha256, "review_packet_sha256"),
        },
        "outcome": {
            "authority_type": authority,
            "verdict": outcome_verdict,
            "defect_id": normalized_defect_id,
            "evidence_refs": refs,
            "source_binding": source_binding,
        },
        "human_outcome_declared": True,
        "automatic_outcome_inference": False,
        "outcome_recorded": False,
        "automation_authorized": False,
        "pilot_authorized": False,
        "merge_authorized": False,
        "deploy_authorized": False,
        "production_effect_authorized": False,
        "status": STATUS,
        "next_step": NEXT_STEP,
        "declaration_sha256": "",
    }
    digest = canonical_json_sha256(_payload(value))
    value["declaration_id"] = f"outcome-declaration-{digest[:32]}"
    value["declaration_sha256"] = canonical_json_sha256(_payload(value))
    errors = verify_outcome_declaration_data(value)
    if errors:
        raise OutcomeDeclarationVerificationError(errors)
    return value


def verify_outcome_declaration_data(value: Any) -> list[str]:
    errors = _schema_errors(value)
    if not isinstance(value, dict):
        return sorted(set(errors or ["declaration must contain an object"]))

    if value.get("contract_version") != CONTRACT_VERSION or value.get("stage") != STAGE or value.get("mode") != MODE:
        errors.append("AUTO-3A contract identity mismatch")
    if value.get("human_outcome_declared") is not True:
        errors.append("human_outcome_declared must be true")
    for field in (
        "automatic_outcome_inference",
        "outcome_recorded",
        "automation_authorized",
        "pilot_authorized",
        "merge_authorized",
        "deploy_authorized",
        "production_effect_authorized",
    ):
        if value.get(field) is not False:
            errors.append(f"{field} must remain false")
    if value.get("status") != STATUS or value.get("next_step") != NEXT_STEP:
        errors.append("status/next_step mismatch")

    assessment = value.get("assessment") if isinstance(value.get("assessment"), dict) else {}
    assessment_id = assessment.get("assessment_id")
    if not isinstance(assessment_id, str) or _ASSESSMENT_ID.fullmatch(assessment_id) is None:
        errors.append("assessment.assessment_id binding is invalid")
    source_revision = assessment.get("source_revision")
    if not isinstance(source_revision, str) or not source_revision.startswith("git:") or _SHA40.fullmatch(source_revision[4:]) is None:
        errors.append("assessment.source_revision binding is invalid")
    trust_hash = assessment.get("trust_report_sha256")
    if not isinstance(trust_hash, str) or _SHA256.fullmatch(trust_hash) is None:
        errors.append("assessment.trust_report_sha256 binding is invalid")

    review = value.get("review") if isinstance(value.get("review"), dict) else {}
    if review.get("review_level") not in SUPPORTED_REVIEW_LEVELS:
        errors.append("AUTO-3 requires REVIEWED or AUDITED prior review")
    if review.get("decision") not in SUPPORTED_DECISIONS:
        errors.append("review.decision is invalid")
    event_id = review.get("event_id")
    if not isinstance(event_id, str) or _EVENT_ID.fullmatch(event_id) is None:
        errors.append("review.event_id binding is invalid")
    packet_id = review.get("review_packet_id")
    if not isinstance(packet_id, str) or _PACKET_ID.fullmatch(packet_id) is None:
        errors.append("review.review_packet_id binding is invalid")
    for field in ("event_sha256", "review_packet_sha256"):
        item = review.get(field)
        if not isinstance(item, str) or _SHA256.fullmatch(item) is None:
            errors.append(f"review.{field} binding is invalid")

    outcome = value.get("outcome") if isinstance(value.get("outcome"), dict) else {}
    authority = outcome.get("authority_type")
    verdict = outcome.get("verdict")
    if authority not in SUPPORTED_AUTHORITIES:
        errors.append("outcome.authority_type is unsupported")
    elif isinstance(outcome.get("source_binding"), dict):
        errors.extend(_expected_source_binding(authority, outcome["source_binding"]))
    if verdict not in SUPPORTED_VERDICTS:
        errors.append("outcome.verdict is invalid")
    if authority == "PRODUCTION_DEFECT" and verdict == "SAFE":
        errors.append("PRODUCTION_DEFECT authority cannot prove SAFE")
    if authority == "PRODUCTION_DEFECT" and not outcome.get("defect_id"):
        errors.append("PRODUCTION_DEFECT requires defect_id")
    if authority in {"CONTROLLED_EVALUATION", "INDEPENDENT_AUDIT"} and outcome.get("defect_id") is not None:
        errors.append(f"defect_id must be null for {authority}")

    expected_digest = canonical_json_sha256(_payload(value))
    expected_id = f"outcome-declaration-{expected_digest[:32]}"
    if value.get("declaration_id") != expected_id:
        errors.append("declaration_id mismatch")
    if value.get("declaration_sha256") != expected_digest:
        errors.append("declaration_sha256 mismatch")

    return sorted(set(errors))


def verify_outcome_declaration_file(path: str) -> dict[str, Any]:
    value = load_data(path)
    errors = verify_outcome_declaration_data(value)
    if errors:
        raise OutcomeDeclarationVerificationError(errors)
    assert isinstance(value, dict)
    return value
