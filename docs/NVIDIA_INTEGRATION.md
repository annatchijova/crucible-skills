# NVIDIA and Nebius Integration Contract

**Status:** L5 harness implemented; Nebius execution BLOCKED (no API key). Requirements verified, local executor verified.  
**Access date:** 2026-09-23

## Verified hackathon requirements

The official Devpost page and rules state that a submission must be a working software application that runs on Nebius Token Factory or Nebius AI Cloud and uses at least one NVIDIA open source model. The rules define runtime use as a call to the Token Factory inference API or execution on Nebius AI Cloud compute, including Serverless Jobs, Serverless Endpoints, or DevPods.

The submission must include a working project, track, description, working demo URL or test build where applicable, a public demonstration video of three minutes or less, and a public code repository with an open-source license and README setup instructions. The README must explain use of the NVIDIA model, Token Factory acceleration, and other Nebius tools used. If the project existed before the submission period, the submission must explain what was significantly updated during that period. Submission materials must be in English or include English translations.

The four tracks are Coding and Agentic Engineering, Best Apps and Agents, Personal AI, and Physical AI. CRUCIBLE currently fits most directly in Coding and Agentic Engineering as a developer tool, with Best Apps and Agents as a fallback if the product experience becomes the stronger story.

Sources: [hackathon overview](https://nebiusglobalaihackathon.devpost.com/), [official rules](https://nebiusglobalaihackathon.devpost.com/rules), accessed 2026-09-23.

## Requirement-to-evidence matrix

| Requirement | Primary source | CRUCIBLE component | Status | Evidence required |
|---|---|---|---|---|
| Working software application | Official rules §4 | CLI/core plus artifact | VERIFIED | Runnable repository and recorded execution |
| Runtime call to Token Factory or Nebius AI Cloud compute | Official rules §4 | Behavioral harness Nebius executor | BLOCKED | Redacted request metadata, endpoint/runtime record, successful run |
| At least one NVIDIA open-source model | Overview/rules | `nvidia/nemotron-3-super-120b-a12b` pinned in NebiusExecutor | VERIFIED (selected) | Model identifier, license/source, runtime metadata |
| Track fit | Overview/rules | Developer tool for methodology verification | PLANNED | Demo task showing code-agent workflow |
| Working demo URL/test build | Overview | Read-only viewer or CLI test build | PLANNED | Public URL or deterministic test instructions |
| ≤3-minute public video | Overview | Contradiction → mutation → replay storyboard | PLANNED | Published video with model/Nebius narration |
| Public repository with open-source license | Overview/rules | Apache-2.0 repository | VERIFIED | `LICENSE` at repository root |
| README setup instructions | Overview | README and technical docs | VERIFIED | Fresh-clone instructions tested before submission |
| Explain NVIDIA/Nebius usage | Overview | `NVIDIA_INTEGRATION.md` and final README | VERIFIED (code) / BLOCKED (run) | Concrete model call that affects an experiment |
| Feedback on tools/models | Overview | Submission notes | PLANNED | Recorded, honest operational feedback |
| Pre-existing project disclosure | Overview | Submission delta note | PLANNED | Written explanation of hackathon-period changes |
| English submission materials | Rules | README/docs in English plus Spanish companion | VERIFIED | English primary materials |
| Complete product experience | Judging criteria | CLI/artifact + optional viewer | PLANNED | Judges can run the workflow and inspect evidence |

`VERIFIED` here means verified from repository state or source text, not hackathon eligibility approval.

## Architecturally honest model role

The NVIDIA model must affect an experiment. The intended first experiment is a pinned behavioral differential:

```text
same task + same agent route + same runtime
    ├── no skill
    ├── original skill
    ├── methodology mutant
    └── candidate repair
              ↓
     explicit property observations
```

The model may generate behavior that the property oracle observes. Its prose is not itself the deterministic finding. Each run records model ID, provider/runtime, task fixture digest, skill digest, temperature/sampling controls where available, and limitations.

## Integration boundary

CRUCIBLE may consume SkillSpector/SkillEvaluator outputs as neighboring evidence. It must not silently treat a security finding, benchmark score, signature, or model judgment from another tool as a CRUCIBLE invariant. Imported evidence retains source URL, version/commit, artifact digest, and scope.

## What is not yet claimed

- We have not executed a Token Factory or Nebius AI Cloud run. The Nebius executor is real code (OpenAI-compatible API, Bearer auth, pinned `nvidia/nemotron-3-super-120b-a12b`) but the execution is BLOCKED because `NEBIUS_API_KEY` is not yet available.
- We have not verified that every planned behavioral task is stable across model versions.
- We have not established that a model-generated observation generalizes beyond its pinned task/runtime.
- We have not claimed hackathon compliance merely because the architecture mentions Nebius.

## What IS claimed

- The L5 behavioral differential harness is implemented and verified with a local deterministic executor.
- The property oracle is deterministic: the same output always produces the same observations.
- The Nebius executor is real code that will call the Token Factory API when `NEBIUS_API_KEY` is set.
- The report honestly documents `nebius_blocked: True` when the key is absent, with a local fallback for harness verification.
- The model is the subject of observation, not the judge. The property oracle decides; the model generates behavior.
