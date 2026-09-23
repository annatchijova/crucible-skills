# ADR-0004: Description-Based Edge Extraction for L3

**Status:** Accepted for L3  
**Date:** 2026-09-23  
**Reversibility:** low; changing the trigger phrases or extraction logic changes every edge and every downstream mutation oracle

## Context

L1 extracts `composes_with` and `delegates_to` from section headings (`## Composes with`, `## Delegates to`). The real corpus has 0 such section headings — all relation language lives in the description field, using phrases like "Sibling of X", "Pairs with Y", "member of the family (A, B, C)", and "Companion to Z". L1 captures none of this.

L3 needs typed edges to analyze the corpus as a composed system and to support L4 mutations (remove composition edge, introduce cycle, break producer→consumer). Without description-based extraction, the graph would be empty and L3 would be useless on the real corpus.

## Decision

L3 extracts typed relation edges from the description field using five trigger phrases:

| Trigger phrase | Edge type | Relation type |
|---|---|---|
| `sibling of` | SIBLING_OF | REINFORCEMENT |
| `pairs with` | PAIRS_WITH | COMPOSITION |
| `composes with` | COMPOSES_WITH | COMPOSITION |
| `member of the family` | FAMILY_OF | REINFORCEMENT |
| `companion to` | COMPANION_TO | COMPOSITION |

Extraction is two-pass:

1. **Known names:** match skill names from the name_set anywhere in the segment after the trigger phrase (handles single-word names like "alpha" and multi-word names like "red-team-auditing").
2. **Kebab-case tokens:** extract hyphenated tokens from structural positions (after removing parenthetical context, from the start of each comma/and-separated part) for potential unresolved targets (handles names like "ghost-skill" that don't exist in the corpus).

Pass 2 requires at least one hyphen and a minimum length of 5 characters to avoid false positives from common English words. This means single-word unresolved targets are not extracted — they must be in the corpus to be found.

L1 section-heading relations are also included and merged with description-extracted edges (deduplicated by source, target, and edge type).

## Alternatives rejected

- **Enhance L1 to extract from descriptions.** Rejected because it would reopen L1 and delay the coherent level; L1's parser boundary is documented in ADR-0002. Best argument for it: single extraction point.
- **Use semantic similarity to infer edges.** Rejected because it requires a model or embedding, violating the deterministic core. Best argument for it: catches relations not expressed in trigger phrases.
- **Extract all kebab-case tokens as potential targets.** Rejected because it produces false positives from common phrases ("chain-of-custody", "one-way-door"). Best argument for it: catches more unresolved targets.
- **Match single-word unresolved targets.** Rejected because common English words ("the", "and", "this") would produce false positives. Best argument for it: catches single-word skill names not in the corpus.

## Assumption this rests on

The five trigger phrases cover the dominant relation language in the target corpus. If a significant corpus uses other phrases ("extends", "specializes", "see also"), the extractor will miss those edges. This is acceptable for L3 because the missed edges are an honest absence, not a false pass — the graph reports 38 isolated skills, and the limitations list documents what is not detected.

## Consequences

Accepted now:

- L3 extracts 83 edges from the real corpus (vs. 0 from L1 section headings alone).
- The graph reveals real corpus structure: 12 hubs, 4 disconnected components.
- Edge extraction is deterministic and cross-process reproducible.
- Unresolved targets are detected and reported as BROKEN_EDGE properties.

Deferred:

- "extends", "specializes", and other trigger phrases (spot-checks showed high false-positive rates).
- Conditional contradiction detection (needs conditions/subjects not in the IR).
- Semantic redundancy (needs normalized subjects/predicates).
- Producer/consumer typing (edge direction reflects declaration, not property flow).

## Revisit trigger

Revisit when a selected external corpus uses relation language outside the five trigger phrases, or when L4 mutation testing reveals that a critical mutation class cannot be expressed because the graph misses a relation type.
