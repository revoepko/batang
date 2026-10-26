"""복사 스냅샷의 단일 Batang 등록과 구성요소 참조를 확인한다."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest


PACKAGE = Path(__file__).resolve().parents[1]
WORKFLOW_PATHS = (
    "components/madi/workflow.md",
    "components/gadak/workflow.md",
    "components/naru/workflow.md",
    "components/dure/workflow.md",
    "components/supul/workflow.md",
    "components/supul/galpi/workflow.md",
    "components/supul/gori/workflow.md",
    "components/supul/bogi/workflow.md",
)


class InstallLifecycleBoundaryTests(unittest.TestCase):
    def test_single_registered_batang_resolves_internal_workflows_in_same_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            copied = root / "snapshot"
            shutil.copytree(PACKAGE, copied, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            registry = root / "registry"
            registry.mkdir()
            unrelated = registry / "notes.txt"
            unrelated.write_text("preserve this registry sibling", encoding="utf-8")
            other_skill = root / "other-skill"
            other_skill.mkdir()
            other_skill_file = other_skill / "marker.txt"
            other_skill_file.write_text("preserve this registration", encoding="utf-8")
            (registry / "other-skill").symlink_to(other_skill, target_is_directory=True)
            target = copied / "skills/batang"
            (registry / "batang").symlink_to(target, target_is_directory=True)

            resolved_registry = (registry / "batang").resolve(strict=True)
            entrypoint = resolved_registry / "SKILL.md"
            self.assertTrue(entrypoint.is_file())
            self.assertEqual(resolved_registry, target.resolve())
            for relative in WORKFLOW_PATHS:
                workflow = resolved_registry / relative
                self.assertTrue(workflow.is_file(), relative)
                self.assertEqual(workflow.resolve().relative_to(copied.resolve()), Path("skills/batang") / relative)

            self.assertEqual(unrelated.read_text(encoding="utf-8"), "preserve this registry sibling")
            self.assertEqual(other_skill_file.read_text(encoding="utf-8"), "preserve this registration")
            self.assertEqual(set(os.listdir(registry)), {"batang", "other-skill", "notes.txt"})
            self.assertTrue((registry / "batang").is_symlink())
            self.assertTrue((registry / "other-skill").is_symlink())


if __name__ == "__main__":
    unittest.main()
