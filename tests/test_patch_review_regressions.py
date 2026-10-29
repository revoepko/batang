"""독립 검토에서 확인한 타입 변경·같은 문서 anchor·점 포함 위키링크 회귀."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_file_ops import metadata, ops


class ScalarTypeChanges(unittest.TestCase):
    def test_noop_checks_scalar_types_recursively(self):
        for before, after in ((1, True), (False, 0), (1, 1.0), ([1], [True]), ([False], [0.0])):
            with self.subTest(before=before, after=after):
                value = metadata()
                value["custom"] = before
                original = ops.serialize_document(value, b"body")
                changed = copy.deepcopy(value)
                changed["custom"] = after
                encoded = ops.serialize_document(changed, b"body", original=original)
                actual, body = ops.parse_document(encoded)
                self.assertNotEqual(encoded, original)
                if isinstance(after, list):
                    self.assertIs(type(actual["custom"][0]), type(after[0]))
                else:
                    self.assertIs(type(actual["custom"]), type(after))
                self.assertEqual(actual["custom"], after)
                self.assertEqual(body, b"body")
                self.assertEqual(ops.serialize_document(actual, body, original=encoded), encoded)

    def test_heading_hierarchy_and_code_comment_anchors_are_checked(self):
        body = (b"# A\n## ChildA\n### GrandA\n# B\n## ChildB\n"
                b"```md\n# Missing\nexample ^missing\n```\n"
                b"<!--\n# Comment\nexample ^comment\n-->\n"
                b"    # Indented\n    example ^indented\n"
                b"<pre>\n# Pre\nexample ^pre\n</pre>\n"
                b"actual block ^real\n# C#\n")
        snapshot = ops.Snapshot(ops.serialize_document(metadata(), body), "unused", 0o600)
        cases = {"#A": True, "#A#ChildA": True, "#A#GrandA": True,
                 "#A#ChildA#GrandA": True, "#B#ChildB": True, "#C%23": True,
                 "#A#ChildB": False, "#B#ChildA": False, "#A#ChildA#ChildB": False,
                 "#Missing": False, "#^missing": False, "#Comment": False, "#^comment": False,
                 "#Indented": False, "#^indented": False, "#Pre": False, "#^pre": False,
                 "#^real": True}
        for anchor, expected in cases.items():
            with self.subTest(anchor=anchor):
                self.assertIs(ops._anchor_present(snapshot, anchor), expected)

    def test_unsupported_heading_formats_are_unverified_instead_of_confirmed(self):
        for body, anchor in ((b"# **Bold**\n", "#Bold"),
                             (b"# A\nB\n===\n## Child\n", "#A#Child"),
                             (b"<div>\n# Html\n</div>\n", "#Html")):
            with self.subTest(body=body):
                snapshot = ops.Snapshot(ops.serialize_document(metadata(), body), "unused", 0o600)
                self.assertIsNone(ops._anchor_present(snapshot, anchor))

    def test_markdown_mask_preserves_normal_text_after_code_and_comment_fences(self):
        content = ("<!--\n```\n# Comment\n-->\n# Actual\n"
                   "````md\n# Code\n``` not a closing fence\n# Still code\n````\n# After\n"
                   "`<!-- literal -->`\n# Last\n")
        masked = ops._link_data.markdown_content(content)
        self.assertEqual(len(masked), len(content))
        self.assertIn("# Actual", masked)
        self.assertIn("# After", masked)
        self.assertIn("# Last", masked)
        for absent in ("# Comment", "# Code", "# Still code"):
            self.assertNotIn(absent, masked)

    def test_indented_container_and_paragraph_links_are_not_silently_dropped(self):
        for body in (b"- item\n    [[topic]]\n", b"paragraph\n    [[topic]]\n",
                     b"> quote\n    [[topic]]\n", b"> [[topic]]\n"):
            with self.subTest(body=body):
                refs = ops._link_data.inventory(body, "source.md", ["source.md", "topic.md"])
                self.assertEqual(len(refs), 1)
                self.assertEqual(refs[0]["status"], "unverified")
                self.assertEqual(refs[0]["uncertainty"], "markdown_container_or_continuation")
        for body in (b"    [[topic]]\n", b"paragraph\n\n    [[topic]]\n",
                     b"```md\n- item\n    [[topic]]\n```\n", b"- item\n    `[[topic]]`\n"):
            with self.subTest(code=body):
                self.assertEqual(ops._link_data.inventory(body, "source.md", ["topic.md"]), ())

    def test_escaped_opening_bracket_parity_and_escaped_bang(self):
        for backslashes in range(5):
            prefix = b"\\" * backslashes
            body = prefix + b"[example](topic.md)"
            refs = ops._link_data.inventory(body, "one.md", ["topic.md"])
            with self.subTest(backslashes=backslashes):
                self.assertEqual(len(refs), 0 if backslashes % 2 else 1)
                rewritten, _ = ops._link_data.rewrite(body, refs, "one.md", {"topic.md": "renamed.md"})
                self.assertEqual(rewritten, body if backslashes % 2 else prefix + b"[example](renamed.md)")
        for body, selected in ((br"\![alt](topic.md)", True),
                               (br"!\[alt](topic.md)", False),
                               (br"\\![alt](topic.md)", True),
                               (br"!\\[alt](topic.md)", True),
                               (br"`[example](topic.md)`", False)):
            refs = ops._link_data.inventory(body, "one.md", ["topic.md"])
            with self.subTest(body=body):
                self.assertEqual(bool(refs), selected)
                rewritten, _ = ops._link_data.rewrite(body, refs, "one.md", {"topic.md": "renamed.md"})
                self.assertEqual(rewritten, body.replace(b"topic.md", b"renamed.md") if selected else body)

    def test_escaped_wiki_is_preserved_as_unverified_and_escaped_label_closing_is_literal(self):
        for backslashes in range(1, 5):
            body = b"\\" * backslashes + b"[[topic]]"
            refs = ops._link_data.inventory(body, "one.md", ["topic.md"])
            with self.subTest(backslashes=backslashes):
                self.assertEqual(len(refs), 1)
                self.assertEqual(refs[0]["status"], "unverified" if backslashes % 2 else "selected")
                rewritten, _ = ops._link_data.rewrite(body, refs, "one.md", {"topic.md": "renamed.md"})
                self.assertEqual(rewritten, body if backslashes % 2 else body.replace(b"topic", b"renamed"))
        literal = br"[label\](topic.md)"
        self.assertEqual(ops._link_data.inventory(literal, "one.md", ["topic.md"]), ())
        real = br"[label\]](topic.md)"
        refs = ops._link_data.inventory(real, "one.md", ["topic.md"])
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["status"], "selected")

    def test_escape_precedes_inline_code_and_comment_opening_masks(self):
        for body in (br"\`[example](topic.md)\`", br"\<!--[example](topic.md)-->"):
            with self.subTest(body=body):
                refs = ops._link_data.inventory(body, "one.md", ["topic.md"])
                self.assertEqual(len(refs), 1)
                self.assertEqual(refs[0]["status"], "selected")
        mixed = br"\` literal `[code](topic.md)` and [real](topic.md)"
        refs = ops._link_data.inventory(mixed, "one.md", ["topic.md"])
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["start"], mixed.rfind(b"topic.md"))
        for body in (b"`[example](topic.md)`", b"<!-- [example](topic.md) -->"):
            self.assertEqual(ops._link_data.inventory(body, "one.md", ["topic.md"]), ())


@unittest.skipUnless(os.sys.platform == "darwin", "macOS 파일 게시 계약")
class LinkReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.target = self.root / "target"
        self.stage = self.root / "stage"
        for path in (self.source, self.target, self.stage):
            path.mkdir(mode=0o700)
        (self.source / "notes").mkdir()

    def test_same_document_missing_heading_and_block_are_not_complete(self):
        source = (b"# Heading\nbody ^exists\n\n"
                  b"[[#Heading]] [[#^exists]] [[#Missing]] [[#^missing]]\n")
        (self.source / "one.md").write_bytes(source)
        src = ops.FileScope(self.source, ["one.md"], staging_root=self.stage)
        dst = ops.FileScope(self.target, ["one.md"], staging_root=self.stage)
        result = ops.prepare_import_batch(src, ["one.md"], dst, {"one.md": "one.md"})
        self.assertEqual([ref["status"] for ref in result["references"]],
                         ["same_document", "same_document", "broken_anchor", "broken_anchor"])
        self.assertFalse(result["references_complete"])
        self.assertEqual(src.read("one.md").data, source)

    def test_dotted_wiki_name_resolves_md_and_keeps_exact_attachment_and_ambiguity(self):
        source = b"[[notes/topic.v1]] [[asset.png]]"
        (self.source / "one.md").write_bytes(source)
        (self.source / "notes/topic.v1.md").write_bytes(b"# V1")
        (self.source / "asset.png").write_bytes(b"image")
        src = ops.FileScope(self.source, ["one.md", "notes/topic.v1.md", "notes/topic.v1", "asset.png"], staging_root=self.stage)
        references = ops.inspect_import_links(source, src, "one.md", ["notes/topic.v1.md", "asset.png"])
        self.assertEqual([ref["status"] for ref in references], ["selected", "selected"])
        self.assertEqual(references[0]["source_path"], "notes/topic.v1.md")
        (self.source / "notes/topic.v1").write_bytes(b"literal other file")
        ambiguous = ops.inspect_import_links(source, src, "one.md", ["notes/topic.v1.md", "notes/topic.v1", "asset.png"])
        self.assertEqual(ambiguous[0]["status"], "ambiguous")
        self.assertEqual(ambiguous[1]["status"], "selected")
        dst = ops.FileScope(self.target, ["one.md", "renamed.v2.md"], staging_root=self.stage)
        batch = ops.prepare_import_batch(src, ["one.md", "notes/topic.v1.md"], dst,
                   {"one.md": "one.md", "notes/topic.v1.md": "renamed.v2.md"})
        self.assertEqual(batch["references"][0]["status"], "verified")
        self.assertIn(b"[[renamed.v2]]", ops.parse_document(dst.read("one.md").data)[1])

    def test_missing_unreferenced_attachment_and_note_make_batch_incomplete(self):
        for attachment in (True, False):
            with self.subTest(attachment=attachment):
                source_path = "asset.bin" if attachment else "one.md"
                target_path = "asset-copy.bin" if attachment else "copy.md"
                data = b"binary\x00\xff" if attachment else b"# Plain note without links"
                (self.source / source_path).write_bytes(data)
                src = ops.FileScope(self.source, [source_path], staging_root=self.stage)
                dst = ops.FileScope(self.target, [target_path], staging_root=self.stage)
                verify = ops.verify_import_destinations

                def removed_before_recheck(results, scope, **kwargs):
                    (self.target / target_path).unlink()
                    return verify(results, scope, **kwargs)

                with patch.object(ops, "verify_import_destinations", side_effect=removed_before_recheck):
                    batch = ops.prepare_import_batch(src, [source_path], dst, {source_path: target_path},
                                attachment_paths=[source_path] if attachment else [])
                self.assertEqual(len(batch["entries"]), batch["selected_count"])
                self.assertEqual(batch["entries"][0]["status"], "failed")
                self.assertEqual(batch["entries"][0]["copy_validation_status"], "missing")
                self.assertEqual(batch["prepared_count"], 0)
                self.assertFalse(batch["copies_complete"])
                self.assertFalse(batch["references_complete"])
                self.assertEqual(batch["references"][0]["status"], "missing")
                self.assertEqual((self.source / source_path).read_bytes(), data)

    def test_changed_unreferenced_attachment_is_not_claimed_complete(self):
        (self.source / "asset.bin").write_bytes(b"original bytes")
        src = ops.FileScope(self.source, ["asset.bin"], staging_root=self.stage)
        dst = ops.FileScope(self.target, ["asset-copy.bin"], staging_root=self.stage)
        verify = ops.verify_import_destinations

        def changed_before_recheck(results, scope, **kwargs):
            (self.target / "asset-copy.bin").write_bytes(b"external change")
            return verify(results, scope, **kwargs)

        with patch.object(ops, "verify_import_destinations", side_effect=changed_before_recheck):
            batch = ops.prepare_import_batch(src, ["asset.bin"], dst, {"asset.bin": "asset-copy.bin"},
                                             attachment_paths=["asset.bin"])
        self.assertFalse(batch["copies_complete"])
        self.assertFalse(batch["references_complete"])
        self.assertEqual(batch["entries"][0]["copy_validation_status"], "changed")
        self.assertEqual(batch["reference_check_error"], "import_destination_changed")

    def test_uncertain_indented_list_link_prevents_complete_migration(self):
        original = b"- item\n    [[topic]]\n"
        (self.source / "one.md").write_bytes(original)
        (self.source / "topic.md").write_bytes(b"# Topic")
        src = ops.FileScope(self.source, ["one.md", "topic.md"], staging_root=self.stage)
        dst = ops.FileScope(self.target, ["one.md", "renamed.md"], staging_root=self.stage)
        batch = ops.prepare_import_batch(src, ["one.md", "topic.md"], dst,
                                         {"one.md": "one.md", "topic.md": "renamed.md"})
        self.assertTrue(batch["copies_complete"])
        self.assertFalse(batch["references_complete"])
        self.assertEqual(len(batch["references"]), 1)
        self.assertEqual(batch["references"][0]["status"], "unverified")
        self.assertEqual(ops.parse_document(dst.read("one.md").data)[1], original)
        self.assertEqual(src.read("one.md").data, original)

    def test_escaped_wiki_stays_unverified_and_markdown_literal_is_not_rewritten(self):
        original = br"\[[topic]] and \[example](topic.md)"
        (self.source / "one.md").write_bytes(original)
        (self.source / "topic.md").write_bytes(b"# Topic")
        src = ops.FileScope(self.source, ["one.md", "topic.md"], staging_root=self.stage)
        dst = ops.FileScope(self.target, ["one.md", "renamed.md"], staging_root=self.stage)
        batch = ops.prepare_import_batch(src, ["one.md", "topic.md"], dst,
                                         {"one.md": "one.md", "topic.md": "renamed.md"})
        self.assertTrue(batch["copies_complete"])
        self.assertFalse(batch["references_complete"])
        self.assertEqual(len(batch["references"]), 1)
        self.assertEqual(batch["references"][0]["status"], "unverified")
        self.assertEqual(ops.parse_document(dst.read("one.md").data)[1], original)
        self.assertEqual(src.read("one.md").data, original)


if __name__ == "__main__":
    unittest.main()
