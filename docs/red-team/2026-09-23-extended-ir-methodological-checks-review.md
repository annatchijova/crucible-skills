# Red-Team Review — Extended IR and Methodological Defect Checks

**Date:** 2026-09-23  
**Scope:** adversarial review of the IR extension (subjects, procedural
steps), modality extraction fix, and two new L2 checks
(METHODOLOGICAL_VACUITY, NORMATIVE_CONFLICT)  
**Method:** hypothesis-driven, evidence-verified against live code and
the real corpus  
**Status:** 1 confirmed defect fixed, 1 rejected finding

## Method

The review verifies:
1. The modality extraction fix is correct (MUST NOT → MUST_NOT).
2. Subject extraction handles markdown formatting.
3. Procedural step extraction is correct.
4. METHODOLOGICAL_VACUITY detects the right thing.
5. NORMATIVE_CONFLICT detects the right thing.
6. No false positives on the real corpus.
7. Determinism is preserved.
8. No floats in the decision path.
9. No LLM in the decision path.

## Confirmed defect (fixed)

### D1: Markdown `**` in subjects caused 664 false NORMATIVE_CONFLICT findings

**Firstness:** 664 NORMATIVE_CONFLICT findings on the real corpus, all
with subject `**`.

**Secondness:** the auditor should not produce 664 confirmed
contradictions on a well-formed corpus. This is a false positive
explosion.

**Thirdness (root cause):** many rules in the corpus start with
`**MUST**` or `**MUST NOT**` (modal verb in bold). The subject extractor
took everything before the modal verb, which was just `**`. All rules
with `**MUST**` got the same subject `**`, triggering NORMATIVE_CONFLICT
for every pair.

**Fix:** strip markdown formatting (`**`, `*`, `` ` ``, `_`) and
leading list/table/heading markers from the subject. If the result is
empty, the rule has no explicit subject (the modal is at the start of
the line). Rules with empty subjects are excluded from
NORMATIVE_CONFLICT matching.

**Verification:** after the fix, the real corpus produces 0
NORMATIVE_CONFLICT findings. The subjects are now meaningful (each
appears at most once). 169 tests pass. Cross-process determinism
confirmed.

## Rejected finding

### R1: METHODOLOGICAL_VACUITY might false-positive on skills with embedded procedural prose

**Hypothesis:** a skill that has procedural content in prose (no `## Steps`
section, no numbered list) would be flagged as vacuous even though it
has methodology.

**Verification:** this is a known limitation, documented in the
finding's `limitation` field: "procedural step extraction is
section-heading and numbered-list based; a skill with embedded
procedural prose (no ## Steps section, no numbered list) will be a
false positive." The epistemic status is CANDIDATE, not CONFIRMED.
The limitation is explicitly disclosed, not hidden.

**Conclusion:** not a defect. The limitation is documented and the
epistemic status is honest.

## Invariant verification

### Determinism

**Verified:** cross-process audit digest on the real corpus is
identical across two runs in separate processes.

### No floats in decision paths

**Verified:** no floats in the IR or audit artifact. All values are
strings, integers, booleans, or nested structures thereof.

### No LLM in decision paths

**Verified:** subject extraction, procedural step extraction,
METHODOLOGICAL_VACUITY, and NORMATIVE_CONFLICT are all deterministic.
No LLM is called.

### Honest degradation

**Verified:** both new checks document their limitations in the
finding's `limitation` field. METHODOLOGICAL_VACUITY is CANDIDATE
(heuristic). NORMATIVE_CONFLICT is CONFIRMED (direct contradiction).
CONDITIONAL_CONTRADICTION replaces NORMATIVE_CONFLICT in the
AUDIT_LIMITATIONS list.

### Source evidence

**Verified:** both new checks include `source_span` and `rule_id`
pointing to the first rule that triggered the finding.

## Real corpus results

| Check | Findings | Epistemic status |
|---|---|---|
| NORMATIVE_CONFLICT | 0 | — |
| METHODOLOGICAL_VACUITY | 0 | — |
| REQUIREMENT_WITHOUT_CHECK | 1 (compact) | CANDIDATE |

The real corpus is well-formed: no contradictions, no vacuous skills.
The `compact` skill has 2 MUST/SHOULD rules, 0 checks, but 3 procedural
steps — so it triggers REQUIREMENT_WITHOUT_CHECK but not
METHODOLOGICAL_VACUITY.

## Summary

1 confirmed defect (markdown `**` in subjects) fixed. 1 rejected
finding (embedded procedural prose, documented limitation). All
invariants preserved. 169 tests pass. Cross-process determinism
confirmed.
