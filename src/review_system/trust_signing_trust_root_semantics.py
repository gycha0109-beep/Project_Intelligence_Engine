from __future__ import annotations

import re
from typing import Any


_DOCUMENT_PREFIXES = ("docs/", "documentation/", "examples/", "example/")
_SUPPORT_PREFIXES = ("tests/", "test/", "scripts/")
_EXECUTABLE_SUFFIXES = (
    ".rs",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".py",
    ".go",
    ".java",
    ".kt",
)


def _matches(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.MULTILINE) is not None


def _is_runtime_or_config_surface(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    if normalized.startswith(_DOCUMENT_PREFIXES) or normalized.startswith(_SUPPORT_PREFIXES):
        return False
    return normalized.endswith(_EXECUTABLE_SUFFIXES)


def analyze_signing_trust_root_semantics(path: str, excerpt: str) -> dict[str, Any]:
    """Classify the frozen signing trust-root semantic boundary without authority policy."""

    normalized_path = path.replace("\\", "/")
    combined = f"{normalized_path}\n{excerpt}"

    trust_material = _matches(
        r"(?:UPDATE_PUBLIC_KEY|SIGNATURE[_-]?PUBLIC[_-]?KEY|VERIFICATION[_-]?KEY|"
        r"TRUST[_-]?ROOT(?:[_-]?(?:PUBLIC)?[_-]?KEY)?|trusted[_-]?keys?|"
        r"trustRootPublicKey|\bpubkey\b|public\s+key)",
        combined,
    )
    signing_or_verification = _matches(
        r"(?:signature|signing|minisign|artifact\s+verification|verify(?:ing|ied)?|"
        r"verification|updater|update\s+signature|trust\s+root)",
        combined,
    )
    operational_context = _matches(
        r"(?:production|published|stable|release|updater|update\s+channel|artifact)",
        combined,
    )
    trust_root_assignment = _matches(
        r"[\"']?(?:UPDATE_PUBLIC_KEY|SIGNATURE[_-]?PUBLIC[_-]?KEY|VERIFICATION[_-]?KEY|"
        r"TRUST[_-]?ROOT(?:[_-]?(?:PUBLIC)?[_-]?KEY)?|trusted[_-]?keys?|"
        r"trustRootPublicKey|pubkey)[\"']?\s*(?::|=)",
        excerpt,
    )
    runtime_or_config_surface = _is_runtime_or_config_surface(normalized_path)

    signals = {
        "trust_material": trust_material,
        "signing_or_verification": signing_or_verification,
        "operational_context": operational_context,
        "trust_root_assignment": trust_root_assignment,
        "runtime_or_config_surface": runtime_or_config_surface,
    }
    return {
        "path": normalized_path,
        "signals": signals,
        "candidate_triggered": all(signals.values()),
    }
