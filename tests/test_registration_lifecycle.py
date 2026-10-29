"""등록 실패·그래프 대기·재개와 원본 검사를 합성 자료로 확인한다."""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

from test_graph_ops import GRAPHIFY, GraphFixture, chunks_for, files, note, ops


class RegistrationBase(GraphFixture):
    def empty_index(self):
        (self.vault / "ACTIVE.md").write_bytes(b"")
        return self.note_scope.read("ACTIVE.md").sha256

    def registration_args(self, expected):
        return {"expected_active_sha256": expected,
                "backup_scope": files.FileScope(str(self.backups), ["active-before.md"]),
                "backup_path": "active-before.md"}


class Registration(RegistrationBase):

    def test_registration_idempotence_and_no_silent_missing_file(self):
        expected = self.empty_index()
        active = ops.register_documents(self.note_scope, "ACTIVE.md", ["one.md"],
                                        **self.registration_args(expected))
        self.assertEqual([doc.path for doc in active.documents], ["one.md"])
        saved = self.note_scope.read("ACTIVE.md")
        again = ops.register_documents(self.note_scope, "ACTIVE.md", ["one.md"],
                                       expected_active_sha256=saved.sha256)
        self.assertEqual(self.note_scope.read("ACTIVE.md").data, saved.data)
        self.assertEqual(again.active_sha256, saved.sha256)
        with self.assertRaises((files.FileError, FileNotFoundError)):
            ops.register_documents(self.note_scope, "ACTIVE.md", ["outside.md"],
                                   expected_active_sha256=saved.sha256)
        self.assertEqual(self.note_scope.read("ACTIVE.md").data, saved.data)

    def test_import_source_binding_and_source_revalidation_precede_registration(self):
        expected = self.empty_index()
        source = self.root / "source"
        source.mkdir(mode=0o700)
        (source / "original.md").write_bytes(b"# original\nsource content\n")
        source_scope = files.FileScope(str(source), ["original.md"])
        result = files.prepare_import(source_scope, "original.md", self.note_scope, "outside.md")
        # 기존 reader와 신규 backend 모두에서 등록 전 binding 검증을 확인한다.
        values = dict(vars(result))
        values["source_root_binding"] = {"source-root": str(source)}
        result = SimpleNamespace(**values)
        args = self.registration_args(expected)
        args.update(import_results=[result], source_scopes=[source_scope])
        with self.assertRaisesRegex(ops.GraphError, "registration_source_binding_missing"):
            ops.register_documents(self.note_scope, "ACTIVE.md", ["outside.md"], **args)
        self.assertEqual(self.note_scope.read("ACTIVE.md").sha256, expected)
        (source / "original.md").write_bytes(b"changed original\n")
        with self.assertRaises(files.FileError):
            ops.register_documents(self.note_scope, "ACTIVE.md", ["outside.md"],
                                   source_roots={"source-root": str(source)}, **args)
        self.assertEqual(self.note_scope.read("ACTIVE.md").sha256, expected)

    def test_no_active_list_change_when_duplicate_document_id_is_found(self):
        before = self.note_scope.read("ACTIVE.md")
        (self.vault / "outside.md").write_bytes(note("one"))
        with self.assertRaisesRegex(ops.GraphError, "active_document_id_collision"):
            ops.register_documents(self.note_scope, "ACTIVE.md", ["outside.md"],
                                   expected_active_sha256=before.sha256)
        self.assertEqual(self.note_scope.read("ACTIVE.md").data, before.data)


@unittest.skipUnless(GRAPHIFY and sys.platform == "darwin", "실제 Graphify와 macOS 저장 도우미 필요")
class Lifecycle(RegistrationBase):
    def graph_arguments_before_registration(self):
        active = self.active(["one.md"])
        arguments = self.arguments(active)
        return active, arguments

    def test_failed_graph_allows_note_query_then_resumes_without_duplicate_registration(self):
        active, graph = self.graph_arguments_before_registration()
        expected = self.empty_index()
        graph["chunks"] = []
        outcome = ops.registration_lifecycle(self.note_scope, "ACTIVE.md", ["one.md"],
                    registration=self.registration_args(expected), graph=graph)
        self.assertEqual((outcome.notes_status, outcome.graph_status), ("registered", "pending"))
        self.assertTrue(outcome.graph.note_query_allowed)
        self.assertEqual(self.note_scope.read("one.md").sha256, active.documents[0].sha256)
        index = self.note_scope.read("ACTIVE.md")
        before_node = (self.vault / "one.md").stat().st_ino
        resumed_active = self.active(["one.md"])
        resumed = ops.resume_registration(self.note_scope, "ACTIVE.md", ["one.md"],
                                           **self.arguments(resumed_active))
        self.assertEqual(resumed.graph_status, "current", resumed)
        self.assertEqual(self.note_scope.read("ACTIVE.md").data, index.data)
        self.assertEqual((self.vault / "one.md").stat().st_ino, before_node)
        self.assertEqual(len(ops._active_paths(index.data)), 1)

    def test_read_only_resume_does_not_write_graph_active_or_notes(self):
        active = self.active(["one.md"])
        before = {path.name: path.read_bytes() for path in self.vault.iterdir()}
        result = ops.resume_registration(self.note_scope, "ACTIVE.md", ["one.md"],
                                         read_only=True, **self.arguments(active))
        self.assertEqual(result.graph_status, "pending")
        self.assertEqual(result.graph.error_code, "read_only")
        self.assertFalse(list(self.work.iterdir()))
        self.assertFalse((self.root / "graph.json").exists())
        self.assertEqual({path.name: path.read_bytes() for path in self.vault.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()
