"""Falsifiable contract tests for the CLAIM_WITHOUT_PROVENANCE check."""

from __future__ import annotations

import tempfile
from pathlib import Path

from crucible.auditor import audit_corpus
from crucible.compiler import compile_corpus


def _audit(corpus: dict[str, str]) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for name, content in corpus.items():
            d = root / name
            d.mkdir()
            (d / "SKILL.md").write_text(content, encoding="utf-8", newline="\n")
        ir = compile_corpus(root)
        return audit_corpus(ir)


def _findings_by_class(audit: dict, cls: str) -> list[dict]:
    return [f for f in audit["findings"] if f["class"] == cls]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_claim_without_provenance_detected() -> None:
    """Invariant: a rule with a numeric claim but no provenance is flagged.
    Mutation: skip the check -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded to 5 attempts.\n"
        ),
    })
    claims = _findings_by_class(audit, "CLAIM_WITHOUT_PROVENANCE")
    assert len(claims) >= 1
    assert claims[0]["epistemic_status"] == "CANDIDATE"


def test_claim_with_provenance_not_detected() -> None:
    """Invariant: a rule with a numeric claim AND provenance is NOT flagged.
    Mutation: flag all claims -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nLatency MUST be under 50ms per NIST SP 800-53.\n"
        ),
    })
    claims = _findings_by_class(audit, "CLAIM_WITHOUT_PROVENANCE")
    assert len(claims) == 0


def test_no_claim_not_detected() -> None:
    """Invariant: a rule without any numeric claim is NOT flagged.
    Mutation: flag all rules -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded.\n"
        ),
    })
    claims = _findings_by_class(audit, "CLAIM_WITHOUT_PROVENANCE")
    assert len(claims) == 0


def test_claim_with_url_provenance_not_detected() -> None:
    """Invariant: a rule with a URL as provenance is NOT flagged.
    Mutation: ignore URL provenance -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nLatency MUST be under 50ms (see https://example.com/spec).\n"
        ),
    })
    claims = _findings_by_class(audit, "CLAIM_WITHOUT_PROVENANCE")
    assert len(claims) == 0


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------

def test_percentage_claim_extracted() -> None:
    """Invariant: a percentage claim is extracted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nCoverage MUST be at 90%.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    claims = ir["skills"][0]["rules"][0]["claims"]
    assert len(claims) >= 1
    assert claims[0]["kind"] == "percentage"


def test_time_claim_extracted() -> None:
    """Invariant: a time claim is extracted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nLatency MUST be under 50ms.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    claims = ir["skills"][0]["rules"][0]["claims"]
    assert len(claims) >= 1
    assert claims[0]["kind"] == "time"


def test_count_claim_extracted() -> None:
    """Invariant: a count claim is extracted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nRetries MUST be bounded to 3 attempts.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    claims = ir["skills"][0]["rules"][0]["claims"]
    assert len(claims) >= 1
    assert claims[0]["kind"] == "count"


def test_standard_claim_extracted() -> None:
    """Invariant: a standards reference claim is extracted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nEncryption MUST follow NIST SP 800-53.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
    claims = ir["skills"][0]["rules"][0]["claims"]
    assert len(claims) >= 1
    assert claims[0]["kind"] == "standard"


# ---------------------------------------------------------------------------
# Evidence and limitation
# ---------------------------------------------------------------------------

def test_evidence_names_rule_id() -> None:
    """Invariant: the evidence mentions the rule id. Mutation: omit
    the rule id -> red (untraceable)."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded to 5 attempts.\n"
        ),
    })
    claims = _findings_by_class(audit, "CLAIM_WITHOUT_PROVENANCE")
    assert len(claims) >= 1
    assert "rule-" in claims[0]["evidence"]


def test_evidence_names_claim_kind() -> None:
    """Invariant: the evidence mentions the claim kind. Mutation: omit
    the kind -> red (untraceable)."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded to 5 attempts.\n"
        ),
    })
    claims = _findings_by_class(audit, "CLAIM_WITHOUT_PROVENANCE")
    assert len(claims) >= 1
    assert "count" in claims[0]["evidence"]


def test_has_limitation_documented() -> None:
    """Invariant: the finding documents that provenance detection is
    pattern-based. Mutation: claim full coverage -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded to 5 attempts.\n"
        ),
    })
    claims = _findings_by_class(audit, "CLAIM_WITHOUT_PROVENANCE")
    assert len(claims) >= 1
    assert claims[0]["limitation"] is not None
    assert "pattern" in claims[0]["limitation"].lower()


def test_has_source_evidence() -> None:
    """Invariant: the finding points to the rule. Mutation: emit
    without source_span -> red."""
    audit = _audit({
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded to 5 attempts.\n"
        ),
    })
    claims = _findings_by_class(audit, "CLAIM_WITHOUT_PROVENANCE")
    assert len(claims) >= 1
    assert claims[0]["source_span"] is not None
    assert claims[0]["rule_id"] is not None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_is_deterministic() -> None:
    """Invariant: two audits produce the same digest. Mutation: introduce
    non-determinism -> red."""
    corpus = {
        "test": (
            "---\nname: test\ndescription: T.\nlicense: Apache-2.0\n---\n\n"
            "# T\n\nRetries MUST be bounded to 5 attempts.\n"
        ),
    }
    audit1 = _audit(corpus)
    audit2 = _audit(corpus)
    assert audit1["audit_digest"] == audit2["audit_digest"]


def test_not_in_limitations() -> None:
    """Invariant: CLAIM_WITHOUT_PROVENANCE is no longer in the abstained
    limitations list. Mutation: leave it in limitations -> red."""
    audit = _audit({
        "empty": (
            "---\nname: empty\ndescription: E.\nlicense: Apache-2.0\n---\n\n"
            "# E\n\nNo rules here.\n"
        ),
    })
    limitation_classes = [l["check_class"] for l in audit["limitations"]]
    assert "CLAIM_WITHOUT_PROVENANCE" not in limitation_classes
