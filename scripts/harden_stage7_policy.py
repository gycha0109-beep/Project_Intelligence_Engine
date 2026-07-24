from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)


path = Path("src/review_system/policy_registry.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    '''def _semver(value: str) -> str:
    text = _required_text(value, "version")
    if not _SEMVER_RE.fullmatch(text):
        raise PolicyRegistryError("version must be semantic version X.Y.Z")
    return text


def _path_has_symlink(path: Path) -> bool:
''',
    '''def _semver(value: str) -> str:
    text = _required_text(value, "version")
    if not _SEMVER_RE.fullmatch(text):
        raise PolicyRegistryError("version must be semantic version X.Y.Z")
    return text


def _semver_tuple(value: str) -> tuple[int, int, int]:
    return tuple(int(part) for part in _semver(value))


def _expected_registry_id(project_id: str) -> str:
    return f"policy-registry-{canonical_json_sha256({'project_id': project_id})[:24]}"


def _expected_policy_id(
    *,
    project_id: str,
    version: str,
    parent_policy_id: str | None,
    ruleset_sha256: str,
    evaluation_id: str,
) -> str:
    key = {
        "project_id": project_id,
        "version": version,
        "parent_policy_id": parent_policy_id,
        "ruleset_sha256": ruleset_sha256,
        "evaluation_id": evaluation_id,
    }
    return f"policy-{canonical_json_sha256(key)[:32]}"


def _safe_reference(value: Any, field: str) -> str:
    raw = _required_text(value, field).replace("\\\\", "/")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise PolicyRegistryError(f"{field} must be relative")
    parts = [part for part in PurePosixPath(raw).parts if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise PolicyRegistryError(f"{field} contains an unsafe relative path")
    return PurePosixPath(*parts).as_posix()


def _path_has_symlink(path: Path) -> bool:
''',
    "identity helpers",
)

text = replace_once(
    text,
    '''        "registry_id": f"policy-registry-{canonical_json_sha256({'project_id': project})[:24]}",
''',
    '''        "registry_id": _expected_registry_id(project),
''',
    "registry id builder",
)

text = replace_once(
    text,
    '''    for field in ("registry_id", "project_id"):
        if not isinstance(registry.get(field), str) or not registry[field].strip():
            errors.append(f"{field} is required")
    recorded_registry_hash = registry.get("registry_sha256")
''',
    '''    for field in ("registry_id", "project_id"):
        if not isinstance(registry.get(field), str) or not registry[field].strip():
            errors.append(f"{field} is required")
    if isinstance(registry.get("project_id"), str):
        if registry.get("registry_id") != _expected_registry_id(registry["project_id"]):
            errors.append("registry_id mismatch")
    recorded_registry_hash = registry.get("registry_sha256")
''',
    "registry id verifier",
)

text = replace_once(
    text,
    '''        if policy.get("project_id") != registry.get("project_id"):
            errors.append(f"{prefix}.project_id does not match registry")
        status = policy.get("status")
''',
    '''        if policy.get("project_id") != registry.get("project_id"):
            errors.append(f"{prefix}.project_id does not match registry")
        try:
            _required_text(policy.get("created_by"), f"{prefix}.created_by")
            _timestamp(policy.get("created_at"), f"{prefix}.created_at")
        except PolicyRegistryError as exc:
            errors.append(str(exc))
        status = policy.get("status")
''',
    "creation metadata verifier",
)

text = replace_once(
    text,
    '''        for field in ("evaluation_id", "report", "report_sha256"):
            if not isinstance(evaluation.get(field), str) or not evaluation[field]:
                errors.append(f"{prefix}.evaluation.{field} is required")

        events = policy.get("events")
''',
    '''        for field in ("evaluation_id", "report", "report_sha256"):
            if not isinstance(evaluation.get(field), str) or not evaluation[field]:
                errors.append(f"{prefix}.evaluation.{field} is required")
        try:
            _safe_reference(evaluation.get("report"), f"{prefix}.evaluation.report")
        except PolicyRegistryError as exc:
            errors.append(str(exc))
        if all(
            isinstance(value, str) and value
            for value in (
                policy.get("project_id"),
                version,
                ruleset.get("sha256"),
                evaluation.get("evaluation_id"),
            )
        ):
            expected_policy_id = _expected_policy_id(
                project_id=policy["project_id"],
                version=version,
                parent_policy_id=policy.get("parent_policy_id"),
                ruleset_sha256=ruleset["sha256"],
                evaluation_id=evaluation["evaluation_id"],
            )
            if policy_id != expected_policy_id:
                errors.append(f"{prefix}.policy_id mismatch")

        events = policy.get("events")
''',
    "policy id and report reference verifier",
)

text = replace_once(
    text,
    '''        previous: str | None = None
        projected_status = "DRAFT"
        for event_index, event in enumerate(events):
''',
    '''        previous: str | None = None
        previous_at: str | None = None
        projected_status = "DRAFT"
        for event_index, event in enumerate(events):
''',
    "event timestamp state",
)

text = replace_once(
    text,
    '''            try:
                _timestamp(event.get("at"), f"{event_prefix}.at")
                _required_text(event.get("actor"), f"{event_prefix}.actor")
            except PolicyRegistryError as exc:
                errors.append(str(exc))
            if event_index == 0 and event_type != "BUILT":
                errors.append(f"{event_prefix} first event must be BUILT")
            if event_type == "APPROVED":
''',
    '''            try:
                event_at = _timestamp(event.get("at"), f"{event_prefix}.at")
                _required_text(event.get("actor"), f"{event_prefix}.actor")
                if previous_at is not None and event_at < previous_at:
                    errors.append(f"{event_prefix}.at precedes the previous event")
                previous_at = event_at
            except PolicyRegistryError as exc:
                errors.append(str(exc))
            if event_index == 0 and event_type != "BUILT":
                errors.append(f"{event_prefix} first event must be BUILT")
            if event_type == "BUILT" and event_index != 0:
                errors.append(f"{event_prefix} BUILT may only be the first event")
            if event_type == "APPROVED":
''',
    "event ordering verifier",
)

text = replace_once(
    text,
    '''        if status in {"ACTIVE", "SUPERSEDED", "RETIRED"}:
            approval = policy.get("approval")
            if not isinstance(approval, dict):
                errors.append(f"{prefix}.approval is required")
            else:
                for field in ("approved_by", "approved_at"):
                    if not isinstance(approval.get(field), str) or not approval[field]:
                        errors.append(f"{prefix}.approval.{field} is required")
            if not isinstance(policy.get("effective_at"), str):
                errors.append(f"{prefix}.effective_at is required")
''',
    '''        if status == "DRAFT":
            if any(policy.get(field) is not None for field in ("approval", "effective_at", "superseded_by", "retirement")):
                errors.append(f"{prefix} DRAFT lifecycle projection contains terminal metadata")
        if status in {"ACTIVE", "SUPERSEDED", "RETIRED"}:
            approval = policy.get("approval")
            if not isinstance(approval, dict):
                errors.append(f"{prefix}.approval is required")
            else:
                for field in ("approved_by", "approved_at"):
                    if not isinstance(approval.get(field), str) or not approval[field]:
                        errors.append(f"{prefix}.approval.{field} is required")
                approved_events = [event for event in events if isinstance(event, dict) and event.get("type") == "APPROVED"]
                if len(approved_events) != 1:
                    errors.append(f"{prefix} must contain exactly one APPROVED event")
                elif approval.get("approved_by") != approved_events[0].get("actor") or approval.get("approved_at") != approved_events[0].get("at"):
                    errors.append(f"{prefix}.approval does not match APPROVED event")
            if not isinstance(policy.get("effective_at"), str):
                errors.append(f"{prefix}.effective_at is required")
            activated_events = [event for event in events if isinstance(event, dict) and event.get("type") == "ACTIVATED"]
            if len(activated_events) != 1 or policy.get("effective_at") != activated_events[0].get("at"):
                errors.append(f"{prefix}.effective_at does not match ACTIVATED event")
''',
    "lifecycle metadata verifier",
)

text = replace_once(
    text,
    '''        if status == "SUPERSEDED" and not isinstance(policy.get("superseded_by"), str):
            errors.append(f"{prefix}.superseded_by is required")
        if status == "RETIRED":
''',
    '''        if status == "SUPERSEDED":
            if not isinstance(policy.get("superseded_by"), str):
                errors.append(f"{prefix}.superseded_by is required")
            superseded_events = [event for event in events if isinstance(event, dict) and event.get("type") == "SUPERSEDED"]
            if len(superseded_events) != 1 or superseded_events[0].get("details", {}).get("superseded_by") != policy.get("superseded_by"):
                errors.append(f"{prefix}.superseded_by does not match SUPERSEDED event")
        if status == "RETIRED":
''',
    "supersession metadata verifier",
)

text = replace_once(
    text,
    '''            elif not all(isinstance(retirement.get(field), str) and retirement[field] for field in ("retired_by", "retired_at", "reason")):
                errors.append(f"{prefix}.retirement is incomplete")

        recorded_policy_hash = policy.get("policy_sha256")
''',
    '''            elif not all(isinstance(retirement.get(field), str) and retirement[field] for field in ("retired_by", "retired_at", "reason")):
                errors.append(f"{prefix}.retirement is incomplete")
            else:
                retired_events = [event for event in events if isinstance(event, dict) and event.get("type") == "RETIRED"]
                if len(retired_events) != 1:
                    errors.append(f"{prefix} must contain exactly one RETIRED event")
                elif (
                    retirement.get("retired_by") != retired_events[0].get("actor")
                    or retirement.get("retired_at") != retired_events[0].get("at")
                    or retirement.get("reason") != retired_events[0].get("details", {}).get("reason")
                ):
                    errors.append(f"{prefix}.retirement does not match RETIRED event")

        recorded_policy_hash = policy.get("policy_sha256")
''',
    "retirement metadata verifier",
)

text = replace_once(
    text,
    '''        elif parent == policy_id:
            errors.append(f"Policy {policy_id} cannot parent itself")
        superseded_by = policy.get("superseded_by")
''',
    '''        elif parent == policy_id:
            errors.append(f"Policy {policy_id} cannot parent itself")
        elif isinstance(parent, str) and parent in policy_map:
            try:
                if _semver_tuple(policy["version"]) <= _semver_tuple(policy_map[parent]["version"]):
                    errors.append(f"Policy {policy_id} version must be greater than its parent")
            except (KeyError, PolicyRegistryError):
                pass
        superseded_by = policy.get("superseded_by")
''',
    "parent semver verifier",
)

text = replace_once(
    text,
    '''    if parent_policy_id is not None and parent_policy_id not in policy_map:
        raise PolicyRegistryError(f"parent Policy not found: {parent_policy_id}")
    if any(item["version"] == semantic_version for item in updated["policies"]):
''',
    '''    if parent_policy_id is not None and parent_policy_id not in policy_map:
        raise PolicyRegistryError(f"parent Policy not found: {parent_policy_id}")
    if parent_policy_id is not None and _semver_tuple(semantic_version) <= _semver_tuple(policy_map[parent_policy_id]["version"]):
        raise PolicyRegistryError("Policy version must be greater than its parent version")
    if any(item["version"] == semantic_version for item in updated["policies"]):
''',
    "build parent semver",
)

text = replace_once(
    text,
    '''    key = {
        "project_id": project,
        "version": semantic_version,
        "parent_policy_id": parent_policy_id,
        "ruleset_sha256": ruleset_hash,
        "evaluation_id": report["evaluation_id"],
    }
    policy_id = f"policy-{canonical_json_sha256(key)[:32]}"
''',
    '''    policy_id = _expected_policy_id(
        project_id=project,
        version=semantic_version,
        parent_policy_id=parent_policy_id,
        ruleset_sha256=ruleset_hash,
        evaluation_id=report["evaluation_id"],
    )
''',
    "build policy identity",
)

path.write_text(text, encoding="utf-8")


tests_path = Path("tests/test_policy_registry_hardening.py")
tests = tests_path.read_text(encoding="utf-8")
insert = '''    def test_rehashed_registry_and_policy_identity_tamper_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            fixture.build_root()
            registry = load_data(fixture.registry)
            registry["registry_id"] = "policy-registry-forged"
            registry["policies"][0]["policy_id"] = "policy-forged"
            rehash_policy(registry["policies"][0])
            rehash_registry(registry)
            errors = verify_policy_registry_data(registry)
            self.assertIn("registry_id mismatch", errors)
            self.assertTrue(any("policy_id mismatch" in error for error in errors))

    def test_parent_version_must_increase(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            parent = fixture.build_root()
            with self.assertRaisesRegex(PolicyRegistryError, "greater than its parent"):
                build_policy(
                    fixture.registry,
                    project_id="demo",
                    version="0.9.0",
                    rules=fixture.rules_ab,
                    evaluation_report=fixture.report_ab,
                    created_by="builder",
                    created_at="2026-07-24T03:00:00Z",
                    parent_policy_id=parent["policy_id"],
                )

    def test_rehashed_unsafe_report_reference_and_event_projection_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = PolicyFixture(Path(tmp))
            active = fixture.activate_root()
            registry = load_data(fixture.registry)
            policy = registry["policies"][0]
            policy["evaluation"]["report"] = "../outside.json"
            policy["approval"]["approved_by"] = "forged"
            policy["events"].append(copy.deepcopy(policy["events"][0]))
            policy["events"][-1]["sequence"] = len(policy["events"])
            policy["events"][-1]["previous_event_sha256"] = policy["events"][-2]["event_sha256"]
            base = copy.deepcopy(policy["events"][-1])
            base.pop("event_id", None)
            base.pop("event_sha256", None)
            policy["events"][-1]["event_id"] = f"policy-event-{canonical_json_sha256(base)[:24]}"
            event_payload = copy.deepcopy(policy["events"][-1])
            event_payload.pop("event_sha256", None)
            policy["events"][-1]["event_sha256"] = canonical_json_sha256(event_payload)
            rehash_policy(policy)
            rehash_registry(registry)
            errors = verify_policy_registry_data(registry)
            self.assertTrue(any("unsafe relative path" in error for error in errors))
            self.assertTrue(any("approval does not match" in error for error in errors))
            self.assertTrue(any("BUILT may only" in error for error in errors))

'''
anchor = '    def test_registry_policy_and_materialized_tamper_are_detected(self):\n'
if insert not in tests:
    if anchor not in tests:
        raise SystemExit("missing hardening test anchor")
    tests = tests.replace(anchor, insert + anchor, 1)
tests_path.write_text(tests, encoding="utf-8")
