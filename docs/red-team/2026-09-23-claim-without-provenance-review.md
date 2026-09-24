# Red-Team Review — Claim-Without-Provenance Check

**Date:** 2026-09-23  
**Scope:** adversarial review of the CLAIM_WITHOUT_PROVENANCE check
(claim extraction, provenance detection, unprovenanced claim flagging)  
**Method:** hypothesis-driven, evidence-verified against live code and
the real corpus  
**Status:** 0 confirmed defects, 1 rejected finding

## Method

The review verifies:
1. Claim extraction is correct (percentage, time, count, standard, year).
2. Provenance detection is correct (source citation, standards reference, URL).
3. Only claims without provenance are flagged.
4. Claims with provenance are NOT flagged.
5. Rules without claims are NOT flagged.
6. No floats in the decision path.
7. Determinism.
8. No LLM in the decision path.
9. Real corpus findings are classified honestly.

## Invariant verification

### Claim extraction

**Verified:** `test_percentage_claim_extracted` asserts "90%" is
extracted as "percentage". `test_time_claim_extracted` asserts "50ms"
is extracted as "time". `test_count_claim_extracted` asserts "5
attempts" is extracted as "count". `test_standard_claim_extracted`
asserts "NIST SP 800-53" is extracted as "standard".

### Detection

**Verified:** `test_claim_without_provenance_detected` asserts a rule
with a numeric claim but no provenance is flagged.
`test_claim_with_provenance_not_detected` asserts a rule with "per
NIST SP 800-53" is NOT flagged. `test_no_claim_not_detected` asserts a
rule without claims is NOT flagged.
`test_claim_with_url_provenance_not_detected` asserts a rule with a
URL is NOT flagged.

### No floats

**Verified:** the check uses only string comparisons and boolean
flags. No floats are computed.

### Determinism

**Verified:** cross-process audit digest on the real corpus is
identical across two runs. `test_is_deterministic` asserts same-process
determinism.

### No LLM

**Verified:** the check is entirely deterministic. No LLM is called.

### Non-abstention

**Verified:** `test_not_in_limitations` asserts CLAIM_WITHOUT_PROVENANCE
is not in the limitations list.

## Real corpus findings

The real corpus produces 0 CLAIM_WITHOUT_PROVENANCE findings. The only
rule with a numeric claim ("WCA 2026") has a standards reference as
provenance, so it is not flagged.

## Rejected finding

### R1: The check only extracts claims from rules, not body prose

**Hypothesis:** body prose contains many numeric claims without
provenance that the check misses.

**Verification:** this is a known design decision, documented in the
ADR: "body prose contains code examples, illustrations, and
non-normative claims. Restricting to normative rules is more
conservative and produces fewer false positives." The check is
designed to detect claims in normative rules, not in body prose.
Extending to body prose is a future improvement, not a defect.

**Conclusion:** not a defect. The scope is intentional and documented.

## Summary

0 confirmed defects. 1 rejected finding (body prose scope —
intentional design decision). All invariants preserved. 251 tests
pass. Cross-process determinism confirmed. No floats, no LLM in the
decision path.
