"""Command-line surface for compilation, auditing, and composition analysis."""

from __future__ import annotations

import argparse
import json

from .auditor import audit_corpus
from .compiler import compile_corpus
from .graph import build_composition_graph


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="crucible",
        description="Compile, audit, and analyze a skill corpus.",
    )
    parser.add_argument("root", help="directory containing SKILL.md files")
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
    args = parser.parse_args()

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
