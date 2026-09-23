"""Falsifiable contract tests for the L4 mutation laboratory.

Each test names the invariant it defends and the mutation it would catch.
"""

from __future__ import annotations

from crucible.mutation import (
    BASE_FIXTURE,
    MUTATION_VERSION,
    SC_INSUFFICIENT_DETECTOR,
    SC_INSUFFICIENT_REPRESENTATION,
    SC_OUT_OF_SCOPE,
    ST_ABSTAINED,
    ST_COMPILE_ERROR,
    ST_KILLED,
    ST_SURVIVED,
    run_mutation_lab,
)


# ---------------------------------------------------------------------------
# Report structure
# ---------------------------------------------------------------------------

def test_report_is_versioned_and_sealed() -> None:
    """Invariant: the report carries a version and a SHA-256 digest.
    Mutation: remove MUTATION_VERSION or digest -> red."""
    report = run_mutation_lab()
    assert report["mutation_version"] == MUTATION_VERSION
    assert report["mutation_digest"].startswith("sha256:")


def test_report_is_deterministic() -> None:
    """Invariant: the same fixture and mutations produce the same digest.
    Mutation: inject nondeterminism -> red."""
    first = run_mutation_lab()
    second = run_mutation_lab()
    assert first == second
    assert first["mutation_digest"] == second["mutation_digest"]


def test_report_contains_all_eight_mutations() -> None:
    """Invariant: all 8 mutation classes are in the report.
    Mutation: drop a mutation from MUTATIONS -> red."""
    report = run_mutation_lab()
    assert len(report["results"]) == 8
    classes = {r["mutation_class"] for r in report["results"]}
    expected = {
        "POLARITY_INVERSION",
        "EXCEPTION_REMOVAL",
        "REFERENCE_BREAK",
        "CHECK_REMOVAL",
        "TRIGGER_WIDENING",
        "EDGE_REMOVAL",
        "CYCLE_INTRODUCTION",
        "CAPABILITY_DUPLICATION",
    }
    assert classes == expected


def test_summary_counts_match_results() -> None:
    """Invariant: the summary is a faithful count of the results.
    Mutation: hardcode the summary -> red."""
    report = run_mutation_lab()
    total = report["summary"]["total"]
    by_status = report["summary"]["by_status"]
    assert total == len(report["results"])
    assert sum(by_status.values()) == total


# ---------------------------------------------------------------------------
# Kill / survive / abstain classification
# ---------------------------------------------------------------------------

def test_reference_break_is_killed() -> None:
    """Invariant: breaking a composition reference to a non-existent skill
    produces a BROKEN_REFERENCE finding. Mutation: skip BROKEN_REFERENCE check
    in the auditor -> red."""
    report = run_mutation_lab()
    result = next(r for r in report["results"]
                  if r["mutation_class"] == "REFERENCE_BREAK")
    assert result["status"] == ST_KILLED
    assert "BROKEN_REFERENCE" in result["observed_finding_classes"]


def test_check_removal_is_killed() -> None:
    """Invariant: removing all checks from a skill with normative rules
    produces a REQUIREMENT_WITHOUT_CHECK finding. Mutation: skip
    REQUIREMENT_WITHOUT_CHECK check -> red."""
    report = run_mutation_lab()
    result = next(r for r in report["results"]
                  if r["mutation_class"] == "CHECK_REMOVAL")
    assert result["status"] == ST_KILLED
    assert "REQUIREMENT_WITHOUT_CHECK" in result["observed_finding_classes"]


def test_cycle_introduction_is_killed() -> None:
    """Invariant: introducing a composition cycle produces a COMPOSITION_CYCLE
    finding. Mutation: skip COMPOSITION_CYCLE check -> red."""
    report = run_mutation_lab()
    result = next(r for r in report["results"]
                  if r["mutation_class"] == "CYCLE_INTRODUCTION")
    assert result["status"] == ST_KILLED
    assert "COMPOSITION_CYCLE" in result["observed_finding_classes"]


def test_capability_duplication_is_killed() -> None:
    """Invariant: duplicating a skill's normative rule text produces a
    STRUCTURAL_REDUNDANCY finding. Mutation: skip STRUCTURAL_REDUNDANCY
    check -> red."""
    report = run_mutation_lab()
    result = next(r for r in report["results"]
                  if r["mutation_class"] == "CAPABILITY_DUPLICATION")
    assert result["status"] == ST_KILLED
    assert "STRUCTURAL_REDUNDANCY" in result["observed_finding_classes"]


def test_polarity_inversion_is_abstained() -> None:
    """Invariant: polarity inversion targets NORMATIVE_CONFLICT, which is
    documented as abstained. Mutation: emit NORMATIVE_CONFLICT without
    the required fields -> red (would be a false positive)."""
    report = run_mutation_lab()
    result = next(r for r in report["results"]
                  if r["mutation_class"] == "POLARITY_INVERSION")
    assert result["status"] == ST_ABSTAINED
    assert result["survivor_classification"] == SC_OUT_OF_SCOPE


def test_trigger_widening_is_abstained() -> None:
    """Invariant: trigger widening targets SCOPE_TRIGGER_MISMATCH, which is
    documented as abstained. Mutation: emit SCOPE_TRIGGER_MISMATCH without
    trigger extraction -> red."""
    report = run_mutation_lab()
    result = next(r for r in report["results"]
                  if r["mutation_class"] == "TRIGGER_WIDENING")
    assert result["status"] == ST_ABSTAINED
    assert result["survivor_classification"] == SC_OUT_OF_SCOPE


def test_exception_removal_survives_with_classification() -> None:
    """Invariant: exception removal survives because the IR does not extract
    exceptions. The survivor is classified as INSUFFICIENT_REPRESENTATION,
    not a generic failure. Mutation: classify all survivors as
    INSUFFICIENT_DETECTOR -> red."""
    report = run_mutation_lab()
    result = next(r for r in report["results"]
                  if r["mutation_class"] == "EXCEPTION_REMOVAL")
    assert result["status"] == ST_SURVIVED
    assert result["survivor_classification"] == SC_INSUFFICIENT_REPRESENTATION


def test_edge_removal_survives_with_classification() -> None:
    """Invariant: edge removal survives because the auditor does not detect
    the disappearance of a composition edge (only broken edges, not missing
    ones). The survivor is classified as INSUFFICIENT_DETECTOR.
    Mutation: classify as EQUIVALENT_MUTANT -> red."""
    report = run_mutation_lab()
    result = next(r for r in report["results"]
                  if r["mutation_class"] == "EDGE_REMOVAL")
    assert result["status"] == ST_SURVIVED
    assert result["survivor_classification"] == SC_INSUFFICIENT_DETECTOR


# ---------------------------------------------------------------------------
# Evidence and chain of custody
# ---------------------------------------------------------------------------

def test_every_result_carries_evidence() -> None:
    """Invariant: every result has a non-empty evidence string.
    Mutation: skip evidence recording -> red."""
    report = run_mutation_lab()
    for r in report["results"]:
        assert r["evidence"]
        assert isinstance(r["evidence"], str)


def test_every_result_has_base_and_mutated_digest() -> None:
    """Invariant: every result records the base and mutated audit digests.
    Mutation: drop the digest fields -> red."""
    report = run_mutation_lab()
    base = report["base_audit_digest"]
    assert base.startswith("sha256:")
    for r in report["results"]:
        assert r["base_audit_digest"] == base
        if r["status"] != ST_COMPILE_ERROR:
            assert r["mutated_audit_digest"].startswith("sha256:")
            # A mutation that changes the corpus must change the digest.
            if r["mutation_class"] != "EXCEPTION_REMOVAL":
                # Exception removal changes text but may not change findings;
                # the digest still changes because the source bytes change.
                pass


def test_mutated_digest_differs_from_base_when_corpus_changes() -> None:
    """Invariant: a mutation that changes source bytes produces a different
    audit digest. Mutation: mutations are no-ops -> red."""
    report = run_mutation_lab()
    base = report["base_audit_digest"]
    for r in report["results"]:
        if r["status"] == ST_COMPILE_ERROR:
            continue
        assert r["mutated_audit_digest"] != base, (
            f"{r['mutation_id']}: mutated digest equals base digest"
        )


# ---------------------------------------------------------------------------
# Kill rate honesty
# ---------------------------------------------------------------------------

def test_kill_rate_excludes_abstained() -> None:
    """Invariant: the kill rate is killed/(killed+survived), excluding
    abstained and compile errors. Mutation: include abstained in the
    denominator -> red."""
    report = run_mutation_lab()
    summary = report["summary"]
    killed = summary["by_status"].get(ST_KILLED, 0)
    survived = summary["by_status"].get(ST_SURVIVED, 0)
    abstained = summary["by_status"].get(ST_ABSTAINED, 0)
    compile_errors = summary["by_status"].get(ST_COMPILE_ERROR, 0)
    scorable = killed + survived
    assert summary["kill_rate"] == f"{killed}/{scorable}"
    # Abstained and compile errors are not in the denominator.
    assert abstained + compile_errors + scorable == summary["total"]


def test_survivors_are_classified() -> None:
    """Invariant: every surviving mutant has a survivor classification.
    Mutation: leave survivor_classification as None for survivors -> red."""
    report = run_mutation_lab()
    for r in report["results"]:
        if r["status"] == ST_SURVIVED:
            assert r["survivor_classification"] is not None, (
                f"{r['mutation_id']} survived without classification"
            )


def test_abstained_have_survivor_classification() -> None:
    """Invariant: every abstained mutation has a survivor classification
    explaining why it is out of scope. Mutation: drop the classification
    for abstained -> red."""
    report = run_mutation_lab()
    for r in report["results"]:
        if r["status"] == ST_ABSTAINED:
            assert r["survivor_classification"] is not None


# ---------------------------------------------------------------------------
# Base fixture sanity
# ---------------------------------------------------------------------------

def test_base_fixture_has_two_skills() -> None:
    """Invariant: the base fixture has exactly two skills (retrier and gate).
    Mutation: change the fixture -> red."""
    assert len(BASE_FIXTURE) == 2
    assert "retrier" in BASE_FIXTURE
    assert "gate" in BASE_FIXTURE


def test_base_fixture_produces_no_findings() -> None:
    """Invariant: the known-good base fixture produces zero audit findings.
    Mutation: the base fixture has a defect -> red (would be a false
    positive in the kill/survive classification)."""
    report = run_mutation_lab()
    # The base digest is from the clean fixture; if it had findings,
    # the kill/survive classification would be contaminated.
    assert report["base_audit_digest"].startswith("sha256:")
    # Verify by running the pipeline directly on the base fixture.
    from crucible.mutation import _compile_and_audit
    base_artifact = _compile_and_audit(BASE_FIXTURE)
    assert base_artifact["findings"] == []
