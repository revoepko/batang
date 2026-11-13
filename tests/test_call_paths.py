"""등록 전 준비와 실제 등록 후 기존 v1/v2 수명주기 연결을 합성 검증한다."""
import json
import io
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_query_ops import QueryFixture, q, f, g, r
import query_session as session
from test_graph_ops import GraphFixture, chunks_for, GRAPHIFY, note


def documented_extraction_errors(calls_path):
    source = Path(calls_path).read_text(encoding="utf-8")
    section = source.split("### 추출 chunk 입력", 1)[1]
    match = re.search(r"```json\s*(.*?)\s*```", section, re.DOTALL)
    example = json.loads(match.group(1))
    chunks = example["chunks"]
    from graphify.validate import validate_extraction

    return validate_extraction({
        "nodes": [node for chunk in chunks for node in chunk["nodes"]],
        "edges": [edge for chunk in chunks for edge in chunk["edges"]],
    })


@unittest.skipUnless(GRAPHIFY, "Graphify 설치 필요")
class DocumentedExtractionExample(unittest.TestCase):
    def test_calls_example_passes_graphify_validator(self):
        calls = Path(__file__).resolve().parents[1] / "skills/batang/references/calls.md"
        self.assertEqual(documented_extraction_errors(calls), [])


class QuerySessionTransport(QueryFixture):
    def start_session(self):
        script = Path(__file__).resolve().parents[1] / "skills/batang/scripts/query_session.py"
        process = subprocess.Popen([sys.executable, "-B", "-u", str(script)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.addCleanup(self.close_session, process)
        return process

    @staticmethod
    def close_session(process):
        if process.poll() is None:
            process.kill()
            process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()

    def test_pipe_session_dispatches_repeated_reads_without_ack(self):
        self.save_graph(relations=[self.relation()])
        process = self.start_session()

        def send(raw):
            process.stdin.write(raw + "\n")
            process.stdin.flush()
            return json.loads(process.stdout.readline())

        self.assertEqual(json.loads(process.stdout.readline()), {"status": "ready"})
        config = {"root": str(self.root), "active_path": "ACTIVE.md", "selected_paths": ["a.md", "b.md", "c.md"],
                  "graph": {"root": str(self.root), "path": "graph.json"},
                  "source": {"root": str(self.root), "paths": ["a.md"]}}
        self.assertEqual(send(json.dumps({"op": "open", "config": config})), {"status": "opened"})
        self.assertEqual(send('{"op":"search","op":"close"}'),
                         {"status": "error", "code": "invalid_or_unavailable"})

        search_reply = send(json.dumps({"op": "search", "args": {"query": "첫 줄 a", "fields": ["body"]}}))
        self.assertEqual(search_reply["response_id"], 1)
        self.assertEqual(search_reply["result"]["status"], "ok")
        reference = search_reply["result"]["items"][0]["spans"][0]["ref"]

        read_reply = send(json.dumps({"op": "read_spans", "args": {"requests": [reference]}}))
        self.assertEqual(read_reply["response_id"], 2)
        self.assertEqual(read_reply["result"]["items"][0]["spans"][0]["text"], "첫 줄 a\n")
        self.assertEqual(send(json.dumps({"op": "ack", "response_id": 2})),
                         {"status": "error", "code": "unsupported_operation"})

        reread = send(json.dumps({"op": "read_spans", "args": {"requests": [reference]}}))
        self.assertEqual(reread["response_id"], 3)
        self.assertEqual(reread["result"]["items"][0]["spans"][0]["text"], "첫 줄 a\n")
        self.assertNotIn("already_seen", reread["result"]["items"][0])
        self.assertEqual(send(json.dumps({"op": "search", "args": {"query": "첫", "seen_refs": []}})),
                         {"status": "error", "code": "unsupported_argument"})
        relations = send(json.dumps({"op": "relations"}))
        self.assertEqual(relations["response_id"], 4)
        self.assertEqual(relations["result"]["status"], "ok")
        prepared = send(json.dumps({"op": "prepare_review_context", "args": {
            "stage": "pre_registration", "source_paths": ["a.md"]}}))
        self.assertEqual(prepared["response_id"], 5)
        self.assertEqual(prepared["result"]["status"], "ok")
        self.assertEqual(send('{"op":"reset_context"}'), {"status": "error", "code": "unsupported_operation"})
        fresh = send(json.dumps({"op": "search", "args": {"query": "첫 줄 a", "fields": ["body"]}}))
        self.assertEqual(fresh["response_id"], 6)
        self.assertTrue(fresh["result"]["items"][0]["spans"])
        self.assertEqual(send(json.dumps({"op": "open", "config": config})), {"status": "opened"})
        reopened = send(json.dumps({"op": "read_spans", "args": {"requests": [reference]}}))
        self.assertEqual(reopened["response_id"], 7)
        new_ref = reopened["result"]["items"][0]["spans"][0]["ref"]
        self.assertNotEqual(new_ref["context_id"], reference["context_id"])
        self.assertEqual(reopened["result"]["items"][0]["spans"][0]["text"], "첫 줄 a\n")
        self.assertEqual(send('{"op":"close"}'), {"status": "closed"})
        process.stdin.close()
        self.assertEqual(process.wait(timeout=5), 0)
        self.assertEqual(process.stderr.read(), "")

    def test_removed_operations_and_internal_type_errors_are_distinct(self):
        config = {"root": str(self.root), "active_path": "ACTIVE.md", "selected_paths": ["a.md"]}
        requests = [{"op": "ack"}, {"op": "reset_context"}, {"op": "open", "config": config},
                    {"op": "search", "args": {"query": "a"}}, {"op": "close"}]
        incoming = io.TextIOWrapper(io.BytesIO(("\n".join(json.dumps(x) for x in requests) + "\n").encode()))
        output = io.StringIO()
        with patch.object(sys, "stdin", incoming), patch.object(sys, "stdout", output), \
             patch.object(session, "search", side_effect=TypeError("PRIVATE implementation details")):
            session.main()
        replies = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(replies[1:3], [{"status": "error", "code": "unsupported_operation"}] * 2)
        self.assertEqual(replies[4], {"status": "error", "code": "invalid_or_unavailable"})
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_session_partial_packets_repeat_omissions_with_total_byte_budget(self):
        (self.root / "b.md").write_bytes(b"broken")
        process = self.start_session()
        self.assertEqual(json.loads(process.stdout.readline()), {"status": "ready"})
        def send(request):
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            raw = process.stdout.readline()
            self.assertLessEqual(len(raw.rstrip("\n").encode()), 2200)
            return json.loads(raw)
        config = {"root": str(self.root), "active_path": "ACTIVE.md", "selected_paths": list(self.paths)}
        send({"op": "open", "config": config})
        cursor, replies = None, []
        while True:
            reply = send({"op": "search", "args": {"query": "공통", "cursor": cursor},
                          "limits": {"max_items": 1, "max_bytes": 2200}})
            packet = reply["result"]
            self.assertEqual(packet["status"], "partial", packet)
            self.assertIn({"path": "b.md", "reason": "document_invalid"}, packet["omissions"])
            replies.append(packet)
            cursor = packet["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(replies), 2)
        send({"op": "close"})

    def test_pipe_session_rejects_oversized_request_frame(self):
        process = self.start_session()
        output, _ = process.communicate("x" * (1024 * 1024 + 1) + "\n", timeout=5)
        lines = [json.loads(line) for line in output.splitlines()]
        self.assertEqual(lines, [{"status": "ready"},
                                 {"status": "error", "code": "request_size_or_frame"}])
        self.assertEqual(process.returncode, 0)


class ReviewPreparation(QueryFixture):
    def test_pre_registration_does_not_preflight_unrelated_knowledge_root(self):
        alias = self.root.parent / (self.root.name + "-alias")
        alias.symlink_to(self.root, target_is_directory=True)
        self.addCleanup(alias.unlink)
        context = self.ctx(scope=f.FileScope(str(alias), ["ACTIVE.md", *self.paths]))
        (self.root / "new.txt").write_text("explicit source\n")
        source = f.FileScope(str(self.root), ["new.txt"])
        packet = q.prepare_review_context(context, stage="pre_registration", source_scope=source,
                                          source_paths=["new.txt"])
        self.assertEqual(packet["status"], "ok", packet)
        self.assertTrue(packet["items"])

    def test_partial_targets_preserve_normal_content_without_candidate_synthesis(self):
        self.save_graph(relations=[self.relation("b", "c", ("b", "c"))])
        (self.root / "a.md").write_bytes(b"broken")
        with patch.object(r, "discover_candidates", side_effect=AssertionError("incomplete selection")):
            packet = q.prepare_review_context(self.context, stage="post_registration", target_paths=["a.md"],
                                              comparison_paths=["b.md", "c.md"], limits=q.QueryLimits(max_items=100))
        self.assertEqual(packet["status"], "partial", packet)
        self.assertEqual(packet["candidate_discovery"], "not_run")
        self.assertEqual(packet["review_completion"], "not_assessed")
        self.assertIn({"path": "a.md", "reason": "document_invalid"}, packet["omissions"])
        self.assertEqual({i["ref"]["path"] for i in packet["items"] if i["type"] == "document_content"}, {"b.md", "c.md"})
        self.assertFalse(any(i["type"] == "additional_candidate" for i in packet["items"]))

    def test_authorized_existing_and_deferred_signals_remain_available(self):
        relation = self.relation()
        value = self.save_graph(relations=[relation])
        docs = self.active().documents[:2]
        event = dict(r._assertion_descriptor("a", "b", "references", "명시 관계"),
                     decision="deferred", reason="허용 원문 판단 보류", context_document_ids=["a", "b"])
        value["relation_review"] = [{"review_id": "review", "candidate_status": "complete",
                                    "relation_status": "partial", "documents": [
                                        {"document_id": d.document_id, "path": d.path, "source_sha256": d.sha256} for d in docs],
                                    "assertion_decisions": [event]}]
        (self.root / "graph.json").write_text(json.dumps(value, ensure_ascii=False))
        packet = q.prepare_review_context(self.ctx(["a.md", "b.md"]), stage="post_registration",
                                          target_paths=["a.md"], comparison_paths=["b.md"],
                                          limits=q.QueryLimits(max_items=100))
        self.assertEqual(packet["status"], "ok", packet)
        signals = {s for item in packet["items"] if item["type"] == "additional_candidate" for s in item["signals"]}
        self.assertIn("existing_relation", signals)
        self.assertIn("unresolved_deferred", signals)
        self.assertTrue(any(i["type"] == "existing_judgment" for i in packet["items"]))

    def test_hidden_support_cannot_leak_as_existing_or_deferred_candidate_signal(self):
        relation = self.relation(evidence=("a", "b", "c"))
        value = self.save_graph(relations=[relation])
        docs = self.active().documents
        event = dict(r._assertion_descriptor("a", "b", "references", "명시 관계"),
                     decision="deferred", reason="비공개 지원 관계 보류", context_document_ids=["a", "b"])
        outside = dict(r._assertion_descriptor("a", "c", "references", "범위 밖 판단"),
                       decision="deferred", reason="범위 밖 보류", context_document_ids=["a", "c"])
        value["relation_review"] = [{"review_id": "private-review", "candidate_status": "partial",
                                    "relation_status": "partial", "documents": [
                                        {"document_id": d.document_id, "path": d.path, "source_sha256": d.sha256} for d in docs],
                                    "assertion_decisions": [event, outside],
                                    "decisions": [{"source_document_id": "a", "target_document_id": "b",
                                                   "decision": "deferred", "relation_ids": [], "reason": "비공개 pair"}]}]
        (self.root / "graph.json").write_text(json.dumps(value, ensure_ascii=False))
        packet = q.prepare_review_context(self.ctx(["a.md", "b.md"]), stage="post_registration",
                                          target_paths=["a.md"], comparison_paths=["b.md"],
                                          limits=q.QueryLimits(max_items=100))
        self.assertEqual(packet["status"], "ok", packet)
        signals = {s for item in packet["items"] if item["type"] == "additional_candidate" for s in item["signals"]}
        self.assertNotIn("existing_relation", signals)
        self.assertNotIn("unresolved_deferred", signals)
        self.assertEqual(packet["candidate_omissions"], [])
        self.assertEqual(packet["candidate_discovery"], "complete")
        self.assertFalse(any(i["type"] in {"existing_record", "existing_judgment"} for i in packet["items"]))
        self.assertNotIn("비공개", json.dumps(packet, ensure_ascii=False))

    def test_legacy_review_identifier_is_returned_only_as_scoped_opaque_ref(self):
        value = self.save_graph()
        docs = self.active().documents[:2]
        decision = {"source_document_id": "a", "target_document_id": "b", "decision": "no_relation",
                    "relation_ids": [], "reason": "선택 원문 검토"}
        value["relation_review"] = [{"review_id": "c.md", "candidate_status": "complete",
                                    "relation_status": "complete", "documents": [
                                        {"document_id": d.document_id, "path": d.path, "source_sha256": d.sha256} for d in docs],
                                    "decisions": [decision]}]
        (self.root / "graph.json").write_text(json.dumps(value, ensure_ascii=False))
        packet = q.prepare_review_context(self.ctx(["a.md", "b.md"]), stage="post_registration",
                                          target_paths=["a.md"], comparison_paths=["b.md"],
                                          limits=q.QueryLimits(max_items=100))
        judgments = [i for i in packet["items"] if i["type"] == "existing_judgment"]
        self.assertEqual(judgments[0]["record"], decision)
        self.assertRegex(judgments[0]["review_ref"], r"^review_[0-9a-f]{64}$")
        self.assertNotIn("c.md", json.dumps(packet, ensure_ascii=False))
        self.assertNotIn("review_id", judgments[0])

    def test_raw_relation_is_repeated_by_review_preparation(self):
        self.save_graph(relations=[self.relation()])
        context = self.ctx()
        first = q.relations(context)
        packet = q.prepare_review_context(context, stage="post_registration", target_paths=["a.md"],
                                          comparison_paths=["b.md"], limits=q.QueryLimits(max_items=100))
        records = [i for i in packet["items"] if i["type"] == "existing_record"]
        self.assertEqual(records[0]["record"], first["items"][0]["record"])
        self.assertNotIn("already_seen", records[0])

    def test_pre_registration_reads_only_explicit_source_without_active_or_write(self):
        (self.root / "new.txt").write_text("새 source\n아직 등록 안 됨\n")
        scope = f.FileScope(str(self.root), ["new.txt"])
        before = {p.name: p.read_bytes() for p in self.root.iterdir()}
        with patch.object(g, "read_active_documents", side_effect=AssertionError("no fake ACTIVE")), \
             patch.object(r, "discover_candidates", side_effect=AssertionError("not registered")), \
             patch.object(f.FileScope, "write", side_effect=AssertionError("read only")):
            packet = q.prepare_review_context(self.context, stage="pre_registration",
                                              source_scope=scope, source_paths=["new.txt"])
        self.assertEqual(packet["status"], "ok", packet)
        self.assertEqual(packet["candidate_discovery"], "not_run")
        self.assertFalse(packet["registration_performed"])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_pre_source_permissions_and_partial_failure_do_not_claim_rollback(self):
        (self.root / "new.txt").write_bytes(b"good\n")
        (self.root / "bad.txt").write_bytes(b"\xff")
        scope = f.FileScope(str(self.root), ["new.txt", "bad.txt"])
        bad = q.prepare_review_context(self.context, stage="pre_registration", source_scope=scope,
                                       source_paths=["new.txt", "bad.txt"])
        self.assertEqual(bad["status"], "error")
        self.assertEqual(bad["items"], [])
        denied = q.prepare_review_context(self.context, stage="pre_registration", source_scope=scope,
                                          source_paths=["a.md"])
        self.assertEqual(denied["status"], "error")
        self.assertNotIn("a.md", json.dumps(denied))

    def test_source_repeats_bytes_with_context_scope_and_hash_references(self):
        (self.root / "new.txt").write_text("새 source 본문\n")
        scope = f.FileScope(str(self.root), ["new.txt"])
        context = self.ctx()
        first = q.prepare_review_context(context, stage="pre_registration", source_scope=scope,
                                         source_paths=["new.txt"], limits=q.QueryLimits(max_excerpt_bytes=9))
        self.assertTrue(self.output_refs(first))
        repeat = q.prepare_review_context(context, stage="pre_registration", source_scope=scope,
                                          source_paths=["new.txt"], limits=q.QueryLimits(max_excerpt_bytes=9))
        self.assertEqual(first, repeat)
        self.assertNotIn("already_seen", json.dumps(first))
        (self.root / "new.txt").write_text("새 source 변경\n")
        changed = q.prepare_review_context(context, stage="pre_registration", source_scope=scope,
                                           source_paths=["new.txt"])
        self.assertTrue(self.output_refs(changed))

    def test_actual_registration_rebuilds_post_snapshot_without_pre_hash_reuse(self):
        (self.root / "new.md").write_bytes(note("new"))
        scope = f.FileScope(str(self.root), ["ACTIVE.md", *self.paths, "new.md"])
        source_scope = f.FileScope(str(self.root), ["new.md"])
        context = q.QueryContext(scope, "ACTIVE.md", [*self.paths, "new.md"])
        before = q.prepare_review_context(context, stage="pre_registration", source_scope=source_scope,
                                          source_paths=["new.md"])
        self.assertEqual(before["status"], "ok")
        denied = q.prepare_review_context(context, stage="post_registration", target_paths=["new.md"],
                                          comparison_paths=["a.md"])
        self.assertEqual(denied["status"], "error")
        old = scope.read("ACTIVE.md")
        backup = f.FileScope(str(self.root), ["active.backup"])
        registered = g.register_documents(scope, "ACTIVE.md", ["new.md"], expected_active_sha256=old.sha256,
                                           backup_scope=backup, backup_path="active.backup")
        packet = q.prepare_review_context(context, stage="post_registration", target_paths=["new.md"],
                                          comparison_paths=["a.md"], limits=q.QueryLimits(max_items=100))
        self.assertEqual(packet["status"], "ok", packet)
        refs = self.output_refs(packet)
        self.assertTrue(any(x["document_id"] == "new" for x in refs))
        self.assertNotEqual(registered.active_sha256, old.sha256)

    def test_minimal_existing_judgments_do_not_dump_unrelated_history(self):
        value = self.save_graph()
        active = self.active()
        snapshots = [{"document_id": d.document_id, "path": d.path, "source_sha256": d.sha256}
                     for d in active.documents]
        event = dict(r._assertion_descriptor("a", "b", "references", "기존 판단"),
                     decision="no_relation", reason="지정 원문 미지지", context_document_ids=["a", "b"])
        unrelated = dict(r._assertion_descriptor("b", "c", "references", "다른 판단"),
                         decision="no_relation", reason="불필요한 과거 설명", context_document_ids=["b", "c"])
        value["relation_review"] = [{"review_id": "review-test", "candidate_status": "complete",
                                    "relation_status": "complete", "documents": snapshots,
                                    "assertion_decisions": [event, unrelated]}]
        (self.root / "graph.json").write_text(json.dumps(value, ensure_ascii=False))
        packet = q.prepare_review_context(self.context, stage="post_registration", target_paths=["a.md"],
                                          comparison_paths=["b.md", "c.md"], limits=q.QueryLimits(max_items=100))
        self.assertEqual(packet["status"], "ok", packet)
        decisions = [i for i in packet["items"] if i["type"] == "existing_judgment"]
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["record"], event)
        self.assertNotIn("불필요한 과거", json.dumps(packet, ensure_ascii=False))

    def test_post_reconstructs_actual_active_and_passes_only_explicit_comparison(self):
        original, arguments = r.discover_candidates, []
        def observed(targets, comparisons, envelope=None):
            arguments.append((targets, comparisons))
            return original(targets, comparisons, envelope)
        with patch.object(r, "discover_candidates", side_effect=observed):
            packet = q.prepare_review_context(self.context, stage="post_registration",
                                              target_paths=["a.md"], comparison_paths=["b.md"])
        self.assertEqual(packet["status"], "ok", packet)
        targets, comparisons = arguments[0]
        self.assertEqual([d.path for d in targets.documents], ["a.md"])
        self.assertEqual([d.path for d in comparisons.documents], ["b.md"])
        self.assertEqual(targets.active_sha256, comparisons.active_sha256)
        self.assertIs(targets.scope, self.scope)
        self.assertFalse(packet["packet_complete_is_review_complete"])

    def test_full_scope_does_not_read_extra_allowed_documents(self):
        reads, original = [], self.scope.read
        with patch.object(self.scope, "read", side_effect=lambda p: (reads.append(p), original(p))[1]):
            packet = q.prepare_review_context(self.context, stage="post_registration", target_paths=["a.md"],
                                              comparison_paths=["b.md"], mode="full")
        self.assertEqual(packet["status"], "ok", packet)
        self.assertNotIn("c.md", reads)

    def test_incremental_includes_third_document_support_but_narrow_scope_hides_it(self):
        self.save_graph(relations=[self.relation("a", "b", ("a", "b", "c"))])
        packet = q.prepare_review_context(self.context, stage="post_registration", target_paths=["c.md"],
                                          comparison_paths=["a.md", "b.md"])
        ids = {i["ref"]["document_id"] for i in packet["items"] if i["type"] == "document_content"}
        self.assertEqual(ids, {"a", "b", "c"})
        self.assertTrue(any(i["type"] == "existing_record" for i in packet["items"]))
        narrow = q.prepare_review_context(self.ctx(["a.md", "b.md"]), stage="post_registration",
                                          target_paths=["a.md"], comparison_paths=["b.md"])
        self.assertFalse(any(i["type"] == "existing_record" for i in narrow["items"]))

    def test_full_mode_is_partitioned_and_never_auto_decides_no_relation(self):
        limits = q.QueryLimits(max_items=1, max_bytes=4096, max_excerpt_bytes=100)
        cursor, ids = None, set()
        while True:
            packet = q.prepare_review_context(self.context, stage="post_registration", target_paths=["a.md"],
                                              comparison_paths=["b.md", "c.md"], mode="full", limits=limits,
                                              cursor=cursor)
            self.assertEqual(packet["review_completion"], "not_assessed")
            self.assertLessEqual(len(q._json(packet)), limits.max_bytes)
            for item in packet["items"]:
                if item["type"] == "document_content":
                    ids.add(item["ref"]["document_id"])
            self.assertNotIn("no_relation", json.dumps(packet))
            cursor = packet["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(ids, {"a", "b", "c"})

    def test_unregistered_target_and_source_hash_change_are_rejected(self):
        (self.root / "new.md").write_bytes(note("new"))
        self.assertEqual(q.prepare_review_context(self.context, stage="post_registration",
                          target_paths=["new.md"])["status"], "error")
        packet = q.prepare_review_context(self.context, stage="post_registration", target_paths=["a.md"],
                                           comparison_paths=["b.md"], limits=q.QueryLimits(max_items=1))
        self.write_note("a", b"changed\n")
        stale = q.prepare_review_context(self.context, stage="post_registration", target_paths=["a.md"],
                                         comparison_paths=["b.md"], limits=q.QueryLimits(max_items=1),
                                         cursor=packet["next_cursor"])
        self.assertEqual(stale["status"], "stale")


@unittest.skipUnless(GRAPHIFY, "Graphify 설치 필요")
class ExistingLifecycle(GraphFixture):
    def context(self):
        return q.QueryContext(self.note_scope, "ACTIVE.md", list(self.paths),
                              graph_scope=self.graph_scope, graph_path="graph.json", context_id="lifecycle")

    def test_v1_full_incremental_query_keeps_unaffected_records(self):
        active = self.active()
        args = self.arguments(active)
        full = g.refresh_graph(active, **args)
        self.assertTrue(full.graph_written, full)
        before = json.loads(self.graph_scope.read("graph.json").data)
        one = self.active(["one.md"])
        args = self.arguments(one, expected_hash=full.graph_sha256, chunks=chunks_for(one, suffix="new"))
        delta = g.refresh_graph(one, **args)
        self.assertTrue(delta.graph_written, delta)
        after = json.loads(self.graph_scope.read("graph.json").data)
        self.assertEqual([n for n in before["nodes"] if n.get("source_file") == "two.md"],
                         [n for n in after["nodes"] if n.get("source_file") == "two.md"])
        packet = q.relations(self.context())
        self.assertEqual(packet["format"], 1)
        self.assertTrue(packet["items"])

    def test_v2_full_incremental_prepare_preserves_storage_and_judgment(self):
        active = self.active()
        docs = {d.document_id: d for d in active.documents}
        evidence = [r.evidence_span(docs[i], 1, 1) for i in ("one", "two")]
        relation = {"relation_id": r.relation_id("one", "two", "shares_topic", "합성 주제"),
                    "source_document_id": "one", "target_document_id": "two", "kind": "shares_topic",
                    "qualifier": "합성 주제", "status": "active", "support_sets": [{
                        "support_id": r.support_set_id(evidence), "confidence": "EXTRACTED",
                        "evidence": evidence, "rationale": "실제 합성 원문", "status": "active"}]}
        plan = r.discover_candidates(active)
        request = {"candidate_plan": plan, "decisions": [{"source_document_id": "one",
                    "target_document_id": "two", "decision": "accepted",
                    "relation_ids": [relation["relation_id"]], "reason": "합성 근거"}], "relations": [relation]}
        full = g.refresh_graph(active, **self.arguments(active), relationship_request=request)
        self.assertTrue(full.graph_written, full)
        before = self.graph_scope.read("graph.json").data
        with patch.object(f.FileScope, "write", side_effect=AssertionError("prepare must not write")):
            packet = q.prepare_review_context(self.context(), stage="post_registration", target_paths=["one.md"],
                                              comparison_paths=["two.md"], mode="incremental",
                                              limits=q.QueryLimits(max_items=100, max_bytes=65536))
        self.assertEqual(packet["status"], "ok", packet)
        self.assertTrue(any(x["type"] == "existing_judgment" for x in packet["items"]))
        self.assertEqual(before, self.graph_scope.read("graph.json").data)
        # 준비 결과를 저장 포맷으로 승격하지 않고 기존 갱신 요청을 다시 사용한다.
        delta = g.refresh_graph(active, **self.arguments(active, expected_hash=full.graph_sha256),
                                relationship_request=request)
        self.assertTrue(delta.graph_written, delta)
        saved = r.parse_envelope(self.graph_scope.read("graph.json").data)
        self.assertEqual(saved["relations"][0]["relation_id"], relation["relation_id"])
        self.assertEqual(q.relations(self.context())["format"], 2)


if __name__ == "__main__":
    unittest.main()
