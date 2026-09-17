# M10 Discovery Ranking Refinement Report

## 1. Executive Summary

Mission **M10** performs targeted refinement of the discovery ranking layer, starting from M09's empirical finding that `LEXICAL_ONLY` outperforms all structural/hybrid variants on the current benchmark.

M10 strategy (per mission brief):
- **STRONG LEXICAL BASELINE FIRST** — implement BM25-style ranking as `BM25_LEXICAL`
- **TASK-SPECIFIC STRUCTURAL RELATIONS SECOND** — authorized only if miss autopsy justifies it
- **GLOBAL GRAPH CENTRALITY ONLY IF IT EARNS VALUE** — remains deferred (NOT_PROVEN from M09)
- **DO_NOT_PAY_GRAPH_COMPLEXITY_FOR_A_LEXICAL_PROBLEM**

```
M10_CANONICAL_VERDICT = M10_DISCOVERY_REFINEMENT_PASS_LEXICAL_FIRST
```

**M10-R1 Integrity Audit**: Benchmark population reconciliation, ranking determinism hardening,
hash-seed reproducibility gate, input-order independence, zero-overlap field diagnostic,
and structural bridge diagnostic.

---

## 2. Phase A — M09 Claim Hygiene (Completed)

All M09 claim corrections applied and pushed:

| Claim | M09 (Before) | M09 (After) |
| :--- | :--- | :--- |
| Verdict | `ADVANCE_TO_M10` | `M09_DISCOVERY_SHADOW_PASS_MORE_RANKING_EVIDENCE_REQUIRED` |
| Edge metric | `edge_coverage=100%` | `RECOGNIZED_LOCAL_IMPORT_RESOLUTION_COVERAGE=429/429` + `GRAPH_RELATION_COMPLETENESS=UNKNOWN` |
| PPR insight | "PPR provides neighborhood expansion" | `PPR_VALUE_AS_IMPLEMENTED=NOT_PROVEN` (CLAIMED_ONLY) |
| Source A | implied structural rank replay | `SOURCE_A_STRUCTURAL_RANK_REPLAY=NOT_PROVEN` |
| Donor hypothesis | not explicit | `CURRENT_GLOBAL_STRUCTURAL_SIGNALS_DO_NOT_BEAT_LEXICAL_BASELINE=PROVEN` |

**FINAL_M09_MAIN** = `4e3121ecb15bfe1143a1191211303a6bcad8f66b`
**FINAL_M09_TREE** = `c79d2f0a68268da2823b50abd85e3d3d7ec0c479`

### M09 Merge-Policy Incident (M10-R1 Recorded)

| Fact | Value |
| :--- | :--- |
| `M09_CONTENT_PRESERVED` | YES (tree SHA match) |
| `M09_HISTORY_POLICY_VIOLATION` | YES (squash not ff-only) |
| `M09_VALIDATED_HEAD_PRESERVED_IN_MAIN_HISTORY` | NO |
| `M09_TREE_EQUIVALENCE` | PASS |
| `M09_AUTHOR_IDENTITY_VIOLATION` | YES (gh pr merge used web-auth identity, not NOREPLY) |
| `DO_NOT_USE_GH_PR_MERGE_FOR_EXACT_FAST_FORWARD_MISSIONS` | YES |

Future exact promotion mechanism: `git checkout main && git merge --ff-only <validated-branch> && git push origin main`

---

## 3. Phase B — M10 Implementation

### 3.1 BM25_STYLE_LEXICAL_V1 (`fiofilter/discovery_lexical.py`)

Implements two ablation modes:

- **`LEGACY_LEXICAL`**: M09 exact stem-overlap ranker, preserved for ablation parity
- **`BM25_LEXICAL`**: BM25 ranking with frozen V1 weights

**BM25 V1 frozen weights** (DO NOT change without M10-D001 supersession):
- `k1 = 1.2`
- `b = 0.75`

**Ranking determinism (M10-R1 fix)**: Both `BM25Index.rank()` and `legacy_rank()` sort by
`score DESC, path ASC`. This is a stable tie-breaker that is deterministic regardless of
PYTHONHASHSEED, set iteration order, or document insertion order.

**Query tokenization V2** (same function used for both query and code — V2 PARITY):
- Splits on path separators, whitespace, all punctuation, dots
- Normalizes `snake_case` → atomic tokens (`read_receipt_shadow` → `read, receipt, shadow`)
- Normalizes `camelCase` → atomic tokens (`ReadReceiptShadow` → `read, receipt, shadow`)
- Normalizes `PascalCase` → atomic tokens (`ContextWasteCensus` → `context, waste, census`)
- Filters stopwords and single-character tokens
- Returns deduplicated list (tokenize_v2) or multiset counts (tokenize_v2_multiset for BM25 TF)

### 3.2 Benchmark Population Reconciliation (M10-R1 Corrected)

Full FioFilter commit history classified (19 commits total including M10 branch HEAD):

| Bucket | Count | Description |
| :--- | :---: | :--- |
| `ROOT_NO_PARENT` | 1 | No parent (ddc08707) — excluded |
| `NO_PYTHON_CHANGE` | 3 | Parent exists but no .py files changed — excluded |
| `EXISTING_FILE_ONLY` | 5 | All changed .py files existed in parent snapshot |
| `NEW_FILE_ONLY` | 6 | All changed .py files are new (not in parent git ls-tree) |
| `MIXED_EXISTING_AND_NEW` | 4 | Some new, some existing |
| **Total** | **19** | |

**Benchmarkable commits**: 9 (EXISTING_FILE_ONLY=5, MIXED_EXISTING_AND_NEW=4)

**Ground truth methodology**:
- `retrievable_gt` = existing-file positives only (files that existed in parent snapshot)
- `unretrievable_new` = new files introduced by the commit (NOT added to GT — ranker cannot retrieve files not yet in corpus)
- For MIXED commits: existing-file positives are benchmarked; new files are excluded from GT

**Path matching**: Exact normalized repository-relative paths from `git ls-tree -r --name-only <parent_sha>`. NOT basename matching.

**Query leakage taxonomy V2**:
- `PATH_LEAKING`: any token from `tokenize_v2(stem_of_changed_file)` appears in `tokenize_v2(cleaned_query)`
- `NON_LEAKING`: no such overlap

**Corrected leakage classification** (M10-R1):

| Leakage | Count |
| :--- | :---: |
| `NON_LEAKING` | 5 |
| `PATH_LEAKING` | 4 |

> **Note**: Original M10 reported 7 NON_LEAKING / 2 PATH_LEAKING. M10-R1 corrects this to 5 / 4 using exact tokenize_v2 stem matching instead of naive prefix matching. Commits like `M02` (contains "raw_store.py" → "raw" appears in "RAW integrity") are now correctly classified as PATH_LEAKING.

**Small-sample limitations**:
- N=5 non-leaking: `NO_WEIGHT_TUNING` (too small to tune BM25 parameters)
- `TEMPORAL_HOLDOUT=INSUFFICIENT_SAMPLE` (cannot split train/test)
- `GENERAL_SUPERIORITY=NOT_PROVEN` (results are local observations on this corpus only)

### 3.3 Ablation Matrix Results (M10-R1 Corrected with Deterministic Ranking)

#### Non-leaking subset (n=5, corrected):

| Mode | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **LEGACY_LEXICAL** | 18.3% | 30.0% | 30.0% | 36.7% | **0.6000** |
| **BM25_LEXICAL** | 11.7% | 23.3% | 30.0% | 36.7% | **0.4500** |

#### Path-leaking subset (n=4, corrected):

| Mode | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **LEGACY_LEXICAL** | 20.0% | 58.8% | 78.8% | 82.5% | 0.8333 |
| **BM25_LEXICAL** | 20.0% | 47.5% | 80.0% | 85.0% | 0.8125 |

> **Corrected interpretation**: On the corrected 5-commit non-leaking corpus, the original M10 claim "BM25_LEXICAL wins R@10 by +5.6pp" is **NOT reproduced** — both modes score identically at R@10. LEGACY_LEXICAL has higher MRR (0.6000 vs 0.4500). This shift is driven by the leakage reclassification. The corrected claim: `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_R10=NOT_PROVEN` on the corrected corpus. Path-leaking shows BM25 wins R@5/R@10 by ~1.2pp but loses MRR slightly.
>
> **Epistemic scope**: Results are `VERIFIED IN CURRENT TEST CORPUS (N=5 non-leaking)`. N < 20 → no weight tuning, no holdout, no general superiority claim.

### 3.4 Ranking Determinism (M10-R1)

| Property | Result |
| :--- | :--- |
| `HASH_SEED_RANKING_DETERMINISM` | **PASS** (seeds 1, 42, 999 identical) |
| `INPUT_ORDER_INDEPENDENCE` | **PASS** (original, reversed, shuffled identical) |
| Tie-breaking | `score DESC, path ASC` — stable, deterministic |

### 3.5 Zero-Overlap Field Diagnostic (Miss Commit `5091ac08`)

Miss: GT=`fiofilter/context_census.py`, query="M05: clarify epistemic scope of exact redelivery versus reference replacement"

Query tokens (9): `[clarify, epistemic, exact, m05, redelivery, reference, replacement, scope, versus]`

| Index Field | Tokens | Overlap with Query | Count |
| :--- | :--- | :--- | :---: |
| `PATH_ONLY` | census, context, fiofilter, py | none | 0 |
| `PATH_PLUS_SYMBOL` | analyze, call, census, classify, command, context, decode, event, extract, fiofilter, init, load, output, path, py, range, session, tool, waste | none | 0 |
| `FULL_SOURCE_TEXT` | 432 unique tokens | exact, m05, redelivery | **3** |

**Result**: `CURRENT_PATH_SYMBOL_BM25_HAS_ZERO_DIRECT_OVERLAP`
**Classification**: `INDEX_FIELD_COVERAGE_GAP` — full source text indexing would enable 3-token overlap

> The original M10 report claimed "no ranking algorithm, structural or lexical, can bridge this gap from available signals." This is **CORRECTED**: the gap is not inherent — it is a **field coverage gap**. Indexing full source text (not just path+symbol) would provide overlap. The current path+symbol index has zero overlap; full source text has 3-token overlap ("exact", "m05", "redelivery"). Field expansion to full source text is `DIAGNOSTICALLY_PROMISING` but not authorized in M10.

### 3.6 Structural Bridge Diagnostic (Miss Commit `5091ac08`)

At parent snapshot `725597f8`, BM25 ranking for the miss query returns **zero positive-score results** (no lexical seeds exist). Therefore:

| Result | Value |
| :--- | :--- |
| BM25 top-5 positive results | 0 (empty) |
| Importers of `context_census.py` | `scripts/run_context_waste_census.py`, `tests/test_context_census.py` |
| Bridge classification | `NO_LEXICAL_SEED_EXISTS` |

**Interpretation**: Structural relations cannot bridge this miss because there are no BM25 seeds to expand from. Even if IMPORTS edges were added, the expansion starting point is empty. This confirms `DO_NOT_PAY_GRAPH_COMPLEXITY_FOR_A_LEXICAL_PROBLEM`.

```
STRUCTURAL_RELATION_STATUS = NOT_AUTHORIZED_YET
```

> The structural bridge is `NOT_OBSERVED_USEFUL` on this specific miss because there are no BM25 seeds. However, full source text indexing (INDEX_FIELD_COVERAGE_GAP) could provide seeds and make structural expansion viable in the future. This is a scoped diagnostic, not a universal claim.

### 3.7 Source A Status

| Claim | Status |
| :--- | :--- |
| `SOURCE_A_DISCOVERY_ACTIVITY_CHARACTERIZED` | YES (490 FILE_READ, 151 episodes, 256 distinct targets) |
| `SOURCE_A_STRUCTURAL_RANK_REPLAY` | NOT_PROVEN (no task→target ground-truth labels available) |
| `SOURCE_A_BM25_LEXICAL_REPLAY` | NOT_PROVEN (same constraint — no task labels) |

---

## 4. Tests

- **M10 tests**: `tests/test_discovery_lexical.py` — 38 tests covering tokenization V2,
  BM25Index, scoring, ranking, frozen weights, empty corpus, legacy ranker
- **M10-R1 tests**: `tests/test_discovery_lexical_determinism.py` — 17 tests covering:
  - Deterministic tie-breaking (score DESC, path ASC) for BM25 and legacy
  - Input-order independence
  - PYTHONHASHSEED independence (fixed-data determinism)
  - Duplicate basenames matched by exact repo-relative path
  - NEW_FILE_ONLY commit → empty retrievable GT
  - MIXED commit → existing-file positives benchmarked only
  - Exact repo-relative path matching (not basename)
  - Zero path+symbol overlap → score 0
  - Field coverage gap: full source text may contain tokens absent from path+symbol
  - legacy_rank tie-breaking by path ASC
- **Total suite**: 448 passed (17 new M10-R1 + 38 M10 + 393 pre-M10)

---

## 5. Local Artifacts

Stored in `C:\Users\phped\.fiofilter\structural-shadow\`:

| File | Description |
| :--- | :--- |
| `m10_miss_autopsy_v1.json` | M10 original miss autopsy |
| `m10_ranking_benchmark_v1.json` | M10 original benchmark |
| `m10_ablation_v1.json` | M10 original ablation |
| `m10_summary_v1.json` | M10 original summary |
| `m10r1_ranking_benchmark_v1.json` | M10-R1 corrected benchmark (9 commits, leakage reclassified) |

---

## 6. Mission Verdict

```
M10_CANONICAL_VERDICT = M10_DISCOVERY_REFINEMENT_PASS_LEXICAL_FIRST
```

### Justification:

1. **BM25_LEXICAL implemented** as a strong deterministic lexical baseline with frozen V1 weights
   (`k1=1.2`, `b=0.75`). No external dependencies. Fully deterministic (PYTHONHASHSEED-independent,
   input-order-independent).

2. **Corrected benchmark** (M10-R1): 5 NON_LEAKING, 4 PATH_LEAKING commits. On the corrected
   non-leaking corpus (n=5), BM25_LEXICAL and LEGACY_LEXICAL achieve identical R@10 (36.7%).
   LEGACY_LEXICAL has higher MRR (0.6000 vs 0.4500). `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_R10=NOT_PROVEN`
   on corrected corpus. Small sample (N=5): no weight tuning, no holdout, no general superiority claim.

3. **Only 1 miss@10** (both modes, non-leaking): commit `5091ac08`. Root cause: `INDEX_FIELD_COVERAGE_GAP`
   — the current path+symbol index has zero overlap with query tokens, but full source text indexing
   would provide 3-token overlap ("exact", "m05", "redelivery"). This is a field coverage limitation,
   not a fundamental impossibility.

4. **Structural bridge diagnostic**: `NO_LEXICAL_SEED_EXISTS` — no BM25 seeds exist for the miss
   commit, so structural expansion cannot help. `STRUCTURAL_RELATION_STATUS = NOT_AUTHORIZED_YET`.

5. **PPR remains NOT_PROVEN**: The M09 finding stands. Global graph centrality does not earn value.

6. **`FioFilter BECOMES SIMPLER`**: BM25_LEXICAL wins in simplicity and determinism. Structural
   relations remain unauthorized — a valid and valuable negative result.

### Epistemic Classification:

| Claim | Status |
| :--- | :--- |
| `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_R10` | **NOT_PROVEN** (equal on corrected 5-commit corpus; was PROVEN before leakage correction) |
| `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_MRR` | **NOT_PROVEN** (LEGACY wins MRR on corrected corpus) |
| `STRUCTURAL_RELATIONS_ADD_VALUE_OVER_BM25` | **NOT_PROVEN** (not authorized by miss autopsy) |
| `PPR_VALUE_AS_IMPLEMENTED` | **NOT_PROVEN** (unchanged from M09) |
| `BM25_V1_WEIGHTS_FROZEN` | `k1=1.2, b=0.75` — **FROZEN** |
| `STRUCTURAL_RELATIONS_V2_AUTHORIZED` | **FALSE** |
| `DISCOVERY_READ_SUPPRESSION` | **NO** (frozen, non-authoritative) |
| `HASH_SEED_RANKING_DETERMINISM` | **PASS** |
| `INPUT_ORDER_INDEPENDENCE` | **PASS** |
| `CURRENT_PATH_SYMBOL_BM25_HAS_ZERO_DIRECT_OVERLAP` | **PROVEN** (for commit 5091ac08) |
| `INDEX_FIELD_COVERAGE_GAP` | **PROVEN** (full text has 3-token overlap; path+symbol has 0) |
| `STRUCTURAL_BRIDGE_RESULT` | `NO_LEXICAL_SEED_EXISTS` |
| `STRUCTURAL_RELATION_STATUS` | `NOT_AUTHORIZED_YET` |
| `NO_WEIGHT_TUNING` | YES (N < 20) |
| `TEMPORAL_HOLDOUT` | `INSUFFICIENT_SAMPLE` |
| `GENERAL_SUPERIORITY` | `NOT_PROVEN` |

---

## 7. Repository State

- **Branch**: `antigravity/m10-discovery-ranking-refinement`
- **Based on**: `main @ 4e3121e` (FINAL_M09_MAIN)
- **PR**: DO NOT MERGE until authorized
- **Tests**: 448 passed, 0 failed (17 new M10-R1 + 38 M10 + 393 pre-M10)
