"""Falsifiable contract tests for the red-team security fixes (RT-01 through RT-05).

Each test verifies that a specific vulnerability found in the red-team audit
is no longer exploitable. The tests are designed to go red if the fix is
reverted.

See docs/red-team/2026-09-24-l11-api-red-team.md for the full audit report.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from crucible.api import (
    _redact_ir,
    _sanitize_skill_name,
    scan_directory,
    scan_installed_skills,
    scan_skill_text,
)
from crucible.compiler import compile_corpus

VALID_SKILL = (
    "---\nname: test-skill\ndescription: A test skill.\n---\n\n"
    "# Instructions\n\nDo good things.\n"
)


# ---------------------------------------------------------------------------
# RT-01: Path traversal via skill_name
# ---------------------------------------------------------------------------

class TestRT01PathTraversal:
    """RT-01: skill_name must not allow path traversal."""

    def test_rejects_forward_slash(self) -> None:
        """Invariant: skill_name with / is rejected.
        Mutation: remove the separator check -> this test goes red."""
        with pytest.raises(ValueError, match="path separators"):
            _sanitize_skill_name("../escape")

    def test_rejects_backslash(self) -> None:
        """Invariant: skill_name with \\ is rejected."""
        with pytest.raises(ValueError, match="path separators"):
            _sanitize_skill_name("..\\escape")

    def test_rejects_dot_dot(self) -> None:
        """Invariant: skill_name = '..' is rejected."""
        with pytest.raises(ValueError, match="traversal"):
            _sanitize_skill_name("..")

    def test_rejects_empty(self) -> None:
        """Invariant: empty skill_name is rejected."""
        with pytest.raises(ValueError, match="empty"):
            _sanitize_skill_name("")

    def test_rejects_non_string(self) -> None:
        """Invariant: non-string skill_name is rejected."""
        with pytest.raises(ValueError, match="string"):
            _sanitize_skill_name(123)  # type: ignore[arg-type]

    def test_rejects_oversized(self) -> None:
        """Invariant: skill_name > 200 chars is rejected."""
        with pytest.raises(ValueError, match="200"):
            _sanitize_skill_name("a" * 201)

    def test_accepts_valid_name(self) -> None:
        """Invariant: a valid skill name is accepted.
        Mutation: over-strict validation -> this test goes red."""
        assert _sanitize_skill_name("my-valid-skill") == "my-valid-skill"

    def test_scan_skill_text_rejects_traversal(self) -> None:
        """Invariant: scan_skill_text rejects path-traversing skill_name.
        Mutation: remove _sanitize_skill_name call -> this test goes red."""
        with pytest.raises(ValueError, match="path separators"):
            scan_skill_text(VALID_SKILL, skill_name="../escape")

    def test_no_file_created_on_traversal_attempt(self) -> None:
        """Invariant: no file is created outside the temp dir when
        a traversal attempt is rejected.
        Mutation: skip validation -> file is created -> this test goes red."""
        marker = Path(tempfile.gettempdir()) / "crucible-rt01-marker"
        if marker.exists():
            marker.unlink()
        try:
            with pytest.raises(ValueError):
                scan_skill_text(VALID_SKILL, skill_name="../crucible-rt01-marker")
            assert not marker.exists(), "file was created despite rejection"
        finally:
            if marker.exists():
                marker.unlink()


# ---------------------------------------------------------------------------
# RT-02: Symlink content leak via copytree
# ---------------------------------------------------------------------------

class TestRT02SymlinkLeak:
    """RT-02: copytree must preserve symlinks so the compiler can catch them."""

    def test_copytree_preserves_symlinks(self) -> None:
        """Invariant: scan_installed_skills uses symlinks=True so the
        compiler's symlink check catches symlinked SKILL.md files.
        Mutation: revert to symlinks=False -> symlink content leaks."""
        import shutil
        home = Path.home()
        fake_dir = home / ".claude" / "skills" / "crucible-rt02-test"
        fake_dir.mkdir(exist_ok=True)
        leak_target = Path(tempfile.gettempdir()) / "crucible-rt02-leak.md"
        leak_target.write_text(
            "---\nname: rt02-leaked\ndescription: secret\n---\n\n"
            "# Secret\n\nPassword: hunter2\n"
        )
        symlink_path = fake_dir / "SKILL.md"
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
        os.symlink(str(leak_target), symlink_path)
        try:
            # The compiler should reject the symlinked SKILL.md.
            with pytest.raises(ValueError, match="symlinked SKILL.md is not allowed"):
                scan_installed_skills()
        finally:
            symlink_path.unlink()
            fake_dir.rmdir()
            leak_target.unlink()


# ---------------------------------------------------------------------------
# RT-03: body_text redaction in API responses
# ---------------------------------------------------------------------------

class TestRT03BodyTextRedaction:
    """RT-03: the API must not return body_text in the IR."""

    def test_scan_skill_text_redacts_body_text(self) -> None:
        """Invariant: scan_skill_text does not include body_text in the IR.
        Mutation: remove _redact_ir call -> body_text leaks -> this test goes red."""
        result = scan_skill_text(VALID_SKILL, skill_name="test")
        ir = result["ir"]
        for skill in ir["skills"]:
            assert "body_text" not in skill, "body_text present in redacted IR"

    def test_scan_directory_redacts_body_text(self, tmp_path: Path) -> None:
        """Invariant: scan_directory does not include body_text."""
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(VALID_SKILL)
        result = scan_directory(str(tmp_path))
        ir = result["ir"]
        for skill in ir["skills"]:
            assert "body_text" not in skill

    def test_redact_ir_preserves_identity(self) -> None:
        """Invariant: _redact_ir preserves identity, metadata, rules, checks.
        Mutation: over-redaction -> this test goes red."""
        from crucible.compiler import compile_corpus
        skill_dir = Path(tempfile.mkdtemp()) / "test"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(VALID_SKILL)
        ir = compile_corpus(str(skill_dir))
        redacted = _redact_ir(ir)
        skill = redacted["skills"][0]
        assert skill["identity"]["name"] == "test-skill"
        assert "rules" in skill
        assert "checks" in skill
        assert "body_text" not in skill
        import shutil
        shutil.rmtree(skill_dir.parent)


# ---------------------------------------------------------------------------
# RT-04: File count cap
# ---------------------------------------------------------------------------

class TestRT04SizeCap:
    """RT-04: compile_corpus must enforce a max_skills limit."""

    def test_compile_corpus_rejects_too_many_skills(self, tmp_path: Path) -> None:
        """Invariant: compile_corpus raises ValueError when the corpus
        exceeds max_skills.
        Mutation: remove the max_skills check -> this test goes red."""
        for i in range(3):
            d = tmp_path / f"skill-{i}"
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nname: skill-{i}\ndescription: test\n---\n\n# Body\n\nTest.\n"
            )
        with pytest.raises(ValueError, match="exceeding the limit of 2"):
            compile_corpus(str(tmp_path), max_skills=2)

    def test_compile_corpus_allows_under_limit(self, tmp_path: Path) -> None:
        """Invariant: compile_corpus works when under the limit."""
        for i in range(2):
            d = tmp_path / f"skill-{i}"
            d.mkdir()
            (d / "SKILL.md").write_text(
                f"---\nname: skill-{i}\ndescription: test\n---\n\n# Body\n\nTest.\n"
            )
        ir = compile_corpus(str(tmp_path), max_skills=5)
        assert len(ir["skills"]) == 2

    def test_compile_corpus_no_limit_by_default(self, tmp_path: Path) -> None:
        """Invariant: compile_corpus with max_skills=None has no limit."""
        d = tmp_path / "skill-0"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill-0\ndescription: test\n---\n\n# Body\n\nTest.\n"
        )
        ir = compile_corpus(str(tmp_path), max_skills=None)
        assert len(ir["skills"]) == 1


# ---------------------------------------------------------------------------
# RT-05: Deduplication warning in scan_installed_skills
# ---------------------------------------------------------------------------

class TestRT05DedupWarning:
    """RT-05: scan_installed_skills must report skipped duplicates."""

    def test_skipped_duplicates_field_exists(self) -> None:
        """Invariant: scan_installed_skills returns a skipped_duplicates field.
        Mutation: remove the field -> this test goes red."""
        result = scan_installed_skills()
        assert "skipped_duplicates" in result

    def test_skipped_duplicates_is_list(self) -> None:
        """Invariant: skipped_duplicates is a list."""
        result = scan_installed_skills()
        assert isinstance(result.get("skipped_duplicates"), list)
