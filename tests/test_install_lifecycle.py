"""격리된 복사본의 등록·전환·복구 호스트 절차를 실제 파일시스템에서 확인한다.

제품 installer나 실제 전역 설치를 실행하지 않는다. 이 검사는 Codex의 새 턴
자동 전달이나 실제 사용자 설치·권한·운영 볼트 보존을 증명하지 않는다.
"""

from __future__ import annotations

import os
import hashlib
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
    @staticmethod
    def _fixture_bytes(root: Path) -> dict[str, bytes]:
        return {path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*") if path.is_file() and not path.is_symlink()}

    def _transition_fixture(self, root: Path) -> dict:
        snapshots = [root / "snapshot-A", root / "snapshot-B"]
        for snapshot in snapshots:
            shutil.copytree(PACKAGE, snapshot, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        readme_a = snapshots[0] / "README.md"
        readme_a.chmod(readme_a.stat().st_mode | 0o200)
        for snapshot in snapshots:
            checksums_path = snapshot / "SHA256SUMS"
            checksums_path.chmod(checksums_path.stat().st_mode | 0o200)
        # 두 고정본의 identity를 구분하는 합성 변경이며 입력 package에는 쓰지 않는다.
        with readme_a.open("ab") as stream:
            stream.write(b"\nfixture snapshot A\n")
        for snapshot in snapshots:
            files = self._fixture_bytes(snapshot)
            checksums = "".join(hashlib.sha256(data).hexdigest() + "  " + relative + "\n"
                                for relative, data in sorted(files.items()) if relative != "SHA256SUMS")
            (snapshot / "SHA256SUMS").write_text(checksums, encoding="utf-8")
        registry = root / "registry"
        registry.mkdir()
        markers = {
            root / "vault/note.md": b"synthetic vault note\n",
            root / "project/AGENTS.md": b"synthetic project policy\n",
            root / "graph/graph.json": b'{"fixture":"preserve"}\n',
            root / "backups/note.before": b"synthetic backup\n",
            root / "runs/previous.md": b"synthetic prior run\n",
            root / "other-skill/marker.txt": b"synthetic unrelated skill\n",
            registry / "notes.txt": b"synthetic registry sibling\n",
        }
        for path, data in markers.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        old_batang = str(snapshots[0] / "skills/batang")
        old_madi = str(snapshots[0] / "skills/batang/components/madi")
        new_batang = str(snapshots[1] / "skills/batang")
        other_target = str(root / "other-skill")
        for name, target in (("batang", old_batang), ("madi", old_madi), ("other-skill", other_target)):
            (registry / name).symlink_to(target, target_is_directory=True)
        return {"snapshots": snapshots, "registry": registry, "markers": markers,
                "original_trees": [self._fixture_bytes(snapshot) for snapshot in snapshots],
                "old_batang": old_batang, "old_madi": old_madi, "new_batang": new_batang,
                "other_target": other_target,
                "bundle_identity": hashlib.sha256((snapshots[1] / "SHA256SUMS").read_bytes()).hexdigest()}

    @staticmethod
    def _observe_fixture_link(path: Path):
        if path.is_symlink():
            return os.readlink(path)
        if path.exists():
            return "regular_entry"
        return None

    @staticmethod
    def _replace_fixture_link(path: Path, target: str) -> None:
        pending = path.with_name("." + path.name + "-fixture-switch")
        pending.symlink_to(target, target_is_directory=True)
        os.replace(pending, path)

    def _verify_fixture_registration(self, fixture: dict) -> None:
        snapshot = fixture["snapshots"][1]
        registered = fixture["registry"] / "batang"
        self.assertEqual(registered.resolve(strict=True), (snapshot / "skills/batang").resolve())
        sums = snapshot / "SHA256SUMS"
        self.assertEqual(hashlib.sha256(sums.read_bytes()).hexdigest(), fixture["bundle_identity"])
        for line in sums.read_text(encoding="utf-8").splitlines():
            digest, relative = line.split("  ", 1)
            self.assertEqual(hashlib.sha256((snapshot / relative).read_bytes()).hexdigest(), digest, relative)
        self.assertTrue((registered / "SKILL.md").is_file())
        for relative in WORKFLOW_PATHS:
            workflow = registered / relative
            self.assertTrue(workflow.is_file(), relative)
            self.assertEqual(workflow.resolve().relative_to(snapshot.resolve()), Path("skills/batang") / relative)

    def _host_transition_fixture(self, fixture: dict, failure=None) -> dict:
        """테스트 호스트의 선택 절차이며 재사용 installer 또는 제품 API가 아니다."""
        registry = fixture["registry"]
        changes = []
        observations = []

        def observe(phase):
            state = {name: self._observe_fixture_link(registry / name) for name in ("batang", "madi")}
            observations.append({"phase": phase, "links": state})
            return state

        if failure == "unexpected_madi_before":
            self._replace_fixture_link(registry / "madi", fixture["other_target"])
        try:
            initial = observe("before")
            if initial != {"batang": fixture["old_batang"], "madi": fixture["old_madi"]}:
                raise RuntimeError("unexpected_initial_registration")
            self._replace_fixture_link(registry / "batang", fixture["new_batang"])
            changes.append(("batang", fixture["old_batang"], fixture["new_batang"]))
            observe("after_batang_switch")
            if failure == "after_switch":
                raise RuntimeError("fixture_failure_after_switch")
            self._verify_fixture_registration(fixture)
            observe("new_snapshot_verified")
            if failure == "unexpected_madi_after_verification":
                self._replace_fixture_link(registry / "madi", fixture["other_target"])
            if self._observe_fixture_link(registry / "madi") != fixture["old_madi"]:
                raise RuntimeError("unexpected_madi_registration")
            (registry / "madi").unlink()
            changes.append(("madi", fixture["old_madi"], None))
            observe("owned_madi_reclaimed")
            if failure == "after_madi_reclamation":
                raise RuntimeError("fixture_failure_after_madi_reclamation")
            if failure == "foreign_batang_before_recovery":
                self._replace_fixture_link(registry / "batang", fixture["other_target"])
                raise RuntimeError("fixture_foreign_registration")
            observe("success")
            return {"status": "success", "observations": observations, "restored": [], "deferred": []}
        except RuntimeError as error:
            # 실패 후 실제 현재 target을 기록하고 이번 절차에서 바꾼 link만 복구한다.
            observe("failure_before_recovery")
            restored, deferred = [], []
            for name, before, after in reversed(changes):
                path = registry / name
                if self._observe_fixture_link(path) != after:
                    deferred.append(name)
                    continue
                if after is None:
                    path.symlink_to(before, target_is_directory=True)
                else:
                    self._replace_fixture_link(path, before)
                restored.append(name)
            observe("after_conditional_recovery")
            return {"status": "partial" if deferred else "recovered", "error": str(error),
                    "observations": observations, "restored": restored, "deferred": deferred}

    def _assert_fixture_preserved(self, fixture: dict) -> None:
        for snapshot, expected in zip(fixture["snapshots"], fixture["original_trees"]):
            self.assertEqual(self._fixture_bytes(snapshot), expected)
        for path, expected in fixture["markers"].items():
            self.assertEqual(path.read_bytes(), expected, str(path))
        self.assertEqual(os.readlink(fixture["registry"] / "other-skill"), fixture["other_target"])

    def test_existing_owned_links_transition_after_hash_verification_and_preserve_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self._transition_fixture(Path(temporary).resolve())
            result = self._host_transition_fixture(fixture)
            self.assertEqual(result["status"], "success")
            self.assertEqual(os.readlink(fixture["registry"] / "batang"), fixture["new_batang"])
            self.assertFalse(os.path.lexists(fixture["registry"] / "madi"))
            phases = [item["phase"] for item in result["observations"]]
            self.assertLess(phases.index("new_snapshot_verified"), phases.index("owned_madi_reclaimed"))
            self._assert_fixture_preserved(fixture)

    def test_transition_failures_restore_only_changed_expected_links_and_report_foreign_targets(self) -> None:
        for failure in ("unexpected_madi_before", "after_switch", "after_madi_reclamation",
                        "unexpected_madi_after_verification", "foreign_batang_before_recovery"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                fixture = self._transition_fixture(Path(temporary).resolve())
                result = self._host_transition_fixture(fixture, failure)
                self.assertIn("error", result)
                failed_state = next(item["links"] for item in result["observations"]
                                    if item["phase"] == "failure_before_recovery")
                expected_batang = fixture["old_batang"]
                expected_madi = fixture["old_madi"]
                if failure.startswith("unexpected_madi"):
                    expected_madi = fixture["other_target"]
                    self.assertNotIn("madi", result["restored"])
                    self.assertEqual(failed_state["madi"], fixture["other_target"])
                if failure == "after_madi_reclamation":
                    self.assertEqual(result["restored"], ["madi", "batang"])
                    self.assertIsNone(failed_state["madi"])
                if failure == "foreign_batang_before_recovery":
                    expected_batang = fixture["other_target"]
                    self.assertEqual(result["status"], "partial")
                    self.assertEqual(result["deferred"], ["batang"])
                    self.assertEqual(failed_state["batang"], fixture["other_target"])
                else:
                    self.assertEqual(result["status"], "recovered")
                self.assertEqual(os.readlink(fixture["registry"] / "batang"), expected_batang)
                self.assertEqual(os.readlink(fixture["registry"] / "madi"), expected_madi)
                self.assertEqual(set(os.listdir(fixture["registry"])),
                                 {"batang", "madi", "other-skill", "notes.txt"})
                self._assert_fixture_preserved(fixture)

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
