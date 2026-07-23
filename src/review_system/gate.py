from __future__ import annotations

import ast
from typing import Any


class UnsafeExpression(ValueError):
    pass


_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.Compare, ast.Eq, ast.NotEq, ast.Gt, ast.GtE, ast.Lt, ast.LtE,
    ast.Name, ast.Load, ast.Constant,
)


def evaluate_expression(expression: str, context: dict[str, Any]) -> bool:
    local_context = {**context, "true": True, "false": False}
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpression(f"invalid expression: {exc.msg}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise UnsafeExpression(f"unsupported expression node: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in local_context:
            raise UnsafeExpression(f"unknown metric: {node.id}")
    return bool(eval(compile(tree, "<gate>", "eval"), {"__builtins__": {}}, local_context))


def validate_gate_policy(policy: dict[str, Any]) -> None:
    if not isinstance(policy, dict):
        raise ValueError("gate policy must be an object")
    seen: set[str] = set()
    for section in ("fail", "hold", "conditional_pass", "pass"):
        rules = policy.get(section, [])
        if not isinstance(rules, list):
            raise ValueError(f"gate policy section {section!r} must be an array")
        for index, rule in enumerate(rules):
            if not isinstance(rule, dict):
                raise ValueError(f"gate policy {section}[{index}] must be an object")
            missing = [
                key
                for key in ("id", "expression", "message")
                if not isinstance(rule.get(key), str) or not rule.get(key)
            ]
            if missing:
                raise ValueError(f"gate policy {section}[{index}] has invalid fields: {', '.join(missing)}")
            if rule["id"] in seen:
                raise ValueError(f"duplicate gate rule ID: {rule['id']}")
            seen.add(rule["id"])
    if not policy.get("pass"):
        raise ValueError("gate policy must define at least one PASS prerequisite")


def normalize_gate_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(metrics)
    normalized.setdefault("open_confirmed_p0", 0)
    normalized.setdefault("open_confirmed_p1", 0)
    normalized.setdefault("open_supported_p0", 0)
    normalized.setdefault("open_supported_p1", 0)
    normalized.setdefault("open_confirmed_blocking_fail", normalized["open_confirmed_p0"])
    normalized.setdefault("open_confirmed_blocking_hold", normalized["open_confirmed_p1"])
    normalized.setdefault(
        "open_supported_blockers",
        normalized["open_supported_p0"] + normalized["open_supported_p1"],
    )
    normalized.setdefault("fixed_unverified_blockers", 0)
    normalized.setdefault("accepted_residual_risk_count", 0)
    return normalized


def calculate_gate(metrics: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    validate_gate_policy(policy)
    metrics = normalize_gate_metrics(metrics)
    triggered: dict[str, list[dict[str, str]]] = {
        key: [] for key in ("fail", "hold", "conditional_pass", "pass")
    }
    for section in triggered:
        for rule in policy.get(section, []):
            if evaluate_expression(rule["expression"], metrics):
                triggered[section].append(
                    {
                        "id": rule["id"],
                        "message": rule["message"],
                        "expression": rule["expression"],
                    }
                )
    if triggered["fail"]:
        decision = "FAIL"
    elif triggered["hold"]:
        decision = "HOLD"
    elif triggered["conditional_pass"]:
        decision = "CONDITIONAL_PASS"
    else:
        expected_ids = {item["id"] for item in policy.get("pass", [])}
        passed_ids = {item["id"] for item in triggered["pass"]}
        decision = "PASS" if expected_ids.issubset(passed_ids) else "HOLD"
        if decision == "HOLD":
            triggered["hold"].append(
                {
                    "id": "G-H999",
                    "message": "Not all PASS prerequisites were satisfied.",
                    "expression": "all pass rules",
                }
            )
    return {"decision": decision, "triggered": triggered}


def derive_finding_metrics(
    findings: list[dict[str, Any]],
    *,
    block_on: list[str] | None = None,
) -> dict[str, int]:
    blocking = set(block_on or ["P0", "P1"])
    metrics = {
        **{f"open_confirmed_{severity.lower()}": 0 for severity in ("P0", "P1", "P2", "P3")},
        **{f"open_supported_{severity.lower()}": 0 for severity in ("P0", "P1", "P2", "P3")},
        "open_confirmed_blocking_fail": 0,
        "open_confirmed_blocking_hold": 0,
        "open_supported_blockers": 0,
        "fixed_unverified_blockers": 0,
        "accepted_residual_risk_count": 0,
    }
    for finding in findings:
        status = finding.get("status")
        severity = finding.get("severity")
        confidence = finding.get("confidence")
        if severity not in {"P0", "P1", "P2", "P3"}:
            continue

        if status == "ACCEPTED":
            metrics["accepted_residual_risk_count"] += 1
            continue

        if status == "FIXED" and confidence != "RESOLVED" and severity in blocking:
            metrics["fixed_unverified_blockers"] += 1
            continue

        if status != "OPEN":
            continue

        if confidence == "CONFIRMED":
            metrics[f"open_confirmed_{severity.lower()}"] += 1
            if severity in blocking:
                if severity == "P0":
                    metrics["open_confirmed_blocking_fail"] += 1
                else:
                    metrics["open_confirmed_blocking_hold"] += 1
        elif confidence == "SUPPORTED":
            metrics[f"open_supported_{severity.lower()}"] += 1
            if severity in blocking:
                metrics["open_supported_blockers"] += 1
    return metrics


def calculate_gate_from_run(
    run: dict[str, Any],
    policy: dict[str, Any],
    *,
    trust_metrics: bool = False,
) -> dict[str, Any]:
    metrics = dict(run["metrics"])
    block_on = run.get("gate_config", {}).get("block_on", ["P0", "P1"])
    derived = derive_finding_metrics(run.get("findings", []), block_on=block_on)
    discrepancies: dict[str, dict[str, Any]] = {}
    for key, value in derived.items():
        if metrics.get(key) != value:
            discrepancies[key] = {"declared": metrics.get(key), "derived": value}
        if not trust_metrics:
            metrics[key] = value
    result = calculate_gate(metrics, policy)
    result["effective_metrics"] = metrics
    result["metric_discrepancies"] = discrepancies
    result["finding_metrics_source"] = "declared" if trust_metrics else "derived"
    result["block_on"] = block_on
    return result
