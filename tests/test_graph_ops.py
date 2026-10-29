"""합성 활성 노트와 실제 Graphify의 저장·실패 경계를 검사한다."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/batang/scripts"
sys.path.insert(0, str(SCRIPTS))
import file_ops as files
import graph_ops as ops

GRAPHIFY = importlib.util.find_spec("graphify") is not None


def note(identifier, *, subject=None, aliases=()):
    value = {"batang_schema_version": 2, "batang_id": identifier,
             "subject": subject or identifier, "content_kind": "note", "tags": ["검증"],
             "sources": [{"id": "source-" + identifier, "path": None, "origin": "user",
                          "sha256": None, "raw_path": None}], "legacy_refs": []}
    if aliases:
        value["aliases"] = list(aliases)
    return files.serialize_document(value, ("# " + identifier + "\n본문\n").encode())


def chunks_for(active, *, suffix="fact", empty=False):
    nodes = {node["source_file"]: node for node in ops.document_nodes(active)}
    result = []
    for doc in active.documents:
        provenance = {"source_file": doc.path, "document_id": doc.document_id,
                      "source_sha256": doc.sha256, "source_location": "L11",
                      "confidence": "EXTRACTED", "_origin": "semantic"}
        concept = {"id": doc.document_id + "_" + suffix, "label": suffix,
                   "file_type": "concept", "node_role": "fact", **provenance}
        edge = {"source": nodes[doc.path]["id"], "target": concept["id"],
                "relation": "mentions", **provenance}
        result.append({"chunk_id": doc.path + "::1", "source_file": doc.path,
                       "document_id": doc.document_id, "source_sha256": doc.sha256,
                       "nodes": [] if empty else [concept], "edges": [] if empty else [edge]})
    return result


class GraphFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="graph-ops-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.vault = self.root / "vault"
        self.work = self.root / "work"
        self.backups = self.root / "backups"
        for path in (self.vault, self.work, self.backups):
            path.mkdir(mode=0o700)
        self.paths = ("one.md", "two.md")
        for path, identifier in zip(self.paths, ("one", "two")):
            (self.vault / path).write_bytes(note(identifier, subject="같은 제목", aliases=("같은 별칭",)))
        (self.vault / "ACTIVE.md").write_bytes(b"- [one](one.md)\n- [two](two.md)\n")
        self.note_scope = files.FileScope(str(self.vault), ["ACTIVE.md", *self.paths, "outside.md"])
        self.graph_scope = files.FileScope(str(self.root), ["graph.json"])
        self.counter = 0

    def active(self, selected=None):
        return ops.read_active_documents(self.note_scope, "ACTIVE.md", selected)

    def arguments(self, active, *, chunks=None, expected_hash=None):
        self.counter += 1
        baseline = f"baseline-{self.counter}.json"
        candidate = f"candidate-{self.counter}.json"
        backup = f"backup-{self.counter}.json"
        return {"chunks": chunks_for(active) if chunks is None else chunks,
                "expected_chunk_ids": {doc.path: [doc.path + "::1"] for doc in active.documents},
                "graph_scope": self.graph_scope, "graph_path": "graph.json",
                "expected_graph_sha256": expected_hash,
                "work_scope": files.FileScope(str(self.work), [baseline, candidate]),
                "baseline_path": baseline, "candidate_path": candidate,
                "backup_scope": files.FileScope(str(self.backups), [backup]), "backup_path": backup}


class ScopeAndCoverage(GraphFixture):
    def test_active_selection_never_reads_unlisted_or_unallowed_note(self):
        (self.vault / "outside.md").write_bytes(note("outside"))
        with self.assertRaisesRegex(ops.GraphError, "active_selection_invalid"):
            self.active(["outside.md"])
        narrow = files.FileScope(str(self.vault), ["ACTIVE.md", "one.md"])
        with self.assertRaises(files.FileError):
            ops.read_active_documents(narrow, "ACTIVE.md")
        one = ops.read_active_documents(narrow, "ACTIVE.md", ["one.md"])
        self.assertEqual([doc.path for doc in one.documents], ["one.md"])

    def test_coverage_distinguishes_missing_stale_invalid_and_duplicate_names(self):
        active = self.active()
        self.assertEqual([item["status"] for item in ops.graph_coverage(active)], ["missing", "missing"])
        graph = {"nodes": ops.document_nodes(active), "links": []}
        self.assertEqual([item["status"] for item in ops.graph_coverage(active, graph)], ["current", "current"])
        self.assertEqual(len({node["id"] for node in graph["nodes"]}), 2)
        graph["nodes"][0]["source_sha256"] = "0" * 64
        self.assertEqual(ops.graph_coverage(active, graph)[0]["status"], "stale")
        graph["nodes"].append(dict(graph["nodes"][1], id="duplicate"))
        self.assertEqual(ops.graph_coverage(active, graph)[1]["status"], "invalid")
        self.assertEqual(ops.graph_coverage(active, b"not-json")[0]["status"], "invalid")

    def test_active_duplicate_id_is_rejected(self):
        (self.vault / "two.md").write_bytes(note("one"))
        with self.assertRaisesRegex(ops.GraphError, "active_document_id_collision"):
            self.active()

    def test_malformed_endpoint_has_invalid_coverage_and_workspace_cannot_alias_graph(self):
        active = self.active()
        graph = {"nodes": ops.document_nodes(active),
                 "links": [{"source": ["bad"], "target": "bad"}]}
        self.assertEqual(ops.graph_coverage(active, graph)[0]["status"], "invalid")
        args = self.arguments(active)
        args["work_scope"] = self.graph_scope
        args["baseline_path"] = "graph.json"
        result = ops.refresh_graph(active, **args)
        self.assertEqual(result.error_code, "graph_work_path_collision")
        self.assertFalse((self.root / "graph.json").exists())

    def test_read_only_does_not_create_work_files_or_graph(self):
        active = self.active()
        args = self.arguments(active)
        result = ops.refresh_graph(active, read_only=True, **args)
        self.assertEqual((result.status, result.error_code), ("pending", "read_only"))
        self.assertFalse(list(self.work.iterdir()))
        self.assertFalse((self.root / "graph.json").exists())


@unittest.skipUnless(GRAPHIFY and sys.platform == "darwin", "실제 Graphify와 macOS 저장 도우미 필요")
class RealGraphify(GraphFixture):
    def test_absolute_provenance_never_triggers_file_or_metadata_lookup(self):
        # 도구 import는 검사 전에 끝내고 실제 build 호출의 파일 접근만 관찰한다.
        import graphify.build
        import graphify.dedup
        old = {"directed": False, "multigraph": False, "graph": {"retained": "value"},
               "nodes": [
                   {"id": "outside_a", "label": "Outside A", "file_type": "code",
                    "source_file": "/synthetic-unselected/shortcut.md",
                    "definition_file": "/synthetic-unselected/definition.md",
                    "_origin": "ast", "source_location": "L1"},
                   {"id": "outside_b", "label": "Outside B", "file_type": "code",
                    "source_file": "other.md", "_origin": "ast", "source_location": "L2"},
                   {"id": "same_source_ast", "label": "Same source AST", "file_type": "code",
                    "source_file": "one.md", "_origin": "ast", "source_location": "L1"},
                   {"id": "obsolete_semantic", "label": "Old semantic", "file_type": "concept",
                    "source_file": "one.md", "_origin": "semantic", "source_location": "text"}],
               "links": [
                   {"source": "outside_a", "target": "outside_b", "relation": "mentions",
                    "confidence": "EXTRACTED", "source_file": "/synthetic-unselected/edge.md",
                    "definition_file": "/synthetic-unselected/edge-definition.md",
                    "_origin": "ast", "source_location": "L1"},
                   {"source": "same_source_ast", "target": "outside_b", "relation": "mentions",
                    "confidence": "EXTRACTED", "source_file": "one.md",
                    "_origin": "ast", "source_location": "L1"},
                   {"source": "obsolete_semantic", "target": "outside_b", "relation": "mentions",
                    "confidence": "EXTRACTED", "source_file": "one.md",
                    "_origin": "semantic", "source_location": "text"}]}
        prepared = [{"nodes": [{"id": "fresh_semantic", "label": "New semantic",
                                  "file_type": "concept", "source_file": "one.md",
                                  "_origin": "semantic", "source_location": "text"}], "edges": []}]
        events = []

        def forbidden(operation):
            def invoked(*args, **kwargs):
                events.append(operation)
                raise AssertionError("파일 또는 메타데이터 접근이 허용되지 않음")
            return invoked

        with patch("os.stat", forbidden("stat")), patch("os.lstat", forbidden("lstat")), \
                patch("os.readlink", forbidden("readlink")), \
                patch("os.open", forbidden("os.open")), patch("builtins.open", forbidden("open")), \
                patch.object(Path, "read_text", forbidden("read_text")), \
                patch.object(Path, "read_bytes", forbidden("read_bytes")):
            # 이전 내부 인자를 주어도 upstream 경로 해석으로 전달하지 않는다.
            graph = ops._build_from_snapshot(copy.deepcopy(old), prepared, {"one.md"},
                                              "/synthetic-selected")
        self.assertEqual(events, [])
        import networkx as nx
        saved = ops._graph_data(nx.node_link_data(graph, edges="links"))
        ops._preserved(old, saved, {"one.md"})
        nodes = {item["id"]: item for item in saved["nodes"]}
        self.assertNotIn("obsolete_semantic", nodes)
        self.assertIn("fresh_semantic", nodes)
        self.assertIn("same_source_ast", nodes)
        self.assertEqual(nodes["outside_a"]["source_file"], "/synthetic-unselected/shortcut.md")
        self.assertEqual(nodes["outside_a"]["definition_file"], "/synthetic-unselected/definition.md")
        self.assertEqual(len(saved["links"]), 2)
        self.assertEqual(saved["graph"]["retained"], "value")

    def test_tier_contract_matches_installed_graphify_legacy_cases(self):
        from graphify.build import _is_ast_tier
        for item in ({}, {"_origin": "ast"}, {"_origin": "semantic", "source_location": "L1"},
                     {"source_location": "L1"}, {"source_location": "L12-L18"},
                     {"source_location": "L1:3"}, {"source_location": None},
                     {"source_location": "document"}):
            with self.subTest(item=item):
                self.assertEqual(ops._ast_tier(item), _is_ast_tier(item))

    def test_first_graph_saved_and_reloaded_including_isolated_document(self):
        active = self.active()
        chunks = chunks_for(active)
        chunks[1]["nodes"] = []
        chunks[1]["edges"] = []
        result = ops.refresh_graph(active, **self.arguments(active, chunks=chunks))
        self.assertEqual(result.status, "current", result)
        self.assertTrue(result.graph_written)
        self.assertTrue(result.note_query_allowed)
        saved = self.graph_scope.read("graph.json")
        graph = json.loads(saved.data)
        self.assertEqual((len(graph["nodes"]), len(graph["links"])), (3, 1))
        self.assertEqual(result.graph_sha256, saved.sha256)
        self.assertEqual([item["status"] for item in result.coverage], ["current", "current"])
        self.assertEqual(len(list(self.work.iterdir())), 2)

    def test_partial_malformed_stale_and_unknown_endpoint_preserve_old_graph(self):
        active = self.active()
        first = ops.refresh_graph(active, **self.arguments(active))
        self.assertEqual(first.status, "current", first)
        original = self.graph_scope.read("graph.json")
        invalid = [chunks_for(active)[:1], b"not-json"]
        stale = chunks_for(active)
        stale[0]["source_sha256"] = "0" * 64
        invalid.append(stale)
        endpoint = chunks_for(active)
        endpoint[0]["edges"][0]["target"] = "not-allowed-node"
        invalid.append(endpoint)
        for chunks in invalid:
            with self.subTest(chunks=type(chunks).__name__):
                result = ops.refresh_graph(active, **self.arguments(
                    active, chunks=chunks, expected_hash=original.sha256))
                self.assertEqual(result.status, "pending")
                self.assertFalse(result.graph_written)
                self.assertFalse(result.publication_uncertain)
                self.assertEqual(self.graph_scope.read("graph.json").data, original.data)

    def test_refresh_removes_reextracted_relation_and_preserves_untouched_source(self):
        active = self.active()
        first = ops.refresh_graph(active, **self.arguments(active))
        self.assertEqual(first.status, "current", first)
        before = self.graph_scope.read("graph.json")
        selected = self.active(["one.md"])
        result = ops.refresh_graph(selected, **self.arguments(
            selected, chunks=chunks_for(selected, suffix="new"), expected_hash=before.sha256))
        self.assertEqual(result.status, "current", result)
        graph = json.loads(self.graph_scope.read("graph.json").data)
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertNotIn("one_fact", nodes)
        self.assertIn("one_new", nodes)
        self.assertIn("two_fact", nodes)
        self.assertEqual(len(graph["links"]), 2)
        self.assertTrue(any(self.backups.iterdir()))

    def test_expected_graph_hash_conflict_does_not_publish(self):
        active = self.active()
        first = ops.refresh_graph(active, **self.arguments(active))
        self.assertEqual(first.status, "current", first)
        original = self.graph_scope.read("graph.json")
        result = ops.refresh_graph(active, **self.arguments(active, expected_hash="0" * 64))
        self.assertEqual(result.error_code, "graph_expected_hash_changed")
        self.assertEqual(self.graph_scope.read("graph.json").data, original.data)

    def test_semantic_update_keeps_same_source_ast_layer(self):
        active = self.active()
        first = ops.refresh_graph(active, **self.arguments(active))
        self.assertEqual(first.status, "current", first)
        graph = json.loads(self.graph_scope.read("graph.json").data)
        doc_node = ops.document_nodes(active)[0]
        ast_node = {"id": "ast-heading", "label": "heading", "file_type": "code",
                    "source_file": "one.md", "source_location": "L1", "_origin": "ast"}
        ast_edge = {"source": doc_node["id"], "target": "ast-heading", "relation": "contains",
                    "source_file": "one.md", "source_location": "L1", "_origin": "ast",
                    "confidence": "EXTRACTED"}
        graph["nodes"].append(ast_node)
        graph["links"].append(ast_edge)
        (self.root / "graph.json").write_text(json.dumps(graph))
        before = self.graph_scope.read("graph.json")
        selected = self.active(["one.md"])
        result = ops.refresh_graph(selected, **self.arguments(
            selected, chunks=chunks_for(selected, suffix="new"), expected_hash=before.sha256))
        self.assertEqual(result.status, "current", result)
        saved = json.loads(self.graph_scope.read("graph.json").data)
        node = next(item for item in saved["nodes"] if item["id"] == "ast-heading")
        for key, value in ast_node.items():
            self.assertEqual(node[key], value)
        self.assertNotIn("one_fact", {item["id"] for item in saved["nodes"]})
        self.assertIn("two_fact", {item["id"] for item in saved["nodes"]})

    def test_source_change_during_build_is_pending_before_graph_publication(self):
        from graphify.build import build
        active = self.active()
        first = ops.refresh_graph(active, **self.arguments(active))
        self.assertEqual(first.status, "current", first)
        original = self.graph_scope.read("graph.json")

        def changed(*args, **kwargs):
            result = build(*args, **kwargs)
            path = self.vault / "one.md"
            path.write_bytes(path.read_bytes() + b"changed\n")
            return result

        with patch("graphify.build.build", changed):
            result = ops.refresh_graph(active, **self.arguments(active, expected_hash=original.sha256))
        self.assertEqual(result.status, "pending")
        self.assertEqual(result.error_code, "graph_source_changed")
        self.assertFalse(result.publication_uncertain)
        self.assertEqual(result.coverage[0]["status"], "stale")
        self.assertEqual(self.graph_scope.read("graph.json").data, original.data)

    def test_bad_stored_json_is_not_replaced(self):
        active = self.active()
        (self.root / "graph.json").write_bytes(b"recoverable invalid graph")
        before = self.graph_scope.read("graph.json")
        result = ops.refresh_graph(active, **self.arguments(active, expected_hash=before.sha256))
        self.assertEqual(result.error_code, "graph_json_invalid")
        self.assertEqual(self.graph_scope.read("graph.json").data, before.data)

    def test_failure_after_write_is_uncertain_and_preserves_backup_and_candidate(self):
        active = self.active()
        first = ops.refresh_graph(active, **self.arguments(active))
        self.assertEqual(first.status, "current", first)
        before = self.graph_scope.read("graph.json")
        arguments = self.arguments(active, chunks=chunks_for(active, suffix="changed"),
                                   expected_hash=before.sha256)
        write = self.graph_scope.write

        def publish_then_change_note(*args, **kwargs):
            result = write(*args, **kwargs)
            path = self.vault / "one.md"
            path.write_bytes(path.read_bytes() + b"external edit\n")
            return result

        with patch.object(self.graph_scope, "write", publish_then_change_note):
            result = ops.refresh_graph(active, **arguments)
        self.assertEqual(result.status, "pending")
        self.assertTrue(result.publication_uncertain)
        self.assertIsNone(result.graph_written)
        self.assertEqual(result.coverage[0]["status"], "stale")
        self.assertEqual(arguments["backup_scope"].read(arguments["backup_path"]).data, before.data)
        self.assertTrue(arguments["work_scope"].read(arguments["candidate_path"]).data)

    def test_read_error_after_write_reports_uncertainty_without_automatic_rollback(self):
        active = self.active()
        first = ops.refresh_graph(active, **self.arguments(active))
        self.assertEqual(first.status, "current", first)
        before = self.graph_scope.read("graph.json")
        arguments = self.arguments(active, chunks=chunks_for(active, suffix="changed"),
                                   expected_hash=before.sha256)
        write = self.graph_scope.write
        read = self.graph_scope.read
        fail_next = [False]

        def publish(*args, **kwargs):
            result = write(*args, **kwargs)
            fail_next[0] = True
            return result

        def read_once_error(*args, **kwargs):
            if fail_next[0]:
                fail_next[0] = False
                raise OSError("synthetic post-publication read failure")
            return read(*args, **kwargs)

        with patch.object(self.graph_scope, "write", publish), patch.object(
                self.graph_scope, "read", read_once_error):
            result = ops.refresh_graph(active, **arguments)
        self.assertEqual((result.status, result.publication_uncertain), ("pending", True))
        self.assertIsNone(result.graph_written)
        self.assertNotEqual(self.graph_scope.read("graph.json").data, before.data)
        self.assertEqual(arguments["backup_scope"].read(arguments["backup_path"]).data, before.data)
        self.assertTrue(arguments["work_scope"].read(arguments["candidate_path"]).data)


if __name__ == "__main__":
    unittest.main()
