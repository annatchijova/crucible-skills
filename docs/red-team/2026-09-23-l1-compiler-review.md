# L1 Red-Team Review — Corpus Compiler

**Date:** 2026-09-23  
**Scope:** corpus discovery, frontmatter parsing, source identity, candidate extraction, canonical artifact digest  
**Level:** L1  
**Status:** reviewed; deeper semantic analysis remains out of scope

## Threat model

The corpus may contain malformed or adversarial `SKILL.md` files. A file may be a symlink, two files may claim the same skill identity, frontmatter may use unsupported YAML syntax, and Markdown may contain modal words in examples rather than actual normative rules.

The compiler does not trust corpus text as confirmed methodology. It emits candidate lexical rules with source spans. It does not execute skill instructions.

## Invariants reviewed

| Invariant | Evidence | Result |
|---|---|---|
| Artifact schema is versioned | `schema_version: skill-ir/v1` test | PASS |
| Same corpus produces same artifact | repeated compilation plus two independent real-corpus processes | PASS |
| Source identity is content-addressed | exact UTF-8 source-byte SHA-256 | PASS |
| Unsupported/malformed frontmatter fails visibly | missing, nested, and block-scalar fixtures | PASS |
| Symlinked skill cannot silently escape corpus identity | symlink fixture | PASS |
| Duplicate skill names cannot create ambiguous identity | duplicate-name fixture | PASS |
| Lexical modal extraction is not silently promoted to truth | `extraction_status: candidate` | PASS |
| Existing unrelated workspace changes are preserved | `visual/` remains untracked and untouched | PASS |

## Induction evidence

### Expected failure: schema mutation

**Prediction:** changing `skill-ir/v1` to a different schema string must fail the contract test.  
**Observed:** the test failed with an exact schema mismatch.  
**Restoration:** schema constant restored; full suite returned green.

### Real corpus run

Input: local skills corpus at `/home/labestiadevigia/.codex/skills`.  
Observed: 103 skills, 140 lexical rule candidates, 175 checks.  
Artifact digest: `sha256:eadb4606fc8fe608d725bc9dc807449be58db787aa3bfd5ef17912e20973ca9d`.

The digest is evidence of repeatability for this input and implementation, not evidence that the extracted rules are correct.

## Discarded vectors

| Vector | Result | Why |
|---|---|---|
| Treat every modal word as a confirmed invariant | FALSIFIED as a design assumption | extraction is explicitly marked `candidate`; semantic adjudication belongs to later levels |
| Continue after malformed frontmatter | Rejected | would produce a partial artifact that looks complete |
| Follow symlinked skill files | Rejected | source identity could escape the declared corpus boundary |
| Allow duplicate names | Rejected | graph and later findings would have ambiguous identity |
| Claim full YAML compatibility | FALSIFIED | L1 supports a documented subset and fails visibly outside it |

## Known blind spots

- The parser does not establish semantic meaning, condition overlap, or exception relationships.
- Markdown structure outside the recognized headings is retained only through raw source digest, not fully represented in the IR.
- Full YAML constructs such as sequences, aliases, anchors, and deeper mappings are unsupported.
- No behavioral execution or model/runtime integration occurs at L1.
- A content digest proves identity of source bytes, not truth of the methodology.

## Gate decision

L1 is coherent and independently useful as a deterministic corpus compiler. L2 may begin only by consuming this IR and preserving its candidate status, source spans, identity checks, and artifact determinism.
