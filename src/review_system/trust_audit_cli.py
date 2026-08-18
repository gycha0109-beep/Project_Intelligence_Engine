from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .trust_audit_verified import (
    TrustAuditError,
    TrustAuditVerificationError,
    add_trust_root,
    authorize_issuer,
    evaluate_audit_authority,
    issue_audit,
    load_audit_artifact,
    load_authority_registry,
    new_authority_registry,
    revoke_issuer,
    verify_audit_artifact_data,
    verify_audit_assessment_binding,
    verify_authority_registry_data,
    write_audit_artifact,
    write_authority_registry,
)
from .trust_comparison import load_registry


def _print_json(value: object, *, stream=None) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False), file=stream or sys.stdout)


def cmd_new_registry(args: argparse.Namespace) -> int:
    registry = new_authority_registry(args.project_id, created_at=args.created_at)
    output = write_authority_registry(args.output, registry)
    _print_json({"valid": True, "output": str(output), "registry_id": registry["registry_id"], "registry_sha256": registry["registry_sha256"]})
    return 0


def cmd_add_root(args: argparse.Namespace) -> int:
    _, registry = load_authority_registry(args.registry)
    updated = add_trust_root(
        registry,
        identity_kind=args.identity_kind,
        subject=args.subject,
        fingerprint=args.fingerprint,
        valid_from=args.valid_from,
        valid_until=args.valid_until,
        registered_at=args.registered_at,
    )
    output = write_authority_registry(args.output, updated)
    root = next(item for item in updated["trust_roots"] if item not in registry["trust_roots"])
    _print_json({"valid": True, "output": str(output), "trust_root_id": root["trust_root_id"], "trust_root_sha256": root["trust_root_sha256"]})
    return 0


def cmd_authorize(args: argparse.Namespace) -> int:
    _, registry = load_authority_registry(args.registry)
    updated = authorize_issuer(
        registry,
        trust_root_id=args.trust_root_id,
        issuer_subject=args.issuer_subject,
        valid_from=args.valid_from,
        valid_until=args.valid_until,
        granted_at=args.granted_at,
    )
    output = write_authority_registry(args.output, updated)
    grant = next(item for item in updated["grants"] if item not in registry["grants"])
    _print_json({"valid": True, "output": str(output), "issuer_id": grant["issuer_id"], "grant_id": grant["grant_id"], "grant_sha256": grant["grant_sha256"]})
    return 0


def cmd_revoke(args: argparse.Namespace) -> int:
    _, registry = load_authority_registry(args.registry)
    updated = revoke_issuer(
        registry,
        grant_id=args.grant_id,
        effective_at=args.effective_at,
        recorded_at=args.recorded_at,
        retroactive=args.retroactive,
        reason_codes=args.reason_code,
    )
    output = write_authority_registry(args.output, updated)
    revocation = next(item for item in updated["revocations"] if item not in registry["revocations"])
    _print_json({"valid": True, "output": str(output), "revocation_id": revocation["revocation_id"], "retroactive": revocation["retroactive"]})
    return 0


def cmd_issue(args: argparse.Namespace) -> int:
    artifact = issue_audit(
        args.comparison_registry,
        args.authority_registry,
        assessment_id=args.assessment_id,
        grant_id=args.grant_id,
        verdict=args.verdict,
        evidence_refs=args.evidence_ref,
        issued_at=args.issued_at,
    )
    output = write_audit_artifact(args.output, artifact)
    _print_json({
        "valid": True,
        "output": str(output),
        "audit_id": artifact["audit_id"],
        "artifact_sha256": artifact["artifact_sha256"],
        "verdict": artifact["verdict"],
        "issuer_id": artifact["issuer_id"],
        "automation_authorized": artifact["automation_authorized"],
        "pilot_authorized": artifact["pilot_authorized"],
    })
    return 0


def cmd_verify_registry(args: argparse.Namespace) -> int:
    source, registry = load_authority_registry(args.registry)
    errors = verify_authority_registry_data(registry)
    _print_json({"valid": not errors, "registry": str(source), "registry_id": registry["registry_id"], "registry_sha256": registry["registry_sha256"], "errors": errors})
    return 0 if not errors else 4


def cmd_verify_artifact(args: argparse.Namespace) -> int:
    source, artifact = load_audit_artifact(args.artifact)
    errors = list(verify_audit_artifact_data(artifact))
    authority_verified = None
    assessment_verified = None
    if args.authority_registry is not None:
        _, registry = load_authority_registry(args.authority_registry)
        authority = evaluate_audit_authority(artifact, registry)
        authority_verified = authority["valid"]
        errors.extend(authority["errors"])
    if args.comparison_registry is not None:
        _, comparison = load_registry(args.comparison_registry)
        assessment = verify_audit_assessment_binding(artifact, comparison)
        assessment_verified = assessment["valid"]
        errors.extend(assessment["errors"])
    _print_json({
        "valid": not errors,
        "artifact": str(source),
        "audit_id": artifact["audit_id"],
        "artifact_sha256": artifact["artifact_sha256"],
        "authority_verified": authority_verified,
        "assessment_verified": assessment_verified,
        "automation_authorized": artifact["automation_authorized"],
        "pilot_authorized": artifact["pilot_authorized"],
        "errors": sorted(set(errors)),
    })
    return 0 if not errors else 4


def add_audit_subparsers(sub: argparse._SubParsersAction) -> None:
    command = sub.add_parser("new-audit-authority", help="Create an empty Independent Audit authority registry.")
    command.add_argument("--project-id", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--created-at")
    command.set_defaults(func=cmd_new_registry)

    command = sub.add_parser("add-audit-trust-root", help="Register a non-backdated trust root for Independent Audit issuers.")
    command.add_argument("--registry", required=True)
    command.add_argument("--identity-kind", required=True, choices=["ORGANIZATION", "TEAM", "EXTERNAL_AUDITOR"])
    command.add_argument("--subject", required=True)
    command.add_argument("--fingerprint", required=True)
    command.add_argument("--valid-from", required=True)
    command.add_argument("--valid-until")
    command.add_argument("--registered-at")
    command.add_argument("--output", required=True)
    command.set_defaults(func=cmd_add_root)

    command = sub.add_parser("authorize-audit-issuer", help="Grant an issuer authority under an exact trust root.")
    command.add_argument("--registry", required=True)
    command.add_argument("--trust-root-id", required=True)
    command.add_argument("--issuer-subject", required=True)
    command.add_argument("--valid-from", required=True)
    command.add_argument("--valid-until")
    command.add_argument("--granted-at")
    command.add_argument("--output", required=True)
    command.set_defaults(func=cmd_authorize)

    command = sub.add_parser("revoke-audit-issuer", help="Revoke an issuer grant with explicit temporal semantics.")
    command.add_argument("--registry", required=True)
    command.add_argument("--grant-id", required=True)
    command.add_argument("--effective-at", required=True)
    command.add_argument("--recorded-at")
    command.add_argument("--retroactive", action="store_true")
    command.add_argument("--reason-code", action="append", default=[])
    command.add_argument("--output", required=True)
    command.set_defaults(func=cmd_revoke)

    command = sub.add_parser("issue-independent-audit", help="Issue a report-only audit artifact bound to a captured Trust assessment.")
    command.add_argument("--comparison-registry", required=True)
    command.add_argument("--authority-registry", required=True)
    command.add_argument("--assessment-id", required=True)
    command.add_argument("--grant-id", required=True)
    command.add_argument("--verdict", required=True, choices=["SAFE", "UNSAFE", "INCONCLUSIVE"])
    command.add_argument("--evidence-ref", action="append", default=[])
    command.add_argument("--issued-at")
    command.add_argument("--output", required=True)
    command.set_defaults(func=cmd_issue)

    command = sub.add_parser("verify-audit-authority", help="Verify an Independent Audit authority registry.")
    command.add_argument("--registry", required=True)
    command.set_defaults(func=cmd_verify_registry)

    command = sub.add_parser("verify-independent-audit", help="Verify an Independent Audit artifact and optional authority/assessment sources.")
    command.add_argument("--artifact", required=True)
    command.add_argument("--authority-registry")
    command.add_argument("--comparison-registry")
    command.set_defaults(func=cmd_verify_artifact)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pie-trust-audit",
        description="Manage repository-backed Independent Audit provenance without granting pilot or automation authority.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    add_audit_subparsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        return args.func(args)
    except TrustAuditVerificationError as exc:
        _print_json({"valid": False, "errors": list(exc.errors)}, stream=sys.stderr)
        return 4
    except (TrustAuditError, TrustComparisonError, TrustComparisonVerificationError, OSError, ValueError) as exc:
        errors = list(exc.errors) if hasattr(exc, "errors") else None
        if errors is not None:
            _print_json({"valid": False, "errors": errors}, stream=sys.stderr)
            return 4
        _print_json({"valid": False, "error": str(exc)}, stream=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
