# ADR-0009: No Consumer Has Independent Decision Logic (L8)

**Status:** Accepted for L8  
**Date:** 2026-09-23  
**Reversibility:** high; the viewer and report are pure projections

## Context

L8 adds presentation surfaces: a composite report generator, an HTML
viewer, and a CI workflow. The question: should any of these consumers
implement their own decision logic (re-compute digests, re-run audits,
make acceptance decisions)?

## Decision

No consumer has independent decision logic. Each consumer is a pure
projection of sealed artifacts:

- **Report generator (`report.py`):** delegates to each level's runner
  (`run_mutation_lab`, `run_behavioral_differential`, `run_bob_workflow`,
  `run_repair_loop`). It orchestrates and seals; it does not re-implement.
  The L4 digest in the report is the L4 mutation lab's digest, not a
  re-computed one.
- **HTML viewer (`viewer.py`):** reads a JSON artifact and renders it.
  Imports only `html`, `json`, `typing`. No `<script>` tags. No
  computation. No re-computation of digests or outcomes.
- **CI workflow (`.github/workflows/ci.yml`):** runs `pytest` and the CLI.
  Uploads artifacts. Does not implement any decision logic.

## Alternatives rejected

- **Viewer re-computes digests for display.** Rejected because it would
  create a second source of truth. If the viewer's digest differs from the
  artifact's, which one is correct? Best argument for it: verifies the
  seal on render. But that is verification, not projection — a separate
  verifier tool would be appropriate, not the viewer.
- **Report generator re-implements level logic.** Rejected because it
  would diverge from the levels. The report must reflect what the levels
  actually produced, not what a re-implementation thinks they should
  produce.
- **CI makes acceptance decisions.** Rejected because CI is a
  presentation surface, not an authority. The deterministic engine decides;
  CI reports.

## Assumption this rests on

The level runners are the single source of truth for their respective
outputs. If a level runner changes, the report automatically reflects the
change because it delegates.

## Consequences

Accepted now:
- The report, viewer, and CI are pure projections.
- Adding a new level (L9+) only requires adding a delegation call to the
  report generator; the viewer and CI do not need changes.
- The viewer works with any artifact type (L1-L7 or composite report)
  because it renders what it sees, not what it computes.

Deferred:
- a standalone verifier tool that re-computes digests to confirm seal
  integrity (separate from the viewer);
- interactive viewer features (filtering, search) that would require
  client-side JavaScript.

## Revisit trigger

Revisit if the viewer needs interactive features (filtering, search) that
require client-side computation, or if a standalone seal verifier is added.
