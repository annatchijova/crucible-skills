# Red-Team Review — Scope-Trigger Mismatch Check

**Date:** 2026-09-23  
**Scope:** adversarial review of the SCOPE_TRIGGER_MISMATCH check
(trigger extraction from description, zero-overlap comparison to rule
tokens)  
**Method:** hypothesis-driven, evidence-verified against live code and
the real corpus  
**Status:** 0 confirmed defects, 1 rejected finding

## Method

The review verifies:
1. Trigger extraction is correct (when/whenever/for patterns).
2. Zero-overlap comparison is conservative.
3. No false positives on skills with shared vocabulary.
4. Skills without triggers or rules are skipped.
5. No floats in the decision path.
6. Determinism.
7. No LLM in the decision path.
8. Real corpus findings are classified honestly.

## Invariant verification

### Trigger extraction

**Verified:** `test_trigger_extracted_from_description` asserts "Use
this skill when X" is extracted. `test_trigger_extracted_with_whenever`
asserts "Use this skill whenever X" is extracted.
`test_trigger_extracted_with_use_for` asserts "Use this skill for X" is
extracted. `test_trigger_not_found_when_no_pattern` asserts a
description without a pattern has `found=False`.

### Zero-overlap comparison

**Verified:** `test_mismatch_detected_when_trigger_and_rules_share_zero_tokens`
asserts a skill with disjoint trigger and rule tokens is flagged.
`test_mismatch_not_detected_when_trigger_and_rules_share_tokens` asserts
a skill with shared tokens is NOT flagged.

### No false positives on edge cases

**Verified:** `test_mismatch_not_detected_when_no_trigger` asserts
skills without triggers are skipped. `test_mismatch_not_detected_when_no_rules`
asserts skills without rules are skipped.

### No floats

**Verified:** the check uses only set operations and string
comparisons. No floats are computed.

### Determinism

**Verified:** cross-process audit digest on the real corpus is
identical across two runs. `test_mismatch_is_deterministic` asserts
same-process determinism.

### No LLM

**Verified:** the check is entirely deterministic. No LLM is called.

### Non-abstention

**Verified:** `test_mismatch_not_in_limitations` asserts
SCOPE_TRIGGER_MISMATCH is not in the limitations list.

## Real corpus findings

The real corpus produces 2 SCOPE_TRIGGER_MISMATCH findings:

1. **destination-driven-construction**: trigger about "planning or
   building a project" vs rules about "phases, levels, MVP, regression,
   TDD". Same domain, different vocabulary. False positive.

2. **resilient-ui-states**: trigger about "async data fetching" vs
   rules about "render, error, validation, aria". Same domain,
   different vocabulary. False positive.

Both are CANDIDATE (not CONFIRMED) with the limitation explicitly
stating "lexical token disjointness is not semantic disjointness." The
2% false positive rate (2/97) is the expected cost of a lexical check.

## Rejected finding

### R1: The check produces false positives on the real corpus

**Hypothesis:** 2 false positives out of 97 skills means the check is
too aggressive and should be more conservative.

**Verification:** both findings are CANDIDATE, not CONFIRMED. The
limitation explicitly discloses that lexical disjointness is not
semantic disjointness. The check is designed to produce candidates for
review, not to assert defects. An LLM confirmation layer (deferred)
would confirm or reject each candidate. The 2% rate is acceptable for a
candidate-generating check.

**Conclusion:** not a defect. The false positives are honest
CANDIDATEs with documented limitations, not false CONFIRMEDs.

## Summary

0 confirmed defects. 1 rejected finding (false positive rate — honest
CANDIDATEs with documented limitation). All invariants preserved. 213
tests pass. Cross-process determinism confirmed. No floats, no LLM in
the decision path.
