from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing {label}")
    return text.replace(old, new, 1)


defects_path = Path("src/review_system/defects.py")
defects = defects_path.read_text(encoding="utf-8")
defects = replace_once(
    defects,
    '''        payload = dict(item)
        recorded_hash = payload.pop("event_sha256", None)
        if recorded_hash != canonical_json_sha256(payload):
''',
    '''        payload = dict(item)
        recorded_hash = payload.pop("event_sha256", None)
        payload.pop("event_id", None)
        if recorded_hash != canonical_json_sha256(payload):
''',
    "event hash validation",
)
defects_path.write_text(defects, encoding="utf-8")


tests_path = Path("tests/test_defects.py")
tests = tests_path.read_text(encoding="utf-8")
tests = replace_once(
    tests,
    '            self.assertEqual(8, len(shown["events"]))\n',
    '            self.assertEqual(9, len(shown["events"]))\n',
    "lifecycle event count",
)
tests_path.write_text(tests, encoding="utf-8")
