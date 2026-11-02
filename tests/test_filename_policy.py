"""명시적으로 선택한 짧은 주제 파일명과 관리 문서 보존을 확인한다."""
import os
from pathlib import Path
import tempfile
import unittest

from test_file_ops import metadata, ops


@unittest.skipUnless(os.sys.platform == "darwin", "macOS 파일 게시 계약")
class ExplicitFilenamePolicy(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="filename-policy-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.target = self.root / "target"
        self.source.mkdir(mode=0o700)
        self.target.mkdir(mode=0o700)
        self.source_scope = ops.FileScope(self.source, ["old--45ae8a62.md"])
        self.target_scope = ops.FileScope(self.target, [
            "toss-technical-writing.md",
            "toss-technical-writing-korean.md",
        ])
        self.metadata = metadata()
        self.metadata["batang_schema_version"] = 2
        self.metadata["batang_id"] = "stable-managed-id"
        self.metadata["subject"] = "토스 기술 글쓰기"
        self.body = "\r\n# 본문\r\n\r\n원문 바이트 유지\r\n".encode()
        self.original = ops.serialize_document(self.metadata, self.body)
        (self.source / "old--45ae8a62.md").write_bytes(self.original)

    def test_explicit_short_topic_filename_preserves_managed_metadata_and_body(self):
        result = ops.prepare_import(self.source_scope, "old--45ae8a62.md",
                                    self.target_scope, "toss-technical-writing.md")

        self.assertEqual(result.status, "prepared")
        self.assertEqual(result.target_path, "toss-technical-writing.md")
        saved = (self.target / result.target_path).read_bytes()
        saved_metadata, saved_body = ops.parse_document(saved)
        self.assertEqual(saved_metadata, self.metadata)
        self.assertEqual(saved_metadata["batang_id"], "stable-managed-id")
        self.assertEqual(saved_body, self.body)
        self.assertEqual(saved, self.original)
        self.assertFalse((self.target / "toss-technical-writing-45ae8a62.md").exists())
        self.assertEqual((self.source / "old--45ae8a62.md").read_bytes(), self.original)

    def test_conflicting_target_bytes_survive_and_explicit_topic_supplement_succeeds(self):
        collision = "사용자 소유 파일\r\n".encode()
        (self.target / "toss-technical-writing.md").write_bytes(collision)
        with self.assertRaisesRegex(ops.ConflictError, "import_target_collision"):
            ops.prepare_import(self.source_scope, "old--45ae8a62.md",
                               self.target_scope, "toss-technical-writing.md")
        self.assertEqual((self.target / "toss-technical-writing.md").read_bytes(), collision)

        result = ops.prepare_import(self.source_scope, "old--45ae8a62.md",
                                    self.target_scope, "toss-technical-writing-korean.md",
                                    subject="토스 한국어 기술 글쓰기")
        self.assertEqual(result.status, "prepared")
        self.assertEqual(result.target_path, "toss-technical-writing-korean.md")
        saved_metadata, saved_body = ops.parse_document(
            (self.target / result.target_path).read_bytes())
        self.assertEqual(saved_metadata["batang_id"], "stable-managed-id")
        self.assertEqual(saved_body, self.body)
        self.assertEqual((self.target / "toss-technical-writing.md").read_bytes(), collision)


if __name__ == "__main__":
    unittest.main()
