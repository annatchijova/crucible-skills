"""Command-line surface for compilation, auditing, composition analysis, mutation testing, behavioral differential, Bob workflow, closed repair loop, report, and viewer."""

from __future__ import annotations

import argparse
import json

from .auditor import audit_corpus
from .behavioral import LocalExecutor, NebiusExecutor, run_behavioral_differential
from .bob import LLMProposer, RuleBasedProposer, run_bob_workflow
from .compiler import compile_corpus
from .confirm import (
    MockConfirmExecutor,
    NebiusConfirmExecutor,
    confirm_semantic_redundancy,
)
from .graph import build_composition_graph
from .mutation import run_mutation_lab
from .repair_loop import run_repair_loop
from .report import run_full_report
from .viewer import render_artifact_html


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="crucible",
        description="Compile, audit, analyze, mutation-test, behaviorally evaluate, repair, close the loop, report, and view a skill corpus.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        help="directory containing SKILL.md files (required unless --mutate/--behave/--bob/--repair-loop/--report/--view)",
    )
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="emit the L1 Skill IR without auditing or graph analysis",
    )
    parser.add_argument(
        "--no-graph",
        action="store_true",
        help="emit L1 + L2 audit without L3 composition graph",
    )
    parser.add_argument(
        "--mutate",
        action="store_true",
        help="run the L4 mutation lab against the built-in base fixture",
    )
    parser.add_argument(
        "--behave",
        action="store_true",
        help="run the L5 behavioral differential harness",
    )
    parser.add_argument(
        "--local-executor",
        action="store_true",
        help="use the local deterministic executor instead of Nebius (for testing)",
    )
    parser.add_argument(
        "--bob",
        action="store_true",
        help="run the L6 Bob workflow on the first finding",
    )
    parser.add_argument(
        "--repair-loop",
        action="store_true",
        help="run the L7 closed repair loop (find -> repair -> re-audit -> behavioral replay -> accept/reject)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="run the full L1-L7 pipeline and emit a sealed composite report",
    )
    parser.add_argument(
        "--view",
        metavar="ARTIFACT_JSON",
        help="render a sealed artifact JSON as a self-contained HTML page",
    )
    parser.add_argument(
        "--llm-proposer",
        action="store_true",
        help="use the LLM proposer (Nemotron via Nebius) instead of rule-based",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="run the L2.5 semantic redundancy confirmation layer on the audit",
    )
    parser.add_argument(
        "--mock-confirm",
        action="store_true",
        help="use the deterministic mock executor for the confirmation layer (for testing)",
    )
    args = parser.parse_args()

    if args.view:
        with open(args.view, encoding="utf-8") as f:
            artifact = json.load(f)
        print(render_artifact_html(artifact))
        return 0

    if args.mutate:
        report = run_mutation_lab()
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.behave:
        if args.local_executor:
            executor = LocalExecutor()
        else:
            executor = NebiusExecutor()
        report = run_behavioral_differential(executor=executor)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.bob:
        if args.llm_proposer:
            proposer = LLMProposer()
        else:
            proposer = RuleBasedProposer()
        report = run_bob_workflow(proposer=proposer)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.repair_loop:
        if args.llm_proposer:
            proposer = LLMProposer()
        else:
            proposer = RuleBasedProposer()
        if args.local_executor:
            executor = LocalExecutor()
        else:
            executor = None  # let the loop decide (Nebius or LocalExecutor fallback)
        report = run_repair_loop(proposer=proposer, executor=executor)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.report:
        if args.local_executor:
            executor = LocalExecutor()
        else:
            executor = None  # let the report decide (Nebius or LocalExecutor fallback)
        report = run_full_report(corpus_root=args.root, executor=executor)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.confirm:
        if not args.root:
            parser.error("root is required with --confirm")
        artifact = compile_corpus(args.root)
        audit = audit_corpus(artifact)
        if args.mock_confirm:
            executor = MockConfirmExecutor()
        else:
            executor = NebiusConfirmExecutor()
        confirmation = confirm_candidates(audit, artifact, executor)
        print(json.dumps(confirmation, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if not args.root:
        parser.error("root is required unless --mutate/--behave/--bob/--repair-loop/--report/--view is given")

    artifact = compile_corpus(args.root)
    if args.compile_only:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    audit = audit_corpus(artifact)
    if args.no_graph:
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    graph = build_composition_graph(artifact, audit)
    print(json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
