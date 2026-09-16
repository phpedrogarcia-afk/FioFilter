# M03 corpus report — R1 oracle-integrity audit

## Status

M03 created a useful extraction/replay harness, but its original report did not
establish an independent oracle. The extractor assigned evidence, sensitivity,
eligibility, required facts and frontier buckets from the same strata heuristics
used to select records. Replay then injected sensitivity and required facts from
those labels into FioFilter. Consequently, the reported zero-danger results were
circular and the claimed frontier ranking was not decision-grade evidence.

M03-R1 hardens the method. Schema v4 distinguishes source data, detector
screening, extractor suggestions, independently reviewed oracle labels and
derived metrics. Legacy v3 input is rejected unless the caller explicitly uses
`M03_V3_AS_HEURISTIC`, which demotes the old labels rather than blessing them.

This review does **not** add a transform, authorize M04, reproduce the local
historical corpus, or change T01.

## Guarantee classification

| Claim | R1 classification | Evidence |
|---|---|---|
| Schema separates source, screening, heuristic, oracle and metrics | PROVEN IN CURRENT TEST CORPUS | v4 validation and serialization tests |
| Extractor output is independently reviewed | FALSE for original M03; prevented in v4 | extractor emits no `oracle_labels` |
| Detector no-match proves non-sensitive | FALSE | v4 records `DETECTOR_NO_MATCH`, never `NOT_SENSITIVE` |
| Replay is independent of oracle inputs | PROVEN IN CURRENT TEST CORPUS | subject receives UNKNOWN sensitivity and no oracle facts |
| Original 50-record safety result proves the boundary | CLAIMED_ONLY | source corpus and review artifacts are not in Git and original labels were heuristic |
| Original T01 result was 0.0% on that local sample | HISTORICAL_LOCAL_OBSERVATION | report values preserved; corpus unavailable here for replay |
| `DUPLICATED_HEADERS` is the largest safe frontier | CLAIMED_ONLY / HEURISTIC CANDIDATE | bucket was assigned by extractor, not independent review |
| No real sensitive data is committed | VERIFIED BY REPOSITORY REVIEW, NOT UNIVERSAL HISTORY | committed fixture is explicit inert synthetic detector text |

## Historical source and count semantics

The original M03 report named a local Codex rollout outside this repository and
reported:

- 4,362 call events;
- 50 sampled outputs;
- 442,488 sampled raw bytes;
- 21,863,707 total output bytes;
- 83 detector-positive candidates excluded.

The source JSONL is not committed and is unavailable in Codex Web, so these
figures were not independently recounted in M03-R1. They remain historical local
observations, not Git-reconstructable results.

M03-R3 identifies a further provenance conflict that this R1 report could not
resolve. Historical M03 material described an approximately 203,780,102-byte
August rollout (`M03_SOURCE_A`), while R2 recorded a 16,076,013-byte March file
with SHA-256 `d8ba8cb30d3cb3d958564b1509fa861460d3bfa9900c735a4d4a84f479a4bbcd`
(`M03_SOURCE_B`). Both carry the same session identifier, but that does not prove
content identity. Their relationship remains `UNKNOWN`; see
`M03-R3-CLEAN-SEARCH-CORPUS.md`.

The extractor's `total_calls_seen` counter has a precise, narrower meaning: the
number of parseable JSONL payloads whose type is `custom_tool_call` and whose
`call_id` is truthy. It increments before a matching output is found; it does not
filter the tool name to `exec`, prove completion, or count OS processes. The
separate `total_outputs_seen` counter records parseable `custom_tool_call_output`
events with a truthy `call_id`, including outputs later skipped for empty content
or detector matches. Therefore **4,362 must not be described as completed
physical `exec` calls**.

A separate historical value of 4,567 was cited outside the implemented M03
counter. Its source definition and event-selection rules are not present here.
The relationship is:

`M03_4362_RELATION_TO_HISTORICAL_4567 = UNKNOWN`

No reconciliation should be inferred from the numeric difference alone.

## Extraction and sampling limits

The extractor is a deterministic laboratory adapter, not a representative
sampler or a labeler:

1. It pairs calls and outputs by `call_id` only when both parse successfully.
2. It reconstructs text from supported output shapes and skips empty output.
3. It excludes configured detector matches when screening is enabled.
4. It assigns a command/output heuristic stratum.
5. It periodically samples within each available stratum, then trims in timeline
   order to the requested size.
6. It emits a heuristic suggestion for later review.

This procedure can omit malformed records, unmatched calls, unsupported output
shapes, detector false negatives/positives and strata not represented by the
fixed target table. Periodic selection is deterministic but is not random,
distribution-preserving or proof of workload representativeness.

R1 fixes two concrete stratum errors:

- `rg --files` is evaluated before generic `rg`, so it is a directory listing;
- `0 failed` is not failure evidence, while an explicit nonzero exit wins over
  benign-looking test text.

## Sensitivity boundary

`contains_sensitive_material` is a finite-pattern backstop. A match justifies
excluding or treating a record cautiously. A no-match means only that no
configured pattern matched these bytes; it does not establish absence of secrets,
PII, private source or other sensitive material. Counts such as the historical
83 are **detector-match counts**, not a count of all sensitive calls.

Schema v4 records `DETECTOR_MATCH`, `DETECTOR_NO_MATCH`, `NOT_RUN` or `UNKNOWN`
with method provenance. Only an independently reviewed oracle may carry a
sensitivity assessment, and even that assessment is scoped to its protocol.

## Oracle protocol

An oracle label requires all of:

- provenance: `INDEPENDENT_REVIEW`, `HUMAN_REVIEW` or `GOLD`;
- non-empty reviewer identifier;
- non-empty review protocol identifier;
- a valid evidence class and eligibility;
- no protected/sensitive `SAFE_TO_REDUCE` contradiction;
- every required fact present in source bytes with required multiplicity;
- source byte length matching the loaded bytes.

`GOLD` in this repository is limited to transparent synthetic unit fixtures. It
does not upgrade the unavailable historical corpus. Real historical entries must
be reviewed locally without letting extractor suggestions serve as their own
oracle.

## Replay and metric scope

Replay builds the subject `ToolResult` from source data only. It deliberately
passes `Sensitivity.UNKNOWN` and an empty required-facts list. Oracle facts are
checked after processing, including repeated occurrence requirements.

Safety comparisons, missed-opportunity bytes and confusion matrices are grouped
under explicit keys such as `ORACLE:INDEPENDENT_REVIEW` and
`HEURISTIC:M03_EXTRACTOR_V1`. A heuristic scope is diagnostic only and must not
be promoted into a safety claim.

Raw and visible byte counts are exact for loaded entries. Token values use
`utf8_bytes_div_4_ESTIMATE`; they are not actual model tokens, billing units or
whole-mission savings. The report runner now emits that provenance explicitly.

## Historical results retained with corrected status

The original local run reported 0 transformed bytes on 50 sampled outputs and
placed 97,503 of 162,487 heuristic missed-opportunity bytes (60.01%) in
`DUPLICATED_HEADERS`. M03-R1 does not silently discard those observations, but
reclassifies them:

- `ORIGINAL_M03_SAMPLE_RESULTS = HISTORICAL_NOT_REPRODUCED`
- `ORIGINAL_M03_LABEL_SCOPE = HEURISTIC`
- `ORIGINAL_M03_SAFETY_PROOF = INVALID`
- `ORIGINAL_M03_FRONTIER_RANKING = HYPOTHESIS_ONLY`

The unavailable corpus should be migrated as heuristic input and independently
reviewed before any of these numbers are reused for a decision.

## `DUPLICATED_HEADERS` contract gaps

The candidate remains plausible but is not yet proven safe. Equality of a set of
`(file, line_number, match_text)` triples is insufficient: sets discard ordering,
multiplicity and separators. A future review must first define and test at least:

- exact supported producer grammars (`rg`, `grep`, heading/no-heading, context);
- path association, original order and duplicate-match multiplicity;
- line and column numbers, match text, context separators and multiline records;
- relative, absolute, Windows drive and UNC paths, colons and case behavior;
- warnings, errors, nonzero exits, stderr/combined streams and truncated output;
- ANSI/color, binary notices, JSON output and unknown formats;
- marker collision, no expansion, deterministic encoding and exact decoding;
- protected evidence mixed anywhere in the output;
- corrective retrieval and whole-mission effects.

Unknown or ambiguous formats must remain RAW. Until local review supplies a real
oracle and this contract is approved:

`DUPLICATED_HEADERS_STATUS = HEURISTIC_CANDIDATE_PENDING_LOCAL_VALIDATION`

## Required local validation before M04 selection

1. Preserve the original external corpus; do not copy it into Git.
2. Load v3 only with `M03_V3_AS_HEURISTIC`.
3. Review records against a written protocol, recording reviewer and provenance.
4. Re-screen sensitivity independently; treat detector no-match as unknown.
5. Re-run evaluation and inspect each label scope separately.
6. Recompute frontier rankings only from accepted oracle scopes.
7. Publish aggregate evidence and limitations without raw/private content.

No M04 transform is selected or authorized by this report.
