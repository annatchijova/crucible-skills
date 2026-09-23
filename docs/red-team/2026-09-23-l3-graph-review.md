# L3 Red-Team Review — Typed Composition Graph

**Date:** 2026-09-23  
**Scope:** edge extraction from descriptions, relation type classification, graph property detection, artifact sealing, invariant preservation from L1+L2  
**Level:** L3  
**Status:** reviewed; conditional contradiction and semantic redundancy remain explicitly abstained

## Threat model

The graph consumes the L1 Skill IR. An attacker may have written skills with
misleading relation language in descriptions: a "Sibling of" reference to a
non-existent skill, a description that mentions a skill name in a
non-relation context, or a family declaration that lists common phrases
instead of skill names.

The graph does not trust description text as confirmed semantics. It extracts
candidate edges with evidence text and marks unresolved targets. It does not
execute skills or call any model.

## L1+L2 invariant preservation

| Invariant | How L3 preserves it | Result |
|---|---|---|
| L1 artifact is versioned and sealed | Graph checks `schema_version == skill-ir/v1` and stamps `graph_version: crucible-graph/v1` | PASS |
| L1 artifact digest is content-addressed | Graph includes `input_ir_digest` in the graph artifact | PASS |
| L2 audit digest is content-addressed | Graph includes `input_audit_digest` when audit artifact is provided | PASS |
| Same input produces same output | Graph is deterministic; cross-process digest verified identical | PASS |
| Source identity is preserved | Graph uses skill names and source_paths from the IR; does not re-read files | PASS |
| Modal extraction not promoted to truth | Graph does not interpret rules; it only extracts relation edges | PASS |
| No float in the decision path | Source inspection: all operations are set/dict/sort based | PASS |
| No LLM in the decision path | Graph builder is pure Python; no model calls | PASS |
| Fail closed on incompatible input | Wrong schema_version, missing digest, missing skills all raise ValueError | PASS |
| Honest abstention for unsupported checks | 3 limitations documented in every artifact | PASS |

## L3 invariants reviewed

| Invariant | Evidence | Result |
|---|---|---|
| Graph is deterministic (same input, same digest) | same-process and cross-process digest comparison | PASS |
| Edges carry source evidence | every edge has source, target, edge_type, relation_type, resolved, extraction_method | PASS |
| Edge extraction is two-pass (known names + kebab-case) | pass 1 matches name_set; pass 2 extracts hyphenated tokens from structural positions | PASS |
| Relation types are classified deterministically | COMPOSES_WITH/PAIRS_WITH/COMPANION_TO → COMPOSITION; SIBLING_OF/FAMILY_OF → REINFORCEMENT; DELEGATES_TO → DELEGATION | PASS |
| Broken edges are detected and reported | unresolved targets produce BROKEN_EDGE properties | PASS |
| Hubs are detected by incoming edge count | threshold >= 3; verified on real corpus (12 hubs) | PASS |
| Disconnected components are detected | union-find on resolved edges; verified on real corpus (4 components) | PASS |
| Limitations are explicit | CONDITIONAL_CONTRADICTION, SEMANTIC_REDUNDANCY, PRODUCER_CONSUMER_TYPING | PASS |

## Induction evidence

### Real corpus run

Input: local skills corpus at `/home/labestiadevigia/.codex/skills`.  
Observed: 83 edges (64 SIBLING_OF, 9 FAMILY_OF, 4 PAIRS_WITH, 4 COMPOSES_WITH,
2 COMPANION_TO), all resolved, 0 broken. 12 hubs (top: red-team-auditing with
7 incoming, falsifiable-testing with 6, abductive-engineering with 5). 4
disconnected components (largest: 58 skills). 38 isolated skills.  
Graph digest (with audit): `sha256:7ecd0ec5942b61c87137da619dd758a645ac735b5d4d80d7922dec94811daef7`.  
Cross-process digest (without audit): `sha256:46731245b88f7d1b2fe1ace18a034ce4fe6334adbb0ef681611a49c705226ff7`.

The graph reveals the corpus structure: the "family" of abductive-engineering,
secure-by-construction, red-team-auditing, software-archaeology, and
daubert-defensible-writing forms a dense hub cluster. 38 skills have no
extracted edges — these are either genuinely standalone or use relation
language the extractor does not recognize.

### Test suite

19 graph tests + 19 auditor tests + 7 compiler tests = 45 total, all green.
Each graph test names the invariant it defends and includes a negative
control (a fixture that must NOT produce the edge/property).

## Discarded vectors

| Vector | Result | Why |
|---|---|---|
| Detect CONDITIONAL_CONTRADICTION from rule modalities | Rejected | the IR does not extract conditions, exceptions, or normalized subjects; conflict detection would require semantic adjudication not available deterministically |
| Detect SEMANTIC_REDUNDANCY via similarity | Rejected | no semantic similarity in the deterministic path; redundancy is exact-text (L2) plus graph co-occurrence, not semantic equivalence |
| Type edges as producer/consumer | Rejected | edge direction reflects declaration, not a typed property flow; "composes with" means the source declares a relation, not that the target produces a specific property |
| Extract "see also" as a relation | Rejected | spot-check showed 8 matches but all were false positives ("see below", "see the test", "see user B's data") — not skill references |
| Match single-word unresolved targets | Rejected | pass 2 requires kebab-case (with hyphens) for unresolved targets to avoid false positives from common English words; single-word targets are found by pass 1 if they exist in the corpus |

## Known blind spots

- The extractor recognizes five trigger phrases (sibling of, pairs with,
  composes with, member of the family, companion to). Other relation language
  ("extends", "specializes", "see also") is not extracted because spot-checks
  showed high false-positive rates or ambiguous semantics.
- Edge direction reflects declaration, not semantic flow. A SIBLING_OF edge
  from A to B does not mean A depends on B; it means A declares a sibling
  relationship. The graph is directed by declaration, not by dependency.
- 38 skills are isolated. Some may have relations in body text (not
  descriptions) that the extractor misses. This is a parser-boundary
  limitation, not a graph defect.
- The union-find component detection uses resolved edges only. A skill with
  only broken edges appears as isolated, which is correct (it has no
  confirmed connections).
- FAMILY_OF extraction requires parentheses after the trigger phrase. A
  family declaration without parentheses ("member of the family — X, Y, Z")
  would not be extracted.

## Gate decision

L3 is coherent and independently useful as a typed composition graph. It
consumes the L1 IR without modifying it, preserves L1+L2 invariants, seals
its own artifact, and honestly abstains from semantic checks the current IR
cannot support. The graph reveals real corpus structure (83 edges, 12 hubs, 4
components) that was invisible to L1+L2. L4 (mutation laboratory) may begin
by consuming the graph to mutate edges, rules, and relations, preserving the
determinism, evidence, and epistemic discipline established by L1-L3.
