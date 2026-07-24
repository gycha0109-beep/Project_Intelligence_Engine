from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise RuntimeError(f"missing design anchor: {label}")
    if text.count(old) != 1:
        raise RuntimeError(f"ambiguous design anchor: {label}")
    return text.replace(old, new, 1)


path = Path(__file__).resolve().parents[1] / "docs/architecture/STAGE-9-BUILDMAP-EXPORT.md"
text = path.read_text(encoding="utf-8")
text = replace_once(
    text,
    "상태: `DESIGN_APPROVED / IMPLEMENTATION_PENDING`",
    "상태: `PASS`",
    "status",
)
text = replace_once(
    text,
    "status\nartifact_id\nartifact_redacted\nfinding_sha256",
    "status\ndefect_ids\nartifact_id\nartifact_redacted\nfinding_sha256",
    "Finding Defect links",
)
text = replace_once(
    text,
    "last_seen_run_id\n```",
    "last_seen_run_id\nartifact_refs: artifact_id + relation + artifact_redacted\n```",
    "Defect Artifact references",
)
text = replace_once(
    text,
    "- Finding과 linked Defect\n- Decision과 Policy snapshot",
    "- Finding, Finding→Defect link와 linked Defect\n- Defect→Artifact evidence link\n- Decision과 Policy snapshot",
    "source fingerprint relationships",
)
text = replace_once(
    text,
    "- opaque reference integrity\n- reason reference projection",
    "- opaque reference integrity\n- Finding→Defect와 Defect→Artifact relationship projection\n- reason reference projection",
    "relationship verification",
)
path.write_text(text, encoding="utf-8")
