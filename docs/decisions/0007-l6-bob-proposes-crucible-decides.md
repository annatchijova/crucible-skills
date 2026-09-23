# ADR-0007: Bob Proposes, Crucible Decides (L6)

**Status:** Accepted for L6  
**Date:** 2026-09-23  
**Reversibility:** low; changing the decision boundary between Bob and Crucible would violate the LLM-out-of-the-loop invariant

## Context

L6 introduces Bob, an engineering workflow that receives audit findings and
proposes repairs. The architectural question is: who decides whether a repair
is accepted?

Two options:
1. **Bob decides:** the LLM proposer evaluates its own repair and accepts or
   rejects it. This puts the LLM in the decision path.
2. **Crucible decides:** Bob proposes a repair; Crucible deterministically
   re-audits the repaired corpus and accepts or rejects based on deterministic
   criteria. The LLM never touches the verdict.

Option 1 violates the LLM-out-of-the-loop invariant (§5.1 of CLAUDE.md). A
language model can read the evidence correctly and still reach the wrong
conclusion under narrative pressure. The model's judgment is not reproducible
and not tamper-evident.

Option 2 preserves the invariant: the deterministic engine (re-audit) produces
the verdict. The proposer generates text; the re-audit decides.

## Decision

L6 uses the "Bob proposes, Crucible decides" boundary:

1. Bob receives a finding (class, skill, evidence) and the current skill text.
2. Bob proposes a repair (modified skill text) via a pluggable proposer.
3. Crucible re-compiles and re-audits the repaired corpus.
4. Crucible deterministically evaluates:
   - ACCEPTED if: the targeted finding is gone AND no new findings AND compiles.
   - REJECTED if: the targeted finding persists OR new findings appear OR
     compilation fails.
5. The proposer's identity and rationale are recorded in the report but are
   NOT in the decision path.

The proposer is pluggable:
- RuleBasedProposer: deterministic repair patterns for 3 finding classes.
- LLMProposer: Nemotron via Nebius; BLOCKED without API key.

## Alternatives rejected

- **Bob decides (LLM in the decision path).** Rejected because it violates
  the LLM-out-of-the-loop invariant. Best argument for it: the LLM can
  evaluate semantic quality that deterministic checks cannot.
- **Hybrid: Bob proposes, LLM evaluates, Crucible seals.** Rejected because
  the LLM evaluation is in the decision path even if Crucible seals it.
  Best argument for it: combines LLM semantic evaluation with deterministic
  sealing.
- **No proposer (deterministic only).** Rejected for L6 because the purpose
  is to allow an LLM to propose repairs that a human or agent would find
  useful. Without a proposer, there is no repair to evaluate.

## Assumption this rests on

The deterministic re-audit is sufficient to evaluate whether a repair
resolves the finding. The re-audit checks:
1. The targeted finding class is no longer present on the same skill.
2. No new findings were introduced (total count did not increase).
3. The corpus still compiles.

This does not check semantic correctness — a repair that deletes the rule
text would be accepted if it doesn't introduce new findings. L7 (closed
repair loop) will add behavioral replay to catch semantic regressions.

## Consequences

Accepted now:
- Bob proposes; Crucible decides. The decision path is deterministic.
- The proposer is pluggable and interchangeable.
- The LLM proposer is BLOCKED without an API key, not simulated.
- The rule-based proposer handles 3 finding classes; others produce
  NO_PROPOSAL honestly.

Deferred:
- behavioral replay in the acceptance criteria (L7);
- multi-finding repair (L6 processes one finding at a time);
- auto-selection of which finding to repair;
- semantic correctness evaluation (requires a model as judge, out of scope
  for the deterministic core).

## Revisit trigger

Revisit when L7 (closed repair loop) adds behavioral replay to the acceptance
criteria, or when the LLM proposer is unblocked with a real API key.
