# FioFilter M03 Real Corpus & Frontier Report

## 1. Executive Summary

Mission **FIOFILTER-M03-REAL-CORPUS-FRONTIER** established the first empirical evaluation of FioFilter against real historical coding-agent execution outputs from Codex.

### Core Findings
1. **Safety Boundary Holds**: Against 50 stratified real-world tool outputs, FioFilter achieved **`DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY = 0`** and **`UNSAFE_SENSITIVITY_LEAK = 0`**. Protected canonical state, security, failure, and authority outputs were preserved at 100% RAW fidelity.
2. **T01 Real-Workload Limit**: T01 (exact duplicate consecutive-line folding) achieved **0.0% reduction** on real coding-agent outputs. In real agent workloads, repetitive text does not take the form of identical consecutive lines; it appears as duplicated path headers in search results, varying progress percentages in build logs, and per-test line items in pass lists.
3. **Largest Safe Reduction Frontier**: **60.01% of all missed reduction opportunity** (97.5 KB across 6 sample entries) is driven by **`DUPLICATED_HEADERS`** (repeated file path headers and search match prefixes in `rg`/`grep` outputs).
4. **Selected M04 Frontier**: **`DUPLICATED_HEADERS`** is selected as the single recommended frontier for M04.

---

## 2. Historical Source Discovery

### Canonical FioOS Session
- **Location**: `C:\Users\phped\.codex\sessions\2026\08\23\rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl`
- **Session ID**: `01a02f96-42a2-7a80-b8bc-6d066d0e322f`
- **Size**: 203.8 MB (194.34 MiB)
- **Completed Tool Calls**: 4,362 physical `exec` calls
- **Total Output Bytes**: 21,863,707 bytes (~21.8 MB)

### P14 Corpus Status
- **Result**: `P14_EXACT_CORPUS_AVAILABLE = NO`
- An exhaustive filesystem scan of `C:\Users\phped\.codex` and `C:\Users\phped\Documents` confirmed that no standalone temporary file or artifact from the historical P14 CCA experiment was preserved.
- Consistent with mission discipline, no substitute was fabricated under the name "P14". Instead, a new, rigorously audited corpus sample was derived from the canonical session and designated **`M03_FIOOS_SAMPLE_V1`**.

---

## 3. Sampling Methodology & Privacy Boundary

### Strata & Deterministic Selection
The 4,362 calls in the canonical session were classified into 8 operational strata. A deterministic periodic sampling step selected 50 entries across the full timeline:

| Stratum | Calls in Session | Target Sample | Extracted | Provenance Category |
|---|---|---|---|---|
| `git` | 973 | 8 | 8 | Canonical repository status, log, diff, commit |
| `search` | 445 | 8 | 8 | Codebase search queries (`rg`) |
| `file_read` | 517 | 8 | 8 | Source, memory, and config inspection (`Get-Content`) |
| `dir_list` | 422 | 6 | 6 | Directory enumeration (`dir`, `rg --files`) |
| `test_success` | 195 | 6 | 6 | Passing test suite outputs |
| `test_failure` | 94 | 6 | 6 | Diagnostic tracebacks, assertion failures |
| `progress_build` | 62 | 4 | 4 | Long-running build / download logs |
| `script_or_unknown` | 1,654 | 4 | 4 | Orchestrator and multi-tool scripts |
| **Total** | **4,362** | **50** | **50** | |

### Privacy and Sensitivity Screening
- FioFilter's sensitivity detector (`contains_sensitive_material`) was applied as an automated filter before persisting any entry.
- **83 tool calls** containing credential patterns, tokens, or private keys were screened out from candidate extraction.
- The resulting corpus file was saved strictly outside the Git repository at `C:\Users\phped\.fiofilter\corpus\m03_fioos_sample_v1.jsonl`.
- Zero raw historical user outputs or credentials were committed to Git.

---

## 4. Ground-Truth Oracle Labeling

Each entry was independently audited and assigned oracle labels prior to FioFilter evaluation:
- **`evidence_class`**: Assigned by domain inspection of command and stream intent (`CANONICAL_STATE`, `DISCOVERY`, `FAILURE`, `SUCCESS_SUMMARY`, `PROGRESS`, `UNKNOWN`).
- **`sensitivity`**: Screened and marked `NOT_SENSITIVE`.
- **`transform_eligibility`**:
  - `RAW_REQUIRED` for Git canonical state, test failures, file reads, and unknown scripts (29 entries).
  - `SAFE_TO_REDUCE` for search results, directory listings, passing test summaries, and repetitive progress (21 entries).
- **`inline_required_facts`**: Specific commit hashes, branch names, and summary tallies that must remain visible inline.
- **`missed_opportunity_category`**: Pre-classified candidate bucket for safe reduction opportunities.

---

## 5. Replay Results (FioOS Real Workload Sample)

Evaluated with `fiofilter.corpus.replay_corpus` under `Mode.BUILD` and `profile_id='fioos'`:

```
Total Sample Entries:        50
Total Raw Bytes:             442,488 bytes (110,622.0 estimated tokens)
Total Visible Bytes:         442,488 bytes (110,622.0 estimated tokens)
Local Byte Reduction:        0.0%
Local Token Reduction:       0.0%
```

### Safety Audit
```
DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY:  0  (PASS)
UNSAFE_SENSITIVITY_LEAK:                0  (PASS)
SAFE_MATCH:                            29
SAFE_OPPORTUNITY_MISSED:               21
```
- **0 false eligibilities**: No protected Git evidence, test failure, or canonical state was modified.
- **21 safe opportunities missed**: Outputs that a human oracle confirms could be safely reduced without evidence loss remained 100% RAW.

### T01 Performance Analysis
```
T01 Eligible Entries:                   0
T01 Transformed Entries:                0
T01 Marker Overhead Defeated Entries:   0
T01 Unapproved Grammar Entries:        21
```
**Why did T01 achieve 0% reduction on real workloads?**
T01 strictly requires *identical consecutive lines* (`lines[i] == lines[i+1]`). Real coding agent tool outputs do not have identical lines repeating consecutively:
1. Search results repeat the *file path*, but each line has a different line number and matching code snippet.
2. Build outputs repeat the *status prefix*, but the percentage or elapsed time advances on every line.
3. Test outputs repeat the *outcome label* (`PASSED`), but each line contains a distinct test function name.
4. Codex `exec` wraps commands with execution headers (`Script completed\nWall time...`), preventing naive multi-line deduplication.

---

## 6. Missed Safe Opportunity Analysis

For the 21 entries labeled `SAFE_TO_REDUCE` where FioFilter returned `RAW`, the volume of compressible context was measured across four candidate buckets:

| Candidate Bucket | Entries | Raw Bytes | Estimated Tokens | Share of Missed Bytes | Risk Level | Likely Transform Family |
|---|---|---|---|---|---|---|
| **`DUPLICATED_HEADERS`** | 6 | 97,503 B | 24,375.8 tok | **60.01%** | Very Low | Path-grouping search transform |
| **`REPETITIVE_PROGRESS`** | 3 | 53,169 B | 13,292.2 tok | **32.72%** | Low | Template/progress fold |
| **`KNOWN_SUCCESS_RECORDS`** | 6 | 9,803 B | 2,450.8 tok | **6.03%** | Moderate | Pass-list aggregator |
| **`DIRECTORY_OR_PATH_REDUNDANCY`** | 6 | 2,012 B | 503.0 tok | **1.24%** | Low | Prefix/tree compressor |
| **Total Missed Opportunity** | **21** | **162,487 B** | **40,621.8 tok** | **100.0%** | | |

---

## 7. Secondary Observational Sample (FioIdeias)

A secondary sample of 10 entries was extracted from FioIdeias session `01a059d2-0075-7101-815a-b8408619a86f` to observe cross-project consistency:
- **Status**: `SECONDARY — NOT_GENERAL_PROOF`
- **Total Raw Bytes**: 175,558 bytes (43,889.5 estimated tokens)
- **Safety**: `DANGEROUS_FALSE_TRANSFORM_ELIGIBILITY = 0`, `UNSAFE_SENSITIVITY_LEAK = 0`
- **T01 Reduction**: `0.0%`
- **Missed Opportunities**:
  - `REPETITIVE_PROGRESS`: 40,154 B (47.14% of missed)
  - `DIRECTORY_OR_PATH_REDUNDANCY`: 40,154 B (47.14% of missed)
  - `DUPLICATED_HEADERS`: 4,032 B (4.73% of missed)
  - `KNOWN_SUCCESS_RECORDS`: 837 B (0.98% of missed)

**Cross-Project Takeaway**: Across both projects, exact duplicate line folding (T01) fails to compress real outputs, while search header redundancy, progress streaming, and path repetition account for 100% of missed context savings.

---

## 8. Frontier Ranking & Dimension Analysis

Dimensions evaluated:
- **A**: Estimated removable context
- **B**: Frequency in real coding workflows
- **C**: Evidence risk (risk of stripping actionable signal)
- **D**: Determinism (100% reproducible byte transformation)
- **E**: Transform complexity
- **F**: Likelihood of causing corrective retrieval
- **G**: Cross-project relevance
- **H**: Testability / independent oracle strength

### Ranking

#### **FRONTIER_RANK_1: `DUPLICATED_HEADERS` (Search Match Path Deduplication)**
- **Removable Context**: **60.01%** of missed context (97.5 KB in sample).
- **Frequency**: Very high. Coding agents repeatedly run `rg` / search queries during exploration and refactoring.
- **Evidence Risk**: **Very Low**. The file path is simply grouped at the top of matches rather than repeated before every matching line. 100% of line numbers, line contents, and file associations are preserved.
- **Determinism**: 100% deterministic grouping.
- **Complexity**: Low to moderate. Path grouping is a well-understood bijection.
- **Corrective Retrieval Risk**: Near zero. All matching content and locations remain visible inline.
- **Relevance**: Universal across all repositories and programming languages.
- **Oracle Strength**: Very high; exact bijective reconstruction testable.

#### **FRONTIER_RANK_2: `REPETITIVE_PROGRESS` (Progress Bar & Streaming Log Folding)**
- **Removable Context**: **32.72%** of missed context (53.2 KB in sample).
- **Frequency**: High during build, test suite runs, and package installation.
- **Evidence Risk**: Low for completed tasks; moderate if intermediate warnings are embedded.
- **Determinism**: High if pattern-anchored.
- **Complexity**: Moderate (requires template grammar).
- **Corrective Retrieval Risk**: Low once process exits cleanly.

#### **FRONTIER_RANK_3: `KNOWN_SUCCESS_RECORDS` (Pass List Aggregation)**
- **Removable Context**: **6.03%** of missed context (9.8 KB in sample).
- **Frequency**: High during test cycles.
- **Evidence Risk**: Moderate (agents occasionally check if a specific test ran).
- **Determinism**: High.
- **Complexity**: Moderate.
- **Corrective Retrieval Risk**: Moderate if individual test names are needed.

---

## 9. M04 Recommendation

### **`M04_RECOMMENDED_FRONTIER = DUPLICATED_HEADERS`**

**Rationale**:
1. **Largest Opportunity**: It accounts for the majority (60%) of compressible bytes in the real workload.
2. **Safest Frontier**: Grouping search matches under their file path loses zero evidence, zero line numbers, and zero match contents. It presents virtually zero risk of inducing corrective retrieval loops.
3. **Universality**: Every coding agent running in any codebase produces `rg` / `grep` search outputs with heavy path redundancy.
4. **Clean Evidence Contract**: The contract requires only that the set of (file, line_number, match_text) triples in visible output equals the set in raw input.

---

## 10. Economics Disclaimer

All figures reported in this document are **local byte reductions and token approximations (chars / 4)** on bounded sample corpora.
- **`LOCAL_REDUCTION != WHOLE_MISSION_SAVINGS`**
- **`WHOLE_MISSION_SAVINGS = UNKNOWN`**
- Whole-mission savings require end-to-end multi-turn A/B benchmarking measuring prompt tokens, completions, turns, and task success rates.
