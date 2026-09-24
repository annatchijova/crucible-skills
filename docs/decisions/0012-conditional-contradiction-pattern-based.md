# ADR-0012: Conditional Contradiction — Pattern-Based Condition Extraction

**Status:** Accepted  
**Date:** 2026-09-23  
**Reversibility:** high; the condition extraction is additive

## Context

CONDITIONAL_CONTRADICTION was abstained because the IR did not extract
conditions or exceptions from rule text. The user requested detection of
contradictory skills: two rules that seem compatible in general but
conflict under a specific condition.

## Decision

Extend the L1 IR with condition extraction and add the
CONDITIONAL_CONTRADICTION check.

### IR extension (additive)

Each rule now carries a `conditions` list — condition clauses extracted
from the rule text using pattern matching:

- **Exception patterns** (invert polarity): `except for X`, `unless X`
- **Scope patterns** (restrict polarity): `when X`, `if X`, `for X`,
  `during X`, `while X`

Each condition is `{text, type}` where type is `"exception"` or
`"scope"`. The text is normalized to lowercase with articles stripped.

### L2 check: CONDITIONAL_CONTRADICTION

Two rules with:
1. The same subject
2. Overlapping conditions (substring or token-subset match)
3. Opposite effective polarity under those conditions

**Effective polarity** is computed as:
- Base polarity: MUST/SHOULD = positive, MUST_NOT/SHOULD_NOT = negative
- Exception condition: inverts the polarity for that condition
- Scope condition: applies the base polarity for that condition
- No matching condition: the rule does not apply (returns None)

The check skips pairs already caught by NORMATIVE_CONFLICT
(unconditional opposite modality) to avoid duplicates.

### Example

```
Rule A: "Retries MUST be bounded, except for read-only operations"
  -> under "read-only operations": negative (not bounded, via exception)

Rule B: "Retries MUST be bounded for read-only operations"
  -> under "read-only operations": positive (bounded, via scope)

-> CONDITIONAL_CONTRADICTION on "read-only operations"
```

Both rules are MUST (same modality), same subject "retries". NORMATIVE_CONFLICT
does not catch this. But under the condition "read-only operations",
Rule A says "not bounded" (exception inverts) and Rule B says "bounded"
(scope preserves). That is a conditional contradiction.

## Alternatives rejected

- **Full NLP for condition parsing.** Rejected: would put an LLM in
  the decision path. Pattern-based extraction is deterministic and its
  limitations are documented.
- **Only check both-conditional pairs.** Rejected: an unconditional
  rule and a conditional exception on the same subject can also
  conflict. The check handles both cases.
- **Semantic condition matching.** Rejected: "read-only operations" and
  "read-only" should match, but "read-only" and "write-only" should
  not. Substring + token-subset matching is conservative and
  deterministic. Semantic matching is deferred to the LLM layer.

## Consequences

Accepted now:
- CONDITIONAL_CONTRADICTION is the 10th emitted check. The auditor
  emits 10 checks and abstains on 3.
- The IR has a new `conditions` field on rules. Existing consumers
  ignore it.
- The real corpus produces 0 CONDITIONAL_CONTRADICTION findings — the
  skills do not have conflicting conditional rules.
- 18 new falsifiable tests cover detection, no-false-positives,
  condition extraction (exception/scope types, unless/when patterns),
  evidence, limitation, determinism, and non-duplication with
  NORMATIVE_CONFLICT.

Deferred:
- Semantic condition matching (different surface forms for the same
  condition).
- SCOPE_TRIGGER_MISMATCH (needs trigger/scope extraction from
  frontmatter and description).
