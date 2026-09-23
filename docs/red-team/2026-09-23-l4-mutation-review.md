# L4 Red-Team Review — Mutation Laboratory

**Date:** 2026-09-23  
**Scope:** base fixture, mutation classes, kill/survive/abstain classification, survivor classification, artifact sealing, invariant preservation from L1+L2+L3  
**Level:** L4  
**Status:** reviewed; two survivors and two abstentions are honestly classified

## Threat model

The mutation lab tests whether the auditor (L2) and graph (L3) actually detect
the defect classes they claim to detect. The threat is a false sense of
security: the auditor passes all its own tests, but a deliberate defect of a
class it claims to detect goes unnoticed. This is the mutation testing problem
applied to the verifier itself.

The lab does not trust the auditor's self-assessment. It seeds known defects,
runs the full pipeline, and classifies the outcome independently. Survivors
are not failures to be hidden — they are diagnostic information about where
the detector is insufficient, where the representation is insufficient, or
where the check is genuinely out of scope.

## L1+L2+L3 invariant preservation

| Invariant | How L4 preserves it | Result |
|---|---|---|
| L1 artifact is versioned and sealed | L4 uses compile_corpus, which checks schema_version | PASS |
| L2 audit is deterministic and sealed | L4 uses audit_corpus, which seals the audit | PASS |
| L3 graph is deterministic and sealed | L4 uses build_composition_graph, which seals the graph | PASS |
| Same input produces same output | L4 report is deterministic; cross-process digest verified identical | PASS |
| No float in the decision path | L4 uses integer counts and string comparisons only | PASS |
| No LLM in the decision path | L4 is pure Python; no model calls | PASS |
| Fail closed on incompatible input | L4 catches ValueError from compile and reports COMPILE_ERROR | PASS |
| Honest abstention | 2 mutations are ABSTAINED with OUT_OF_SCOPE classification | PASS |
| Source evidence | every result carries evidence, base digest, and mutated digest | PASS |

## L4 invariants reviewed

| Invariant | Evidence | Result |
|---|---|---|
| Report is versioned and sealed | `mutation_version: crucible-mutation/v1`, `mutation_digest: sha256:...` | PASS |
| Report is deterministic | same-process and cross-process digest comparison | PASS |
| All 8 mutation classes are present | POLARITY_INVERSION, EXCEPTION_REMOVAL, REFERENCE_BREAK, CHECK_REMOVAL, TRIGGER_WIDENING, EDGE_REMOVAL, CYCLE_INTRODUCTION, CAPABILITY_DUPLICATION | PASS |
| Kill rate excludes abstained | `4/6` (4 killed + 2 survived = 6 scorable; 2 abstained excluded) | PASS |
| Every survivor is classified | INSUFFICIENT_DETECTOR, INSUFFICIENT_REPRESENTATION | PASS |
| Every abstained is classified | OUT_OF_SCOPE (x2) | PASS |
| Every result carries evidence | non-empty evidence string for all 8 results | PASS |
| Every result carries digests | base_audit_digest and mutated_audit_digest for all results | PASS |
| Mutated digest differs from base | all 8 mutations change the source bytes and the digest | PASS |
| Base fixture is clean | base fixture produces zero audit findings | PASS |

## Induction evidence

### Mutation lab run

| Mutation | Class | Expected finding | Status | Classification |
|---|---|---|---|---|
| M001 | POLARITY_INVERSION | NORMATIVE_CONFLICT | ABSTAINED | OUT_OF_SCOPE |
| M002 | EXCEPTION_REMOVAL | (none) | SURVIVED | INSUFFICIENT_REPRESENTATION |
| M003 | REFERENCE_BREAK | BROKEN_REFERENCE | KILLED | — |
| M004 | CHECK_REMOVAL | REQUIREMENT_WITHOUT_CHECK | KILLED | — |
| M005 | TRIGGER_WIDENING | SCOPE_TRIGGER_MISMATCH | ABSTAINED | OUT_OF_SCOPE |
| M006 | EDGE_REMOVAL | (none) | SURVIVED | INSUFFICIENT_DETECTOR |
| M007 | CYCLE_INTRODUCTION | COMPOSITION_CYCLE | KILLED | — |
| M008 | CAPABILITY_DUPLICATION | STRUCTURAL_REDUNDANCY | KILLED | — |

Kill rate: 4/6 (67%). 2 abstained (out of scope). 2 survived (with classification).

Report digest: `sha256:f7a5762ceedbfde0af0c09479c33f401071dc9b4db41e0a6efa2b50795404fbb`.  
Cross-process digest: identical.

### What the survivors tell us

**M002 EXCEPTION_REMOVAL (INSUFFICIENT_REPRESENTATION):** The IR does not
extract exception clauses from normative rules. The mutation removes
", except for read-only operations" from a MUST rule, but the auditor has no
way to know the exception existed. This is not a detector defect — it is a
representation gap. The fix is in L1 (extract exceptions) or L3 (typed
conditions), not in L2.

**M006 EDGE_REMOVAL (INSUFFICIENT_DETECTOR):** The auditor detects broken
edges (target does not exist) but not missing edges (a composition that
should exist but doesn't). The mutation removes a "Pairs with" declaration
and the "Composes with" section, but the auditor has no baseline to compare
against. This is a detector gap: the auditor needs a "declared composition
is now absent" check, which requires either a baseline corpus or a
graph-diff approach. This is a candidate for L7 (closed repair loop) or a
future graph-diff check.

### What the abstentions tell us

**M001 POLARITY_INVERSION (OUT_OF_SCOPE):** The mutation flips MUST to
MUST_NOT, which would create a normative contradiction if the original rule
and the inverted rule coexisted. But the mutation replaces the text, so
only the inverted rule exists. NORMATIVE_CONFLICT requires comparing two
rules with overlapping subjects and contradictory modalities — the IR does
not extract subjects or conditions. This is honestly out of scope.

**M005 TRIGGER_WIDENING (OUT_OF_SCOPE):** The mutation changes "Triggers on
retry operations only" to "Triggers on all operations". SCOPE_TRIGGER_MISMATCH
requires extracting declared triggers and comparing them to the description
scope — the IR does not extract triggers. This is honestly out of scope.

### Test suite

16 mutation tests + 19 graph tests + 19 auditor tests + 7 compiler tests =
61 total, all green. Each mutation test names the invariant it defends and
includes the expected status and classification.

## Discarded vectors

| Vector | Result | Why |
|---|---|---|
| Treat survivors as failures | Rejected | survivors are diagnostic, not failures; classifying them by cause is the value |
| Include abstained in kill rate | Rejected | abstained checks are documented limitations, not detector failures; including them would penalize honest scope |
| Use the real corpus as the base fixture | Rejected | the real corpus has unknown ground truth; the base fixture must be known-good by construction |
| Mutate the IR directly instead of the source | Rejected | mutating the source tests the full pipeline including compilation; mutating the IR would skip L1, hiding L1 defects |
| Add more mutation classes | Deferred for L4 | 8 classes cover the primary defect categories; more classes can be added without changing the framework |

## Known blind spots

- The base fixture is synthetic. It covers the properties the 8 mutations
  target, but it does not cover all possible skill structures. A mutation
  that requires a more complex fixture (e.g., a 5-skill composition chain)
  would need a new fixture.
- The mutation lab does not test the real corpus. It tests the detector
  against seeded defects in a controlled fixture. This is by design: the
  real corpus has unknown ground truth.
- SURVIVED mutations are classified by pre-specified expected behavior, not
  by analyzing the mutated corpus. This means the classification is a
  prediction, not a diagnosis. A more sophisticated lab would analyze the
  mutated corpus to determine the cause automatically.
- The kill rate (4/6) is a property of the current detector against the
  current fixture, not a universal quality metric. Adding more mutations
  or changing the fixture would change the rate.

## Gate decision

L4 is coherent and independently useful as a mutation laboratory. It
seeds 8 defect classes, runs the full pipeline, and honestly classifies
each result as KILLED, SURVIVED, or ABSTAINED. Survivors are classified by
cause (INSUFFICIENT_DETECTOR, INSUFFICIENT_REPRESENTATION), providing
diagnostic information for improving L2/L3. Abstentions are classified as
OUT_OF_SCOPE, documenting what the current IR cannot support. The report
is deterministic, sealed, and cross-process reproducible. L5 (behavioral
differential) may begin by consuming the mutation lab to run baseline vs.
mutant behavioral comparisons, with Nemotron as the execution engine.
