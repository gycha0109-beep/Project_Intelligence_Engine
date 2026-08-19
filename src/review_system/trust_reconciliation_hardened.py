from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from .trust_audit import TrustAuditError, TrustAuditVerificationError
from .trust_comparison import TrustComparisonError, TrustComparisonVerificationError
from .trust_reconciliation_verified import (
    TrustReconciliationError,
    TrustReconciliationVerificationError,
    load_reconciliation_report,
    load_source_manifest,
    manifest_sha256,
    reconcile_sources,
    verify_reconciliation_report_data,
)
from . import trust_reconciliation as legacy


def verify_reconciliation_report_sources(
    report: dict[str, Any], *, registry_path: str | Path, source_manifest_path: str | Path,
) -> list[str]:
    errors = verify_reconciliation_report_data(report)
    if errors:
        return errors
    try:
        replay = reconcile_sources(registry_path, source_manifest_path, generated_at=report["generated_at"])
    except (
        TrustReconciliationError,
        TrustReconciliationVerificationError,
        TrustComparisonError,
        TrustComparisonVerificationError,
        TrustAuditError,
        TrustAuditVerificationError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
    ) as exc:
        return [f"source replay failed: {exc}"]
    fields = (
        "comparison_registry", "source_manifest", "assessment_reconciliation", "outcome_reconciliation",
        "summary", "status", "evidence_snapshot_sha256", "report_id", "report_sha256",
    )
    return [f"source replay {field} mismatch" for field in fields if replay.get(field) != report.get(field)]


def write_reconciliation_report(path: str | Path, report: dict[str, Any]) -> Path:
    errors = verify_reconciliation_report_data(report)
    if errors:
        raise TrustReconciliationVerificationError(errors)
    target = legacy._safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise TrustReconciliationError(f"cannot write Trust reconciliation report: {exc}") from exc
    return target
