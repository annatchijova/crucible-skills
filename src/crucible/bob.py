"""Bob engineering workflow (L6).

Bob receives audit findings, investigates the corpus context, and proposes a
repair. Crucible deterministically re-audits the repaired corpus and accepts
or rejects the repair. Bob proposes; Crucible decides.

The acceptance criteria are deterministic:
- ACCEPTED if: the targeted finding is gone AND no new findings AND compiles.
- REJECTED if: the targeted finding persists OR new findings appear OR
  compilation fails.

The proposer is pluggable. The LLM proposer uses Nemotron via Nebius to
generate a repair. The rule-based proposer applies known repair patterns
deterministically. The decision path never uses the LLM.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from .auditor import audit_corpus
from .compiler import compile_corpus
from .ir import digest_payload
from .mutation import BASE_FIXTURE

BOB_VERSION = "crucible-bob/v1"

# ---------------------------------------------------------------------------
# Repair proposal outcome codes
# ---------------------------------------------------------------------------

OUTCOME_ACCEPTED = "ACCEPTED"
OUTCOME_REJECTED = "REJECTED"
OUTCOME_BLOCKED = "BLOCKED"
OUTCOME_ERROR = "ERROR"

REJECTION_REASONS = {
    "FINDING_PERSISTS": "the targeted finding is still present after repair",
    "NEW_FINDINGS": "the repair introduced new findings",
    "COMPILE_ERROR": "the repaired corpus does not compile",
    "NO_PROPOSAL": "the proposer did not generate a repair",
    "PROPOSAL_ERROR": "the proposer raised an error",
}


# ---------------------------------------------------------------------------
# Proposer protocol
# ---------------------------------------------------------------------------

class Proposer(Protocol):
    """Pluggable interface for repair proposers."""

    def propose(
        self,
        finding: dict[str, Any],
        skill_text: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Propose a repair for the finding.

        Returns a dict with:
        - proposed_text: the repaired skill text (or None if no proposal)
        - rationale: why this repair was proposed
        - proposer: the proposer type name
        """
        ...


# ---------------------------------------------------------------------------
# Rule-based proposer (deterministic, for testing)
# ---------------------------------------------------------------------------

class RuleBasedProposer:
    """Deterministic proposer that applies known repair patterns.

    Each repair pattern targets a specific finding class and produces a
    deterministic fix. No LLM, no randomness.
    """

    def propose(
        self,
        finding: dict[str, Any],
        skill_text: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        finding_class = finding.get("class", "")
        if finding_class == "REQUIREMENT_WITHOUT_CHECK":
            return self._repair_requirement_without_check(finding, skill_text)
        if finding_class == "METHODOLOGICAL_VACUITY":
            return self._repair_methodological_vacuity(finding, skill_text)
        if finding_class == "BROKEN_REFERENCE":
            return self._repair_broken_reference(finding, skill_text)
        if finding_class == "STRUCTURAL_REDUNDANCY":
            return self._repair_structural_redundancy(finding, skill_text)
        return {
            "proposed_text": None,
            "rationale": f"no rule-based repair pattern for {finding_class}",
            "proposer": "rule-based",
        }

    def _repair_requirement_without_check(
        self, finding: dict[str, Any], skill_text: str
    ) -> dict[str, Any]:
        """Add a check section if the skill has rules but no checks."""
        if "## Checks" in skill_text:
            return {
                "proposed_text": None,
                "rationale": "skill already has a Checks section",
                "proposer": "rule-based",
            }
        # Insert a Checks section before the end of the skill text.
        check_section = (
            "\n## Checks\n\n"
            "- Verify the requirement is satisfied before proceeding.\n"
        )
        if "## Composes with" in skill_text:
            proposed = skill_text.replace(
                "\n## Composes with",
                check_section + "\n## Composes with",
            )
        else:
            proposed = skill_text.rstrip() + "\n" + check_section
        return {
            "proposed_text": proposed,
            "rationale": "added a Checks section with a verification check",
            "proposer": "rule-based",
        }

    def _repair_methodological_vacuity(
        self, finding: dict[str, Any], skill_text: str
    ) -> dict[str, Any]:
        """Add procedural steps and checks to a vacuous skill.

        A vacuous skill has rules but no steps and no checks. The repair
        adds both a Steps section (how) and a Checks section (verification).
        """
        proposed = skill_text.rstrip()
        rationale_parts = []
        if "## Steps" not in skill_text:
            steps_section = (
                "\n## Steps\n\n"
                "1. Identify the requirement that applies.\n"
                "2. Apply the requirement to the current context.\n"
            )
            if "## Composes with" in proposed:
                proposed = proposed.replace(
                    "\n## Composes with",
                    steps_section + "\n## Composes with",
                )
            else:
                proposed = proposed + "\n" + steps_section
            rationale_parts.append("a Steps section")
        if "## Checks" not in skill_text:
            check_section = (
                "\n## Checks\n\n"
                "- Verify the requirement is satisfied before proceeding.\n"
            )
            if "## Composes with" in proposed:
                proposed = proposed.replace(
                    "\n## Composes with",
                    check_section + "\n## Composes with",
                )
            else:
                proposed = proposed + "\n" + check_section
            rationale_parts.append("a Checks section")
        if not rationale_parts:
            return {
                "proposed_text": None,
                "rationale": "skill already has Steps and Checks sections",
                "proposer": "rule-based",
            }
        return {
            "proposed_text": proposed,
            "rationale": f"added {' and '.join(rationale_parts)}",
            "proposer": "rule-based",
        }

    def _repair_broken_reference(
        self, finding: dict[str, Any], skill_text: str
    ) -> dict[str, Any]:
        """Remove the broken reference target."""
        evidence = finding.get("evidence", "")
        # Extract the target name from the evidence.
        import re
        match = re.search(r"target\s+'([^']+)'", evidence)
        if not match:
            return {
                "proposed_text": None,
                "rationale": "could not extract broken target from evidence",
                "proposer": "rule-based",
            }
        target = match.group(1)
        # Remove the line containing the broken target.
        lines = skill_text.split("\n")
        filtered = [
            line for line in lines
            if target not in line or line.strip().startswith("description:")
        ]
        # Also remove from description if present.
        proposed = "\n".join(filtered)
        # Clean up empty section headings.
        proposed = proposed.replace(
            "\n## Composes with\n\n\n", "\n"
        ).replace("\n## Composes with\n\n", "\n")
        return {
            "proposed_text": proposed,
            "rationale": f"removed broken reference to {target}",
            "proposer": "rule-based",
        }

    def _repair_structural_redundancy(
        self, finding: dict[str, Any], skill_text: str
    ) -> dict[str, Any]:
        """Rename the redundant skill to differentiate it."""
        # For structural redundancy, the fix is to differentiate the text.
        # We append a distinguishing note to the description.
        if "description:" in skill_text:
            proposed = skill_text.replace(
                "description:",
                "description: (variant) ",
                1,
            )
            return {
                "proposed_text": proposed,
                "rationale": "differentiated the redundant skill description",
                "proposer": "rule-based",
            }
        return {
            "proposed_text": None,
            "rationale": "could not find description to differentiate",
            "proposer": "rule-based",
        }


# ---------------------------------------------------------------------------
# LLM proposer (Nemotron via Nebius)
# ---------------------------------------------------------------------------

class LLMProposer:
    """Proposer that uses Nemotron via Nebius to generate a repair.

    Requires NEBIUS_API_KEY. If the key is not present, the proposal is
    BLOCKED, not simulated.
    """

    NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
    NEBIUS_MODEL = "nvidia/nemotron-3-super-120b-a12b"

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("NEBIUS_API_KEY")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def propose(
        self,
        finding: dict[str, Any],
        skill_text: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.api_key:
            return {
                "proposed_text": None,
                "rationale": "NEBIUS_API_KEY not set; cannot generate LLM proposal",
                "proposer": "llm-nebius",
                "blocked": True,
            }
        import json
        import urllib.error
        import urllib.request

        prompt = self._build_prompt(finding, skill_text, context)
        payload = {
            "model": self.NEBIUS_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a methodology repair engine. You receive a "
                        "finding from a skill audit and the current skill text. "
                        "Propose a repaired version of the skill text that "
                        "resolves the finding without introducing new issues. "
                        "Output ONLY the repaired skill text, no explanation."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": 1000,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.NEBIUS_BASE_URL + "chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            return {
                "proposed_text": None,
                "rationale": f"API error: {exc}",
                "proposer": "llm-nebius",
                "blocked": False,
                "error": str(exc),
            }
        output = ""
        if result.get("choices"):
            output = result["choices"][0].get("message", {}).get("content", "")
        return {
            "proposed_text": output if output.strip() else None,
            "rationale": "generated by Nemotron via Nebius Token Factory",
            "proposer": "llm-nebius",
            "blocked": False,
            "model": self.NEBIUS_MODEL,
            "response_id": result.get("id", ""),
        }

    def _build_prompt(
        self, finding: dict[str, Any], skill_text: str, context: dict[str, Any]
    ) -> str:
        return (
            f"Audit finding:\n"
            f"  class: {finding.get('class', 'unknown')}\n"
            f"  skill: {finding.get('skill', 'unknown')}\n"
            f"  evidence: {finding.get('evidence', 'none')}\n\n"
            f"Current skill text:\n---\n{skill_text}\n---\n\n"
            f"Propose a repaired version of this skill text that resolves "
            f"the finding. Output only the repaired skill text."
        )


# ---------------------------------------------------------------------------
# Bob workflow runner
# ---------------------------------------------------------------------------

def run_bob_workflow(
    corpus: dict[str, str] | None = None,
    finding_index: int = 0,
    proposer: Proposer | None = None,
) -> dict[str, Any]:
    """Run the Bob workflow on one finding.

    1. Compile and audit the corpus to get findings.
    2. Select the finding at finding_index.
    3. Bob investigates the context and proposes a repair.
    4. Crucible re-compiles and re-audits the repaired corpus.
    5. Crucible accepts or rejects the repair deterministically.

    If no corpus is given, uses a fixture that has a
    REQUIREMENT_WITHOUT_CHECK finding.
    """
    if corpus is None:
        corpus = BOB_FIXTURE
    if proposer is None:
        proposer = RuleBasedProposer()

    # Step 1: compile and audit.
    base_artifact = _compile_and_audit(corpus)
    findings = base_artifact["findings"]
    base_audit_digest = base_artifact["audit_digest"]

    if not findings:
        return _no_findings_report(base_audit_digest, proposer)

    if finding_index >= len(findings):
        return _error_report(
            base_audit_digest,
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
            base_audit_digest, finding, str(exc), proposer
        )

    proposed_text = proposal.get("proposed_text")
    if proposed_text is None:
        blocked = proposal.get("blocked", False)
        return _no_proposal_report(
            base_audit_digest, finding, proposal, blocked
        )

    # Step 4: Crucible re-audits the repaired corpus.
    repaired_corpus = dict(corpus)
    repaired_corpus[skill_name] = proposed_text

    try:
        repaired_artifact = _compile_and_audit(repaired_corpus)
    except ValueError as exc:
        return _compile_error_report(
            base_audit_digest, finding, proposal, str(exc)
        )

    repaired_findings = repaired_artifact["findings"]
    repaired_audit_digest = repaired_artifact["audit_digest"]

    # Step 5: deterministic acceptance/rejection.
    outcome, reason = _evaluate_repair(
        finding, findings, repaired_findings
    )

    # no_new_findings: check that no finding in the repaired audit is absent
    # from the original audit (set-difference, not count comparison).
    original_pairs = {
        (f.get("class", ""), f.get("skill", "")) for f in findings
    }
    no_new = all(
        (rf.get("class", ""), rf.get("skill", "")) in original_pairs
        for rf in repaired_findings
    )

    return {
        "bob_version": BOB_VERSION,
        "base_audit_digest": base_audit_digest,
        "repaired_audit_digest": repaired_audit_digest,
        "finding": finding,
        "proposal": {
            "proposed_text": proposed_text,
            "rationale": proposal.get("rationale", ""),
            "proposer": proposal.get("proposer", "unknown"),
            "blocked": proposal.get("blocked", False),
        },
        "outcome": outcome,
        "rejection_reason": reason,
        "original_finding_count": len(findings),
        "repaired_finding_count": len(repaired_findings),
        "original_findings": [f["class"] for f in findings],
        "repaired_findings": [f["class"] for f in repaired_findings],
        "original_finding_gone": _finding_gone(finding, repaired_findings),
        "no_new_findings": no_new,
    }


def _evaluate_repair(
    finding: dict[str, Any],
    original_findings: list[dict[str, Any]],
    repaired_findings: list[dict[str, Any]],
) -> tuple[str, str | None]:
    """Deterministically evaluate whether the repair is accepted.

    The novelty check uses set-difference, not count comparison. A repair
    that removes the targeted finding but introduces a different finding
    (even if the total count stays the same or drops) is REJECTED.
    """
    if not _finding_gone(finding, repaired_findings):
        return OUTCOME_REJECTED, "FINDING_PERSISTS"
    # Check for findings that were not in the original audit.
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


def _compile_and_audit(corpus: dict[str, str]) -> dict[str, Any]:
    """Write corpus to temp dir, compile, and audit."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for skill_name, content in corpus.items():
            skill_dir = root / skill_name
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                content, encoding="utf-8", newline="\n"
            )
        ir = compile_corpus(root)
        audit = audit_corpus(ir)
    return {
        "findings": audit["findings"],
        "audit_digest": audit["audit_digest"],
    }


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------

def _no_findings_report(
    base_audit_digest: str, proposer: Proposer
) -> dict[str, Any]:
    return {
        "bob_version": BOB_VERSION,
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
    }


def _error_report(
    base_audit_digest: str, error: str
) -> dict[str, Any]:
    return {
        "bob_version": BOB_VERSION,
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
    }


def _no_proposal_report(
    base_audit_digest: str,
    finding: dict[str, Any],
    proposal: dict[str, Any],
    blocked: bool,
) -> dict[str, Any]:
    return {
        "bob_version": BOB_VERSION,
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
    }


def _proposal_error_report(
    base_audit_digest: str,
    finding: dict[str, Any],
    error: str,
    proposer: Proposer,
) -> dict[str, Any]:
    return {
        "bob_version": BOB_VERSION,
        "base_audit_digest": base_audit_digest,
        "finding": finding,
        "proposal": {
            "proposed_text": None,
            "rationale": f"proposer error: {error}",
            "proposer": type(proposer).__name__,
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
    }


def _compile_error_report(
    base_audit_digest: str,
    finding: dict[str, Any],
    proposal: dict[str, Any],
    error: str,
) -> dict[str, Any]:
    return {
        "bob_version": BOB_VERSION,
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
    }


# ---------------------------------------------------------------------------
# Bob fixture: a corpus with a known REQUIREMENT_WITHOUT_CHECK finding
# ---------------------------------------------------------------------------

BOB_FIXTURE: dict[str, str] = {
    "retrier": (
        "---\n"
        "name: retrier\n"
        "description: Retry operations with a bounded budget.\n"
        "license: Apache-2.0\n"
        "---\n\n"
        "# Bounded retries\n\n"
        "Retries MUST have a finite budget.\n\n"
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
