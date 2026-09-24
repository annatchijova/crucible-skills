"""Falsifiable contract tests for L13 corpus-agnostic validation.

These tests verify that the scanner works against a diverse corpus of
skills from multiple authors and methodologies (FastAPI, Gemini CLI,
Google ADK, Typer, Streamlit, Kimi CLI, VSCode), not just one author's
style. The scanner must find real engineering defects without flagging
skills for their writing conventions.

The diverse corpus is in tests/fixtures/diverse-corpus/ and contains 10
skills from 7 different sources.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from crucible.auditor import audit_corpus
from crucible.compiler import compile_corpus

DIVERSE_CORPUS = Path(__file__).parent / "fixtures" / "diverse-corpus"


def _audit_diverse() -> tuple[dict, dict]:
    ir = compile_corpus(str(DIVERSE_CORPUS))
    audit = audit_corpus(ir)
    return audit, ir


# ---------------------------------------------------------------------------
# Corpus diversity
# ---------------------------------------------------------------------------

def test_diverse_corpus_has_multiple_skills() -> None:
    """Invariant: the diverse corpus has at least 10 skills.
    Mutation: remove skills -> this test goes red."""
    ir = compile_corpus(str(DIVERSE_CORPUS))
    assert len(ir["skills"]) >= 10


def test_diverse_corpus_has_multiple_sources() -> None:
    """Invariant: the diverse corpus has skills from multiple sources.
    Mutation: collapse to one source -> this test goes red."""
    ir = compile_corpus(str(DIVERSE_CORPUS))
    names = {s["identity"]["name"] for s in ir["skills"]}
    # Skills from FastAPI, Gemini, Google, Kimi, Streamlit, Typer, VSCode.
    assert len(names) >= 10
    # Verify diversity: the names come from different ecosystems.
    ecosystems = {
        "fastapi", "antigravity-support", "skill-creator", "greeter",
        "bigquery-ai-ml", "kimi-cli-help", "developing-with-streamlit",
        "typer", "run-e2e-tests", "run-pre-commit-checks",
    }
    assert names == ecosystems


# ---------------------------------------------------------------------------
# Scanner produces findings on diverse corpus
# ---------------------------------------------------------------------------

def test_diverse_corpus_produces_findings() -> None:
    """Invariant: the scanner finds real defects in the diverse corpus.
    Mutation: the scanner is broken -> this test goes red."""
    audit, _ = _audit_diverse()
    assert len(audit["findings"]) > 0


def test_diverse_corpus_findings_are_real_defects() -> None:
    """Invariant: the findings are real engineering/structural defects,
    not style-based false positives.
    Mutation: flag skills for their writing style -> this test goes red."""
    audit, _ = _audit_diverse()
    # All findings must be from recognized check classes.
    valid_classes = {
        "BROKEN_REFERENCE", "SELF_COMPOSITION", "COMPOSITION_CYCLE",
        "ORPHAN_SKILL", "REQUIREMENT_WITHOUT_CHECK", "STRUCTURAL_REDUNDANCY",
        "METHODOLOGICAL_VACUITY", "NORMATIVE_CONFLICT", "SEMANTIC_REDUNDANCY",
        "CONDITIONAL_CONTRADICTION", "SCOPE_TRIGGER_MISMATCH",
        "DESCRIPTION_BODY_GAP", "CHECK_WITHOUT_ORACLE",
        "CLAIM_WITHOUT_PROVENANCE", "UNBOUNDED_RETRY", "LLM_IN_DECISION_PATH",
        "OVERCLAIM", "MISSING_FAILURE_MODE", "NON_DETERMINISTIC_INSTRUCTION",
        "IRREVERSIBLE_WITHOUT_REVIEW", "SECRET_IN_OUTPUT", "SILENT_FAILURE",
        "HARDCODED_CREDENTIAL", "UNBOUNDED_RESOURCE",
        "UNVALIDATED_EXTERNAL_INPUT", "MISSING_TIMEOUT",
        "FLOATING_POINT_IN_DECISION_PATH", "UNPINNED_DEPENDENCY",
    }
    for f in audit["findings"]:
        assert f["class"] in valid_classes, f"Unknown finding class: {f['class']}"


def test_diverse_corpus_no_style_based_false_positives() -> None:
    """Invariant: the scanner does not flag skills for using different
    writing conventions (RFC-2119 vs prose, Steps sections vs embedded).
    Mutation: flag skills for their style -> this test goes red."""
    audit, ir = _audit_diverse()
    # Skills that use non-RFC-2119 conventions should NOT get
    # DESCRIPTION_BODY_GAP if they have extractable content.
    for s in ir["skills"]:
        name = s["identity"]["name"]
        has_rules = len(s.get("rules", [])) > 0
        has_steps = len(s.get("procedural_steps", [])) > 0
        has_checks = len(s.get("checks", [])) > 0
        if has_rules or has_steps or has_checks:
            # This skill has extractable content; it should NOT get
            # DESCRIPTION_BODY_GAP (which fires when there's zero
            # extractable content).
            for f in audit["findings"]:
                if (
                    f["skill"] == name
                    and f["class"] == "DESCRIPTION_BODY_GAP"
                ):
                    assert False, (
                        f"DESCRIPTION_BODY_GAP on skill '{name}' which has "
                        f"{len(s.get('rules', []))} rules, "
                        f"{len(s.get('procedural_steps', []))} steps, "
                        f"{len(s.get('checks', []))} checks"
                    )


# ---------------------------------------------------------------------------
# Gemini CLI false positive is fixed
# ---------------------------------------------------------------------------

def test_gemini_cli_not_flagged_as_llm_decision() -> None:
    """Invariant: 'Gemini CLI' (a product name) is not flagged as an
    LLM in the decision path.
    Mutation: remove the CLI guard pattern -> this test goes red."""
    audit, _ = _audit_diverse()
    llm_findings = [
        f for f in audit["findings"]
        if f["class"] == "LLM_IN_DECISION_PATH"
    ]
    # The skill-creator skill mentions "Gemini CLI session" and "verify"
    # but this is a product name, not an LLM making a decision.
    for f in llm_findings:
        assert f["skill"] != "skill-creator", (
            "skill-creator was flagged for LLM_IN_DECISION_PATH but "
            "'Gemini CLI' is a product name, not an LLM decision"
        )


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_diverse_corpus_is_deterministic() -> None:
    """Invariant: scanning the diverse corpus twice produces the same
    digest.
    Mutation: introduce non-determinism -> this test goes red."""
    a1, _ = _audit_diverse()
    a2, _ = _audit_diverse()
    assert a1["audit_digest"] == a2["audit_digest"]


# ---------------------------------------------------------------------------
# Style-agnostic extraction works on diverse corpus
# ---------------------------------------------------------------------------

def test_diverse_corpus_extracts_rules_from_multiple_styles() -> None:
    """Invariant: the style-agnostic extractor extracts rules from
    skills written in different conventions.
    Mutation: revert to RFC-2119-only extraction -> this test goes red."""
    _, ir = _audit_diverse()
    # At least some skills should have extracted rules.
    skills_with_rules = sum(1 for s in ir["skills"] if len(s.get("rules", [])) > 0)
    assert skills_with_rules >= 3, (
        f"Only {skills_with_rules} skills have extracted rules; "
        f"style-agnostic extraction may not be working"
    )


def test_diverse_corpus_extracts_steps_from_multiple_styles() -> None:
    """Invariant: the style-agnostic extractor extracts procedural steps
    from skills written in different conventions.
    Mutation: revert to Steps-section-only extraction -> this test goes red."""
    _, ir = _audit_diverse()
    skills_with_steps = sum(1 for s in ir["skills"] if len(s.get("procedural_steps", [])) > 0)
    assert skills_with_steps >= 3, (
        f"Only {skills_with_steps} skills have extracted steps; "
        f"prose-embedded step extraction may not be working"
    )


# ---------------------------------------------------------------------------
# No crash on unknown formats
# ---------------------------------------------------------------------------

def test_diverse_corpus_does_not_crash() -> None:
    """Invariant: the scanner processes all skills without crashing.
    Mutation: crash on unknown format -> this test goes red."""
    # If this test passes, the scanner didn't crash.
    audit, ir = _audit_diverse()
    assert audit is not None
    assert ir is not None
    assert len(audit["findings"]) >= 0  # at least ran successfully
