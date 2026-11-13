"""문서 간 관계의 내부 데이터·검증·갱신 도우미.

호스트가 자료 접근 권한과 의미 판단을 담당한다. 이 모듈은 전달된 활성
snapshot만 읽으며 새 모델·CLI·서비스를 호출하지 않는다. v1 이관은 명시
함수로만 가능하고 조회용 투영은 원본을 수정하지 않는다.
"""
import copy
import hashlib
import json
import re
import unicodedata
from bisect import bisect_right
from urllib.parse import unquote

import graph_ops as g
from file_ops import ConflictError, FileError

KINDS = frozenset({"references", "depends_on", "supports", "contradicts", "supersedes", "shares_topic"})
SYMMETRIC = frozenset({"contradicts", "shares_topic"})
STATES = frozenset({"active", "stale", "unavailable", "retracted", "unknown"})
_LEGACY_ARCHIVE = "batang_legacy_relations"


def _fail(code):
    raise g.GraphError(code)


def _text(value):
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        _fail("relationship_string_invalid")
    return " ".join(unicodedata.normalize("NFC", value).split())


def _identifier(value):
    # 문서 ID는 원본 metadata의 식별값이다. 표시문자열처럼 정규화하지 않는다.
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        _fail("relationship_identifier_invalid")
    return value


def _encoded(value):
    try:
        data = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                           separators=(",", ":")) + "\n").encode()
    except (ValueError, TypeError):
        _fail("relationship_json_invalid")
    if len(data) > g.MAX_GRAPH_BYTES:
        _fail("graph_data_size")
    return data


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def _pair(a, b):
    a, b = _identifier(a), _identifier(b)
    if a == b:
        _fail("relationship_self_reference")
    return tuple(sorted((a, b)))


def relation_id(source_document_id, target_document_id, kind, qualifier):
    """표시명·경로·내용 hash와 독립된 assertion 식별자."""
    a, b, qualifier = _identifier(source_document_id), _identifier(target_document_id), _text(qualifier)
    _pair(a, b)
    if not isinstance(kind, str) or kind not in KINDS:
        _fail("relationship_kind_invalid")
    if kind in SYMMETRIC:
        a, b = sorted((a, b))
    return "relation_" + _digest([a, b, kind, qualifier])


def evidence_span(document, start_line, end_line):
    """Markdown body의 개행을 포함한 1-based 닫힌 줄 구간 hash."""
    lines = document.body.splitlines(keepends=True)
    if (type(start_line) is not int or type(end_line) is not int
            or start_line < 1 or end_line < start_line or end_line > len(lines)):
        _fail("relationship_evidence_location")
    return {"document_id": document.document_id, "source_sha256": document.sha256,
            "start_line": start_line, "end_line": end_line,
            "span_sha256": hashlib.sha256(b"".join(lines[start_line - 1:end_line])).hexdigest()}


def support_set_id(evidence, confidence="EXTRACTED"):
    if not isinstance(confidence, str) or confidence not in g._CONFIDENCE or not isinstance(evidence, list) or not evidence:
        _fail("relationship_support_invalid")
    return "support_" + _digest([confidence, sorted(evidence, key=lambda e: _encoded(e))])


def _evidence_shape(evidence):
    if (not isinstance(evidence, dict)
            or set(evidence) != {"document_id", "source_sha256", "start_line", "end_line", "span_sha256"}
            or type(evidence.get("start_line")) is not int
            or type(evidence.get("end_line")) is not int
            or evidence["start_line"] < 1 or evidence["end_line"] < evidence["start_line"]):
        _fail("relationship_evidence_invalid")
    _identifier(evidence["document_id"])
    for key in ("source_sha256", "span_sha256"):
        if not isinstance(evidence[key], str) or not re.fullmatch(r"[0-9a-f]{64}", evidence[key]):
            _fail("relationship_evidence_invalid")


def _support_shape(support):
    if (not isinstance(support, dict)
            or set(support) != {"support_id", "confidence", "evidence", "rationale", "status"}
            or not isinstance(support.get("status"), str) or support.get("status") not in STATES
            or not isinstance(support.get("evidence"), list) or not support["evidence"]):
        _fail("relationship_support_invalid")
    _text(support["rationale"])
    for item in support["evidence"]:
        _evidence_shape(item)
    keys = [_encoded(item) for item in support["evidence"]]
    if len(set(keys)) != len(keys):
        _fail("relationship_duplicate_evidence")
    if support["support_id"] != support_set_id(support["evidence"], support["confidence"]):
        _fail("relationship_support_id")


def _relation_shape(relation):
    if (not isinstance(relation, dict)
            or set(relation) != {"relation_id", "source_document_id", "target_document_id", "kind",
                                 "qualifier", "support_sets", "status"}
            or not isinstance(relation.get("status"), str) or relation.get("status") not in STATES
            or not isinstance(relation.get("support_sets"), list)):
        _fail("relationship_assertion_invalid")
    expected = relation_id(relation["source_document_id"], relation["target_document_id"],
                           relation["kind"], relation["qualifier"])
    if expected != relation["relation_id"] or _text(relation["qualifier"]) != relation["qualifier"]:
        _fail("relationship_assertion_id")
    if (relation["kind"] in SYMMETRIC
            and relation["source_document_id"] > relation["target_document_id"]):
        _fail("relationship_assertion_order")
    for support in relation["support_sets"]:
        _support_shape(support)
    ids = [s["support_id"] for s in relation["support_sets"]]
    if len(ids) != len(set(ids)) or (relation["status"] == "active" and not any(
            s["status"] == "active" for s in relation["support_sets"])):
        _fail("relationship_support_invalid")


def _assertion_descriptor(source, target, kind, qualifier):
    source, target, qualifier = _identifier(source), _identifier(target), _text(qualifier)
    identifier = relation_id(source, target, kind, qualifier)
    if kind in SYMMETRIC:
        source, target = sorted((source, target))
    return {"relation_id": identifier, "source_document_id": source,
            "target_document_id": target, "kind": kind, "qualifier": qualifier}


def _assertion_event_shape(event):
    fields = {"relation_id", "source_document_id", "target_document_id", "kind", "qualifier",
              "decision", "reason", "context_document_ids"}
    if (not isinstance(event, dict) or set(event) not in (fields, fields | {"accepted_support_ids"})
            or not isinstance(event.get("decision"), str)
            or event["decision"] not in {"accepted", "no_relation", "deferred"}
            or not isinstance(event.get("context_document_ids"), list)):
        _fail("relationship_assertion_decision_invalid")
    descriptor = _assertion_descriptor(event["source_document_id"], event["target_document_id"],
                                        event["kind"], event["qualifier"])
    if any(event[key] != val for key, val in descriptor.items()):
        _fail("relationship_assertion_decision_selector")
    _text(event["reason"])
    context = event["context_document_ids"]
    for identifier in context:
        _identifier(identifier)
    if (context != sorted(set(context))
            or not {event["source_document_id"], event["target_document_id"]}.issubset(context)):
        _fail("relationship_assertion_decision_context")
    if "accepted_support_ids" in event:
        identifiers = event["accepted_support_ids"]
        if (event["decision"] != "accepted" or not isinstance(identifiers, list) or not identifiers
                or any(not isinstance(identifier, str) or not re.fullmatch(r"support_[0-9a-f]{64}", identifier)
                       for identifier in identifiers)
                or identifiers != sorted(set(identifiers))):
            _fail("relationship_assertion_decision_supports")


def _review_snapshots(review, *, strict=False):
    documents = review.get("documents", [] if not strict else None)
    if not isinstance(documents, list):
        _fail("relationship_review_invalid")
    snapshots = {}
    fields = {"document_id", "path", "source_sha256"}
    for document in documents:
        if not isinstance(document, dict):
            _fail("relationship_review_invalid")
        if not fields.issubset(document) or strict and set(document) != fields:
            if strict:
                _fail("relationship_review_invalid")
            # 누락된 과거 snapshot을 추정해 채택 근거로 승격하지 않는다.
            continue
        identifier = _identifier(document["document_id"])
        g._relative(document["path"])
        digest = document["source_sha256"]
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            if strict:
                _fail("relationship_review_invalid")
            continue
        if identifier in snapshots:
            _fail("relationship_review_invalid")
        snapshots[identifier] = {key: document[key] for key in fields}
    return snapshots


def _manifest_supports(event, relation, snapshots):
    """과거 검증 목록을 보존된 근거와 당시 snapshot에 결합한다. 현재 접근과 분리한다."""
    if relation is None:
        _fail("relationship_assertion_decision_supports")
    endpoints = {relation["source_document_id"], relation["target_document_id"]}
    supports = {support["support_id"]: support for support in relation["support_sets"]}
    contexts = []
    for identifier in event["accepted_support_ids"]:
        support = supports.get(identifier)
        if support is None:
            _fail("relationship_assertion_decision_supports")
        required = endpoints | {e["document_id"] for e in support["evidence"]}
        if (not required.issubset(snapshots)
                or any(snapshots[e["document_id"]]["source_sha256"] != e["source_sha256"]
                       for e in support["evidence"])):
            _fail("relationship_assertion_decision_supports")
        contexts.append(required)
    if set(event["context_document_ids"]) not in contexts:
        _fail("relationship_assertion_decision_context")
    return set(event["accepted_support_ids"])


def _recorded_acceptance_context(relation, snapshots, graph, context_limit=None, current_docs=None,
                                 support_ids=None):
    """현재 assertion에 대응하는 실제 기록 snapshot과 완전 OR 근거 한 묶음만 인정한다."""
    if relation is None or relation["status"] != "active":
        return None
    try:
        nodes = _node_map(graph)
        endpoints = {relation["source_document_id"], relation["target_document_id"]}
        for identifier in endpoints:
            if (identifier not in snapshots or identifier not in nodes
                    or snapshots[identifier]["source_sha256"] != nodes[identifier].get("source_sha256")):
                return None
            # 동일 ID·동일 bytes의 승인 rename은 이전 경로 문자열과 독립적이다.
            if current_docs is not None and (identifier not in current_docs
                                             or current_docs[identifier].sha256 != snapshots[identifier]["source_sha256"]):
                return None
        for support in sorted(relation["support_sets"], key=lambda item: item["support_id"]):
            if support["status"] != "active" or support_ids is not None and support["support_id"] not in support_ids:
                continue
            required = endpoints | {e["document_id"] for e in support["evidence"]}
            if context_limit is not None and required != context_limit:
                continue
            if not required.issubset(snapshots):
                continue
            matched = True
            for evidence in support["evidence"]:
                identifier = evidence["document_id"]
                digest = snapshots[identifier]["source_sha256"]
                if (digest != evidence["source_sha256"]
                        or identifier in nodes and nodes[identifier].get("source_sha256") != digest):
                    matched = False
                    break
            if not matched:
                continue
            if current_docs is not None:
                if (not required.issubset(current_docs)
                        or any(current_docs[i].sha256 != snapshots[i]["source_sha256"] for i in required)
                        or _support_current(support, current_docs) != "active"):
                    continue
            return required
    except g.GraphError:
        return None
    return None


def _review_assertion_events(review, relations, graph, current_docs=None):
    """불완전한 과거 채택을 보류 해제 권한으로 승격하지 않고 사건을 읽는다."""
    snapshots = _review_snapshots(review, strict="assertion_decisions" in review)
    if "assertion_decisions" in review:
        events = []
        for event in review["assertion_decisions"]:
            relation = relations.get(event["relation_id"])
            if event["decision"] == "accepted":
                support_ids = None
                context_limit = set(event["context_document_ids"])
                if "accepted_support_ids" in event:
                    support_ids = _manifest_supports(event, relation, snapshots)
                    context_limit = None
                context = _recorded_acceptance_context(relation, snapshots, graph,
                                                       context_limit, current_docs, support_ids)
                if context is None:
                    continue
            elif event["decision"] == "no_relation" and relation is not None:
                if relation["status"] != "retracted" or any(s["status"] != "retracted" for s in relation["support_sets"]):
                    continue
            events.append(event)
        return events
    events = {}
    for decision in review.get("decisions", []):
        if not isinstance(decision, dict) or decision.get("decision") not in {"accepted", "deferred"}:
            continue
        pair = _pair(decision["source_document_id"], decision["target_document_id"])
        identifiers = decision.get("relation_ids", []) if decision["decision"] == "accepted" else [
            rid for rid, relation in relations.items()
            if _pair(relation["source_document_id"], relation["target_document_id"]) == pair]
        for rid in identifiers:
            relation = relations.get(rid)
            if relation is None or _pair(relation["source_document_id"], relation["target_document_id"]) != pair:
                continue
            if decision["decision"] == "accepted":
                context = _recorded_acceptance_context(relation, snapshots, graph, current_docs=current_docs)
                if context is None:
                    continue
            else:
                context = _dependencies(relation)
            event = _assertion_descriptor(relation["source_document_id"], relation["target_document_id"],
                                          relation["kind"], relation["qualifier"])
            event.update(decision=decision["decision"], reason=decision.get("reason", "legacy pair decision"),
                         context_document_ids=sorted(context))
            events[rid] = event
    return [events[rid] for rid in sorted(events)]


def _unresolved_deferred(envelope, current_docs=None):
    """동일 assertion의 유효한 명시 사건만 보류를 끝낸다. hash 변화는 해제가 아니다."""
    relations = {r["relation_id"]: r for r in envelope["relations"]}
    pending = {}
    for review in envelope["relation_review"]:
        snapshots = {identifier: record["source_sha256"]
                     for identifier, record in _review_snapshots(review, strict="assertion_decisions" in review).items()}
        for event in _review_assertion_events(review, relations, envelope["content_graph"], current_docs):
            rid = event["relation_id"]
            if event["decision"] == "deferred":
                pending[rid] = {"event": copy.deepcopy(event),
                                "source_hashes": {i: snapshots[i] for i in event["context_document_ids"] if i in snapshots}}
            elif event["decision"] in {"accepted", "no_relation"}:
                pending.pop(rid, None)
    return pending


_WORK_STATES = frozenset({"complete", "partial", "not_run", "unknown"})
_JUDGMENTS = ("accepted", "no_relation", "deferred")


def _judgment_summary_shape(summary):
    counts = {"unreviewed_pair_count", "unreviewed_assertion_count", "decision_conflict_count"}
    identifiers = {"pending_assertion_ids", "stale_assertion_ids", "unavailable_assertion_ids"}
    if not isinstance(summary, dict) or set(summary) != counts | identifiers | {"pair_decisions", "assertion_decisions"}:
        _fail("relationship_judgment_summary_invalid")
    for key in counts:
        if type(summary[key]) is not int or summary[key] < 0:
            _fail("relationship_judgment_summary_invalid")
    for key in identifiers:
        values = summary[key]
        if (not isinstance(values, list) or any(not isinstance(i, str) or not i for i in values)
                or values != sorted(set(values))):
            _fail("relationship_judgment_summary_invalid")
        for identifier in values:
            _identifier(identifier)
    for key in ("pair_decisions", "assertion_decisions"):
        values = summary[key]
        if (not isinstance(values, dict) or set(values) != set(_JUDGMENTS)
                or any(type(v) is not int or v < 0 for v in values.values())):
            _fail("relationship_judgment_summary_invalid")


def _review_work(envelope, review, docs, *, affected_ids=None):
    """현재 원문으로 판단을 수행했는지 계산한다. 판단의 보류와 작업 누락을 구분한다."""
    summary = {"pair_decisions": dict.fromkeys(_JUDGMENTS, 0),
               "assertion_decisions": dict.fromkeys(_JUDGMENTS, 0),
               "pending_assertion_ids": [], "unreviewed_pair_count": 0,
               "unreviewed_assertion_count": 0, "stale_assertion_ids": [],
               "unavailable_assertion_ids": [], "decision_conflict_count": 0}
    if review is None:
        return "unknown", summary, False
    relations = {r["relation_id"]: r for r in envelope["relations"]}
    snapshots = _review_snapshots(review, strict="assertion_decisions" in review)
    plan = review.get("candidate_plan")
    enough = (isinstance(plan, dict) and isinstance(plan.get("candidates"), list)
              and isinstance(plan.get("considered_document_ids"), list)
              and isinstance(plan.get("omissions"), list) and isinstance(review.get("targets"), list)
              and isinstance(plan.get("method"), str) and bool(plan["method"].strip())
              and isinstance(plan.get("status"), str) and plan["status"] in {"complete", "partial", "not_run"}
              and isinstance(review.get("decisions"), list) and isinstance(review.get("documents"), list))
    if not enough:
        plan = plan if isinstance(plan, dict) else {}
    raw_targets = review.get("targets", [])
    raw_considered = plan.get("considered_document_ids", [])
    if (not isinstance(raw_targets, list) or any(not isinstance(i, str) for i in raw_targets)
            or not isinstance(raw_considered, list) or any(not isinstance(i, str) for i in raw_considered)):
        enough = False
        raw_targets, raw_considered = [], []
    targets = set(raw_targets)
    if len(targets) != len(raw_targets) or len(set(raw_considered)) != len(raw_considered):
        enough = False
    pairs = set()
    candidates = plan.get("candidates", [])
    for candidate in candidates if isinstance(candidates, list) else []:
        if not isinstance(candidate, dict) or not {"source_document_id", "target_document_id"}.issubset(candidate):
            enough = False
            continue
        pair = _pair(candidate["source_document_id"], candidate["target_document_id"])
        if pair in pairs or not set(pair).issubset(raw_considered):
            enough = False
        pairs.add(pair)
    decisions = {}
    raw_decisions = review.get("decisions", [])
    for item in raw_decisions if isinstance(raw_decisions, list) else []:
        if not isinstance(item, dict) or item.get("decision") not in _JUDGMENTS:
            enough = False
            continue
        pair = _pair(item["source_document_id"], item["target_document_id"])
        if pair in decisions or pair not in pairs:
            enough = False
        decisions[pair] = item
    for item in decisions.values():
        summary["pair_decisions"][item["decision"]] += 1
    summary["unreviewed_pair_count"] = len(pairs - decisions.keys())
    # 원형 legacy review에는 assertion 단위 사건이 없을 수 있다.
    events = {e["relation_id"]: e for e in review.get("assertion_decisions", [])}
    valid_events = {e["relation_id"]: e for e in _review_assertion_events(
        review, relations, envelope["content_graph"], docs)}
    if "assertion_decisions" not in review:
        events = valid_events
    for event in events.values():
        summary["assertion_decisions"][event["decision"]] += 1
    affected = {rid for rid, relation in relations.items() if _dependencies(relation) & targets}
    if affected_ids is not None:
        affected.update(affected_ids)
    elif "affected_relation_ids" in review:
        # 저장된 목록은 현재 의존성에서 확인되는 최소 영향 범위를 줄일 수 없다.
        extensions = set(review["affected_relation_ids"]) - affected
        allowed_context = set(snapshots) | set(review.get("unavailable_document_ids", [])) | set(review.get("removed_document_ids", []))
        for rid in extensions:
            if rid not in relations or not _dependencies(relations[rid]).issubset(allowed_context):
                enough = False
        affected.update(extensions)
    elif any(rid in relations and rid not in affected for rid in events):
        # 과거의 명시 확장 권한·미검토 범위는 기록이 없으면 추정하지 않는다.
        enough = False
    pending = _unresolved_deferred(envelope, docs)
    relevant_pending = {rid: record for rid, record in pending.items()
                        if rid in affected or _pair(record["event"]["source_document_id"],
                                                   record["event"]["target_document_id"]) in pairs
                        or set(record["event"]["context_document_ids"]) & targets}
    summary["pending_assertion_ids"] = sorted(relevant_pending)
    required_ids = affected | set(events) | set(relevant_pending)
    stale, unavailable, reviewed = set(), set(), set()
    removed = set(review.get("removed_document_ids", []))
    scope_ids = set(raw_considered) | targets
    enough = enough and scope_ids.issubset(snapshots)
    scope_current = scope_ids.issubset(snapshots)
    for identifier in scope_ids:
        if (identifier not in docs or identifier not in snapshots
                or docs[identifier].sha256 != snapshots[identifier]["source_sha256"]):
            scope_current = False
    retracts = {x["relation_id"] for x in review.get("retract_supports", [])}
    for rid in required_ids:
        event = events.get(rid)
        relation = relations.get(rid)
        if event is not None:
            context = set(event["context_document_ids"])
            if event["decision"] == "accepted" and rid in valid_events:
                allowed = set(event["accepted_support_ids"]) if "accepted_support_ids" in event else None
                context = _recorded_acceptance_context(relation, snapshots, envelope["content_graph"],
                    None if allowed is not None else context, docs, allowed)
                if context is None:
                    context = set(event["context_document_ids"])
        elif rid in relevant_pending:
            context = set(relevant_pending[rid]["event"]["context_document_ids"])
        else:
            context = _dependencies(relation) if relation is not None else set()
        context -= removed
        if relation is not None:
            endpoints = {relation["source_document_id"], relation["target_document_id"]}
            retired_context = {e["document_id"] for support in relation["support_sets"]
                               if support["status"] == "retracted" for e in support["evidence"]}
            retained_context = {e["document_id"] for support in relation["support_sets"]
                                if support["status"] != "retracted" for e in support["evidence"]}
            # 승인 사실로 철회한 근거를 다시 읽는 것은 현재 검토의 필수 AND 입력이 아니다.
            context -= retired_context - retained_context - endpoints
        missing = context - docs.keys()
        mismatched = {i for i in context & docs.keys() if i not in snapshots
                      or docs[i].sha256 != snapshots[i]["source_sha256"]}
        if missing:
            unavailable.add(rid)
        if mismatched:
            stale.add(rid)
        if missing or mismatched:
            continue
        if event is not None:
            if event["decision"] == "deferred" or rid in valid_events:
                reviewed.add(rid)
        elif rid in retracts or relation is not None and _dependencies(relation) & removed:
            reviewed.add(rid)
    summary["unreviewed_assertion_count"] = len(required_ids - reviewed)
    summary["stale_assertion_ids"] = sorted(stale)
    summary["unavailable_assertion_ids"] = sorted(unavailable)
    conflicts = set()
    for conflict in review.get("decision_conflicts", []):
        if not isinstance(conflict, dict) or "reason" not in conflict:
            enough = False
            continue
        pair = _pair(conflict["source_document_id"], conflict["target_document_id"])
        conflicts.add((pair, conflict["reason"]))
    for pair, decision in decisions.items():
        active = {rid for rid, relation in relations.items() if relation["status"] == "active"
                  and _pair(relation["source_document_id"], relation["target_document_id"]) == pair}
        if decision["decision"] == "no_relation" and active:
            conflicts.add((pair, "active_relations_remain"))
        elif decision["decision"] == "accepted" and set(decision.get("relation_ids", [])) != active:
            conflicts.add((pair, "accepted_ids_mismatch"))
    summary["decision_conflict_count"] = len(conflicts)
    # 전달된 전체 snapshot의 탐색 coverage와 이번 명시 검토 범위의 완료는 별개다.
    # 영향받은 관계의 현행 endpoint는 후보 목록에 없더라도 범위에서 빠질 수 없다.
    required_scope = targets | {identifier for rid in affected if rid in relations
                                for identifier in (relations[rid]["source_document_id"],
                                                   relations[rid]["target_document_id"])
                                if identifier not in removed}
    if conflicts:
        status = "partial"
    elif plan.get("status") == "not_run":
        status = "not_run"
    elif not enough:
        status = "unknown"
    elif (plan.get("status") != "complete" or plan.get("omissions")
          or not required_scope.issubset(raw_considered)
          or not scope_current or summary["unreviewed_pair_count"] or summary["unreviewed_assertion_count"]
          or stale or unavailable):
        status = "partial"
    else:
        status = "complete"
    return status, summary, enough


def summarize_review(envelope, active_documents):
    """최신 검토의 작업 완료와 판단 결과를 읽기 전용으로 현재 snapshot에 대조한다."""
    value = parse_envelope(envelope)
    g._verify_current(active_documents)
    docs = {d.document_id: d for d in active_documents.documents}
    review = value["relation_review"][-1] if value["relation_review"] else None
    status, summary, enough = _review_work(value, review, docs)
    basis = "derived" if enough else "insufficient"
    if (review is not None and enough and review.get("review_work_status") == status
            and review.get("judgment_summary") == summary):
        basis = "stored"
    return {"review_id": review["review_id"] if review else None, "review_work_status": status,
            "judgment_summary": summary, "basis": basis}


def parse_envelope(data):
    """v2만 수용한다. v1/알 수 없는 형식은 자동 전환하지 않는다."""
    value = g._json(data) if isinstance(data, (str, bytes)) else copy.deepcopy(data)
    if (not isinstance(value, dict) or type(value.get("batang_graph_format")) is not int
            or value.get("batang_graph_format") != 2
            or set(value) != {"batang_graph_format", "content_graph", "relations", "relation_review"}
            or not isinstance(value.get("relations"), list)
            or not isinstance(value.get("relation_review"), list)):
        _fail("relationship_format_invalid")
    value["content_graph"] = g._graph_data(value["content_graph"])
    _validate_legacy_archive(value["content_graph"])
    ids = set()
    for item in value["relations"]:
        _relation_shape(item)
        if item["relation_id"] in ids:
            _fail("relationship_duplicate_assertion")
        ids.add(item["relation_id"])
    review_ids = set()
    relations = {relation["relation_id"]: relation for relation in value["relations"]}
    for review in value["relation_review"]:
        if (not isinstance(review, dict) or not isinstance(review.get("review_id"), str)
                or review["review_id"] in review_ids
                or not isinstance(review.get("candidate_status"), str) or review.get("candidate_status") not in {"complete", "partial", "not_run"}
                or not isinstance(review.get("relation_status"), str) or review.get("relation_status") not in {"complete", "partial", "unknown", "stale"}):
            _fail("relationship_review_invalid")
        if "previous_review_id" in review and (not isinstance(review["previous_review_id"], str)
                                               or review["previous_review_id"] not in review_ids):
            _fail("relationship_review_invalid")
        review_ids.add(review["review_id"])
        snapshots = _review_snapshots(review, strict="assertion_decisions" in review)
        new_fields = {"review_work_status", "judgment_summary"}
        if new_fields & review.keys():
            if (not new_fields.issubset(review) or not isinstance(review["review_work_status"], str)
                    or review["review_work_status"] not in _WORK_STATES):
                _fail("relationship_review_work_invalid")
            _judgment_summary_shape(review["judgment_summary"])
        if "affected_relation_ids" in review:
            affected = review["affected_relation_ids"]
            if (not isinstance(affected, list) or any(not isinstance(i, str) for i in affected)
                    or affected != sorted(set(affected)) or not set(affected).issubset(ids)):
                _fail("relationship_review_work_invalid")
        if "assertion_decisions" in review:
            events = review["assertion_decisions"]
            if not isinstance(events, list):
                _fail("relationship_review_invalid")
            event_ids = set()
            for event in events:
                _assertion_event_shape(event)
                if event["relation_id"] in event_ids:
                    _fail("relationship_assertion_decision_duplicate")
                event_ids.add(event["relation_id"])
                if event["decision"] == "accepted" and not set(event["context_document_ids"]).issubset(snapshots):
                    _fail("relationship_assertion_decision_context")
                if "accepted_support_ids" in event:
                    _manifest_supports(event, relations.get(event["relation_id"]), snapshots)
    _encoded(value)
    return value


def _empty():
    return {"batang_graph_format": 2,
            "content_graph": {"directed": False, "multigraph": False, "graph": {}, "nodes": [], "links": []},
            "relations": [], "relation_review": []}


def _legacy_record(graph, edge, node_map):
    # 누적 archive 예산을 확인하기 전에는 큰 endpoint를 복제하지 않는다.
    nodes = [node_map[i] for i in sorted({edge["source"], edge["target"]})]
    value = {"directed": graph["directed"], "edge": edge, "nodes": nodes}
    value["record_id"] = "legacy_" + _digest(value)
    return value


def _validate_legacy_archive(graph):
    archive = graph["graph"].get(_LEGACY_ARCHIVE)
    if archive is None:
        if _LEGACY_ARCHIVE in graph["graph"]:
            _fail("relationship_legacy_archive_invalid")
        return {}
    if (not isinstance(archive, dict) or set(archive) != {"archive_version", "records"}
            or type(archive["archive_version"]) is not int or archive["archive_version"] != 1
            or not isinstance(archive["records"], list)):
        _fail("relationship_legacy_archive_invalid")
    records = {}
    for record in archive["records"]:
        if (not isinstance(record, dict) or set(record) != {"record_id", "directed", "edge", "nodes"}
                or type(record["directed"]) is not bool):
            _fail("relationship_legacy_archive_invalid")
        snapshot = g._graph_data({"directed": record["directed"], "nodes": record["nodes"], "links": [record["edge"]]})
        nodes = {n["id"]: n for n in snapshot["nodes"]}
        expected = _legacy_record(snapshot, record["edge"], nodes)
        if record != expected or record["record_id"] in records:
            _fail("relationship_legacy_archive_invalid")
        records[record["record_id"]] = copy.deepcopy(record)
    return records


def _partition_legacy(graph):
    """미검토 legacy edge와 원래 endpoint를 현재 개념 노드 수명에서 분리한다."""
    # 원래 graph와 archive를 함께 보관하는 보수적 누적 예산이다. 제거할 live
    # edge의 크기는 차감하지 않아도 저장 가능 범위를 넘겨 복제하는 일이 없다.
    archive_budget = len(_encoded(graph))
    live = copy.deepcopy(graph)
    records = _validate_legacy_archive(live)
    nodes = {n["id"]: n for n in live["nodes"]}
    paths = {}
    for node in live["nodes"]:
        if node.get("node_role") == "document":
            paths.setdefault(node.get("source_file"), set()).add(node.get("document_id"))
    path_owner = {p: next(iter(ids)) for p, ids in paths.items() if len(ids) == 1}

    def owner(node):
        identifier = path_owner.get(node.get("source_file"))
        if node.get("document_id") not in (None, identifier):
            return None
        return identifier

    kept, moved_records = [], []
    for edge in live["links"]:
        a, b = nodes[edge["source"]], nodes[edge["target"]]
        if all(g._ast_tier(item) for item in (a, b, edge)):
            kept.append(edge)
            continue
        left, right = owner(a), owner(b)
        source_owner = path_owner.get(edge.get("source_file"))
        same_source = (left is not None and left == right == source_owner
                       and edge.get("document_id") in (None, left))
        if same_source:
            kept.append(edge)
            continue
        record = _legacy_record(graph, edge, nodes)
        previous = records.get(record["record_id"])
        if previous is not None and previous != record:
            _fail("relationship_legacy_archive_collision")
        if previous is None:
            record_size = len(_encoded(record))
            if archive_budget + record_size + 256 > g.MAX_GRAPH_BYTES:
                _fail("graph_data_size")
            archive_budget += record_size + 1
            records[record["record_id"]] = copy.deepcopy(record)
        moved_records.append(record)
    live["links"] = kept
    if records or _LEGACY_ARCHIVE in live["graph"]:
        live["graph"][_LEGACY_ARCHIVE] = {"archive_version": 1,
                                             "records": [records[i] for i in sorted(records)]}
    # 모든 이동 edge와 endpoint의 원래 속성이 archive에 온전히 남는지 대조한다.
    for record in moved_records:
        if records.get(record["record_id"]) != record:
            _fail("relationship_legacy_archive_changed")
    if any(records.get(i) != record for i, record in _validate_legacy_archive(graph).items()):
        _fail("relationship_legacy_archive_changed")
    return live


def migrate_graph(graph_bytes):
    """명시된 v1 bytes를 보존한 v2 후보 bytes를 반환한다. 파일은 쓰지 않는다.

    기존 교차 edge는 원형 content_graph에 보존하되 투영에서는 제외된다.
    단순 포장만으로 의미 검토 완료 또는 새로운 active assertion을 만들지 않는다.
    """
    graph = g._graph_data(graph_bytes)
    value = _empty()
    value["content_graph"] = graph
    return _encoded(value)


def _documents(targets, comparisons=None):
    comparisons = targets if comparisons is None else comparisons
    if (not isinstance(targets, g.ActiveDocuments) or not isinstance(comparisons, g.ActiveDocuments)
            or targets.scope.root_parts != comparisons.scope.root_parts
            or targets.active_path != comparisons.active_path
            or targets.active_sha256 != comparisons.active_sha256):
        _fail("relationship_comparison_scope")
    g._verify_current(targets)
    g._verify_current(comparisons)
    docs = {}
    paths = {}
    for doc in (*targets.documents, *comparisons.documents):
        if (doc.document_id in docs and docs[doc.document_id] != doc
                and (docs[doc.document_id].path != doc.path or docs[doc.document_id].sha256 != doc.sha256
                     or docs[doc.document_id].body != doc.body
                     or docs[doc.document_id].metadata != doc.metadata)):
            _fail("relationship_document_collision")
        if doc.path in paths and paths[doc.path] != doc.document_id:
            _fail("relationship_document_collision")
        paths[doc.path] = doc.document_id
        docs[doc.document_id] = doc
    return docs, comparisons


def _dependencies(relation):
    return {relation["source_document_id"], relation["target_document_id"]} | {
        e["document_id"] for s in relation["support_sets"] for e in s["evidence"]}


def _terms(doc):
    names = [doc.metadata["subject"], *doc.metadata.get("aliases", []), *doc.metadata["tags"]]
    return {unicodedata.normalize("NFC", word).casefold()
            for text in names for word in re.findall(r"[^\W_]+", text, re.UNICODE) if len(word) > 1}


def _target_pairs(document_ids, target_ids):
    """전체 정렬 쌍 중 target이 있는 쌍만 같은 순서로 직접 열거한다."""
    if not target_ids:
        return
    ordered = sorted(document_ids)
    targets = sorted(target_ids)
    for index, a in enumerate(ordered):
        if a in target_ids:
            for next_index in range(index + 1, len(ordered)):
                yield a, ordered[next_index]
        else:
            for next_index in range(bisect_right(targets, a), len(targets)):
                yield a, targets[next_index]


def _candidate_features(doc):
    """현재 호출의 검증된 문서에서 후보 탐색 특징을 한 번 계산한다."""
    terms = _terms(doc)
    body = doc.body.decode("utf-8")
    return {"terms": terms, "body": body,
            "names": {doc.document_id, doc.path, doc.path.rsplit("/", 1)[-1].removesuffix(".md"),
                      doc.metadata["subject"], *doc.metadata.get("aliases", [])},
            "refs": _link_destinations(body),
            "words": {w.casefold() for w in re.findall(r"[^\W_]+", body) if len(w) > 2}}


def _link_destinations(body):
    """위키와 inline Markdown 링크의 목적지만 추출한다. 파일을 읽지 않는다."""
    refs = {(value, "wiki") for value in re.findall(r"\[\[([^\]\n|]+)(?:\|[^\]\n]*)?\]\]", body)}
    for match in re.finditer(r"\]\(\s*", body):
        start = match.end()
        if start < len(body) and body[start] == "<":
            end = body.find(">", start + 1)
            if end != -1 and _markdown_link_end(body, end + 1):
                refs.add((body[start + 1:end], "markdown"))
            continue
        # 괄호가 포함된 파일명과 backslash escape를 보존하되 title은 제외한다.
        depth, escaped, end = 0, False, start
        while end < len(body):
            char = body[end]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "(":
                depth += 1
            elif char == ")":
                if not depth:
                    break
                depth -= 1
            elif char.isspace() and not depth:
                break
            end += 1
        if end > start and _markdown_link_end(body, end):
            refs.add((body[start:end], "markdown"))
    return refs


def _markdown_link_end(body, start):
    return re.compile(r'''\s*(?:"[^"\n]*"|'[^'\n]*'|\([^()\n]*\))?\s*\)''').match(body, start) is not None


def _reference_name(value):
    return unicodedata.normalize("NFC", value)


def _reference_index(docs, features):
    paths, names = {}, {}
    for identifier, doc in docs.items():
        paths.setdefault(_reference_name(doc.path), set()).add(identifier)
        for name in features[identifier]["names"]:
            names.setdefault(_reference_name(name), set()).add(identifier)
        basename = doc.path.rsplit("/", 1)[-1]
        names.setdefault(_reference_name(basename), set()).add(identifier)
    return paths, names


def _reference_target(raw, syntax, source_path, paths, names):
    # fragment은 URL decode 전에 분리하여 파일명의 %23과 앵커를 혼동하지 않는다.
    try:
        value = unquote(raw.split("#", 1)[0], errors="strict")
    except (UnicodeError, ValueError):
        return None
    value = _reference_name(re.sub(r"\\([\\() ])", r"\1", value.strip()))
    if (not value or value.startswith("/") or "\\" in value or "?" in value
            or any(ord(char) < 32 for char in value)):
        return None
    # Markdown의 목적지는 URI 문법을 따르지만 위키 이름의 콜론은 제목 문자일
    # 수 있다. 위키도 명시적인 외부 URL을 내부 이름으로 재해석하지 않는다.
    scheme = r"^[A-Za-z][A-Za-z0-9+.-]*:"
    if re.match(scheme + (r"//" if syntax == "wiki" else ""), value):
        return None
    root_wiki_path = syntax == "wiki" and "/" in value and not value.startswith(("./", "../"))
    components = [] if root_wiki_path else _reference_name(source_path).split("/")[:-1]
    for part in value.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not components:
                return None
            components.pop()
        else:
            components.append(part)
    if syntax == "wiki" and value in names:
        named = names[value]
        return next(iter(named)) if len(named) == 1 else None
    relative = _reference_name("/".join(components))
    variants = [relative] if relative.lower().endswith(".md") else [relative, relative + ".md"]
    found = set().union(*(paths.get(path, set()) for path in variants))
    if found:
        return next(iter(found)) if len(found) == 1 else None
    # 명시된 경로가 없으면 다른 폴더의 동명 파일로 재해석하지 않는다.
    if "/" in value or (syntax == "markdown" and value.lower().endswith(".md")):
        return None
    found = names.get(value, set())
    if not found and value.lower().endswith(".md"):
        found = names.get(value[:-3], set())
    return next(iter(found)) if len(found) == 1 else None


def discover_candidates(targets, comparisons=None, envelope=None):
    """허용된 snapshot 안에서만 후보를 찾는다. 의미 관계를 자동 확정하지 않는다.

    호스트는 같은 범위 안의 의미 후보를 추가하거나 예산 제한을 omissions에
    기록할 수 있다. complete는 이 탐색 방법과 전달된 범위에만 적용된다.
    """
    docs, comparisons = _documents(targets, comparisons)
    target_ids = {d.document_id for d in targets.documents}
    old = None if envelope is None else parse_envelope(envelope)
    pairs = {}
    features = {identifier: _candidate_features(doc) for identifier, doc in docs.items()} if target_ids and len(docs) > 1 else {}
    paths, names = _reference_index(docs, features) if features else ({}, {})
    references = {identifier: {target for raw, syntax in feature["refs"]
                              if (target := _reference_target(raw, syntax, docs[identifier].path, paths, names))}
                  for identifier, feature in features.items()}
    for a, b in _target_pairs(docs, target_ids):
        fa, fb = features[a], features[b]
        signals = []
        if fa["terms"] & fb["terms"]:
            signals.append("metadata_terms")
        if (b in references[a] or a in references[b]
                or re.search(r"(?<![A-Za-z0-9_-])" + re.escape(b) + r"(?![A-Za-z0-9_-])", fa["body"])
                or re.search(r"(?<![A-Za-z0-9_-])" + re.escape(a) + r"(?![A-Za-z0-9_-])", fb["body"])):
            signals.append("explicit_reference")
        if fa["words"] & fb["words"]:
            signals.append("body_terms")
        if signals:
            pairs[(a, b)] = signals
    omissions = []
    if old:
        for relation in old["relations"]:
            a, b = _pair(relation["source_document_id"], relation["target_document_id"])
            if _dependencies(relation) & target_ids and a in docs and b in docs:
                pairs.setdefault((a, b), []).append("existing_relation")
        for record in _unresolved_deferred(old, docs).values():
            event = record["event"]
            if not set(event["context_document_ids"]) & target_ids:
                continue
            pair = _pair(event["source_document_id"], event["target_document_id"])
            if set(pair).issubset(docs):
                pairs.setdefault(pair, []).append("unresolved_deferred")
            else:
                # 기록을 허용 밖 파일 읽기로 확대하지 않으며 상세 ID도 노출하지 않는다.
                omissions.append("unresolved_deferred_endpoint_unavailable")
    return {"method": "explicit-metadata-body-existing", "status": "partial" if omissions else "complete",
            "considered_document_ids": sorted(docs),
            "candidates": [{"source_document_id": a, "target_document_id": b,
                            "signals": sorted(set(signals))} for (a, b), signals in sorted(pairs.items())],
            "omissions": sorted(set(omissions))}


def _node_map(graph):
    result = {}
    for node in graph["nodes"]:
        if node.get("node_role") == "document":
            identifier = node.get("document_id")
            if identifier in result:
                _fail("graph_document_id_collision")
            result[identifier] = node
    return result


def _endpoint(identifier, docs, graph, *, nodes=None):
    if identifier not in docs:
        _fail("relationship_endpoint_scope")
    nodes = _node_map(graph) if nodes is None else nodes
    doc = docs[identifier]
    if identifier not in nodes:
        _fail("relationship_endpoint_missing")
    node = nodes[identifier]
    if (node.get("source_file") != doc.path or node.get("source_sha256") != doc.sha256
            or node.get("tags") != doc.metadata["tags"]
            or node.get("aliases") != doc.metadata.get("aliases")):
        _fail("relationship_endpoint_stale")
    return node


def _support_current(support, docs):
    if support["status"] == "retracted":
        return "retracted"
    for e in support["evidence"]:
        if e["document_id"] not in docs:
            return "unavailable"
        doc = docs[e["document_id"]]
        if doc.sha256 != e["source_sha256"]:
            return "stale"
        if evidence_span(doc, e["start_line"], e["end_line"]) != e:
            return "stale"
    return "active"


def _relation_state(relation):
    states = {s["status"] for s in relation["support_sets"]}
    if "active" in states:
        return "active"
    for state in ("stale", "unavailable", "unknown"):
        if state in states:
            return state
    return "retracted"


def _validate_proposal(relation, docs, graph):
    relation = copy.deepcopy(relation)
    _relation_shape(relation)
    if relation["status"] != "active":
        _fail("relationship_proposal_status")
    for identifier in (relation["source_document_id"], relation["target_document_id"]):
        _endpoint(identifier, docs, graph)
    for support in relation["support_sets"]:
        if support["status"] != "active" or _support_current(support, docs) != "active":
            _fail("relationship_evidence_stale")
    return relation


def _request_plan(request, docs, target_ids, old):
    plan = request.get("candidate_plan")
    if (not isinstance(plan, dict) or set(plan) != {"method", "status", "considered_document_ids", "candidates", "omissions"}
            or not isinstance(plan.get("status"), str) or plan.get("status") not in {"complete", "partial", "not_run"}
            or not isinstance(plan.get("considered_document_ids"), list)
            or not isinstance(plan.get("candidates"), list) or not isinstance(plan.get("omissions"), list)):
        _fail("relationship_candidate_plan")
    _text(plan["method"])
    considered = plan["considered_document_ids"]
    if (any(not isinstance(x, str) for x in considered) or len(set(considered)) != len(considered)
            or not set(considered).issubset(docs)):
        _fail("relationship_candidate_scope")
    pairs = set()
    for item in plan["candidates"]:
        if (not isinstance(item, dict) or set(item) != {"source_document_id", "target_document_id", "signals"}
                or not isinstance(item["signals"], list) or not item["signals"]):
            _fail("relationship_candidate_invalid")
        pair = _pair(item["source_document_id"], item["target_document_id"])
        if not set(pair).issubset(considered) or pair in pairs:
            _fail("relationship_candidate_scope")
        for signal in item["signals"]:
            _text(signal)
        pairs.add(pair)
    for omission in plan["omissions"]:
        _text(omission)
    status = plan["status"]
    if set(considered) != set(docs) or plan["omissions"]:
        status = "partial" if status != "not_run" else status
    explicit = request.get("affected_relation_ids", [])
    if not isinstance(explicit, list) or len(set(explicit)) != len(explicit):
        _fail("relationship_change_scope")
    existing = {r["relation_id"]: r for r in old["relations"]}
    if not set(explicit).issubset(existing):
        _fail("relationship_change_scope")
    unavailable = request.get("unavailable_document_ids", [])
    removed = request.get("removed_document_ids", [])
    if any(not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids)
           for ids in (unavailable, removed)):
        _fail("relationship_change_scope")
    allowed_dependencies = set(docs) | set(unavailable) | set(removed)
    for identifier in explicit:
        if not _dependencies(existing[identifier]).issubset(allowed_dependencies):
            _fail("relationship_change_scope")
    affected = {rid for rid, relation in existing.items() if _dependencies(relation) & target_ids} | set(explicit)
    allowed_pairs = {_pair(r["source_document_id"], r["target_document_id"])
                     for rid, r in existing.items() if rid in affected}
    for proposal in request.get("relations", []):
        _relation_shape(proposal)
        if _dependencies(proposal) & target_ids:
            allowed_pairs.add(_pair(proposal["source_document_id"], proposal["target_document_id"]))
    if any(not (set(pair) & target_ids) and pair not in allowed_pairs for pair in pairs):
        _fail("relationship_change_scope")
    return copy.deepcopy(plan), pairs, status, affected


def _decisions(request, pairs, docs):
    result = {}
    for item in request.get("decisions", []):
        if (not isinstance(item, dict) or set(item) != {"source_document_id", "target_document_id", "decision", "relation_ids", "reason"}
                or not isinstance(item["decision"], str) or item["decision"] not in {"accepted", "no_relation", "deferred"}
                or not isinstance(item["relation_ids"], list)
                or any(not isinstance(x, str) for x in item["relation_ids"])):
            _fail("relationship_decision_invalid")
        pair = _pair(item["source_document_id"], item["target_document_id"])
        if pair not in pairs or pair in result or not set(pair).issubset(docs):
            _fail("relationship_decision_scope")
        _text(item["reason"])
        if (len(set(item["relation_ids"])) != len(item["relation_ids"])
                or (item["decision"] == "accepted") != bool(item["relation_ids"])):
            _fail("relationship_decision_invalid")
        result[pair] = copy.deepcopy(item)
    return result


def _typed_decisions(request, pairs, docs, existing, proposed, affected, pair_decisions, target_ids):
    items = request.get("assertion_decisions", [])
    if not isinstance(items, list):
        _fail("relationship_assertion_decision_invalid")
    normalized = {}
    for item in items:
        if not isinstance(item, dict):
            _fail("relationship_assertion_decision_invalid")
        selector_a = {"relation_id", "decision", "reason"}
        selector_b = {"source_document_id", "target_document_id", "kind", "qualifier", "decision", "reason"}
        if set(item) == selector_a:
            rid = _identifier(item["relation_id"])
            relation = proposed.get(rid, existing.get(rid))
            if relation is None:
                _fail("relationship_assertion_decision_selector")
            event = _assertion_descriptor(relation["source_document_id"], relation["target_document_id"],
                                          relation["kind"], relation["qualifier"])
        elif set(item) == selector_b:
            event = _assertion_descriptor(item["source_document_id"], item["target_document_id"],
                                          item["kind"], item["qualifier"])
            rid = event["relation_id"]
        else:
            _fail("relationship_assertion_decision_invalid")
        decision = item["decision"]
        if not isinstance(decision, str) or decision not in {"accepted", "no_relation", "deferred"}:
            _fail("relationship_assertion_decision_invalid")
        _text(item["reason"])
        pair = _pair(event["source_document_id"], event["target_document_id"])
        if pair not in pairs or not set(pair).issubset(docs):
            _fail("relationship_assertion_decision_scope")
        if rid in normalized:
            _fail("relationship_assertion_decision_duplicate")
        pair_decision = pair_decisions.get(pair)
        accepted_ids = set(pair_decision["relation_ids"]) if pair_decision and pair_decision["decision"] == "accepted" else set()
        if decision == "accepted":
            if rid not in accepted_ids or rid not in existing and rid not in proposed:
                _fail("relationship_assertion_decision_conflict")
        elif rid in accepted_ids:
            _fail("relationship_assertion_decision_conflict")
        if decision in {"deferred", "no_relation"}:
            if rid in existing and rid not in affected:
                _fail("relationship_change_scope")
            if rid not in existing and rid not in proposed and not set(pair) & target_ids:
                _fail("relationship_change_scope")
        context = {event["source_document_id"], event["target_document_id"]}
        for relation in (existing.get(rid), proposed.get(rid)):
            if relation is not None:
                context.update(_dependencies(relation))
        event.update(decision=decision, reason=item["reason"], context_document_ids=sorted(context))
        normalized[rid] = event
    # pair 보류는 이번에 승인된 영향 범위의 기존 assertions에만 확장한다.
    for pair, decision in pair_decisions.items():
        if decision["decision"] != "deferred":
            continue
        for rid, relation in existing.items():
            if _pair(relation["source_document_id"], relation["target_document_id"]) != pair:
                continue
            if rid not in affected:
                _fail("relationship_change_scope")
            previous = normalized.get(rid)
            if previous is not None:
                if previous["decision"] != "deferred":
                    _fail("relationship_assertion_decision_conflict")
                continue
            event = _assertion_descriptor(relation["source_document_id"], relation["target_document_id"],
                                          relation["kind"], relation["qualifier"])
            event.update(decision="deferred", reason=decision["reason"],
                         context_document_ids=sorted(_dependencies(relation)))
            normalized[rid] = event
    return normalized


def _current_assertion_supports(relation, docs, graph):
    """당시 실제 원문으로 검증한 모든 완전한 OR support와 그 context를 반환한다."""
    if relation["status"] != "active":
        return []
    try:
        endpoints = {relation["source_document_id"], relation["target_document_id"]}
        for identifier in endpoints:
            _endpoint(identifier, docs, graph)
        verified = []
        for support in sorted(relation["support_sets"], key=lambda s: s["support_id"]):
            if support["status"] == "active" and _support_current(support, docs) == "active":
                verified.append((support["support_id"], endpoints | {e["document_id"] for e in support["evidence"]}))
        return verified
    except g.GraphError:
        return []


def _current_assertion_context(relation, docs, graph):
    """하나의 완전한 현재 OR support를 대표로 선택한다."""
    verified = _current_assertion_supports(relation, docs, graph)
    return verified[0][1] if verified else None


def _updated_relations(old, request, docs, old_graph, graph, target_ids):
    plan, pairs, candidate_status, affected = _request_plan(request, docs, target_ids, old)
    decisions = _decisions(request, pairs, docs)
    proposals = request.get("relations", [])
    if not isinstance(proposals, list):
        _fail("relationship_assertion_invalid")
    proposed = {}
    for relation in proposals:
        value = _validate_proposal(relation, docs, graph)
        rid = value["relation_id"]
        if rid in proposed:
            _fail("relationship_duplicate_assertion")
        pair = _pair(value["source_document_id"], value["target_document_id"])
        decision = decisions.get(pair)
        if (not decision or decision["decision"] != "accepted" or rid not in decision["relation_ids"]
                or not (_dependencies(value) & target_ids or rid in affected)):
            _fail("relationship_decision_scope")
        proposed[rid] = value
    unavailable = request.get("unavailable_document_ids", [])
    removed = request.get("removed_document_ids", [])
    for ids in (unavailable, removed):
        if not isinstance(ids, list) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            _fail("relationship_change_scope")
    known_dependencies = set().union(*(_dependencies(r) for r in old["relations"])) if old["relations"] else set()
    if not (set(unavailable) | set(removed)).issubset(known_dependencies | target_ids):
        _fail("relationship_change_scope")
    retractions = request.get("retract_supports", [])
    if not isinstance(retractions, list):
        _fail("relationship_retraction_invalid")
    withdrawn = {}
    for item in retractions:
        if (not isinstance(item, dict) or set(item) != {"relation_id", "support_ids", "reason"}
                or item["relation_id"] not in affected or item["relation_id"] in withdrawn
                or not isinstance(item["support_ids"], list)):
            _fail("relationship_retraction_invalid")
        _text(item["reason"])
        relation = next(r for r in old["relations"] if r["relation_id"] == item["relation_id"])
        ids = {s["support_id"] for s in relation["support_sets"]}
        if len(set(item["support_ids"])) != len(item["support_ids"]) or not set(item["support_ids"]).issubset(ids):
            _fail("relationship_retraction_invalid")
        withdrawn[item["relation_id"]] = set(item["support_ids"])
    existing = {relation["relation_id"]: relation for relation in old["relations"]}
    typed = _typed_decisions(request, pairs, docs, existing, proposed, affected, decisions, target_ids)
    prior_pending = _unresolved_deferred(old, docs)
    explicit_proposals = set(proposed)
    deferred_ids = {rid for rid, event in typed.items() if event["decision"] == "deferred"}
    values = {}
    reviewed = set()
    old_nodes = _node_map(old_graph)
    renamed = {x["document_id"] for x in request.get("renamed_documents", [])}
    for original in old["relations"]:
        relation = copy.deepcopy(original)
        rid = relation["relation_id"]
        if rid not in affected:
            if _dependencies(relation) & (set(unavailable) | set(removed)):
                _fail("relationship_change_scope")
            values[rid] = relation
            continue
        pair = _pair(relation["source_document_id"], relation["target_document_id"])
        endpoint_state = None
        for identifier in pair:
            if identifier in removed:
                endpoint_state = "retracted"
                break
            if identifier in unavailable or identifier not in docs:
                endpoint_state = "unavailable"
            elif (identifier not in old_nodes or old_nodes[identifier].get("source_sha256") != docs[identifier].sha256
                  or (old_nodes[identifier].get("source_file") != docs[identifier].path and identifier not in renamed)):
                endpoint_state = endpoint_state or "stale"
        for support in relation["support_sets"]:
            if (support["support_id"] in withdrawn.get(rid, set())
                    or any(e["document_id"] in removed for e in support["evidence"])):
                support["status"] = "retracted"
            elif any(e["document_id"] in unavailable for e in support["evidence"]):
                support["status"] = "unavailable"
            else:
                support["status"] = _support_current(support, docs)
        relation["status"] = endpoint_state or _relation_state(relation)
        if relation["status"] == "active" and original["status"] != "active":
            relation["status"] = original["status"]
        if relation["status"] == "active" and (rid in deferred_ids or rid in prior_pending):
            relation["status"] = "unknown"
        decision = decisions.get(pair)
        if rid in proposed:
            incoming = proposed.pop(rid)
            previous_supports = {s["support_id"]: s for s in relation["support_sets"]}
            for support in incoming["support_sets"]:
                if support["support_id"] in withdrawn.get(rid, set()):
                    _fail("relationship_retraction_conflict")
                previous_supports[support["support_id"]] = support
            incoming["support_sets"] = sorted(previous_supports.values(), key=lambda s: s["support_id"])
            incoming["status"] = _relation_state(incoming)
            relation = incoming
            reviewed.add(rid)
        elif rid in withdrawn:
            reviewed.add(rid)
        elif (decision and decision["decision"] == "accepted" and rid in decision["relation_ids"]
              and relation["status"] == "active"):
            for identifier in pair:
                _endpoint(identifier, docs, graph)
            reviewed.add(rid)
        elif _dependencies(relation) & set(removed):
            reviewed.add(rid)
        values[rid] = relation
    values.update(proposed)
    reviewed.update(proposed)
    all_accepted = {rid for d in decisions.values() if d["decision"] == "accepted" for rid in d["relation_ids"]}
    for pair, decision in decisions.items():
        for rid in decision["relation_ids"]:
            if rid not in values or _pair(values[rid]["source_document_id"], values[rid]["target_document_id"]) != pair:
                _fail("relationship_decision_scope")
    if not all(rid in all_accepted for rid in set(values) - {r["relation_id"] for r in old["relations"]}):
        _fail("relationship_decision_scope")
    decision_conflicts = []
    for pair, decision in decisions.items():
        active_ids = {rid for rid, relation in values.items()
                      if relation["status"] == "active"
                      and _pair(relation["source_document_id"], relation["target_document_id"]) == pair}
        if ((decision["decision"] == "no_relation" and active_ids)
                or (decision["decision"] == "accepted" and set(decision["relation_ids"]) != active_ids)):
            decision_conflicts.append({"source_document_id": pair[0], "target_document_id": pair[1],
                                       "reason": "active_relations_remain" if decision["decision"] == "no_relation"
                                       else "accepted_ids_mismatch",
                                       "active_relation_ids": sorted(active_ids)})
        if decision["decision"] == "accepted":
            unverified, requires_proposal = [], []
            for rid in decision["relation_ids"]:
                relation = values[rid]
                context = _current_assertion_context(relation, docs, graph)
                if rid in prior_pending and rid not in explicit_proposals:
                    requires_proposal.append(rid)
                elif context is None:
                    unverified.append(rid)
                else:
                    event = typed.get(rid)
                    if event is None:
                        event = _assertion_descriptor(relation["source_document_id"], relation["target_document_id"],
                                                      relation["kind"], relation["qualifier"])
                        event.update(decision="accepted", reason=decision["reason"])
                    event["context_document_ids"] = sorted(context)
                    typed[rid] = event
            if unverified:
                decision_conflicts.append({"source_document_id": pair[0], "target_document_id": pair[1],
                                           "reason": "accepted_relations_unverified",
                                           "unverified_relation_ids": sorted(unverified)})
            if requires_proposal:
                decision_conflicts.append({"source_document_id": pair[0], "target_document_id": pair[1],
                                           "reason": "deferred_reacceptance_requires_proposal",
                                           "unverified_relation_ids": sorted(requires_proposal)})
    for rid, event in typed.items():
        relation = values.get(rid)
        if event["decision"] == "accepted":
            verified = [] if relation is None else _current_assertion_supports(relation, docs, graph)
            if (not verified or rid in prior_pending and rid not in explicit_proposals):
                _fail("relationship_assertion_decision_not_current")
            event["context_document_ids"] = sorted(verified[0][1])
            event["accepted_support_ids"] = [identifier for identifier, _ in verified]
        elif event["decision"] == "no_relation" and relation is not None:
            if relation["status"] != "retracted" or any(s["status"] != "retracted" for s in relation["support_sets"]):
                _fail("relationship_assertion_decision_conflict")
            reviewed.add(rid)
    # 미생성 assertion의 보류도 사건으로 보존하며, 동일 ID의 유효한 명시 사건만 해제한다.
    pending = dict(prior_pending)
    for rid, event in typed.items():
        if event["decision"] == "deferred":
            pending[rid] = {"event": event, "source_hashes": {i: docs[i].sha256 for i in event["context_document_ids"] if i in docs}}
        else:
            pending.pop(rid, None)
    relevant_pending = {rid for rid, record in pending.items()
                        if rid in affected
                        or _pair(record["event"]["source_document_id"], record["event"]["target_document_id"]) in pairs
                        or set(record["event"]["context_document_ids"]) & target_ids}
    relation_status = "complete"
    if decision_conflicts or relevant_pending:
        relation_status = "partial"
    elif candidate_status == "not_run":
        relation_status = "unknown"
    elif (candidate_status != "complete" or set(decisions) != pairs
          or any(d["decision"] == "deferred" for d in decisions.values())
          or not affected.issubset(reviewed)
          or any(values[rid]["status"] in {"stale", "unavailable", "unknown"} for rid in affected)):
        relation_status = "partial"
    review = {"targets": sorted(target_ids),
              "documents": [{"document_id": d.document_id, "path": d.path, "source_sha256": d.sha256}
                            for d in sorted(docs.values(), key=lambda d: d.document_id)],
              "candidate_plan": plan, "decision_conflicts": decision_conflicts,
              "assertion_decisions": [typed[rid] for rid in sorted(typed)],
              "decisions": sorted(decisions.values(), key=lambda d: _pair(d["source_document_id"], d["target_document_id"])),
              "candidate_status": candidate_status, "relation_status": relation_status,
              "retract_supports": copy.deepcopy(retractions),
              "unavailable_document_ids": sorted(unavailable), "removed_document_ids": sorted(removed),
              "affected_relation_ids": sorted(affected)}
    work_envelope = {"content_graph": graph, "relations": list(values.values()),
                     "relation_review": old["relation_review"] + [review]}
    work_status, judgment_summary, _ = _review_work(work_envelope, review, docs, affected_ids=affected)
    review.update(review_work_status=work_status, judgment_summary=judgment_summary)
    if old["relation_review"]:
        previous = old["relation_review"][-1]
        comparable = {key: value for key, value in previous.items()
                      if key not in {"review_id", "previous_review_id"}}
        if comparable == review:
            # 직전과 같은 관측은 중복 기록하지 않는다. 과거의 동일 내용으로
            # 되돌아오는 새 판단은 아래 인과 ID로 별개의 사건이 된다.
            return sorted(values.values(), key=lambda r: r["relation_id"]), copy.deepcopy(previous)
        review["previous_review_id"] = previous["review_id"]
    review["review_id"] = "review_" + _digest(review)
    return sorted(values.values(), key=lambda r: r["relation_id"]), review


def _merge_content(old, targets, chunks, expected_chunk_ids, renamed_documents=()):
    old = _partition_legacy(old)
    prepared = g._chunks(targets, chunks, expected_chunk_ids, old)
    if not targets.documents:
        if renamed_documents:
            _fail("relationship_rename_invalid")
        return copy.deepcopy(old)
    from graphify.validate import validate_extraction
    import networkx as nx
    if validate_extraction(prepared[0]):
        _fail("extraction_schema_invalid")
    paths = {d.path for d in targets.documents}
    docs = {d.document_id: d for d in targets.documents}
    previous = _node_map(old)
    rename_ids, rename_paths = set(), set()
    listed = set(g._active_paths(targets.scope.read(targets.active_path).data))
    for change in renamed_documents:
        if not isinstance(change, dict) or set(change) != {"document_id", "old_path", "new_path"}:
            _fail("relationship_rename_invalid")
        identifier = change["document_id"]
        if (identifier in rename_ids or identifier not in docs or identifier not in previous
                or change["old_path"] != previous[identifier].get("source_file")
                or change["new_path"] != docs[identifier].path
                or change["old_path"] == change["new_path"]):
            _fail("relationship_rename_invalid")
        g._relative(change["old_path"])
        g._relative(change["new_path"])
        change_paths = {change["old_path"], change["new_path"]}
        if change_paths & rename_paths or change["old_path"] in listed:
            _fail("relationship_rename_collision")
        for node in old["nodes"]:
            if node.get("source_file") in change_paths and not g._ast_tier(node) and node.get("document_id") != identifier:
                _fail("relationship_rename_collision")
        for edge in old["links"]:
            if edge.get("source_file") in change_paths and not g._ast_tier(edge) and edge.get("document_id") != identifier:
                _fail("relationship_rename_collision")
        rename_paths.update(change_paths)
        rename_ids.add(identifier)
        paths.add(change["old_path"])
    for identifier, doc in docs.items():
        if identifier in previous and previous[identifier].get("source_file") != doc.path and identifier not in rename_ids:
            _fail("relationship_rename_required")
    merged = g._build_from_snapshot(old, prepared, paths)
    value = g._graph_data(nx.node_link_data(merged, edges="links"))
    g._preserved(old, value, paths)
    nodes = {n["id"]: n for n in value["nodes"]}
    for node in prepared[0]["nodes"]:
        if node["id"] not in nodes or any(nodes[node["id"]].get(k) != v for k, v in node.items()):
            _fail("graph_new_node_changed")
    def edge_key(edge):
        ends = (edge["source"], edge["target"])
        return ends if value["directed"] else tuple(sorted(ends))
    actual_edges = {edge_key(edge): edge for edge in value["links"]}
    for edge in prepared[0]["edges"]:
        actual = actual_edges.get(edge_key(edge))
        if actual is None or any(actual.get(k) != v for k, v in edge.items()
                                 if value["directed"] or k not in ("source", "target")):
            _fail("graph_new_edge_changed")
    permitted = {n["id"] for n in old["nodes"]} | {n["id"] for n in prepared[0]["nodes"]}
    if not set(nodes).issubset(permitted):
        _fail("graph_unexpected_node")
    if any(x["status"] != "current" for x in g.graph_coverage(targets, value)):
        _fail("graph_candidate_coverage")
    return value


def project_graph(envelope, active_documents):
    """허용된 현재 원문과 유효 근거만을 담은 메모리용 Graphify simple graph."""
    value = parse_envelope(envelope)
    g._verify_current(active_documents)
    docs = {d.document_id: d for d in active_documents.documents}
    graph = value["content_graph"]
    current = {}
    try:
        nodes = _node_map(graph) if docs else {}
    except g.GraphError:
        # 중복 document ID는 기존의 endpoint별 검사처럼 모든 표시에서 제외한다.
        nodes = {}
    for identifier in docs:
        try:
            current[identifier] = _endpoint(identifier, docs, graph, nodes=nodes)
        except g.GraphError:
            continue
    by_path = {docs[i].path: i for i in current}
    owners = {}
    visible = []
    for node in graph["nodes"]:
        identifier = node.get("document_id") or by_path.get(node.get("source_file"))
        if (identifier in current and node.get("source_file") == docs[identifier].path
                and node.get("source_sha256", docs[identifier].sha256) == docs[identifier].sha256):
            owners[node["id"]] = identifier
            safe_fields = {"id", "label", "file_type", "node_role", "source_file", "source_location",
                           "document_id", "source_sha256", "tags", "aliases", "_origin"}
            visible.append({k: copy.deepcopy(v) for k, v in node.items() if k in safe_fields})
    links = []
    for edge in graph["links"]:
        a, b = edge["source"], edge["target"]
        # Legacy 교차 edge와 owner 미식별 edge는 확정 관계로 투영하지 않는다.
        if a in owners and b in owners and owners[a] == owners[b]:
            source = edge.get("source_file")
            if source in by_path and edge.get("source_sha256", docs[by_path[source]].sha256) == docs[by_path[source]].sha256:
                links.append({k: copy.deepcopy(edge[k]) for k in
                              ("source", "target", "relation", "confidence") if k in edge})
    pair_relations = {}
    pending = _unresolved_deferred(value, docs)
    for relation in value["relations"]:
        a, b = relation["source_document_id"], relation["target_document_id"]
        if relation["status"] != "active" or relation["relation_id"] in pending or a not in current or b not in current:
            continue
        if not any(s["status"] == "active" and _support_current(s, docs) == "active" for s in relation["support_sets"]):
            continue
        pair_relations.setdefault(_pair(a, b), []).append(relation)
    for pair, relations in sorted(pair_relations.items()):
        links.append({"source": current[pair[0]]["id"], "target": current[pair[1]]["id"],
                      "relation": "; ".join(sorted({r["kind"] + ": " + r["qualifier"] for r in relations})),
                      "confidence": "INFERRED", "assertion_ids": sorted(r["relation_id"] for r in relations)})
    # 방향이 다른 내부 edge도 하나의 무방향 물리 edge로 요약한다.
    collapsed = {}
    for edge in links:
        pair = tuple(sorted((edge["source"], edge["target"])))
        if pair not in collapsed:
            collapsed[pair] = dict(edge, source=pair[0], target=pair[1])
        else:
            previous = collapsed[pair]
            previous["relation"] = "; ".join(sorted(set(previous.get("relation", "").split("; ") + edge.get("relation", "").split("; "))))
            previous["assertion_ids"] = sorted(set(previous.get("assertion_ids", []) + edge.get("assertion_ids", [])))
    # 원형 graph metadata는 숨겨진 출처 목록·통계가 있을 수 있어 전달하지 않는다.
    return {"directed": False, "multigraph": False, "graph": {}, "nodes": visible,
            "links": [collapsed[p] for p in sorted(collapsed)]}


def _publication(targets, comparisons, old_bytes, candidate, *, graph_scope, graph_path,
                 expected_graph_sha256, work_scope, baseline_path, candidate_path,
                 backup_scope=None, backup_path=None):
    g._work_paths(work_scope, baseline_path, candidate_path, graph_scope, graph_path)
    baseline = old_bytes if old_bytes is not None else _encoded(_empty())
    work_scope.write(baseline_path, baseline)
    base = work_scope.read(baseline_path)
    encoded = _encoded(parse_envelope(candidate))
    work_scope.write(candidate_path, encoded)
    staged = work_scope.read(candidate_path)
    if staged.data != encoded or parse_envelope(staged.data) != candidate:
        _fail("graph_candidate_reload")
    def before_publish():
        g._verify_current(targets)
        g._verify_current(comparisons)
        if work_scope.read(baseline_path).data != baseline or work_scope.read(baseline_path).sha256 != base.sha256:
            raise ConflictError("graph_baseline_changed")
        if work_scope.read(candidate_path).sha256 != staged.sha256:
            raise ConflictError("graph_candidate_changed")
    before_publish()
    written = graph_scope.write(graph_path, encoded, expected_graph_sha256,
                                backup_scope=backup_scope, backup_path=backup_path,
                                _before_publish=before_publish)
    return encoded, written


def refresh_relationships(active_documents, chunks, *, expected_chunk_ids, graph_scope,
                          graph_path, expected_graph_sha256, work_scope, baseline_path,
                          candidate_path, relationship_request, backup_scope=None,
                          backup_path=None, read_only=False):
    """관계 요청을 한 번 검증·게시한다. v1 입력은 명시 이관 전까지 거부한다."""
    previous = None
    old_bytes = None
    publication_started = False
    candidate_status = relation_status = review_work_status = judgment_summary = None
    review_id = None
    try:
        if not isinstance(relationship_request, dict):
            _fail("relationship_request_invalid")
        allowed = {"comparisons", "candidate_plan", "decisions", "relations", "retract_supports",
                   "unavailable_document_ids", "removed_document_ids", "affected_relation_ids", "renamed_documents", "assertion_decisions"}
        if set(relationship_request) - allowed:
            _fail("relationship_request_invalid")
        docs, comparisons = _documents(active_documents, relationship_request.get("comparisons"))
        previous = g._optional_read(graph_scope, graph_path)
        old_bytes = previous.data if previous else None
        if expected_graph_sha256 != (previous.sha256 if previous else None):
            raise ConflictError("graph_expected_hash_changed")
        old = _empty() if previous is None else parse_envelope(old_bytes)
        coverage = g.graph_coverage(active_documents, old["content_graph"])
        if read_only:
            latest = old["relation_review"][-1] if old["relation_review"] else None
            work_status, summary, _ = _review_work(old, latest, docs)
            return g.GraphUpdateResult("current" if all(c["status"] == "current" for c in coverage) else "pending",
                                       coverage, graph_sha256=previous.sha256 if previous else None,
                                       review_work_status=work_status, judgment_summary=summary)
        renames = relationship_request.get("renamed_documents", [])
        if not isinstance(renames, list):
            _fail("relationship_rename_invalid")
        graph = _merge_content(old["content_graph"], active_documents, chunks, expected_chunk_ids, renames)
        relations, review = _updated_relations(old, relationship_request, docs, old["content_graph"], graph,
                                               {d.document_id for d in active_documents.documents})
        if renames:
            review["renamed_documents"] = copy.deepcopy(renames)
            review.pop("review_id")
            review["review_id"] = "review_" + _digest(review)
        candidate_status, relation_status, review_id = review["candidate_status"], review["relation_status"], review["review_id"]
        review_work_status, judgment_summary = review["review_work_status"], review["judgment_summary"]
        candidate = copy.deepcopy(old)
        candidate["content_graph"], candidate["relations"] = graph, relations
        # 동일 범위·hash·판단의 반복 저장은 기록을 증식시키지 않는다.
        if review_id not in {r["review_id"] for r in candidate["relation_review"]}:
            candidate["relation_review"].append(review)
        candidate = parse_envelope(candidate)
        g._work_paths(work_scope, baseline_path, candidate_path, graph_scope, graph_path)
        # write 호출이 게시 후 실패하는 경우까지 불확실성으로 보수적으로 보고한다.
        def tracking_write(*args, **kwargs):
            nonlocal publication_started
            publication_started = True
            return original_write(*args, **kwargs)
        original_write = graph_scope.write
        # publication_started는 파일 helper 실행 직전에만 설정한다.
        class PublicationScope:
            root_parts = graph_scope.root_parts
            write = staticmethod(tracking_write)
        encoded, written = _publication(active_documents, comparisons, old_bytes, candidate,
                                        graph_scope=PublicationScope(), graph_path=graph_path,
                                        expected_graph_sha256=expected_graph_sha256, work_scope=work_scope,
                                        baseline_path=baseline_path, candidate_path=candidate_path,
                                        backup_scope=backup_scope, backup_path=backup_path)
        if not written:
            publication_started = False
        saved = graph_scope.read(graph_path)
        g._verify_current(active_documents)
        g._verify_current(comparisons)
        if saved.data != encoded:
            raise ConflictError("graph_saved_changed")
        final = parse_envelope(saved.data)
        coverage = g.graph_coverage(active_documents, final["content_graph"])
        if any(x["status"] != "current" for x in coverage):
            _fail("graph_saved_coverage")
        return g.GraphUpdateResult("current", coverage, graph_sha256=saved.sha256,
                                   graph_written=bool(written), candidate_status=candidate_status,
                                   relation_status=relation_status, review_id=review_id,
                                   review_work_status=review_work_status, judgment_summary=judgment_summary)
    except Exception as exc:
        code = exc.code if isinstance(exc, FileError) else (
            "graph_dependency_unavailable" if isinstance(exc, ImportError) else "relationship_update_failed")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", code):
            code = "relationship_update_failed"
        observed_hash = None
        coverage = tuple({"path": d.path, "document_id": d.document_id, "status": "invalid"}
                         for d in active_documents.documents)
        try:
            observed = g._optional_read(graph_scope, graph_path) if publication_started else previous
            observed_hash = observed.sha256 if observed else None
            value = parse_envelope(observed.data) if observed else _empty()
            coverage = g._current_coverage(active_documents, value["content_graph"])
        except Exception:
            pass
        return g.GraphUpdateResult("pending", coverage, code, graph_sha256=observed_hash,
                                   graph_written=None if publication_started else False,
                                   publication_uncertain=publication_started, candidate_status=candidate_status,
                                   relation_status=relation_status, review_id=review_id,
                                   review_work_status=review_work_status, judgment_summary=judgment_summary)


def _tracked_scope(graph_scope, state):
    class Scope:
        root_parts = graph_scope.root_parts

        def write(self, *args, **kwargs):
            state[0] = True
            return graph_scope.write(*args, **kwargs)
    return Scope()


def _transition_failure(exc, state, graph_scope, graph_path):
    code = exc.code if isinstance(exc, FileError) else "relationship_transition_failed"
    if not re.fullmatch(r"[a-z][a-z0-9_]*", code):
        code = "relationship_transition_failed"
    observed_hash = None
    try:
        observed = g._optional_read(graph_scope, graph_path)
        observed_hash = observed.sha256 if observed else None
    except Exception:
        pass
    return {"status": "pending", "error_code": code,
            "graph_written": None if state[0] else False,
            "publication_uncertain": state[0], "graph_sha256": observed_hash}


def publish_migration(active_documents, *, graph_scope, graph_path, expected_graph_sha256,
                      work_scope, baseline_path, candidate_path, backup_scope=None, backup_path=None):
    """호출자가 명시 승인한 v1→v2 전환 한 번. 설치·갱신이 자동 호출하지 않는다.

    입력·기대 hash 오류는 쓰기 전에 예외로 거부한다. 게시 구간의 실패는
    status=pending/publication_uncertain으로 반환하며 자동 복구하지 않는다.
    """
    g._verify_current(active_documents)
    old = graph_scope.read(graph_path)
    if old.sha256 != expected_graph_sha256:
        raise ConflictError("graph_expected_hash_changed")
    candidate = parse_envelope(migrate_graph(old.data))
    state = [False]
    try:
        encoded, written = _publication(active_documents, active_documents, old.data, candidate,
                                        graph_scope=_tracked_scope(graph_scope, state), graph_path=graph_path,
                                        expected_graph_sha256=expected_graph_sha256, work_scope=work_scope,
                                        baseline_path=baseline_path, candidate_path=candidate_path,
                                        backup_scope=backup_scope, backup_path=backup_path)
        if not written:
            state[0] = False
        saved = graph_scope.read(graph_path)
        g._verify_current(active_documents)
        if saved.data != encoded:
            raise ConflictError("graph_saved_changed")
        return {"status": "current", "graph_written": bool(written), "graph_sha256": saved.sha256,
                "relation_status": "unknown", "publication_uncertain": False}
    except Exception as exc:
        return _transition_failure(exc, state, graph_scope, graph_path)


def restore_graph(*, graph_scope, graph_path, expected_graph_sha256, restore_bytes,
                  backup_scope, backup_path):
    """명시 복구 범위에서 현재 v2를 백업하고 검증한 snapshot을 조건부 복구한다."""
    current = graph_scope.read(graph_path)
    if current.sha256 != expected_graph_sha256:
        raise ConflictError("graph_expected_hash_changed")
    parse_envelope(current.data)
    if not isinstance(restore_bytes, bytes):
        _fail("relationship_restore_invalid")
    try:
        parse_envelope(restore_bytes)
    except g.GraphError:
        g._graph_data(restore_bytes)
    state = [False]
    try:
        changed = _tracked_scope(graph_scope, state).write(
            graph_path, restore_bytes, expected_graph_sha256,
            backup_scope=backup_scope, backup_path=backup_path)
        if not changed:
            state[0] = False
        saved = graph_scope.read(graph_path)
        if saved.data != restore_bytes:
            raise ConflictError("graph_saved_changed")
        return {"status": "current", "graph_written": bool(changed), "graph_sha256": saved.sha256,
                "publication_uncertain": False}
    except Exception as exc:
        return _transition_failure(exc, state, graph_scope, graph_path)
