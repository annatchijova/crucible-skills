"""Compile SKILL.md files into a deterministic, source-addressable IR."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .ir import SCHEMA_VERSION, digest_bytes, digest_payload

# Match "MUST NOT" / "SHOULD NOT" (with space) before bare MUST/SHOULD/MAY
# so that negated modalities are captured correctly.
_MODALITY = re.compile(r"\b(MUST\s+NOT|SHOULD\s+NOT|MUST|SHOULD|MAY)\b")
_FRONTMATTER_LINE = re.compile(r"^(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.*)$")
_URL = re.compile(r"https?://[^\s)>]+")
_HEADING = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(?P<value>.+?)\s*$")
_NUMBERED = re.compile(r"^\s*(?P<num>\d+)\.\s+(?P<value>.+?)\s*$")
_PROCEDURAL_SECTIONS = {"steps", "procedure", "how to", "how", "process", "workflow", "method"}


def compile_corpus(root: Path | str) -> dict[str, Any]:
    """Compile every ``SKILL.md`` below *root* into a canonical artifact."""
    corpus_root = Path(root).resolve()
    if not corpus_root.is_dir():
        raise ValueError(f"corpus root is not a directory: {root}")

    paths = sorted(corpus_root.rglob("SKILL.md"), key=lambda p: p.relative_to(corpus_root).as_posix())
    if not paths:
        raise ValueError(f"corpus contains no SKILL.md files: {root}")

    skills = [_compile_skill(path, corpus_root) for path in paths]
    names = [skill["identity"]["name"] for skill in skills]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate skill name(s): {', '.join(duplicates)}")

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "skills": skills,
    }
    payload["artifact_digest"] = digest_payload(payload)
    return payload


def _compile_skill(path: Path, root: Path) -> dict[str, Any]:
    relative_path = path.relative_to(root).as_posix()
    if path.is_symlink():
        raise ValueError(f"{relative_path}: symlinked SKILL.md is not allowed")
    raw_bytes = path.read_bytes()
    raw = raw_bytes.decode("utf-8")
    lines = raw.splitlines()
    frontmatter, body_start = _parse_frontmatter(lines, relative_path)
    name = frontmatter.get("name")
    if not name:
        raise ValueError(f"{relative_path}: frontmatter requires name")
    if not frontmatter.get("description"):
        raise ValueError(f"{relative_path}: frontmatter requires description")

    sections = _section_ranges(lines, body_start)
    return {
        "identity": {
            "name": name,
            "source_path": relative_path,
            "content_digest": digest_bytes(raw_bytes),
        },
        "metadata": {key: frontmatter[key] for key in sorted(frontmatter)},
        "trigger": _extract_trigger(frontmatter.get("description", "")),
        "rules": _extract_rules(lines, body_start),
        "checks": _extract_checks(lines, sections),
        "procedural_steps": _extract_procedural_steps(lines, sections, body_start),
        "relations": {
            "composes_with": _extract_relations(lines, sections, "composes with"),
            "delegates_to": _extract_relations(lines, sections, "delegates to"),
        },
        "references": sorted(set(_URL.findall(raw))),
    }


def _parse_frontmatter(lines: list[str], relative_path: str) -> tuple[dict[str, Any], int]:
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{relative_path}: missing frontmatter opening delimiter")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise ValueError(f"{relative_path}: unterminated frontmatter") from exc

    metadata: dict[str, Any] = {}
    current_mapping: dict[str, str] | None = None
    index = 1
    while index < end:
        line_number = index + 1
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        match = _FRONTMATTER_LINE.match(line.strip())
        if not match:
            raise ValueError(f"{relative_path}:{line_number}: unsupported frontmatter line")
        key = match.group("key")
        value = _strip_scalar(match.group("value"))
        block_marker = match.group("value").strip()
        if line.startswith((" ", "\t")):
            if current_mapping is None:
                raise ValueError(f"{relative_path}:{line_number}: nested value without mapping")
            current_mapping[key] = value
        elif block_marker in {">", "|", ">-", "|-", ">+", "|+"}:
            folded = block_marker[0] == ">"
            block: list[str] = []
            index += 1
            while index < end and (not lines[index].strip() or lines[index].startswith((" ", "\t"))):
                block.append(lines[index].strip())
                index += 1
            separator = " " if folded else "\n"
            metadata[key] = separator.join(part for part in block if part)
            current_mapping = None
            continue
        elif value:
            metadata[key] = value
            current_mapping = None
        else:
            current_mapping = {}
            metadata[key] = current_mapping
        index += 1
    return metadata, end + 1


def _strip_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _section_ranges(lines: list[str], body_start: int) -> dict[str, tuple[int, int]]:
    headings: list[tuple[int, str]] = []
    for index in range(body_start, len(lines)):
        match = _HEADING.match(lines[index])
        if match:
            headings.append((index, match.group("title").strip().lower()))
    ranges: dict[str, tuple[int, int]] = {}
    for position, (start, title) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        ranges[title] = (start + 1, end)
    return ranges


# Trigger extraction patterns. These capture the clause that describes
# when the skill should be activated, from the description text.
_TRIGGER_PATTERNS = [
    re.compile(
        r"\buse\s+(?:this skill\s+)?(?:whenever|when|if|for)\b\s*(.+?)(?:[.;]|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\btrigger(?:s|ed)?\s+(?:on|when|for)\b\s*(.+?)(?:[.;]|\Z)",
        re.IGNORECASE | re.DOTALL,
    ),
]


def _extract_trigger(description: str) -> dict[str, Any]:
    """Extract the trigger clause from a skill's description.

    Returns a dict with:
    - text: the raw trigger clause text (or "" if no trigger found)
    - found: whether a trigger pattern was matched
    """
    for pattern in _TRIGGER_PATTERNS:
        match = pattern.search(description)
        if match:
            raw = match.group(1).strip()
            # Truncate at reasonable length to avoid capturing the entire
            # description as a trigger clause.
            if len(raw) > 300:
                raw = raw[:300]
            return {"text": raw, "found": True}
    return {"text": "", "found": False}


def _extract_rules(lines: list[str], body_start: int) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for index in range(body_start, len(lines)):
        match = _MODALITY.search(lines[index])
        if match:
            raw_modality = match.group(1)
            # Normalize "MUST NOT" -> "MUST_NOT", "SHOULD NOT" -> "SHOULD_NOT"
            modality = raw_modality.replace(" ", "_").upper()
            text = lines[index].strip()
            subject = _extract_subject(text, raw_modality)
            conditions = _extract_conditions(text)
            rules.append({
                "id": f"rule-{len(rules) + 1:04d}",
                "extraction_status": "candidate",
                "modality": modality,
                "subject": subject,
                "conditions": conditions,
                "text": text,
                "source_span": {"line": index + 1, "column": match.start(1) + 1},
            })
    return rules


# Condition extraction patterns. Each pattern captures a condition
# clause from rule text. The type determines how the condition affects
# the rule's polarity:
#   "exception" — inverts the modality for this condition (except for, unless)
#   "scope" — restricts the modality to this condition (when, if, for, during, while)
_CONDITION_PATTERNS = [
    # Exception patterns (invert polarity).
    (re.compile(r"\bexcept\s+(?:for\s+)?(.+?)(?:[.;,]|$)", re.IGNORECASE), "exception"),
    (re.compile(r"\bunless\s+(.+?)(?:[.;,]|$)", re.IGNORECASE), "exception"),
    # Scope patterns (restrict polarity).
    (re.compile(r"\bwhen\s+(.+?)(?:[.;,]|$)", re.IGNORECASE), "scope"),
    (re.compile(r"\bif\s+(.+?)(?:[.;,]|$)", re.IGNORECASE), "scope"),
    (re.compile(r"\bduring\s+(.+?)(?:[.;,]|$)", re.IGNORECASE), "scope"),
    (re.compile(r"\bwhile\s+(.+?)(?:[.;,]|$)", re.IGNORECASE), "scope"),
    # "for X" is ambiguous (could be a recipient), but in normative rules
    # it often introduces a scope condition. We extract it as scope.
    (re.compile(r"\bfor\s+(.+?)(?:[.;,]|$)", re.IGNORECASE), "scope"),
]


def _extract_conditions(rule_text: str) -> list[dict[str, str]]:
    """Extract condition clauses from a normative rule.

    Returns a list of {text, type} where type is "exception" (inverts
    the modality) or "scope" (restricts the modality). The text is
    normalized to lowercase and stripped.
    """
    conditions: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pattern, cond_type in _CONDITION_PATTERNS:
        for match in pattern.finditer(rule_text):
            raw = match.group(1).strip().lower()
            # Strip articles and trailing punctuation.
            for article in ("the ", "a ", "an "):
                if raw.startswith(article):
                    raw = raw[len(article):]
            raw = raw.strip(" ,;:.")
            if len(raw) < 2:
                continue
            key = (raw, cond_type)
            if key in seen:
                continue
            seen.add(key)
            conditions.append({"text": raw, "type": cond_type})
    # Sort for determinism.
    conditions.sort(key=lambda c: (c["text"], c["type"]))
    return conditions


def _extract_subject(rule_text: str, raw_modality: str) -> str:
    """Extract the subject of a normative rule.

    The subject is the noun phrase before the modal verb, normalized
    to lowercase with leading articles and markdown formatting stripped.
    If the modal verb is at the start of the line (after stripping
    markdown), there is no explicit subject and we return "".
    """
    idx = rule_text.find(raw_modality)
    if idx <= 0:
        return ""
    subject = rule_text[:idx].strip()
    # Strip markdown formatting: bold (**), italic (*), code (`), underline (_)
    subject = re.sub(r"\*+|`+|_+", " ", subject)
    # Strip leading list markers, table pipes, heading markers
    subject = re.sub(r"^[\s|\-*+#>]+", "", subject)
    # Normalize: lowercase, strip leading articles, strip trailing punctuation
    subject = subject.lower()
    for article in ("the ", "a ", "an ", "you ", "your "):
        if subject.startswith(article):
            subject = subject[len(article):]
    subject = subject.strip(" ,;:.")
    return subject


def _extract_procedural_steps(
    lines: list[str],
    sections: dict[str, tuple[int, int]],
    body_start: int,
) -> list[dict[str, Any]]:
    """Extract procedural steps from a skill body.

    Procedural steps are found in:
    - Sections titled "## Steps", "## Procedure", "## How to", "## Process", etc.
    - Numbered lists anywhere in the body (1. ... 2. ...)
    - Bullet lists with action verbs in procedural sections
    """
    steps: list[dict[str, Any]] = []
    seen_lines: set[int] = set()

    # 1. Extract from procedural sections.
    for title, (start, end) in sections.items():
        if not any(ps in title for ps in _PROCEDURAL_SECTIONS):
            continue
        for index in range(start, end):
            if index in seen_lines:
                continue
            # Numbered list
            num_match = _NUMBERED.match(lines[index])
            if num_match:
                steps.append({
                    "id": f"step-{len(steps) + 1:04d}",
                    "text": num_match.group("value"),
                    "source_span": {"line": index + 1, "column": 1},
                })
                seen_lines.add(index)
                continue
            # Bullet list
            bullet_match = _BULLET.match(lines[index])
            if bullet_match:
                steps.append({
                    "id": f"step-{len(steps) + 1:04d}",
                    "text": bullet_match.group("value"),
                    "source_span": {"line": index + 1, "column": 1},
                })
                seen_lines.add(index)

    # 2. Extract numbered lists from anywhere in the body.
    for index in range(body_start, len(lines)):
        if index in seen_lines:
            continue
        num_match = _NUMBERED.match(lines[index])
        if num_match:
            steps.append({
                "id": f"step-{len(steps) + 1:04d}",
                "text": num_match.group("value"),
                "source_span": {"line": index + 1, "column": 1},
            })
            seen_lines.add(index)

    return steps


def _extract_checks(lines: list[str], sections: dict[str, tuple[int, int]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for title, (start, end) in sections.items():
        if "check" not in title and "verification" not in title:
            continue
        for index in range(start, end):
            match = _BULLET.match(lines[index])
            if match:
                checks.append({
                    "id": f"check-{len(checks) + 1:04d}",
                    "text": match.group("value"),
                    "source_span": {"line": index + 1, "column": 1},
                })
    return checks


def _extract_relations(lines: list[str], sections: dict[str, tuple[int, int]], section_name: str) -> list[str]:
    relations: list[str] = []
    for title, (start, end) in sections.items():
        if section_name not in title:
            continue
        for index in range(start, end):
            match = _BULLET.match(lines[index])
            if match:
                relations.append(match.group("value"))
    return sorted(set(relations))
