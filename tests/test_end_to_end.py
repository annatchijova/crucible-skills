"""End-to-end integration test: L1 -> L2 -> L3 -> L4 -> L5 -> L6.

This test verifies that all six levels compose into a coherent pipeline.
It does NOT test each level's internal contract (that's in the per-level
test files). It tests that the levels connect and produce artifacts that
feed each other correctly.

This is the smoke test that proves CRUCIBLE is a system, not a collection
of independent modules.
"""

from __future__ import annotations

from crucible.auditor import audit_corpus
from crucible.behavioral import LocalExecutor, run_behavioral_differential
from crucible.bob import RuleBasedProposer, run_bob_workflow
from crucible.compiler import compile_corpus
from crucible.graph import build_composition_graph
from crucible.mutation import run_mutation_lab


def test_full_pipeline_l1_through_l6() -> None:
    """L1 IR -> L2 audit -> L3 graph -> L4 mutation -> L5 behavioral -> L6 Bob.

    Each level consumes the previous level's artifact. This test verifies
    that the chain holds end-to-end.
    """
    # L1: compile a small corpus.
    import tempfile
    from pathlib import Path

    corpus = {
        "retrier": (
            "---\nname: retrier\n"
            "description: Retry with a bounded budget. "
            "Pairs with gate.\n"
            "license: Apache-2.0\n---\n\n"
            "# Bounded retries\n\n"
            "Retries MUST have a finite budget.\n\n"
            "## Checks\n\n- Verify budget.\n"
            "## Composes with\n\n- gate\n"
        ),
        "gate": (
            "---\nname: gate\n"
            "description: Gate irreversible operations.\n"
            "license: Apache-2.0\n---\n\n"
            "# Gate\n\n"
            "Operations MUST be bounded.\n\n"
            "## Checks\n\n- Verify bounded.\n"
        ),
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        for name, content in corpus.items():
            d = root / name
            d.mkdir()
            (d / "SKILL.md").write_text(content, encoding="utf-8", newline="\n")

        # L1: compile.
        ir = compile_corpus(root)
        assert ir["schema_version"] == "skill-ir/v1"
        assert len(ir["skills"]) == 2
        ir_digest = ir["artifact_digest"]
        assert ir_digest.startswith("sha256:")

        # L2: audit (consumes L1 IR).
        audit = audit_corpus(ir)
        assert audit["audit_version"] == "crucible-audit/v1"
        assert audit["input_artifact_digest"] == ir_digest
        audit_digest = audit["audit_digest"]
        assert audit_digest.startswith("sha256:")

        # L3: graph (consumes L1 IR + L2 audit).
        graph = build_composition_graph(ir, audit)
        assert graph["graph_version"] == "crucible-graph/v1"
        assert graph["input_ir_digest"] == ir["artifact_digest"]
        assert graph["input_audit_digest"] == audit_digest
        assert len(graph["edges"]) >= 1  # retrier -> gate

    # L4: mutation lab (uses its own built-in fixture).
    mutation_report = run_mutation_lab()
    assert mutation_report["mutation_version"] == "crucible-mutation/v1"
    assert len(mutation_report["results"]) == 8
    assert mutation_report["summary"]["total"] == 8

    # L5: behavioral differential (uses local executor).
    behavioral_report = run_behavioral_differential(executor=LocalExecutor())
    assert behavioral_report["behavioral_version"] == "crucible-behavioral/v1"
    assert len(behavioral_report["runs"]) == 4
    # The mutant must fail P3 (unbounded retry).
    mutant = next(
        r for r in behavioral_report["runs"]
        if r["variant_id"] == "V3-mutant-polarity-inversion"
    )
    p3 = next(
        o for o in mutant["observations"]
        if o["property_id"] == "P3-no-unbounded-retry"
    )
    assert p3["status"] == "FAIL"

    # L6: Bob workflow (uses its own built-in fixture).
    bob_report = run_bob_workflow(proposer=RuleBasedProposer())
    assert bob_report["bob_version"] == "crucible-bob/v1"
    assert bob_report["outcome"] == "ACCEPTED"
    assert bob_report["original_finding_gone"] is True
    assert bob_report["repaired_finding_count"] == 0

    # L7: closed repair loop (uses local executor).
    from crucible.repair_loop import run_repair_loop, LOOP_VERSION
    loop_report = run_repair_loop(executor=LocalExecutor())
    assert loop_report["loop_version"] == LOOP_VERSION
    assert loop_report["outcome"] == "ACCEPTED"
    assert loop_report["original_finding_gone"] is True
    assert loop_report["behavioral_replay"]["regression"] is False
    assert loop_report["loop_digest"].startswith("sha256:")


def test_chain_of_custody_is_unbroken() -> None:
    """Every artifact carries the digests of its inputs.

    L2 carries L1's digest. L3 carries L1 + L2 digests. This test verifies
    that the chain of custody is unbroken across the pipeline.
    """
    import tempfile
    from pathlib import Path

    corpus = {
        "skill-a": (
            "---\nname: skill-a\ndescription: Skill A.\n"
            "license: Apache-2.0\n---\n\n"
            "# A\n\nA MUST be bounded.\n\n## Checks\n\n- Verify A.\n"
        ),
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        d = root / "skill-a"
        d.mkdir()
        (d / "SKILL.md").write_text(
            corpus["skill-a"], encoding="utf-8", newline="\n"
        )

        ir = compile_corpus(root)
        audit = audit_corpus(ir)
        graph = build_composition_graph(ir, audit)

    # L2 carries L1's digest.
    assert audit["input_artifact_digest"] == ir["artifact_digest"]

    # L3 carries L1 + L2 digests.
    assert graph["input_ir_digest"] == ir["artifact_digest"]
    assert graph["input_audit_digest"] == audit["audit_digest"]

    # L4 carries the base audit digest.
    mutation_report = run_mutation_lab()
    assert mutation_report["base_audit_digest"].startswith("sha256:")
    for result in mutation_report["results"]:
        assert result["base_audit_digest"] == mutation_report["base_audit_digest"]

    # L5 carries the task digest.
    behavioral_report = run_behavioral_differential(executor=LocalExecutor())
    assert behavioral_report["task_digest"].startswith("sha256:")

    # L6 carries base + repaired audit digests.
    bob_report = run_bob_workflow(proposer=RuleBasedProposer())
    assert bob_report["base_audit_digest"].startswith("sha256:")
    assert bob_report["repaired_audit_digest"].startswith("sha256:")

    # L7 carries base + repaired audit digests + loop digest.
    from crucible.repair_loop import run_repair_loop
    loop_report = run_repair_loop(executor=LocalExecutor())
    assert loop_report["base_audit_digest"].startswith("sha256:")
    assert loop_report["repaired_audit_digest"].startswith("sha256:")
    assert loop_report["loop_digest"].startswith("sha256:")


def test_all_artifacts_are_versioned() -> None:
    """Every artifact carries a schema version. This is the contract that
    makes the system forward-compatible."""
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
        ir = compile_corpus(root)
        audit = audit_corpus(ir)
        graph = build_composition_graph(ir, audit)

    assert ir["schema_version"] == "skill-ir/v1"
    assert audit["audit_version"] == "crucible-audit/v1"
    assert graph["graph_version"] == "crucible-graph/v1"

    mutation_report = run_mutation_lab()
    assert mutation_report["mutation_version"] == "crucible-mutation/v1"

    behavioral_report = run_behavioral_differential(executor=LocalExecutor())
    assert behavioral_report["behavioral_version"] == "crucible-behavioral/v1"

    bob_report = run_bob_workflow(proposer=RuleBasedProposer())
    assert bob_report["bob_version"] == "crucible-bob/v1"

    from crucible.repair_loop import run_repair_loop
    loop_report = run_repair_loop(executor=LocalExecutor())
    assert loop_report["loop_version"] == "crucible-repair-loop/v1"
