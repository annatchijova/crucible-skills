# Evaluation Plan

**Status:** planned. This document separates evidence about CRUCIBLE from evidence about the skills it analyzes.

## Evaluation questions

1. Can CRUCIBLE compile real skill corpora without losing source provenance?
2. Does it detect seeded methodology defects with acceptable false-positive pressure?
3. Does its typed graph distinguish redundancy from composition and contradiction?
4. Does a methodology mutation produce the predicted static and/or behavioral change?
5. Can Bob propose useful repairs that survive deterministic re-audit and replay?
6. Does the NVIDIA/Nebius runtime contribute to the experiment rather than merely appear in the stack?

## Three evidence populations

### A — Author corpus

Real skills with deliberate composition and known methodological boundaries. This is a regression/reference corpus, not neutral ground truth.

### B — Seeded mutants

Plausible skills with hidden labels for expected findings and non-findings. Mutations include exception removal, polarity inversion, broken references, widened triggers, unsupported claims, missing checks, cycles, and duplicate capabilities.

### C — External corpora

Independent OSS skills and NVIDIA's published catalog. These provide interoperability and false-positive pressure. They are not universal ground truth.

## Negative controls

Every behavioral claim needs a negative control where possible:

- a benign non-triggering task;
- a skill whose mutation should not affect the selected property;
- a disjoint-scope pair that resembles a conflict lexically;
- a repair that only changes wording but should not restore the invariant;
- a model/runtime change recorded as a confounder.

## Deterministic metrics

- parse success and explicit abstention rate;
- finding precision/recall on seeded fixtures;
- false-positive rate on benign fixtures;
- class-level recall by finding type;
- mutation kill rate;
- surviving mutant inventory;
- source-span and artifact reproducibility;
- regression diff between auditor versions.

“Marginal utility” is not a magic scalar in the first version. It is an evidence-backed comparison of the distinct decisions, checks, or boundaries available with and without a candidate skill.

## Behavioral observation format

```yaml
BehaviorObservation:
  task_id: retry-irreversible-001
  task_digest: sha256:...
  corpus_digest: sha256:...
  skill_variant: original | mutant | repaired | baseline
  model:
    provider: nebius-token-factory
    model_id: pending
    runtime_id: pending
  property_id: bounded-retry-for-irreversible-operation
  expected: PASS | FAIL | ABSTAIN
  observed: PASS | FAIL | ABSTAIN
  raw_artifact_ref: ...
  limitations: []
```

Behavior observations are not automatically universal claims. They are bounded results under the recorded task, model, runtime, corpus, and oracle.

## Initial demonstration

The first target example is deliberately conditional:

```text
Skill A: retry failed operations until success.
Skill B: irreversible actions must be bounded and reviewable.

Candidate conflict condition:
retry target is irreversible AND non-idempotent

Falsifier:
the operation is proven idempotent, or an external idempotency key / equivalent guard
prevents duplicate effects.
```

This is a target fixture. Until the parser, graph, oracle, and behavioral harness implement it, the README must call it intended capability, not demonstrated proof.
