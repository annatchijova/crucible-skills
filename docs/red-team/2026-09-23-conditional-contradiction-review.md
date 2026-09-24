# Red-Team Review — Conditional Contradiction Check

**Date:** 2026-09-23  
**Scope:** adversarial review of the CONDITIONAL_CONTRADICTION check
(condition extraction, effective polarity computation, overlap
matching, non-duplication with NORMATIVE_CONFLICT)  
**Method:** hypothesis-driven, evidence-verified against live code and
the real corpus  
**Status:** 0 confirmed defects, 1 rejected finding

## Method

The review verifies:
1. Condition extraction is correct (exception vs scope types).
2. Effective polarity computation is correct (exception inverts, scope
   preserves).
3. Overlap matching is conservative (no false positives on different
   conditions).
4. Non-duplication with NORMATIVE_CONFLICT.
5. No floats in the decision path.
6. Determinism.
7. No LLM in the decision path.
8. No false positives on the real corpus.

## Invariant verification

### Condition extraction

**Verified:** `test_exception_type_extracted` asserts "except for X" is
extracted as type "exception". `test_scope_type_extracted` asserts
"for X" is extracted as type "scope".
`test_unless_extracted_as_exception` asserts "unless X" is exception.
`test_when_extracted_as_scope` asserts "when X" is scope.

### Effective polarity

**Verified:** `test_contradiction_detected_exception_vs_scope` confirms
that an exception (inverts polarity) and a scope (preserves polarity)
on the same condition produce a contradiction. The fixture has both
rules as MUST (positive base), but the exception inverts Rule A to
negative under "read-only operations" while Rule B stays positive.

### Overlap matching

**Verified:** `test_no_contradiction_when_different_conditions` asserts
that "read-only operations" and "write operations" do not overlap.
`test_conditions_overlap` uses substring + token-subset matching, which
is conservative.

### Non-duplication with NORMATIVE_CONFLICT

**Verified:** `test_no_contradiction_when_normative_conflict_handles_it`
asserts that unconditional MUST vs MUST_NOT produces NORMATIVE_CONFLICT
but NOT CONDITIONAL_CONTRADICTION. The check explicitly skips pairs
where `(modality_i, modality_j)` is in `_CONFLICT_PAIRS`.

### No floats

**Verified:** the check uses only string comparisons and set
operations. No floats are computed or stored.

### Determinism

**Verified:** cross-process audit digest on the real corpus is
identical across two runs. `test_contradiction_is_deterministic` asserts
same-process determinism.

### No LLM

**Verified:** the check is entirely deterministic. No LLM is called.

### No false positives on the real corpus

**Verified:** the real corpus produces 0 CONDITIONAL_CONTRADICTION
findings. The skills do not have conflicting conditional rules.

## Rejected finding

### R1: "for X" is ambiguous (could be a recipient, not a condition)

**Hypothesis:** "for read-only operations" is a condition, but "for the
user" is a recipient. The pattern `for X` might extract recipients as
conditions, causing false positives.

**Verification:** this is a known limitation, documented in the ADR:
"'for X' is ambiguous (could be a recipient), but in normative rules it
often introduces a scope condition." The check only compares conditions
between rules with the same subject, so a false condition extraction
would only matter if two rules with the same subject have conflicting
polarity under that false condition. This is unlikely but possible.

**Conclusion:** not a defect. The ambiguity is documented and the
impact is limited by the same-subject requirement. The LLM layer
(deferred) could disambiguate.

## Summary

0 confirmed defects. 1 rejected finding ("for X" ambiguity — documented
limitation). All invariants preserved. 199 tests pass. Cross-process
determinism confirmed. No floats, no LLM in the decision path.
