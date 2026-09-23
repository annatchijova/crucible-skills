# ADR-0006: Model as Observed Subject, Not Judge (L5)

**Status:** Accepted for L5  
**Date:** 2026-09-23  
**Reversibility:** low; changing the model's role from observed subject to judge would violate the deterministic core and the LLM-out-of-the-loop invariant

## Context

L5 runs a model (NVIDIA Nemotron via Nebius Token Factory) against four skill
variants and observes whether the model's behavior satisfies explicit
properties. The architectural question is: what role does the model play?

Two options:
1. **Model as judge:** the model evaluates whether the skill is "good" or
   "bad" and its verdict is the result.
2. **Model as observed subject:** the model generates behavior; a
   deterministic property oracle observes the behavior and decides.

Option 1 violates the LLM-out-of-the-loop invariant (§5.1 of CLAUDE.md): a
language model can read evidence correctly and still reach the wrong
conclusion under narrative pressure. The model's judgment is not sealed; it
is not reproducible; it is not tamper-evident.

Option 2 preserves the invariant: the deterministic engine (property oracle)
produces and seals the result. The model generates behavior that the oracle
observes. The model cannot influence the verdict because the verdict is
computed from the model's output by a deterministic function, not from the
model's judgment.

## Decision

L5 uses the model as an observed subject, not a judge:

1. The model receives a system prompt (skill guidance) and a user prompt
   (task) and generates an output.
2. The property oracle (deterministic Python functions) checks the output
   against 4 explicit properties (P1: mentions budget, P2: respects exception,
   P3: no unbounded retry, P4: mentions idempotency).
3. The oracle's observations are sealed with SHA-256.
4. The model's output is recorded as evidence (with output_digest) but is
   NOT in the sealed decision path — only the oracle's observations are sealed.

The model metadata (model ID, provider, temperature, usage) is recorded in
the report for reproducibility but is NOT in the sealed payload. This means
swapping the model (Nemotron ↔ local executor) changes the output and the
observations, but the seal is computed over whatever the oracle observes.

## Alternatives rejected

- **Model as judge.** Rejected because it violates the LLM-out-of-the-loop
  invariant. Best argument for it: the model can evaluate semantic quality
  that keyword checks cannot.
- **Model in the decision path with a seal after.** Rejected because the
  seal must be computed before the model is called to prevent the model from
  influencing the sealed value. Best argument for it: simpler architecture.
- **No model at all (deterministic only).** Rejected for L5 because the
  purpose of L5 is to observe model behavior under different skill variants.
  Without a model, there is no behavior to observe. Best argument for it:
  fully deterministic, no external dependencies.

## Assumption this rests on

The property oracle's keyword checks are sufficient to detect the behavioral
difference caused by the polarity-inversion mutation. The local executor
verifies this: the mutant output recommends unbounded retry (P3 FAIL) while
the original passes. A real model may produce different wording, but the
property checks are designed to catch the semantic category (unbounded vs.
bounded retry), not specific phrases.

## Consequences

Accepted now:

- The model is the subject of observation, not the judge.
- The property oracle is deterministic and sealed.
- The Nebius executor is real code that will work with an API key.
- The report honestly documents BLOCKED when the key is absent.

Deferred:

- semantic quality evaluation (requires a model as judge, which is out of
  scope for the deterministic core);
- statistical analysis across multiple model samples;
- generalization beyond the pinned task/model/runtime.

## Revisit trigger

Revisit when L6 (Bob workflow) needs the model to propose repairs, or when
L7 (closed repair loop) needs the model to evaluate whether a repair
restores a property. At that point, the model's proposal is evidence, not a
verdict — the deterministic re-audit and replay decide.
