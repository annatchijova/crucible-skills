# Red-Team Review — Description-Body Gap Check

**Date:** 2026-09-23  
**Scope:** adversarial review of the DESCRIPTION_BODY_GAP check
(substantive description with zero extractable body structure)  
**Method:** hypothesis-driven, evidence-verified against live code and
the real corpus  
**Status:** 0 confirmed defects, 1 rejected finding

## Method

The review verifies:
1. The check detects the right thing (substantive description, empty body).
2. No false positives on skills with rules, checks, or steps.
3. No false positives on skills with short descriptions.
4. Distinction from METHODOLOGICAL_VACUITY.
5. No floats in the decision path.
6. Determinism.
7. No LLM in the decision path.
8. Real corpus findings are classified honestly.

## Invariant verification

### Detection

**Verified:** `test_gap_detected_when_description_substantive_but_body_empty`
asserts a skill with 11+ meaningful tokens and zero body structure is
flagged. `test_gap_not_detected_when_body_has_rules` asserts a skill
with rules is NOT flagged. `test_gap_not_detected_when_body_has_checks`
asserts a skill with checks is NOT flagged.
`test_gap_not_detected_when_body_has_procedural_steps` asserts a skill
with steps is NOT flagged.

### Short description

**Verified:** `test_gap_not_detected_when_description_too_short` asserts
a skill with a 1-token description is NOT flagged (not enough substance
to promise anything).

### Distinction from METHODOLOGICAL_VACUITY

**Verified:** `test_gap_distinct_from_vacuity` asserts a skill with
rules but no steps gets METHODOLOGICAL_VACUITY, not DESCRIPTION_BODY_GAP.
The checks are complementary: VACUITY detects skills WITH rules but
WITHOUT steps/checks; GAP detects skills WITHOUT any structure.

### No floats

**Verified:** the check uses only integer counts and string
comparisons. No floats are computed.

### Determinism

**Verified:** cross-process audit digest on the real corpus is
identical across two runs. `test_gap_is_deterministic` asserts
same-process determinism.

### No LLM

**Verified:** the check is entirely deterministic. No LLM is called.

### Non-abstention

**Verified:** `test_gap_not_in_limitations` asserts DESCRIPTION_BODY_GAP
is not in the limitations list.

## Real corpus findings

The real corpus produces 27 DESCRIPTION_BODY_GAP findings (28% of
skills). All are CANDIDATE with the limitation: "the L1 extractor is
lexical and conservative; a skill with zero extracted rules may use
non-RFC-2119 normative language that the extractor does not capture."

This is an honest signal: 28% of the corpus has no extractable
normative structure. The check cannot distinguish "extractor can't see
the normative language" from "there is no normative language." That's
why it's CANDIDATE.

## Rejected finding

### R1: 27 findings is too many — the check is too aggressive

**Hypothesis:** 28% false positive rate means the check is not useful.

**Verification:** all 27 findings are CANDIDATE, not CONFIRMED. The
limitation explicitly discloses the conservative extractor scope. The
high rate is a known consequence of the L1 extractor only capturing
RFC-2119 modalities (MUST/SHOULD/MAY). Many skills use non-RFC-2119
normative language ("always", "never", "ensure"). The check is
designed to produce candidates for review, not to assert defects. The
27 findings are a signal that the extractor could be extended, not
that 28% of skills are broken.

**Conclusion:** not a defect. The high rate is honest, documented, and
CANDIDATE. Extending the extractor to capture non-RFC-2119 normative
language would reduce false positives — that's a future improvement,
not a defect in this check.

## Summary

0 confirmed defects. 1 rejected finding (high finding rate — honest
CANDIDATEs with documented limitation). All invariants preserved. 223
tests pass. Cross-process determinism confirmed. No floats, no LLM in
the decision path.
