"""LLM confirmation layer for SEMANTIC_REDUNDANCY candidates (L2.5).

Takes CANDIDATE findings from the L2 audit and asks an executor (LLM or
deterministic mock) whether each pair is semantically redundant.

Architecture:

    L2 audit (sealed, deterministic, never modified)
        |
        v
    confirmation layer extracts SEMANTIC_REDUNDANCY candidates
        |
        v
    executor (Nemotron via Nebius, or deterministic mock)
        |
        v
    confirmation artifact (separate, OBSERVATION status, own digest)

The L2 audit artifact is NEVER modified by this layer. The confirmation
is a separate artifact with its own digest. The executor's verdict is an
OBSERVATION, not a promotion to CONFIRMED in the L2 sense.

If the Nebius API key is not available, the confirmation is BLOCKED, not
simulated as verified.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Protocol

from .ir import digest_payload

CONFIRMATION_VERSION = "crucible-confirmation/v1"

# ---------------------------------------------------------------------------
# Executor protocol
# ---------------------------------------------------------------------------


class ConfirmExecutor(Protocol):
    """Pluggable executor for semantic redundancy confirmation."""

    def execute(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        """Run the model and return a response dict with output and metadata."""
        ...


# ---------------------------------------------------------------------------
# Nebius Token Factory executor (NVIDIA Nemotron)
# ---------------------------------------------------------------------------

NEBIUS_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"
NEBIUS_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b"
NEBIUS_DEFAULT_TEMPERATURE = 0
NEBIUS_DEFAULT_MAX_TOKENS = 2000


class NebiusConfirmExecutor:
    """Executor that calls the Nebius Token Factory API with Nemotron.

    Requires NEBIUS_API_KEY. If the key is not present, ``execute`` returns
    a BLOCKED response so the confirmation layer can mark the run as
    BLOCKED rather than simulating it.
    """

    def __init__(
        self,
        model: str = NEBIUS_DEFAULT_MODEL,
        temperature: int = NEBIUS_DEFAULT_TEMPERATURE,
        max_tokens: int = NEBIUS_DEFAULT_MAX_TOKENS,
        api_key: str | None = None,
        base_url: str = NEBIUS_BASE_URL,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key or os.environ.get("NEBIUS_API_KEY")
        self.base_url = base_url

    def is_available(self) -> bool:
        """Check whether the API key is present."""
        return bool(self.api_key)

    def execute(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        if not self.api_key:
            return {
                "output": "",
                "error": "NEBIUS_API_KEY not set; cannot call Nebius",
                "model": self.model,
                "provider": "nebius-token-factory",
                "blocked": True,
            }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        # Retry on rate limiting (HTTP 429) with backoff.
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    result = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 429 and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return {
                    "output": "",
                    "error": f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:200]}",
                    "model": self.model,
                    "provider": "nebius-token-factory",
                    "blocked": False,
                }
            except urllib.error.URLError as exc:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return {
                    "output": "",
                    "error": f"URL error: {exc}",
                    "model": self.model,
                    "provider": "nebius-token-factory",
                    "blocked": False,
                }
        output = ""
        if result.get("choices"):
            output = result["choices"][0].get("message", {}).get("content", "")
        usage = result.get("usage", {})
        return {
            "output": output,
            "error": None,
            "model": self.model,
            "provider": "nebius-token-factory",
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            "response_id": result.get("id", ""),
            "blocked": False,
        }


# ---------------------------------------------------------------------------
# Mock executor (deterministic, for testing without external dependencies)
# ---------------------------------------------------------------------------


class MockConfirmExecutor:
    """Deterministic executor for testing the confirmation layer.

    For SEMANTIC_REDUNDANCY (pair-wise): returns CONFIRMED if the two
    skill texts share more than 80% of their lines, REJECTED otherwise.

    For single-skill findings (CHECK_WITHOUT_ORACLE, DESCRIPTION_BODY_GAP,
    REQUIREMENT_WITHOUT_CHECK, SCOPE_TRIGGER_MISMATCH): returns CONFIRMED
    if the skill text has fewer than 5 non-empty lines (short body
    supports the finding), REJECTED otherwise.

    This is a deterministic heuristic, not an LLM. It exists so the
    confirmation harness can be tested without NEBIUS_API_KEY.
    """

    def __init__(self, threshold: int = 80) -> None:
        self.model = "crucible-mock-confirm/v1"
        self.temperature = 0
        self.max_tokens = 0
        self.threshold = threshold

    def execute(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        # Try the pair-wise format first (SKILL_A/SKILL_B).
        skill_a_match = re.search(
            r"SKILL_A:\n(.*?)\n\nSKILL_B:", user_prompt, re.DOTALL
        )
        skill_b_match = re.search(
            r"SKILL_B:\n(.*?)\n\nQUESTION:", user_prompt, re.DOTALL
        )
        if skill_a_match and skill_b_match:
            return self._execute_pairwise(
                system_prompt, user_prompt,
                skill_a_match.group(1).strip(),
                skill_b_match.group(1).strip(),
            )

        # Try the single-skill format (SKILL/FINDING).
        skill_match = re.search(
            r"SKILL:\n(.*?)\n\nFINDING:", user_prompt, re.DOTALL
        )
        if skill_match:
            return self._execute_single(
                system_prompt, user_prompt, skill_match.group(1).strip()
            )

        # Unknown format.
        return self._unclear(system_prompt, user_prompt, "Could not parse prompt format.")

    def _execute_pairwise(
        self, system_prompt: str, user_prompt: str,
        text_a: str, text_b: str,
    ) -> dict[str, Any]:
        lines_a = set(l.strip() for l in text_a.splitlines() if l.strip())
        lines_b = set(l.strip() for l in text_b.splitlines() if l.strip())
        if not lines_a or not lines_b:
            verdict = "UNCLEAR"
            rationale = "One or both skills have no content."
        else:
            overlap = len(lines_a & lines_b)
            union = len(lines_a | lines_b)
            pct = (overlap * 100) // union if union > 0 else 0
            if pct >= self.threshold:
                verdict = "CONFIRMED"
                rationale = (
                    f"Line overlap {pct}% >= {self.threshold}%; "
                    f"the two skills cover the same ground."
                )
            else:
                verdict = "REJECTED"
                rationale = (
                    f"Line overlap {pct}% < {self.threshold}%; "
                    f"the two skills cover different ground."
                )
        return self._response(system_prompt, user_prompt, verdict, rationale)

    def _execute_single(
        self, system_prompt: str, user_prompt: str, skill_text: str,
    ) -> dict[str, Any]:
        # Heuristic: if the skill body has very few non-empty lines,
        # the finding is likely true (the body is genuinely thin).
        # If it has many lines, the finding is likely a false positive
        # (the body has content the extractor missed).
        lines = [l.strip() for l in skill_text.splitlines() if l.strip()]
        if len(lines) < 5:
            verdict = "CONFIRMED"
            rationale = (
                f"Skill has only {len(lines)} non-empty lines; "
                f"the body is genuinely thin and the finding is likely true."
            )
        else:
            verdict = "REJECTED"
            rationale = (
                f"Skill has {len(lines)} non-empty lines; "
                f"the body has content the extractor may have missed."
            )
        return self._response(system_prompt, user_prompt, verdict, rationale)

    def _unclear(
        self, system_prompt: str, user_prompt: str, reason: str,
    ) -> dict[str, Any]:
        return self._response(system_prompt, user_prompt, "UNCLEAR", reason)

    def _response(
        self, system_prompt: str, user_prompt: str,
        verdict: str, rationale: str,
    ) -> dict[str, Any]:
        output = f"{verdict}\n{rationale}"
        output_hash = hashlib.sha256(output.encode("utf-8")).hexdigest()
        return {
            "output": output,
            "error": None,
            "model": self.model,
            "provider": "mock-deterministic",
            "temperature": 0,
            "max_tokens": 0,
            "usage": {
                "prompt_tokens": len(system_prompt) + len(user_prompt),
                "completion_tokens": len(output),
                "total_tokens": len(system_prompt) + len(user_prompt) + len(output),
            },
            "response_id": f"mock-{output_hash[:16]}",
            "blocked": False,
        }


# ---------------------------------------------------------------------------
# Finding parsing
# ---------------------------------------------------------------------------

# The evidence string format is:
# "lexical Jaccard overlap X/Y with <skill-name> (threshold 2/3); ..."
_OTHER_SKILL_RE = re.compile(
    r"lexical Jaccard overlap (\d+/\d+) with (\S+) "
)


def _parse_semantic_redundancy_pair(
    finding: dict[str, Any]
) -> tuple[str, str, str] | None:
    """Extract (skill_a, skill_b, jaccard) from a SEMANTIC_REDUNDANCY finding.

    Returns None if the evidence cannot be parsed.
    """
    if finding.get("class") != "SEMANTIC_REDUNDANCY":
        return None
    evidence = finding.get("evidence", "")
    match = _OTHER_SKILL_RE.search(evidence)
    if not match:
        return None
    jaccard = match.group(1)
    other_skill = match.group(2)
    reported_skill = finding.get("skill", "")
    if not reported_skill or not other_skill:
        return None
    # Order for determinism.
    skill_a, skill_b = sorted([reported_skill, other_skill])
    return skill_a, skill_b, jaccard


# ---------------------------------------------------------------------------
# Skill text extraction
# ---------------------------------------------------------------------------


def _skill_text(ir: dict[str, Any], skill_name: str) -> str:
    """Extract a readable text representation of a skill from the L1 IR."""
    for skill in ir.get("skills", []):
        if skill["identity"]["name"] == skill_name:
            parts = []
            # Description (stored under metadata.description in the IR).
            desc = skill.get("metadata", {}).get("description", "")
            if desc:
                parts.append(f"Description: {desc}")
            # Trigger.
            trigger = skill.get("trigger", "")
            if trigger:
                parts.append(f"Trigger: {trigger}")
            # Raw body text (the full markdown body after frontmatter).
            # This gives the executor the full context including
            # non-RFC-2119 normative language the extractor may miss.
            body_text = skill.get("body_text", "")
            if body_text:
                parts.append(f"Body:\n{body_text}")
            # Extracted rules.
            for rule in skill.get("rules", []):
                parts.append(f"Rule: {rule.get('text', '')}")
            # Extracted checks.
            for check in skill.get("checks", []):
                parts.append(f"Check: {check.get('text', '')}")
            # Procedural steps.
            for step in skill.get("procedural_steps", []):
                parts.append(f"Step: {step.get('text', '')}")
            return "\n".join(parts)
    return ""


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a methodology redundancy analyst. You receive two skills "
    "and must determine whether they are semantically redundant — i.e., "
    "they cover the same ground and a maintainer would only need one.\n\n"
    "Respond with exactly one line containing one of:\n"
    "  CONFIRMED — the two skills are semantically redundant\n"
    "  REJECTED — the two skills cover different ground\n"
    "  UNCLEAR — cannot determine from the provided text\n\n"
    "On the second line, provide a one-sentence rationale.\n\n"
    "Do not modify any values. Do not add commentary. The audit "
    "findings are fixed and cannot be changed."
)


def _build_user_prompt(
    skill_a: str, text_a: str, skill_b: str, text_b: str, jaccard: str
) -> str:
    """Build the user prompt for the executor."""
    return (
        f"SKILL_A:\n{text_a}\n\n"
        f"SKILL_B:\n{text_b}\n\n"
        f"QUESTION: The deterministic auditor found a lexical Jaccard "
        f"overlap of {jaccard} between these two skills. "
        f"Are they semantically redundant? "
        f"Respond with CONFIRMED, REJECTED, or UNCLEAR and a rationale."
    )


# ---------------------------------------------------------------------------
# Per-class prompt builders
# ---------------------------------------------------------------------------

# Each prompt builder takes (finding, skill_text) and returns
# (system_prompt, user_prompt). The system prompt sets the executor's
# role; the user prompt provides the evidence and asks the question.

_CONFIRMATION_SYSTEM_PROMPT = (
    "You are a methodology audit confirmation analyst. You receive a "
    "CANDIDATE finding from a deterministic auditor and the full text "
    "of the skill it applies to. You must determine whether the "
    "finding is a true defect or a false positive.\n\n"
    "Respond with exactly one line containing one of:\n"
    "  CONFIRMED — the finding is a true defect\n"
    "  REJECTED — the finding is a false positive\n"
    "  UNCLEAR — cannot determine from the provided text\n\n"
    "On the second line, provide a one-sentence rationale.\n\n"
    "Do not modify any values. Do not add commentary. The audit "
    "findings are fixed and cannot be changed."
)


def _build_check_without_oracle_prompt(
    finding: dict[str, Any], skill_text: str, ir: dict[str, Any] | None = None
) -> tuple[str, str]:
    """Prompt for CHECK_WITHOUT_ORACLE: is the check verifiable?"""
    evidence = finding.get("evidence", "")
    skill_name = finding.get("skill", "")
    # Try to extract the specific check text from the IR.
    check_text = ""
    if ir is not None:
        import re as _re
        check_id_match = _re.search(r"check-(\d+)", evidence)
        if check_id_match:
            check_id = f"check-{check_id_match.group(1).zfill(4)}"
            for s in ir.get("skills", []):
                if s["identity"]["name"] == skill_name:
                    for c in s.get("checks", []):
                        if c.get("id") == check_id:
                            check_text = c.get("text", "")
                            break
                    break
    check_section = (
        f"\n\nFLAGGED CHECK: {check_text}"
        if check_text
        else ""
    )
    return (
        _CONFIRMATION_SYSTEM_PROMPT,
        (
            f"SKILL:\n{skill_text}{check_section}\n\n"
            f"FINDING: {evidence}\n\n"
            f"QUESTION: The deterministic auditor flagged a check as "
            f"having no recognizable verification oracle (no question "
            f"mark, no checkbox marker, no verification verb). Is this "
            f"check actually unverifiable, or does it have a "
            f"domain-specific oracle the patterns missed? "
            f"Respond with CONFIRMED, REJECTED, or UNCLEAR and a rationale."
        ),
    )


def _build_description_body_gap_prompt(
    finding: dict[str, Any], skill_text: str
) -> tuple[str, str]:
    """Prompt for DESCRIPTION_BODY_GAP: does the body deliver?"""
    evidence = finding.get("evidence", "")
    return (
        _CONFIRMATION_SYSTEM_PROMPT,
        (
            f"SKILL:\n{skill_text}\n\n"
            f"FINDING: {evidence}\n\n"
            f"QUESTION: The deterministic auditor found that the "
            f"description is substantive but the body has zero "
            f"extractable rules, checks, and procedural steps. Does "
            f"the body actually fail to deliver what the description "
            f"promises, or does it use non-RFC-2119 normative language "
            f"the extractor missed? "
            f"Respond with CONFIRMED, REJECTED, or UNCLEAR and a rationale."
        ),
    )


def _build_requirement_without_check_prompt(
    finding: dict[str, Any], skill_text: str
) -> tuple[str, str]:
    """Prompt for REQUIREMENT_WITHOUT_CHECK: are rules without checks?"""
    evidence = finding.get("evidence", "")
    return (
        _CONFIRMATION_SYSTEM_PROMPT,
        (
            f"SKILL:\n{skill_text}\n\n"
            f"FINDING: {evidence}\n\n"
            f"QUESTION: The deterministic auditor found that the skill "
            f"has normative rules but zero extracted checks. Are these "
            f"rules actually without any verification checks, or does "
            f"the skill have checks the extractor missed? "
            f"Respond with CONFIRMED, REJECTED, or UNCLEAR and a rationale."
        ),
    )


def _build_scope_trigger_mismatch_prompt(
    finding: dict[str, Any], skill_text: str
) -> tuple[str, str]:
    """Prompt for SCOPE_TRIGGER_MISMATCH: does the trigger match scope?"""
    evidence = finding.get("evidence", "")
    return (
        _CONFIRMATION_SYSTEM_PROMPT,
        (
            f"SKILL:\n{skill_text}\n\n"
            f"FINDING: {evidence}\n\n"
            f"QUESTION: The deterministic auditor found that the "
            f"trigger clause and the rule content share zero "
            f"meaningful tokens. Does the trigger actually mismatch "
            f"the rules' scope, or do they use different vocabulary "
            f"for the same domain? "
            f"Respond with CONFIRMED, REJECTED, or UNCLEAR and a rationale."
        ),
    )


# Registry of prompt builders by finding class.
_PROMPT_BUILDERS: dict[str, Any] = {
    "CHECK_WITHOUT_ORACLE": _build_check_without_oracle_prompt,
    "DESCRIPTION_BODY_GAP": _build_description_body_gap_prompt,
    "REQUIREMENT_WITHOUT_CHECK": _build_requirement_without_check_prompt,
    "SCOPE_TRIGGER_MISMATCH": _build_scope_trigger_mismatch_prompt,
}


# ---------------------------------------------------------------------------
# Generic engineering-check prompt builder
# ---------------------------------------------------------------------------

# The engineering checks (UNBOUNDED_RETRY, LLM_IN_DECISION_PATH, OVERCLAIM,
# MISSING_FAILURE_MODE, NON_DETERMINISTIC_INSTRUCTION,
# IRREVERSIBLE_WITHOUT_REVIEW, SECRET_IN_OUTPUT, SILENT_FAILURE,
# HARDCODED_CREDENTIAL, UNBOUNDED_RESOURCE, UNVALIDATED_EXTERNAL_INPUT,
# MISSING_TIMEOUT, FLOATING_POINT_IN_DECISION_PATH, UNPINNED_DEPENDENCY)
# all follow the same pattern: the deterministic auditor found a pattern
# that indicates an engineering defect, and the LLM is asked to confirm
# or reject based on the full skill context.

# Per-class question text describing what the auditor found.
_ENGINEERING_QUESTIONS: dict[str, str] = {
    "UNBOUNDED_RETRY": (
        "The deterministic auditor found a retry or repeat instruction "
        "without a bound (max attempts, timeout, backoff, circuit breaker). "
        "Is this actually an unbounded retry, or is the bound expressed "
        "in vocabulary the patterns missed?"
    ),
    "LLM_IN_DECISION_PATH": (
        "The deterministic auditor found an instruction to use an LLM or "
        "model for a consequential decision without a deterministic guard. "
        "Is the LLM actually in the decision path without a guard, or is "
        "there a deterministic fallback the patterns missed?"
    ),
    "OVERCLAIM": (
        "The deterministic auditor found an absolute claim (always, never, "
        "guaranteed, failsafe) without qualification. Is this actually an "
        "unqualified absolute claim, or is it qualified in a way the "
        "patterns missed?"
    ),
    "MISSING_FAILURE_MODE": (
        "The deterministic auditor found that the skill has normative "
        "rules and procedural steps but no mention of failure, error, "
        "exception, fallback, or recovery. Does the skill actually lack "
        "a failure mode, or does it describe one using vocabulary the "
        "patterns missed?"
    ),
    "NON_DETERMINISTIC_INSTRUCTION": (
        "The deterministic auditor found a non-deterministic instruction "
        "(random, arbitrary, pick any) without a deterministic anchor "
        "(seed, fixed, pinned, reproducible). Is this actually "
        "unanchored non-determinism, or is the anchor expressed in "
        "vocabulary the patterns missed?"
    ),
    "IRREVERSIBLE_WITHOUT_REVIEW": (
        "The deterministic auditor found an irreversible action (delete, "
        "drop, destroy, force-push, truncate, purge) without a review "
        "bound (review, confirm, backup, idempotent, rollback). Is this "
        "actually an unbounded irreversible action, or is the bound "
        "expressed in vocabulary the patterns missed?"
    ),
    "SECRET_IN_OUTPUT": (
        "The deterministic auditor found an instruction to send a secret "
        "to an output channel (log, print, echo, stdout) without "
        "protection (redact, mask, hash, encrypt). Is this actually "
        "leaking a secret, or is the protection expressed in vocabulary "
        "the patterns missed?"
    ),
    "SILENT_FAILURE": (
        "The deterministic auditor found an instruction to suppress an "
        "error silently (ignore, swallow, suppress, catch and continue) "
        "without handling (log, report, raise, abort, retry). Is this "
        "actually a silent failure, or is the error handling expressed "
        "in vocabulary the patterns missed?"
    ),
    "HARDCODED_CREDENTIAL": (
        "The deterministic auditor found an instruction to hardcode a "
        "credential (secret, password, token) in code without secure "
        "storage (env var, vault, KMS). Is this actually hardcoding a "
        "credential, or is the secure storage expressed in vocabulary "
        "the patterns missed?"
    ),
    "UNBOUNDED_RESOURCE": (
        "The deterministic auditor found an instruction to load all, "
        "read all, or load into memory without a bound (limit, max, "
        "batch, stream, paginate). Is this actually unbounded resource "
        "consumption, or is the bound expressed in vocabulary the "
        "patterns missed?"
    ),
    "UNVALIDATED_EXTERNAL_INPUT": (
        "The deterministic auditor found an instruction to accept "
        "external input (user input, request, stdin, argv) without "
        "validation (validate, sanitize, schema, type check). Is this "
        "actually accepting unvalidated input, or is the validation "
        "expressed in vocabulary the patterns missed?"
    ),
    "MISSING_TIMEOUT": (
        "The deterministic auditor found an instruction to wait or block "
        "without a timeout (wait indefinitely, block forever, wait "
        "until success) without a deadline (timeout, deadline, TTL). "
        "Is this actually an unbounded wait, or is the timeout "
        "expressed in vocabulary the patterns missed?"
    ),
    "FLOATING_POINT_IN_DECISION_PATH": (
        "The deterministic auditor found an instruction to use "
        "floating-point arithmetic for an exact decision (equality, "
        "comparison, money) without exact arithmetic (Fraction, "
        "Decimal, integer, epsilon). Is this actually using floats for "
        "an exact decision, or is the exact arithmetic expressed in "
        "vocabulary the patterns missed?"
    ),
    "UNPINNED_DEPENDENCY": (
        "The deterministic auditor found an instruction to install a "
        "dependency without version pinning (pip install, npm install, "
        "install latest) without a pin (==version, @version, lock file). "
        "Is this actually an unpinned dependency, or is the pin "
        "expressed in vocabulary the patterns missed?"
    ),
}


def _build_engineering_check_prompt(
    finding: dict[str, Any], skill_text: str
) -> tuple[str, str]:
    """Generic prompt builder for engineering checks.

    All engineering checks follow the same pattern: the auditor found a
    pattern indicating a defect, and the LLM is asked to confirm or reject
    based on the full skill context. The question text is customized per
    check class.
    """
    cls = finding.get("class", "")
    evidence = finding.get("evidence", "")
    question = _ENGINEERING_QUESTIONS.get(cls, (
        f"The deterministic auditor found a potential engineering defect "
        f"of class {cls}. Is this a true defect or a false positive?"
    ))
    return (
        _CONFIRMATION_SYSTEM_PROMPT,
        (
            f"SKILL:\n{skill_text}\n\n"
            f"FINDING: {evidence}\n\n"
            f"QUESTION: {question} "
            f"Respond with CONFIRMED, REJECTED, or UNCLEAR and a rationale."
        ),
    )


# Register the engineering check prompt builders.
for _cls in _ENGINEERING_QUESTIONS:
    _PROMPT_BUILDERS[_cls] = _build_engineering_check_prompt


# ---------------------------------------------------------------------------
# Verdict parsing
# ---------------------------------------------------------------------------

_VERDICT_RE = re.compile(
    r"^(CONFIRMED|REJECTED|UNCLEAR)\b", re.MULTILINE
)


def _parse_verdict(output: str) -> tuple[str, str]:
    """Parse the executor output into (verdict, rationale)."""
    if not output:
        return "UNCLEAR", "No output from executor."
    match = _VERDICT_RE.search(output)
    if not match:
        return "UNCLEAR", f"Could not parse verdict from output: {output[:200]}"
    verdict = match.group(1)
    # Rationale is the rest of the output after the verdict line.
    rest = output[match.end():].strip()
    # Take the first non-empty line as the rationale.
    rationale = ""
    for line in rest.splitlines():
        line = line.strip()
        if line:
            rationale = line
            break
    if not rationale:
        rationale = "No rationale provided."
    return verdict, rationale


# ---------------------------------------------------------------------------
# Confirmation artifact
# ---------------------------------------------------------------------------


def confirm_semantic_redundancy(
    audit: dict[str, Any],
    ir: dict[str, Any],
    executor: ConfirmExecutor,
) -> dict[str, Any]:
    """Confirm or reject SEMANTIC_REDUNDANCY CANDIDATEs using an executor.

    The L2 audit artifact is NEVER modified. The confirmation is a
    separate artifact with its own digest. The executor's verdict is an
    OBSERVATION, not a promotion to CONFIRMED in the L2 sense.

    If the executor is BLOCKED (no API key), the confirmation artifact
    has status "BLOCKED" and no confirmations.
    """
    # Extract SEMANTIC_REDUNDANCY findings from the audit.
    semantic_findings = [
        f for f in audit.get("findings", [])
        if f.get("class") == "SEMANTIC_REDUNDANCY"
        and f.get("epistemic_status") == "CANDIDATE"
    ]

    # Check if the executor is blocked.
    is_blocked = (
        hasattr(executor, "is_available") and not executor.is_available()
    )

    confirmations: list[dict[str, Any]] = []
    for finding in semantic_findings:
        parsed = _parse_semantic_redundancy_pair(finding)
        if parsed is None:
            continue
        skill_a, skill_b, jaccard = parsed
        text_a = _skill_text(ir, skill_a)
        text_b = _skill_text(ir, skill_b)
        user_prompt = _build_user_prompt(
            skill_a, text_a, skill_b, text_b, jaccard
        )
        response = executor.execute(_SYSTEM_PROMPT, user_prompt)
        if response.get("blocked"):
            is_blocked = True
            confirmations.append({
                "finding_id": finding.get("id", ""),
                "finding_class": "SEMANTIC_REDUNDANCY",
                "skill_a": skill_a,
                "skill_b": skill_b,
                "jaccard_overlap": jaccard,
                "verdict": "BLOCKED",
                "rationale": response.get("error", "Executor blocked"),
                "executor_model": response.get("model", ""),
                "executor_provider": response.get("provider", ""),
            })
            continue
        verdict, rationale = _parse_verdict(response.get("output", ""))
        confirmations.append({
            "finding_id": finding.get("id", ""),
            "finding_class": "SEMANTIC_REDUNDANCY",
            "skill_a": skill_a,
            "skill_b": skill_b,
            "jaccard_overlap": jaccard,
            "verdict": verdict,
            "rationale": rationale,
            "executor_model": response.get("model", ""),
            "executor_provider": response.get("provider", ""),
            "executor_response_id": response.get("response_id", ""),
        })

    # Build the confirmation artifact.
    # The sealed payload excludes the digest itself.
    payload = {
        "schema_version": CONFIRMATION_VERSION,
        "source_audit_digest": audit.get("audit_digest", ""),
        "source_ir_digest": ir.get("artifact_digest", ""),
        "executor": {
            "model": getattr(executor, "model", ""),
            "provider": getattr(executor, "provider", "")
            if hasattr(executor, "provider")
            else "",
            "temperature": getattr(executor, "temperature", 0),
        },
        "status": "BLOCKED" if is_blocked else "COMPLETED",
        "confirmations": confirmations,
        "summary": {
            "total": len(confirmations),
            "confirmed": sum(
                1 for c in confirmations if c["verdict"] == "CONFIRMED"
            ),
            "rejected": sum(
                1 for c in confirmations if c["verdict"] == "REJECTED"
            ),
            "unclear": sum(
                1 for c in confirmations if c["verdict"] == "UNCLEAR"
            ),
            "blocked": sum(
                1 for c in confirmations if c["verdict"] == "BLOCKED"
            ),
        },
    }
    digest = digest_payload(payload)
    artifact = dict(payload)
    artifact["confirmation_digest"] = digest
    return artifact


def confirm_candidates(
    audit: dict[str, Any],
    ir: dict[str, Any],
    executor: ConfirmExecutor,
    classes: list[str] | None = None,
) -> dict[str, Any]:
    """Confirm or reject ALL CANDIDATE findings using an executor.

    This is the general confirmation layer. It handles all CANDIDATE
    finding types that have a registered prompt builder:
    - SEMANTIC_REDUNDANCY (pair-wise, uses its own prompt)
    - CHECK_WITHOUT_ORACLE
    - DESCRIPTION_BODY_GAP
    - REQUIREMENT_WITHOUT_CHECK
    - SCOPE_TRIGGER_MISMATCH

    If ``classes`` is given, only those finding classes are confirmed.
    Otherwise all CANDIDATEs with a registered prompt builder are
    confirmed.

    The L2 audit artifact is NEVER modified. The confirmation is a
    separate artifact with its own digest. The executor's verdict is an
    OBSERVATION, not a promotion to CONFIRMED in the L2 sense.

    If the executor is BLOCKED (no API key), the confirmation artifact
    has status "BLOCKED".
    """
    # Determine which classes to confirm.
    if classes is None:
        # All classes with a prompt builder, plus SEMANTIC_REDUNDANCY.
        target_classes = set(_PROMPT_BUILDERS.keys()) | {"SEMANTIC_REDUNDANCY"}
    else:
        target_classes = set(classes)

    # Extract CANDIDATE findings from the audit.
    candidate_findings = [
        f for f in audit.get("findings", [])
        if f.get("epistemic_status") == "CANDIDATE"
        and f.get("class") in target_classes
    ]

    # Check if the executor is blocked.
    is_blocked = (
        hasattr(executor, "is_available") and not executor.is_available()
    )

    confirmations: list[dict[str, Any]] = []
    for finding in candidate_findings:
        cls = finding.get("class", "")
        skill_name = finding.get("skill", "")
        skill_text = _skill_text(ir, skill_name)

        if cls == "SEMANTIC_REDUNDANCY":
            # Use the pair-wise prompt.
            parsed = _parse_semantic_redundancy_pair(finding)
            if parsed is None:
                continue
            skill_a, skill_b, jaccard = parsed
            text_a = _skill_text(ir, skill_a)
            text_b = _skill_text(ir, skill_b)
            system_prompt = _SYSTEM_PROMPT
            user_prompt = _build_user_prompt(
                skill_a, text_a, skill_b, text_b, jaccard
            )
            extra_fields: dict[str, Any] = {
                "skill_a": skill_a,
                "skill_b": skill_b,
                "jaccard_overlap": jaccard,
            }
        elif cls in _PROMPT_BUILDERS:
            builder = _PROMPT_BUILDERS[cls]
            # Pass ir for builders that need it (e.g., CHECK_WITHOUT_ORACLE
            # extracts the specific check text from the IR).
            try:
                system_prompt, user_prompt = builder(finding, skill_text, ir)
            except TypeError:
                system_prompt, user_prompt = builder(finding, skill_text)
            extra_fields = {"skill": skill_name}
        else:
            # No prompt builder for this class; skip.
            continue

        response = executor.execute(system_prompt, user_prompt)
        if response.get("blocked"):
            is_blocked = True
            confirmations.append({
                "finding_id": finding.get("id", ""),
                "finding_class": cls,
                "verdict": "BLOCKED",
                "rationale": response.get("error", "Executor blocked"),
                "executor_model": response.get("model", ""),
                "executor_provider": response.get("provider", ""),
                **extra_fields,
            })
            continue
        # Check for API errors (not blocked, but error present).
        if response.get("error"):
            confirmations.append({
                "finding_id": finding.get("id", ""),
                "finding_class": cls,
                "verdict": "UNCLEAR",
                "rationale": f"Executor error: {response['error'][:200]}",
                "executor_model": response.get("model", ""),
                "executor_provider": response.get("provider", ""),
                **extra_fields,
            })
            continue
        verdict, rationale = _parse_verdict(response.get("output", ""))
        confirmations.append({
            "finding_id": finding.get("id", ""),
            "finding_class": cls,
            "verdict": verdict,
            "rationale": rationale,
            "executor_model": response.get("model", ""),
            "executor_provider": response.get("provider", ""),
            "executor_response_id": response.get("response_id", ""),
            **extra_fields,
        })

    # Build the confirmation artifact.
    payload = {
        "schema_version": CONFIRMATION_VERSION,
        "source_audit_digest": audit.get("audit_digest", ""),
        "source_ir_digest": ir.get("artifact_digest", ""),
        "executor": {
            "model": getattr(executor, "model", ""),
            "provider": getattr(executor, "provider", "")
            if hasattr(executor, "provider")
            else "",
            "temperature": getattr(executor, "temperature", 0),
        },
        "status": "BLOCKED" if is_blocked else "COMPLETED",
        "confirmations": confirmations,
        "summary": {
            "total": len(confirmations),
            "confirmed": sum(
                1 for c in confirmations if c["verdict"] == "CONFIRMED"
            ),
            "rejected": sum(
                1 for c in confirmations if c["verdict"] == "REJECTED"
            ),
            "unclear": sum(
                1 for c in confirmations if c["verdict"] == "UNCLEAR"
            ),
            "blocked": sum(
                1 for c in confirmations if c["verdict"] == "BLOCKED"
            ),
        },
    }
    digest = digest_payload(payload)
    artifact = dict(payload)
    artifact["confirmation_digest"] = digest
    return artifact
