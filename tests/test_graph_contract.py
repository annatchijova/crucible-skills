"""Falsifiable contract tests for the L3 composition graph.

Each test names the invariant it defends and the mutation it would catch.
"""

from __future__ import annotations

from pathlib import Path

from crucible.compiler import compile_corpus
from crucible.graph import GRAPH_VERSION, build_composition_graph


def _write_skill(root: Path, name: str, body: str) -> Path:
    skill = root / name
    skill.mkdir()
    (skill / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")
    return skill


def _graph(root: Path) -> dict:
    return build_composition_graph(compile_corpus(root))


def _edge_types(graph: dict) -> set[str]:
    return {e["edge_type"] for e in graph["edges"]}


def _edges_from(graph: dict, source: str) -> list[dict]:
    return [e for e in graph["edges"] if e["source"] == source]


# ---------------------------------------------------------------------------
# SIBLING_OF extraction
# ---------------------------------------------------------------------------

def test_sibling_of_extracted_from_description(tmp_path: Path) -> None:
    """Invariant: 'Sibling of X' in description produces a SIBLING_OF edge.
    Mutation: skip the sibling trigger -> this test goes red."""
    _write_skill(
        tmp_path, "alpha",
        "---\nname: alpha\ndescription: A skill.\n---\n\nA MUST stop.\n",
    )
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Sibling of alpha — that skill "
        "governs X; this one governs Y.\n---\n\nB MUST stop.\n",
    )
    graph = _graph(tmp_path)
    assert "SIBLING_OF" in _edge_types(graph)
    beta_edges = _edges_from(graph, "beta")
    assert any(e["target"] == "alpha" and e["edge_type"] == "SIBLING_OF"
               for e in beta_edges)
    edge = next(e for e in beta_edges if e["edge_type"] == "SIBLING_OF")
    assert edge["relation_type"] == "REINFORCEMENT"
    assert edge["resolved"] is True
    assert edge["extraction_method"] == "description"


def test_sibling_of_does_not_fire_on_unrelated_text(tmp_path: Path) -> None:
    """Invariant: 'sibling' in non-relation context must not produce an edge.
    Mutation: match 'sibling' anywhere -> false positive."""
    _write_skill(
        tmp_path, "alpha",
        "---\nname: alpha\ndescription: A skill about siblings.\n---\n\n"
        "A MUST stop.\n",
    )
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Another skill.\n---\n\nB MUST stop.\n",
    )
    graph = _graph(tmp_path)
    assert "SIBLING_OF" not in _edge_types(graph)


# ---------------------------------------------------------------------------
# PAIRS_WITH extraction
# ---------------------------------------------------------------------------

def test_pairs_with_extracted_from_description(tmp_path: Path) -> None:
    """Invariant: 'Pairs with X' produces a PAIRS_WITH edge classified as
    COMPOSITION. Mutation: skip the pairs trigger -> red."""
    _write_skill(
        tmp_path, "alpha",
        "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n",
    )
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Pairs with alpha (complementary).\n---\n\n"
        "B MUST stop.\n",
    )
    graph = _graph(tmp_path)
    assert "PAIRS_WITH" in _edge_types(graph)
    edge = next(e for e in graph["edges"] if e["edge_type"] == "PAIRS_WITH")
    assert edge["relation_type"] == "COMPOSITION"
    assert edge["source"] == "beta"
    assert edge["target"] == "alpha"


# ---------------------------------------------------------------------------
# COMPOSES_WITH extraction (description + section heading merge)
# ---------------------------------------------------------------------------

def test_composes_with_from_description_and_section_are_merged(tmp_path: Path) -> None:
    """Invariant: the same target from description and section heading is
    one edge, not two. Mutation: don't deduplicate -> red."""
    _write_skill(
        tmp_path, "alpha",
        "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n",
    )
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Composes with alpha.\n---\n\n"
        "B MUST stop.\n\n## Composes with\n\n- alpha\n",
    )
    graph = _graph(tmp_path)
    cw_edges = [e for e in graph["edges"]
                if e["source"] == "beta" and e["target"] == "alpha"
                and e["edge_type"] == "COMPOSES_WITH"]
    assert len(cw_edges) == 1


# ---------------------------------------------------------------------------
# FAMILY_OF extraction
# ---------------------------------------------------------------------------

def test_family_of_extracts_multiple_targets(tmp_path: Path) -> None:
    """Invariant: 'member of the family (X, Y, Z)' produces edges to all
    named skills. Mutation: only take the first name -> red."""
    _write_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n")
    _write_skill(tmp_path, "beta", "---\nname: beta\ndescription: B.\n---\n\nB MUST stop.\n")
    _write_skill(tmp_path, "gamma", "---\nname: gamma\ndescription: C.\n---\n\nC MUST stop.\n")
    _write_skill(
        tmp_path, "delta",
        "---\nname: delta\ndescription: Fourth member of the family "
        "(alpha, beta, gamma) — this one governs D.\n---\n\nD MUST stop.\n",
    )
    graph = _graph(tmp_path)
    family_edges = [e for e in graph["edges"] if e["edge_type"] == "FAMILY_OF"
                    and e["source"] == "delta"]
    targets = {e["target"] for e in family_edges}
    assert targets == {"alpha", "beta", "gamma"}
    for e in family_edges:
        assert e["relation_type"] == "REINFORCEMENT"


# ---------------------------------------------------------------------------
# COMPANION_TO extraction
# ---------------------------------------------------------------------------

def test_companion_to_extracted_from_description(tmp_path: Path) -> None:
    """Invariant: 'Companion to X' produces a COMPANION_TO edge.
    Mutation: skip the companion trigger -> red."""
    _write_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n")
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Companion to alpha (the engine).\n---\n\n"
        "B MUST stop.\n",
    )
    graph = _graph(tmp_path)
    assert "COMPANION_TO" in _edge_types(graph)
    edge = next(e for e in graph["edges"] if e["edge_type"] == "COMPANION_TO")
    assert edge["relation_type"] == "COMPOSITION"


# ---------------------------------------------------------------------------
# Broken edges
# ---------------------------------------------------------------------------

def test_broken_edge_detected_when_target_not_in_corpus(tmp_path: Path) -> None:
    """Invariant: an edge to a non-existent skill is marked unresolved and
    reported as a BROKEN_EDGE property. Mutation: skip resolution check -> red."""
    _write_skill(
        tmp_path, "alpha",
        "---\nname: alpha\ndescription: Sibling of ghost-skill — not here.\n---\n\n"
        "A MUST stop.\n",
    )
    graph = _graph(tmp_path)
    edge = next(e for e in graph["edges"] if e["target"] == "ghost-skill")
    assert edge["resolved"] is False
    props = [p for p in graph["graph_properties"] if p["property"] == "BROKEN_EDGE"]
    assert len(props) == 1
    assert props[0]["epistemic_status"] == "CONFIRMED"


# ---------------------------------------------------------------------------
# Hub detection
# ---------------------------------------------------------------------------

def test_hub_detected_when_skill_has_many_incoming_edges(tmp_path: Path) -> None:
    """Invariant: a skill with >= 3 incoming edges is flagged as a hub.
    Mutation: change threshold or skip hub detection -> red."""
    _write_skill(
        tmp_path, "hub",
        "---\nname: hub\ndescription: The hub skill.\n---\n\nH MUST stop.\n",
    )
    for i, name in enumerate(["a", "b", "c"]):
        _write_skill(
            tmp_path, name,
            f"---\nname: {name}\ndescription: Sibling of hub — related.\n---\n\n"
            f"{name.upper()} MUST stop.\n",
        )
    graph = _graph(tmp_path)
    hub_nodes = [n for n in graph["nodes"] if n["is_hub"]]
    assert len(hub_nodes) == 1
    assert hub_nodes[0]["name"] == "hub"
    assert hub_nodes[0]["incoming_edges"] >= 3
    hub_props = [p for p in graph["graph_properties"] if p["property"] == "HUB"]
    assert any(p["skill"] == "hub" for p in hub_props)


def test_non_hub_not_flagged(tmp_path: Path) -> None:
    """Invariant: a skill with < 3 incoming edges is not a hub.
    Mutation: always flag hubs -> red."""
    _write_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n")
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Sibling of alpha.\n---\n\nB MUST stop.\n",
    )
    graph = _graph(tmp_path)
    hubs = [n for n in graph["nodes"] if n["is_hub"]]
    assert len(hubs) == 0


# ---------------------------------------------------------------------------
# Disconnected components
# ---------------------------------------------------------------------------

def test_disconnected_components_detected(tmp_path: Path) -> None:
    """Invariant: two groups with no edges between them are separate components.
    Mutation: skip component detection -> red."""
    _write_skill(tmp_path, "a1", "---\nname: a1\ndescription: A.\n---\n\nA MUST stop.\n")
    _write_skill(
        tmp_path, "a2",
        "---\nname: a2\ndescription: Sibling of a1.\n---\n\nB MUST stop.\n",
    )
    _write_skill(tmp_path, "b1", "---\nname: b1\ndescription: B.\n---\n\nC MUST stop.\n")
    _write_skill(
        tmp_path, "b2",
        "---\nname: b2\ndescription: Sibling of b1.\n---\n\nD MUST stop.\n",
    )
    graph = _graph(tmp_path)
    components = [p for p in graph["graph_properties"]
                 if p["property"] == "DISCONNECTED_COMPONENT"]
    assert len(components) >= 1


def test_connected_corpus_is_one_component(tmp_path: Path) -> None:
    """Invariant: a fully connected corpus has one component.
    Mutation: always report disconnected -> red."""
    _write_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n")
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Sibling of alpha.\n---\n\nB MUST stop.\n",
    )
    graph = _graph(tmp_path)
    disconnected = [p for p in graph["graph_properties"]
                   if p["property"] in ("DISCONNECTED_COMPONENT", "ISOLATED_SKILL")]
    assert len(disconnected) == 0


# ---------------------------------------------------------------------------
# Determinism and artifact integrity
# ---------------------------------------------------------------------------

def test_same_input_produces_identical_graph_digest(tmp_path: Path) -> None:
    """Invariant: the graph is deterministic. Mutation: inject nondeterminism -> red."""
    _write_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n")
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Sibling of alpha.\n---\n\nB MUST stop.\n",
    )
    first = _graph(tmp_path)
    second = _graph(tmp_path)
    assert first == second
    assert first["graph_digest"] == second["graph_digest"]
    assert first["graph_digest"].startswith("sha256:")


def test_graph_version_is_stamped(tmp_path: Path) -> None:
    """Invariant: the artifact carries a version. Mutation: remove GRAPH_VERSION -> red."""
    _write_skill(tmp_path, "v", "---\nname: v\ndescription: V.\n---\n\nV MUST stop.\n")
    graph = _graph(tmp_path)
    assert graph["graph_version"] == GRAPH_VERSION


def test_graph_rejects_wrong_schema_version() -> None:
    """Invariant: the graph builder must fail closed on incompatible input.
    Mutation: accept any schema_version -> red."""
    try:
        build_composition_graph({"schema_version": "wrong", "artifact_digest": "x", "skills": []})
    except ValueError as exc:
        assert "schema_version" in str(exc)
    else:
        raise AssertionError("wrong schema_version must be rejected")


def test_graph_includes_audit_digest_when_provided(tmp_path: Path) -> None:
    """Invariant: when an audit artifact is passed, its digest is in the graph.
    Mutation: drop the audit_digest field -> red."""
    from crucible.auditor import audit_corpus
    ir = compile_corpus(tmp_path / "_dummy") if (tmp_path / "_dummy").exists() else None
    _write_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n")
    ir = compile_corpus(tmp_path)
    audit = audit_corpus(ir)
    graph = build_composition_graph(ir, audit)
    assert graph["input_audit_digest"] == audit["audit_digest"]


def test_limitations_are_documented(tmp_path: Path) -> None:
    """Invariant: abstained checks are explicit, not silently passed.
    Mutation: remove the limitations list -> red."""
    _write_skill(tmp_path, "l", "---\nname: l\ndescription: L.\n---\n\nL MUST stop.\n")
    graph = _graph(tmp_path)
    assert len(graph["limitations"]) >= 3
    classes = {lim["check_class"] for lim in graph["limitations"]}
    assert "CONDITIONAL_CONTRADICTION" in classes
    assert "SEMANTIC_REDUNDANCY" in classes


def test_edges_carry_source_evidence(tmp_path: Path) -> None:
    """Invariant: every edge has source, target, edge_type, relation_type.
    Mutation: drop a field -> red."""
    _write_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n")
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Sibling of alpha.\n---\n\nB MUST stop.\n",
    )
    graph = _graph(tmp_path)
    for edge in graph["edges"]:
        assert edge["source"]
        assert edge["target"]
        assert edge["edge_type"]
        assert edge["relation_type"]
        assert "resolved" in edge
        assert "extraction_method" in edge


def test_relation_summary_matches_edges(tmp_path: Path) -> None:
    """Invariant: the summary is a faithful count of the edges.
    Mutation: hardcode the summary -> red."""
    _write_skill(tmp_path, "alpha", "---\nname: alpha\ndescription: A.\n---\n\nA MUST stop.\n")
    _write_skill(
        tmp_path, "beta",
        "---\nname: beta\ndescription: Sibling of alpha.\n---\n\nB MUST stop.\n",
    )
    graph = _graph(tmp_path)
    assert graph["relation_summary"]["total_edges"] == len(graph["edges"])
    for et, count in graph["relation_summary"]["by_edge_type"].items():
        actual = sum(1 for e in graph["edges"] if e["edge_type"] == et)
        assert actual == count


# ---------------------------------------------------------------------------
# Real corpus smoke test
# ---------------------------------------------------------------------------

REAL_CORPUS = Path("/home/labestiadevigia/.codex/skills")


def test_real_corpus_graph_is_deterministic() -> None:
    """Invariant: the real corpus produces a stable, reproducible graph.
    Mutation: nondeterministic ordering -> red."""
    if not REAL_CORPUS.is_dir():
        import pytest
        pytest.skip("real corpus not available")
    ir = compile_corpus(REAL_CORPUS)
    first = build_composition_graph(ir)
    second = build_composition_graph(ir)
    assert first == second
    assert first["graph_digest"].startswith("sha256:")
    # The real corpus has rich relation language in descriptions.
    assert first["relation_summary"]["total_edges"] > 50
    assert "SIBLING_OF" in first["relation_summary"]["by_edge_type"]
    # No broken edges in the real corpus (all targets resolve).
    assert first["relation_summary"]["broken"] == 0
