"""Read-only HTML viewer for sealed artifacts (L8).

The viewer reads a JSON artifact (any level or composite report) and
produces a self-contained HTML page that renders it. The viewer does
NOT compute anything: it does not re-run audits, re-compute digests, or
make decisions. It is a pure projection of the sealed artifact.

The HTML is self-contained: inline CSS, no external dependencies, no
JavaScript that computes anything. It is read-only.
"""

from __future__ import annotations

import html
import json
from typing import Any


def render_artifact_html(artifact: dict[str, Any]) -> str:
    """Render a sealed artifact as a self-contained HTML page.

    The artifact can be any level output (L1-L7) or a composite report.
    The viewer inspects the artifact's version field to determine the
    rendering strategy. It does NOT re-compute anything.
    """
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Crucible Artifact Viewer</title>",
        "<style>",
        _CSS,
        "</style>",
        "</head>",
        "<body>",
        '<div class="container">',
    ]

    # Determine artifact type from version field.
    version = (
        artifact.get("report_version")
        or artifact.get("loop_version")
        or artifact.get("bob_version")
        or artifact.get("behavioral_version")
        or artifact.get("mutation_version")
        or artifact.get("graph_version")
        or artifact.get("audit_version")
        or artifact.get("schema_version")
        or "unknown"
    )

    parts.append(f'<h1>Crucible Artifact</h1>')
    parts.append(f'<p class="version">Version: <code>{html.escape(version)}</code></p>')

    # Render the digest if present.
    for digest_key in (
        "report_digest",
        "loop_digest",
        "behavioral_digest",
        "mutation_digest",
        "graph_digest",
        "audit_digest",
        "artifact_digest",
    ):
        if digest_key in artifact:
            parts.append(
                f'<p class="digest">{html.escape(digest_key)}: '
                f'<code>{html.escape(str(artifact[digest_key]))}</code></p>'
            )
            break

    # Render Nebius blocked status if present.
    if "nebius_blocked" in artifact:
        blocked = artifact["nebius_blocked"]
        cls = "blocked" if blocked else "available"
        parts.append(f'<p class="status {cls}">Nebius: {"BLOCKED" if blocked else "AVAILABLE"}</p>')
        if artifact.get("block_reason"):
            parts.append(
                f'<p class="status-detail">{html.escape(str(artifact["block_reason"]))}</p>'
            )

    # Render composite report.
    if "levels" in artifact:
        parts.extend(_render_levels(artifact["levels"]))

    # Render findings if present.
    if "findings" in artifact and isinstance(artifact["findings"], list):
        parts.extend(_render_findings(artifact["findings"]))

    # Render mutation results if present.
    if "results" in artifact and isinstance(artifact["results"], list):
        parts.extend(_render_mutation_results(artifact["results"]))

    # Render behavioral runs if present.
    if "runs" in artifact and isinstance(artifact["runs"], list):
        parts.extend(_render_behavioral_runs(artifact["runs"]))

    # Render behavioral replay if present.
    if "behavioral_replay" in artifact and artifact["behavioral_replay"]:
        parts.extend(_render_behavioral_replay(artifact["behavioral_replay"]))

    # Render outcome if present.
    if "outcome" in artifact:
        outcome = artifact["outcome"]
        cls = "accepted" if outcome == "ACCEPTED" else "rejected"
        parts.append(
            f'<p class="outcome {cls}">Outcome: <strong>{html.escape(str(outcome))}</strong></p>'
        )
        if artifact.get("rejection_reason"):
            parts.append(
                f'<p class="rejection">Reason: {html.escape(str(artifact["rejection_reason"]))}</p>'
            )

    # Render summary if present.
    if "summary" in artifact:
        parts.extend(_render_summary(artifact["summary"]))

    # Render limitations if present.
    if "limitations" in artifact and isinstance(artifact["limitations"], list):
        parts.extend(_render_limitations(artifact["limitations"]))

    # Render chain of custody digests.
    parts.extend(_render_chain_of_custody(artifact))

    parts.append("</div>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def _render_levels(levels: dict[str, Any]) -> list[str]:
    parts = ['<h2>Levels</h2>']
    for level_id in sorted(levels):
        level = levels[level_id]
        parts.append(f'<div class="level">')
        parts.append(f'<h3>{html.escape(level_id)}</h3>')
        parts.append('<table>')
        for key in sorted(level):
            value = level[key]
            parts.append(
                f'<tr><td class="key">{html.escape(key)}</td>'
                f'<td>{_render_value(value)}</td></tr>'
            )
        parts.append('</table>')
        parts.append('</div>')
    return parts


def _render_findings(findings: list[dict[str, Any]]) -> list[str]:
    parts = ['<h2>Findings</h2>']
    if not findings:
        parts.append('<p class="empty">No findings.</p>')
        return parts
    parts.append('<table class="findings">')
    parts.append('<tr><th>ID</th><th>Class</th><th>Skill</th><th>Status</th><th>Evidence</th></tr>')
    for f in findings:
        parts.append(
            f'<tr><td>{html.escape(str(f.get("id", "")))}</td>'
            f'<td>{html.escape(str(f.get("class", "")))}</td>'
            f'<td>{html.escape(str(f.get("skill", "")))}</td>'
            f'<td>{html.escape(str(f.get("epistemic_status", "")))}</td>'
            f'<td>{html.escape(str(f.get("evidence", "")))}</td></tr>'
        )
    parts.append('</table>')
    return parts


def _render_mutation_results(results: list[dict[str, Any]]) -> list[str]:
    parts = ['<h2>Mutation Results</h2>']
    parts.append('<table class="mutations">')
    parts.append('<tr><th>ID</th><th>Class</th><th>Status</th><th>Survivor</th><th>Evidence</th></tr>')
    for r in results:
        sc = r.get("survivor_classification") or ""
        parts.append(
            f'<tr><td>{html.escape(str(r.get("mutation_id", "")))}</td>'
            f'<td>{html.escape(str(r.get("mutation_class", "")))}</td>'
            f'<td class="status-{html.escape(str(r.get("status", "")).lower())}">'
            f'{html.escape(str(r.get("status", "")))}</td>'
            f'<td>{html.escape(str(sc))}</td>'
            f'<td>{html.escape(str(r.get("evidence", "")))}</td></tr>'
        )
    parts.append('</table>')
    return parts


def _render_behavioral_runs(runs: list[dict[str, Any]]) -> list[str]:
    parts = ['<h2>Behavioral Differential</h2>']
    parts.append('<table class="behavioral">')
    parts.append('<tr><th>Variant</th><th>Status</th><th>Properties</th></tr>')
    for r in runs:
        observations = r.get("observations", [])
        props = ", ".join(
            f'{html.escape(str(o.get("property_id", "")))}='
            f'{html.escape(str(o.get("status", "")))}'
            for o in observations
        )
        parts.append(
            f'<tr><td>{html.escape(str(r.get("variant_id", "")))}</td>'
            f'<td>{html.escape(str(r.get("status", "")))}</td>'
            f'<td>{props}</td></tr>'
        )
    parts.append('</table>')
    return parts


def _render_behavioral_replay(replay: dict[str, Any]) -> list[str]:
    parts = ['<h2>Behavioral Replay</h2>']
    regression = replay.get("regression", False)
    cls = "regression-yes" if regression else "regression-no"
    parts.append(
        f'<p class="{cls}">Regression: <strong>{regression}</strong></p>'
    )
    regressions = replay.get("regressions", [])
    if regressions:
        parts.append('<table class="regressions">')
        parts.append('<tr><th>Property</th><th>Original</th><th>Repaired</th></tr>')
        for reg in regressions:
            parts.append(
                f'<tr><td>{html.escape(str(reg.get("property_id", "")))}</td>'
                f'<td>{html.escape(str(reg.get("original_status", "")))}</td>'
                f'<td>{html.escape(str(reg.get("repaired_status", "")))}</td></tr>'
            )
        parts.append('</table>')
    return parts


def _render_summary(summary: dict[str, Any]) -> list[str]:
    parts = ['<h2>Summary</h2>']
    parts.append('<table>')
    for key in sorted(summary):
        parts.append(
            f'<tr><td class="key">{html.escape(key)}</td>'
            f'<td>{_render_value(summary[key])}</td></tr>'
        )
    parts.append('</table>')
    return parts


def _render_limitations(limitations: list[dict[str, Any]]) -> list[str]:
    parts = ['<h2>Limitations (Honest Abstentions)</h2>']
    parts.append('<ul class="limitations">')
    for lim in limitations:
        parts.append(
            f'<li><strong>{html.escape(str(lim.get("check_class", "")))}</strong>: '
            f'{html.escape(str(lim.get("reason", "")))}</li>'
        )
    parts.append('</ul>')
    return parts


def _render_chain_of_custody(artifact: dict[str, Any]) -> list[str]:
    parts = ['<h2>Chain of Custody</h2>']
    parts.append('<table class="custody">')
    for key in sorted(artifact):
        if "digest" in key.lower() and isinstance(artifact[key], str):
            parts.append(
                f'<tr><td class="key">{html.escape(key)}</td>'
                f'<td><code>{html.escape(str(artifact[key]))}</code></td></tr>'
            )
    parts.append('</table>')
    return parts


def _render_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return f'<pre>{html.escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))}</pre>'
    if isinstance(value, bool):
        return f'<span class="bool">{value}</span>'
    if isinstance(value, int):
        return f'<span class="int">{value}</span>'
    return html.escape(str(value))


_CSS = """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; padding: 20px; background: #f5f5f5; color: #222; }
.container { max-width: 960px; margin: 0 auto; background: #fff; padding: 40px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
h1 { margin-top: 0; color: #1a1a2e; }
h2 { margin-top: 32px; border-bottom: 2px solid #e0e0e0; padding-bottom: 8px; color: #1a1a2e; }
h3 { color: #333; }
.version { color: #666; font-size: 14px; }
.digest { font-size: 12px; color: #555; word-break: break-all; }
.digest code { background: #f0f0f0; padding: 2px 4px; border-radius: 3px; }
.status { font-weight: bold; padding: 4px 8px; border-radius: 4px; display: inline-block; margin: 4px 0; }
.status.blocked { background: #fff3cd; color: #856404; }
.status.available { background: #d4edda; color: #155724; }
.status-detail { font-size: 13px; color: #666; margin-top: 4px; }
.outcome { font-size: 18px; padding: 8px 12px; border-radius: 4px; display: inline-block; margin: 8px 0; }
.outcome.accepted { background: #d4edda; color: #155724; }
.outcome.rejected { background: #f8d7da; color: #721c24; }
.rejection { color: #721c24; font-size: 14px; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th, td { text-align: left; padding: 8px 12px; border: 1px solid #ddd; vertical-align: top; }
th { background: #f8f8f8; font-weight: 600; }
td.key { font-weight: 600; color: #555; width: 200px; }
.findings th, .mutations th, .behavioral th, .custody th { font-size: 13px; }
.status-killed { color: #155724; font-weight: bold; }
.status-survived { color: #856404; font-weight: bold; }
.status-abstained { color: #6c757d; font-weight: bold; }
.regression-yes { color: #721c24; }
.regression-no { color: #155724; }
.limitations { color: #555; }
.limitations li { margin-bottom: 8px; }
.empty { color: #999; font-style: italic; }
pre { background: #f8f8f8; padding: 8px; border-radius: 4px; overflow-x: auto; font-size: 12px; }
.bool { color: #007bff; }
.int { color: #28a745; }
.level { margin-bottom: 24px; padding: 16px; background: #fafafa; border-radius: 6px; }
"""
