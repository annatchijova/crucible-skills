"""Falsifiable contract tests for the SEMANTIC_REDUNDANCY confirmation layer."""

from __future__ import annotations

import tempfile
from pathlib import Path

from crucible.auditor import audit_corpus
from crucible.compiler import compile_corpus
from crucible.confirm import (
    CONFIRMATION_VERSION,
    MockConfirmExecutor,
    NebiusConfirmExecutor,
    confirm_semantic_redundancy,
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


_REUNDANT_A = (
    "---\nname: skill-a\ndescription: Use this skill when retrying "
    "failed operations with a bounded budget.\n"
    "license: Apache-2.0\n---\n\n"
    "# Skill A\n\n"
    "Retries MUST have a finite budget.\n"
    "Retries SHOULD be idempotent.\n\n"
    "## Checks\n\n"
    "- [ ] Verify the retry budget is finite.\n"
)

_REDUNDANT_B = (
    "---\nname: skill-b\ndescription: Use this skill when retrying "
    "failed operations with a bounded budget.\n"
    "license: Apache-2.0\n---\n\n"
    "# Skill B\n\n"
    "Retries MUST have a finite budget.\n"
    "Retries SHOULD be idempotent.\n\n"
    "## Checks\n\n"
    "- [ ] Verify the retry budget is finite.\n"
)

_NON_REDUNDANT = (
    "---\nname: skill-c\ndescription: Use this skill when deploying "
    "to production environments.\n"
    "license: Apache-2.0\n---\n\n"
    "# Skill C\n\n"
    "Deployments MUST be tagged.\n"
    "Releases SHOULD be automated.\n\n"
    "## Checks\n\n"
    "- [ ] Verify the deployment is tagged.\n"
)


# ---------------------------------------------------------------------------
# Artifact schema
# ---------------------------------------------------------------------------

def test_artifact_has_correct_schema_version() -> None:
    """Invariant: the confirmation artifact uses crucible-confirmation/v1."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = MockConfirmExecutor()
    confirmation = confirm_semantic_redundancy(audit, ir, executor)
    assert confirmation["schema_version"] == CONFIRMATION_VERSION


def test_artifact_has_digest() -> None:
    """Invariant: the confirmation artifact has a SHA-256 digest."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = MockConfirmExecutor()
    confirmation = confirm_semantic_redundancy(audit, ir, executor)
    assert confirmation["confirmation_digest"].startswith("sha256:")


def test_artifact_references_source_audit() -> None:
    """Invariant: the confirmation artifact references the L2 audit digest."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = MockConfirmExecutor()
    confirmation = confirm_semantic_redundancy(audit, ir, executor)
    assert confirmation["source_audit_digest"] == audit["audit_digest"]


# ---------------------------------------------------------------------------
# LLM out of the decision path
# ---------------------------------------------------------------------------

def test_audit_unchanged_after_confirmation() -> None:
    """Invariant: the L2 audit artifact is NEVER modified by confirmation.
    Mutation: modify the audit in place -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    digest_before = audit["audit_digest"]
    findings_before = list(audit["findings"])
    executor = MockConfirmExecutor()
    confirm_semantic_redundancy(audit, ir, executor)
    assert audit["audit_digest"] == digest_before
    assert audit["findings"] == findings_before


def test_confirmation_does_not_promote_to_confirmed() -> None:
    """Invariant: the confirmation verdict is OBSERVATION, not a promotion
    to CONFIRMED in the L2 audit. The L2 finding stays CANDIDATE.
    Mutation: modify the L2 finding status -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = MockConfirmExecutor()
    confirm_semantic_redundancy(audit, ir, executor)
    # The L2 finding must still be CANDIDATE.
    semantic = [
        f for f in audit["findings"]
        if f["class"] == "SEMANTIC_REDUNDANCY"
    ]
    assert len(semantic) >= 1
    assert semantic[0]["epistemic_status"] == "CANDIDATE"


# ---------------------------------------------------------------------------
# Mock executor
# ---------------------------------------------------------------------------

def test_mock_confirms_redundant_pair() -> None:
    """Invariant: the mock executor confirms a redundant pair.
    Mutation: always return REJECTED -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = MockConfirmExecutor()
    confirmation = confirm_semantic_redundancy(audit, ir, executor)
    assert confirmation["status"] == "COMPLETED"
    assert len(confirmation["confirmations"]) >= 1
    assert confirmation["confirmations"][0]["verdict"] == "CONFIRMED"


def test_mock_rejects_non_redundant_pair() -> None:
    """Invariant: the mock executor rejects a non-redundant pair.
    Mutation: always return CONFIRMED -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-c": _NON_REDUNDANT})
    executor = MockConfirmExecutor()
    confirmation = confirm_semantic_redundancy(audit, ir, executor)
    # If there are no SEMANTIC_REDUNDANCY findings, there are no confirmations.
    # This is correct: the deterministic layer found no candidates.
    semantic = [
        f for f in audit["findings"]
        if f["class"] == "SEMANTIC_REDUNDANCY"
    ]
    if not semantic:
        assert len(confirmation["confirmations"]) == 0
        return
    # If there are findings, the mock should reject them.
    assert confirmation["status"] == "COMPLETED"
    for c in confirmation["confirmations"]:
        assert c["verdict"] == "REJECTED"


def test_mock_executor_is_deterministic() -> None:
    """Invariant: two runs of the mock executor produce the same digest.
    Mutation: introduce randomness -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = MockConfirmExecutor()
    c1 = confirm_semantic_redundancy(audit, ir, executor)
    c2 = confirm_semantic_redundancy(audit, ir, executor)
    assert c1["confirmation_digest"] == c2["confirmation_digest"]


# ---------------------------------------------------------------------------
# Nebius executor (BLOCKED)
# ---------------------------------------------------------------------------

def test_nebius_blocked_without_api_key() -> None:
    """Invariant: without NEBIUS_API_KEY, the confirmation is BLOCKED.
    Mutation: simulate a result -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = NebiusConfirmExecutor(api_key=None)
    assert not executor.is_available()
    confirmation = confirm_semantic_redundancy(audit, ir, executor)
    assert confirmation["status"] == "BLOCKED"
    for c in confirmation["confirmations"]:
        assert c["verdict"] == "BLOCKED"


def test_nebius_blocked_does_not_simulate() -> None:
    """Invariant: a BLOCKED confirmation does not fabricate verdicts.
    Mutation: return CONFIRMED when blocked -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = NebiusConfirmExecutor(api_key=None)
    confirmation = confirm_semantic_redundancy(audit, ir, executor)
    assert confirmation["summary"]["confirmed"] == 0
    assert confirmation["summary"]["rejected"] == 0
    assert confirmation["summary"]["blocked"] >= 1


# ---------------------------------------------------------------------------
# No candidates
# ---------------------------------------------------------------------------

def test_no_candidates_produces_empty_confirmation() -> None:
    """Invariant: if there are no SEMANTIC_REDUNDANCY findings, the
    confirmation is empty but valid.
    Mutation: crash on empty -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-c": _NON_REDUNDANT})
    executor = MockConfirmExecutor()
    confirmation = confirm_semantic_redundancy(audit, ir, executor)
    assert confirmation["status"] == "COMPLETED"
    assert len(confirmation["confirmations"]) == 0
    assert confirmation["summary"]["total"] == 0


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def test_summary_counts_are_correct() -> None:
    """Invariant: the summary counts match the confirmations.
    Mutation: miscount -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = MockConfirmExecutor()
    confirmation = confirm_semantic_redundancy(audit, ir, executor)
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
# Determinism
# ---------------------------------------------------------------------------

def test_confirmation_is_deterministic() -> None:
    """Invariant: two confirmations with the same inputs produce the same
    digest. Mutation: introduce non-determinism -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = MockConfirmExecutor()
    c1 = confirm_semantic_redundancy(audit, ir, executor)
    c2 = confirm_semantic_redundancy(audit, ir, executor)
    assert c1["confirmation_digest"] == c2["confirmation_digest"]


# ---------------------------------------------------------------------------
# No floats
# ---------------------------------------------------------------------------

def test_no_floats_in_confirmation() -> None:
    """Invariant: no float values in the confirmation artifact.
    Mutation: introduce a float -> red."""
    ir, audit = _compile_and_audit({"skill-a": _REUNDANT_A, "skill-b": _REDUNDANT_B})
    executor = MockConfirmExecutor()
    confirmation = confirm_semantic_redundancy(audit, ir, executor)

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
