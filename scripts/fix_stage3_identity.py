from pathlib import Path

path = Path("src/review_system/identity.py")
text = path.read_text(encoding="utf-8")
old = '''    head_oid = pull_request.get("head_oid")
    source_hash = source.get("source_sha256")
    if isinstance(head_oid, str) and head_oid:
        revision = head_oid
    elif isinstance(source_hash, str) and len(source_hash) == 64 and _HEX_RE.fullmatch(source_hash):
        revision = f"sha256:{source_hash}"
    else:
        revision = "unresolved"
'''
new = '''    head_oid = pull_request.get("head_oid")
    source_hash = source.get("source_sha256")
    revision = "unresolved"
    if isinstance(head_oid, str) and head_oid:
        try:
            revision = normalize_source_revision(head_oid)
        except ValueError:
            revision = "unresolved"
    if revision == "unresolved" and isinstance(source_hash, str) and len(source_hash) == 64 and _HEX_RE.fullmatch(source_hash):
        revision = f"sha256:{source_hash}"
'''
if old not in text:
    raise SystemExit("pull request revision block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
