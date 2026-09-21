"""Unit checks for non-circular release manifest and binding helpers."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


manifest = load("generate_release_manifest", ROOT / "tools/generate_release_manifest.py")
binding = load("generate_manuscript_binding", ROOT / "tools/generate_manuscript_binding.py")


class ReleaseClosureTests(unittest.TestCase):
    def test_release_name_contract(self):
        self.assertEqual(manifest.validate_release_name("companion-2026-09-21-rc1"),
                         "companion-2026-09-21-rc1")
        for invalid in ("S3", "companion 2026", "../release", ""):
            with self.assertRaises(ValueError):
                manifest.validate_release_name(invalid)

    def test_manifest_is_deterministic_for_exact_head(self):
        first = manifest.build_manifest(ROOT, "HEAD", "companion-2026-09-21-rc1")
        second = manifest.build_manifest(ROOT, first["content_commit"], "companion-2026-09-21-rc1")
        self.assertEqual(first, second)
        self.assertEqual(first["totals"]["files"], len(first["files"]))
        self.assertEqual(first["files"], sorted(first["files"], key=lambda row: row["path"]))
        self.assertTrue(any(row["path"] == "companion/FIGURE_MAP.json" for row in first["files"]))

    def test_tracked_output_is_rejected(self):
        commit = manifest.resolve_commit(ROOT, "HEAD")
        with self.assertRaisesRegex(ValueError, "circular"):
            manifest.output_is_untracked_at_commit(ROOT, commit, ROOT / "README.md")

    def test_binding_reads_json_from_exact_commit(self):
        commit = manifest.resolve_commit(ROOT, "HEAD")
        value, raw = binding.read_commit_json(
            ROOT, commit, "companion/FIGURE_MAP.json"
        )
        expected = next(
            row for row in manifest.build_manifest(
                ROOT, commit, "companion-2026-09-21-rc1"
            )["files"]
            if row["path"] == "companion/FIGURE_MAP.json"
        )
        self.assertEqual(binding.digest_bytes(raw), expected["sha256"])
        self.assertEqual(value["schema"], "publication-figure-map/1.1")

    def test_binding_refuses_artifact_path_escape(self):
        for name in ("../outside", "/absolute", "nested\\windows", "a//b"):
            with self.assertRaises(ValueError):
                binding.path_under(ROOT, name)
        self.assertEqual(
            binding.path_under(ROOT, "release/MANUSCRIPT_TARGET.json"),
            ROOT / "release/MANUSCRIPT_TARGET.json",
        )

    def test_new_json_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "asset.json"
            manifest.write_new_json(path, {"status": "PASS"})
            with self.assertRaises(FileExistsError):
                manifest.write_new_json(path, {"status": "PASS"})

    def test_schemas_and_candidate_metadata_are_json(self):
        for path in (
            ROOT / "release/RELEASE_CONTENT_MANIFEST.schema.json",
            ROOT / "release/MANUSCRIPT_BINDING.schema.json",
            ROOT / "release/RELEASE_CANDIDATE.json",
            ROOT / "release/MANUSCRIPT_TARGET.json",
        ):
            self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_manuscript_target_has_three_sources_and_three_pdfs(self):
        target = json.loads(
            (ROOT / "release/MANUSCRIPT_TARGET.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(target["sources"]), 3)
        self.assertEqual(len(target["pdfs"]), 3)
        for group in (target["sources"], target["pdfs"]):
            self.assertEqual(len({row["name"] for row in group}), 3)
            self.assertTrue(all(len(row["sha256"]) == 64 for row in group))

    def test_candidate_name_is_author_approved_without_external_action(self):
        candidate = json.loads(
            (ROOT / "release/RELEASE_CANDIDATE.json").read_text(encoding="utf-8")
        )
        self.assertEqual(candidate["release_name"], "companion-2026-09-21-rc1")
        self.assertEqual(candidate["name_approval"]["status"], "APPROVED")
        self.assertEqual(candidate["name_approval"]["authority"], "author")
        self.assertFalse(candidate["external_actions_performed"])
        self.assertFalse(candidate["external_actions_authorized"])

    def test_release_name_is_consistent_across_public_metadata(self):
        name = "companion-2026-09-21-rc1"
        for relative in (
            "CHANGELOG.md",
            "CITATION.cff",
            "README.md",
            "companion/README.md",
            "docs/VERIFICATION.md",
            "release/README.md",
            "release/RELEASE_NOTES.md",
        ):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn(name, text, relative)
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertNotIn("## Unreleased", changelog)
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
        self.assertIn("version: " + name, citation)


if __name__ == "__main__":
    unittest.main()
