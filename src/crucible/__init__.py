"""Crucible's deterministic corpus compiler, audit engine, composition graph, mutation lab, behavioral differential, Bob workflow, closed repair loop, and report/viewer."""

from .auditor import audit_corpus
from .behavioral import run_behavioral_differential
from .bob import run_bob_workflow
from .compiler import compile_corpus
from .graph import build_composition_graph
from .mutation import run_mutation_lab
from .repair_loop import run_repair_loop
from .report import run_full_report
from .viewer import render_artifact_html

__all__ = [
    "compile_corpus",
    "audit_corpus",
    "build_composition_graph",
    "run_mutation_lab",
    "run_behavioral_differential",
    "run_bob_workflow",
    "run_repair_loop",
    "run_full_report",
    "render_artifact_html",
]
