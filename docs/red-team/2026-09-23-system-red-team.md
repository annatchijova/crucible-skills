# Red-Team Review — Full System L1-L6

**Date:** 2026-09-23  
**Scope:** adversarial review of all six implementation levels as a system  
**Method:** hypothesis-driven, evidence-verified against live code  
**Status:** 3 confirmed defects, 2 false positives rejected

## Method

Each level was inspected against its invariants using the abductive loop:
observe (Firstness), compare to expected (Secondness), infer the rule
(Thirdness), then attempt to refute before acting. Findings were verified
against the live code, not against documentation or memory.

## Confirmed defects

### D1: L6 `no_new_findings` is a count check, not a novelty check

**Severity:** high — accepts a repair that introduces a new defect class

**Location:** `src/crucible/bob.py`, `_evaluate_repair` function, line 405

**Evidence:**

The acceptance criteria in `_evaluate_repair` are:

```python
if not _finding_gone(finding, repaired_findings):
    return OUTCOME_REJECTED, "FINDING_PERSISTS"
if len(repaired_findings) > len(original_findings):
    return OUTCOME_REJECTED, "NEW_FINDINGS"
return OUTCOME_ACCEPTED, None
```

The second check compares counts: `len(repaired) > len(original)`. This
means a repair that removes the targeted finding (count -1) but introduces
a different finding (count +1) produces `len(repaired) == len(original)`,
which passes the check. The repair is ACCEPTED despite introducing a new
defect.

**Reproduction:**

A corpus with 2 findings (COMPOSITION_CYCLE + REQUIREMENT_WITHOUT_CHECK).
A repair that adds checks (removes REQUIREMENT_WITHOUT_CHECK) but adds a
self-composition (introduces SELF_COMPOSITION) produces 1 finding. The
count drops from 2 to 1, so `len(repaired) > len(original)` is False. The
repair is ACCEPTED, but SELF_COMPOSITION is a new finding that was not in
the original audit.

**Root cause:**

The check asks "are there more findings than before?" but should ask "are
there findings that were not in the original audit?" A count comparison
cannot distinguish "same findings, fewer" from "different findings, same
count".

**Fix:**

Replace the count comparison with a set-difference check: compute the set
of (class, skill) pairs in the repaired audit that are not in the original
audit. If that set is non-empty, reject with NEW_FINDINGS.

### D2: L5 property oracle has false positives from keyword polarity

**Severity:** medium — the oracle passes outputs that semantically contradict
the property

**Location:** `src/crucible/behavioral.py`, `_check_mentions_budget` (line 343)
and `_check_respects_exception` (line 351)

**Evidence:**

P1 (`_check_mentions_budget`) checks for the presence of keywords:
`("finite", "bounded", "budget", "at most")`. It returns PASS if any keyword
is present, regardless of polarity. The output "The budget is not needed
for this operation" passes P1 because "budget" is present, even though the
output says the budget is NOT needed.

P2 (`_check_respects_exception`) checks for:
`("except", "exempt", "exception", "read-only")`. The output "There is no
exception to this rule" passes P2 because "exception" is present, even
though the output says there is NO exception.

**Root cause:**

Keyword presence without polarity analysis. The oracle detects the word
but not its semantic role. This is a known limitation of deterministic
keyword oracles, but the current implementation does not document it as
a limitation in the report.

**Fix:**

Two options:
1. Add negation detection: if the keyword is preceded by "not", "no",
   "without", or "never" within a small window, treat it as a negated
   mention and return FAIL.
2. Document this as a known limitation in `BEHAVIORAL_LIMITATIONS` so
   consumers know the oracle checks keyword presence, not polarity.

Option 1 is better because it fixes the false positive. Option 2 is
honest but leaves the false positive in place.

### D3: L5 P3 oracle is too permissive with concurrent positive bounds

**Severity:** low — the oracle passes an output that recommends unbounded
retry but also mentions a bound

**Location:** `src/crucible/behavioral.py`, `_check_no_unbounded_retry` (line 359)

**Evidence:**

P3 checks for negation patterns (e.g., "not be bounded") and unbounded
recommendations ("until the operation succeeds"). If a positive bound is
present anywhere in the output (`budget of \d+`), the check returns PASS
even if the primary recommendation is unbounded.

The output "Retries should not be bounded by a finite budget. However,
use a budget of 3 attempts as a guideline" passes P3 because "budget of 3"
matches the positive bound regex. But the primary recommendation is
"not be bounded" — the "however" clause is a weak qualification, not a
bound.

**Root cause:**

The positive bound check is too generous: any `budget of \d+` anywhere in
the output overrides the negation. A real fix would check whether the
positive bound is the primary recommendation, not a qualification.

**Fix:**

Tighten the positive bound check: only count it if the bound appears in
the same sentence as the recommendation, not in a separate qualifying
clause. Alternatively, require the positive bound to appear WITHOUT a
preceding negation in the same sentence.

## Rejected findings (false positives)

### R1: L6 DELETE_RULE repair is accepted

**Hypothesis:** a repair that deletes the rule text would be accepted
because the finding disappears.

**Verification:** tested empirically. The repair was REJECTED with
FINDING_PERSISTS because the auditor still finds REQUIREMENT_WITHOUT_CHECK
on the skill (the SHOULD rule remains even after deleting the MUST rule).

**Conclusion:** false positive. The auditor checks for any MUST/SHOULD
rule without checks, not for a specific rule. Deleting one rule does not
remove the finding if others remain.

### R2: L6 SWAP finding (1-for-1) is accepted

**Hypothesis:** a repair that swaps one finding for exactly one different
finding would be accepted because the count is unchanged.

**Verification:** tested empirically with the BOB_FIXTURE. The swap
produced 3 findings (BROKEN_REFERENCE + 2 ORPHAN_SKILL), not 1, because
adding a broken reference to a corpus with no edges triggers ORPHAN_SKILL
on the other skills. The count increased, so the repair was REJECTED.

**Conclusion:** false positive for this specific fixture. However, the
underlying bug (D1) is real and was confirmed with a different corpus
that has a cycle, where the swap produces exactly 1 finding.

## Summary

| ID | Level | Severity | Confirmed | Fix |
|---|---|---|---|---|
| D1 | L6 | high | yes | replace count check with set-difference |
| D2 | L5 | medium | yes | add negation detection to P1 and P2 |
| D3 | L5 | low | yes | tighten positive bound check in P3 |
| R1 | L6 | — | no (rejected) | — |
| R2 | L6 | — | no (rejected) | — |
