"""Falsifiable contract tests for the extended L2 checks:
METHODOLOGICAL_VACUITY and NORMATIVE_CONFLICT.

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
# METHODOLOGICAL_VACUITY
# ---------------------------------------------------------------------------

def test_vacuity_detected_when_rules_but_no_steps_no_checks() -> None:
    """Invariant: a skill with normative rules but 0 procedural steps and
    0 checks is flagged as METHODOLOGICAL_VACUITY. Mutation: skip the
    check -> red (vacuous skills pass silently)."""
    audit = _audit({
        "vacuous": (
            "---\nname: vacuous\ndescription: V.\nlicense: Apache-2.0\n---\n\n"
            "# V\n\nRetries MUST have a finite budget.\n"
        ),
    })
    vacuity = _findings_by_class(audit, "METHODOLOGICAL_VACUITY")
    assert len(vacuity) == 1
    assert vacuity[0]["skill"] == "vacuous"
    assert "0 procedural steps and 0 checks" in vacuity[0]["evidence"]


def test_vacuity_not_detected_when_skill_has_steps() -> None:
    """Invariant: a skill with normative rules AND procedural steps is NOT
    flagged. Mutation: flag any skill with rules -> red (false positive)."""
    audit = _audit({
        "methodical": (
            "---\nname: methodical\ndescription: M.\nlicense: Apache-2.0\n---\n\n"
            "# M\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n2. Compare to budget.\n"
        ),
    })
    vacuity = _findings_by_class(audit, "METHODOLOGICAL_VACUITY")
    assert len(vacuity) == 0


def test_vacuity_not_detected_when_skill_has_checks() -> None:
    """Invariant: a skill with normative rules AND checks is NOT flagged.
    Mutation: flag any skill with rules -> red (false positive)."""
    audit = _audit({
        "checked": (
            "---\nname: checked\ndescription: C.\nlicense: Apache-2.0\n---\n\n"
            "# C\n\nRetries MUST have a finite budget.\n\n"
            "## Checks\n\n- Verify the budget is finite.\n"
        ),
    })
    vacuity = _findings_by_class(audit, "METHODOLOGICAL_VACUITY")
    assert len(vacuity) == 0


def test_vacuity_not_detected_when_skill_has_no_rules() -> None:
    """Invariant: a skill with no normative rules is NOT flagged.
    Mutation: flag skills without rules -> red (false positive)."""
    audit = _audit({
        "descriptive": (
            "---\nname: descriptive\ndescription: D.\nlicense: Apache-2.0\n---\n\n"
            "# D\n\nThis skill provides guidance on retry strategies.\n"
        ),
    })
    vacuity = _findings_by_class(audit, "METHODOLOGICAL_VACUITY")
    assert len(vacuity) == 0


def test_vacuity_finding_has_source_evidence() -> None:
    """Invariant: the finding points to the first normative rule.
    Mutation: emit finding without source_span -> red."""
    audit = _audit({
        "vacuous": (
            "---\nname: vacuous\ndescription: V.\nlicense: Apache-2.0\n---\n\n"
            "# V\n\nRetries MUST have a finite budget.\n"
        ),
    })
    vacuity = _findings_by_class(audit, "METHODOLOGICAL_VACUITY")
    assert len(vacuity) == 1
    assert vacuity[0]["source_span"] is not None
    assert vacuity[0]["rule_id"] is not None


def test_vacuity_has_limitation_documented() -> None:
    """Invariant: the finding documents its limitation (procedural step
    extraction is section-heading based). Mutation: claim full coverage
    -> red."""
    audit = _audit({
        "vacuous": (
            "---\nname: vacuous\ndescription: V.\nlicense: Apache-2.0\n---\n\n"
            "# V\n\nRetries MUST have a finite budget.\n"
        ),
    })
    vacuity = _findings_by_class(audit, "METHODOLOGICAL_VACUITY")
    assert len(vacuity) == 1
    assert vacuity[0]["limitation"] is not None
    assert "procedural" in vacuity[0]["limitation"].lower()


# ---------------------------------------------------------------------------
# NORMATIVE_CONFLICT
# ---------------------------------------------------------------------------

def test_conflict_detected_when_must_and_must_not_same_subject() -> None:
    """Invariant: two rules with the same subject and opposite modalities
    (MUST vs MUST_NOT) are flagged as NORMATIVE_CONFLICT. Mutation: skip
    the check -> red (contradictions pass silently)."""
    audit = _audit({
        "conflicted": (
            "---\nname: conflicted\ndescription: C.\nlicense: Apache-2.0\n---\n\n"
            "# C\n\n"
            "Retries MUST have a finite budget.\n\n"
            "Retries MUST NOT have a finite budget.\n"
        ),
    })
    conflicts = _findings_by_class(audit, "NORMATIVE_CONFLICT")
    assert len(conflicts) >= 1
    assert conflicts[0]["epistemic_status"] == "CONFIRMED"
    assert "retries" in conflicts[0]["evidence"].lower()


def test_conflict_detected_across_skills() -> None:
    """Invariant: two rules in different skills with the same subject and
    opposite modalities are flagged. Mutation: only check within-skill
    -> red (cross-skill contradictions pass)."""
    audit = _audit({
        "skill-a": (
            "---\nname: skill-a\ndescription: A.\nlicense: Apache-2.0\n---\n\n"
            "# A\n\nRetries MUST have a finite budget.\n\n"
            "## Checks\n\n- Verify budget.\n"
        ),
        "skill-b": (
            "---\nname: skill-b\ndescription: B.\nlicense: Apache-2.0\n---\n\n"
            "# B\n\nRetries MUST NOT have a finite budget.\n\n"
            "## Checks\n\n- Verify no budget.\n"
        ),
    })
    conflicts = _findings_by_class(audit, "NORMATIVE_CONFLICT")
    assert len(conflicts) >= 1
    assert "skill-a" in conflicts[0]["evidence"]
    assert "skill-b" in conflicts[0]["evidence"]


def test_conflict_detected_should_vs_should_not() -> None:
    """Invariant: SHOULD vs SHOULD_NOT for the same subject is also a
    conflict. Mutation: only check MUST vs MUST_NOT -> red."""
    audit = _audit({
        "conflicted": (
            "---\nname: conflicted\ndescription: C.\nlicense: Apache-2.0\n---\n\n"
            "# C\n\n"
            "The operation SHOULD be idempotent.\n\n"
            "The operation SHOULD NOT be idempotent.\n"
        ),
    })
    conflicts = _findings_by_class(audit, "NORMATIVE_CONFLICT")
    assert len(conflicts) >= 1


def test_no_conflict_when_same_modality_same_subject() -> None:
    """Invariant: two rules with the same subject and same modality are
    NOT a conflict. Mutation: flag any duplicate subject -> red."""
    audit = _audit({
        "redundant": (
            "---\nname: redundant\ndescription: R.\nlicense: Apache-2.0\n---\n\n"
            "# R\n\n"
            "Retries MUST have a finite budget.\n\n"
            "Retries MUST be bounded by a maximum count.\n"
        ),
    })
    conflicts = _findings_by_class(audit, "NORMATIVE_CONFLICT")
    assert len(conflicts) == 0


def test_no_conflict_when_different_subjects() -> None:
    """Invariant: two rules with different subjects and opposite
    modalities are NOT a conflict. Mutation: flag any opposite modality
    -> red (false positive)."""
    audit = _audit({
        "different": (
            "---\nname: different\ndescription: D.\nlicense: Apache-2.0\n---\n\n"
            "# D\n\n"
            "Retries MUST have a finite budget.\n\n"
            "Logging MUST NOT be verbose.\n"
        ),
    })
    conflicts = _findings_by_class(audit, "NORMATIVE_CONFLICT")
    assert len(conflicts) == 0


def test_conflict_finding_has_source_evidence() -> None:
    """Invariant: the finding points to the first rule of the conflict.
    Mutation: emit finding without source_span -> red."""
    audit = _audit({
        "conflicted": (
            "---\nname: conflicted\ndescription: C.\nlicense: Apache-2.0\n---\n\n"
            "# C\n\n"
            "Retries MUST have a finite budget.\n\n"
            "Retries MUST NOT have a finite budget.\n"
        ),
    })
    conflicts = _findings_by_class(audit, "NORMATIVE_CONFLICT")
    assert len(conflicts) >= 1
    assert conflicts[0]["source_span"] is not None
    assert conflicts[0]["rule_id"] is not None


def test_conflict_has_limitation_documented() -> None:
    """Invariant: the finding documents its limitation (subject extraction
    is lexical). Mutation: claim full coverage -> red."""
    audit = _audit({
        "conflicted": (
            "---\nname: conflicted\ndescription: C.\nlicense: Apache-2.0\n---\n\n"
            "# C\n\n"
            "Retries MUST have a finite budget.\n\n"
            "Retries MUST NOT have a finite budget.\n"
        ),
    })
    conflicts = _findings_by_class(audit, "NORMATIVE_CONFLICT")
    assert len(conflicts) >= 1
    assert conflicts[0]["limitation"] is not None
    assert "lexical" in conflicts[0]["limitation"].lower()


def test_conflict_not_in_limitations_list() -> None:
    """Invariant: NORMATIVE_CONFLICT is no longer in the abstained
    limitations list (it's now implemented). Mutation: leave it in
    limitations -> red (claim it's abstained when it's not)."""
    audit = _audit({
        "empty": (
            "---\nname: empty\ndescription: E.\nlicense: Apache-2.0\n---\n\n"
            "# E\n\nNo rules here.\n"
        ),
    })
    limitation_classes = [l["check_class"] for l in audit["limitations"]]
    assert "NORMATIVE_CONFLICT" not in limitation_classes


# ---------------------------------------------------------------------------
# Modality extraction fix
# ---------------------------------------------------------------------------

def test_must_not_is_captured_correctly() -> None:
    """Invariant: 'MUST NOT' is captured as 'MUST_NOT', not 'MUST'.
    Mutation: revert the regex fix -> red (negated rules misclassified)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nRetries MUST NOT be unbounded.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    rules = ir["skills"][0]["rules"]
    assert len(rules) == 1
    assert rules[0]["modality"] == "MUST_NOT"


def test_should_not_is_captured_correctly() -> None:
    """Invariant: 'SHOULD NOT' is captured as 'SHOULD_NOT', not 'SHOULD'.
    Mutation: revert the regex fix -> red."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nLogging SHOULD NOT be verbose.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    rules = ir["skills"][0]["rules"]
    assert len(rules) == 1
    assert rules[0]["modality"] == "SHOULD_NOT"


# ---------------------------------------------------------------------------
# Subject extraction
# ---------------------------------------------------------------------------

def test_subject_extracted_from_rule() -> None:
    """Invariant: each rule has a subject (the noun phrase before the
    modal verb). Mutation: skip subject extraction -> red."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nRetries MUST have a finite budget.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    rules = ir["skills"][0]["rules"]
    assert len(rules) == 1
    assert rules[0]["subject"] == "retries"


def test_subject_normalized_strips_articles() -> None:
    """Invariant: 'The operation' is normalized to 'operation'.
    Mutation: don't normalize -> red (same subject not detected)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nThe operation MUST be idempotent.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    rules = ir["skills"][0]["rules"]
    assert rules[0]["subject"] == "operation"


# ---------------------------------------------------------------------------
# Procedural steps extraction
# ---------------------------------------------------------------------------

def test_procedural_steps_extracted_from_steps_section() -> None:
    """Invariant: numbered lists in ## Steps sections are extracted as
    procedural steps. Mutation: skip extraction -> red."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nRetries MUST be bounded.\n\n"
            "## Steps\n\n1. Check count.\n2. Compare to budget.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    steps = ir["skills"][0]["procedural_steps"]
    assert len(steps) == 2
    assert "Check count" in steps[0]["text"]
    assert "Compare to budget" in steps[1]["text"]


def test_procedural_steps_extracted_from_numbered_list_anywhere() -> None:
    """Invariant: numbered lists anywhere in the body are extracted.
    Mutation: only extract from ## Steps -> red."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nRetries MUST be bounded.\n\n"
            "1. First do this.\n2. Then do that.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    steps = ir["skills"][0]["procedural_steps"]
    assert len(steps) == 2


def test_no_procedural_steps_when_no_numbered_list() -> None:
    """Invariant: a skill with only prose has 0 procedural steps.
    Mutation: extract steps from prose -> red (false positive)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nRetries MUST be bounded. This is important.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    steps = ir["skills"][0]["procedural_steps"]
    assert len(steps) == 0
