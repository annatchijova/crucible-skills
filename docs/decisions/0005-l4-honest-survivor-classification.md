# ADR-0005: Honest Survivor Classification for L4

**Status:** Accepted for L4  
**Date:** 2026-09-23  
**Reversibility:** low; changing the survivor classification scheme changes every mutation report and every downstream improvement target

## Context

L4 seeds 8 defect classes against a known-good base fixture and runs the full
pipeline. The natural temptation is to report a single "kill rate" and treat
non-killed mutations as failures. But survivors have different causes, and
each cause points to a different improvement action:

- **INSUFFICIENT_DETECTOR:** the detector should have caught this but didn't.
  Fix: improve the auditor or graph.
- **INSUFFICIENT_REPRESENTATION:** the IR does not carry the field the check
  needs. Fix: enhance L1 or L3 to extract the field.
- **EQUIVALENT_MUTANT:** the mutation is semantically equivalent to the
  original. No fix needed; the mutant is not a real defect.
- **DEFECTIVE_ORACLE:** the expected finding was wrong. Fix: correct the
  oracle definition.
- **OUT_OF_SCOPE:** the check is documented as abstained. No fix needed; the
  limitation is honest.

Collapsing these into a single "survived" loses the diagnostic value.

## Decision

L4 classifies every non-killed mutation:

- **ABSTAINED** with `OUT_OF_SCOPE` for mutations targeting checks documented
  as abstained in L2 or L3.
- **SURVIVED** with one of:
  - `INSUFFICIENT_DETECTOR` — the detector exists but missed the defect;
  - `INSUFFICIENT_REPRESENTATION` — the IR lacks the field the check needs;
  - `EQUIVALENT_MUTANT` — the mutation is not a real defect;
  - `DEFECTIVE_ORACLE` — the expected finding was wrong.

The kill rate is `killed / (killed + survived)`, excluding abstained and
compile errors. This prevents honest scope limitations from penalizing the
metric.

## Alternatives rejected

- **Single kill rate, no classification.** Rejected because it hides the
  cause of survivors, making it impossible to prioritize improvements.
  Best argument for it: simplicity.
- **Include abstained in the kill rate.** Rejected because it penalizes
  honest scope: a check documented as abstained is not a detector failure.
  Best argument for it: a single number.
- **Classify survivors automatically by analyzing the mutated corpus.**
  Rejected for L4 because it requires semantic analysis not available
  deterministically. Pre-specified classification based on the mutation spec
  is honest and reproducible. Best argument for it: catches misclassified
  survivors.

## Assumption this rests on

The pre-specified survivor classifications are correct: each mutation's
expected behavior is derived from the documented L2/L3 limitations. If a
limitation is wrong (e.g., a check documented as abstained actually works),
the classification would be wrong. This is bounded by the L2/L3 red-team
reviews, which verified the limitations empirically.

## Consequences

Accepted now:

- Survivors are diagnostic, not shameful. Each survivor points to a specific
  improvement action.
- The kill rate (4/6) is honest: it excludes abstained and counts only
  scorable mutations.
- The two survivors (EXCEPTION_REMOVAL, EDGE_REMOVAL) identify two specific
  gaps: exception extraction (L1/L3) and missing-edge detection (L2/L3).

Deferred:

- automatic survivor classification by analyzing the mutated corpus;
- more mutation classes (the framework supports adding them without
  changing the report structure);
- running the mutation lab against the real corpus (requires known ground
  truth).

## Revisit trigger

Revisit when L5 (behavioral differential) needs to compare baseline vs. mutant
behavior, or when a new mutation class is added that doesn't fit the existing
survivor classification codes.
