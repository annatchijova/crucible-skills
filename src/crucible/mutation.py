"""Mutation laboratory for testing the auditor against seeded defects (L4).

The mutation lab takes a known-good fixture corpus, applies deliberate
mutations, runs the full pipeline (compile -> audit -> graph), and classifies
each result as KILLED, SURVIVED, or ABSTAINED. Survivors are classified by
cause: insufficient detector, equivalent mutant, insufficient representation,
defective oracle, or out of scope.

The lab is deterministic: the same fixture and mutations always produce the
same report and the same ``mutation_digest``. No floats, no LLM, no randomness.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from .auditor import AUDIT_VERSION, audit_corpus
from .compiler import compile_corpus
from .graph import GRAPH_VERSION, build_composition_graph
from .ir import digest_payload

MUTATION_VERSION = "crucible-mutation/v1"

# ---------------------------------------------------------------------------
# Base fixture: a known-good corpus with specific properties
# ---------------------------------------------------------------------------

BASE_FIXTURE: dict[str, str] = {
    "retrier": (
        "---\n"
        "name: retrier\n"
        "description: Retry operations with a bounded budget. "
        "Triggers on retry operations only. "
        "Pairs with irreversible-action-gate.\n"
        "license: Apache-2.0\n"
        "---\n\n"
        "# Bounded retries\n\n"
        "Retries MUST have a finite budget, except for read-only operations.\n\n"
        "The operation SHOULD be idempotent before retrying.\n\n"
        "## Checks\n\n"
        "- Verify the retry budget is present.\n"
        "- Confirm idempotency before retry.\n\n"
        "## Composes with\n\n"
        "- irreversible-action-gate\n"
    ),
    "gate": (
        "---\n"
        "name: irreversible-action-gate\n"
        "description: Gate irreversible operations so they remain bounded and reviewable.\n"
        "license: Apache-2.0\n"
        "---\n\n"
        "# Irreversible action gate\n\n"
        "Irreversible operations MUST have bounded, reviewable effects.\n\n"
        "## Checks\n\n"
        "- Verify the effect is bounded.\n"
        "- Confirm the review path exists.\n"
    ),
}

# ---------------------------------------------------------------------------
# Mutation specifications
# ---------------------------------------------------------------------------

# Survivor classification codes.
SC_INSUFFICIENT_DETECTOR = "INSUFFICIENT_DETECTOR"
SC_EQUIVALENT_MUTANT = "EQUIVALENT_MUTANT"
SC_INSUFFICIENT_REPRESENTATION = "INSUFFICIENT_REPRESENTATION"
SC_DEFECTIVE_ORACLE = "DEFECTIVE_ORACLE"
SC_OUT_OF_SCOPE = "OUT_OF_SCOPE"

# Result statuses.
ST_KILLED = "KILLED"
ST_SURVIVED = "SURVIVED"
ST_ABSTAINED = "ABSTAINED"
ST_COMPILE_ERROR = "COMPILE_ERROR"

# Check locations.
LOC_AUDIT = "audit"
LOC_GRAPH = "graph"


def _spec(
    mutation_id: str,
    mutation_class: str,
    description: str,
    expected_finding_class: str | None,
    expected_location: str | None,
    property_under_test: str,
    pre_classification: str | None,
    survivor_classification: str | None,
) -> dict[str, Any]:
    return {
        "mutation_id": mutation_id,
        "mutation_class": mutation_class,
        "description": description,
        "expected_finding_class": expected_finding_class,
        "expected_location": expected_location,
        "property_under_test": property_under_test,
        "pre_classification": pre_classification,
        "survivor_classification": survivor_classification,
    }


# ---------------------------------------------------------------------------
# Mutator functions
# ---------------------------------------------------------------------------

def _polarity_inversion(base: dict[str, str]) -> dict[str, str]:
    """Flip MUST to MUST_NOT in a normative rule."""
    mutated = dict(base)
    mutated["retrier"] = mutated["retrier"].replace(
        "Retries MUST have a finite budget",
        "Retries MUST NOT have a finite budget",
    )
    return mutated


def _exception_removal(base: dict[str, str]) -> dict[str, str]:
    """Remove an exception clause from a normative rule."""
    mutated = dict(base)
    mutated["retrier"] = mutated["retrier"].replace(
        ", except for read-only operations",
        "",
    )
    return mutated


def _reference_break(base: dict[str, str]) -> dict[str, str]:
    """Break a composition reference to a non-existent skill."""
    mutated = dict(base)
    mutated["retrier"] = mutated["retrier"].replace(
        "- irreversible-action-gate",
        "- ghost-skill",
    )
    return mutated


def _check_removal(base: dict[str, str]) -> dict[str, str]:
    """Remove all checks from a skill that has normative rules."""
    mutated = dict(base)
    mutated["retrier"] = mutated["retrier"].replace(
        "\n## Checks\n\n"
        "- Verify the retry budget is present.\n"
        "- Confirm idempotency before retry.\n",
        "\n",
    )
    return mutated


def _trigger_widening(base: dict[str, str]) -> dict[str, str]:
    """Widen a trigger from specific to general."""
    mutated = dict(base)
    mutated["retrier"] = mutated["retrier"].replace(
        "Triggers on retry operations only.",
        "Triggers on all operations.",
    )
    return mutated


def _edge_removal(base: dict[str, str]) -> dict[str, str]:
    """Remove a composition edge from both description and section heading."""
    mutated = dict(base)
    mutated["retrier"] = mutated["retrier"].replace(
        " Pairs with irreversible-action-gate.",
        "",
    ).replace(
        "\n## Composes with\n\n- irreversible-action-gate\n",
        "\n",
    )
    return mutated


def _cycle_introduction(base: dict[str, str]) -> dict[str, str]:
    """Introduce a composition cycle by adding a reverse edge."""
    mutated = dict(base)
    mutated["gate"] = mutated["gate"] + (
        "\n## Composes with\n\n- retrier\n"
    )
    return mutated


def _capability_duplication(base: dict[str, str]) -> dict[str, str]:
    """Duplicate a skill's normative rule text in a new skill."""
    mutated = dict(base)
    mutated["retrier-v2"] = (
        "---\n"
        "name: retrier-v2\n"
        "description: Alternative retry approach.\n"
        "license: Apache-2.0\n"
        "---\n\n"
        "# Alternative retries\n\n"
        "Retries MUST have a finite budget, except for read-only operations.\n\n"
        "## Checks\n\n"
        "- Verify the retry budget is present.\n"
    )
    return mutated


# ---------------------------------------------------------------------------
# Mutation registry
# ---------------------------------------------------------------------------

MUTATIONS: list[tuple[dict[str, Any], Callable]] = [
    (
        _spec(
            "M001-polarity-inversion",
            "POLARITY_INVERSION",
            "Flip MUST to MUST_NOT in a normative rule.",
            "NORMATIVE_CONFLICT",
            LOC_AUDIT,
            "normative polarity and contradiction checks",
            ST_ABSTAINED,
            SC_OUT_OF_SCOPE,
        ),
        _polarity_inversion,
    ),
    (
        _spec(
            "M002-exception-removal",
            "EXCEPTION_REMOVAL",
            "Remove an exception clause from a normative rule.",
            "OVERGENERALIZATION",
            LOC_AUDIT,
            "boundary and overgeneralization checks",
            None,
            None,
        ),
        _exception_removal,
    ),
    (
        _spec(
            "M003-reference-break",
            "REFERENCE_BREAK",
            "Break a composition reference to a non-existent skill.",
            "BROKEN_REFERENCE",
            LOC_AUDIT,
            "provenance and graph integrity",
            None,
            None,
        ),
        _reference_break,
    ),
    (
        _spec(
            "M004-check-removal",
            "CHECK_REMOVAL",
            "Remove all checks from a skill that has normative rules.",
            "REQUIREMENT_WITHOUT_CHECK",
            LOC_AUDIT,
            "requirement-to-verification coverage",
            None,
            None,
        ),
        _check_removal,
    ),
    (
        _spec(
            "M005-trigger-widening",
            "TRIGGER_WIDENING",
            "Widen a trigger from specific to general.",
            "SCOPE_TRIGGER_MISMATCH",
            LOC_AUDIT,
            "activation contamination",
            ST_ABSTAINED,
            SC_OUT_OF_SCOPE,
        ),
        _trigger_widening,
    ),
    (
        _spec(
            "M006-edge-removal",
            "EDGE_REMOVAL",
            "Remove a composition edge from description and section heading.",
            "ISOLATED_SKILL",
            LOC_GRAPH,
            "composition graph integrity",
            None,
            None,
        ),
        _edge_removal,
    ),
    (
        _spec(
            "M007-cycle-introduction",
            "CYCLE_INTRODUCTION",
            "Introduce a composition cycle by adding a reverse edge.",
            "COMPOSITION_CYCLE",
            LOC_AUDIT,
            "graph invariants",
            None,
            None,
        ),
        _cycle_introduction,
    ),
    (
        _spec(
            "M008-capability-duplication",
            "CAPABILITY_DUPLICATION",
            "Duplicate a skill's normative rule text in a new skill.",
            "STRUCTURAL_REDUNDANCY",
            LOC_AUDIT,
            "marginal utility and redundancy",
            None,
            None,
        ),
        _capability_duplication,
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_mutation_lab(
    base_corpus: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run all mutations against the base fixture and return a sealed report.

    The report is deterministic: the same fixture and mutations always
    produce the same ``mutation_digest``.
    """
    if base_corpus is None:
        base_corpus = BASE_FIXTURE

    base_artifact = _compile_and_audit(base_corpus)
    base_digest = base_artifact["audit_digest"]

    results: list[dict[str, Any]] = []
    for spec, mutator in MUTATIONS:
        mutated_corpus = mutator(base_corpus)
        result = _run_single_mutation(spec, mutated_corpus, base_digest)
        results.append(result)

    report: dict[str, Any] = {
        "mutation_version": MUTATION_VERSION,
        "audit_version": AUDIT_VERSION,
        "graph_version": GRAPH_VERSION,
        "base_audit_digest": base_digest,
        "results": results,
        "summary": _summarize(results),
    }
    report["mutation_digest"] = digest_payload(report)
    return report


def _run_single_mutation(
    spec: dict[str, Any],
    mutated_corpus: dict[str, str],
    base_digest: str,
) -> dict[str, Any]:
    """Apply one mutation, run the pipeline, and classify the result."""
    try:
        artifact = _compile_and_audit(mutated_corpus)
    except ValueError as exc:
        return _result(
            spec,
            ST_COMPILE_ERROR,
            observed_classes=[],
            survivor_classification=None,
            evidence=f"compilation failed: {exc}",
            audit_digest="",
            base_digest=base_digest,
        )

    observed_classes = _observed_finding_classes(artifact, spec)
    expected_class = spec["expected_finding_class"]
    pre = spec["pre_classification"]

    if pre == ST_ABSTAINED:
        status = ST_ABSTAINED
        evidence = (
            f"expected check class {expected_class} is documented as "
            f"abstained in the audit limitations"
        )
        survivor_classification = spec["survivor_classification"]
    elif expected_class is not None and expected_class in observed_classes:
        status = ST_KILLED
        evidence = (
            f"expected finding {expected_class} was emitted by the auditor"
        )
        survivor_classification = None
    elif expected_class is not None:
        status = ST_SURVIVED
        evidence = (
            f"expected finding {expected_class} was NOT emitted; "
            f"observed: {observed_classes or 'none'}"
        )
        survivor_classification = _classify_survivor(spec, observed_classes)
    else:
        status = ST_SURVIVED
        evidence = (
            f"no specific finding expected for this mutation class; "
            f"observed: {observed_classes or 'none'}"
        )
        survivor_classification = spec["survivor_classification"]

    return _result(
        spec,
        status,
        observed_classes,
        survivor_classification,
        evidence,
        artifact["audit_digest"],
        base_digest,
    )


def _observed_finding_classes(
    artifact: dict[str, Any], spec: dict[str, Any]
) -> list[str]:
    """Extract finding/property class names from the audit or graph."""
    location = spec["expected_location"]
    if location == LOC_GRAPH:
        return sorted(
            p["property"] for p in artifact.get("graph_properties", [])
        )
    return sorted(f["class"] for f in artifact.get("findings", []))


def _classify_survivor(
    spec: dict[str, Any], observed: list[str]
) -> str:
    """Classify a surviving mutant by its likely cause."""
    pre = spec.get("survivor_classification")
    if pre is not None:
        return pre
    if not observed:
        return SC_INSUFFICIENT_DETECTOR
    return SC_INSUFFICIENT_DETECTOR


def _result(
    spec: dict[str, Any],
    status: str,
    observed_classes: list[str],
    survivor_classification: str | None,
    evidence: str,
    audit_digest: str,
    base_digest: str,
) -> dict[str, Any]:
    return {
        "mutation_id": spec["mutation_id"],
        "mutation_class": spec["mutation_class"],
        "description": spec["description"],
        "property_under_test": spec["property_under_test"],
        "expected_finding_class": spec["expected_finding_class"],
        "observed_finding_classes": observed_classes,
        "status": status,
        "survivor_classification": survivor_classification,
        "evidence": evidence,
        "mutated_audit_digest": audit_digest,
        "base_audit_digest": base_digest,
    }


def _compile_and_audit(corpus: dict[str, str]) -> dict[str, Any]:
    """Write a corpus dict to a temp dir, compile, audit, and build graph."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for skill_name, content in corpus.items():
            skill_dir = root / skill_name
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(content, encoding="utf-8", newline="\n")
        ir = compile_corpus(root)
        audit = audit_corpus(ir)
        graph = build_composition_graph(ir, audit)
    return {
        "findings": audit["findings"],
        "audit_digest": audit["audit_digest"],
        "graph_properties": graph["graph_properties"],
        "graph_digest": graph["graph_digest"],
    }


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_survivor: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        sc = r["survivor_classification"]
        if sc:
            by_survivor[sc] = by_survivor.get(sc, 0) + 1
    killed = by_status.get(ST_KILLED, 0)
    survived = by_status.get(ST_SURVIVED, 0)
    abstained = by_status.get(ST_ABSTAINED, 0)
    compile_errors = by_status.get(ST_COMPILE_ERROR, 0)
    # Kill rate excludes abstained and compile errors.
    scorable = killed + survived
    kill_rate = f"{killed}/{scorable}" if scorable > 0 else "N/A"
    return {
        "total": len(results),
        "by_status": dict(sorted(by_status.items())),
        "by_survivor_classification": dict(sorted(by_survivor.items())),
        "kill_rate": kill_rate,
    }
