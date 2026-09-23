"""Typed composition graph for the skill corpus (L3).

Consumes the L1 Skill IR and extracts typed relation edges from both the
explicit section-heading relations (composes_with, delegates_to) and the
description text (sibling of, pairs with, composes with, member of the
family, companion to). Classifies edges into relation types (composition,
reinforcement, delegation) and detects graph-level properties (hubs,
disconnected components, asymmetric declarations).

The graph is deterministic: the same IR always produces the same edges and
the same ``graph_digest``. No floats, no LLM, no semantic similarity.
"""

from __future__ import annotations

import re
from typing import Any

from .ir import digest_payload

GRAPH_VERSION = "crucible-graph/v1"

# Trigger phrases in description text, mapped to edge types.
_DESCRIPTION_TRIGGERS: list[tuple[str, str]] = [
    (r"sibling of", "SIBLING_OF"),
    (r"pairs? with", "PAIRS_WITH"),
    (r"composes? with", "COMPOSES_WITH"),
    (r"member of the (?:family|set)", "FAMILY_OF"),
    (r"companion to", "COMPANION_TO"),
]

# Edge type → relation type classification.
_RELATION_TYPE: dict[str, str] = {
    "COMPOSES_WITH": "COMPOSITION",
    "PAIRS_WITH": "COMPOSITION",
    "COMPANION_TO": "COMPOSITION",
    "SIBLING_OF": "REINFORCEMENT",
    "FAMILY_OF": "REINFORCEMENT",
    "DELEGATES_TO": "DELEGATION",
}

# Edge types that are semantically symmetric (if A→B then B is a peer of A).
_SYMMETRIC_TYPES = {"SIBLING_OF", "FAMILY_OF"}

# Minimum incoming edges to qualify as a hub.
_HUB_THRESHOLD = 3

# Limitations: what L3 cannot detect with the current IR.
GRAPH_LIMITATIONS: list[dict[str, str]] = [
    {
        "check_class": "CONDITIONAL_CONTRADICTION",
        "reason": (
            "The IR does not extract conditions, exceptions, or normalized "
            "subjects for normative rules. Conditional contradiction requires "
            "semantic adjudication that is not deterministically available."
        ),
    },
    {
        "check_class": "SEMANTIC_REDUNDANCY",
        "reason": (
            "The IR does not normalize rule subjects or predicates. "
            "Redundancy is limited to exact-text overlap (L2) and graph "
            "co-occurrence, not semantic equivalence."
        ),
    },
    {
        "check_class": "PRODUCER_CONSUMER_TYPING",
        "reason": (
            "Edge direction reflects declaration, not a typed "
            "producer/consumer property. A 'composes with' edge means the "
            "source declares a relation to the target, not that the target "
            "produces a specific property the source consumes."
        ),
    },
]


def build_composition_graph(
    artifact: dict[str, Any],
    audit_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a typed composition graph from a compiled L1 artifact.

    If an L2 audit artifact is provided, its digest is included in the
    graph artifact for chain-of-custody. The audit artifact is not modified.
    """
    schema_version = artifact.get("schema_version")
    if schema_version != "skill-ir/v1":
        raise ValueError(
            f"expected schema_version skill-ir/v1, got {schema_version!r}"
        )
    if "artifact_digest" not in artifact:
        raise ValueError("input artifact is missing artifact_digest")
    skills = artifact.get("skills")
    if not isinstance(skills, list):
        raise ValueError("input artifact is missing the skills list")

    name_set = {skill["identity"]["name"] for skill in skills}
    edges = _extract_edges(skills, name_set)

    nodes = _build_nodes(skills, edges, name_set)
    properties = _detect_properties(nodes, edges, name_set)

    graph_artifact: dict[str, Any] = {
        "graph_version": GRAPH_VERSION,
        "input_ir_digest": artifact["artifact_digest"],
        "input_schema_version": schema_version,
        "edges": edges,
        "nodes": nodes,
        "relation_summary": _summarize_relations(edges),
        "graph_properties": properties,
        "limitations": GRAPH_LIMITATIONS,
    }
    if audit_artifact is not None:
        graph_artifact["input_audit_digest"] = audit_artifact.get("audit_digest", "")
    graph_artifact["graph_digest"] = digest_payload(graph_artifact)
    return graph_artifact


# ---------------------------------------------------------------------------
# Edge extraction
# ---------------------------------------------------------------------------

def _extract_edges(
    skills: list[dict[str, Any]], name_set: set[str]
) -> list[dict[str, Any]]:
    """Extract typed edges from L1 relations and description text."""
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for skill in skills:
        source_name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        desc = skill["metadata"].get("description", "")

        # L1 section-heading relations.
        for target in skill["relations"].get("composes_with", []):
            _add_edge(edges, seen, source_name, target, "COMPOSES_WITH",
                      source_path, "section-heading", None, name_set)
        for target in skill["relations"].get("delegates_to", []):
            _add_edge(edges, seen, source_name, target, "DELEGATES_TO",
                      source_path, "section-heading", None, name_set)

        # Description-text relations.
        for trigger_pat, edge_type in _DESCRIPTION_TRIGGERS:
            for match in re.finditer(trigger_pat, desc, re.IGNORECASE):
                segment = _extract_segment(desc, match.end())
                evidence = desc[match.start():match.start() + len(segment) + len(match.group())].strip()
                for target in _extract_targets(segment, edge_type, source_name, name_set):
                    _add_edge(edges, seen, source_name, target, edge_type,
                              source_path, "description", evidence, name_set)

    edges.sort(key=lambda e: (e["source"], e["target"], e["edge_type"]))
    return edges


def _extract_segment(desc: str, start: int) -> str:
    """Extract the text segment from after a trigger to the next boundary."""
    rest = desc[start:]
    boundary = re.search(r"[;—.]", rest)
    if boundary:
        return rest[:boundary.start()]
    return rest


_KEBAB_CASE = re.compile(r"[a-z][a-z0-9]+(?:-[a-z0-9]+)+")

# Minimum length for a potential unresolved skill name (avoids short phrases).
_MIN_NAME_LEN = 5


def _extract_targets(
    segment: str, edge_type: str, exclude: str, name_set: set[str]
) -> list[str]:
    """Extract potential skill name targets from a description segment.

    Two-pass extraction:
    1. Match known skill names from the name_set anywhere in the segment
       (high confidence, resolved edges).
    2. Extract kebab-case tokens (with hyphens) from the structural
       positions (after removing parenthetical context, from the start of
       each comma/and-separated part) for potential unresolved targets.

    This handles both hyphenated names (ghost-skill) and single-word names
    (alpha) that exist in the corpus, while avoiding false positives from
    common English words for unresolved targets.
    """
    targets: list[str] = []
    seen: set[str] = set()

    # Pass 1: match known skill names anywhere in the segment.
    for name in sorted(name_set, key=len, reverse=True):
        if name == exclude or name in seen:
            continue
        pattern = r"(?<![a-z0-9-])" + re.escape(name) + r"(?![a-z0-9-])"
        if re.search(pattern, segment, re.IGNORECASE):
            targets.append(name)
            seen.add(name)

    # Pass 2: extract kebab-case tokens from structural positions.
    for part in _get_structural_text(segment, edge_type):
        part = part.strip()
        m = _KEBAB_CASE.match(part)
        if m and len(m.group()) >= _MIN_NAME_LEN and m.group() != exclude and m.group() not in seen:
            targets.append(m.group())
            seen.add(m.group())

    return targets


def _get_structural_text(segment: str, edge_type: str) -> list[str]:
    """Return the structural parts of a segment for kebab-case extraction."""
    if edge_type == "FAMILY_OF":
        paren = re.search(r"\(([^)]+)\)", segment)
        if not paren:
            return []
        return [part.strip() for part in paren.group(1).split(",")]
    cleaned = re.sub(r"\([^)]*\)", "", segment)
    return re.split(r"\s+(?:and|,)\s+", cleaned)


def _add_edge(
    edges: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    source: str,
    target: str,
    edge_type: str,
    source_path: str,
    extraction_method: str,
    evidence: str | None,
    name_set: set[str],
) -> None:
    key = (source, target, edge_type)
    if key in seen:
        return
    seen.add(key)
    resolved = target in name_set
    edges.append({
        "source": source,
        "target": target,
        "edge_type": edge_type,
        "relation_type": _RELATION_TYPE.get(edge_type, "UNKNOWN"),
        "symmetric": edge_type in _SYMMETRIC_TYPES,
        "resolved": resolved,
        "extraction_method": extraction_method,
        "source_path": source_path,
        "evidence": evidence,
    })


# ---------------------------------------------------------------------------
# Node construction
# ---------------------------------------------------------------------------

def _build_nodes(
    skills: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    name_set: set[str],
) -> list[dict[str, Any]]:
    """Build node metadata with incoming/outgoing edge counts."""
    incoming: dict[str, int] = {name: 0 for name in name_set}
    outgoing: dict[str, int] = {name: 0 for name in name_set}
    for edge in edges:
        if edge["resolved"]:
            incoming[edge["target"]] = incoming.get(edge["target"], 0) + 1
        outgoing[edge["source"]] = outgoing.get(edge["source"], 0) + 1

    nodes: list[dict[str, Any]] = []
    for skill in sorted(skills, key=lambda s: s["identity"]["name"]):
        name = skill["identity"]["name"]
        nodes.append({
            "name": name,
            "source_path": skill["identity"]["source_path"],
            "incoming_edges": incoming.get(name, 0),
            "outgoing_edges": outgoing.get(name, 0),
            "is_hub": incoming.get(name, 0) >= _HUB_THRESHOLD,
        })
    return nodes


# ---------------------------------------------------------------------------
# Graph property detection
# ---------------------------------------------------------------------------

def _detect_properties(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    name_set: set[str],
) -> list[dict[str, Any]]:
    """Detect graph-level properties: hubs, broken edges, disconnected components."""
    properties: list[dict[str, Any]] = []

    # Hubs: skills with many incoming edges.
    for node in nodes:
        if node["is_hub"]:
            properties.append({
                "property": "HUB",
                "skill": node["name"],
                "evidence": f"{node['incoming_edges']} incoming edges (threshold {_HUB_THRESHOLD})",
                "epistemic_status": "OBSERVATION",
            })

    # Broken edges: unresolved targets.
    for edge in edges:
        if not edge["resolved"]:
            properties.append({
                "property": "BROKEN_EDGE",
                "skill": edge["source"],
                "evidence": (
                    f"{edge['edge_type']} target {edge['target']!r} does not "
                    f"match any skill name"
                ),
                "epistemic_status": "CONFIRMED",
            })

    # Disconnected components: groups with no edges to the rest.
    components = _find_components(edges, name_set)
    if len(components) > 1:
        for component in components:
            if len(component) == 1:
                properties.append({
                    "property": "ISOLATED_SKILL",
                    "skill": component[0],
                    "evidence": "skill has no resolved edges to any other skill",
                    "epistemic_status": "OBSERVATION",
                })
            else:
                properties.append({
                    "property": "DISCONNECTED_COMPONENT",
                    "skill": component[0],
                    "evidence": (
                        f"component of {len(component)} skills with no edges "
                        f"to the rest of the graph: {', '.join(component[:5])}"
                    ),
                    "epistemic_status": "OBSERVATION",
                })

    properties.sort(key=lambda p: (p["property"], p["skill"]))
    return properties


def _find_components(
    edges: list[dict[str, Any]], name_set: set[str]
) -> list[list[str]]:
    """Find connected components using union-find on resolved edges."""
    parent: dict[str, str] = {name: name for name in name_set}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for edge in edges:
        if edge["resolved"]:
            union(edge["source"], edge["target"])

    groups: dict[str, list[str]] = {}
    for name in name_set:
        root = find(name)
        groups.setdefault(root, []).append(name)

    components = [sorted(names) for names in groups.values()]
    components.sort()
    return components


# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------

def _summarize_relations(edges: list[dict[str, Any]]) -> dict[str, Any]:
    by_edge_type: dict[str, int] = {}
    by_relation_type: dict[str, int] = {}
    resolved = 0
    broken = 0
    for edge in edges:
        by_edge_type[edge["edge_type"]] = by_edge_type.get(edge["edge_type"], 0) + 1
        by_relation_type[edge["relation_type"]] = by_relation_type.get(edge["relation_type"], 0) + 1
        if edge["resolved"]:
            resolved += 1
        else:
            broken += 1
    return {
        "total_edges": len(edges),
        "resolved": resolved,
        "broken": broken,
        "by_edge_type": dict(sorted(by_edge_type.items())),
        "by_relation_type": dict(sorted(by_relation_type.items())),
    }
