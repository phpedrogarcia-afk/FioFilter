# M03-R3 provenance and clean-search corpus specification

## Mission boundary

M03-R3 prepares a local evidence run. It does not implement a transform, select
M04, or establish that `DUPLICATED_HEADERS` is safe. The code introduced here is
an offline extractor and byte-exact characterizer that never calls the FioFilter
transform engine and never assigns reviewed oracle labels.

## Historical source-provenance conflict

The repository preserves two materially different descriptions carrying session
identifier `01a02f96-42a2-7a80-b8bc-6d066d0e322f`:

### `M03_SOURCE_A`

| Field | Repository evidence |
|---|---|
| Session ID | `01a02f96-42a2-7a80-b8bc-6d066d0e322f` |
| Reported local path | `C:\Users\phped\.codex\sessions\2026\08\23\rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl` |
| Filename | `rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl` |
| Reported approximate size | `203,780,102` bytes |
| SHA-256 | `UNKNOWN` |
| First/last timestamp | `UNKNOWN` |
| Record/payload counts | `UNKNOWN` |
| Evidence status | Historical M03 description; bytes unavailable to Codex Web |

### `M03_SOURCE_B`

| Field | Repository evidence |
|---|---|
| Session ID | `01a02f96-42a2-7a80-b8bc-6d066d0e322f` |
| Reported local path | `C:\Users\phped\.codex\sessions\2026\03\08\01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl` |
| Filename | `01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl` |
| Measured size | `16,076,013` bytes |
| SHA-256 | `d8ba8cb30d3cb3d958564b1509fa861460d3bfa9900c735a4d4a84f479a4bbcd` |
| First/last timestamp | Not recorded in R2 |
| Record/payload counts | R2 reported `4,362` call events under the previously qualified counter semantics |
| Evidence status | Local R2 forensic artifact; bytes unavailable to Codex Web |

The same session identifier is metadata, not content identity. Different paths,
dates, filenames and sizes prevent an equivalence inference. Source A lacks a
hash and neither artifact is available here for byte comparison.

```text
SESSION_PROVENANCE_CONFLICT=YES
M03_SOURCE_A=HISTORICAL_AUGUST_ROLLOUT_203780102_BYTES_SHA256_UNKNOWN
M03_SOURCE_B=R2_MARCH_ARTIFACT_16076013_BYTES_SHA256_D8BA8CB3...
RELATION=UNKNOWN
SOURCE_ARTIFACT_IDENTITY_PENDING_RECONCILIATION=YES
```

No claim is made that either source supersedes, contains, derives from, or equals
the other. Future local work may change `RELATION` only with hashes and a recorded
comparison supporting one of `SAME_BYTES`, `DERIVED_FROM`, `SUBSET`, `SUPERSET`,
`DIFFERENT_ARTIFACT`, or `UNKNOWN`.

## Scope of the R2 search observation

R2's raw-byte forensic observation may remain useful. Its current defensible
scope is the exact local artifact described as `M03_SOURCE_B`, not a universal or
canonical session identity:

```text
LOCAL_ARTIFACT_SEARCH_REDUNDANCY_OBSERVED=TRUE
LOCAL_ARTIFACT_PURE_RG_CANDIDATES=193
SOURCE_ARTIFACT_IDENTITY_PENDING_RECONCILIATION=YES
CANONICAL_SESSION_PROOF=NO
```

The 193 count is an R2 local observation pending a fresh run of the R3 extractor.
It is not a safety oracle, a transform authorization, or proof that Source A has
the same calls.

## Source-artifact fingerprint contract

Every historical JSONL admitted as evidence must produce a local manifest with:

- `artifact_id`, derived from the content SHA-256 rather than session ID;
- `session_id_if_present` and every observed session identifier;
- `absolute_path_local_only` and filename;
- exact byte size and SHA-256;
- first and last record timestamps when present;
- parsed record count and malformed-record count;
- measured payload-type counts;
- extractor version and explicit observation date;
- relationship and optional prior artifact ID.

Absolute paths remain only in the local manifest. Git documentation uses the
sanitized source labels above. A matching session ID never changes the default
relationship from `UNKNOWN`.

## `M03_SEARCH_CORPUS_V1`

The dedicated corpus characterizes outputs from one structurally established
ripgrep process. Its purpose is grammar discovery and counterexample collection,
not maximizing compressibility.

### Admission boundary

A clean candidate requires all of the following:

1. A paired `custom_tool_call` and `custom_tool_call_output` with one call ID.
2. Tool name exactly `exec` or `exec_command`.
3. A supported mapping/JSON/strict `tools.exec_command({...})` input envelope.
4. One shell-free command whose first executable is `rg`, `rg.exe`, `ripgrep`,
   or `ripgrep.exe`.
5. No unquoted pipeline, redirection, command separator, command substitution,
   newline or unterminated quoting.
6. A structured result envelope with integer exit status and text output.
7. Exit status exactly 0.
8. No truncation flag, truncation metadata, or explicit upstream marker.
9. No shell/script failure wrapper.
10. Non-empty output bytes and no configured sensitivity-detector match.
11. One supported output grammar with exact reconstruction.

Failure of any prerequisite excludes the record and increments a stable reason.
Ambiguous records are never silently promoted into the clean set.

### Ripgrep exit semantics

For ripgrep itself:

```text
exit 0  = at least one match
exit 1  = no match
exit >=2 = execution error
```

The extractor records exit 1 as `RG_NO_MATCH_EXIT_1` and exit values other than
0/1 as `RG_EXECUTION_ERROR`. Both remain excluded, and the broader FioFilter I6
policy continues to preserve any nonzero result as RAW. Describing ripgrep exit 1
itself as an execution error is incorrect.

## Initial producer/grammar taxonomy

| Category | R3 status | Boundary |
|---|---|---|
| `RG_STANDARD_PATH_LINE_TEXT` | Characterization supported | `path:line:payload` |
| `RG_PATH_LINE_COLUMN_TEXT` | Characterization supported | `path:line:column:payload`, only with `--column` |
| `RG_HEADING` | Excluded | Header association not yet contracted |
| `RG_CONTEXT` | Excluded | Match/context delimiters and `--` grouping deferred |
| `RG_JSON` | Excluded | Separate machine-data grammar; no plain-text assumptions |
| `RG_COLORIZED` | Excluded | ANSI bytes are not parsed in R3 |
| `RG_BINARY_NOTICE` | Excluded | Separate notice grammar not implemented |
| `RG_EMPTY` | Excluded | Cannot be a clean exit-0 match output |
| `RG_UNKNOWN` | Excluded | Fail closed |

This is intentionally not “rg support.” It is support for two explicit output
grammars under an independently established producer command.

## Parser/characterizer contract

The parser records, for every line:

- exact path bytes and spelling/case;
- line number and optional column number;
- `MATCH` kind;
- exact payload bytes;
- ordering index;
- literal separator;
- exact LF, CRLF, or absent final line ending;
- header association, currently `null` because heading is unsupported.

Ordering and duplicate occurrences are retained. Windows drive paths and UNC
paths are recognized without naïvely splitting on every colon. Non-drive paths
containing an ambiguous numeric-colon sequence fail closed. A colon in ordinary
match payload remains payload.

The admission gate is:

```text
encode(parse(raw)) == raw
```

byte for byte. Set equality, normalized text, reordered records and semantic
equivalence do not satisfy this contract. The encoder exists only as a test
oracle; it is not a compressed representation.

## Extraction products and memory boundary

`scripts/extract_rg_corpus.py` produces three caller-named, local-only files:

1. all clean candidates and their exact characterization;
2. bounded negative controls selected as the first N occurrences per reason;
3. a manifest containing fingerprint, counts and independent-review selection.

The session is streamed twice. Pending call metadata, negative controls and the
candidate review index have explicit bounds. Raw candidate bytes are written
incrementally rather than accumulated. Outputs use same-volume, no-clobber
publication and the manifest is published last; an interrupted run without a
manifest is not evidence of completion. Source bytes are never modified.

The utility refuses to place any of these products inside the repository. A
detector match is counted but its bytes are never written. Detector no-match is
recorded only as screening, not a non-sensitive assessment. Neither candidates
nor controls receive `GOLD`, `HUMAN_REVIEW`, or `INDEPENDENT_REVIEW` labels.

## Negative controls

The manifest counts every exclusion and retains a bounded deterministic local
sample where non-sensitive bytes are available. Expected categories include:

- `COMPOSITE_COMMAND`;
- `RG_NO_MATCH_EXIT_1`;
- `RG_EXECUTION_ERROR`;
- `TRUNCATED_RESULT` and `UPSTREAM_TRUNCATION_MARKER`;
- `SHELL_FAILURE_WRAPPER`;
- `UNKNOWN_PRODUCER` and unstructured envelopes;
- unsupported context, heading, JSON, color, binary, null and unknown formats;
- malformed/mixed output;
- detector matches, counted without persisted bytes.

A future transform recognizer must reject every represented negative category.

## Deterministic review protocol for the next local mission

### Layer A — automated characterization

- Run the exact parser and byte-roundtrip oracle on every clean candidate.
- Verify zero candidate has an exclusion precondition.
- Report counts by artifact ID, grammar, size and exclusion reason.
- Preserve all raw products outside Git.

### Layer B — independent review

- Use the manifest selection, ordered by grammar and deterministic output-size
  quantiles with occurrence/entry ID tie breakers.
- Review at most 12 candidates per observed grammar by default.
- Review every observed grammar and every negative-control category.
- Expand review only for a category showing ambiguity or heterogeneous structure.
- Add oracle labels through a separate sidecar with reviewer and protocol; never
  rewrite extractor heuristics as oracle labels.

This bounds human effort while still covering small, median and large outputs.

## M04 readiness gates

Only a specifically named grammar may advance, and only when all are true:

```text
SOURCE_ARTIFACT_PROVENANCE_RESOLVED=YES
CLEAN_EXTRACTION_BOUNDARY_PROVEN=YES
GRAMMAR_RECOGNIZER_FAILS_CLOSED=YES
BYTE_EXACT_PARSE_ROUNDTRIP=PASS
NEGATIVE_CONTROLS_REJECTED=PASS
INDEPENDENT_REVIEW_SAMPLE=PASS
SENSITIVITY_BOUNDARY=PASS
RAW_HISTORICAL_DATA_COMMITTED=NO
NONTRIVIAL_REAL_OPPORTUNITY=YES
```

No universal `DUPLICATED_HEADERS` authorization is possible from these gates.
At most, a narrow grammar such as `RG_STANDARD_PATH_LINE_TEXT` could later be
proposed. Current mission state is:

```text
SOURCE_ARTIFACT_PROVENANCE_RESOLVED=NO
M04_AUTHORIZED=NO
```

M03-R3 leaves provenance unresolved and does not authorize M04.

## Local CLI shape

Example only; all output paths must remain outside Git:

```powershell
python scripts/extract_rg_corpus.py `
  --session '<LOCAL-HISTORICAL-JSONL>' `
  --output '<LOCAL-CORPUS>\m03_search_corpus_v1.jsonl' `
  --negative-output '<LOCAL-CORPUS>\m03_search_corpus_v1.negative.jsonl' `
  --manifest '<LOCAL-CORPUS>\m03_search_corpus_v1.manifest.json' `
  --observation-date '<YYYY-MM-DD>' `
  --relationship-to-prior-artifact UNKNOWN
```

The next Antigravity mission must first compare the resulting fingerprint with
the documented Sources A and B. It must not reuse the flawed stratified 50-entry
sample to validate a search grammar.
