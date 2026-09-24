# ADR-0010: Extended IR for Methodological Defect Detection

**Status:** Accepted  
**Date:** 2026-09-23  
**Reversibility:** high; the new IR fields are additive

## Context

The L2 auditor abstained on NORMATIVE_CONFLICT because the IR did not
extract rule subjects. It also could not detect METHODOLOGICAL_VACUITY
because the IR did not extract procedural steps. The user requested
detection of methodologically useless and contradictory skills.

## Decision

Extend the L1 IR with two new fields and add two new L2 checks.

### IR extensions (additive, backward-compatible)

1. **Rule subjects:** each rule now carries a `subject` field — the noun
   phrase before the modal verb, normalized to lowercase with leading
   articles and markdown formatting stripped. Rules where the modal
   verb is at the start of the line (e.g., `**MUST** do X`) have an
   empty subject (no explicit subject).

2. **Procedural steps:** each skill now carries a `procedural_steps`
   list — numbered lists and bullet lists extracted from procedural
   sections (`## Steps`, `## Procedure`, `## How to`, `## Process`,
   `## Workflow`, `## Method`) and numbered lists anywhere in the body.

### Modality extraction fix

The previous modality regex `\b(MUST_NOT|SHOULD_NOT|MUST|SHOULD|MAY)\b`
matched `MUST` when the text said `MUST NOT` (with a space), because
`MUST_NOT` (underscore) does not match `MUST NOT` (space). The regex is
now `\b(MUST\s+NOT|SHOULD\s+NOT|MUST|SHOULD|MAY)\b` and the captured
modality is normalized to `MUST_NOT` / `SHOULD_NOT`.

### New L2 checks

1. **METHODOLOGICAL_VACUITY** (CANDIDATE): a skill with normative rules
   (MUST/SHOULD/MUST_NOT/SHOULD_NOT) but 0 procedural steps AND 0 checks.
   The skill says what to do but never how. Limitation: procedural step
   extraction is section-heading and numbered-list based; a skill with
   embedded procedural prose will be a false positive.

2. **NORMATIVE_CONFLICT** (CONFIRMED): two rules with the same normalized
   subject but contradictory modalities (MUST vs MUST_NOT, or SHOULD vs
   SHOULD_NOT). Detects both within-skill and cross-skill contradictions.
   Limitation: subject extraction is lexical; two rules with different
   surface forms but the same semantic subject will not be detected.

### Removed from AUDIT_LIMITATIONS

NORMATIVE_CONFLICT is no longer abstained — it is now implemented.
CONDITIONAL_CONTRADICTION replaces it in the limitations list, with the
reason that the IR extracts subjects but not conditions or exceptions.

## Alternatives rejected

- **LLM-based subject extraction.** Rejected: would put an LLM in the
  decision path. The lexical extractor is deterministic and its
  limitations are documented.
- **Full NLP for contradiction detection.** Rejected: same reason. The
  lexical subject match catches the clear case (same subject, opposite
  modality) and documents what it cannot catch (semantic equivalence
  with different surface forms).
- **Bump schema version to v2.** Rejected: the changes are additive.
  Existing consumers ignore the new fields. The digest changes, but
  the schema is backward-compatible.

## Consequences

Accepted now:
- The IR has two new fields (`subject` on rules, `procedural_steps` on
  skills). Existing consumers ignore them.
- The auditor has two new checks. The AUDIT_LIMITATIONS list is updated
  (NORMATIVE_CONFLICT removed, CONDITIONAL_CONTRADICTION added).
- The RuleBasedProposer has a new repair pattern for
  METHODOLOGICAL_VACUITY (adds Steps and Checks sections).
- The real corpus produces 0 NORMATIVE_CONFLICT and 0
  METHODOLOGICAL_VACUITY findings — the corpus is well-formed.
- 21 new falsifiable tests cover both checks, the modality fix, subject
  extraction, and procedural step extraction.

Deferred:
- CONDITIONAL_CONTRADICTION (needs condition/exception extraction).
- SCOPE_TRIGGER_MISMATCH (needs trigger/scope extraction).
- SEMANTIC_REDUNDANCY (needs semantic similarity, hard deterministically).
