"""Crucible's deterministic corpus compiler and audit engine."""

from .auditor import audit_corpus
from .compiler import compile_corpus

__all__ = ["compile_corpus", "audit_corpus"]
