"""실제 격리 파일에서 선택 목록·복제 링크·출처 권한·명시 staging을 검증한다."""
import os
from pathlib import Path
import stat
import tempfile
import unittest

from test_file_ops import ops
from test_data_compat import ROOT_ID


@unittest.skipUnless(os.sys.platform == "darwin", "macOS 파일 게시 계약")
class ImportMapping(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.vault = self.root / "vault"
        self.target = self.root / "copy"
        self.stage = self.root / "private-stage"
        for folder in (self.vault, self.target, self.stage):
            folder.mkdir(mode=0o700)
        for folder in (self.vault / "daily", self.vault / "notes", self.vault / "other"):
            folder.mkdir()

    def scopes(self, sources, targets):
        return (ops.FileScope(self.vault, sources, staging_root=self.stage),
                ops.FileScope(self.target, targets, staging_root=self.stage))

    def test_batch_accounts_for_notes_and_attachment_and_verifies_renamed_links(self):
        source = self.vault / "daily/one.md"
        source.write_text("# One\n[[notes/topic#Heading|표시]] [[notes/topic#^block-a]] ![그림](../asset.png) [[not-selected]]\n")
        (self.vault / "notes/topic.md").write_text("# Heading\nBody ^block-a\n")
        (self.vault / "asset.png").write_bytes(b"synthetic binary\x00\xff")
        selected = ["daily/one.md", "notes/topic.md", "asset.png"]
        mapping = {"daily/one.md": "one.md", "notes/topic.md": "renamed topic.md", "asset.png": "asset-copy.png"}
        sources, targets = self.scopes(selected, mapping.values())
        before = {path: sources.read(path).data for path in selected}
        batch = ops.prepare_import_batch(sources, selected, targets, mapping,
                                        source_root_id=ROOT_ID, attachment_paths=["asset.png"])
        self.assertEqual(batch["selected_count"], 3)
        self.assertEqual(len(batch["entries"]), 3)
        self.assertTrue(batch["selection_accounted"])
        self.assertTrue(batch["copies_complete"])
        self.assertFalse(batch["references_complete"])
        self.assertEqual([item["status"] for item in batch["references"]],
                         ["verified", "verified", "verified", "unverified"])
        body = ops.parse_document(targets.read("one.md").data)[1].decode()
        self.assertIn("[[renamed topic#Heading|표시]]", body)
        self.assertIn("[[renamed topic#^block-a]]", body)
        self.assertIn("![그림](asset-copy.png)", body)
        self.assertEqual(targets.read("asset-copy.png").data, before["asset.png"])
        for path in selected:
            self.assertEqual(sources.read(path).data, before[path])
        self.assertFalse(batch["registration_complete"])
        self.assertFalse(batch["graph_complete"])

    def test_partial_conversion_failure_is_not_dropped_or_claimed_complete(self):
        (self.vault / "daily/one.md").write_text("[[notes/topic]]")
        (self.vault / "notes/topic.md").write_text("---\ntitle: &unsupported value\n---\nbody")
        selected = ["daily/one.md", "notes/topic.md"]
        mapping = dict(zip(selected, ["one.md", "topic.md"]))
        sources, targets = self.scopes(selected, mapping.values())
        batch = ops.prepare_import_batch(sources, selected, targets, mapping, source_root_id=ROOT_ID)
        self.assertEqual(batch["selected_count"], len(batch["entries"]))
        self.assertEqual([entry["status"] for entry in batch["entries"]], ["prepared", "failed"])
        self.assertEqual(batch["entries"][1]["error_code"], "yaml_feature_unsupported")
        self.assertFalse(batch["copies_complete"])
        self.assertEqual(batch["references"][0]["status"], "broken")
        self.assertFalse((self.target / "topic.md").exists())

    def test_managed_identity_removed_together_is_not_reissued_during_import(self):
        value = ops.new_metadata("Managed", "note", [])
        original = ops.serialize_document(value, b"body")
        original = b"\n".join(line for line in original.split(b"\n")
                              if not line.startswith((b"batang_id:", b"batang_schema_version:")))
        (self.vault / "daily/one.md").write_bytes(original)
        source, target = self.scopes(["daily/one.md"], ["one.md"])
        with self.assertRaisesRegex(ops.FileError, "import_managed_metadata_incomplete"):
            ops.prepare_import(source, "daily/one.md", target, "one.md")
        self.assertEqual(source.read("daily/one.md").data, original)
        self.assertFalse((self.target / "one.md").exists())

    def test_batch_reimport_preserves_original_root_binding_and_does_not_duplicate_registry(self):
        (self.vault / "daily/one.md").write_bytes(b"first")
        (self.vault / "notes/topic.md").write_bytes(b"second")
        selected = ["daily/one.md", "notes/topic.md"]
        mapping = dict(zip(selected, ["one.md", "topic.md"]))
        source, target = self.scopes(selected, mapping.values())
        first = ops.prepare_import_batch(source, selected, target, mapping, source_root_id=ROOT_ID)
        results = [entry["result"] for entry in first["entries"]]
        second = ops.prepare_import_batch(source, selected, target, mapping,
                    registered_documents=[(target, result.target_path) for result in results],
                    prior_imports=results)
        self.assertEqual([entry["status"] for entry in second["entries"]], ["skipped", "skipped"])
        self.assertIn(ROOT_ID, second["source_root_binding"])

    def test_vault_root_is_semantic_only_and_short_names_remain_ambiguous(self):
        (self.vault / "daily/one.md").write_text("[[notes/topic]] [[topic]] [[other/topic]]")
        (self.vault / "notes/topic.md").write_text("# metadata meaning A")
        (self.vault / "other/topic.md").write_text("# metadata meaning B")
        sources = ops.FileScope(self.vault, ["daily/one.md", "notes/topic.md", "other/topic.md"])
        refs = ops.inspect_import_links(sources.read("daily/one.md").data, sources, "daily/one.md",
                                        ["notes/topic.md", "other/topic.md"], source_vault_root=self.vault)
        self.assertEqual([ref["status"] for ref in refs], ["selected", "ambiguous", "selected"])
        narrow = ops.FileScope(self.vault / "daily", ["one.md"])
        refs = ops.inspect_import_links(narrow.read("one.md").data, narrow, "one.md", ["one.md"],
                                        source_vault_root=self.vault)
        self.assertTrue(all(ref["status"] == "unverified" for ref in refs))
        with self.assertRaisesRegex(ops.FileError, "path_canonical"):
            ops.inspect_import_links(b"[[notes/topic]]", narrow, "one.md", ["../notes/topic.md"],
                                     source_vault_root=self.vault)

    def test_code_examples_are_preserved_and_duplicate_root_short_names_are_ambiguous(self):
        body = b"`[[topic]]`\n```md\n[[topic]]\n```\n<!-- [[topic]] -->\n[[topic]]\n"
        source, _ = self.scopes(["topic.md", "notes/topic.md", "daily/one.md"], [])
        (self.vault / "topic.md").write_bytes(b"root")
        (self.vault / "notes/topic.md").write_bytes(b"nested")
        refs = ops.inspect_import_links(body, source, "daily/one.md", ["topic.md", "notes/topic.md"])
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["status"], "ambiguous")
        result, _ = ops._link_data.rewrite(body, refs, "one.md", {"topic.md": "renamed.md"})
        self.assertEqual(result, body)

    def test_same_vault_nested_copy_allowed_but_selected_source_collision_is_blocked(self):
        (self.vault / "daily/one.md").write_text("# safe")
        (self.vault / "copy").mkdir()
        source = ops.FileScope(self.vault, ["daily/one.md"], staging_root=self.stage)
        target = ops.FileScope(self.vault, ["copy/one.md", "daily/one.md"], staging_root=self.stage)
        result = ops.prepare_import(source, "daily/one.md", target, "copy/one.md", source_root_id=ROOT_ID)
        self.assertEqual(result.status, "prepared")
        with self.assertRaisesRegex(ops.FileError, "import_source_overlap"):
            ops.prepare_import(source, "daily/one.md", target, "daily/one.md")

    def test_uri_mapping_never_grants_source_read_permission_and_checks_hash(self):
        (self.vault / "daily/one.md").write_text("# original")
        sources, targets = self.scopes(["daily/one.md"], ["copy.md"])
        result = ops.prepare_import(sources, "daily/one.md", targets, "copy.md", source_root_id=ROOT_ID)
        source = result.metadata["sources"][0]
        self.assertEqual(ops.read_source_reference(source, result.source_root_binding, [sources]).data, b"# original")
        empty = ops.FileScope(self.vault, [])
        with self.assertRaisesRegex(ops.FileError, "source_read_scope"):
            ops.read_source_reference(source, result.source_root_binding, [empty])
        (self.vault / "daily/one.md").write_text("# changed")
        with self.assertRaisesRegex(ops.ConflictError, "source_reference_changed"):
            ops.read_source_reference(source, result.source_root_binding, [sources])

    def test_explicit_staging_checks_owner_mode_and_no_follow(self):
        source = ops.FileScope(self.target, ["a.md"], staging_root=self.stage)
        self.assertTrue(source.write("a.md", b"private"))
        self.stage.chmod(0o755)
        other = ops.FileScope(self.target, ["b.md"], staging_root=self.stage)
        with self.assertRaisesRegex(ops.FileError, "private_staging_unavailable"):
            other.write("b.md", b"must not publish")
        self.assertFalse((self.target / "b.md").exists())
        self.stage.chmod(0o700)
        alias = self.root / "stage-link"
        alias.symlink_to(self.stage, target_is_directory=True)
        with self.assertRaisesRegex(ops.FileError, "path_symlink"):
            ops.FileScope(self.target, ["c.md"], staging_root=alias).write("c.md", b"must not publish")


if __name__ == "__main__":
    unittest.main()
