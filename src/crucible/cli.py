"""Command-line surface for compilation and auditing."""

from __future__ import annotations

import argparse
import json

from .auditor import audit_corpus
from .compiler import compile_corpus


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="crucible",
        description="Compile and audit a skill corpus into a sealed artifact.",
    )
    parser.add_argument("root", help="directory containing SKILL.md files")
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="emit the L1 Skill IR without auditing",
    )
    args = parser.parse_args()

    artifact = compile_corpus(args.root)
    if args.compile_only:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    audit = audit_corpus(artifact)
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
