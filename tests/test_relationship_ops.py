"""합성 원문으로 관계 참조·근거 수명·허용 범위와 단일 게시를 검사한다."""
import copy
import importlib.util
import json
from pathlib import Path
import random
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_graph_ops import GraphFixture, chunks_for, note, GRAPHIFY
import graph_ops as g
import file_ops as files
import relationship_ops as r


class RelationshipFixture(GraphFixture):
    def setUp(self):
        super().setUp()
        (self.vault / "outside.md").write_bytes(note("three", subject="같은 제목"))
        (self.vault / "ACTIVE.md").write_bytes(b"- [one](one.md)\n- [two](two.md)\n- [three](outside.md)\n")

    def request(self, targets, comparisons=None, relations=(), **extras):
        plan = r.discover_candidates(targets, comparisons)
        by_pair = {}
        for relation in relations:
            pair = tuple(sorted((relation["source_document_id"], relation["target_document_id"])))
            by_pair.setdefault(pair, []).append(relation["relation_id"])
        for pair in by_pair:
            if pair not in {(x["source_document_id"], x["target_document_id"]) for x in plan["candidates"]}:
                plan["candidates"].append({"source_document_id": pair[0], "target_document_id": pair[1], "signals": ["host_semantic"]})
        decisions = []
        for candidate in plan["candidates"]:
            pair = (candidate["source_document_id"], candidate["target_document_id"])
            ids = by_pair.get(pair, [])
            decisions.append({"source_document_id": pair[0], "target_document_id": pair[1],
                              "decision": "accepted" if ids else "no_relation", "relation_ids": ids,
                              "reason": "합성 원문을 비교한 단위시험 판단"})
        result = {"comparisons": comparisons, "candidate_plan": plan,
                  "decisions": decisions, "relations": list(relations)}
        result.update(extras)
        return result

    def relation(self, active, kind="shares_topic", qualifier="공통 주제", evidence_ids=("one", "two")):
        docs = {d.document_id: d for d in active.documents}
        evidence = [r.evidence_span(docs[i], 1, 1) for i in evidence_ids]
        support = {"support_id": r.support_set_id(evidence), "confidence": "EXTRACTED",
                   "evidence": evidence, "rationale": "합성 원문의 지정 구간 확인", "status": "active"}
        return {"relation_id": r.relation_id("one", "two", kind, qualifier),
                "source_document_id": "one", "target_document_id": "two", "kind": kind,
                "qualifier": qualifier, "support_sets": [support], "status": "active"}

    def update(self, active=None, *, request=None, expected_hash=None, suffix="fact", **extra):
        active = self.active() if active is None else active
        args = self.arguments(active, expected_hash=expected_hash,
                              chunks=chunks_for(active, suffix=suffix))
        args.update(extra)
        return g.refresh_graph(active, **args,
                               relationship_request=request if request is not None else self.request(active))

    def saved(self):
        return r.parse_envelope(self.graph_scope.read("graph.json").data)


class PureRelationshipContract(RelationshipFixture):
    def test_id_normalization_retains_direction_and_separates_meaning(self):
        self.assertEqual(r.relation_id("one", "two", "shares_topic", "  주제   A "),
                         r.relation_id("two", "one", "shares_topic", "주제 A"))
        self.assertNotEqual(r.relation_id("one", "two", "references", "참조"),
                            r.relation_id("two", "one", "references", "참조"))
        self.assertNotEqual(r.relation_id("one", "two", "references", "참조"),
                            r.relation_id("one", "two", "references", "다른 범위"))
        self.assertNotEqual(r.relation_id("one", "two", "references", "참조"),
                            r.relation_id(" one", "two", "references", "참조"))

    def test_span_is_body_bytes_with_line_endings(self):
        doc = self.active().documents[0]
        import hashlib
        self.assertEqual(r.evidence_span(doc, 1, 2)["span_sha256"], hashlib.sha256(doc.body).hexdigest())
        for start, end in [(0, 1), (1, 20), (True, 1), (2, 1)]:
            with self.subTest(start=start, end=end), self.assertRaises(g.GraphError):
                r.evidence_span(doc, start, end)

    def test_unknown_envelope_duplicate_relations_and_forged_ids_rejected(self):
        empty = r._empty()
        for field, value in [("batang_graph_format", 3), ("batang_graph_format", True), ("nodes", [])]:
            bad = copy.deepcopy(empty)
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(g.GraphError):
                r.parse_envelope(bad)
        relation = self.relation(self.active())
        bad = dict(empty, relations=[relation, relation])
        with self.assertRaisesRegex(g.GraphError, "duplicate_assertion"):
            r.parse_envelope(bad)
        relation["relation_id"] = "forged"
        with self.assertRaisesRegex(g.GraphError, "assertion_id"):
            r.parse_envelope(dict(empty, relations=[relation]))

    def test_discovery_never_reads_outside_explicit_scope_and_does_not_accept_tags(self):
        selected = self.active(["one.md"])
        comparisons = self.active(["two.md"])
        before = {p: (self.vault / p).read_bytes() for p in self.paths}
        plan = r.discover_candidates(selected, comparisons)
        self.assertEqual(plan["considered_document_ids"], ["one", "two"])
        self.assertEqual(len(plan["candidates"]), 1)
        self.assertNotIn("relations", plan)
        self.assertEqual(before, {p: (self.vault / p).read_bytes() for p in self.paths})

    def test_comparison_active_snapshot_mismatch_is_rejected(self):
        selected = self.active(["one.md"])
        comparison = self.active(["two.md"])
        forged = g.ActiveDocuments(comparison.scope, comparison.active_path, "0" * 64, comparison.documents)
        with self.assertRaisesRegex(g.GraphError, "comparison_scope"):
            r.discover_candidates(selected, forged)

    def test_legacy_conversion_preserves_cross_edges_without_promoting_relations(self):
        active = self.active()
        nodes = g.document_nodes(active)
        cross = {"source": nodes[0]["id"], "target": nodes[1]["id"], "relation": "legacy", "custom": "retain"}
        old = {"nodes": nodes, "links": [cross], "graph": {"legacy": "retain"}}
        envelope = r.parse_envelope(r.migrate_graph(json.dumps(old).encode()))
        self.assertEqual(envelope["content_graph"]["links"], [cross])
        self.assertEqual(envelope["relations"], [])
        self.assertEqual(r.project_graph(envelope, active)["links"], [])
        with self.assertRaisesRegex(g.GraphError, "graph_shape_invalid"):
            g._graph_data(envelope)


class CandidateComputationContract(GraphFixture):
    """독립 기대 쌍과 신호로 호출 안의 계산 재사용·범위 보존을 검사한다."""

    def setUp(self):
        super().setUp()
        self.identifiers = ["id-alpha", "id-bravo", "id-charlie", "id-delta", "id-echo"]
        self.paths = tuple(identifier + ".md" for identifier in self.identifiers)
        bodies = ["commonword [[Alias Delta]]\n", "commonword\n", "uniqueword\n",
                  "different\n", "uniqueword\n"]
        for index, (identifier, path, body) in enumerate(zip(self.identifiers, self.paths, bodies)):
            metadata, _ = files.parse_document(note(identifier, subject="subject" + str(index)))
            metadata["tags"] = ["sharedmeta" if index < 2 else "tag" + str(index)]
            if index == 3:
                metadata["aliases"] = ["Alias Delta"]
            (self.vault / path).write_bytes(files.serialize_document(metadata, body.encode()))
        self.index_bytes = "".join(f"- [{identifier}]({path})\n"
                                   for identifier, path in zip(self.identifiers, self.paths)).encode()
        (self.vault / "ACTIVE.md").write_bytes(self.index_bytes)
        self.note_scope = files.FileScope(str(self.vault), ["ACTIVE.md", *self.paths])
        a, b, c, d, e = self.identifiers
        self.expected_signals = {(a, b): ["body_terms", "metadata_terms"],
                                 (a, d): ["explicit_reference"], (c, e): ["body_terms"]}

    def selected(self, identifiers):
        return self.active([identifier + ".md" for identifier in identifiers])

    def expected_plan(self, targets, comparisons):
        considered = set(targets) | set(comparisons)
        candidates = [{"source_document_id": pair[0], "target_document_id": pair[1], "signals": signals}
                      for pair, signals in sorted(self.expected_signals.items())
                      if set(pair).issubset(considered) and set(pair) & set(targets)]
        return {"method": "explicit-metadata-body-existing", "status": "complete",
                "considered_document_ids": sorted(considered), "candidates": candidates, "omissions": []}

    def history_envelope(self):
        active = self.active()
        docs = {doc.document_id: doc for doc in active.documents}
        a, _, c, _, e = self.identifiers
        evidence = [r.evidence_span(docs[a], 1, 1)]
        relation = {"relation_id": r.relation_id(c, e, "supports", "제삼 문서 근거"),
                    "source_document_id": c, "target_document_id": e, "kind": "supports",
                    "qualifier": "제삼 문서 근거", "status": "active",
                    "support_sets": [{"support_id": r.support_set_id(evidence), "confidence": "EXTRACTED",
                                      "evidence": evidence, "rationale": "합성 근거", "status": "active"}]}
        envelope = r._empty()
        envelope["content_graph"]["nodes"] = g.document_nodes(active)
        envelope["relations"] = [relation]
        envelope["relation_review"] = [{
            "review_id": "legacy-deferred", "candidate_status": "complete", "relation_status": "partial",
            "documents": [{"document_id": doc.document_id, "path": doc.path, "source_sha256": doc.sha256}
                          for doc in active.documents],
            "decisions": [{"source_document_id": c, "target_document_id": e, "decision": "deferred",
                           "relation_ids": [], "reason": "판단 보류"}]}]
        return envelope

    def test_discovery_exact_signals_and_order_including_target_on_right(self):
        a, b, c, d, e = self.identifiers
        for targets, comparisons in [([a, c], [b, d, e]), ([d, e], [a, b, c]),
                                     ([c, a], [e, d, c, b, a]), (self.identifiers, [])]:
            with self.subTest(targets=targets, comparisons=comparisons):
                self.assertEqual(r.discover_candidates(self.selected(targets), self.selected(comparisons)),
                                 self.expected_plan(targets, comparisons))

    def test_randomized_scope_overlap_and_order_match_independent_expected_pairs(self):
        randomizer = random.Random(20261110)
        for _ in range(48):
            targets = randomizer.sample(self.identifiers, randomizer.randrange(6))
            comparisons = randomizer.sample(self.identifiers, randomizer.randrange(6))
            with self.subTest(targets=targets, comparisons=comparisons):
                self.assertEqual(r.discover_candidates(self.selected(targets), self.selected(comparisons)),
                                 self.expected_plan(targets, comparisons))

    def test_default_comparisons_empty_targets_and_single_document(self):
        for identifiers in ([], self.identifiers[:1], self.identifiers[:2], self.identifiers):
            targets = self.selected(identifiers)
            with self.subTest(identifiers=identifiers):
                self.assertEqual(r.discover_candidates(targets), self.expected_plan(identifiers, identifiers))
        with patch.object(r, "_candidate_features", wraps=r._candidate_features) as features:
            self.assertEqual(r.discover_candidates(self.selected([]), self.active()),
                             self.expected_plan([], self.identifiers))
        features.assert_not_called()

    def test_target_pairs_only_emit_relevant_unique_pairs_in_original_order(self):
        expected = [("a", "b"), ("a", "d"), ("b", "c"), ("b", "d"), ("c", "d")]
        self.assertEqual(list(r._target_pairs(["d", "b", "a", "c"], {"b", "d"})), expected)
        self.assertEqual(list(r._target_pairs(["a", "b", "c"], set())), [])
        self.assertEqual(list(r._target_pairs(["a", "b", "c"], {"a", "b", "c"})),
                         [("a", "b"), ("a", "c"), ("b", "c")])

    def test_features_terms_and_body_decode_once_per_document_per_call(self):
        decodes = []

        class CountedBody(bytes):
            def decode(self, *args, **kwargs):
                decodes.append(self)
                return super().decode(*args, **kwargs)

        active = self.active()
        documents = tuple(g.Document(doc.scope, doc.path, doc.sha256, doc.metadata, CountedBody(doc.body))
                          for doc in active.documents)
        counted = g.ActiveDocuments(active.scope, active.active_path, active.active_sha256, documents)
        with patch.object(r, "_terms", wraps=r._terms) as terms, \
                patch.object(r, "_candidate_features", wraps=r._candidate_features) as features:
            self.assertEqual(r.discover_candidates(counted), self.expected_plan(self.identifiers, self.identifiers))
        self.assertEqual(features.call_count, 5)
        self.assertEqual(terms.call_count, 5)
        self.assertEqual(len(decodes), 5)
        # 다음 호출은 변경된 snapshot에서 다시 계산하며 영속 캐시를 공유하지 않는다.
        path = self.vault / self.paths[0]
        metadata, _ = files.parse_document(path.read_bytes())
        path.write_bytes(files.serialize_document(metadata, b"changedword\n"))
        current = self.active()
        with patch.object(r, "_candidate_features", wraps=r._candidate_features) as features:
            changed = r.discover_candidates(current)
        self.assertEqual(features.call_count, 5)
        expected = self.expected_plan(self.identifiers, self.identifiers)
        expected["candidates"] = [dict(item, signals=["metadata_terms"])
                                  if item["target_document_id"] == self.identifiers[1] else item
                                  for item in expected["candidates"]
                                  if item["target_document_id"] != self.identifiers[3]]
        self.assertEqual(changed, expected)

    def test_explicit_link_forms_keep_alias_path_fragment_and_literal_id_behavior(self):
        a, _, _, d, _ = self.identifiers
        path = self.vault / (a + ".md")
        metadata, _ = files.parse_document(path.read_bytes())
        for body in ("[[Alias Delta#section|label]]", "[label](id-delta.md#section)",
                     "[label](Alias%20Delta)", "text " + d + " suffix"):
            path.write_bytes(files.serialize_document(metadata, (body + "\n").encode()))
            with self.subTest(body=body):
                plan = r.discover_candidates(self.selected([a]), self.selected([d]))
                self.assertEqual(plan["candidates"], [{"source_document_id": a, "target_document_id": d,
                                                       "signals": ["explicit_reference"]}])

    def test_duplicate_snapshots_stale_sources_and_missing_comparison_are_not_bypassed(self):
        active = self.active()
        duplicate = g.ActiveDocuments(active.scope, active.active_path, active.active_sha256,
                                      active.documents + active.documents[:1])
        self.assertEqual(r.discover_candidates(duplicate, active),
                         self.expected_plan(self.identifiers, self.identifiers))
        stale = self.selected(self.identifiers[:1])
        with (self.vault / self.paths[0]).open("ab") as stream:
            stream.write(b"changed\n")
        with patch.object(r, "_candidate_features", wraps=r._candidate_features) as features:
            with self.assertRaisesRegex(files.ConflictError, "graph_source_changed"):
                r.discover_candidates(stale, self.selected(self.identifiers[1:]))
        features.assert_not_called()
        current_comparisons = self.selected(self.identifiers[1:2])
        (self.vault / self.paths[1]).unlink()
        with patch.object(r, "_candidate_features", wraps=r._candidate_features) as features:
            with self.assertRaises(FileNotFoundError):
                r.discover_candidates(self.selected(self.identifiers[:1]), current_comparisons)
        features.assert_not_called()

    def test_different_current_documents_with_duplicate_id_still_fail_before_computation(self):
        a, b = self.identifiers[:2]
        path = self.vault / (b + ".md")
        metadata, body = files.parse_document(path.read_bytes())
        metadata["batang_id"] = a
        path.write_bytes(files.serialize_document(metadata, body))
        with patch.object(r, "_candidate_features", wraps=r._candidate_features) as features:
            with self.assertRaisesRegex(g.GraphError, "relationship_document_collision"):
                r.discover_candidates(self.selected([a]), self.selected([b]))
        features.assert_not_called()

    def test_history_third_document_deferred_and_unavailable_omission_are_preserved(self):
        a, _, c, _, e = self.identifiers
        envelope = self.history_envelope()
        original = copy.deepcopy(envelope)
        plan = r.discover_candidates(self.selected([a]), self.selected([c, e]), envelope)
        self.assertEqual(plan, {"method": "explicit-metadata-body-existing", "status": "complete",
                               "considered_document_ids": [a, c, e], "omissions": [],
                               "candidates": [{"source_document_id": c, "target_document_id": e,
                                               "signals": ["existing_relation", "unresolved_deferred"]}]})
        plan = r.discover_candidates(self.selected([a]), self.selected([c]), envelope)
        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["candidates"], [])
        self.assertEqual(plan["omissions"], ["unresolved_deferred_endpoint_unavailable"])
        self.assertEqual(envelope, original)

    def test_projection_reuses_node_map_and_preserves_current_missing_stale_and_duplicate_behavior(self):
        active = self.active()
        envelope = r._empty()
        envelope["content_graph"]["nodes"] = g.document_nodes(active)
        expected = {"directed": False, "multigraph": False, "graph": {}, "links": [],
                    "nodes": copy.deepcopy(envelope["content_graph"]["nodes"])}
        with patch.object(r, "_node_map", wraps=r._node_map) as node_map:
            self.assertEqual(r.project_graph(envelope, active), expected)
        self.assertEqual(node_map.call_count, 1)
        for change in ("missing", "stale", "duplicate"):
            changed = copy.deepcopy(envelope)
            nodes = changed["content_graph"]["nodes"]
            if change == "missing":
                nodes.pop(0)
            elif change == "stale":
                nodes[0]["source_sha256"] = "0" * 64
            else:
                nodes.append(dict(nodes[0], id="duplicate-document-node"))
            with self.subTest(change=change), patch.object(r, "_node_map", wraps=r._node_map) as node_map:
                projection = r.project_graph(changed, active)
                self.assertEqual(projection["nodes"], [] if change == "duplicate" else expected["nodes"][1:])
                self.assertEqual(projection["links"], [])
                self.assertEqual(node_map.call_count, 1)
        with patch.object(r, "_node_map", wraps=r._node_map) as node_map:
            self.assertEqual(r.project_graph(envelope, self.selected([]))["nodes"], [])
        node_map.assert_not_called()


@unittest.skipUnless(GRAPHIFY and sys.platform == "darwin", "실제 Graphify와 macOS 저장 도우미 필요")
class RelationshipUpdates(RelationshipFixture):
    def test_first_v2_write_accepts_relationship_and_records_scope(self):
        active = self.active()
        relation = self.relation(active)
        result = self.update(active, request=self.request(active, relations=[relation]))
        self.assertEqual((result.status, result.candidate_status, result.relation_status), ("current", "complete", "complete"), result)
        value = self.saved()
        self.assertEqual(value["relations"], [relation])
        self.assertEqual(value["relation_review"][0]["review_id"], result.review_id)
        projected = r.project_graph(value, active)
        self.assertEqual(len([e for e in projected["links"] if e.get("assertion_ids")]), 1)

    def test_incremental_existing_endpoint_does_not_reextract_comparison(self):
        self.assertEqual(self.update().status, "current")
        old = self.graph_scope.read("graph.json")
        before = self.saved()
        target, comparisons = self.active(["one.md"]), self.active(["two.md"])
        relation = self.relation(self.active())
        result = self.update(target, request=self.request(target, comparisons, [relation]), expected_hash=old.sha256, suffix="new")
        self.assertEqual(result.status, "current", result)
        after = self.saved()
        for node in before["content_graph"]["nodes"]:
            if node.get("source_file") == "two.md":
                self.assertIn(node, after["content_graph"]["nodes"])
        self.assertIn(relation, after["relations"])

    def test_comparison_stale_or_outside_endpoint_preserves_graph(self):
        self.update()
        old = self.graph_scope.read("graph.json")
        (self.vault / "two.md").write_bytes((self.vault / "two.md").read_bytes() + b"changed\n")
        all_docs = self.active()
        target, comparisons = self.active(["one.md"]), self.active(["two.md"])
        relation = self.relation(all_docs)
        result = self.update(target, request=self.request(target, comparisons, [relation]), expected_hash=old.sha256)
        self.assertEqual(result.error_code, "relationship_endpoint_stale", result)
        self.assertEqual(self.graph_scope.read("graph.json").data, old.data)
        request = self.request(target, relations=[relation])
        result = self.update(target, request=request, expected_hash=old.sha256)
        self.assertEqual(result.status, "pending")
        self.assertEqual(self.graph_scope.read("graph.json").data, old.data)

    def test_forged_evidence_span_or_missing_chunk_never_publishes(self):
        active = self.active()
        self.update()
        old = self.graph_scope.read("graph.json")
        relation = self.relation(active)
        relation["support_sets"][0]["evidence"][0]["span_sha256"] = "0" * 64
        relation["support_sets"][0]["support_id"] = r.support_set_id(relation["support_sets"][0]["evidence"])
        result = self.update(active, request=self.request(active, relations=[relation]), expected_hash=old.sha256)
        self.assertEqual(result.error_code, "relationship_evidence_stale", result)
        args = self.arguments(active, expected_hash=old.sha256)
        args["chunks"] = args["chunks"][:-1]
        result = g.refresh_graph(active, **args, relationship_request=self.request(active))
        self.assertEqual(result.error_code, "extraction_incomplete", result)
        self.assertEqual(self.graph_scope.read("graph.json").data, old.data)

    def test_multiple_kinds_and_directions_project_to_one_edge(self):
        active = self.active()
        first = self.relation(active)
        second = self.relation(active, "references", "明示参照")
        third = copy.deepcopy(second)
        third["source_document_id"], third["target_document_id"] = "two", "one"
        third["relation_id"] = r.relation_id("two", "one", "references", third["qualifier"])
        result = self.update(active, request=self.request(active, relations=[first, second, third]))
        self.assertEqual(result.status, "current", result)
        projected = r.project_graph(self.saved(), active)
        cross = [e for e in projected["links"] if e.get("assertion_ids")]
        self.assertEqual(len(cross), 1)
        self.assertEqual(len(cross[0]["assertion_ids"]), 3)
        self.assertFalse(projected["directed"])

    def test_zero_relationships_is_valid_but_unreviewed_candidates_are_partial(self):
        active = self.active()
        request = self.request(active)
        result = self.update(active, request=request)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        old = self.graph_scope.read("graph.json")
        request["decisions"] = []
        result = self.update(active, request=request, expected_hash=old.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "partial"), result)
        self.assertEqual(len(self.saved()["relation_review"]), 2)

    def test_omitted_scope_cannot_be_complete_and_deferred_is_partial(self):
        active = self.active()
        request = self.request(active)
        request["candidate_plan"]["omissions"] = ["예산으로 일부 의미 비교를 유보"]
        request["decisions"][0].update(decision="deferred", relation_ids=[])
        result = self.update(active, request=request)
        self.assertEqual((result.candidate_status, result.relation_status), ("partial", "partial"), result)

    def test_endpoint_content_change_marks_old_relation_stale_without_new_support(self):
        active = self.active()
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]))
        old = self.graph_scope.read("graph.json")
        (self.vault / "one.md").write_bytes((self.vault / "one.md").read_bytes() + b"changed\n")
        target, comparisons = self.active(["one.md"]), self.active(["two.md"])
        result = self.update(target, request=self.request(target, comparisons), expected_hash=old.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "partial"), result)
        self.assertEqual(self.saved()["relations"][0]["status"], "stale")
        self.assertFalse([x for x in r.project_graph(self.saved(), self.active())["links"] if x.get("assertion_ids")])

    def test_retract_one_independent_support_retains_other_and_full_retract_removes_active(self):
        active = self.active()
        relation = self.relation(active, evidence_ids=("three",))
        second = self.relation(active)["support_sets"][0]
        relation["support_sets"].append(second)
        self.update(active, request=self.request(active, relations=[relation]))
        old = self.graph_scope.read("graph.json")
        target, comparisons = self.active(["one.md"]), self.active(["two.md", "outside.md"])
        retract = [{"relation_id": relation["relation_id"], "support_ids": [second["support_id"]], "reason": "명시 철회"}]
        request = self.request(target, comparisons, retract_supports=retract)
        for decision in request["decisions"]:
            if {decision["source_document_id"], decision["target_document_id"]} == {"one", "two"}:
                decision.update(decision="accepted", relation_ids=[relation["relation_id"]])
        result = self.update(target, request=request, expected_hash=old.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertEqual(self.saved()["relations"][0]["status"], "active")
        old = self.graph_scope.read("graph.json")
        retract[0]["support_ids"] = [s["support_id"] for s in relation["support_sets"]]
        result = self.update(target, request=self.request(target, comparisons, retract_supports=retract), expected_hash=old.sha256)
        self.assertEqual(result.status, "current", result)
        self.assertEqual(self.saved()["relations"][0]["status"], "retracted")

    def test_permission_loss_preserves_record_but_hides_relation(self):
        active = self.active()
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]))
        old = self.graph_scope.read("graph.json")
        target = self.active(["one.md"])
        result = self.update(target, request=self.request(target, unavailable_document_ids=["two"]), expected_hash=old.sha256)
        self.assertEqual(result.status, "current", result)
        self.assertEqual(self.saved()["relations"][0]["status"], "unavailable")
        projected = r.project_graph(self.saved(), target)
        self.assertNotIn("two", {n.get("document_id") for n in projected["nodes"]})
        self.assertEqual(projected["graph"], {})
        self.assertFalse([e for e in projected["links"] if e.get("assertion_ids")])

    def test_explicit_unregistration_can_retract_relations_without_reextracting_notes(self):
        active = self.active()
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]))
        old = self.graph_scope.read("graph.json")
        original_content = self.saved()["content_graph"]
        (self.vault / "ACTIVE.md").write_bytes(b"- [one](one.md)\n- [three](outside.md)\n")
        targets, comparisons = self.active([]), self.active(["one.md"])
        request = self.request(targets, comparisons, removed_document_ids=["two"],
                               affected_relation_ids=[relation["relation_id"]])
        result = self.update(targets, request=request, expected_hash=old.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertEqual(self.saved()["relations"][0]["status"], "retracted")
        self.assertEqual(self.saved()["content_graph"], original_content)
        self.assertTrue((self.vault / "two.md").exists())

    def test_projection_requires_all_evidence_in_one_complete_support_set(self):
        active = self.active()
        relation = self.relation(active, evidence_ids=("one", "two", "three"))
        self.update(active, request=self.request(active, relations=[relation]))
        permitted = self.active(["one.md", "two.md"])
        projected = r.project_graph(self.saved(), permitted)
        self.assertFalse([e for e in projected["links"] if e.get("assertion_ids")])

    def test_idempotent_request_does_not_duplicate_review_and_read_only_does_not_write(self):
        active = self.active()
        request = self.request(active)
        self.update(active, request=request)
        old = self.graph_scope.read("graph.json")
        result = self.update(active, request=request, expected_hash=old.sha256)
        self.assertEqual(result.status, "current", result)
        self.assertEqual(len(self.saved()["relation_review"]), 1)
        args = self.arguments(active, expected_hash=self.graph_scope.read("graph.json").sha256)
        result = g.refresh_graph(active, **args, relationship_request=request, read_only=True)
        self.assertEqual(result.status, "current", result)
        self.assertFalse((self.work / args["baseline_path"]).exists())

    def test_v1_requires_explicit_migration_and_legacy_writer_rejects_v2(self):
        active = self.active()
        first = g.refresh_graph(active, **self.arguments(active))
        self.assertEqual(first.status, "current")
        old = self.graph_scope.read("graph.json")
        result = self.update(active, expected_hash=old.sha256)
        self.assertEqual(result.error_code, "relationship_format_invalid", result)
        self.assertEqual(self.graph_scope.read("graph.json").data, old.data)
        args = self.arguments(active, expected_hash=old.sha256)
        args.pop("chunks"); args.pop("expected_chunk_ids")
        migration = r.publish_migration(active, **args)
        self.assertTrue(migration["graph_written"])
        current = self.graph_scope.read("graph.json")
        result = g.refresh_graph(active, **self.arguments(active, expected_hash=current.sha256))
        self.assertEqual(result.error_code, "graph_shape_invalid", result)
        self.assertEqual(self.graph_scope.read("graph.json").data, current.data)

    def test_restore_keeps_current_v2_backup_and_requires_expected_hash(self):
        active = self.active()
        legacy = json.dumps({"nodes": g.document_nodes(active), "links": []}).encode()
        self.update(active)
        current = self.graph_scope.read("graph.json")
        backups = files.FileScope(str(self.backups), ["restore.json"])
        with self.assertRaises(ConflictError):
            r.restore_graph(graph_scope=self.graph_scope, graph_path="graph.json", expected_graph_sha256="0" * 64,
                            restore_bytes=legacy, backup_scope=backups, backup_path="restore.json")
        result = r.restore_graph(graph_scope=self.graph_scope, graph_path="graph.json", expected_graph_sha256=current.sha256,
                                 restore_bytes=legacy, backup_scope=backups, backup_path="restore.json")
        self.assertTrue(result["graph_written"])
        self.assertEqual(backups.read("restore.json").data, current.data)
        self.assertEqual(self.graph_scope.read("graph.json").data, legacy)

    def _legacy_cross_source_reextract(self, source_path, document_id):
        active = self.active()
        self.assertEqual(g.refresh_graph(active, **self.arguments(active)).status, "current")
        original = g._graph_data(self.graph_scope.read("graph.json").data)
        nodes = {n["id"]: n for n in original["nodes"]}
        doc_nodes = {n["document_id"]: n for n in g.document_nodes(active)}
        cross = {"source": doc_nodes["two"]["id"], "target": "one_fact", "relation": "legacy cross",
                 "source_file": source_path, "document_id": document_id,
                 "_origin": "semantic", "confidence": "EXTRACTED", "custom": {"keep": [1, 2]}}
        original["links"].append(cross)
        (self.root / "graph.json").write_bytes(r._encoded(original))
        before = self.graph_scope.read("graph.json")
        migration_args = self.arguments(active, expected_hash=before.sha256)
        migration_args.pop("chunks"); migration_args.pop("expected_chunk_ids")
        self.assertEqual(r.publish_migration(active, **migration_args)["status"], "current")
        before = self.graph_scope.read("graph.json")
        target = self.active(["one.md"])
        comparison = self.active(["two.md"])
        result = self.update(target, request=self.request(target, comparison), expected_hash=before.sha256, suffix="new")
        self.assertEqual(result.status, "current", result)
        saved = self.saved()
        self.assertNotIn("one_fact", {n["id"] for n in saved["content_graph"]["nodes"]})
        archive = saved["content_graph"]["graph"]["batang_legacy_relations"]
        self.assertEqual(len(archive["records"]), 1)
        record = archive["records"][0]
        self.assertEqual(record["edge"], cross)
        self.assertEqual(record["directed"], original["directed"])
        self.assertEqual({n["id"]: n for n in record["nodes"]},
                         {i: nodes[i] for i in (cross["source"], cross["target"])})
        self.assertFalse(any(e.get("relation") == "legacy cross" for e in r.project_graph(saved, self.active())["links"]))
        before = self.graph_scope.read("graph.json")
        result = self.update(target, request=self.request(target, comparison), expected_hash=before.sha256, suffix="newer")
        self.assertEqual(result.status, "current", result)
        self.assertEqual(self.saved()["content_graph"]["graph"]["batang_legacy_relations"], archive)

    def test_legacy_comparison_source_cross_edge_keeps_raw_endpoints_after_target_reextract(self):
        self._legacy_cross_source_reextract("two.md", "two")

    def test_legacy_target_source_cross_edge_is_archived_before_source_replacement(self):
        self._legacy_cross_source_reextract("one.md", "one")

    def test_legacy_archive_collision_or_unknown_version_is_rejected(self):
        active = self.active()
        for archive in ("old user value", {"archive_version": 9, "records": []}):
            value = r._empty()
            value["content_graph"]["graph"]["batang_legacy_relations"] = archive
            with self.subTest(archive=archive), self.assertRaisesRegex(g.GraphError, "legacy_archive_invalid"):
                r.parse_envelope(value)

    def test_legacy_archive_checks_cumulative_budget_before_copying_large_hub(self):
        active = self.active()
        self.update(active)
        value = self.saved()
        graph = value["content_graph"]
        hub = next(n for n in graph["nodes"] if n["id"] == "one_fact")
        hub["large_attribute"] = "x" * 4096
        for number in range(6):
            identifier = "legacy_leaf_" + str(number)
            graph["nodes"].append({"id": identifier, "label": identifier, "file_type": "concept",
                                   "source_file": "two.md", "document_id": "two", "_origin": "semantic"})
            graph["links"].append({"source": identifier, "target": "one_fact", "relation": "legacy",
                                   "source_file": "two.md", "document_id": "two", "_origin": "semantic"})
        raw = r._encoded(value)
        (self.root / "graph.json").write_bytes(raw)
        old = self.graph_scope.read("graph.json")
        target, comparisons = self.active(["one.md"]), self.active(["two.md", "outside.md"])
        request = self.request(target, comparisons)
        args = self.arguments(target, expected_hash=old.sha256)
        copied_records = []
        original_copy = copy.deepcopy
        def counted(value, *a, **kw):
            if isinstance(value, dict) and set(value) == {"record_id", "directed", "edge", "nodes"}:
                copied_records.append(value["record_id"])
            return original_copy(value, *a, **kw)
        with patch.object(g, "MAX_GRAPH_BYTES", len(raw) + 512), patch.object(r.copy, "deepcopy", counted):
            result = g.refresh_graph(target, **args, relationship_request=request)
        self.assertEqual((result.status, result.error_code), ("pending", "graph_data_size"), result)
        self.assertFalse(result.publication_uncertain)
        self.assertLess(len(copied_records), 6)
        self.assertEqual(self.graph_scope.read("graph.json").data, raw)
        self.assertFalse((self.work / args["candidate_path"]).exists())

    def test_accepted_unaffected_relation_requires_current_evidence_for_complete_review(self):
        (self.vault / "four.md").write_bytes(note("four", subject="독립 근거"))
        index = self.vault / "ACTIVE.md"
        index.write_bytes(index.read_bytes() + b"- [four](four.md)\n")
        self.note_scope = files.FileScope(str(self.vault),
                                          ["ACTIVE.md", "one.md", "two.md", "outside.md", "four.md"])
        all_docs = self.active()
        old_relation = self.relation(all_docs, "supports", "기존 판정", evidence_ids=("four",))
        result = self.update(all_docs, request=self.request(all_docs, relations=[old_relation]))
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        old = self.graph_scope.read("graph.json")
        preserved = copy.deepcopy(self.saved()["relations"][0])
        target = self.active(["outside.md"])
        comparisons = self.active(["one.md", "two.md"])
        new_relation = self.relation(all_docs, "supports", "새 판정", evidence_ids=("three",))
        request = self.request(target, comparisons, [new_relation])
        for decision in request["decisions"]:
            if {decision["source_document_id"], decision["target_document_id"]} == {"one", "two"}:
                decision["relation_ids"] = [old_relation["relation_id"], new_relation["relation_id"]]
        result = self.update(target, request=request, expected_hash=old.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "partial"), result)
        saved = self.saved()
        self.assertEqual(next(x for x in saved["relations"] if x["relation_id"] == old_relation["relation_id"]), preserved)
        review = next(x for x in saved["relation_review"] if x["review_id"] == result.review_id)
        conflict = next(x for x in review["decision_conflicts"] if x["reason"] == "accepted_relations_unverified")
        self.assertEqual(conflict["unverified_relation_ids"], [old_relation["relation_id"]])
        # 같은 기존 관계도 현재 허용된 근거를 다시 확인하면 complete가 가능하다.
        before = self.graph_scope.read("graph.json")
        request["comparisons"] = self.active(["one.md", "two.md", "four.md"])
        request["candidate_plan"] = r.discover_candidates(target, request["comparisons"])
        request["candidate_plan"]["candidates"].append({"source_document_id": "one", "target_document_id": "two", "signals": ["host_semantic"]})
        request["decisions"] = [{"source_document_id": c["source_document_id"],
                                 "target_document_id": c["target_document_id"], "decision": "no_relation",
                                 "relation_ids": [], "reason": "합성 현재 원문 비교"}
                                for c in request["candidate_plan"]["candidates"]]
        for decision in request["decisions"]:
            if {decision["source_document_id"], decision["target_document_id"]} == {"one", "two"}:
                decision.update(decision="accepted", relation_ids=[old_relation["relation_id"], new_relation["relation_id"]])
        result = self.update(target, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertEqual(next(x for x in self.saved()["relations"] if x["relation_id"] == old_relation["relation_id"]), preserved)
        # 읽기 허용된 근거라도 현재 hash가 바뀌었으면 완료로 승격하지 않는다.
        before = self.graph_scope.read("graph.json")
        evidence_path = self.vault / "four.md"
        evidence_path.write_bytes(evidence_path.read_bytes() + b"changed evidence\n")
        request["comparisons"] = self.active(["one.md", "two.md", "four.md"])
        result = self.update(target, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "partial"), result)
        self.assertEqual(next(x for x in self.saved()["relations"] if x["relation_id"] == old_relation["relation_id"]), preserved)

    def test_no_relation_with_surviving_independent_support_is_partial(self):
        active = self.active()
        relation = self.relation(active, evidence_ids=("three",))
        second = self.relation(active)["support_sets"][0]
        relation["support_sets"].append(second)
        self.update(active, request=self.request(active, relations=[relation]))
        old = self.graph_scope.read("graph.json")
        target, comparisons = self.active(["one.md"]), self.active(["two.md", "outside.md"])
        request = self.request(target, comparisons, retract_supports=[{
            "relation_id": relation["relation_id"], "support_ids": [second["support_id"]], "reason": "일부 근거 철회"}])
        result = self.update(target, request=request, expected_hash=old.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "partial"), result)
        saved = self.saved()
        self.assertEqual(saved["relations"][0]["status"], "active")
        review = next(x for x in saved["relation_review"] if x["review_id"] == result.review_id)
        self.assertEqual(review["decision_conflicts"][0]["reason"], "active_relations_remain")
        self.assertEqual(review["decisions"][0]["decision"], "no_relation")
        request["candidate_plan"]["status"] = "not_run"
        before = self.graph_scope.read("graph.json")
        result = self.update(target, request=request, expected_hash=before.sha256)
        self.assertEqual((result.candidate_status, result.relation_status), ("not_run", "partial"), result)

    def test_explicit_rename_retains_relation_id_without_changing_other_documents(self):
        active = self.active()
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]))
        original = self.saved()
        ast = {"id": "kept_ast", "label": "AST", "file_type": "code", "source_file": "one.md",
               "source_location": "L1", "_origin": "ast"}
        original["content_graph"]["nodes"].append(ast)
        (self.root / "graph.json").write_bytes(r._encoded(original))
        old = self.graph_scope.read("graph.json")
        old_value = self.saved()
        (self.vault / "one.md").rename(self.vault / "renamed.md")
        (self.vault / "ACTIVE.md").write_bytes(b"- [one](renamed.md)\n- [two](two.md)\n- [three](outside.md)\n")
        self.note_scope = files.FileScope(str(self.vault), ["ACTIVE.md", "renamed.md", "two.md", "outside.md"])
        target = self.active(["renamed.md"])
        comparison = self.active(["two.md"])
        request = self.request(target, comparison)
        result = self.update(target, request=request, expected_hash=old.sha256)
        self.assertEqual(result.error_code, "relationship_rename_required", result)
        request["renamed_documents"] = [{"document_id": "one", "old_path": "one.md", "new_path": "renamed.md"}]
        request["decisions"][0].update(decision="accepted", relation_ids=[relation["relation_id"]])
        result = self.update(target, request=request, expected_hash=old.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        saved = self.saved()
        self.assertEqual(saved["relations"][0]["relation_id"], relation["relation_id"])
        self.assertEqual(saved["relations"][0]["status"], "active")
        self.assertIn(ast, saved["content_graph"]["nodes"])
        for node in old_value["content_graph"]["nodes"]:
            if node.get("source_file") == "two.md":
                self.assertIn(node, saved["content_graph"]["nodes"])

    def test_target_as_third_evidence_source_can_support_existing_document_pair(self):
        self.update()
        old = self.graph_scope.read("graph.json")
        all_docs = self.active()
        target, comparisons = self.active(["outside.md"]), self.active(["one.md", "two.md"])
        relation = self.relation(all_docs, "supports", "독립 출처 비교", evidence_ids=("three",))
        result = self.update(target, request=self.request(target, comparisons, [relation]), expected_hash=old.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertEqual(self.saved()["relations"][0]["relation_id"], relation["relation_id"])

    def test_migration_post_write_error_is_uncertain_and_preserves_backup(self):
        active = self.active()
        first = g.refresh_graph(active, **self.arguments(active))
        self.assertEqual(first.status, "current")
        old = self.graph_scope.read("graph.json")
        args = self.arguments(active, expected_hash=old.sha256)
        args.pop("chunks"); args.pop("expected_chunk_ids")
        write = self.graph_scope.write
        def changed(*a, **kw):
            result = write(*a, **kw)
            (self.vault / "one.md").write_bytes((self.vault / "one.md").read_bytes() + b"changed\n")
            return result
        with patch.object(self.graph_scope, "write", changed):
            result = r.publish_migration(active, **args)
        self.assertEqual((result["status"], result["publication_uncertain"], result["graph_written"]),
                         ("pending", True, None), result)
        self.assertEqual(args["backup_scope"].read(args["backup_path"]).data, old.data)

    def test_restore_post_write_read_failure_reports_uncertainty(self):
        self.update()
        old = self.graph_scope.read("graph.json")
        legacy = json.dumps({"nodes": [], "links": []}).encode()
        read, write = self.graph_scope.read, self.graph_scope.write
        fail = [False]
        def changed(*a, **kw):
            value = write(*a, **kw)
            fail[0] = True
            return value
        def observed(*a, **kw):
            if fail[0]:
                fail[0] = False
                raise OSError("synthetic failure")
            return read(*a, **kw)
        with patch.object(self.graph_scope, "write", changed), patch.object(self.graph_scope, "read", observed):
            result = r.restore_graph(graph_scope=self.graph_scope, graph_path="graph.json",
                                     expected_graph_sha256=old.sha256, restore_bytes=legacy,
                                     backup_scope=files.FileScope(str(self.backups), ["restore.json"]), backup_path="restore.json")
        self.assertEqual((result["status"], result["publication_uncertain"], result["graph_written"]),
                         ("pending", True, None), result)
        self.assertEqual(self.graph_scope.read("graph.json").data, legacy)

    def _retained_direction_fixture(self, *, invalid=False):
        active = self.active()
        docs = {doc.document_id: doc for doc in active.documents}
        graph = {"directed": False, "multigraph": False, "graph": {},
                 "nodes": g.document_nodes(active), "links": []}
        provenance = {"source_file": "one.md", "document_id": "one",
                      "source_sha256": docs["one"].sha256, "source_location": "body:L1-L2",
                      "_origin": "semantic", "file_type": "concept"}
        graph["nodes"].extend([dict(id="concept_a", label="A", **provenance),
                                dict(id="concept_z", label="Z", **provenance)])
        edge = {"source": "concept_a", "target": "concept_z", "_src": "concept_z", "_tgt": "concept_a",
                "source_file": "one.md", "document_id": "one", "source_sha256": docs["one"].sha256,
                "source_location": "body:L1-L2", "_origin": "semantic", "confidence": "EXTRACTED",
                "relation": "constrains", "custom": {"preserve": True}}
        if invalid:
            edge["_src"] = "unrelated_endpoint"
        graph["links"].append(edge)
        envelope = r._empty()
        envelope["content_graph"] = graph
        (self.root / "graph.json").write_bytes(r._encoded(envelope))
        return edge

    def test_undirected_serialized_endpoint_order_keeps_original_direction_markers(self):
        edge = self._retained_direction_fixture()
        before = self.graph_scope.read("graph.json")
        target, comparisons = self.active(["outside.md"]), self.active(["one.md", "two.md"])
        result = self.update(target, request=self.request(target, comparisons), expected_hash=before.sha256)
        self.assertEqual(result.status, "current", result)
        saved = next(item for item in self.saved()["content_graph"]["links"]
                     if {item["source"], item["target"]} == {"concept_a", "concept_z"})
        self.assertEqual({k: v for k, v in saved.items() if k not in {"source", "target"}},
                         {k: v for k, v in edge.items() if k not in {"source", "target"}})

    def test_invalid_original_direction_marker_does_not_expand_edge_endpoints(self):
        self._retained_direction_fixture(invalid=True)
        before = self.graph_scope.read("graph.json")
        target, comparisons = self.active(["outside.md"]), self.active(["one.md", "two.md"])
        result = self.update(target, request=self.request(target, comparisons), expected_hash=before.sha256)
        self.assertEqual((result.status, result.error_code), ("pending", "graph_unrelated_edge_changed"), result)
        self.assertEqual(self.graph_scope.read("graph.json").data, before.data)

    def _pair_decision(self, request, decision, relation_ids=()):
        item = next(x for x in request["decisions"]
                    if {x["source_document_id"], x["target_document_id"]} == {"one", "two"})
        item.update(decision=decision, relation_ids=list(relation_ids))
        return item

    def _visible_assertions(self, active=None):
        projection = r.project_graph(self.saved(), self.active() if active is None else active)
        return {rid for edge in projection["links"] for rid in edge.get("assertion_ids", [])}

    def _hold_topic_relation(self):
        active = self.active(["one.md", "two.md"])
        relation = self.relation(active)
        self.assertEqual(self.update(active, request=self.request(active, relations=[relation])).status, "current")
        before = self.graph_scope.read("graph.json")
        request = self.request(active)
        self._pair_decision(request, "deferred")
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "partial"), result)
        return active, relation

    def test_explicit_pair_deferred_hides_existing_relation_and_keeps_support_history(self):
        active, relation = self._hold_topic_relation()
        saved = next(x for x in self.saved()["relations"] if x["relation_id"] == relation["relation_id"])
        self.assertEqual(saved["status"], "unknown")
        self.assertEqual(saved["support_sets"], relation["support_sets"])
        self.assertEqual(saved["qualifier"], relation["qualifier"])
        self.assertNotIn(relation["relation_id"], self._visible_assertions(active))
        event = self.saved()["relation_review"][-1]["assertion_decisions"][0]
        self.assertEqual((event["relation_id"], event["decision"]), (relation["relation_id"], "deferred"))
        self.assertEqual(event["context_document_ids"], ["one", "two"])

    def test_same_pair_can_accept_topic_and_defer_specific_existing_dependency(self):
        active = self.active(["one.md", "two.md"])
        topic = self.relation(active)
        dependency = self.relation(active, "depends_on", "동일 버전 의존")
        self.update(active, request=self.request(active, relations=[topic, dependency]))
        before = self.graph_scope.read("graph.json")
        request = self.request(active)
        self._pair_decision(request, "accepted", [topic["relation_id"]])
        request["assertion_decisions"] = [{"relation_id": dependency["relation_id"], "decision": "deferred",
                                          "reason": "공유 주제와 의존 판단을 구별해 보류"}]
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "partial"), result)
        actual = {x["relation_id"]: x for x in self.saved()["relations"]}
        self.assertEqual(actual[dependency["relation_id"]]["status"], "unknown")
        self.assertEqual(actual[dependency["relation_id"]]["support_sets"], dependency["support_sets"])
        self.assertEqual(self._visible_assertions(active), {topic["relation_id"]})
        events = self.saved()["relation_review"][-1]["assertion_decisions"]
        self.assertEqual({(e["relation_id"], e["decision"]) for e in events},
                         {(topic["relation_id"], "accepted"), (dependency["relation_id"], "deferred")})

    def test_uncreated_typed_deferred_is_review_only_and_narrow_unrelated_run_stays_complete(self):
        active = self.active()
        topic = self.relation(active)
        selector = {"source_document_id": "one", "target_document_id": "two", "kind": "depends_on",
                    "qualifier": "미확인 의존", "decision": "deferred", "reason": "명시 의존 근거 없음"}
        request = self.request(active, relations=[topic], assertion_decisions=[selector])
        result = self.update(active, request=request)
        pending_id = r.relation_id("one", "two", "depends_on", "미확인 의존")
        self.assertEqual(result.relation_status, "partial", result)
        self.assertEqual({x["relation_id"] for x in self.saved()["relations"]}, {topic["relation_id"]})
        self.assertIn(pending_id, r._unresolved_deferred(self.saved()))
        before = self.graph_scope.read("graph.json")
        target = self.active(["outside.md"])
        result = self.update(target, request=self.request(target), expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertIn(pending_id, r._unresolved_deferred(self.saved()))

    def test_pending_reacceptance_requires_current_proposal_and_same_id(self):
        active, relation = self._hold_topic_relation()
        old_reviews = copy.deepcopy(self.saved()["relation_review"])
        before = self.graph_scope.read("graph.json")
        request = self.request(active)
        self._pair_decision(request, "accepted", [relation["relation_id"]])
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual(result.relation_status, "partial", result)
        self.assertNotIn(relation["relation_id"], self._visible_assertions(active))
        before = self.graph_scope.read("graph.json")
        request["assertion_decisions"] = [{"relation_id": relation["relation_id"], "decision": "accepted",
                                          "reason": "proposal가 없어 재채택할 수 없음"}]
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.error_code),
                         ("pending", "relationship_assertion_decision_not_current"), result)
        self.assertEqual(self.graph_scope.read("graph.json").data, before.data)
        request = self.request(active, relations=[relation])
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertEqual(self._visible_assertions(active), {relation["relation_id"]})
        self.assertNotIn(relation["relation_id"], r._unresolved_deferred(self.saved()))
        self.assertEqual(self.saved()["relation_review"][:len(old_reviews)], old_reviews)

    def test_repeated_accept_defer_events_keep_causal_history_and_adjacent_idempotence(self):
        active, relation = self._hold_topic_relation()
        first_hold = self.saved()["relation_review"][-1]["review_id"]
        before = self.graph_scope.read("graph.json")
        result = self.update(active, request=self.request(active, relations=[relation]), expected_hash=before.sha256)
        self.assertEqual(result.relation_status, "complete", result)
        accepted_id = result.review_id
        before = self.graph_scope.read("graph.json")
        request = self.request(active)
        self._pair_decision(request, "deferred")
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual(result.relation_status, "partial", result)
        self.assertNotEqual(result.review_id, first_hold)
        last = self.saved()["relation_review"][-1]
        self.assertEqual(last["previous_review_id"], accepted_id)
        self.assertNotIn(relation["relation_id"], self._visible_assertions(active))
        count = len(self.saved()["relation_review"])
        before = self.graph_scope.read("graph.json")
        repeated = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual(repeated.review_id, result.review_id)
        self.assertEqual(len(self.saved()["relation_review"]), count)

    def test_hash_change_or_different_typed_relation_does_not_clear_unresolved_deferred(self):
        active = self.active(["one.md", "two.md"])
        topic = self.relation(active)
        pending = {"source_document_id": "one", "target_document_id": "two", "kind": "depends_on",
                   "qualifier": "검토 중 의존", "decision": "deferred", "reason": "판단 보류"}
        result = self.update(active, request=self.request(active, relations=[topic], assertion_decisions=[pending]))
        pending_id = r.relation_id("one", "two", "depends_on", "검토 중 의존")
        self.assertEqual(result.relation_status, "partial", result)
        original_context = copy.deepcopy(r._unresolved_deferred(self.saved())[pending_id]["source_hashes"])
        before = self.graph_scope.read("graph.json")
        (self.vault / "one.md").write_bytes((self.vault / "one.md").read_bytes() + b"changed\n")
        current = self.active(["one.md", "two.md"])
        new_topic = self.relation(current)
        different = self.relation(current, "depends_on", "다른 범위의 의존")
        request = self.request(current, relations=[new_topic, different])
        result = self.update(current, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "partial"), result)
        self.assertEqual(r._unresolved_deferred(self.saved())[pending_id]["source_hashes"], original_context)
        plan = r.discover_candidates(current, envelope=self.saved())
        self.assertIn("unresolved_deferred", plan["candidates"][0]["signals"])

    def test_discovery_marks_unavailable_pending_endpoint_without_reading_it(self):
        active, relation = self._hold_topic_relation()
        target = self.active(["one.md"])
        plan = r.discover_candidates(target, envelope=self.saved())
        self.assertEqual(plan["status"], "partial")
        self.assertEqual(plan["considered_document_ids"], ["one"])
        self.assertEqual(plan["omissions"], ["unresolved_deferred_endpoint_unavailable"])
        self.assertEqual(plan["candidates"], [])
        self.assertNotIn(relation["relation_id"], self._visible_assertions(target))

    def test_typed_no_relation_requires_support_retraction_and_can_close_pending(self):
        active, relation = self._hold_topic_relation()
        before = self.graph_scope.read("graph.json")
        negative = {"relation_id": relation["relation_id"], "decision": "no_relation", "reason": "근거 철회로 관계 종료"}
        request = self.request(active, assertion_decisions=[negative])
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.error_code), ("pending", "relationship_assertion_decision_conflict"), result)
        self.assertEqual(self.graph_scope.read("graph.json").data, before.data)
        request["retract_supports"] = [{"relation_id": relation["relation_id"],
                                        "support_ids": [s["support_id"] for s in relation["support_sets"]],
                                        "reason": "원문 대조 뒤 명시적으로 근거 철회"}]
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertEqual(self.saved()["relations"][0]["status"], "retracted")
        self.assertNotIn(relation["relation_id"], r._unresolved_deferred(self.saved()))

    def test_typed_no_relation_can_resolve_uncreated_pending_without_making_an_assertion(self):
        active = self.active(["one.md", "two.md"])
        topic = self.relation(active)
        selector = {"source_document_id": "one", "target_document_id": "two", "kind": "depends_on",
                    "qualifier": "검토한 의존", "decision": "deferred", "reason": "초기에는 보류"}
        self.update(active, request=self.request(active, relations=[topic], assertion_decisions=[selector]))
        before = self.graph_scope.read("graph.json")
        selector = dict(selector, decision="no_relation", reason="근거 대조 결과 의존 아님")
        request = self.request(active, assertion_decisions=[selector])
        self._pair_decision(request, "accepted", [topic["relation_id"]])
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertEqual({x["relation_id"] for x in self.saved()["relations"]}, {topic["relation_id"]})
        self.assertEqual(r._unresolved_deferred(self.saved()), {})

    def test_typed_selector_conflicts_and_scope_fail_before_graph_publication(self):
        active = self.active()
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]))
        before = self.graph_scope.read("graph.json")
        base = self.request(active, relations=[relation])
        deferred = {"relation_id": relation["relation_id"], "decision": "deferred", "reason": "명시 보류"}
        requests = []
        requests.append(dict(base, assertion_decisions=[deferred]))  # accepted IDs와 같은 ID 보류
        duplicates = self.request(active)
        duplicates["assertion_decisions"] = [deferred, deferred]
        requests.append(duplicates)
        injected = self.request(active)
        injected["assertion_decisions"] = [dict(deferred, context_document_ids=["forged"])]
        requests.append(injected)
        unknown = self.request(active)
        unknown["assertion_decisions"] = [dict(deferred, relation_id="unknown")]
        requests.append(unknown)
        for request in requests:
            with self.subTest(request=request["assertion_decisions"]):
                result = self.update(active, request=request, expected_hash=before.sha256)
                self.assertEqual(result.status, "pending", result)
                self.assertEqual(self.graph_scope.read("graph.json").data, before.data)
        # 제3 문서만 targets인 상황에서 범위 밖 기존 assertion을 보류할 수 없다.
        target = self.active(["outside.md"])
        comparisons = self.active(["one.md", "two.md"])
        other = self.relation(active, "supports", "제3 문서의 새 근거", evidence_ids=("three",))
        request = self.request(target, comparisons, [other], assertion_decisions=[deferred])
        result = self.update(target, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.error_code), ("pending", "relationship_change_scope"), result)
        self.assertEqual(self.graph_scope.read("graph.json").data, before.data)

    def test_accepted_event_context_uses_one_valid_or_support_not_unavailable_history(self):
        active = self.active()
        relation = self.relation(active, evidence_ids=("three",))
        relation["support_sets"].append(self.relation(active)["support_sets"][0])
        self.update(active, request=self.request(active, relations=[relation]))
        before = self.graph_scope.read("graph.json")
        current = self.active(["one.md", "two.md"])
        request = self.request(current)
        self._pair_decision(request, "accepted", [relation["relation_id"]])
        request["assertion_decisions"] = [{"relation_id": relation["relation_id"], "decision": "accepted",
                                          "reason": "현재 두 문서의 독립 근거로 확인"}]
        result = self.update(current, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        event = self.saved()["relation_review"][-1]["assertion_decisions"][0]
        self.assertEqual(event["context_document_ids"], ["one", "two"])
        self.assertIn(relation["relation_id"], self._visible_assertions(current))

    def _accepted_or_history(self, *, include_ab=True):
        active = self.active()
        relation = self.relation(active, evidence_ids=("three",))
        docs = {d.document_id: d for d in active.documents}
        alternatives = {}
        for ids in (("three",), ("one", "two")):
            options = []
            for confidence in ("EXTRACTED", "INFERRED"):
                for start, end in ((1, 1), (1, 2), (2, 2)):
                    support = copy.deepcopy(relation["support_sets"][0])
                    support.update(confidence=confidence, evidence=[r.evidence_span(docs[i], start, end) for i in ids])
                    support["support_id"] = r.support_set_id(support["evidence"], confidence)
                    options.append(support)
            alternatives[ids] = sorted(options, key=lambda s: s["support_id"])
        relation["support_sets"] = [alternatives[("three",)][0], alternatives[("one", "two")][-1]]
        self.assertLess(relation["support_sets"][0]["support_id"], relation["support_sets"][1]["support_id"])
        if not include_ab:
            relation["support_sets"] = relation["support_sets"][:1]
        first = self.update(active, request=self.request(active, relations=[relation]))
        self.assertEqual(first.status, "current", first)
        request = self.request(active)
        self._pair_decision(request, "deferred")
        held = self.update(active, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(held.status, "current", held)
        accepted = self.update(active, request=self.request(active, relations=[relation]),
                               expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual((accepted.status, accepted.relation_status), ("current", "complete"), accepted)
        return active, relation, self.saved()

    def test_manifest_keeps_recorded_independent_or_with_representative_source_unread(self):
        _, relation, envelope = self._accepted_or_history()
        event = envelope["relation_review"][-1]["assertion_decisions"][0]
        self.assertEqual(event["context_document_ids"], ["one", "three", "two"])
        self.assertEqual(event.get("accepted_support_ids"), sorted(s["support_id"] for s in relation["support_sets"]))
        before = copy.deepcopy(envelope)
        current = self.active(["one.md", "two.md"])
        docs = {d.document_id: d for d in current.documents}
        self.assertNotIn(relation["relation_id"], r._unresolved_deferred(envelope, docs))
        self.assertTrue([e for e in r.project_graph(envelope, current)["links"] if e.get("assertion_ids")])
        self.assertEqual(envelope, before)
        request = self.request(current)
        self._pair_decision(request, "accepted", [relation["relation_id"]])
        result = self.update(current, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertEqual(self.saved()["relation_review"][:len(before["relation_review"])], before["relation_review"])

    def test_manifest_does_not_promote_support_added_after_acceptance(self):
        active, relation, envelope = self._accepted_or_history(include_ab=False)
        history = copy.deepcopy(envelope["relation_review"])
        envelope["relations"][0]["support_sets"].append(self.relation(active)["support_sets"][0])
        # 같은 source hash의 A/B 근거도 당시 manifest 밖이면 이전 보류 해제에 쓰지 않는다.
        current = self.active(["one.md", "two.md"])
        docs = {d.document_id: d for d in current.documents}
        self.assertIn(relation["relation_id"], r._unresolved_deferred(envelope, docs))
        self.assertFalse([e for e in r.project_graph(envelope, current)["links"] if e.get("assertion_ids")])
        self.assertEqual(envelope["relation_review"], history)

    def test_manifest_without_current_recorded_or_keeps_deferred(self):
        _, relation, envelope = self._accepted_or_history()
        for mode in ("unavailable", "stale"):
            current = copy.deepcopy(envelope)
            for support in current["relations"][0]["support_sets"]:
                support["status"] = mode
            current["relations"][0]["status"] = mode
            docs = {d.document_id: d for d in self.active().documents}
            with self.subTest(mode=mode):
                self.assertIn(relation["relation_id"], r._unresolved_deferred(current, docs))
                self.assertFalse([e for e in r.project_graph(current, self.active())["links"] if e.get("assertion_ids")])
        # 저장 status가 active여도 현재 허용 원문이 없으면 채택 증명으로 사용하지 않는다.
        self.assertIn(relation["relation_id"], r._unresolved_deferred(envelope, {}))

    def test_manifestless_history_uses_only_recorded_context_and_complete_snapshots(self):
        _, relation, envelope = self._accepted_or_history()
        event = envelope["relation_review"][-1]["assertion_decisions"][0]
        event.pop("accepted_support_ids", None)
        current = self.active(["one.md", "two.md"])
        docs = {d.document_id: d for d in current.documents}
        self.assertIn(relation["relation_id"], r._unresolved_deferred(envelope, docs))
        for typed in (False, True):
            for bad_hash in (False, True):
                bad = copy.deepcopy(envelope)
                review = bad["relation_review"][-1]
                if not typed:
                    review.pop("assertion_decisions")
                if bad_hash:
                    review["documents"][0]["source_sha256"] = "0" * 64
                else:
                    review["documents"] = []
                with self.subTest(typed=typed, bad_hash=bad_hash):
                    self.assertIn(relation["relation_id"], r._unresolved_deferred(bad, docs))

    def test_manifest_validates_all_proof_ids_and_is_not_host_input(self):
        active, relation, envelope = self._accepted_or_history()
        valid_ids = sorted(s["support_id"] for s in relation["support_sets"])
        for ids in ([], [valid_ids[0], valid_ids[0]], valid_ids[::-1], ["unknown"], [None]):
            bad = copy.deepcopy(envelope)
            bad["relation_review"][-1]["assertion_decisions"][0]["accepted_support_ids"] = ids
            with self.subTest(ids=ids), self.assertRaises(g.GraphError):
                r.parse_envelope(bad)
        bad = copy.deepcopy(envelope)
        bad["relation_review"][-1]["assertion_decisions"][0]["decision"] = "deferred"
        with self.assertRaises(g.GraphError):
            r.parse_envelope(bad)
        bad = copy.deepcopy(envelope)
        bad["relation_review"][-1]["documents"][-1]["source_sha256"] = "0" * 64
        with self.assertRaises(g.GraphError):
            r.parse_envelope(bad)
        before = self.graph_scope.read("graph.json")
        request = self.request(active, relations=[relation], assertion_decisions=[{
            "relation_id": relation["relation_id"], "decision": "accepted", "reason": "허위 manifest 주입",
            "accepted_support_ids": valid_ids}])
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual(result.status, "pending", result)
        self.assertEqual(self.graph_scope.read("graph.json").data, before.data)

    def test_legacy_pair_deferred_masks_active_relation_without_rewriting_old_review(self):
        active = self.active(["one.md", "two.md"])
        relation = self.relation(active)
        request = self.request(active)
        self._pair_decision(request, "deferred")
        legacy = {"review_id": "legacy-deferred", "candidate_status": "complete", "relation_status": "partial",
                  "decisions": request["decisions"],
                  "documents": [{"document_id": d.document_id, "path": d.path, "source_sha256": d.sha256}
                                for d in active.documents]}
        envelope = {"batang_graph_format": 2, "content_graph": {"nodes": g.document_nodes(active), "links": []},
                    "relations": [relation], "relation_review": [legacy]}
        original = copy.deepcopy(envelope)
        projected = r.project_graph(envelope, active)
        self.assertFalse([e for e in projected["links"] if e.get("assertion_ids")])
        self.assertEqual(envelope, original)
        accepted = copy.deepcopy(legacy)
        accepted["review_id"] = "legacy-explicit-accept"
        accepted["relation_status"] = "complete"
        accepted["decisions"][0].update(decision="accepted", relation_ids=[relation["relation_id"]])
        envelope["relation_review"].append(accepted)
        projected = r.project_graph(envelope, active)
        self.assertEqual({rid for e in projected["links"] for rid in e.get("assertion_ids", [])}, {relation["relation_id"]})

    def _historical_defer_envelope(self):
        active = self.active(["one.md", "two.md"])
        relation = self.relation(active)
        documents = [{"document_id": d.document_id, "path": d.path, "source_sha256": d.sha256}
                     for d in active.documents]
        request = self.request(active)
        self._pair_decision(request, "deferred")
        deferred = {"review_id": "history-deferred", "candidate_status": "complete", "relation_status": "partial",
                    "documents": documents, "decisions": request["decisions"]}
        envelope = {"batang_graph_format": 2, "content_graph": {"nodes": g.document_nodes(active), "links": []},
                    "relations": [relation], "relation_review": [deferred]}
        return active, relation, envelope

    def test_work_complete_can_keep_new_typed_judgment_deferred(self):
        active = self.active(["one.md", "two.md"])
        decision = {"source_document_id": "one", "target_document_id": "two", "kind": "depends_on",
                    "qualifier": "현재 자료로 미확정", "decision": "deferred", "reason": "현재 두 원문 검토 후 보류"}
        result = self.update(active, request=self.request(active, assertion_decisions=[decision]))
        rid = r.relation_id("one", "two", "depends_on", decision["qualifier"])
        self.assertEqual((result.status, result.relation_status, result.review_work_status),
                         ("current", "partial", "complete"), result)
        self.assertEqual(result.judgment_summary["assertion_decisions"],
                         {"accepted": 0, "no_relation": 0, "deferred": 1})
        self.assertEqual(result.judgment_summary["pending_assertion_ids"], [rid])
        self.assertEqual(result.judgment_summary["unreviewed_assertion_count"], 0)
        self.assertEqual(self.saved()["relations"], [])
        summarized = r.summarize_review(self.saved(), active)
        self.assertEqual((summarized["review_work_status"], summarized["basis"]), ("complete", "stored"))

    def test_work_complete_existing_deferred_keeps_projection_and_reacceptance_contract(self):
        active, relation = self._hold_topic_relation()
        snapshot = self.graph_scope.read("graph.json")
        summarized = r.summarize_review(self.saved(), active)
        self.assertEqual(summarized["review_work_status"], "complete")
        self.assertEqual(summarized["judgment_summary"]["assertion_decisions"]["deferred"], 1)
        self.assertEqual(self._visible_assertions(active), set())
        request = self.request(active)
        self._pair_decision(request, "accepted", [relation["relation_id"]])
        bare = self.update(active, request=request, expected_hash=snapshot.sha256)
        self.assertEqual((bare.relation_status, bare.review_work_status), ("partial", "partial"), bare)
        self.assertEqual(self._visible_assertions(active), set())
        accepted = self.update(active, request=self.request(active, relations=[relation]),
                               expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual((accepted.relation_status, accepted.review_work_status), ("complete", "complete"), accepted)
        self.assertEqual(accepted.judgment_summary["assertion_decisions"]["accepted"], 1)
        self.assertEqual(self._visible_assertions(active), {relation["relation_id"]})

    def test_work_complete_current_deferred_is_independent_of_historical_stale_support(self):
        active = self.active(["one.md", "two.md"])
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]))
        before = self.graph_scope.read("graph.json")
        (self.vault / "one.md").write_bytes(note("one", subject="변경한 현행 원문"))
        active = self.active(["one.md", "two.md"])
        request = self.request(active)
        self._pair_decision(request, "deferred")
        result = self.update(active, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status, result.review_work_status),
                         ("current", "partial", "complete"), result)
        self.assertEqual(result.judgment_summary["stale_assertion_ids"], [])
        self.assertEqual(self.saved()["relations"][0]["support_sets"][0]["status"], "stale")

    def test_work_unreviewed_pending_is_partial_until_explicit_current_reconsideration(self):
        active = self.active(["one.md", "two.md"])
        decision = {"source_document_id": "one", "target_document_id": "two", "kind": "depends_on",
                    "qualifier": "미생성 이월", "decision": "deferred", "reason": "현재 검토 보류"}
        self.update(active, request=self.request(active, assertion_decisions=[decision]))
        omitted = self.update(active, request=self.request(active), expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(omitted.review_work_status, "partial", omitted)
        self.assertEqual(omitted.judgment_summary["unreviewed_assertion_count"], 1)
        repeated = self.update(active, request=self.request(active, assertion_decisions=[decision]),
                               expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(repeated.review_work_status, "complete", repeated)

    def test_work_missing_current_dependency_is_partial_despite_explicit_deferred(self):
        full = self.active()
        relation = self.relation(full, evidence_ids=("three",))
        self.update(full, request=self.request(full, relations=[relation]))
        active = self.active(["one.md", "two.md"])
        request = self.request(active)
        self._pair_decision(request, "deferred")
        result = self.update(active, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(result.review_work_status, "partial", result)
        self.assertEqual(result.judgment_summary["unavailable_assertion_ids"], [relation["relation_id"]])

    def test_work_approved_retraction_or_removal_does_not_require_retired_source(self):
        full = self.active()
        relation = self.relation(full, evidence_ids=("three",))
        self.update(full, request=self.request(full, relations=[relation]))
        before = self.graph_scope.read("graph.json")
        active = self.active(["one.md", "two.md"])
        for removed in (False, True):
            (self.root / "graph.json").write_bytes(before.data)
            extras = ({"removed_document_ids": ["three"]} if removed else {"retract_supports": [{
                "relation_id": relation["relation_id"], "support_ids": [relation["support_sets"][0]["support_id"]],
                "reason": "승인된 근거 철회 사실"}]})
            result = self.update(active, request=self.request(active, **extras), expected_hash=before.sha256)
            with self.subTest(removed=removed):
                self.assertEqual((result.status, result.review_work_status), ("current", "complete"), result)
                self.assertEqual(result.judgment_summary["unavailable_assertion_ids"], [])
                self.assertEqual(result.judgment_summary["unreviewed_assertion_count"], 0)
                self.assertEqual(self.saved()["relations"][0]["support_sets"][0]["status"], "retracted")
                self.assertEqual(r.summarize_review(self.saved(), active)["review_work_status"], "complete")

    def test_work_retraction_does_not_hide_surviving_support_decision_conflict(self):
        full = self.active()
        relation = self.relation(full, evidence_ids=("three",))
        relation["support_sets"].extend(self.relation(full)["support_sets"])
        self.update(full, request=self.request(full, relations=[relation]))
        current = self.active(["one.md", "two.md"])
        request = self.request(current, retract_supports=[{"relation_id": relation["relation_id"],
            "support_ids": [relation["support_sets"][0]["support_id"]], "reason": "C 근거만 철회"}])
        result = self.update(current, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual((result.relation_status, result.review_work_status), ("partial", "partial"), result)
        self.assertEqual(result.judgment_summary["decision_conflict_count"], 1)
        self.assertEqual(self.saved()["relations"][0]["status"], "active")

    def test_work_readonly_old_review_is_derived_without_rewriting_history(self):
        active, _ = self._hold_topic_relation()
        envelope = self.saved()
        for review in envelope["relation_review"]:
            for field in ("review_work_status", "judgment_summary", "affected_relation_ids"):
                review.pop(field, None)
        original = copy.deepcopy(envelope)
        result = r.summarize_review(envelope, active)
        self.assertEqual((result["review_work_status"], result["basis"]), ("complete", "derived"))
        self.assertEqual(envelope, original)
        envelope["relation_review"][-1].pop("candidate_plan")
        result = r.summarize_review(envelope, active)
        self.assertEqual((result["review_work_status"], result["basis"]), ("unknown", "insufficient"))

    def test_work_stored_summary_is_recomputed_when_context_hash_changes_or_counts_are_forged(self):
        active, relation = self._hold_topic_relation()
        envelope = self.saved()
        envelope["relation_review"][-1]["judgment_summary"]["unreviewed_assertion_count"] = 999
        computed = r.summarize_review(envelope, active)
        self.assertEqual((computed["review_work_status"], computed["basis"]), ("complete", "derived"))
        self.assertEqual(computed["judgment_summary"]["unreviewed_assertion_count"], 0)
        (self.vault / "one.md").write_bytes(note("one", subject="검토 뒤 원문 변경"))
        current = self.active(["one.md", "two.md"])
        computed = r.summarize_review(envelope, current)
        self.assertEqual((computed["review_work_status"], computed["basis"]), ("partial", "derived"))
        self.assertEqual(computed["judgment_summary"]["stale_assertion_ids"], [relation["relation_id"]])

    def test_work_conflicts_and_candidate_omissions_remain_partial(self):
        active = self.active(["one.md", "two.md"])
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]))
        conflict = self.update(active, request=self.request(active), expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(conflict.review_work_status, "partial", conflict)
        self.assertEqual(conflict.judgment_summary["decision_conflict_count"], 1)
        request = self.request(active)
        self._pair_decision(request, "deferred")
        request["candidate_plan"]["omissions"] = ["승인 범위 일부 비교 미완료"]
        partial = self.update(active, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(partial.review_work_status, "partial", partial)

    def _focused_incremental_work_review(self):
        full = self.active()
        relation = self.relation(full)
        self.update(full, request=self.request(full, relations=[relation]))
        target, comparisons = self.active(["one.md"]), self.active(["two.md", "outside.md"])
        request = self.request(target, comparisons, relations=[relation])
        request["candidate_plan"]["considered_document_ids"] = ["one", "two"]
        request["candidate_plan"]["candidates"] = [item for item in request["candidate_plan"]["candidates"]
            if {item["source_document_id"], item["target_document_id"]} == {"one", "two"}]
        request["decisions"] = [item for item in request["decisions"]
            if {item["source_document_id"], item["target_document_id"]} == {"one", "two"}]
        result = self.update(target, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        return full, relation, result

    def test_work_incremental_scope_completes_without_promoting_full_candidate_coverage(self):
        full, _, result = self._focused_incremental_work_review()
        self.assertEqual((result.status, result.candidate_status, result.relation_status, result.review_work_status),
                         ("current", "partial", "partial", "complete"), result)
        envelope = self.saved()
        review = envelope["relation_review"][-1]
        self.assertEqual((len(review["documents"]), len(review["candidate_plan"]["considered_document_ids"])), (3, 2))
        self.assertEqual((result.judgment_summary["unreviewed_pair_count"],
                          result.judgment_summary["unreviewed_assertion_count"]), (0, 0))
        self.assertEqual(r.summarize_review(envelope, full)["basis"], "stored")
        # 이전 규칙으로 기록된 partial도 읽고, 저장 이력을 고치지 않고 다시 계산한다.
        review["review_work_status"] = "partial"
        before = copy.deepcopy(envelope)
        self.assertEqual(r.parse_envelope(envelope), before)
        computed = r.summarize_review(envelope, full)
        self.assertEqual((computed["review_work_status"], computed["basis"]), ("complete", "derived"))
        self.assertEqual(envelope, before)

    def test_work_incremental_scope_cannot_omit_target_even_without_candidate_or_assertion_gaps(self):
        full = self.active()
        self.update(full, request=self.request(full))
        target, comparisons = self.active(["one.md"]), self.active(["two.md", "outside.md"])
        request = self.request(target, comparisons)
        request["candidate_plan"].update(considered_document_ids=["two", "three"], candidates=[])
        request["decisions"] = []
        result = self.update(target, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(result.review_work_status, "partial", result)
        self.assertEqual((result.judgment_summary["unreviewed_pair_count"],
                          result.judgment_summary["unreviewed_assertion_count"]), (0, 0))

    def test_work_incremental_candidate_and_affected_endpoints_cannot_leave_considered_scope(self):
        full, _, _ = self._focused_incremental_work_review()
        original = self.saved()
        for keep_pair in (True, False):
            envelope = copy.deepcopy(original)
            review = envelope["relation_review"][-1]
            review["candidate_plan"]["considered_document_ids"] = ["one"]
            if not keep_pair:
                review["candidate_plan"]["candidates"] = []
                review["decisions"] = []
            computed = r.summarize_review(envelope, full)
            with self.subTest(candidate_pair_present=keep_pair):
                self.assertNotEqual(computed["review_work_status"], "complete")
                self.assertEqual(computed["judgment_summary"]["unreviewed_assertion_count"], 0)
                self.assertEqual(computed["review_work_status"], "unknown" if keep_pair else "partial")

    def test_work_incremental_declared_candidate_without_decision_remains_partial(self):
        full, _, _ = self._focused_incremental_work_review()
        envelope = self.saved()
        envelope["relation_review"][-1]["decisions"] = []
        computed = r.summarize_review(envelope, full)
        self.assertEqual(computed["review_work_status"], "partial")
        self.assertEqual(computed["judgment_summary"]["unreviewed_pair_count"], 1)

    def test_work_not_run_does_not_mean_judgment_completed(self):
        active = self.active(["one.md", "two.md"])
        request = self.request(active)
        request["candidate_plan"]["status"] = "not_run"
        request["decisions"] = []
        result = self.update(active, request=request)
        self.assertEqual((result.relation_status, result.review_work_status), ("unknown", "not_run"), result)
        self.assertEqual(result.judgment_summary["unreviewed_pair_count"], 1)
        positional = g.GraphUpdateResult("pending", (), "example")
        self.assertIsNone(positional.review_work_status)
        self.assertIsNone(positional.judgment_summary)
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]),
                    expected_hash=self.graph_scope.read("graph.json").sha256)
        request = self.request(active)
        request["candidate_plan"]["status"] = "not_run"
        result = self.update(active, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(result.review_work_status, "partial", result)
        self.assertEqual(result.judgment_summary["decision_conflict_count"], 1)

    def test_work_assertion_count_deduplicates_pair_acceptance_and_explicit_typed_acceptance(self):
        active = self.active(["one.md", "two.md"])
        relation = self.relation(active)
        result = self.update(active, request=self.request(active, relations=[relation], assertion_decisions=[{
            "relation_id": relation["relation_id"], "decision": "accepted", "reason": "같은 assertion 명시 확인"}]))
        self.assertEqual(result.review_work_status, "complete", result)
        self.assertEqual(result.judgment_summary["pair_decisions"]["accepted"], 1)
        self.assertEqual(result.judgment_summary["assertion_decisions"]["accepted"], 1)

    def test_work_readonly_result_uses_allowed_comparison_snapshots_without_writing(self):
        full = self.active()
        relation = self.relation(full, evidence_ids=("three",))
        self.update(full, request=self.request(full, relations=[relation]))
        before = self.graph_scope.read("graph.json")
        target, comparisons = self.active(["one.md"]), self.active(["two.md", "outside.md"])
        result = self.update(target, request={"comparisons": comparisons}, expected_hash=before.sha256, read_only=True)
        self.assertEqual((result.status, result.review_work_status), ("current", "complete"), result)
        self.assertFalse(result.graph_written)
        self.assertEqual(self.graph_scope.read("graph.json").data, before.data)

    def test_work_explicit_affected_scope_is_saved_and_unreviewed_item_is_counted(self):
        full = self.active()
        relation = self.relation(full)
        self.update(full, request=self.request(full, relations=[relation]))
        target, comparisons = self.active(["outside.md"]), self.active(["one.md", "two.md"])
        request = self.request(target, comparisons, affected_relation_ids=[relation["relation_id"]])
        request["candidate_plan"]["candidates"] = []
        request["decisions"] = []
        result = self.update(target, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(result.review_work_status, "partial", result)
        self.assertEqual(result.judgment_summary["unreviewed_assertion_count"], 1)
        self.assertEqual(self.saved()["relation_review"][-1]["affected_relation_ids"], [relation["relation_id"]])
        self.assertEqual(r.summarize_review(self.saved(), full)["review_work_status"], "partial")

    def test_work_stored_affected_scope_cannot_shrink_target_dependency_minimum(self):
        active = self.active(["one.md", "two.md"])
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]))
        request = self.request(active)
        request["candidate_plan"]["candidates"] = []
        request["decisions"] = []
        result = self.update(active, request=request, expected_hash=self.graph_scope.read("graph.json").sha256)
        self.assertEqual(result.review_work_status, "partial", result)
        envelope = self.saved()
        review = envelope["relation_review"][-1]
        review["affected_relation_ids"] = []
        review["review_work_status"] = "complete"
        review["judgment_summary"]["unreviewed_assertion_count"] = 0
        before = copy.deepcopy(envelope)
        computed = r.summarize_review(envelope, active)
        self.assertEqual((computed["review_work_status"], computed["basis"]), ("partial", "derived"))
        self.assertEqual(computed["judgment_summary"]["unreviewed_assertion_count"], 1)
        self.assertEqual(envelope, before)

    def test_work_stored_scope_extension_requires_recorded_document_context(self):
        full = self.active()
        relation = self.relation(full)
        self.update(full, request=self.request(full, relations=[relation]))
        target = self.active(["outside.md"])
        self.update(target, request=self.request(target), expected_hash=self.graph_scope.read("graph.json").sha256)
        envelope = self.saved()
        review = envelope["relation_review"][-1]
        review["affected_relation_ids"] = [relation["relation_id"]]
        computed = r.summarize_review(envelope, target)
        self.assertEqual((computed["review_work_status"], computed["basis"]), ("unknown", "insufficient"))
        self.assertEqual(computed["judgment_summary"]["unreviewed_assertion_count"], 1)

    def test_work_summary_shape_and_host_injection_are_rejected(self):
        active, _ = self._hold_topic_relation()
        envelope = self.saved()
        for field, value in (("review_work_status", "finished"), ("judgment_summary", {})):
            bad = copy.deepcopy(envelope)
            bad["relation_review"][-1][field] = value
            with self.subTest(field=field), self.assertRaises(g.GraphError):
                r.parse_envelope(bad)
        for value in (True, -1, "0"):
            bad = copy.deepcopy(envelope)
            bad["relation_review"][-1]["judgment_summary"]["unreviewed_pair_count"] = value
            with self.subTest(value=value), self.assertRaises(g.GraphError):
                r.parse_envelope(bad)
        bad = copy.deepcopy(envelope)
        bad["relation_review"][-1]["judgment_summary"]["pending_assertion_ids"] = ["id", "id"]
        with self.assertRaises(g.GraphError):
            r.parse_envelope(bad)
        before = self.graph_scope.read("graph.json")
        for field, value in (("review_work_status", "complete"), ("judgment_summary", {})):
            request = self.request(active, **{field: value})
            result = self.update(active, request=request, expected_hash=before.sha256)
            self.assertEqual((result.status, result.error_code), ("pending", "relationship_request_invalid"), result)
            self.assertEqual(self.graph_scope.read("graph.json").data, before.data)

    def test_incomplete_legacy_acceptance_snapshots_do_not_resolve_prior_deferred(self):
        active, relation, envelope = self._historical_defer_envelope()
        accepted = copy.deepcopy(envelope["relation_review"][0])
        accepted["review_id"] = "legacy-incomplete-accepted"
        accepted["relation_status"] = "complete"
        accepted["decisions"][0].update(decision="accepted", relation_ids=[relation["relation_id"]])
        valid_documents = copy.deepcopy(accepted["documents"])
        missing_hash = copy.deepcopy(valid_documents)
        missing_hash[0].pop("source_sha256")
        wrong_hash = copy.deepcopy(valid_documents)
        wrong_hash[0]["source_sha256"] = "0" * 64
        for documents in ([], valid_documents[:1], missing_hash, wrong_hash):
            with self.subTest(documents=documents):
                current = copy.deepcopy(envelope)
                current["relation_review"].append(dict(accepted, documents=documents))
                before = copy.deepcopy(current)
                self.assertIn(relation["relation_id"], r._unresolved_deferred(current))
                projection = r.project_graph(current, active)
                self.assertFalse([e for e in projection["links"] if e.get("assertion_ids")])
                self.assertEqual(current, before)

    def test_typed_acceptance_requires_matching_current_support_and_snapshot_hashes(self):
        active, relation, envelope = self._historical_defer_envelope()
        event = r._assertion_descriptor(relation["source_document_id"], relation["target_document_id"],
                                         relation["kind"], relation["qualifier"])
        event.update(decision="accepted", reason="기록된 채택", context_document_ids=["one", "two"])
        accepted = {"review_id": "typed-accepted", "candidate_status": "complete", "relation_status": "complete",
                    "documents": copy.deepcopy(envelope["relation_review"][0]["documents"]),
                    "assertion_decisions": [event], "decisions": []}
        accepted["documents"][0]["source_sha256"] = "0" * 64
        envelope["relation_review"].append(accepted)
        self.assertIn(relation["relation_id"], r._unresolved_deferred(envelope))
        self.assertFalse([e for e in r.project_graph(envelope, active)["links"] if e.get("assertion_ids")])
        # 현재 assertion의 근거가 달라졌다면 예전 context의 채택으로 해제하지 않는다.
        full = self.active()
        replacement = self.relation(full, evidence_ids=("three",))
        changed = copy.deepcopy(envelope)
        changed["relations"] = [replacement]
        changed["content_graph"] = {"nodes": g.document_nodes(full), "links": []}
        changed["relation_review"][-1]["documents"] = copy.deepcopy(envelope["relation_review"][0]["documents"])
        self.assertIn(replacement["relation_id"], r._unresolved_deferred(changed))
        self.assertFalse([e for e in r.project_graph(changed, full)["links"] if e.get("assertion_ids")])
        followup = copy.deepcopy(changed["relation_review"][-1])
        followup["review_id"] = "typed-current-accepted"
        followup["documents"] = [{"document_id": d.document_id, "path": d.path, "source_sha256": d.sha256}
                                 for d in full.documents]
        followup["assertion_decisions"][0]["context_document_ids"] = ["one", "three", "two"]
        changed["relation_review"].append(followup)
        self.assertNotIn(replacement["relation_id"], r._unresolved_deferred(changed))
        self.assertEqual({rid for e in r.project_graph(changed, full)["links"] for rid in e.get("assertion_ids", [])},
                         {replacement["relation_id"]})

    def test_pure_approved_rename_preserves_valid_earlier_reacceptance(self):
        active, relation = self._hold_topic_relation()
        before = self.graph_scope.read("graph.json")
        accepted = self.update(active, request=self.request(active, relations=[relation]), expected_hash=before.sha256)
        self.assertEqual(accepted.relation_status, "complete", accepted)
        before = self.graph_scope.read("graph.json")
        old_history = copy.deepcopy(self.saved()["relation_review"])
        (self.vault / "one.md").rename(self.vault / "renamed.md")
        (self.vault / "ACTIVE.md").write_bytes(b"- [one](renamed.md)\n- [two](two.md)\n- [three](outside.md)\n")
        self.note_scope = files.FileScope(str(self.vault), ["ACTIVE.md", "renamed.md", "two.md", "outside.md"])
        target, comparisons = self.active(["renamed.md"]), self.active(["two.md"])
        request = self.request(target, comparisons,
                               renamed_documents=[{"document_id": "one", "old_path": "one.md", "new_path": "renamed.md"}])
        self._pair_decision(request, "accepted", [relation["relation_id"]])
        result = self.update(target, request=request, expected_hash=before.sha256)
        self.assertEqual((result.status, result.relation_status), ("current", "complete"), result)
        self.assertEqual(self.saved()["relation_review"][:len(old_history)], old_history)
        self.assertEqual(self._visible_assertions(self.active(["renamed.md", "two.md"])), {relation["relation_id"]})

    def test_malformed_legacy_document_snapshot_is_graph_error(self):
        active, _, envelope = self._historical_defer_envelope()
        envelope["relation_review"][0]["documents"] = [None]
        with self.assertRaises(g.GraphError):
            r.project_graph(envelope, active)

    def test_uncreated_assertion_cannot_borrow_other_relations_third_source_scope(self):
        active = self.active()
        topic = self.relation(active, evidence_ids=("three",))
        deferred = {"source_document_id": "one", "target_document_id": "two", "kind": "depends_on",
                    "qualifier": "다른 판단 대상", "decision": "deferred", "reason": "미생성 의존 보류"}
        self.update(active, request=self.request(active, relations=[topic], assertion_decisions=[deferred]))
        before = self.graph_scope.read("graph.json")
        target, comparisons = self.active(["outside.md"]), self.active(["one.md", "two.md"])
        for decision in ("no_relation", "deferred"):
            (self.root / "graph.json").write_bytes(before.data)
            request = self.request(target, comparisons,
                                   assertion_decisions=[dict(deferred, decision=decision, reason="타 문서 근거로 판단 변경 시도")])
            request["candidate_plan"] = r.discover_candidates(target, comparisons, self.saved())
            request["decisions"] = [{"source_document_id": c["source_document_id"],
                                     "target_document_id": c["target_document_id"], "decision": "no_relation",
                                     "relation_ids": [], "reason": "승인 범위의 기존 영향 관계 확인"}
                                    for c in request["candidate_plan"]["candidates"]]
            self._pair_decision(request, "accepted", [topic["relation_id"]])
            with self.subTest(decision=decision):
                result = self.update(target, request=request, expected_hash=before.sha256)
                self.assertEqual((result.status, result.error_code), ("pending", "relationship_change_scope"), result)
                self.assertEqual(self.graph_scope.read("graph.json").data, before.data)

    def test_new_review_assertion_event_shape_rejects_forged_context_or_selector(self):
        active = self.active(["one.md", "two.md"])
        relation = self.relation(active)
        self.update(active, request=self.request(active, relations=[relation]))
        value = self.saved()
        for field, new_value in (("relation_id", "forged"), ("context_document_ids", ["one", "two", "missing"])):
            malformed = copy.deepcopy(value)
            malformed["relation_review"][-1]["assertion_decisions"][0][field] = new_value
            with self.subTest(field=field), self.assertRaises(g.GraphError):
                r.parse_envelope(malformed)
        for pointer in ([], "missing-review"):
            malformed = copy.deepcopy(value)
            malformed["relation_review"][-1]["previous_review_id"] = pointer
            with self.subTest(pointer=pointer), self.assertRaises(g.GraphError):
                r.parse_envelope(malformed)

    def test_source_race_before_publish_preserves_old_graph(self):
        self.update()
        active = self.active()
        old = self.graph_scope.read("graph.json")
        from graphify.build import build
        def changed(*args, **kwargs):
            result = build(*args, **kwargs)
            (self.vault / "two.md").write_bytes((self.vault / "two.md").read_bytes() + b"race\n")
            return result
        with patch("graphify.build.build", changed):
            result = self.update(active, expected_hash=old.sha256)
        self.assertEqual(result.status, "pending", result)
        self.assertFalse(result.publication_uncertain)
        self.assertEqual(self.graph_scope.read("graph.json").data, old.data)

    def test_failure_after_publish_reports_uncertain_without_rollback(self):
        self.update()
        active = self.active()
        old = self.graph_scope.read("graph.json")
        write = self.graph_scope.write
        def changed(*args, **kwargs):
            result = write(*args, **kwargs)
            (self.vault / "one.md").write_bytes((self.vault / "one.md").read_bytes() + b"race\n")
            return result
        with patch.object(self.graph_scope, "write", changed):
            result = self.update(active, expected_hash=old.sha256, suffix="new")
        self.assertEqual(result.status, "pending", result)
        self.assertTrue(result.publication_uncertain)
        self.assertIsNone(result.graph_written)
        self.assertNotEqual(self.graph_scope.read("graph.json").data, old.data)


# 공개적으로 노출할 오류 타입은 기존 파일 계약과 같다.
ConflictError = files.ConflictError

if __name__ == "__main__":
    unittest.main()
