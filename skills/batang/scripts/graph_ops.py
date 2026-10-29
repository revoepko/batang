"""선택된 활성 문서의 그래프 반영을 돕는 내부 함수. 제공자·CLI·감시는 없다.

호스트가 권한과 추출의 의미적 완전성을 판단한다. 이 모듈은 명시된 chunk
목록, 현재 파일, 그래프 대응과 저장을 검사한다. 쓰기는 FileScope를 거친다.
동일 scripts 경로에서 ``import graph_ops``로 사용한다.
"""
from dataclasses import dataclass
import copy
import hashlib
import json
import re
from urllib.parse import unquote, urlsplit

from file_ops import FileError, ConflictError, parse_document, sha256, verify_import_source


MAX_GRAPH_BYTES = 32 * 1024 * 1024
_CONFIDENCE = {"EXTRACTED", "INFERRED"}


class GraphError(FileError):
    """내용이나 절대 경로를 포함하지 않는 그래프 처리 오류."""


@dataclass(frozen=True)
class Document:
    scope: object
    path: str
    sha256: str
    metadata: dict
    body: bytes

    @property
    def document_id(self):
        return self.metadata["batang_id"]


@dataclass(frozen=True)
class ActiveDocuments:
    scope: object
    active_path: str
    active_sha256: str
    documents: tuple


@dataclass(frozen=True)
class GraphUpdateResult:
    status: str
    coverage: tuple
    error_code: str | None = None
    graph_sha256: str | None = None
    note_query_allowed: bool = True
    graph_written: bool | None = False
    publication_uncertain: bool = False


@dataclass(frozen=True)
class RegistrationResult:
    notes_status: str
    graph_status: str
    active_documents: ActiveDocuments
    graph: GraphUpdateResult


def _relative(path):
    if (not isinstance(path, str) or not path or path.startswith("/")
            or "\\" in path or "\x00" in path
            or any(part in ("", ".", "..") for part in path.split("/"))):
        raise GraphError("graph_path_invalid")
    return path


def _active_paths(data):
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        raise GraphError("active_encoding") from None
    paths = []
    for line in text.split("\n"):
        match = re.fullmatch(r"- \[[^\]\n]*\]\(([^)\n]+)\)\r?", line)
        if not match:
            continue
        value = match.group(1)
        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
            raise GraphError("active_path_invalid")
        path = _relative(unquote(value, errors="strict"))
        if path in paths:
            raise GraphError("active_duplicate_path")
        paths.append(path)
    return tuple(paths)


def read_active_documents(note_scope, active_path, selected_paths=None):
    """활성 목록과 허용된 개별 파일만 읽는다. 목록은 권한을 부여하지 않는다."""
    active = note_scope.read(active_path)
    listed = _active_paths(active.data)
    selected = listed if selected_paths is None else tuple(selected_paths)
    if len(set(selected)) != len(selected) or not set(selected).issubset(listed):
        raise GraphError("active_selection_invalid")
    documents = []
    ids = set()
    for path in selected:
        snapshot = note_scope.read(_relative(path))
        metadata, body = parse_document(snapshot.data)
        if metadata["batang_id"] in ids:
            raise GraphError("active_document_id_collision")
        ids.add(metadata["batang_id"])
        documents.append(Document(note_scope, path, snapshot.sha256,
                                  copy.deepcopy(metadata), body))
    if note_scope.read(active_path).sha256 != active.sha256:
        raise ConflictError("active_changed_during_read")
    return ActiveDocuments(note_scope, active_path, active.sha256, tuple(documents))


def _verify_current(active):
    if active.scope.read(active.active_path).sha256 != active.active_sha256:
        raise ConflictError("active_changed")
    for document in active.documents:
        saved = document.scope.read(document.path)
        if saved.sha256 != document.sha256:
            raise ConflictError("graph_source_changed")
        metadata, body = parse_document(saved.data)
        if metadata != document.metadata or body != document.body:
            raise ConflictError("graph_source_changed")


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise GraphError("graph_duplicate_key")
        value[key] = item
    return value


def _json(data):
    try:
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not isinstance(data, bytes) or len(data) > MAX_GRAPH_BYTES:
            raise GraphError("graph_data_size")
        return json.loads(data, object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(GraphError("graph_nonfinite")))
    except (UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, GraphError):
            raise
        raise GraphError("graph_json_invalid") from None


def _graph_data(data):
    value = _json(data) if isinstance(data, (bytes, str)) else copy.deepcopy(data)
    if not isinstance(value, dict):
        raise GraphError("graph_shape_invalid")
    if "links" in value and "edges" in value:
        raise GraphError("graph_edge_keys")
    links = value.get("links", value.get("edges"))
    nodes = value.get("nodes")
    if (not isinstance(nodes, list) or not isinstance(links, list)
            or value.get("multigraph", False) is not False
            or type(value.get("directed", False)) is not bool):
        raise GraphError("graph_shape_invalid")
    ids = set()
    for node in nodes:
        if (not isinstance(node, dict) or not isinstance(node.get("id"), str)
                or not node["id"] or node["id"] in ids):
            raise GraphError("graph_node_invalid")
        ids.add(node["id"])
    edges = set()
    directed = value.get("directed", False)
    for edge in links:
        if (not isinstance(edge, dict) or not isinstance(edge.get("source"), str)
                or not isinstance(edge.get("target"), str) or edge.get("source") not in ids
                or edge.get("target") not in ids):
            raise GraphError("graph_endpoint_invalid")
        key = (edge["source"], edge["target"])
        if not directed:
            key = tuple(sorted(key))
        if key in edges:
            raise GraphError("graph_duplicate_edge")
        edges.add(key)
    value.pop("edges", None)
    value["links"] = links
    value.setdefault("directed", False)
    value.setdefault("multigraph", False)
    value.setdefault("graph", {})
    if not isinstance(value["graph"], dict):
        raise GraphError("graph_attributes_invalid")
    return value


def graph_coverage(documents, graph_bytes=None):
    """문서 노드의 ID·해시·tags·aliases 대응. 의미 추출 완전성 검사는 아니다."""
    documents = documents.documents if isinstance(documents, ActiveDocuments) else tuple(documents)
    try:
        graph = None if graph_bytes is None else _graph_data(graph_bytes)
    except GraphError:
        return tuple({"path": doc.path, "document_id": doc.document_id, "status": "invalid"}
                     for doc in documents)
    results = []
    for doc in documents:
        nodes = [] if graph is None else [node for node in graph["nodes"]
                  if node.get("node_role") == "document" and node.get("document_id") == doc.document_id]
        if not nodes:
            status = "missing"
        elif len(nodes) != 1 or nodes[0].get("source_file") != doc.path:
            status = "invalid"
        elif (nodes[0].get("source_sha256") != doc.sha256
              or nodes[0].get("tags") != doc.metadata["tags"]
              or nodes[0].get("aliases") != doc.metadata.get("aliases")):
            status = "stale"
        else:
            status = "current"
        results.append({"path": doc.path, "document_id": doc.document_id,
                        "status": status, "graph_node_id": nodes[0]["id"] if len(nodes) == 1 else None})
    return tuple(results)


def _current_coverage(active, graph_bytes):
    try:
        current = read_active_documents(active.scope, active.active_path,
                                        [doc.path for doc in active.documents])
        old_ids = {doc.path: doc.document_id for doc in active.documents}
        result = list(graph_coverage(current, graph_bytes))
        for item in result:
            if item["document_id"] != old_ids[item["path"]]:
                item["status"] = "invalid"
        return tuple(result)
    except Exception:
        return tuple({"path": doc.path, "document_id": doc.document_id, "status": "invalid"}
                     for doc in active.documents)


def document_node_id(document_id):
    if not isinstance(document_id, str) or not document_id:
        raise GraphError("document_id_invalid")
    return "batang_doc_" + hashlib.sha256(document_id.encode("utf-8")).hexdigest()


def document_nodes(documents, graph_bytes=None):
    """관계 없는 노트도 포함한다. 유효한 기존 문서 node ID는 유지한다."""
    documents = documents.documents if isinstance(documents, ActiveDocuments) else tuple(documents)
    existing = None if graph_bytes is None else _graph_data(graph_bytes)
    result = []
    for doc in documents:
        matches = [] if existing is None else [node for node in existing["nodes"]
                  if node.get("node_role") == "document" and node.get("document_id") == doc.document_id]
        if len(matches) > 1:
            raise GraphError("graph_document_id_collision")
        node = {"id": matches[0]["id"] if matches else document_node_id(doc.document_id),
                "label": doc.metadata["subject"], "file_type": "document", "node_role": "document",
                "source_file": doc.path, "source_location": "document",
                "document_id": doc.document_id, "source_sha256": doc.sha256,
                "tags": copy.deepcopy(doc.metadata["tags"]), "_origin": "semantic"}
        if "aliases" in doc.metadata:
            node["aliases"] = copy.deepcopy(doc.metadata["aliases"])
        result.append(node)
    return result


def _chunks(active, chunks, expected_chunk_ids, old_graph):
    if isinstance(chunks, (bytes, str)):
        chunks = _json(chunks)
    try:
        chunks = json.loads(json.dumps(chunks, allow_nan=False))
    except (TypeError, ValueError):
        raise GraphError("extraction_json_invalid") from None
    if not isinstance(chunks, list) or not isinstance(expected_chunk_ids, dict):
        raise GraphError("extraction_manifest_invalid")
    docs = {doc.path: doc for doc in active.documents}
    if set(expected_chunk_ids) != set(docs):
        raise GraphError("extraction_manifest_scope")
    expected = {}
    for path, identifiers in expected_chunk_ids.items():
        if (not isinstance(identifiers, (list, tuple)) or not identifiers
                or any(not isinstance(key, str) or not key for key in identifiers)):
            raise GraphError("extraction_manifest_invalid")
        for key in identifiers:
            if key in expected:
                raise GraphError("extraction_chunk_duplicate")
            expected[key] = path
    seen = set()
    all_nodes = {node["id"]: node for node in document_nodes(active, old_graph)}
    all_edges = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            raise GraphError("extraction_chunk_invalid")
        identifier = chunk.get("chunk_id")
        if not isinstance(identifier, str) or identifier not in expected or identifier in seen:
            raise GraphError("extraction_chunk_invalid")
        seen.add(identifier)
        path = expected[identifier]
        doc = docs[path]
        if (chunk.get("source_file") != path or chunk.get("document_id") != doc.document_id
                or chunk.get("source_sha256") != doc.sha256):
            raise GraphError("extraction_source_stale")
        if (not isinstance(chunk.get("nodes"), list) or not isinstance(chunk.get("edges"), list)
                or chunk.get("hyperedges")):
            raise GraphError("extraction_chunk_invalid")
        for node in chunk["nodes"]:
            _provenance(node, doc)
            if (not isinstance(node.get("id"), str) or not node["id"]
                    or not isinstance(node.get("label"), str) or not node["label"]
                    or node.get("node_role") == "document"
                    or node["id"] in all_nodes):
                raise GraphError("extraction_node_invalid")
            all_nodes[node["id"]] = node
        for edge in chunk["edges"]:
            _provenance(edge, doc)
            if not isinstance(edge.get("relation"), str) or not edge["relation"]:
                raise GraphError("extraction_edge_invalid")
            all_edges.append(edge)
    if seen != set(expected):
        raise GraphError("extraction_incomplete")
    edges_seen = set()
    for edge in all_edges:
        if (not isinstance(edge.get("source"), str) or not isinstance(edge.get("target"), str)
                or edge.get("source") not in all_nodes or edge.get("target") not in all_nodes):
            raise GraphError("extraction_endpoint_invalid")
        key = (edge["source"], edge["target"])
        if not old_graph["directed"]:
            key = tuple(sorted(key))
        if key in edges_seen:
            raise GraphError("extraction_duplicate_edge")
        edges_seen.add(key)
    # 문서 노드는 호스트 추출 내용과 별도로 모든 대상에서 한 번만 생성한다.
    return [{"nodes": list(all_nodes.values()), "edges": all_edges}]


def _provenance(item, doc):
    if (not isinstance(item, dict) or item.get("source_file") != doc.path
            or item.get("document_id") != doc.document_id
            or item.get("source_sha256") != doc.sha256
            or item.get("_origin") != "semantic"
            or not isinstance(item.get("source_location"), str) or not item["source_location"]
            or item.get("confidence") not in _CONFIDENCE):
        raise GraphError("extraction_provenance_invalid")


def _optional_read(scope, path):
    try:
        return scope.read(path)
    except FileNotFoundError:
        return None


def _preserved(old, candidate, paths):
    nodes = {node["id"]: node for node in candidate["nodes"]}
    for node in old["nodes"]:
        if _retained(node, paths):
            actual = nodes.get(node["id"])
            if actual is None or any(actual.get(key) != value for key, value in node.items()):
                raise GraphError("graph_unrelated_node_changed")
    directed = old["directed"]
    def edge_key(edge):
        ends = (edge["source"], edge["target"])
        return ends if directed else tuple(sorted(ends))
    links = {edge_key(edge): edge for edge in candidate["links"]}
    for edge in old["links"]:
        if _retained(edge, paths):
            actual = links.get(edge_key(edge))
            # 무방향 graph의 JSON endpoint 순서는 의미가 없다. 방향 속성은 보존한다.
            if actual is None or any(actual.get(key) != value for key, value in edge.items()
                                     if directed or key not in ("source", "target")):
                raise GraphError("graph_unrelated_edge_changed")
    old_hyperedges = old.get("graph", {}).get("hyperedges", [])
    new_hyperedges = candidate.get("graph", {}).get("hyperedges", [])
    for edge in old_hyperedges:
        if edge.get("source_file") not in paths and edge not in new_hyperedges:
            raise GraphError("graph_unrelated_hyperedge_changed")


def _ast_tier(item):
    """명시 origin을 우선한다. 기존 Graphify 0.9.92의 위치형식도 수용한다."""
    if item.get("_origin") is not None:
        return item["_origin"] == "ast"
    location = item.get("source_location")
    return isinstance(location, str) and bool(re.match(r"^L\d", location))


def _retained(item, paths):
    return item.get("source_file") not in paths or _ast_tier(item)


def _build_from_snapshot(old, prepared, paths, root=None):
    """검증된 JSON을 메모리에서 갱신한다. 경로 속성은 읽기 대상이 아니다.

    root는 이전 내부 호출과의 호환을 위해 받지만 경로 해석에 사용하지 않는다.
    기존 절대 출처도 데이터로 보존하며 Graphify의 파일 경로 정규화를 끈다.
    """
    from graphify.build import build
    # 갱신한 semantic source만 교체하고 같은 source의 AST 층은 보존한다.
    nodes = [copy.deepcopy(item) for item in old["nodes"] if _retained(item, paths)]
    edges = [copy.deepcopy(item) for item in old["links"] if _retained(item, paths)]
    hyperedges = old.get("graph", {}).get("hyperedges", [])
    if not isinstance(hyperedges, list) or any(not isinstance(item, dict) for item in hyperedges):
        raise GraphError("graph_hyperedges_invalid")
    kept_hyperedges = [copy.deepcopy(item) for item in hyperedges
                       if isinstance(item, dict) and item.get("source_file") not in paths]
    merged = build([{"nodes": nodes, "edges": edges, "hyperedges": kept_hyperedges}, *prepared],
                   directed=old["directed"], dedup=False, root=None,
                   protected_ids={item["id"] for item in nodes})
    for key, value in old["graph"].items():
        if key != "hyperedges":
            merged.graph.setdefault(key, copy.deepcopy(value))
    return merged


def _work_paths(work_scope, baseline_path, candidate_path, graph_scope, graph_path):
    baseline = work_scope.root_parts + tuple(_relative(baseline_path).split("/"))
    candidate = work_scope.root_parts + tuple(_relative(candidate_path).split("/"))
    destination = graph_scope.root_parts + tuple(_relative(graph_path).split("/"))
    if len({baseline, candidate, destination}) != 3:
        raise GraphError("graph_work_path_collision")


def refresh_graph(active_documents, chunks, *, expected_chunk_ids, graph_scope,
                  graph_path, expected_graph_sha256, work_scope, baseline_path,
                  candidate_path, backup_scope=None, backup_path=None, read_only=False):
    """호스트가 허용한 갱신 한 번. 실패는 대기로 반환하며 자동 재시도하지 않는다.

    expected_chunk_ids는 {문서 상대경로: [예상 chunk ID,...]}다. 각 chunk는
    chunk_id/source_file/document_id/source_sha256/nodes/edges를 가진다.
    의미 노드·관계에는 같은 출처 정보와 source_location/confidence/_origin이 필요하다.
    문서 노드는 자동 생성하며 연결 endpoint는 document_nodes()의 ID를 사용한다.
    work_scope에는 아직 없는 baseline_path/candidate_path를 명시 허용한다.
    read_only는 실행 선택값이며 권한 인증을 대신하지 않는다.
    """
    old_bytes = None
    publication_started = False
    try:
        _verify_current(active_documents)
        previous = _optional_read(graph_scope, graph_path)
        old_bytes = None if previous is None else previous.data
        coverage = graph_coverage(active_documents, old_bytes)
        if read_only:
            return GraphUpdateResult("current" if all(c["status"] == "current" for c in coverage)
                                     else "pending", coverage, "read_only" if any(
                                         c["status"] != "current" for c in coverage) else None,
                                     previous.sha256 if previous else None)
        _work_paths(work_scope, baseline_path, candidate_path, graph_scope, graph_path)
        if expected_graph_sha256 != (previous.sha256 if previous else None):
            raise ConflictError("graph_expected_hash_changed")
        old = _graph_data(old_bytes) if old_bytes is not None else {
            "directed": False, "multigraph": False, "graph": {}, "nodes": [], "links": []}
        prepared = _chunks(active_documents, chunks, expected_chunk_ids, old)
        from graphify.validate import validate_extraction
        import networkx as nx
        if validate_extraction(prepared[0]):
            raise GraphError("extraction_schema_invalid")
        baseline = (json.dumps(old, ensure_ascii=False, allow_nan=False) + "\n").encode()
        work_scope.write(baseline_path, baseline)
        baseline_snapshot = work_scope.read(baseline_path)
        if baseline_snapshot.data != baseline:
            raise ConflictError("graph_baseline_changed")
        merged = _build_from_snapshot(old, prepared,
                                      {doc.path for doc in active_documents.documents})
        if work_scope.read(baseline_path).sha256 != baseline_snapshot.sha256:
            raise ConflictError("graph_baseline_changed")
        encoded = (json.dumps(nx.node_link_data(merged, edges="links"), ensure_ascii=False,
                              allow_nan=False, sort_keys=True) + "\n").encode()
        candidate = _graph_data(encoded)
        _preserved(old, candidate, {doc.path for doc in active_documents.documents})
        actual_nodes = {node["id"]: node for node in candidate["nodes"]}
        permitted_ids = {node["id"] for node in old["nodes"]} | {
            node["id"] for node in prepared[0]["nodes"]}
        if not set(actual_nodes).issubset(permitted_ids):
            raise GraphError("graph_unexpected_node")
        for node in prepared[0]["nodes"]:
            actual = actual_nodes.get(node["id"])
            if actual is None or any(actual.get(key) != value for key, value in node.items()):
                raise GraphError("graph_new_node_changed")
        def candidate_edge_key(edge):
            endpoints = (edge["source"], edge["target"])
            return endpoints if candidate["directed"] else tuple(sorted(endpoints))
        actual_edges = {candidate_edge_key(edge): edge for edge in candidate["links"]}
        for edge in prepared[0]["edges"]:
            actual = actual_edges.get(candidate_edge_key(edge))
            if actual is None or any(actual.get(key) != value for key, value in edge.items()
                                     if candidate["directed"] or key not in ("source", "target")):
                raise GraphError("graph_new_edge_changed")
        coverage = graph_coverage(active_documents, encoded)
        if any(check["status"] != "current" for check in coverage):
            raise GraphError("graph_candidate_coverage")
        # 대상 밖의 이전 node ID를 추출 결과가 덮어쓰는 것도 거부한다.
        work_scope.write(candidate_path, encoded)
        staged = work_scope.read(candidate_path)
        reloaded = nx.node_link_graph(_graph_data(staged.data), edges="links")
        if (staged.data != encoded or reloaded.number_of_nodes() != len(candidate["nodes"])
                or reloaded.number_of_edges() != len(candidate["links"])):
            raise GraphError("graph_candidate_reload")

        def before_publish():
            _verify_current(active_documents)
            if work_scope.read(candidate_path).sha256 != staged.sha256:
                raise ConflictError("graph_candidate_changed")

        before_publish()
        publication_started = True
        written = graph_scope.write(graph_path, encoded, expected_graph_sha256,
                                    backup_scope=backup_scope, backup_path=backup_path,
                                    _before_publish=before_publish)
        if not written:
            publication_started = False
        saved = graph_scope.read(graph_path)
        _verify_current(active_documents)
        if saved.data != encoded:
            raise ConflictError("graph_saved_changed")
        final_coverage = graph_coverage(active_documents, saved.data)
        if any(item["status"] != "current" for item in final_coverage):
            raise GraphError("graph_saved_coverage")
        return GraphUpdateResult("current", final_coverage, graph_sha256=saved.sha256,
                                 graph_written=bool(written))
    except Exception as exc:
        code = getattr(exc, "code", str(exc)) if isinstance(exc, (FileError, GraphError)) else (
            "graph_dependency_unavailable" if isinstance(exc, ImportError) else "graph_update_failed")
        # 다른 도구의 오류 본문·경로·원문은 결과에 복제하지 않는다.
        if not re.fullmatch(r"[a-z][a-z0-9_]*", code):
            code = "graph_update_failed"
        observed_hash = None
        if publication_started:
            try:
                observed = _optional_read(graph_scope, graph_path)
                old_bytes = observed.data if observed else None
                observed_hash = observed.sha256 if observed else None
            except Exception:
                old_bytes = None
        return GraphUpdateResult("pending", _current_coverage(active_documents, old_bytes), code,
                                 graph_sha256=observed_hash,
                                 graph_written=None if publication_started else False,
                                 publication_uncertain=publication_started)


def register_documents(note_scope, active_path, paths, *, expected_active_sha256,
                       backup_scope=None, backup_path=None, import_results=(),
                       source_scopes=(), source_roots=None):
    """검증된 파일을 목록에 추가한다. 복제하지 않으며 등록만으로 완료를 선언하지 않는다."""
    paths = tuple(paths)
    if len(set(paths)) != len(paths):
        raise GraphError("registration_duplicate_path")
    previous = _optional_read(note_scope, active_path)
    if expected_active_sha256 != (previous.sha256 if previous else None):
        raise ConflictError("active_expected_hash_changed")
    original = previous.data if previous else b""
    existing = _active_paths(original)
    names = existing + tuple(path for path in paths if path not in existing)
    documents = {}
    ids = set()
    for path in names:
        saved = note_scope.read(_relative(path))
        metadata, body = parse_document(saved.data)
        if metadata["batang_id"] in ids:
            raise GraphError("active_document_id_collision")
        ids.add(metadata["batang_id"])
        documents[path] = Document(note_scope, path, saved.sha256, metadata, body)
    scope_root = "/" + "/".join(note_scope.root_parts)
    roots = {} if source_roots is None else dict(source_roots)
    verifications = []
    for result in import_results:
        if (result.target_root != scope_root or result.target_path not in paths
                or result.target_path not in documents):
            raise GraphError("registration_import_scope")
        document = documents[result.target_path]
        if (document.sha256 != result.target_sha256
                or document.metadata["batang_id"] != result.metadata["batang_id"]):
            raise ConflictError("registration_copy_changed")
        binding = getattr(result, "source_root_binding", {})
        if binding and (not isinstance(binding, dict) or any(roots.get(key) != root
                                                           for key, root in binding.items())):
            raise GraphError("registration_source_binding_missing")
        matches = [scope for scope in source_scopes
                   if "/" + "/".join(scope.root_parts) == result.provenance["source_root"]]
        if len(matches) != 1:
            raise GraphError("registration_source_scope_missing")
        verify_import_source(matches[0], result)
        verifications.append((matches[0], result))
    addition = [path for path in paths if path not in existing]
    appended = original + (b"\n" if original and not original.endswith(b"\n") else b"")
    for path in addition:
        # 경로 표시값과 Markdown 목적지는 JSON이나 shell 명령으로 해석하지 않는다.
        from urllib.parse import quote
        appended += ("- [노트](" + quote(path, safe="/") + ")\n").encode()

    def before_register():
        for document in documents.values():
            if document.scope.read(document.path).sha256 != document.sha256:
                raise ConflictError("registration_note_changed")
        for scope, result in verifications:
            verify_import_source(scope, result)

    before_register()
    if addition or previous is None:
        note_scope.write(active_path, appended, expected_active_sha256,
                         backup_scope=backup_scope, backup_path=backup_path,
                         _before_publish=before_register)
    return read_active_documents(note_scope, active_path, paths)


def registration_lifecycle(note_scope, active_path, paths, *, registration, graph):
    """등록과 한 번의 그래프 반영 결과를 묶는다. 설치·권한을 인증하지 않는다."""
    active = register_documents(note_scope, active_path, paths, **registration)
    outcome = refresh_graph(active, **graph)
    return RegistrationResult("registered", outcome.status, active, outcome)


def resume_registration(note_scope, active_path, paths, *, read_only=False, **graph):
    """등록 노트만 다시 읽어 반영한다. 가져오기·복제·활성 목록 변경은 하지 않는다."""
    active = read_active_documents(note_scope, active_path, paths)
    outcome = refresh_graph(active, read_only=read_only, **graph)
    return RegistrationResult("registered", outcome.status, active, outcome)
