from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

from .trust import BAND_ORDER, TRUST_MODE, _risk_projection


CONTRACT_VERSION = "TRUST_SIGNING_TRUST_ROOT_AUTHORITY_SHADOW_V1"
TARGET_BAND = "R3"
REASON_ID = "SEMANTIC_R3_SIGNING_TRUST_ROOT_CANDIDATE"

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


def analyze_signing_trust_root_candidate(path: str, excerpt: str) -> dict[str, Any]:
    """Shadow-only detector for executable signature-verification trust-root mutation.

    The detector deliberately excludes documentation, tests and supporting scripts.
    It requires a concrete trust-material assignment on a runtime/configuration
    surface plus signing/verification and operational context. Repository names
    are not inputs.
    """

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
        r"(?:UPDATE_PUBLIC_KEY|SIGNATURE[_-]?PUBLIC[_-]?KEY|VERIFICATION[_-]?KEY|"
        r"TRUST[_-]?ROOT(?:[_-]?(?:PUBLIC)?[_-]?KEY)?|trusted[_-]?keys?|"
        r"trustRootPublicKey|\"pubkey\")\s*(?::|=)",
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
    candidate_triggered = all(signals.values())

    return {
        "contract_version": CONTRACT_VERSION,
        "mode": TRUST_MODE,
        "authority": "SHADOW_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "path": normalized_path,
        "signals": signals,
        "candidate_triggered": candidate_triggered,
        "candidate_band": TARGET_BAND if candidate_triggered else None,
        "reason_id": REASON_ID if candidate_triggered else None,
    }


def project_signing_trust_root_candidate(
    request: dict[str, Any],
    profile: dict[str, Any],
    file_texts: dict[str, str],
) -> dict[str, Any]:
    """Compare current Trust projection with the bounded shadow R3 candidate."""

    current = _risk_projection(request, profile)
    analyses = [
        analyze_signing_trust_root_candidate(path, file_texts.get(path, ""))
        for path in request.get("changed_files", [])
    ]
    candidate_paths = [item["path"] for item in analyses if item["candidate_triggered"]]

    candidate = deepcopy(current)
    if candidate_paths and BAND_ORDER[candidate["effective_band"]] < BAND_ORDER[TARGET_BAND]:
        candidate["effective_band"] = TARGET_BAND
        candidate.setdefault("reasons", []).append(
            {
                "reason_id": REASON_ID,
                "band": TARGET_BAND,
                "paths": candidate_paths,
            }
        )

    return {
        "contract_version": CONTRACT_VERSION,
        "mode": TRUST_MODE,
        "authority": "SHADOW_ONLY",
        "automation_authorized": False,
        "pilot_authorized": False,
        "current_risk": current,
        "candidate_risk": candidate,
        "analyses": analyses,
        "candidate_paths": candidate_paths,
        "band_changed": current["effective_band"] != candidate["effective_band"],
    }
