import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from review_system.buildmap_export import (
    BuildMapExportError,
    BuildMapExportVerificationError,
    _expected_export_id,
    _export_payload,
    _projection_payload,
    load_buildmap_export,
    verify_buildmap_export_data,
    verify_buildmap_export_source,
    write_buildmap_export,
)
from review_system.identity import canonical_json_sha256
from review_system.io import dump_json
from test_buildmap_export import BuildMapFixture


def rehash_export(export: dict) -> None:
    export["projection_sha256"] = canonical_json_sha256(_projection_payload(export))
    export["export_id"] = _expected_export_id(export, export["projection_sha256"])
    export["export_sha256"] = canonical_json_sha256(_export_payload(export))


class BuildMapExportIntegrityTests(unittest.TestCase):
    def test_rehashed_body_injection_is_rejected_by_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export()
            export["projection"]["artifacts"][0]["body"] = "INJECTED_PRIVATE_CONTENT"
            rehash_export(export)
            errors = verify_buildmap_export_data(export)
            self.assertTrue(any("Additional properties" in error and "body" in error for error in errors))

    def test_rehashed_reordering_is_rejected_by_canonical_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export()
            self.assertGreaterEqual(len(export["projection"]["artifacts"]), 2)
            export["projection"]["artifacts"].reverse()
            rehash_export(export)
            self.assertIn(
                "projection.artifacts canonical projection mismatch",
                verify_buildmap_export_data(export),
            )

    def test_rehashed_artifact_redaction_flag_is_recomputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export()
            item = export["projection"]["evidence"][0]
            item["artifact_redacted"] = not item["artifact_redacted"]
            rehash_export(export)
            errors = verify_buildmap_export_data(export)
            self.assertTrue(any("artifact_redacted mismatch" in error for error in errors))

    def test_rehashed_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export()
            export["projection"]["artifacts"][0]["relative_path"] = "../escape.json"
            rehash_export(export)
            errors = verify_buildmap_export_data(export)
            self.assertTrue(any("path traversal" in error for error in errors))

    def test_source_fingerprint_tamper_requires_ledger_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export()
            export["source_fingerprint_sha256"] = "0" * 64
            rehash_export(export)
            self.assertEqual([], verify_buildmap_export_data(export))
            self.assertIn(
                "source_fingerprint_sha256 mismatch",
                verify_buildmap_export_source(export, fixture.database),
            )

    def test_source_projection_tamper_is_detected_against_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export()
            export["projection"]["claims"][0]["status"] = "FORGED"
            rehash_export(export)
            self.assertEqual([], verify_buildmap_export_data(export))
            self.assertIn(
                "BuildMap source projection mismatch",
                verify_buildmap_export_source(export, fixture.database),
            )

    def test_custom_redaction_pattern_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            with self.assertRaisesRegex(BuildMapExportError, "redaction path pattern"):
                fixture.export(redaction_paths=["../private/**"])


class BuildMapExportFileSafetyTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_export_and_ledger_symlink_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = BuildMapFixture(root)
            export = fixture.export()
            real_export = root / "real-export.json"
            dump_json(real_export, export)
            export_link = root / "export-link.json"
            ledger_link = root / "ledger-link.sqlite3"
            try:
                export_link.symlink_to(real_export)
                ledger_link.symlink_to(fixture.database)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(BuildMapExportError, "symlinks"):
                load_buildmap_export(export_link)
            with self.assertRaisesRegex(BuildMapExportError, "symlinks"):
                fixture.export()
            with self.assertRaisesRegex(BuildMapExportError, "symlinks"):
                from review_system.buildmap_export import build_buildmap_export

                build_buildmap_export(
                    ledger_link,
                    project_id="demo",
                    run_id=fixture.run_id,
                )

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_output_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = BuildMapFixture(root)
            target = root / "real-output.json"
            target.write_text("existing\n", encoding="utf-8")
            link = root / "output-link.json"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(BuildMapExportError, "symlinks"):
                write_buildmap_export(link, fixture.export())
            self.assertEqual("existing\n", target.read_text(encoding="utf-8"))

    def test_atomic_replace_failure_preserves_existing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            output = Path(tmp) / "export.json"
            output.write_bytes(b"existing\n")
            with patch("review_system.buildmap_export.os.replace", side_effect=OSError("replace failed")):
                with self.assertRaisesRegex(OSError, "replace failed"):
                    write_buildmap_export(output, fixture.export())
            self.assertEqual(b"existing\n", output.read_bytes())
            self.assertEqual([], list(output.parent.glob(output.name + ".*.tmp")))

    def test_invalid_document_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = BuildMapFixture(Path(tmp))
            export = fixture.export()
            export["export_id"] = "buildmap-forged"
            output = Path(tmp) / "invalid.json"
            with self.assertRaises(BuildMapExportVerificationError):
                write_buildmap_export(output, export)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
