from pathlib import Path


path = Path("src/review_system/cli.py")
text = path.read_text(encoding="utf-8")

old_imports = '''from .application import (
    AnalyzeChangeRequest,
    AnalyzePullRequestRequest,
    IndexProjectRequest,
    analyze_project_change,
    analyze_pull_request,
    index_project,
)
'''
new_imports = '''from .application import (
    AnalyzeChangeRequest,
    AnalyzePullRequestRequest,
    ApproveRuleRequest,
    CalculateGateRequest,
    IndexProjectRequest,
    ReviewRunValidationError,
    analyze_project_change,
    analyze_pull_request,
    approve_rule,
    calculate_review_gate,
    index_project,
)
'''
if old_imports not in text:
    raise SystemExit("application import block not found")
text = text.replace(old_imports, new_imports, 1)
text = text.replace("from .gate import calculate_gate_from_run\n", "", 1)
text = text.replace(
    "from .io import dump_json, dump_yaml, dump_yaml_pair_atomic, load_data\n",
    "from .io import dump_json, dump_yaml, load_data\n",
    1,
)
text = text.replace(
    "from .intelligence_learning import approve_candidate_rule, discover_rule_candidates, merge_rule_candidates\n",
    "from .intelligence_learning import discover_rule_candidates, merge_rule_candidates\n",
    1,
)

old_gate = '''def cmd_calculate_gate(args: argparse.Namespace) -> int:
    run, errors = validate_review_run_file(args.run)
    if errors:
        _print_errors(errors)
        return 2
    try:
        policy = load_data(args.policy or asset("core/default-gate-policy.yml"))
        result = calculate_gate_from_run(run, policy, trust_metrics=args.trust_metrics)
    except Exception as exc:
        return _error(exc)
    if args.output:
        dump_json(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["decision"] in {"PASS", "CONDITIONAL_PASS"} else 3
'''
new_gate = '''def cmd_calculate_gate(args: argparse.Namespace) -> int:
    try:
        result = calculate_review_gate(
            CalculateGateRequest(
                run=args.run,
                policy=args.policy,
                output=args.output,
                trust_metrics=args.trust_metrics,
            )
        )
    except ReviewRunValidationError as exc:
        _print_errors(list(exc.errors))
        return 2
    except Exception as exc:
        return _error(exc)
    print(json.dumps(result.gate, indent=2, ensure_ascii=False))
    return 0 if result.gate["decision"] in {"PASS", "CONDITIONAL_PASS"} else 3
'''
if old_gate not in text:
    raise SystemExit("calculate gate block not found")
text = text.replace(old_gate, new_gate, 1)

old_approve = '''def cmd_approve_rule(args: argparse.Namespace) -> int:
    try:
        candidates = load_rules(args.candidates)
        approved = load_rules(args.approved, required_status="approved")
        updated_candidates, updated_approved = approve_candidate_rule(
            candidates,
            approved,
            args.rule_id,
            approved_by=args.approved_by,
            approved_at=args.approved_at,
            rationale=args.rationale,
        )
        dump_yaml_pair_atomic(args.approved, updated_approved, args.candidates, updated_candidates)
    except Exception as exc:
        return _error(exc)
    print(f"APPROVED rule: {args.rule_id}; approved_file={args.approved}")
    return 0
'''
new_approve = '''def cmd_approve_rule(args: argparse.Namespace) -> int:
    try:
        approve_rule(
            ApproveRuleRequest(
                candidates=args.candidates,
                approved=args.approved,
                rule_id=args.rule_id,
                approved_by=args.approved_by,
                approved_at=args.approved_at,
                rationale=args.rationale,
            )
        )
    except Exception as exc:
        return _error(exc)
    print(f"APPROVED rule: {args.rule_id}; approved_file={args.approved}")
    return 0
'''
if old_approve not in text:
    raise SystemExit("approve rule block not found")
text = text.replace(old_approve, new_approve, 1)

path.write_text(text, encoding="utf-8")
