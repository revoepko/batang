"""명시 파일만 다루는 내부 stdlib 도우미. CLI 또는 외부 writer 잠금은 제공하지 않는다."""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import copy
import ctypes
import errno
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import uuid


class FileError(ValueError):
    """원문 내용이나 민감 경로를 포함하지 않는 계약 오류."""


class ConflictError(FileError):
    """기대 상태와 현재 파일이 다르다."""


KEYS = ("batang_schema_version", "batang_id", "subject", "tags", "content_kind",
        "sources", "legacy_refs")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MISSING = object()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def validate_metadata(metadata):
    if not isinstance(metadata, dict) or set(metadata) != set(KEYS):
        raise FileError("metadata_keys")
    version = metadata["batang_schema_version"]
    if type(version) is not int or version not in (1, 2):
        raise FileError("schema_version")
    for key in ("batang_id", "subject", "content_kind"):
        if not isinstance(metadata[key], str) or not metadata[key].strip():
            raise FileError("metadata_string")
    if not isinstance(metadata["tags"], list) or any(not isinstance(t, str) for t in metadata["tags"]):
        raise FileError("metadata_tags")
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


def new_metadata(subject, content_kind, sources, *, tags=_MISSING, legacy_refs=_MISSING):
    """호스트의 신규 v2 입력만 생성한다. 저장·기존 문서 변환·권한 판단은 하지 않는다."""
    metadata = {"batang_schema_version": 2, "batang_id": str(uuid.uuid4()),
                "subject": subject, "tags": [] if tags is _MISSING else copy.deepcopy(tags),
                "content_kind": content_kind, "sources": copy.deepcopy(sources),
                "legacy_refs": [] if legacy_refs is _MISSING else copy.deepcopy(legacy_refs)}
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


def serialize_document(metadata, body, *, original=None):
    validate_metadata(metadata)
    if not isinstance(body, bytes):
        raise FileError("body_bytes")
    if original is not None:
        previous_metadata, previous_body = parse_document(original)
        if previous_metadata == metadata and previous_body == body:
            return original
    header = "---\n" + "".join(
        key + ": " + json.dumps(metadata[key], ensure_ascii=False, allow_nan=False,
                                 separators=(",", ":")) + "\n" for key in KEYS) + "---\n"
    return header.encode("utf-8") + body


def parse_document(data):
    header, body = split_frontmatter(data)
    metadata = {}
    try:
        # JSON 문자열 안의 U+0085/U+2028/U+2029는 metadata 값이며 줄 경계가 아니다.
        for line in header.decode("utf-8").removesuffix("\n").split("\n"):
            key, value = line.split(": ", 1)
            if key not in KEYS or key in metadata:
                raise FileError("frontmatter_key")
            metadata[key] = json.loads(value, object_pairs_hook=_unique_object)
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, FileError):
            raise
        raise FileError("frontmatter_unsupported") from None
    validate_metadata(metadata)
    return metadata, body


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


def _parts(value, absolute=False):
    raw = os.fspath(value)
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


def _open_staging_dir(target_parent, acl):
    """같은 파일시스템의 소유자 전용 staging 디렉터리를 fd로 연다."""
    if acl is None:
        raise FileError("private_staging_unavailable")
    # /var 같은 시스템 symlink는 한 번 정규화하고 실제 경로는 모두 no-follow로 연다.
    parts = _parts(os.path.realpath(tempfile.gettempdir()), absolute=True)
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
    def __init__(self, root, explicit_relative_paths):
        if isinstance(explicit_relative_paths, (str, bytes)):
            raise FileError("explicit_file_list")
        self.root_parts = _parts(root, absolute=True)
        self.allowed = frozenset(_parts(p) for p in explicit_relative_paths)

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
        finally:
            if fd is not None:
                os.close(fd)

    def read(self, path):
        with self._parent(path) as (parent, name):
            return _read_at(parent, name)

    def write(self, path, data, expected_sha256=None, *, backup_scope=None, backup_path=None):
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
            staging_parent = _open_staging_dir(parent, acl)
            descriptors.callback(os.close, staging_parent)
            if previous is not None:
                if backup_scope is None or backup_path is None:
                    raise FileError("backup_required")
                original_acl = acl.read(original_fd) if acl else None
                _check_at(parent, name, original_fd, original_info)
                backup_scope.write(backup_path, previous.data)
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
                if acl and previous is not None:
                    acl.apply(fd, original_acl)
                os.fchmod(fd, previous.mode if previous else 0o600)
                os.fsync(fd)
                ready = os.fstat(fd)
                if stat.S_IMODE(ready.st_mode) != (previous.mode if previous else 0o600):
                    raise ConflictError("changed_temporary_mode")
                if (ready.st_dev, ready.st_ino) != (temporary_info.st_dev, temporary_info.st_ino):
                    raise ConflictError("changed_temporary_identity")
                _check_at(staging_parent, temporary, fd, ready)
                if acl and acl.read(fd) != (original_acl if previous else acl.empty):
                    raise FileError("acl_verification")
                if _read_fd_at(staging_parent, temporary, fd).data != data:
                    raise ConflictError("changed_temporary_contents")
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
                    if fd is not None and not publication_started:
                        # 경로의 stat→unlink는 타인의 교체 파일을 지울 수 있다.
                        # fd가 가리키는 우리 임시 inode만 비우고 0600으로 제한한다.
                        # 게시를 시도한 뒤에는 대상 inode일 수 있어 비우지 않는다.
                        os.fchmod(fd, 0o600)
                        os.ftruncate(fd, 0)
                finally:
                    if fd is not None:
                        os.close(fd)
