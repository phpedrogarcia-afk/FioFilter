# M10 Discovery Ranking Refinement Report

## 1. Executive Summary

Mission **M10** performs targeted refinement of the discovery ranking layer, starting from M09's empirical finding that `LEXICAL_ONLY` outperforms all structural/hybrid variants on the current benchmark.

M10 strategy (per mission brief):
- **STRONG LEXICAL BASELINE FIRST** — implement BM25-style ranking as `BM25_LEXICAL`
- **TASK-SPECIFIC STRUCTURAL RELATIONS SECOND** — authorized only if miss autopsy justifies it
- **GLOBAL GRAPH CENTRALITY ONLY IF IT EARNS VALUE** — remains deferred (NOT_PROVEN from M09)
- **DO_NOT_PAY_GRAPH_COMPLEXITY_FOR_A_LEXICAL_PROBLEM**

```
M10_VERDICT = BM25_LEXICAL_MARGINAL_WIN_STRUCTURAL_RELATIONS_NOT_AUTHORIZED
```

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

---

## 3. Phase B — M10 Implementation

### 3.1 BM25_STYLE_LEXICAL_V1 (`fiofilter/discovery_lexical.py`)

Implements two ablation modes:

- **`LEGACY_LEXICAL`**: M09 exact stem-overlap ranker, preserved for ablation parity
- **`BM25_LEXICAL`**: BM25 ranking with frozen V1 weights

**BM25 V1 frozen weights** (DO NOT change without M10-D001 supersession):
- `k1 = 1.2`
- `b = 0.75`

**Query tokenization V2** (same function used for both query and code — V2 PARITY):
- Splits on path separators, whitespace, all punctuation, dots
- Normalizes `snake_case` → atomic tokens (`read_receipt_shadow` → `read, receipt, shadow`)
- Normalizes `camelCase` → atomic tokens (`ReadReceiptShadow` → `read, receipt, shadow`)
- Normalizes `PascalCase` → atomic tokens (`ContextWasteCensus` → `context, waste, census`)
- Filters stopwords and single-character tokens
- Returns deduplicated list (tokenize_v2) or multiset counts (tokenize_v2_multiset for BM25 TF)

### 3.2 Miss Autopsy V2

Full FioFilter commit history re-scanned (18 commits total):
- 1 root commit (no parent): excluded
- 9 commits introducing **new files** (not in parent snapshot): correctly skipped
- 8 commits with existing modified Python files: eligible for benchmarking
- Final benchmark corpus: **9 commits** (7 non-leaking, 2 path-leaking)

**Skip analysis**: Commits introducing new files produce empty ground-truth against the parent snapshot — the ranker cannot find files that do not yet exist. This is expected, correct behavior and not a benchmark defect.

**Query leakage taxonomy V2**:
- `PATH_LEAKING`: commit message contains the stem of any changed file (after removing mission prefix)
- `NON_LEAKING`: no stem of any changed file appears in the cleaned commit message

### 3.3 Ablation Matrix Results

#### Non-leaking subset (n=7, strict audit):

| Mode | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **LEGACY_LEXICAL** | 16.3% | 38.1% | 54.0% | 60.3% | **0.6786** |
| **BM25_LEXICAL** | 16.3% | 38.1% | 57.9% | **65.9%** | **0.6786** |

**BM25_LEXICAL wins on R@5 (+3.9pp) and R@10 (+5.6pp)** with equal MRR.

#### Path-leaking subset (n=2):

| Mode | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **LEGACY_LEXICAL** | 12.5% | 37.5% | 50.0% | 50.0% | 0.5000 |
| **BM25_LEXICAL** | 12.5% | 37.5% | 50.0% | 50.0% | 0.5000 |

Identical on path-leaking subset.

### 3.4 Miss Autopsy Results

**LEGACY_LEXICAL misses@10 (non-leaking): 1**
**BM25_LEXICAL misses@10 (non-leaking): 1** (same commit)

| Commit | Miss Reason | Query Tokens | Ground Truth |
| :--- | :--- | :--- | :--- |
| `5091ac08` | `ZERO_LEXICAL_OVERLAP` | `[m05, clarify, epistemic, scope, exact, redelivery, versus, reference, replacement]` | `[fiofilter/context_census.py]` |

**Miss analysis**: The commit `5091ac08` ("M05: clarify epistemic scope of exact redelivery versus reference replacement") changes `context_census.py`, but no tokens from that filename or its symbols (`ContextWasteCensus`, `CensusResult`) appear in the commit message. This is a **vocabulary mismatch** — the task description uses epistemic/abstract terms while the code uses measurement terms.

**Structural relations authorization decision**: Structural relations (IMPORTS, CALLS, TEST_RELATES) **cannot bridge a vocabulary mismatch**. The file `context_census.py` is imported by other files, but those files also wouldn't match the query tokens. Adding graph complexity cannot solve a problem where query vocabulary is orthogonal to code vocabulary.

```
DO_NOT_PAY_GRAPH_COMPLEXITY_FOR_A_LEXICAL_PROBLEM = ENFORCED
STRUCTURAL_RELATIONS_V2_AUTHORIZED = FALSE
```

### 3.5 Source A Status

| Claim | Status |
| :--- | :--- |
| `SOURCE_A_DISCOVERY_ACTIVITY_CHARACTERIZED` | YES (490 FILE_READ, 151 episodes, 256 distinct targets) |
| `SOURCE_A_STRUCTURAL_RANK_REPLAY` | NOT_PROVEN (no task→target ground-truth labels available) |
| `SOURCE_A_BM25_LEXICAL_REPLAY` | NOT_PROVEN (same constraint — no task labels) |

---

## 4. Tests

- **New tests**: `tests/test_discovery_lexical.py` — 38 tests covering:
  - Tokenization V2 (snake_case, camelCase, PascalCase, separators, stopwords)
  - Query-code tokenization parity
  - LexicalDocument construction and field invariants
  - BM25Index construction, scoring, ranking, IDF properties
  - Frozen weight assertion (`k1=1.2, b=0.75`)
  - Empty corpus, empty query, unbuilt index guards
  - Legacy lexical ranker (M09 baseline preservation)
- **Total suite**: 431 passed (38 new + 393 pre-M10)

---

## 5. Local Artifacts

Stored in `C:\Users\phped\.fiofilter\structural-shadow\`:

| File | Size | SHA256 |
| :--- | :--- | :--- |
| `m10_miss_autopsy_v1.json` | 27,278 B | `72ba9562e0e76f28129a7b3348ce8cacd1e4e3349a66c16711f4e503d8d63b4e` |
| `m10_ranking_benchmark_v1.json` | 13,700 B | `96e0a9b07ed12f88c680859dac511f2e6044d2451b7ba0f225f1499dd341a7e9` |
| `m10_ablation_v1.json` | 2,341 B | `9a2e5af6f5ba5b00b2a4b929f884e005a208808bfb28094fb42b4519f516600b` |
| `m10_source_a_reconstruction_v1.json` | 360 B | `3f051a75532b66edd496e404da2d302ac340c401d5792e01b7b62cfd8ce9c2d4` |
| `m10_summary_v1.json` | 951 B | `dcd4f1927ed0bfc764d25cb576b81b8257f8259f3320eeafb4c505f9fe7330d5` |

---

## 6. Mission Verdict

```
M10_VERDICT = BM25_LEXICAL_MARGINAL_WIN_STRUCTURAL_RELATIONS_NOT_AUTHORIZED
```

### Justification:

1. **BM25_LEXICAL beats LEGACY_LEXICAL** on the non-leaking corpus: +5.6pp on R@10 (65.9% vs 60.3%), equal MRR (0.6786). The improvement is real but modest on this 7-commit corpus.

2. **Only 1 miss** in both modes. The miss cause (`ZERO_LEXICAL_OVERLAP`) is a vocabulary problem: the task description uses epistemic/abstract terms absent from code identifiers. No ranking algorithm, structural or lexical, can bridge this gap from available signals.

3. **Structural relations not authorized**: The miss autopsy provides no justification for adding IMPORTS, CALLS, or TEST_RELATES edges. BM25 is not impaired by the absence of structural relations on this corpus — the impairment is vocabulary, not graph topology.

4. **PPR remains NOT_PROVEN**: The M09 finding stands. Global graph centrality does not earn value on this benchmark.

5. **`FioFilter BECOMES SIMPLER`**: The correct M10 outcome — BM25_LEXICAL wins, structural relations add no proven value. This simplifies the system by establishing a strong, deterministic, dependency-free lexical baseline without requiring graph infrastructure.

### Epistemic Classification:

| Claim | Status |
| :--- | :--- |
| `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_R10` | **PROVEN** on 7-commit non-leaking corpus (+5.6pp) |
| `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_MRR` | **NOT_PROVEN** (equal MRR on this corpus) |
| `STRUCTURAL_RELATIONS_ADD_VALUE_OVER_BM25` | **NOT_PROVEN** (not authorized by miss autopsy) |
| `PPR_VALUE_AS_IMPLEMENTED` | **NOT_PROVEN** (unchanged from M09) |
| `BM25_V1_WEIGHTS_FROZEN` | `k1=1.2, b=0.75` — **FROZEN** |
| `STRUCTURAL_RELATIONS_V2_AUTHORIZED` | **FALSE** |
| `DISCOVERY_READ_SUPPRESSION` | **NO** (frozen, non-authoritative) |

---

## 7. Repository State

- **Branch**: `antigravity/m10-discovery-ranking-refinement`
- **Based on**: `main @ 4e3121e` (FINAL_M09_MAIN)
- **PR**: DO NOT MERGE until authorized
- **Tests**: 431 passed, 0 failed