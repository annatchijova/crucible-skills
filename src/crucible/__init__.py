"""Crucible's deterministic corpus compiler, audit engine, composition graph, and mutation lab."""

from .auditor import audit_corpus
from .compiler import compile_corpus
from .graph import build_composition_graph
from .mutation import run_mutation_lab

__all__ = ["compile_corpus", "audit_corpus", "build_composition_graph", "run_mutation_lab"]
