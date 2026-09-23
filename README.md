# Crucible Skills

**Verification engineering for AI agent methodologies.**

[English](README.md) · [Español](README_ES.md) · **[Technical README](TECHNICAL.md)**

![Crucible Skills logo](visual/logo.png)

> **Status: In progress — architecture and evaluation contract first.**

Agent skills are executable methodology: they change what a capable coding agent notices, prioritizes, verifies, and does. Existing tools can validate their shape, scan them for malicious behavior, and evaluate whether an agent performs better with them. That still leaves a harder question:

> **Is this methodology coherent, verifiable, composable, and worth adding to the corpus?**

Crucible Skills is being built to answer that question with structured evidence instead of an opaque quality score.

## Why this exists now

Agent Skills are becoming infrastructure. NVIDIA is already building serious infrastructure around them: SkillSpector addresses security and supply-chain risk; SkillEvaluator covers validation, semantic overlap, synthetic evaluation, and live agent comparison; and the NVIDIA catalog adds Skill Cards, signatures, benchmark artifacts, and publication gates. We want those controls. CRUCIBLE does not exist because they are unimportant; it exists because they do not exhaust the methodology question.

> **A skill does not need to be malicious to be harmful methodology. It can be perfectly benign and still teach an agent to engineer badly.**

For example:

```text
Skill A: retry failed operations until success.
Skill B: irreversible actions must be bounded and reviewable.

Neither is necessarily malicious in isolation.
The composition is problematic when the retry target is irreversible and non-idempotent.
```

CRUCIBLE is designed to make that kind of claim inspectable, conditional, and falsifiable. It is a complementary methodology-verification layer, not a replacement security scanner or live-agent evaluator. See the [competitive boundary](docs/COMPETITIVE_BOUNDARY.md) for the evidence-backed comparison.

## The idea in one example

Two skills can each look reasonable while creating a bad composition:

```text
Skill A: retry critical operations until they succeed.
Skill B: irreversible operations must have bounded, reviewable effects.

Individually plausible → jointly unsafe when retries duplicate an irreversible effect.
```

Crucible extracts the declared rules, scopes, triggers, checks, references, and composition edges; then it tests the corpus for contradictions, missing verification, redundancy, broken provenance, and mutation resistance.

```mermaid
flowchart LR
    C[Skill corpus] --> P[Parse into Skill IR]
    P --> G[Composition graph]
    P --> A[Deterministic audit]
    G --> A
    A --> M[Mutation laboratory]
    M --> R[Reproducible audit artifact]
    R --> B[Bob engineering workflow]
    B --> V[Re-audit and behavioral replay]
    V --> R
```

## What makes it different

| Existing question | Crucible question |
|---|---|
| Is the file valid? | Does the methodology declare a coherent contract? |
| Is the skill dangerous? | Does its composition create a new failure surface? |
| Does an agent score better with it? | Which invariant changed, and can the change be reproduced? |
| Is the text similar to another skill? | Is it redundant, compositional, reinforcing, or contradictory? |

Crucible is intended to complement security scanners and live agent evaluators, not to replace them.

## Planned verification layers

1. **Corpus compiler** — parse frontmatter, normative language, scopes, triggers, checks, references, provenance, and declared composition into a versioned intermediate representation.
2. **Deterministic auditor** — find broken references, orphaned skills, cycles, scope conflicts, trigger collisions, requirements without checks, unsupported numeric claims, and structural duplication.
3. **Composition analysis** — distinguish redundancy, composition, reinforcement, and contradiction rather than treating every overlap as a duplicate.
4. **Mutation laboratory** — deliberately weaken or distort a valid skill and measure whether the auditor kills the mutant.
5. **Behavioral differential** — compare baseline, original, mutated, and repaired methodology on the same task with explicit properties.
6. **Bob workflow** — let IBM Bob investigate, repair, and challenge findings while Crucible remains the authority that verifies the result.

## The NVIDIA/Nebius experiment

For the Nebius x NVIDIA Global AI Hackathon, the NVIDIA open-source model must have a real experimental role. The planned experiment pins one task, corpus, skill variant, model/runtime, and property oracle, then compares:

```text
no skill → original skill → deliberate mutant → candidate repair
```

The model generates the agent behavior that the oracle observes. CRUCIBLE records the model/runtime metadata and keeps deterministic findings separate from behavioral observations. The integration contract and current requirement matrix are in [`docs/NVIDIA_INTEGRATION.md`](docs/NVIDIA_INTEGRATION.md).

The hackathon requires a working application running on Nebius Token Factory or Nebius AI Cloud, at least one NVIDIA open-source model, an open-source public repository, README setup instructions, a working demo or test build where applicable, and a public demo video of three minutes or less. These are planned submission obligations, not claims that the current repository already satisfies them.

## Current state

This repository has the first three coherent implementation levels:

- **L1 — Corpus compiler:** parses `SKILL.md` frontmatter, normative language, checks, relations, and references into a versioned, source-addressable Skill IR (`skill-ir/v1`) with deterministic SHA-256 artifact digests.
- **L2 — Deterministic auditor:** consumes the L1 IR and emits findings with source evidence and epistemic status (CONFIRMED / CANDIDATE / OBSERVATION), seals an AuditArtifact (`crucible-audit/v1`), and documents five abstained checks as explicit limitations rather than silently passing them.
- **L3 — Composition graph:** extracts typed relation edges from both L1 section headings and description text (sibling of, pairs with, composes with, member of the family, companion to), classifies them into composition/reinforcement/delegation, detects hubs and disconnected components, and seals a GraphArtifact (`crucible-graph/v1`). The real corpus produces 83 edges, 12 hubs, and 4 disconnected components.

L1 has been exercised against the local real corpus (103 skills, 140 extracted normative lines, 175 checks). L2 produces 1 finding (a CANDIDATE requirement-without-check) and 5 documented limitations. L3 produces 83 typed edges and reveals the corpus structure (12 hub skills, 4 disconnected components, 38 isolated skills). The deeper mutation, behavioral, and UI levels remain explicitly in progress.

### Run L1, L2, and L3 locally

```bash
PYTHONPATH=src python3 -m pytest -q
# Compile, audit, and build composition graph (default):
PYTHONPATH=src python3 -m crucible.cli /path/to/skill-corpus > graph-artifact.json
# Compile and audit without graph:
PYTHONPATH=src python3 -m crucible.cli --no-graph /path/to/skill-corpus > audit-artifact.json
# Compile only (L1 IR):
PYTHONPATH=src python3 -m crucible.cli --compile-only /path/to/skill-corpus > ir.json
```

The current corpus numbers are an observed run, not a universal benchmark. See the parser boundary in [ADR-0002](docs/decisions/0002-conservative-frontmatter-parser.md).

The intended stopping rule is deliberate: under a deadline, reach fewer complete levels rather than many disposable slices. Every level must remain useful and compatible with the final system.

## Repository map

```text
crucible-skills/
├── README.md              # primary project narrative
├── README_ES.md           # Spanish project adaptation
├── TECHNICAL.md           # architecture, contracts, threats, evidence
├── docs/
│   ├── ROADMAP.md         # public construction map
│   ├── COMPETITIVE_BOUNDARY.md # NVIDIA overlap and surviving gap
│   ├── NVIDIA_INTEGRATION.md   # hackathon requirements and runtime contract
│   ├── EVALUATION_PLAN.md      # metrics, fixtures, and negative controls
│   ├── SOURCES.md              # source-backed research record
│   ├── decisions/         # durable architectural decisions
│   └── red-team/          # adversarial review plans and evidence
├── src/crucible/
│   ├── ir.py              # canonical serialization and SHA-256 sealing
│   ├── compiler.py        # L1: SKILL.md → versioned Skill IR
│   ├── auditor.py         # L2: deterministic audit engine
│   ├── graph.py           # L3: typed composition graph
│   └── cli.py             # compile + audit + graph command-line surface
└── tests/
    ├── test_compiler_contract.py  # L1 falsifiable contract tests
    ├── test_auditor_contract.py   # L2 falsifiable contract tests
    └── test_graph_contract.py     # L3 falsifiable contract tests
```

## Why “Crucible”

A skill should survive heat: parsing, composition, deliberate mutation, adversarial review, and replay. The name describes the verification process, not a claim that the output is universally safe.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
