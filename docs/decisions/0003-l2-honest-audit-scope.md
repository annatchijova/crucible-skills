# ADR-0003: Honest Audit Scope for L2

**Status:** Accepted for L2  
**Date:** 2026-09-23  
**Reversibility:** low; changing which checks are emitted vs abstained changes every downstream finding set and mutation oracle

## Context

L2 must audit the L1 Skill IR and produce findings. The finding taxonomy in
TECHNICAL.md §5 lists eleven classes, but the L1 IR does not extract all the
fields every class needs. Specifically, the IR lacks:

- `oracle_kind` on checks (needed for CHECK_WITHOUT_ORACLE);
- structured `claims` with numeric flags (needed for CLAIM_WITHOUT_PROVENANCE);
- `declared_triggers` and scope inclusions/exclusions (needed for
  SCOPE_TRIGGER_MISMATCH);
- `conditions` and `exceptions` on rules (needed for NORMATIVE_CONFLICT);
- a semantic description-to-body correspondence (needed for
  DESCRIPTION_BODY_GAP).

Emitting these checks with the available data would produce false positives or
semantically empty verdicts. The real corpus has 68/103 skills with zero
extracted rules because the L1 extractor is lexical and conservative; flagging
them as DESCRIPTION_BODY_GAP would conflate extractor scope with methodology
absence.

## Decision

L2 emits only the checks it can ground in IR evidence:

- **Emitted (6):** BROKEN_REFERENCE, SELF_COMPOSITION, COMPOSITION_CYCLE,
  ORPHAN_SKILL, REQUIREMENT_WITHOUT_CHECK, STRUCTURAL_REDUNDANCY.
- **Abstained (5):** DESCRIPTION_BODY_GAP, CHECK_WITHOUT_ORACLE,
  CLAIM_WITHOUT_PROVENANCE, SCOPE_TRIGGER_MISMATCH, NORMATIVE_CONFLICT.

Every abstained check is documented in the artifact's `limitations` list with
the specific reason it cannot run. Findings carry an epistemic status:
`CONFIRMED` for structural checks, `CANDIDATE` for coarse heuristics, and
`OBSERVATION` for non-defect corpus observations.

## Alternatives rejected

- **Emit all checks with best-effort heuristics.** Rejected because
  false-positive storms (e.g., 68 DESCRIPTION_BODY_GAP findings) destroy the
  auditor's credibility and violate honest degradation. Best argument for it:
  broader apparent coverage.
- **Emit only fully confirmed checks.** Rejected because REQUIREMENT_WITHOUT_CHECK
  and STRUCTURAL_REDUNDANCY are useful candidate signals even when coarse;
  suppressing them loses real information. Best argument for it: zero false
  positives.
- **Enhance L1 to extract all fields before building L2.** Rejected because it
  would reopen L1 and delay the coherent level; the IR can evolve in later
  levels. Best argument for it: fuller audit from the start.

## Assumption this rests on

The six emitted checks are sufficient to demonstrate the audit framework is
deterministic, evidence-bearing, and honestly scoped. Downstream levels (L3
composition, L4 mutation) can extend the IR and re-enable abstained checks
without rebuilding L2.

## Consequences

Accepted now:

- L2 is honest: it says what it checked and what it did not.
- The audit artifact is reproducible and sealed.
- CANDIDATE findings carry explicit limitations so consumers know the
  precision boundary.

Deferred:

- the five abstained checks, until the IR extracts the fields they require;
- per-rule check linking (needs `target_rule_ids` on checks);
- relation source spans (needs L1 enhancement).

## Revisit trigger

Revisit when L3 or a later level enriches the IR with conditions, exceptions,
oracle kinds, triggers, scopes, or structured claims. At that point, move the
corresponding check from abstained to emitted and bump the audit version.
