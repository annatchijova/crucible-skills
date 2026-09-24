"""Falsifiable contract tests for the eight L10 engineering checks.

Each test names the invariant it defends and the mutation it would catch.
Each check has a positive test (fires on the defect) and a negative test
(does not fire on a clean skill).
"""
from __future__ import annotations

from pathlib import Path

from crucible.auditor import audit_corpus
from crucible.compiler import compile_corpus


def _write_skill(root: Path, name: str, body: str) -> Path:
    skill = root / name
    skill.mkdir()
    (skill / "SKILL.md").write_text(body, encoding="utf-8", newline="\n")
    return skill


def _audit(root: Path) -> dict:
    return audit_corpus(compile_corpus(root))


def _classes(findings: list[dict]) -> list[str]:
    return sorted(f["class"] for f in findings)


# ---------------------------------------------------------------------------
# SECRET_IN_OUTPUT
# ---------------------------------------------------------------------------

def test_secret_in_output_fires_on_log_secret(tmp_path: Path) -> None:
    """Invariant: logging a secret without protection is a defect.
    Mutation: remove the secret-output check -> this test goes red."""
    _write_skill(
        tmp_path,
        "leaky",
        "---\nname: leaky\ndescription: Logs secrets.\n---\n\n"
        "1. Log the API key for debugging.\n",
    )
    audit = _audit(tmp_path)
    assert "SECRET_IN_OUTPUT" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "SECRET_IN_OUTPUT")
    assert finding["epistemic_status"] == "CANDIDATE"


def test_secret_in_output_does_not_fire_on_redacted(tmp_path: Path) -> None:
    """Invariant: logging a redacted secret is not a defect.
    Mutation: always emit SECRET_IN_OUTPUT -> this test goes red."""
    _write_skill(
        tmp_path,
        "safe",
        "---\nname: safe\ndescription: Redacts secrets.\n---\n\n"
        "1. Log the API key after redacting it.\n",
    )
    audit = _audit(tmp_path)
    assert "SECRET_IN_OUTPUT" not in _classes(audit["findings"])


def test_secret_in_output_fires_on_step(tmp_path: Path) -> None:
    """Invariant: a step that prints a secret is also a defect.
    Mutation: only check rules, not steps -> this test goes red."""
    _write_skill(
        tmp_path,
        "leaky-step",
        "---\nname: leaky-step\ndescription: Logs secrets in steps.\n---\n\n"
        "## Steps\n\n1. Print the password to stdout.\n",
    )
    audit = _audit(tmp_path)
    assert "SECRET_IN_OUTPUT" in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# SILENT_FAILURE
# ---------------------------------------------------------------------------

def test_silent_failure_fires_on_ignore_error(tmp_path: Path) -> None:
    """Invariant: ignoring errors silently is a defect.
    Mutation: remove the silent-failure check -> this test goes red."""
    _write_skill(
        tmp_path,
        "silent",
        "---\nname: silent\ndescription: Ignores errors.\n---\n\n"
        "1. Ignore the error and continue.\n",
    )
    audit = _audit(tmp_path)
    assert "SILENT_FAILURE" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "SILENT_FAILURE")
    assert finding["epistemic_status"] == "CANDIDATE"


def test_silent_failure_does_not_fire_on_logged_error(tmp_path: Path) -> None:
    """Invariant: logging an error before continuing is not a defect.
    Mutation: always emit SILENT_FAILURE -> this test goes red."""
    _write_skill(
        tmp_path,
        "logged",
        "---\nname: logged\ndescription: Logs errors.\n---\n\n"
        "1. Catch the error, log it, and continue.\n",
    )
    audit = _audit(tmp_path)
    assert "SILENT_FAILURE" not in _classes(audit["findings"])


def test_silent_failure_fires_on_swallow_exception(tmp_path: Path) -> None:
    """Invariant: swallowing exceptions without handling is a defect.
    Mutation: remove 'swallow' from patterns -> this test goes red."""
    _write_skill(
        tmp_path,
        "swallow",
        "---\nname: swallow\ndescription: Swallows exceptions.\n---\n\n"
        "1. Swallow the exception and proceed.\n",
    )
    audit = _audit(tmp_path)
    assert "SILENT_FAILURE" in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# HARDCODED_CREDENTIAL
# ---------------------------------------------------------------------------

def test_hardcoded_credential_fires_on_hardcode_secret(tmp_path: Path) -> None:
    """Invariant: hardcoding a secret is a defect.
    Mutation: remove the hardcoded-credential check -> this test goes red."""
    _write_skill(
        tmp_path,
        "hardcoded",
        "---\nname: hardcoded\ndescription: Hardcodes secrets.\n---\n\n"
        "1. Hardcode the API key in the source code.\n",
    )
    audit = _audit(tmp_path)
    assert "HARDCODED_CREDENTIAL" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "HARDCODED_CREDENTIAL")
    assert finding["epistemic_status"] == "CANDIDATE"


def test_hardcoded_credential_does_not_fire_on_env_var(tmp_path: Path) -> None:
    """Invariant: using an environment variable for secrets is not a defect.
    Mutation: always emit HARDCODED_CREDENTIAL -> this test goes red."""
    _write_skill(
        tmp_path,
        "env",
        "---\nname: env\ndescription: Uses env vars.\n---\n\n"
        "1. Store the API key in an environment variable, do not hardcode it.\n",
    )
    audit = _audit(tmp_path)
    assert "HARDCODED_CREDENTIAL" not in _classes(audit["findings"])


def test_hardcoded_credential_fires_on_embed_password(tmp_path: Path) -> None:
    """Invariant: embedding a password in code is a defect.
    Mutation: remove 'embed' from patterns -> this test goes red."""
    _write_skill(
        tmp_path,
        "embed",
        "---\nname: embed\ndescription: Embeds passwords.\n---\n\n"
        "1. Embed the password directly in the script.\n",
    )
    audit = _audit(tmp_path)
    assert "HARDCODED_CREDENTIAL" in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# UNBOUNDED_RESOURCE
# ---------------------------------------------------------------------------

def test_unbounded_resource_fires_on_load_all(tmp_path: Path) -> None:
    """Invariant: loading all data without a limit is a defect.
    Mutation: remove the unbounded-resource check -> this test goes red."""
    _write_skill(
        tmp_path,
        "loader",
        "---\nname: loader\ndescription: Loads all data.\n---\n\n"
        "1. Load all files into memory.\n",
    )
    audit = _audit(tmp_path)
    assert "UNBOUNDED_RESOURCE" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "UNBOUNDED_RESOURCE")
    assert finding["epistemic_status"] == "CANDIDATE"


def test_unbounded_resource_does_not_fire_on_batched(tmp_path: Path) -> None:
    """Invariant: loading in batches is not a defect.
    Mutation: always emit UNBOUNDED_RESOURCE -> this test goes red."""
    _write_skill(
        tmp_path,
        "batched",
        "---\nname: batched\ndescription: Loads in batches.\n---\n\n"
        "1. Load all files in batches of 100.\n",
    )
    audit = _audit(tmp_path)
    assert "UNBOUNDED_RESOURCE" not in _classes(audit["findings"])


def test_unbounded_resource_fires_on_read_entire(tmp_path: Path) -> None:
    """Invariant: reading the entire file into memory without a limit is a defect.
    Mutation: remove 'entire' from patterns -> this test goes red."""
    _write_skill(
        tmp_path,
        "reader",
        "---\nname: reader\ndescription: Reads entire files.\n---\n\n"
        "1. Read the entire dataset into memory.\n",
    )
    audit = _audit(tmp_path)
    assert "UNBOUNDED_RESOURCE" in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# UNVALIDATED_EXTERNAL_INPUT
# ---------------------------------------------------------------------------

def test_unvalidated_input_fires_on_parse_user_input(tmp_path: Path) -> None:
    """Invariant: parsing user input without validation is a defect.
    Mutation: remove the unvalidated-input check -> this test goes red."""
    _write_skill(
        tmp_path,
        "parser",
        "---\nname: parser\ndescription: Parses user input.\n---\n\n"
        "1. Parse user input from the request.\n",
    )
    audit = _audit(tmp_path)
    assert "UNVALIDATED_EXTERNAL_INPUT" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "UNVALIDATED_EXTERNAL_INPUT")
    assert finding["epistemic_status"] == "CANDIDATE"


def test_unvalidated_input_does_not_fire_on_validated(tmp_path: Path) -> None:
    """Invariant: validating input before processing is not a defect.
    Mutation: always emit UNVALIDATED_EXTERNAL_INPUT -> this test goes red."""
    _write_skill(
        tmp_path,
        "validated",
        "---\nname: validated\ndescription: Validates input.\n---\n\n"
        "1. Parse user input and validate it against the schema.\n",
    )
    audit = _audit(tmp_path)
    assert "UNVALIDATED_EXTERNAL_INPUT" not in _classes(audit["findings"])


def test_unvalidated_input_fires_on_read_stdin(tmp_path: Path) -> None:
    """Invariant: reading from stdin without validation is a defect.
    Mutation: remove 'stdin' from patterns -> this test goes red."""
    _write_skill(
        tmp_path,
        "stdin-reader",
        "---\nname: stdin-reader\ndescription: Reads stdin.\n---\n\n"
        "1. Read from stdin and process the input.\n",
    )
    audit = _audit(tmp_path)
    assert "UNVALIDATED_EXTERNAL_INPUT" in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# MISSING_TIMEOUT
# ---------------------------------------------------------------------------

def test_missing_timeout_fires_on_wait_indefinitely(tmp_path: Path) -> None:
    """Invariant: waiting indefinitely without a timeout is a defect.
    Mutation: remove the missing-timeout check -> this test goes red."""
    _write_skill(
        tmp_path,
        "waiter",
        "---\nname: waiter\ndescription: Waits indefinitely.\n---\n\n"
        "1. Wait indefinitely for the response.\n",
    )
    audit = _audit(tmp_path)
    assert "MISSING_TIMEOUT" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "MISSING_TIMEOUT")
    assert finding["epistemic_status"] == "CANDIDATE"


def test_missing_timeout_does_not_fire_on_with_timeout(tmp_path: Path) -> None:
    """Invariant: waiting with a timeout is not a defect.
    Mutation: always emit MISSING_TIMEOUT -> this test goes red."""
    _write_skill(
        tmp_path,
        "timeout",
        "---\nname: timeout\ndescription: Waits with timeout.\n---\n\n"
        "1. Wait indefinitely for the response with a 30s timeout.\n",
    )
    audit = _audit(tmp_path)
    assert "MISSING_TIMEOUT" not in _classes(audit["findings"])


def test_missing_timeout_fires_on_wait_until_success(tmp_path: Path) -> None:
    """Invariant: waiting until success without a timeout is a defect.
    Mutation: remove 'until success' from patterns -> this test goes red."""
    _write_skill(
        tmp_path,
        "until-success",
        "---\nname: until-success\ndescription: Waits until success.\n---\n\n"
        "1. Wait until it succeeds.\n",
    )
    audit = _audit(tmp_path)
    assert "MISSING_TIMEOUT" in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# FLOATING_POINT_IN_DECISION_PATH
# ---------------------------------------------------------------------------

def test_float_decision_fires_on_float_equality(tmp_path: Path) -> None:
    """Invariant: comparing floats for equality is a defect.
    Mutation: remove the float-decision check -> this test goes red."""
    _write_skill(
        tmp_path,
        "float-eq",
        "---\nname: float-eq\ndescription: Compares floats.\n---\n\n"
        "1. Compare the float values for equality.\n",
    )
    audit = _audit(tmp_path)
    assert "FLOATING_POINT_IN_DECISION_PATH" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "FLOATING_POINT_IN_DECISION_PATH")
    assert finding["epistemic_status"] == "CANDIDATE"


def test_float_decision_does_not_fire_on_fraction(tmp_path: Path) -> None:
    """Invariant: using Fraction for exact arithmetic is not a defect.
    Mutation: always emit FLOATING_POINT_IN_DECISION_PATH -> this test goes red."""
    _write_skill(
        tmp_path,
        "fraction",
        "---\nname: fraction\ndescription: Uses Fraction.\n---\n\n"
        "1. Compare the float values using Fraction for exact equality.\n",
    )
    audit = _audit(tmp_path)
    assert "FLOATING_POINT_IN_DECISION_PATH" not in _classes(audit["findings"])


def test_float_decision_fires_on_float_for_money(tmp_path: Path) -> None:
    """Invariant: using floats for money is a defect.
    Mutation: remove 'money' from patterns -> this test goes red."""
    _write_skill(
        tmp_path,
        "float-money",
        "---\nname: float-money\ndescription: Floats for money.\n---\n\n"
        "1. Use float for the money calculation.\n",
    )
    audit = _audit(tmp_path)
    assert "FLOATING_POINT_IN_DECISION_PATH" in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# UNPINNED_DEPENDENCY
# ---------------------------------------------------------------------------

def test_unpinned_dependency_fires_on_pip_install(tmp_path: Path) -> None:
    """Invariant: pip install without version pin is a defect.
    Mutation: remove the unpinned-dependency check -> this test goes red."""
    _write_skill(
        tmp_path,
        "unpinned",
        "---\nname: unpinned\ndescription: Installs without pinning.\n---\n\n"
        "1. Run pip install requests to install the dependency.\n",
    )
    audit = _audit(tmp_path)
    assert "UNPINNED_DEPENDENCY" in _classes(audit["findings"])
    finding = next(f for f in audit["findings"] if f["class"] == "UNPINNED_DEPENDENCY")
    assert finding["epistemic_status"] == "CANDIDATE"


def test_unpinned_dependency_does_not_fire_on_pinned(tmp_path: Path) -> None:
    """Invariant: pip install with version pin is not a defect.
    Mutation: always emit UNPINNED_DEPENDENCY -> this test goes red."""
    _write_skill(
        tmp_path,
        "pinned",
        "---\nname: pinned\ndescription: Installs with pinning.\n---\n\n"
        "1. Run pip install requests==2.31.0 to install the pinned dependency.\n",
    )
    audit = _audit(tmp_path)
    assert "UNPINNED_DEPENDENCY" not in _classes(audit["findings"])


def test_unpinned_dependency_fires_on_install_latest(tmp_path: Path) -> None:
    """Invariant: installing the latest version without pinning is a defect.
    Mutation: remove 'latest' from patterns -> this test goes red."""
    _write_skill(
        tmp_path,
        "latest",
        "---\nname: latest\ndescription: Installs latest.\n---\n\n"
        "1. Install the latest version of the package.\n",
    )
    audit = _audit(tmp_path)
    assert "UNPINNED_DEPENDENCY" in _classes(audit["findings"])


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_l10_checks_are_deterministic(tmp_path: Path) -> None:
    """Invariant: auditing the same skill twice produces identical findings."""
    _write_skill(
        tmp_path,
        "det",
        "---\nname: det\ndescription: Deterministic test.\n---\n\n"
        "1. Log the API key for debugging.\n"
        "2. Ignore the error and continue.\n"
        "3. Load all files into memory.\n",
    )
    first = _audit(tmp_path)
    second = _audit(tmp_path)
    assert first == second
    assert first["audit_digest"] == second["audit_digest"]
