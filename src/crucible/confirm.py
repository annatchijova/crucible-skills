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
NEBIUS_DEFAULT_MAX_TOKENS = 200


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
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return {
                "output": "",
                "error": f"HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:200]}",
                "model": self.model,
                "provider": "nebius-token-factory",
                "blocked": False,
            }
        except urllib.error.URLError as exc:
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

    Returns CONFIRMED if the two skill texts share more than 80% of their
    lines, REJECTED otherwise. This is a deterministic heuristic, not an
    LLM. It exists so the confirmation harness can be tested without
    NEBIUS_API_KEY.
    """

    def __init__(self, threshold: int = 80) -> None:
        self.model = "crucible-mock-confirm/v1"
        self.temperature = 0
        self.max_tokens = 0
        self.threshold = threshold

    def execute(
        self, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        # The user_prompt contains the two skill texts in a structured
        # format. Parse them to compute line overlap.
        # Format: "SKILL_A:\n<text>\n\nSKILL_B:\n<text>\n\nQUESTION: ..."
        skill_a_match = re.search(
            r"SKILL_A:\n(.*?)\n\nSKILL_B:", user_prompt, re.DOTALL
        )
        skill_b_match = re.search(
            r"SKILL_B:\n(.*?)\n\nQUESTION:", user_prompt, re.DOTALL
        )
        if not skill_a_match or not skill_b_match:
            return {
                "output": "UNCLEAR\nCould not parse skill texts.",
                "error": None,
                "model": self.model,
                "provider": "mock-deterministic",
                "temperature": 0,
                "max_tokens": 0,
                "usage": {
                    "prompt_tokens": len(system_prompt) + len(user_prompt),
                    "completion_tokens": 20,
                    "total_tokens": len(system_prompt) + len(user_prompt) + 20,
                },
                "response_id": "mock-unclear",
                "blocked": False,
            }
        text_a = skill_a_match.group(1).strip()
        text_b = skill_b_match.group(1).strip()
        lines_a = set(l.strip() for l in text_a.splitlines() if l.strip())
        lines_b = set(l.strip() for l in text_b.splitlines() if l.strip())
        if not lines_a or not lines_b:
            verdict = "UNCLEAR"
            rationale = "One or both skills have no content."
        else:
            overlap = len(lines_a & lines_b)
            union = len(lines_a | lines_b)
            # Use integer percentage (no float).
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
            # Description.
            desc = skill.get("description", "")
            if desc:
                parts.append(f"Description: {desc}")
            # Rules.
            for rule in skill.get("rules", []):
                parts.append(f"Rule: {rule.get('text', '')}")
            # Checks.
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
        "source_ir_digest": ir.get("digest", ""),
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
