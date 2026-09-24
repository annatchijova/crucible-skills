"""Falsifiable contract tests for the L7 closed repair loop.

Each test has a positive and negative fixture. The mutation comment
describes what would make the test go red if the invariant is violated.
"""

from __future__ import annotations

from crucible.behavioral import LocalExecutor, TASK_FIXTURE
from crucible.bob import RuleBasedProposer
from crucible.repair_loop import (
    LOOP_VERSION,
    OUTCOME_BEHAVIORAL_REGRESSION,
    run_repair_loop,
)
from crucible.bob import OUTCOME_ACCEPTED, OUTCOME_REJECTED, OUTCOME_BLOCKED


# ---------------------------------------------------------------------------
# Acceptance: good repair passes both deterministic and behavioral
# ---------------------------------------------------------------------------

def test_good_repair_is_accepted() -> None:
    """Invariant: a repair that fixes the finding AND passes behavioral
    replay is ACCEPTED. Mutation: skip behavioral replay -> red (would
    accept repairs that break behavior)."""
    report = run_repair_loop(executor=LocalExecutor())
    assert report["loop_version"] == LOOP_VERSION
    assert report["outcome"] == OUTCOME_ACCEPTED
    assert report["rejection_reason"] is None
    assert report["original_finding_gone"] is True
    assert report["no_new_findings"] is True
    assert report["behavioral_replay"] is not None
    assert report["behavioral_replay"]["regression"] is False
    assert report["loop_digest"].startswith("sha256:")


# ---------------------------------------------------------------------------
# Rejection: repair that doesn't fix the finding
# ---------------------------------------------------------------------------

def test_noop_repair_is_rejected_finding_persists() -> None:
    """Invariant: a no-op repair is REJECTED with FINDING_PERSISTS.
    Mutation: accept no-op repairs -> red."""

    class NoOpProposer:
        def propose(self, finding, skill_text, context):
            return {
                "proposed_text": skill_text,
                "rationale": "no-op",
                "proposer": "no-op",
            }

    report = run_repair_loop(proposer=NoOpProposer(), executor=LocalExecutor())
    assert report["outcome"] == OUTCOME_REJECTED
    assert report["rejection_reason"] == "FINDING_PERSISTS"
    assert report["original_finding_gone"] is False
    # Behavioral replay is skipped when deterministic check fails.
    assert report["behavioral_replay"] is None


# ---------------------------------------------------------------------------
# Rejection: repair that introduces a new finding
# ---------------------------------------------------------------------------

def test_repair_introducing_new_finding_is_rejected() -> None:
    """Invariant: a repair that introduces a new finding is REJECTED
    with NEW_FINDINGS. Mutation: only check finding gone -> red."""

    class BrokenRefProposer:
        def propose(self, finding, skill_text, context):
            # Add checks (fixes REQUIREMENT_WITHOUT_CHECK) but add a
            # broken reference (introduces BROKEN_REFERENCE).
            proposed = skill_text + "\n## Checks\n\n- Verify.\n"
            proposed = proposed + "\n## Composes with\n\n- ghost-skill\n"
            return {
                "proposed_text": proposed,
                "rationale": "added checks + broken ref",
                "proposer": "broken-ref",
            }

    report = run_repair_loop(proposer=BrokenRefProposer(), executor=LocalExecutor())
    assert report["outcome"] == OUTCOME_REJECTED
    assert report["rejection_reason"] == "NEW_FINDINGS"
    assert report["original_finding_gone"] is True
    assert "BROKEN_REFERENCE" in report["repaired_findings"]


# ---------------------------------------------------------------------------
# Rejection: behavioral regression
# ---------------------------------------------------------------------------

def test_behavioral_regression_is_rejected() -> None:
    """Invariant: a repair that fixes the finding deterministically but
    introduces a behavioral regression is REJECTED with
    BEHAVIORAL_REGRESSION. Mutation: skip behavioral replay -> red
    (would accept a repair that breaks behavior)."""

    class PolarityFlipProposer:
        def propose(self, finding, skill_text, context):
            # Add checks (fixes REQUIREMENT_WITHOUT_CHECK) but also
            # flip MUST to MUST NOT (introduces unbounded retry).
            proposed = skill_text.replace(
                "Retries MUST have a finite budget",
                "Retries MUST NOT have a finite budget",
            )
            proposed = proposed + "\n## Checks\n\n- Verify.\n"
            return {
                "proposed_text": proposed,
                "rationale": "added checks but flipped polarity",
                "proposer": "polarity-flip",
            }

    report = run_repair_loop(proposer=PolarityFlipProposer(), executor=LocalExecutor())
    # The deterministic check passes (finding is gone, no new findings).
    assert report["original_finding_gone"] is True
    assert report["no_new_findings"] is True
    # But the behavioral replay catches the regression.
    assert report["outcome"] == OUTCOME_REJECTED
    assert report["rejection_reason"] == OUTCOME_BEHAVIORAL_REGRESSION
    assert report["behavioral_replay"] is not None
    assert report["behavioral_replay"]["regression"] is True
    # The regression must be in P3 (no unbounded retry).
    regression_props = [r["property_id"] for r in report["behavioral_replay"]["regressions"]]
    assert "P3-no-unbounded-retry" in regression_props


# ---------------------------------------------------------------------------
# Rejection: compile error
# ---------------------------------------------------------------------------

def test_compile_error_repair_is_rejected() -> None:
    """Invariant: a repair that breaks compilation is REJECTED with
    COMPILE_ERROR. Mutation: skip compile check -> red."""

    class BadFormatProposer:
        def propose(self, finding, skill_text, context):
            # Produce invalid frontmatter that will fail compilation.
            return {
                "proposed_text": "---\nname: \n---\n\nbroken",
                "rationale": "broken frontmatter",
                "proposer": "bad-format",
            }

    report = run_repair_loop(proposer=BadFormatProposer(), executor=LocalExecutor())
    assert report["outcome"] == OUTCOME_REJECTED
    assert report["rejection_reason"] == "COMPILE_ERROR"


# ---------------------------------------------------------------------------
# No findings
# ---------------------------------------------------------------------------

def test_no_findings_produces_no_findings_report() -> None:
    """Invariant: a corpus with no findings produces NO_FINDINGS.
    Mutation: crash on empty findings -> red."""
    corpus = {
        "gate": (
            "---\nname: gate\n"
            "description: Gate operations.\n"
            "license: Apache-2.0\n---\n\n"
            "# Gate\n\n"
            "Operations MUST be bounded.\n\n"
            "## Checks\n\n- Verify bounded.\n"
        ),
    }
    report = run_repair_loop(corpus=corpus, executor=LocalExecutor())
    assert report["outcome"] == "NO_FINDINGS"
    assert report["finding"] is None


# ---------------------------------------------------------------------------
# Blocked LLM proposer
# ---------------------------------------------------------------------------

def test_blocked_llm_proposer_produces_blocked_report(monkeypatch) -> None:
    """Invariant: without NEBIUS_API_KEY, the LLM proposer is BLOCKED.
    Mutation: simulate LLM output -> red."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    from crucible.bob import LLMProposer
    report = run_repair_loop(proposer=LLMProposer(), executor=LocalExecutor())
    assert report["outcome"] == OUTCOME_BLOCKED
    assert report["proposal"]["blocked"] is True
    assert "NEBIUS_API_KEY" in report["proposal"]["rationale"]


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_same_process_determinism() -> None:
    """Invariant: two runs in the same process produce the same digest.
    Mutation: non-deterministic field in the report -> red."""
    r1 = run_repair_loop(executor=LocalExecutor())
    r2 = run_repair_loop(executor=LocalExecutor())
    assert r1["loop_digest"] == r2["loop_digest"]
    assert r1["outcome"] == r2["outcome"]


def test_cross_process_determinism() -> None:
    """Invariant: two runs in different processes produce the same digest.
    Mutation: PYTHONHASHSEED or set ordering leaks into the digest -> red."""
    import subprocess
    results = []
    for _ in range(2):
        out = subprocess.run(
            ["python3", "-c",
             "from crucible.repair_loop import run_repair_loop; "
             "from crucible.behavioral import LocalExecutor; "
             "r = run_repair_loop(executor=LocalExecutor()); "
             "print(r['loop_digest'], r['outcome'])"],
            capture_output=True, text=True,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/usr/local/bin",
                 "PYTHONHASHSEED": "0"},
        )
        results.append(out.stdout.strip().split())
    assert results[0] == results[1], f"cross-process divergence: {results}"
    assert results[0][1] == OUTCOME_ACCEPTED


# ---------------------------------------------------------------------------
# LLM out of the decision path
# ---------------------------------------------------------------------------

def test_llm_does_not_affect_outcome() -> None:
    """Invariant: swapping the proposer changes the proposal text but
    not the outcome when the deterministic and behavioral criteria are
    met. Mutation: LLM in the decision path -> red (outcome would change
    with the proposer)."""

    class CustomProposer:
        def propose(self, finding, skill_text, context):
            proposed = skill_text + "\n## Checks\n\n- Verify the requirement.\n"
            return {
                "proposed_text": proposed,
                "rationale": "custom rationale",
                "proposer": "custom",
            }

    r1 = run_repair_loop(proposer=RuleBasedProposer(), executor=LocalExecutor())
    r2 = run_repair_loop(proposer=CustomProposer(), executor=LocalExecutor())
    # Both should be ACCEPTED (both fix the finding and pass behavioral).
    assert r1["outcome"] == OUTCOME_ACCEPTED
    assert r2["outcome"] == OUTCOME_ACCEPTED
    # The proposers are different but the outcome is the same.
    assert r1["proposal"]["proposer"] != r2["proposal"]["proposer"]
    # The digests differ (different proposed text) but the outcome is the same.
    assert r1["loop_digest"] != r2["loop_digest"]


# ---------------------------------------------------------------------------
# Behavioral replay details
# ---------------------------------------------------------------------------

def test_behavioral_replay_records_observations() -> None:
    """Invariant: the behavioral replay records observations for both
    original and repaired. Mutation: skip recording -> red."""
    report = run_repair_loop(executor=LocalExecutor())
    replay = report["behavioral_replay"]
    assert replay is not None
    assert "original_observations" in replay
    assert "repaired_observations" in replay
    assert len(replay["original_observations"]) == 4
    assert len(replay["repaired_observations"]) == 4
    # Original passes all 4 properties.
    for obs in replay["original_observations"]:
        assert obs["status"] == "PASS"
    # Repaired also passes all 4 properties (no regression).
    for obs in replay["repaired_observations"]:
        assert obs["status"] == "PASS"


# ---------------------------------------------------------------------------
# Nebius blocked status
# ---------------------------------------------------------------------------

def test_nebius_blocked_status_is_honest(monkeypatch) -> None:
    """Invariant: without NEBIUS_API_KEY, the report documents Nebius
    as BLOCKED and uses LocalExecutor. Mutation: simulate Nebius -> red."""
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    report = run_repair_loop()  # no executor -> tries Nebius -> falls back
    assert report["nebius_blocked"] is True
    assert "NEBIUS_API_KEY" in (report["block_reason"] or "")
    assert report["executor"]["type"] == "LocalExecutor"
