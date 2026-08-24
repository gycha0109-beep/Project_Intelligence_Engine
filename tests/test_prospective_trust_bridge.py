from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.identity import canonical_json_sha256
from review_system.prospective_trust_bridge import (
    AUTHORITY_REPOSITORY,
    ProspectiveTrustBridgeError,
    TrustedGitHubPRRequest,
    _provider_file,
    _safe_source_path,
    build_bridge_result_projection,
    run_trusted_github_pr,
)


HEAD = "a" * 40
BASE = "b" * 40
AUTHORITY = "c" * 40


class _Result:
    def __init__(self, stdout: str):
        self.stdout = stdout


class _CLI:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def run(self, args, *, cwd=None, check=True):
        self.calls.append(list(args))
        return _Result(json.dumps(self.payloads.pop(0)))


def _live_source(repository: str = "demo/repo") -> dict:
    return {
        "repository": {"name_with_owner": repository, "hostname": "github.com"},
        "pull_request": {
            "number": 7,
            "state": "OPEN",
            "head_oid": HEAD,
            "base_oid": BASE,
            "changed_files": [{"path": "src/app.py", "additions": 1, "deletions": 0}],
        },
    }


class TrustedBridgeUnitTests(unittest.TestCase):
    def test_trust_source_path_is_constrained_to_authority_prefix(self):
        self.assertEqual(
            "evidence/trust/requests/example.json",
            _safe_source_path("evidence/trust/requests/example.json"),
        )
        for value in (
            "../request.json",
            "/evidence/trust/requests/request.json",
            "evidence/trust/request.json",
            "evidence/trust/requests/../request.json",
            "evidence/trust/requests/request.yml",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ProspectiveTrustBridgeError):
                    _safe_source_path(value)

    def test_provider_file_requires_exact_provider_path_and_decodes_bytes(self):
        raw = b'{"schema_version":"1.0"}\n'
        cli = _CLI(
            [
                {
                    "type": "file",
                    "path": "evidence/trust/requests/example.json",
                    "sha": "d" * 40,
                    "encoding": "base64",
                    "content": base64.b64encode(raw).decode("ascii"),
                }
            ]
        )
        content, provider_sha = _provider_file(
            cli,
            cwd=Path(".").resolve(),
            authority_revision=AUTHORITY,
            source_path="evidence/trust/requests/example.json",
        )
        self.assertEqual(raw, content)
        self.assertEqual("d" * 40, provider_sha)
        self.assertIn("GET", cli.calls[0])
        self.assertIn(f"ref={AUTHORITY}", cli.calls[0])

    def test_pie_target_cannot_use_unrelated_authority_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch(
                "review_system.prospective_trust_bridge.collect_pull_request",
                return_value=(_live_source(AUTHORITY_REPOSITORY), None),
            ):
                with self.assertRaises(ProspectiveTrustBridgeError) as caught:
                    run_trusted_github_pr(
                        TrustedGitHubPRRequest(
                            pull_request=7,
                            target_repository=AUTHORITY_REPOSITORY,
                            event_head_sha=HEAD,
                            event_base_sha=BASE,
                            pie_revision=AUTHORITY,
                            trust_request_path="evidence/trust/requests/example.json",
                            trust_request_sha256="1" * 64,
                            repository_root=root,
                            output_root=root / "out",
                        ),
                        github_cli=_CLI([]),
                    )
            self.assertEqual("SELF_AUTHORITY_REJECTED", caught.exception.code)

    def test_bridge_projection_ignores_raw_packet_transport_hash(self):
        source_evidence = {
            "authority": {
                "repository": AUTHORITY_REPOSITORY,
                "revision": AUTHORITY,
                "committed_at": "2026-08-24T00:00:00Z",
                "path": "evidence/trust/requests/example.json",
                "provider_blob_sha": "d" * 40,
                "content_sha256": "1" * 64,
            },
            "target": {
                "repository": "demo/repo",
                "pull_request": 7,
                "head_sha": HEAD,
                "base_sha": BASE,
                "changed_files": ["src/app.py"],
            },
            "trust_request": {
                "request_id": "request-1",
                "project_id": "demo",
                "task_id": "github-pr:example",
                "source_revision": f"git:{HEAD}",
            },
        }
        run_result = {
            "status": "READY_FOR_HUMAN_REVIEW",
            "assessment_id": "assessment-1",
            "risk_band": "R2",
            "readiness": "READY_FOR_HUMAN_COMPARISON",
        }
        first_packet = {
            "packet_id": "packet-1",
            "evidence_snapshot_sha256": "2" * 64,
            "packet_sha256": "3" * 64,
            "generated_at": "2026-08-24T01:00:00Z",
        }
        second_packet = {
            **first_packet,
            "packet_sha256": "4" * 64,
            "generated_at": "2026-08-24T02:00:00Z",
        }
        first = build_bridge_result_projection(
            source_evidence=source_evidence,
            run_result=run_result,
            packet=first_packet,
            request_sha256="1" * 64,
        )
        second = build_bridge_result_projection(
            source_evidence=source_evidence,
            run_result=run_result,
            packet=second_packet,
            request_sha256="1" * 64,
        )
        self.assertEqual(first, second)
        self.assertEqual(canonical_json_sha256(first), canonical_json_sha256(second))
        self.assertFalse(first["human_review_recorded"])
        self.assertFalse(first["outcome_recorded"])
        self.assertFalse(first["automation_authorized"])
        self.assertFalse(first["pilot_authorized"])


if __name__ == "__main__":
    unittest.main()
