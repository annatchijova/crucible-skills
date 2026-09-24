# ADR-0013: Scope-Trigger Mismatch — Lexical Disjointness Base

**Status:** Accepted  
**Date:** 2026-09-23  
**Reversibility:** high; the trigger extraction is additive

## Context

SCOPE_TRIGGER_MISMATCH was abstained because the IR did not extract
triggers or scope from the skill description. The user requested
detection of skills whose declared scope doesn't match their actual
content — a methodologically incoherent skill.

## Decision

Extend the L1 IR with trigger extraction and add the
SCOPE_TRIGGER_MISMATCH check.

### IR extension (additive)

Each skill now carries a `trigger` field — a clause extracted from the
description using pattern matching:

- `Use this skill whenever X`
- `Use this skill when X`
- `Use this skill if X`
- `Use this skill for X`
- `Trigger on X` / `Trigger when X` / `Trigger for X`

The trigger is `{text, found}` where `found` is True if a pattern
matched. The text is truncated at 300 characters to avoid capturing
the entire description.

### L2 check: SCOPE_TRIGGER_MISMATCH

The check compares the trigger's token set to the combined rule texts'
token set. If both are non-empty and their intersection is empty, the
declared scope and the normative content are lexically disjoint — a
CANDIDATE finding.

The check uses the same tokenizer and stopword list as
SEMANTIC_REDUNDANCY for consistency.

### Why zero overlap (not low overlap)

Zero overlap is a much stronger signal than low overlap. It means the
trigger and the rules share NO meaningful vocabulary at all. A lower
threshold (e.g., "below 1/3 Jaccard") would produce many false positives
on skills where the trigger uses high-level domain terms and the rules
use specific implementation terms — which is the normal case.

### Real corpus results

The real corpus produces 2 SCOPE_TRIGGER_MISMATCH findings:

1. **destination-driven-construction**: trigger about "planning or
   building a project" vs rules about "phases, levels, MVP, regression,
   TDD". Same domain (project construction) but different vocabulary.
   False positive.

2. **resilient-ui-states**: trigger about "building or reviewing a
   component that does async data fetching" vs rules about "render,
   error, loading, validation, aria". Same domain (UI state management)
   but different vocabulary. False positive.

Both are CANDIDATE (not CONFIRMED) with the limitation explicitly
stating "lexical token disjointness is not semantic disjointness." The
2% false positive rate (2/97) is the expected cost of a lexical check.
An LLM confirmation layer (deferred) would confirm or reject each
candidate.

## Alternatives rejected

- **Low Jaccard threshold.** Rejected: trigger descriptions use
  high-level domain terms while rules use implementation terms. Low
  overlap is the normal case, not a defect signal.
- **Semantic similarity (LLM).** Rejected: would put the LLM in the
  decision path. The deterministic base produces candidates; the LLM
  confirms or rejects (deferred).
- **Compare trigger to rule subjects only.** Rejected: most rules have
  empty subjects (modal at start of line). Comparing to full rule text
  is more reliable.

## Consequences

Accepted now:
- SCOPE_TRIGGER_MISMATCH is the 11th emitted check. The auditor emits
  11 checks and abstains on 3.
- The IR has a new `trigger` field. Existing consumers ignore it.
- The real corpus produces 2 CANDIDATE findings (both false positives,
  documented as CANDIDATE with limitation).
- 14 new falsifiable tests cover detection, no-false-positives, trigger
  extraction (when/whenever/for patterns), evidence, limitation,
  determinism, and non-abstention.

Deferred:
- LLM confirmation layer for SCOPE_TRIGGER_MISMATCH candidates.
- Semantic trigger-rule matching (different vocabulary, same domain).
