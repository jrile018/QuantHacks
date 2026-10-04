"""Behavioral checks for the read-only notebook catalog."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from src.repository_data_catalog import audit_exported_run, data_area_summary, inventory_data_files


class RepositoryDataCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_empty_checkout_reports_missing_areas_without_inventing_files(self):
        self.assertEqual(inventory_data_files(self.root), [])
        summary = data_area_summary(self.root)
        by_area = {row["area"]: row for row in summary}
        self.assertEqual(by_area["raw"], dict(area="raw", path="data/raw", status="missing", files=0, bytes=0))
        self.assertEqual(by_area["processed"]["status"], "missing")
        self.assertEqual(by_area["supporting"]["path"], "repository root metadata")

    def test_nested_inventory_is_sorted_and_metadata_only(self):
        for relative, body in {
            "data/raw/z/secret.csv": b"do not parse me\n",
            "data/processed/a.csv": b"a,b\n1,2\n",
            "artifacts/run/report.json": b"{}",
            "examples/demo.txt": b"sample",
            "references/readme.md": b"ref",
            "configs/sources/test/source.json": b"{}",
            ".massive_cache/cache.bin": b"x",
            "industries.csv": b"industry\n",
            "tickers_8k_sample.json": b"[]",
        }.items():
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        (self.root / "data/raw/__pycache__/hidden.pyc").parent.mkdir()
        (self.root / "data/raw/__pycache__/hidden.pyc").write_bytes(b"hidden")
        (self.root / "data/raw/.ipynb_checkpoints/checkpoint.csv").parent.mkdir()
        (self.root / "data/raw/.ipynb_checkpoints/checkpoint.csv").write_bytes(b"hidden")

        rows = inventory_data_files(self.root)
        self.assertEqual([row["path"] for row in rows], sorted(row["path"] for row in rows))
        self.assertEqual(len(rows), 9)
        self.assertEqual({row["status"] for row in rows}, {"present"})
        self.assertEqual(next(row for row in rows if row["path"] == "data/raw/z/secret.csv")["bytes"], 16)
        summary = {row["area"]: row for row in data_area_summary(self.root, rows)}
        self.assertEqual(summary["raw"]["files"], 1)
        self.assertEqual(summary["raw"]["bytes"], 16)
        self.assertEqual(summary["supporting"]["files"], 2)

    def test_symlinked_files_and_directories_are_skipped(self):
        outside = self.root / "outside.csv"
        outside.write_bytes(b"outside")
        raw = self.root / "data/raw"
        raw.mkdir(parents=True)
        try:
            (raw / "linked.csv").symlink_to(outside)
            (raw / "linked_dir").symlink_to(outside.parent, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertEqual(inventory_data_files(self.root), [])

    def test_symlinked_data_parent_is_not_traversed(self):
        elsewhere = self.root / "elsewhere"
        (elsewhere / "raw").mkdir(parents=True)
        (elsewhere / "raw" / "private.csv").write_bytes(b"private")
        try:
            (self.root / "data").symlink_to(elsewhere, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertEqual(inventory_data_files(self.root), [])
        summary = {row["area"]: row for row in data_area_summary(self.root)}
        self.assertEqual(summary["raw"]["status"], "missing")

    def test_unreadable_directory_is_reported_as_partial(self):
        raw = self.root / "data/raw"
        raw.mkdir(parents=True)
        def failed_walk(path, *, topdown, followlinks, onerror):
            onerror(PermissionError(13, "Access denied", str(raw / "hidden")))
            yield str(raw), [], []

        from unittest.mock import patch
        with patch("src.repository_data_catalog.os.walk", side_effect=failed_walk):
            rows = inventory_data_files(self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "unreadable")
        self.assertEqual(rows[0]["path"], "data/raw/hidden")
        self.assertEqual(rows[0]["type"], "directory")
        self.assertEqual(data_area_summary(self.root, rows)[0]["status"], "partial")

    def test_symlinked_run_directory_is_invalid(self):
        real = self.root / "real"
        real.mkdir()
        (real / "manifest.json").write_text('{"exported_tables":{"good":{"rows":0,"sha256":"' + "0" * 64 + '"}}}', encoding="utf-8")
        try:
            link = self.root / "run"
            link.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertEqual(audit_exported_run(link)[0]["status"], "invalid_manifest")

    def test_audit_missing_and_old_manifests(self):
        run = self.root / "run"
        run.mkdir()
        self.assertEqual(audit_exported_run(run)[0]["status"], "missing")
        (run / "manifest.json").write_text('{"run_id":"old"}', encoding="utf-8")
        self.assertEqual(audit_exported_run(run)[0]["status"], "unsealed")

    def test_audit_hash_verification_missing_and_tamper(self):
        run = self.root / "run"
        run.mkdir()
        content = b"a,b\n1,2\n"
        digest = hashlib.sha256(content).hexdigest()
        (run / "good.csv").write_bytes(content)
        manifest = {"exported_tables": {"good": {"rows": 1, "sha256": digest},
                                        "missing": {"rows": 2, "sha256": "0" * 64}}}
        (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        rows = {row["table"]: row for row in audit_exported_run(run)}
        self.assertEqual(rows["good"]["status"], "verified")
        self.assertEqual(rows["good"]["expected_rows"], 1)
        self.assertEqual(rows["missing"]["status"], "missing")
        (run / "good.csv").write_bytes(b"a,b\n9,9\n")
        self.assertEqual(audit_exported_run(run)[0]["status"], "hash_mismatch")

    def test_audit_rejects_unsafe_names_and_lfs_pointer(self):
        run = self.root / "run"
        run.mkdir()
        lfs = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 8\n"
        (run / "pointer.csv").write_bytes(lfs)
        manifest = {"exported_tables": {
            "../escape.csv": {"rows": 1, "sha256": "0" * 64},
            "pointer": {"rows": 1, "sha256": hashlib.sha256(lfs).hexdigest()},
        }}
        (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        rows = {row["table"]: row for row in audit_exported_run(run)}
        self.assertEqual(rows["../escape.csv"]["status"], "invalid_manifest")
        self.assertEqual(rows["pointer"]["status"], "lfs_pointer")
        self.assertIsNone(rows["../escape.csv"]["observed_sha256"])

    def test_audit_rejects_absolute_name_and_symlinked_csv(self):
        run = self.root / "run"
        run.mkdir()
        outside = self.root / "outside.csv"
        outside.write_bytes(b"secret\n")
        try:
            (run / "linked.csv").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        manifest = {"exported_tables": {
            "C:/outside.csv": {"rows": 1, "sha256": "0" * 64},
            "linked": {"rows": 1, "sha256": hashlib.sha256(outside.read_bytes()).hexdigest()},
        }}
        (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        rows = {row["table"]: row for row in audit_exported_run(run)}
        self.assertEqual(rows["C:/outside.csv"]["status"], "invalid_manifest")
        self.assertEqual(rows["linked"]["status"], "invalid_manifest")
        (run / "manifest.json").write_text("{bad json", encoding="utf-8")
        self.assertEqual(audit_exported_run(run)[0]["status"], "invalid_manifest")


if __name__ == "__main__":
    unittest.main()
