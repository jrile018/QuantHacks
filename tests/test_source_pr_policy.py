"""The source PR gate runs against small local repositories only."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.source_pr_policy import validate_changed_paths


ROOT = Path(__file__).resolve().parents[1]


class SourcePrPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source("alpha-source")

    def source(self, source_id):
        folder = self.root / "configs" / "sources" / source_id
        folder.mkdir(parents=True)
        (folder / "source.json").write_text(json.dumps({"source_id": source_id}), encoding="utf-8")
        (folder / "manifest.jsonl").write_text('{}\n', encoding="utf-8")
        (folder / "README.md").write_text("# Source\n", encoding="utf-8")
        return folder

    def check(self, paths, branch="codex/source-alpha-source-alice"):
        return validate_changed_paths(paths, self.root, branch)

    def test_registered_source_files_and_adapter_pair_are_eligible(self):
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "src" / "alpha_source_adapter.py").write_text("VERSION = 1\n")
        (self.root / "tests" / "test_alpha_source_adapter.py").write_text("def test_version(): pass\n")
        result = self.check([
            "configs/sources/alpha-source/source.json",
            "configs/sources/alpha-source/manifest.jsonl",
            "configs/sources/alpha-source/README.md",
            "src/alpha_source_adapter.py",
            "tests/test_alpha_source_adapter.py",
        ])
        self.assertTrue(result.eligible, result.errors)
        self.assertEqual(result.source_id, "alpha-source")

    def test_adapter_only_change_uses_registered_source(self):
        (self.root / "src").mkdir()
        (self.root / "tests").mkdir()
        (self.root / "src" / "alpha_source_adapter.py").write_text("VERSION = 1\n")
        (self.root / "tests" / "test_alpha_source_adapter.py").write_text("def test_version(): pass\n")
        self.assertTrue(self.check(["src/alpha_source_adapter.py"]).eligible)

    def test_shared_core_ci_and_schema_paths_are_ineligible(self):
        for path in ("src/document_manifest.py", ".github/workflows/source.yml", "configs/schema.json"):
            with self.subTest(path=path):
                result = self.check(["configs/sources/alpha-source/README.md", path])
                self.assertFalse(result.eligible)
                self.assertTrue(result.errors)

    def test_branch_source_must_match_and_one_namespace_only(self):
        self.source("beta-source")
        self.assertFalse(self.check(["configs/sources/alpha-source/README.md"],
                                    "codex/source-beta-source-alice").eligible)
        self.assertFalse(self.check(["configs/sources/alpha-source/README.md",
                                     "configs/sources/beta-source/README.md"]).eligible)
        self.assertFalse(self.check(["configs/sources/alpha-source/README.md"],
                                    "feature/alpha-source").eligible)

    def test_overlapping_registered_names_do_not_block_affected_source(self):
        self.source("alpha")
        self.assertTrue(self.check(["configs/sources/alpha/README.md"],
                                   "codex/source-alpha-source-alice").eligible)
        self.assertTrue(self.check(["configs/sources/alpha-source/README.md"],
                                   "codex/source-alpha-source-alice").eligible)
        self.assertFalse(self.check(["src/unknown_adapter.py"]).eligible)
        self.assertFalse(self.check([]).eligible)

    def test_path_escapes_disguised_files_and_symlinks_are_ineligible(self):
        bad_paths = [
            "configs/sources/alpha-source/../beta-source/README.md",
            "configs\\sources\\alpha-source\\README.md",
            "/configs/sources/alpha-source/README.md",
            "configs/sources/alpha-source/schema.json",
            "examples/team_sources/alpha-source/.git/config.txt",
            "examples/team_sources/alpha-source/raw/secret.txt",
            "examples/team_sources/alpha-source/credentials.txt",
            "examples/team_sources/alpha-source/results.html",
            "examples/team_sources/alpha-source/secret.py",
        ]
        for path in bad_paths:
            with self.subTest(path=path):
                self.assertFalse(self.check([path]).eligible)
        link = self.root / "examples" / "team_sources" / "alpha-source" / "linked.txt"
        link.parent.mkdir(parents=True)
        try:
            link.symlink_to(self.root / "configs" / "sources" / "alpha-source" / "README.md")
        except (OSError, NotImplementedError):
            pass
        else:
            self.assertFalse(self.check(["examples/team_sources/alpha-source/linked.txt"]).eligible)

    def test_required_files_id_and_adapter_test_are_enforced(self):
        folder = self.root / "configs" / "sources" / "alpha-source"
        (folder / "manifest.jsonl").unlink()
        self.assertFalse(self.check(["configs/sources/alpha-source/manifest.jsonl"]).eligible)
        (folder / "manifest.jsonl").write_text('{}\n')
        (folder / "source.json").write_text('{"source_id":"beta-source"}')
        self.assertFalse(self.check(["configs/sources/alpha-source/source.json"]).eligible)
        (folder / "source.json").write_text('{"source_id":"alpha-source"}')
        (self.root / "src").mkdir()
        (self.root / "src" / "alpha_source_adapter.py").write_text("VERSION = 1\n")
        self.assertFalse(self.check(["src/alpha_source_adapter.py"]).eligible)

    def test_registry_symlink_cannot_register_an_adapter(self):
        backing = self.root / "backing"
        (self.root / "configs").rename(backing)
        try:
            (self.root / "configs").symlink_to(backing, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("directory symlinks unavailable")
        self.assertFalse(self.check(["src/alpha_source_adapter.py"]).eligible)

    def test_file_size_caps_are_enforced(self):
        sample = self.root / "examples" / "team_sources" / "alpha-source" / "sample.txt"
        sample.parent.mkdir(parents=True)
        with sample.open("wb") as stream:
            stream.truncate(1024 * 1024 + 1)
        self.assertFalse(self.check(["examples/team_sources/alpha-source/sample.txt"]).eligible)
        sample.unlink()
        doc = self.root / "configs" / "sources" / "alpha-source" / "README.md"
        with doc.open("wb") as stream:
            stream.truncate(5 * 1024 * 1024 + 1)
        self.assertFalse(self.check(["configs/sources/alpha-source/README.md"]).eligible)

    def test_git_cli_rejects_rename_from_shared_path(self):
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.org")
        shared = self.root / "shared.txt"
        shared.write_text("original\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        base = self.git("rev-parse", "HEAD").strip()
        example = self.root / "examples" / "team_sources" / "alpha-source" / "shared.txt"
        example.parent.mkdir(parents=True)
        shared.rename(example)
        self.git("add", "-A")
        self.git("commit", "-qm", "rename")
        head = self.git("rev-parse", "HEAD").strip()
        command = [sys.executable, str(ROOT / "scripts" / "check_source_pr.py"),
                   "--repo-root", str(self.root), "--base", base, "--head", head,
                   "--branch", "codex/source-alpha-source-alice"]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 1, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertFalse(result["eligible"])
        self.assertTrue(any("shared.txt" in error for error in result["errors"]), result)

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True,
                                text=True, check=True)
        return result.stdout


if __name__ == "__main__":
    unittest.main()
