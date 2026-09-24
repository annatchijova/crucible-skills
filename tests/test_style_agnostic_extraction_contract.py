"""Contract tests for L9 style-agnostic extraction.

These tests encode the invariant that the compiler extracts normative
rules, procedural steps, and checks from skills written in any valid
style -- not only RFC-2119 modals under dedicated section headings.

Covered styles:
- RFC-2119 modals (MUST, SHOULD, MAY) -- existing behavior, must not regress.
- Absoluteness starters (Never, Always, Do not, Don't).
- Imperative constraint verbs (Ensure, Require, Prevent, Avoid, ...).
- Prose-embedded procedural steps (action-verb bullets outside Steps).
- Verification statements outside Checks sections.
- Code-fence exclusion (code blocks are not normative prose).
- Source spans and deterministic compilation.
- Negative cases (ordinary explanatory text is not extracted).
"""
from __future__ import annotations

import json
from pathlib import Path

from crucible.compiler import compile_corpus


def _write_skill(root: Path, name: str, body: str) -> Path:
    skill = root / name
    skill.mkdir()
    (skill / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")
    return skill


def _compile(root: Path) -> dict:
    return compile_corpus(root)


# ---------------------------------------------------------------------------
# Rule extraction: absoluteness starters
# ---------------------------------------------------------------------------

def test_never_starter_extracted_as_rule(tmp_path: Path) -> None:
    """Invariant: a line starting with 'Never' is extracted as a
    normative rule with modality NEVER. Mutation: skip negative
    starters -> red (rule count drops to 0)."""
    _write_skill(
        tmp_path,
        "never-skill",
        "---\nname: never-skill\ndescription: Never delete without backup.\n---\n\n"
        "# Safety\n\nNever delete production data without a backup.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 1
    assert rules[0]["modality"] == "NEVER"
    assert "Never delete production data" in rules[0]["text"]
    assert rules[0]["source_span"]["line"] == 8


def test_always_starter_extracted_as_rule(tmp_path: Path) -> None:
    """Invariant: a line starting with 'Always' is extracted as a
    normative rule with modality ALWAYS."""
    _write_skill(
        tmp_path,
        "always-skill",
        "---\nname: always-skill\ndescription: Always validate inputs.\n---\n\n"
        "# Discipline\n\nAlways validate inputs at the boundary.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 1
    assert rules[0]["modality"] == "ALWAYS"
    assert "Always validate inputs" in rules[0]["text"]


def test_do_not_starter_extracted_as_must_not(tmp_path: Path) -> None:
    """Invariant: 'Do not' and 'Don't' starters are extracted as
    modality MUST_NOT."""
    _write_skill(
        tmp_path,
        "dont-skill",
        "---\nname: dont-skill\ndescription: Do not skip tests.\n---\n\n"
        "# Rules\n\nDo not commit directly to main.\nDon't force-push.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 2
    assert rules[0]["modality"] == "MUST_NOT"
    assert rules[1]["modality"] == "MUST_NOT"


def test_negative_starter_with_bullet_marker(tmp_path: Path) -> None:
    """Invariant: a bullet list item starting with 'Never' is extracted
    as a rule, not skipped because of the bullet marker."""
    _write_skill(
        tmp_path,
        "bullet-never",
        "---\nname: bullet-never\ndescription: Bullet prohibitions.\n---\n\n"
        "# Prohibitions\n\n- Never store secrets in logs.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 1
    assert rules[0]["modality"] == "NEVER"


# ---------------------------------------------------------------------------
# Rule extraction: imperative constraint verbs
# ---------------------------------------------------------------------------

def test_imperative_verb_starter_extracted_as_rule(tmp_path: Path) -> None:
    """Invariant: a line starting with a normative constraint verb
    (Ensure, Require, Prevent, Avoid, Validate, ...) is extracted as a
    rule with modality IMPERATIVE."""
    _write_skill(
        tmp_path,
        "imperative-skill",
        "---\nname: imperative-skill\ndescription: Ensure determinism.\n---\n\n"
        "# Constraints\n\nEnsure the decision path has no floats.\n"
        "Prevent unbounded retries.\n"
        "Avoid irreversible actions without review.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 3
    assert all(r["modality"] == "IMPERATIVE" for r in rules)
    assert "Ensure the decision path" in rules[0]["text"]
    assert "Prevent unbounded retries" in rules[1]["text"]
    assert "Avoid irreversible actions" in rules[2]["text"]


def test_imperative_verb_with_bullet_marker(tmp_path: Path) -> None:
    """Invariant: a bullet starting with a normative verb is extracted
    as a rule."""
    _write_skill(
        tmp_path,
        "bullet-imperative",
        "---\nname: bullet-imperative\ndescription: Bullet constraints.\n---\n\n"
        "# Constraints\n\n- Validate inputs at the boundary.\n"
        "- Isolate failure domains.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 2
    assert all(r["modality"] == "IMPERATIVE" for r in rules)


# ---------------------------------------------------------------------------
# Rule extraction: RFC-2119 compatibility
# ---------------------------------------------------------------------------

def test_rfc2119_modals_still_extracted(tmp_path: Path) -> None:
    """Invariant: RFC-2119 modal extraction is not broken by the new
    styles. A skill with MUST/SHOULD/MAY still produces rules with
    those modalities."""
    _write_skill(
        tmp_path,
        "rfc-skill",
        "---\nname: rfc-skill\ndescription: RFC-2119 style.\n---\n\n"
        "# Rules\n\nThe system MUST validate inputs.\n"
        "The operator SHOULD log errors.\n"
        "The user MAY skip optional steps.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 3
    assert [r["modality"] for r in rules] == ["MUST", "SHOULD", "MAY"]


def test_mixed_styles_extracted_together(tmp_path: Path) -> None:
    """Invariant: a skill mixing RFC-2119 and non-RFC-2119 styles
    extracts rules from both."""
    _write_skill(
        tmp_path,
        "mixed-skill",
        "---\nname: mixed-skill\ndescription: Mixed styles.\n---\n\n"
        "# Rules\n\nThe system MUST validate inputs.\n"
        "Never store secrets in logs.\n"
        "Ensure the decision path is deterministic.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 3
    modalities = [r["modality"] for r in rules]
    assert "MUST" in modalities
    assert "NEVER" in modalities
    assert "IMPERATIVE" in modalities


# ---------------------------------------------------------------------------
# Rule extraction: code-fence exclusion
# ---------------------------------------------------------------------------

def test_code_block_not_extracted_as_rule(tmp_path: Path) -> None:
    """Invariant: lines inside fenced code blocks are not extracted as
    rules, even if they contain normative language."""
    _write_skill(
        tmp_path,
        "code-skill",
        "---\nname: code-skill\ndescription: Has code.\n---\n\n"
        "# Example\n\n```\nNever run this in production.\n"
        "Always use a test environment.\n```\n\n"
        "Ensure the example is not extracted.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    # Only the line outside the code block should be extracted.
    assert len(rules) == 1
    assert "Ensure the example" in rules[0]["text"]


# ---------------------------------------------------------------------------
# Rule extraction: negative cases
# ---------------------------------------------------------------------------

def test_explanatory_prose_not_extracted_as_rule(tmp_path: Path) -> None:
    """Invariant: ordinary explanatory sentences that do not start with
    a normative verb or absoluteness starter are not extracted as rules."""
    _write_skill(
        tmp_path,
        "prose-skill",
        "---\nname: prose-skill\ndescription: Explanatory.\n---\n\n"
        "# Overview\n\nThis skill helps you debug memory leaks.\n"
        "It uses valgrind and other tools.\n"
        "The output is a report of leaked allocations.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 0


def test_heading_not_extracted_as_rule(tmp_path: Path) -> None:
    """Invariant: markdown headings are not extracted as rules, even if
    they contain a normative verb."""
    _write_skill(
        tmp_path,
        "heading-skill",
        "---\nname: heading-skill\ndescription: Has headings.\n---\n\n"
        "# Ensure determinism\n\nSome body text.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert len(rules) == 0


# ---------------------------------------------------------------------------
# Step extraction: prose-embedded action-verb bullets
# ---------------------------------------------------------------------------

def test_action_verb_bullet_extracted_as_step(tmp_path: Path) -> None:
    """Invariant: a bullet starting with an action verb outside a
    Steps section is extracted as a procedural step."""
    _write_skill(
        tmp_path,
        "prose-steps",
        "---\nname: prose-steps\ndescription: Steps in prose.\n---\n\n"
        "# How to use\n\n- Run the test suite.\n"
        "- Review the output.\n"
        "- Fix any failures.\n",
    )
    artifact = _compile(tmp_path)
    steps = artifact["skills"][0]["procedural_steps"]
    assert len(steps) == 3
    assert "Run the test suite" in steps[0]["text"]
    assert "Review the output" in steps[1]["text"]
    assert "Fix any failures" in steps[2]["text"]


def test_explanatory_bullet_not_extracted_as_step(tmp_path: Path) -> None:
    """Invariant: a bullet that does not start with an action verb is
    not extracted as a step (e.g., 'This is important because ...')."""
    _write_skill(
        tmp_path,
        "explanatory-bullets",
        "---\nname: explanatory-bullets\ndescription: Explanatory.\n---\n\n"
        "# Notes\n\n- This skill is important for safety.\n"
        "- The reason is that unbounded retries cause outages.\n"
        "It was introduced in version 2.\n",
    )
    artifact = _compile(tmp_path)
    steps = artifact["skills"][0]["procedural_steps"]
    assert len(steps) == 0


def test_check_section_bullet_not_extracted_as_step(tmp_path: Path) -> None:
    """Invariant: a bullet in a Checks/Verification section is not
    extracted as a procedural step, even if it starts with an action
    verb like 'Verify'."""
    _write_skill(
        tmp_path,
        "check-bullets",
        "---\nname: check-bullets\ndescription: Has checks.\n---\n\n"
        "# Rules\n\nThe system MUST validate inputs.\n\n"
        "## Checks\n\n- Verify the inputs are validated.\n"
        "- Test the validation logic.\n",
    )
    artifact = _compile(tmp_path)
    steps = artifact["skills"][0]["procedural_steps"]
    checks = artifact["skills"][0]["checks"]
    # The check bullets must not become steps.
    assert len(steps) == 0
    assert len(checks) == 2


def test_numbered_list_outside_steps_section_extracted(tmp_path: Path) -> None:
    """Invariant: numbered lists anywhere in the body are extracted as
    steps, not only under Steps sections."""
    _write_skill(
        tmp_path,
        "numbered-prose",
        "---\nname: numbered-prose\ndescription: Numbered in prose.\n---\n\n"
        "# Procedure\n\n1. Install the package.\n"
        "2. Configure the options.\n"
        "3. Run the build.\n",
    )
    artifact = _compile(tmp_path)
    steps = artifact["skills"][0]["procedural_steps"]
    assert len(steps) == 3


# ---------------------------------------------------------------------------
# Check extraction: verification starters outside Checks sections
# ---------------------------------------------------------------------------

def test_verification_starter_outside_checks_section(tmp_path: Path) -> None:
    """Invariant: a line starting with a verification verb (verify,
    check, test, assert, confirm, demonstrate, prove) outside a Checks
    section is extracted as a check."""
    _write_skill(
        tmp_path,
        "verify-prose",
        "---\nname: verify-prose\ndescription: Verify in prose.\n---\n\n"
        "# Workflow\n\nRun the analysis.\n"
        "Verify the results are consistent.\n"
        "Confirm the output matches expectations.\n",
    )
    artifact = _compile(tmp_path)
    checks = artifact["skills"][0]["checks"]
    assert len(checks) == 2
    assert "Verify the results are consistent" in checks[0]["text"]
    assert "Confirm the output matches expectations" in checks[1]["text"]


def test_verification_starter_with_bullet_marker(tmp_path: Path) -> None:
    """Invariant: a bullet starting with a verification verb is
    extracted as a check."""
    _write_skill(
        tmp_path,
        "verify-bullet",
        "---\nname: verify-bullet\ndescription: Verify bullets.\n---\n\n"
        "# Process\n\n- Verify the seal is present.\n"
        "- Assert the digest matches.\n",
    )
    artifact = _compile(tmp_path)
    checks = artifact["skills"][0]["checks"]
    assert len(checks) == 2


def test_code_block_not_extracted_as_check(tmp_path: Path) -> None:
    """Invariant: lines inside fenced code blocks are not extracted as
    checks, even if they start with a verification verb."""
    _write_skill(
        tmp_path,
        "code-check",
        "---\nname: code-check\ndescription: Has code.\n---\n\n"
        "# Example\n\n```\nverify_seal(digest)\nassert result == True\n```\n\n"
        "Verify the real check outside code.\n",
    )
    artifact = _compile(tmp_path)
    checks = artifact["skills"][0]["checks"]
    assert len(checks) == 1
    assert "Verify the real check" in checks[0]["text"]


def test_checks_section_still_extracted(tmp_path: Path) -> None:
    """Invariant: checks in a dedicated Checks section are still
    extracted (existing behavior not broken)."""
    _write_skill(
        tmp_path,
        "checks-section",
        "---\nname: checks-section\ndescription: Has checks section.\n---\n\n"
        "## Checks\n\n- Verify the seal is present.\n"
        "- Confirm the digest matches.\n",
    )
    artifact = _compile(tmp_path)
    checks = artifact["skills"][0]["checks"]
    assert len(checks) == 2


# ---------------------------------------------------------------------------
# Determinism and source spans
# ---------------------------------------------------------------------------

def test_style_agnostic_extraction_is_deterministic(tmp_path: Path) -> None:
    """Invariant: compiling the same skill twice produces identical
    artifacts and digests."""
    _write_skill(
        tmp_path,
        "deterministic-skill",
        "---\nname: deterministic-skill\ndescription: Deterministic.\n---\n\n"
        "# Rules\n\nNever store secrets in logs.\n"
        "Ensure the decision path is deterministic.\n"
        "Always validate inputs.\n\n"
        "# Steps\n\n- Run the analysis.\n"
        "- Verify the results.\n",
    )
    first = _compile(tmp_path)
    second = _compile(tmp_path)
    assert first == second
    assert first["artifact_digest"] == second["artifact_digest"]


def test_source_spans_are_stable(tmp_path: Path) -> None:
    """Invariant: source spans point to the correct line numbers."""
    _write_skill(
        tmp_path,
        "spans-skill",
        "---\nname: spans-skill\ndescription: Has spans.\n---\n\n"
        "# Rules\n\nNever store secrets in logs.\n"
        "Ensure the decision path is deterministic.\n",
    )
    artifact = _compile(tmp_path)
    rules = artifact["skills"][0]["rules"]
    assert rules[0]["source_span"]["line"] == 8
    assert rules[1]["source_span"]["line"] == 9
    assert rules[0]["source_span"]["column"] == 1
    assert rules[1]["source_span"]["column"] == 1


def test_artifact_digest_is_sha256(tmp_path: Path) -> None:
    """Invariant: the artifact digest is a SHA-256 hash."""
    _write_skill(
        tmp_path,
        "digest-skill",
        "---\nname: digest-skill\ndescription: Digest.\n---\n\n"
        "Never skip the tests.\n",
    )
    artifact = _compile(tmp_path)
    assert artifact["artifact_digest"].startswith("sha256:")
    assert len(artifact["artifact_digest"]) == len("sha256:") + 64


def test_no_floats_in_sealed_artifact(tmp_path: Path) -> None:
    """Invariant: no float values appear in the sealed artifact."""
    _write_skill(
        tmp_path,
        "no-floats",
        "---\nname: no-floats\ndescription: No floats.\n---\n\n"
        "Never use floats in the decision path.\n"
        "Ensure determinism with Fraction.\n",
    )
    artifact = _compile(tmp_path)
    serialized = json.dumps(artifact, sort_keys=True)
    # The artifact must not contain float literals like 1.0 or 0.5.
    import re
    float_pattern = re.compile(r":\s*\d+\.\d+")
    assert not float_pattern.search(serialized)


# ---------------------------------------------------------------------------
# Integration: style-agnostic extraction reduces false positives
# ---------------------------------------------------------------------------

def test_prose_style_skill_not_flagged_as_vacuous(tmp_path: Path) -> None:
    """Invariant: a skill that uses prose normative language (Never,
    Ensure) and has procedural steps is NOT flagged as
    METHODOLOGICAL_VACUITY, because it has rules AND steps."""
    from crucible.auditor import audit_corpus
    _write_skill(
        tmp_path,
        "prose-method",
        "---\nname: prose-method\ndescription: A prose-style method.\n---\n\n"
        "# Method\n\nNever delete without backup.\n"
        "Ensure the decision path is deterministic.\n\n"
        "# How to use\n\n- Run the analysis.\n"
        "- Review the output.\n"
        "- Verify the results.\n",
    )
    artifact = _compile(tmp_path)
    audit = audit_corpus(artifact)
    classes = [f["class"] for f in audit["findings"]]
    assert "METHODOLOGICAL_VACUITY" not in classes


def test_prose_style_skill_not_flagged_as_description_body_gap(tmp_path: Path) -> None:
    """Invariant: a skill with a substantive description and prose
    normative rules is NOT flagged as DESCRIPTION_BODY_GAP."""
    from crucible.auditor import audit_corpus
    _write_skill(
        tmp_path,
        "prose-gap",
        "---\nname: prose-gap\ndescription: A skill that uses prose normative language to express its constraints clearly and completely.\n---\n\n"
        "# Constraints\n\nNever store secrets in logs.\n"
        "Always validate inputs at the boundary.\n"
        "Ensure the decision path is deterministic.\n",
    )
    artifact = _compile(tmp_path)
    audit = audit_corpus(artifact)
    classes = [f["class"] for f in audit["findings"]]
    assert "DESCRIPTION_BODY_GAP" not in classes
