"""Falsifiable contract tests for the L12 confirmation layer extension.

Tests cover:
- All 14 engineering check prompt builders produce correct prompts.
- The LLM stays OUT of the decision path: the confirmation is an
  OBSERVATION, the L2 audit is never modified, and the confirmation
  artifact has its own separate digest.
- The confirmation layer is BLOCKED when NEBIUS_API_KEY is not set.
- The mock executor can confirm/reject engineering check findings.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from crucible.api import scan_skill_text
from crucible.auditor import audit_corpus
from crucible.compiler import compile_corpus
from crucible.confirm import (
    CONFIRMATION_VERSION,
    MockConfirmExecutor,
    NebiusConfirmExecutor,
    _ENGINEERING_QUESTIONS,
    _PROMPT_BUILDERS,
    _build_engineering_check_prompt,
    confirm_candidates,
)


def _write_skill(root: Path, name: str, body: str) -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")
    return skill


def _audit_with_finding(tmp_path: Path, finding_class: str, body: str) -> tuple[dict, dict]:
    """Compile and audit a skill, return (audit, ir)."""
    _write_skill(tmp_path, "test-skill", body)
    ir = compile_corpus(str(tmp_path))
    audit = audit_corpus(ir)
    return audit, ir


# ---------------------------------------------------------------------------
# Prompt builder registration
# ---------------------------------------------------------------------------

def test_all_engineering_checks_have_prompt_builders() -> None:
    """Invariant: all 14 engineering check classes have prompt builders.
    Mutation: remove a builder -> this test goes red."""
    expected = {
        "UNBOUNDED_RETRY", "LLM_IN_DECISION_PATH", "OVERCLAIM",
        "MISSING_FAILURE_MODE", "NON_DETERMINISTIC_INSTRUCTION",
        "IRREVERSIBLE_WITHOUT_REVIEW", "SECRET_IN_OUTPUT",
        "SILENT_FAILURE", "HARDCODED_CREDENTIAL", "UNBOUNDED_RESOURCE",
        "UNVALIDATED_EXTERNAL_INPUT", "MISSING_TIMEOUT",
        "FLOATING_POINT_IN_DECISION_PATH", "UNPINNED_DEPENDENCY",
    }
    registered = set(_PROMPT_BUILDERS.keys())
    missing = expected - registered
    assert not missing, f"Missing prompt builders: {missing}"


def test_engineering_questions_cover_all_registered() -> None:
    """Invariant: _ENGINEERING_QUESTIONS has an entry for every engineering check.
    Mutation: remove a question -> this test goes red."""
    expected = {
        "UNBOUNDED_RETRY", "LLM_IN_DECISION_PATH", "OVERCLAIM",
        "MISSING_FAILURE_MODE", "NON_DETERMINISTIC_INSTRUCTION",
        "IRREVERSIBLE_WITHOUT_REVIEW", "SECRET_IN_OUTPUT",
        "SILENT_FAILURE", "HARDCODED_CREDENTIAL", "UNBOUNDED_RESOURCE",
        "UNVALIDATED_EXTERNAL_INPUT", "MISSING_TIMEOUT",
        "FLOATING_POINT_IN_DECISION_PATH", "UNPINNED_DEPENDENCY",
    }
    assert _ENGINEERING_QUESTIONS.keys() == expected


# ---------------------------------------------------------------------------
# Prompt builder output
# ---------------------------------------------------------------------------

def test_engineering_prompt_contains_skill_text() -> None:
    """Invariant: the prompt includes the skill text.
    Mutation: omit skill text -> this test goes red."""
    finding = {"class": "SECRET_IN_OUTPUT", "evidence": "leaks key"}
    system, user = _build_engineering_check_prompt(finding, "This is the skill body.")
    assert "This is the skill body." in user


def test_engineering_prompt_contains_evidence() -> None:
    """Invariant: the prompt includes the finding evidence.
    Mutation: omit evidence -> this test goes red."""
    finding = {"class": "SILENT_FAILURE", "evidence": "ignores error silently"}
    system, user = _build_engineering_check_prompt(finding, "skill text")
    assert "ignores error silently" in user


def test_engineering_prompt_contains_verdict_instruction() -> None:
    """Invariant: the prompt asks for CONFIRMED/REJECTED/UNCLEAR.
    Mutation: remove verdict instruction -> this test goes red."""
    finding = {"class": "UNBOUNDED_RETRY", "evidence": "retry without bound"}
    system, user = _build_engineering_check_prompt(finding, "skill text")
    assert "CONFIRMED" in user
    assert "REJECTED" in user
    assert "UNCLEAR" in user


def test_engineering_prompt_system_says_do_not_modify() -> None:
    """Invariant: the system prompt tells the LLM not to modify values.
    Mutation: remove the guardrail -> this test goes red."""
    finding = {"class": "OVERCLAIM", "evidence": "always succeeds"}
    system, user = _build_engineering_check_prompt(finding, "skill text")
    assert "Do not modify" in system


def test_engineering_prompt_class_specific_question() -> None:
    """Invariant: each class gets its own question text.
    Mutation: use a generic question for all -> this test goes red."""
    finding_retry = {"class": "UNBOUNDED_RETRY", "evidence": "retry"}
    finding_secret = {"class": "SECRET_IN_OUTPUT", "evidence": "leak"}
    _, user_retry = _build_engineering_check_prompt(finding_retry, "text")
    _, user_secret = _build_engineering_check_prompt(finding_secret, "text")
    # The retry question mentions "retry or repeat"; the secret question mentions "secret".
    assert "retry" in user_retry.lower()
    assert "secret" in user_secret.lower()


# ---------------------------------------------------------------------------
# LLM out of decision path
# ---------------------------------------------------------------------------

def test_confirmation_does_not_modify_audit(tmp_path: Path) -> None:
    """Invariant: the L2 audit artifact is never modified by the confirmation layer.
    Mutation: the confirmation layer mutates the audit -> this test goes red."""
    audit, ir = _audit_with_finding(
        tmp_path, "SECRET_IN_OUTPUT",
        "---\nname: test\ndescription: Test.\n---\n\n1. Log the API key for debugging.\n",
    )
    original_digest = audit["audit_digest"]
    original_findings = list(audit["findings"])
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    # The audit must be unchanged.
    assert audit["audit_digest"] == original_digest
    assert audit["findings"] == original_findings


def test_confirmation_has_separate_digest(tmp_path: Path) -> None:
    """Invariant: the confirmation artifact has its own digest, separate from the audit.
    Mutation: reuse the audit digest -> this test goes red."""
    audit, ir = _audit_with_finding(
        tmp_path, "SECRET_IN_OUTPUT",
        "---\nname: test\ndescription: Test.\n---\n\n1. Log the API key for debugging.\n",
    )
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["confirmation_digest"] != audit["audit_digest"]
    assert confirmation["schema_version"] == CONFIRMATION_VERSION


def test_confirmation_does_not_promote_to_confirmed(tmp_path: Path) -> None:
    """Invariant: the confirmation is an OBSERVATION, not a promotion to CONFIRMED.
    Mutation: the confirmation modifies the audit's epistemic_status -> this test goes red."""
    audit, ir = _audit_with_finding(
        tmp_path, "SECRET_IN_OUTPUT",
        "---\nname: test\ndescription: Test.\n---\n\n1. Log the API key for debugging.\n",
    )
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    # The audit findings must still be CANDIDATE, not CONFIRMED.
    for f in audit["findings"]:
        assert f["epistemic_status"] == "CANDIDATE"
    # The confirmation artifact has its own verdicts, not audit promotions.
    for c in confirmation["confirmations"]:
        assert c["verdict"] in ("CONFIRMED", "REJECTED", "UNCLEAR", "BLOCKED")


def test_nebius_executor_blocked_without_key() -> None:
    """Invariant: without NEBIUS_API_KEY, the executor is BLOCKED.
    Mutation: simulate results without a key -> this test goes red."""
    executor = NebiusConfirmExecutor(api_key="")
    assert not executor.is_available()


def test_nebius_executor_blocked_returns_blocked_response() -> None:
    """Invariant: a blocked executor returns a blocked response, not a fake verdict.
    Mutation: return a fake CONFIRMED -> this test goes red."""
    executor = NebiusConfirmExecutor(api_key="")
    response = executor.execute("system", "user")
    assert response["blocked"] is True
    assert response["output"] == ""


# ---------------------------------------------------------------------------
# Mock executor with engineering checks
# ---------------------------------------------------------------------------

def test_mock_executor_confirms_engineering_finding(tmp_path: Path) -> None:
    """Invariant: the mock executor can confirm an engineering finding.
    Mutation: the mock executor skips engineering checks -> this test goes red."""
    audit, ir = _audit_with_finding(
        tmp_path, "SECRET_IN_OUTPUT",
        "---\nname: test\ndescription: Test.\n---\n\n1. Log the API key for debugging.\n",
    )
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["status"] == "COMPLETED"
    assert confirmation["summary"]["total"] > 0
    # At least one confirmation for SECRET_IN_OUTPUT.
    classes = [c["finding_class"] for c in confirmation["confirmations"]]
    assert "SECRET_IN_OUTPUT" in classes


def test_mock_executor_rejects_false_positive(tmp_path: Path) -> None:
    """Invariant: the mock executor rejects a finding when the skill has content.
    Mutation: always confirm -> this test goes red."""
    # A skill with many lines but a SECRET_IN_OUTPUT finding.
    body = (
        "---\nname: test\ndescription: A longer skill.\n---\n\n"
        "## Steps\n\n"
        "1. Log the API key for debugging.\n"
        "2. Validate the input.\n"
        "3. Check the result.\n"
        "4. Handle the error.\n"
        "5. Report the status.\n"
        "6. Clean up resources.\n"
        "7. Close the connection.\n"
    )
    _write_skill(tmp_path, "test", body)
    ir = compile_corpus(str(tmp_path))
    audit = audit_corpus(ir)
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    # The mock executor rejects findings when the skill has >= 5 non-empty lines.
    for c in confirmation["confirmations"]:
        if c["finding_class"] == "SECRET_IN_OUTPUT":
            assert c["verdict"] == "REJECTED"


# ---------------------------------------------------------------------------
# Full pipeline: audit -> confirm
# ---------------------------------------------------------------------------

def test_full_pipeline_audit_then_confirm(tmp_path: Path) -> None:
    """Invariant: the full pipeline (audit -> confirm) works end-to-end.
    Mutation: the confirmation layer breaks the pipeline -> this test goes red."""
    body = (
        "---\nname: leaky\ndescription: Leaks secrets.\n---\n\n"
        "1. Log the API key for debugging.\n"
        "2. Ignore the error and continue.\n"
    )
    _write_skill(tmp_path, "leaky", body)
    ir = compile_corpus(str(tmp_path))
    audit = audit_corpus(ir)
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["status"] == "COMPLETED"
    assert confirmation["source_audit_digest"] == audit["audit_digest"]
    assert confirmation["source_ir_digest"] == ir["artifact_digest"]
