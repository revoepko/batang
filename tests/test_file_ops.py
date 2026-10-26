"""운영 자료를 읽지 않는 격리된 파일 동작 검증."""
import copy
import ctypes
import errno
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[1] / "skills/batang/scripts/file_ops.py"
spec = importlib.util.spec_from_file_location("batang009_file_ops", HELPER)
ops = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ops
spec.loader.exec_module(ops)


def metadata():
    return {"batang_schema_version": 1, "batang_id": "synth-source-a", "subject": "합성 주제",
            "tags": ["한글", "조건"], "content_kind": "note",
            "sources": [{"id": "synth-source-a", "path": "synthetic/original.md", "origin": "user",
                         "sha256": "1" * 64, "raw_path": "legacy/raw.md"}],
            "legacy_refs": [{"path": "legacy/wiki.md", "sha256": "2" * 64},
                            {"path": "legacy/metadata.json", "sha256": "3" * 64},
                            {"path": "legacy/provenance.json", "sha256": "4" * 64}]}


class Documents(unittest.TestCase):
    def test_named_synthetic_fixtures_roundtrip_without_byte_change(self):
        for name, version in (("schema-v1.md", 1), ("schema-v2-null.md", 2)):
            original = (Path(__file__).parent / "fixtures" / name).read_bytes()
            parsed, body = ops.parse_document(original)
            self.assertEqual(parsed["batang_schema_version"], version)
            self.assertEqual(ops.serialize_document(parsed, body, original=original), original)

    def test_new_v2_metadata_uses_uuid_and_only_missing_defaults(self):
        sources = [{"id": "source-a", "origin": "user", "path": None,
                    "sha256": None, "raw_path": None}]
        created = ops.new_metadata("주제", "note", sources)
        self.assertEqual(created["batang_schema_version"], 2)
        self.assertEqual(uuid.UUID(created["batang_id"]).version, 4)
        self.assertEqual(created["tags"], [])
        self.assertEqual(created["legacy_refs"], [])
        created["sources"][0]["origin"] = "different"
        self.assertEqual(sources[0]["origin"], "user")
        for kwargs in ({"tags": None}, {"legacy_refs": None}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ops.FileError):
                ops.new_metadata("주제", "note", sources, **kwargs)

    def test_v2_nullable_source_combinations_and_preserved_existing_id(self):
        for bits in range(8):
            value = metadata()
            value["batang_schema_version"] = 2
            for index, key in enumerate(("path", "sha256", "raw_path")):
                if bits & (1 << index):
                    value["sources"][0][key] = None
            encoded = ops.serialize_document(value, b"body\r\n")
            actual, body = ops.parse_document(encoded)
            self.assertEqual(actual, value)
            self.assertEqual(actual["batang_id"], "synth-source-a")
            self.assertEqual(body, b"body\r\n")

    def test_v1_remains_strict_and_saved_documents_require_all_keys(self):
        for version in (1, 2):
            for key in ops.KEYS:
                value = metadata()
                value["batang_schema_version"] = version
                del value[key]
                with self.subTest(version=version, missing=key), self.assertRaises(ops.FileError):
                    ops.serialize_document(value, b"body")
        for key in ("path", "sha256", "raw_path"):
            value = metadata()
            value["sources"][0][key] = None
            with self.subTest(v1_null=key), self.assertRaises(ops.FileError):
                ops.serialize_document(value, b"body")

    def test_v2_invalid_sources_and_schema_rejected(self):
        for key, invalid in (("id", None), ("id", ""), ("origin", ""), ("origin", 7),
                             ("path", ""), ("raw_path", False), ("sha256", "A" * 64),
                             ("sha256", "abcd"), ("sha256", 7)):
            value = metadata()
            value["batang_schema_version"] = 2
            value["sources"][0][key] = invalid
            with self.subTest(key=key, invalid=invalid), self.assertRaises(ops.FileError):
                ops.serialize_document(value, b"body")
        for invalid in (0, 3, True, "2", None):
            value = metadata()
            value["batang_schema_version"] = invalid
            with self.subTest(version=invalid), self.assertRaises(ops.FileError):
                ops.serialize_document(value, b"body")

    def test_original_parameter_preserves_noop_crlf_and_v1_on_edit(self):
        original = ops.serialize_document(metadata(), b"body\r\n")
        header, body = ops.split_frontmatter(original)
        crlf = b"---\r\n" + header.replace(b"\n", b"\r\n") + b"---\r\n" + body
        parsed, parsed_body = ops.parse_document(crlf)
        self.assertEqual(ops.serialize_document(parsed, parsed_body, original=crlf), crlf)
        parsed["subject"] = "명시 수정"
        updated = ops.serialize_document(parsed, parsed_body, original=crlf)
        actual, actual_body = ops.parse_document(updated)
        self.assertEqual(actual["batang_schema_version"], 1)
        self.assertEqual(actual["batang_id"], metadata()["batang_id"])
        self.assertEqual(actual["sources"], metadata()["sources"])
        self.assertEqual(actual_body, body)

    def test_unicode_separators_in_metadata_roundtrip(self):
        for separator in ("\u0085", "\u2028", "\u2029"):
            with self.subTest(codepoint=hex(ord(separator))):
                value = metadata()
                value["subject"] = "앞" + separator + "뒤"
                value["tags"] = ["태그" + separator + "계속"]
                value["sources"][0]["origin"] = "origin" + separator + "continued"
                body = ("\r\n본문" + separator + "보존\n").encode()
                encoded = ops.serialize_document(value, body)
                self.assertIn(separator.encode(), encoded)
                decoded, actual_body = ops.parse_document(encoded)
                self.assertEqual(decoded, value)
                self.assertEqual(actual_body, body)

    def test_metadata_and_body_roundtrip_preserves_bytes(self):
        body = "\r\n# 본문 😀\r\n\r\n부정: 실행하지 않음. e\u0301 ≠ é\n마지막".encode()
        original = metadata()
        untouched = copy.deepcopy(original)
        encoded = ops.serialize_document(original, body)
        decoded, actual = ops.parse_document(encoded)
        self.assertEqual(decoded, original)
        self.assertEqual(actual, body)
        self.assertEqual(original, untouched)
        self.assertEqual(decoded["sources"][0]["sha256"], "1" * 64)
        self.assertEqual(decoded["legacy_refs"][0]["sha256"], "2" * 64)

    def test_split_legacy_framing_without_interpreting_or_normalizing(self):
        body = b"\r\n# synthetic\r\n\nend"
        header, result = ops.split_frontmatter(b"---\r\nlegacy: [not-json]\r\n---\r\n" + body)
        self.assertEqual(header, b"legacy: [not-json]\r\n")
        self.assertEqual(result, body)
        with self.assertRaises(ops.FileError):
            ops.parse_document(b"---\nsubject: plain-yaml\n---\n" + body)

    def test_unsupported_keys_duplicates_types_and_hashes_rejected(self):
        for change in ({"confidence": "PASS"}, {"batang_schema_version": True},
                       {"tags": "tag"}, {"subject": None}, {"legacy_refs": {}},
                       {"sources": [{"id": "missing-fields"}]}):
            value = metadata()
            value.update(change)
            with self.subTest(change=change), self.assertRaises(ops.FileError):
                ops.serialize_document(value, b"body")
        valid = ops.serialize_document(metadata(), b"body")
        with self.assertRaises(ops.FileError):
            ops.parse_document(valid.replace(b"subject: ", b"subject: \"duplicate\"\nsubject: "))
        with self.assertRaises(ops.FileError):
            ops.parse_document(valid.replace(b'"origin":"user"', b'"origin":"user","origin":"other"'))

    def test_quote_repeated_unicode_explicit_byte_range(self):
        source = "첫 반복 😀\r\n두 반복 😀 e\u0301".encode()
        quote = "반복 😀"
        start = source.rfind(quote.encode())
        self.assertTrue(ops.verify_quote(source, start, start + len(quote.encode()), quote))
        for begin, end, text in ((start, start + 1, quote), (0, len(source) + 1, quote),
                                 (start, start + len(quote.encode()), "반복 😃"),
                                 (False, 4, quote), (0, 1, "")):
            with self.subTest(begin=begin, end=end), self.assertRaises(ops.FileError):
                ops.verify_quote(source, begin, end, text)

    def test_quote_does_not_normalize_combining_characters(self):
        with self.assertRaises(ops.FileError):
            ops.verify_quote("e\u0301".encode(), 0, 3, "é")


class Files(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "Knowledge").mkdir()
        (self.root / "backups").mkdir(mode=0o700)
        self.stage = self.root / ".staging"
        self.stage.mkdir(mode=0o700)
        staging_patch = patch.object(ops.tempfile, "gettempdir", return_value=str(self.stage))
        staging_patch.start()
        self.addCleanup(staging_patch.stop)
        self.scope = ops.FileScope(self.root, ["Knowledge/a.md", "Knowledge/new.md", "ACTIVE.md"])
        self.backups = ops.FileScope(self.root / "backups", ["a.before", "second.before"])
        self.target = self.root / "Knowledge/a.md"
        self.original = ops.serialize_document(metadata(), "\n기존 합성 본문\r\n".encode())
        self.target.write_bytes(self.original)
        self.target.chmod(0o640)

    def test_read_hash_regular_file_and_mode(self):
        value = self.scope.read("Knowledge/a.md")
        self.assertEqual(value.data, self.original)
        self.assertEqual(value.sha256, ops.sha256(self.original))
        self.assertEqual(value.mode, 0o640)

    def test_custom_folder_and_fixture_noop_preserve_file_bytes(self):
        (self.root / "Personal Notes").mkdir()
        target = self.root / "Personal Notes/note.md"
        fixture = (Path(__file__).parent / "fixtures/schema-v1.md").read_bytes()
        target.write_bytes(fixture)
        scope = ops.FileScope(self.root, ["Personal Notes/note.md"])
        original = scope.read("Personal Notes/note.md")
        parsed, body = ops.parse_document(original.data)
        encoded = ops.serialize_document(parsed, body, original=original.data)
        self.assertFalse(scope.write("Personal Notes/note.md", encoded, original.sha256))
        self.assertEqual(target.read_bytes(), fixture)
        self.assertEqual(parsed["batang_schema_version"], 1)
        self.assertEqual(list((self.root / "backups").iterdir()), [])

    def test_exact_path_boundary_and_escape_rejected(self):
        outside = self.root / "outside.md"
        outside.write_bytes(b"untouched")
        for path in ("../outside.md", "Knowledge/../outside.md", "./Knowledge/a.md",
                     "Knowledge//a.md", str(outside), "outside.md", "Knowledge/a.md/", ""):
            with self.subTest(path=path), self.assertRaises(ops.FileError):
                self.scope.read(path)
        self.assertEqual(outside.read_bytes(), b"untouched")

    def test_symlink_leaf_and_parent_rejected(self):
        outside = self.root / "outside.md"
        outside.write_bytes(b"untouched")
        self.target.unlink()
        self.target.symlink_to(outside)
        with self.assertRaises(OSError):
            self.scope.read("Knowledge/a.md")
        with self.assertRaises(OSError):
            self.scope.write("Knowledge/a.md", b"bad")
        self.assertEqual(outside.read_bytes(), b"untouched")
        self.target.unlink()
        (self.root / "Knowledge").rmdir()
        (self.root / "Knowledge").symlink_to(self.root / "backups", target_is_directory=True)
        with self.assertRaises(OSError):
            self.scope.write("Knowledge/new.md", b"bad")
        self.assertEqual(list((self.root / "backups").iterdir()), [])

    def test_root_symlink_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.root / "Knowledge", target_is_directory=True)
        scope = ops.FileScope(alias, ["a.md"])
        with self.assertRaises(OSError):
            scope.read("a.md")

    def test_nonregular_file_rejected(self):
        scope = ops.FileScope(self.root, ["Knowledge"])
        with self.assertRaises(ops.FileError):
            scope.read("Knowledge")

    def test_new_creation_and_collision_without_clobber(self):
        self.assertTrue(self.scope.write("Knowledge/new.md", b"new"))
        new = self.root / "Knowledge/new.md"
        self.assertEqual(new.read_bytes(), b"new")
        self.assertEqual(stat.S_IMODE(new.stat().st_mode), 0o600)
        with self.assertRaises(ops.ConflictError):
            self.scope.write("Knowledge/new.md", b"different")
        self.assertEqual(new.read_bytes(), b"new")

    def test_concurrent_create_is_no_clobber(self):
        real_rename = ops._rename_new_at
        def race(source_parent, source, target_parent, dest):
            (self.root / "Knowledge/new.md").write_bytes(b"external")
            return real_rename(source_parent, source, target_parent, dest)
        with patch.object(ops, "_rename_new_at", side_effect=race), self.assertRaises(FileExistsError):
            self.scope.write("Knowledge/new.md", b"ours")
        self.assertEqual((self.root / "Knowledge/new.md").read_bytes(), b"external")
        temporary, = self.stage.glob(".batang-*.tmp")
        self.assertEqual(temporary.read_bytes(), b"ours")
        self.assertEqual(stat.S_IMODE(self.stage.stat().st_mode), 0o700)

    def test_expected_hash_and_missing_backup_stop_before_writes(self):
        with self.assertRaises(ops.ConflictError):
            self.scope.write("Knowledge/a.md", b"new", "0" * 64,
                             backup_scope=self.backups, backup_path="a.before")
        with self.assertRaises(ops.FileError):
            self.scope.write("Knowledge/a.md", b"new", ops.sha256(self.original))
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(list((self.root / "backups").iterdir()), [])

    def test_changed_write_backup_permissions_and_noop_reapply(self):
        expected = ops.sha256(self.original)
        self.assertTrue(self.scope.write("Knowledge/a.md", b"new", expected,
                                        backup_scope=self.backups, backup_path="a.before"))
        backup = self.root / "backups/a.before"
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertFalse(self.scope.write("Knowledge/a.md", b"new", ops.sha256(b"new")))
        self.assertEqual(len(list((self.root / "backups").iterdir())), 1)

    def test_backup_collision_keeps_original(self):
        (self.root / "backups/a.before").write_bytes(b"existing-backup")
        with self.assertRaises(ops.ConflictError):
            self.scope.write("Knowledge/a.md", b"new", ops.sha256(self.original),
                             backup_scope=self.backups, backup_path="a.before")
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual((self.root / "backups/a.before").read_bytes(), b"existing-backup")

    def test_concurrent_edit_detected_after_temp_preparation(self):
        real_fsync = ops.os.fsync
        def edit(fd):
            self.target.write_bytes(b"external-edit")
            return real_fsync(fd)
        with patch.object(ops.os, "fsync", side_effect=edit), self.assertRaises(ops.ConflictError):
            self.scope.write("Knowledge/a.md", b"ours", ops.sha256(self.original),
                             backup_scope=self.backups, backup_path="a.before")
        self.assertEqual(self.target.read_bytes(), b"external-edit")
        self.assertEqual((self.root / "backups/a.before").read_bytes(), self.original)

    def test_replace_failure_preserves_original_and_private_staged_temp(self):
        with patch.object(ops.os, "replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                self.scope.write("Knowledge/a.md", b"new", ops.sha256(self.original),
                                 backup_scope=self.backups, backup_path="a.before")
        self.assertEqual(self.target.read_bytes(), self.original)
        temporary, = self.stage.glob(".batang-*.tmp")
        self.assertEqual(temporary.read_bytes(), b"new")
        self.assertEqual(stat.S_IMODE(self.stage.stat().st_mode), 0o700)

    def assert_scrubbed_temps(self, directory):
        for temporary in (self.root / directory).glob(".batang-*.tmp"):
            self.assertEqual(temporary.read_bytes(), b"")
            self.assertEqual(stat.S_IMODE(temporary.stat().st_mode), 0o600)

    def test_restore_does_not_overwrite_later_user_edit(self):
        self.scope.write("Knowledge/a.md", b"updated", ops.sha256(self.original),
                         backup_scope=self.backups, backup_path="a.before")
        self.target.write_bytes(b"user-edit")
        with self.assertRaises(ops.ConflictError):
            self.scope.write("Knowledge/a.md", self.original, ops.sha256(b"updated"),
                             backup_scope=self.backups, backup_path="second.before")
        self.assertEqual(self.target.read_bytes(), b"user-edit")

    def test_path_change_keeps_id_and_body_before_explicit_removal(self):
        source = self.scope.read("Knowledge/a.md")
        self.scope.write("Knowledge/new.md", source.data)
        old_meta, old_body = ops.parse_document(source.data)
        new_meta, new_body = ops.parse_document(self.scope.read("Knowledge/new.md").data)
        self.assertEqual(new_meta["batang_id"], old_meta["batang_id"])
        self.assertEqual(new_body, old_body)
        # 삭제 권한은 helper가 만들지 않는다. 호스트가 명시 대상/hash를 확인한다.
        self.assertEqual(self.scope.read("Knowledge/a.md").sha256, source.sha256)
        self.target.unlink()
        self.assertFalse(self.target.exists())
        self.assertTrue((self.root / "Knowledge/new.md").exists())


class MacOSACL(unittest.TestCase):
    """실제 Darwin ACL이 필수다. 도구·권한 부재를 skip/PASS로 바꾸지 않는다."""

    @classmethod
    def setUpClass(cls):
        if sys.platform != "darwin":
            raise RuntimeError("required_macos_acl_tests_need_darwin")
        subprocess.run(["/usr/bin/id", "-u", "_www"], check=True, capture_output=True)

    def setUp(self):
        Files.setUp(self)
        self.acl = ops._MacOSACL()
        self.updated = b"new-private-data"

    def add_acl(self, path, entry):
        subprocess.run(["/bin/chmod", "+a", entry, str(path)],
                       check=True, capture_output=True)

    def read_acl(self, path):
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            return self.acl.read(fd)
        finally:
            os.close(fd)

    def text_acl(self, path):
        result = subprocess.run(["/bin/ls", "-lde", str(path)],
                                check=True, capture_output=True)
        return result.stdout.splitlines()[1:]

    def update(self):
        return self.scope.write("Knowledge/a.md", self.updated, ops.sha256(self.original),
                                backup_scope=self.backups, backup_path="a.before")

    def assert_original(self, before, acl):
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(ops._identity(self.target.stat()), ops._identity(before))
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertEqual(self.read_acl(self.target), acl)
        Files.assert_scrubbed_temps(self, ".staging")

    def test_deny_allow_order_flags_and_backup_bytes_preserved(self):
        self.add_acl(self.target, "user:_www deny read")
        self.add_acl(self.target, "user:_www allow readattr,readextattr")
        before_acl = self.read_acl(self.target)
        before_text = self.text_acl(self.target)
        before_inode = self.target.stat().st_ino
        self.assertNotEqual(before_acl, self.acl.empty)
        self.assertIn(b"deny read", b"\n".join(before_text))
        # 백업에도 상속 허용 ACL이 남지 않아야 한다.
        self.add_acl(self.root / "backups", "user:_www allow read,file_inherit,directory_inherit")
        self.assertTrue(self.update())
        self.assertEqual(self.target.read_bytes(), self.updated)
        self.assertNotEqual(self.target.stat().st_ino, before_inode)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertEqual(self.read_acl(self.target), before_acl)
        self.assertEqual(self.text_acl(self.target), before_text)
        backup = self.root / "backups/a.before"
        self.assertEqual(backup.read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o600)
        self.assertEqual(self.read_acl(backup), self.acl.empty)

    def test_acl_noop_keeps_inode_ctime_and_needs_no_backup(self):
        self.add_acl(self.target, "user:_www deny read")
        before, before_acl = self.target.stat(), self.read_acl(self.target)
        with patch.object(ops, "_MacOSACL", side_effect=AssertionError("noop_acl_write")):
            self.assertFalse(self.scope.write("Knowledge/a.md", self.original,
                                              ops.sha256(self.original)))
        self.assert_original(before, before_acl)
        self.assertEqual(list((self.root / "backups").iterdir()), [])

    def test_inherited_source_flags_survive_and_acl_precedes_final_mode(self):
        self.add_acl(self.root / "Knowledge", "user:_www allow read,file_inherit,directory_inherit")
        self.target.unlink()
        self.target.write_bytes(self.original)
        self.target.chmod(0o640)
        before_acl, before_text = self.read_acl(self.target), self.text_acl(self.target)
        self.assertIn(b"inherited", b"\n".join(before_text))
        real_apply, real_fchmod = ops._MacOSACL.apply, ops.os.fchmod
        restored = []

        def apply(instance, fd, value):
            if os.fstat(fd).st_size == len(self.updated):
                self.assertEqual(stat.S_IMODE(os.fstat(fd).st_mode), 0o600)
                self.assertEqual(instance.read(fd), instance.empty)
                restored.append(True)
            return real_apply(instance, fd, value)

        def fchmod(fd, mode):
            if mode == 0o640:
                self.assertEqual(os.fstat(fd).st_size, len(self.updated))
                self.assertEqual(self.acl.read(fd), before_acl)
            return real_fchmod(fd, mode)

        with patch.object(ops._MacOSACL, "apply", new=apply), patch.object(ops.os, "fchmod", new=fchmod):
            self.assertTrue(self.update())
        self.assertEqual(restored, [True])
        self.assertEqual(self.read_acl(self.target), before_acl)
        self.assertEqual(self.text_acl(self.target), before_text)

    def test_empty_original_uses_private_stage_before_bytes(self):
        self.assertEqual(self.read_acl(self.target), self.acl.empty)
        self.add_acl(self.root / "Knowledge", "user:_www allow read,file_inherit,directory_inherit")
        observed_inherited = []
        observed_stream = []
        real_apply, real_fdopen = ops._MacOSACL.apply, ops.os.fdopen

        def apply(instance, fd, value):
            if os.fstat(fd).st_size == 0:
                observed_inherited.append(instance.read(fd) != instance.empty)
            return real_apply(instance, fd, value)

        def fdopen(fd, mode, **kwargs):
            if mode == "wb":
                observed_stream.append(True)
                self.assertEqual(os.fstat(fd).st_size, 0)
                self.assertEqual(stat.S_IMODE(os.fstat(fd).st_mode), 0o600)
                self.assertEqual(self.acl.read(fd), self.acl.empty)
            return real_fdopen(fd, mode, **kwargs)

        with patch.object(ops._MacOSACL, "apply", new=apply), patch.object(ops.os, "fdopen", new=fdopen):
            self.assertTrue(self.update())
        self.assertTrue(observed_inherited)
        self.assertTrue(all(not value for value in observed_inherited))
        self.assertEqual(len(observed_stream), 2)
        self.assertEqual(self.read_acl(self.target), self.acl.empty)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)

    def test_new_file_has_empty_acl_and_0600_despite_directory_inheritance(self):
        self.add_acl(self.root / "Knowledge", "user:_www allow read,file_inherit,directory_inherit")
        real_fdopen = ops.os.fdopen
        observed = []

        def fdopen(fd, mode, **kwargs):
            if mode == "wb":
                observed.append(True)
                self.assertEqual(os.fstat(fd).st_size, 0)
                self.assertEqual(stat.S_IMODE(os.fstat(fd).st_mode), 0o600)
                self.assertEqual(self.acl.read(fd), self.acl.empty)
            return real_fdopen(fd, mode, **kwargs)

        with patch.object(ops.os, "fdopen", new=fdopen):
            self.assertTrue(self.scope.write("Knowledge/new.md", self.updated))
        self.assertEqual(observed, [True])
        new = self.root / "Knowledge/new.md"
        self.assertEqual(new.read_bytes(), self.updated)
        self.assertEqual(stat.S_IMODE(new.stat().st_mode), 0o600)
        self.assertEqual(self.read_acl(new), self.acl.empty)
        self.assertEqual(self.text_acl(new), [])

    def test_acl_query_enoent_is_empty_but_other_errors_preserve_original(self):
        self.add_acl(self.target, "user:_www deny read")
        before, before_acl = self.target.stat(), self.read_acl(self.target)

        def fail(fd, acl_type):
            self.assertEqual(acl_type, 0x100)
            ctypes.set_errno(errno.EACCES)
            return None

        with patch.object(ops, "_MacOSACL", return_value=self.acl):
            with patch.object(self.acl.lib, "acl_get_fd_np", side_effect=fail):
                with self.assertRaises(OSError) as error:
                    self.update()
            self.assertEqual(error.exception.errno, errno.EACCES)
        self.assert_original(before, before_acl)
        self.assertEqual(list((self.root / "backups").iterdir()), [])
        self.assertEqual(self.read_acl(self.root / "Knowledge"), self.acl.empty)

    def test_inherited_acl_clear_verification_fails_before_sensitive_bytes(self):
        self.add_acl(self.root / "Knowledge", "user:_www allow read,file_inherit,directory_inherit")
        real_fdopen = ops.os.fdopen
        real_read = self.acl.read

        def fdopen(fd, mode, **kwargs):
            self.assertNotEqual(mode, "wb", "ACL 확인 실패 전에 bytes 쓰기를 시작함")
            return real_fdopen(fd, mode, **kwargs)

        def wrong(fd):
            if stat.S_ISREG(os.fstat(fd).st_mode) and os.fstat(fd).st_size == 0:
                return b"synthetic-acl-mismatch"
            return real_read(fd)

        with patch.object(ops, "_MacOSACL", return_value=self.acl):
            with patch.object(self.acl, "read", side_effect=wrong):
                with patch.object(ops.os, "fdopen", new=fdopen):
                    with self.assertRaisesRegex(ops.FileError, "acl_verification"):
                        self.scope.write("Knowledge/new.md", self.updated)
        self.assertFalse((self.root / "Knowledge/new.md").exists())
        Files.assert_scrubbed_temps(self, ".staging")

    def test_private_stage_with_access_acl_is_rejected_before_write(self):
        self.add_acl(self.stage, "user:_www allow read,search")
        with self.assertRaisesRegex(ops.FileError, "private_staging_unavailable"):
            self.scope.write("Knowledge/new.md", self.updated)
        self.assertFalse((self.root / "Knowledge/new.md").exists())
        self.assertFalse(list(self.stage.glob(".batang-*.tmp")))

    def test_allocated_acl_is_freed_on_serialization_and_set_errors(self):
        self.add_acl(self.target, "user:_www deny read")
        fd = os.open(self.target, os.O_RDONLY | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        real_free = self.acl.lib.acl_free

        def fail(*args):
            ctypes.set_errno(errno.EIO)
            return -1

        for operation in ("acl_size", "acl_copy_ext", "acl_set_fd_np"):
            with self.subTest(operation=operation):
                with patch.object(self.acl.lib, "acl_free", wraps=real_free) as free:
                    with patch.object(self.acl.lib, operation, side_effect=fail):
                        with self.assertRaises(OSError) as error:
                            if operation == "acl_set_fd_np":
                                self.acl.apply(fd, self.acl.empty)
                            else:
                                self.acl.read(fd)
                    self.assertEqual(error.exception.errno, errno.EIO)
                    free.assert_called_once()
                    self.assertTrue(free.call_args.args[0])

    def test_acl_set_failures_never_fallback_and_keep_completed_backup(self):
        self.add_acl(self.target, "user:_www deny read")
        before, before_acl = self.target.stat(), self.read_acl(self.target)
        real_set = self.acl.lib.acl_set_fd_np
        # 백업 ACL 제거, 본문 임시 ACL 제거, 원본 ACL 복원 각각의 실패를 확인한다.
        for failure_call in (1, 2, 3):
            with self.subTest(failure_call=failure_call):
                calls = []

                def fail(fd, value, acl_type):
                    calls.append(fd)
                    if len(calls) == failure_call:
                        ctypes.set_errno(errno.EPERM)
                        return -1
                    return real_set(fd, value, acl_type)

                with patch.object(ops, "_MacOSACL", return_value=self.acl):
                    with patch.object(self.acl.lib, "acl_set_fd_np", side_effect=fail):
                        with self.assertRaises(OSError) as error:
                            self.update()
                    self.assertEqual(error.exception.errno, errno.EPERM)
                self.assert_original(before, before_acl)
                backup = self.root / "backups/a.before"
                if failure_call > 1:
                    self.assertEqual(backup.read_bytes(), self.original)
                    self.assertEqual(self.read_acl(backup), self.acl.empty)
                    backup.unlink()
                else:
                    self.assertFalse(backup.exists())

    def test_acl_verification_mismatch_preserves_original(self):
        self.add_acl(self.target, "user:_www deny read")
        before, before_acl = self.target.stat(), self.read_acl(self.target)
        real_read = self.acl.read

        def wrong(fd):
            value = real_read(fd)
            if os.fstat(fd).st_size == len(self.updated):
                return self.acl.empty
            return value

        with patch.object(ops, "_MacOSACL", return_value=self.acl):
            with patch.object(self.acl, "read", side_effect=wrong):
                with self.assertRaisesRegex(ops.FileError, "acl_verification"):
                    self.update()
        self.assert_original(before, before_acl)
        self.assertEqual((self.root / "backups/a.before").read_bytes(), self.original)

    def test_acl_query_failure_after_bytes_preserves_original_and_backup(self):
        self.add_acl(self.target, "user:_www deny read")
        before, before_acl = self.target.stat(), self.read_acl(self.target)
        real_get = self.acl.lib.acl_get_fd_np

        def fail(fd, acl_type):
            if os.fstat(fd).st_size == len(self.updated):
                ctypes.set_errno(errno.EIO)
                return None
            return real_get(fd, acl_type)

        with patch.object(ops, "_MacOSACL", return_value=self.acl):
            with patch.object(self.acl.lib, "acl_get_fd_np", side_effect=fail):
                with self.assertRaises(OSError) as error:
                    self.update()
            self.assertEqual(error.exception.errno, errno.EIO)
        self.assert_original(before, before_acl)
        self.assertEqual((self.root / "backups/a.before").read_bytes(), self.original)

    def test_acl_only_concurrent_edit_is_a_conflict(self):
        self.add_acl(self.target, "user:_www deny read")
        old_acl = self.read_acl(self.target)
        real_fsync = ops.os.fsync
        edited = []

        def race(fd):
            if os.fstat(fd).st_size == len(self.updated):
                self.add_acl(self.target, "user:_www allow readattr")
                edited.append(True)
            return real_fsync(fd)

        with patch.object(ops.os, "fsync", side_effect=race), self.assertRaises(ops.ConflictError):
            self.update()
        self.assertEqual(edited, [True])
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)
        self.assertNotEqual(self.read_acl(self.target), old_acl)
        self.assertEqual((self.root / "backups/a.before").read_bytes(), self.original)
        Files.assert_scrubbed_temps(self, ".staging")

    def test_same_bytes_replacement_inode_is_a_conflict(self):
        before = self.target.stat()
        real_fsync = ops.os.fsync
        replacement_inode = []

        def race(fd):
            if os.fstat(fd).st_size == len(self.updated):
                other = self.root / "replacement.md"
                other.write_bytes(self.original)
                other.chmod(0o640)
                os.utime(other, ns=(before.st_atime_ns, before.st_mtime_ns))
                replacement_inode.append(other.stat().st_ino)
                os.replace(other, self.target)
            return real_fsync(fd)

        with patch.object(ops.os, "fsync", side_effect=race), self.assertRaises(ops.ConflictError):
            self.update()
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.target.stat().st_ino, replacement_inode[0])
        self.assertNotEqual(self.target.stat().st_ino, before.st_ino)
        Files.assert_scrubbed_temps(self, ".staging")

    def test_acl_changed_and_restored_still_conflicts_by_ctime(self):
        self.add_acl(self.target, "user:_www deny read")
        before, before_acl = self.target.stat(), self.read_acl(self.target)
        real_fsync = ops.os.fsync

        def race(fd):
            if os.fstat(fd).st_size == len(self.updated):
                self.add_acl(self.target, "user:_www allow readattr")
                subprocess.run(["/bin/chmod", "-a#", "1", str(self.target)],
                               check=True, capture_output=True)
            return real_fsync(fd)

        with patch.object(ops.os, "fsync", side_effect=race), self.assertRaises(ops.ConflictError):
            self.update()
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(self.read_acl(self.target), before_acl)
        self.assertNotEqual(self.target.stat().st_ctime_ns, before.st_ctime_ns)
        Files.assert_scrubbed_temps(self, ".staging")

    def test_temp_mode_changed_after_acl_preparation_blocks_publication(self):
        before, before_acl = self.target.stat(), self.read_acl(self.target)
        real_fsync = ops.os.fsync

        def race(fd):
            if os.fstat(fd).st_size == len(self.updated):
                os.fchmod(fd, 0o666)
            return real_fsync(fd)

        with patch.object(ops.os, "fsync", side_effect=race):
            with self.assertRaisesRegex(ops.ConflictError, "changed_temporary_mode"):
                self.update()
        self.assert_original(before, before_acl)

    def test_temporary_content_change_before_publication_is_rejected(self):
        before, before_acl = self.target.stat(), self.read_acl(self.target)
        real_fsync = ops.os.fsync
        changed = []

        def race(fd):
            if os.fstat(fd).st_size == len(self.updated):
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, b"X" * len(self.updated))
                changed.append(True)
            return real_fsync(fd)

        with patch.object(ops.os, "fsync", side_effect=race):
            with self.assertRaisesRegex(ops.ConflictError, "changed_temporary_contents"):
                self.update()
        self.assertEqual(changed, [True])
        self.assert_original(before, before_acl)
        self.assertEqual((self.root / "backups/a.before").read_bytes(), self.original)

    def test_substituted_temporary_is_neither_published_nor_deleted(self):
        before, before_acl = self.target.stat(), self.read_acl(self.target)
        real_fsync = ops.os.fsync
        foreign = []

        def race(fd):
            if os.fstat(fd).st_size == len(self.updated):
                temporary, = self.stage.glob(".batang-*.tmp")
                temporary.rename(self.root / "detached-owned-temp")
                temporary.write_bytes(b"other-writer")
                foreign.append(temporary)
            return real_fsync(fd)

        with patch.object(ops.os, "fsync", side_effect=race), self.assertRaises(ops.ConflictError):
            self.update()
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(ops._identity(self.target.stat()), ops._identity(before))
        self.assertEqual(self.read_acl(self.target), before_acl)
        self.assertEqual(len(foreign), 1)
        self.assertEqual(foreign[0].read_bytes(), b"other-writer")

    def test_replace_failure_never_unlinks_substituted_temporary(self):
        foreign = []

        def race(source, destination, **kwargs):
            temporary, = self.stage.glob(".batang-*.tmp")
            detached = self.root / "detached-owned-temp"
            temporary.rename(detached)
            temporary.write_bytes(b"other-writer")
            foreign.append(temporary)
            raise OSError("synthetic replacement failure")

        with patch.object(ops.os, "replace", side_effect=race):
            with patch.object(ops.os, "unlink", side_effect=AssertionError("foreign unlink")):
                with self.assertRaises(OSError):
                    self.update()
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(len(foreign), 1)
        self.assertEqual(foreign[0].read_bytes(), b"other-writer")
        detached = self.root / "detached-owned-temp"
        self.assertEqual(detached.read_bytes(), self.updated)

    def test_interrupt_after_new_publication_keeps_published_bytes(self):
        real_rename = ops._rename_new_at

        def interrupted(*args):
            real_rename(*args)
            raise KeyboardInterrupt("after publication")

        with patch.object(ops, "_rename_new_at", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.scope.write("Knowledge/new.md", self.updated)
        self.assertEqual((self.root / "Knowledge/new.md").read_bytes(), self.updated)
        self.assertFalse(list(self.stage.glob(".batang-*.tmp")))

    def test_interrupt_after_existing_publication_keeps_published_bytes_and_acl(self):
        self.add_acl(self.target, "user:_www deny read")
        before_acl = self.read_acl(self.target)
        real_replace = ops.os.replace

        def interrupted(*args, **kwargs):
            real_replace(*args, **kwargs)
            raise KeyboardInterrupt("after publication")

        with patch.object(ops.os, "replace", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.update()
        self.assertEqual(self.target.read_bytes(), self.updated)
        self.assertEqual(self.read_acl(self.target), before_acl)
        self.assertEqual((self.root / "backups/a.before").read_bytes(), self.original)
        self.assertFalse(list(self.stage.glob(".batang-*.tmp")))

    def test_exclusive_temp_collision_never_deletes_other_file(self):
        temporary = self.stage / ".batang-collision.tmp"
        temporary.write_bytes(b"other-writer")
        fake_uuid = unittest.mock.Mock(hex="collision")
        with patch.object(ops.uuid, "uuid4", return_value=fake_uuid), self.assertRaises(FileExistsError):
            self.scope.write("Knowledge/new.md", self.updated)
        self.assertEqual(temporary.read_bytes(), b"other-writer")
        self.assertFalse((self.root / "Knowledge/new.md").exists())


if __name__ == "__main__":
    unittest.main()
