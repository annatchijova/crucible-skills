"""Falsifiable contract tests for the L5 behavioral differential harness.

Each test names the invariant it defends and the mutation it would catch.
Tests use the LocalExecutor (deterministic) to verify the harness without
external dependencies. Nebius execution is tested for correct BLOCKED behavior
when the API key is absent.
"""

from __future__ import annotations

from crucible.behavioral import (
    BEHAVIORAL_VERSION,
    LocalExecutor,
    MissingCredentialError,
    NebiusExecutor,
    TASK_FIXTURE,
    ALL_VARIANTS,
    run_behavioral_differential,
    run_property_oracle,
)


# ---------------------------------------------------------------------------
# Report structure
# ---------------------------------------------------------------------------

def test_report_is_versioned_and_sealed() -> None:
    """Invariant: the report carries a version and a SHA-256 digest.
    Mutation: remove BEHAVIORAL_VERSION or digest -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    assert report["behavioral_version"] == BEHAVIORAL_VERSION
    assert report["behavioral_digest"].startswith("sha256:")


def test_report_is_deterministic_with_local_executor() -> None:
    """Invariant: the same local executor produces the same digest.
    Mutation: inject nondeterminism -> red."""
    first = run_behavioral_differential(executor=LocalExecutor())
    second = run_behavioral_differential(executor=LocalExecutor())
    assert first == second
    assert first["behavioral_digest"] == second["behavioral_digest"]


def test_report_contains_all_four_variants() -> None:
    """Invariant: all 4 variants (no-skill, original, mutant, repair) are present.
    Mutation: drop a variant -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    assert len(report["runs"]) == 4
    variant_ids = {r["variant_id"] for r in report["runs"]}
    assert "V1-no-skill" in variant_ids
    assert "V2-original" in variant_ids
    assert "V3-mutant-polarity-inversion" in variant_ids
    assert "V4-repair" in variant_ids


def test_task_fixture_is_sealed() -> None:
    """Invariant: the task fixture has a deterministic digest.
    Mutation: change the task prompt without updating the digest -> red."""
    assert TASK_FIXTURE["task_digest"].startswith("sha256:")
    # The digest must be stable.
    import hashlib, json
    canonical = json.dumps(
        {"task_id": TASK_FIXTURE["task_id"], "task_prompt": TASK_FIXTURE["task_prompt"]},
        ensure_ascii=False, sort_keys=True,
    )
    expected = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert TASK_FIXTURE["task_digest"] == expected


# ---------------------------------------------------------------------------
# Property oracle
# ---------------------------------------------------------------------------

def test_property_oracle_passes_on_budget_mention() -> None:
    """Invariant: P1 passes when the output mentions a finite budget.
    Mutation: remove 'finite' from the check -> red."""
    observations = run_property_oracle(
        "Use a finite retry budget of 5 attempts.",
        TASK_FIXTURE["properties"],
    )
    p1 = next(o for o in observations if o["property_id"] == "P1-mentions-budget")
    assert p1["status"] == "PASS"


def test_property_oracle_fails_on_no_budget() -> None:
    """Invariant: P1 fails when the output does not mention a budget.
    Mutation: always PASS P1 -> red."""
    observations = run_property_oracle(
        "Just retry until it works.",
        TASK_FIXTURE["properties"],
    )
    p1 = next(o for o in observations if o["property_id"] == "P1-mentions-budget")
    assert p1["status"] == "FAIL"


def test_property_oracle_passes_on_exception() -> None:
    """Invariant: P2 passes when the output mentions an exception.
    Mutation: remove 'except' from the check -> red."""
    observations = run_property_oracle(
        "Retry with a budget, except for read-only operations.",
        TASK_FIXTURE["properties"],
    )
    p2 = next(o for o in observations if o["property_id"] == "P2-respects-exception")
    assert p2["status"] == "PASS"


def test_property_oracle_fails_on_no_exception() -> None:
    """Invariant: P2 fails when the output does not mention exceptions.
    Mutation: always PASS P2 -> red."""
    observations = run_property_oracle(
        "Retry with a budget of 5.",
        TASK_FIXTURE["properties"],
    )
    p2 = next(o for o in observations if o["property_id"] == "P2-respects-exception")
    assert p2["status"] == "FAIL"


def test_property_oracle_detects_unbounded_retry() -> None:
    """Invariant: P3 fails when the output recommends unbounded retry.
    Mutation: remove the unbounded check -> red."""
    observations = run_property_oracle(
        "Retries should not be bounded by a finite budget. "
        "Continue retrying until the operation succeeds.",
        TASK_FIXTURE["properties"],
    )
    p3 = next(o for o in observations if o["property_id"] == "P3-no-unbounded-retry")
    assert p3["status"] == "FAIL"


def test_property_oracle_passes_no_unbounded_when_bounded() -> None:
    """Invariant: P3 passes when the output is bounded.
    Mutation: always FAIL P3 -> red."""
    observations = run_property_oracle(
        "Use a finite retry budget of 5 attempts.",
        TASK_FIXTURE["properties"],
    )
    p3 = next(o for o in observations if o["property_id"] == "P3-no-unbounded-retry")
    assert p3["status"] == "PASS"


def test_property_oracle_passes_on_idempotency() -> None:
    """Invariant: P4 passes when the output mentions idempotency.
    Mutation: remove 'idempotent' from the check -> red."""
    observations = run_property_oracle(
        "Ensure the operation is idempotent before retrying.",
        TASK_FIXTURE["properties"],
    )
    p4 = next(o for o in observations if o["property_id"] == "P4-mentions-idempotency")
    assert p4["status"] == "PASS"


def test_property_oracle_fails_on_no_idempotency() -> None:
    """Invariant: P4 fails when the output does not mention idempotency.
    Mutation: always PASS P4 -> red."""
    observations = run_property_oracle(
        "Retry with a budget of 5.",
        TASK_FIXTURE["properties"],
    )
    p4 = next(o for o in observations if o["property_id"] == "P4-mentions-idempotency")
    assert p4["status"] == "FAIL"


def test_property_oracle_abstains_on_unknown_check() -> None:
    """Invariant: an unknown check function produces ABSTAINED, not a crash.
    Mutation: raise on unknown check -> red."""
    observations = run_property_oracle(
        "Some output.",
        [{"property_id": "PX-unknown", "description": "Unknown", "check": "nonexistent"}],
    )
    assert observations[0]["status"] == "ABSTAINED"


# ---------------------------------------------------------------------------
# Behavioral differential with LocalExecutor
# ---------------------------------------------------------------------------

def test_local_executor_original_skill_passes_all_properties() -> None:
    """Invariant: the original skill variant passes all 4 properties.
    Mutation: the local executor ignores the skill text -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    original = next(r for r in report["runs"] if r["variant_id"] == "V2-original")
    assert original["status"] == "COMPLETED"
    for obs in original["observations"]:
        assert obs["status"] == "PASS", (
            f"{obs['property_id']} should PASS for original skill"
        )


def test_local_executor_mutant_fails_unbounded_check() -> None:
    """Invariant: the polarity-inversion mutant fails P3 (unbounded retry).
    Mutation: the local executor follows the original skill instead of the
    mutant -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    mutant = next(r for r in report["runs"] if r["variant_id"] == "V3-mutant-polarity-inversion")
    p3 = next(o for o in mutant["observations"] if o["property_id"] == "P3-no-unbounded-retry")
    assert p3["status"] == "FAIL"


def test_local_executor_no_skill_fails_budget() -> None:
    """Invariant: the no-skill variant fails P1 (no budget mentioned).
    Mutation: the local executor mentions budget without skill guidance -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    no_skill = next(r for r in report["runs"] if r["variant_id"] == "V1-no-skill")
    p1 = next(o for o in no_skill["observations"] if o["property_id"] == "P1-mentions-budget")
    assert p1["status"] == "FAIL"


def test_local_executor_repair_passes_all_properties() -> None:
    """Invariant: the repair variant passes all 4 properties.
    Mutation: the repair skill text is wrong -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    repair = next(r for r in report["runs"] if r["variant_id"] == "V4-repair")
    for obs in repair["observations"]:
        assert obs["status"] == "PASS", (
            f"{obs['property_id']} should PASS for repair variant"
        )


def test_differential_shows_behavioral_difference() -> None:
    """Invariant: the differential summary shows different property outcomes
    across variants. Mutation: all variants produce the same output -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    summary = report["differential_summary"]
    by_variant = summary["by_variant_property"]
    # The no-skill variant should fail P1; the original should pass P1.
    assert by_variant["V1-no-skill"]["P1-mentions-budget"] == "FAIL"
    assert by_variant["V2-original"]["P1-mentions-budget"] == "PASS"
    # The mutant should fail P3; the original should pass P3.
    assert by_variant["V3-mutant-polarity-inversion"]["P3-no-unbounded-retry"] == "FAIL"
    assert by_variant["V2-original"]["P3-no-unbounded-retry"] == "PASS"


# ---------------------------------------------------------------------------
# Nebius executor: honest BLOCKED behavior
# ---------------------------------------------------------------------------

def test_nebius_executor_reports_blocked_without_key(monkeypatch) -> None:
    """Invariant: without NEBIUS_API_KEY, the Nebius executor reports BLOCKED,
    not a fake success. Mutation: simulate success without a key -> red."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    executor = NebiusExecutor()
    assert not executor.is_available()
    report = run_behavioral_differential(executor=executor)
    assert report["nebius_blocked"] is True
    assert report["block_reason"] is not None
    for run in report["runs"]:
        assert run["status"] == "BLOCKED"


def test_nebius_blocked_report_includes_local_fallback(monkeypatch) -> None:
    """Invariant: when Nebius is blocked, the report includes a local fallback
    run for harness verification. Mutation: skip the fallback -> red."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    executor = NebiusExecutor()
    report = run_behavioral_differential(executor=executor)
    assert report["nebius_blocked"] is True
    assert report["local_fallback_runs"] is not None
    assert len(report["local_fallback_runs"]) == 4
    # The local fallback should have COMPLETED status.
    for run in report["local_fallback_runs"]:
        assert run["status"] == "COMPLETED"


def test_nebius_executor_raises_without_key(monkeypatch) -> None:
    """Invariant: calling execute() without a key raises MissingCredentialError.
    Mutation: return a fake response -> red."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    executor = NebiusExecutor()
    try:
        executor.execute("system", "user")
    except MissingCredentialError:
        pass
    else:
        raise AssertionError("should raise MissingCredentialError without a key")


# ---------------------------------------------------------------------------
# Evidence and chain of custody
# ---------------------------------------------------------------------------

def test_every_run_has_output_digest() -> None:
    """Invariant: every completed run has an output_digest.
    Mutation: skip the digest -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    for run in report["runs"]:
        if run["status"] == "COMPLETED":
            assert run["output_digest"].startswith("sha256:")


def test_every_run_has_model_metadata() -> None:
    """Invariant: every run records model, provider, temperature.
    Mutation: drop metadata -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    for run in report["runs"]:
        assert run["model"]
        assert run["provider"]
        assert "temperature" in run


def test_limitations_are_documented() -> None:
    """Invariant: the report documents 3 limitations honestly.
    Mutation: remove limitations -> red."""
    report = run_behavioral_differential(executor=LocalExecutor())
    assert len(report["limitations"]) >= 3
    classes = {lim["check_class"] for lim in report["limitations"]}
    assert "SEMANTIC_QUALITY" in classes
    assert "MODEL_STABILITY" in classes


# ---------------------------------------------------------------------------
# LLM out of the decision path
# ---------------------------------------------------------------------------

def test_property_oracle_is_deterministic() -> None:
    """Invariant: the property oracle produces the same result for the same
    output. Mutation: inject randomness into the oracle -> red."""
    output = "Use a finite retry budget of 5, except for read-only operations."
    first = run_property_oracle(output, TASK_FIXTURE["properties"])
    second = run_property_oracle(output, TASK_FIXTURE["properties"])
    assert first == second


def test_model_output_does_not_affect_oracle_logic() -> None:
    """Invariant: the oracle checks properties of the text, not the model's
    intent. Two different texts with the same keyword produce the same
    verdict. Mutation: the oracle interprets intent -> red."""
    obs1 = run_property_oracle("finite budget", TASK_FIXTURE["properties"])
    obs2 = run_property_oracle(
        "I will use a finite budget for the retry mechanism.",
        TASK_FIXTURE["properties"],
    )
    p1_1 = next(o for o in obs1 if o["property_id"] == "P1-mentions-budget")
    p1_2 = next(o for o in obs2 if o["property_id"] == "P1-mentions-budget")
    assert p1_1["status"] == p1_2["status"] == "PASS"


# ---------------------------------------------------------------------------
# D2 regression: negation detection in property oracle
# ---------------------------------------------------------------------------

def test_d2_p1_fails_on_negated_budget() -> None:
    """D2 regression: P1 fails when the output says the budget is NOT
    needed. Mutation: revert to keyword-only matching -> red."""
    observations = run_property_oracle(
        "The budget is not needed for this operation.",
        TASK_FIXTURE["properties"],
    )
    p1 = next(o for o in observations if o["property_id"] == "P1-mentions-budget")
    assert p1["status"] == "FAIL"


def test_d2_p2_fails_on_negated_exception() -> None:
    """D2 regression: P2 fails when the output says there is NO exception.
    Mutation: revert to keyword-only matching -> red."""
    observations = run_property_oracle(
        "There is no exception to this rule.",
        TASK_FIXTURE["properties"],
    )
    p2 = next(o for o in observations if o["property_id"] == "P2-respects-exception")
    assert p2["status"] == "FAIL"


def test_d2_p1_passes_on_non_negated_budget() -> None:
    """D2 regression: P1 still passes when the budget is mentioned without
    negation. Mutation: over-correct negation detection -> red."""
    observations = run_property_oracle(
        "Use a finite retry budget of 5 attempts.",
        TASK_FIXTURE["properties"],
    )
    p1 = next(o for o in observations if o["property_id"] == "P1-mentions-budget")
    assert p1["status"] == "PASS"


def test_d2_p2_passes_on_non_negated_exception() -> None:
    """D2 regression: P2 still passes when an exception is mentioned without
    negation. Mutation: over-correct negation detection -> red."""
    observations = run_property_oracle(
        "Except for read-only operations, the budget applies.",
        TASK_FIXTURE["properties"],
    )
    p2 = next(o for o in observations if o["property_id"] == "P2-respects-exception")
    assert p2["status"] == "PASS"


# ---------------------------------------------------------------------------
# D3 regression: P3 positive bound must not be negated
# ---------------------------------------------------------------------------

def test_d3_p3_fails_on_negated_bound_with_qualification() -> None:
    """D3 regression: P3 fails when the output recommends unbounded retry
    but qualifies with a bound that is itself negated. Mutation: revert
    to count-any-positive-bound -> red."""
    observations = run_property_oracle(
        "Retries should not be bounded by a finite budget. "
        "However, use a budget of 3 attempts as a guideline.",
        TASK_FIXTURE["properties"],
    )
    p3 = next(o for o in observations if o["property_id"] == "P3-no-unbounded-retry")
    assert p3["status"] == "FAIL"


def test_d3_p3_passes_on_genuine_positive_bound() -> None:
    """D3 regression: P3 passes when the output has a genuine positive
    bound without negation. Mutation: over-correct the bound check -> red."""
    observations = run_property_oracle(
        "Use a finite budget of 5 attempts for retries.",
        TASK_FIXTURE["properties"],
    )
    p3 = next(o for o in observations if o["property_id"] == "P3-no-unbounded-retry")
    assert p3["status"] == "PASS"
