# ADR-0014: Description-Body Gap — Substantive Description, Empty Body

**Status:** Accepted  
**Date:** 2026-09-23  
**Reversibility:** high; the check is additive

## Context

DESCRIPTION_BODY_GAP was abstained because the L1 extractor is lexical
and conservative. The user requested detection of skills whose
description promises something but whose body doesn't deliver.

## Decision

Implement DESCRIPTION_BODY_GAP as a check that detects the most extreme
form of description-body gap: a skill with a substantive description
(>= 10 meaningful tokens) but zero extractable rules, checks, and
procedural steps.

### What the check detects

A skill where:
- The description has >= 10 meaningful tokens (after stopword removal)
- The body has 0 rules (no MUST/SHOULD/MAY)
- The body has 0 checks
- The body has 0 procedural steps

This is the most extreme form of description-body gap: the description
promises something, but the body has no extractable normative structure
at all.

### Epistemic status: CANDIDATE

The finding is CANDIDATE, not CONFIRMED, because the L1 extractor is
lexical and conservative. A skill with zero extracted rules may use
non-RFC-2119 normative language (e.g., "always", "never", "ensure")
that the extractor does not capture. The limitation explicitly
discloses this: "cannot distinguish extractor scope from a real
description-body gap."

### Distinction from METHODOLOGICAL_VACUITY

- **METHODOLOGICAL_VACUITY**: skill WITH rules but WITHOUT steps or
  checks. The skill says what to require but not how to execute.
- **DESCRIPTION_BODY_GAP**: skill WITHOUT any extractable structure
  (no rules, no checks, no steps). The description promises something
  but the body has no extractable normative content at all.

### Real corpus results

The real corpus produces 27 DESCRIPTION_BODY_GAP findings (27/97 =
28%). This is a high rate, but expected: many skills in the corpus use
non-RFC-2119 normative language ("always", "never", "ensure", "do not")
instead of MUST/SHOULD/MAY. The L1 extractor only captures RFC-2119
modalities. All 27 findings are CANDIDATE with the limitation
documented.

This is an honest signal: 28% of the corpus has no extractable
normative structure. Either the extractor needs to be extended to
capture non-RFC-2119 normative language, or these skills genuinely
lack normative structure. The check cannot distinguish the two cases
— that's why it's CANDIDATE.

## Alternatives rejected

- **Token overlap between description and body.** Rejected: the
  description uses high-level domain terms while the body uses
  implementation terms. Low overlap is the normal case, not a defect
  signal. The extreme case (zero extractable structure) is a much
  stronger signal.
- **CONFIRMED status.** Rejected: the extractor is conservative. A
  skill may have normative content in non-RFC-2119 language that the
  extractor doesn't capture. CANDIDATE is the honest epistemic status.
- **Higher token threshold.** Rejected: 10 tokens is the minimum for a
  "substantive" description. A higher threshold would miss skills with
  short but meaningful descriptions.

## Consequences

Accepted now:
- DESCRIPTION_BODY_GAP is the 12th emitted check. The auditor emits 12
  checks and abstains on 2.
- The real corpus produces 27 CANDIDATE findings (28% of skills). All
  are honest CANDIDATEs with documented limitations.
- 10 new falsifiable tests cover detection, no-false-positives (with
  rules, with checks, with steps, short description), evidence,
  limitation, distinction from METHODOLOGICAL_VACUITY, determinism, and
  non-abstention.

Deferred:
- Extending the L1 extractor to capture non-RFC-2119 normative language
  ("always", "never", "ensure", "do not") would reduce false positives.
- An LLM confirmation layer could distinguish extractor scope from real
  gaps.
