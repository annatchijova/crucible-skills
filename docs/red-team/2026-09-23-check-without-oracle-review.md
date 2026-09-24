# Red-Team Review — Check-Without-Oracle Check

**Date:** 2026-09-23  
**Scope:** adversarial review of the CHECK_WITHOUT_ORACLE check
(oracle_kind extraction, unknown-oracle detection)  
**Method:** hypothesis-driven, evidence-verified against live code and
the real corpus  
**Status:** 0 confirmed defects, 1 rejected finding

## Method

The review verifies:
1. Oracle kind extraction is correct (question, checkbox, command, unknown).
2. Only checks with oracle_kind "unknown" are flagged.
3. Checks with known oracle_kind are NOT flagged.
4. No floats in the decision path.
5. Determinism.
6. No LLM in the decision path.
7. Real corpus findings are classified honestly.

## Invariant verification

### Oracle kind extraction

**Verified:** `test_oracle_kind_question_extracted` asserts a check
ending with ? is "question". `test_oracle_kind_command_extracted`
asserts a check with "verify" is "command".
`test_oracle_kind_checkbox_extracted` asserts a check with [ ] is
"checkbox". `test_oracle_kind_unknown_for_descriptive_check` asserts a
descriptive check is "unknown".

### Detection

**Verified:** `test_without_oracle_detected_for_unknown_check` asserts
a check with oracle_kind "unknown" is flagged.
`test_with_oracle_not_detected_for_question_check`,
`test_with_oracle_not_detected_for_command_check`, and
`test_with_oracle_not_detected_for_checkbox_check` assert checks with
known oracle_kind are NOT flagged. `test_mixed_checks_only_unknown_flagged`
asserts only the unknown check is flagged in a mixed set.

### No floats

**Verified:** the check uses only string comparisons. No floats are
computed.

### Determinism

**Verified:** cross-process audit digest on the real corpus is
identical across two runs. `test_is_deterministic` asserts same-process
determinism.

### No LLM

**Verified:** the check is entirely deterministic. No LLM is called.

### Non-abstention

**Verified:** `test_not_in_limitations` asserts CHECK_WITHOUT_ORACLE is
not in the limitations list.

## Real corpus findings

The real corpus produces 16 CHECK_WITHOUT_ORACLE findings (9% of
checks). All are CANDIDATE with the limitation: "oracle_kind extraction
is pattern-based; a check may be verifiable through domain-specific
means not captured by the patterns."

The 16 checks are mostly descriptive statements or classifications in
## Checks sections that are not actually verifiable oracles. The 9%
rate is reasonable for a pattern-based check.

## Rejected finding

### R1: Some "unknown" checks are actually verifiable

**Hypothesis:** a check like "The sky is blue" is not verifiable, but a
check like "Confirmed exposed — reachable, reached, preconditions hold"
might be verifiable through domain-specific means not captured by the
patterns.

**Verification:** this is a known limitation, documented in the finding's
limitation field: "oracle_kind extraction is pattern-based; a check may
be verifiable through domain-specific means not captured by the
patterns." The finding is CANDIDATE, not CONFIRMED. The LLM confirmation
layer (deferred) could distinguish truly unverifiable checks from
domain-specific verifiable ones.

**Conclusion:** not a defect. The limitation is documented and the
epistemic status is honest.

## Summary

0 confirmed defects. 1 rejected finding (domain-specific verifiability
— documented limitation). All invariants preserved. 237 tests pass.
Cross-process determinism confirmed. No floats, no LLM in the decision
path.
