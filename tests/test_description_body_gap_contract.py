"""Falsifiable contract tests for the DESCRIPTION_BODY_GAP check."""

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

def test_gap_detected_when_description_substantive_but_body_empty() -> None:
    """Invariant: a skill with a substantive description but zero rules,
    checks, and procedural steps is flagged. Mutation: skip the check
    -> red."""
    audit = _audit({
        "gap": (
            "---\nname: gap\n"
            "description: Use this skill when debugging memory leaks in C programs. "
            "It helps find leaks with valgrind and other tools.\n"
            "license: Apache-2.0\n---\n\n"
            "# Gap\n\nThis skill helps you find memory leaks.\n"
        ),
    })
    gaps = _findings_by_class(audit, "DESCRIPTION_BODY_GAP")
    assert len(gaps) >= 1
    assert gaps[0]["epistemic_status"] == "CANDIDATE"


def test_gap_not_detected_when_body_has_rules() -> None:
    """Invariant: a skill with rules in the body is NOT flagged.
    Mutation: flag any skill -> red."""
    audit = _audit({
        "nogap": (
            "---\nname: nogap\n"
            "description: Use this skill when debugging memory leaks in C programs. "
            "It helps find leaks with valgrind and other tools.\n"
            "license: Apache-2.0\n---\n\n"
            "# NoGap\n\nMemory MUST be freed after allocation.\n"
        ),
    })
    gaps = _findings_by_class(audit, "DESCRIPTION_BODY_GAP")
    assert len(gaps) == 0


def test_gap_not_detected_when_body_has_checks() -> None:
    """Invariant: a skill with checks in the body is NOT flagged.
    Mutation: flag any skill with checks -> red."""
    audit = _audit({
        "nogap": (
            "---\nname: nogap\n"
            "description: Use this skill when debugging memory leaks in C programs. "
            "It helps find leaks with valgrind and other tools.\n"
            "license: Apache-2.0\n---\n\n"
            "# NoGap\n\n"
            "## Checks\n\n- Verify no leaks with valgrind.\n"
        ),
    })
    gaps = _findings_by_class(audit, "DESCRIPTION_BODY_GAP")
    assert len(gaps) == 0


def test_gap_not_detected_when_body_has_procedural_steps() -> None:
    """Invariant: a skill with procedural steps in the body is NOT
    flagged. Mutation: flag any skill with steps -> red."""
    audit = _audit({
        "nogap": (
            "---\nname: nogap\n"
            "description: Use this skill when debugging memory leaks in C programs. "
            "It helps find leaks with valgrind and other tools.\n"
            "license: Apache-2.0\n---\n\n"
            "# NoGap\n\n"
            "## Steps\n\n1. Run valgrind.\n2. Analyze output.\n"
        ),
    })
    gaps = _findings_by_class(audit, "DESCRIPTION_BODY_GAP")
    assert len(gaps) == 0


def test_gap_not_detected_when_description_too_short() -> None:
    """Invariant: a skill with a very short description is NOT flagged
    (not enough substance to promise anything). Mutation: flag short
    descriptions -> red."""
    audit = _audit({
        "short": (
            "---\nname: short\ndescription: A skill.\n"
            "license: Apache-2.0\n---\n\n"
            "# Short\n\nNo rules here.\n"
        ),
    })
    gaps = _findings_by_class(audit, "DESCRIPTION_BODY_GAP")
    assert len(gaps) == 0


# ---------------------------------------------------------------------------
# Evidence and limitation
# ---------------------------------------------------------------------------

def test_gap_evidence_mentions_token_count() -> None:
    """Invariant: the evidence mentions the description token count.
    Mutation: omit the count -> red (untraceable)."""
    audit = _audit({
        "gap": (
            "---\nname: gap\n"
            "description: Use this skill when debugging memory leaks in C programs. "
            "It helps find leaks with valgrind and other tools.\n"
            "license: Apache-2.0\n---\n\n"
            "# Gap\n\nThis skill helps you find memory leaks.\n"
        ),
    })
    gaps = _findings_by_class(audit, "DESCRIPTION_BODY_GAP")
    assert len(gaps) >= 1
    assert "meaningful tokens" in gaps[0]["evidence"]
    assert "0 rules" in gaps[0]["evidence"]


def test_gap_has_limitation_documented() -> None:
    """Invariant: the finding documents that the extractor is
    conservative. Mutation: claim full coverage -> red."""
    audit = _audit({
        "gap": (
            "---\nname: gap\n"
            "description: Use this skill when debugging memory leaks in C programs. "
            "It helps find leaks with valgrind and other tools.\n"
            "license: Apache-2.0\n---\n\n"
            "# Gap\n\nThis skill helps you find memory leaks.\n"
        ),
    })
    gaps = _findings_by_class(audit, "DESCRIPTION_BODY_GAP")
    assert len(gaps) >= 1
    assert gaps[0]["limitation"] is not None
    assert "conservative" in gaps[0]["limitation"].lower()
    assert "non-RFC-2119" in gaps[0]["limitation"]


# ---------------------------------------------------------------------------
# Distinction from METHODOLOGICAL_VACUITY
# ---------------------------------------------------------------------------

def test_gap_distinct_from_vacuity() -> None:
    """Invariant: DESCRIPTION_BODY_GAP detects skills with NO structure;
    METHODOLOGICAL_VACUITY detects skills WITH rules but NO steps/checks.
    A skill with rules but no steps should get VACUITY, not GAP.
    Mutation: flag vacuous skills as GAP -> red (duplicate)."""
    audit = _audit({
        "vacuous": (
            "---\nname: vacuous\n"
            "description: Use this skill when debugging memory leaks in C programs. "
            "It helps find leaks with valgrind and other tools.\n"
            "license: Apache-2.0\n---\n\n"
            "# Vacuous\n\nMemory MUST be freed after allocation.\n"
        ),
    })
    gaps = _findings_by_class(audit, "DESCRIPTION_BODY_GAP")
    assert len(gaps) == 0
    vacuity = _findings_by_class(audit, "METHODOLOGICAL_VACUITY")
    assert len(vacuity) >= 1


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_gap_is_deterministic() -> None:
    """Invariant: two audits produce the same digest. Mutation: introduce
    non-determinism -> red."""
    corpus = {
        "gap": (
            "---\nname: gap\n"
            "description: Use this skill when debugging memory leaks in C programs. "
            "It helps find leaks with valgrind and other tools.\n"
            "license: Apache-2.0\n---\n\n"
            "# Gap\n\nThis skill helps you find memory leaks.\n"
        ),
    }
    audit1 = _audit(corpus)
    audit2 = _audit(corpus)
    assert audit1["audit_digest"] == audit2["audit_digest"]


def test_gap_not_in_limitations() -> None:
    """Invariant: DESCRIPTION_BODY_GAP is no longer in the abstained
    limitations list. Mutation: leave it in limitations -> red."""
    audit = _audit({
        "empty": (
            "---\nname: empty\ndescription: E.\nlicense: Apache-2.0\n---\n\n"
            "# E\n\nNo rules here.\n"
        ),
    })
    limitation_classes = [l["check_class"] for l in audit["limitations"]]
    assert "DESCRIPTION_BODY_GAP" not in limitation_classes
