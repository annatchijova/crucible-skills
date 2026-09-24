# ADR-0017: Semantic Redundancy Confirmation Layer (L2.5)

**Status:** Accepted  
**Date:** 2026-09-23  
**Reversibility:** high; the confirmation layer is a separate artifact

## Context

The SEMANTIC_REDUNDANCY check (L2) uses a deterministic lexical base
(Jaccard token overlap >= 2/3 with `fractions.Fraction`, no floats). It
produces CANDIDATE findings — two skills may share vocabulary while
governing different scopes. The check's limitation states: "an LLM
confirmation layer is deferred and would confirm or reject each
candidate."

The user requested exploration of the LLM-dependent parts. This ADR
documents the confirmation layer.

## Decision

Add a confirmation layer (`confirm.py`) that takes SEMANTIC_REDUNDANCY
CANDIDATEs from the L2 audit and asks an executor whether each pair is
semantically redundant.

### Architecture

```
L2 audit (sealed, deterministic, never modified)
    |
    v
confirmation layer extracts SEMANTIC_REDUNDANCY candidates
    |
    v
executor (Nemotron via Nebius, or deterministic mock)
    |
    v
confirmation artifact (separate, OBSERVATION status, own digest)
```

### Artifact schema: `crucible-confirmation/v1`

```json
{
    "schema_version": "crucible-confirmation/v1",
    "source_audit_digest": "sha256:...",
    "source_ir_digest": "sha256:...",
    "executor": {
        "model": "...",
        "provider": "...",
        "temperature": 0
    },
    "status": "COMPLETED" | "BLOCKED",
    "confirmations": [
        {
            "finding_id": "finding-0001",
            "skill_a": "skill-a",
            "skill_b": "skill-b",
            "jaccard_overlap": "1/1",
            "verdict": "CONFIRMED" | "REJECTED" | "UNCLEAR" | "BLOCKED",
            "rationale": "...",
            "executor_model": "...",
            "executor_provider": "...",
            "executor_response_id": "..."
        }
    ],
    "summary": {
        "total": 1,
        "confirmed": 1,
        "rejected": 0,
        "unclear": 0,
        "blocked": 0
    },
    "confirmation_digest": "sha256:..."
}
```

### Invariants preserved

1. **LLM out of the decision path (§5.1).** The L2 audit artifact is
   NEVER modified by the confirmation layer. The confirmation is a
   separate artifact with its own digest. The L2 finding stays
   CANDIDATE — the confirmation does not promote it to CONFIRMED.

2. **Deterministic core (§5.2).** The confirmation artifact has its own
   SHA-256 digest over canonical bytes. The mock executor is
   deterministic. No floats in the confirmation artifact.

3. **Honest degradation (§5.3).** If the Nebius API key is not
   available, the confirmation is BLOCKED, not simulated as verified.
   The status is "BLOCKED" and the verdict is "BLOCKED" for each
   candidate.

4. **Three states, not two.** The executor can return CONFIRMED,
   REJECTED, or UNCLEAR. UNCLEAR is a valid verdict — the executor
   cannot determine semantic redundancy from the provided text.

### Executors

- **NebiusConfirmExecutor:** calls the Nebius Token Factory API with
  `nvidia/nemotron-3-super-120b-a12b`. Requires `NEBIUS_API_KEY`. If
  not present, returns BLOCKED.
- **MockConfirmExecutor:** deterministic heuristic (line overlap >=
  80% → CONFIRMED, else REJECTED). For testing without external
  dependencies. Not an LLM.

### Prompt design

The system prompt tells the executor:
- It is a methodology redundancy analyst.
- It must respond with CONFIRMED, REJECTED, or UNCLEAR.
- It must provide a one-sentence rationale.
- It must not modify any values (the audit findings are fixed).

The user prompt provides:
- SKILL_A: the full text of skill A (description, rules, checks, steps)
- SKILL_B: the full text of skill B
- The Jaccard overlap found by the deterministic layer
- The question: are they semantically redundant?

### Real corpus results

The real corpus produces 0 SEMANTIC_REDUNDANCY CANDIDATEs (the
deterministic threshold of 2/3 is exigent). Therefore the confirmation
layer has 0 confirmations. This is correct: the deterministic layer
found no candidates to confirm.

## Alternatives rejected

- **LLM in the decision path.** Rejected: the L2 audit must remain
  sealed and deterministic. The confirmation is an OBSERVATION in a
  separate artifact.
- **Promote to CONFIRMED.** Rejected: the confirmation verdict is
  OBSERVATION, not a promotion to CONFIRMED in the L2 audit. The L2
  finding stays CANDIDATE.
- **Simulate when BLOCKED.** Rejected: if the API key is not
  available, the confirmation is BLOCKED, not simulated as verified.
- **Only Nebius executor.** Rejected: a mock executor is needed for
  testing the harness without external dependencies.

## Consequences

Accepted now:
- The confirmation layer is a separate artifact (`crucible-confirmation/v1`).
- The L2 audit is never modified.
- The mock executor allows testing without NEBIUS_API_KEY.
- The Nebius executor is BLOCKED without NEBIUS_API_KEY.
- 14 new falsifiable tests cover schema, LLM-out-of-decision-path,
  mock executor, Nebius BLOCKED, no candidates, summary, determinism,
  and no floats.
- 265 tests total, all green. Cross-process determinism confirmed.

Deferred:
- Running the confirmation layer with a real Nebius API key.
- Confirming other CANDIDATE finding types (not just SEMANTIC_REDUNDANCY).
