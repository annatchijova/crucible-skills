# L2 Red-Team Review — Deterministic Auditor

**Date:** 2026-09-23  
**Scope:** audit engine, finding emission, artifact sealing, invariant preservation from L1  
**Level:** L2  
**Status:** reviewed; deeper semantic checks remain explicitly abstained

## Threat model

The auditor consumes the L1 Skill IR artifact. An attacker may have submitted
skills with broken composition references, self-referential edges, cycles,
duplicate methodology, or normative rules without verification paths. The
auditor must detect these without promoting lexical candidates to confirmed
truth.

The attacker does not control the auditor source code, the sealed audit
artifact, or the verifier configuration. The LLM is not in the audit path.

## L1 invariant preservation

| L1 invariant | How L2 preserves it | Result |
|---|---|---|
| Artifact schema is versioned | Auditor checks `schema_version == skill-ir/v1` and stamps `audit_version: crucible-audit/v1` | PASS |
| Same corpus produces same artifact | Audit is deterministic; cross-process digest verified identical | PASS |
| Source identity is content-addressed | Auditor does not modify the IR; references `input_artifact_digest` | PASS |
| Unsupported frontmatter fails visibly | Auditor does not re-parse; it consumes the compiled IR | PASS |
| Symlinked skill cannot escape | Auditor does not touch files; L1 already rejected symlinks | PASS |
| Duplicate names cannot create ambiguity | Auditor builds `name_set` from the IR; L1 already rejected duplicates | PASS |
| Modal extraction not promoted to truth | Rules retain `extraction_status: candidate`; REQUIREMENT_WITHOUT_CHECK is CANDIDATE | PASS |
| Workspace changes preserved | `visual/` remains untracked and untouched | PASS |

## L2 invariants reviewed

| Invariant | Evidence | Result |
|---|---|---|
| Audit is deterministic (same input, same digest) | same-process and cross-process digest comparison | PASS |
| No float in the decision path | source inspection: all arithmetic is integer set/dict operations | PASS |
| No LLM in the decision path | auditor is pure Python; no model calls | PASS |
| Artifact is sealed with SHA-256 | `audit_digest` computed over canonical bytes before any external use | PASS |
| Findings carry source evidence | every finding has `skill`, `source_path`, `evidence`, `class`, `epistemic_status` | PASS |
| Fail closed on incompatible input | wrong schema_version, missing digest, missing skills all raise ValueError | PASS |
| Honest abstention for unsupported checks | 5 limitations documented in every artifact | PASS |
| Summary is a faithful count | `summary.total` and `by_class` match the findings list | PASS |

## Induction evidence

### Real corpus run

Input: local skills corpus at `/home/labestiadevigia/.codex/skills`.  
Observed: 1 finding (REQUIREMENT_WITHOUT_CHECK, CANDIDATE) on the `compact`
skill; 5 documented limitations; 0 graph-based findings (the corpus has no
extracted composition/delegation edges).  
Audit digest: `sha256:21a5f4444ded87d2500096a4de5a10f44de8fea853e26f1a5edb8fc6c4119ebd`.  
Cross-process digest: identical.

The single finding is honest: the `compact` skill has 2 MUST/SHOULD rules but
0 extracted checks. The finding is CANDIDATE with an explicit limitation
stating the IR does not link checks to specific rules.

### Test suite

19 auditor tests + 7 compiler tests = 26 total, all green. Each auditor test
names the invariant it defends and includes a negative control (a fixture
that must NOT trigger the check).

## Discarded vectors

| Vector | Result | Why |
|---|---|---|
| Emit DESCRIPTION_BODY_GAP for skills with 0 extracted rules | Rejected | 68/103 real skills have 0 extracted rules because the L1 extractor is lexical and conservative; flagging them would be a false-positive storm conflating extractor scope with methodology absence |
| Emit ORPHAN_SKILL when the relation graph is empty | Rejected | an empty graph makes every skill trivially disconnected; the observation is only meaningful when a graph exists |
| Link checks to specific rules | Rejected for L2 | the IR does not carry `target_rule_ids` on checks; per-rule coverage would be a guess, not evidence |
| Detect NORMATIVE_CONFLICT | Rejected for L2 | the IR does not extract conditions or exceptions; conflict detection would require semantic adjudication not available deterministically |
| Use float for redundancy scoring | Rejected | no float in the decision path; redundancy is exact-text match, not a similarity score |

## Known blind spots

- The auditor can only check what the L1 IR exposes. Checks requiring
  conditions, exceptions, oracle kinds, triggers, scopes, or structured claims
  are abstained and documented.
- Relation source spans are not preserved in the current IR; BROKEN_REFERENCE
  and COMPOSITION_CYCLE findings locate the skill, not the exact relation
  line. This is noted in each finding's `limitation` field.
- Cycle detection uses recursive Tarjan's SCC; a pathologically deep graph
  could hit Python's recursion limit. Real skill corpora are small (103
  skills); this is a bounded risk, not a current defect.
- The relation target matching is exact-text: a relation bullet like
  `"the gate skill"` will not match a skill named `"gate"`. This is a
  parser-boundary limitation inherited from L1, not an auditor defect.

## Gate decision

L2 is coherent and independently useful as a deterministic auditor. It
consumes the L1 IR without modifying it, preserves all L1 invariants, seals
its own artifact, and honestly abstains from checks the current IR cannot
support. L3 (typed composition graph) may begin by consuming both the L1 IR
and the L2 audit artifact, preserving their determinism, source evidence, and
epistemic discipline.
