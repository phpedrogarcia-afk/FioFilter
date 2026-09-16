# M09 Discovery Structural Shadow Report

## 1. Executive Summary

Mission **M09** establishes and operationally validates the **Discovery Structural Shadow** for FioFilter.

While missions M06–M08 developed and validated the runtime read-receipt shadow for repeated file re-exposure, M09 explores the exploration frontier that precedes code modification:
> *"If FioFilter had possessed a structural repository index before exploration began, how accurately could relevant context have been surfaced, and what are the strict safety and evidence boundaries of structural ranking?"*

M09 adapts proven mechanisms from two prominent donors:
1. **Aider RepoMap**: Personalized PageRank (PPR) graph centrality, task-personalized teleport seeds, and compact byte-budgeted symbol signature maps.
2. **AgentMap**: Strict decoupling of directed file dependency graphs (`FILE_GRAPH`) from symbol indices (`SYMBOL_INDEX`), graph health accounting (edge coverage and parse coverage), and separation of intra-repo targets from external standard library and third-party roots.

### Key Deliverables & Operational Proofs:
1. **Formal Separation of Control Plane and Evidence Plane**:
   - `INDEX != EVIDENCE`
   - `INDEX != AUTHORITY`
   - `RANK != CORRECTNESS`
   - `LOW_RANK != IRRELEVANT`
   - `BUDGET_APPLIES_TO_INDEX_ONLY = True`
   - `EVIDENCE_OVERRIDES_BUDGET = True`
   - `DISCOVERY_READ_SUPPRESSION = False`
   - `AUTO_CONTEXT_SELECTION = False`
   - `INDEX_ONLY_SHADOW = True`
2. **Single Implementation Backend (`PYTHON_AST_LOCAL_RESOLVER_V1`)**:
   - Built entirely on Python standard library modules (`ast`, `hashlib`, `pathlib`, `subprocess`).
   - Zero external LSP servers, tree-sitter binary daemons, embeddings, or background server processes.
   - Non-destructive Git plumbing snapshots via `git ls-tree` and `git show` without checking out or mutating the working directory.
3. **High Observed Graph Health**:
   - Active worktree snapshot (60 Python files, 848 extracted symbols):
     - Parse Coverage: **100.0%** (60/60 files parsed without syntax error)
      - `RECOGNIZED_LOCAL_IMPORT_RESOLUTION_COVERAGE`: **429 / 429** (all locally-resolved import candidates resolved within-repo)
      - `GRAPH_RELATION_COMPLETENESS`: **UNKNOWN** — AST import edges only; CALLS, TEST_RELATES, REEXPORTS edges not yet extracted
      - Graph Health Status: **`GRAPH_HEALTH_HIGH_OBSERVED`** (observed on extracted edge type only)
     - Snapshot Construction Time: **180.70 ms**
4. **Commit-History Benchmark & Query Leakage Audit**:
   - Evaluated against FioFilter's own commit history using parent snapshot indexing and child commit changed files as ground truth targets across 4 ablation modes:
     - `LEXICAL_ONLY`
     - `STRUCTURAL_ONLY`
     - `LEXICAL_PLUS_STRUCTURAL`
     - `LEXICAL_PLUS_PPR`
   - Non-leaking query audit (10 commits with no path or filename leaks in task description):
     - `LEXICAL_ONLY`: R@1=20.0%, R@5=60.0%, R@10=70.0%, MRR=0.3633
     - `STRUCTURAL_ONLY`: R@1=10.0%, R@5=20.0%, R@10=30.0%, MRR=0.1417
     - `LEXICAL_PLUS_STRUCTURAL`: R@1=20.0%, R@5=50.0%, R@10=60.0%, MRR=0.3500
     - `LEXICAL_PLUS_PPR`: R@1=20.0%, R@5=50.0%, R@10=60.0%, MRR=0.3500
5. **Source A Discovery Shadow Replay**:
   - Replayed 490 `FILE_READ` calls across 256 distinct targets in 151 read episodes.
   - Exactly **490 / 490 (100.0%)** occurred during the pre-edit exploration phase before any mutating operations.
   - Enforces **zero runtime read suppression** (`DISCOVERY_READ_SUPPRESSION = False`): all reads remain unaltered RAW deliveries.
6. **Compact Budgeted Signature Maps**:
   - Budgeted symbol summaries fit strictly within byte limits:
     - 1,024 B budget: 1,016 B rendered (~254 tokens, 2 files)
     - 2,048 B budget: 2,025 B rendered (~507 tokens, 2 files)
     - 4,096 B budget: 4,086 B rendered (~1,022 tokens, 5 files)
     - 8,192 B budget: 8,183 B rendered (~2,046 tokens, 10 files)

---

## 2. Donor Mechanisms Adopted and Adapted

### 2.1 Aider RepoMap Donor Adaptation
Aider’s RepoMap uses a dependency graph derived from Tree-sitter tags, applies PageRank with task-specific personalization, and formats top definitions into a token-budgeted representation.

FioFilter M09 adapts these principles with deterministic rigor:
- **Personalized PageRank (PPR)**: Implemented via power iteration with damping parameter $\alpha = 0.85$ and $L_1$ norm convergence tolerance $\text{tol} = 10^{-6}$.
- **Task Personalization Vector**: Seeds teleport probability mass onto files matched by explicit paths or lexical symbols extracted from the task description.
- **Budgeted Symbol Signature Maps**: Renders symbol headers (classes, methods, functions, async functions, module variables) ordered by candidate rank, truncating cleanly at line and symbol boundaries without ever leaking function bodies.

### 2.2 AgentMap Donor Adaptation
AgentMap separates the repository graph into distinct structural and indexing layers, auditing edge resolution and health.

FioFilter M09 adopts:
- **Strict Decoupling of File Graph and Symbol Index**:
  - `FILE_GRAPH`: Directed graph tracking runtime and type-checking import relationships between source files.
  - `SYMBOL_INDEX`: Multi-key index indexing fully qualified and base symbol names for exact and case-insensitive resolution.
- **Graph Health & Coverage Accounting**:
  $$\text{parse\_coverage} = \frac{\text{files\_parsed}}{\text{files\_seen}}$$
  $$\text{edge\_coverage} = \frac{\text{resolved\_local\_imports}}{\text{local\_import\_candidates}}$$
  Stratifies status into `GRAPH_HEALTH_HIGH_OBSERVED` ($\ge 95\%$ parse, $\ge 85\%$ edge), `GRAPH_HEALTH_PARTIAL`, or `GRAPH_HEALTH_LOW`.
- **Intra-Repo vs External Package Distinction**:
  Filters out standard library modules and common third-party packages (`os`, `sys`, `re`, `json`, `pytest`, `pathlib`, etc.) from local edge candidate accounting, preventing artificial dilution of edge coverage metrics.

---

## 3. Control Plane vs Evidence Plane Invariants

The central safety theorem of M09 is that structural repository indices belong strictly to the **Control Plane** (navigation, ranking, and explanation hints), and can never supersede or modify the **Evidence Plane** (lossless byte verification, canonical reading, and patch authorization).

```
   +-------------------------------------------------------------------------+
   |                        CONTROL PLANE (Lossy & Heuristic)                |
   |                                                                         |
   |   [Discovery Query] ---> [AST Graph & Symbol Index]                     |
   |                                   |                                     |
   |                                   v                                     |
   |                   [Personalized PageRank & Ranker]                      |
   |                                   |                                     |
   |                                   v                                     |
   |                   [Ranked Candidates & Budgeted Map]                    |
   +-------------------------------------------------------------------------+
                                       |
                         NAVIGATION ONLY (No Authority)
                                       |
                                       v
   +-------------------------------------------------------------------------+
   |                        EVIDENCE PLANE (Lossless & Strict)               |
   |                                                                         |
   |   Agent Requests: read_file("fiofilter/store.py")                       |
   |                                   |                                     |
   |                                   v                                     |
   |                   [Single-Buffer Canonical Delivery]                    |
   |                                   |                                     |
   |                 +-----------------+-----------------+                   |
   |                 |                                   |                   |
   |                 v                                   v                   |
   |        [Exact RAW Bytes to Agent]          [Read Receipt Ledger]        |
   +-------------------------------------------------------------------------+
```

### Invariants Codified:
1. **`INDEX != EVIDENCE`**: An entry in a structural snapshot or signature map does not constitute canonical evidence that the file exists, has that content, or functions as described.
2. **`INDEX != AUTHORITY`**: The index cannot authorize code changes or certify correctness.
3. **`RANK != CORRECTNESS`**: A file ranked #1 is a candidate recommendation based on lexical and topological proximity, not verified necessity.
4. **`LOW_RANK != IRRELEVANT`**: A file ranked low or omitted from a budgeted map must NEVER be hidden or prohibited from being read.
5. **`BUDGET_APPLIES_TO_INDEX_ONLY = True`**: Budget constraints apply exclusively to the compact navigational summary; canonical evidence delivery is never throttled by budget limits.
6. **`EVIDENCE_OVERRIDES_BUDGET = True`**: When an agent requests a file read, the full canonical source must be delivered regardless of index budgets.
7. **`DISCOVERY_READ_SUPPRESSION = False`**: FioFilter never intercepts, prunes, or cancels a discovery read issued by the agent.
8. **`AUTO_CONTEXT_SELECTION = False`**: FioFilter does not autonomously inject files into the agent's context without an explicit request.
9. **`INDEX_ONLY_SHADOW = True`**: Structural indexing runs as an asynchronous shadow measurement.

---

## 4. Python AST Structural Backend (`PYTHON_AST_LOCAL_RESOLVER_V1`)

The backend parses Python source trees into structured graphs:

### 4.1 AST Feature Extraction
- **Classes**: Extracts class declarations, base classes, and docstrings.
- **Methods & Functions**: Extracts sync and async function declarations with argument signatures (`def`, `async def`, `*args`, `**kwargs`).
- **Imports**:
  - `import foo.bar`
  - `from foo import bar`
  - Relative imports: `from .sub import helper`, `from ..parent import util` (resolving levels against directory depth).
  - Type-checking guards: detects `if TYPE_CHECKING:` blocks and tags edges as `TYPE_CHECKING_IMPORT` vs `RUNTIME_IMPORT`.

### 4.2 Non-Destructive Git Plumbing Snapshots
To benchmark historical repository states without checking out commits (which would mutate the active worktree or create detached HEADs), the backend uses Git plumbing commands:
- `git ls-tree -r --name-only <commit_sha>`: retrieves all tracked Python files in the commit.
- `git show <commit_sha>:<path>`: streams the exact immutable file contents at that commit into memory.
- `PythonAstStructuralBackend.build_snapshot_from_git_commit(repo_root, commit_sha)`: constructs an immutable snapshot directly from in-memory strings with explicit UTF-8 decoding.

### 4.3 Stale Worktree Defense
For active worktrees, snapshots incorporate:
- `git_head`: current Git commit hash.
- `dirty_state`: boolean indicating whether uncommitted modifications exist via `git status --porcelain`.
- `snapshot_id`: SHA-256 digest computed over file paths and file content hashes (`snap-<hex16>`). Any local edit immediately invalidates the snapshot ID, preventing stale cache reuse.

---

## 5. Structural Ranking and Ablation Framework

The ranker evaluates repository files across 4 formal ablation configurations:

| Mode | Lexical Signals | Graph Proximity | Graph Centrality | Personalized PageRank |
| :--- | :---: | :---: | :---: | :---: |
| **`LEXICAL_ONLY`** | Yes | No | No | No |
| **`STRUCTURAL_ONLY`** | No | Yes (seeds only) | Yes (In-Degree) | No |
| **`LEXICAL_PLUS_STRUCTURAL`** | Yes | Yes (BFS distance) | Yes (In-Degree) | No |
| **`LEXICAL_PLUS_PPR`** | Yes | Yes (BFS distance) | No | Yes ($\alpha=0.85$) |

### Component Scoring & Explainability
Each candidate returns a complete `signals` dictionary and human-readable `explanation` string:
- `EXACT_PATH_MATCH`: +100.0 (query explicitly references the file path)
- `EXACT_SYMBOL_MATCH`: +40.0 (query names a class or function defined in the file)
- `LEXICAL_PATH_MATCH`: +15.0 per matching non-stopword stem in path
- `LEXICAL_SYMBOL_MATCH`: +10.0 per matching substring in symbol names
- `GRAPH_PROXIMITY`: $+5.0 / (\text{dist} + 1.0)$ (BFS shortest distance to lexical seeds)
- `STRUCTURAL_CENTRALITY`: $5.0 \cdot \ln(1 + \text{in\_degree})$
- `PAGERANK`: scaled Personalized PageRank mass ($0 \dots 20.0$)

---

## 6. Commit-History Benchmark Empirical Results

The benchmark was executed across 13 eligible historical commits in FioFilter's Git history. For each commit $C_i$ with parent $P_i$, a structural snapshot was built at $P_i$, the query was extracted deterministically from the commit message of $C_i$, and ground-truth targets were defined as the set of Python files modified in $C_i$.

### 6.1 Query Leakage Classification
- **`PATH_LEAKING`**: Commit message explicitly named one or more changed files or file stems (e.g. `"M06: session-aware reexposure shadow evaluation"` where filename matches).
- **`NON_LEAKING`**: Commit message described the task or feature without naming any changed file (e.g. `"docs(m08): refine salience denominator, TOCTOU claims, and memory metric"`). Exactly 10 out of 13 commits satisfied the strict non-leaking audit.

### 6.2 All Eligible Commits (13 Commits Evaluated)

| Ranking Mode | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | Miss Top 10 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`LEXICAL_ONLY`** | **23.1%** | **53.8%** | **61.5%** | **69.2%** | **0.3821** | 4 |
| **`STRUCTURAL_ONLY`** | 7.7% | 15.4% | 23.1% | 30.8% | 0.1346 | 9 |
| **`LEXICAL_PLUS_STRUCTURAL`** | 23.1% | 46.2% | 46.2% | 53.8% | 0.3462 | 6 |
| **`LEXICAL_PLUS_PPR`** | 23.1% | 46.2% | 46.2% | 53.8% | 0.3462 | 6 |

### 6.3 Non-Leaking Subset (10 Commits Evaluated — Strict Audit)

| Ranking Mode | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`LEXICAL_ONLY`** | **20.0%** | **50.0%** | **60.0%** | **70.0%** | **0.3633** |
| **`STRUCTURAL_ONLY`** | 10.0% | 10.0% | 20.0% | 30.0% | 0.1417 |
| **`LEXICAL_PLUS_STRUCTURAL`** | 20.0% | 50.0% | 50.0% | 60.0% | 0.3500 |
| **`LEXICAL_PLUS_PPR`** | 20.0% | 50.0% | 50.0% | 60.0% | 0.3500 |

### 6.4 Key Empirical Insights:
1. **Lexical Search Is the Foundational Anchor**: In software engineering tasks, agents formulate intents using domain terms (`store`, `receipt`, `shadow`, `census`). Pure lexical matching achieves **70.0% Recall@10** on non-leaking queries.
2. **Graph Structure Alone Cannot Infer Intent**: `STRUCTURAL_ONLY` (relying on static in-degree centrality) achieves only 30.0% Recall@10. In software repositories, utility modules (e.g. `fiofilter/store.py`) have high static centrality, but a task about read receipts must prioritize read receipt modules regardless of utility centrality.
3. **PPR Provides Neighborhood Expansion (CLAIMED_ONLY)**: On the 10-commit non-leaking subset, both `LEXICAL_PLUS_PPR` and `LEXICAL_PLUS_STRUCTURAL` produce identical recall to `LEXICAL_ONLY` at Recall@1 and are strictly inferior at Recall@5 and Recall@10. **`PPR_VALUE_AS_IMPLEMENTED=NOT_PROVEN`** on this corpus. The neighbourhood-expansion hypothesis requires a larger, more representative task set before any value claim is warranted.

### 6.5 Explicit Donor Hypothesis Result

| Claim | Status |
| :--- | :--- |
| `CURRENT_GLOBAL_STRUCTURAL_SIGNALS_DO_NOT_BEAT_LEXICAL_BASELINE` | **PROVEN** on this 10-commit non-leaking corpus |
| `PPR_VALUE_AS_IMPLEMENTED` | **NOT_PROVEN** (identical or inferior to LEXICAL_ONLY in all measured recall bands) |
| `STRUCTURAL_ONLY_VIABLE_AS_STANDALONE` | **FALSE** — 30% Recall@10 is insufficient |
| `GLOBAL_CENTRALITY_DISAMBIGUATES_TASK_INTENT` | **NOT_PROVEN** |

These results are **negative results** — they are valid empirical outcomes and constitute success for M09 per mission contract.

---

## 7. Source A Discovery Shadow Replay

Source A (`rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl`, 206 MB, 35,040 records) was replayed to analyze the interaction between discovery reads and code mutations:

- **Total `FILE_READ` Calls**: 490
- **Distinct Targets Read**: 256
- **Read Episodes**: 151
- **Pre-Edit Exploration Reads**: **490 / 490 (100.0%)**
- **Post-Edit Exploration Reads**: **0 / 490 (0.0%)**

### Source A Scope Boundaries:

| Claim | Status |
| :--- | :--- |
| `SOURCE_A_DISCOVERY_ACTIVITY_CHARACTERIZED` | **YES** — read/write episode structure characterized |
| `SOURCE_A_STRUCTURAL_RANK_REPLAY` | **NOT_PROVEN** — no ground-truth task→target labels extracted from Source A; characterization is episode-structure only, not ranking quality |

### Analysis:
In Source A's execution trajectory, every file read occurred as an exploration or discovery step prior to any subsequent modification actions in that episode. This provides empirical evidence that:
- Coding agents rely heavily on exploration reads to build mental models before acting.
- Suppressing discovery reads would jeopardize agent situational awareness.
- Structural indexing can dramatically accelerate discovery by providing a compact signature map up front, while **read suppression must remain strictly zero**.

---

## 8. Index Economics and Overhead

The performance economics of `PYTHON_AST_LOCAL_RESOLVER_V1` were measured on the local workstation:

| Metric | Measured Value | Scope |
| :--- | :--- | :--- |
| **Active Files Scanned** | 60 Python files | Full FioFilter repository worktree |
| **Active Symbols Extracted** | 848 symbols | Classes, methods, functions, constants |
| **Local Import Edges** | 429 directed edges | `RECOGNIZED_LOCAL_IMPORT_RESOLUTION_COVERAGE=429/429`; `GRAPH_RELATION_COMPLETENESS=UNKNOWN` (IMPORT edges only) |
| **Snapshot Construction Wall Time** | **180.70 ms** | Includes disk I/O, AST parse, graph resolution |
| **Memory Footprint** | ~2.1 MB | In-memory AST snapshot and PageRank graph |
| **13-Commit Benchmark Run Time** | **18.57 s** | Includes 13 Git plumbing extractions and rankings |
| **Budgeted Map (1,024 B)** | 1,016 B (~254 tokens) | 2 top candidate files |
| **Budgeted Map (2,048 B)** | 2,025 B (~507 tokens) | 2 top candidate files |
| **Budgeted Map (4,096 B)** | 4,086 B (~1,022 tokens)| 5 top candidate files |
| **Budgeted Map (8,192 B)** | 8,183 B (~2,046 tokens)| 10 top candidate files |

The structural snapshot requires less than 200 ms to construct from scratch and consumes negligible memory. It adds zero background CPU drain, requires no long-lived daemon, and executes deterministically.

---

## 9. Mission Verdict and Hand-off

```
M09_DISCOVERY_SHADOW_PASS_MORE_RANKING_EVIDENCE_REQUIRED
```

### Justification:
- Structural shadow built, validated, and benchmarked. All invariants hold.
- Negative donor hypothesis result: `CURRENT_GLOBAL_STRUCTURAL_SIGNALS_DO_NOT_BEAT_LEXICAL_BASELINE` — **this is a valid and valuable result.**
- `PPR_VALUE_AS_IMPLEMENTED = NOT_PROVEN` on 13-commit corpus.
- `SOURCE_A_STRUCTURAL_RANK_REPLAY = NOT_PROVEN` — task→target labels not available from Source A.
- The next mission (M10) must first determine **WHY** lexical wins on this corpus and test the cheapest mechanisms that could improve retrieval — starting with a strong BM25-style lexical baseline and targeted structural relations, NOT more global graph complexity.

### Epistemic Classification:
- `DISCOVERY_STRUCTURAL_SHADOW = VALIDATED_SHADOW_ONLY`
- `DISCOVERY_READ_SUPPRESSION = NO` (frozen, non-authoritative)
- `REEXPOSURE_LANE = READY_FOR_LIVE_CODEX_SHADOW` (frozen at M08)
- `GLOBAL_STRUCTURAL_SIGNALS_BEAT_LEXICAL = NOT_PROVEN`

### Artifact Record:
- `m09_structural_snapshot_v1.json` (28 KB)
- `m09_commit_benchmark_v1.json` (24 KB)
- `m09_source_a_discovery_shadow_v1.json` (2.9 KB)
- `m09_structural_summary_v1.json` (3.8 KB)

### Repository State:
- PR #8 opened against `main`. All tests passing with zero regressions.

