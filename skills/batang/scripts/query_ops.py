"""명시된 현재 파일의 읽기 전용 조회. CLI·모델·영속 상태를 만들지 않는다.

QueryContext는 호스트가 고정 호출 안에서 구성한다. context_id는 전달 문맥을
구별하는 정보용 식별자일 뿐 권한이나 수신 증명이 아니다.
각 함수는 JSON으로 직렬화 가능한 제한된 packet을 반환한다. currentness는
snapshot 대응이며 관계의 의미적 타당성이나 추출 완료 판정이 아니다.
"""
from dataclasses import dataclass
from collections import deque
import copy
import json
import os
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
    """명시 FileScope·선택 목록과 비영속 참조 식별. 전달 이력은 보관하지 않는다."""
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
    elif code in {"path_symlink", "path_unavailable"}:
        code = "query_path_unavailable"
    elif code == "graph_data_size":
        code = "query_graph_limit"
    elif code.startswith(("graph_", "relationship_")):
        code = "query_graph_invalid"
    elif code.startswith(("metadata_", "frontmatter_", "yaml_", "schema_")):
        code = "query_document_invalid"
    elif code not in {"query_context_invalid", "query_limits_invalid", "query_search_invalid",
                      "query_reference_invalid", "query_graph_invalid",
                      "query_selector_invalid", "query_operation_invalid", "query_view_invalid",
                      "query_review_invalid", "query_document_collision", "query_excerpt_too_small"}:
        code = "query_invalid_or_unavailable"
    return _packet("error", error_code=code)


def _safe(function):
    def call(*args, **kwargs):
        try:
            if "seen_refs" in kwargs:
                return _packet("error", error_code="unsupported_argument")
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


def _stat_signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _observation(scope, path):
    """허용 상대 경로만 no-follow로 관찰한다. 상세 identity는 출력하지 않는다."""
    try:
        with scope._parent(path) as (parent, name):
            owner = _stat_signature(os.fstat(parent))
            try:
                leaf = _stat_signature(os.stat(name, dir_fd=parent, follow_symlinks=False))
            except FileNotFoundError:
                leaf = None
            return (owner, leaf)
    except FileError as exc:
        if getattr(exc, "scope_location", None) == "internal" and getattr(exc, "path_signature", None):
            return exc.path_signature
        raise


def _document_reason(exc):
    location = getattr(exc, "scope_location", None)
    if location in {"root", "unknown"}:
        raise exc
    if isinstance(exc, ConflictError):
        return "snapshot_changed"
    if location == "internal" or getattr(exc, "code", "") in {"path_symlink", "not_regular"}:
        return "path_unavailable"
    if isinstance(exc, FileNotFoundError):
        return "document_missing"
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, OSError):
        return "io_error"
    if isinstance(exc, (UnicodeError, FileError)):
        return "document_invalid"
    raise exc


def _collect(context, paths, *, retain_body=True):
    docs, failures, observations = {}, {}, {}
    for path in paths:
        before = _observation(context.note_scope, path)
        try:
            doc = _document(context.note_scope, path)
        except (FileError, OSError, UnicodeError) as exc:
            reason = _document_reason(exc)
        else:
            reason = None
        after = _observation(context.note_scope, path)
        observations[path] = after
        if before != after:
            failures[path] = "snapshot_changed"
        elif reason is not None:
            failures[path] = reason
        else:
            docs[path] = (doc if retain_body else
                          g.Document(doc.scope, doc.path, doc.sha256, doc.metadata, b""))
    groups = {}
    for path, doc in docs.items():
        groups.setdefault(doc.document_id, []).append(path)
    for paths in groups.values():
        if len(paths) > 1:
            for path in paths:
                failures[path] = "document_collision"
                del docs[path]
    return docs, failures, observations


def _verify(context, active_hash, docs, failures, observations):
    if context.note_scope.read(context.active_path).sha256 != active_hash:
        raise ConflictError("query_active_changed")
    for path, expected in observations.items():
        if _observation(context.note_scope, path) != expected:
            raise ConflictError("query_source_changed")
        if path in docs:
            try:
                current = context.note_scope.read(path).sha256
            except (FileError, OSError, UnicodeError):
                raise ConflictError("query_source_changed") from None
            if current != docs[path].sha256:
                raise ConflictError("query_source_changed")


def _identity(context, active_hash, hashes, query, graph_hash=None, failures=None, observations=None):
    value = [context.note_scope.root_parts, sorted(context.note_scope.allowed),
             context.active_path, active_hash, sorted(context.selected_paths), hashes,
             query, graph_hash, sorted((failures or {}).items()),
             sorted((observations or {}).items())]
    if context.graph_scope is not None:
        value.extend([context.graph_scope.root_parts, sorted(context.graph_scope.allowed),
                      context.graph_path])
    return sha256(_json(value))


def _omissions(*groups):
    values = {}
    for group in groups:
        for item in group:
            key = ((0, item) if isinstance(item, str)
                   else (1, item["path"], item["reason"]))
            values[key] = item
    return [values[key] for key in sorted(values)]


def _failure_omissions(failures):
    return _omissions(["document_failure"] if failures else [],
                      [{"path": path, "reason": reason} for path, reason in failures.items()])


def _offset(cursor, fingerprint):
    if cursor is None:
        return 0
    if (not isinstance(cursor, dict) or set(cursor) != {"fingerprint", "offset"}
            or cursor["fingerprint"] != fingerprint
            or type(cursor["offset"]) is not int or cursor["offset"] < 0):
        raise ConflictError("query_cursor_changed")
    return cursor["offset"]


def _page(items, *, fingerprint, cursor, limits, extra=None, failures=None, omissions=()):
    """offset은 정상 결과 스트림 위치이며 전체 실패 목록을 매 페이지 반복한다."""
    start = _offset(cursor, fingerprint)
    base = _omissions(_failure_omissions(failures or {}), omissions)
    result = _packet(**(extra or {}))
    result["omissions"] = base
    # cursor는 실제 페이지가 잘릴 때만 필수다. 빈 최종 페이지에는 더하지 않는다.
    if len(_json(result)) > limits.max_bytes:
        return _packet("limit", error_code="query_metadata_exceeds_limit")
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
                          omissions=_omissions(base, [item["_limit"]]),
                          required_excerpt_bytes=item["required_excerpt_bytes"])
            return result if len(_json(result)) <= limits.max_bytes else _packet("limit", error_code="query_metadata_exceeds_limit")
        proposed = copy.deepcopy(result)
        proposed["items"].append(item)
        following = consumed + 1
        proposed.update(status="partial", truncated=True,
                        next_cursor={"fingerprint": fingerprint, "offset": following},
                        omissions=_omissions(base, ["response_limit"]))
        if len(_json(proposed)) > limits.max_bytes:
            break
        result = proposed
        consumed = following
    else:
        if start > total:
            raise ConflictError("query_cursor_changed")
        result.update(status="partial" if base else "ok" if result["items"] else "absent",
                      truncated=False, next_cursor=None, omissions=base)
        return result if len(_json(result)) <= limits.max_bytes else _packet("limit", error_code="query_metadata_exceeds_limit")
    if consumed < total:
        result.update(status="partial" if result["items"] else "limit", truncated=True,
                      next_cursor={"fingerprint": fingerprint, "offset": consumed},
                      omissions=_omissions(base, ["response_limit" if result["items"] else "item_exceeds_byte_limit"]))
    return result if len(_json(result)) <= limits.max_bytes else _packet("limit", error_code="query_metadata_exceeds_limit")


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


def _spans(context, doc, start, end, limits):
    # 저장 evidence_span과 같은 완전 줄만 참조한다. 긴 줄을 임의 절단하지 않는다.
    for a, b in _line_offsets(doc.body):
        if a < start or b > end:
            continue
        if b - a > limits.max_excerpt_bytes:
            yield {"_limit": "line_exceeds_excerpt_limit", "required_excerpt_bytes": b - a}
            continue
        ref = _ref(context, doc, a, b)
        yield {"ref": ref, "spans": [{"ref": ref, "text": doc.body[a:b].decode("utf-8")}]}


@_safe
def search(context, query, *, fields=("title", "id", "tags", "aliases", "body"),
           limits=None, cursor=None):
    """선택 문서를 순차로 읽는 결정적 부분문자열 검색. 의미 검색은 아니다."""
    limits = _limits(limits)
    if (not isinstance(query, str) or not query.strip() or not isinstance(fields, (list, tuple))
            or not fields or len(set(fields)) != len(fields)
            or not set(fields).issubset({"title", "id", "tags", "aliases", "body"})):
        raise FileError("query_search_invalid")
    active, paths = _selection(context)
    docs, failures, observations = _collect(context, paths, retain_body=False)
    hashes = [(path, doc.sha256) for path, doc in docs.items()]
    needle = query.casefold()
    def matches():
        # 본문을 모든 후보 packet으로 누적하지 않는다. 한 문서와 반환 페이지만 보유한다.
        for path, observed in docs.items():
            # 선검사 후 본문은 한 문서씩 읽고 변경은 전체 stale로 승격한다.
            try:
                doc = _document(context.note_scope, path)
            except (FileError, OSError, UnicodeError):
                raise ConflictError("query_source_changed") from None
            if doc.sha256 != observed.sha256:
                raise ConflictError("query_source_changed")
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
                for item in _spans(context, doc, a, b, limits):
                    yield dict(item, path=path, document_id=doc.document_id,
                               matched_fields=matched + ["body"])
            if matched and not body_match:
                if offsets:
                    for item in _spans(context, doc, *offsets[0], limits):
                        yield dict(item, path=path, document_id=doc.document_id, matched_fields=matched)
                else:
                    yield {"path": path, "document_id": doc.document_id,
                           "source_sha256": doc.sha256, "matched_fields": matched, "spans": []}
    fingerprint = _identity(context, active.sha256, hashes,
                            ["search", query, list(fields)],
                            failures=failures, observations=observations)
    result = _page(matches(), fingerprint=fingerprint, cursor=cursor, limits=limits,
                   extra={"method": "literal_casefold", "semantic_completeness": "not_assessed"},
                   failures=failures)
    _verify(context, active.sha256, docs, failures, observations)
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
def read_spans(context, requests, *, limits=None, cursor=None):
    """현재 선택 문서의 hash가 있는 실제 참조만 확인해 전달한다."""
    limits = _limits(limits)
    if not isinstance(requests, (list, tuple)):
        raise FileError("query_reference_invalid")
    active, paths = _selection(context)
    if any(not isinstance(x, dict) or x.get("path") not in paths for x in requests):
        raise FileError("query_scope_invalid")
    paths = sorted({x["path"] for x in requests})
    docs, failures, observations = _collect(context, paths)
    ranges = []
    for request in requests:
        path = request["path"]
        if path not in docs:
            continue
        try:
            a, b = _request_range(docs[path], request)
            ranges.append((path, a, b))
        except ConflictError as exc:
            failures[path] = "reference_invalid" if exc.code == "query_span_changed" else "snapshot_changed"
        except (FileError, UnicodeError):
            failures[path] = "reference_invalid"
    items = [item for path, a, b in ranges if path not in failures
             for item in _spans(context, docs[path], a, b, limits)]
    hashes = [(path, doc.sha256) for path, doc in docs.items()]
    fingerprint = _identity(context, active.sha256, hashes,
                            ["read_spans", requests],
                            failures=failures, observations=observations)
    result = _page(items, fingerprint=fingerprint, cursor=cursor, limits=limits, failures=failures)
    _verify(context, active.sha256, docs, failures, observations)
    return result


def _load(context, paths=None):
    active, selected = _selection(context)
    docs, failures, observations = _collect(context, selected if paths is None else paths)
    result = g.ActiveDocuments(context.note_scope, context.active_path, active.sha256, tuple(docs.values()))
    return result, docs, failures, observations


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


def _record_item(context, item, graph_hash, active):
    payload = {k: v for k, v in item.items() if k != "type"}
    ref = {"context_id": context.context_id, "graph_sha256": graph_hash,
           "scope_sha256": _record_scope(context, active, item, graph_hash),
           "record_sha256": sha256(_json(payload))}
    return dict(item, record_ref=ref)


def _source_spans(context, scope, path, snapshot, limits):
    scope_id = sha256(_json([scope.root_parts, sorted(scope.allowed)]))
    for a, b in _chunks(snapshot.data, 0, len(snapshot.data), limits.max_excerpt_bytes):
        ref = {"context_id": context.context_id, "source_scope_sha256": scope_id,
               "source_path": path, "source_sha256": snapshot.sha256,
               "start_byte": a, "end_byte": b, "span_sha256": sha256(snapshot.data[a:b])}
        yield {"type": "source_content", "source_path": path,
               "source_sha256": snapshot.sha256,
               "spans": [{"ref": ref, "text": snapshot.data[a:b].decode("utf-8")}]}


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
              cursor=None):
    """v1/v2의 허용 원 기록 조회. 표시 투영은 별도 project_graph 호출이다."""
    limits = _limits(limits)
    if view != "raw":
        raise FileError("query_view_invalid")
    active, doc_paths, failures, observations = _load(context)
    graph, digest = _graph(context)
    if graph is None:
        if cursor is not None:
            raise ConflictError("query_cursor_changed")
        _verify(context, active.active_sha256, doc_paths, failures, observations)
        fingerprint = _identity(context, active.active_sha256,
                                [(p, d.sha256) for p, d in doc_paths.items()],
                                ["relations", operation, selector, view, limits.max_depth],
                                failures=failures, observations=observations)
        return _page([], fingerprint=fingerprint, cursor=cursor, limits=limits,
                     failures=failures, extra={"graph_status": "missing"})
    records, version = _records(graph, {d.document_id: d for d in active.documents})
    selected, exploration = _traverse(records, version, graph, operation, selector, limits.max_depth)
    _verify(context, active.active_sha256, doc_paths, failures, observations)
    if context.graph_scope.read(context.graph_path).sha256 != digest:
        raise ConflictError("query_graph_changed")
    fingerprint = _identity(context, active.active_sha256,
                            [(d.path, d.sha256) for d in active.documents],
                            ["relations", operation, selector, view, limits.max_depth], digest,
                            failures=failures, observations=observations)
    selected = [_record_item(context, item, digest, active) for item in selected]
    extra = {"graph_status": "available", "graph_sha256": digest,
             "format": version, "view": "raw", "semantic_completeness": "not_assessed"}
    if version == 1 and "directed" in graph:
        extra["directed"] = graph["directed"]
    if exploration is not None:
        extra["exploration"] = exploration
    result = _page(selected, fingerprint=fingerprint, cursor=cursor, limits=limits, extra=extra, failures=failures,
                   omissions=["exploration_depth_limit"] if exploration and exploration["depth_limited"] else [])
    if exploration is not None and "exploration" in result and exploration["depth_limited"] and result["status"] != "limit":
        result.update(status="partial", truncated=True,
                      omissions=_omissions(result["omissions"], ["exploration_depth_limit"]))
    elif (exploration is not None and exploration.get("outcome") == "path_found"
          and result["status"] == "absent"):
        result["status"] = "ok"
    return result if len(_json(result)) <= limits.max_bytes else _packet("limit", error_code="query_metadata_exceeds_limit")


@_safe
def prepare_review_context(context, *, stage, target_paths=(), comparison_paths=(),
                           source_scope=None, source_paths=(), mode="incremental",
                           limits=None, cursor=None):
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
            items.extend(_source_spans(context, source_scope, path, snapshot, limits))
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
        # 정상 부분집합은 원문 전달에만 사용하고 불완전한 후보 판단을 합성하지 않는다.
        active, doc_paths, failures, observations = _load(
            context, sorted(set((*target_paths, *comparison_paths))))
        targets = g.ActiveDocuments(context.note_scope, context.active_path, active.active_sha256,
                                    tuple(d for d in active.documents if d.path in target_paths))
        comparisons = g.ActiveDocuments(context.note_scope, context.active_path, active.active_sha256,
                                        tuple(d for d in active.documents if d.path in comparison_paths))
        graph, graph_hash = _graph(context)
        envelope = graph if graph is not None and "batang_graph_format" in graph else None
        docs = {d.document_id: d for d in active.documents}
        target_ids = {d.document_id for d in targets.documents}
        records, version = ([], None) if graph is None else _records(graph, docs)
        # 기존 history/기존 판단 처리는 이 명시된 관계 검토 준비에서만 수행한다.
        plan = ({"method": "not_assessed", "status": "not_run", "omissions": ["document_failure"], "candidates": []}
                if failures else _review_plan(targets, comparisons, envelope, docs, records))
        affected = [x for x in records if (r._dependencies(x["record"]) & target_ids
                    if version == 2 else any(n.get("document_id") in target_ids for n in x["nodes"]))]
        affected_ids = set(target_ids)
        for item in affected:
            if version == 2:
                affected_ids.update(r._dependencies(item["record"]))
        # full는 모든 명시 비교 원문, incremental은 변경·endpoint·제3 support 우선.
        content_ids = set(docs) if mode == "full" or failures else affected_ids
        for doc in active.documents:
            hashes.append((doc.path, doc.sha256))
            if doc.document_id in content_ids:
                for item in _spans(context, doc, 0, len(doc.body), limits):
                    items.append(dict(item, type="document_content"))
        items.extend(dict(item, type="existing_record") for item in affected)
        # 현재 대상에 관련된 최소 결정만 반환하며 raw history 전체를 보내지 않는다.
        if envelope is not None:
            review_scope = _identity(context, active.active_sha256, [], None, graph_hash)
            items.extend(_judgments(envelope, docs, target_ids, affected, review_scope))
        items.extend({"type": "additional_candidate", **candidate} for candidate in plan["candidates"])
        _verify(context, active.active_sha256, doc_paths, failures, observations)
        if graph_hash is not None and context.graph_scope.read(context.graph_path).sha256 != graph_hash:
            raise ConflictError("query_graph_changed")
        fingerprint = _identity(context, active.active_sha256, hashes,
                                ["prepare_review_context", stage, sorted(target_paths),
                                 sorted(comparison_paths), mode], graph_hash,
                                failures=failures, observations=observations)
        items = [_record_item(context, item, graph_hash, active)
                 if item["type"] in {"existing_record", "existing_judgment", "additional_candidate"}
                 else item for item in items]
        extra = {"stage": stage, "mode": mode, "scope": "explicit_active_selection",
                 "graph_status": "missing" if graph is None else "available",
                 "candidate_method": plan["method"], "candidate_discovery": plan["status"],
                 "candidate_omissions": plan["omissions"],
                 "semantic_completeness": "not_assessed", "registration_performed": False,
                 "packet_complete_is_review_complete": False,
                 "coverage_note": "explicit_targets_and_comparisons_only; bounded_pages; scope_limited_records; lexical_candidates_may_omit_semantic_pairs; request_more_evidence"}
    result = _page(items, fingerprint=fingerprint, cursor=cursor, limits=limits, extra=extra,
                   failures=failures if stage == "post_registration" else None)
    result["review_completion"] = "not_assessed"
    if len(_json(result)) > limits.max_bytes:
        return _packet("limit", error_code="query_metadata_exceeds_limit")
    return result
