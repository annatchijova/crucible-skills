"""Small L1 command-line surface."""

from __future__ import annotations

import argparse
import json

from .compiler import compile_corpus


def main() -> int:
    parser = argparse.ArgumentParser(prog="crucible")
    parser.add_argument("root", help="directory containing SKILL.md files")
    args = parser.parse_args()
    print(json.dumps(compile_corpus(args.root), ensure_ascii=False, indent=2, sort_keys=True))
    return 0
