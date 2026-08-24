from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from .identity import canonical_json_sha256


_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ProspectiveExecutionIdentity:
    schema_version: str
    execution_id: str
    execution_key_sha256: str
    repository: str
    pull_request: int
    source_revision: str
    pie_revision: str
    profile_sha256: str
    config_sha256: str
    trust_request_sha256: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sha40(value: str, field: str) -> str:
    normalized = value.strip().lower()
    if _SHA40.fullmatch(normalized) is None:
        raise ValueError(f"{field} must be an exact 40-character Git SHA")
    return normalized


def _sha256(value: str, field: str) -> str:
    normalized = value.strip().lower()
    if _SHA256.fullmatch(normalized) is None:
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return normalized


def build_prospective_execution_identity(
    *,
    repository: str,
    pull_request: int,
    source_revision: str,
    pie_revision: str,
    profile_sha256: str,
    config_sha256: str,
    trust_request_sha256: str | None,
) -> ProspectiveExecutionIdentity:
    repo = repository.strip().lower()
    if not repo or "/" not in repo:
        raise ValueError("repository must be OWNER/REPO")
    if pull_request <= 0:
        raise ValueError("pull_request must be positive")
    source = _sha40(source_revision, "source_revision")
    pie = _sha40(pie_revision, "pie_revision")
    profile = _sha256(profile_sha256, "profile_sha256")
    config = _sha256(config_sha256, "config_sha256")
    request = None if trust_request_sha256 is None else _sha256(trust_request_sha256, "trust_request_sha256")
    natural_key = {
        "repository": repo,
        "pull_request": pull_request,
        "source_revision": source,
        "pie_revision": pie,
        "profile_sha256": profile,
        "config_sha256": config,
        "trust_request_sha256": request,
    }
    digest = canonical_json_sha256(natural_key)
    return ProspectiveExecutionIdentity(
        schema_version="PIE_PROSPECTIVE_EXECUTION_IDENTITY_V1",
        execution_id=f"pie-pr-auto-{digest[:32]}",
        execution_key_sha256=digest,
        repository=repo,
        pull_request=pull_request,
        source_revision=source,
        pie_revision=pie,
        profile_sha256=profile,
        config_sha256=config,
        trust_request_sha256=request,
    )
