"""Falsifiable contract tests for the L2 deterministic auditor.

Each test names the invariant it defends and the mutation it would catch.
"""

from __future__ import annotations

import json
from pathlib import Path

from crucible.auditor import AUDIT_VERSION, audit_corpus
from crucible.compiler import compile_corpus


def _write_skill(root: Path, name: str, body: str) -> Path:
    skill = root / name
    skill.mkdir()
    (skill / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")
    return skill


def _audit(root: Path) -> dict:
    return audit_corpus(compile_corpus(root))


def _classes(findings: list[dict]) -> list[str]:
    return sorted(f["class"] for f in findings)


# ---------------------------------------------------------------------------
# BROKEN_REFERENCE
# ---------------------------------------------------------------------------

def test_broken_reference_fires_on_missing_target(tmp_path: Path) -> None:
    """Invariant: a composition target must resolve to an existing skill.
    Mutation: skip the name_set lookup -> this test goes red."""
    _write_skill(
        tmp_path,
        "retrier",
        "---\nname: retrier\ndescription: Retry operations.\n---\n\n"
        "# Composes with\n\n- ghost-skill\n",
    )
    audit = _audit(tmp_path)
    assert "BROKEN_REFERENCE" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "BROKEN_REFERENCE")
    assert finding["epistemic_status"] == "CONFIRMED"
    assert "ghost-skill" in finding["evidence"]
    assert finding["skill"] == "retrier"


def test_broken_reference_does_not_fire_on_valid_target(tmp_path: Path) -> None:
    """Invariant: a resolvable target must not produce a false positive.
    Mutation: always emit BROKEN_REFERENCE -> this test goes red."""
    _write_skill(
        tmp_path,
        "gate",
        "---\nname: gate\ndescription: Gate operations.\n---\n\nA MUST stop.\n",
    )
    _write_skill(
        tmp_path,
        "retrier",
        "---\nname: retrier\ndescription: Retry.\n---\n\n"
        "# Composes with\n\n- gate\n",
    )
    audit = _audit(tmp_path)
    assert "BROKEN_REFERENCE" not in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# SELF_COMPOSITION
# ---------------------------------------------------------------------------

def test_self_composition_fires_on_self_reference(tmp_path: Path) -> None:
    """Invariant: a skill must not compose with itself.
    Mutation: remove the self-name check -> this test goes red."""
    _write_skill(
        tmp_path,
        "loopy",
        "---\nname: loopy\ndescription: Loops.\n---\n\n"
        "# Composes with\n\n- loopy\n",
    )
    audit = _audit(tmp_path)
    assert "SELF_COMPOSITION" in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# COMPOSITION_CYCLE
# ---------------------------------------------------------------------------

def test_composition_cycle_fires_on_two_node_cycle(tmp_path: Path) -> None:
    """Invariant: the composition graph must be acyclic.
    Mutation: skip cycle detection -> this test goes red."""
    _write_skill(
        tmp_path,
        "alpha",
        "---\nname: alpha\ndescription: A.\n---\n\n# Composes with\n\n- beta\n",
    )
    _write_skill(
        tmp_path,
        "beta",
        "---\nname: beta\ndescription: B.\n---\n\n# Composes with\n\n- alpha\n",
    )
    audit = _audit(tmp_path)
    assert "COMPOSITION_CYCLE" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "COMPOSITION_CYCLE")
    assert "alpha" in finding["evidence"]
    assert "beta" in finding["evidence"]


def test_composition_cycle_does_not_fire_on_acyclic_graph(tmp_path: Path) -> None:
    """Invariant: a DAG must not produce a cycle finding.
    Mutation: always emit COMPOSITION_CYCLE -> this test goes red."""
    _write_skill(
        tmp_path,
        "alpha",
        "---\nname: alpha\ndescription: A.\n---\n\n# Composes with\n\n- beta\n",
    )
    _write_skill(
        tmp_path,
        "beta",
        "---\nname: beta\ndescription: B.\n---\n\n",
    )
    audit = _audit(tmp_path)
    assert "COMPOSITION_CYCLE" not in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# ORPHAN_SKILL
# ---------------------------------------------------------------------------

def test_orphan_skill_fires_when_graph_exists_and_skill_is_disconnected(
    tmp_path: Path,
) -> None:
    """Invariant: ORPHAN_SKILL is an observation about disconnection in a
    non-empty graph. Mutation: always emit ORPHAN_SKILL -> the empty-graph
    test below goes red."""
    _write_skill(
        tmp_path,
        "alpha",
        "---\nname: alpha\ndescription: A.\n---\n\n# Composes with\n\n- beta\n",
    )
    _write_skill(
        tmp_path,
        "beta",
        "---\nname: beta\ndescription: B.\n---\n\n",
    )
    _write_skill(
        tmp_path,
        "lonely",
        "---\nname: lonely\ndescription: L.\n---\n\n",
    )
    audit = _audit(tmp_path)
    orphans = [f for f in audit["findings"] if f["class"] == "ORPHAN_SKILL"]
    assert len(orphans) == 1
    assert orphans[0]["skill"] == "lonely"
    assert orphans[0]["epistemic_status"] == "OBSERVATION"


def test_orphan_skill_does_not_fire_when_graph_is_empty(tmp_path: Path) -> None:
    """Invariant: an empty relation graph must not flag every skill as
    orphan. Mutation: remove the has_any_edge guard -> this test goes red."""
    _write_skill(
        tmp_path,
        "solo",
        "---\nname: solo\ndescription: S.\n---\n\nA MUST stop.\n",
    )
    audit = _audit(tmp_path)
    assert "ORPHAN_SKILL" not in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# REQUIREMENT_WITHOUT_CHECK
# ---------------------------------------------------------------------------

def test_requirement_without_check_fires_on_rules_no_checks(tmp_path: Path) -> None:
    """Invariant: a MUST/SHOULD rule with no extracted checks is a candidate
    gap. Mutation: invert the `if not rules or checks` guard -> red."""
    _write_skill(
        tmp_path,
        "strict",
        "---\nname: strict\ndescription: Strict.\n---\n\n"
        "The operation MUST be idempotent.\n",
    )
    audit = _audit(tmp_path)
    assert "REQUIREMENT_WITHOUT_CHECK" in _classes(audit["findings"])
    finding = next(
        f for f in audit["findings"] if f["class"] == "REQUIREMENT_WITHOUT_CHECK"
    )
    assert finding["epistemic_status"] == "CANDIDATE"
    assert finding["limitation"] is not None


def test_requirement_without_check_does_not_fire_when_checks_exist(
    tmp_path: Path,
) -> None:
    """Invariant: a skill with both rules and checks must not trigger the
    gap. Mutation: ignore the checks count -> red."""
    _write_skill(
        tmp_path,
        "covered",
        "---\nname: covered\ndescription: Covered.\n---\n\n"
        "The operation MUST be idempotent.\n\n## Checks\n\n- Verify idempotency.\n",
    )
    audit = _audit(tmp_path)
    assert "REQUIREMENT_WITHOUT_CHECK" not in _classes(audit["findings"])


def test_requirement_without_check_ignores_may_only_rules(tmp_path: Path) -> None:
    """Invariant: MAY is permissive, not a requirement; a MAY-only skill with
    no checks is not a requirement-without-check gap."""
    _write_skill(
        tmp_path,
        "permissive",
        "---\nname: permissive\ndescription: P.\n---\n\nA MAY run.\n",
    )
    audit = _audit(tmp_path)
    assert "REQUIREMENT_WITHOUT_CHECK" not in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# STRUCTURAL_REDUNDANCY
# ---------------------------------------------------------------------------

def test_structural_redundancy_fires_on_duplicate_rule_text(tmp_path: Path) -> None:
    """Invariant: identical rule text across skills is a candidate redundancy.
    Mutation: skip the len < 2 check -> red."""
    body = (
        "---\nname: {name}\ndescription: D.\n---\n\n"
        "The operation MUST be bounded.\n"
    )
    _write_skill(tmp_path, "skill-a", body.format(name="skill-a"))
    _write_skill(tmp_path, "skill-b", body.format(name="skill-b"))
    audit = _audit(tmp_path)
    assert "STRUCTURAL_REDUNDANCY" in _classes(audit["findings"])
    finding = next(
        f for f in audit["findings"] if f["class"] == "STRUCTURAL_REDUNDANCY"
    )
    assert finding["epistemic_status"] == "CANDIDATE"
    assert "skill-a" in finding["evidence"]
    assert "skill-b" in finding["evidence"]


def test_structural_redundancy_does_not_fire_on_unique_rules(tmp_path: Path) -> None:
    """Invariant: distinct rule text must not trigger redundancy.
    Mutation: always emit STRUCTURAL_REDUNDANCY -> red."""
    _write_skill(
        tmp_path,
        "skill-a",
        "---\nname: skill-a\ndescription: A.\n---\n\nAlpha MUST be first.\n",
    )
    _write_skill(
        tmp_path,
        "skill-b",
        "---\nname: skill-b\ndescription: B.\n---\n\nBeta MUST be second.\n",
    )
    audit = _audit(tmp_path)
    assert "STRUCTURAL_REDUNDANCY" not in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# Determinism and artifact integrity
# ---------------------------------------------------------------------------

def test_same_input_produces_identical_audit_digest(tmp_path: Path) -> None:
    """Invariant: the audit is deterministic. Mutation: inject a timestamp
    or unordered set into the payload -> red."""
    _write_skill(
        tmp_path,
        "stable",
        "---\nname: stable\ndescription: S.\n---\n\n"
        "A MUST stop.\n\n# Composes with\n\n- ghost\n",
    )
    first = _audit(tmp_path)
    second = _audit(tmp_path)
    assert first == second
    assert first["audit_digest"] == second["audit_digest"]
    assert first["audit_digest"].startswith("sha256:")


def test_audit_version_is_stamped(tmp_path: Path) -> None:
    """Invariant: the artifact carries a version. Mutation: remove AUDIT_VERSION
    -> red."""
    _write_skill(tmp_path, "v", "---\nname: v\ndescription: V.\n---\n\nA MUST stop.\n")
    audit = _audit(tmp_path)
    assert audit["audit_version"] == AUDIT_VERSION


def test_audit_rejects_wrong_schema_version() -> None:
    """Invariant: the auditor must fail closed on an incompatible input.
    Mutation: accept any schema_version -> red."""
    try:
        audit_corpus({"schema_version": "wrong", "artifact_digest": "x", "skills": []})
    except ValueError as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("wrong schema_version must be rejected")


def test_limitations_are_documented(tmp_path: Path) -> None:
    """Invariant: abstained checks are explicit, not silently passed.
    Mutation: remove the limitations list -> red."""
    _write_skill(tmp_path, "l", "---\nname: l\ndescription: L.\n---\n\nA MUST stop.\n")
    audit = _audit(tmp_path)
    assert len(audit["limitations"]) >= 2
    classes = {lim["check_class"] for lim in audit["limitations"]}
    assert "CHECK_WITHOUT_ORACLE" in classes
    assert "CLAIM_WITHOUT_PROVENANCE" in classes


def test_findings_carry_source_evidence(tmp_path: Path) -> None:
    """Invariant: every finding points to a skill and carries evidence text.
    Mutation: drop the evidence or skill field -> red."""
    _write_skill(
        tmp_path,
        "evidenced",
        "---\nname: evidenced\ndescription: E.\n---\n\n"
        "A MUST stop.\n\n# Composes with\n\n- ghost\n",
    )
    audit = _audit(tmp_path)
    for finding in audit["findings"]:
        assert finding["skill"] is not None
        assert finding["source_path"] is not None
        assert finding["evidence"]
        assert finding["class"]
        assert finding["epistemic_status"]


def test_summary_counts_match_findings(tmp_path: Path) -> None:
    """Invariant: the summary is a faithful count of the findings.
    Mutation: hardcode the summary -> red."""
    _write_skill(
        tmp_path,
        "counted",
        "---\nname: counted\ndescription: C.\n---\n\n"
        "A MUST stop.\n\n# Composes with\n\n- ghost\n",
    )
    audit = _audit(tmp_path)
    assert audit["summary"]["total"] == len(audit["findings"])
    class_counts = audit["summary"]["by_class"]
    for cls, count in class_counts.items():
        actual = sum(1 for f in audit["findings"] if f["class"] == cls)
        assert actual == count


# ---------------------------------------------------------------------------
# Real corpus smoke test
# ---------------------------------------------------------------------------

REAL_CORPUS = Path("/home/labestiadevigia/.codex/skills")


def test_real_corpus_audit_is_deterministic() -> None:
    """Invariant: the real corpus produces a stable, reproducible audit.
    Mutation: nondeterministic ordering or a float in the path -> red."""
    if not REAL_CORPUS.is_dir():
        import pytest
        pytest.skip("real corpus not available")
    first = audit_corpus(compile_corpus(REAL_CORPUS))
    second = audit_corpus(compile_corpus(REAL_CORPUS))
    assert first == second
    assert first["audit_digest"].startswith("sha256:")
    # The real corpus has no relation edges, so no graph-based findings.
    graph_classes = {"BROKEN_REFERENCE", "SELF_COMPOSITION", "COMPOSITION_CYCLE", "ORPHAN_SKILL"}
    emitted = {f["class"] for f in first["findings"]}
    assert not (emitted & graph_classes)
