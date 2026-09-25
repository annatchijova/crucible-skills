# Pre-existing Project Disclosure

**Project:** Crucible Skills
**Repository:** https://github.com/annatchijova/crucible-skills
**License:** Apache-2.0

## Project origin

Crucible Skills was built from scratch during the hackathon period. The
first commit (`7319b81 chore: establish repository baseline`) was made on
2026-09-23. All 38 commits in the repository were made on 2026-09-23 and
2026-09-24. No code, tests, or documentation existed before the hackathon.

The project was conceived and implemented entirely within the hackathon
window. The research notes in `docs/research/` (intentionally gitignored)
were also created during the hackathon.

## What was built during the hackathon

### Day 1 (2026-09-23) — Core system

- L1: Corpus compiler — compiles SKILL.md files into a versioned,
  source-addressable Skill IR with SHA-256 content digests.
- L2: Deterministic auditor — 14 engineering and methodology checks
  covering normative conflicts, vacuity, redundancy, scope/trigger
  mismatch, requirement-without-check, claim-without-provenance,
  check-without-oracle, description-body gap, unbounded retry,
  irreversible-without-review, missing timeout, floating-point-in-
  decision-path, unpinned dependency, and overgeneralization.
- L3: Typed composition graph — resolves composition and delegation
  edges, detects cycles and orphan skills.
- L4: Mutation laboratory — 8 seeded mutations with 100% kill rate
  (6 killed, 2 abstained as out-of-scope, 0 survived).
- L5: Behavioral differential harness — deterministic property oracles
  with local executor and Nebius integration (blocked without API key).
- L6: Bob workflow — rule-based proposer with deterministic re-audit.
- L7: Closed repair loop — find, repair, re-audit, replay, accept/reject.
- L8: CI workflow and read-only HTML viewer.

### Day 2 (2026-09-24) — Extension and hardening

- L9: Style-agnostic extraction for non-RFC-2119 normative language.
- L10: 8 additional universal engineering checks (total: 22+ checks).
- L11: Public API, demo UI, Dockerfile for single-container deployment.
- L12: Nemotron confirmation layer extended to all engineering checks.
- L13: Corpus-agnostic validation against 10 skills from 7 sources.
- Red-team security audit of the L11 API surface (5 findings, all fixed).
- CI gate policy: determinism verification, mutation kill rate gate,
  security regression job.

## What is NOT complete

The following are honestly incomplete or blocked:

1. **Real Nebius/Nemotron execution** — the code is written and wired,
   but `NEBIUS_API_KEY` was not available during the hackathon. The
   system correctly reports `nebius_blocked: true` and falls back to
   the local deterministic executor. No simulated results are claimed.

2. **External corpus evaluation** — the system has been validated
   against the author's local corpus (97 installed skills) and a
   10-skill diverse corpus from 7 sources. Independent OSS and NVIDIA
   catalog skills are planned but not yet integrated.

3. **Seeded defect ground truth** — the mutation lab uses 8 seeded
   mutations with 100% kill rate. A larger seeded corpus with hidden
   labels for precision/recall measurement is planned.

4. **Polished demo** — the CLI, API, and HTML viewer are functional
   but not polished. A demo video and reproducible demo script are
   planned.

## NVIDIA / Nebius usage

Nebius is integrated as the model execution provider for the L5
behavioral differential harness and the L2.5 confirmation layer. The
default model is `nvidia/nemotron-3-super-120b-a12b` via the Nebius
Token Factory API. The integration is code-complete but has not been
executed against the real API due to missing credentials. The system
honestly reports this as blocked rather than simulating success.

## Verification

All claims in this document are verifiable:

- `git log --oneline` shows the commit history and dates.
- `PYTHONPATH=src python3 -m pytest` runs 420 tests, all passing.
- `PYTHONPATH=src python3 -m crucible.cli --report --local-executor`
  produces a sealed report with `nebius_blocked: true`.
- `PYTHONPATH=src python3 -m crucible.cli --mutate` shows 100% kill rate.
