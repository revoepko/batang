"""명시 파일만 다루는 내부 stdlib 도우미. CLI 또는 외부 writer 잠금은 제공하지 않는다."""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import copy
import ctypes
import errno
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import uuid
from urllib.parse import quote, unquote, urlsplit


def _internal_module(name):
    """호출 경로에 무관하게 같은 고정본의 순수 데이터 모듈만 불러온다."""
    spec = importlib.util.spec_from_file_location(__name__ + "_" + name,
                                                Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_yaml_data = _internal_module("yaml_data")
_link_data = _internal_module("link_data")


class FileError(ValueError):
    """원문 내용이나 민감 경로를 포함하지 않는 계약 오류."""

    def __init__(self, code, *, key=None, line=None):
        self.code, self.key, self.line = code, key, line
        if code.startswith(("yaml_", "frontmatter_", "metadata_", "import_yaml")):
            message = "속성 형식을 확인해 주세요. 문제가 있는 값은 자동으로 고치지 않습니다."
        elif code in ("private_staging_unavailable", "staging_path"):
            message = "임시 위치의 소유자 전용 권한과 대상과 같은 파일시스템인지 확인해 주세요."
        elif "link" in code or code == "path_symlink":
            message = "심볼릭 링크나 참조 경로를 확인해 주세요. 안전 검사를 우회하지 않습니다."
        elif "collision" in code or "changed" in code or "identity" in code:
            message = "파일이 바뀌었거나 대상이 충돌했습니다. 현재 파일을 다시 확인해 주세요."
        else:
            message = "해당 항목의 설정과 허용 범위를 확인해 주세요."
        detail = (" [속성: " + json.dumps(key, ensure_ascii=False) + "]") if key is not None else ""
        detail += (" [줄: " + str(line) + "]") if line is not None else ""
        super().__init__(code + ": " + message + detail)


class ConflictError(FileError):
    """기대 상태와 현재 파일이 다르다."""


KEYS = ("batang_schema_version", "batang_id", "subject", "tags", "content_kind",
        "sources", "legacy_refs")
OPTIONAL_KEYS = ("aliases",)
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MISSING = object()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def validate_metadata(metadata):
    if not isinstance(metadata, dict) or not set(KEYS).issubset(metadata):
        raise FileError("metadata_keys")
    for key, value in metadata.items():
        if not isinstance(key, str) or not key or any(c in key for c in "\x00\r\n"):
            raise FileError("metadata_key")
        if key not in KEYS + OPTIONAL_KEYS:
            if key.startswith("batang_"):
                raise FileError("metadata_reserved_key", key=key)
            _validate_property(value, key)
    version = metadata["batang_schema_version"]
    if type(version) is not int or version not in (1, 2):
        raise FileError("schema_version")
    for key in ("batang_id", "subject", "content_kind"):
        if not isinstance(metadata[key], str) or not metadata[key].strip():
            raise FileError("metadata_string")
    if not isinstance(metadata["tags"], list) or any(not isinstance(t, str) for t in metadata["tags"]):
        raise FileError("metadata_tags")
    if "aliases" in metadata:
        aliases = metadata["aliases"]
        if (not isinstance(aliases, list)
                or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)):
            raise FileError("metadata_aliases")
    for key, fields in (("sources", {"id", "path", "origin", "sha256", "raw_path"}),
                        ("legacy_refs", {"path", "sha256"})):
        if not isinstance(metadata[key], list):
            raise FileError("metadata_refs")
        for item in metadata[key]:
            if not isinstance(item, dict) or set(item) != fields:
                raise FileError("metadata_ref")
            for field, value in item.items():
                if key == "sources" and version == 2 and field in ("path", "sha256", "raw_path") and value is None:
                    continue
                if not isinstance(value, str) or not value:
                    raise FileError("metadata_ref")
                if field == "sha256" and not SHA256.fullmatch(value):
                    raise FileError("metadata_ref")
                if field == "path" and value.startswith("batang-source:"):
                    _decode_source_uri(value)


def _validate_property(value, key):
    def scalar(item):
        return (item is None or type(item) in (str, bool, int)
                or (type(item) is float and math.isfinite(item)))
    if not scalar(value) and not (isinstance(value, list) and all(scalar(item) for item in value)):
        raise FileError("metadata_property_unsupported", key=key)


def new_metadata(subject, content_kind, sources, *, tags=_MISSING, legacy_refs=_MISSING,
                 aliases=_MISSING, properties=None):
    """호스트의 신규 v2 입력만 생성한다. 저장·기존 문서 변환·권한 판단은 하지 않는다."""
    metadata = {"batang_schema_version": 2, "batang_id": str(uuid.uuid4()),
                "subject": subject, "tags": [] if tags is _MISSING else copy.deepcopy(tags),
                "content_kind": content_kind, "sources": copy.deepcopy(sources),
                "legacy_refs": [] if legacy_refs is _MISSING else copy.deepcopy(legacy_refs)}
    if aliases is not _MISSING:
        metadata["aliases"] = copy.deepcopy(aliases)
    if properties is not None:
        if not isinstance(properties, dict) or set(properties).intersection(KEYS + OPTIONAL_KEYS):
            raise FileError("metadata_property_collision")
        metadata.update(copy.deepcopy(properties))
    validate_metadata(metadata)
    return metadata


def split_frontmatter(data):
    """YAML의 의미를 해석하지 않고 header bytes와 그 뒤 body bytes만 분리한다."""
    if not isinstance(data, bytes):
        raise FileError("document_bytes")
    lines = data.splitlines(keepends=True)
    if not lines or lines[0] not in (b"---\n", b"---\r\n"):
        raise FileError("frontmatter_missing")
    offset = len(lines[0])
    for line in lines[1:]:
        if line in (b"---\n", b"---\r\n", b"---"):
            return data[len(lines[0]):offset], data[offset + len(line):]
        offset += len(line)
    raise FileError("frontmatter_unclosed")


def _typed_equal(left, right):
    """숫자와 체크박스처럼 Python ==가 같게 보는 다른 데이터 타입도 구분한다."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_typed_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def serialize_document(metadata, body, *, original=None):
    validate_metadata(metadata)
    if not isinstance(body, bytes):
        raise FileError("body_bytes")
    if original is not None:
        previous_metadata, previous_body = parse_document(original)
        if _typed_equal(previous_metadata, metadata) and previous_body == body:
            return original
    keys = tuple(key for key in KEYS + OPTIONAL_KEYS if key in metadata) + tuple(
        key for key in metadata if key not in KEYS + OPTIONAL_KEYS)
    header = "---\n" + "".join(
        (key if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key)
         else json.dumps(key, ensure_ascii=False)) + ": " + json.dumps(metadata[key], ensure_ascii=False, allow_nan=False,
                                 separators=(",", ":")) + "\n"
        for key in keys) + "---\n"
    return header.encode("utf-8") + body


def parse_document(data):
    header, body = split_frontmatter(data)
    metadata = _load_metadata(header)
    validate_metadata(metadata)
    return metadata, body


def _load_metadata(header):
    try:
        return _yaml_data.load(header)
    except _yaml_data.DataError as exc:
        raise FileError(exc.code, key=exc.key, line=exc.line) from None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FileError("frontmatter_duplicate")
        result[key] = value
    return result


def verify_quote(source, start_byte, end_byte, quote):
    if (not isinstance(source, bytes) or not isinstance(quote, str) or not quote
            or type(start_byte) is not int or type(end_byte) is not int
            or not 0 <= start_byte < end_byte <= len(source)):
        raise FileError("quote_range")
    try:
        source.decode("utf-8")
        actual = source[start_byte:end_byte].decode("utf-8")
    except UnicodeError:
        raise FileError("quote_encoding") from None
    if actual != quote:
        raise FileError("quote_mismatch")
    return True


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    sha256: str
    mode: int


@dataclass(frozen=True)
class ImportResult:
    """활성 등록 요청이 아닌, 호스트가 재검사할 복제 결과와 관측 출처."""
    status: str
    target_root: str
    target_path: str
    target_sha256: str
    metadata: dict
    provenance: dict
    references: tuple
    source_identity: tuple
    source_root_binding: dict = None


def _scope_root(scope):
    return "/" + "/".join(scope.root_parts)


def _root_id(value):
    try:
        result = str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise FileError("source_root_id") from None
    if value != result:
        raise FileError("source_root_id")
    return result


def source_uri(source_root_id, relative_path):
    root_id = _root_id(source_root_id)
    parts = _parts(relative_path)
    return "batang-source://" + root_id + "/" + "/".join(quote(part, safe="-._~") for part in parts)


def _decode_source_uri(value):
    if not isinstance(value, str):
        raise FileError("source_uri")
    try:
        parsed = urlsplit(value)
    except ValueError:
        raise FileError("source_uri") from None
    if (parsed.scheme != "batang-source" or parsed.query or parsed.fragment
            or not parsed.path.startswith("/") or "@" in parsed.netloc or ":" in parsed.netloc):
        raise FileError("source_uri")
    root_id = _root_id(parsed.netloc)
    if re.search(r"%(?:2f|5c|00)", parsed.path, re.I):
        raise FileError("source_uri_path")
    try:
        relative = unquote(parsed.path[1:], errors="strict")
    except UnicodeError:
        raise FileError("source_uri_path") from None
    _parts(relative)
    if source_uri(root_id, relative) != value:
        raise FileError("source_uri_canonical")
    return root_id, relative


def resolve_source_uri(value, source_roots):
    """로컬 참조를 해석할 뿐 파일을 읽거나 네트워크에 접근하지 않는다."""
    if not isinstance(source_roots, dict):
        raise FileError("source_roots")
    root_id, relative = _decode_source_uri(value)
    if root_id not in source_roots:
        raise FileError("source_root_unmapped")
    root = source_roots[root_id]
    _parts(root, absolute=True)
    return os.fspath(root), relative


def read_source_reference(source, source_roots, scopes):
    """root mapping은 권한이 아니다. 읽기는 별도 명시 FileScope에 한정한다."""
    path = source.get("path") if isinstance(source, dict) else None
    if not isinstance(path, str) or not path:
        raise FileError("source_unlocated")
    scopes = tuple(scopes.values()) if isinstance(scopes, dict) else tuple(scopes)
    if path.startswith("batang-source:"):
        root, relative = resolve_source_uri(path, source_roots)
        candidates = [(scope, relative) for scope in scopes if _scope_root(scope) == root
                      and _parts(relative) in scope.allowed]
    elif path.startswith("/"):
        parts = _parts(path, absolute=True)
        candidates = [(scope, "/".join(parts[len(scope.root_parts):])) for scope in scopes
                      if parts[:len(scope.root_parts)] == scope.root_parts
                      and parts[len(scope.root_parts):] in scope.allowed]
    else:
        parts = _parts(path)
        candidates = [(scope, path) for scope in scopes if parts in scope.allowed]
    if len(candidates) != 1:
        raise FileError("source_read_scope")
    snapshot = candidates[0][0].read(candidates[0][1])
    expected = source.get("sha256")
    if expected is not None and snapshot.sha256 != expected:
        raise ConflictError("source_reference_changed")
    return snapshot


def _source_snapshot(scope, path):
    with scope._parent(path) as (parent, name):
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            result = _read_fd_at(parent, name, fd)
            _check_at(parent, name, fd, before)
            return result, _identity(before)
        finally:
            os.close(fd)


def verify_import_source(source_scope, result):
    """호스트는 활성 목록 반영 직전에 호출한다. 전체 등록 원자성은 제공하지 않는다."""
    if _scope_root(source_scope) != result.provenance["source_root"]:
        raise ConflictError("import_source_scope")
    snapshot, identity = _source_snapshot(source_scope, result.provenance["source_path"])
    if identity != result.source_identity or snapshot.sha256 != result.provenance["source_sha256"]:
        raise ConflictError("import_source_changed")
    return True


def _limited_yaml(header):
    return _load_metadata(header)


def _import_metadata(data, source_path, source_hash, subject, content_kind, *, private_source_uri):
    if data.startswith((b"---\n", b"---\r\n")):
        header, body = split_frontmatter(data)
        metadata = _load_metadata(header)
        if ("batang_schema_version" in metadata or "batang_id" in metadata
                or {"sources", "legacy_refs"}.issubset(metadata)):
            if not set(KEYS).issubset(metadata):
                raise FileError("import_managed_metadata_incomplete")
            validate_metadata(metadata)
    else:
        metadata, body = {}, data
    # 기존 속성을 바꾸지 않고 없는 필수 키만 신규 문서 기본값으로 채운다.
    metadata = copy.deepcopy(metadata)
    metadata.setdefault("batang_schema_version", 2)
    metadata.setdefault("batang_id", str(uuid.uuid4()))
    metadata.setdefault("subject", subject if subject is not None else os.path.splitext(source_path[-1])[0])
    metadata.setdefault("content_kind", content_kind)
    metadata.setdefault("tags", [])
    metadata.setdefault("legacy_refs", [])
    metadata.setdefault("sources", [{"id": str(uuid.uuid4()), "path": private_source_uri,
                                    "origin": "user", "sha256": source_hash, "raw_path": None}])
    validate_metadata(metadata)
    # strict 문서는 CRLF, 순서와 formatting까지 no-op으로 보존한다.
    try:
        original_metadata, original_body = parse_document(data)
    except FileError:
        return metadata, body, serialize_document(metadata, body)
    return metadata, body, serialize_document(metadata, body, original=data)


def _vault_prefix(scope, source_vault_root):
    vault = scope.root_parts if source_vault_root is None else _parts(source_vault_root, absolute=True)
    if scope.root_parts[:len(vault)] != vault:
        raise FileError("import_vault_scope")
    return "/".join(scope.root_parts[len(vault):])


def inspect_import_links(data, source_scope, source_path, selected_sources, *, source_vault_root=None):
    """명시 선택 표 안에서만 참조를 대조한다. 선택 밖 stat/read는 하지 않는다."""
    selected = tuple(selected_sources)
    if not {_parts(path) for path in selected}.issubset(source_scope.allowed):
        raise FileError("import_reference_scope")
    try:
        references = _link_data.inventory(data, source_path, selected,
                            vault_prefix=_vault_prefix(source_scope, source_vault_root))
    except (UnicodeError, ValueError):
        raise FileError("import_reference_format") from None
    result = []
    for reference in references:
        reference = dict(reference)
        if reference["status"] == "selected":
            try:
                source_scope.read(reference["source_path"])
            except (OSError, FileError):
                reference["status"] = "broken"
        result.append(reference)
    return tuple(result)


def _import_references(data, source_scope, source_path, selected_sources):
    return inspect_import_links(data, source_scope, source_path, selected_sources)


def prepare_import(source_scope, source_path, target_scope, target_path, *, subject=None,
                   content_kind="note", registered_documents=(), prior_imports=(),
                   selected_sources=(), source_root_id=None, source_vault_root=None,
                   target_mapping=None, target_vault_root=None):
    """선택한 원본의 독립 복제만 만든다. ACTIVE 편집·동기화·실패 복제 삭제는 하지 않는다."""
    source_parts = source_scope.root_parts + _parts(source_path)
    target_parts = target_scope.root_parts + _parts(target_path)
    selected_sources = tuple(selected_sources)
    selected_parts = {_parts(path) for path in selected_sources} | {_parts(source_path)}
    if not selected_parts.issubset(source_scope.allowed):
        raise FileError("import_reference_scope")
    if target_parts in {source_scope.root_parts + parts for parts in selected_parts}:
        raise FileError("import_source_overlap")
    mapping = {} if target_mapping is None else dict(target_mapping)
    if (not {_parts(path) for path in mapping}.issubset(selected_parts)
            or not {_parts(path) for path in mapping.values()}.issubset(target_scope.allowed)
            or len(set(mapping.values())) != len(mapping)
            or (source_path in mapping and mapping[source_path] != target_path)):
        raise FileError("import_destination_mapping")
    snapshot, identity = _source_snapshot(source_scope, source_path)
    provenance = {"source_root": _scope_root(source_scope), "source_path": source_path,
                  "source_sha256": snapshot.sha256, "source_file_identity": identity[:2]}
    registered = []
    registered_ids = set()
    for scope, path in registered_documents:
        saved = scope.read(path)
        value, _ = parse_document(saved.data)
        if value["batang_id"] in registered_ids:
            raise ConflictError("import_registered_id_collision")
        registered_ids.add(value["batang_id"])
        registered.append((scope, path, saved, value))
    source_key = (_scope_root(source_scope), source_path)
    for prior in prior_imports:
        if (prior.provenance["source_root"], prior.provenance["source_path"]) != source_key:
            continue
        if prior.provenance["source_file_identity"] != identity[:2]:
            raise ConflictError("import_source_identity_conflict")
        if prior.provenance["source_sha256"] != snapshot.sha256:
            continue
        for scope, path, saved, value in registered:
            if (_scope_root(scope), path) == (prior.target_root, prior.target_path):
                if value["batang_id"] != prior.metadata["batang_id"]:
                    raise ConflictError("import_registered_identity")
                result = ImportResult("skipped", prior.target_root, path, saved.sha256,
                                      value, provenance, prior.references, identity,
                                      prior.source_root_binding)
                verify_import_source(source_scope, result)
                return result
        raise ConflictError("import_registered_missing")
    with target_scope._parent(target_path) as (parent, name):
        try:
            existing = os.stat(name, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if (existing.st_dev, existing.st_ino) == identity[:2]:
                raise ConflictError("import_same_inode")
            raise ConflictError("import_target_collision")
    root_id = str(uuid.uuid4()) if source_root_id is None else _root_id(source_root_id)
    uri = source_uri(root_id, source_path)
    metadata, body, encoded = _import_metadata(snapshot.data, source_parts, snapshot.sha256,
                                               subject, content_kind, private_source_uri=uri)
    binding = {root_id: _scope_root(source_scope)} if any(
        source["path"] == uri for source in metadata["sources"]) else {}
    if any(value["batang_id"] == metadata["batang_id"] for _, _, _, value in registered):
        raise ConflictError("import_metadata_id_collision")
    references = inspect_import_links(body, source_scope, source_path, selected_sources,
                                      source_vault_root=source_vault_root)
    if target_mapping is not None:
        try:
            body, references = _link_data.rewrite(body, references, target_path, mapping,
                                  target_vault_prefix=_vault_prefix(target_scope, target_vault_root))
        except ValueError:
            raise FileError("import_reference_format") from None
        encoded = serialize_document(metadata, body, original=encoded)
    result = ImportResult("prepared", _scope_root(target_scope), target_path, sha256(encoded),
                          metadata, provenance, references, identity, binding)
    verify_import_source(source_scope, result)

    def transform(copied):
        if copied != snapshot.data or sha256(copied) != snapshot.sha256:
            raise ConflictError("import_copy_mismatch")
        parsed, actual_body = parse_document(encoded)
        if parsed != metadata or actual_body != body:
            raise FileError("import_conversion_mismatch")
        return encoded

    def before_publish():
        verify_import_source(source_scope, result)
        for scope, path, saved, _ in registered:
            if scope.read(path).sha256 != saved.sha256:
                raise ConflictError("import_registered_changed")

    target_scope.write(target_path, snapshot.data, _prepare=transform, _before_publish=before_publish)
    copied = target_scope.read(target_path)
    if copied.data != encoded:
        raise ConflictError("import_target_changed")
    _, target_identity = _source_snapshot(target_scope, target_path)
    if target_identity[:2] == identity[:2]:
        raise ConflictError("import_copy_not_independent")
    with target_scope._parent(target_path) as (parent, name):
        if os.stat(name, dir_fd=parent, follow_symlinks=False).st_nlink != 1:
            raise ConflictError("import_copy_not_independent")
    verify_import_source(source_scope, result)
    return result


def _anchor_present(snapshot, anchor):
    try:
        _, target_body = parse_document(snapshot.data)
        content = target_body.decode("utf-8")
    except (FileError, UnicodeError):
        return None
    ambiguous = []
    html = []
    visible = _link_data.markdown_content(content, uncertain_ranges=ambiguous, html_ranges=html)
    if html:
        return None
    if re.search(r"<[A-Za-z/!]", visible):
        return None
    label = unquote(anchor[1:])
    if label.startswith("^"):
        block_id = label[1:]
        if not re.fullmatch(r"[A-Za-z0-9-]+", block_id):
            return False
        found = list(re.finditer(r"(?:^|[ \t])\^" + re.escape(block_id) + r"[ \t\r]*$", visible, re.M))
        if any(not any(match.start() < end and match.end() > start for start, end in ambiguous)
               for match in found):
            return True
        return None if found else False
    requested = [unquote(part).strip().casefold() for part in anchor[1:].split("#")]
    if not requested or any(not part for part in requested):
        return False
    raw_visible = _link_data.markdown_content(content, inline_code=False)
    # HTML 제목·여러 줄 코드 span·Setext·복잡한 inline 표현은 확정 대상으로 만들지 않는다.
    uncertain = bool(ambiguous)
    stack = []
    line_offset = 0
    for raw_line, line in zip(raw_visible.split("\n"), visible.split("\n")):
        line_ambiguous = any(line_offset < end and line_offset + len(line) > start for start, end in ambiguous)
        line_offset += len(line) + 1
        if re.fullmatch(r" {0,3}(?:=+|-+)[ \t\r]*", line):
            uncertain = True
            depth = 1 if line.lstrip().startswith("=") else 2
            while stack and stack[-1][0] >= depth:
                stack.pop()
            stack.append((depth, None))
        match = re.fullmatch(r" {0,3}(#{1,6})(?:[ \t]+(.*?)|[ \t]*)\r?", line)
        if not match:
            continue
        depth = len(match.group(1))
        title = re.sub(r"[ \t]+#+[ \t]*$", "", match.group(2) or "").strip().casefold()
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if line_ambiguous or any(char in raw_line for char in "`*_[]<\\"):
            title = None
            uncertain = True
        stack.append((depth, title))
        if title != requested[-1]:
            continue
        parents = iter(value for _, value in reversed(stack[:-1]))
        if all(any(parent == expected for parent in parents) for expected in reversed(requested[:-1])):
            return True
    return None if uncertain else False


def verify_import_destinations(results, target_scope, *, target_vault_root=None):
    """복제된 파일의 현재 내용과 각 링크의 실제 목적지를 다시 대조한다."""
    results = tuple(results)
    by_target = {result.target_path: result for result in results}
    if len(by_target) != len(results):
        raise FileError("import_destination_duplicate")
    snapshots = {}
    for path, result in by_target.items():
        if result.target_root != _scope_root(target_scope):
            raise FileError("import_destination_scope")
        try:
            saved = target_scope.read(path)
        except (FileError, OSError):
            continue
        if saved.sha256 != result.target_sha256:
            raise ConflictError("import_destination_changed")
        snapshots[path] = saved
    checked = []
    for result in results:
        if result.target_path not in snapshots:
            checked.append({"target_path": result.target_path, "status": "missing"})
            continue
        if not result.metadata:
            continue
        metadata, body = parse_document(snapshots[result.target_path].data)
        if metadata["batang_id"] != result.metadata["batang_id"]:
            raise ConflictError("import_destination_identity")
        actual = _link_data.inventory(body, result.target_path, snapshots,
                                      vault_prefix=_vault_prefix(target_scope, target_vault_root))
        for ref in result.references:
            status = ref.get("destination_status", "unverified")
            destination = ref.get("destination_path")
            target = None
            if status == "same_document":
                destination = result.target_path
                target = snapshots[destination]
            if status == "mapped":
                target = snapshots.get(destination)
                found = [item for item in actual if item["reference"] == ref["destination_reference"]]
                if target is None or not any(item.get("source_path") == destination for item in found):
                    status = "broken"
                else:
                    status = "verified"
            anchor = ref.get("anchor", "")
            if target is not None and status in ("verified", "same_document") and anchor:
                found_anchor = _anchor_present(target, anchor)
                if found_anchor is None:
                    status = "anchor_unverified"
                elif not found_anchor:
                    status = "broken_anchor"
            checked.append({"target_path": result.target_path, "reference": ref["reference"],
                            "destination_path": destination, "status": status})
    return tuple(checked)


def prepare_import_batch(source_scope, selected_sources, target_scope, target_mapping, *,
                         source_root_id=None, source_vault_root=None, target_vault_root=None,
                         registered_documents=(), prior_imports=(), attachment_paths=()):
    """선택 항목 수와 처리 결과 수를 맞춘다. 등록과 그래프 반영은 호출자가 이어간다."""
    selected = tuple(selected_sources)
    if len(set(selected)) != len(selected) or set(target_mapping) != set(selected):
        raise FileError("import_batch_selection")
    if (not {_parts(path) for path in selected}.issubset(source_scope.allowed)
            or not {_parts(path) for path in target_mapping.values()}.issubset(target_scope.allowed)
            or len(set(target_mapping.values())) != len(target_mapping)
            or not set(attachment_paths).issubset(selected)):
        raise FileError("import_batch_scope")
    source_paths = {source_scope.root_parts + _parts(path) for path in selected}
    if any(target_scope.root_parts + _parts(path) in source_paths for path in target_mapping.values()):
        raise FileError("import_source_overlap")
    root_id = str(uuid.uuid4()) if source_root_id is None else _root_id(source_root_id)
    entries, results = [], []
    registered = list(registered_documents)
    for path in selected:
        entry = {"source_path": path, "target_path": target_mapping[path],
                 "registration_status": "not_registered", "graph_status": "not_registered"}
        try:
            if path in attachment_paths:
                snapshot, identity = _source_snapshot(source_scope, path)
                provenance = {"source_root": _scope_root(source_scope), "source_path": path,
                              "source_sha256": snapshot.sha256, "source_file_identity": identity[:2]}
                result = ImportResult("prepared", _scope_root(target_scope), target_mapping[path],
                                      snapshot.sha256, {}, provenance, (), identity, {root_id: _scope_root(source_scope)})
                verify_import_source(source_scope, result)
                target_scope.write(result.target_path, snapshot.data,
                                   _before_publish=lambda: verify_import_source(source_scope, result))
                saved = target_scope.read(result.target_path)
                if saved.sha256 != result.target_sha256:
                    raise ConflictError("import_target_changed")
                verify_import_source(source_scope, result)
                entry["kind"] = "attachment"
            else:
                result = prepare_import(source_scope, path, target_scope, target_mapping[path],
                    source_root_id=root_id, source_vault_root=source_vault_root,
                    target_mapping=target_mapping, target_vault_root=target_vault_root,
                    registered_documents=registered, prior_imports=prior_imports, selected_sources=selected)
                if not any(_scope_root(scope) == result.target_root and registered_path == result.target_path
                           for scope, registered_path in registered):
                    registered.append((target_scope, result.target_path))
                entry["kind"] = "note"
            entry.update(status=result.status, result=result)
            results.append(result)
        except (FileError, OSError) as exc:
            entry.update(status="failed", error_code=getattr(exc, "code", "import_io_error"),
                         error_message=str(exc) if isinstance(exc, FileError) else "파일 접근 또는 게시를 완료하지 못했습니다.")
        entries.append(entry)
    reference_error = None
    try:
        references = verify_import_destinations(results, target_scope, target_vault_root=target_vault_root)
    except (FileError, OSError) as exc:
        references = ()
        reference_error = getattr(exc, "code", "import_io_error")
    bindings = {root_id: _scope_root(source_scope)}
    for result in results:
        bindings.update(result.source_root_binding or {})
    # 준비 시 성공했어도 마지막 대조에서 사라진 파일을 성공 집계에 남기지 않는다.
    copy_validation = {}
    for result in results:
        try:
            current = target_scope.read(result.target_path)
        except FileNotFoundError:
            status = "missing"
        except (FileError, OSError):
            status = "unverified"
        else:
            status = "verified" if current.sha256 == result.target_sha256 else "changed"
        copy_validation[result.target_path] = status
    for entry in entries:
        if entry["status"] in ("prepared", "skipped"):
            status = copy_validation[entry["target_path"]]
            entry["copy_validation_status"] = status
            if status != "verified":
                entry["preparation_status"] = entry["status"]
                entry.update(status="failed", error_code="import_destination_" + status,
                             error_message="준비 후 복제본이 사라졌거나 변경됐습니다. 현재 파일을 확인해 주세요.")
    valid_count = sum(entry["status"] in ("prepared", "skipped") for entry in entries)
    return {"entries": tuple(entries), "selected_count": len(selected),
            "prepared_count": valid_count, "source_root_binding": bindings,
            "references": references,
            "reference_check_error": reference_error,
            "selection_accounted": len(entries) == len(selected),
            "copies_complete": valid_count == len(selected) and reference_error is None,
            "references_complete": (valid_count == len(selected) and reference_error is None
                                     and all(ref["status"] in ("verified", "same_document") for ref in references)),
            "registration_complete": False, "graph_complete": False}


def _parts(value, absolute=False):
    try:
        raw = os.fspath(value)
    except TypeError:
        raise FileError("path_format") from None
    if not isinstance(raw, str) or "\\" in raw or "\x00" in raw:
        raise FileError("path_format")
    pieces = raw.split("/")
    if absolute:
        if not raw.startswith("/"):
            raise FileError("root_absolute")
        pieces = pieces[1:]
    elif raw.startswith("/"):
        raise FileError("path_relative")
    if not pieces or any(p in ("", ".", "..") for p in pieces):
        raise FileError("path_canonical")
    return tuple(pieces)


def _open_dir(name, parent=None):
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class _MacOSACL:
    """Darwin의 ACL만 fd로 처리한다. 외부 표현은 이 인스턴스 내부에서 생성한다."""

    ACL_TYPE_EXTENDED = 0x100

    def __init__(self):
        self.lib = ctypes.CDLL(None, use_errno=True)
        signatures = {
            "acl_get_fd_np": ([ctypes.c_int, ctypes.c_int], ctypes.c_void_p),
            "acl_set_fd_np": ([ctypes.c_int, ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            "acl_init": ([ctypes.c_int], ctypes.c_void_p),
            "acl_size": ([ctypes.c_void_p], ctypes.c_ssize_t),
            "acl_copy_ext": ([ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ssize_t], ctypes.c_ssize_t),
            "acl_copy_int": ([ctypes.c_void_p], ctypes.c_void_p),
            "acl_free": ([ctypes.c_void_p], ctypes.c_int),
        }
        try:
            for name, (arguments, result) in signatures.items():
                function = getattr(self.lib, name)
                function.argtypes = arguments
                function.restype = result
        except AttributeError:
            raise FileError("acl_unavailable") from None
        acl = self.lib.acl_init(0)
        if not acl:
            self._error("acl_init")
        try:
            self.empty = self._serialize(acl)
        finally:
            self.lib.acl_free(acl)

    @staticmethod
    def _error(operation):
        code = ctypes.get_errno()
        raise OSError(code, operation)

    def _serialize(self, acl):
        size = self.lib.acl_size(acl)
        if size < 0:
            self._error("acl_size")
        if size == 0:
            raise FileError("acl_size_empty")
        buffer = ctypes.create_string_buffer(size)
        copied = self.lib.acl_copy_ext(buffer, acl, size)
        if copied < 0:
            self._error("acl_copy_ext")
        if not 0 < copied <= size:
            raise FileError("acl_serialization")
        # 엔트리 순서·UUID·권한·상속 flag를 이름 해석 없이 비교한다.
        return buffer.raw[:copied]

    def read(self, fd):
        acl = self.lib.acl_get_fd_np(fd, self.ACL_TYPE_EXTENDED)
        if not acl:
            if ctypes.get_errno() == errno.ENOENT:
                return self.empty
            self._error("acl_get_fd_np")
        try:
            return self._serialize(acl)
        finally:
            self.lib.acl_free(acl)

    def apply(self, fd, value):
        buffer = ctypes.create_string_buffer(value)
        acl = self.lib.acl_copy_int(buffer)
        if not acl:
            self._error("acl_copy_int")
        try:
            if self.lib.acl_set_fd_np(fd, acl, self.ACL_TYPE_EXTENDED) != 0:
                self._error("acl_set_fd_np")
        finally:
            self.lib.acl_free(acl)
        if self.read(fd) != value:
            raise FileError("acl_verification")


def _rename_new_at(source_parent, temporary, target_parent, name):
    """macOS에서 대상이 없을 때만 임시 파일을 원자적으로 게시한다."""
    if sys.platform != "darwin":
        raise FileError("atomic_create_unavailable")
    library = ctypes.CDLL(None, use_errno=True)
    try:
        rename = library.renameatx_np
    except AttributeError:
        raise FileError("atomic_create_unavailable") from None
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                       ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    # Darwin <sys/stdio.h>: RENAME_EXCL = 0x00000004.
    if rename(source_parent, os.fsencode(temporary), target_parent,
              os.fsencode(name), 0x4) != 0:
        code = ctypes.get_errno()
        raise OSError(code, "renameatx_np")


def _open_staging_dir(target_parent, acl, staging_root=None):
    """같은 파일시스템의 소유자 전용 staging 디렉터리를 fd로 연다."""
    if acl is None:
        raise FileError("private_staging_unavailable")
    # /var 같은 시스템 symlink는 한 번 정규화하고 실제 경로는 모두 no-follow로 연다.
    root = os.path.realpath(tempfile.gettempdir()) if staging_root is None else staging_root
    parts = _parts(root, absolute=True)
    fd = _open_dir("/")
    try:
        for component in parts:
            following = _open_dir(component, fd)
            os.close(fd)
            fd = following
        info = os.fstat(fd)
        if (info.st_dev != os.fstat(target_parent).st_dev or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700 or acl.read(fd) != acl.empty):
            raise FileError("private_staging_unavailable")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _open_operation_staging(parent, acl):
    """private root 안의 새 전용 디렉터리. 이름 충돌은 덮어쓰지 않는다."""
    name = ".batang-op-" + uuid.uuid4().hex
    os.mkdir(name, 0o700, dir_fd=parent)
    fd = _open_dir(name, parent)
    try:
        acl.apply(fd, acl.empty)
        os.fchmod(fd, 0o700)
        info = os.fstat(fd)
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700 or acl.read(fd) != acl.empty
                or (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)):
            raise FileError("operation_staging_identity")
        # 같은 절차를 쓰는 writer만 배제한다. 비협력 same-UID writer는 막지 못한다.
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return name, fd, info
    except BaseException:
        os.close(fd)
        raise


def _cleanup_operation(parent, name, directory, expected, temporary, fd, temporary_info):
    """호스트의 실제 배타 guard 안에서만 호출한다. 식별 실패 시 모두 보존한다."""
    actual = os.fstat(directory)
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (not stat.S_ISDIR(actual.st_mode) or not stat.S_ISDIR(current.st_mode)
            or (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino)
            or (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino)
            or actual.st_uid != os.geteuid() or current.st_uid != os.geteuid()
            or stat.S_IMODE(actual.st_mode) != 0o700 or stat.S_IMODE(current.st_mode) != 0o700):
        return
    if fd is not None:
        try:
            staged = os.stat(temporary, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return
        held = os.fstat(fd)
        if (not stat.S_ISREG(held.st_mode) or not stat.S_ISREG(staged.st_mode)
                or (held.st_dev, held.st_ino) != (temporary_info.st_dev, temporary_info.st_ino)
                or (staged.st_dev, staged.st_ino) != (temporary_info.st_dev, temporary_info.st_ino)
                or held.st_uid != os.geteuid() or staged.st_uid != os.geteuid()
                or held.st_nlink != 1 or staged.st_nlink != 1 or held.st_size or staged.st_size
                or set(os.listdir(directory)) != {temporary}):
            return
        os.unlink(temporary, dir_fd=directory)
    if not os.listdir(directory):
        os.rmdir(name, dir_fd=parent)


def _check_at(parent, name, fd, expected):
    actual = os.fstat(fd)
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (not stat.S_ISREG(actual.st_mode) or not stat.S_ISREG(current.st_mode)
            or _identity(actual) != _identity(expected)
            or _identity(current) != _identity(expected)
            or actual.st_mode != expected.st_mode or current.st_mode != expected.st_mode):
        raise ConflictError("changed_file_identity")


def _read_fd_at(parent, name, fd):
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise FileError("not_regular")
    os.lseek(fd, 0, os.SEEK_SET)
    with os.fdopen(os.dup(fd), "rb") as stream:
        data = stream.read()
    _check_at(parent, name, fd, before)
    return Snapshot(data, sha256(data), stat.S_IMODE(before.st_mode))


def _read_at(parent, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    try:
        return _read_fd_at(parent, name, fd)
    finally:
        os.close(fd)


class FileScope:
    def __init__(self, root, explicit_relative_paths, *, cleanup_guard=None, staging_root=None):
        if isinstance(explicit_relative_paths, (str, bytes)):
            raise FileError("explicit_file_list")
        self.root_parts = _parts(root, absolute=True)
        self.allowed = frozenset(_parts(p) for p in explicit_relative_paths)
        # None이면 삭제하지 않는다. guard는 호스트가 실제 writer 배타를 유지하는
        # contextmanager factory이며 boolean을 보안 근거로 받지 않는다.
        if cleanup_guard is not None and not callable(cleanup_guard):
            raise FileError("cleanup_guard_context")
        self.cleanup_guard = cleanup_guard
        if staging_root is not None:
            _parts(staging_root, absolute=True)
        self.staging_root = staging_root

    @contextmanager
    def _parent(self, path):
        parts = _parts(path)
        if parts not in self.allowed:
            raise FileError("path_not_allowed")
        fd = None
        try:
            fd = _open_dir("/")
            for component in self.root_parts + parts[:-1]:
                following = _open_dir(component, fd)
                os.close(fd)
                fd = following
            yield fd, parts[-1]
        except OSError as exc:
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise FileError("path_symlink") from None
            raise
        finally:
            if fd is not None:
                os.close(fd)

    def read(self, path):
        with self._parent(path) as (parent, name):
            return _read_at(parent, name)

    def write(self, path, data, expected_sha256=None, *, backup_scope=None, backup_path=None,
              _prepare=None, _before_publish=None):
        if not isinstance(data, bytes):
            raise FileError("write_bytes")
        if expected_sha256 is not None and (not isinstance(expected_sha256, str)
                                            or not SHA256.fullmatch(expected_sha256)):
            raise FileError("expected_hash")
        with self._parent(path) as (parent, name), ExitStack() as descriptors:
            try:
                original_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                                      dir_fd=parent)
            except FileNotFoundError:
                original_fd = None
                previous = None
            else:
                descriptors.callback(os.close, original_fd)
                original_info = os.fstat(original_fd)
                previous = _read_fd_at(parent, name, original_fd)
            if expected_sha256 is None:
                if previous is not None:
                    raise ConflictError("create_collision")
            elif previous is None or previous.sha256 != expected_sha256:
                raise ConflictError("expected_hash_changed")
            if previous is not None and previous.data == data:
                return False
            # 다른 플랫폼의 ACL 지원을 추가하지 않는다. Darwin 오류에는 fallback이 없다.
            acl = _MacOSACL() if sys.platform == "darwin" else None
            staging_root = _open_staging_dir(parent, acl, self.staging_root)
            descriptors.callback(os.close, staging_root)
            if previous is not None:
                if backup_scope is None or backup_path is None:
                    raise FileError("backup_required")
                original_acl = acl.read(original_fd) if acl else None
                _check_at(parent, name, original_fd, original_info)
                backup_scope.write(backup_path, previous.data)
            operation, staging_parent, operation_info = _open_operation_staging(staging_root, acl)
            descriptors.callback(os.close, staging_parent)
            cleanup_allowed = False
            if self.cleanup_guard is not None:
                descriptors.enter_context(self.cleanup_guard(staging_parent))
                cleanup_allowed = True
            temporary = ".batang-" + uuid.uuid4().hex + ".tmp"
            temporary_info = None
            fd = None
            publication_started = False
            try:
                fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=staging_parent)
                temporary_info = os.fstat(fd)
                if acl:
                    # 상속 ACL은 0600보다 넓은 접근을 줄 수 있으므로 bytes보다 먼저 제거한다.
                    acl.apply(fd, acl.empty)
                os.fchmod(fd, 0o600)
                with os.fdopen(fd, "wb", closefd=False) as stream:
                    stream.write(data)
                    stream.flush()
                if _prepare is not None:
                    data = _prepare(_read_fd_at(staging_parent, temporary, fd).data)
                    if not isinstance(data, bytes):
                        raise FileError("prepare_bytes")
                    os.lseek(fd, 0, os.SEEK_SET)
                    with os.fdopen(fd, "wb", closefd=False) as stream:
                        stream.write(data)
                        stream.truncate()
                        stream.flush()
                if acl and previous is not None:
                    acl.apply(fd, original_acl)
                os.fchmod(fd, previous.mode if previous else 0o600)
                os.fsync(fd)
                ready = os.fstat(fd)
                if ready.st_nlink != 1 or ready.st_uid != os.geteuid():
                    raise ConflictError("changed_temporary_links_or_owner")
                if stat.S_IMODE(ready.st_mode) != (previous.mode if previous else 0o600):
                    raise ConflictError("changed_temporary_mode")
                if (ready.st_dev, ready.st_ino) != (temporary_info.st_dev, temporary_info.st_ino):
                    raise ConflictError("changed_temporary_identity")
                _check_at(staging_parent, temporary, fd, ready)
                if acl and acl.read(fd) != (original_acl if previous else acl.empty):
                    raise FileError("acl_verification")
                if _read_fd_at(staging_parent, temporary, fd).data != data:
                    raise ConflictError("changed_temporary_contents")
                if _before_publish is not None:
                    _before_publish()
                if previous is None:
                    _check_at(staging_parent, temporary, fd, ready)
                    publication_started = True
                    _rename_new_at(staging_parent, temporary, parent, name)
                else:
                    current = _read_fd_at(parent, name, original_fd)
                    if current.sha256 != expected_sha256 or current.mode != previous.mode:
                        raise ConflictError("changed_before_replace")
                    if acl and acl.read(original_fd) != original_acl:
                        raise ConflictError("changed_acl_before_replace")
                    _check_at(parent, name, original_fd, original_info)
                    _check_at(staging_parent, temporary, fd, ready)
                    # 이 최종 확인과 replace 사이의 외부 writer 경합은 잠그지 않는다.
                    publication_started = True
                    os.replace(temporary, name, src_dir_fd=staging_parent, dst_dir_fd=parent)
                return True
            finally:
                try:
                    interrupted = sys.exc_info()[0] is not None and not issubclass(sys.exc_info()[0], Exception)
                    if fd is not None and not publication_started and not interrupted:
                        # 경로의 stat→unlink는 타인의 교체 파일을 지울 수 있다.
                        # fd가 가리키는 우리 임시 inode만 비우고 0600으로 제한한다.
                        # 게시를 시도한 뒤에는 대상 inode일 수 있어 비우지 않는다.
                        held = os.fstat(fd)
                        if (stat.S_ISREG(held.st_mode) and held.st_nlink == 1
                                and held.st_uid == os.geteuid()
                                and (held.st_dev, held.st_ino) == (temporary_info.st_dev, temporary_info.st_ino)):
                            os.fchmod(fd, 0o600)
                            os.ftruncate(fd, 0)
                    if cleanup_allowed and not interrupted:
                        if not publication_started and fd is not None:
                            _cleanup_operation(staging_root, operation, staging_parent, operation_info,
                                               temporary, fd, temporary_info)
                        elif publication_started and sys.exc_info()[0] is None:
                            _cleanup_operation(staging_root, operation, staging_parent, operation_info,
                                               temporary, None, None)
                finally:
                    if fd is not None:
                        os.close(fd)
