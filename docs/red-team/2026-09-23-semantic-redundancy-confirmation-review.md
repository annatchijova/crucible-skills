# Red-Team Review — Semantic Redundancy Confirmation Layer (L2.5)

**Date:** 2026-09-23  
**Scope:** adversarial review of the SEMANTIC_REDUNDANCY confirmation
layer (artifact schema, LLM isolation, executor protocol, determinism,
honest degradation)  
**Method:** hypothesis-driven, evidence-verified against live code and
the real corpus  
**Status:** 0 confirmed defects, 1 rejected finding

## Method

The review verifies:
1. The L2 audit artifact is NEVER modified by the confirmation.
2. The confirmation is a separate artifact with its own digest.
3. The confirmation does not promote CANDIDATE to CONFIRMED in the L2 audit.
4. The Nebius executor is BLOCKED without an API key (no simulation).
5. The mock executor is deterministic.
6. No floats in the confirmation artifact.
7. Cross-process determinism.
8. The confirmation references the source audit digest.

## Invariant verification

### LLM out of the decision path

**Verified:** `test_audit_unchanged_after_confirmation` asserts the L2
audit digest and findings are unchanged after confirmation.
`test_confirmation_does_not_promote_to_confirmed` asserts the L2
finding stays CANDIDATE.

### Separate artifact with own digest

**Verified:** `test_artifact_has_digest` asserts the confirmation has
a SHA-256 digest. `test_artifact_references_source_audit` asserts it
references the L2 audit digest.

### Honest degradation (BLOCKED)

**Verified:** `test_nebius_blocked_without_api_key` asserts the
confirmation is BLOCKED without NEBIUS_API_KEY.
`test_nebius_blocked_does_not_simulate` asserts no CONFIRMED or
REJECTED verdicts are fabricated when BLOCKED.

### Mock executor determinism

**Verified:** `test_mock_executor_is_deterministic` asserts two runs
produce the same digest. `test_confirmation_is_deterministic` asserts
the same.

### No floats

**Verified:** `test_no_floats_in_confirmation` recursively checks the
entire confirmation artifact for float values.

### Schema

**Verified:** `test_artifact_has_correct_schema_version` asserts
`crucible-confirmation/v1`.

### Mock executor behavior

**Verified:** `test_mock_confirms_redundant_pair` asserts CONFIRMED for
a redundant pair. `test_mock_rejects_non_redundant_pair` asserts
REJECTED (or no candidates) for a non-redundant pair.

### No candidates

**Verified:** `test_no_candidates_produces_empty_confirmation` asserts
the confirmation is valid and empty when there are no SEMANTIC_REDUNDANCY
findings.

### Summary

**Verified:** `test_summary_counts_are_correct` asserts the summary
counts match the confirmations.

## Real corpus findings

The real corpus produces 0 SEMANTIC_REDUNDANCY CANDIDATEs. The
confirmation layer has 0 confirmations. Cross-process determinism
confirmed.

## Rejected finding

### R1: The mock executor is not a real LLM

**Hypothesis:** the mock executor uses a line-overlap heuristic, not a
real LLM. It may produce different verdicts than Nemotron.

**Verification:** this is a known design decision, documented in the
ADR: "a mock executor is needed for testing the harness without
external dependencies. Not an LLM." The mock executor exists to test
the confirmation harness, not to replace the LLM. When NEBIUS_API_KEY
is available, the NebiusConfirmExecutor is used instead.

**Conclusion:** not a defect. The design is intentional and documented.

## Summary

0 confirmed defects. 1 rejected finding (mock executor is not a real
LLM — intentional design decision). All invariants preserved. 265
tests pass. Cross-process determinism confirmed. No floats, no LLM in
the decision path, honest BLOCKED status without API key.
