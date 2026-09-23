"""Command-line surface for compilation, auditing, composition analysis, and mutation testing."""

from __future__ import annotations

import argparse
import json

from .auditor import audit_corpus
from .compiler import compile_corpus
from .graph import build_composition_graph
from .mutation import run_mutation_lab


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="crucible",
        description="Compile, audit, analyze, and mutation-test a skill corpus.",
    )
    parser.add_argument(
        "root",
        nargs="?",
        help="directory containing SKILL.md files (required unless --mutate)",
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
    args = parser.parse_args()

    if args.mutate:
        report = run_mutation_lab()
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if not args.root:
        parser.error("root is required unless --mutate is given")

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
