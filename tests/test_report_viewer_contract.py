"""Falsifiable contract tests for L8 (report + viewer).

The key invariant: no consumer has independent decision logic. The report
generator delegates to each level's runner. The viewer reads a sealed
artifact and renders it; it does NOT compute anything.
"""

from __future__ import annotations

import json

from crucible.behavioral import LocalExecutor
from crucible.report import REPORT_VERSION, run_full_report
from crucible.viewer import render_artifact_html


# ---------------------------------------------------------------------------
# Report: sealed composite artifact
# ---------------------------------------------------------------------------

def test_report_is_sealed() -> None:
    """Invariant: the report carries a SHA-256 digest. Mutation: skip
    sealing -> red."""
    report = run_full_report(executor=LocalExecutor())
    assert report["report_version"] == REPORT_VERSION
    assert report["report_digest"].startswith("sha256:")


def test_report_contains_all_levels() -> None:
    """Invariant: the report contains L4-L7 (L1-L3 are optional, require
    a corpus root). Mutation: skip a level -> red."""
    report = run_full_report(executor=LocalExecutor())
    levels = report["levels"]
    assert "L4" in levels
    assert "L5" in levels
    assert "L6" in levels
    assert "L7" in levels


def test_report_includes_corpus_levels_when_given() -> None:
    """Invariant: when a corpus root is given, L1-L3 are included.
    Mutation: skip corpus levels even when root is given -> red."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nS MUST be bounded.\n\n## Checks\n\n- Verify.\n",
            encoding="utf-8", newline="\n",
        )
        report = run_full_report(corpus_root=str(root), executor=LocalExecutor())
        levels = report["levels"]
        assert "L1" in levels
        assert "L2" in levels
        assert "L3" in levels


def test_report_nebius_blocked_is_honest() -> None:
    """Invariant: without NEBIUS_API_KEY, the report documents Nebius as
    BLOCKED. Mutation: simulate Nebius -> red."""
    report = run_full_report(executor=LocalExecutor())
    assert report["nebius_blocked"] is True
    assert "NEBIUS_API_KEY" in (report["block_reason"] or "")


def test_report_determinism_same_process() -> None:
    """Invariant: two runs in the same process produce the same digest.
    Mutation: non-deterministic field -> red."""
    r1 = run_full_report(executor=LocalExecutor())
    r2 = run_full_report(executor=LocalExecutor())
    assert r1["report_digest"] == r2["report_digest"]


def test_report_determinism_cross_process() -> None:
    """Invariant: two runs in different processes produce the same digest.
    Mutation: PYTHONHASHSEED or set ordering leaks -> red."""
    import subprocess
    results = []
    for _ in range(2):
        out = subprocess.run(
            ["python3", "-c",
             "from crucible.report import run_full_report; "
             "from crucible.behavioral import LocalExecutor; "
             "r = run_full_report(executor=LocalExecutor()); "
             "print(r['report_digest'])"],
            capture_output=True, text=True,
            env={"PYTHONPATH": "src", "PATH": "/usr/bin:/usr/local/bin",
                 "PYTHONHASHSEED": "0"},
        )
        results.append(out.stdout.strip())
    assert results[0] == results[1], f"cross-process divergence: {results}"


# ---------------------------------------------------------------------------
# Report: no independent decision logic
# ---------------------------------------------------------------------------

def test_report_delegates_to_levels() -> None:
    """Invariant: the report delegates to each level's runner. The L4
    kill rate in the report matches the L4 mutation lab directly.
    Mutation: report re-implements level logic -> red (would diverge)."""
    from crucible.mutation import run_mutation_lab
    mutation = run_mutation_lab()
    report = run_full_report(executor=LocalExecutor())
    assert report["levels"]["L4"]["kill_rate"] == mutation["summary"]["kill_rate"]
    assert report["levels"]["L4"]["mutation_digest"] == mutation["mutation_digest"]


def test_report_l7_outcome_matches_loop() -> None:
    """Invariant: the L7 outcome in the report matches the repair loop
    directly. Mutation: report re-implements loop logic -> red."""
    from crucible.repair_loop import run_repair_loop
    loop = run_repair_loop(executor=LocalExecutor())
    report = run_full_report(executor=LocalExecutor())
    assert report["levels"]["L7"]["outcome"] == loop["outcome"]
    assert report["levels"]["L7"]["loop_digest"] == loop["loop_digest"]


# ---------------------------------------------------------------------------
# Viewer: read-only projection
# ---------------------------------------------------------------------------

def test_viewer_produces_html() -> None:
    """Invariant: the viewer produces a non-empty HTML string.
    Mutation: return empty string -> red."""
    report = run_full_report(executor=LocalExecutor())
    html_output = render_artifact_html(report)
    assert html_output.startswith("<!DOCTYPE html>")
    assert "</html>" in html_output
    assert len(html_output) > 1000


def test_viewer_renders_version() -> None:
    """Invariant: the HTML contains the artifact version. Mutation: skip
    version rendering -> red."""
    report = run_full_report(executor=LocalExecutor())
    html_output = render_artifact_html(report)
    assert "crucible-report/v1" in html_output


def test_viewer_renders_digest() -> None:
    """Invariant: the HTML contains the report digest. Mutation: skip
    digest rendering -> red."""
    report = run_full_report(executor=LocalExecutor())
    html_output = render_artifact_html(report)
    assert report["report_digest"][:40] in html_output


def test_viewer_renders_nebius_blocked() -> None:
    """Invariant: the HTML shows Nebius BLOCKED status. Mutation: hide
    blocked status -> red."""
    report = run_full_report(executor=LocalExecutor())
    html_output = render_artifact_html(report)
    assert "BLOCKED" in html_output


def test_viewer_renders_levels() -> None:
    """Invariant: the HTML contains all level sections. Mutation: skip
    a level -> red."""
    report = run_full_report(executor=LocalExecutor())
    html_output = render_artifact_html(report)
    for level_id in ("L4", "L5", "L6", "L7"):
        assert level_id in html_output


def test_viewer_renders_mutation_results() -> None:
    """Invariant: the HTML contains mutation results. Mutation: skip
    mutation rendering -> red."""
    from crucible.mutation import run_mutation_lab
    mutation = run_mutation_lab()
    html_output = render_artifact_html(mutation)
    assert "Mutation Results" in html_output
    assert "KILLED" in html_output or "SURVIVED" in html_output


def test_viewer_renders_findings() -> None:
    """Invariant: the HTML renders audit findings. Mutation: skip
    findings -> red."""
    import tempfile
    from pathlib import Path
    from crucible.compiler import compile_corpus
    from crucible.auditor import audit_corpus

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: skill\ndescription: S.\nlicense: Apache-2.0\n---\n\n"
            "# S\n\nS MUST be bounded.\n",
            encoding="utf-8", newline="\n",
        )
        ir = compile_corpus(root)
        audit = audit_corpus(ir)
        html_output = render_artifact_html(audit)
        assert "Findings" in html_output
        assert "REQUIREMENT_WITHOUT_CHECK" in html_output


def test_viewer_renders_behavioral_replay() -> None:
    """Invariant: the HTML renders behavioral replay when present.
    Mutation: skip behavioral replay -> red."""
    from crucible.repair_loop import run_repair_loop
    loop = run_repair_loop(executor=LocalExecutor())
    html_output = render_artifact_html(loop)
    assert "Behavioral Replay" in html_output
    assert "Regression" in html_output


def test_viewer_does_not_compute_anything() -> None:
    """Invariant: the viewer does NOT re-compute digests or outcomes.
    It only renders what's in the JSON. Mutation: viewer computes
    digests -> red (would produce a different digest than the artifact)."""
    report = run_full_report(executor=LocalExecutor())
    html_output = render_artifact_html(report)
    # The viewer must contain the digest from the artifact, not a
    # re-computed one. We verify by checking that the exact digest
    # string appears.
    assert report["report_digest"] in html_output
    # The viewer must NOT contain any script tags (no computation).
    assert "<script" not in html_output


# ---------------------------------------------------------------------------
# Viewer: works with any artifact type
# ---------------------------------------------------------------------------

def test_viewer_works_with_mutation_artifact() -> None:
    """Invariant: the viewer works with any artifact type, not just
    composite reports. Mutation: viewer only handles reports -> red."""
    from crucible.mutation import run_mutation_lab
    mutation = run_mutation_lab()
    html_output = render_artifact_html(mutation)
    assert "crucible-mutation/v1" in html_output
    assert mutation["mutation_digest"] in html_output


def test_viewer_works_with_bob_artifact() -> None:
    """Invariant: the viewer works with Bob workflow artifacts.
    Mutation: viewer only handles reports -> red."""
    from crucible.bob import run_bob_workflow, RuleBasedProposer
    bob = run_bob_workflow(proposer=RuleBasedProposer())
    html_output = render_artifact_html(bob)
    assert "crucible-bob/v1" in html_output
    assert "ACCEPTED" in html_output
