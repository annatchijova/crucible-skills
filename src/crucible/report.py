"""Composite report generator (L8).

Runs the full L1-L7 pipeline and produces a single sealed artifact that
contains all level outputs with their digests and chain of custody.

The report generator delegates to each level's runner. It does NOT
re-implement any level's logic. It only orchestrates and seals.

The report is deterministic: the same corpus and fixtures always
produce the same report digest. No floats, no LLM, no randomness.
"""

from __future__ import annotations

from typing import Any

from .auditor import AUDIT_VERSION, audit_corpus
from .behavioral import (
    BEHAVIORAL_VERSION,
    LocalExecutor,
    NebiusExecutor,
    run_behavioral_differential,
)
from .bob import BOB_VERSION, RuleBasedProposer, run_bob_workflow
from .compiler import SCHEMA_VERSION, compile_corpus
from .confirm import (
    CONFIRMATION_VERSION,
    MockConfirmExecutor,
    NebiusConfirmExecutor,
    confirm_semantic_redundancy,
)
from .graph import GRAPH_VERSION, build_composition_graph
from .ir import digest_payload
from .mutation import MUTATION_VERSION, run_mutation_lab
from .repair_loop import LOOP_VERSION, run_repair_loop

REPORT_VERSION = "crucible-report/v1"


def run_full_report(
    corpus_root: str | None = None,
    executor: Any | None = None,
) -> dict[str, Any]:
    """Run the full L1-L7 pipeline and return a sealed composite report.

    If corpus_root is given, L1-L3 run against that corpus. If not, they
    use the built-in fixtures from L4/L6/L7.

    The report includes:
    - L1: Skill IR (if corpus_root is given)
    - L2: Audit artifact (if corpus_root is given)
    - L3: Composition graph (if corpus_root is given)
    - L4: Mutation lab report
    - L5: Behavioral differential report
    - L6: Bob workflow report
    - L7: Closed repair loop report
    - Chain of custody: all digests
    - Nebius blocked status
    """
    # Determine executor and blocked status.
    nebius_blocked = False
    block_reason = None
    if executor is None:
        nebius = NebiusExecutor()
        if nebius.is_available():
            executor = nebius
        else:
            nebius_blocked = True
            block_reason = (
                "NEBIUS_API_KEY is not set; using LocalExecutor for "
                "behavioral and repair loop; Nebius execution is BLOCKED"
            )
            executor = LocalExecutor()
    else:
        # If the caller passed an executor, check whether it's Nebius.
        # If it's not Nebius and Nebius is not available, document as blocked.
        from .behavioral import NebiusExecutor as _Nebius
        if not isinstance(executor, _Nebius):
            nebius = NebiusExecutor()
            if not nebius.is_available():
                nebius_blocked = True
                block_reason = (
                    "NEBIUS_API_KEY is not set; using LocalExecutor for "
                    "behavioral and repair loop; Nebius execution is BLOCKED"
                )

    report: dict[str, Any] = {
        "report_version": REPORT_VERSION,
        "levels": {},
        "nebius_blocked": nebius_blocked,
        "block_reason": block_reason,
    }

    # L1-L3: only if a corpus root is given.
    if corpus_root is not None:
        ir = compile_corpus(corpus_root)
        audit = audit_corpus(ir)
        graph = build_composition_graph(ir, audit)
        report["levels"]["L1"] = {
            "schema_version": ir["schema_version"],
            "artifact_digest": ir["artifact_digest"],
            "skill_count": len(ir["skills"]),
        }
        report["levels"]["L2"] = {
            "audit_version": audit["audit_version"],
            "audit_digest": audit["audit_digest"],
            "input_artifact_digest": audit["input_artifact_digest"],
            "finding_count": len(audit["findings"]),
            "findings": [f["class"] for f in audit["findings"]],
            "limitation_count": len(audit["limitations"]),
        }
        report["levels"]["L3"] = {
            "graph_version": graph["graph_version"],
            "graph_digest": graph["graph_digest"],
            "input_ir_digest": graph["input_ir_digest"],
            "input_audit_digest": graph["input_audit_digest"],
            "edge_count": len(graph["edges"]),
            "node_count": len(graph["nodes"]),
            "graph_property_count": len(graph["graph_properties"]),
        }

        # L2.5: semantic redundancy confirmation layer.
        # Uses the mock executor for determinism in the composite report.
        # The Nebius executor is used when NEBIUS_API_KEY is available.
        confirm_executor = NebiusConfirmExecutor()
        if not confirm_executor.is_available():
            confirm_executor = MockConfirmExecutor()
        confirmation = confirm_semantic_redundancy(audit, ir, confirm_executor)
        report["levels"]["L2.5"] = {
            "confirmation_version": confirmation["schema_version"],
            "confirmation_digest": confirmation["confirmation_digest"],
            "source_audit_digest": confirmation["source_audit_digest"],
            "status": confirmation["status"],
            "executor_model": confirmation["executor"]["model"],
            "total_confirmations": confirmation["summary"]["total"],
            "confirmed": confirmation["summary"]["confirmed"],
            "rejected": confirmation["summary"]["rejected"],
            "unclear": confirmation["summary"]["unclear"],
            "blocked": confirmation["summary"]["blocked"],
        }

    # L4: mutation lab (uses built-in fixture).
    mutation_report = run_mutation_lab()
    report["levels"]["L4"] = {
        "mutation_version": mutation_report["mutation_version"],
        "mutation_digest": mutation_report["mutation_digest"],
        "base_audit_digest": mutation_report["base_audit_digest"],
        "total_mutations": mutation_report["summary"]["total"],
        "kill_rate": mutation_report["summary"]["kill_rate"],
        "by_status": mutation_report["summary"]["by_status"],
        "by_survivor_classification": mutation_report["summary"][
            "by_survivor_classification"
        ],
        "results": [
            {
                "mutation_id": r["mutation_id"],
                "mutation_class": r["mutation_class"],
                "status": r["status"],
                "survivor_classification": r["survivor_classification"],
                "evidence": r["evidence"],
            }
            for r in mutation_report["results"]
        ],
    }

    # L5: behavioral differential.
    behavioral_report = run_behavioral_differential(executor=executor)
    report["levels"]["L5"] = {
        "behavioral_version": behavioral_report["behavioral_version"],
        "behavioral_digest": behavioral_report["behavioral_digest"],
        "task_id": behavioral_report["task_id"],
        "task_digest": behavioral_report["task_digest"],
        "executor_type": behavioral_report["executor"]["type"],
        "nebius_blocked": behavioral_report["nebius_blocked"],
        "block_reason": behavioral_report["block_reason"],
        "runs": [
            {
                "variant_id": r["variant_id"],
                "status": r["status"],
                "observations": r.get("observations", []),
            }
            for r in behavioral_report["runs"]
        ],
        "local_fallback_runs": (
            [
                {
                    "variant_id": r["variant_id"],
                    "status": r["status"],
                    "observations": r.get("observations", []),
                }
                for r in behavioral_report["local_fallback_runs"]
            ]
            if behavioral_report["local_fallback_runs"]
            else None
        ),
    }

    # L6: Bob workflow.
    bob_report = run_bob_workflow(proposer=RuleBasedProposer())
    report["levels"]["L6"] = {
        "bob_version": bob_report["bob_version"],
        "base_audit_digest": bob_report["base_audit_digest"],
        "repaired_audit_digest": bob_report.get("repaired_audit_digest", ""),
        "outcome": bob_report["outcome"],
        "rejection_reason": bob_report.get("rejection_reason"),
        "finding_class": bob_report["finding"]["class"] if bob_report["finding"] else None,
        "finding_skill": bob_report["finding"]["skill"] if bob_report["finding"] else None,
        "proposer": bob_report["proposal"]["proposer"] if bob_report["proposal"] else None,
        "original_finding_gone": bob_report["original_finding_gone"],
        "no_new_findings": bob_report["no_new_findings"],
        "original_finding_count": bob_report["original_finding_count"],
        "repaired_finding_count": bob_report["repaired_finding_count"],
    }

    # L7: closed repair loop.
    loop_report = run_repair_loop(proposer=RuleBasedProposer(), executor=executor)
    report["levels"]["L7"] = {
        "loop_version": loop_report["loop_version"],
        "loop_digest": loop_report["loop_digest"],
        "base_audit_digest": loop_report["base_audit_digest"],
        "repaired_audit_digest": loop_report.get("repaired_audit_digest", ""),
        "outcome": loop_report["outcome"],
        "rejection_reason": loop_report.get("rejection_reason"),
        "original_finding_gone": loop_report["original_finding_gone"],
        "no_new_findings": loop_report["no_new_findings"],
        "behavioral_regression": (
            loop_report["behavioral_replay"]["regression"]
            if loop_report["behavioral_replay"]
            else None
        ),
        "behavioral_regressions": (
            loop_report["behavioral_replay"]["regressions"]
            if loop_report["behavioral_replay"]
            else []
        ),
    }

    # Seal the composite report.
    report["report_digest"] = digest_payload(report)
    return report
