"""일반 속성 보존과 source URI의 데이터 경계를 검증한다. 앱 실행 시험은 별도다."""
import copy
import json
import math
import unittest
import uuid

from test_file_ops import metadata, ops


ROOT_ID = "14097dc0-f75f-4a61-9927-74f3225fb6c1"


class DataCompatibility(unittest.TestCase):
    def test_obsidian_style_block_source_and_additional_properties_roundtrip(self):
        original = ("---\n# keep on no-op\nbatang_schema_version: 2\n"
            "batang_id: managed-example\nsubject: 합성 주제\ncontent_kind: note\n"
            "tags:\n  - 작업\n  - example\naliases:\n  - A:B\n"
            "sources:\n  - id: original-id\n    path: batang-source://" + ROOT_ID + "/notes/topic.md\n"
            "    origin: user\n    sha256: \"" + "1" * 64 + "\"\n    raw_path: null\n"
            "legacy_refs:\n  - path: legacy/a.md\n    sha256: \"" + "2" * 64 + "\"\n"
            "title: 점검 일정\ncreated: 2026-10-29\n날짜 시간: 2026-10-29T09:30:00+09:00\n"
            "checked: true\ncount: 3\nratio: 1.25\nempty: null\n"
            "related: [a, b, 'C:D']\n---\n\r\n본문\r\n").encode()
        value, body = ops.parse_document(original)
        self.assertEqual(value["sources"][0]["raw_path"], None)
        self.assertEqual(value["aliases"], ["A:B"])
        self.assertEqual(value["created"], "2026-10-29")
        self.assertEqual(value["related"], ["a", "b", "C:D"])
        self.assertEqual(ops.serialize_document(value, body, original=original), original)
        changed = copy.deepcopy(value)
        changed["tags"].append("updated")
        actual, actual_body = ops.parse_document(ops.serialize_document(changed, body, original=original))
        self.assertEqual(actual, changed)
        self.assertEqual(actual_body, body)
        self.assertEqual(actual["sources"], value["sources"])

    def test_json_frontmatter_and_indentless_yaml_lists(self):
        value = metadata()
        value["custom"] = ["yes", False, None, 4]
        original = ("---\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n---\nbody").encode()
        self.assertEqual(ops.parse_document(original), (value, b"body"))
        encoded = ops.serialize_document(value, b"body").replace(
            b'tags: ["' + "한글".encode() + b'","' + "조건".encode() + b'"]',
            'tags:\n- 한글\n- 조건'.encode())
        self.assertEqual(ops.parse_document(encoded)[0], value)

    def test_extra_property_constructor_preserves_values_and_reserved_fields(self):
        extra = {"Created At": "2026-10-29", "작성 제목": "Hello", "flags": [True, None, 4.5]}
        value = ops.new_metadata("주제", "note", [], properties=extra)
        extra["flags"].append("later")
        self.assertEqual(value["flags"], [True, None, 4.5])
        self.assertEqual(ops.parse_document(ops.serialize_document(value, b"body"))[0], value)
        for props in ({"subject": "replace"}, {"batang_unknown": "reserved"}, {"nested": {"a": "b"}}):
            with self.assertRaises(ops.FileError):
                ops.new_metadata("주제", "note", [], properties=props)

    def test_unsupported_yaml_preserves_specific_error_key_and_line(self):
        for header in ("title: &anchor value", "title: *alias", "title: !!str text", "title: |\n  value"):
            with self.subTest(header=header), self.assertRaises(ops.FileError) as caught:
                ops._load_metadata(header.encode())
            self.assertEqual(caught.exception.key, "title")
            self.assertEqual(caught.exception.line, 1)
        with self.assertRaises(ops.FileError) as duplicate:
            ops._load_metadata(b"title: first\ntitle: second\n")
        self.assertEqual(duplicate.exception.code, "frontmatter_duplicate")
        self.assertEqual(duplicate.exception.line, 2)

    def test_nonfinite_and_nested_extra_properties_cannot_be_serialized(self):
        for item in (math.nan, math.inf, [math.inf], {"nested": "value"}, [["nested"]]):
            value = metadata()
            value["extra"] = item
            with self.subTest(item=item), self.assertRaises(ops.FileError):
                ops.serialize_document(value, b"body")

    def test_uri_roundtrip_does_not_include_local_root(self):
        uri = ops.source_uri(ROOT_ID, "자료/공백 노트 %.md")
        root, path = ops.resolve_source_uri(uri, {ROOT_ID: "/synthetic/root"})
        self.assertEqual((root, path), ("/synthetic/root", "자료/공백 노트 %.md"))
        self.assertNotIn("/synthetic/root", uri)
        self.assertEqual(ops.resolve_source_uri(ops.source_uri(ROOT_ID, "a%2fb.md"),
                         {ROOT_ID: "/synthetic/root"})[1], "a%2fb.md")

    def test_uri_mapping_and_encoded_path_bypasses_rejected(self):
        for tail in ("../x.md", ".%2e/x.md", "a%2fb.md", "a%5Cb.md", "a%00b.md",
                     "a//b.md", "a.md?query=1", "a.md#part", "%FF.md", "%61.md"):
            with self.subTest(tail=tail), self.assertRaises(ops.FileError):
                ops.resolve_source_uri("batang-source://" + ROOT_ID + "/" + tail,
                                       {ROOT_ID: "/synthetic/root"})
        for host in (ROOT_ID + ":80", "user@" + ROOT_ID, "not-a-root-id"):
            with self.assertRaises(ops.FileError):
                ops.resolve_source_uri("batang-source://" + host + "/a.md", {})
        with self.assertRaisesRegex(ops.FileError, "source_root_unmapped"):
            ops.resolve_source_uri(ops.source_uri(ROOT_ID, "a.md"), {})


if __name__ == "__main__":
    unittest.main()
