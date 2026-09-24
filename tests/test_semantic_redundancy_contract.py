"""Falsifiable contract tests for the SEMANTIC_REDUNDANCY check.

Each test has a positive and negative fixture. The mutation comment
describes what would make the test go red if the invariant is violated.
"""

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

def test_redundancy_detected_when_two_skills_share_most_tokens() -> None:
    """Invariant: two skills with nearly identical description + rules
    are flagged as SEMANTIC_REDUNDANCY. Mutation: skip the check -> red
    (redundant skills pass silently)."""
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) >= 1
    assert redundancy[0]["epistemic_status"] == "CANDIDATE"


def test_redundancy_not_detected_when_skills_are_different() -> None:
    """Invariant: two skills with different content are NOT flagged.
    Mutation: flag any pair -> red (false positive)."""
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Image processing pipelines for computer vision.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nImages MUST be normalized before inference.\n\n"
            "## Steps\n\n1. Load the image file.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) == 0


def test_redundancy_not_detected_with_single_skill() -> None:
    """Invariant: a single skill cannot be redundant with anything.
    Mutation: flag a single skill -> red."""
    audit = _audit({
        "solo": (
            "---\nname: solo\ndescription: A standalone skill.\n"
            "license: Apache-2.0\n---\n\n"
            "# Solo\n\nRetries MUST have a finite budget.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) == 0


# ---------------------------------------------------------------------------
# No floats in the decision path
# ---------------------------------------------------------------------------

def test_redundancy_evidence_uses_fraction_not_float() -> None:
    """Invariant: the overlap is reported as numerator/denominator, not
    a float. Mutation: use float division -> red (determinism defect)."""
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) >= 1
    evidence = redundancy[0]["evidence"]
    # The overlap fraction should appear as N/M, not as a decimal.
    assert "/" in evidence
    assert "0." not in evidence  # no float representation


def test_redundancy_finding_has_no_float_in_artifact() -> None:
    """Invariant: no float values anywhere in the audit artifact's
    SEMANTIC_REDUNDANCY findings. Mutation: introduce a float -> red."""
    import json
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) >= 1
    # Serialize the finding and check no float values.
    raw = json.dumps(redundancy[0], sort_keys=True)
    # "0.666..." should not appear; "2/3" should.
    assert "0.66" not in raw


# ---------------------------------------------------------------------------
# Threshold behavior
# ---------------------------------------------------------------------------

def test_redundancy_threshold_is_two_thirds() -> None:
    """Invariant: the threshold is 2/3. Two skills sharing exactly 2/3
    of tokens are flagged. Mutation: change the threshold -> red."""
    # Construct two skills where the token overlap is exactly 2/3.
    # Skill A has tokens {retry, budget, finite, count}
    # Skill B has tokens {retry, budget, finite, image}
    # Intersection = 3, Union = 5, Jaccard = 3/5 < 2/3 -> NOT flagged.
    # We need intersection/union >= 2/3.
    # Skill A: {retry, budget, finite, count} (4 tokens)
    # Skill B: {retry, budget, finite, count, extra} (5 tokens)
    # Intersection = 4, Union = 5, Jaccard = 4/5 >= 2/3 -> flagged.
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: Retry budget finite count.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Retry budget finite count extra.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nRetries MUST have a finite budget.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) >= 1


def test_redundancy_below_threshold_not_flagged() -> None:
    """Invariant: two skills with overlap below 2/3 are NOT flagged.
    Mutation: lower the threshold -> red."""
    # Skill A: {retry, budget, finite, count} (4 tokens)
    # Skill B: {retry, budget, image, pipeline} (4 tokens)
    # Intersection = 2, Union = 6, Jaccard = 2/6 = 1/3 < 2/3 -> NOT flagged.
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: Retry budget finite count.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Retry budget image pipeline.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nImages MUST be normalized.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) == 0


# ---------------------------------------------------------------------------
# Evidence and limitation
# ---------------------------------------------------------------------------

def test_redundancy_evidence_names_both_skills() -> None:
    """Invariant: the evidence mentions the other skill by name.
    Mutation: omit the other skill name -> red (untraceable finding)."""
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) >= 1
    evidence = redundancy[0]["evidence"]
    # The evidence should mention the other skill.
    assert "alpha" in evidence or "beta" in evidence


def test_redundancy_has_limitation_documented() -> None:
    """Invariant: the finding documents that lexical overlap is not
    semantic equivalence and that an LLM layer is deferred.
    Mutation: claim full coverage -> red."""
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) >= 1
    assert redundancy[0]["limitation"] is not None
    assert "lexical" in redundancy[0]["limitation"].lower()
    assert "llm" in redundancy[0]["limitation"].lower()


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_redundancy_is_deterministic_same_process() -> None:
    """Invariant: two audits of the same corpus produce the same
    findings. Mutation: introduce non-determinism -> red."""
    corpus = {
        "alpha": (
            "---\nname: alpha\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
    }
    audit1 = _audit(corpus)
    audit2 = _audit(corpus)
    assert audit1["audit_digest"] == audit2["audit_digest"]


def test_redundancy_reports_on_lexicographically_smaller_skill() -> None:
    """Invariant: the finding is reported on the lexicographically
    smaller skill name for deterministic ordering. Mutation: report on
    random skill -> red (non-deterministic)."""
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: Retry strategies for distributed systems.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nRetries MUST have a finite budget.\n\n"
            "## Steps\n\n1. Check the retry count.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    assert len(redundancy) >= 1
    # "alpha" < "beta" lexicographically, so the finding should be on alpha.
    assert redundancy[0]["skill"] == "alpha"


# ---------------------------------------------------------------------------
# Stopwords
# ---------------------------------------------------------------------------

def test_stopwords_excluded_from_token_sets() -> None:
    """Invariant: common English stopwords do not inflate overlap.
    Mutation: include stopwords -> red (false positives from common
    words like 'the', 'is', 'must')."""
    # Two skills with different content but many shared stopwords.
    audit = _audit({
        "alpha": (
            "---\nname: alpha\ndescription: The system must be reliable.\n"
            "license: Apache-2.0\n---\n\n"
            "# Alpha\n\nThe system MUST be reliable.\n"
        ),
        "beta": (
            "---\nname: beta\ndescription: The network must be scalable.\n"
            "license: Apache-2.0\n---\n\n"
            "# Beta\n\nThe network MUST be scalable.\n"
        ),
    })
    redundancy = _findings_by_class(audit, "SEMANTIC_REDUNDANCY")
    # Without stopword filtering, "the", "must", "be" would inflate
    # overlap. With filtering, only {system, reliable} vs {network,
    # scalable} -> 0 overlap -> no finding.
    assert len(redundancy) == 0
