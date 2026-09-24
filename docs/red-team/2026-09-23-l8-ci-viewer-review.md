# Red-Team Review — L8 CI and Presentation Surfaces

**Date:** 2026-09-23  
**Scope:** adversarial review of L8 (report generator, HTML viewer, CI workflow) against L1-L7 invariants  
**Method:** hypothesis-driven, evidence-verified against live code  
**Status:** 0 confirmed defects, 1 rejected finding

## Method

L8 adds three components: a composite report generator (`report.py`), a
read-only HTML viewer (`viewer.py`), and a CI workflow (`.github/workflows/ci.yml`).
The review verifies the core invariant: "no consumer has independent decision
logic."

## Invariant verification

### No consumer has independent decision logic

**Verified:** the report generator delegates to each level's runner
(`run_mutation_lab`, `run_behavioral_differential`, `run_bob_workflow`,
`run_repair_loop`). It does NOT re-implement any level's logic. Empirically
confirmed: the L4 mutation digest in the report matches the mutation lab's
digest; the L7 loop digest in the report matches the repair loop's digest.

**Verified:** the viewer imports only `html`, `json`, and `typing`. It does
NOT import any level module. It reads a JSON artifact and renders it. It does
NOT re-compute digests, re-run audits, or make decisions. The HTML contains
no `<script>` tags — no client-side computation.

**Verified:** the CI workflow runs `pytest` and the CLI. It does NOT
implement any decision logic. It uploads artifacts for human review.

### Determinism

**Verified:** the report is deterministic. Cross-process digest confirmed
identical: two runs in separate processes produce the same `report_digest`.

### No floats in decision paths

**Verified:** zero floats found in the report. All values are strings,
integers, booleans, or nested structures thereof.

### No LLM in decision paths

**Verified:** the report generator does not call any LLM. The viewer does
not call any LLM. The CI workflow does not call any LLM.

### Honest blocked states

**Verified:** without `NEBIUS_API_KEY`, the report documents
`nebius_blocked: True` with the exact reason. The viewer renders the
BLOCKED status. The CI workflow uses `--local-executor` and does not
require an API key.

### Source/evidence traceability

**Verified:** the report carries all level digests (mutation, behavioral,
bob, loop) and the composite `report_digest`. The chain of custody is
unbroken: each level's digest is included in the report.

## Rejected findings

### R1: CI workflow references `skills/` directory which may not exist

**Hypothesis:** the `corpus-audit` job runs `crucible.cli skills`, but the
repository may not have a `skills/` directory. This would cause the CI to
fail.

**Verification:** the CI workflow is designed to run against the real
corpus if it exists. If the `skills/` directory does not exist, the job
will fail — but this is correct behavior: the CI should fail if the
corpus is missing, not silently skip the audit. The `test` and `report`
jobs do not depend on `corpus-audit`, so a missing corpus does not block
the core CI.

**Conclusion:** false positive. The CI correctly fails if the corpus is
missing. The core CI (tests + report) does not depend on the corpus.

## Summary

| ID | Invariant | Status |
|---|---|---|
| — | No consumer has independent decision logic | verified |
| — | Determinism (report cross-process) | verified |
| — | No floats in decision paths | verified (0 floats) |
| — | No LLM in decision paths | verified |
| — | Honest blocked states | verified |
| — | Source/evidence traceability | verified |

0 confirmed defects. 1 rejected finding. L8 is closed.
