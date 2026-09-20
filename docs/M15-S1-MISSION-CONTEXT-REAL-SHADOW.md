# M15-S1 — real mission-context shadow measurement

## Boundary

```text
READREF_CANARY=OFF
MISSION_CONTEXT=SHADOW_ONLY
PROMPT_DELIVERY_CHANGED=NO
AUTOMATIC_SUPPRESSION=NO
AUTOMATIC_MERGE=NO
FIO_HANDOFF_INTEGRATION=NO
```

M15-S1 adds an explicitly invoked, deterministic measurement surface around the
existing `M15_MISSION_CONTEXT_CONTRACT_V1`. It reads caller-supplied local prompt
bytes and a payload-free manifest, reports structural byte accounting, and always
returns the original prompt bytes as the delivered mission. It has no connection
to the canary, normal FioFilter delivery, Codex App Server, hooks, proxy, daemon,
MCP, or automatic context selection.

The surface is `MissionContextShadowAnalyzer` in
`fiofilter/mission_context_shadow.py`. The local runner is:

```text
python scripts/run_mission_context_shadow.py \
  --repo <repository-root> \
  --mission <local-original-prompt> \
  --manifest <payload-free-manifest.json>
```

It emits JSON metadata to stdout and never emits or writes prompt/candidate
content. The prompt and manifest remain caller-controlled local inputs; this
mission commits neither the dogfood prompt nor any historical prompt.

## Evidence model

The strict manifest is `FIO_MISSION_CONTEXT_SHADOW_MANIFEST_V1`. It binds an exact
mission ID, UTF-8 byte count, SHA-256, evidence-quality enum, explicit sensitivity
assessment and non-overlapping byte spans. It cannot contain raw prompt fields,
free-form semantic judgments or model conclusions.

| Byte class | Admission proof | Candidate behavior |
| --- | --- | --- |
| `INLINE_CRITICAL` | Caller supplies exact byte offsets. | Original bytes always remain inline. |
| `DELTA` | Caller supplies exact byte offsets. | Original bytes always remain inline. |
| `REFERENCE_CANONICAL` | Relative normalized path is tracked; full artifact SHA-256 matches; range exists; prompt span equals artifact range byte-for-byte. | Deterministic path/hash/range marker is considered only when shorter; otherwise original bytes remain. |
| `DROP_DUPLICATE` | An earlier equal-length source range remains inline and target bytes equal it exactly. | Only the proven later target is omitted in the shadow candidate. |
| `UNKNOWN` | Every gap or failed proof. | Original bytes remain inline. |

Canonical proof is content identity, not a semantic-equivalence judgment.
Mentioning a repository path in prose is not proof that surrounding instructions
duplicate that artifact. Duplicate proof cannot point forward, form a hidden-copy
chain, use partial equality or rely on similar meaning. Missing, untracked,
out-of-repository, changed, hash-mismatched or range-mismatched artifacts become
UNKNOWN. `UNKNOWN` and ambiguous material remain byte-exact inline.

Only explicit `NON_SENSITIVE` assessment can permit reference/duplicate
measurement, and deterministic sensitivity detection can veto it. Detector
no-match is not itself a non-sensitive assessment. The tool persists no raw
mission bytes.

## Accounting contract

The five raw-byte categories form an exact partition:

```text
RAW_MISSION_BYTES = INLINE_CRITICAL_BYTES
                  + DELTA_BYTES
                  + REFERENCE_CANONICAL_BYTES
                  + DROP_DUPLICATE_CANDIDATE_BYTES
                  + UNKNOWN_CONSERVATIVE_BYTES
```

`MINIMUM_SUFFICIENT_CANDIDATE_BYTES` is the exact size of the structurally
constructed shadow candidate under the caller's proven spans. The name does not
claim behavioral sufficiency: `BEHAVIORAL_EQUIVALENCE=UNKNOWN` and
`ACTIVE_DELIVERY_AUTHORIZED=false`. Canonical marker overhead is charged; a
non-economic marker leaves the original span visible. Therefore:

```text
HYPOTHETICAL_VISIBLE_BYTES_REDUCTION =
  RAW_MISSION_BYTES - MINIMUM_SUFFICIENT_CANDIDATE_BYTES
```

The result also binds delivered/candidate SHA-256 values. It includes no token or
Plus-credit estimate. `DELIVERED_MISSION_MUTATED=false`,
`AUTOMATIC_SUPPRESSION=false`, and `SEMANTIC_INFERENCE_USED=false` are contract
fields rather than empirical model-quality claims.

When at least two real byte-bound samples exist, the aggregate reports the median
hypothetical percentage, gross bytes proven canonical-or-duplicate, and total
UNKNOWN bytes. Synthetic test fixtures never enter that denominator. Exact and
estimated token totals are not produced.

## Dogfood: current S1 mission

The visible current user mission was transcribed as received into a local-only
UTF-8 analysis file with one final LF. The byte scope and normalization are
therefore explicit; this is not a claim about hidden transport framing. The file
was assessed non-sensitive and remained outside Git.

The prompt itself explicitly labels one `CRITICAL` section. Its exact byte range
was caller-designated `INLINE_CRITICAL`. No other span was promoted: the mission
does not include an exact copy of a tracked artifact, its repository paths are
already references rather than repeated artifact contents, and no meaningful
earlier/later block duplicate was proven. Remaining bytes stayed UNKNOWN rather
than receiving an LLM-derived `DELTA` or equivalence label.

```text
MISSION_ID=FIOFILTER-M15-S1-MISSION-CONTEXT-REAL-SHADOW
MISSION_SHA256=a947d0992a2cd2c2f167c9521c00c315fb4e89a1a7fb14776a842dcbf7693a1b
RAW_BYTES=2808
INLINE_CRITICAL_BYTES=182
DELTA_BYTES=0
REFERENCE_CANONICAL_BYTES=0
DROP_DUPLICATE_BYTES=0
UNKNOWN_BYTES=2626
CANDIDATE_BYTES=2808
HYPOTHETICAL_REDUCTION_BYTES=0
HYPOTHETICAL_REDUCTION_PERCENT=0.0
EVIDENCE_QUALITY=CURRENT_MISSION_VISIBLE_TEXT_UTF8_LF
DELIVERED_MISSION_MUTATED=NO
```

This one result is `LOW_REEXPOSURE_OBSERVED_IN_CURRENT_SAMPLE`, not evidence that
instruction reexposure is generally low.

## Historical-sample audit and aggregate

Repository inspection found no preserved original recent FioFilter mission-prompt
bytes. M15-C1 records only a 1,988-byte size and SHA-256; it explicitly says no
comparable prompt was available. A hash and narrative report cannot reconstruct
the original bytes. No conversational memory, report prose or inferred baseline
was substituted.

```text
SAMPLES_ANALYZED=1
HISTORICAL_PROMPTS_ANALYZED=0
AGGREGATE_STATUS=NOT_COMPUTED_INSUFFICIENT_TRUSTWORTHY_SAMPLES
MEDIAN_HYPOTHETICAL_REDUCTION_PERCENT=NOT_COMPUTED
TOTAL_PROVEN_REEXPOSURE_BYTES=NOT_COMPUTED
TOTAL_UNKNOWN_BYTES=NOT_COMPUTED
```

## Validation and limits

Tests cover exact accounting conservation, raw/candidate hashes, critical-inline
preservation, UNKNOWN defaults, sensitivity/assessment vetoes, missing/untracked/
changed canonical artifacts, exact duplicates, hidden-source rejection,
determinism, strict manifests, payload-free records, unchanged delivery, and
synthetic-exclusion from aggregates.

M15-S1 establishes measurement integrity in the current test corpus. It does not
prove semantic minimality, behavioral equivalence, model salience, actual token
savings, general prevalence, or permission to hide prompt text. One real sample
cannot prioritize an active optimization. READREF remains off and Mission Context
remains shadow only.

**Verdict:** `M15_S1_PASS_INSUFFICIENT_REAL_SAMPLES`.
