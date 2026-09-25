"""Falsifiable contract tests for the mutation survivor kills (M002, M006).

These tests verify that the two previously-surviving mutations are now
killed by deterministic checks. Each test is designed to go red if the
check is removed or weakened.

M002 (EXCEPTION_REMOVAL) was killed by adding the OVERGENERALIZATION
check, which flags absolute-modality rules about retry/irreversible
subjects with bound indicators (budget, finite, limit) that have zero
exception conditions.

M006 (EDGE_REMOVAL) was killed by wiring the ISOLATED_SKILL graph
property to the mutation spec. When all composition edges are removed,
every skill becomes isolated and the graph property fires.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from crucible.auditor import audit_corpus
from crucible.compiler import compile_corpus
from crucible.graph import build_composition_graph
from crucible.mutation import BASE_FIXTURE, _edge_removal, _exception_removal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compile_and_audit(corpus: dict[str, str]) -> tuple[dict, dict, dict]:
    """Compile a corpus dict, audit, and build graph. Returns (ir, audit, graph)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for name, content in corpus.items():
            d = root / name
            d.mkdir()
            (d / "SKILL.md").write_text(content, encoding="utf-8", newline="\n")
        ir = compile_corpus(str(root))
        audit = audit_corpus(ir)
        graph = build_composition_graph(ir, audit)
    return ir, audit, graph


# ---------------------------------------------------------------------------
# M002: OVERGENERALIZATION check
# ---------------------------------------------------------------------------

def test_overgeneralization_fires_on_must_without_exception() -> None:
    """A MUST rule about retries with a bound indicator (finite budget)
    and zero exception conditions must produce an OVERGENERALIZATION finding.
    Mutation: remove the OVERGENERALIZATION check -> red."""
    corpus = {
        "retrier": (
            "---\n"
            "name: retrier\n"
            "description: Retry operations with a bounded budget.\n"
            "license: Apache-2.0\n"
            "---\n\n"
            "# Bounded retries\n\n"
            "Retries MUST have a finite budget.\n\n"
            "## Checks\n\n"
            "- Verify the retry budget is present.\n"
        ),
    }
    _, audit, _ = _compile_and_audit(corpus)
    classes = [f["class"] for f in audit["findings"]]
    assert "OVERGENERALIZATION" in classes


def test_overgeneralization_does_not_fire_with_exception() -> None:
    """A MUST rule about retries with an exception clause must NOT produce
    an OVERGENERALIZATION finding.
    Mutation: ignore exception conditions -> red (false positive)."""
    corpus = {
        "retrier": (
            "---\n"
            "name: retrier\n"
            "description: Retry operations with a bounded budget.\n"
            "license: Apache-2.0\n"
            "---\n\n"
            "# Bounded retries\n\n"
            "Retries MUST have a finite budget, except for read-only operations.\n\n"
            "## Checks\n\n"
            "- Verify the retry budget is present.\n"
        ),
    }
    _, audit, _ = _compile_and_audit(corpus)
    classes = [f["class"] for f in audit["findings"]]
    assert "OVERGENERALIZATION" not in classes


def test_overgeneralization_does_not_fire_without_bound_indicator() -> None:
    """A MUST rule about retries without a bound indicator (budget, finite,
    limit, etc.) must NOT produce an OVERGENERALIZATION finding. The rule
    is a general constraint, not a bound that needs exceptions.
    Mutation: remove the bound indicator requirement -> red (false positive)."""
    corpus = {
        "retrier": (
            "---\n"
            "name: retrier\n"
            "description: Retry operations.\n"
            "license: Apache-2.0\n"
            "---\n\n"
            "# Retries\n\n"
            "Retries MUST be logged.\n\n"
            "## Checks\n\n"
            "- Verify retries are logged.\n"
        ),
    }
    _, audit, _ = _compile_and_audit(corpus)
    classes = [f["class"] for f in audit["findings"]]
    assert "OVERGENERALIZATION" not in classes


def test_overgeneralization_does_not_fire_on_irreversible() -> None:
    """A MUST rule about irreversible operations with 'bounded' must NOT
    produce an OVERGENERALIZATION finding. 'irreversible' is not in the
    subject set, and 'bounded' is not a bound indicator.
    Mutation: add 'irreversible' to subjects or 'bounded' to indicators -> red."""
    corpus = {
        "gate": (
            "---\n"
            "name: gate\n"
            "description: Gate irreversible operations.\n"
            "license: Apache-2.0\n"
            "---\n\n"
            "# Irreversible action gate\n\n"
            "Irreversible operations MUST have bounded effects.\n\n"
            "## Checks\n\n"
            "- Verify the effect is bounded.\n"
        ),
    }
    _, audit, _ = _compile_and_audit(corpus)
    classes = [f["class"] for f in audit["findings"]]
    assert "OVERGENERALIZATION" not in classes


def test_overgeneralization_fires_on_must_not() -> None:
    """A MUST_NOT rule about retries with a bound indicator and zero
    exceptions must produce an OVERGENERALIZATION finding."""
    corpus = {
        "retrier": (
            "---\n"
            "name: retrier\n"
            "description: Retry operations.\n"
            "license: Apache-2.0\n"
            "---\n\n"
            "# Retries\n\n"
            "Retries MUST NOT exceed the maximum budget.\n\n"
            "## Checks\n\n"
            "- Verify the budget is respected.\n"
        ),
    }
    _, audit, _ = _compile_and_audit(corpus)
    classes = [f["class"] for f in audit["findings"]]
    assert "OVERGENERALIZATION" in classes


def test_exception_removal_produces_overgeneralization() -> None:
    """The M002 mutation (removing the exception clause) must produce a
    new OVERGENERALIZATION finding that was not present in the original.
    Mutation: remove the OVERGENERALIZATION check -> red."""
    _, orig_audit, _ = _compile_and_audit(BASE_FIXTURE)
    _, mut_audit, _ = _compile_and_audit(_exception_removal(BASE_FIXTURE))

    orig_classes = [f["class"] for f in orig_audit["findings"]]
    mut_classes = [f["class"] for f in mut_audit["findings"]]

    assert "OVERGENERALIZATION" not in orig_classes
    assert "OVERGENERALIZATION" in mut_classes


# ---------------------------------------------------------------------------
# M006: ISOLATED_SKILL graph property
# ---------------------------------------------------------------------------

def test_edge_removal_produces_isolated_skill() -> None:
    """The M006 mutation (removing all composition edges) must produce
    ISOLATED_SKILL graph properties that were not present in the original.
    Mutation: remove the ISOLATED_SKILL graph property -> red."""
    _, _, orig_graph = _compile_and_audit(BASE_FIXTURE)
    _, _, mut_graph = _compile_and_audit(_edge_removal(BASE_FIXTURE))

    orig_props = [p["property"] for p in orig_graph["graph_properties"]]
    mut_props = [p["property"] for p in mut_graph["graph_properties"]]

    assert "ISOLATED_SKILL" not in orig_props
    assert "ISOLATED_SKILL" in mut_props


def test_edge_removal_makes_all_skills_isolated() -> None:
    """After removing all edges, every skill in the corpus must have an
    ISOLATED_SKILL property."""
    _, _, graph = _compile_and_audit(_edge_removal(BASE_FIXTURE))
    isolated = [
        p for p in graph["graph_properties"]
        if p["property"] == "ISOLATED_SKILL"
    ]
    # The base fixture has 2 skills; both should be isolated.
    assert len(isolated) == 2


# ---------------------------------------------------------------------------
# Kill rate regression
# ---------------------------------------------------------------------------

def test_kill_rate_is_100_percent() -> None:
    """The mutation lab kill rate must be 6/6 (100%) with zero survivors.
    Mutation: remove OVERGENERALIZATION or ISOLATED_SKILL -> red."""
    from crucible.mutation import run_mutation_lab

    report = run_mutation_lab()
    assert report["summary"]["kill_rate"] == "6/6"
    assert report["summary"]["by_status"].get("SURVIVED", 0) == 0
