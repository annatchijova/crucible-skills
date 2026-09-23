# Documentation Red-Team — Competitive Boundary

**Date:** 2026-09-23  
**Scope:** public narrative, NVIDIA/Nebius integration claim, and CRUCIBLE differentiation  
**Method:** claim/counterargument/falsifier review; source provenance preserved

## Threat model for the narrative

The hostile reader is a technically informed judge or maintainer who can inspect the public NVIDIA repositories, run competing tools, and ask whether CRUCIBLE's claimed gap is already covered. They can reject unsupported novelty, distinguish a plan from an implementation, and penalize sponsor integration that is decorative.

## Claim review

| Claim | Strongest counterargument | Current status | Falsifier / next experiment |
|---|---|---|---|
| Agent skills are executable methodology | A skill is only documentation; agent behavior depends on runtime, model, and task context | PLAUSIBLE, source-supported framing | Show a pinned task where adding/removing a skill changes an explicit property; record confounders |
| A security-clean skill can still be bad methodology | Security tools may already encode broad quality or behavioral checks that catch the example | PLAUSIBLE HYPOTHESIS | Run the retry/irreversible fixture through SkillSpector and SkillEvaluator, then compare what each actually reports |
| Composition needs more than semantic similarity | Embeddings plus LLM analysis may already infer relations indirectly | PLAUSIBLE HYPOTHESIS | Build disjoint-scope, composition, reinforcement, and conditional-conflict fixtures; compare classifications |
| Mutation kill rate says something useful about verifier quality | A weak mutant or weak oracle can inflate or depress the metric | DESIGN HYPOTHESIS | Hidden expectations, negative controls, mutation classes, and surviving-mutant analysis |
| Behavioral differential can use explicit properties without becoming LLM-as-judge | The property extractor/oracle may itself become a hidden model judgment | PARTIAL OVERLAP | Keep the oracle deterministic where possible; label model-generated observations; test against negative controls |
| NVIDIA/Nebius integration is necessary to the experiment | A model call could be bolted on without changing the result | REQUIREMENT VERIFIED; SCIENTIFIC VALUE PLANNED | Remove the model route and show the behavioral experiment loses the intended observation, or narrow the claim |
| CRUCIBLE remains distinct from SkillEvaluator | Tier 3 already performs baseline/skill live evaluation, and future versions may add more methodology analysis | PROVISIONAL BOUNDARY | Re-run variant analysis against each new upstream release; if normative IR/mutation/composition exists, narrow CRUCIBLE |

## Findings

### RT-DOC-001 — The differentiation is real only as a scoped research boundary

**Epistemic level:** CODE FACT / DOCUMENTED CAPABILITY for NVIDIA overlap; PLAUSIBLE HYPOTHESIS for the remaining gap.  
**Scope:** public repositories and documentation inspected on 2026-09-23; SkillEvaluator checkout `5c73273`.  
**Evidence:** [`docs/COMPETITIVE_BOUNDARY.md`](../COMPETITIVE_BOUNDARY.md).  
**Falsifier:** a current or future NVIDIA component demonstrates the same normative IR, typed conditional composition, and methodology mutation loop.

The README therefore avoids “first,” “unique,” “better,” and “NVIDIA cannot.”

### RT-DOC-002 — The retry example is a target fixture, not a demonstrated finding

**Epistemic level:** PLAUSIBLE HYPOTHESIS.  
**Scope:** two hypothetical skills; no parser, oracle, or model run exists yet.  
**Evidence:** [`docs/EVALUATION_PLAN.md`](../EVALUATION_PLAN.md).  
**Falsifier:** idempotency or an external idempotency key makes the retry composition safe under the stated conditions.

The narrative explicitly calls the conflict conditional and names a falsifier.

### RT-DOC-003 — Hackathon compliance is planned, not earned

**Epistemic level:** CODE FACT for the published rules; PLANNED for CRUCIBLE execution.  
**Scope:** Devpost overview/rules accessed 2026-09-23.  
**Evidence:** [`docs/NVIDIA_INTEGRATION.md`](../NVIDIA_INTEGRATION.md).  
**Falsifier:** a source update changes the runtime/model/submission requirements, or a final run fails to produce the required evidence.

The documentation does not call the project compliant merely because it names Nebius.

## Discarded overclaims

- “NVIDIA tools only scan for malicious strings.” Rejected: SkillSpector has broad analyzers and SkillEvaluator has Tier 1–3 evaluation.
- “SkillEvaluator does not evaluate behavior.” Rejected: Tier 3 explicitly compares with-skill and without-skill agent runs.
- “NVIDIA's verified catalog is ground-truth clean.” Rejected: signatures and benchmarks establish bounded properties, not universal correctness.
- “CRUCIBLE proves methodology correctness.” Rejected: the current project is in progress and can only test declared properties within explicit scope.
- “The NVIDIA model is just used for narration.” Rejected as an acceptable architecture; the planned model route must generate observed behavior.
