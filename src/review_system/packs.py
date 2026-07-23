from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Iterable, Any

from .io import load_data
from .paths import asset


_EXTENSION_RULES: dict[str, tuple[str, ...]] = {
    ".sql": ("data.relational-integrity",),
}

_TOKEN_RULES: list[tuple[set[str], tuple[str, ...]]] = [
    ({"migration", "migrations", "schema"}, ("data.migration-safety", "data.relational-integrity")),
    ({"rls", "policy", "policies", "supabase"}, ("data.rls", "application.authorization")),
    ({"auth", "authentication", "session", "jwt", "middleware"}, ("application.authentication", "application.authorization")),
    ({"recommend", "recommendation", "ranking", "scoring", "candidate"}, ("domain.recommendation", "universal.test-completeness")),
    ({"search", "query", "cursor", "pagination"}, ("domain.search", "universal.test-completeness")),
    ({"retry", "idempotency", "idempotent", "webhook", "queue", "job"}, ("runtime.retries-idempotency", "data.transactionality")),
    ({"test", "tests", "spec", "fixture", "fixtures"}, ("universal.test-completeness",)),
    ({"controller", "route", "routes", "api", "endpoint"}, ("application.authorization", "universal.requirements-traceability")),
    ({"repository", "repositories", "dao", "database", "db"}, ("data.relational-integrity", "data.transactionality")),
    ({"model", "inference", "vision", "prompt", "embedding", "evaluation", "evaluator"}, ("domain.ai-inference",)),
    ({"architecture", "module", "modules", "dependency", "dependencies"}, ("universal.architecture",)),
    ({"contract", "contracts", "decision", "decisions", "handoff", "allocation"}, ("universal.requirements-traceability",)),
    ({"design"}, ("universal.architecture", "universal.requirements-traceability")),
]


def _tokens(path: str) -> set[str]:
    normalized = path.strip().lower().replace("\\", "/")
    return {token for token in re.split(r"[^a-z0-9]+", normalized) if token}


def pack_metadata(pack_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*(?:\.[a-z0-9][a-z0-9-]*)+", pack_id):
        raise ValueError(f"invalid pack ID: {pack_id!r}")
    manifest = asset("packs") / PurePosixPath(*pack_id.split(".")) / "pack.yml"
    if not manifest.exists():
        # Category may be two words but pack path is category/name in the current contract.
        parts = pack_id.split(".", 1)
        manifest = asset("packs") / parts[0] / parts[1].replace(".", "/") / "pack.yml"
    data = load_data(manifest)
    if not isinstance(data, dict):
        raise ValueError(f"invalid pack manifest: {manifest}")
    return data


def lock_packs(pack_ids: Iterable[str]) -> list[dict[str, str]]:
    result = []
    for pack_id in pack_ids:
        metadata = pack_metadata(pack_id)
        result.append({"pack_id": pack_id, "version": str(metadata["version"])})
    return result


def select_packs_with_reasons(
    changed_files: Iterable[str],
    configured_packs: Iterable[str],
) -> dict[str, list[str]]:
    files = [raw.strip() for raw in changed_files if raw.strip()]
    configured = set(configured_packs)
    reasons: dict[str, list[str]] = {}
    for raw in files:
        normalized = raw.lower().replace("\\", "/")
        suffix = PurePosixPath(normalized).suffix
        candidates: set[str] = set(_EXTENSION_RULES.get(suffix, ()))
        path_tokens = _tokens(normalized)
        if suffix == ".sql":
            migration_location = (
                normalized.startswith("database/")
                or "/migrations/" in normalized
                or "/db/migration/" in normalized
                or bool(path_tokens & {"migration", "migrations", "schema"})
            )
            test_sql = bool(path_tokens & {"test", "tests", "fixture", "fixtures"})
            if migration_location and not test_sql:
                candidates.add("data.migration-safety")
        for needles, packs in _TOKEN_RULES:
            if path_tokens & needles:
                candidates.update(packs)
        for pack in candidates & configured:
            reasons.setdefault(pack, []).append(raw)
    if files and "universal.test-completeness" in configured:
        reasons.setdefault("universal.test-completeness", []).append("<every non-empty change set>")
    return {pack: sorted(set(paths)) for pack, paths in sorted(reasons.items())}


def select_packs(changed_files: Iterable[str], configured_packs: Iterable[str]) -> list[str]:
    return list(select_packs_with_reasons(changed_files, configured_packs))
