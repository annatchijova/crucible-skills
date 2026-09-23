"""Command-line surface for compilation, auditing, composition analysis, mutation testing, and behavioral differential."""

from __future__ import annotations

import argparse
import json

from .auditor import audit_corpus
from .behavioral import LocalExecutor, NebiusExecutor, run_behavioral_differential
from .compiler import compile_corpus
from .graph import build_composition_graph
from .mutation import run_mutation_lab


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="crucible",
        description="Compile, audit, analyze, mutation-test, and behaviorally evaluate a skill corpus.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        help="directory containing SKILL.md files (required unless --mutate or --behave)",
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
    args = parser.parse_args()

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

    if not args.root:
        parser.error("root is required unless --mutate or --behave is given")

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
