from pathlib import Path

path = Path("src/review_system/trust_comparison.py")
text = path.read_text(encoding="utf-8")
old = '''    request = report.get("request")
    advisory = report.get("task_advisory")
    readiness = report.get("readiness")
    if not isinstance(request, dict) or not isinstance(advisory, dict) or not isinstance(readiness, dict):
        raise TrustComparisonError("Trust report projections are incomplete")
'''
new = '''    request = report.get("request")
    risk = report.get("risk")
    advisory = report.get("task_advisory")
    readiness = report.get("readiness")
    if (
        not isinstance(request, dict)
        or not isinstance(risk, dict)
        or not isinstance(advisory, dict)
        or not isinstance(readiness, dict)
    ):
        raise TrustComparisonError("Trust report projections are incomplete")
'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("projection anchor missing")
old = '        "predicted_risk_band": advisory.get("risk_band"),\n'
new = '        "predicted_risk_band": risk.get("effective_band"),\n'
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("risk band anchor missing")
old = '    path = asset("schemas", "trust-comparison-registry.schema.json")\n'
new = '    path = asset("schemas/trust-comparison-registry.schema.json")\n'
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("schema asset anchor missing")
path.write_text(text, encoding="utf-8")
