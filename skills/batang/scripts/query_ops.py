"""명시된 현재 파일의 읽기 전용 조회. CLI·모델·영속 상태를 만들지 않는다.

QueryContext는 호스트가 고정 호출 안에서 구성한다. context_id는 전달 문맥을
구별할 뿐 권한이 아니며, 실제 전달을 확인한 ref만 confirm_seen으로 기록한다.
각 함수는 JSON으로 직렬화 가능한 제한된 packet을 반환한다. currentness는
snapshot 대응이며 관계의 의미적 타당성이나 추출 완료 판정이 아니다.
"""
from dataclasses import dataclass
from collections import deque
import copy
import json
import re
import uuid

from file_ops import FileScope, FileError, ConflictError, SHA256, parse_document, sha256
import graph_ops as g
import relationship_ops as r


@dataclass(frozen=True)
class QueryLimits:
    max_items: int = 20
    max_bytes: int = 16384
    max_excerpt_bytes: int = 2048
    max_depth: int = 4

    def __post_init__(self):
        if (any(type(v) is not int or v < 1 for v in
                (self.max_items, self.max_bytes, self.max_excerpt_bytes))
                or self.max_bytes < 512 or type(self.max_depth) is not int
                or not 0 <= self.max_depth <= 32):
            raise FileError("query_limits_invalid")


class QueryContext:
    """명시 FileScope·선택 목록과 비영속 전달 문맥. 자동 상태 복원은 없다."""
    def __init__(self, note_scope, active_path, selected_paths, *, graph_scope=None,
                 graph_path=None, context_id=None):
        if (not isinstance(note_scope, FileScope)
                or isinstance(selected_paths, (str, bytes)) or selected_paths is None
                or ((graph_scope is None) != (graph_path is None))
                or (graph_scope is not None and not isinstance(graph_scope, FileScope))):
            raise FileError("query_context_invalid")
        self.note_scope = note_scope
        self.active_path = g._relative(active_path)
        self.selected_paths = tuple(selected_paths)
        if (any(not isinstance(p, str) for p in self.selected_paths)
                or len(set(self.selected_paths)) != len(self.selected_paths)):
            raise FileError("query_scope_invalid")
        for path in self.selected_paths:
            g._relative(path)
        self.graph_scope, self.graph_path = graph_scope, graph_path
        if graph_path is not None:
            g._relative(graph_path)
        self.context_id = str(uuid.uuid4()) if context_id is None else context_id
        if not isinstance(self.context_id, str) or not self.context_id:
            raise FileError("query_context_invalid")
        self.seen_refs = []

    def confirm_seen(self, refs):
        """호스트가 이 모델 문맥에 실제 전달한 refs만 명시적으로 확인한다."""
        if not isinstance(refs, (list, tuple)) or any(not isinstance(x, dict) for x in refs):
            raise FileError("query_seen_invalid")
        self.seen_refs.extend(copy.deepcopy(refs))

    def clear_seen(self):
        self.seen_refs.clear()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def _limits(limits):
    if limits is None:
        return QueryLimits()
    if not isinstance(limits, QueryLimits):
        raise FileError("query_limits_invalid")
    return limits


def _packet(status="ok", **extra):
    return dict(status=status, items=[], next_cursor=None, truncated=False,
                omissions=[], currentness="snapshot_only", **extra)


def _error(exc):
    if isinstance(exc, ConflictError):
        return _packet("stale", error_code="query_cursor_changed" if exc.code == "query_cursor_changed"
                       else "query_snapshot_changed")
    if isinstance(exc, FileNotFoundError):
        return _packet("error", error_code="query_source_missing")
    if isinstance(exc, OSError):
        return _packet("error", error_code="query_io_error")
    code = getattr(exc, "code", "")
    if code in {"query_scope_invalid", "path_not_allowed", "active_selection_invalid"}:
        code = "query_scope_invalid"
    elif code == "path_symlink":
        code = "query_path_unavailable"
    elif code == "graph_data_size":
        code = "query_graph_limit"
    elif code.startswith(("graph_", "relationship_")):
        code = "query_graph_invalid"
    elif code.startswith(("metadata_", "frontmatter_", "yaml_", "schema_")):
        code = "query_document_invalid"
    elif code not in {"query_context_invalid", "query_limits_invalid", "query_search_invalid",
                      "query_reference_invalid", "query_seen_invalid", "query_graph_invalid",
                      "query_selector_invalid", "query_operation_invalid", "query_view_invalid",
                      "query_review_invalid", "query_document_collision", "query_excerpt_too_small"}:
        code = "query_invalid_or_unavailable"
    return _packet("error", error_code=code)


def _safe(function):
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except (FileError, OSError, UnicodeError, ValueError, TypeError, KeyError,
                RecursionError):
            # 이름·경로·개수·손상 원문은 오류 상세로 반환하지 않는다.
            import sys
            return _error(sys.exc_info()[1])
    call.__name__, call.__doc__ = function.__name__, function.__doc__
    return call


def _selection(context):
    if not isinstance(context, QueryContext):
        raise FileError("query_context_invalid")
    snapshot = context.note_scope.read(context.active_path)
    listed = set(g._active_paths(snapshot.data))
    selected = sorted(context.selected_paths)
    if any(p not in listed or tuple(p.split("/")) not in context.note_scope.allowed
           for p in selected):
        raise FileError("query_scope_invalid")
    return snapshot, selected


def _document(scope, path):
    snapshot = scope.read(path)
    metadata, body = parse_document(snapshot.data)
    body.decode("utf-8")
    return g.Document(scope, path, snapshot.sha256, metadata, body)


def _verify(context, active_hash, hashes):
    if context.note_scope.read(context.active_path).sha256 != active_hash:
        raise ConflictError("query_active_changed")
    for path, digest in hashes:
        if context.note_scope.read(path).sha256 != digest:
            raise ConflictError("query_source_changed")


def _identity(context, active_hash, hashes, query, graph_hash=None):
    value = [context.note_scope.root_parts, sorted(context.note_scope.allowed),
             context.active_path, active_hash, sorted(context.selected_paths), hashes,
             query, graph_hash]
    if context.graph_scope is not None:
        value.extend([context.graph_scope.root_parts, sorted(context.graph_scope.allowed),
                      context.graph_path])
    return sha256(_json(value))


def _offset(cursor, fingerprint):
    if cursor is None:
        return 0
    if (not isinstance(cursor, dict) or set(cursor) != {"fingerprint", "offset"}
            or cursor["fingerprint"] != fingerprint
            or type(cursor["offset"]) is not int or cursor["offset"] < 0):
        raise ConflictError("query_cursor_changed")
    return cursor["offset"]


def _page(items, *, fingerprint, cursor, limits, extra=None):
    """중단 위치는 원 후보 순서에 결합한다. 전달되지 않은 ref는 seen이 아니다."""
    start = _offset(cursor, fingerprint)
    result = _packet(**(extra or {}))
    consumed, total = start, 0
    for index, item in enumerate(items):
        total = index + 1
        if index < start:
            continue
        if len(result["items"]) >= limits.max_items:
            break
        if "_limit" in item:
            result.update(status="partial" if result["items"] else "limit", truncated=True,
                          next_cursor={"fingerprint": fingerprint, "offset": consumed},
                          omissions=[item["_limit"]],
                          required_excerpt_bytes=item["required_excerpt_bytes"])
            return result if len(_json(result)) <= limits.max_bytes else _packet("limit", error_code="query_metadata_exceeds_limit")
        proposed = copy.deepcopy(result)
        proposed["items"].append(item)
        following = consumed + 1
        proposed.update(status="partial", truncated=True,
                        next_cursor={"fingerprint": fingerprint, "offset": following},
                        omissions=["response_limit"])
        if len(_json(proposed)) > limits.max_bytes:
            break
        result = proposed
        consumed = following
    else:
        if start > total:
            raise ConflictError("query_cursor_changed")
        result.update(status="ok" if result["items"] else "absent", truncated=False,
                      next_cursor=None, omissions=[])
        return result if len(_json(result)) <= limits.max_bytes else _packet("limit", error_code="query_metadata_exceeds_limit")
    if consumed < total:
        result.update(status="partial" if result["items"] else "limit", truncated=True,
                      next_cursor={"fingerprint": fingerprint, "offset": consumed},
                      omissions=["response_limit" if result["items"] else "item_exceeds_byte_limit"])
    if len(_json(result)) > limits.max_bytes:
        # 추가 메타데이터도 전체 응답 예산에 포함한다.
        result = _packet("limit", error_code="query_metadata_exceeds_limit")
    return result


def _ref(context, doc, start, end):
    offsets = _line_offsets(doc.body)
    first = next(i for i, (a, b) in enumerate(offsets, 1) if a <= start < b)
    last = next(i for i, (a, b) in enumerate(offsets, 1) if a < end <= b)
    return {"context_id": context.context_id, "path": doc.path,
            "document_id": doc.document_id, "source_sha256": doc.sha256,
            "start_line": first, "end_line": last, "start_byte": start,
            "end_byte": end, "span_sha256": sha256(doc.body[start:end])}


def _line_offsets(body):
    result, offset = [], 0
    for line in body.splitlines(keepends=True):
        result.append((offset, offset + len(line)))
        offset += len(line)
    return result


def _seen_ranges(context, doc, seen_refs):
    refs = context.seen_refs if seen_refs is None else seen_refs
    if not isinstance(refs, (list, tuple)):
        raise FileError("query_seen_invalid")
    ranges = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise FileError("query_seen_invalid")
        if (ref.get("context_id") != context.context_id or ref.get("path") != doc.path
                or ref.get("document_id") != doc.document_id
                or ref.get("source_sha256") != doc.sha256):
            continue
        a, b = ref.get("start_byte"), ref.get("end_byte")
        if (type(a) is int and type(b) is int and 0 <= a < b <= len(doc.body)
                and sha256(doc.body[a:b]) == ref.get("span_sha256")):
            try:
                if _request_range(doc, ref) == (a, b):
                    ranges.append((a, b))
            except FileError:
                continue
    return sorted(ranges)


def _unseen(start, end, ranges):
    intervals = [(start, end)]
    for a, b in ranges:
        intervals = [(x, y) for left, right in intervals
                     for x, y in ((left, min(right, a)), (max(left, b), right)) if x < y]
    return intervals


def _chunks(body, start, end, size):
    while start < end:
        stop = min(end, start + size)
        while stop > start:
            try:
                body[start:stop].decode("utf-8")
                break
            except UnicodeError:
                stop -= 1
        if stop == start:
            raise FileError("query_excerpt_too_small")
        yield start, stop
        start = stop


def _spans(context, doc, start, end, limits, seen_refs):
    ranges = _seen_ranges(context, doc, seen_refs)
    # 저장 evidence_span과 같은 완전 줄만 참조한다. 긴 줄을 임의 절단하지 않는다.
    for a, b in _line_offsets(doc.body):
        if a < start or b > end:
            continue
        if b - a > limits.max_excerpt_bytes:
            yield {"_limit": "line_exceeds_excerpt_limit", "required_excerpt_bytes": b - a}
            continue
        fragments = [{"ref": _ref(context, doc, x, y),
                      "text": doc.body[x:y].decode("utf-8")}
                     for x, y in _unseen(a, b, ranges)]
        yield {"ref": _ref(context, doc, a, b), "spans": fragments,
               "already_seen": not fragments}


@_safe
def search(context, query, *, fields=("title", "id", "tags", "aliases", "body"),
           limits=None, cursor=None, seen_refs=None):
    """선택 문서를 순차로 읽는 결정적 부분문자열 검색. 의미 검색은 아니다."""
    limits = _limits(limits)
    if (not isinstance(query, str) or not query.strip() or not isinstance(fields, (list, tuple))
            or not fields or len(set(fields)) != len(fields)
            or not set(fields).issubset({"title", "id", "tags", "aliases", "body"})):
        raise FileError("query_search_invalid")
    active, paths = _selection(context)
    hashes, ids = [], set()
    needle = query.casefold()
    for path in paths:
        doc = _document(context.note_scope, path)
        if doc.document_id in ids:
            raise FileError("query_document_collision")
        ids.add(doc.document_id)
        hashes.append((path, doc.sha256))
    def matches():
        # 본문을 모든 후보 packet으로 누적하지 않는다. 한 문서와 반환 페이지만 보유한다.
        for path in paths:
            doc = _document(context.note_scope, path)
            values = {"title": [doc.metadata["subject"]], "id": [doc.document_id],
                      "tags": doc.metadata["tags"], "aliases": doc.metadata.get("aliases", [])}
            matched = [field for field in fields if field != "body" and
                       any(needle in value.casefold() for value in values[field])]
            offsets = _line_offsets(doc.body)
            body_match = False
            for a, b in offsets:
                if "body" not in fields or needle not in doc.body[a:b].decode("utf-8").casefold():
                    continue
                body_match = True
                for item in _spans(context, doc, a, b, limits, seen_refs):
                    yield dict(item, path=path, document_id=doc.document_id,
                               matched_fields=matched + ["body"])
            if matched and not body_match:
                if offsets:
                    for item in _spans(context, doc, *offsets[0], limits, seen_refs):
                        yield dict(item, path=path, document_id=doc.document_id, matched_fields=matched)
                else:
                    yield {"path": path, "document_id": doc.document_id,
                           "source_sha256": doc.sha256, "matched_fields": matched, "spans": []}
    fingerprint = _identity(context, active.sha256, hashes,
                            ["search", query, list(fields)])
    result = _page(matches(), fingerprint=fingerprint, cursor=cursor, limits=limits,
                   extra={"method": "literal_casefold", "semantic_completeness": "not_assessed"})
    _verify(context, active.sha256, hashes)
    return result


def _request_range(doc, request):
    if (not isinstance(request, dict) or request.get("document_id") != doc.document_id
            or not isinstance(request.get("source_sha256"), str)
            or not SHA256.fullmatch(request["source_sha256"])
            or not isinstance(request.get("span_sha256"), str)
            or not SHA256.fullmatch(request["span_sha256"])):
        raise FileError("query_reference_invalid")
    if request["source_sha256"] != doc.sha256:
        raise ConflictError("query_source_changed")
    first, last = request.get("start_line"), request.get("end_line")
    offsets = _line_offsets(doc.body)
    if (type(first) is not int or type(last) is not int
            or not 1 <= first <= last <= len(offsets)):
        raise FileError("query_reference_invalid")
    a, b = offsets[first - 1][0], offsets[last - 1][1]
    if "start_byte" in request or "end_byte" in request:
        x, y = request.get("start_byte"), request.get("end_byte")
        if type(x) is not int or type(y) is not int or (x, y) != (a, b):
            raise FileError("query_reference_invalid")
        a, b = x, y
    doc.body[a:b].decode("utf-8")
    if sha256(doc.body[a:b]) != request["span_sha256"]:
        raise ConflictError("query_span_changed")
    return a, b


@_safe
def read_spans(context, requests, *, limits=None, cursor=None, seen_refs=None):
    """현재 선택 문서의 hash가 있는 실제 참조만 확인해 전달한다."""
    limits = _limits(limits)
    if not isinstance(requests, (list, tuple)):
        raise FileError("query_reference_invalid")
    active, paths = _selection(context)
    if any(not isinstance(x, dict) or x.get("path") not in paths for x in requests):
        raise FileError("query_scope_invalid")
    items, hashes, docs = [], [], {}
    # 요청하지 않은 본문은 읽지 않는다. cursor는 이 요청의 source snapshot에 결합한다.
    for path in sorted({x["path"] for x in requests}):
        docs[path] = _document(context.note_scope, path)
        hashes.append((path, docs[path].sha256))
    if len({d.document_id for d in docs.values()}) != len(docs):
        raise FileError("query_document_collision")
    for request in requests:
        doc = docs[request["path"]]
        a, b = _request_range(doc, request)
        items.extend(_spans(context, doc, a, b, limits, seen_refs))
    _verify(context, active.sha256, hashes)
    fingerprint = _identity(context, active.sha256, hashes,
                            ["read_spans", requests])
    return _page(items, fingerprint=fingerprint, cursor=cursor, limits=limits)


def _load(context):
    active, paths = _selection(context)
    docs = tuple(_document(context.note_scope, p) for p in paths)
    if len({d.document_id for d in docs}) != len(docs):
        raise FileError("query_document_collision")
    result = g.ActiveDocuments(context.note_scope, context.active_path, active.sha256, docs)
    g._verify_current(result)
    return result


def _graph(context):
    if context.graph_scope is None:
        return None, None
    try:
        snapshot = context.graph_scope.read(context.graph_path)
    except FileNotFoundError:
        return None, None
    value = g._json(snapshot.data)
    if not isinstance(value, dict):
        raise FileError("query_graph_invalid")
    if "batang_graph_format" in value:
        if (type(value["batang_graph_format"]) is not int or value["batang_graph_format"] != 2
                or set(value) != {"batang_graph_format", "content_graph", "relations", "relation_review"}
                or not isinstance(value["relations"], list) or not isinstance(value["relation_review"], list)):
            raise FileError("query_graph_invalid")
        # 일반 조회는 history folding·deferred 계산·project_graph를 수행하지 않는다.
        g._graph_data(value["content_graph"])
        ids = set()
        for relation in value["relations"]:
            r._relation_shape(relation)
            if relation["relation_id"] in ids:
                raise FileError("query_graph_invalid")
            ids.add(relation["relation_id"])
    else:
        g._graph_data(value)
    return value, snapshot.sha256


def _hidden_tokens(graph, docs):
    content = graph.get("content_graph", graph)
    allowed_ids, allowed_paths = set(docs), {d.path for d in docs.values()}
    tokens, private_names = set(), set()
    public_names = {name for doc in docs.values()
                    for name in (doc.metadata["subject"], *doc.metadata.get("aliases", []))}
    for node in content["nodes"]:
        if node.get("document_id") in allowed_ids and node.get("source_file") in allowed_paths:
            public_names.update(x for x in (node.get("label"), *node.get("aliases", []))
                                if isinstance(x, str) and x)
    for node in content["nodes"]:
        owner = node.get("document_id")
        path = node.get("source_file")
        if (owner is not None and owner not in allowed_ids) or (path is not None and path not in allowed_paths):
            tokens.update(x for x in (owner, path, node.get("id"))
                          if isinstance(x, str) and x)
            private_names.update(x for x in (node.get("label"), *node.get("aliases", []))
                                 if isinstance(x, str) and x)
    for relation in graph.get("relations", []):
        tokens.update(r._dependencies(relation) - allowed_ids)
    return tokens | (private_names - public_names)


def _mentions_hidden(value, tokens):
    if isinstance(value, str):
        # 한국어 조사(예: 숨은ID의)가 붙어도 식별자를 놓치지 않는다. hash 안의
        # 짧은 ASCII ID를 부분일치로 오인하지 않도록 ASCII 경계는 유지한다.
        return any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(token) + r"(?![A-Za-z0-9_])", value)
                   for token in tokens)
    if isinstance(value, list):
        return any(_mentions_hidden(x, tokens) for x in value)
    if isinstance(value, dict):
        return any(_mentions_hidden(x, tokens) for x in value.values())
    return False


def _records(graph, docs):
    tokens = _hidden_tokens(graph, docs)
    records = []
    if "batang_graph_format" in graph:
        coverage = {item["document_id"]: item["status"]
                    for item in g.graph_coverage(docs.values(), graph["content_graph"])}
        for relation in graph["relations"]:
            if not r._dependencies(relation).issubset(docs) or _mentions_hidden(relation, tokens):
                continue
            state = [coverage.get(identifier, "unknown") for identifier in
                     (relation["source_document_id"], relation["target_document_id"])]
            for support in relation["support_sets"]:
                for evidence in support["evidence"]:
                    doc = docs[evidence["document_id"]]
                    try:
                        actual = r.evidence_span(doc, evidence["start_line"], evidence["end_line"])
                        current = actual == evidence
                    except FileError:
                        current = False
                    state.append("current" if current else "stale")
            records.append({"record": copy.deepcopy(relation),
                            "currentness": "stale" if "stale" in state else
                            "current" if state and all(s == "current" for s in state) else "unknown"})
        return records, 2
    content = g._graph_data(graph)
    safe_nodes = {}
    for node in content["nodes"]:
        owner = node.get("document_id")
        if owner is None:
            owner = next((i for i, d in docs.items() if d.path == node.get("source_file")), None)
        if (owner in docs and node.get("source_file") == docs[owner].path
                and not _mentions_hidden(node, tokens)):
            safe_nodes[node["id"]] = (node, owner)
    fields = {"source", "target", "relation", "confidence", "source_file", "document_id",
              "source_sha256", "source_location", "_origin", "rationale"}
    node_fields = {"id", "label", "file_type", "node_role", "source_file", "source_location",
                   "document_id", "source_sha256", "tags", "aliases", "_origin"}
    for edge in content["links"]:
        if edge["source"] not in safe_nodes or edge["target"] not in safe_nodes:
            continue
        if (edge.get("document_id", safe_nodes[edge["source"]][1]) not in docs
                or ("source_file" in edge and edge["source_file"] not in {d.path for d in docs.values()})
                or _mentions_hidden(edge, tokens)):
            continue
        nodes = [safe_nodes[i] for i in dict.fromkeys((edge["source"], edge["target"]))]
        current = all(node.get("source_sha256") == docs[owner].sha256 for node, owner in nodes)
        if "source_sha256" in edge:
            current &= edge["source_sha256"] in {docs[owner].sha256 for _, owner in nodes}
        records.append({"record": {k: copy.deepcopy(v) for k, v in edge.items() if k in fields},
                        "nodes": [{k: copy.deepcopy(v) for k, v in node.items() if k in node_fields}
                                  for node, _ in nodes],
                        "currentness": "current" if current else "stale"})
    return records, 1


def _endpoints(item, version):
    record = item["record"]
    return ((record["source_document_id"], record["target_document_id"])
            if version == 2 else (record["source"], record["target"]))


def _record_scope(context, active, item, graph_hash):
    """문자열 query와 출력 래퍼가 아닌 실제 권한·참조 source snapshot에 결합한다."""
    record = item.get("record", item)
    ids = set(record.get("context_document_ids", []))
    ids.update(record[k] for k in ("source_document_id", "target_document_id") if k in record)
    if "support_sets" in record:
        ids.update(e["document_id"] for s in record["support_sets"] for e in s["evidence"])
    paths = {n["source_file"] for n in item.get("nodes", []) if "source_file" in n}
    if "source_file" in record:
        paths.add(record["source_file"])
    hashes = [(d.path, d.sha256) for d in active.documents if d.document_id in ids or d.path in paths]
    return _identity(context, active.active_sha256, hashes, None, graph_hash)


def _record_item(context, item, graph_hash, active, seen_refs=None):
    payload = {k: v for k, v in item.items() if k != "type"}
    ref = {"context_id": context.context_id, "graph_sha256": graph_hash,
           "scope_sha256": _record_scope(context, active, item, graph_hash),
           "record_sha256": sha256(_json(payload))}
    refs = context.seen_refs if seen_refs is None else seen_refs
    if not isinstance(refs, (list, tuple)):
        raise FileError("query_seen_invalid")
    if ref in refs:
        return {"record_ref": ref, "already_seen": True,
                **({"type": item["type"]} if "type" in item else {})}
    return dict(item, record_ref=ref, already_seen=False)


def _source_spans(context, scope, path, snapshot, limits, seen_refs):
    refs = context.seen_refs if seen_refs is None else seen_refs
    if not isinstance(refs, (list, tuple)):
        raise FileError("query_seen_invalid")
    scope_id = sha256(_json([scope.root_parts, sorted(scope.allowed)]))
    ranges = []
    for ref in refs:
        if not isinstance(ref, dict):
            raise FileError("query_seen_invalid")
        if (ref.get("context_id") != context.context_id or ref.get("source_path") != path
                or ref.get("source_scope_sha256") != scope_id
                or ref.get("source_sha256") != snapshot.sha256):
            continue
        a, b = ref.get("start_byte"), ref.get("end_byte")
        if (type(a) is int and type(b) is int and 0 <= a < b <= len(snapshot.data)
                and sha256(snapshot.data[a:b]) == ref.get("span_sha256")):
            snapshot.data[a:b].decode("utf-8")
            ranges.append((a, b))
    for a, b in _chunks(snapshot.data, 0, len(snapshot.data), limits.max_excerpt_bytes):
        spans = []
        for x, y in _unseen(a, b, sorted(ranges)):
            ref = {"context_id": context.context_id, "source_scope_sha256": scope_id,
                   "source_path": path, "source_sha256": snapshot.sha256,
                   "start_byte": x, "end_byte": y, "span_sha256": sha256(snapshot.data[x:y])}
            spans.append({"ref": ref, "text": snapshot.data[x:y].decode("utf-8")})
        yield {"type": "source_content", "source_path": path,
               "source_sha256": snapshot.sha256, "spans": spans, "already_seen": not spans}


def _decision_allowed(decision, docs, visible_ids, existing_ids, hidden):
    ids = set(decision.get("context_document_ids", [])) | {
        decision.get("source_document_id"), decision.get("target_document_id")}
    ids.discard(None)
    relation_ids = set(decision.get("relation_ids", []))
    if "relation_id" in decision:
        relation_ids.add(decision["relation_id"])
    return (ids.issubset(docs) and not (relation_ids & existing_ids) - visible_ids
            and not _mentions_hidden(decision, hidden))


def _review_plan(targets, comparisons, envelope, docs, records):
    """숨겨진 저장 기록의 신호·보류·omission을 후보 packet으로 옮기지 않는다."""
    plan = r.discover_candidates(targets, comparisons)
    if envelope is None:
        return plan
    # 관계 검토 준비에서는 기존 계약으로 원형을 검증하되 출력 범위는 별도로 좁힌다.
    value = r.parse_envelope(envelope)
    visible = {x["record"]["relation_id"]: x["record"] for x in records}
    existing_ids = {x["relation_id"] for x in value["relations"]}
    hidden = _hidden_tokens(value, docs)
    scoped_reviews = []
    for review in value["relation_review"]:
        snapshots = r._review_snapshots(review, strict="assertion_decisions" in review)
        events = [event for event in r._review_assertion_events(
            review, visible, value["content_graph"], docs)
            if _decision_allowed(event, docs, set(visible), existing_ids, hidden)]
        scoped_reviews.append({"documents": [record for identifier, record in snapshots.items()
                                                if identifier in docs and record["path"] == docs[identifier].path],
                               "assertion_decisions": events})
    scoped = {"relations": list(visible.values()), "content_graph": value["content_graph"],
              "relation_review": scoped_reviews}
    pairs = {(x["source_document_id"], x["target_document_id"]): list(x["signals"])
             for x in plan["candidates"]}
    target_ids = {d.document_id for d in targets.documents}
    for relation in visible.values():
        if r._dependencies(relation) & target_ids:
            pair = r._pair(relation["source_document_id"], relation["target_document_id"])
            pairs.setdefault(pair, []).append("existing_relation")
    for pending in r._unresolved_deferred(scoped, docs).values():
        event = pending["event"]
        if set(event["context_document_ids"]) & target_ids:
            pair = r._pair(event["source_document_id"], event["target_document_id"])
            pairs.setdefault(pair, []).append("unresolved_deferred")
    plan["candidates"] = [{"source_document_id": a, "target_document_id": b,
                           "signals": sorted(set(signals))} for (a, b), signals in sorted(pairs.items())]
    return plan


def _judgments(envelope, docs, target_ids, affected_records, scope_binding):
    """현재 대상/영향 assertion의 기존 판단만 전달하며 전체 history는 출력하지 않는다."""
    hidden = _hidden_tokens(envelope, docs)
    visible_ids = {x["record"]["relation_id"] for x in affected_records}
    all_visible = {x["record"]["relation_id"] for x in _records(envelope, docs)[0]}
    existing_ids = {x["relation_id"] for x in envelope["relations"]}
    for review in envelope["relation_review"]:
        snapshots = r._review_snapshots(review, strict="assertion_decisions" in review)
        for field in ("decisions", "assertion_decisions"):
            for decision in review.get(field, []):
                ids = set(decision.get("context_document_ids", [])) | {
                    decision.get("source_document_id"), decision.get("target_document_id")}
                ids.discard(None)
                relations = set(decision.get("relation_ids", []))
                if "relation_id" in decision:
                    relations.add(decision["relation_id"])
                pair = {decision.get("source_document_id"), decision.get("target_document_id")}
                hidden_pair = any({relation["source_document_id"], relation["target_document_id"]} == pair
                                  and relation["relation_id"] not in all_visible for relation in envelope["relations"])
                if (not _decision_allowed(decision, docs, all_visible, existing_ids, hidden)
                        or (not relations and hidden_pair)
                        or not (ids & target_ids or relations & visible_ids)
                        ):
                    continue
                selected_snapshots = [copy.deepcopy(snapshots[i]) for i in sorted(ids)
                                      if i in snapshots and snapshots[i]["path"] == docs[i].path]
                current = all(s["source_sha256"] == docs[s["document_id"]].sha256 for s in selected_snapshots)
                yield {"type": "existing_judgment", "review_ref": "review_" + sha256(_json([
                           scope_binding, review["review_id"]])),
                       "decision_field": field, "record": copy.deepcopy(decision),
                       "documents": selected_snapshots,
                       "currentness": "current" if current and len(selected_snapshots) == len(ids) else "unknown"}


def _traverse(records, version, graph, operation, selector, depth):
    selector = {} if selector is None else selector
    if not isinstance(selector, dict) or not set(selector).issubset({"source", "target", "relation_ids"}):
        raise FileError("query_selector_invalid")
    if any(not isinstance(selector[k], str) for k in ("source", "target") if k in selector):
        raise FileError("query_selector_invalid")
    source, target = selector.get("source"), selector.get("target")
    if operation == "records":
        relation_ids = selector.get("relation_ids")
        if relation_ids is not None and (not isinstance(relation_ids, list) or any(not isinstance(i, str) for i in relation_ids)):
            raise FileError("query_selector_invalid")
        return [x for x in records if (source is None or source in _endpoints(x, version))
                and (target is None or target in _endpoints(x, version))
                and (relation_ids is None or x["record"].get("relation_id") in relation_ids)], None
    if operation not in {"neighbors", "shortest_path", "traverse"} or source is None:
        raise FileError("query_operation_invalid")
    if operation == "shortest_path" and target is None:
        raise FileError("query_selector_invalid")
    adjacency = {}
    for index, item in enumerate(records):
        a, b = _endpoints(item, version)
        adjacency.setdefault(a, []).append((b, index))
        symmetric = item["record"]["kind"] in r.SYMMETRIC if version == 2 else not graph.get("directed", False)
        if symmetric:
            adjacency.setdefault(b, []).append((a, index))
    queue, visited, selected = deque([(source, 0, [])]), {source}, []
    depth_limited = False
    exploration = {"operation": operation, "max_depth": 1 if operation == "neighbors" else depth,
                   "depth_limited": False, "scope": "permitted_subgraph"}
    while queue:
        node, level, path = queue.popleft()
        if operation == "shortest_path" and node == target:
            return [records[i] for i in path], dict(exploration, outcome="path_found")
        if level >= (1 if operation == "neighbors" else depth):
            if operation != "neighbors" and any(neighbor not in visited for neighbor, _ in adjacency.get(node, [])):
                depth_limited = True
            continue
        for neighbor, index in sorted(adjacency.get(node, [])):
            if index not in selected:
                selected.append(index)
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, level + 1, path + [index]))
    exploration.update(depth_limited=depth_limited,
                       outcome="depth_limit" if depth_limited else "exhausted_requested_scope")
    return ([] if operation == "shortest_path" else [records[i] for i in selected]), exploration


@_safe
def relations(context, *, operation="records", selector=None, view="raw", limits=None,
              cursor=None, seen_refs=None):
    """v1/v2의 허용 원 기록 조회. 표시 투영은 별도 project_graph 호출이다."""
    limits = _limits(limits)
    if view != "raw":
        raise FileError("query_view_invalid")
    active = _load(context)
    graph, digest = _graph(context)
    if graph is None:
        if cursor is not None:
            raise ConflictError("query_cursor_changed")
        return _packet("absent", graph_status="missing")
    records, version = _records(graph, {d.document_id: d for d in active.documents})
    selected, exploration = _traverse(records, version, graph, operation, selector, limits.max_depth)
    g._verify_current(active)
    if context.graph_scope.read(context.graph_path).sha256 != digest:
        raise ConflictError("query_graph_changed")
    fingerprint = _identity(context, active.active_sha256,
                            [(d.path, d.sha256) for d in active.documents],
                            ["relations", operation, selector, view, limits.max_depth], digest)
    selected = [_record_item(context, item, digest, active, seen_refs) for item in selected]
    extra = {"graph_status": "available", "graph_sha256": digest,
             "format": version, "view": "raw", "semantic_completeness": "not_assessed"}
    if version == 1 and "directed" in graph:
        extra["directed"] = graph["directed"]
    if exploration is not None:
        extra["exploration"] = exploration
    result = _page(selected, fingerprint=fingerprint, cursor=cursor, limits=limits, extra=extra)
    if exploration is not None and "exploration" in result and exploration["depth_limited"]:
        result.update(status="partial", truncated=True,
                      omissions=sorted(set((*result["omissions"], "exploration_depth_limit"))))
    elif (exploration is not None and exploration.get("outcome") == "path_found"
          and result["status"] == "absent"):
        result["status"] = "ok"
    return result if len(_json(result)) <= limits.max_bytes else _packet("limit", error_code="query_metadata_exceeds_limit")


@_safe
def prepare_review_context(context, *, stage, target_paths=(), comparison_paths=(),
                           source_scope=None, source_paths=(), mode="incremental",
                           limits=None, cursor=None, seen_refs=None):
    """명시 source 준비 또는 실제 등록 후 관계 검토 입력을 분할한다. 쓰기 없음."""
    limits = _limits(limits)
    if stage not in {"pre_registration", "post_registration"} or mode not in {"full", "incremental"}:
        raise FileError("query_review_invalid")
    if any(isinstance(x, (str, bytes)) or not isinstance(x, (list, tuple))
           for x in (target_paths, comparison_paths, source_paths)):
        raise FileError("query_review_invalid")
    graph_hash, graph = None, None
    items, hashes = [], []
    if stage == "pre_registration":
        if not isinstance(source_scope, FileScope) or not source_paths or target_paths or comparison_paths:
            raise FileError("query_review_invalid")
        if len(set(source_paths)) != len(source_paths):
            raise FileError("query_review_invalid")
        # 아직 ACTIVE 문서가 아니다. Markdown 본문과 metadata를 가정하지 않는다.
        for path in sorted(source_paths):
            g._relative(path)
            snapshot = source_scope.read(path)
            snapshot.data.decode("utf-8")
            hashes.append((path, snapshot.sha256))
            items.extend(_source_spans(context, source_scope, path, snapshot, limits, seen_refs))
        for path, digest in hashes:
            if source_scope.read(path).sha256 != digest:
                raise ConflictError("query_source_changed")
        fingerprint = sha256(_json(["pre_registration", source_scope.root_parts,
                                   sorted(source_scope.allowed), hashes, mode, limits.max_excerpt_bytes]))
        extra = {"stage": stage, "mode": mode, "scope": "explicit_sources",
                 "semantic_completeness": "not_assessed", "registration_performed": False,
                 "candidate_discovery": "not_run", "packet_complete_is_review_complete": False}
    else:
        if source_scope is not None or source_paths or not target_paths:
            raise FileError("query_review_invalid")
        if (len(set(target_paths)) != len(target_paths)
                or len(set(comparison_paths)) != len(comparison_paths)
                or not set((*target_paths, *comparison_paths)).issubset(context.selected_paths)):
            raise FileError("query_scope_invalid")
        # 실제 같은 root/ACTIVE/hash로 읽은 객체만 기존 discover_candidates에 전달한다.
        _selection(context)
        active = g.read_active_documents(context.note_scope, context.active_path,
                                         sorted(set((*target_paths, *comparison_paths))))
        targets = g.read_active_documents(context.note_scope, context.active_path, sorted(target_paths))
        comparisons = g.read_active_documents(context.note_scope, context.active_path, sorted(comparison_paths))
        graph, graph_hash = _graph(context)
        envelope = graph if graph is not None and "batang_graph_format" in graph else None
        docs = {d.document_id: d for d in active.documents}
        target_ids = {d.document_id for d in targets.documents}
        records, version = ([], None) if graph is None else _records(graph, docs)
        # 기존 history/기존 판단 처리는 이 명시된 관계 검토 준비에서만 수행한다.
        plan = _review_plan(targets, comparisons, envelope, docs, records)
        affected = [x for x in records if (r._dependencies(x["record"]) & target_ids
                    if version == 2 else any(n.get("document_id") in target_ids for n in x["nodes"]))]
        affected_ids = set(target_ids)
        for item in affected:
            if version == 2:
                affected_ids.update(r._dependencies(item["record"]))
        # full는 모든 명시 비교 원문, incremental은 변경·endpoint·제3 support 우선.
        content_ids = set(docs) if mode == "full" else affected_ids
        for doc in active.documents:
            hashes.append((doc.path, doc.sha256))
            if doc.document_id in content_ids:
                for item in _spans(context, doc, 0, len(doc.body), limits, seen_refs):
                    items.append(dict(item, type="document_content"))
        items.extend(dict(item, type="existing_record") for item in affected)
        # 현재 대상에 관련된 최소 결정만 반환하며 raw history 전체를 보내지 않는다.
        if envelope is not None:
            review_scope = _identity(context, active.active_sha256, [], None, graph_hash)
            items.extend(_judgments(envelope, docs, target_ids, affected, review_scope))
        items.extend({"type": "additional_candidate", **candidate} for candidate in plan["candidates"])
        g._verify_current(active)
        if graph_hash is not None and context.graph_scope.read(context.graph_path).sha256 != graph_hash:
            raise ConflictError("query_graph_changed")
        fingerprint = _identity(context, active.active_sha256, hashes,
                                ["prepare_review_context", stage, sorted(target_paths),
                                 sorted(comparison_paths), mode], graph_hash)
        items = [_record_item(context, item, graph_hash, active, seen_refs)
                 if item["type"] in {"existing_record", "existing_judgment", "additional_candidate"}
                 else item for item in items]
        extra = {"stage": stage, "mode": mode, "scope": "explicit_active_selection",
                 "graph_status": "missing" if graph is None else "available",
                 "candidate_method": plan["method"], "candidate_discovery": plan["status"],
                 "candidate_omissions": plan["omissions"],
                 "semantic_completeness": "not_assessed", "registration_performed": False,
                 "packet_complete_is_review_complete": False,
                 "coverage_note": "explicit_targets_and_comparisons_only; bounded_pages; scope_limited_records; lexical_candidates_may_omit_semantic_pairs; request_more_evidence"}
    result = _page(items, fingerprint=fingerprint, cursor=cursor, limits=limits, extra=extra)
    result["review_completion"] = "not_assessed"
    if len(_json(result)) > limits.max_bytes:
        return _packet("limit", error_code="query_metadata_exceeds_limit")
    return result
