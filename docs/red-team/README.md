# Red-Team Charter

**Status: planned; execution begins after the first integrated implementation.**

This project will not call a scanner result a vulnerability or a methodology defect merely because the text looks suspicious. Findings must carry an epistemic level and a reproducible path.

## Threat model

The corpus may contain malicious, careless, misleading, incomplete, or merely incompatible skills. A skill author may try to evade shallow checks through wording, scope manipulation, broken provenance, or plausible-looking exceptions. Bob may propose a repair that silences a finding without restoring the violated property.

The attacker does not automatically control the auditor, its source code, the sealed audit artifact, or the verifier's configuration. Those assumptions must be stated for every experiment.

## Attack rounds

### Round 1 — Parser and boundary defects

- malformed frontmatter;
- Unicode normalization and source-span drift;
- duplicate identities and path traversal;
- oversized sections and resource exhaustion;
- ambiguous Markdown structure;
- references that escape the corpus boundary.

### Round 2 — Invariant violations

- same source producing different canonical IR;
- findings changing when unrelated skills are added;
- mutation kill rate inflated by duplicate fixtures;
- unsupported semantics emitted as PASS;
- artifact metadata changing the decision payload;
- a repair suppressing evidence instead of restoring the property.

### Round 3 — Emergent composition failures

- two individually valid rules becoming incompatible under shared activation;
- delegation cycles and authority loops;
- graph edges that claim composition but merely encode text similarity;
- a “check” that cannot observe the property it claims to verify;
- a behavioral change attributed to a skill when the agent route or task changed;
- viewer/CLI/CI projections disagreeing about the same artifact.

## Epistemic labels

- **CODE FACT** — directly observed in source or artifact.
- **PLAUSIBLE HYPOTHESIS** — mechanism is supported but not executed.
- **CONFIRMED BY INDUCTION** — a stated prediction was executed and observed.
- **FALSIFIED** — the experiment contradicted the prediction.

No report may use “confirmed,” “bypass,” or “exploitable” without the induction evidence, threat-model precondition, corpus digest, runtime, and exact reproduction.

## Required evidence for a finding

```text
finding ID
epistemic level
threat model
corpus commit and digest
prediction stated before execution
reproduction command or fixture
observed result
causal explanation
discarded rival hypotheses
```

## Discarded vectors belong in the report

The final report must include attempted vectors that failed: parser tricks that did not alter the IR, mutations the fixture could not expose, and supposed conflicts whose conditions were actually disjoint. Falsification demonstrates that the audit is not merely confirmatory.

## Integrated review gate

Before claiming a hackathon-ready level, review the complete path:

```text
source skill → IR → graph/audit → mutation → artifact → Bob proposal
       → recompilation → re-audit → behavioral replay → projection
```

The red-team review must attack the authority boundary at every arrow. A green unit test is evidence for its covered property, not proof of the entire system.
