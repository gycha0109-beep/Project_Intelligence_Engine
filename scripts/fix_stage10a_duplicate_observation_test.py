from pathlib import Path

path = Path(__file__).resolve().parents[1] / "tests/test_trust_gate_hardening.py"
text = path.read_text(encoding="utf-8")
old = '            duplicate["observation_id"] = "obs-2"\n'
new = '            duplicate["observation_id"] = "obs-duplicate"\n'
if new not in text:
    if text.count(old) != 1:
        raise RuntimeError("duplicate observation fixture anchor mismatch")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
