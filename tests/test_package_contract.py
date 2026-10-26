"""공개 package의 파일 allowlist, privacy, Markdown 상대 링크와 문서 경계를 검사한다.

이 검사는 실제 host의 설치·권한·vault 보존·Graphify/Archify 실행·link 전환이나
rollback을 증명하지 않는다.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


PACKAGE = Path(__file__).resolve().parents[1]
MADI = PACKAGE / "skills" / "batang" / "components" / "madi"
SKILLS = PACKAGE / "skills"
BATANG = SKILLS / "batang"
COMPONENTS = BATANG / "components"
INTERNAL_WORKFLOWS = {
    COMPONENTS / component / "workflow.md"
    for component in ("madi", "gadak", "naru", "dure", "supul")
} | {
    COMPONENTS / "supul" / component / "workflow.md"
    for component in ("galpi", "gori", "bogi")
}

MADI_PUBLIC_FILES = {
    "workflow.md",
    "assets/decision-record.md",
    "assets/project-profile.md",
    "assets/run-record.md",
    "assets/execution-plan.md",
    "references/clear-language.md",
    "references/document-workflow.md",
    "references/user-review-presentation.md",
    "references/workflow-contract.md",
    "references/synthetic-example.md",
    "references/diagram-workflow.md",
}
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
INLINE_CODE = re.compile(r"`[^`]*`")
PRIVATE_PATH = re.compile(
    "/" + "(?:Us" + "ers|ho" + "me)/|" + "iC" + "loud~",
    re.IGNORECASE,
)
DEVELOPMENT_DATE = re.compile(r"\b20\d{2}[-./]\d{2}[-./]\d{2}\b")
LOCAL_RELEASE_STATE = re.compile(
    r"로컬\s*공개\s*후보|이\s*후보에는|현재\s*후보|"
    r"GitHub\s*공개는\s*승인[·ㆍ]?실행되지|"
    r"GitHub\s*공개[·ㆍ]?원격\s*게시\s*승인",
    re.IGNORECASE,
)
PUBLIC_PROSE = {
    PACKAGE / "README.md",
    PACKAGE / "README.ko.md",
    PACKAGE / "AGENTS.md",
    PACKAGE / "THIRD_PARTY.md",
    PACKAGE / "examples" / "AGENTS.md",
    MADI / "workflow.md",
    *INTERNAL_WORKFLOWS,
}
RELEASE_WORKFLOW = MADI / "references" / "workflow-contract.md"


def _relative_files(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def _excluded_package_metadata(path: Path) -> bool:
    relative = path.relative_to(PACKAGE)
    return (
        (path.suffix == ".pyc" and "__pycache__" in relative.parts)
        or ".git" in relative.parts
    )


def _manifest_files() -> set[str]:
    files: set[str] = set()
    for line in (PACKAGE / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        if separator and re.fullmatch(r"[0-9a-f]{64}", digest):
            files.add(relative)
    return files


def _relative_markdown_links(path: Path) -> list[Path]:
    targets: list[Path] = []
    prose_lines: list[str] = []
    in_fence = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            prose_lines.append(line)
    prose = INLINE_CODE.sub("", "\n".join(prose_lines))
    for href in MARKDOWN_LINK.findall(prose):
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        targets.append((path.parent / unquote(parsed.path)).resolve())
    return targets


class PackageContractTests(unittest.TestCase):
    def test_madi_public_allowlist_is_exact(self) -> None:
        self.assertEqual(_relative_files(MADI), MADI_PUBLIC_FILES)

    def test_only_batang_skill_entrypoint_is_published(self) -> None:
        self.assertTrue((PACKAGE / "skills/batang/SKILL.md").is_file())
        self.assertFalse((PACKAGE / "skills/madi/SKILL.md").exists())

    def test_only_one_skill_entrypoint_is_published(self) -> None:
        self.assertEqual(set(SKILLS.rglob("SKILL.md")), {BATANG / "SKILL.md"})

    def test_internal_workflows_are_plain_markdown(self) -> None:
        self.assertEqual(set(BATANG.rglob("workflow.md")), INTERNAL_WORKFLOWS)
        for workflow in INTERNAL_WORKFLOWS:
            self.assertFalse(workflow.read_text(encoding="utf-8").startswith("---\n"), workflow)

    def test_component_workflows_are_reachable_from_batang_entrypoint(self) -> None:
        entrypoint = BATANG / "SKILL.md"
        visited: set[Path] = set()
        pending = [entrypoint.resolve()]
        while pending:
            source = pending.pop()
            if source in visited:
                continue
            visited.add(source)
            pending.extend(
                target for target in _relative_markdown_links(source)
                if target.is_file() and target.is_relative_to(BATANG.resolve())
            )

        self.assertTrue(INTERNAL_WORKFLOWS <= visited, INTERNAL_WORKFLOWS - visited)

    def test_deployable_files_match_checksum_allowlist(self) -> None:
        actual = {
            source.relative_to(PACKAGE).as_posix()
            for source in PACKAGE.rglob("*")
            if source.is_file() and not _excluded_package_metadata(source)
        }
        self.assertEqual(actual, _manifest_files() | {"SHA256SUMS"})


    def test_product_markdown_relative_links_resolve_inside_candidate_bundle(self) -> None:
        bundle = PACKAGE.resolve()

        for source in set(SKILLS.rglob("*.md")) | PUBLIC_PROSE:
            for target in _relative_markdown_links(source):
                self.assertTrue(target.is_file(), f"{source}: {target}")
                self.assertTrue(target.is_relative_to(bundle), f"{source}: {target}")

    def test_product_skills_contain_no_private_absolute_path_pattern(self) -> None:
        for source in SKILLS.rglob("*"):
            if source.is_file() and not _excluded_package_metadata(source):
                self.assertIsNone(PRIVATE_PATH.search(source.read_text(encoding="utf-8")), source)

    def test_public_bundle_contains_no_private_absolute_path_pattern(self) -> None:
        for source in PACKAGE.rglob("*"):
            if source.is_file() and not _excluded_package_metadata(source):
                self.assertIsNone(PRIVATE_PATH.search(source.read_text(encoding="utf-8")), source)

    def test_public_prose_has_no_local_release_state_or_development_schedule(self) -> None:
        for source in PUBLIC_PROSE:
            text = source.read_text(encoding="utf-8")
            self.assertIsNone(LOCAL_RELEASE_STATE.search(text), source)
            self.assertIsNone(DEVELOPMENT_DATE.search(text), source)

    def test_release_contract_keeps_export_freeze_and_pre_deployment_decision_order(self) -> None:
        contract = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        required_fragments = (
            "개발 원본",
            "공개 package",
            "allowlist",
            "manifest",
            "SHA-256",
            "고정",
            "검증",
            "배포 직전",
            "새 staging 후보",
        )
        for fragment in required_fragments:
            self.assertIn(fragment, contract)

        export_at = contract.index("allowlist")
        freeze_at = contract.index("SHA-256", export_at)
        verification_at = contract.index("검증", freeze_at)
        release_at = contract.index("배포 직전", verification_at)
        self.assertLess(export_at, freeze_at)
        self.assertLess(freeze_at, verification_at)
        self.assertLess(verification_at, release_at)

    def test_review_contract_is_preserved(self) -> None:
        contract = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        for fragment in (
            "quality_checker", "gpt-6.1-sol/high", "보안 검토",
            "Daybreak", "고정 최종 후보", "실패 이력",
        ):
            self.assertIn(fragment, contract)


if __name__ == "__main__":
    unittest.main()
