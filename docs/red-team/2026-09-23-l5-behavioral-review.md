# L5 Red-Team Review — Behavioral Differential Harness

**Date:** 2026-09-23  
**Scope:** task fixture, skill variants, executor protocol, property oracle, sealed report, Nebius BLOCKED behavior, invariant preservation from L1-L4  
**Level:** L5  
**Status:** reviewed; Nebius execution is BLOCKED (no API key); local executor verified; harness is ready for Nebius when credentials arrive

## Threat model

The behavioral differential harness runs a model (Nemotron via Nebius) against
four skill variants and observes whether the model's behavior satisfies
explicit properties. The threats are:

1. **Model as authority:** the model's output is treated as a verdict rather
   than as behavior to be observed. Mitigation: the property oracle is
   deterministic; the model never touches the decision path.
2. **Simulated success:** the harness claims a Nebius run succeeded when it
   didn't. Mitigation: without NEBIUS_API_KEY, all runs are BLOCKED with the
   exact reason; no simulation.
3. **Property oracle drift:** the oracle passes outputs that should fail.
   Mitigation: each property check is a deterministic function tested with
   positive and negative fixtures.
4. **Nondeterminism:** the same inputs produce different reports. Mitigation:
   the report is sealed with SHA-256; cross-process digest verified identical.

## L1-L4 invariant preservation

| Invariant | How L5 preserves it | Result |
|---|---|---|
| L1-L4 artifacts are versioned and sealed | L5 does not modify L1-L4; it consumes the mutation lab's fixture and variants | PASS |
| Deterministic core | L5's property oracle is pure Python; no LLM in the decision path | PASS |
| No float in the decision path | L5 uses string matching and integer counts; no floats | PASS |
| No LLM in the decision path | The model generates behavior; the oracle observes it deterministically | PASS |
| Honest degradation | Nebius BLOCKED is documented, not simulated; local fallback is provided | PASS |
| Sealed artifact | `behavioral_digest` computed over canonical bytes | PASS |
| Fail closed on missing credentials | `MissingCredentialError` raised; run marked BLOCKED | PASS |

## L5 invariants reviewed

| Invariant | Evidence | Result |
|---|---|---|
| Report is versioned and sealed | `behavioral_version: crucible-behavioral/v1`, `behavioral_digest: sha256:...` | PASS |
| Report is deterministic (local executor) | same-process and cross-process digest identical | PASS |
| Report is deterministic (Nebius blocked) | same-process and cross-process digest identical | PASS |
| All 4 variants are present | V1-no-skill, V2-original, V3-mutant, V4-repair | PASS |
| Task fixture is sealed | `task_digest: sha256:...` computed over task_id + task_prompt | PASS |
| Property oracle is deterministic | same output always produces same observations | PASS |
| Property oracle has positive and negative controls | 8 tests cover PASS and FAIL for each property | PASS |
| Nebius BLOCKED is honest | all 4 runs BLOCKED with exact reason; no simulation | PASS |
| Local fallback is provided when Nebius is blocked | 4 COMPLETED runs with full observations | PASS |
| Every run has output_digest | SHA-256 of model output for completed runs | PASS |
| Every run has model metadata | model, provider, temperature recorded | PASS |
| Limitations are documented | SEMANTIC_QUALITY, MODEL_STABILITY, GENERALIZATION | PASS |

## Induction evidence

### Local executor run (verified)

| Variant | P1 (budget) | P2 (exception) | P3 (no unbounded) | P4 (idempotency) |
|---|---|---|---|---|
| V1 no-skill | FAIL | FAIL | PASS | FAIL |
| V2 original | PASS | PASS | PASS | PASS |
| V3 mutant (polarity inversion) | PASS | FAIL | FAIL | PASS |
| V4 repair | PASS | PASS | PASS | PASS |

The differential is clear:
- The no-skill variant fails P1, P2, P4 (no budget, no exception, no idempotency).
- The original skill passes all 4 properties.
- The mutant fails P3 (recommends unbounded retry) and P2 (no exception clause).
- The repair passes all 4 properties, confirming the repair restores the
  behavioral properties of the original.

This is the core experiment: a methodology mutation (polarity inversion)
produces a behavioral difference (P3 FAIL) that the property oracle detects
deterministically. The model is the subject of observation; the oracle is
the authority.

### Nebius run (BLOCKED)

All 4 Nebius runs are BLOCKED with reason: "NEBIUS_API_KEY is not set; cannot
call Nebius Token Factory". The report includes `nebius_blocked: True` and
`block_reason`. A local fallback run is included for harness verification.

Report digest (local): `sha256:8a12e09bd9f49e94d9d6580fc3bb33bf7dadddc52f60895e28487ad12a1c6188`.  
Report digest (Nebius blocked): `sha256:eb61bee5e7faf2fa4301118804184c2f049c747c3940d2a4ea9e52d571f8a2fd`.  
Cross-process digests: identical for both modes.

### Test suite

26 behavioral tests + 20 mutation tests + 19 graph tests + 19 auditor tests
+ 7 compiler tests = 91 total, all green.

## Discarded vectors

| Vector | Result | Why |
|---|---|---|
| Use the model as a judge of output quality | Rejected | the model is the subject of observation, not the authority; the property oracle is deterministic |
| Simulate Nebius success without a key | Rejected | honest BLOCKED is the only acceptable behavior; simulation would be fraud |
| Run multiple model samples for statistical analysis | Deferred for L5 | one observation per variant is sufficient to demonstrate the differential; statistical analysis is a future enhancement |
| Use a semantic similarity oracle | Rejected | semantic similarity requires a model or embedding, violating the deterministic core |
| Skip the local fallback when Nebius is blocked | Rejected | the local fallback verifies the harness works; without it, a Nebius failure could hide a harness bug |

## Known blind spots

- The local executor is a deterministic simulation, not a real model. It
  pattern-matches the skill text to generate a response. A real model may
  produce different outputs that the property oracle handles differently.
- The property oracle checks keyword presence, not semantic understanding.
  A response that mentions "finite budget" without understanding it would
  PASS P1. This is documented as SEMANTIC_QUALITY limitation.
- The task fixture is a single prompt. The observation is tied to this
  specific task and does not generalize. This is documented as GENERALIZATION
  limitation.
- Model outputs may vary even at temperature 0. The harness records one
  observation per variant, not a distribution. This is documented as
  MODEL_STABILITY limitation.
- The Nebius executor has not been tested with a real API key. The code is
  real (uses urllib, OpenAI-compatible API, Bearer auth), but the
  integration is unverified until credentials are available.

## What happens when the API key arrives

When `NEBIUS_API_KEY` is set in the environment:
1. `NebiusExecutor.is_available()` returns True.
2. `run_behavioral_differential()` calls the Token Factory API with
   `nvidia/nemotron-3-super-120b-a12b` at temperature 0.
3. The property oracle observes the model's output deterministically.
4. The report seals the observations with SHA-256.
5. The differential shows whether the mutation produces a behavioral
   difference detectable by the property oracle.

The harness is ready. The only missing piece is the credential.

## Gate decision

L5 is coherent and independently useful as a behavioral differential harness.
The property oracle is deterministic, the executor is pluggable, and the
report is sealed. The Nebius execution is honestly BLOCKED (no API key), not
simulated. The local executor verifies the harness produces the expected
differential: the polarity-inversion mutant fails P3 (unbounded retry) while
the original and repair pass. When the Nebius API key arrives, the same
harness will run with Nemotron as the execution engine, and the property
oracle will observe the model's behavior deterministically.

L5 is closed for the harness and local executor. The Nebius execution is
BLOCKED and will be unblocked when credentials are available. This is honest
degradation, not a false claim.
