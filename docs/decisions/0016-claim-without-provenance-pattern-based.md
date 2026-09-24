# ADR-0016: Claim-Without-Provenance — Pattern-Based Claim Extraction

**Status:** Accepted  
**Date:** 2026-09-23  
**Reversibility:** high; the claims field is additive

## Context

CLAIM_WITHOUT_PROVENANCE was the last abstained check. The IR did not
extract structured claims with numeric flags. The user requested
detection of skills that make factual claims without citing sources.

## Decision

Extend the L1 IR with claim extraction and add the
CLAIM_WITHOUT_PROVENANCE check.

### IR extension (additive)

Each rule now carries a `claims` list. A claim is a factual assertion
with a numeric value or standards reference:

- **percentage** — e.g., "90%"
- **time** — e.g., "50ms", "3 seconds"
- **count** — e.g., "5 attempts", "3 retries"
- **standard** — e.g., "NIST SP 800-53", "OWASP Top 10", "WCAG 2.1"
- **year** — e.g., "2026"

Each claim records `has_provenance` — whether the rule text contains a
provenance indicator:

- Source citation: "per X", "according to X", "source: X", "see X"
- Standards reference: NIST, OWASP, CWE, CVE, MITRE, ISO, RFC, W3C,
  WCAG, WCA (with optional "SP" between name and number)
- URL: https://...
- Parenthetical citation: (Author, Year)

### L2 check: CLAIM_WITHOUT_PROVENANCE

A rule with claims where `has_provenance` is False is a CANDIDATE
finding: the rule makes a factual assertion but does not cite a
source. The claim may be common knowledge, derived from the skill's
domain expertise, or stated without evidence — the check cannot
distinguish.

### Real corpus results

The real corpus produces 0 CLAIM_WITHOUT_PROVENANCE findings. The
only rule with a numeric claim ("WCA 2026") has a standards reference
as provenance, so it is not flagged.

## Alternatives rejected

- **CONFIRMED status.** Rejected: provenance detection is
  pattern-based. A claim may have provenance in a form not captured by
  the patterns. CANDIDATE is the honest status.
- **Claims in body prose (not just rules).** Rejected: body prose
  contains code examples, illustrations, and non-normative claims.
  Restricting to normative rules is more conservative and produces
  fewer false positives.
- **Semantic provenance detection (LLM).** Rejected: would put the
  LLM in the decision path. The deterministic base produces candidates;
  the LLM confirms or rejects (deferred).

## Consequences

Accepted now:
- CLAIM_WITHOUT_PROVENANCE is the 14th emitted check. The auditor
  emits 14 checks and abstains on 0. All checks are now emitted.
- The IR has a new `claims` field on rules. Existing consumers ignore it.
- The real corpus produces 0 findings.
- 14 new falsifiable tests cover detection, no-false-positives (with
  provenance, no claims, URL provenance), claim extraction
  (percentage, time, count, standard), evidence, limitation,
  determinism, and non-abstention.

Deferred:
- LLM confirmation layer for CLAIM_WITHOUT_PROVENANCE candidates.
- Extending claim extraction to body prose (not just rules).
