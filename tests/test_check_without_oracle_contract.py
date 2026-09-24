"""Falsifiable contract tests for the CHECK_WITHOUT_ORACLE check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from crucible.auditor import audit_corpus
from crucible.compiler import compile_corpus


def _audit(corpus: dict[str, str]) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for name, content in corpus.items():
            d = root / name
            d.mkdir()
            (d / "SKILL.md").write_text(content, encoding="utf-8", newline="\n")
        ir = compile_corpus(root)
        return audit_corpus(ir)


def _findings_by_class(audit: dict, cls: str) -> list[dict]:
    return [f for f in audit["findings"] if f["class"] == cls]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_without_oracle_detected_for_unknown_check() -> None:
    """Invariant: a check with oracle_kind 'unknown' is flagged.
    Mutation: skip the check -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n\n"
            "## Checks\n\n"
            "- The sky is blue.\n"
        ),
    })
    no_oracle = _findings_by_class(audit, "CHECK_WITHOUT_ORACLE")
    assert len(no_oracle) >= 1
    assert no_oracle[0]["epistemic_status"] == "CANDIDATE"


def test_with_oracle_not_detected_for_question_check() -> None:
    """Invariant: a check that is a question is NOT flagged.
    Mutation: flag questions -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n\n"
            "## Checks\n\n"
            "- Is the budget recorded?\n"
        ),
    })
    no_oracle = _findings_by_class(audit, "CHECK_WITHOUT_ORACLE")
    assert len(no_oracle) == 0


def test_with_oracle_not_detected_for_command_check() -> None:
    """Invariant: a check with a verification verb is NOT flagged.
    Mutation: flag commands -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n\n"
            "## Checks\n\n"
            "- Verify the retry count is finite.\n"
        ),
    })
    no_oracle = _findings_by_class(audit, "CHECK_WITHOUT_ORACLE")
    assert len(no_oracle) == 0


def test_with_oracle_not_detected_for_checkbox_check() -> None:
    """Invariant: a checkbox check is NOT flagged.
    Mutation: flag checkboxes -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n\n"
            "## Checks\n\n"
            "- [ ] Confirm the limit is enforced.\n"
        ),
    })
    no_oracle = _findings_by_class(audit, "CHECK_WITHOUT_ORACLE")
    assert len(no_oracle) == 0


def test_mixed_checks_only_unknown_flagged() -> None:
    """Invariant: only checks with oracle_kind 'unknown' are flagged;
    checks with known oracle_kind are NOT. Mutation: flag all -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n\n"
            "## Checks\n\n"
            "- Verify the retry count is finite.\n"
            "- Is the budget recorded?\n"
            "- [ ] Confirm the limit is enforced.\n"
            "- The sky is blue.\n"
        ),
    })
    no_oracle = _findings_by_class(audit, "CHECK_WITHOUT_ORACLE")
    assert len(no_oracle) == 1
    assert "check-0004" in no_oracle[0]["evidence"]


# ---------------------------------------------------------------------------
# Oracle kind extraction
# ---------------------------------------------------------------------------

def test_oracle_kind_question_extracted() -> None:
    """Invariant: a check ending with ? is classified as 'question'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nR MUST be.\n\n## Checks\n\n- Is it done?\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    assert ir["skills"][0]["checks"][0]["oracle_kind"] == "question"


def test_oracle_kind_command_extracted() -> None:
    """Invariant: a check with 'verify' is classified as 'command'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nR MUST be.\n\n## Checks\n\n- Verify the output.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    assert ir["skills"][0]["checks"][0]["oracle_kind"] == "command"


def test_oracle_kind_checkbox_extracted() -> None:
    """Invariant: a check with [ ] is classified as 'checkbox'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nR MUST be.\n\n## Checks\n\n- [ ] Confirm the limit.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    assert ir["skills"][0]["checks"][0]["oracle_kind"] == "checkbox"


def test_oracle_kind_unknown_for_descriptive_check() -> None:
    """Invariant: a descriptive check is classified as 'unknown'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nR MUST be.\n\n## Checks\n\n- The sky is blue.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    assert ir["skills"][0]["checks"][0]["oracle_kind"] == "unknown"


# ---------------------------------------------------------------------------
# Evidence and limitation
# ---------------------------------------------------------------------------

def test_evidence_names_check_id() -> None:
    """Invariant: the evidence mentions the check id. Mutation: omit
    the check id -> red (untraceable)."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n\n"
            "## Checks\n\n- The sky is blue.\n"
        ),
    })
    no_oracle = _findings_by_class(audit, "CHECK_WITHOUT_ORACLE")
    assert len(no_oracle) >= 1
    assert "check-" in no_oracle[0]["evidence"]


def test_has_limitation_documented() -> None:
    """Invariant: the finding documents that oracle_kind extraction is
    pattern-based. Mutation: claim full coverage -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n\n"
            "## Checks\n\n- The sky is blue.\n"
        ),
    })
    no_oracle = _findings_by_class(audit, "CHECK_WITHOUT_ORACLE")
    assert len(no_oracle) >= 1
    assert no_oracle[0]["limitation"] is not None
    assert "pattern" in no_oracle[0]["limitation"].lower()


def test_has_source_evidence() -> None:
    """Invariant: the finding points to the check. Mutation: emit
    without source_span -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n\n"
            "## Checks\n\n- The sky is blue.\n"
        ),
    })
    no_oracle = _findings_by_class(audit, "CHECK_WITHOUT_ORACLE")
    assert len(no_oracle) >= 1
    assert no_oracle[0]["source_span"] is not None
    assert no_oracle[0]["rule_id"] is not None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_is_deterministic() -> None:
    """Invariant: two audits produce the same digest. Mutation: introduce
    non-determinism -> red."""
    corpus = {
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n\n"
            "## Checks\n\n- The sky is blue.\n"
        ),
    }
    audit1 = _audit(corpus)
    audit2 = _audit(corpus)
    assert audit1["audit_digest"] == audit2["audit_digest"]


def test_not_in_limitations() -> None:
    """Invariant: CHECK_WITHOUT_ORACLE is no longer in the abstained
    limitations list. Mutation: leave it in limitations -> red."""
    audit = _audit({
        "empty": (
            "---\nname: empty\ndescription: E.\nlicense: Apache-2.0\n---\n\n"
            "# E\n\nNo rules here.\n"
        ),
    })
    limitation_classes = [l["check_class"] for l in audit["limitations"]]
    assert "CHECK_WITHOUT_ORACLE" not in limitation_classes
