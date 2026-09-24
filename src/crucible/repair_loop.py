"""Closed repair loop (L7).

Integrates L4 (mutation), L5 (behavioral differential), and L6 (Bob
workflow) into a single closed loop:

    finding (from audit)
        |
        v
    Bob proposes repair (L6)
        |
        v
    Crucible re-audits (L6 deterministic acceptance)
        |
        v
    behavioral replay: repaired vs original through property oracle (L5)
        |
        v
    accept / reject (deterministic + behavioral)

The acceptance criteria are:
- ACCEPTED if: the targeted finding is gone (L6) AND no new findings (L6)
  AND the repaired skill passes all properties that the original skill
  passed (L5 behavioral replay).
- REJECTED if: the targeted finding persists (L6) OR new findings appear
  (L6) OR the repaired skill fails a property that the original skill
  passed (L5 behavioral regression).

The behavioral replay uses the same property oracle as L5. The executor
is pluggable: LocalExecutor for deterministic testing, NebiusExecutor for
Nemotron via Nebius. Without NEBIUS_API_KEY, the behavioral replay uses
the LocalExecutor and the Nebius path is documented as BLOCKED.

The LLM never touches the decision path. Bob proposes; the property
oracle observes; Crucible decides.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from .auditor import audit_corpus
from .behavioral import (
    BEHAVIORAL_VERSION,
    LocalExecutor,
    NebiusExecutor,
    TASK_FIXTURE,
    run_property_oracle,
)
from .bob import (
    BOB_VERSION,
    OUTCOME_ACCEPTED,
    OUTCOME_REJECTED,
    OUTCOME_BLOCKED,
    OUTCOME_ERROR,
    Proposer,
    RuleBasedProposer,
    _compile_and_audit,
)
from .ir import digest_payload

LOOP_VERSION = "crucible-repair-loop/v1"

# ---------------------------------------------------------------------------
# Outcome codes
# ---------------------------------------------------------------------------

OUTCOME_BEHAVIORAL_REGRESSION = "BEHAVIORAL_REGRESSION"

REJECTION_REASONS = {
    "FINDING_PERSISTS": "the targeted finding is still present after repair",
    "NEW_FINDINGS": "the repair introduced new findings",
    "COMPILE_ERROR": "the repaired corpus does not compile",
    "NO_PROPOSAL": "the proposer did not generate a repair",
    "PROPOSAL_ERROR": "the proposer raised an error",
    "BEHAVIORAL_REGRESSION": "the repair fails a property that the original passed",
}


# ---------------------------------------------------------------------------
# Repair loop runner
# ---------------------------------------------------------------------------

def run_repair_loop(
    corpus: dict[str, str] | None = None,
    finding_index: int = 0,
    proposer: Proposer | None = None,
    executor: Any | None = None,
    task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the closed repair loop on one finding.

    1. Compile and audit the corpus to get findings.
    2. Select the finding at finding_index.
    3. Bob proposes a repair.
    4. Crucible re-compiles and re-audits the repaired corpus (L6).
    5. Behavioral replay: run repaired and original skill through the
       executor and property oracle (L5).
    6. Accept or reject based on deterministic AND behavioral criteria.

    If no corpus is given, uses LOOP_FIXTURE which has a
    REQUIREMENT_WITHOUT_CHECK finding.
    """
    if corpus is None:
        corpus = LOOP_FIXTURE
    if proposer is None:
        proposer = RuleBasedProposer()
    if task is None:
        task = TASK_FIXTURE

    # Determine executor and blocked status.
    nebius_blocked = False
    block_reason = None
    if executor is None:
        nebius = NebiusExecutor()
        if nebius.is_available():
            executor = nebius
        else:
            nebius_blocked = True
            block_reason = (
                "NEBIUS_API_KEY is not set; using LocalExecutor for "
                "behavioral replay; Nebius execution is BLOCKED"
            )
            executor = LocalExecutor()

    # Step 1: compile and audit.
    base_artifact = _compile_and_audit(corpus)
    findings = base_artifact["findings"]
    base_audit_digest = base_artifact["audit_digest"]

    if not findings:
        return _no_findings_report(base_audit_digest, executor, nebius_blocked, block_reason)

    if finding_index >= len(findings):
        return _error_report(
            base_audit_digest, executor, nebius_blocked, block_reason,
            f"finding_index {finding_index} out of range (have {len(findings)})",
        )

    # Step 2: select the finding.
    finding = findings[finding_index]
    skill_name = finding.get("skill", "")
    skill_text = corpus.get(skill_name, "")

    # Step 3: Bob proposes a repair.
    context = {
        "finding_index": finding_index,
        "total_findings": len(findings),
        "all_findings": findings,
    }
    try:
        proposal = proposer.propose(finding, skill_text, context)
    except Exception as exc:
        return _proposal_error_report(
            base_audit_digest, finding, str(exc), executor, nebius_blocked, block_reason
        )

    proposed_text = proposal.get("proposed_text")
    if proposed_text is None:
        blocked = proposal.get("blocked", False)
        return _no_proposal_report(
            base_audit_digest, finding, proposal, blocked, executor, nebius_blocked, block_reason
        )

    # Step 4: Crucible re-audits the repaired corpus (L6 deterministic).
    repaired_corpus = dict(corpus)
    repaired_corpus[skill_name] = proposed_text

    try:
        repaired_artifact = _compile_and_audit(repaired_corpus)
    except ValueError as exc:
        return _compile_error_report(
            base_audit_digest, finding, proposal, str(exc), executor, nebius_blocked, block_reason
        )

    repaired_findings = repaired_artifact["findings"]
    repaired_audit_digest = repaired_artifact["audit_digest"]

    # L6 deterministic acceptance check.
    deterministic_outcome, deterministic_reason = _evaluate_deterministic(
        finding, findings, repaired_findings
    )

    # If the deterministic check fails, skip behavioral replay.
    if deterministic_outcome != OUTCOME_ACCEPTED:
        return _build_report(
            base_audit_digest, repaired_audit_digest, finding, proposal,
            deterministic_outcome, deterministic_reason,
            findings, repaired_findings,
            behavioral_replay=None,
            executor=executor, nebius_blocked=nebius_blocked, block_reason=block_reason,
        )

    # Step 5: behavioral replay (L5).
    behavioral_replay = _run_behavioral_replay(
        executor, task, skill_text, proposed_text, skill_name
    )

    # Step 6: accept/reject based on deterministic AND behavioral.
    if behavioral_replay["regression"]:
        return _build_report(
            base_audit_digest, repaired_audit_digest, finding, proposal,
            OUTCOME_REJECTED, OUTCOME_BEHAVIORAL_REGRESSION,
            findings, repaired_findings,
            behavioral_replay=behavioral_replay,
            executor=executor, nebius_blocked=nebius_blocked, block_reason=block_reason,
        )

    return _build_report(
        base_audit_digest, repaired_audit_digest, finding, proposal,
        OUTCOME_ACCEPTED, None,
        findings, repaired_findings,
        behavioral_replay=behavioral_replay,
        executor=executor, nebius_blocked=nebius_blocked, block_reason=block_reason,
    )


# ---------------------------------------------------------------------------
# Deterministic evaluation (reuses L6 logic)
# ---------------------------------------------------------------------------

def _evaluate_deterministic(
    finding: dict[str, Any],
    original_findings: list[dict[str, Any]],
    repaired_findings: list[dict[str, Any]],
) -> tuple[str, str | None]:
    """L6 deterministic acceptance check (set-difference novelty check)."""
    if not _finding_gone(finding, repaired_findings):
        return OUTCOME_REJECTED, "FINDING_PERSISTS"
    original_pairs = {
        (f.get("class", ""), f.get("skill", "")) for f in original_findings
    }
    for rf in repaired_findings:
        pair = (rf.get("class", ""), rf.get("skill", ""))
        if pair not in original_pairs:
            return OUTCOME_REJECTED, "NEW_FINDINGS"
    return OUTCOME_ACCEPTED, None


def _finding_gone(
    finding: dict[str, Any],
    repaired_findings: list[dict[str, Any]],
) -> bool:
    """Check whether the targeted finding is gone in the repaired audit."""
    target_class = finding.get("class", "")
    target_skill = finding.get("skill", "")
    for rf in repaired_findings:
        if rf.get("class") == target_class and rf.get("skill") == target_skill:
            return False
    return True


# ---------------------------------------------------------------------------
# Behavioral replay (L5 integration)
# ---------------------------------------------------------------------------

def _run_behavioral_replay(
    executor: Any,
    task: dict[str, Any],
    original_text: str,
    repaired_text: str,
    skill_name: str,
) -> dict[str, Any]:
    """Run the original and repaired skill through the executor and
    property oracle. Return the comparison.

    The repair must pass all properties that the original passed. If the
    repair fails a property that the original passed, it is a behavioral
    regression.
    """
    original_prompt = _build_system_prompt(original_text)
    repaired_prompt = _build_system_prompt(repaired_text)
    user_prompt = task["task_prompt"]

    original_result = executor.execute(original_prompt, user_prompt)
    repaired_result = executor.execute(repaired_prompt, user_prompt)

    original_output = original_result.get("output", "")
    repaired_output = repaired_result.get("output", "")

    original_obs = run_property_oracle(original_output, task["properties"])
    repaired_obs = run_property_oracle(repaired_output, task["properties"])

    original_props = {o["property_id"]: o["status"] for o in original_obs}
    repaired_props = {o["property_id"]: o["status"] for o in repaired_obs}

    # Find regressions: properties that original passed but repaired fails.
    regressions = []
    for prop_id, orig_status in original_props.items():
        rep_status = repaired_props.get(prop_id, "FAIL")
        if orig_status == "PASS" and rep_status != "PASS":
            regressions.append({
                "property_id": prop_id,
                "original_status": orig_status,
                "repaired_status": rep_status,
            })

    return {
        "skill_name": skill_name,
        "original_observations": original_obs,
        "repaired_observations": repaired_obs,
        "original_properties": original_props,
        "repaired_properties": repaired_props,
        "regressions": regressions,
        "regression": len(regressions) > 0,
    }


def _build_system_prompt(skill_text: str) -> str:
    """Build a system prompt from the skill text.

    Extracts the body (after frontmatter) and wraps it as guidance.
    """
    # Strip frontmatter if present.
    body = skill_text
    if body.startswith("---\n"):
        end = body.find("\n---\n", 4)
        if end != -1:
            body = body[end + 5:]
    return f"You are guided by the following skill:\n\n{body.strip()}"


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------

def _build_report(
    base_audit_digest: str,
    repaired_audit_digest: str,
    finding: dict[str, Any],
    proposal: dict[str, Any],
    outcome: str,
    rejection_reason: str | None,
    original_findings: list[dict[str, Any]],
    repaired_findings: list[dict[str, Any]],
    behavioral_replay: dict[str, Any] | None,
    executor: Any,
    nebius_blocked: bool,
    block_reason: str | None,
) -> dict[str, Any]:
    original_pairs = {
        (f.get("class", ""), f.get("skill", "")) for f in original_findings
    }
    no_new = all(
        (rf.get("class", ""), rf.get("skill", "")) in original_pairs
        for rf in repaired_findings
    )
    report: dict[str, Any] = {
        "loop_version": LOOP_VERSION,
        "base_audit_digest": base_audit_digest,
        "repaired_audit_digest": repaired_audit_digest,
        "finding": finding,
        "proposal": {
            "proposed_text": proposal.get("proposed_text", ""),
            "rationale": proposal.get("rationale", ""),
            "proposer": proposal.get("proposer", "unknown"),
            "blocked": proposal.get("blocked", False),
        },
        "outcome": outcome,
        "rejection_reason": rejection_reason,
        "original_finding_count": len(original_findings),
        "repaired_finding_count": len(repaired_findings),
        "original_findings": [f["class"] for f in original_findings],
        "repaired_findings": [f["class"] for f in repaired_findings],
        "original_finding_gone": _finding_gone(finding, repaired_findings),
        "no_new_findings": no_new,
        "behavioral_replay": behavioral_replay,
        "executor": {
            "type": type(executor).__name__,
            "model": getattr(executor, "model", "unknown"),
            "provider": getattr(executor, "provider", "unknown"),
        },
        "nebius_blocked": nebius_blocked,
        "block_reason": block_reason,
    }
    report["loop_digest"] = digest_payload(report)
    return report


def _no_findings_report(
    base_audit_digest: str,
    executor: Any,
    nebius_blocked: bool,
    block_reason: str | None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "loop_version": LOOP_VERSION,
        "base_audit_digest": base_audit_digest,
        "finding": None,
        "proposal": None,
        "outcome": "NO_FINDINGS",
        "rejection_reason": None,
        "original_finding_count": 0,
        "repaired_finding_count": 0,
        "original_findings": [],
        "repaired_findings": [],
        "original_finding_gone": True,
        "no_new_findings": True,
        "behavioral_replay": None,
        "executor": {
            "type": type(executor).__name__,
            "model": getattr(executor, "model", "unknown"),
            "provider": getattr(executor, "provider", "unknown"),
        },
        "nebius_blocked": nebius_blocked,
        "block_reason": block_reason,
    }
    report["loop_digest"] = digest_payload(report)
    return report


def _error_report(
    base_audit_digest: str,
    executor: Any,
    nebius_blocked: bool,
    block_reason: str | None,
    error: str,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "loop_version": LOOP_VERSION,
        "base_audit_digest": base_audit_digest,
        "finding": None,
        "proposal": None,
        "outcome": OUTCOME_ERROR,
        "rejection_reason": error,
        "original_finding_count": 0,
        "repaired_finding_count": 0,
        "original_findings": [],
        "repaired_findings": [],
        "original_finding_gone": False,
        "no_new_findings": False,
        "behavioral_replay": None,
        "executor": {
            "type": type(executor).__name__,
            "model": getattr(executor, "model", "unknown"),
            "provider": getattr(executor, "provider", "unknown"),
        },
        "nebius_blocked": nebius_blocked,
        "block_reason": block_reason,
    }
    report["loop_digest"] = digest_payload(report)
    return report


def _no_proposal_report(
    base_audit_digest: str,
    finding: dict[str, Any],
    proposal: dict[str, Any],
    blocked: bool,
    executor: Any,
    nebius_blocked: bool,
    block_reason: str | None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "loop_version": LOOP_VERSION,
        "base_audit_digest": base_audit_digest,
        "finding": finding,
        "proposal": {
            "proposed_text": None,
            "rationale": proposal.get("rationale", ""),
            "proposer": proposal.get("proposer", "unknown"),
            "blocked": blocked,
        },
        "outcome": OUTCOME_BLOCKED if blocked else OUTCOME_REJECTED,
        "rejection_reason": "NO_PROPOSAL" if not blocked else None,
        "original_finding_count": 1,
        "repaired_finding_count": 1,
        "original_findings": [finding.get("class", "")],
        "repaired_findings": [finding.get("class", "")],
        "original_finding_gone": False,
        "no_new_findings": True,
        "behavioral_replay": None,
        "executor": {
            "type": type(executor).__name__,
            "model": getattr(executor, "model", "unknown"),
            "provider": getattr(executor, "provider", "unknown"),
        },
        "nebius_blocked": nebius_blocked,
        "block_reason": block_reason,
    }
    report["loop_digest"] = digest_payload(report)
    return report


def _proposal_error_report(
    base_audit_digest: str,
    finding: dict[str, Any],
    error: str,
    executor: Any,
    nebius_blocked: bool,
    block_reason: str | None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "loop_version": LOOP_VERSION,
        "base_audit_digest": base_audit_digest,
        "finding": finding,
        "proposal": {
            "proposed_text": None,
            "rationale": f"proposer error: {error}",
            "proposer": "unknown",
            "blocked": False,
        },
        "outcome": OUTCOME_ERROR,
        "rejection_reason": "PROPOSAL_ERROR",
        "original_finding_count": 1,
        "repaired_finding_count": 1,
        "original_findings": [finding.get("class", "")],
        "repaired_findings": [finding.get("class", "")],
        "original_finding_gone": False,
        "no_new_findings": True,
        "behavioral_replay": None,
        "executor": {
            "type": type(executor).__name__,
            "model": getattr(executor, "model", "unknown"),
            "provider": getattr(executor, "provider", "unknown"),
        },
        "nebius_blocked": nebius_blocked,
        "block_reason": block_reason,
    }
    report["loop_digest"] = digest_payload(report)
    return report


def _compile_error_report(
    base_audit_digest: str,
    finding: dict[str, Any],
    proposal: dict[str, Any],
    error: str,
    executor: Any,
    nebius_blocked: bool,
    block_reason: str | None,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "loop_version": LOOP_VERSION,
        "base_audit_digest": base_audit_digest,
        "finding": finding,
        "proposal": {
            "proposed_text": proposal.get("proposed_text", ""),
            "rationale": proposal.get("rationale", ""),
            "proposer": proposal.get("proposer", "unknown"),
            "blocked": False,
        },
        "outcome": OUTCOME_REJECTED,
        "rejection_reason": "COMPILE_ERROR",
        "original_finding_count": 1,
        "repaired_finding_count": 0,
        "original_findings": [finding.get("class", "")],
        "repaired_findings": [],
        "original_finding_gone": False,
        "no_new_findings": False,
        "behavioral_replay": None,
        "executor": {
            "type": type(executor).__name__,
            "model": getattr(executor, "model", "unknown"),
            "provider": getattr(executor, "provider", "unknown"),
        },
        "nebius_blocked": nebius_blocked,
        "block_reason": block_reason,
    }
    report["loop_digest"] = digest_payload(report)
    return report


# ---------------------------------------------------------------------------
# Loop fixture: a corpus with a known finding and behavioral properties
# ---------------------------------------------------------------------------

LOOP_FIXTURE: dict[str, str] = {
    "retrier": (
        "---\n"
        "name: retrier\n"
        "description: Retry operations with a bounded budget.\n"
        "license: Apache-2.0\n"
        "---\n\n"
        "# Bounded retries\n\n"
        "Retries MUST have a finite budget, except for read-only operations.\n\n"
        "The operation SHOULD be idempotent before retrying.\n"
    ),
    "gate": (
        "---\n"
        "name: gate\n"
        "description: Gate irreversible operations.\n"
        "license: Apache-2.0\n"
        "---\n\n"
        "# Irreversible action gate\n\n"
        "Irreversible operations MUST have bounded effects.\n\n"
        "## Checks\n\n"
        "- Verify the effect is bounded.\n"
    ),
}
