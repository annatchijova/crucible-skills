"""Deterministic audit engine consuming the L1 Skill IR artifact.

The auditor is the authority for findings within its declared scope. It never
calls a model, never uses floating-point arithmetic, and never emits a finding
it cannot ground in the IR evidence. Checks that the current IR cannot support
are documented as explicit limitations rather than silently passed.
"""

from __future__ import annotations

from typing import Any

from .ir import SCHEMA_VERSION, digest_payload

AUDIT_VERSION = "crucible-audit/v1"

# Modality pairs that constitute a direct contradiction for the same subject.
_CONFLICT_PAIRS = frozenset({
    ("MUST", "MUST_NOT"),
    ("MUST_NOT", "MUST"),
    ("SHOULD", "SHOULD_NOT"),
    ("SHOULD_NOT", "SHOULD"),
})

# Checks the current IR cannot support, with the reason each is abstained.
# These are emitted in every artifact so consumers know what was NOT assessed.
AUDIT_LIMITATIONS: list[dict[str, str]] = [
    {
        "check_class": "DESCRIPTION_BODY_GAP",
        "reason": (
            "The L1 extractor is lexical and conservative; a skill with zero "
            "extracted rules/checks may use non-RFC-2119 normative language. "
            "Cannot distinguish extractor scope from a real description-body gap."
        ),
    },
    {
        "check_class": "CHECK_WITHOUT_ORACLE",
        "reason": "The IR does not extract oracle_kind for checks.",
    },
    {
        "check_class": "CLAIM_WITHOUT_PROVENANCE",
        "reason": "The IR does not extract structured claims with numeric flags.",
    },
    {
        "check_class": "SCOPE_TRIGGER_MISMATCH",
        "reason": "The IR does not extract declared triggers or scope inclusions/exclusions.",
    },
    {
        "check_class": "CONDITIONAL_CONTRADICTION",
        "reason": (
            "The IR extracts rule subjects but not conditions or exceptions; "
            "cannot determine whether two rules with the same subject can both "
            "be active simultaneously."
        ),
    },
]


def audit_corpus(artifact: dict[str, Any]) -> dict[str, Any]:
    """Audit a compiled L1 artifact and return a sealed AuditArtifact.

    The input must be a dictionary produced by
    :func:`crucible.compiler.compile_corpus`. The output is deterministic:
    the same input always produces the same findings and the same
    ``audit_digest``.
    """
    schema_version = artifact.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"expected schema_version {SCHEMA_VERSION}, got {schema_version!r}"
        )
    if "artifact_digest" not in artifact:
        raise ValueError("input artifact is missing artifact_digest")
    skills = artifact.get("skills")
    if not isinstance(skills, list):
        raise ValueError("input artifact is missing the skills list")

    name_set = {skill["identity"]["name"] for skill in skills}

    findings: list[dict[str, Any]] = []
    findings.extend(_check_broken_references(skills, name_set))
    findings.extend(_check_self_composition(skills))
    findings.extend(_check_composition_cycles(skills, name_set))
    findings.extend(_check_orphan_skills(skills, name_set))
    findings.extend(_check_requirement_without_check(skills))
    findings.extend(_check_structural_redundancy(skills))
    findings.extend(_check_methodological_vacuity(skills))
    findings.extend(_check_normative_conflict(skills))

    findings.sort(key=_finding_sort_key)
    for index, finding in enumerate(findings):
        finding["id"] = f"finding-{index + 1:04d}"

    audit_artifact: dict[str, Any] = {
        "audit_version": AUDIT_VERSION,
        "input_artifact_digest": artifact["artifact_digest"],
        "input_schema_version": schema_version,
        "findings": findings,
        "summary": _summarize(findings),
        "limitations": AUDIT_LIMITATIONS,
    }
    audit_artifact["audit_digest"] = digest_payload(audit_artifact)
    return audit_artifact


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_broken_references(
    skills: list[dict[str, Any]], name_set: set[str]
) -> list[dict[str, Any]]:
    """Relation targets that do not resolve to an existing skill name."""
    findings: list[dict[str, Any]] = []
    for skill in skills:
        skill_name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for relation_key in ("composes_with", "delegates_to"):
            for target in skill["relations"].get(relation_key, []):
                if target not in name_set:
                    findings.append(_finding(
                        cls="BROKEN_REFERENCE",
                        epistemic_status="CONFIRMED",
                        skill=skill_name,
                        source_path=source_path,
                        source_span=None,
                        rule_id=None,
                        evidence=(
                            f"{relation_key} target {target!r} does not match "
                            f"any skill name in the corpus"
                        ),
                        violated_invariant=(
                            "composition and delegation references must resolve "
                            "to existing skills"
                        ),
                        limitation=(
                            "relation source spans are not preserved in the "
                            "current IR; the finding locates the skill, not the "
                            "exact relation line"
                        ),
                    ))
    return findings


def _check_self_composition(skills: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A skill that composes with or delegates to itself."""
    findings: list[dict[str, Any]] = []
    for skill in skills:
        skill_name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for relation_key in ("composes_with", "delegates_to"):
            for target in skill["relations"].get(relation_key, []):
                if target == skill_name:
                    findings.append(_finding(
                        cls="SELF_COMPOSITION",
                        epistemic_status="CONFIRMED",
                        skill=skill_name,
                        source_path=source_path,
                        source_span=None,
                        rule_id=None,
                        evidence=(
                            f"{relation_key} target {target!r} is the skill itself"
                        ),
                        violated_invariant=(
                            "a skill must not declare a composition or delegation "
                            "edge to itself"
                        ),
                        limitation=None,
                    ))
    return findings


def _check_composition_cycles(
    skills: list[dict[str, Any]], name_set: set[str]
) -> list[dict[str, Any]]:
    """Cycles of length > 1 in the composition/delegation graph.

    Only edges whose target resolves to an existing skill are considered;
    broken references are reported separately by ``_check_broken_references``.
    """
    edges: dict[str, list[str]] = {}
    for skill in skills:
        skill_name = skill["identity"]["name"]
        targets: list[str] = []
        for relation_key in ("composes_with", "delegates_to"):
            for target in skill["relations"].get(relation_key, []):
                if target in name_set and target != skill_name:
                    targets.append(target)
        if targets:
            edges[skill_name] = sorted(set(targets))

    cycles = _find_cycles(edges)
    findings: list[dict[str, Any]] = []
    skill_by_name = {s["identity"]["name"]: s for s in skills}
    for cycle in cycles:
        start_name = cycle[0]
        skill = skill_by_name[start_name]
        findings.append(_finding(
            cls="COMPOSITION_CYCLE",
            epistemic_status="CONFIRMED",
            skill=start_name,
            source_path=skill["identity"]["source_path"],
            source_span=None,
            rule_id=None,
            evidence=f"cycle detected: {' -> '.join(cycle)} -> {cycle[0]}",
            violated_invariant=(
                "composition and delegation graphs must be acyclic"
            ),
            limitation=None,
        ))
    return findings


def _check_orphan_skills(
    skills: list[dict[str, Any]], name_set: set[str]
) -> list[dict[str, Any]]:
    """Skills disconnected from the relation graph.

    Only emitted when the corpus has at least one relation edge; an empty
    graph makes every skill trivially disconnected, which is not an
    interesting observation.
    """
    has_any_edge = False
    for skill in skills:
        for relation_key in ("composes_with", "delegates_to"):
            if skill["relations"].get(relation_key):
                has_any_edge = True
                break
        if has_any_edge:
            break
    if not has_any_edge:
        return []

    connected: set[str] = set()
    for skill in skills:
        skill_name = skill["identity"]["name"]
        for relation_key in ("composes_with", "delegates_to"):
            for target in skill["relations"].get(relation_key, []):
                if target in name_set:
                    connected.add(skill_name)
                    connected.add(target)

    findings: list[dict[str, Any]] = []
    for skill in sorted(skills, key=lambda s: s["identity"]["name"]):
        skill_name = skill["identity"]["name"]
        if skill_name not in connected:
            findings.append(_finding(
                cls="ORPHAN_SKILL",
                epistemic_status="OBSERVATION",
                skill=skill_name,
                source_path=skill["identity"]["source_path"],
                source_span=None,
                rule_id=None,
                evidence=(
                    "skill has no incoming or outgoing composition/delegation "
                    "edges in a corpus that has a relation graph"
                ),
                violated_invariant=None,
                limitation=(
                    "ORPHAN_SKILL is a corpus-level observation, not a defect; "
                    "a standalone skill may be intentionally independent"
                ),
            ))
    return findings


def _check_requirement_without_check(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A skill with normative rules but zero extracted checks."""
    findings: list[dict[str, Any]] = []
    for skill in skills:
        rules = skill["rules"]
        checks = skill["checks"]
        if not rules or checks:
            continue
        normative = [r for r in rules if r["modality"] in ("MUST", "SHOULD")]
        if not normative:
            continue
        first_rule = normative[0]
        findings.append(_finding(
            cls="REQUIREMENT_WITHOUT_CHECK",
            epistemic_status="CANDIDATE",
            skill=skill["identity"]["name"],
            source_path=skill["identity"]["source_path"],
            source_span=first_rule["source_span"],
            rule_id=first_rule["id"],
            evidence=(
                f"skill has {len(normative)} MUST/SHOULD rule(s) but "
                f"0 extracted checks"
            ),
            violated_invariant=(
                "normative rules should have an identifiable verification path"
            ),
            limitation=(
                "the IR does not link checks to specific rules; this is a "
                "coarse skill-level heuristic, not a per-rule coverage claim"
            ),
        ))
    return findings


def _check_structural_redundancy(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Exact duplicate rule text appearing in more than one skill."""
    text_to_skills: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for skill in skills:
        for rule in skill["rules"]:
            text_to_skills.setdefault(rule["text"], []).append(
                (skill["identity"]["name"], rule)
            )

    findings: list[dict[str, Any]] = []
    for text in sorted(text_to_skills):
        occurrences = text_to_skills[text]
        if len(occurrences) < 2:
            continue
        skill_names = sorted({name for name, _ in occurrences})
        first_skill, first_rule = occurrences[0]
        findings.append(_finding(
            cls="STRUCTURAL_REDUNDANCY",
            epistemic_status="CANDIDATE",
            skill=first_skill,
            source_path=next(
                s["identity"]["source_path"]
                for s in skills
                if s["identity"]["name"] == first_skill
            ),
            source_span=first_rule["source_span"],
            rule_id=first_rule["id"],
            evidence=(
                f"identical rule text appears in {len(skill_names)} skill(s): "
                f"{', '.join(skill_names)}"
            ),
            violated_invariant=None,
            limitation=(
                "exact-text duplication is a coarse lexical signal; the rules "
                "may govern different scopes or compose rather than duplicate"
            ),
        ))
    return findings


def _check_methodological_vacuity(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A skill with normative rules but zero procedural steps and zero checks.

    This detects skills that say what to do (MUST/SHOULD) but never say how
    (no steps, no procedure, no verification). The skill is methodologically
    vacuous: it is a wish, not a method.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        rules = skill["rules"]
        if not rules:
            continue
        normative = [
            r for r in rules
            if r["modality"] in ("MUST", "SHOULD", "MUST_NOT", "SHOULD_NOT")
        ]
        if not normative:
            continue
        steps = skill.get("procedural_steps", [])
        checks = skill["checks"]
        if steps or checks:
            continue
        first_rule = normative[0]
        findings.append(_finding(
            cls="METHODOLOGICAL_VACUITY",
            epistemic_status="CANDIDATE",
            skill=skill["identity"]["name"],
            source_path=skill["identity"]["source_path"],
            source_span=first_rule["source_span"],
            rule_id=first_rule["id"],
            evidence=(
                f"skill has {len(normative)} normative rule(s) but "
                f"0 procedural steps and 0 checks"
            ),
            violated_invariant=(
                "a methodology skill should specify how to verify or "
                "execute its normative rules, not just what to require"
            ),
            limitation=(
                "procedural step extraction is section-heading and "
                "numbered-list based; a skill with embedded procedural "
                "prose (no ## Steps section, no numbered list) will be "
                "a false positive"
            ),
        ))
    return findings


def _check_normative_conflict(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Two rules with the same subject but contradictory modalities.

    A conflict is: same normalized subject, one rule says MUST and another
    says MUST_NOT (or SHOULD vs SHOULD_NOT). This detects both within-skill
    and cross-skill contradictions.
    """
    # Group rules by subject: subject -> list of (skill_name, rule, source_path)
    by_subject: dict[str, list[tuple[str, dict[str, Any], str]]] = {}
    for skill in skills:
        skill_name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill["rules"]:
            subject = rule.get("subject", "")
            if not subject:
                continue
            by_subject.setdefault(subject, []).append(
                (skill_name, rule, source_path)
            )

    findings: list[dict[str, Any]] = []
    for subject in sorted(by_subject):
        entries = by_subject[subject]
        # Check all pairs for conflicting modalities.
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                skill_i, rule_i, path_i = entries[i]
                skill_j, rule_j, path_j = entries[j]
                pair = (rule_i["modality"], rule_j["modality"])
                if pair not in _CONFLICT_PAIRS:
                    continue
                # Report on the first rule of the pair (deterministic order).
                findings.append(_finding(
                    cls="NORMATIVE_CONFLICT",
                    epistemic_status="CONFIRMED",
                    skill=skill_i,
                    source_path=path_i,
                    source_span=rule_i["source_span"],
                    rule_id=rule_i["id"],
                    evidence=(
                        f"subject {subject!r} has conflicting modalities: "
                        f"{rule_i['modality']} in {skill_i} vs "
                        f"{rule_j['modality']} in {skill_j} "
                        f"(rule {rule_j['id']})"
                    ),
                    violated_invariant=(
                        "two rules governing the same subject must not "
                        "prescribe contradictory modalities"
                    ),
                    limitation=(
                        "subject extraction is lexical (noun phrase before "
                        "the modal verb); two rules with different surface "
                        "forms but the same semantic subject will not be "
                        "detected as conflicting"
                    ),
                ))
    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _finding(
    cls: str,
    epistemic_status: str,
    skill: str | None,
    source_path: str | None,
    source_span: dict[str, int] | None,
    rule_id: str | None,
    evidence: str,
    violated_invariant: str | None,
    limitation: str | None,
) -> dict[str, Any]:
    return {
        "id": "",  # assigned after sorting
        "class": cls,
        "epistemic_status": epistemic_status,
        "skill": skill,
        "source_path": source_path,
        "source_span": source_span,
        "rule_id": rule_id,
        "evidence": evidence,
        "violated_invariant": violated_invariant,
        "limitation": limitation,
    }


def _finding_sort_key(finding: dict[str, Any]) -> tuple:
    span = finding["source_span"]
    return (
        finding["class"],
        finding["skill"] or "",
        span["line"] if span else 0,
        span["column"] if span else 0,
        finding["rule_id"] or "",
        finding["evidence"],
    )


def _summarize(findings: list[dict[str, Any]]) -> dict[str, Any]:
    by_class: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for finding in findings:
        by_class[finding["class"]] = by_class.get(finding["class"], 0) + 1
        by_status[finding["epistemic_status"]] = by_status.get(finding["epistemic_status"], 0) + 1
    return {
        "total": len(findings),
        "by_class": dict(sorted(by_class.items())),
        "by_epistemic_status": dict(sorted(by_status.items())),
    }


def _find_cycles(edges: dict[str, list[str]]) -> list[list[str]]:
    """Return the lexicographically smallest representative of each cycle.

    Uses Tarjan's strongly-connected-components algorithm. Each SCC with
    more than one node is a cycle. Self-loops are excluded here (handled by
    ``_check_self_composition``).
    """
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(node: str) -> None:
        indices[node] = index_counter[0]
        lowlinks[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack.add(node)

        for successor in edges.get(node, []):
            if successor not in indices:
                strongconnect(successor)
                lowlinks[node] = min(lowlinks[node], lowlinks[successor])
            elif successor in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[successor])

        if lowlinks[node] == indices[node]:
            component: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == node:
                    break
            sccs.append(component)

    for node in sorted(edges):
        if node not in indices:
            strongconnect(node)

    cycles: list[list[str]] = []
    for component in sccs:
        if len(component) < 2:
            continue
        component_sorted = sorted(component)
        cycles.append(component_sorted)
    cycles.sort()
    return cycles
