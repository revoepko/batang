"""미지원 구문을 누락하거나 일부만 재작성하지 않는 링크 보존 행렬."""
import os
from pathlib import Path
import tempfile
import unittest

from test_file_ops import ops


class LinkPreservationMatrix(unittest.TestCase):
    selected = ["topic.md", "asset.png", "before.md", "after.md", "folder/topic(1).md"]
    mapping = {"topic.md": "renamed.md", "asset.png": "asset-copy.png",
               "before.md": "before-copy.md", "after.md": "after-copy.md",
               "folder/topic(1).md": "renamed-complex.md"}

    def inspect(self, body):
        return ops._link_data.inventory(body, "one.md", self.selected)

    def rewrite(self, body, refs):
        return ops._link_data.rewrite(body, refs, "one.md", self.mapping)[0]

    def test_nested_labels_images_destinations_and_title_angle_are_preserved(self):
        cases = [b"[outer [inner]](topic.md)", b"[![alt](asset.png)](topic.md)",
                 b"[outer [[topic]]](topic.md)", b"[label](folder/topic(1).md)",
                 b'[label](topic.md "title")', b"[label](<topic.md>)",
                 b"[first\nsecond](topic.md)"]
        for body in cases:
            with self.subTest(body=body):
                refs = self.inspect(body)
                self.assertTrue(refs)
                self.assertTrue(all(ref["status"] == "unverified" for ref in refs))
                self.assertEqual(self.rewrite(body, refs), body)

    def test_reference_definition_full_collapsed_shortcut_and_image_are_preserved(self):
        cases = [b"[text][id]\n[id]: topic.md\n", b"[id][]\n[id]: topic.md\n",
                 b"[ID]\n[id]: topic.md\n", b"![alt][id]\n[id]: asset.png\n",
                 b"[id]: <topic.md>\n", b"[id]: topic.md\n",
                 "[참고]\r\n[참고]: topic.md\r\n".encode()]
        for body in cases:
            with self.subTest(body=body):
                refs = self.inspect(body)
                self.assertTrue(refs)
                self.assertTrue(all(ref["status"] == "unverified" for ref in refs))
                self.assertEqual(self.rewrite(body, refs), body)

    def test_reference_continuation_title_cannot_be_partially_rewritten(self):
        for definition in (b'[id]: topic.md\n  "title [example](topic.md)"',
                           b'[id]: topic.md\n"title [example](topic.md)"',
                           b'[id]:\n  topic.md\n  "title [example](topic.md)"',
                           b'[id]: topic.md\n  "first line\nexample [example](topic.md)\nlast line"',
                           b'[id]: topic.md "first line\n[example](topic.md)\nlast line"'):
            body = b"[before](before.md)\n" + definition + b"\n[after](after.md)"
            with self.subTest(definition=definition):
                refs = self.inspect(body)
                self.assertEqual(sum(ref["status"] == "selected" for ref in refs), 2)
                self.assertEqual(self.rewrite(body, refs), b"[before](before-copy.md)\n" + definition + b"\n[after](after-copy.md)")

    def test_title_parentheses_and_angle_destination_do_not_end_protected_span_early(self):
        for inner in (b'[label](topic.md "title ) [example](topic.md)")',
                      b"[label](<folder/topic(1).md>)"):
            body = b"[before](before.md) " + inner + b" [after](after.md)"
            with self.subTest(inner=inner):
                refs = self.inspect(body)
                self.assertEqual(sum(ref["status"] == "selected" for ref in refs), 2)
                self.assertEqual(self.rewrite(body, refs), b"[before](before-copy.md) " + inner + b" [after](after-copy.md)")

    def test_unsupported_spans_do_not_consume_normal_links_before_and_after(self):
        cases = [b"[outer [inner]](topic.md)", b"[![alt](asset.png)](topic.md)",
                 b'[label](topic.md "title")', b"[label](<topic.md>)",
                 b"<code>[example](topic.md)</code>", b"<div>[example](topic.md)</div>"]
        for inner in cases:
            body = b"[before](before.md) " + inner + b" [after](after.md)"
            with self.subTest(inner=inner):
                refs = self.inspect(body)
                self.assertEqual(sum(ref["status"] == "selected" for ref in refs), 2)
                rewritten = self.rewrite(body, refs)
                self.assertEqual(rewritten, b"[before](before-copy.md) " + inner + b" [after](after-copy.md)")

    def test_raw_html_blocks_are_literal_and_do_not_mask_following_markdown(self):
        for tag in ("script", "style", "textarea", "pre", "ScRiPt"):
            literal = ("<" + tag + ">\n[example](topic.md) [[topic]]\n<!-- unclosed in raw text\n</" + tag + ">\n").encode()
            body = b"[before](before.md)\n" + literal + b"[after](after.md)"
            with self.subTest(tag=tag):
                refs = self.inspect(body)
                self.assertEqual(len(refs), 2)
                self.assertTrue(all(ref["status"] == "selected" for ref in refs))
                self.assertEqual(self.rewrite(body, refs), b"[before](before-copy.md)\n" + literal + b"[after](after-copy.md)")

    def test_comments_cdata_and_processing_instructions_are_literal_blocks(self):
        for literal in (b"<!-- [example](topic.md) [[topic]] -->\n",
                        b"<![CDATA[[example](topic.md) [[topic]]]]>\n",
                        b'<?instruction [example](topic.md) [[topic]] ?>\n'):
            body = literal + b"[after](after.md)"
            with self.subTest(literal=literal):
                refs = self.inspect(body)
                self.assertEqual(len(refs), 1)
                self.assertEqual(refs[0]["reference"], "after.md")
                self.assertEqual(self.rewrite(body, refs), literal + b"[after](after-copy.md)")

    def test_inline_and_ambiguous_html_remains_unverified(self):
        cases = [b"text <script>[example](topic.md)</script> text",
                 b"text <style>[example](topic.md)</style> text",
                 b"<code>[example](topic.md)</code>",
                 b"<div>[example](topic.md)<div>[[topic]]</div>[other](topic.md)</div>",
                 b"text <!-- [example](topic.md) --> text",
                 b"<https://example.invalid/topic>"]
        for body in cases:
            with self.subTest(body=body):
                refs = self.inspect(body)
                self.assertTrue(refs)
                self.assertTrue(all(ref["status"] == "unverified" for ref in refs))
                self.assertEqual(self.rewrite(body, refs), body)

    def test_opaque_regions_precede_link_and_reference_detection(self):
        for body in (b"```md\n[id]: topic.md\n[outer [inner]](topic.md)\n<script>\n```\n",
                     b"`<script>[example](topic.md)</script>`",
                     b"    [id]: topic.md\n    [id]\n"):
            with self.subTest(body=body):
                refs = self.inspect(body)
                self.assertEqual(refs, ())
                self.assertEqual(self.rewrite(body, refs), body)
        body = b"```md\n[id]: topic.md\n```\n[id]"
        self.assertEqual(self.inspect(body), ())

    def test_escape_parity_is_preserved_in_structural_scan(self):
        for count in range(5):
            prefix = b"\\" * count
            body = prefix + b"[plain](topic.md)"
            refs = self.inspect(body)
            with self.subTest(count=count):
                self.assertEqual(len(refs), 0 if count % 2 else 1)
                self.assertEqual(self.rewrite(body, refs), body if count % 2 else prefix + b"[plain](renamed.md)")

    def test_hangul_crlf_and_unsupported_span_bytes_are_preserved(self):
        inner = "[바깥 [안쪽]](topic.md)".encode()
        body = "[이전](before.md)\r\n".encode() + inner + "\r\n[다음](after.md)".encode()
        refs = self.inspect(body)
        self.assertEqual(self.rewrite(body, refs), "[이전](before-copy.md)\r\n".encode() + inner + "\r\n[다음](after-copy.md)".encode())

    def test_duplicate_or_forged_rewrite_spans_fail_before_any_change(self):
        body = b"[plain](topic.md)"
        refs = self.inspect(body)
        with self.assertRaisesRegex(ValueError, "link_overlapping_rewrite"):
            self.rewrite(body, refs + refs)
        forged = dict(refs[0], start=0)
        with self.assertRaisesRegex(ValueError, "link_reference_span"):
            self.rewrite(body, [forged])


@unittest.skipUnless(os.sys.platform == "darwin", "macOS 파일 게시 계약")
class PreservationBatch(unittest.TestCase):
    def test_unsupported_syntax_cannot_make_reference_completion_true(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            for name in ("source", "target", "stage"):
                (root / name).mkdir(mode=0o700)
            for index, body in enumerate((b"[outer [inner]](topic.md)",
                                          b"[![alt](asset.png)](topic.md)",
                                          b"[ref][id]\n[id]: topic.md",
                                          b"<code>[example](topic.md)</code>")):
                with self.subTest(body=body):
                    (root / "source/one.md").write_bytes(body)
                    (root / "source/topic.md").write_bytes(b"# Topic")
                    src = ops.FileScope(root / "source", ["one.md", "topic.md"], staging_root=root / "stage")
                    mapping = {"one.md": "one" + str(index) + ".md", "topic.md": "renamed" + str(index) + ".md"}
                    dst = ops.FileScope(root / "target", mapping.values(), staging_root=root / "stage")
                    batch = ops.prepare_import_batch(src, ["one.md", "topic.md"], dst, mapping)
                    self.assertTrue(batch["copies_complete"])
                    self.assertFalse(batch["references_complete"])
                    self.assertTrue(batch["references"])
                    self.assertEqual(ops.parse_document(dst.read(mapping["one.md"]).data)[1], body)
                    self.assertEqual(src.read("one.md").data, body)


if __name__ == "__main__":
    unittest.main()
