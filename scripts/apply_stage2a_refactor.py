from pathlib import Path


path = Path("src/review_system/github_connector.py")
text = path.read_text(encoding="utf-8")
text = text.replace(
    '_GITHUB_PR_RE = re.compile(r"^/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>[1-9][0-9]*)(?:/.*)?$")\n',
    "",
)
text = text.replace(
    '_REPOSITORY_RE = re.compile(r"^(?:(?P<host>[A-Za-z0-9.-]+)/)?(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)$")\n',
    "",
)
if "_GITHUB_PR_RE" in text or "_REPOSITORY_RE" in text:
    raise SystemExit("legacy target parser constants remain")
path.write_text(text, encoding="utf-8")
