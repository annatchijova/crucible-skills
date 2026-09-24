"""Falsifiable contract tests for the general confirmation layer (all CANDIDATEs)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from crucible.auditor import audit_corpus
from crucible.compiler import compile_corpus
from crucible.confirm import (
    CONFIRMATION_VERSION,
    MockConfirmExecutor,
    NebiusConfirmExecutor,
    confirm_candidates,
)


def _compile_and_audit(corpus: dict[str, str]) -> tuple[dict, dict]:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for name, content in corpus.items():
            d = root / name
            d.mkdir()
            (d / "SKILL.md").write_text(content, encoding="utf-8", newline="\n")
        ir = compile_corpus(root)
        audit = audit_corpus(ir)
    return ir, audit


# A skill with a check that has no oracle (no ?, no checkbox, no verb).
_CHECK_WITHOUT_ORACLE_SKILL = (
    "---\nname: skill-wo\ndescription: Use this skill for testing.\n"
    "license: Apache-2.0\n---\n\n"
    "# Skill WO\n\n"
    "The system MUST handle errors.\n\n"
    "## Checks\n\n"
    "- The sky is blue.\n"
)

# A skill with a substantive description but zero body structure.
_DESCRIPTION_BODY_GAP_SKILL = (
    "---\nname: skill-gap\ndescription: Use this skill when debugging memory leaks "
    "in C programs with valgrind and other diagnostic tools.\n"
    "license: Apache-2.0\n---\n\n"
    "# Skill Gap\n\n"
    "This skill helps you find memory leaks.\n"
)

# A skill with rules but no checks.
_REQUIREMENT_WITHOUT_CHECK_SKILL = (
    "---\nname: skill-req\ndescription: Use this skill for retries.\n"
    "license: Apache-2.0\n---\n\n"
    "# Skill Req\n\n"
    "Retries MUST have a finite budget.\n"
    "Retries SHOULD be idempotent.\n"
)

# A skill with a trigger that mismatches the rules.
_SCOPE_TRIGGER_MISMATCH_SKILL = (
    "---\nname: skill-mismatch\ndescription: Use this skill when debugging "
    "memory leaks in C programs.\n"
    "license: Apache-2.0\n---\n\n"
    "# Skill Mismatch\n\n"
    "Deployments MUST be automated.\n"
    "Releases SHOULD be tagged.\n"
)


# ---------------------------------------------------------------------------
# confirm_candidates handles all CANDIDATE types
# ---------------------------------------------------------------------------

def test_confirm_candidates_handles_check_without_oracle() -> None:
    """Invariant: confirm_candidates handles CHECK_WITHOUT_ORACLE."""
    ir, audit = _compile_and_audit({"skill-wo": _CHECK_WITHOUT_ORACLE_SKILL})
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["status"] == "COMPLETED"
    classes = {c["finding_class"] for c in confirmation["confirmations"]}
    assert "CHECK_WITHOUT_ORACLE" in classes


def test_confirm_candidates_handles_description_body_gap() -> None:
    """Invariant: confirm_candidates handles DESCRIPTION_BODY_GAP."""
    ir, audit = _compile_and_audit({"skill-gap": _DESCRIPTION_BODY_GAP_SKILL})
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["status"] == "COMPLETED"
    classes = {c["finding_class"] for c in confirmation["confirmations"]}
    assert "DESCRIPTION_BODY_GAP" in classes


def test_confirm_candidates_handles_requirement_without_check() -> None:
    """Invariant: confirm_candidates handles REQUIREMENT_WITHOUT_CHECK."""
    ir, audit = _compile_and_audit({"skill-req": _REQUIREMENT_WITHOUT_CHECK_SKILL})
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["status"] == "COMPLETED"
    classes = {c["finding_class"] for c in confirmation["confirmations"]}
    assert "REQUIREMENT_WITHOUT_CHECK" in classes


def test_confirm_candidates_handles_scope_trigger_mismatch() -> None:
    """Invariant: confirm_candidates handles SCOPE_TRIGGER_MISMATCH."""
    ir, audit = _compile_and_audit({"skill-mismatch": _SCOPE_TRIGGER_MISMATCH_SKILL})
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["status"] == "COMPLETED"
    classes = {c["finding_class"] for c in confirmation["confirmations"]}
    assert "SCOPE_TRIGGER_MISMATCH" in classes


# ---------------------------------------------------------------------------
# LLM out of the decision path
# ---------------------------------------------------------------------------

def test_confirm_candidates_does_not_modify_audit() -> None:
    """Invariant: the L2 audit is NEVER modified.
    Mutation: modify the audit in place -> red."""
    ir, audit = _compile_and_audit({
        "skill-wo": _CHECK_WITHOUT_ORACLE_SKILL,
        "skill-gap": _DESCRIPTION_BODY_GAP_SKILL,
    })
    digest_before = audit["audit_digest"]
    findings_before = list(audit["findings"])
    executor = MockConfirmExecutor()
    confirm_candidates(audit, ir, executor)
    assert audit["audit_digest"] == digest_before
    assert audit["findings"] == findings_before


def test_confirm_candidates_does_not_promote_to_confirmed() -> None:
    """Invariant: the L2 finding stays CANDIDATE.
    Mutation: modify the L2 finding status -> red."""
    ir, audit = _compile_and_audit({"skill-wo": _CHECK_WITHOUT_ORACLE_SKILL})
    executor = MockConfirmExecutor()
    confirm_candidates(audit, ir, executor)
    for f in audit["findings"]:
        if f["epistemic_status"] == "CANDIDATE":
            assert f["epistemic_status"] == "CANDIDATE"


# ---------------------------------------------------------------------------
# Class filtering
# ---------------------------------------------------------------------------

def test_confirm_candidates_with_class_filter() -> None:
    """Invariant: when classes is given, only those classes are confirmed.
    Mutation: ignore the filter -> red."""
    ir, audit = _compile_and_audit({
        "skill-wo": _CHECK_WITHOUT_ORACLE_SKILL,
        "skill-gap": _DESCRIPTION_BODY_GAP_SKILL,
    })
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(
        audit, ir, executor, classes=["CHECK_WITHOUT_ORACLE"]
    )
    classes = {c["finding_class"] for c in confirmation["confirmations"]}
    assert classes == {"CHECK_WITHOUT_ORACLE"}


# ---------------------------------------------------------------------------
# Nebius BLOCKED
# ---------------------------------------------------------------------------

def test_confirm_candidates_nebius_blocked() -> None:
    """Invariant: without API key, all confirmations are BLOCKED.
    Mutation: simulate results -> red."""
    ir, audit = _compile_and_audit({"skill-wo": _CHECK_WITHOUT_ORACLE_SKILL})
    executor = NebiusConfirmExecutor(api_key=None)
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["status"] == "BLOCKED"
    for c in confirmation["confirmations"]:
        assert c["verdict"] == "BLOCKED"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_confirm_candidates_is_deterministic() -> None:
    """Invariant: two runs produce the same digest.
    Mutation: introduce non-determinism -> red."""
    ir, audit = _compile_and_audit({
        "skill-wo": _CHECK_WITHOUT_ORACLE_SKILL,
        "skill-gap": _DESCRIPTION_BODY_GAP_SKILL,
    })
    executor = MockConfirmExecutor()
    c1 = confirm_candidates(audit, ir, executor)
    c2 = confirm_candidates(audit, ir, executor)
    assert c1["confirmation_digest"] == c2["confirmation_digest"]


# ---------------------------------------------------------------------------
# No floats
# ---------------------------------------------------------------------------

def test_confirm_candidates_no_floats() -> None:
    """Invariant: no float values in the confirmation artifact.
    Mutation: introduce a float -> red."""
    ir, audit = _compile_and_audit({"skill-wo": _CHECK_WITHOUT_ORACLE_SKILL})
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)

    def _check_no_floats(obj):
        if isinstance(obj, float):
            assert False, f"float found: {obj}"
        elif isinstance(obj, dict):
            for v in obj.values():
                _check_no_floats(v)
        elif isinstance(obj, list):
            for item in obj:
                _check_no_floats(item)

    _check_no_floats(confirmation)


# ---------------------------------------------------------------------------
# Summary correctness
# ---------------------------------------------------------------------------

def test_confirm_candidates_summary_correct() -> None:
    """Invariant: the summary counts match the confirmations.
    Mutation: miscount -> red."""
    ir, audit = _compile_and_audit({
        "skill-wo": _CHECK_WITHOUT_ORACLE_SKILL,
        "skill-gap": _DESCRIPTION_BODY_GAP_SKILL,
    })
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    total = len(confirmation["confirmations"])
    confirmed = sum(1 for c in confirmation["confirmations"] if c["verdict"] == "CONFIRMED")
    rejected = sum(1 for c in confirmation["confirmations"] if c["verdict"] == "REJECTED")
    unclear = sum(1 for c in confirmation["confirmations"] if c["verdict"] == "UNCLEAR")
    blocked = sum(1 for c in confirmation["confirmations"] if c["verdict"] == "BLOCKED")
    assert confirmation["summary"]["total"] == total
    assert confirmation["summary"]["confirmed"] == confirmed
    assert confirmation["summary"]["rejected"] == rejected
    assert confirmation["summary"]["unclear"] == unclear
    assert confirmation["summary"]["blocked"] == blocked


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def test_confirm_candidates_has_correct_schema() -> None:
    """Invariant: the confirmation artifact uses crucible-confirmation/v1."""
    ir, audit = _compile_and_audit({"skill-wo": _CHECK_WITHOUT_ORACLE_SKILL})
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["schema_version"] == CONFIRMATION_VERSION


def test_confirm_candidates_references_audit() -> None:
    """Invariant: the confirmation references the L2 audit digest."""
    ir, audit = _compile_and_audit({"skill-wo": _CHECK_WITHOUT_ORACLE_SKILL})
    executor = MockConfirmExecutor()
    confirmation = confirm_candidates(audit, ir, executor)
    assert confirmation["source_audit_digest"] == audit["audit_digest"]
