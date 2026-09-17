# M11 Discovery Runtime Shadow Report

## 1. Executive Summary

Mission **M11** (and integrity repair **M11-R1**) establishes the explicit runtime shadow harness for lexical repository discovery navigation.

Inheriting the deterministic BM25 lexical ranking validated in M10/M10-R1, M11 provides `DiscoveryRuntimeShadow`, an evaluation engine that transforms a task query and a repository worktree snapshot into ranked navigation candidates and a compact index map.

```
M11_CANONICAL_VERDICT = M11_DISCOVERY_RUNTIME_SHADOW_PASS_LIVE_TARGET_READY
```

### Core Invariants

- **`INDEX_AUTHORITY = NAVIGATION_ONLY`**: The index is an orientation hint, never ground-truth evidence.
- **`INDEX_CAN_SATISFY_EVIDENCE = NO`**: Reading an index entry does not count as reading the source file.
- **`INDEX_CAN_AUTHORIZE_CHANGE = NO`**: Edits require full raw source inspection.
- **`INDEX_CAN_HIDE_LOW_RANK_FILES = NO`**: Unranked or low-ranked files are never pruned or hidden from tools.
- **`DISCOVERY_READ_SUPPRESSION = NO`**: No read suppression is performed or authorized.
- **`AUTO_CONTEXT_SELECTION = NO`**: No context is automatically injected into LLM or agent prompts.
- **`SHADOW_FAILURE_AGENT_PATH_UNCHANGED = PASS`**: If shadow computation fails, the agent experience is unchanged.
- **`WORKTREE_STATUS_IS_NOT_CONTENT_IDENTITY`**: `git status --porcelain` alone is metadata, not a freshness proof.
- **`CACHE_HIT_MUST_BE_PROVEN`**: Index reuse requires bit-identical V2 content key match.

---

## 2. M10-R1 Integrity Inheritance & Final Promotion

M10 was finalized through exact fast-forward merge without squash, preserving full validated commit history:

- **`M10_EXACT_FAST_FORWARD`**: `PASS`
- **`FINAL_M10_MAIN`**: `362e6e6eba526ca1d7ebe1e28553678a92573e6e`
- **`FINAL_M10_TREE`**: `08566b3b3e4c9def41c31271cb3a5a94c597ec0a`

All determinism, hash-seed reproducibility, and tie-breaking contracts (`SCORE_DESC_PATH_ASC`) from M10-R1 are preserved in M11.

---

## 3. Worktree Snapshot Integrity & V2 Fingerprint (M11-R1)

### 3.1 Status-Only Stale Detection Failure (Reproduced)

An integrity audit identified that the original M11 fingerprint:
```python
dirty_digest = hashlib.sha256(git_status_porcelain.encode()).hexdigest()[:16]
```
failed to detect mutations to an already-dirty file:
- File modified to content B: status is `' M file.py'` -> digest `b769e784e6cc980b`
- Same file modified to content C: status remains `' M file.py'` -> digest `b769e784e6cc980b` (UNCHANGED)

```
STATUS_ONLY_STALE_DETECTION_FAILURE = REPRODUCED
```

### 3.2 Content-Sensitive Worktree Fingerprint (`WORKTREE_STATE_DIGEST_V2`)

Implemented `get_worktree_state_digest_v2()` in `fiofilter/discovery_runtime_shadow.py`:
```
WORKTREE_STATE_DIGEST_V2 = SHA256(
    "WORKTREE_STATE_V2:"
    + HEAD_SHA
    + "\nDIFF:" + git_diff_binary_HEAD_py
    + "\nUNTRACKED:" + sorted_untracked_py_with_byte_hashes
)
```

Scope policy: `INDEXED_FILE_UNIVERSE_POLICY = "PYTHON_SOURCES_V1"`. Non-Python changes (e.g. `README.md`, `.txt`, `.git` internals) do not needlessly invalidate the Python index.

### 3.3 Verification Gates Matrix

| Gate | Status | Evidence |
| :--- | :---: | :--- |
| `ALREADY_DIRTY_SECOND_MUTATION_DETECTED` | **PASS** | Byte change in already-dirty file alters diff against HEAD |
| `STAGED_UNSTAGED_MATRIX` | **PASS** | Captures staged, unstaged, re-staged, and hard-reset states |
| `UNTRACKED_SAME_STATUS_CONTENT_CHANGE_DETECTED` | **PASS** | Content change in `?? new.py` alters byte hash |
| `DELETE_RENAME_NEW_FILE` | **PASS** | Deletions and renames alter diff and untracked entries |
| `CONTENT_IDENTITY_NOT_MTIME_IDENTITY` | **PASS** | Rewriting identical bytes leaves content digest unchanged |
| `CACHE_HIT_REQUIRES_V2_KEY` | **PASS** | Cache key binds to `(repo, head, digest_v2, bm25_v, policy)` |
| `STALE_CACHE_DEFENSE` | **PASS** | Stale dirty file mutation forces `CACHE_HIT=NO`, index rebuild |

---

## 4. Runtime Shadow Architecture & API

### 4.1 API

```python
DiscoveryRuntimeShadow.evaluate(
    repo_root: pathlib.Path,
    task_query: str,
    top_k: int = 10,
    map_budget_bytes: int = 2048,
) -> Optional[ShadowEvaluation]
```

Returns `ShadowEvaluation` metadata only:
- Provenance: `repo_root`, `head_sha`, `dirty_digest` (status metadata), `worktree_state_digest` (V2 content digest), `snapshot_id`, `query_hash`, `evaluation_hash`, `file_universe_policy`
- Version binding: `tokenizer_version = V2`, `bm25_version = BM25_STYLE_LEXICAL_V1`, `k1 = 1.2`, `b = 0.75`, `indexed_fields = ('PATH', 'SYMBOL_NAMES')`, `tie_break_policy = SCORE_DESC_PATH_ASC`
- Results: ranked `CandidateResult` list (rank, path, score, matched tokens)
- Map representation: compact text index map bounded by `map_budget_bytes`
- Timings: `state_validation_ms`, `snapshot_build_ms`, `index_build_ms`, `query_tokenize_ms`, `ranking_ms`, `map_render_ms`, `total_ms`, `is_warm`, `query_type` ("COLD_EVALUATION" vs "INDEX_REUSE_QUERY")
- Index health: `files_indexed`, `candidate_count`, `estimated_map_tokens`

### 4.2 Explicit Invocation Only

M11 operates solely via explicit programmatic invocation:
- NO global Codex/Antigravity hooks
- NO shell intercepts or daemon processes
- NO MCP server or proxy
- NO automatic task query interception

---

## 5. Shadow Ledger

Append-only local JSONL ledger:
`C:\Users\phped\.fiofilter\discovery-runtime-shadow\shadow_ledger.jsonl`

**Privacy**: The ledger never records the raw task query string. Only `query_hash`, `snapshot_id`, `worktree_state_digest`, candidate paths, scores, map sizes, and chained event hashes are persisted.

---

## 6. Empirical Experiments & Integrity Audits

### 6.1 Self-Shadow Audit (Prework Contamination)

An audit of `m11_self_shadow_prework_v1.json` revealed:
- Timestamp: `2026-09-17T15:48:06Z`
- Candidate rank 6: `fiofilter/discovery_runtime_shadow.py`
- Root cause: `fiofilter/discovery_runtime_shadow.py` was written to disk prior to running the prework script. The snapshot evaluated an already-contaminated worktree.

```
SELF_SHADOW_PREWORK_CONTAMINATED = YES
M11_SELF_SHADOW_N1 = INVALIDATED_PREWORK_CONTAMINATION
```

- Negative evidence preserved: The artifact is retained locally for provenance.
- Claim hygiene: `Recall@10 = 0.5` is **NOT** counted as live empirical evidence.

### 6.2 Synthetic Task Stream Semantics

Executed 5 deterministic synthetic tasks:

| Task ID | Query | Target | Status | R@1 | R@5 | R@10 | Time |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `SYN-001` | "update read receipt freshness check" | `read_receipt.py` | OK | 1.0 | 1.0 | 1.0 | ~251ms (cold) |
| `SYN-002` | "change runtime shadow checkpoint stream" | `runtime_shadow.py` | OK | 1.0 | 1.0 | 1.0 | ~144ms (index reuse) |
| `SYN-003` | "modify context waste census accounting" | `context_census.py` | OK | 0.0 | 1.0 | 1.0 | ~144ms (index reuse) |
| `SYN-004` | "adjust search grammar grouping transform" | `store.py` | OK | 0.0 | 0.0 | 0.0 | ~144ms (index reuse) |
| `SYN-005` | "session reexposure shadow evaluation" | `reexposure.py` | OK | 0.0 | 1.0 | 1.0 | ~144ms (index reuse) |

**Semantic Clarification**:
- **`HARNESS_EXECUTION_SUCCESS = 5/5`**: All 5 tasks ran through the harness and logged chained ledger entries.
- **`TARGET_RETRIEVAL_AT_10 = 4/5`**: Task SYN-004 missed.
  - Failure classification: **`QUERY_TARGET_MISMATCH_AND_TARGET_LABEL_QUESTIONABLE`**. The query describes T02 (which is in `fiofilter/transforms/rg_standard_group.py`), whereas the target label was assigned `fiofilter/store.py` which contains generic blob logic. Negative result preserved honestly.

---

## 7. Cost & Performance Economics (Remeasured V2)

Measured on 64-file repository snapshot:

| Phase | Cold Evaluation | Index-Reuse Query |
| :--- | :---: | :---: |
| State validation (`git diff` + untracked check) | ~143 ms | ~143 ms |
| Worktree AST parsing | ~174 ms | **0.0 ms** (cached) |
| BM25 index build | ~8.6 ms | **0.0 ms** (cached) |
| Query tokenization | <0.1 ms | <0.1 ms |
| BM25 ranking | <0.1 ms | <0.1 ms |
| Map rendering | <0.1 ms | <0.1 ms |
| **Total Evaluation** | **~326 ms** | **~144 ms** |

Terminology: A query that reuses the BM25 index is designated **`INDEX_REUSE_QUERY`**, accurately acknowledging that worktree state validation (~143 ms) must still execute to guarantee cache freshness.

### Behavioral Savings Claims

```
DISCOVERY_BYTES_AVOIDABLE = UNKNOWN
MODEL_TURN_SAVINGS = UNKNOWN
BEHAVIORAL_EQUIVALENCE = UNKNOWN
```

---

## 8. Failure Isolation & Safety

```
SHADOW_FAILURE_AGENT_PATH_UNCHANGED = PASS
```

Any exception during snapshot extraction, tokenization, ranking, map formatting, or ledger recording is caught inside `evaluate()`, returning `None`. The agent workflow continues without interruption.

---

## 9. Status of All Shadow Lanes

| Lane | Status |
| :--- | :--- |
| **Read Receipt Shadow (M07/M08)** | `READY_FOR_LIVE_CODEX_SHADOW` (frozen until Codex available) |
| **Reexposure Shadow (M06)** | `READY_FOR_LIVE_CODEX_SHADOW` (frozen until Codex available) |
| **Discovery Runtime Shadow (M11/M11-R1)** | **`DISCOVERY_READY_FOR_LIVE_CODEX_SHADOW`** |

---

## 10. Local Artifacts

Stored in `C:\Users\phped\.fiofilter\discovery-runtime-shadow\`:

| File | Status | Notes |
| :--- | :---: | :--- |
| `m11_self_shadow_prework_v1.json` | INVALIDATED | Prework contaminated; preserved as negative evidence |
| `m11_self_shadow_eval_v1.json` | SUPERSEDED | Overclaim removed; not counted as live evidence |
| `m11_synthetic_stream_v1.json` | VALID | 5 tasks (4/5 target hits, 5/5 execution pass) |
| `m11_summary_v1.json` | UPDATED | V2 metrics and semantic corrections recorded |
| `shadow_ledger.jsonl` | VALID | Append-only ledger with chained event hashes |

---

## 11. Final Verdict

```
M11_CANONICAL_VERDICT = M11_DISCOVERY_RUNTIME_SHADOW_PASS_LIVE_TARGET_READY
```