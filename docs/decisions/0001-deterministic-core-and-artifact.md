# ADR-0001: Deterministic Core and Versioned Audit Artifact

**Status:** Accepted for the in-progress architecture  
**Date:** 2026-09-23

## Context

Crucible must analyze agent skills whose instructions can influence other agents. Using an LLM as the final judge would make reproducibility, provenance, and disagreement handling difficult. At the same time, some future questions—conditional contradiction, entailment, and behavioral interpretation—may benefit from model-assisted investigation.

The project also needs multiple interfaces: CLI/CI, TUI, and a read-only presentation viewer. Duplicating decision logic across them would create authority drift.

## Decision

The system will compile skills into a versioned, evidence-bearing Skill IR and produce a versioned `AuditArtifact`. The deterministic audit engine is the authority for findings within its declared scope.

Models, including IBM Bob, may explore evidence, suggest classifications, or propose repairs. They may not turn an unsupported suggestion into a passing verdict. Every proposal must return through compilation, deterministic audit, and—when applicable—behavioral replay.

All interfaces consume the artifact. They do not independently adjudicate the corpus.

## Consequences

Positive:

- repeated runs over identical inputs can be compared;
- findings retain source and configuration provenance;
- the TUI and web viewer cannot silently disagree with CI;
- model-assisted features can fail closed or abstain without corrupting the core contract;
- mutation testing can measure the auditor rather than its rhetoric.

Costs:

- the IR and artifact schemas must evolve explicitly;
- natural-language semantics require candidate findings and honest uncertainty;
- a repair loop is slower than accepting a model's first answer;
- behavioral results need pinned task fixtures and runtime metadata.

## Alternatives rejected

### LLM-as-judge as the primary decision path

Rejected because an opaque model score would not provide sufficient reproducibility or explainable evidence for corpus-level findings.

### Separate logic for CLI, TUI, and web

Rejected because it creates multiple authorities and makes presentation changes capable of changing the apparent result.

### Security scanner plus quality score

Rejected as incomplete for the thesis. Security and quality are useful neighboring signals, but neither models methodology composition and mutation resistance as the primary object.

## Revisit trigger

Revisit if deterministic coverage proves unable to express a required claim without silently collapsing into arbitrary heuristics. The response should be to narrow the claim or add an explicit candidate/abstain state before moving authority into a model.

## External boundary recorded

This decision does not assume that CRUCIBLE is the first or only system to validate Agent Skills. NVIDIA's public tools already cover adjacent and overlapping lifecycle stages. The decision remains useful because it specifies how CRUCIBLE treats imported scanner/evaluator output: as provenance-bearing neighboring evidence, never as an implicit replacement for the local deterministic authority.
