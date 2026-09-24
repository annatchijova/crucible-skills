# ADR-0011: Semantic Redundancy — Deterministic Lexical Base

**Status:** Accepted  
**Date:** 2026-09-23  
**Reversibility:** high; the check is additive and the threshold is a constant

## Context

SEMANTIC_REDUNDANCY detects when two skills cover the same ground. The
full solution requires semantic understanding — an LLM comparing two
skills and deciding whether they are redundant. But the LLM cannot be
the first filter: it would be expensive, non-deterministic, and would
put the LLM in the decision path.

The user requested: "la de semantic va con llm pero podemos hacer las
bases, vamos de a una" — build the deterministic base now, add the LLM
confirmation layer later.

## Decision

Implement SEMANTIC_REDUNDANCY as a two-layer check:

1. **Deterministic base (now):** Jaccard token overlap on the combined
   description + rules + checks text of each skill. Computed with
   `fractions.Fraction` (no floats). Threshold: 2/3. A pair with
   overlap >= 2/3 is a CANDIDATE finding.

2. **LLM confirmation layer (deferred):** for each candidate, the LLM
   would compare the two skills and confirm or reject the redundancy.
   The LLM never enters the decision path alone — it only confirms or
   rejects candidates produced by the deterministic base.

### Why Jaccard with Fraction

- **Jaccard** is the simplest set-similarity metric. It is
  ordering-independent (no `set`/`dict` ordering issues) and
  deterministic.
- **Fraction** (not float) ensures bit-for-bit reproducibility. The
  overlap is reported as `numerator/denominator` in the evidence string,
  never as a decimal.
- **2/3 threshold** is deliberately high. A lower threshold (e.g.,
  1/2) would produce many false positives on skills that share domain
  vocabulary but govern different scopes. The LLM layer (deferred)
  can lower the effective threshold by confirming or rejecting
  candidates.

### Tokenization

- Lowercase, strip surrounding punctuation, keep internal hyphens.
- Drop single-character tokens.
- Drop a small deterministic stopword list (articles, pronouns,
  modals, prepositions). This is not an NLP pipeline — it is a
  conservative filter to avoid inflating overlap on common English.

### What the finding looks like

```json
{
  "class": "SEMANTIC_REDUNDANCY",
  "epistemic_status": "CANDIDATE",
  "skill": "alpha",
  "evidence": "lexical Jaccard overlap 4/5 with beta (threshold 2/3); ...",
  "limitation": "lexical token overlap is not semantic equivalence; ... an LLM confirmation layer is deferred ..."
}
```

The finding is CANDIDATE, not CONFIRMED, because lexical overlap is not
semantic equivalence. The limitation explicitly discloses this and
mentions the deferred LLM layer.

## Alternatives rejected

- **Cosine similarity with TF-IDF.** Rejected: requires float vectors,
  violating the no-floats-in-decision-path invariant. Could use
  integer-weighted cosine, but Jaccard is simpler and sufficient for a
  first filter.
- **LLM as the first filter.** Rejected: expensive, non-deterministic,
  and puts the LLM in the decision path. The deterministic base
  produces candidates; the LLM confirms or rejects.
- **Lower threshold (1/2).** Rejected: too many false positives on
  skills that share domain vocabulary. 2/3 is conservative; the LLM
  layer can compensate.

## Consequences

Accepted now:
- SEMANTIC_REDUNDANCY is the 9th emitted check. The auditor now emits
  9 checks and abstains on 4.
- The real corpus produces 0 SEMANTIC_REDUNDANCY findings at the 2/3
  threshold — the skills are lexically distinct enough.
- 12 new falsifiable tests cover detection, no-false-positives,
  threshold behavior, no-floats, evidence, limitation, determinism,
  and stopword filtering.

Deferred:
- LLM confirmation layer: takes each CANDIDATE and asks the model
  whether the two skills are semantically redundant. The model
  confirms or rejects; it never produces the candidate.
- Lowering the threshold once the LLM layer is available.
