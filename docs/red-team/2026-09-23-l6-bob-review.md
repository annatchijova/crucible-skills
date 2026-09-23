# L6 Red-Team Review — Bob Engineering Workflow

**Date:** 2026-09-23  
**Scope:** finding selection, repair proposal, deterministic re-audit, acceptance/rejection, LLM proposer BLOCKED behavior, invariant preservation from L1-L5  
**Level:** L6  
**Status:** reviewed; rule-based proposer verified; LLM proposer BLOCKED (no API key)

## Threat model

Bob receives audit findings and proposes a repair. The threats are:

1. **Bob as authority:** the LLM proposer's repair is accepted without
   deterministic verification. Mitigation: the acceptance criteria are
   deterministic (re-audit must show the finding is gone and no new findings).
2. **Bob suppresses the finding:** the repair removes the finding text without
   actually fixing the methodology. Mitigation: the re-audit checks for the
   finding class on the same skill; if the finding persists, the repair is
   rejected.
3. **Bob introduces new defects:** the repair adds a broken reference or a
   new structural issue. Mitigation: the re-audit checks that the total
   finding count does not increase.
4. **Simulated LLM proposal:** the LLM proposer generates a fake repair when
   the API key is absent. Mitigation: without NEBIUS_API_KEY, the proposal is
   BLOCKED with the exact reason; no simulation.

## L1-L5 invariant preservation

| Invariant | How L6 preserves it | Result |
|---|---|---|
| L1-L5 artifacts are versioned and sealed | L6 uses compile_corpus and audit_corpus; does not modify them | PASS |
| Deterministic core | L6's acceptance criteria are deterministic (finding gone + no new findings) | PASS |
| No float in the decision path | L6 uses integer counts and string comparisons | PASS |
| No LLM in the decision path | the proposer generates text; the re-audit decides; the LLM never touches the verdict | PASS |
| Honest degradation | LLM proposer BLOCKED is documented, not simulated | PASS |
| Sealed artifact | base and repaired audit digests recorded for chain of custody | PASS |
| Fail closed on missing credentials | MissingCredentialError -> BLOCKED outcome | PASS |

## L6 invariants reviewed

| Invariant | Evidence | Result |
|---|---|---|
| Report is versioned | `bob_version: crucible-bob/v1` | PASS |
| Report is deterministic | same-process and cross-process outcome identical | PASS |
| Bob fixture has 1 finding | REQUIREMENT_WITHOUT_CHECK on retrier | PASS |
| Rule-based proposer fixes the finding | ACCEPTED, 0 repaired findings | PASS |
| Bad repair is rejected | no-op repair -> REJECTED, FINDING_PERSISTS | PASS |
| Compile-breaking repair is rejected | malformed repair -> REJECTED, COMPILE_ERROR | PASS |
| LLM proposer BLOCKED without key | BLOCKED, no simulated proposal | PASS |
| No-findings corpus produces NO_FINDINGS | clean corpus -> NO_FINDINGS report | PASS |
| Decision path is deterministic | same repair text from different proposers -> same verdict | PASS |
| Proposer does not affect verdict | verdict depends on re-audit, not proposer identity | PASS |
| Finding index out of range produces ERROR | index 99 -> ERROR report | PASS |

## Induction evidence

### Rule-based proposer run

| Field | Value |
|---|---|
| Finding | REQUIREMENT_WITHOUT_CHECK on retrier |
| Proposal | added a Checks section with a verification check |
| Outcome | ACCEPTED |
| Original findings | 1 |
| Repaired findings | 0 |
| Original finding gone | True |
| No new findings | True |

The rule-based proposer adds a `## Checks` section to the `retrier` skill.
The deterministic re-audit confirms the finding is gone and no new findings
were introduced. The repair is accepted.

### LLM proposer run (BLOCKED)

| Field | Value |
|---|---|
| Outcome | BLOCKED |
| Blocked | True |
| Proposed text | None |
| Rationale | NEBIUS_API_KEY not set; cannot generate LLM proposal |

The LLM proposer is BLOCKED because the API key is not available. No
proposal is simulated. The finding count is unchanged.

### Test suite

14 Bob tests + 26 behavioral tests + 20 mutation tests + 19 graph tests +
19 auditor tests + 7 compiler tests = 105 total, all green.

## Discarded vectors

| Vector | Result | Why |
|---|---|---|
| Let the proposer decide acceptance | Rejected | the proposer is evidence, not the verdict; the deterministic re-audit decides |
| Accept repairs that only suppress the finding text | Rejected | the re-audit checks for the finding class on the same skill; suppressing text without fixing the methodology would leave the finding or introduce new ones |
| Run behavioral replay in L6 | Deferred for L7 | L6 is the proposal workflow; L7 is the closed repair loop that includes behavioral replay |
| Use the LLM proposer without a key | Rejected | honest BLOCKED is the only acceptable behavior; simulation would be fraud |
| Auto-select the finding to repair | Deferred | L6 takes a finding_index; auto-selection (by severity, by class) is a future enhancement |

## Known blind spots

- The rule-based proposer handles 3 finding classes
  (REQUIREMENT_WITHOUT_CHECK, BROKEN_REFERENCE, STRUCTURAL_REDUNDANCY).
  Other finding classes produce NO_PROPOSAL. This is honest: the proposer
  does not guess.
- The acceptance criteria check that the finding is gone and no new findings
  were introduced. They do not check that the repair is semantically correct
  — a repair that removes the finding by deleting the rule text would be
  accepted if it doesn't introduce new findings. This is a known limitation;
  L7 (closed repair loop) will add behavioral replay to catch semantic
  regressions.
- The LLM proposer has not been tested with a real API key. The code is real
  (uses urllib, OpenAI-compatible API, Bearer auth), but the integration is
  unverified until credentials are available.
- The workflow processes one finding at a time. Multi-finding repair is a
  future enhancement.

## Gate decision

L6 is coherent and independently useful as a Bob engineering workflow. Bob
receives findings, proposes a repair, and Crucible deterministically accepts
or rejects based on re-audit. The rule-based proposer is verified; the LLM
proposer is BLOCKED (no API key) and honestly documented. The decision path
is deterministic: the proposer generates text, the re-audit decides. L7
(closed repair loop) may begin by adding behavioral replay to the acceptance
criteria, closing the loop: find -> propose -> re-audit -> replay -> accept/reject.
