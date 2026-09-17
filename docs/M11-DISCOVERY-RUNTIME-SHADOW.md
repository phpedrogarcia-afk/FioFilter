# M11 Discovery Runtime Shadow Report

## 1. Executive Summary

Mission **M11** operationalizes the cheapest useful discovery mechanism as an explicit runtime shadow harness.

Inheriting the deterministic BM25 lexical ranking validated in M10 and repaired in M10-R1, M11 provides `DiscoveryRuntimeShadow`, an evaluation engine that transforms a task query and a repository worktree snapshot into ranked navigation candidates and a compact index map.

```
M11_VERDICT = M11_DISCOVERY_RUNTIME_SHADOW_PASS_LIVE_TARGET_READY
```

### Core Invariants

- **`INDEX_AUTHORITY = NAVIGATION_ONLY`**: The index is an orientation hint, never ground-truth evidence.
- **`INDEX_CAN_SATISFY_EVIDENCE = NO`**: Reading an index entry does not count as reading the source file.
- **`INDEX_CAN_AUTHORIZE_CHANGE = NO`**: Edits require full raw source inspection.
- **`INDEX_CAN_HIDE_LOW_RANK_FILES = NO`**: Unranked or low-ranked files are never pruned or hidden from tools.
- **`DISCOVERY_READ_SUPPRESSION = NO`**: No read suppression is performed or authorized.
- **`AUTO_CONTEXT_SELECTION = NO`**: No context is automatically injected into LLM or agent prompts.
- **`SHADOW_FAILURE_AGENT_PATH_UNCHANGED = PASS`**: If shadow computation fails, the agent experience is unchanged.

---

## 2. M10-R1 Integrity Inheritance & Final Promotion

M10 was finalized through exact fast-forward merge without squash, preserving full validated commit history:

- **`M10_EXACT_FAST_FORWARD`**: `PASS`
- **`FINAL_M10_MAIN`**: `362e6e6eba526ca1d7ebe1e28553678a92573e6e`
- **`FINAL_M10_TREE`**: `08566b3b3e4c9def41c31271cb3a5a94c597ec0a`

All determinism, hash-seed reproducibility, and tie-breaking contracts from M10-R1 are preserved in M11.

---

## 3. Runtime Shadow Architecture

### 3.1 API (`fiofilter/discovery_runtime_shadow.py`)

```python
DiscoveryRuntimeShadow.evaluate(
    repo_root: pathlib.Path,
    task_query: str,
    top_k: int = 10,
    map_budget_bytes: int = 2048,
) -> Optional[ShadowEvaluation]
```

Returns `ShadowEvaluation` metadata only:
- Provenance: `repo_root`, `head_sha`, `dirty_digest`, `snapshot_id`, `query_hash`, `evaluation_hash`
- Version binding: `tokenizer_version`, `bm25_version`, `k1`, `b`, `indexed_fields`, `tie_break_policy`, `index_authority`
- Navigation results: ranked `CandidateResult` list (rank, path, score, matched tokens)
- Map representation: compact text index map bounded by `map_budget_bytes`
- Timings: `snapshot_build_ms`, `index_build_ms`, `query_tokenize_ms`, `ranking_ms`, `map_render_ms`, `total_ms`, `is_warm`
- Health: `files_indexed`, `candidate_count`, `estimated_map_tokens`

### 3.2 Explicit Invocation Only

M11 operates solely via explicit programmatic invocation. It installs:
- NO global Codex/Antigravity hooks
- NO shell intercepts or daemon processes
- NO MCP server or proxy
- NO automatic task query interception

---

## 4. Provenance & Determinism

### 4.1 Provenance Binding

Every shadow evaluation is bound to:
1. `head_sha`: Current git `HEAD` commit SHA
2. `dirty_digest`: 16-char hash of `git status --porcelain`
3. `snapshot_id`: `SHA256(head_sha:dirty_digest:sorted_files_hash)[:16]`
4. `query_hash`: `SHA256(task_query)[:16]`
5. `evaluation_hash`: `SHA256(snapshot_id:query_hash:top_k_paths)[:16]`

### 4.2 Stale Snapshot Defense

If the working tree changes between calls (different `git status --porcelain`), the `dirty_digest` changes, forcing a new `snapshot_id`. The in-memory cache rejects stale snapshots and re-indexes the modified worktree.

### 4.3 Deterministic Tie-Breaking

All candidate ordering follows `(-score, path ASC)`. Rankings are bit-identical across runs, input orders, and Python hash seeds.

```
RUNTIME_SHADOW_DETERMINISM = PASS
```

---

## 5. Shadow Ledger

Append-only local JSONL ledger:
`C:\Users\phped\.fiofilter\discovery-runtime-shadow\shadow_ledger.jsonl`

**Privacy**: The ledger never records the raw task query string. Only `query_hash`, `snapshot_id`, candidate paths, scores, map sizes, and chained event hashes are persisted.

Each event includes:
- `previous_event_hash`
- `event_hash`: `SHA256(previous_event_hash + evaluation_hash)[:16]`

---

## 6. Empirical Experiments

### 6.1 Self-Shadow Experiment (Controlled Live Task)

Before implementing M11 code, M10 BM25 was run against M11's own mission query:
*"lexical first discovery runtime shadow harness evaluate snapshot query provenance BM25"*

Prework top-10 candidates were stored locally before any M11 edits.
After implementation, actually modified files (`fiofilter/discovery_runtime_shadow.py`, `tests/test_discovery_runtime_shadow.py`) were compared against the prework prediction:

| Metric | Result | Note |
| :--- | :---: | :--- |
| `SELF_SHADOW_CHANGED_FILE_RECALL_AT_1` | **0.0%** | (rank 1 was tests/test_discovery_shadow.py) |
| `SELF_SHADOW_CHANGED_FILE_RECALL_AT_3` | **0.0%** | |
| `SELF_SHADOW_CHANGED_FILE_RECALL_AT_5` | **0.0%** | |
| `SELF_SHADOW_CHANGED_FILE_RECALL_AT_10` | **50.0%** | `discovery_runtime_shadow.py` ranked #6 |
| Sample size | `N=1 TASK` | Anecdotal live evidence only |

`tests/test_discovery_runtime_shadow.py` did not exist in the prework snapshot and was unretrievable. The primary implemented file `fiofilter/discovery_runtime_shadow.py` was retrieved at rank 6.

### 6.2 Synthetic Task Stream

Ran 5 deterministic synthetic tasks against the repository:

| Task ID | Query | Target | Status | R@1 | R@5 | R@10 | Time |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `SYN-001` | "update read receipt freshness check" | `read_receipt.py` | OK | 1.0 | 1.0 | 1.0 | 250.9ms (cold) |
| `SYN-002` | "change runtime shadow checkpoint stream" | `runtime_shadow.py` | OK | 1.0 | 1.0 | 1.0 | 230.3ms (warm) |
| `SYN-003` | "modify context waste census accounting" | `context_census.py` | OK | 0.0 | 1.0 | 1.0 | 229.5ms (warm) |
| `SYN-004` | "adjust search grammar grouping transform" | `store.py` | OK | 0.0 | 0.0 | 0.0 | 229.3ms (warm) |
| `SYN-005` | "session reexposure shadow evaluation" | `reexposure.py` | OK | 0.0 | 1.0 | 1.0 | 234.4ms (warm) |

**Stream Summary**: 4/5 tasks retrieved in top 5. All 5 logged to local ledger with chained hashes.

---

## 7. Cost & Performance Economics

Measured on 64-file repository snapshot:

| Phase | Cold Evaluation | Warm Reused Snapshot |
| :--- | :---: | :---: |
| Worktree AST snapshot | ~175 ms | ~175 ms (worktree check) |
| BM25 index build | ~8.6 ms | **0.0 ms** (cached) |
| Query tokenization | <0.1 ms | <0.1 ms |
| BM25 ranking | <0.1 ms | <0.1 ms |
| Map rendering | <0.1 ms | <0.1 ms |
| **Total Evaluation** | **~251 ms** | **~230 ms** |

- Map footprint: ~909 bytes for top-10 candidates
- Estimated token cost: **227 tokens** (`bytes // 4` model)

### Behavioral Savings Claims

```
DISCOVERY_BYTES_AVOIDABLE = UNKNOWN
MODEL_TURN_SAVINGS = UNKNOWN
BEHAVIORAL_EQUIVALENCE = UNKNOWN
```

M11 proves only runtime feasibility and deterministic candidate delivery, not production token savings.

---

## 8. Failure Isolation & Safety

```
SHADOW_FAILURE_AGENT_PATH_UNCHANGED = PASS
```

Any exception during snapshot extraction, tokenization, ranking, map formatting, or ledger recording is caught inside `evaluate()`, returning `None`. The agent workflow continues without error or interruption.

---

## 9. Status of All Shadow Lanes

| Lane | Status |
| :--- | :--- |
| **Read Receipt Shadow (M07/M08)** | `READY_FOR_LIVE_CODEX_SHADOW` (frozen until Codex available) |
| **Reexposure Shadow (M06)** | `READY_FOR_LIVE_CODEX_SHADOW` (frozen until Codex available) |
| **Discovery Runtime Shadow (M11)** | **`DISCOVERY_READY_FOR_LIVE_CODEX_SHADOW`** |

Both major shadow lanes are now complete at the shadow level, fully characterized on historical and synthetic corpora, and ready for passive live observation when the live environment becomes available.

---

## 10. Local Artifacts

Stored in `C:\Users\phped\.fiofilter\discovery-runtime-shadow\`:

| File | Size | SHA256 |
| :--- | :--- | :--- |
| `m11_self_shadow_prework_v1.json` | 2,539 B | `e1582778e04cc1bb11cca6705cfc9762cd1b93e4abf213895c80329d55066d3e` |
| `m11_self_shadow_eval_v1.json` | 1,197 B | `28a97e466a7a6007cdbd7931e50dccd34153c2ac17b5da786005f330fac32c4c` |
| `m11_synthetic_stream_v1.json` | 3,740 B | `0918317acf3f29070f86682018fbb8aa6a56bbbf13ee31f14da05cbd8a432557` |
| `m11_summary_v1.json` | 1,419 B | `af2574aca587067bb71fff65dd89df86521e8b2daae0d04c777e3b546a6d999a` |
| `shadow_ledger.jsonl` | 4,666 B | `f1e19f7d25ddca7babd680dc048965c91e3bec06c7f3efbbcebeedae91a46d4e` |

---

## 11. Final Verdict

```
M11_CANONICAL_VERDICT = M11_DISCOVERY_RUNTIME_SHADOW_PASS_LIVE_TARGET_READY
```