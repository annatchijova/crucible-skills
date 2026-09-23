from __future__ import annotations

import json
from pathlib import Path

from crucible.compiler import compile_corpus


def _write_skill(root: Path, name: str, body: str) -> Path:
    skill = root / name
    skill.mkdir()
    (skill / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")
    return skill


def test_compiler_emits_versioned_source_addressable_ir(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "bounded-retries",
        """---\nname: bounded-retries\ndescription: Bound retries for operations.\nlicense: Apache-2.0\n---\n\n# Bounded retries\n\nRetries MUST have a finite budget.\n\nThe operation SHOULD be idempotent before retrying.\n\n## Checks\n\n- Verify the retry budget is present.\n\n## Composes with\n\n- irreversible-action-gate\n\n## References\n\n- https://example.com/retry-guidance\n""",
    )

    artifact = compile_corpus(tmp_path)

    assert artifact["schema_version"] == "skill-ir/v1"
    assert artifact["skills"][0]["identity"]["name"] == "bounded-retries"
    assert artifact["skills"][0]["identity"]["content_digest"].startswith("sha256:")
    assert [rule["modality"] for rule in artifact["skills"][0]["rules"]] == ["MUST", "SHOULD"]
    assert artifact["skills"][0]["rules"][0]["extraction_status"] == "candidate"
    assert artifact["skills"][0]["rules"][0]["source_span"]["line"] == 9
    assert artifact["skills"][0]["relations"]["composes_with"] == ["irreversible-action-gate"]
    assert artifact["skills"][0]["references"] == ["https://example.com/retry-guidance"]


def test_same_corpus_has_identical_canonical_bytes_and_digest(tmp_path: Path) -> None:
    _write_skill(tmp_path, "z-skill", "---\nname: z-skill\ndescription: Z\n---\n\nA MAY run.\n")
    _write_skill(tmp_path, "a-skill", "---\nname: a-skill\ndescription: A\n---\n\nB MUST stop.\n")

    first = compile_corpus(tmp_path)
    second = compile_corpus(tmp_path)

    assert first == second
    assert first["artifact_digest"] == second["artifact_digest"]
    assert json.dumps(first, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def test_invalid_frontmatter_fails_closed_with_path(tmp_path: Path) -> None:
    skill = tmp_path / "broken"
    skill.mkdir()
    (skill / "SKILL.md").write_text("# no frontmatter\n", encoding="utf-8")

    try:
        compile_corpus(tmp_path)
    except ValueError as exc:
        assert "broken/SKILL.md" in str(exc)
        assert "frontmatter" in str(exc).lower()
    else:
        raise AssertionError("invalid frontmatter must not compile")


def test_compiler_preserves_simple_nested_frontmatter_metadata(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "nested",
        """---\nname: nested\ndescription: Nested metadata\nmetadata:\n  short-description: A short description\n---\n\nA MUST remain explicit.\n""",
    )

    artifact = compile_corpus(tmp_path)

    assert artifact["skills"][0]["metadata"]["metadata"]["short-description"] == "A short description"


def test_compiler_supports_folded_description_block(tmp_path: Path) -> None:
    _write_skill(
        tmp_path,
        "folded",
        """---\nname: folded\ndescription: >\n  First line of the description.\n  Second line remains part of it.\n---\n\nA MUST remain explicit.\n""",
    )

    artifact = compile_corpus(tmp_path)

    assert artifact["skills"][0]["metadata"]["description"] == (
        "First line of the description. Second line remains part of it."
    )


def test_symlinked_skill_fails_closed(tmp_path: Path) -> None:
    target = _write_skill(tmp_path, "target", "---\nname: target\ndescription: Target\n---\n")
    link = tmp_path / "linked"
    link.mkdir()
    (link / "SKILL.md").symlink_to(target / "SKILL.md")

    try:
        compile_corpus(tmp_path)
    except ValueError as exc:
        assert "symlink" in str(exc).lower()
    else:
        raise AssertionError("symlinked skill must not compile")


def test_duplicate_skill_names_fail_closed(tmp_path: Path) -> None:
    body = "---\nname: duplicate\ndescription: Same identity\n---\n"
    _write_skill(tmp_path, "one", body)
    _write_skill(tmp_path, "two", body)

    try:
        compile_corpus(tmp_path)
    except ValueError as exc:
        assert "duplicate skill name" in str(exc).lower()
    else:
        raise AssertionError("duplicate skill names must not compile")
