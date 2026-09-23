# ADR-0002: Conservative Frontmatter Parser for L1

**Status:** Accepted for L1  
**Date:** 2026-09-23  
**Reversibility:** one-way-ish; changing the accepted syntax changes corpus coverage and artifact output

## Forces at the time

- Real skills use frontmatter with scalar values, simple nested mappings, and folded/literal block descriptions.
- L1 needs to compile a real corpus without silently dropping metadata.
- A new parser dependency would enlarge the supply-chain and runtime surface before the IR contract is stable.
- The compiler is an evidence boundary: silently accepting syntax it cannot preserve would create a false artifact.

## Decision

L1 implements a bounded frontmatter subset sufficient for the current corpus:

- top-level scalar key/value pairs;
- one-level nested mappings;
- folded (`>`) and literal (`|`) block scalar values;
- quoted scalar unwrapping;
- explicit path-bearing errors for unsupported or malformed syntax.

The parser preserves the resulting metadata in the IR and does not silently coerce unsupported YAML structures. Full YAML compatibility is not claimed.

## Alternatives rejected

- **Use a general YAML dependency immediately** — rejected for L1 because it would expand the dependency/trust surface before the artifact contract is stable. Best argument for it: broader compatibility and less custom parsing.
- **Accept only flat scalar metadata** — rejected because the real corpus already contains nested metadata and block descriptions. Best argument for it: smaller parser and easier reasoning.
- **Skip unsupported files and continue** — rejected because a partial corpus artifact would look complete unless every omission became explicit. Best argument for it: one malformed skill would not block unrelated analysis.

## Assumption this rests on

The first corpus contract does not require arbitrary YAML features such as sequences, anchors, aliases, or multi-level nested structures. If that assumption fails, the compiler must add an explicit schema/parser boundary rather than silently widening coercion.

## Consequences

Accepted now:

- L1 remains dependency-light and deterministic;
- real current corpus formats are represented;
- unsupported syntax fails visibly with a source path.

Deferred:

- full YAML semantics;
- schema validation beyond fields required by the IR;
- semantic interpretation of arbitrary Markdown prose.

## Revisit trigger

Revisit when a selected external corpus contains required frontmatter syntax outside this subset, or when a false artifact is possible because a supported value is parsed differently from the agent runtime's YAML parser.
