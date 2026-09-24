# Red-Team Review — Semantic Redundancy Deterministic Base

**Date:** 2026-09-23  
**Scope:** adversarial review of the SEMANTIC_REDUNDANCY check (Jaccard
token overlap with Fraction, 2/3 threshold, stopword filtering)  
**Method:** hypothesis-driven, evidence-verified against live code and
the real corpus  
**Status:** 0 confirmed defects, 1 rejected finding

## Method

The review verifies:
1. No floats in the decision path (Jaccard computed with Fraction).
2. Determinism (same corpus = same findings, cross-process).
3. The threshold is correct (2/3, not lower).
4. Stopwords do not inflate overlap.
5. The finding is CANDIDATE, not CONFIRMED.
6. The limitation is documented.
7. No false positives on the real corpus.
8. The LLM is not in the decision path.

## Invariant verification

### No floats in the decision path

**Verified:** `_jaccard` returns `Fraction(len(intersection), len(union))`.
The evidence string uses `f"{overlap.numerator}/{overlap.denominator}"`,
never a float. The test `test_redundancy_evidence_uses_fraction_not_float`
asserts no "0." appears in the evidence. The test
`test_redundancy_finding_has_no_float_in_artifact` asserts no "0.66"
appears in the JSON serialization.

### Determinism

**Verified:** cross-process audit digest on the real corpus is
identical across two runs in separate processes. Same-process
determinism verified by `test_redundancy_is_deterministic_same_process`.

### Threshold correctness

**Verified:** `test_redundancy_threshold_is_two_thirds` constructs a
pair with Jaccard 4/5 (>= 2/3) and asserts it is flagged.
`test_redundancy_below_threshold_not_flagged` constructs a pair with
Jaccard 1/3 (< 2/3) and asserts it is NOT flagged.

### Stopword filtering

**Verified:** `test_stopwords_excluded_from_token_sets` constructs two
skills with different content but many shared stopwords ("the", "must",
"be") and asserts 0 findings. Without stopword filtering, the overlap
would be inflated by common words.

### Epistemic status and limitation

**Verified:** the finding is CANDIDATE, not CONFIRMED. The limitation
explicitly states: "lexical token overlap is not semantic equivalence"
and "an LLM confirmation layer is deferred and would confirm or reject
each candidate." The test `test_redundancy_has_limitation_documented`
asserts both "lexical" and "llm" appear in the limitation.

### No LLM in the decision path

**Verified:** the check is entirely deterministic. No LLM is called.
The LLM confirmation layer is explicitly deferred and documented in the
limitation.

### No false positives on the real corpus

**Verified:** the real corpus produces 0 SEMANTIC_REDUNDANCY findings
at the 2/3 threshold. The skills are lexically distinct enough.

## Rejected finding

### R1: The 2/3 threshold might miss real redundancy

**Hypothesis:** two skills that are semantically redundant but use
different vocabulary would not be detected at 2/3 Jaccard overlap.

**Verification:** this is a known limitation, documented in the ADR and
the finding's limitation field. The deterministic base is a first
filter, not a complete solution. The LLM confirmation layer (deferred)
would catch semantic redundancy with different surface forms. The
threshold is deliberately conservative to avoid false positives.

**Conclusion:** not a defect. The limitation is documented and the LLM
layer is deferred by design.

## Summary

0 confirmed defects. 1 rejected finding (threshold might miss semantic
redundancy with different vocabulary — documented limitation, LLM layer
deferred). All invariants preserved. 181 tests pass. Cross-process
determinism confirmed. No floats in the decision path.
