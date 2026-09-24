# ADR-0018: General Confirmation Layer for All CANDIDATE Findings

**Status:** Accepted  
**Date:** 2026-09-24  
**Reversibility:** high; the confirmation layer is a separate artifact

## Context

ADR-0017 introduced the confirmation layer for SEMANTIC_REDUNDANCY only.
The user requested extending it to all CANDIDATE finding types so the LLM
can confirm or reject each candidate.

## Decision

Extend the confirmation layer with `confirm_candidates`, a general
function that handles all CANDIDATE finding types with registered prompt
builders.

### Supported finding classes

| Class | Question the LLM answers |
|---|---|
| SEMANTIC_REDUNDANCY | Are these two skills semantically redundant? |
| CHECK_WITHOUT_ORACLE | Is this check actually unverifiable? |
| DESCRIPTION_BODY_GAP | Does the body fail to deliver what the description promises? |
| REQUIREMENT_WITHOUT_CHECK | Are these rules actually without checks? |
| SCOPE_TRIGGER_MISMATCH | Does the trigger actually mismatch the rules' scope? |

### Per-class prompt builders

Each finding class has a dedicated prompt builder that constructs a
(system_prompt, user_prompt) pair. The system prompt sets the executor's
role as a "methodology audit confirmation analyst". The user prompt
provides:
- The full skill text (description, rules, checks, steps)
- The finding evidence
- A class-specific question

The executor responds with CONFIRMED, REJECTED, or UNCLEAR and a
one-sentence rationale.

### Mock executor extension

The `MockConfirmExecutor` now handles two prompt formats:
- **Pair-wise** (SKILL_A/SKILL_B): for SEMANTIC_REDUNDANCY. Returns
  CONFIRMED if line overlap >= 80%.
- **Single-skill** (SKILL/FINDING): for all other classes. Returns
  CONFIRMED if the skill has fewer than 5 non-empty lines (genuinely
  thin body), REJECTED otherwise.

### Class filtering

`confirm_candidates` accepts an optional `classes` parameter to
confirm only specific finding types. This allows targeted confirmation
(e.g., only CHECK_WITHOUT_ORACLE) without confirming all CANDIDATEs.

### Backward compatibility

`confirm_semantic_redundancy` is preserved as a backward-compatible
wrapper. The CLI and composite report now use `confirm_candidates`.

### Real corpus results

The real corpus produces 46 CANDIDATEs:
- CHECK_WITHOUT_ORACLE: 16 (5 CONFIRMED, 11 REJECTED by mock)
- DESCRIPTION_BODY_GAP: 27 (27 CONFIRMED by mock)
- REQUIREMENT_WITHOUT_CHECK: 1 (0 CONFIRMED, 1 REJECTED by mock)
- SCOPE_TRIGGER_MISMATCH: 2 (0 CONFIRMED, 2 REJECTED by mock)

Cross-process determinism confirmed.

## Alternatives rejected

- **One prompt for all classes.** Rejected: each finding class asks a
  different question. A generic prompt would not provide the executor
  with the class-specific context it needs.
- **Remove `confirm_semantic_redundancy`.** Rejected: backward
  compatibility. Existing consumers may call it directly.
- **CONFIRMED status in L2.** Rejected: the confirmation is an
  OBSERVATION in a separate artifact. The L2 finding stays CANDIDATE.

## Consequences

Accepted now:
- All 5 CANDIDATE finding types can be confirmed or rejected by an
  executor (Nemotron or mock).
- The CLI `--confirm` flag now confirms all CANDIDATEs, not just
  SEMANTIC_REDUNDANCY.
- The composite report (L8) includes all confirmations.
- 13 new falsifiable tests cover all finding types, class filtering,
  LLM-out-of-decision-path, Nebius BLOCKED, determinism, no floats,
  summary correctness, and schema.
- 278 tests total, all green.

Deferred:
- Running the confirmation layer with a real Nebius API key.
- Confirming STRUCTURAL_REDUNDANCY and METHODOLOGICAL_VACUITY (currently
  CANDIDATE but without dedicated prompt builders — they could be added
  if needed).
