from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing {label}")
    return text.replace(old, new, 1)


defects_path = Path("src/review_system/defects.py")
defects = defects_path.read_text(encoding="utf-8")
defects = replace_once(
    defects,
    '''        recorded_hash = payload.pop("event_sha256", None)
        payload.pop("event_id", None)
        if recorded_hash != canonical_json_sha256(payload):
            errors.append(f"{prefix}.event_sha256 mismatch")
        status_from = item.get("status_from")
        status_to = item.get("status_to")
        if item.get("event_type") == "CREATED":
''',
    '''        recorded_hash = payload.pop("event_sha256", None)
        payload.pop("event_id", None)
        if recorded_hash != canonical_json_sha256(payload):
            errors.append(f"{prefix}.event_sha256 mismatch")
        if isinstance(recorded_hash, str) and event_id != f"event-{recorded_hash[:32]}":
            errors.append(f"{prefix}.event_id does not match event_sha256")
        status_from = item.get("status_from")
        status_to = item.get("status_to")
        event_type = item.get("event_type")
        if event_type != "CREATED" and current_status[defect_id] is None:
            errors.append(f"{prefix} occurs before the Defect CREATED event")
        if event_type == "CREATED":
''',
    "event identity and creation ordering",
)
defects = replace_once(
    defects,
    '''        elif item.get("event_type") == "TRANSITIONED":
''',
    '''        elif event_type == "TRANSITIONED":
''',
    "transition event branch",
)
defects = replace_once(
    defects,
    '''        elif item.get("event_type") not in {"FINDING_LINKED", "ARTIFACT_LINKED"}:
''',
    '''        elif event_type not in {"FINDING_LINKED", "ARTIFACT_LINKED"}:
''',
    "link event branch",
)
defects = replace_once(
    defects,
    '''    for defect_id, defect in defect_by_id.items():
        if current_status.get(defect_id) != defect.get("lifecycle_status"):
            errors.append(f"defect {defect_id} lifecycle_status does not match event history")

    recorded_hash = registry.get("registry_sha256")
''',
    '''    resolution_evidence_defects = {
        str(item.get("defect_id"))
        for item in artifact_links
        if isinstance(item, dict) and item.get("relation") == "resolution_evidence"
    }
    for defect_id, defect in defect_by_id.items():
        if current_status.get(defect_id) != defect.get("lifecycle_status"):
            errors.append(f"defect {defect_id} lifecycle_status does not match event history")
        for field in ("root_cause", "first_seen_run_id", "last_seen_run_id", "owner", "resolution"):
            value = defect.get(field)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                errors.append(f"defect {defect_id} {field} must be null or a non-empty string")
        if defect.get("lifecycle_status") == "CLOSED":
            if not isinstance(defect.get("resolution"), str) or not defect["resolution"].strip():
                errors.append(f"defect {defect_id} CLOSED requires a resolution")
            if defect_id not in resolution_evidence_defects:
                errors.append(f"defect {defect_id} CLOSED requires resolution_evidence")

    recorded_hash = registry.get("registry_sha256")
''',
    "closed and optional field invariants",
)
defects_path.write_text(defects, encoding="utf-8")


ledger_path = Path("src/review_system/ledger.py")
ledger = ledger_path.read_text(encoding="utf-8")
ledger = replace_once(
    ledger,
    '''            ("artifacts", "artifacts", "relative_path"),
            ("claims", "claims", "claim_id"),
''',
    '''            ("artifacts", "artifacts", "relative_path"),
            ("findings", "findings", "finding_id"),
            ("claims", "claims", "claim_id"),
''',
    "show-run finding projection",
)
ledger_path.write_text(ledger, encoding="utf-8")
