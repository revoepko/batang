"""허용된 합성 문서만으로 일반 링크의 명시 참조 신호를 검증한다."""
from pathlib import Path
import sys
import unicodedata
import unittest
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_graph_ops import GraphFixture, note
import file_ops as files
import relationship_ops as r


class ScopedLinkCandidates(GraphFixture):
    def prepare(self, documents):
        self.paths = tuple(path for path, _, _, _ in documents)
        for path, identifier, subject, body in documents:
            target = self.vault / path
            target.parent.mkdir(parents=True, exist_ok=True)
            metadata, _ = files.parse_document(note(identifier, subject=subject))
            target.write_bytes(files.serialize_document(metadata, body.encode()))
        (self.vault / "ACTIVE.md").write_text("".join(
            f"- [선택]({quote(path, safe='/')})\n" for path in self.paths))
        self.note_scope = files.FileScope(str(self.vault), ["ACTIVE.md", *self.paths])

    def reference_ids(self, source="origin", selected=None):
        active = self.active(selected)
        source_path = next(doc.path for doc in active.documents if doc.document_id == source)
        plan = r.discover_candidates(self.active([source_path]), active)
        self.assertEqual(plan["status"], "complete")
        return {item["target_document_id"] if item["source_document_id"] == source
                else item["source_document_id"] for item in plan["candidates"]
                if "explicit_reference" in item["signals"]}

    def test_relative_markdown_extension_encoding_and_anchor(self):
        for link in ("[근거](../자료/사용자%20운영.md#서비스)",
                     "[근거](../자료/사용자%20운영#서비스)",
                     "[근거](<../자료/사용자 운영.md#서비스> \"제목\")"):
            with self.subTest(link=link):
                self.prepare([("질문/시작.md", "origin", "시작", link),
                              ("자료/사용자 운영.md", "destination", "운영", "고유 근거")])
                self.assertEqual(self.reference_ids(), {"destination"})

    def test_wiki_root_path_and_unique_filename_are_supported(self):
        for link in ("[[자료/운영.md#절|표시]]", "[[운영#절]]", "[[운영.md]]"):
            with self.subTest(link=link):
                self.prepare([("질문/시작.md", "origin", "시작", link),
                              ("자료/운영.md", "destination", "다른 제목", "고유 근거")])
                self.assertEqual(self.reference_ids(), {"destination"})

    def test_unicode_nfc_and_parenthesized_filename(self):
        decomposed = unicodedata.normalize("NFD", "근거(한국어).md")
        for link in ("[근거](근거(한국어).md#절)", "[근거](근거\\(한국어\\).md)"):
            with self.subTest(link=link):
                self.prepare([("시작.md", "origin", "시작", link),
                              (decomposed, "destination", "자료", "고유 근거")])
                self.assertEqual(self.reference_ids(), {"destination"})

    def test_decomposed_source_directory_resolves_relative_link_with_same_nfc_key(self):
        source = unicodedata.normalize('NFD', '자료/시작.md')
        self.prepare([(source, 'origin', '시작', '[대상](대상.md#절)'),
                      ('자료/대상.md', 'destination', '근거', '고유 근거')])
        self.assertEqual(self.reference_ids(), {'destination'})

    def test_literal_uuid_accepts_korean_particles_without_ascii_substring_matches(self):
        identifier = '80000000-0000-4000-8000-000000000002'
        for body, expected in ((f'{identifier}의 정책을 따른다.', {identifier}),
                               (f'{identifier}를 확인한다.', {identifier}),
                               (f'({identifier})', {identifier}),
                               (f'x{identifier}', set()), (f'{identifier}f', set()),
                               (f'{identifier}-suffix', set()), (f'{identifier}_suffix', set())):
            with self.subTest(body=body):
                self.prepare([('시작.md', 'origin', '시작', body),
                              ('대상.md', identifier, '근거', '고유 근거')])
                self.assertEqual(self.reference_ids(), expected)

    def test_duplicate_filename_alias_and_title_are_not_arbitrarily_selected(self):
        self.prepare([("질문/시작.md", "origin", "시작", "[[동명.md]] [[공통 제목]]"),
                      ("가/동명.md", "first", "공통 제목", "첫 근거"),
                      ("나/동명.md", "second", "공통 제목", "둘째 근거")])
        self.assertEqual(self.reference_ids(), set())

    def test_explicit_relative_path_disambiguates_duplicate_filename(self):
        self.prepare([("질문/시작.md", "origin", "시작", "[대상](../나/동명.md)"),
                      ("가/동명.md", "first", "공통 제목", "첫 근거"),
                      ("나/동명.md", "second", "공통 제목", "둘째 근거")])
        self.assertEqual(self.reference_ids(), {"second"})

    def test_scope_escape_absolute_uri_and_invalid_encoding_do_not_resolve(self):
        for link in ("[외부](../../대상.md)", "[외부](/대상.md)",
                     "[외부](https://example.invalid/대상.md)", "[외부](file:대상.md)",
                     "[외부](%FF.md)", "[외부](%2E%2E/%2E%2E/대상.md)",
                     "[외부](대상.md?query=1)"):
            with self.subTest(link=link):
                self.prepare([("시작.md", "origin", "시작", link),
                              ("대상.md", "destination", "근거", "고유 근거")])
                self.assertEqual(self.reference_ids(), set())

    def test_missing_relative_markdown_does_not_fall_back_to_other_folder(self):
        self.prepare([("질문/시작.md", "origin", "시작", "[대상](대상.md)"),
                      ("다른/대상.md", "destination", "근거", "고유 근거")])
        self.assertEqual(self.reference_ids(), set())

    def test_incomplete_links_do_not_create_explicit_reference_signal(self):
        for link in ("[[대상", "[근거](대상.md", "[근거](<대상.md>", "[근거](대상.md title)"):
            with self.subTest(link=link):
                self.prepare([("시작.md", "origin", "시작", link),
                              ("대상.md", "destination", "근거", "고유 근거")])
                self.assertEqual(self.reference_ids(), set())

    def test_unselected_targets_are_not_read_or_reported(self):
        self.prepare([("시작.md", "origin", "시작", "[숨김](비허용.md) [[비허용]]"),
                      ("비허용.md", "hidden", "비허용", "고유 근거"),
                      ("허용.md", "visible", "허용", "다른 근거")])
        selected = ["시작.md", "허용.md"]
        self.note_scope = files.FileScope(str(self.vault), ["ACTIVE.md", *selected])
        self.assertEqual(self.reference_ids(selected=selected), set())

    def test_same_tag_remains_candidate_signal_without_assertion_or_id_mutation(self):
        self.prepare([("시작.md", "origin", "시작", "독립 규칙"),
                      ("근거.md", "destination", "자료", "별개 조건")])
        before = {path: (self.vault / path).read_bytes() for path in ("ACTIVE.md", *self.paths)}
        plan = r.discover_candidates(self.active())
        self.assertEqual(plan["candidates"][0]["signals"], ["metadata_terms"])
        self.assertNotIn("relations", plan)
        self.assertEqual(before, {path: (self.vault / path).read_bytes() for path in before})

    def test_wiki_colon_title_and_alias_are_not_misclassified_as_uri(self):
        for title in ('HTTP: 캐시', 'RFC:9110'):
            for field in ('subject', 'alias'):
                with self.subTest(title=title, field=field):
                    self.prepare([("시작.md", "origin", "시작", f"[[{title}]]"),
                                  ("자료.md", "destination", title if field == 'subject' else "다른 제목", "고유 근거")])
                    if field == 'alias':
                        target = self.vault / '자료.md'
                        metadata, body = files.parse_document(target.read_bytes())
                        metadata['aliases'] = [title]
                        target.write_bytes(files.serialize_document(metadata, body))
                    self.assertEqual(self.reference_ids(), {'destination'})

    def test_colon_title_does_not_allow_markdown_uri_or_ambiguous_wiki(self):
        for link, duplicate in (("[대상](HTTP:%20캐시)", False),
                                ("[[HTTP: 캐시]]", True),
                                ("[대상](RFC:9110)", False),
                                ("[[RFC:9110]]", True),
                                ("[[https://example.invalid/HTTP: 캐시]]", False)):
            with self.subTest(link=link, duplicate=duplicate):
                title = 'RFC:9110' if 'RFC:' in link else 'HTTP: 캐시'
                documents = [("시작.md", "origin", "시작", link),
                             ("자료.md", "destination", title, "고유 근거")]
                if duplicate:
                    documents.append(("중복.md", "other", title, "다른 근거"))
                self.prepare(documents)
                self.assertEqual(self.reference_ids(), set())


if __name__ == "__main__":
    unittest.main()
