# M03-R2 Independent Local Validation Report

## Status and Provenance

- **Mission ID**: `MISSION_ID=FIOFILTER-M03-R2-INDEPENDENT-LOCAL-VALIDATION`
- **Reviewer ID**: `ANTIGRAVITY_M03_R2`
- **Review Provenance**: `INDEPENDENT_REVIEW`
- **Review Protocol**: `M03_R2_LOCAL_VALIDATION_V1`
- **Workspace**: `C:\Users\phped\Documents\FioFilter`
- **Target Branch**: `antigravity/m03-real-corpus-frontier` (PR #2)
- **Scientific Verdict**: `DUPLICATED_HEADERS_PARTIALLY_VALIDATED_MORE_EVIDENCE_REQUIRED`
- **Mission Verdict**: `M03_R2_PASS_MORE_VALIDATION_REQUIRED`

This document records the independent local review of historical Codex tool outputs
from the artifact now designated `M03_SOURCE_B`, carrying session identifier
`01a02f96-42a2-7a80-b8bc-6d066d0e322f`. R2 originally called it canonical. R3
supersedes that provenance wording because a materially different historical
artifact carries the same session identifier. The raw-byte review below remains
an observation of Source B while artifact identity is unresolved.

This mission strictly enforces:
- **Zero M04 transform implementation** (no new transforms).
- **Zero persistent leakage of private source bytes or user credentials** into Git.
- **Strict isolation between extractor heuristics and independently reviewed oracle labels**.

---

## Corpus Identity and Integrity

The evaluation was performed against the historical local sample and one locally
observed historical artifact:

| Corpus Artifact | Path | Size (Bytes) | SHA-256 |
|---|---|---|---|
| Sample v1 | `C:\Users\phped\.fiofilter\corpus\m03_fioos_sample_v1.jsonl` | 629,778 | `19200bd30a688cd3cf8607bae0c21cf4eece4d9ca8fd696ae81138469986b9e2` |
| Reviewed Sidecar | `C:\Users\phped\.fiofilter\corpus\m03_fioos_sample_v1.reviewed.jsonl` | 4,769 | `ef3267784f1a603cbe31c6a2b3445582f6e5cfa69b2ff92f4477c7f9999a4e93` |
| `M03_SOURCE_B` local artifact | `C:\Users\phped\.codex\sessions\2026\03\08\01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl` | 16,076,013 | `d8ba8cb30d3cb3d958564b1509fa861460d3bfa9900c735a4d4a84f479a4bbcd` |

The sample contains 50 entries totaling 442,488 raw bytes (110,622.0 estimated
tokens). The reviewed sidecar contains non-sensitive metadata and independently
audited oracle decisions for all search-stratum entries without publishing raw
source bytes.

Earlier M03 material described `M03_SOURCE_A`: an approximately 203,780,102-byte
rollout file under an August 2026 path and a longer `rollout-*` filename, with no
recorded SHA-256. Source A and Source B share a session ID but have different
documented paths, filenames and sizes. Their relationship is `UNKNOWN`; neither
is declared canonical, superseding, derived, subset, superset or byte-identical.
See `M03-R3-CLEAN-SEARCH-CORPUS.md`.

---

## Exhaustive Review of Search-Stratum Records

In M03, the extractor classified 8 entries into the search stratum, and naively
marked 6 of them as `SAFE_TO_REDUCE` in `DUPLICATED_HEADERS`, totaling 97,503 bytes
(60.01% of all heuristic missed reduction bytes).

Every search record in `m03_fioos_sample_v1.jsonl` was independently audited at
the raw-byte level:

| Entry ID | Raw Bytes | M03 Heuristic Label | Reviewed Evidence Class | Reviewed Eligibility | Primary Invariant / Rationale |
|---|---|---|---|---|---|
| `FIOOS-REAL-002` | 40,154 | `DUPLICATED_HEADERS` (SAFE) | `DIAGNOSTIC` | `RAW_REQUIRED` | Invariant I13: Truncated composite JSON chat thread dump. |
| `FIOOS-REAL-010` | 40,153 | `DUPLICATED_HEADERS` (SAFE) | `DISCOVERY` | `RAW_REQUIRED` | Invariant I13: Truncated search output with multiple upstream truncation warnings. |
| `FIOOS-REAL-015` | 4,203 | `UNKNOWN` (RAW) | `FAILURE` | `RAW_REQUIRED` | Invariant I6: Exit code 1; single-file search format without repeated path headers. |
| `FIOOS-REAL-025` | 1,267 | `DUPLICATED_HEADERS` (SAFE) | `FAILURE` | `RAW_REQUIRED` | Invariant I6: SSH connection failure diagnostic (`Script failed`), not search output. |
| `FIOOS-REAL-030` | 40,156 | `UNKNOWN` (RAW) | `FAILURE` | `RAW_REQUIRED` | Invariants I6 & I13: Exit code 1; truncated search output with `-C 3` context. |
| `FIOOS-REAL-038` | 4,842 | `DUPLICATED_HEADERS` (SAFE) | `DISCOVERY` | `UNKNOWN` | Invariant I8: Composite output (18 dir paths + 26 search lines); lacking uniform grammar. |
| `FIOOS-REAL-046` | 47 | `DUPLICATED_HEADERS` (SAFE) | `DISCOVERY` | `RAW_REQUIRED` | Invariant I9: Empty search match (0 hits); zero reducible bytes. |
| `FIOOS-REAL-050` | 11,040 | `DUPLICATED_HEADERS` (SAFE) | `CANONICAL_STATE` | `RAW_REQUIRED` | Invariant I7: 10.5 KB Python source file read followed by search matches; RAW mandatory. |

### Entry Breakdown & Forensic Analysis

1. **`FIOOS-REAL-002` (40,154 bytes)**
   - *Command*: Python script executing search across session logs.
   - *Forensic Finding*: Output is a truncated JSON stream of agent chat messages (`[{"type":"message", ...`). It ends abruptly due to upstream client truncation.
   - *Invariant Enforced*: **Invariant I13 (Truncation requires RAW)**. Truncated output must never be modified or folded because semantic boundaries are lost.

2. **`FIOOS-REAL-010` (40,153 bytes)**
   - *Command*: `rg` search across files.
   - *Forensic Finding*: Output contains multiple explicit warnings `[Output truncated at 40000 bytes...]`.
   - *Invariant Enforced*: **Invariant I13**. Truncated search output cannot be safely parsed or reconstructed.

3. **`FIOOS-REAL-015` (4,203 bytes)**
   - *Command*: `rg` restricted to a single file (`fiofilter/engine.py`).
   - *Forensic Finding*: Exit code is 1. The output has line numbers only (`fiofilter/engine.py:42:...`), with no repeated path headers.
   - *Invariant Enforced*: **Invariant I6 (Nonzero exit requires RAW)**. For a pure
     ripgrep process, exit code 1 means no matches, not an execution error. The
     historical record also contains output, so its wrapper/attribution cannot be
     treated as clean ripgrep evidence. It remains RAW, and the single-file format
     has no demonstrated duplicate-header opportunity.

4. **`FIOOS-REAL-025` (1,267 bytes)**
   - *Command*: Shell execution containing `rg` in a multi-command script.
   - *Forensic Finding*: The command failed immediately at SSH connection (`Script failed...`). The output consists entirely of failure diagnostics.
   - *Invariant Enforced*: **Invariant I6**. Failure evidence is protected and must remain RAW.

5. **`FIOOS-REAL-030` (40,156 bytes)**
   - *Command*: `rg -C 3` search.
   - *Forensic Finding*: Exit code is 1 and content is truncated at 40 KB.
   - *Invariant Enforced*: **Invariants I6 and I13**. Both nonzero exit and truncation require RAW.

6. **`FIOOS-REAL-038` (4,842 bytes)**
   - *Command*: Composite pipeline listing directories then grepping.
   - *Forensic Finding*: The output begins with 18 bare directory paths, followed by 26 `file:line:content` search matches.
   - *Invariant Enforced*: **Invariant I8 (Grammar ambiguity)**. Without a safe composite block splitter, applying a monolithic search transform to mixed stdout is dangerous. Eligibility is `UNKNOWN`.

7. **`FIOOS-REAL-046` (47 bytes)**
   - *Command*: `rg` search for a specific symbol.
   - *Forensic Finding*: Output contains 0 matches (empty stdout).
   - *Invariant Enforced*: **Invariant I9 (No-expansion)**. There are 0 bytes of duplicate path headers to reduce.

8. **`FIOOS-REAL-050` (11,040 bytes)**
   - *Command*: Composite script reading a file then searching (`cat fiofilter/transforms/t01_fold_progress.py; rg ...`).
   - *Forensic Finding*: Over 10.5 KB of the output is canonical Python source code from a file read.
   - *Invariant Enforced*: **Invariant I7 (Canonical state requires RAW)**. Canonical file reads must never be subjected to search header folding.

---

## Root Cause: Why M03 Overclaimed `DUPLICATED_HEADERS`

The original M03 extraction harness suffered from four methodological flaws:

1. **Substring Command Matching**: The stratum classifier checked `if "rg " in command:` inside JavaScript tool invocation wrappers (`tools.exec_command({cmd: '...'})`). This matched scripts that merely mentioned `rg` in strings, comments, or composite shell pipelines (`cat; rg`).
2. **Ignoring Upstream Truncation**: Records with `truncated: true` or upstream truncation markers were treated as normal output, ignoring Invariant I13. In the sample, two 40 KB truncated records (`002` and `010`) accounted for 80,307 of the 97,503 bytes (82.4%).
3. **Ignoring Exit Codes**: Nonzero records were evaluated for reduction, violating
   Invariant I6. Pure ripgrep exit 1 is specifically `NO_MATCH`; shell failure and
   ripgrep exit >=2 are distinct error cases even though all remain RAW here.
4. **Ignoring Mixed Command Streams**: Composite scripts producing both source files and search results (`050`) were grouped under search headers.

---

## Validated Opportunity on Primary Sample

When evaluating the primary 50-entry sample under the independently reviewed oracle:

```
Total entries reviewed: 8
Safe to reduce: 0 entries (0 bytes)
RAW required: 7 entries (137,020 bytes)
Unknown / ambiguous: 1 entry (4,842 bytes)
Confirmed safe bytes: 0 bytes (0.0% of claimed 97,503 bytes)
```

In the primary sample `m03_fioos_sample_v1.jsonl`, **zero bytes** of the claimed
`DUPLICATED_HEADERS` frontier are safe to reduce.

---

## Authentic Phenomenon in Real Coding Sessions

While the primary sample yielded 0 safe bytes due to extraction defects, R2's
local inspection of `M03_SOURCE_B` (16,076,013 bytes; 4,362 historically reported
call events under the qualified counter semantics) observed pure, untruncated
`rg` calls with repeated path prefixes:

- **193 apparent pure `rg` execution calls** were identified locally with exit code
  0, no observed truncation, and multi-file search output. R3 preserves this as a
  Source B observation pending reproduction by the dedicated extractor.
- For example, call `call_s5Ou468Hxw0DAwMfUoXmoYyn` produced 131 search matches
  across 8 files, where each line repeated the full relative path prefix:
  `packages/core/src/indexing/indexer.ts:14:...`
  `packages/core/src/indexing/indexer.ts:28:...` (repeated 45 times).
- In such pure searches, grouping matches under file headers offers substantial token
  savings without evidence loss.

Therefore, the candidate **cannot be dismissed as non-existent in Source B**, but
it was severely mis-sampled and overclaimed in M03. This does not prove the same
phenomenon exists in Source A or authorize a transform.

---

## Search Output Edge-Case Taxonomy & Counterexamples

Before any search transform can ever be authorized, the following format
fingerprints and edge cases must be recognized and tested:

1. **Windows Drive Paths**: Colons in paths (e.g. `C:\repo\file.py:10:match`) must
   not collide with colon field delimiters.
2. **Column Numbers**: ripgrep `--column` produces 3-part colons
   (`path:line:col:text`), distinct from 2-part (`path:line:text`).
3. **Context Separators**: `rg -C` produces `--` divider lines and `-` field
   delimiters for context (`path-line-context` vs `path:line:match`).
4. **ANSI Color Escapes**: When color is enabled (`--color=always`), raw ANSI
   sequences exist in path and match text.
5. **Binary Match Notices**: Lines like `Binary file dist/app.exe matches` lack line
   numbers and match content.
6. **Nonzero Exit Codes**: ripgrep exit code 1 (no match) and exit code >=2 (error)
   must remain strictly RAW under Invariant I6.
7. **Upstream Truncation**: Incomplete output must remain strictly RAW under
   Invariant I13.

All seven edge cases have been implemented as automated tests in
`tests/test_corpus_harness.py`.

---

## Lossless Preservation Contract for Future Search Transforms

Any future transform proposal targeting search headers must formally satisfy:

1. **Input Preconditions**:
   - Exit code MUST be exactly 0.
   - `truncated` flag MUST be false; content MUST NOT contain truncation markers.
   - Stream MUST be single-purpose stdout without mixed non-search commands.
   - Every line MUST conform to a verified, single producer grammar.
2. **Preservation Invariants**:
   - Every matched file path, line number, column number, and text payload must be
     preserved.
   - Original file ordering and match order within files must be maintained.
   - Duplicate match multiplicity must never be folded or altered.
3. **Reconstructability & Fallback**:
   - The transformed representation must be deterministically decodable back to
     exact original bytes, or verified against an exact reconstruction oracle.
   - Any unrecognized line or grammar deviation MUST fail open to 100% RAW.

---

## Summary of Replay Evaluation

Running `scripts/run_corpus_evaluation.py` on the primary corpus with the reviewed
sidecar produces the following partitioned metrics:

```
Corpus: C:\Users\phped\.fiofilter\corpus\m03_fioos_sample_v1.jsonl
Sidecar: C:\Users\phped\.fiofilter\corpus\m03_fioos_sample_v1.reviewed.jsonl
Migration: M03_V3_AS_HEURISTIC
Mode: BUILD | Profile: fioos

--- T01 PERFORMANCE ---
Eligible Entries: 0
Transformed Entries: 0
Local Byte Reduction: 0.0%

--- LABEL SCOPE: HEURISTIC:M03_V3_MIGRATED_HEURISTIC ---
Claim status: HEURISTIC_ONLY_NOT_SAFETY_PROOF
Entry Count: 50
Missed Opportunities:
  DUPLICATED_HEADERS: 6 entries, 97,503 bytes (60.01% of heuristic scope)
  REPETITIVE_PROGRESS: 3 entries, 53,169 bytes (32.72% of heuristic scope)
  KNOWN_SUCCESS_RECORDS: 6 entries, 9,803 bytes (6.03% of heuristic scope)
  DIRECTORY_OR_PATH_REDUNDANCY: 6 entries, 2,012 bytes (1.24% of heuristic scope)

--- LABEL SCOPE: ORACLE:INDEPENDENT_REVIEW ---
Claim status: INDEPENDENTLY_REVIEWED
Entry Count: 8
Dangerous Entries: 0
Safe Match: 7 (all RAW_REQUIRED preserved as RAW)
Label Uncertain: 1 (UNKNOWN preserved as RAW)
Safe Opportunities Missed: 0
Missed Opportunities:
  (None — 0 bytes safe to reduce)
```

---

## Scientific Verdict

- `PRIMARY_SAMPLE_CONFIRMED_SAFE_BYTES = 0` (0.0%)
- `PRIMARY_SAMPLE_DUPLICATED_HEADERS_VALIDATED = FALSE`
- `LOCAL_ARTIFACT_SEARCH_REDUNDANCY_OBSERVED = TRUE`
- `LOCAL_ARTIFACT_PURE_RG_CANDIDATES = 193`
- `SOURCE_ARTIFACT_IDENTITY_PENDING_RECONCILIATION = YES`
- `CANONICAL_SESSION_PROOF = NO`
- `CANDIDATE_STATUS = DUPLICATED_HEADERS_PARTIALLY_VALIDATED_MORE_EVIDENCE_REQUIRED`
- `MISSION_VERDICT = M03_R2_PASS_MORE_VALIDATION_REQUIRED`

`DUPLICATED_HEADERS` is a real phenomenon in coding-agent workloads, but it cannot
be authorized based on M03's sample. A dedicated, cleanly extracted search corpus
and a formal lossless preservation grammar are mandatory before any M04 transform
development may begin.
