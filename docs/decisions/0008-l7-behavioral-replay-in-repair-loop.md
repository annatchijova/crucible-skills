# ADR-0008: Behavioral Replay in the Repair Loop (L7)

**Status:** Accepted for L7  
**Date:** 2026-09-23  
**Reversibility:** low; removing behavioral replay from the acceptance criteria would weaken the loop to L6's deterministic-only check

## Context

L6 (Bob workflow) accepts or rejects a repair based on deterministic
criteria alone: the targeted finding is gone, no new findings appear,
and the corpus compiles. This is necessary but not sufficient. A repair
can fix the finding deterministically while introducing a behavioral
regression: the rule text changes in a way that causes the model to
behave differently, even though the audit no longer flags it.

The question: should L7 (closed repair loop) add behavioral replay to
the acceptance criteria?

## Decision

L7 adds behavioral replay as a second gate:

1. **Deterministic gate (L6):** the targeted finding is gone, no new
   findings, the corpus compiles.
2. **Behavioral gate (L5):** the repaired skill passes all properties
   that the original skill passed.

If the deterministic gate fails, the behavioral gate is skipped (the
repair is already rejected). If the deterministic gate passes but the
behavioral gate fails, the repair is REJECTED with
`BEHAVIORAL_REGRESSION`.

The behavioral replay runs the original and repaired skill through the
same executor and property oracle as L5. The executor is pluggable
(LocalExecutor for testing, NebiusExecutor for Nemotron). The property
oracle is deterministic and does not use the LLM.

## Alternatives rejected

- **Deterministic only (L6 criteria).** Rejected because a repair can
  fix the finding while breaking behavior. Best argument for it:
  simplicity and no executor dependency.
- **Behavioral only (no deterministic).** Rejected because the
  deterministic check catches structural defects (broken references,
  new findings) that the property oracle does not check. Best argument
  for it: behavior is what matters, not structure.
- **LLM as judge.** Rejected because it violates the LLM-out-of-the-loop
  invariant. Best argument for it: the LLM can evaluate semantic quality
  that deterministic checks cannot.

## Assumption this rests on

The property oracle captures the behavioral properties that matter for
the skill under repair. If the oracle does not check a property, a
behavioral regression in that property goes undetected. This is the
same limitation as L5, documented in `BEHAVIORAL_LIMITATIONS`.

## Consequences

Accepted now:
- L7 has two gates: deterministic (L6) and behavioral (L5).
- A repair that passes deterministic but fails behavioral is REJECTED
  with `BEHAVIORAL_REGRESSION`.
- The behavioral replay uses the same executor and property oracle as
  L5, so it inherits L5's limitations.
- Without `NEBIUS_API_KEY`, the behavioral replay uses LocalExecutor
  and the Nebius path is documented as BLOCKED.

Deferred:
- comparing the repair against the mutant (mutation-testing loop);
- multi-property behavioral replay (currently uses the L5 task fixture);
- semantic correctness evaluation (requires a model as judge, out of
  scope for the deterministic core).

## Revisit trigger

Revisit when the property oracle is extended to cover more properties,
or when the Nebius executor is unblocked with a real API key.
