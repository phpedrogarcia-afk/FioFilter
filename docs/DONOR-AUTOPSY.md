# FioFilter — Donor Autopsy

**Mission**: FIOFILTER-M01-FOUNDATION  
**Scope**: Bounded — three donors only  
**Date**: 2026-09-15  
**Internet evidence**: Verified from live upstream repositories

**Principle**: Our own experimental evidence (P3, P11, P13, P14 corpus) outranks
donor marketing claims for our workload.

---

## Donor A: `rtk-ai/rtk`

**Description**: CLI proxy written in Rust. Intercepts shell commands and rewrites
them to `rtk` equivalents before execution. Filters output by command name.
Single binary, zero external runtime dependencies.

**Verified source**: https://github.com/rtk-ai/rtk  
**Language**: Rust  
**Architecture**: Binary CLI proxy + agent hook (PreToolUse or equivalent)  
**Marketing claim**: 60–90% token reduction on common dev commands

---

### RTK Mechanisms

#### RTK-M1: Command-Name-Based Routing

**Mechanism**: RTK intercepts shell commands and routes them to named filters:
`rtk git log`, `rtk cargo test`, `rtk aws sts`, etc. Filter selection is by
command name lookup, not evidence classification.

**Benefit**: Fast, zero-latency routing; no classification overhead.

**Failure Mode**: Evidence-blind. `rtk git status` applies git-specific formatting
regardless of what `git status` means in context. A `git status` showing
unexpected merge conflicts or untracked critical files gets the same compression
as a clean one. This is how RTK destroyed canonical/security evidence in our workload.

**Classification**: DELETE (as a routing mechanism). The concept of command-awareness
is valid, but routing by command name alone without evidence classification is unsafe.

**FioFilter Interpretation**: FioFilter classifies evidence first, then consults
profiles. Command metadata may inform classification but never determines disposition
alone. The classifier may use command name as a *hint*, not an *authority*.

---

#### RTK-M2: Output Regex Filters

**Mechanism**: Per-command regex patterns strip noise from output. Example:
`git push` → retain only the final "ok main" line; progress and counting lines removed.

**Benefit**: Dramatically reduces noise for well-understood commands. Deterministic.

**Failure Mode**: Regexes fire without evidence classification. On a `git push`
that fails mid-stream, the "ok" filter may suppress the failure output. Applied to
diagnostic or canonical outputs, regexes destroy evidence without awareness of
its role.

**Classification**: ADAPT. Pattern-based reduction is valid *after* the evidence
classifier confirms the output is NOISE or PROGRESS. Never applied blindly.

**FioFilter Interpretation**: T01 (duplicate-line folding) is the V0 equivalent —
a deterministic structural transform applied only after evidence class and invariant
checks permit it.

---

#### RTK-M3: Auto-Rewrite Hook

**Mechanism**: A PreToolUse hook (or shell hook) transparently rewrites all Bash
commands to `rtk` equivalents before execution. "100% RTK adoption across all
conversations and subagents."

**Benefit**: Zero per-command overhead; comprehensive coverage.

**Failure Mode**: Hook scope includes ALL commands. RTK's own docs note that
built-in tools (Read, Grep, Glob) bypass the hook — but the hook still applies
to arbitrary shell commands including those carrying security, canonical, or
diagnostic evidence.

**Classification**: ADOPT-CONCEPT (hook architecture) for future integration;
DELETE for V0. M01 spec section 13: "Do not integrate hooks into Codex."

**FioFilter Interpretation**: A hook architecture is the correct long-term
integration point. V0 builds the engine independently so the hook integration
can be tested before being trusted.

---

#### RTK-M4: SQLite Recovery Store

**Mechanism**: Since v0.37.x, RTK uses SQLite to store full unfiltered output
on failure or truncation. Recovery: `rtk recall {hash}`.

**Benefit**: Full output available on demand; no re-execution needed.

**Failure Mode**: Recovery requires an additional model turn. Recovery is
failure/truncation-driven only — successful runs are not stored unless
`tee_on_success = true`. This means the store is inconsistently populated.

**Classification**: ADOPT-CONCEPT (recovery on demand) but REPLACE with
FioFilter's always-write RAW store.

**FioFilter Interpretation**: FioFilter writes RAW before every transform
attempt, not only on failure. The store is always complete. Recovery is always
possible. This eliminates the inconsistency in RTK's approach.

---

#### RTK-M5: Telemetry (`rtk gain`)

**Mechanism**: RTK tracks estimated token savings per command and per session.
`rtk gain --graph` shows ASCII trends.

**Benefit**: Makes savings visible; encourages adoption.

**Failure Mode**: Reports local output reduction as "token savings." Does not
distinguish between: local bytes reduced, estimated tokens reduced, model turns,
corrective retrievals, or whole-mission economics. Violates FioFilter's I14/I15.

**Classification**: ADOPT-CONCEPT (per-result telemetry) but REPLACE with
metrics that properly separate the dimensions.

**FioFilter Interpretation**: `fiofilter/metrics.py` tracks all six dimensions
from day one. No conflation permitted.

---

#### RTK-M6: No Evidence Taxonomy

**Mechanism**: N/A — RTK has no evidence taxonomy. All output is equally eligible
for compression if a command-name filter exists.

**Failure Mode**: This is the root cause of RTK's rejection for our workload.
Diagnostic, canonical, security, and authority evidence receive the same
treatment as noise.

**Classification**: REPLACE. FioFilter's 12-class evidence taxonomy is the
direct replacement for this missing layer.

---

### RTK Summary

| Concept | Classification | Note |
|---|---|---|
| Command-aware routing | ADAPT | By evidence class, not by command name |
| Regex output filters | ADAPT | After evidence classification only |
| Auto-rewrite hook | ADOPT-CONCEPT | Future only; not V0 |
| SQLite recovery store | ADOPT-CONCEPT → REPLACE | Always-write RAW store instead |
| Per-session telemetry | ADOPT-CONCEPT → REPLACE | With proper metric separation |
| No evidence taxonomy | REPLACE | Core FioFilter differentiator |

**RTK Rejection Rationale (Empirical)**: RTK was tested on the FioOS workload
and rejected because compressed representations destroyed or distorted diagnostic,
directory, progress, JSON, and canonical/security evidence. This empirical finding
outranks RTK's marketed 60–90% reduction claim for our workload.

---

## Donor B: `linger-alpha/command-compressor-agent` (CCA)

**Description**: Post-execution tool result compressor for coding agents. Sits
between tool execution and the next model turn. Rule-based splitter (no LLM).
Fail-open. Node.js.

**Verified source**: https://github.com/linger-alpha/command-compressor-agent  
**Language**: Node.js  
**Architecture**: PostToolUse hook → block splitter → tier classifier → adapter  
**Marketing claim**: 22.04% reduction on eligible subset; 9.62% across all tool results

---

### CCA Mechanisms

#### CCA-M1: Rule-Based Block Splitter

**Mechanism**: A linear splitter groups adjacent lines using: blank regions,
timestamps, log levels, traceback state, indentation changes, repetition changes.
No model call; no command-name routing.

**Benefit**: Language-agnostic; works on any text output; deterministic.

**Failure Mode**: Splitting is heuristic. Evidence boundaries may not align
with structural boundaries. A JSON object split across a blank line could be
split incorrectly.

**Classification**: ADOPT-CONCEPT. FioFilter's classifier uses similar structural
signals but operates at the whole-output level (evidence class assignment) rather
than at the block level. Block-level splitting is a V0+ candidate.

**FioFilter Interpretation**: FioFilter's T01 (duplicate-line folding) is
simpler and more conservative than CCA's block splitter. Block splitting is a
future candidate transform (T02: template folding) deferred to M02.

---

#### CCA-M2: Three-Tier Action Assignment

**Mechanism**: Each block is assigned one of: Preserve, Light, Strong.
- **Preserve**: Tracebacks, failures, encoded/binary data, high-value diagnostics
- **Light**: Collapse duplicates, retain head/tail/critical lines
- **Strong**: Remove progress noise, fold repetitive low-information output

**Benefit**: Graduated compression respects evidence value. Tracebacks are not
folded. Noise is strongly compressed.

**Failure Mode**: The tier assignment is rule-based but lacks a formal evidence
taxonomy. The "Preserve" tier correctly identifies tracebacks and failures, but
the classification of "high-value diagnostics" is heuristic and the P14 corpus
showed 70.1% inline fact preservation — meaning 29.9% of critical facts were
not preserved inline.

**Classification**: ADOPT-CONCEPT → REPLACE. FioFilter replaces CCA's implicit
three-tier system with an explicit 12-class evidence taxonomy plus invariant I4
(100% inline fact preservation).

**FioFilter Interpretation**: FioFilter's disposition table (per class × mode)
is the explicit replacement for CCA's tier assignment. The key difference: I4
requires 100% inline fact preservation, which CCA did not achieve.

---

#### CCA-M3: `raw_ref` Recovery System

**Mechanism**: Every transformed result carries a `raw_ref` pointing to the
locally stored original output. Recovery is possible without re-executing the
command.

**Benefit**: Byte-exact recovery without network calls or re-execution.

**Failure Mode**: CCA demonstrated that `raw_ref` alone is insufficient. The
P14 corpus showed: exact RAW recovery was available for all 40 results, but
96/137 critical facts (70.1%) were preserved inline. The remaining 29.9% were
only accessible via `raw_ref` — requiring an additional model turn to retrieve.
CCA was rejected on this basis.

**Classification**: KEEP (mechanism) + extend with I4.

**FioFilter Interpretation**: FioFilter adopts the content-addressable RAW store
concept and extends it with I4: critical inline-required facts must be present
in the visible output. A `raw_ref` is a recovery mechanism, not a license to
remove evidence.

---

#### CCA-M4: Fail-Open Behavior

**Mechanism**: If any adapter or compressor component fails, the agent receives
the original Tool Result unchanged.

**Benefit**: Compression failures are silent and safe. The agent never sees an
error from compression — it just sees more tokens.

**Failure Mode**: None identified. This is correct behavior.

**Classification**: KEEP. FioFilter's fail-open rule is identical: any exception
in the pipeline → return RAW.

---

#### CCA-M5: Command Scope Exemption

**Mechanism**: Inspection commands, raw fallback reads, and RTK-managed commands
pass through CCA unchanged.

**Benefit**: Prevents double-compression; respects existing tools.

**Failure Mode**: Requires maintaining an exemption list. Exemptions can become
stale as new commands are added.

**Classification**: ADOPT-CONCEPT. FioFilter handles this through evidence
classification: inspection commands producing CANONICAL_STATE output will be
routed to RAW by the taxonomy table, not by a command exemption list.

---

#### CCA-M6: Benchmark Evidence

**From CCA's own benchmark (Terminal-Bench 2.1, 80 trials):**

- Whole-mission reduction: 9.62% across all tool results
- Eligible subset reduction: 22.04%
- CCA produced 1 additional success and 2 additional failures vs. no compression
- 1 failure confirmed unrelated to compression
- 1 failure caused by compressed `curl GET` output preventing README access
  (violating inline-fact preservation — the exact failure mode I4 addresses)

**FioFilter Interpretation**: CCA's 9.62% whole-mission reduction is the best
published peer benchmark for our category. FioFilter's goal is not to beat this
number on CCA's benchmark — it's to achieve higher inline fact preservation
(100% vs 70.1%) while maintaining competitive reduction on eligible classes.

The `curl GET` failure case is a direct empirical confirmation that compressed
output without inline fact preservation causes corrective retrievals and task
failures. This is why I4 exists.

---

### CCA Summary

| Concept | Classification | Note |
|---|---|---|
| Rule-based block splitter | ADOPT-CONCEPT | Evidence class assignment is FioFilter's equivalent |
| Three-tier action assignment | ADOPT-CONCEPT → REPLACE | Replaced by 12-class taxonomy + disposition table |
| `raw_ref` recovery system | KEEP + extend | Plus I4: inline facts must stay in visible output |
| Fail-open behavior | KEEP | Identical in FioFilter |
| Command scope exemption | ADOPT-CONCEPT | Via evidence classification, not exemption lists |
| Benchmark evidence | USE | 9.62% whole-mission / 22.04% eligible; curl failure case validates I4 |

**CCA Rejection Rationale (Empirical)**: CCA was tested on the P14 FioOS corpus
(40 tool results). Despite exact RAW recovery, 96/137 critical inline facts were
preserved (70.1%). The remaining 29.9% required an additional model turn via
`raw_ref`. The four genuinely compression-eligible outputs produced 1578→1578
estimated tokens (0% reduction). CCA was rejected because reversibility alone
is not sufficient.

---

## Donor C: `Open330/context-compress`

**Description**: MCP server + hook toolkit. Compresses tool output using multiple
modes including LLM-judged auto mode. Stores output in FTS5 SQLite index for
searchable retrieval. TypeScript/Node.js.

**Verified source**: https://github.com/Open330/context-compress  
**Language**: TypeScript  
**Architecture**: MCP server with 8 tools + PreToolUse hook + FTS5 index  
**Marketing claim**: 93% token reduction in aggressive mode

---

### context-compress Mechanisms

#### CC-M1: MCP Server Architecture

**Mechanism**: Registers as a Claude Code MCP server. Agents call `execute`,
`batch_execute`, `index`, `search`, `fetch_and_index` tools directly.

**Benefit**: Clean integration with MCP-compatible agents; explicit opt-in by agent.

**Failure Mode**: Requires MCP infrastructure. FioFilter V0 explicitly excludes
MCP (non-goal). Also: every MCP tool call is a round-trip that may add latency
or turn overhead.

**Classification**: DELETE for V0. ADOPT-CONCEPT for future integration surface.

---

#### CC-M2: FTS5 Full-Text Index

**Mechanism**: Large outputs are indexed in a local SQLite FTS5 database.
Agents can search indexed content via the `search` tool.

**Benefit**: Indexed content is searchable without re-execution; potentially
removes the need for corrective retrieval.

**Failure Mode**: Each `search` call is a model turn. If the agent must search
multiple times to recover facts, the index adds turns instead of saving them.
P11 empirical evidence: turn reduction is the largest savings lever. Adding
search turns may negate local savings.

**Classification**: ADOPT-CONCEPT for INDEX disposition (future). In V0, INDEX
is a disposition candidate but is not implemented.

**FioFilter Interpretation**: INDEX is a valid disposition for DISCOVERY and
large EXPLORE outputs where content is browsable. But the corrective retrieval
cost must be accounted for (I10). Not in V0.

---

#### CC-M3: Four Compression Modes

**Mechanism**: `auto` (LLM-judged), `aggressive`, `balanced`, `conservative`.
The `auto` mode uses an LLM to decide which mode to apply per output.

**Benefit**: Adaptive; LLM judgment may catch nuance that rules miss.

**Failure Mode**: LLM in the compression path is non-deterministic, adds token
cost to save tokens, and cannot be tested with deterministic oracles. This is
the failure mode FioFilter's I11 invariant was written to prevent.

**Classification**: DELETE for V0 and probably permanently. The `aggressive`,
`balanced`, `conservative` concept maps to FioFilter's EXPLORE/BUILD/PROVE
modes — but determined by context, not by caller-selected strings.

---

#### CC-M4: No Evidence Taxonomy

**Mechanism**: N/A — context-compress has no formal evidence taxonomy.
All content is treated by mode and heuristic patterns, not by epistemic class.

**Failure Mode**: Same as RTK: authority, security, diagnostic, and canonical
evidence receive no special protection.

**Classification**: REPLACE. FioFilter's taxonomy is the replacement.

---

#### CC-M5: `outputSchema`-Free Design

**Mechanism**: No MCP tool declares an `outputSchema`. This prevents the MCP
protocol from requiring both `structuredContent` and a serialized text copy,
which would double-bill the content to the context window.

**Benefit**: Avoids double-billing; reduces context overhead from the MCP layer itself.

**Failure Mode**: None for this specific decision.

**Classification**: ADOPT-CONCEPT if FioFilter ever builds an MCP integration.
File under "things context-compress got right."

---

### context-compress Summary

| Concept | Classification | Note |
|---|---|---|
| MCP server architecture | DELETE V0 / ADOPT-CONCEPT future | Non-goal in V0 |
| FTS5 index + search | ADOPT-CONCEPT → INDEX disposition | Future; costly in model turns |
| LLM auto mode | DELETE | Violates I11; non-deterministic |
| Four compression modes | ADAPT | → EXPLORE/BUILD/PROVE mode model |
| No evidence taxonomy | REPLACE | FioFilter taxonomy is the replacement |
| outputSchema-free design | ADOPT-CONCEPT | For future MCP integration |

---

## Cross-Donor Synthesis

| Concept | Best Donor | FioFilter Treatment |
|---|---|---|
| Command-aware routing | RTK | ADAPT → evidence-class routing instead |
| Structural noise filters | CCA (block splitter) | T01 in V0; T02+ future |
| RAW store / recovery | CCA (`raw_ref`) | ADOPT + I4 (inline facts mandatory) |
| Fail-open | CCA | KEEP identical |
| Session telemetry | RTK (`rtk gain`) | REPLACE with I14/I15-compliant metrics |
| LLM summarization | context-compress | DELETE permanently from V0 |
| Index/search retrieval | context-compress | ADOPT-CONCEPT for INDEX disposition |
| Evidence taxonomy | None | BUILD — core differentiator |
| Economic accounting | None (all three fail I15) | BUILD as first-class primitive |
| Inline-fact protection (I4) | Partially in CCA (70.1%) | BUILD to 100% |

---

## Donors Not Evaluated

No other tools were evaluated per D007 (no compressor tournament).
If a new tool is proposed for evaluation, add it as Donor D and record
the evaluation decision in DECISIONS.md.
