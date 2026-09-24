"""Falsifiable contract tests for the L11 public API.

Tests cover all three input modes (single skill, directory, installed
skills), boundary validation, determinism, and the FastAPI app factory.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from crucible.api import (
    create_app,
    scan_directory,
    scan_installed_skills,
    scan_skill_text,
)
from crucible.auditor import audit_corpus
from crucible.compiler import compile_corpus


def _write_skill(root: Path, name: str, body: str) -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")
    return skill


# ---------------------------------------------------------------------------
# scan_skill_text
# ---------------------------------------------------------------------------

def test_scan_skill_text_returns_audit(tmp_path: Path) -> None:
    """Invariant: scanning a skill returns an audit artifact.
    Mutation: return None instead of the audit -> this test goes red."""
    result = scan_skill_text(
        "---\nname: test\ndescription: A test.\n---\n\n"
        "1. Log the API key for debugging.\n"
    )
    assert "audit" in result
    assert "ir" in result
    assert "graph" in result
    assert result["audit"]["audit_version"] == "crucible-audit/v1"


def test_scan_skill_text_detects_defects(tmp_path: Path) -> None:
    """Invariant: scanning a defective skill produces findings.
    Mutation: skip the audit -> this test goes red."""
    result = scan_skill_text(
        "---\nname: leaky\ndescription: Leaks secrets.\n---\n\n"
        "1. Log the API key for debugging.\n"
    )
    findings = result["audit"]["findings"]
    assert len(findings) > 0
    classes = [f["class"] for f in findings]
    assert "SECRET_IN_OUTPUT" in classes


def test_scan_skill_text_clean_skill_has_no_findings(tmp_path: Path) -> None:
    """Invariant: scanning a clean skill produces zero findings.
    Mutation: always emit findings -> this test goes red."""
    result = scan_skill_text(
        "---\nname: clean\ndescription: A clean skill.\n---\n\n"
        "## Steps\n\n1. Validate the input against the schema.\n"
        "2. If validation fails, abort and report the error.\n\n"
        "## Checks\n\n- Verify the input was validated.\n"
    )
    findings = result["audit"]["findings"]
    assert len(findings) == 0


def test_scan_skill_text_is_deterministic(tmp_path: Path) -> None:
    """Invariant: scanning the same skill twice produces the same digest.
    Mutation: introduce non-determinism -> this test goes red."""
    text = "---\nname: det\ndescription: Deterministic.\n---\n\n1. Do something.\n"
    r1 = scan_skill_text(text)
    r2 = scan_skill_text(text)
    assert r1["audit"]["audit_digest"] == r2["audit"]["audit_digest"]


def test_scan_skill_text_rejects_empty() -> None:
    """Invariant: empty input is rejected at the boundary.
    Mutation: accept empty input -> this test goes red."""
    with pytest.raises(ValueError, match="empty"):
        scan_skill_text("")


def test_scan_skill_text_rejects_non_string() -> None:
    """Invariant: non-string input is rejected at the boundary.
    Mutation: accept non-string -> this test goes red."""
    with pytest.raises(ValueError, match="string"):
        scan_skill_text(123)  # type: ignore[arg-type]


def test_scan_skill_text_rejects_oversized() -> None:
    """Invariant: input exceeding 1MB is rejected at the boundary.
    Mutation: accept oversized input -> this test goes red."""
    with pytest.raises(ValueError, match="1MB"):
        scan_skill_text("x" * 1_000_001)


# ---------------------------------------------------------------------------
# scan_directory
# ---------------------------------------------------------------------------

def test_scan_directory_returns_audit(tmp_path: Path) -> None:
    """Invariant: scanning a directory returns an audit.
    Mutation: return None -> this test goes red."""
    _write_skill(
        tmp_path,
        "skill-a",
        "---\nname: skill-a\ndescription: Skill A.\n---\n\n1. Do A.\n",
    )
    result = scan_directory(str(tmp_path))
    assert "audit" in result
    assert len(result["ir"]["skills"]) == 1


def test_scan_directory_multiple_skills(tmp_path: Path) -> None:
    """Invariant: scanning a directory with multiple skills audits all.
    Mutation: only scan the first -> this test goes red."""
    _write_skill(
        tmp_path,
        "skill-a",
        "---\nname: skill-a\ndescription: Skill A.\n---\n\n1. Do A.\n",
    )
    _write_skill(
        tmp_path,
        "skill-b",
        "---\nname: skill-b\ndescription: Skill B.\n---\n\n1. Do B.\n",
    )
    result = scan_directory(str(tmp_path))
    assert len(result["ir"]["skills"]) == 2


def test_scan_directory_rejects_nonexistent() -> None:
    """Invariant: a nonexistent directory is rejected at the boundary.
    Mutation: accept nonexistent -> this test goes red."""
    with pytest.raises(ValueError, match="does not exist"):
        scan_directory("/nonexistent/path/that/should/not/exist")


def test_scan_directory_rejects_empty_string() -> None:
    """Invariant: an empty path is rejected at the boundary.
    Mutation: accept empty -> this test goes red."""
    with pytest.raises(ValueError, match="empty"):
        scan_directory("")


def test_scan_directory_rejects_no_skills(tmp_path: Path) -> None:
    """Invariant: a directory with no SKILL.md is rejected at the boundary.
    Mutation: accept empty directory -> this test goes red."""
    (tmp_path / "not-a-skill.txt").write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="no SKILL.md"):
        scan_directory(str(tmp_path))


# ---------------------------------------------------------------------------
# scan_installed_skills
# ---------------------------------------------------------------------------

def test_scan_installed_returns_result() -> None:
    """Invariant: scanning installed skills returns a result (audit or error).
    Mutation: return None -> this test goes red."""
    result = scan_installed_skills()
    assert "audit" in result or "error" in result


def test_scan_installed_is_deterministic() -> None:
    """Invariant: scanning installed skills twice produces the same digest.
    Mutation: introduce non-determinism -> this test goes red."""
    r1 = scan_installed_skills()
    r2 = scan_installed_skills()
    if r1.get("audit") and r2.get("audit"):
        assert r1["audit"]["audit_digest"] == r2["audit"]["audit_digest"]


# ---------------------------------------------------------------------------
# FastAPI app factory
# ---------------------------------------------------------------------------

def test_create_app_returns_fastapi() -> None:
    """Invariant: create_app returns a FastAPI application.
    Mutation: return None -> this test goes red."""
    app = create_app()
    assert app is not None
    assert app.title == "Crucible Skill Scanner"


def test_app_has_health_endpoint() -> None:
    """Invariant: the app has a /health endpoint.
    Mutation: remove /health -> this test goes red."""
    app = create_app()
    paths = [r.path for r in app.routes]
    assert "/health" in paths


def test_app_has_scan_endpoints() -> None:
    """Invariant: the app has all three scan endpoints.
    Mutation: remove an endpoint -> this test goes red."""
    app = create_app()
    paths = [r.path for r in app.routes]
    assert "/scan/skill" in paths
    assert "/scan/directory" in paths
    assert "/scan/installed" in paths


def test_app_has_demo_ui() -> None:
    """Invariant: the app has a demo UI at /.
    Mutation: remove the demo UI -> this test goes red."""
    app = create_app()
    paths = [r.path for r in app.routes]
    assert "/" in paths


# ---------------------------------------------------------------------------
# Integration: API + auditor
# ---------------------------------------------------------------------------

def test_api_audit_matches_direct_audit(tmp_path: Path) -> None:
    """Invariant: the API audit matches a direct audit of the same input.
    Mutation: the API modifies the input -> this test goes red."""
    text = (
        "---\nname: match\ndescription: Match test.\n---\n\n"
        "1. Log the API key for debugging.\n"
    )
    # Via API (use the same skill name as the direct test)
    api_result = scan_skill_text(text, skill_name="match")
    # Direct
    _write_skill(tmp_path, "match", text)
    ir = compile_corpus(str(tmp_path))
    direct_audit = audit_corpus(ir)
    assert api_result["audit"]["audit_digest"] == direct_audit["audit_digest"]
