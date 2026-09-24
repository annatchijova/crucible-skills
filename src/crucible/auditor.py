"""Deterministic audit engine consuming the L1 Skill IR artifact.

The auditor is the authority for findings within its declared scope. It never
calls a model, never uses floating-point arithmetic, and never emits a finding
it cannot ground in the IR evidence. Checks that the current IR cannot support
are documented as explicit limitations rather than silently passed.
"""

from __future__ import annotations

import re
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
AUDIT_LIMITATIONS: list[dict[str, str]] = []


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
    findings.extend(_check_without_oracle(skills))
    findings.extend(_check_claim_without_provenance(skills))
    findings.extend(_check_unbounded_retry(skills))
    findings.extend(_check_llm_in_decision_path(skills))
    findings.extend(_check_overclaim(skills))
    findings.extend(_check_missing_failure_mode(skills))
    findings.extend(_check_non_deterministic(skills))
    findings.extend(_check_irreversible_without_review(skills))
    findings.extend(_check_secret_in_output(skills))
    findings.extend(_check_silent_failure(skills))
    findings.extend(_check_hardcoded_credential(skills))
    findings.extend(_check_unbounded_resource(skills))
    findings.extend(_check_unvalidated_external_input(skills))
    findings.extend(_check_missing_timeout(skills))
    findings.extend(_check_floating_point_in_decision_path(skills))
    findings.extend(_check_unpinned_dependency(skills))

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
        # All extracted rules are normative except MAY, which is
        # permissive ("you may do this") rather than a requirement.
        normative = [r for r in rules if r["modality"] != "MAY"]
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
                f"skill has {len(normative)} normative rule(s) but "
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

    This detects skills that say what to do (normative rules in any style:
    RFC-2119 modals, always/never starters, or imperative constraint verbs)
    but never say how (no steps, no procedure, no verification). The skill
    is methodologically vacuous: it is a wish, not a method.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        rules = skill["rules"]
        if not rules:
            continue
        # All extracted rules are normative except MAY, which is
        # permissive. The modality distinguishes the style (MUST, NEVER,
        # ALWAYS, IMPERATIVE, etc.) but all express a normative constraint.
        normative = [r for r in rules if r["modality"] != "MAY"]
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
                "procedural step extraction is pattern-based (section "
                "headings, numbered lists, and action-verb bullets); a "
                "skill with embedded procedural prose that does not "
                "match these patterns will be a false positive"
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
# Style-agnostic: covers RFC-2119 modals, absoluteness starters, and
# imperative constraint verbs.
_POSITIVE_MODALITIES = frozenset({"MUST", "SHOULD", "ALWAYS", "IMPERATIVE"})
_NEGATIVE_MODALITIES = frozenset({"MUST_NOT", "SHOULD_NOT", "NEVER"})


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
    normative rules (RFC-2119 modals, always/never starters, or
    imperative constraint verbs), no checks, and no procedural steps.

    The check is CANDIDATE, not CONFIRMED, because the L1 extractor is
    lexical and conservative: a skill with zero extracted rules may use
    normative language in a form the extractor does not yet recognize.
    The finding documents this limitation.

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
                "with zero extracted rules may use normative language in "
                "a form the extractor does not yet recognize; cannot "
                "distinguish extractor scope from a real description-body "
                "gap"
            ),
        ))
    return findings


# ---------------------------------------------------------------------------
# CHECK_WITHOUT_ORACLE
# ---------------------------------------------------------------------------

def _check_without_oracle(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A check whose oracle_kind is "unknown" — the check text has no
    extractable indicator of how to verify it.

    The IR now extracts oracle_kind for each check:
    - "question"  — the check is a question (ends with ?)
    - "checkbox"  — the check is a checkbox item ([ ] or [x])
    - "command"   — the check contains a verification verb (verify,
                    assert, run, check, confirm, test, query, inspect,
                    does, ensure, prove, validate, demonstrate)
    - "unknown"   — none of the above

    A check with oracle_kind "unknown" is a CANDIDATE finding: the
    check text does not indicate how to verify it. It may be a
    descriptive statement, a classification, or a rule disguised as a
    check — none of which are verifiable oracles.

    Limitation: the oracle_kind extraction is pattern-based. A check
    may be verifiable through domain-specific means not captured by
    the patterns. The finding is CANDIDATE, not CONFIRMED.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        for check in skill.get("checks", []):
            oracle_kind = check.get("oracle_kind", "unknown")
            if oracle_kind != "unknown":
                continue
            name = skill["identity"]["name"]
            source_path = skill["identity"]["source_path"]
            findings.append(_finding(
                cls="CHECK_WITHOUT_ORACLE",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=check["source_span"],
                rule_id=check["id"],
                evidence=(
                    f"check {check['id']} has oracle_kind 'unknown'; "
                    f"the check text does not contain a question mark, "
                    f"a checkbox marker, or a verification verb (verify, "
                    f"assert, run, check, confirm, test, query, inspect, "
                    f"does, ensure, prove, validate, demonstrate)"
                ),
                violated_invariant=(
                    "a check should indicate how to verify it — through "
                    "a question, a checkbox, or a verification command"
                ),
                limitation=(
                    "oracle_kind extraction is pattern-based; a check "
                    "may be verifiable through domain-specific means "
                    "not captured by the patterns; the finding is "
                    "CANDIDATE, not CONFIRMED"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# CLAIM_WITHOUT_PROVENANCE
# ---------------------------------------------------------------------------

def _check_claim_without_provenance(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A normative rule that makes a factual claim (numeric value or
    standards reference) without provenance.

    The IR now extracts claims from each rule. A claim is a factual
    assertion with a numeric value (percentage, time, count, year) or
    a standards reference (NIST, OWASP, CWE, CVE, MITRE, ISO, RFC, W3C,
    WCAG, WCA). Each claim records whether the rule text contains a
    provenance indicator.

    A claim without provenance is a CANDIDATE finding: the rule makes a
    factual assertion but does not cite a source. The claim may be
    common knowledge, derived from the skill's domain expertise, or
    stated without evidence — the check cannot distinguish.

    Limitation: provenance detection is pattern-based. A claim may have
    provenance in a form not captured by the patterns (e.g., "as stated
    in the documentation", "per the team's experience"). The finding is
    CANDIDATE, not CONFIRMED.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        for rule in skill.get("rules", []):
            claims = rule.get("claims", [])
            if not claims:
                continue
            unprovenanced = [c for c in claims if not c["has_provenance"]]
            if not unprovenanced:
                continue
            name = skill["identity"]["name"]
            source_path = skill["identity"]["source_path"]
            claim_descs = [f"{c['kind']} '{c['text']}'" for c in unprovenanced]
            findings.append(_finding(
                cls="CLAIM_WITHOUT_PROVENANCE",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} makes claim(s) "
                    f"{', '.join(claim_descs)} without provenance; "
                    f"the rule text does not contain a source citation, "
                    f"URL, standards reference, or provenance indicator"
                ),
                violated_invariant=(
                    "a normative rule that makes a factual claim should "
                    "cite its source so the claim can be verified"
                ),
                limitation=(
                    "provenance detection is pattern-based; a claim may "
                    "have provenance in a form not captured by the "
                    "patterns (e.g., 'as stated in the documentation'); "
                    "the finding is CANDIDATE, not CONFIRMED"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# UNBOUNDED_RETRY
# ---------------------------------------------------------------------------

# Patterns that indicate a retry/repeat instruction without an explicit bound.
_RETRY_PATTERNS = [
    re.compile(r"\bretry\b", re.IGNORECASE),
    re.compile(r"\brepeat\b", re.IGNORECASE),
    re.compile(r"\buntil\s+success\b", re.IGNORECASE),
    re.compile(r"\bkeep\s+trying\b", re.IGNORECASE),
    re.compile(r"\btry\s+again\b", re.IGNORECASE),
    re.compile(r"\bloop\s+until\b", re.IGNORECASE),
]

# Patterns that indicate an explicit bound on retries.
_RETRY_BOUND_PATTERNS = [
    re.compile(r"\b(?:max(?:imum)?|at\s+most|limit(?:ed)?\s+to)\s+\d+", re.IGNORECASE),
    re.compile(r"\b\d+\s*(?:times|attempts|retries|iterations)\b", re.IGNORECASE),
    re.compile(r"\btimeout\b", re.IGNORECASE),
    re.compile(r"\bbackoff\b", re.IGNORECASE),
    re.compile(r"\bcircuit\s+breaker\b", re.IGNORECASE),
    re.compile(r"\bbounded\b", re.IGNORECASE),
    re.compile(r"\bfinite\b", re.IGNORECASE),
    re.compile(r"\bbudget\b", re.IGNORECASE),
    re.compile(r"\blimit\b", re.IGNORECASE),
    re.compile(r"\bidempotent\b", re.IGNORECASE),
]


def _check_unbounded_retry(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or procedural step that instructs retry/repeat without a bound.

    This detects the flagship composition hazard from the README: a skill that
    says "retry until success" without specifying a maximum number of
    attempts, a timeout, a backoff, or a circuit breaker. Unbounded retry on
    irreversible or non-idempotent operations is a methodology defect.

    The check scans rule text and procedural step text for retry indicators.
    If any retry indicator is found and no bound indicator is present in the
    same text, the finding is CANDIDATE.

    Limitation: the check is pattern-based. A skill may describe a bounded
    retry using vocabulary not captured by the patterns (e.g., "exponential
    delay", "rate limit"). The finding is CANDIDATE, not CONFIRMED.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        # Check rules.
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            if not _has_unbounded_retry(text):
                continue
            findings.append(_finding(
                cls="UNBOUNDED_RETRY",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} contains a retry/repeat indicator "
                    f"without an explicit bound (max attempts, timeout, "
                    f"backoff, or circuit breaker)"
                ),
                violated_invariant=(
                    "a retry or repeat instruction must specify a bound "
                    "(maximum attempts, timeout, backoff, or circuit breaker)"
                ),
                limitation=(
                    "retry and bound detection are pattern-based; a skill "
                    "may describe a bounded retry using vocabulary not "
                    "captured by the patterns; the finding is CANDIDATE"
                ),
            ))
        # Check procedural steps.
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            if not _has_unbounded_retry(text):
                continue
            findings.append(_finding(
                cls="UNBOUNDED_RETRY",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} contains a retry/repeat indicator "
                    f"without an explicit bound (max attempts, timeout, "
                    f"backoff, or circuit breaker)"
                ),
                violated_invariant=(
                    "a retry or repeat instruction must specify a bound "
                    "(maximum attempts, timeout, backoff, or circuit breaker)"
                ),
                limitation=(
                    "retry and bound detection are pattern-based; a skill "
                    "may describe a bounded retry using vocabulary not "
                    "captured by the patterns; the finding is CANDIDATE"
                ),
            ))
    return findings


def _has_unbounded_retry(text: str) -> bool:
    """True if text contains a retry indicator but no bound indicator."""
    has_retry = any(p.search(text) for p in _RETRY_PATTERNS)
    if not has_retry:
        return False
    has_bound = any(p.search(text) for p in _RETRY_BOUND_PATTERNS)
    return not has_bound


# ---------------------------------------------------------------------------
# LLM_IN_DECISION_PATH
# ---------------------------------------------------------------------------

# Patterns that indicate an LLM/model is being used for a consequential decision.
_LLM_DECISION_PATTERNS = [
    re.compile(r"\b(?:LLM|model|AI|GPT|Claude|Gemini|Nemotron|Llama)\b.*\b(?:decide|judge|classify|score|verify|approve|evaluate|assess|determine|rule|adjudicate)\b", re.IGNORECASE),
    re.compile(r"\b(?:decide|judge|classify|score|verify|approve|evaluate|assess|determine|rule|adjudicate)\b.*\b(?:LLM|model|AI|GPT|Claude|Gemini|Nemotron|Llama)\b", re.IGNORECASE),
    re.compile(r"\bask\s+(?:the\s+)?(?:model|LLM|AI)\s+to\b", re.IGNORECASE),
    re.compile(r"\blet\s+(?:the\s+)?(?:model|LLM|AI)\b", re.IGNORECASE),
    re.compile(r"\buse\s+(?:the\s+)?(?:model|LLM|AI)\s+to\b", re.IGNORECASE),
]

# Patterns that indicate a deterministic fallback or guard is present.
_DETERMINISTIC_GUARD_PATTERNS = [
    re.compile(r"\bdeterministic\b", re.IGNORECASE),
    re.compile(r"\b(?:sealed|sealed\s+result)\b", re.IGNORECASE),
    re.compile(r"\b(?:verifier|verify\s+independently|independent\s+verif)\b", re.IGNORECASE),
    re.compile(r"\b(?:fallback|guard|gate|check|assert)\b", re.IGNORECASE),
    re.compile(r"\b(?:must\s+not\s+(?:change|alter|modify|influence))\b", re.IGNORECASE),
    re.compile(r"\b(?:out\s+of\s+(?:the\s+)?decision\s+path)\b", re.IGNORECASE),
]


def _check_llm_in_decision_path(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule that instructs using an LLM/model for a consequential decision
    without a deterministic guard.

    This detects a core engineering anti-pattern: letting a language model
    produce a verdict, score, classification, or approval without a
    deterministic fallback or independent verification. The LLM can read
    evidence correctly and still reach the wrong conclusion under narrative
    pressure.

    The check scans rule text for patterns that place an LLM in a
    consequential decision role. If a deterministic guard pattern is present
    in the same rule, the finding is suppressed.

    Limitation: the check is pattern-based. A skill may describe an LLM
    decision using vocabulary not captured by the patterns, or may have a
    deterministic guard expressed differently. The finding is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_llm_decision = any(p.search(text) for p in _LLM_DECISION_PATTERNS)
            if not has_llm_decision:
                continue
            has_guard = any(p.search(text) for p in _DETERMINISTIC_GUARD_PATTERNS)
            if has_guard:
                continue
            findings.append(_finding(
                cls="LLM_IN_DECISION_PATH",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} instructs using an LLM/model for a "
                    f"consequential decision without a deterministic guard, "
                    f"fallback, or independent verification"
                ),
                violated_invariant=(
                    "an LLM must not be the sole authority for a consequential "
                    "decision (verdict, score, classification, approval); a "
                    "deterministic guard or independent verifier must be present"
                ),
                limitation=(
                    "LLM-decision and guard detection are pattern-based; a "
                    "skill may describe an LLM decision or guard using "
                    "vocabulary not captured by the patterns; the finding is "
                    "CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# OVERCLAIM
# ---------------------------------------------------------------------------

# Absolute claims that cannot be guaranteed without qualification.
_OVERCLAIM_PATTERNS = [
    re.compile(r"\balways\b", re.IGNORECASE),
    re.compile(r"\bnever\b(?!\s+fail)", re.IGNORECASE),
    re.compile(r"\b100\s*%\b", re.IGNORECASE),
    re.compile(r"\bguaranteed?\b", re.IGNORECASE),
    re.compile(r"\bfailsafe\b", re.IGNORECASE),
    re.compile(r"\bbulletproof\b", re.IGNORECASE),
    re.compile(r"\binfallible\b", re.IGNORECASE),
    re.compile(r"\bperfect\b", re.IGNORECASE),
    re.compile(r"\bimpossible\s+to\s+(?:fail|break|breach)\b", re.IGNORECASE),
]

# Qualification patterns that soften an absolute claim.
_QUALIFICATION_PATTERNS = [
    re.compile(r"\b(?:may|might|can|could|should|typically|usually|generally|in\s+most\s+cases|under\s+normal\s+conditions)\b", re.IGNORECASE),
    re.compile(r"\b(?:except|unless|when|if|for\s+most|best\s+effort)\b", re.IGNORECASE),
]


def _check_overclaim(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule that makes an absolute claim without qualification.

    This detects methodology overclaiming: a rule that says "always",
    "never", "100%", "guaranteed", "failsafe", or "bulletproof" without
    any qualification (may, might, typically, except, unless, etc.).
    Absolute claims in methodology are a defect because no method is
    universally correct -- there are always boundary conditions,
    failure modes, and exceptions.

    The check scans rule text for absolute claim patterns. If a
    qualification pattern is present in the same rule, the finding is
    suppressed.

    Style-agnostic note: when a rule's modality is ALWAYS or NEVER, the
    "always"/"never" at the start of the rule IS the modality (a
    normative instruction like "Always validate inputs"), not a
    descriptive overclaim. The "always" and "never" patterns are skipped
    for those rules; the other overclaim patterns (100%, guaranteed,
    failsafe, bulletproof, etc.) still apply.

    Limitation: the check is pattern-based. A skill may make an absolute
    claim using vocabulary not captured by the patterns, or may qualify
    it differently. The finding is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            modality = rule.get("modality", "")
            # For ALWAYS/NEVER rules, "always"/"never" is the modality,
            # not a descriptive overclaim. Skip those patterns but keep
            # the rest (100%, guaranteed, failsafe, etc.).
            if modality in ("ALWAYS", "NEVER"):
                patterns = [
                    p for p in _OVERCLAIM_PATTERNS
                    if not p.search("always") and not p.search("never")
                ]
            else:
                patterns = _OVERCLAIM_PATTERNS
            has_overclaim = any(p.search(text) for p in patterns)
            if not has_overclaim:
                continue
            has_qualification = any(p.search(text) for p in _QUALIFICATION_PATTERNS)
            if has_qualification:
                continue
            # Identify which pattern matched for evidence.
            matched = next(
                p.pattern for p in patterns if p.search(text)
            )
            findings.append(_finding(
                cls="OVERCLAIM",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} makes an absolute claim "
                    f"(matched: {matched}) without qualification "
                    f"(may, might, typically, except, unless, etc.)"
                ),
                violated_invariant=(
                    "a methodology rule must not make an absolute claim "
                    "without qualification; every method has boundary "
                    "conditions and failure modes"
                ),
                limitation=(
                    "absolute-claim and qualification detection are "
                    "pattern-based; a skill may make an absolute claim "
                    "or qualify it using vocabulary not captured by the "
                    "patterns; the finding is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# MISSING_FAILURE_MODE
# ---------------------------------------------------------------------------

# Patterns that indicate failure handling is mentioned.
_FAILURE_MODE_PATTERNS = [
    re.compile(r"\bfail(?:ed|ure)?\b", re.IGNORECASE),
    re.compile(r"\berror\b", re.IGNORECASE),
    re.compile(r"\bexception\b", re.IGNORECASE),
    re.compile(r"\bfallback\b", re.IGNORECASE),
    re.compile(r"\brecover(?:y)?\b", re.IGNORECASE),
    re.compile(r"\brollback\b", re.IGNORECASE),
    re.compile(r"\babort\b", re.IGNORECASE),
    re.compile(r"\btimeout\b", re.IGNORECASE),
    re.compile(r"\bdegrad(?:e|ation)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+happens\s+if\b", re.IGNORECASE),
    re.compile(r"\bif\s+(?:it|this|the)\s+(?:fails?|errors?)\b", re.IGNORECASE),
]


def _check_missing_failure_mode(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A skill with normative rules and procedural steps but zero mention
    of failure, error, exception, fallback, or recovery.

    This detects a methodology that says what to do but never says what
    happens when it goes wrong. A method without a failure mode is a wish:
    it assumes success and has no plan for deviation. This is distinct
    from METHODOLOGICAL_VACUITY (rules but no steps) and
    REQUIREMENT_WITHOUT_CHECK (rules but no checks).

    The check fires when a skill has at least one normative rule AND at
    least one procedural step AND none of the rule texts, step texts, or
    body text mention any failure-mode indicator.

    Limitation: the check is pattern-based. A skill may describe failure
    handling using vocabulary not captured by the patterns. The finding
    is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        rules = skill.get("rules", [])
        steps = skill.get("procedural_steps", [])
        if not rules or not steps:
            continue
        # Combine all text from rules, steps, and body.
        all_texts: list[str] = [rule.get("text", "") for rule in rules]
        all_texts.extend(step.get("text", "") for step in steps)
        all_texts.append(skill.get("body_text", ""))
        combined = " ".join(all_texts)
        has_failure_mode = any(p.search(combined) for p in _FAILURE_MODE_PATTERNS)
        if has_failure_mode:
            continue
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        first_rule = rules[0]
        findings.append(_finding(
            cls="MISSING_FAILURE_MODE",
            epistemic_status="CANDIDATE",
            skill=name,
            source_path=source_path,
            source_span=first_rule["source_span"],
            rule_id=first_rule["id"],
            evidence=(
                f"skill has {len(rules)} rule(s) and {len(steps)} step(s) "
                f"but no mention of failure, error, exception, fallback, "
                f"recovery, rollback, abort, timeout, or degradation"
            ),
            violated_invariant=(
                "a methodology with normative rules and procedural steps "
                "must specify what happens on failure; a method without a "
                "failure mode assumes success and has no plan for deviation"
            ),
            limitation=(
                "failure-mode detection is pattern-based; a skill may "
                "describe failure handling using vocabulary not captured "
                "by the patterns; the finding is CANDIDATE"
            ),
        ))
    return findings


# ---------------------------------------------------------------------------
# NON_DETERMINISTIC_INSTRUCTION
# ---------------------------------------------------------------------------

# Patterns that indicate a non-deterministic instruction.
_NON_DETERMINISTIC_PATTERNS = [
    re.compile(r"\brandom(?:ly)?\b", re.IGNORECASE),
    re.compile(r"\barbitrary\b", re.IGNORECASE),
    re.compile(r"\bpick\s+(?:any|one|a)\b", re.IGNORECASE),
    re.compile(r"\bchoose\s+(?:any|one|a)\b", re.IGNORECASE),
    re.compile(r"\bany\s+(?:order|way|approach|method)\b", re.IGNORECASE),
]

# Patterns that indicate a deterministic anchor (seed, fixed, pinned, etc.).
_DETERMINISTIC_ANCHOR_PATTERNS = [
    re.compile(r"\bseed\b", re.IGNORECASE),
    re.compile(r"\bfixed\b", re.IGNORECASE),
    re.compile(r"\bpinned\b", re.IGNORECASE),
    re.compile(r"\bdeterministic\b", re.IGNORECASE),
    re.compile(r"\breproducib(?:le|ility)\b", re.IGNORECASE),
    re.compile(r"\bsame\s+(?:input|result|output)\b", re.IGNORECASE),
]


def _check_non_deterministic(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or procedural step that introduces non-determinism without a
    deterministic anchor.

    This detects a methodology defect: instructing the agent to use
    "random", "arbitrary", "pick any", or "choose any" without specifying
    a seed, a fixed procedure, or a reproducibility guarantee. Non-
    deterministic instructions in a methodology break reproducibility: the
    same input may produce different outputs across runs.

    The check scans rule text and procedural step text for non-determinism
    indicators. If a deterministic anchor pattern is present in the same
    text, the finding is suppressed.

    Limitation: the check is pattern-based. A skill may introduce non-
    determinism using vocabulary not captured by the patterns, or may
    anchor determinism differently. The finding is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_non_det = any(p.search(text) for p in _NON_DETERMINISTIC_PATTERNS)
            if not has_non_det:
                continue
            has_anchor = any(p.search(text) for p in _DETERMINISTIC_ANCHOR_PATTERNS)
            if has_anchor:
                continue
            findings.append(_finding(
                cls="NON_DETERMINISTIC_INSTRUCTION",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} introduces non-determinism "
                    f"(random, arbitrary, pick any) without a deterministic "
                    f"anchor (seed, fixed, pinned, reproducible)"
                ),
                violated_invariant=(
                    "a methodology instruction must not introduce non-"
                    "determinism without a deterministic anchor; the same "
                    "input must produce the same output"
                ),
                limitation=(
                    "non-determinism and anchor detection are pattern-based; "
                    "a skill may introduce non-determinism or anchor it "
                    "using vocabulary not captured by the patterns; the "
                    "finding is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_non_det = any(p.search(text) for p in _NON_DETERMINISTIC_PATTERNS)
            if not has_non_det:
                continue
            has_anchor = any(p.search(text) for p in _DETERMINISTIC_ANCHOR_PATTERNS)
            if has_anchor:
                continue
            findings.append(_finding(
                cls="NON_DETERMINISTIC_INSTRUCTION",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} introduces non-determinism "
                    f"(random, arbitrary, pick any) without a deterministic "
                    f"anchor (seed, fixed, pinned, reproducible)"
                ),
                violated_invariant=(
                    "a methodology instruction must not introduce non-"
                    "determinism without a deterministic anchor; the same "
                    "input must produce the same output"
                ),
                limitation=(
                    "non-determinism and anchor detection are pattern-based; "
                    "a skill may introduce non-determinism or anchor it "
                    "using vocabulary not captured by the patterns; the "
                    "finding is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# IRREVERSIBLE_WITHOUT_REVIEW
# ---------------------------------------------------------------------------

# Patterns that indicate an irreversible action.
_IRREVERSIBLE_PATTERNS = [
    re.compile(r"\bdelete\b", re.IGNORECASE),
    re.compile(r"\bdrop\b", re.IGNORECASE),
    re.compile(r"\bdestroy\b", re.IGNORECASE),
    re.compile(r"\bforce(?:[- ])?push\b", re.IGNORECASE),
    re.compile(r"\bforce[- ]?reset\b", re.IGNORECASE),
    re.compile(r"\btruncate\b", re.IGNORECASE),
    re.compile(r"\bremove\b", re.IGNORECASE),
    re.compile(r"\bpurge\b", re.IGNORECASE),
    re.compile(r"\bwipe\b", re.IGNORECASE),
    re.compile(r"\boverwrite\b", re.IGNORECASE),
]

# Patterns that indicate a review, confirmation, or bound on irreversible actions.
_REVIEW_BOUND_PATTERNS = [
    re.compile(r"\breview\b", re.IGNORECASE),
    re.compile(r"\bconfirm(?:ation)?\b", re.IGNORECASE),
    re.compile(r"\bapprove(?:d)?\b", re.IGNORECASE),
    re.compile(r"\bbackup\b", re.IGNORECASE),
    re.compile(r"\bsnapshot\b", re.IGNORECASE),
    re.compile(r"\bbounded\b", re.IGNORECASE),
    re.compile(r"\bidempotent\b", re.IGNORECASE),
    re.compile(r"\breversib(?:le|ility)\b", re.IGNORECASE),
    re.compile(r"\bundo\b", re.IGNORECASE),
    re.compile(r"\brollback\b", re.IGNORECASE),
    re.compile(r"\bcheckpoint\b", re.IGNORECASE),
]


def _check_irreversible_without_review(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or procedural step that mentions an irreversible action
    without a review, confirmation, backup, or reversibility bound.

    This detects a methodology defect: instructing the agent to delete,
    drop, destroy, force-push, truncate, purge, or wipe without mentioning
    review, confirmation, backup, idempotency, or rollback. Irreversible
    actions without bounds are dangerous because they cannot be undone
    if the instruction was wrong or the context changed.

    The check scans rule text and procedural step text for irreversible
    action indicators. If a review/bound pattern is present in the same
    text, the finding is suppressed.

    Limitation: the check is pattern-based. A skill may describe an
    irreversible action or its bounds using vocabulary not captured by the
    patterns. The finding is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_irreversible = any(p.search(text) for p in _IRREVERSIBLE_PATTERNS)
            if not has_irreversible:
                continue
            has_review = any(p.search(text) for p in _REVIEW_BOUND_PATTERNS)
            if has_review:
                continue
            findings.append(_finding(
                cls="IRREVERSIBLE_WITHOUT_REVIEW",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} mentions an irreversible action "
                    f"(delete, drop, destroy, force-push, truncate, purge, "
                    f"wipe) without a review bound (review, confirm, backup, "
                    f"idempotent, rollback)"
                ),
                violated_invariant=(
                    "an irreversible action must be bounded by review, "
                    "confirmation, backup, idempotency, or rollback; an "
                    "unbounded irreversible action cannot be undone"
                ),
                limitation=(
                    "irreversible-action and review-bound detection are "
                    "pattern-based; a skill may describe an irreversible "
                    "action or its bounds using vocabulary not captured "
                    "by the patterns; the finding is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_irreversible = any(p.search(text) for p in _IRREVERSIBLE_PATTERNS)
            if not has_irreversible:
                continue
            has_review = any(p.search(text) for p in _REVIEW_BOUND_PATTERNS)
            if has_review:
                continue
            findings.append(_finding(
                cls="IRREVERSIBLE_WITHOUT_REVIEW",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} mentions an irreversible action "
                    f"(delete, drop, destroy, force-push, truncate, purge, "
                    f"wipe) without a review bound (review, confirm, backup, "
                    f"idempotent, rollback)"
                ),
                violated_invariant=(
                    "an irreversible action must be bounded by review, "
                    "confirmation, backup, idempotency, or rollback; an "
                    "unbounded irreversible action cannot be undone"
                ),
                limitation=(
                    "irreversible-action and review-bound detection are "
                    "pattern-based; a skill may describe an irreversible "
                    "action or its bounds using vocabulary not captured "
                    "by the patterns; the finding is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# SECRET_IN_OUTPUT
# ---------------------------------------------------------------------------

# Patterns that indicate a secret is being sent to an output channel.
_SECRET_IN_OUTPUT_PATTERNS = [
    re.compile(
        r"\b(log|print|echo|console\.log|stdout|stderr|output|display|show|"
        r"expose|reveal|return|include)\b"
        r".*\b(secret|password|token|api\s*key|credential|private\s*key|"
        r"access\s*key|session\s*key)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(secret|password|token|api\s*key|credential|private\s*key|"
        r"access\s*key|session\s*key)\b"
        r".*\b(log|print|echo|console\.log|stdout|stderr|output|display|"
        r"show|expose|reveal|return|include)\b",
        re.IGNORECASE,
    ),
]

# Patterns that indicate the secret is protected (redacted, masked, hashed).
_SECRET_PROTECTION_PATTERNS = [
    re.compile(r"\bredact(?:ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\bmask(?:ed)?\b", re.IGNORECASE),
    re.compile(r"\bhash(?:ed)?\b", re.IGNORECASE),
    re.compile(r"\bencrypt(?:ed)?\b", re.IGNORECASE),
    re.compile(r"\bdo\s+not\s+(?:log|print|output|echo)\b", re.IGNORECASE),
    re.compile(r"\bnever\s+(?:log|print|output|echo)\b", re.IGNORECASE),
    re.compile(r"\bavoid\s+(?:log|print|output|echo)ging\b", re.IGNORECASE),
    re.compile(r"\bscrub(?:bed)?\b", re.IGNORECASE),
    re.compile(r"\bsanitiz(?:e|ed)\b", re.IGNORECASE),
]


def _check_secret_in_output(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or step that instructs sending a secret to an output channel
    (log, print, echo, stdout, display) without protection (redact, mask,
    hash, encrypt).

    Leaking secrets to logs or output is a universal security defect: it
    exposes credentials to anyone with access to the output channel. No
    methodology considers this correct.

    Limitation: pattern-based. A skill may describe secret output or
    protection using vocabulary not captured by the patterns. The finding
    is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_leak = any(p.search(text) for p in _SECRET_IN_OUTPUT_PATTERNS)
            if not has_leak:
                continue
            has_protection = any(
                p.search(text) for p in _SECRET_PROTECTION_PATTERNS
            )
            if has_protection:
                continue
            findings.append(_finding(
                cls="SECRET_IN_OUTPUT",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} instructs sending a secret to an "
                    f"output channel (log, print, echo, stdout) without "
                    f"protection (redact, mask, hash, encrypt)"
                ),
                violated_invariant=(
                    "a secret must not be sent to an output channel without "
                    "redaction, masking, hashing, or encryption; leaked "
                    "credentials are exposed to anyone with output access"
                ),
                limitation=(
                    "secret-output and protection detection are pattern-"
                    "based; a skill may describe secret output or protection "
                    "using vocabulary not captured by the patterns; the "
                    "finding is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_leak = any(p.search(text) for p in _SECRET_IN_OUTPUT_PATTERNS)
            if not has_leak:
                continue
            has_protection = any(
                p.search(text) for p in _SECRET_PROTECTION_PATTERNS
            )
            if has_protection:
                continue
            findings.append(_finding(
                cls="SECRET_IN_OUTPUT",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} instructs sending a secret to an "
                    f"output channel (log, print, echo, stdout) without "
                    f"protection (redact, mask, hash, encrypt)"
                ),
                violated_invariant=(
                    "a secret must not be sent to an output channel without "
                    "redaction, masking, hashing, or encryption; leaked "
                    "credentials are exposed to anyone with output access"
                ),
                limitation=(
                    "secret-output and protection detection are pattern-"
                    "based; a skill may describe secret output or protection "
                    "using vocabulary not captured by the patterns; the "
                    "finding is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# SILENT_FAILURE
# ---------------------------------------------------------------------------

# Patterns that indicate an error is being silently suppressed.
_SILENT_FAILURE_PATTERNS = [
    re.compile(r"\bignore\s+(?:the\s+)?error\b", re.IGNORECASE),
    re.compile(r"\bignore\s+(?:the\s+)?exception\b", re.IGNORECASE),
    re.compile(r"\bswallow\s+(?:the\s+)?error\b", re.IGNORECASE),
    re.compile(r"\bswallow\s+(?:the\s+)?exception\b", re.IGNORECASE),
    re.compile(r"\bsuppress\s+(?:the\s+)?error\b", re.IGNORECASE),
    re.compile(r"\bsuppress\s+(?:the\s+)?exception\b", re.IGNORECASE),
    re.compile(r"\bcatch\s+and\s+continue\b", re.IGNORECASE),
    re.compile(r"\bon\s+error\s+resume\s+next\b", re.IGNORECASE),
    re.compile(r"\bsilently\s+(?:ignore|continue|proceed|succeed)\b", re.IGNORECASE),
    re.compile(r"\bcontinue\s+on\s+error\b", re.IGNORECASE),
    re.compile(r"\bpass\s+on\s+error\b", re.IGNORECASE),
]

# Patterns that indicate the error is actually handled (logged, raised, etc.)
_ERROR_HANDLING_PATTERNS = [
    re.compile(r"\blog\b", re.IGNORECASE),
    re.compile(r"\breport\b", re.IGNORECASE),
    re.compile(r"\braise\b", re.IGNORECASE),
    re.compile(r"\bthrow\b", re.IGNORECASE),
    re.compile(r"\babort\b", re.IGNORECASE),
    re.compile(r"\bfail\b", re.IGNORECASE),
    re.compile(r"\bnotify\b", re.IGNORECASE),
    re.compile(r"\balert\b", re.IGNORECASE),
    re.compile(r"\bhandle\b", re.IGNORECASE),
    re.compile(r"\bretry\b", re.IGNORECASE),
]


def _check_silent_failure(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or step that instructs suppressing an error silently (ignore,
    swallow, suppress, catch and continue) without logging, reporting, or
    handling.

    Silent failures are a universal engineering defect: the system
    continues as if nothing went wrong, hiding the root cause and making
    debugging impossible. A crash is better than a silent corruption.

    Limitation: pattern-based. A skill may describe silent failure or
    error handling using vocabulary not captured by the patterns. The
    finding is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_silent = any(p.search(text) for p in _SILENT_FAILURE_PATTERNS)
            if not has_silent:
                continue
            has_handling = any(
                p.search(text) for p in _ERROR_HANDLING_PATTERNS
            )
            if has_handling:
                continue
            findings.append(_finding(
                cls="SILENT_FAILURE",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} instructs suppressing an error "
                    f"silently (ignore, swallow, suppress, catch and "
                    f"continue) without handling (log, report, raise, "
                    f"abort, retry)"
                ),
                violated_invariant=(
                    "an error must not be silently suppressed; a silent "
                    "failure hides the root cause and makes debugging "
                    "impossible; a crash is better than a silent corruption"
                ),
                limitation=(
                    "silent-failure and error-handling detection are "
                    "pattern-based; a skill may describe suppression or "
                    "handling using vocabulary not captured by the "
                    "patterns; the finding is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_silent = any(p.search(text) for p in _SILENT_FAILURE_PATTERNS)
            if not has_silent:
                continue
            has_handling = any(
                p.search(text) for p in _ERROR_HANDLING_PATTERNS
            )
            if has_handling:
                continue
            findings.append(_finding(
                cls="SILENT_FAILURE",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} instructs suppressing an error "
                    f"silently (ignore, swallow, suppress, catch and "
                    f"continue) without handling (log, report, raise, "
                    f"abort, retry)"
                ),
                violated_invariant=(
                    "an error must not be silently suppressed; a silent "
                    "failure hides the root cause and makes debugging "
                    "impossible; a crash is better than a silent corruption"
                ),
                limitation=(
                    "silent-failure and error-handling detection are "
                    "pattern-based; a skill may describe suppression or "
                    "handling using vocabulary not captured by the "
                    "patterns; the finding is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# HARDCODED_CREDENTIAL
# ---------------------------------------------------------------------------

# Patterns that indicate a credential is being hardcoded.
_HARDCODED_CREDENTIAL_PATTERNS = [
    re.compile(
        r"\b(hardcode|hard-?code|embed|inline)\b"
        r".*\b(secret|password|token|api\s*key|credential|private\s*key)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(put|set|store|write|place)\b"
        r".*\b(secret|password|token|api\s*key|credential|private\s*key)\b"
        r".*\b(in\s+the\s+code|in\s+source\s+code|in\s+the\s+config|"
        r"in\s+the\s+script|directly)\b",
        re.IGNORECASE,
    ),
]

# Patterns that indicate the credential is stored securely.
_SECURE_CREDENTIAL_PATTERNS = [
    re.compile(r"\benvironment\s+variable\b", re.IGNORECASE),
    re.compile(r"\bsecret\s+manager\b", re.IGNORECASE),
    re.compile(r"\bvault\b", re.IGNORECASE),
    re.compile(r"\bkey\s+management\s+service\b", re.IGNORECASE),
    re.compile(r"\bKMS\b"),
    re.compile(r"\bdo\s+not\s+hardcode\b", re.IGNORECASE),
    re.compile(r"\bnever\s+hardcode\b", re.IGNORECASE),
    re.compile(r"\bavoid\s+hardcoding\b", re.IGNORECASE),
    re.compile(r"\b\.env\b"),
]


def _check_hardcoded_credential(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or step that instructs hardcoding a credential (secret,
    password, token, API key) in code or config.

    Hardcoding credentials is a universal security defect: the credential
    is visible in source control, logs, and stack traces, and cannot be
    rotated without a code change. No methodology considers this correct.

    Limitation: pattern-based. A skill may describe hardcoding or secure
    storage using vocabulary not captured by the patterns. The finding
    is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_hardcode = any(
                p.search(text) for p in _HARDCODED_CREDENTIAL_PATTERNS
            )
            if not has_hardcode:
                continue
            has_secure = any(
                p.search(text) for p in _SECURE_CREDENTIAL_PATTERNS
            )
            if has_secure:
                continue
            findings.append(_finding(
                cls="HARDCODED_CREDENTIAL",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} instructs hardcoding a credential "
                    f"(secret, password, token, API key) in code or config"
                ),
                violated_invariant=(
                    "a credential must not be hardcoded in code or config; "
                    "hardcoded credentials are visible in source control, "
                    "logs, and stack traces, and cannot be rotated without "
                    "a code change"
                ),
                limitation=(
                    "hardcoding and secure-storage detection are pattern-"
                    "based; a skill may describe hardcoding or secure "
                    "storage using vocabulary not captured by the "
                    "patterns; the finding is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_hardcode = any(
                p.search(text) for p in _HARDCODED_CREDENTIAL_PATTERNS
            )
            if not has_hardcode:
                continue
            has_secure = any(
                p.search(text) for p in _SECURE_CREDENTIAL_PATTERNS
            )
            if has_secure:
                continue
            findings.append(_finding(
                cls="HARDCODED_CREDENTIAL",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} instructs hardcoding a credential "
                    f"(secret, password, token, API key) in code or config"
                ),
                violated_invariant=(
                    "a credential must not be hardcoded in code or config; "
                    "hardcoded credentials are visible in source control, "
                    "logs, and stack traces, and cannot be rotated without "
                    "a code change"
                ),
                limitation=(
                    "hardcoding and secure-storage detection are pattern-"
                    "based; a skill may describe hardcoding or secure "
                    "storage using vocabulary not captured by the "
                    "patterns; the finding is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# UNBOUNDED_RESOURCE
# ---------------------------------------------------------------------------

# Patterns that indicate unbounded resource consumption.
_UNBOUNDED_RESOURCE_PATTERNS = [
    re.compile(r"\b(load|read|collect|gather|fetch|buffer|cache)\s+all\b", re.IGNORECASE),
    re.compile(r"\bread\s+everything\b", re.IGNORECASE),
    re.compile(r"\bload\s+everything\b", re.IGNORECASE),
    re.compile(r"\bload\s+the\s+entire\b", re.IGNORECASE),
    re.compile(r"\bread\s+the\s+entire\b", re.IGNORECASE),
    re.compile(r"\bload\s+into\s+memory\b", re.IGNORECASE),
    re.compile(r"\bread\s+into\s+memory\b", re.IGNORECASE),
]

# Patterns that indicate a bound on resource consumption.
_RESOURCE_BOUND_PATTERNS = [
    re.compile(r"\blimit\b", re.IGNORECASE),
    re.compile(r"\bmax(?:imum)?\b", re.IGNORECASE),
    re.compile(r"\bcap\b", re.IGNORECASE),
    re.compile(r"\bbatch(?:es|ed|ing)?\b", re.IGNORECASE),
    re.compile(r"\bchunk\b", re.IGNORECASE),
    re.compile(r"\bstream\b", re.IGNORECASE),
    re.compile(r"\bpaginat(?:e|ed|ion)\b", re.IGNORECASE),
    re.compile(r"\bspars(?:e|ely)\b", re.IGNORECASE),
    re.compile(r"\bsampl(?:e|ed|ing)\b", re.IGNORECASE),
    re.compile(r"\blazy\b", re.IGNORECASE),
    re.compile(r"\bon\s+demand\b", re.IGNORECASE),
]


def _check_unbounded_resource(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or step that instructs loading, reading, or collecting all of
    something without a limit, batch, or streaming bound.

    Unbounded resource consumption is a universal engineering defect: it
    can exhaust memory, disk, or network bandwidth. "Load all files into
    memory" without a limit is dangerous regardless of methodology.

    Limitation: pattern-based. A skill may describe unbounded consumption
    or its bounds using vocabulary not captured by the patterns. The
    finding is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_unbounded = any(
                p.search(text) for p in _UNBOUNDED_RESOURCE_PATTERNS
            )
            if not has_unbounded:
                continue
            has_bound = any(
                p.search(text) for p in _RESOURCE_BOUND_PATTERNS
            )
            if has_bound:
                continue
            findings.append(_finding(
                cls="UNBOUNDED_RESOURCE",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} instructs unbounded resource "
                    f"consumption (load all, read all, collect all, load "
                    f"into memory) without a bound (limit, max, batch, "
                    f"stream, paginate)"
                ),
                violated_invariant=(
                    "resource consumption must be bounded; loading all "
                    "data into memory without a limit, batch, or stream "
                    "can exhaust memory, disk, or network bandwidth"
                ),
                limitation=(
                    "unbounded-resource and bound detection are pattern-"
                    "based; a skill may describe consumption or bounds "
                    "using vocabulary not captured by the patterns; the "
                    "finding is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_unbounded = any(
                p.search(text) for p in _UNBOUNDED_RESOURCE_PATTERNS
            )
            if not has_unbounded:
                continue
            has_bound = any(
                p.search(text) for p in _RESOURCE_BOUND_PATTERNS
            )
            if has_bound:
                continue
            findings.append(_finding(
                cls="UNBOUNDED_RESOURCE",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} instructs unbounded resource "
                    f"consumption (load all, read all, collect all, load "
                    f"into memory) without a bound (limit, max, batch, "
                    f"stream, paginate)"
                ),
                violated_invariant=(
                    "resource consumption must be bounded; loading all "
                    "data into memory without a limit, batch, or stream "
                    "can exhaust memory, disk, or network bandwidth"
                ),
                limitation=(
                    "unbounded-resource and bound detection are pattern-"
                    "based; a skill may describe consumption or bounds "
                    "using vocabulary not captured by the patterns; the "
                    "finding is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# UNVALIDATED_EXTERNAL_INPUT
# ---------------------------------------------------------------------------

# Patterns that indicate external input is being accepted.
_EXTERNAL_INPUT_PATTERNS = [
    re.compile(
        r"\b(parse|accept|process|read|load|ingest|consume|receive|handle)\b"
        r".*\b(user\s+input|request|stdin|argv|command\s+line\s+argument|"
        r"environment\s+variable|query\s+parameter|form\s+data|"
        r"uploaded\s+file|untrusted\s+(?:input|data|source))\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(user\s+input|request|stdin|argv|command\s+line\s+argument|"
        r"environment\s+variable|query\s+parameter|form\s+data|"
        r"uploaded\s+file|untrusted\s+(?:input|data|source))\b"
        r".*\b(parse|accept|process|read|load|ingest|consume|receive|handle)\b",
        re.IGNORECASE,
    ),
]

# Patterns that indicate validation is present.
_INPUT_VALIDATION_PATTERNS = [
    re.compile(r"\bvalidat(?:e|ed|ion)\b", re.IGNORECASE),
    re.compile(r"\bsanitiz(?:e|ed|ation)\b", re.IGNORECASE),
    re.compile(r"\bschema\b", re.IGNORECASE),
    re.compile(r"\btype\s+check\b", re.IGNORECASE),
    re.compile(r"\bbound(?:ary)?\s+check\b", re.IGNORECASE),
    re.compile(r"\bassert\b", re.IGNORECASE),
    re.compile(r"\bverify\b", re.IGNORECASE),
    re.compile(r"\bcheck\b", re.IGNORECASE),
    re.compile(r"\bguard\b", re.IGNORECASE),
    re.compile(r"\bfilter\b", re.IGNORECASE),
    re.compile(r"\bdenylist\b", re.IGNORECASE),
    re.compile(r"\ballowlist\b", re.IGNORECASE),
    re.compile(r"\bparse\s+into\s+types?\b", re.IGNORECASE),
]


def _check_unvalidated_external_input(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or step that instructs accepting external input (user input,
    request, stdin, argv, uploaded file, untrusted source) without
    validation, sanitization, or type checking.

    Accepting unvalidated external input is a universal engineering
    defect (validate at the boundary): it allows malformed, hostile, or
    unexpected data to reach deep inside the system where it can cause
    silent corruption or security vulnerabilities. No methodology
    considers this correct.

    Limitation: pattern-based. A skill may describe external input or
    validation using vocabulary not captured by the patterns. The
    finding is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_input = any(p.search(text) for p in _EXTERNAL_INPUT_PATTERNS)
            if not has_input:
                continue
            has_validation = any(
                p.search(text) for p in _INPUT_VALIDATION_PATTERNS
            )
            if has_validation:
                continue
            findings.append(_finding(
                cls="UNVALIDATED_EXTERNAL_INPUT",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} instructs accepting external input "
                    f"(user input, request, stdin, argv, uploaded file) "
                    f"without validation (validate, sanitize, schema, "
                    f"type check, assert)"
                ),
                violated_invariant=(
                    "external input must be validated at the boundary; "
                    "unvalidated input allows malformed, hostile, or "
                    "unexpected data to reach deep inside the system "
                    "where it can cause silent corruption or security "
                    "vulnerabilities"
                ),
                limitation=(
                    "external-input and validation detection are pattern-"
                    "based; a skill may describe input or validation using "
                    "vocabulary not captured by the patterns; the finding "
                    "is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_input = any(p.search(text) for p in _EXTERNAL_INPUT_PATTERNS)
            if not has_input:
                continue
            has_validation = any(
                p.search(text) for p in _INPUT_VALIDATION_PATTERNS
            )
            if has_validation:
                continue
            findings.append(_finding(
                cls="UNVALIDATED_EXTERNAL_INPUT",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} instructs accepting external input "
                    f"(user input, request, stdin, argv, uploaded file) "
                    f"without validation (validate, sanitize, schema, "
                    f"type check, assert)"
                ),
                violated_invariant=(
                    "external input must be validated at the boundary; "
                    "unvalidated input allows malformed, hostile, or "
                    "unexpected data to reach deep inside the system "
                    "where it can cause silent corruption or security "
                    "vulnerabilities"
                ),
                limitation=(
                    "external-input and validation detection are pattern-"
                    "based; a skill may describe input or validation using "
                    "vocabulary not captured by the patterns; the finding "
                    "is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# MISSING_TIMEOUT
# ---------------------------------------------------------------------------

# Patterns that indicate an operation waits without a timeout.
_MISSING_TIMEOUT_PATTERNS = [
    re.compile(r"\bwait\s+indefinitely\b", re.IGNORECASE),
    re.compile(r"\bblock\s+forever\b", re.IGNORECASE),
    re.compile(r"\bwait\s+forever\b", re.IGNORECASE),
    re.compile(r"\blisten\s+indefinitely\b", re.IGNORECASE),
    re.compile(r"\bpoll\s+indefinitely\b", re.IGNORECASE),
    re.compile(r"\bwait\s+without\s+(?:a\s+)?timeout\b", re.IGNORECASE),
    re.compile(r"\bblock\s+without\s+(?:a\s+)?timeout\b", re.IGNORECASE),
    re.compile(r"\bwait\s+until\s+(?:it\s+)?succeeds?\b", re.IGNORECASE),
    re.compile(r"\bwait\s+until\s+(?:it\s+)?completes?\b", re.IGNORECASE),
    re.compile(r"\bblock\s+until\s+(?:it\s+)?finishes?\b", re.IGNORECASE),
]

# Patterns that indicate a timeout or deadline is present.
_TIMEOUT_PATTERNS = [
    re.compile(r"\btimeout\b", re.IGNORECASE),
    re.compile(r"\bdeadline\b", re.IGNORECASE),
    re.compile(r"\bmax\s+wait\b", re.IGNORECASE),
    re.compile(r"\btime\s+limit\b", re.IGNORECASE),
    re.compile(r"\bduration\b", re.IGNORECASE),
    re.compile(r"\bexpire(?:s|d|y)?\b", re.IGNORECASE),
    re.compile(r"\bTTL\b"),
]


def _check_missing_timeout(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or step that instructs waiting, blocking, or polling without a
    timeout or deadline.

    Waiting without a timeout is a universal engineering defect: the
    operation can hang forever if the expected event never arrives. No
    methodology considers an indefinite wait correct.

    Limitation: pattern-based. A skill may describe waiting or timeouts
    using vocabulary not captured by the patterns. The finding is
    CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_wait = any(p.search(text) for p in _MISSING_TIMEOUT_PATTERNS)
            if not has_wait:
                continue
            has_timeout = any(p.search(text) for p in _TIMEOUT_PATTERNS)
            if has_timeout:
                continue
            findings.append(_finding(
                cls="MISSING_TIMEOUT",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} instructs waiting or blocking "
                    f"without a timeout (wait indefinitely, block forever, "
                    f"wait until success) without a deadline (timeout, "
                    f"deadline, max wait, TTL)"
                ),
                violated_invariant=(
                    "a wait or block must have a timeout or deadline; an "
                    "indefinite wait can hang forever if the expected "
                    "event never arrives"
                ),
                limitation=(
                    "wait and timeout detection are pattern-based; a skill "
                    "may describe waiting or timeouts using vocabulary not "
                    "captured by the patterns; the finding is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_wait = any(p.search(text) for p in _MISSING_TIMEOUT_PATTERNS)
            if not has_wait:
                continue
            has_timeout = any(p.search(text) for p in _TIMEOUT_PATTERNS)
            if has_timeout:
                continue
            findings.append(_finding(
                cls="MISSING_TIMEOUT",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} instructs waiting or blocking "
                    f"without a timeout (wait indefinitely, block forever, "
                    f"wait until success) without a deadline (timeout, "
                    f"deadline, max wait, TTL)"
                ),
                violated_invariant=(
                    "a wait or block must have a timeout or deadline; an "
                    "indefinite wait can hang forever if the expected "
                    "event never arrives"
                ),
                limitation=(
                    "wait and timeout detection are pattern-based; a skill "
                    "may describe waiting or timeouts using vocabulary not "
                    "captured by the patterns; the finding is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# FLOATING_POINT_IN_DECISION_PATH
# ---------------------------------------------------------------------------

# Patterns that indicate floats are used for exact decisions.
_FLOAT_DECISION_PATTERNS = [
    re.compile(
        r"\bfloat(?:ing|s)?\b.*\b(==|equal(?:ity)?|compare|comparison)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(==|equal(?:ity)?|compare|comparison)\b.*\bfloat(?:ing|s)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bfloat(?:ing|s)?\b.*\b(money|financial|currency|payment|balance|"
        r"total|sum|amount)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(money|financial|currency|payment|balance|total|sum|amount)\b"
        r".*\bfloat(?:ing|s)?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bdouble\b.*\b(==|equal|compare)\b", re.IGNORECASE),
    re.compile(r"\b(==|equal|compare)\b.*\bdouble\b", re.IGNORECASE),
]

# Patterns that indicate exact arithmetic is used instead.
_EXACT_ARITHMETIC_PATTERNS = [
    re.compile(r"\bFraction\b"),
    re.compile(r"\bDecimal\b"),
    re.compile(r"\binteger\b", re.IGNORECASE),
    re.compile(r"\bfixed[- ]?point\b", re.IGNORECASE),
    re.compile(r"\bscaled\s+integer\b", re.IGNORECASE),
    re.compile(r"\bepsilon\b", re.IGNORECASE),
    re.compile(r"\btolerance\b", re.IGNORECASE),
    re.compile(r"\bapproximat(?:e|ely)\b", re.IGNORECASE),
]


def _check_floating_point_in_decision_path(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or step that instructs using floating-point arithmetic for a
    decision requiring exactness (equality, comparison, money, financial).

    Floats in the decision path are a universal engineering defect: float
    summation is ordering- and platform-dependent, so the digest cannot
    be stable. Equality checks on floats are unreliable. Financial
    calculations with floats lose cents. No methodology considers this
    correct.

    Limitation: pattern-based. A skill may describe float usage or exact
    arithmetic using vocabulary not captured by the patterns. The
    finding is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_float = any(p.search(text) for p in _FLOAT_DECISION_PATTERNS)
            if not has_float:
                continue
            has_exact = any(
                p.search(text) for p in _EXACT_ARITHMETIC_PATTERNS
            )
            if has_exact:
                continue
            findings.append(_finding(
                cls="FLOATING_POINT_IN_DECISION_PATH",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} instructs using floating-point "
                    f"arithmetic for an exact decision (equality, "
                    f"comparison, money, financial) without exact "
                    f"arithmetic (Fraction, Decimal, integer, epsilon)"
                ),
                violated_invariant=(
                    "a decision requiring exactness must not use floating-"
                    "point arithmetic; float summation is ordering- and "
                    "platform-dependent, equality checks are unreliable, "
                    "and financial calculations lose cents"
                ),
                limitation=(
                    "float-usage and exact-arithmetic detection are "
                    "pattern-based; a skill may describe float usage or "
                    "exact arithmetic using vocabulary not captured by "
                    "the patterns; the finding is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_float = any(p.search(text) for p in _FLOAT_DECISION_PATTERNS)
            if not has_float:
                continue
            has_exact = any(
                p.search(text) for p in _EXACT_ARITHMETIC_PATTERNS
            )
            if has_exact:
                continue
            findings.append(_finding(
                cls="FLOATING_POINT_IN_DECISION_PATH",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} instructs using floating-point "
                    f"arithmetic for an exact decision (equality, "
                    f"comparison, money, financial) without exact "
                    f"arithmetic (Fraction, Decimal, integer, epsilon)"
                ),
                violated_invariant=(
                    "a decision requiring exactness must not use floating-"
                    "point arithmetic; float summation is ordering- and "
                    "platform-dependent, equality checks are unreliable, "
                    "and financial calculations lose cents"
                ),
                limitation=(
                    "float-usage and exact-arithmetic detection are "
                    "pattern-based; a skill may describe float usage or "
                    "exact arithmetic using vocabulary not captured by "
                    "the patterns; the finding is CANDIDATE"
                ),
            ))
    return findings


# ---------------------------------------------------------------------------
# UNPINNED_DEPENDENCY
# ---------------------------------------------------------------------------

# Patterns that indicate a dependency is installed without version pinning.
_UNPINNED_DEPENDENCY_PATTERNS = [
    re.compile(r"\bpip\s+install\s+(\S+)(?!\s*[=<>!~])", re.IGNORECASE),
    re.compile(r"\bnpm\s+install\s+(\S+)(?!\s*@)", re.IGNORECASE),
    re.compile(r"\byarn\s+add\s+(\S+)(?!\s*@)", re.IGNORECASE),
    re.compile(r"\bcargo\s+add\s+(\S+)(?!\s*@|=)", re.IGNORECASE),
    re.compile(r"\bgo\s+get\s+(\S+)(?!\s*@)", re.IGNORECASE),
    re.compile(r"\bapt(?:-get)?\s+install\s+(\S+)(?!\s*=)", re.IGNORECASE),
    re.compile(r"\binstall\s+the\s+latest\b", re.IGNORECASE),
    re.compile(r"\binstall\s+latest\b", re.IGNORECASE),
    re.compile(r"\buse\s+the\s+latest\s+version\b", re.IGNORECASE),
]

# Patterns that indicate version pinning is present.
_PINNED_DEPENDENCY_PATTERNS = [
    re.compile(r"==\s*[\d.]"),
    re.compile(r"@\s*[\d.]"),
    re.compile(r"=\s*[\d.]"),
    re.compile(r"\bpin(?:ned|ning)?\b", re.IGNORECASE),
    re.compile(r"\block\s+file\b", re.IGNORECASE),
    re.compile(r"\brequirements\.txt\b"),
    re.compile(r"\bpackage-lock\.json\b"),
    re.compile(r"\bCargo\.lock\b"),
    re.compile(r"\bgo\.sum\b"),
    re.compile(r"\bpoetry\.lock\b"),
    re.compile(r"\bpdm\.lock\b"),
    re.compile(r"\buv\.lock\b"),
    re.compile(r"\bversion\s+pin(?:ned|ning)?\b", re.IGNORECASE),
    re.compile(r"\bspecific\s+version\b", re.IGNORECASE),
]


def _check_unpinned_dependency(
    skills: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """A rule or step that instructs installing a dependency without
    version pinning (pip install X without ==version, npm install X
    without @version, install latest).

    Unpinned dependencies are a universal engineering defect: the build
    breaks when a new version is released, and supply-chain attacks
    often arrive in newly published versions. No methodology considers
    floating versions correct for production.

    Limitation: pattern-based. A skill may describe installation or
    pinning using vocabulary not captured by the patterns. The finding
    is CANDIDATE.
    """
    findings: list[dict[str, Any]] = []
    for skill in skills:
        name = skill["identity"]["name"]
        source_path = skill["identity"]["source_path"]
        for rule in skill.get("rules", []):
            text = rule.get("text", "")
            has_unpinned = any(
                p.search(text) for p in _UNPINNED_DEPENDENCY_PATTERNS
            )
            if not has_unpinned:
                continue
            has_pinned = any(
                p.search(text) for p in _PINNED_DEPENDENCY_PATTERNS
            )
            if has_pinned:
                continue
            findings.append(_finding(
                cls="UNPINNED_DEPENDENCY",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=rule["source_span"],
                rule_id=rule["id"],
                evidence=(
                    f"rule {rule['id']} instructs installing a dependency "
                    f"without version pinning (pip install, npm install, "
                    f"install latest) without a pin (==version, @version, "
                    f"lock file)"
                ),
                violated_invariant=(
                    "a dependency must be version-pinned; unpinned "
                    "dependencies break the build when a new version is "
                    "released and expose the system to supply-chain attacks "
                    "that arrive in newly published versions"
                ),
                limitation=(
                    "installation and pinning detection are pattern-based; "
                    "a skill may describe installation or pinning using "
                    "vocabulary not captured by the patterns; the finding "
                    "is CANDIDATE"
                ),
            ))
        for step in skill.get("procedural_steps", []):
            text = step.get("text", "")
            has_unpinned = any(
                p.search(text) for p in _UNPINNED_DEPENDENCY_PATTERNS
            )
            if not has_unpinned:
                continue
            has_pinned = any(
                p.search(text) for p in _PINNED_DEPENDENCY_PATTERNS
            )
            if has_pinned:
                continue
            findings.append(_finding(
                cls="UNPINNED_DEPENDENCY",
                epistemic_status="CANDIDATE",
                skill=name,
                source_path=source_path,
                source_span=step["source_span"],
                rule_id=step["id"],
                evidence=(
                    f"step {step['id']} instructs installing a dependency "
                    f"without version pinning (pip install, npm install, "
                    f"install latest) without a pin (==version, @version, "
                    f"lock file)"
                ),
                violated_invariant=(
                    "a dependency must be version-pinned; unpinned "
                    "dependencies break the build when a new version is "
                    "released and expose the system to supply-chain attacks "
                    "that arrive in newly published versions"
                ),
                limitation=(
                    "installation and pinning detection are pattern-based; "
                    "a skill may describe installation or pinning using "
                    "vocabulary not captured by the patterns; the finding "
                    "is CANDIDATE"
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
