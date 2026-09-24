"""Falsifiable contract tests for the CONDITIONAL_CONTRADICTION check.

Each test has a positive and negative fixture. The mutation comment
describes what would make the test go red if the invariant is violated.
"""

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

def test_contradiction_detected_exception_vs_scope() -> None:
    """Invariant: a rule with an exception and a rule with a scope on
    the same condition, same subject, same modality, but opposite
    effective polarity -> CONDITIONAL_CONTRADICTION. Mutation: skip the
    check -> red (conditional contradictions pass silently)."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded, except for read-only operations.\n\n"
            "Retries MUST be bounded for read-only operations.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) >= 1
    assert contradictions[0]["epistemic_status"] == "CONFIRMED"
    assert "read-only" in contradictions[0]["evidence"]


def test_contradiction_detected_unconditional_vs_conditional() -> None:
    """Invariant: an unconditional MUST and a conditional exception
    (MUST ... except for X) on the same subject conflict under X.
    Mutation: only check both-conditional pairs -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded.\n\n"
            "Retries MUST be bounded, except for read-only operations.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) >= 1


def test_contradiction_detected_across_skills() -> None:
    """Invariant: two rules in different skills with the same subject
    and conflicting conditions are detected. Mutation: only check
    within-skill -> red."""
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: A.\nlicense: Apache-2.0\n---\n\n"
            "# A\n\n"
            "Retries MUST be bounded, except for read-only operations.\n\n"
            "## Checks\n\n- Verify budget.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: B.\nlicense: Apache-2.0\n---\n\n"
            "# B\n\n"
            "Retries MUST be bounded for read-only operations.\n\n"
            "## Checks\n\n- Verify budget.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) >= 1


# ---------------------------------------------------------------------------
# No false positives
# ---------------------------------------------------------------------------

def test_no_contradiction_when_same_polarity() -> None:
    """Invariant: two rules with the same subject, same condition, same
    effective polarity are NOT a contradiction. Mutation: flag any
    shared condition -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded for read-only operations.\n\n"
            "Retries MUST be bounded for read-only operations.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) == 0


def test_no_contradiction_when_different_conditions() -> None:
    """Invariant: two rules with the same subject but non-overlapping
    conditions are NOT a contradiction. Mutation: flag any shared
    subject -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded for read-only operations.\n\n"
            "Retries MUST be bounded for write operations.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) == 0


def test_no_contradiction_when_no_conditions() -> None:
    """Invariant: two rules with the same subject and no conditions are
    NOT a conditional contradiction (NORMATIVE_CONFLICT handles those).
    Mutation: flag unconditional pairs -> red (duplicate NORMATIVE_CONFLICT)."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded.\n\n"
            "Retries MUST be fast.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) == 0


def test_no_contradiction_when_different_subjects() -> None:
    """Invariant: two rules with different subjects are NOT a
    contradiction. Mutation: flag any pair with conditions -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded, except for read-only operations.\n\n"
            "Logging MUST be verbose for read-only operations.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) == 0


def test_no_contradiction_when_normative_conflict_handles_it() -> None:
    """Invariant: unconditional MUST vs MUST_NOT is NORMATIVE_CONFLICT,
    not CONDITIONAL_CONTRADICTION. Mutation: also emit
    CONDITIONAL_CONTRADICTION -> red (duplicate)."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded.\n\n"
            "Retries MUST NOT be bounded.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) == 0
    conflicts = _findings_by_class(audit, "NORMATIVE_CONFLICT")
    assert len(conflicts) >= 1


# ---------------------------------------------------------------------------
# Evidence and limitation
# ---------------------------------------------------------------------------

def test_contradiction_evidence_names_condition() -> None:
    """Invariant: the evidence mentions the condition under which the
    conflict occurs. Mutation: omit the condition -> red (untraceable)."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded, except for read-only operations.\n\n"
            "Retries MUST be bounded for read-only operations.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) >= 1
    assert "read-only" in contradictions[0]["evidence"]


def test_contradiction_has_limitation_documented() -> None:
    """Invariant: the finding documents that condition extraction is
    pattern-based. Mutation: claim full coverage -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded, except for read-only operations.\n\n"
            "Retries MUST be bounded for read-only operations.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) >= 1
    assert contradictions[0]["limitation"] is not None
    assert "pattern" in contradictions[0]["limitation"].lower()


def test_contradiction_has_source_evidence() -> None:
    """Invariant: the finding points to the first rule of the conflict.
    Mutation: emit finding without source_span -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded, except for read-only operations.\n\n"
            "Retries MUST be bounded for read-only operations.\n"
        ),
    })
    contradictions = _findings_by_class(audit, "CONDITIONAL_CONTRADICTION")
    assert len(contradictions) >= 1
    assert contradictions[0]["source_span"] is not None
    assert contradictions[0]["rule_id"] is not None


# ---------------------------------------------------------------------------
# Condition extraction
# ---------------------------------------------------------------------------

def test_conditions_extracted_from_rule() -> None:
    """Invariant: each rule has a conditions list. Mutation: skip
    extraction -> red (no conditions to compare)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nRetries MUST be bounded, except for read-only operations.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    rules = ir["skills"][0]["rules"]
    assert len(rules) == 1
    conditions = rules[0]["conditions"]
    assert len(conditions) >= 1
    assert any(c["text"] == "read-only operations" for c in conditions)


def test_exception_type_extracted() -> None:
    """Invariant: 'except for X' is extracted as type 'exception'.
    Mutation: extract as 'scope' -> red (polarity not inverted)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nRetries MUST be bounded, except for read-only operations.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    conditions = ir["skills"][0]["rules"][0]["conditions"]
    exceptions = [c for c in conditions if c["type"] == "exception"]
    assert len(exceptions) >= 1
    assert exceptions[0]["text"] == "read-only operations"


def test_scope_type_extracted() -> None:
    """Invariant: 'for X' is extracted as type 'scope'. Mutation: extract
    as 'exception' -> red (polarity wrongly inverted)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nRetries MUST be bounded for read-only operations.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    conditions = ir["skills"][0]["rules"][0]["conditions"]
    scopes = [c for c in conditions if c["type"] == "scope"]
    assert len(scopes) >= 1
    assert scopes[0]["text"] == "read-only operations"


def test_unless_extracted_as_exception() -> None:
    """Invariant: 'unless X' is extracted as type 'exception'.
    Mutation: extract as 'scope' -> red."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nLogging SHOULD NOT be verbose unless debugging.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    conditions = ir["skills"][0]["rules"][0]["conditions"]
    exceptions = [c for c in conditions if c["type"] == "exception"]
    assert len(exceptions) >= 1
    assert "debugging" in exceptions[0]["text"]


def test_when_extracted_as_scope() -> None:
    """Invariant: 'when X' is extracted as type 'scope'.
    Mutation: extract as 'exception' -> red."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nLogging SHOULD be verbose when debugging.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    conditions = ir["skills"][0]["rules"][0]["conditions"]
    scopes = [c for c in conditions if c["type"] == "scope"]
    assert len(scopes) >= 1
    assert "debugging" in scopes[0]["text"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_contradiction_is_deterministic() -> None:
    """Invariant: two audits of the same corpus produce the same digest.
    Mutation: introduce non-determinism -> red."""
    corpus = {
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\n"
            "Retries MUST be bounded, except for read-only operations.\n\n"
            "Retries MUST be bounded for read-only operations.\n"
        ),
    }
    audit1 = _audit(corpus)
    audit2 = _audit(corpus)
    assert audit1["audit_digest"] == audit2["audit_digest"]


def test_contradiction_not_in_limitations() -> None:
    """Invariant: CONDITIONAL_CONTRADICTION is no longer in the
    abstained limitations list (it's now implemented). Mutation: leave
    it in limitations -> red."""
    audit = _audit({
        "empty": (
            "---\nname: empty\ndescription: E.\nlicense: Apache-2.0\n---\n\n"
            "# E\n\nNo rules here.\n"
        ),
    })
    limitation_classes = [l["check_class"] for l in audit["limitations"]]
    assert "CONDITIONAL_CONTRADICTION" not in limitation_classes
