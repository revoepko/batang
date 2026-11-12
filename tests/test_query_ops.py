"""조회 packet의 실제 인용·한도·권한 경계를 합성 임시 파일로 확인한다."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/batang/scripts"))
import file_ops as f
import graph_ops as g
import relationship_ops as r
import query_ops as q


class QueryFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="batang-query-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.paths = ("a.md", "b.md", "c.md")
        for name in ("a", "b", "c"):
            self.write_note(name, f"첫 줄 {name}\n공통 단어\n셋째 줄\n".encode())
        (self.root / "ACTIVE.md").write_text("".join(f"- [{p}]({p})\n" for p in self.paths))
        self.scope = f.FileScope(str(self.root), ["ACTIVE.md", *self.paths])
        self.graph_scope = f.FileScope(str(self.root), ["graph.json"])
        self.context = self.ctx()

    def write_note(self, name, body, **properties):
        metadata = {"batang_schema_version": 2, "batang_id": name, "subject": f"제목 {name}",
                    "tags": ["공통 태그"], "aliases": [f"별칭 {name}"], "content_kind": "note",
                    "sources": [{"id": "source", "path": None, "origin": "user", "sha256": None,
                                 "raw_path": None}], "legacy_refs": []}
        metadata.update(properties)
        (self.root / (name + ".md")).write_bytes(f.serialize_document(metadata, body))

    def ctx(self, paths=None, scope=None, context_id="test-context"):
        return q.QueryContext(scope or self.scope, "ACTIVE.md", self.paths if paths is None else paths,
                              graph_scope=self.graph_scope, graph_path="graph.json", context_id=context_id)

    def active(self):
        return g.read_active_documents(self.scope, "ACTIVE.md", self.paths)

    def save_graph(self, *, version=2, relations=None, directed=False, links=None):
        graph = {"nodes": g.document_nodes(self.active()), "links": links or [],
                 "directed": directed, "multigraph": False, "graph": {}}
        value = graph if version == 1 else dict(batang_graph_format=2, content_graph=graph,
                                                relations=relations or [], relation_review=[])
        (self.root / "graph.json").write_text(json.dumps(value, ensure_ascii=False))
        return value

    def relation(self, source="a", target="b", evidence=("a", "b"), kind="references"):
        docs = {d.document_id: d for d in self.active().documents}
        spans = [r.evidence_span(docs[i], 1, 1) for i in evidence]
        support = {"support_id": r.support_set_id(spans), "confidence": "EXTRACTED",
                   "evidence": spans, "rationale": "선택 원문 근거", "status": "active"}
        return {"relation_id": r.relation_id(source, target, kind, "명시 관계"),
                "source_document_id": source, "target_document_id": target,
                "kind": kind, "qualifier": "명시 관계", "support_sets": [support], "status": "active"}

    def ref(self, name="a", first=1, last=1):
        doc = next(d for d in self.active().documents if d.document_id == name)
        return dict(r.evidence_span(doc, first, last), path=doc.path)

    def output_refs(self, packet):
        return [span["ref"] for item in packet["items"] for span in item.get("spans", [])]


class SearchAndSpans(QueryFixture):
    def test_required_explicit_selection_and_literal_fields(self):
        with self.assertRaises(f.FileError):
            q.QueryContext(self.scope, "ACTIVE.md", None)
        for query, field in [("제목 a", "title"), ("a", "id"), ("태그", "tags"),
                             ("별칭 a", "aliases"), ("셋째", "body")]:
            packet = q.search(self.ctx(["a.md"]), query, fields=[field])
            self.assertEqual(packet["status"], "ok", packet)
            self.assertEqual(packet["items"][0]["matched_fields"], [field])

    def test_search_reads_only_selected_intersection_and_no_metadata_sources(self):
        self.write_note("c", b"not selected\n", sources=[{"id": "secret", "path": "outside.md",
                        "sha256": "0" * 64, "origin": "user", "raw_path": "outside.md"}])
        calls, read = [], self.scope.read
        with patch.object(self.scope, "read", side_effect=lambda p: (calls.append(p), read(p))[1]):
            packet = q.search(self.ctx(["a.md"]), "첫")
        self.assertEqual(packet["status"], "ok")
        self.assertNotIn("b.md", calls)
        self.assertNotIn("c.md", calls)
        self.assertNotIn("outside.md", calls)

    def test_inactive_and_denied_selection_have_same_safe_error(self):
        denied = f.FileScope(str(self.root), ["ACTIVE.md", "a.md"])
        p1 = q.search(self.ctx(["b.md"], scope=denied), "x")
        p2 = q.search(self.ctx(["unknown.md"]), "x")
        self.assertEqual(p1, p2)
        self.assertNotIn("b.md", json.dumps(p1))
        self.assertNotIn("unknown", json.dumps(p2))

    def test_symlink_and_corruption_are_errors_not_no_match(self):
        (self.root / "a.md").unlink()
        (self.root / "a.md").symlink_to(self.root / "b.md")
        self.assertEqual(q.search(self.ctx(["a.md"]), "absent")["status"], "error")
        (self.root / "a.md").unlink()
        (self.root / "a.md").write_bytes(b"broken document")
        self.assertEqual(q.search(self.ctx(["a.md"]), "absent")["status"], "error")

    def test_missing_graph_and_no_match_are_distinct_from_source_error(self):
        self.assertEqual(q.relations(self.context)["graph_status"], "missing")
        self.assertEqual(q.search(self.context, "없음")["status"], "absent")
        (self.root / "a.md").unlink()
        self.assertEqual(q.search(self.context, "없음")["status"], "error")

    def test_literal_hashes_and_body_relative_lines_round_trip(self):
        self.write_note("a", "한 줄\r\n둘째\r\n\r\n끝".encode())
        packet = q.search(self.ctx(["a.md"]), "둘째")
        ref = self.output_refs(packet)[0]
        self.assertEqual((ref["start_line"], ref["end_line"]), (2, 2))
        self.assertEqual(ref["span_sha256"], f.sha256("둘째\r\n".encode()))
        reread = q.read_spans(self.ctx(["a.md"]), [ref])
        self.assertEqual(reread["items"][0]["spans"][0]["text"], "둘째\r\n")

    def test_reference_requires_id_and_both_hashes(self):
        original = self.ref()
        for key in ("document_id", "source_sha256", "span_sha256"):
            bad = dict(original)
            del bad[key]
            self.assertEqual(q.read_spans(self.context, [bad])["status"], "error")
        bad = dict(original, document_id="b")
        self.assertEqual(q.read_spans(self.context, [bad])["status"], "error")
        self.assertEqual(q.read_spans(self.context, [dict(original, span_sha256="0" * 64)])["status"], "stale")
        self.write_note("a", b"changed\n")
        self.assertEqual(q.read_spans(self.context, [original])["status"], "stale")

    def test_confirmation_is_explicit_and_overlap_only_returns_new_bytes(self):
        context = self.ctx(["a.md"])
        first = q.read_spans(context, [self.ref(first=1, last=2)])
        again = q.read_spans(context, [self.ref(first=1, last=2)])
        self.assertEqual(first, again)  # 반환 계산만으로 seen 등록하지 않는다.
        context.confirm_seen(self.output_refs(first))
        duplicate = q.read_spans(context, [self.ref(first=1, last=2)])
        self.assertTrue(all(not i["spans"] for i in duplicate["items"]))
        overlap = q.read_spans(context, [self.ref(first=2, last=3)])
        self.assertEqual("".join(s["text"] for i in overlap["items"] for s in i["spans"]), "셋째 줄\n")
        fresh = q.read_spans(self.ctx(["a.md"], context_id="fresh"), [self.ref(first=1, last=2)],
                             seen_refs=self.output_refs(first))
        self.assertTrue(self.output_refs(fresh))

    def test_confirming_truncated_page_does_not_skip_unprinted_body(self):
        self.write_note("a", (b"abcdefghij\n") * 40)
        context = self.ctx(["a.md"])
        limits = q.QueryLimits(max_items=1, max_bytes=3000, max_excerpt_bytes=50)
        first = q.read_spans(context, [self.ref(last=40)], limits=limits)
        context.confirm_seen(self.output_refs(first))
        second = q.read_spans(context, [self.ref(last=40)], limits=limits, cursor=first["next_cursor"])
        self.assertEqual(second["items"][0]["spans"][0]["ref"]["start_byte"], 11)

    def test_response_and_excerpt_bytes_are_bounded_with_unicode_lines(self):
        self.write_note("a", (("문장" * 10 + "\n") * 20).encode())
        limits = q.QueryLimits(max_items=2, max_bytes=2400, max_excerpt_bytes=90)
        cursor, combined = None, []
        while True:
            packet = q.read_spans(self.ctx(["a.md"]), [self.ref(last=20)], limits=limits, cursor=cursor)
            self.assertLessEqual(len(q._json(packet)), limits.max_bytes)
            self.assertLessEqual(len(packet["items"]), limits.max_items)
            for item in packet["items"]:
                for span in item["spans"]:
                    self.assertLessEqual(len(span["text"].encode()), limits.max_excerpt_bytes)
                    combined.append(span["text"])
            cursor = packet["next_cursor"]
            if cursor is None:
                break
        self.assertEqual("".join(combined), ("문장" * 10 + "\n") * 20)

    def test_long_single_line_is_not_cut_and_can_retry_same_cursor_with_larger_limit(self):
        body = ("문장" * 200 + "\n").encode()
        self.write_note("a", body)
        context = self.ctx(["a.md"])
        first = q.read_spans(context, [self.ref()], limits=q.QueryLimits(max_excerpt_bytes=90))
        self.assertEqual(first["status"], "limit")
        self.assertEqual(first["required_excerpt_bytes"], len(body))
        self.assertEqual(first["items"], [])
        second = q.read_spans(context, [self.ref()], limits=q.QueryLimits(max_excerpt_bytes=2000),
                              cursor=first["next_cursor"])
        span = second["items"][0]["spans"][0]
        self.assertEqual(span["text"].encode(), body)
        self.assertEqual(span["ref"]["span_sha256"], r.evidence_span(self.active().documents[0], 1, 1)["span_sha256"])

    def test_cursor_rejects_query_scope_source_and_permission_changes(self):
        limits = q.QueryLimits(max_items=1)
        first = q.search(self.context, "공통", limits=limits)
        cursor = first["next_cursor"]
        self.assertIsNotNone(cursor)
        self.assertEqual(q.search(self.context, "셋째", limits=limits, cursor=cursor)["status"], "stale")
        self.assertEqual(q.search(self.ctx(["a.md"]), "공통", limits=limits, cursor=cursor)["status"], "stale")
        narrower = f.FileScope(str(self.root), ["ACTIVE.md", *self.paths, "new_allowed.md"])
        self.assertEqual(q.search(self.ctx(scope=narrower), "공통", limits=limits, cursor=cursor)["status"], "stale")
        self.write_note("b", b"changed\n")
        self.assertEqual(q.search(self.context, "공통", limits=limits, cursor=cursor)["status"], "stale")

    def test_active_change_during_query_is_stale(self):
        original = self.scope.read
        count = [0]
        def changing(path):
            if path == "ACTIVE.md":
                count[0] += 1
                if count[0] > 1:
                    (self.root / "ACTIVE.md").write_text("- [a](a.md)\n")
            return original(path)
        with patch.object(self.scope, "read", side_effect=changing):
            self.assertEqual(q.search(self.ctx(["a.md"]), "첫")["status"], "stale")

    def test_byte_limit_reports_nonprogress_instead_of_false_absence(self):
        self.write_note("a", b"x" * 6000)
        result = q.search(self.ctx(["a.md"]), "x", limits=q.QueryLimits(max_bytes=512))
        self.assertEqual(result["status"], "limit")
        self.assertLessEqual(len(q._json(result)), 512)

    def test_metadata_and_external_links_are_never_followed(self):
        (self.root / "outside.txt").write_text("PRIVATE")
        self.write_note("a", b"[external](outside.txt)\n", sources=[{"id": "ref", "path": "outside.txt",
                        "sha256": "0" * 64, "origin": "local", "raw_path": "outside.txt"}])
        original, reads = self.scope.read, []
        with patch.object(self.scope, "read", side_effect=lambda path: (reads.append(path), original(path))[1]):
            packet = q.search(self.ctx(["a.md"]), "external")
        self.assertEqual(packet["status"], "ok")
        self.assertNotIn("outside.txt", reads)
        self.assertNotIn("PRIVATE", json.dumps(packet))


class RawRelations(QueryFixture):
    def test_shared_authorized_names_do_not_hide_allowed_relation(self):
        for identifier in ("a", "c"):
            self.write_note(identifier, f"source {identifier}\n".encode(), subject="공유제목", aliases=["공유별칭"])
        relation = self.relation()
        relation["support_sets"][0]["rationale"] = "공유제목의 공유별칭을 근거로 판단"
        self.save_graph(relations=[relation])
        packet = q.relations(self.ctx(["a.md", "b.md"]))
        self.assertEqual(packet["status"], "ok", packet)
        self.assertEqual(packet["items"][0]["record"], relation)

    def test_record_ack_crosses_selector_and_operation_without_weakening_scope(self):
        self.save_graph(relations=[self.relation()])
        context = self.ctx()
        first = q.relations(context)
        context.confirm_seen([i["record_ref"] for i in first["items"]])
        neighbors = q.relations(context, operation="neighbors", selector={"source": "a"})
        self.assertTrue(neighbors["items"][0]["already_seen"])
        self.assertNotIn("record", neighbors["items"][0])
        narrow = q.relations(self.ctx(["a.md", "b.md"]), seen_refs=context.seen_refs)
        self.assertIn("record", narrow["items"][0])
        self.write_note("b", b"different source snapshot\n")
        changed = q.relations(context)
        self.assertIn("record", changed["items"][0])
        self.assertEqual(changed["items"][0]["currentness"], "stale")

    def test_depth_limited_search_does_not_claim_absence_in_either_format(self):
        for identifier in ("d", "e", "f"):
            self.write_note(identifier, f"source {identifier}\n".encode())
        self.paths = tuple(f"{i}.md" for i in "abcdef")
        (self.root / "ACTIVE.md").write_text("".join(f"- [{p}]({p})\n" for p in self.paths))
        self.scope = f.FileScope(str(self.root), ["ACTIVE.md", *self.paths])
        for version in (1, 2):
            with self.subTest(version=version):
                if version == 1:
                    nodes = g.document_nodes(self.active())
                    mapping = {n["document_id"]: n["id"] for n in nodes}
                    self.save_graph(version=1, directed=True, links=[{"source": mapping[a], "target": mapping[b]}
                                    for a, b in zip("abcde", "bcdef")])
                    source, target = mapping["a"], mapping["f"]
                else:
                    self.save_graph(relations=[self.relation(a, b, (a, b)) for a, b in zip("abcde", "bcdef")])
                    source, target = "a", "f"
                context = self.ctx()
                limited = q.relations(context, operation="shortest_path", selector={"source": source, "target": target})
                self.assertEqual(limited["status"], "partial", limited)
                self.assertTrue(limited["truncated"])
                self.assertTrue(limited["exploration"]["depth_limited"])
                self.assertIn("exploration_depth_limit", limited["omissions"])
                complete = q.relations(context, operation="shortest_path", selector={"source": source, "target": target},
                                       limits=q.QueryLimits(max_depth=5))
                self.assertEqual(len(complete["items"]), 5)
                self.assertFalse(complete["exploration"]["depth_limited"])
                reverse = q.relations(context, operation="shortest_path", selector={"source": target, "target": source})
                self.assertEqual(reverse["status"], "absent")
                self.assertFalse(reverse["exploration"]["depth_limited"])
                traversal = q.relations(context, operation="traverse", selector={"source": source},
                                        limits=q.QueryLimits(max_depth=1))
                self.assertEqual(traversal["status"], "partial")
                self.assertEqual(traversal["exploration"]["max_depth"], 1)

    def test_endpoint_snapshot_changes_are_stale_even_with_current_third_support(self):
        relation = self.relation(evidence=("c",))
        self.save_graph(relations=[relation])
        self.write_note("a", b"endpoint changed but third support unchanged\n")
        packet = q.relations(self.context)
        self.assertEqual(packet["items"][0]["record"], relation)
        self.assertEqual(packet["items"][0]["currentness"], "stale")
        value = self.save_graph(relations=[self.relation(evidence=("c",))])
        value["content_graph"]["nodes"][0]["source_sha256"] = "0" * 64
        (self.root / "graph.json").write_text(json.dumps(value))
        self.assertEqual(q.relations(self.context)["items"][0]["currentness"], "stale")

    def test_record_ack_avoids_repeat_raw_body_and_resets_with_context(self):
        self.save_graph(relations=[self.relation()])
        context = self.ctx()
        first = q.relations(context)
        context.confirm_seen([item["record_ref"] for item in first["items"]])
        repeat = q.relations(context)
        self.assertTrue(repeat["items"][0]["already_seen"])
        self.assertNotIn("record", repeat["items"][0])
        fresh = q.relations(self.ctx(context_id="reset"), seen_refs=context.seen_refs)
        self.assertIn("record", fresh["items"][0])

    def test_raw_v2_is_unmodified_fields_without_history_or_projection(self):
        relation = self.relation()
        self.save_graph(relations=[relation])
        with patch.object(r, "parse_envelope", side_effect=AssertionError("full history forbidden")), \
             patch.object(r, "project_graph", side_effect=AssertionError("projection forbidden")):
            packet = q.relations(self.context)
        self.assertEqual(packet["items"][0]["record"], relation)
        self.assertEqual(packet["items"][0]["currentness"], "current")
        self.assertEqual(packet["view"], "raw")

    def test_hidden_support_suppresses_record_and_rationale_without_counts(self):
        relation = self.relation(evidence=("a", "b", "c"))
        relation["support_sets"][0]["rationale"] = "c의 숨은 설명"
        self.save_graph(relations=[relation])
        packet = q.relations(self.ctx(["a.md", "b.md"]))
        self.assertEqual(packet["items"], [])
        self.assertNotIn("숨은", json.dumps(packet, ensure_ascii=False))
        self.assertNotIn("hidden_count", packet)

    def test_hidden_document_label_in_rationale_is_not_indirectly_returned(self):
        relation = self.relation()
        relation["support_sets"][0]["rationale"] = "제목 c의 비공개 판단"
        self.save_graph(relations=[relation])
        packet = q.relations(self.ctx(["a.md", "b.md"]))
        self.assertEqual(packet["items"], [])
        self.assertNotIn("비공개", json.dumps(packet, ensure_ascii=False))

    def test_graph_disappearance_invalidates_existing_cursor(self):
        self.save_graph(relations=[self.relation("a", "b"), self.relation("b", "c", ("b", "c"))])
        first = q.relations(self.context, limits=q.QueryLimits(max_items=1))
        (self.root / "graph.json").unlink()
        self.assertEqual(q.relations(self.context, cursor=first["next_cursor"])["status"], "stale")

    def test_stale_evidence_reports_stale_not_absent_and_does_not_repair(self):
        self.save_graph(relations=[self.relation()])
        before = (self.root / "graph.json").read_bytes()
        self.write_note("a", b"new source\n")
        packet = q.relations(self.context)
        self.assertEqual(packet["items"][0]["currentness"], "stale")
        self.assertEqual((self.root / "graph.json").read_bytes(), before)
        self.assertEqual(q.search(self.ctx(["a.md"]), "new")["status"], "ok")

    def test_duplicate_keys_unknown_format_and_bad_shape_are_errors(self):
        for raw in ('{"nodes":[],"nodes":[],"links":[]}', '{"batang_graph_format":3}',
                    '{"nodes":[],"links":[{"source":"missing","target":"missing"}]}'):
            (self.root / "graph.json").write_text(raw)
            self.assertEqual(q.relations(self.context)["status"], "error")
        self.assertEqual(q.search(self.context, "첫")["status"], "ok")

    def test_graph_size_guard_is_preserved(self):
        (self.root / "graph.json").write_bytes(b" " * (g.MAX_GRAPH_BYTES + 1))
        self.assertEqual(q.relations(self.context)["status"], "error")

    def test_v1_preserves_direction_and_does_not_invent_support_or_status(self):
        nodes = g.document_nodes(self.active())
        a, b, c = [node["id"] for node in nodes]
        self.save_graph(version=1, directed=True, links=[{"source": a, "target": b, "relation": "links"},
                                                       {"source": b, "target": c}])
        packet = q.relations(self.context, operation="shortest_path", selector={"source": a, "target": c})
        self.assertEqual(len(packet["items"]), 2)
        self.assertIs(packet["directed"], True)
        self.assertNotIn("status", packet["items"][0]["record"])
        self.assertNotIn("support_sets", packet["items"][0]["record"])
        reverse = q.relations(self.context, operation="shortest_path", selector={"source": c, "target": a})
        self.assertEqual(reverse["items"], [])
        narrow = q.relations(self.ctx(["a.md", "c.md"]), operation="shortest_path",
                             selector={"source": a, "target": c})
        self.assertEqual(narrow["items"], [])

    def test_v2_bfs_single_shortest_path_and_depth_limit_respect_kind(self):
        self.save_graph(relations=[self.relation("a", "b"), self.relation("b", "c", ("b", "c"))])
        forward = q.relations(self.context, operation="shortest_path", selector={"source": "a", "target": "c"})
        self.assertEqual(len(forward["items"]), 2)
        reverse = q.relations(self.context, operation="shortest_path", selector={"source": "c", "target": "a"})
        self.assertEqual(reverse["items"], [])
        shallow = q.relations(self.context, operation="traverse", selector={"source": "a"},
                             limits=q.QueryLimits(max_depth=1))
        self.assertEqual(len(shallow["items"]), 1)
        self.save_graph(relations=[self.relation(kind="shares_topic")])
        backward = q.relations(self.context, operation="neighbors", selector={"source": "b"})
        self.assertEqual(len(backward["items"]), 1)

    def test_graph_cursor_rejects_graph_replacement(self):
        self.save_graph(relations=[self.relation("a", "b"), self.relation("b", "c", ("b", "c"))])
        limits = q.QueryLimits(max_items=1)
        first = q.relations(self.context, limits=limits)
        self.save_graph(relations=[self.relation()])
        self.assertEqual(q.relations(self.context, limits=limits, cursor=first["next_cursor"])["status"], "stale")


if __name__ == "__main__":
    unittest.main()
