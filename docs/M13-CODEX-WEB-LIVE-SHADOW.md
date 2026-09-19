# M13 — Codex Web live shadow and Efficiency Feed v1

## Status and scope

M13 begins live validation without placing FioFilter in the Codex execution
path. The observed base was commit
`973e2f8452b02e132216861b9c163bb749eb3006`, tree
`aeea14d509dabcc28556a3e655384043d1eeca5e`. Offline V0 remains frozen.

```text
CODEX_RUNTIME_BEHAVIOR_CHANGED=NO
ACTIVE_READ_REFERENCE_SUPPRESSION=NO
AUTO_CONTEXT_SELECTION=NO
AUTOMATIC_T02=NO
PROXY=NO
MCP=NO
HOOK_THAT_MODIFIES_OUTPUT=NO
```

The M13 direction is `AGENT_EVENT_IN -> AGENT_EVENT_OUT -> shadow observation`.
The adapter observes metadata after RAW delivery. It cannot delay, rewrite,
suppress, truncate, reroute or substitute the delivered output.

## Codex Web runtime surface census

The census used environment-variable names, local database schemas and the tool
protocol available to this task. It did not read prompt/message rows, environment
secret values or private payloads. Raw identifiers below are never stored; the
adapter uses SHA-256 digests.

| Field | Availability | Scope |
|---|---|---|
| session ID | `EXACT_STRUCTURED` | `CODEX_SESSION_ID` / `CODEX_THREAD_ID`; hash only in feed |
| task/run ID | `NOT_AVAILABLE` | bootstrap-attempt identity is not assumed to be run identity |
| bootstrap attempt ID | `EXACT_STRUCTURED` | distinct runtime field; not exported as `run_id_hash` |
| task query/prompt | `EXACT_UNSTRUCTURED` | visible to the agent, not a supported structured input feed |
| model identifier | `NOT_AVAILABLE` | no current-run model field exposed to repository code |
| tool call ID | `NOT_AVAILABLE` | protocol does not expose a stable call ID to repository code |
| tool name | `EXACT_STRUCTURED` | visible to the agent-side tool protocol |
| tool arguments | `EXACT_STRUCTURED` | visible to the agent-side tool protocol; never persisted by the feed |
| tool output | `EXACT_STRUCTURED` | delivered protocol result; no repository-side subscription |
| file-read event | `DERIVABLE_DETERMINISTICALLY` | only for explicitly observed tool calls |
| command execution / exit | `EXACT_STRUCTURED` | protocol result for the observed command |
| CWD / repository root | `DERIVABLE_DETERMINISTICALLY` | local process and Git state |
| Git HEAD / worktree state | `DERIVABLE_DETERMINISTICALLY` | Git plus `WORKTREE_STATE_DIGEST_V2` |
| timestamps | `DERIVABLE_DETERMINISTICALLY` | observer time, not a provider delivery timestamp |
| turn boundaries | `NOT_AVAILABLE` | no structured current-run turn stream |
| input/output/cached/reasoning tokens | `NOT_AVAILABLE` | no exact current-run accounting surface |
| context-window metadata | `NOT_AVAILABLE` | not exposed for the current run |
| provider-side accounting | `NOT_AVAILABLE` | not exposed for the current run |
| stream identity | `NOT_AVAILABLE` | combined tool result does not prove stdout/stderr identity |
| truncation status | `NOT_AVAILABLE` | no repository-consumable structural flag |

The local Codex SQLite schema contains columns capable of representing some of
these concepts for other runs, but there was no current-thread row, rollout or
matching log record. Schema existence is not current-run evidence.

```text
PASSIVE_CODEX_EVENT_SURFACE=UNAVAILABLE
TOKEN_USAGE_EXACT=UNAVAILABLE
TOKEN_ESTIMATE_REPORTED_AS_ACTUAL=NO
UI_SCRAPING=NOT_USED
DOM_AUTOMATION=NOT_USED
SCREEN_OCR=NOT_USED
```

## Adapter architecture

`fiofilter.codex_web_shadow.CodexWebShadowEventAdapter` is intentionally named
for the one runtime inspected; it is not an invented generic provider layer.
Its input is a sanitized, post-delivery event containing hashes, byte count,
tool family and optional structural evidence. Command text may exist transiently
for the existing parsers but is absent from `FIO_EFFICIENCY_FEED_V1`.

Read observations reuse `RuntimeReceiptState`. A passive repeat can establish
`PASSIVE_F1_DELIVERY_IDENTITY`; it cannot establish `DIRECT_EXECUTION_F4`.
`BYTE_IDENTITY_PROVEN` is not `BEHAVIORAL_EQUIVALENCE_PROVEN`, and model salience
effects remain unknown.

Discovery reuses `DiscoveryRuntimeShadow` only when task text is
`EXACT_STRUCTURED`. T02 reuses `RgStandardLosslessGrouping` only when producer,
single-command, exit, truncation and stream evidence is complete. Every shadow
method preserves RAW object identity; no optimization is authorized.

## Real M13 observation

Instrumentation began after M13 work had already started. The denominator is one
`REAL_CODEX_PARTIAL_SESSION`, not a full session and not evidence of general
reliability. A genuine implementation review read the complete adapter twice
without an intervening byte change.

| Metric | Observed |
|---|---:|
| `REAL_CODEX_SESSION_COUNT` | 1 |
| `REAL_CODEX_FULL_SESSION_COUNT` | 0 |
| `REAL_CODEX_PARTIAL_SESSION_COUNT` | 1 |
| `TOOL_CALL_COUNT` in observed slice | 2 |
| `TOOL_OUTPUT_BYTES` | 41,830 |
| `FILE_READ_EVENTS` | 2 |
| `FIRST_READS` | 1 |
| `REPEATED_SOURCE_VIEW_READS` | 1 |
| `EXACT_IDENTICAL_REPEAT_EVENTS` | 1 |
| `EXACT_IDENTICAL_REPEAT_BYTES` | 20,915 |
| `F4_PROVEN_EVENTS` | 0 |
| `REFERENCE_ECONOMIC_EVENTS` | 1 |
| `HYPOTHETICAL_REFERENCE_BYTES` | 142 |
| `HYPOTHETICAL_BYTES_AVOIDED` | 20,773 |
| call distance | 1 observed call |
| time / turn / episode distance | unavailable |

The record contains one `REEXPOSURE_WASTE_CANDIDATE`. It does not call the bytes
proven avoidable and does not claim token, turn, billing or behavioral savings.
The local payload-free JSONL is outside Git under the user's FioFilter data area.

## Discovery and T02 status

The M13 task prompt is exact unstructured text from the agent's perspective, not
a supported structured runtime input. Discovery was therefore not run for the
real denominator; changed-file recall, target rank, overlap and discovery bytes
avoidable all remain unavailable/unknown.

The current runtime cannot prove stream identity and truncation status to the
repository adapter. Consequently:

```text
SEARCH_OUTPUT_EVENTS=0
STRUCTURALLY_PROVEN_RG_EVENTS=0
T02_TECHNICALLY_APPLICABLE=0
T02_NO_ECONOMIC_GAIN=0
T02_REJECTED=0
T02_HYPOTHETICAL_BYTES_AVOIDED=0
AUTOMATIC_T02_APPLIED=0
T02_ENGINE_METADATA_GATE_STATUS=ENGINE_METADATA_GATE_REMAINS
```

Zero here means no event in the observed slice, not proof that T02 has no live
opportunity.

## `FIO_EFFICIENCY_FEED_V1`

The versioned schema stores hashed session/run/task identity, repository and Git
state, evidence/outcome classes, explicit token measurements, tool-family byte
counts, read/reexposure counts, discovery counts, T02 counts, corrective rereads
and path observations. Repository-relative paths are optional; portable exports
can retain only their hashes. Absolute paths and parent traversal are rejected.

Every token metric is a `(value, token_measurement_quality, basis_bytes)` record.
Allowed qualities are:

- `PROVIDER_REPORTED_EXACT`
- `RUNTIME_REPORTED_EXACT`
- `DERIVED_FROM_EXACT_ACCOUNTING`
- `ESTIMATED_BYTES_DIV_4`
- `UNAVAILABLE`

The aggregate groups token totals by both metric and quality. It never creates a
combined exact-plus-estimated total. It also reports sessions, evidence classes,
outcomes, tool families/bytes, reread volume, discovery volume, T02 opportunity,
corrective rereads and repeatedly read repository files.

The four candidate classes remain distinct:

- `DISCOVERY_WASTE_CANDIDATE`
- `REEXPOSURE_WASTE_CANDIDATE`
- `REPRESENTATION_WASTE_CANDIDATE`
- `HANDOFF_REDUNDANCY_CANDIDATE`

`TELEMETRY != AUTHORITY` and `PATTERN != PROOF`. The feed cannot tune BM25,
enable READREF/T02, modify thresholds or install an integration. The handoff
redundancy analyzer is `DEFERRED_TO_HANDOFF_BRIDGE_MISSION`; Fio Handoff is not
modified by M13.

## Privacy

The committed schema, adapter, tests and this aggregate description contain no
live prompts, messages, credentials, authorization headers, environment secret
values or raw file/tool contents. The feed schema has no fields for those
payloads. It accepts only repository-relative diagnostic paths and hashed private
identifiers. Raw live telemetry and local session contents are not committed.

## First Behavioral A/B candidate

`READ_RECEIPT_REFERENCE` is selected for design of the first narrow A/B trial.
It is the only candidate observed in the real partial slice, has byte-identity
evidence and a reversible treatment surface. The selection does not activate it.

| Candidate | Live frequency | Proof | Current blocker/risk |
|---|---:|---|---|
| `READ_RECEIPT_REFERENCE` | 1/2 observed file reads | F1 identical delivery, 20,773 hypothetical bytes | behavioral equivalence and salience unknown |
| `T02_EXPLICIT_LOSSLESS` | 0 admissible events | offline byte-lossless proof only | current runtime metadata gate |
| `DISCOVERY_ASSIST` | not run | offline ranker only | task text not structurally exposed; discovery savings unknown |

The next experiment must be explicit, bounded and reversible, and must measure
behavior/outcome alongside bytes and any exact token fields that become available.
One partial task is enough to choose what to test first, not enough to establish
general reliability or authorize treatment.

## Limitations

- No passive current-run event subscription was found.
- Exact provider/runtime token usage, model and context window are unavailable.
- Only a partial-session post-observation bridge produced live evidence.
- No full-session discovery or T02 opportunity denominator exists.
- F1 byte identity does not prove F4 freshness or unchanged model behavior.
- No Behavioral A/B treatment is implemented or activated.
