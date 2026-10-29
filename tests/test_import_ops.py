"""실제 macOS 임시 파일로 선택 복제·출처·제한 YAML을 검증한다."""
import copy
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from test_file_ops import metadata, ops


@unittest.skipUnless(os.sys.platform == "darwin", "macOS 파일 게시 계약")
class Imports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.target = self.root / "target"
        self.stage = self.root / "stage"
        for directory in (self.source, self.target, self.stage):
            directory.mkdir(mode=0o700)
        self.addCleanup(patch.stopall)
        patch.object(ops.tempfile, "gettempdir", return_value=str(self.stage)).start()
        self.source_scope = ops.FileScope(self.source, ["note.md", "same.md", "asset.png", "missing.md"])
        self.target_scope = ops.FileScope(self.target, ["copy.md", "second.md", "registered.md"])
        self.original = b"# synthetic note\r\nbody\r\n"
        (self.source / "note.md").write_bytes(self.original)
        (self.source / "note.md").chmod(0o640)

    def prepare(self, **kwargs):
        return ops.prepare_import(self.source_scope, "note.md", self.target_scope,
                                  kwargs.pop("target_path", "copy.md"), **kwargs)

    def test_plain_document_has_independent_bytes_and_actual_source_provenance(self):
        before = (self.source / "note.md").stat()
        result = self.prepare(subject="합성 문서")
        self.assertEqual(result.status, "prepared")
        self.assertEqual((self.source / "note.md").read_bytes(), self.original)
        self.assertEqual(ops._identity((self.source / "note.md").stat()), ops._identity(before))
        copied, body = ops.parse_document((self.target / "copy.md").read_bytes())
        self.assertEqual(body, self.original)
        self.assertEqual(copied["subject"], "합성 문서")
        self.assertEqual(copied["sources"][0]["path"], str(self.source / "note.md"))
        self.assertEqual(copied["sources"][0]["sha256"], ops.sha256(self.original))
        self.assertIsNone(copied["sources"][0]["raw_path"])
        self.assertEqual(result.provenance["source_sha256"], ops.sha256(self.original))
        self.assertEqual(result.target_sha256, ops.sha256((self.target / "copy.md").read_bytes()))
        self.assertNotEqual((self.target / "copy.md").stat().st_ino, before.st_ino)
        self.assertEqual((self.target / "copy.md").stat().st_nlink, 1)
        self.assertEqual(stat.S_IMODE((self.target / "copy.md").stat().st_mode), 0o600)
        self.assertTrue(ops.verify_import_source(self.source_scope, result))
        self.assertFalse((self.target / "ACTIVE.md").exists())

    def test_strict_v1_v2_import_preserves_all_bytes_sources_id_schema_and_body(self):
        for version in (1, 2):
            value = metadata()
            value["batang_schema_version"] = version
            value["aliases"] = ["별칭", "English", "별칭"]
            original = ops.serialize_document(value, b"\r\nbody\r\n")
            header, body = ops.split_frontmatter(original)
            original = b"---\r\n" + header.replace(b"\n", b"\r\n") + b"---\r\n" + body
            (self.source / "note.md").write_bytes(original)
            result = self.prepare(target_path="copy.md" if version == 1 else "second.md")
            self.assertEqual((self.target / result.target_path).read_bytes(), original)
            self.assertEqual(result.metadata, value)

    def test_limited_yaml_scalar_and_block_lists_preserve_semantic_values_and_body(self):
        original = ("---\r\nsubject: 합성 주제\r\ntags:\r\n  - 태그\r\n  - 'tag''s'\r\n"
                    "aliases:\r\n  - 별칭\r\n  - \" English \"\r\n  - 별칭\r\n"
                    "content_kind: note\r\n---\r\n\r\n본문\r\n").encode()
        (self.source / "note.md").write_bytes(original)
        result = self.prepare(subject="덮어쓰지 않음")
        self.assertEqual(result.metadata["subject"], "합성 주제")
        self.assertEqual(result.metadata["tags"], ["태그", "tag's"])
        self.assertEqual(result.metadata["aliases"], ["별칭", " English ", "별칭"])
        self.assertEqual(ops.parse_document((self.target / "copy.md").read_bytes())[1], "\r\n본문\r\n".encode())
        self.assertEqual((self.source / "note.md").read_bytes(), original)

    def test_managed_v1_v2_missing_required_field_is_held_without_default_repair(self):
        active = self.target / "ACTIVE.md"
        active.write_bytes(b"# fixture active remains unchanged\n")
        for version in (1, 2):
            for missing in ops.KEYS:
                with self.subTest(version=version, missing=missing):
                    value = metadata()
                    value["batang_schema_version"] = version
                    del value[missing]
                    header = "".join(key + ": " + json.dumps(item, ensure_ascii=False) + "\n"
                                     for key, item in value.items())
                    original = ("---\n" + header + "---\nbody\n").encode()
                    (self.source / "note.md").write_bytes(original)
                    source_before = ops._identity((self.source / "note.md").stat())
                    with self.assertRaises(ops.FileError):
                        ops.parse_document(original)
                    with self.assertRaisesRegex(ops.FileError, "import_managed_metadata_incomplete"):
                        self.prepare()
                    self.assertEqual((self.source / "note.md").read_bytes(), original)
                    self.assertEqual(ops._identity((self.source / "note.md").stat()), source_before)
                    self.assertFalse((self.target / "copy.md").exists())
                    self.assertEqual(active.read_bytes(), b"# fixture active remains unchanged\n")
                    self.assertFalse(list(self.stage.iterdir()))

    def test_managed_yaml_format_conversion_preserves_id_and_schema_without_defaults(self):
        for version in (1, 2):
            value = metadata()
            value["batang_schema_version"] = version
            original = ops.serialize_document(value, self.original).replace(
                b'subject: "' + "합성 주제".encode() + b'"', b"subject: " + "합성 주제".encode())
            (self.source / "note.md").write_bytes(original)
            result = self.prepare(target_path="copy.md" if version == 1 else "second.md")
            self.assertEqual(result.metadata, value)
            self.assertEqual((self.source / "note.md").read_bytes(), original)

    def test_unsupported_yaml_is_held_without_source_changes_or_registration(self):
        invalid = ("unknown: value", "subject: first\nsubject: second", "subject: &value anchored",
                   "subject: *value", "subject: !!str text", "<<: *value", "subject: |\n  body",
                   "subject: true", "subject: null", "subject: 2026-10-29", "subject: .NaN",
                   "aliases: [plain, unquoted]", "aliases:\n  - good\n  - 1", "aliases: null",
                   "aliases: [\"good\", 3]", "aliases: [\" \"]", "sources:\n  - id: nested",
                   "subject:\n  nested: value", "subject: foo # comment", "aliases:\n  - good\n    - nested")
        for header in invalid:
            with self.subTest(header=header):
                original = ("---\n" + header + "\n---\nbody\n").encode()
                (self.source / "note.md").write_bytes(original)
                with self.assertRaises(ops.FileError):
                    self.prepare()
                self.assertEqual((self.source / "note.md").read_bytes(), original)
                self.assertFalse((self.target / "copy.md").exists())

    def test_overlap_symlink_hardlink_and_name_collision_are_not_overwritten(self):
        same = ops.FileScope(self.source, ["note.md", "copy.md"])
        with self.assertRaisesRegex(ops.FileError, "import_source_overlap"):
            ops.prepare_import(self.source_scope, "note.md", same, "copy.md")
        (self.source / "sub").mkdir()
        nested = ops.FileScope(self.source / "sub", ["copy.md"])
        with self.assertRaisesRegex(ops.FileError, "import_source_overlap"):
            ops.prepare_import(self.source_scope, "note.md", nested, "copy.md")
        os.link(self.source / "note.md", self.target / "copy.md")
        with self.assertRaisesRegex(ops.ConflictError, "import_same_inode"):
            self.prepare()
        (self.target / "copy.md").unlink()
        (self.target / "copy.md").symlink_to(self.source / "note.md")
        with self.assertRaisesRegex(ops.ConflictError, "import_target_collision"):
            self.prepare()
        (self.target / "copy.md").unlink()
        (self.target / "copy.md").write_bytes(b"user-owned")
        with self.assertRaisesRegex(ops.ConflictError, "import_target_collision"):
            self.prepare()
        self.assertEqual((self.target / "copy.md").read_bytes(), b"user-owned")
        self.assertEqual((self.source / "note.md").read_bytes(), self.original)

    def test_source_parent_or_leaf_link_alias_is_rejected(self):
        alias = self.root / "source-alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(OSError):
            ops.prepare_import(ops.FileScope(alias, ["note.md"]), "note.md", self.target_scope, "copy.md")
        (self.source / "same.md").symlink_to(self.source / "note.md")
        with self.assertRaises(OSError):
            ops.prepare_import(self.source_scope, "same.md", self.target_scope, "copy.md")

    def test_same_bytes_from_different_sources_are_not_deduplicated(self):
        first = self.prepare()
        (self.source / "same.md").write_bytes(self.original)
        second = ops.prepare_import(self.source_scope, "same.md", self.target_scope, "second.md",
                                    prior_imports=[first], registered_documents=[(self.target_scope, "copy.md")])
        self.assertEqual(second.status, "prepared")
        self.assertNotEqual(second.metadata["batang_id"], first.metadata["batang_id"])
        self.assertNotEqual(second.provenance["source_path"], first.provenance["source_path"])

    def test_reimport_requires_source_hash_identity_and_valid_registered_document(self):
        first = self.prepare()
        registered = [(self.target_scope, "copy.md")]
        result = self.prepare(prior_imports=[first], registered_documents=registered)
        self.assertEqual(result.status, "skipped")
        self.assertEqual(result.target_sha256, first.target_sha256)
        with self.assertRaisesRegex(ops.ConflictError, "import_registered_missing"):
            self.prepare(prior_imports=[first])
        (self.source / "note.md").write_bytes(b"changed source")
        with self.assertRaisesRegex(ops.ConflictError, "import_target_collision"):
            self.prepare(prior_imports=[first], registered_documents=registered)
        changed = self.prepare(target_path="second.md", prior_imports=[first], registered_documents=registered)
        self.assertEqual(changed.status, "prepared")
        self.assertNotEqual(changed.provenance["source_sha256"], first.provenance["source_sha256"])
        self.assertEqual((self.target / "copy.md").read_bytes(),
                         ops.serialize_document(first.metadata, self.original))

    def test_registered_missing_invalid_id_and_source_identity_conflicts_stop(self):
        first = self.prepare()
        registered = [(self.target_scope, "copy.md")]
        original_copy = (self.target / "copy.md").read_bytes()
        (self.target / "copy.md").write_bytes(b"not a managed document")
        with self.assertRaises(ops.FileError):
            self.prepare(prior_imports=[first], registered_documents=registered)
        changed = copy.deepcopy(first.metadata)
        changed["batang_id"] = "different-id"
        (self.target / "copy.md").write_bytes(ops.serialize_document(changed, self.original))
        with self.assertRaisesRegex(ops.ConflictError, "import_registered_identity"):
            self.prepare(prior_imports=[first], registered_documents=registered)
        (self.target / "copy.md").write_bytes(original_copy)
        (self.source / "note.md").rename(self.source / "detached.md")
        (self.source / "note.md").write_bytes(self.original)
        with self.assertRaisesRegex(ops.ConflictError, "import_source_identity_conflict"):
            self.prepare(prior_imports=[first], registered_documents=registered)

    def test_explicit_registered_metadata_id_collision_blocks_new_copy(self):
        value = metadata()
        original = ops.serialize_document(value, self.original)
        (self.source / "note.md").write_bytes(original)
        (self.target / "registered.md").write_bytes(original)
        with self.assertRaisesRegex(ops.ConflictError, "import_metadata_id_collision"):
            self.prepare(registered_documents=[(self.target_scope, "registered.md")])
        self.assertFalse((self.target / "copy.md").exists())

    def test_duplicate_registered_ids_are_not_ignored_during_reimport(self):
        first = self.prepare()
        (self.target / "registered.md").write_bytes((self.target / "copy.md").read_bytes())
        with self.assertRaisesRegex(ops.ConflictError, "import_registered_id_collision"):
            self.prepare(prior_imports=[first], registered_documents=[
                (self.target_scope, "copy.md"), (self.target_scope, "registered.md")])

    def test_registered_deletion_and_publication_collision_keep_other_files(self):
        first = self.prepare()
        (self.target / "copy.md").unlink()
        with self.assertRaises(FileNotFoundError):
            self.prepare(prior_imports=[first], registered_documents=[(self.target_scope, "copy.md")])
        real_rename = ops._rename_new_at

        def collision(source_parent, temporary, target_parent, name):
            (self.target / "copy.md").write_bytes(b"external target")
            return real_rename(source_parent, temporary, target_parent, name)

        with patch.object(ops, "_rename_new_at", side_effect=collision):
            with self.assertRaises(FileExistsError):
                self.prepare()
        self.assertEqual((self.target / "copy.md").read_bytes(), b"external target")
        self.assertEqual((self.source / "note.md").read_bytes(), self.original)
        temporary, = self.stage.rglob(".batang-*.tmp")
        self.assertEqual(ops.parse_document(temporary.read_bytes())[1], self.original)

    def test_preparation_reads_independent_raw_copy_before_conversion(self):
        real_write = self.target_scope.write
        observed = []

        def write(path, data, **kwargs):
            prepare = kwargs["_prepare"]

            def verify_raw(copied):
                observed.append(copied)
                self.assertEqual(copied, self.original)
                temporary, = self.stage.rglob(".batang-*.tmp")
                self.assertNotEqual(temporary.stat().st_ino, (self.source / "note.md").stat().st_ino)
                return prepare(copied)

            kwargs["_prepare"] = verify_raw
            return real_write(path, data, **kwargs)

        with patch.object(self.target_scope, "write", side_effect=write):
            self.prepare()
        self.assertEqual(observed, [self.original])

    def test_references_read_only_explicit_selected_paths_and_report_unknowns(self):
        original = b"![asset](asset.png) [[missing.md]] [[unknown.md]] [outside](../secret.md)"
        (self.source / "note.md").write_bytes(original)
        (self.source / "asset.png").write_bytes(b"selected attachment")
        (self.root / "secret.md").write_bytes(b"never read")
        with patch.object(self.source_scope, "read", wraps=self.source_scope.read) as read:
            result = self.prepare(selected_sources=["asset.png", "missing.md"])
        self.assertEqual([call.args[0] for call in read.call_args_list], ["asset.png", "missing.md"])
        self.assertEqual([reference["status"] for reference in result.references],
                         ["selected", "broken", "unverified", "unverified"])
        self.assertFalse((self.target / "asset.png").exists())
        with self.assertRaisesRegex(ops.FileError, "import_reference_scope"):
            self.prepare(target_path="second.md", selected_sources=["unknown.md"])

    def test_source_change_during_staging_blocks_publication_and_preserves_source(self):
        real_fsync = ops.os.fsync
        changed = []

        def race(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode) and not changed:
                (self.source / "note.md").write_bytes(b"external edit")
                changed.append(True)
            return real_fsync(fd)

        with patch.object(ops.os, "fsync", side_effect=race):
            with self.assertRaisesRegex(ops.ConflictError, "import_source_changed"):
                self.prepare()
        self.assertEqual((self.source / "note.md").read_bytes(), b"external edit")
        self.assertFalse((self.target / "copy.md").exists())

    def test_source_change_after_publication_preserves_copy_and_registration_is_not_ready(self):
        real_rename = ops._rename_new_at

        def race(*args):
            real_rename(*args)
            (self.source / "note.md").write_bytes(b"external edit")

        with patch.object(ops, "_rename_new_at", side_effect=race):
            with self.assertRaisesRegex(ops.ConflictError, "import_source_changed"):
                self.prepare()
        self.assertTrue((self.target / "copy.md").is_file())
        self.assertEqual(ops.parse_document((self.target / "copy.md").read_bytes())[1], self.original)

    def test_explicit_registration_time_source_recheck_detects_later_edit(self):
        result = self.prepare()
        (self.source / "note.md").write_bytes(b"later edit")
        with self.assertRaisesRegex(ops.ConflictError, "import_source_changed"):
            ops.verify_import_source(self.source_scope, result)

    def host_registration_fixture(self, result):
        """ACTIVE 등록은 호스트에 해당하는 fixture 동작이며 helper가 자동 실행하지 않는다."""
        ops.verify_import_source(self.source_scope, result)
        target = self.target_scope.read(result.target_path)
        parsed, _ = ops.parse_document(target.data)
        if target.sha256 != result.target_sha256 or parsed["batang_id"] != result.metadata["batang_id"]:
            raise ops.ConflictError("host_registration_target_changed")
        active = ops.FileScope(self.target, ["ACTIVE.md"])
        backups = ops.FileScope(self.target / "backups", ["ACTIVE.before"])
        previous = active.read("ACTIVE.md")
        updated = previous.data + ("- [fixture](" + result.target_path + ")\n").encode()
        active.write("ACTIVE.md", updated, previous.sha256,
                     backup_scope=backups, backup_path="ACTIVE.before")
        self.assertEqual(active.read("ACTIVE.md").data, updated)
        self.assertEqual(self.target_scope.read(result.target_path).sha256, result.target_sha256)

    def prepare_registration_fixture(self):
        (self.target / "ACTIVE.md").write_bytes(b"# selected fixture notes\n")
        (self.target / "backups").mkdir(mode=0o700)
        return self.prepare()

    def test_host_registration_sequence_reopens_target_and_active_and_keeps_backup(self):
        result = self.prepare_registration_fixture()
        original_active = (self.target / "ACTIVE.md").read_bytes()
        self.host_registration_fixture(result)
        self.assertEqual((self.target / "backups/ACTIVE.before").read_bytes(), original_active)
        self.assertIn(b"- [fixture](copy.md)\n", (self.target / "ACTIVE.md").read_bytes())
        self.assertEqual((self.source / "note.md").read_bytes(), self.original)

    def test_host_registration_source_change_leaves_active_and_copy_untouched(self):
        result = self.prepare_registration_fixture()
        original_active = (self.target / "ACTIVE.md").read_bytes()
        original_copy = (self.target / "copy.md").read_bytes()
        (self.source / "note.md").write_bytes(b"later source change")
        with self.assertRaisesRegex(ops.ConflictError, "import_source_changed"):
            self.host_registration_fixture(result)
        self.assertEqual((self.target / "ACTIVE.md").read_bytes(), original_active)
        self.assertEqual((self.target / "copy.md").read_bytes(), original_copy)
        self.assertFalse(list((self.target / "backups").iterdir()))

    def test_host_registration_target_change_leaves_active_and_user_edit_untouched(self):
        result = self.prepare_registration_fixture()
        original_active = (self.target / "ACTIVE.md").read_bytes()
        changed = ops.serialize_document(result.metadata, b"user edited copy")
        (self.target / "copy.md").write_bytes(changed)
        with self.assertRaisesRegex(ops.ConflictError, "host_registration_target_changed"):
            self.host_registration_fixture(result)
        self.assertEqual((self.target / "ACTIVE.md").read_bytes(), original_active)
        self.assertEqual((self.target / "copy.md").read_bytes(), changed)
        self.assertFalse(list((self.target / "backups").iterdir()))


if __name__ == "__main__":
    unittest.main()
