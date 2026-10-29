"""호스트의 실제 협력 lock이 있는 경우에만 전용 빈 임시 대상을 정리한다."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_file_ops import ops


@unittest.skipUnless(sys.platform == "darwin", "macOS 파일 게시 계약")
class Cleanup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.stage = self.root / "stage"
        self.stage.mkdir(mode=0o700)
        self.target = self.root / "target"
        self.target.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(ops.tempfile, "gettempdir", return_value=str(self.stage)).start()
        self.entered = []

        @contextmanager
        def cooperative_guard(operation_fd):
            root_fd = os.open(self.stage, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                fcntl.flock(root_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.entered.append((os.fstat(operation_fd).st_ino, True))
                yield
            finally:
                self.entered.append((os.fstat(operation_fd).st_ino, False))
                os.close(root_fd)

        self.guard = cooperative_guard
        self.scope = ops.FileScope(self.target, ["new.md"], cleanup_guard=self.guard)

    def temps(self):
        return list(self.stage.rglob(".batang-*.tmp"))

    def test_no_guard_means_no_automatic_cleanup_and_bool_is_rejected(self):
        scope = ops.FileScope(self.target, ["new.md"])
        self.assertTrue(scope.write("new.md", b"new"))
        operation, = self.stage.iterdir()
        self.assertTrue(operation.is_dir())
        self.assertFalse(list(operation.iterdir()))
        for invalid in (True, False):
            with self.assertRaisesRegex(ops.FileError, "cleanup_guard_context"):
                ops.FileScope(self.target, ["new.md"], cleanup_guard=invalid)

    def test_success_removes_only_empty_owned_operation_directory_under_guard(self):
        self.assertTrue(self.scope.write("new.md", b"new"))
        self.assertEqual(list(self.stage.iterdir()), [])
        self.assertEqual((self.target / "new.md").read_bytes(), b"new")
        self.assertEqual(len(self.entered), 2)
        self.assertEqual(self.entered[0][0], self.entered[1][0])
        self.assertEqual([state for _, state in self.entered], [True, False])

    def test_real_cooperating_process_cannot_take_guard_lock(self):
        real_rename = ops._rename_new_at
        observed = []
        program = ("import fcntl,os,sys\n"
                   "fd=os.open(sys.argv[1],os.O_RDONLY|os.O_DIRECTORY)\n"
                   "try:\n fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
                   "except BlockingIOError:\n sys.exit(7)\n"
                   "else:\n sys.exit(0)\n")

        def check(*args):
            child = subprocess.run([sys.executable, "-B", "-c", program, str(self.stage)],
                                   capture_output=True, check=False)
            observed.append(child.returncode)
            return real_rename(*args)

        with patch.object(ops, "_rename_new_at", side_effect=check):
            self.assertTrue(self.scope.write("new.md", b"new"))
        self.assertEqual(observed, [7])
        self.assertFalse(list(self.stage.iterdir()))

    def test_prepublication_failure_scrubs_then_removes_only_verified_empty_temp(self):
        with patch.object(ops.os, "fsync", side_effect=OSError("fixture fsync")):
            with self.assertRaises(OSError):
                self.scope.write("new.md", b"sensitive synthetic bytes")
        self.assertFalse((self.target / "new.md").exists())
        self.assertFalse(list(self.stage.iterdir()))

    def test_prepublication_failure_without_guard_preserves_scrubbed_file_and_directory(self):
        scope = ops.FileScope(self.target, ["new.md"])
        with patch.object(ops.os, "fsync", side_effect=OSError("fixture fsync")):
            with self.assertRaises(OSError):
                scope.write("new.md", b"sensitive synthetic bytes")
        temporary, = self.temps()
        self.assertEqual(temporary.read_bytes(), b"")
        self.assertEqual(stat.S_IMODE(temporary.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(temporary.parent.stat().st_mode), 0o700)

    def test_publication_attempt_failure_preserves_staged_bytes_and_directory(self):
        with patch.object(ops, "_rename_new_at", side_effect=OSError("uncertain publication")):
            with self.assertRaises(OSError):
                self.scope.write("new.md", b"preserve")
        temporary, = self.temps()
        self.assertEqual(temporary.read_bytes(), b"preserve")
        self.assertFalse((self.target / "new.md").exists())

    def test_interrupt_before_or_after_publication_preserves_operation_directory(self):
        with patch.object(ops.os, "fsync", side_effect=KeyboardInterrupt("forced termination")):
            with self.assertRaises(KeyboardInterrupt):
                self.scope.write("new.md", b"preserve")
        temporary, = self.temps()
        self.assertEqual(temporary.read_bytes(), b"preserve")
        real_rename = ops._rename_new_at

        def interrupted(*args):
            real_rename(*args)
            raise KeyboardInterrupt("after publication")

        with patch.object(ops, "_rename_new_at", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.scope.write("new.md", b"published")
        self.assertEqual((self.target / "new.md").read_bytes(), b"published")
        self.assertEqual(len(list(self.stage.iterdir())), 2)

    def test_hardlinked_temporary_is_neither_scrubbed_nor_removed(self):
        def race(fd):
            temporary, = self.temps()
            os.link(temporary, self.root / "foreign-link")
            raise OSError("fixture link race")

        with patch.object(ops.os, "fsync", side_effect=race):
            with self.assertRaises(OSError):
                self.scope.write("new.md", b"preserve linked bytes")
        temporary, = self.temps()
        self.assertEqual(temporary.read_bytes(), b"preserve linked bytes")
        self.assertEqual((self.root / "foreign-link").read_bytes(), b"preserve linked bytes")
        self.assertEqual(temporary.stat().st_nlink, 2)

    def test_foreign_file_or_backup_in_operation_directory_prevents_cleanup(self):
        def race(fd):
            temporary, = self.temps()
            (temporary.parent / "recovery.before").write_bytes(b"preserve backup")
            raise OSError("fixture foreign file")

        with patch.object(ops.os, "fsync", side_effect=race):
            with self.assertRaises(OSError):
                self.scope.write("new.md", b"ours")
        temporary, = self.temps()
        self.assertEqual(temporary.read_bytes(), b"")
        self.assertEqual((temporary.parent / "recovery.before").read_bytes(), b"preserve backup")

    def test_replaced_file_identity_is_not_unlinked(self):
        foreign = []

        def race(fd):
            temporary, = self.temps()
            temporary.rename(self.root / "detached-ours")
            temporary.write_bytes(b"foreign")
            foreign.append(temporary)
            raise OSError("fixture replacement")

        with patch.object(ops.os, "fsync", side_effect=race):
            with self.assertRaises(OSError):
                self.scope.write("new.md", b"ours")
        self.assertEqual(foreign[0].read_bytes(), b"foreign")
        self.assertEqual((self.root / "detached-ours").read_bytes(), b"")

    def test_replaced_directory_identity_is_preserved(self):
        real_cleanup = ops._cleanup_operation
        displaced = self.root / "displaced-operation"

        def replace_directory(parent, name, directory, expected, *args):
            os.rename(self.stage / name, displaced)
            (self.stage / name).mkdir(mode=0o700)
            return real_cleanup(parent, name, directory, expected, *args)

        with patch.object(ops, "_cleanup_operation", side_effect=replace_directory):
            self.assertTrue(self.scope.write("new.md", b"new"))
        self.assertTrue(displaced.is_dir())
        self.assertEqual(len(list(self.stage.iterdir())), 1)

    def test_unexpected_temp_owner_refuses_scrub_and_cleanup(self):
        real_fstat = ops.os.fstat
        changed = []

        def incorrect_owner(fd):
            value = real_fstat(fd)
            if changed and stat.S_ISREG(value.st_mode):
                fake = unittest.mock.Mock(wraps=value)
                for key in ("st_mode", "st_nlink", "st_dev", "st_ino", "st_size"):
                    setattr(fake, key, getattr(value, key))
                fake.st_uid = value.st_uid + 1
                return fake
            return value

        def fail(fd):
            changed.append(True)
            raise OSError("fixture owner change")

        with patch.object(ops.os, "fstat", side_effect=incorrect_owner):
            with patch.object(ops.os, "fsync", side_effect=fail):
                with self.assertRaises(OSError):
                    self.scope.write("new.md", b"preserve unknown ownership")
        temporary, = self.temps()
        self.assertEqual(temporary.read_bytes(), b"preserve unknown ownership")

    def test_guard_acquisition_failure_preserves_new_empty_directory(self):
        @contextmanager
        def unavailable(fd):
            raise BlockingIOError("cooperative writer active")
            yield

        scope = ops.FileScope(self.target, ["new.md"], cleanup_guard=unavailable)
        with self.assertRaises(BlockingIOError):
            scope.write("new.md", b"new")
        self.assertFalse((self.target / "new.md").exists())
        operation, = self.stage.iterdir()
        self.assertFalse(list(operation.iterdir()))


if __name__ == "__main__":
    unittest.main()
