"""Deterministic audit engine consuming the L1 Skill IR artifact.

The auditor is the authority for findings within its declared scope. It never
calls a model, never uses floating-point arithmetic, and never emits a finding
it cannot ground in the IR evidence. Checks that the current IR cannot support
are documented as explicit limitations rather than silently passed.
"""

from __future__ import annotations

from fractions import Fraction
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
        "check_class": "CHECK_WITHOUT_ORACLE",
        "reason": "The IR does not extract oracle_kind for checks.",
    },
    {
        "check_class": "CLAIM_WITHOUT_PROVENANCE",
        "reason": "The IR does not extract structured claims with numeric flags.",
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
    findings.extend(_check_semantic_redundancy(skills))
    findings.extend(_check_conditional_contradiction(skills))
    findings.extend(_check_scope_trigger_mismatch(skills))
    findings.extend(_check_description_body_gap(skills))

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


# Minimum Jaccard overlap (as a Fraction) for a SEMANTIC_REDUNDANCY candidate.
# 2/3 means two skills share at least 2/3 of their meaningful tokens.
_SEMANTIC_THRESHOLD = Fraction(2, 3)

# Stopwords excluded from token sets to avoid inflating overlap on
# common English words. This is a small deterministic list, not an NLP
# pipeline.
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "not", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "could", "should", "may", "might", "must",
    "shall", "to", "of", "in", "on", "at", "by", "for", "with", "from",
    "as", "into", "about", "than", "then", "so", "if", "but", "because",
    "while", "this", "that", "these", "those", "it", "its", "they",
    "them", "their", "we", "you", "he", "she", "his", "her", "our",
    "your", "which", "who", "whom", "what", "where", "when", "how",
    "why", "all", "any", "some", "no", "nor", "only", "own", "same",
    "such", "too", "very", "can", "just",
})


def _tokenize(text: str) -> frozenset[str]:
    """Extract a normalized token set from text for Jaccard comparison.

    Lowercases, strips non-alphanumeric, drops stopwords and single-char
    tokens. Returns a frozenset for deterministic ordering-independent
    comparison.
    """
    tokens: set[str] = set()
    for word in text.lower().split():
        # Strip surrounding punctuation but keep internal hyphens.
        cleaned = word.strip(".,;:!?\"'()[]{}<>/\\|`*_-#")
        if len(cleaned) < 2:
            continue
        if cleaned in _STOPWORDS:
            continue
        tokens.add(cleaned)
    return frozenset(tokens)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> Fraction:
    """Jaccard similarity as an exact Fraction (no floats)."""
    if not a and not b:
        return Fraction(1, 1)
    union = a | b
    if not union:
        return Fraction(0, 1)
    intersection = a & b
    return Fraction(len(intersection), len(union))


def _skill_token_set(skill: dict[str, Any]) -> frozenset[str]:
    """Build a token set from a skill's description + rule texts + check texts.

    This is the lexical fingerprint used for semantic redundancy
    comparison. It combines what the skill says it does (description),
    what it requires (rules), and how it verifies (checks).
    """
    parts: list[str] = []
    desc = skill.get("metadata", {}).get("description", "")
    if desc:
        parts.append(desc)
    for rule in skill.get("rules", []):
        parts.append(rule.get("text", ""))
    for check in skill.get("checks", []):
        parts.append(check.get("text", ""))
    combined = " ".join(parts)
    return _tokenize(combined)


def _check_semantic_redundancy(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Two skills whose lexical fingerprint overlaps above the threshold.

    This is the deterministic base for SEMANTIC_REDUNDANCY. It uses
    Jaccard token overlap (computed with fractions.Fraction, no floats)
    on the combined description + rules + checks text of each skill. A
    pair with overlap >= 2/3 is a CANDIDATE finding: the two skills may
    cover the same ground.

    The LLM confirmation layer (deferred) would take each candidate and
    ask the model whether the two skills are semantically redundant. The
    deterministic check produces the candidate; the LLM confirms or
    rejects. The LLM never enters the decision path alone.
    """
    if len(skills) < 2:
        return []

    # Precompute token sets for each skill.
    skill_tokens: list[tuple[str, str, frozenset[str]]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        path = skill["identity"]["source_path"]
        tokens = _skill_token_set(skill)
        # Skip skills with empty token sets (no extractable content).
        if tokens:
            skill_tokens.append((name, path, tokens))

    findings: list[dict[str, Any]] = []
    for i in range(len(skill_tokens)):
        for j in range(i + 1, len(skill_tokens)):
            name_i, path_i, tokens_i = skill_tokens[i]
            name_j, path_j, tokens_j = skill_tokens[j]
            overlap = _jaccard(tokens_i, tokens_j)
            if overlap < _SEMANTIC_THRESHOLD:
                continue
            # Report on the lexicographically smaller skill name.
            if name_i <= name_j:
                report_name, report_path = name_i, path_i
            else:
                report_name, report_path = name_j, path_j
            # Format the fraction as "numerator/denominator" (no float).
            overlap_str = f"{overlap.numerator}/{overlap.denominator}"
            findings.append(_finding(
                cls="SEMANTIC_REDUNDANCY",
                epistemic_status="CANDIDATE",
                skill=report_name,
                source_path=report_path,
                source_span=None,
                rule_id=None,
                evidence=(
                    f"lexical Jaccard overlap {overlap_str} with "
                    f"{name_j if report_name == name_i else name_i} "
                    f"(threshold 2/3); combined description+rules+checks "
                    f"tokens are highly similar"
                ),
                violated_invariant=None,
                limitation=(
                    "lexical token overlap is not semantic equivalence; "
                    "two skills may share vocabulary while governing "
                    "different scopes; an LLM confirmation layer is "
                    "deferred and would confirm or reject each candidate"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# CONDITIONAL_CONTRADICTION
# ---------------------------------------------------------------------------

# Modalities and their polarity: positive = "do X", negative = "don't do X".
_POSITIVE_MODALITIES = frozenset({"MUST", "SHOULD"})
_NEGATIVE_MODALITIES = frozenset({"MUST_NOT", "SHOULD_NOT"})


def _rule_polarity(modality: str) -> str:
    """Return the base polarity of a rule: 'positive' or 'negative'."""
    if modality in _POSITIVE_MODALITIES:
        return "positive"
    if modality in _NEGATIVE_MODALITIES:
        return "negative"
    return "neutral"


def _conditions_overlap(cond_a: str, cond_b: str) -> bool:
    """Check if two condition texts overlap.

    Two conditions overlap if one is a substring of the other (after
    normalization). This is conservative: "read-only operations" and
    "read-only" overlap; "read-only" and "write-only" do not.
    """
    if cond_a == cond_b:
        return True
    # Substring check in both directions.
    if cond_a in cond_b or cond_b in cond_a:
        return True
    # Token overlap: if they share all tokens of the shorter one.
    tokens_a = set(cond_a.split())
    tokens_b = set(cond_b.split())
    if not tokens_a or not tokens_b:
        return False
    shorter = tokens_a if len(tokens_a) <= len(tokens_b) else tokens_b
    longer = tokens_b if shorter is tokens_a else tokens_a
    return shorter.issubset(longer)


def _effective_polarity(rule: dict[str, Any], condition_text: str) -> str | None:
    """Compute the effective polarity of a rule under a specific condition.

    Returns 'positive', 'negative', or None if the rule does not apply
    under the given condition.

    - If the rule has no conditions, it applies unconditionally with its
      base polarity.
    - If the rule has a scope condition matching the given condition, it
      applies with its base polarity.
    - If the rule has an exception condition matching the given
      condition, it applies with inverted polarity (the exception makes
      the rule NOT apply, which means the opposite guidance holds).
    - If the rule has conditions but none match, it does not apply
      under the given condition (returns None).
    """
    base = _rule_polarity(rule["modality"])
    conditions = rule.get("conditions", [])
    if not conditions:
        return base

    # Check if any condition matches.
    for cond in conditions:
        if not _conditions_overlap(cond["text"], condition_text):
            continue
        if cond["type"] == "exception":
            # Exception inverts the polarity for this condition.
            return "negative" if base == "positive" else "positive"
        if cond["type"] == "scope":
            # Scope restricts the rule to this condition.
            return base
    # The rule has conditions but none match — it does not apply.
    return None


def _check_conditional_contradiction(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Two rules with the same subject, overlapping conditions, but
    opposite effective polarity under those conditions.

    This is the subtle sibling of NORMATIVE_CONFLICT. NORMATIVE_CONFLICT
    catches unconditional contradictions (MUST vs MUST_NOT on the same
    subject). CONDITIONAL_CONTRADICTION catches conditional ones: two
    rules that seem compatible in general but conflict under a specific
    condition.

    Example:
      Rule A: "Retries MUST be bounded, except for read-only operations"
        -> under "read-only operations": negative (not bounded)
      Rule B: "Retries MUST be bounded for read-only operations"
        -> under "read-only operations": positive (bounded)
      -> CONDITIONAL_CONTRADICTION on "read-only operations"
    """
    # Collect all rules with subjects and conditions across all skills.
    all_rules: list[tuple[str, dict[str, Any], str]] = []
    for skill in skills:
        skill_name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill["rules"]:
            subject = rule.get("subject", "")
            if not subject:
                continue
            all_rules.append((skill_name, rule, source_path))

    findings: list[dict[str, Any]] = []
    for i in range(len(all_rules)):
        for j in range(i + 1, len(all_rules)):
            skill_i, rule_i, path_i = all_rules[i]
            skill_j, rule_j, path_j = all_rules[j]
            # Must be same subject.
            if rule_i["subject"] != rule_j["subject"]:
                continue
            # Skip if NORMATIVE_CONFLICT already catches this
            # (unconditional opposite modality).
            pair = (rule_i["modality"], rule_j["modality"])
            if pair in _CONFLICT_PAIRS:
                continue
            # Both rules must have at least one condition.
            conds_i = rule_i.get("conditions", [])
            conds_j = rule_j.get("conditions", [])
            if not conds_i and not conds_j:
                continue
            # Collect all condition texts from both rules.
            all_cond_texts: set[str] = set()
            for c in conds_i:
                all_cond_texts.add(c["text"])
            for c in conds_j:
                all_cond_texts.add(c["text"])
            # Also include conditions from one rule when the other has
            # no conditions (the unconditional rule applies everywhere).
            if not conds_i or not conds_j:
                # One rule is unconditional. Check if the conditional
                # rule's polarity under its own condition conflicts with
                # the unconditional rule's base polarity.
                if not conds_i:
                    # Rule i is unconditional, rule j is conditional.
                    base_i = _rule_polarity(rule_i["modality"])
                    for cond_text in all_cond_texts:
                        eff_j = _effective_polarity(rule_j, cond_text)
                        if eff_j is not None and eff_j != base_i:
                            # Report on the lexicographically smaller skill.
                            if skill_i <= skill_j:
                                r_name, r_path, r_rule = skill_i, path_i, rule_i
                                other = skill_j
                            else:
                                r_name, r_path, r_rule = skill_j, path_j, rule_j
                                other = skill_i
                            findings.append(_finding(
                                cls="CONDITIONAL_CONTRADICTION",
                                epistemic_status="CONFIRMED",
                                skill=r_name,
                                source_path=r_path,
                                source_span=r_rule["source_span"],
                                rule_id=r_rule["id"],
                                evidence=(
                                    f"subject {rule_i['subject']!r} conflicts "
                                    f"under condition {cond_text!r}: "
                                    f"{rule_i['modality']} in {skill_i} vs "
                                    f"{rule_j['modality']} in {skill_j} "
                                    f"(rule {rule_j['id']})"
                                ),
                                violated_invariant=(
                                    "two rules governing the same subject "
                                    "must not prescribe opposite guidance "
                                    "under the same condition"
                                ),
                                limitation=(
                                    "condition extraction is pattern-based "
                                    "(except for, when, unless, if, for, "
                                    "during, while); semantic condition "
                                    "matching is not supported"
                                ),
                            ))
                            break  # one conflict per pair is enough
                    continue
            # Both rules have conditions. Check each condition for
            # conflicting polarity.
            for cond_text in sorted(all_cond_texts):
                eff_i = _effective_polarity(rule_i, cond_text)
                eff_j = _effective_polarity(rule_j, cond_text)
                if eff_i is None or eff_j is None:
                    continue
                if eff_i == eff_j:
                    continue
                # Conflict found under this condition.
                if skill_i <= skill_j:
                    r_name, r_path, r_rule = skill_i, path_i, rule_i
                    other = skill_j
                else:
                    r_name, r_path, r_rule = skill_j, path_j, rule_j
                    other = skill_i
                findings.append(_finding(
                    cls="CONDITIONAL_CONTRADICTION",
                    epistemic_status="CONFIRMED",
                    skill=r_name,
                    source_path=r_path,
                    source_span=r_rule["source_span"],
                    rule_id=r_rule["id"],
                    evidence=(
                        f"subject {rule_i['subject']!r} conflicts "
                        f"under condition {cond_text!r}: "
                        f"{rule_i['modality']} in {skill_i} vs "
                        f"{rule_j['modality']} in {skill_j} "
                        f"(rule {rule_j['id']})"
                    ),
                    violated_invariant=(
                        "two rules governing the same subject "
                        "must not prescribe opposite guidance "
                        "under the same condition"
                    ),
                    limitation=(
                        "condition extraction is pattern-based "
                        "(except for, when, unless, if, for, "
                        "during, while); semantic condition "
                        "matching is not supported"
                    ),
                ))
                break  # one conflict per pair is enough
    return findings


# ---------------------------------------------------------------------------
# SCOPE_TRIGGER_MISMATCH
# ---------------------------------------------------------------------------

def _check_scope_trigger_mismatch(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """The declared trigger (from the description) shares zero meaningful
    tokens with the rule content (from the body).

    This is the conservative base for SCOPE_TRIGGER_MISMATCH. It extracts
    the trigger clause from the description ("Use this skill whenever
    X"), tokenizes it, and compares to the combined tokens of all rule
    texts. If both token sets are non-empty and their intersection is
    empty, the skill's declared scope and its actual normative content
    are lexically disjoint — a CANDIDATE finding.

    The check uses the same tokenizer and stopword list as
    SEMANTIC_REDUNDANCY for consistency.

    Limitation: lexical disjointness is not semantic disjointness. The
    trigger and rules may use different vocabulary for the same domain
    (e.g., "debugging" in the trigger and "retries" in the rules could
    be related). The finding is CANDIDATE, not CONFIRMED.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        trigger = skill.get("trigger", {})
        if not trigger.get("found"):
            continue
        trigger_text = trigger.get("text", "")
        if not trigger_text:
            continue
        trigger_tokens = _tokenize(trigger_text)
        if not trigger_tokens:
            continue
        # Build rule text token set from all rules.
        rule_parts: list[str] = []
        for rule in skill.get("rules", []):
            rule_parts.append(rule.get("text", ""))
        if not rule_parts:
            continue
        rule_tokens = _tokenize(" ".join(rule_parts))
        if not rule_tokens:
            continue
        # Check for zero overlap.
        intersection = trigger_tokens & rule_tokens
        if intersection:
            continue
        # Zero overlap — CANDIDATE finding.
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        # Find the first rule for source evidence.
        first_rule = skill["rules"][0] if skill.get("rules") else None
        findings.append(_finding(
            cls="SCOPE_TRIGGER_MISMATCH",
            epistemic_status="CANDIDATE",
            skill=name,
            source_path=source_path,
            source_span=first_rule["source_span"] if first_rule else None,
            rule_id=first_rule["id"] if first_rule else None,
            evidence=(
                f"trigger tokens {sorted(trigger_tokens)[:5]}... share zero "
                f"meaningful tokens with rule tokens "
                f"{sorted(rule_tokens)[:5]}...; the declared activation "
                f"scope and the normative content are lexically disjoint"
            ),
            violated_invariant=(
                "a skill's declared trigger should share vocabulary with "
                "its normative content; zero overlap suggests the trigger "
                "describes a different domain than the rules"
            ),
            limitation=(
                "lexical token disjointness is not semantic disjointness; "
                "the trigger and rules may use different vocabulary for "
                "the same domain; an LLM confirmation layer is deferred"
            ),
        ))
    return findings


# ---------------------------------------------------------------------------
# DESCRIPTION_BODY_GAP
# ---------------------------------------------------------------------------

# Minimum number of meaningful tokens in the description for it to be
# considered "substantive" (i.e., the skill promises something real).
_DESC_MIN_TOKENS = 10


def _check_description_body_gap(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A skill with a substantive description but zero extractable rules,
    checks, and procedural steps.

    This is the most extreme form of description-body gap: the description
    promises something, but the body has no extractable normative
    structure at all. The skill says what it does but the body has no
    MUST/SHOULD rules, no checks, and no procedural steps.

    The check is CANDIDATE, not CONFIRMED, because the L1 extractor is
    lexical and conservative: a skill with zero extracted rules may use
    non-RFC-2119 normative language (e.g., "always", "never", "ensure")
    that the extractor does not capture. The finding documents this
    limitation.

    This is distinct from METHODOLOGICAL_VACUITY, which detects skills
    WITH rules but WITHOUT steps or checks. DESCRIPTION_BODY_GAP detects
    skills WITHOUT any extractable structure at all.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        desc = skill.get("metadata", {}).get("description", "")
        desc_tokens = _tokenize(desc)
        if len(desc_tokens) < _DESC_MIN_TOKENS:
            continue
        rules = skill.get("rules", [])
        checks = skill.get("checks", [])
        steps = skill.get("procedural_steps", [])
        if rules or checks or steps:
            continue
        # No extractable structure despite a substantive description.
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        findings.append(_finding(
            cls="DESCRIPTION_BODY_GAP",
            epistemic_status="CANDIDATE",
            skill=name,
            source_path=source_path,
            source_span=None,
            rule_id=None,
            evidence=(
                f"description has {len(desc_tokens)} meaningful tokens "
                f"but body has 0 rules, 0 checks, 0 procedural steps; "
                f"the description promises something the body does not "
                f"deliver in extractable normative structure"
            ),
            violated_invariant=(
                "a skill's description should be backed by normative "
                "content (rules, checks, or procedural steps) in the body"
            ),
            limitation=(
                "the L1 extractor is lexical and conservative; a skill "
                "with zero extracted rules may use non-RFC-2119 normative "
                "language (e.g., always, never, ensure) that the "
                "extractor does not capture; cannot distinguish "
                "extractor scope from a real description-body gap"
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
