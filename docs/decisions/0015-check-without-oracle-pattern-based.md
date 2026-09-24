# ADR-0015: Check-Without-Oracle — Pattern-Based Oracle Kind Extraction

**Status:** Accepted  
**Date:** 2026-09-23  
**Reversibility:** high; the oracle_kind field is additive

## Context

CHECK_WITHOUT_ORACLE was abstained because the IR did not extract
oracle_kind for checks. The user requested detection of skills that say
"check X" but X is not actually checkable.

## Decision

Extend the L1 IR with oracle_kind extraction and add the
CHECK_WITHOUT_ORACLE check.

### IR extension (additive)

Each check now carries an `oracle_kind` field — classified by how the
check can be verified:

- **"question"** — the check is a question (ends with ?)
- **"checkbox"** — the check is a checkbox item ([ ] or [x])
- **"command"** — the check contains a verification verb (verify,
  assert, run, check, confirm, test, query, inspect, does, ensure,
  prove, validate, demonstrate)
- **"unknown"** — none of the above

### L2 check: CHECK_WITHOUT_ORACLE

A check with oracle_kind "unknown" is a CANDIDATE finding: the check
text does not indicate how to verify it. It may be a descriptive
statement, a classification, or a rule disguised as a check — none of
which are verifiable oracles.

### Real corpus results

The real corpus produces 16 CHECK_WITHOUT_ORACLE findings (16/175 =
9% of checks). All are CANDIDATE with the limitation: "oracle_kind
extraction is pattern-based; a check may be verifiable through
domain-specific means not captured by the patterns."

The 9% rate is reasonable. The 16 checks are mostly descriptive
statements or classifications that happen to be in a ## Checks
section but are not actually verifiable oracles. For example:
- "The sky is blue" (descriptive, not a check)
- "Confirmed exposed — reachable, reached, preconditions hold"
  (classification, not a check)

## Alternatives rejected

- **CONFIRMED status.** Rejected: oracle_kind extraction is
  pattern-based. A check may be verifiable through domain-specific
  means not captured by the patterns. CANDIDATE is the honest status.
- **More oracle kinds.** Rejected: the three kinds (question,
  checkbox, command) cover the vast majority of real checks. Adding
  more kinds (e.g., "metric", "threshold") would require domain
  knowledge and reduce determinism.
- **Semantic oracle detection (LLM).** Rejected: would put the LLM in
  the decision path. The deterministic base produces candidates; the
  LLM confirms or rejects (deferred).

## Consequences

Accepted now:
- CHECK_WITHOUT_ORACLE is the 13th emitted check. The auditor emits
  13 checks and abstains on 1.
- The IR has a new `oracle_kind` field on checks. Existing consumers
  ignore it.
- The real corpus produces 16 CANDIDATE findings (9% of checks).
- 14 new falsifiable tests cover detection, no-false-positives (question,
  command, checkbox), oracle_kind extraction, evidence, limitation,
  determinism, and non-abstention.

Deferred:
- CLAIM_WITHOUT_PROVENANCE (the last abstained check).
- LLM confirmation layer for CHECK_WITHOUT_ORACLE candidates.
