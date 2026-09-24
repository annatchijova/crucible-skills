# Red-Team Review — L7 Closed Repair Loop

**Date:** 2026-09-23  
**Scope:** adversarial review of L7 (closed repair loop) against L1-L6 invariants  
**Method:** hypothesis-driven, evidence-verified against live code  
**Status:** 0 confirmed defects, 2 rejected findings

## Method

L7 integrates L4 (mutation), L5 (behavioral differential), and L6 (Bob
workflow) into a single closed loop. The review verifies that this
integration preserves all prior invariants and that the new behavioral
replay gate is sound.

## Invariant verification

### L1: Determinism and sealing

**Verified:** L7 seals the report with `loop_digest` (SHA-256 over
canonical bytes). Cross-process determinism confirmed: two runs in
separate processes produce identical digests.

### L2: Deterministic audit behavior

**Verified:** L7 uses `audit_corpus` from L2 for both the base audit
and the repaired audit. The audit findings are the same as L2 would
produce independently.

### L3: Typed graph behavior

**Verified:** L7 does not modify L3. The composition graph is not
directly used by L7, but the audit findings that L7 consumes may
include graph-derived findings (e.g., COMPOSITION_CYCLE).

### L4: Mutation classifications

**Verified:** L7 does not modify L4. The mutation lab is a separate
workflow. L7 uses the behavioral replay concept from L5, not the
mutation lab directly.

### L5: Behavioral differential and model boundary

**Verified:** L7 uses the same property oracle and executor protocol
as L5. The executor is pluggable (LocalExecutor for testing,
NebiusExecutor for Nemotron). The property oracle is deterministic and
does not use the LLM. The model is the subject of observation, not the
judge.

### L6: Bob workflow and deterministic acceptance

**Verified:** L7 reuses the L6 acceptance criteria (finding gone + no
new findings + compiles) with the D1 fix (set-difference novelty check,
not count comparison). The proposer is pluggable. The LLM proposer is
BLOCKED without an API key.

### No floats in decision paths

**Verified:** zero floats found in the report. All values are strings,
integers, booleans, or nested structures thereof.

### No LLM in deterministic decision paths

**Verified:** the outcome is determined by `_evaluate_deterministic`
(L6 logic) and `_run_behavioral_replay` (L5 property oracle). Neither
calls the LLM. The LLM proposer generates text; the deterministic engine
decides.

### Honest blocked states

**Verified:** without `NEBIUS_API_KEY`, the report documents
`nebius_blocked: True` with the exact reason and uses `LocalExecutor`.
The LLM proposer returns `BLOCKED` with `proposed_text: None`.

### Source/evidence traceability

**Verified:** the finding carries `class`, `skill`, `evidence`, and
`source_path`. The behavioral replay records observations for both
original and repaired. The chain of custody includes `base_audit_digest`
and `repaired_audit_digest`.

## Rejected findings

### R1: Behavioral replay compares against original, not mutant

**Hypothesis:** the behavioral replay should compare the repaired skill
against the mutant (the defective version), not against the original
(the known-good version). Comparing against the original means the
repair only needs to not regress, not to actively fix behavior.

**Verification:** this is a design choice, not a defect. The L7 loop
starts with a finding from the audit, not with a mutation. The mutation
step in the user's vision is "reproduce the defect class" — but the
loop's purpose is to verify that a repair is safe, not to verify that
it fixes a specific mutation. Comparing against the original ensures
the repair does not introduce a behavioral regression, which is the
correct invariant for a repair loop. Comparing against the mutant
would be a different workflow (mutation testing, which is L4).

**Conclusion:** false positive. The design is correct for a repair
loop. A mutation-testing loop would compare against the mutant, but
that is L4's job, not L7's.

### R2: Behavioral replay uses the full skill text as system prompt

**Hypothesis:** `_build_system_prompt` strips the frontmatter and uses
the body as the system prompt. This means the executor sees the
markdown body, not just the normative rules. A skill with verbose
prose might dilute the rules' influence on the model.

**Verification:** this is the same approach as L5, where the variant
`skill_text` is a prose summary of the skill. The LocalExecutor uses
pattern matching on the system prompt, so the full body works fine.
The NebiusExecutor sends the system prompt to Nemotron, which will
read the full body. This is intentional: the skill's full body is the
guidance the model receives.

**Conclusion:** false positive. The design is consistent with L5.

## Summary

| ID | Invariant | Status |
|---|---|---|
| L1 | Determinism and sealing | verified |
| L2 | Deterministic audit behavior | verified |
| L3 | Typed graph behavior | verified (not modified) |
| L4 | Mutation classifications | verified (not modified) |
| L5 | Behavioral differential and model boundary | verified |
| L6 | Bob workflow and deterministic acceptance | verified |
| — | No floats in decision paths | verified (0 floats) |
| — | No LLM in deterministic decision paths | verified |
| — | Honest blocked states | verified |
| — | Source/evidence traceability | verified |

0 confirmed defects. 2 rejected findings. L7 is closed.
