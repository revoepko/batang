"""보기 예제의 의미 구조와 점진적 선택 UI 계약을 검사한다.

HTMLParser는 no-JS 원문의 콘텐츠·접근성 연결·자원 경계를 검사한다.
Node VM의 작은 DOM 대역은 실제 inline script의 선택 상태와 DOM 보존을 검사한다.
렌더링·브라우저 기본 키보드 동작·viewport·접근성 트리는 별도 브라우저 검증 대상이다.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
PANEL = PACKAGE / "skills/batang/components/supul/bogi/assets/explanation-panel.html"
EXAMPLES = ("structure", "process", "branch", "comparison")
VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
IDREF_ATTRIBUTES = {"aria-controls", "aria-describedby", "aria-labelledby", "for", "headers"}
EXTERNAL = re.compile(r"^(?:https?:|//|data:|blob:|javascript:|vbscript:|\\\\)", re.I)


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None]
    children: list[Element] = field(default_factory=list)
    parts: list[str | Element] = field(default_factory=list)

    def text_content(self) -> str:
        return "".join(part if isinstance(part, str) else part.text_content() for part in self.parts)

    def descendants(self, tag: str | None = None) -> list[Element]:
        return [node for child in self.children for node in [child, *child.descendants()] if tag is None or node.tag == tag]


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("#document", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Element(tag, dict(attrs))
        self.stack[-1].children.append(node)
        self.stack[-1].parts.append(node)
        if tag not in VOID_ELEMENTS:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self.stack[-1].parts.append(data)


def parse(markup: str) -> Element:
    parser = DocumentParser()
    parser.feed(markup)
    parser.close()
    return parser.root


def static_errors(root: Element) -> list[str]:
    nodes = root.descendants()
    ids = Counter(node.attrs["id"] for node in nodes if node.attrs.get("id"))
    errors = [f"duplicate id: {key}" for key, count in ids.items() if count != 1]
    for node in nodes:
        for name, value in node.attrs.items():
            if name.startswith("on"):
                errors.append("inline event handler")
            if name in IDREF_ATTRIBUTES:
                errors.extend(f"missing id: {ref}" for ref in (value or "").split() if ref not in ids)
            if name == "href" and value and value.startswith("#") and value[1:] not in ids:
                errors.append("missing fragment")
            if name in {"src", "href", "action", "formaction", "poster", "data"} and value and EXTERNAL.search(value):
                errors.append("external resource")
        if node.tag in {"iframe", "object", "embed", "form", "link"}:
            errors.append("external or submission surface")
        if node.tag == "script" and node.attrs.get("src"):
            errors.append("script subresource")
        if node.tag == "style" and re.search(r"@import\b|url\s*\(", node.text_content(), re.I):
            errors.append("CSS subresource")
    return errors


# DOM 대역은 script가 사용하는 표면만 제공한다. 외부 호출·타이머·스크롤·DOM 추가는
# 제공하지 않으므로 그런 동작이 도입되면 아래 실행 검사가 실패한다.
DOM_HARNESS = r"""
const vm = require('node:vm');
const assert = require('node:assert/strict');
const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
function run(entries, initialHash = '', valid = true) {
  const articles = entries.map(([key, id, title]) => ({
    id, dataset: { example: key }, hidden: false,
    querySelector: selector => { assert.equal(selector, 'h2'); return { textContent: title }; }
  }));
  function button(attrs, dataset = {}) {
    return {
      dataset, attrs, handlers: {}, getAttribute(name) { return this.attrs[name]; },
      setAttribute(name, value) { this.attrs[name] = value; },
      addEventListener(name, handler) { this.handlers[name] = handler; }
    };
  }
  const buttons = entries.map(([key, id]) => button(
    { 'aria-controls': id, 'aria-pressed': 'false' }, { selectExample: key }));
  const allButton = button({ 'aria-controls': 'explanation-panel', 'aria-pressed': 'false' });
  const picker = {
    hidden: true,
    querySelector: selector => { assert.equal(selector, 'button[data-show-all]'); return allButton; },
    querySelectorAll: selector => { assert.equal(selector, 'button[data-select-example]'); return buttons; }
  };
  const classes = new Set();
  const panel = { querySelectorAll: () => articles, classList: {
    add: name => classes.add(name),
    toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); }
  } };
  const status = { textContent: '' };
  const document = {
    querySelector: selector => { assert.equal(selector, '.example-picker'); return picker; },
    getElementById: id => id === 'explanation-panel' ? panel : id === 'selection-status' ? status : articles.find(a => a.id === id)
  };
  const location = { pathname: '/example.html', search: '?sample=1', hash: initialHash };
  const historyEntries = [{ url: location.pathname + location.search + location.hash, state: { original: true } }];
  let historyIndex = 0;
  const handlers = {};
  function setLocation(url) {
    const parsed = new URL(url, 'https://local.test');
    location.pathname = parsed.pathname; location.search = parsed.search; location.hash = parsed.hash;
  }
  const history = {
    get state() { return historyEntries[historyIndex].state; },
    pushState(state, title, url) {
      assert.equal(title, '');
      historyEntries.splice(historyIndex + 1);
      historyEntries.push({ state, url }); historyIndex++;
      setLocation(url);
    },
    replaceState(state, title, url) {
      assert.equal(title, ''); historyEntries[historyIndex] = { state, url }; setLocation(url);
    }
  };
  const window = { location, history, addEventListener(name, handler) { handlers[name] = handler; } };
  function go(delta) {
    historyIndex += delta;
    assert.ok(historyIndex >= 0 && historyIndex < historyEntries.length);
    setLocation(historyEntries[historyIndex].url); handlers.popstate();
  }
  const originalArticles = articles.slice();
  const originalButtons = buttons.slice();
  if (!valid) buttons[0].attrs['aria-controls'] = 'missing';
  vm.runInNewContext(input.script, { document, window }, { timeout: 1000 });
  function expectSelected(index) {
    assert.deepEqual(articles.filter(a => !a.hidden), [articles[index]]);
    assert.deepEqual(buttons.filter(b => b.attrs['aria-pressed'] === 'true'), [buttons[index]]);
    assert.equal(allButton.attrs['aria-pressed'], 'false');
    assert.equal(classes.has('show-all'), false);
    assert.deepEqual(articles, originalArticles);
    assert.deepEqual(buttons, originalButtons);
  }
  function expectAll() {
    assert.deepEqual(articles.filter(a => !a.hidden), articles);
    assert.equal(buttons.filter(b => b.attrs['aria-pressed'] === 'true').length, 0);
    assert.equal(allButton.attrs['aria-pressed'], 'true');
    assert.equal(classes.has('show-all'), true);
  }
  if (!valid) {
    assert.equal(picker.hidden, true);
    assert.deepEqual(articles.filter(a => !a.hidden), articles);
    assert.equal(classes.size, 0); return;
  }
  assert.equal(picker.hidden, false);
  assert.ok(classes.has('enhanced'));
  if (initialHash === '#view=all') expectAll();
  else {
    const value = initialHash.replace(/^#(?:view=)?/, '');
    const index = entries.findIndex(entry => entry[1] === value);
    expectSelected(index < 0 ? 0 : index);
    if (index >= 0) assert.equal(location.hash, '#view=' + encodeURIComponent(entries[index][1]));
  }
  assert.equal(historyEntries.length, 1);
  assert.equal(status.textContent, '');
  if (initialHash) return;
  for (let round = 0; round < 4; round++) {
    buttons.forEach((item, index) => {
      item.handlers.click(); expectSelected(index);
      assert.equal(location.hash, '#view=' + encodeURIComponent(entries[index][1]));
      const count = historyEntries.length;
      item.handlers.click(); expectSelected(index);
      assert.equal(historyEntries.length, count);
    });
    allButton.handlers.click(); expectAll();
    assert.equal(location.hash, '#view=all');
    assert.equal(status.textContent, '모든 예제를 표시합니다.');
    buttons[0].handlers.click(); expectSelected(0);
  }
  // 뒤로/앞으로는 표시 내용만 복원하며 DOM 추가·타이머·스크롤 API는 제공하지 않는다.
  buttons[1].handlers.click(); expectSelected(1);
  allButton.handlers.click(); expectAll();
  go(-1); expectSelected(1);
  go(-1); expectSelected(0);
  go(1); expectSelected(1);
  go(1); expectAll();
  location.hash = '#' + entries[0][1]; handlers.hashchange(); expectSelected(0);
  assert.equal(location.hash, '#view=' + encodeURIComponent(entries[0][1]));
  location.hash = '#%E0%A4%A'; handlers.hashchange(); expectSelected(0);
  location.hash = '#missing'; handlers.hashchange(); expectSelected(0);
  location.hash = ''; handlers.hashchange(); expectSelected(0);
}
run(input.entries);
run(input.entries, '#' + input.entries[1][1]);
run(input.entries, '#view=' + input.entries[2][1]);
run(input.entries, '#view=all');
run(input.entries, '#missing');
run(input.entries, '#%E0%A4%A');
run(input.entries, '', false);
// 같은 script가 다른 주제·사례 수와 임의 id에서도 작동해야 한다.
run([['water', 'water-panel', '물의 이동'], ['heat', 'heat-panel', '열의 이동']]);
"""


class BogiExamplePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.markup = PANEL.read_text(encoding="utf-8")
        cls.root = parse(cls.markup)
        cls.nodes = cls.root.descendants()
        cls.articles = {node.attrs["data-example"]: node for node in cls.nodes if node.tag == "article" and "data-example" in node.attrs}

    def test_no_js_contains_all_four_complete_examples(self) -> None:
        self.assertEqual(set(self.articles), set(EXAMPLES))
        for key, article in self.articles.items():
            with self.subTest(example=key):
                self.assertTrue(article.descendants("h2"))
                self.assertTrue(article.descendants("p"))
                self.assertGreaterEqual(len(article.descendants("section")), 3)
                for node in [article, *article.descendants()]:
                    self.assertNotIn("hidden", node.attrs)
                    self.assertNotIn("inert", node.attrs)
                    self.assertNotEqual(node.attrs.get("aria-hidden"), "true")
                # 조건과 예외는 접힌 상세가 아닌 본문으로 읽을 수 있어야 한다.
                self.assertFalse(article.descendants("details"))
                for section in article.descendants("section"):
                    self.assertTrue(section.descendants("h3"))
                    self.assertTrue(section.text_content().strip())
        styles = "\n".join(node.text_content() for node in self.nodes if node.tag == "style")
        # CSS may hide only an explicit hidden state, never the no-JS example content.
        for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", styles.split("@media print", 1)[0]):
            if re.search(r"display\s*:\s*none|visibility\s*:\s*hidden", declarations):
                self.assertEqual(selector.strip(), "[hidden]")

    def test_selectors_and_articles_share_one_panel_in_dom_order(self) -> None:
        main = next(node for node in self.nodes if node.tag == "main")
        picker = next(node for node in main.children if node.tag == "nav")
        panel = next(node for node in main.children if node.attrs.get("id") == "explanation-panel")
        self.assertIs(main.children[main.children.index(picker) + 1], panel)
        self.assertIn("hidden", picker.attrs)  # No inert controls when JavaScript is unavailable.
        self.assertEqual(panel.children, list(self.articles.values()))
        buttons = [node for node in picker.descendants("button") if "data-select-example" in node.attrs]
        all_buttons = [node for node in picker.descendants("button") if "data-show-all" in node.attrs]
        self.assertEqual(len(all_buttons), 1)
        self.assertEqual(all_buttons[0].attrs.get("aria-controls"), panel.attrs["id"])
        self.assertEqual(all_buttons[0].attrs.get("aria-pressed"), "false")
        self.assertEqual(all_buttons[0].attrs.get("type"), "button")
        self.assertEqual(len(buttons), 4)
        self.assertEqual({button.attrs.get("data-select-example") for button in buttons}, set(EXAMPLES))
        for button in buttons:
            article = self.articles[button.attrs["data-select-example"]]
            self.assertEqual(button.attrs.get("type"), "button")
            self.assertEqual(button.attrs.get("aria-controls"), article.attrs["id"])
            self.assertEqual(button.attrs.get("aria-pressed"), "false")
            self.assertTrue(button.text_content().strip())
            self.assertNotIn("tabindex", button.attrs)  # Native Tab/Enter/Space behavior.
        status = next(node for node in self.nodes if node.attrs.get("role") == "status")
        self.assertEqual(status.attrs.get("aria-live"), "polite")
        self.assertEqual(status.attrs.get("aria-atomic"), "true")

    def test_examples_keep_distinct_relationship_sequence_branch_and_comparison(self) -> None:
        structure = self.articles["structure"]
        self.assertEqual(len(structure.descendants("ul")), 1)
        self.assertEqual(len(structure.descendants("li")), 3)
        process = self.articles["process"]
        self.assertEqual(len(process.descendants("ol")), 1)
        self.assertEqual(len(process.descendants("li")), 4)
        branch = self.articles["branch"]
        self.assertEqual(len(branch.descendants("ul")), 1)
        self.assertEqual(len(branch.descendants("li")), 4)
        comparison = self.articles["comparison"]
        plans = next(node for node in comparison.descendants("div") if node.attrs.get("class") == "compare").children
        self.assertEqual(len(plans), 2)
        observed = []
        for plan in plans:
            quantities = [int(node.attrs["value"]) for node in plan.descendants("data")]
            self.assertEqual(len(quantities), 3)
            duration, frequency, total = quantities
            self.assertEqual(duration * frequency, total)
            self.assertTrue(all(str(node.attrs["value"]) in node.text_content() for node in plan.descendants("data")))
            observed.append(quantities)
        self.assertEqual(observed, [[25, 5, 125], [60, 2, 120]])
        # Important exceptions and effect limitations remain a separate visible paragraph/block.
        for article in self.articles.values():
            self.assertGreaterEqual(len(article.descendants("p")), 4)
        self.assertEqual(len([node for node in self.nodes if node.attrs.get("class") == "notice"]), 1)
        self.assertFalse([node for node in self.nodes if node.attrs.get("class") == "source"])

    def test_local_resource_and_accessibility_references_resolve(self) -> None:
        self.assertEqual(static_errors(self.root), [])
        self.assertEqual(len(self.root.descendants("script")), 1)
        broken = parse('<a href="#missing">x</a><button aria-controls="absent" onclick="x()">x</button><script src="https://example.test/x.js"></script>')
        errors = static_errors(broken)
        for expected in ("missing fragment", "missing id: absent", "inline event handler", "external resource", "script subresource"):
            self.assertIn(expected, errors)

    def test_print_exposes_all_content_and_omits_selection_controls(self) -> None:
        styles = "\n".join(node.text_content() for node in self.root.descendants("style"))
        print_styles = styles.split("@media print", 1)[1].split("@media", 1)[0]
        self.assertRegex(print_styles, r"#explanation-panel article\[hidden\]\s*\{\s*display:\s*block\s*!important")
        self.assertRegex(print_styles, r"\.example-picker[^{}]*\{\s*display:\s*none\s*!important")

    def test_no_motion_is_required_to_read_or_switch_content(self) -> None:
        styles = "\n".join(node.text_content() for node in self.root.descendants("style"))
        self.assertNotRegex(styles, r"@keyframes|(?:animation|transition)\s*:")
        self.assertIn("prefers-reduced-motion: reduce", styles)
        self.assertNotRegex(styles, r"scroll-behavior\s*:\s*smooth")

    @unittest.skipUnless(shutil.which("node"), "Node runtime is required for the inline-script DOM contract")
    def test_actual_script_replaces_selection_without_adding_nodes_or_scrolling(self) -> None:
        script = self.root.descendants("script")[0].text_content()
        entries = [[key, article.attrs["id"], article.descendants("h2")[0].text_content()] for key, article in self.articles.items()]
        result = subprocess.run([shutil.which("node"), "-e", DOM_HARNESS], input=json.dumps({"script": script, "entries": entries}), text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
