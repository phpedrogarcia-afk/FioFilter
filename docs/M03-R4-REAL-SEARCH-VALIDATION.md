# M03-R4 Real Search Validation and M04 Gate Report

## Mission Boundary

This document records the decisive local empirical validation of the FioFilter search
frontier conducted under `MISSION_ID=FIOFILTER-M03-R4-REAL-CLEAN-CORPUS-AND-M04-GATE`.

In accordance with project doctrine:
- This is NOT M04 implementation. No compression transform has been built.
- No raw session bytes or user credentials have been committed to Git.
- Whole-mission savings are NOT claimed (`WHOLE_MISSION_SAVINGS = UNKNOWN`).
- Token metrics are strictly reported under `utf8_bytes_div_4_ESTIMATE`.

---

## 1. Source A and Source B Physical Investigation & Provenance

### Local Filesystem Investigation

A bounded search was executed across `C:\Users\phped\.codex` for session ID
`01a02f96-42a2-7a80-b8bc-6d066d0e322f`.

| Entity | Path on Local Disk | Status | Size (Bytes) | SHA-256 |
|---|---|---|---|---|
| **Source A** | `C:\Users\phped\.codex\sessions\2026\08\23\rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl` | **FOUND** | `206,427,325` | `bc4561d4588a73a6889ca38d8c180ae467e51eea5f023aaba7a222425cf350a0` |
| **Source B** | `C:\Users\phped\.codex\sessions\2026\03\08\01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl` | **NOT FOUND** | N/A | N/A |

### Provenance Resolution

- **Source A**: Fully verified and fingerprinted under artifact identifier
  `M03-ARTIFACT-SHA256-BC4561D4588A73A6`.
  - JSONL record count: 35,040
  - Payload breakdown: `custom_tool_call`: 4,430, `custom_tool_call_output`: 4,430, `session_meta`: 1, malformed records: 0.
  - Timestamps: `2026-08-23T17:06:11.963Z` to `2026-09-16T11:10:06.981Z`.
- **Source B Origin**: The path for Source B in M03-R2 was inferred from the UUIDv7
  timestamp prefix (`01a02f96` corresponds to 2026-03-08), but the actual session file
  was stored under rollout date directory `2026\08\23`. Directory `2026\03` does not exist on disk.
- **Source Relationship**: `DIFFERENT_ARTIFACT` (Source B is absent on local filesystem).
- **Validation Artifact Provenance**: **RESOLVED** on `M03-ARTIFACT-SHA256-BC4561D4588A73A6`.

---

## 2. Real Clean Corpus Extraction

Extraction was executed using `scripts/extract_rg_corpus.py` on Source A with outputs written
outside Git under `C:\Users\phped\.fiofilter\corpus\`:
- Clean Candidates: `m03_rg_clean_candidates_v1.jsonl`
- Negative Controls: `m03_rg_negative_controls_v1.jsonl`
- Manifest: `m03_rg_manifest_v1.json`

### Extraction Summary

- Total tool call / output pairs inspected: 4,430
- Clean candidates admitted: 23
- Oracle labels assigned by extractor: 0 (labels assigned solely via independent review)

### Grammar Distribution

| Grammar | Admitted Candidates | Percent of Admitted |
|---|---|---|
| `RG_STANDARD_PATH_LINE_TEXT` | 23 | 100.0% |
| `RG_PATH_LINE_COLUMN_TEXT` | 0 | 0.0% |

In real Codex sessions, standard line-numbered ripgrep (`rg -n`) is common, whereas
column output (`--column`) did not occur cleanly without composite shell wrappers.

### Exclusion Counts & Negative Controls

Every non-admitted call in the session was accounted for:

| Exclusion Category | Total Excluded | Bounded Negative Controls Written |
|---|---|---|
| `COMPOSITE_COMMAND` | 2,051 | 5 |
| `UNSTRUCTURED_INVOCATION` | 1,465 | 5 |
| `UNKNOWN_PRODUCER` | 580 | 5 |
| `UNSTRUCTURED_RESULT` | 159 | 0 |
| `SENSITIVE_DETECTOR_MATCH` | 85 | 0 (DO_NOT_PERSIST) |
| `UNRECOGNIZED_LINE` | 40 | 5 |
| `UNSUPPORTED_RG_CONTEXT` | 18 | 5 |
| `RG_EMPTY` | 5 | 5 |
| `UNSUPPORTED_RG_JSON` | 3 | 3 |
| `TRUNCATED_RESULT` | 1 | 1 |
| **Total** | **4,407** | **34** |

**Negative Control False Admissions: 0.**
Every negative control was independently verified to be rejected by the grammar parser.

---

## 3. Byte-Exact Roundtrip Characterization

For every admitted clean candidate:
$$\text{encode}(\text{parse}(\text{raw})) \equiv \text{raw}$$

- Total admitted candidates tested: 23
- Exact byte roundtrip passes: **23 / 23 (100.0%)**
- Byte roundtrip failures: **0**

---

## 4. Headroom Ambiguity Donor Challenges

18 adversarial challenge cases based on Headroom donor failure modes were tested:
- Windows drive paths (`C:\repo\app.py:10:match`)
- UNC paths (`\\server\share\repo\app.py:10:match`)
- Hyphenated file paths and names (`src/my-cool-app/test-runner.py:42:assert`)
- Dated directories (`logs/2026-05-03/run.log:15:started`)
- CVE-like filenames (`advisories/CVE-2021-44228.md:99:vuln`)
- Digits separated by dashes (`data/part-01-2024-v2.txt:7:row`)
- Column-like syntax without `--column` (`src/a.py:10:5:match` -> fails closed to RAW)
- Colon inside match payload (`src/config.py:12:url = https://example.com:8080`)
- Duplicate identical matches preserved with multiplicity
- Context-like separator lines (`--` -> fails closed to RAW)
- Extensionless filenames (`bin/run:25:exec`, `Makefile:4:all:`)
- Apparent `<sep><digits><sep>` inside paths (`build/123/output.py:40:match`)
- Unrecognized lines, binary notices, ANSI color codes, JSON lines (all fail closed to RAW)

**Results:**
- `HEADROOM_AMBIGUITY_CASES_TESTED = 18`
- `AMBIGUOUS_CASES_ADMITTED = 0`

---

## 5. Independent Review (`M03_R4_REAL_SEARCH_VALIDATION_V1`)

- **Reviewer**: `ANTIGRAVITY_M03_R4`
- **Protocol**: `M03_R4_REAL_SEARCH_VALIDATION_V1`
- **Selection**: 12 candidates sampled deterministically across size quantiles from min (110B) to max (9,399B).

| Review # | Entry ID | Raw Bytes | Matches | Files | Dup Paths | Disposition | Notes |
|---|---|---|---|---|---|---|---|
| 1 | `M03-RG-CLEAN-00019812-2FBDDAB0E0` | 110 | 2 | 2 | 0 | `RAW_REQUIRED` | Economic non-expansion guard (saved -2B) |
| 2 | `M03-RG-CLEAN-00003383-E4B0D014D3` | 316 | 3 | 2 | 1 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 36B (11.4%) |
| 3 | `M03-RG-CLEAN-00000698-3CAE62B327` | 356 | 4 | 4 | 0 | `RAW_REQUIRED` | Economic non-expansion guard (saved -4B) |
| 4 | `M03-RG-CLEAN-00003268-9D012621C5` | 762 | 7 | 2 | 5 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 163B (21.4%) |
| 5 | `M03-RG-CLEAN-00022701-D9E67B2F60` | 1,237 | 16 | 7 | 9 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 287B (23.2%) |
| 6 | `M03-RG-CLEAN-00008214-9843AA9C68` | 1,474 | 16 | 2 | 14 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 427B (29.0%) |
| 7 | `M03-RG-CLEAN-00004971-7D5AD87B24` | 1,643 | 20 | 3 | 17 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 512B (31.2%) |
| 8 | `M03-RG-CLEAN-00028190-43734D4693` | 2,083 | 18 | 6 | 12 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 335B (16.1%) |
| 9 | `M03-RG-CLEAN-00023066-9902633092` | 3,553 | 31 | 4 | 27 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 882B (24.8%) |
| 10 | `M03-RG-CLEAN-00013433-924860F228` | 5,527 | 60 | 2 | 58 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 1,847B (33.4%) |
| 11 | `M03-RG-CLEAN-00023956-F63F59843E` | 6,629 | 67 | 21 | 46 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 1,547B (23.3%) |
| 12 | `M03-RG-CLEAN-00000168-54DE285D44` | 9,399 | 131 | 8 | 123 | `SAFE_FOR_LOSSLESS_GROUPING` | Saved 3,334B (35.5%) |

### Review Verification Checklist

- Producer identity proven: **YES** (isolated `rg -n` invocations)
- Exit code exactly 0: **YES**
- Output untruncated: **YES**
- Stream single-purpose: **YES**
- Every material line belongs to recognized grammar: **YES**
- Paths, line numbers, and payloads exact: **YES**
- Ordering and multiplicity exact: **YES**
- Sensitivity assessment acceptable: **YES** (no credentials/tokens detected)
- Byte roundtrip pass: **YES** (12 / 12)
- All facts retained inline: **YES**
- Corrective retrieval plausibly required: **NO** (0 facts omitted)

---

## 6. Real Lossless Grouping Economics

Economics were evaluated on the candidate grouped representation:
```text
RAW:
path/to/file.py:10:match line A
path/to/file.py:25:match line B

CANDIDATE GROUPED:
path/to/file.py
10:match line A
25:match line B
```
No files, line numbers, or payloads are omitted or summarized.

### Aggregate Metrics across all 23 Real Candidates

- Total raw bytes: **62,373 bytes**
- Total candidate grouped bytes: **45,021 bytes**
- Net bytes saved: **17,352 bytes** (**27.82% reduction**)
- Estimated raw tokens (`utf8_bytes_div_4_ESTIMATE`): **15,594 tokens**
- Estimated grouped tokens (`utf8_bytes_div_4_ESTIMATE`): **11,256 tokens**
- Estimated tokens saved: **4,338 tokens**
- Size distribution: Min: 110 B, Median: 1,537 B, P90: 6,629 B, Max: 9,399 B
- Total matches parsed: 658
- Total unique files referenced: 108
- Duplicate path occurrences: 533

### Economic Non-Expansion Disposition

- Candidates with positive savings: **20 / 23** (up to 35.5% savings per call)
- Candidates with zero or negative savings: **3 / 23** (saved -1B, -2B, -4B due to 0 path duplicates across matches)
- For the 3 candidates with no savings, economic disposition is **`RAW`** (`VALID_BUT_NO_SAVINGS`).
- Non-expansion invariant is strictly preserved.

---

## 7. Grammar-by-Grammar M04 Readiness Gates

| Gate Requirement | `RG_STANDARD_PATH_LINE_TEXT` | `RG_PATH_LINE_COLUMN_TEXT` |
|---|---|---|
| `REAL_CASES_FOUND` | **23** | **0** |
| `REAL_RAW_BYTES` | **62,373** | **0** |
| `ROUNDTRIP_100_PERCENT` | **PASS (23/23)** | N/A (Synthetic pass only) |
| `NEGATIVE_CONTROLS_ZERO_FALSE_ADMISSIONS` | **PASS (0 false admissions)** | **PASS** |
| `INDEPENDENT_REVIEW_PASS` | **PASS (12/12 reviewed)** | N/A |
| `AMBIGUOUS_CASES_FAIL_RAW` | **PASS (0 admitted)** | **PASS** |
| `NONTRIVIAL_REDUCTION` | **PASS (27.82% net, 17,352 B)** | UNKNOWN |
| `SENSITIVE_DATA_COMMITTED_NO` | **PASS (0 sensitive bytes)** | **PASS** |
| `CORRECTIVE_RETRIEVAL_RISK_ASSESSED` | **PASS (0 facts omitted)** | **PASS** |
| **M04_READY** | **YES** | **NO** |
| **FINAL GATE DECISION** | **`VALIDATED`** | **`MORE_REAL_EVIDENCE_REQUIRED`** |

---

## 8. M04 Authorization Decision

In accordance with M03-R4 doctrine:
- Exact grammar ID authorized for M04 transform investigation:
  **`RG_STANDARD_PATH_LINE_TEXT`**
- Defer from M04:
  `RG_PATH_LINE_COLUMN_TEXT` (remains laboratory grammar pending real workload evidence).
- Universal authorization of `DUPLICATED_HEADERS`: **REJECTED**.
- Implementation of M04 transform in this mission: **NONE**.
