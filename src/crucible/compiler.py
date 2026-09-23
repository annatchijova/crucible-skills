"""Compile SKILL.md files into a deterministic, source-addressable IR."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .ir import SCHEMA_VERSION, digest_bytes, digest_payload

_MODALITY = re.compile(r"\b(MUST_NOT|SHOULD_NOT|MUST|SHOULD|MAY)\b")
_FRONTMATTER_LINE = re.compile(r"^(?P<key>[A-Za-z0-9_-]+):\s*(?P<value>.*)$")
_URL = re.compile(r"https?://[^\s)>]+")
_HEADING = re.compile(r"^(#{1,6})\s+(?P<title>.+?)\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(?P<value>.+?)\s*$")


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
        "rules": _extract_rules(lines, body_start),
        "checks": _extract_checks(lines, sections),
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


def _extract_rules(lines: list[str], body_start: int) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for index in range(body_start, len(lines)):
        match = _MODALITY.search(lines[index])
        if match:
            rules.append({
                "id": f"rule-{len(rules) + 1:04d}",
                "extraction_status": "candidate",
                "modality": match.group(1),
                "text": lines[index].strip(),
                "source_span": {"line": index + 1, "column": match.start(1) + 1},
            })
    return rules


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
