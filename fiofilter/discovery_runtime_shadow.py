"""
fiofilter/discovery_runtime_shadow.py
M11-R1: Lexical-first discovery runtime shadow harness with content-sensitive
worktree fingerprinting (V2).

DiscoveryRuntimeShadow provides a shadow navigation mechanism using BM25_LEXICAL.
It does NOT inject context, suppress reads, block grep, replace source evidence,
install hooks, or modify any runtime.

Authority invariants:
  INDEX_AUTHORITY=NAVIGATION_ONLY
  DISCOVERY_READ_SUPPRESSION=NO
  AUTO_CONTEXT_SELECTION=NO
  SHADOW_FAILURE_AGENT_PATH_UNCHANGED=PASS
  WORKTREE_STATUS_IS_NOT_CONTENT_IDENTITY
  CACHE_HIT_MUST_BE_PROVEN
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from fiofilter.discovery_lexical import (
    BM25Index,
    _BM25_K1,
    _BM25_B,
    build_bm25_index_from_paths,
    tokenize_v2,
)
from fiofilter.structural_python import (
    DEFAULT_EXCLUDE_PARTS,
    PythonAstStructuralBackend,
)


# ---------------------------------------------------------------------------
# Version constants (frozen for M11-V1 / M11-R1)
# ---------------------------------------------------------------------------

M11_TOKENIZER_VERSION = "V2"
M11_BM25_VERSION = "BM25_STYLE_LEXICAL_V1"
M11_K1 = _BM25_K1   # 1.2
M11_B = _BM25_B     # 0.75
M11_INDEXED_FIELDS = ("PATH", "SYMBOL_NAMES")
M11_TIE_BREAK_POLICY = "SCORE_DESC_PATH_ASC"
M11_INDEX_AUTHORITY = "NAVIGATION_ONLY"
INDEXED_FILE_UNIVERSE_POLICY = "PYTHON_SOURCES_V1"


# ---------------------------------------------------------------------------
# Provenance and Content-Sensitive Fingerprinting (V2)
# ---------------------------------------------------------------------------

def _get_head_sha(repo_root: pathlib.Path) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=repo_root,
    )
    return r.stdout.strip() if r.returncode == 0 else "UNKNOWN"


def _get_dirty_digest(repo_root: pathlib.Path) -> str:
    """
    Hash of the git status output. Retained as status metadata only.
    INVARIANT: WORKTREE_STATUS_IS_NOT_CONTENT_IDENTITY.
    """
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=repo_root,
    )
    status = r.stdout.strip() if r.returncode == 0 else ""
    return hashlib.sha256(status.encode()).hexdigest()[:16]


def get_worktree_state_digest_v2(
    repo_root: pathlib.Path,
    exclude_parts: Optional[Set[str]] = None,
) -> str:
    """
    Content-sensitive worktree fingerprint (WORKTREE_STATE_DIGEST_V2).

    Binds directly to:
    1. HEAD commit SHA
    2. Tracked worktree delta content (git diff --binary HEAD for *.py)
    3. Untracked relevant *.py files sorted by path with exact byte hashes

    Properties:
    - Same content -> same digest
    - Tracked change (staged, unstaged, or double-mutated) -> digest changes
    - Untracked change (same '??' status but different content) -> digest changes
    - File addition, deletion, rename -> digest changes
    - Touch / mtime rewrite of identical content -> digest remains identical
    - Irrelevant file change (e.g. README.md, .txt) -> digest remains identical
    """
    root = repo_root.resolve()
    excludes = exclude_parts if exclude_parts is not None else DEFAULT_EXCLUDE_PARTS

    # 1. HEAD sha
    head_sha = _get_head_sha(root)

    # 2. Tracked diff against HEAD for *.py files
    r_diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD", "--", "*.py"],
        cwd=root,
        capture_output=True,
    )
    diff_bytes = r_diff.stdout if r_diff.returncode == 0 else b""

    # 3. Untracked relevant *.py files
    r_untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "*.py"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    untracked_lines: List[str] = []
    if r_untracked.returncode == 0:
        raw_paths = [
            p.strip().replace("\\", "/")
            for p in r_untracked.stdout.strip().split("\n")
            if p.strip()
        ]
        for rel in sorted(raw_paths):
            parts = set(rel.split("/"))
            if parts.intersection(excludes):
                continue
            full = root / rel
            if full.exists() and full.is_file():
                try:
                    file_hash = hashlib.sha256(full.read_bytes()).hexdigest()
                    untracked_lines.append(f"{rel}:{file_hash}")
                except Exception:
                    pass

    hasher = hashlib.sha256()
    hasher.update(b"WORKTREE_STATE_V2:")
    hasher.update(head_sha.encode("utf-8"))
    hasher.update(b"\nDIFF:")
    hasher.update(diff_bytes)
    hasher.update(b"\nUNTRACKED:")
    hasher.update("\n".join(untracked_lines).encode("utf-8"))
    return hasher.hexdigest()[:16]


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def _snapshot_id(head_sha: str, worktree_state_digest: str, indexed_files_hash: str) -> str:
    combined = f"{head_sha}:{worktree_state_digest}:{indexed_files_hash}"
    return hashlib.sha256(combined.encode()).hexdigest()[:16]


def _files_hash(file_paths: List[str]) -> str:
    """Deterministic hash over the sorted list of indexed file paths."""
    canon = sorted(file_paths)
    return hashlib.sha256("\n".join(canon).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CandidateResult:
    """A single ranked navigation candidate."""
    rank: int
    path: str
    score: float
    matched_tokens: List[str]


@dataclass
class ShadowEvaluation:
    """
    Result of a single DiscoveryRuntimeShadow.evaluate() call.
    Contains metadata only — no file contents beyond compact index declarations.
    """
    # Provenance
    repo_root: str
    head_sha: str
    dirty_digest: str             # git status metadata (not content identity)
    worktree_state_digest: str    # V2 content-sensitive digest
    snapshot_id: str
    query_hash: str
    file_universe_policy: str

    # Ranker version binding (auditable)
    tokenizer_version: str
    bm25_version: str
    k1: float
    b: float
    indexed_fields: Tuple[str, ...]
    tie_break_policy: str
    index_authority: str

    # Results
    candidates: List[CandidateResult]
    map_bytes: int
    map_content: str  # compact index map (paths + scores, no file contents)

    # Cost metrics
    state_validation_ms: float
    snapshot_build_ms: float
    index_build_ms: float
    query_tokenize_ms: float
    ranking_ms: float
    map_render_ms: float
    total_ms: float
    is_warm: bool
    query_type: str  # "COLD_EVALUATION" or "INDEX_REUSE_QUERY"

    # Index health
    files_indexed: int
    candidate_count: int
    estimated_map_tokens: int  # bytes / 4 only

    # Determinism
    evaluation_hash: str  # SHA256 of canonical result (snapshot_id + query_hash + top-k paths)

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items()}
        d["candidates"] = [c.__dict__ for c in self.candidates]
        d["indexed_fields"] = list(self.indexed_fields)
        return d


# ---------------------------------------------------------------------------
# Snapshot cache (process-local, warm reuse)
# ---------------------------------------------------------------------------

@dataclass
class _CachedSnapshot:
    cache_key: Tuple[str, str, str, str, str]  # (repo_root, head_sha, worktree_state_digest, bm25_version, universe_policy)
    snapshot_id: str
    file_paths: List[str]
    symbol_names_by_path: Dict[str, List[str]]
    bm25_index: BM25Index
    build_ms: float


# ---------------------------------------------------------------------------
# Main shadow class
# ---------------------------------------------------------------------------

class DiscoveryRuntimeShadow:
    """
    Lexical-first discovery runtime shadow with V2 content-sensitive state.

    Evaluates repository file navigation candidates using BM25_LEXICAL.
    Returns metadata only. Never modifies agent behavior.

    AUTHORITY: NAVIGATION_ONLY
    """

    def __init__(
        self,
        ledger_dir: Optional[pathlib.Path] = None,
        snapshot_mode: str = "WORKTREE",
    ):
        """
        ledger_dir: path for append-only local shadow ledger (no raw query text)
        snapshot_mode: "WORKTREE" (current HEAD + worktree), "HEAD_ONLY" (pure HEAD)
        """
        self._ledger_dir = ledger_dir
        self._snapshot_mode = snapshot_mode
        self._cache: Optional[_CachedSnapshot] = None
        self._backend = PythonAstStructuralBackend()

    def evaluate(
        self,
        repo_root: pathlib.Path,
        task_query: str,
        top_k: int = 10,
        map_budget_bytes: int = 2048,
    ) -> Optional[ShadowEvaluation]:
        """
        Shadow evaluate: produce ranked navigation candidates for task_query.

        Returns ShadowEvaluation (metadata only), or None if shadow fails.
        Failure does NOT affect any agent workflow (SHADOW_FAILURE_AGENT_PATH_UNCHANGED=PASS).
        """
        try:
            return self._evaluate_inner(repo_root, task_query, top_k, map_budget_bytes)
        except Exception:
            # Shadow failure: return None, never propagate to caller
            return None

    def _evaluate_inner(
        self,
        repo_root: pathlib.Path,
        task_query: str,
        top_k: int,
        map_budget_bytes: int,
    ) -> ShadowEvaluation:
        t_total_start = time.monotonic()

        # Provenance: State Validation
        t_state_start = time.monotonic()
        head_sha = _get_head_sha(repo_root)
        dirty_digest = _get_dirty_digest(repo_root)
        worktree_state_digest = get_worktree_state_digest_v2(repo_root)
        t_state_ms = (time.monotonic() - t_state_start) * 1000

        # Exact cache key: (repo_path, head_sha, worktree_state_digest, version, policy)
        cache_key = (
            str(repo_root.resolve()),
            head_sha,
            worktree_state_digest,
            M11_BM25_VERSION,
            INDEXED_FILE_UNIVERSE_POLICY,
        )

        # Cache hit assertion: CACHE_HIT_MUST_BE_PROVEN
        is_warm = False
        if self._cache is not None and self._cache.cache_key == cache_key:
            index = self._cache.bm25_index
            sym_by_file = self._cache.symbol_names_by_path
            file_paths = self._cache.file_paths
            sid = self._cache.snapshot_id
            t_snap_ms = 0.0
            t_index_ms = 0.0
            is_warm = True
            query_type = "INDEX_REUSE_QUERY"
        else:
            # Rebuild snapshot and index from worktree
            t_snap_start = time.monotonic()
            snapshot = self._backend.build_snapshot_from_worktree(repo_root)
            all_files = sorted(snapshot.file_graph.nodes)  # sorted for determinism
            files_hash = _files_hash(all_files)
            sid = _snapshot_id(head_sha, worktree_state_digest, files_hash)
            t_snap_ms = (time.monotonic() - t_snap_start) * 1000

            # Build symbol map
            sym_by_file: Dict[str, List[str]] = {}
            for f in all_files:
                sym_by_file[f] = [
                    s.qualified_name.split(".")[-1]
                    for s in snapshot.symbol_index.symbols_in_file(f)
                ]

            # Build BM25 index
            t_idx_start = time.monotonic()
            index = build_bm25_index_from_paths(all_files, sym_by_file)
            t_index_ms = (time.monotonic() - t_idx_start) * 1000

            # Cache with V2 content key
            self._cache = _CachedSnapshot(
                cache_key=cache_key,
                snapshot_id=sid,
                file_paths=all_files,
                symbol_names_by_path=sym_by_file,
                bm25_index=index,
                build_ms=t_index_ms,
            )
            file_paths = all_files
            query_type = "COLD_EVALUATION"

        # --- Query tokenization ---
        t_tok_start = time.monotonic()
        query_toks = tokenize_v2(task_query)
        t_tok_ms = (time.monotonic() - t_tok_start) * 1000
        qhash = _query_hash(task_query)

        # --- Ranking ---
        t_rank_start = time.monotonic()
        ranked = index.rank(query_toks, top_k=top_k)
        t_rank_ms = (time.monotonic() - t_rank_start) * 1000

        # --- Candidates ---
        candidates: List[CandidateResult] = []
        for i, (path, score) in enumerate(ranked):
            # Identify matched tokens for explanation
            doc = next((d for d in index.documents if d.path == path), None)
            matched = [t for t in query_toks if doc and doc.token_counts.get(t, 0) > 0]
            candidates.append(
                CandidateResult(
                    rank=i + 1,
                    path=path,
                    score=round(score, 6),
                    matched_tokens=matched,
                )
            )

        # --- Map rendering ---
        t_map_start = time.monotonic()
        map_lines = [f"# Discovery shadow — {head_sha[:8]} | query:{qhash}"]
        map_lines.append(f"# tokenizer:{M11_TOKENIZER_VERSION} bm25:{M11_BM25_VERSION} k1={M11_K1} b={M11_B}")
        map_lines.append(f"# tie_break:{M11_TIE_BREAK_POLICY} authority:{M11_INDEX_AUTHORITY}")
        map_lines.append(f"# digest_v2:{worktree_state_digest} query_type:{query_type}")
        map_lines.append("")
        for c in candidates:
            line = f"[{c.rank:02d}] {c.path} (score={c.score:.4f} tokens={c.matched_tokens})"
            map_lines.append(line)
            if sum(len(l) + 1 for l in map_lines) >= map_budget_bytes:
                map_lines.append(f"# ... truncated to {map_budget_bytes}B budget")
                break
        map_content = "\n".join(map_lines)
        map_bytes_actual = len(map_content.encode("utf-8"))
        t_map_ms = (time.monotonic() - t_map_start) * 1000

        total_ms = (time.monotonic() - t_total_start) * 1000

        # --- Evaluation hash (determinism token) ---
        canon = sid + ":" + qhash + ":" + ":".join(c.path for c in candidates)
        eval_hash = hashlib.sha256(canon.encode()).hexdigest()[:16]

        result = ShadowEvaluation(
            repo_root=str(repo_root),
            head_sha=head_sha,
            dirty_digest=dirty_digest,
            worktree_state_digest=worktree_state_digest,
            snapshot_id=sid,
            query_hash=qhash,
            file_universe_policy=INDEXED_FILE_UNIVERSE_POLICY,
            tokenizer_version=M11_TOKENIZER_VERSION,
            bm25_version=M11_BM25_VERSION,
            k1=M11_K1,
            b=M11_B,
            indexed_fields=M11_INDEXED_FIELDS,
            tie_break_policy=M11_TIE_BREAK_POLICY,
            index_authority=M11_INDEX_AUTHORITY,
            candidates=candidates,
            map_bytes=map_bytes_actual,
            map_content=map_content,
            state_validation_ms=round(t_state_ms, 2),
            snapshot_build_ms=round(t_snap_ms, 2),
            index_build_ms=round(t_index_ms, 2),
            query_tokenize_ms=round(t_tok_ms, 4),
            ranking_ms=round(t_rank_ms, 4),
            map_render_ms=round(t_map_ms, 4),
            total_ms=round(total_ms, 2),
            is_warm=is_warm,
            query_type=query_type,
            files_indexed=len(file_paths),
            candidate_count=len(candidates),
            estimated_map_tokens=map_bytes_actual // 4,
            evaluation_hash=eval_hash,
        )

        # --- Ledger ---
        if self._ledger_dir is not None:
            self._append_ledger(result)

        return result

    def _append_ledger(self, result: ShadowEvaluation) -> None:
        """Append event to local ledger. No raw query text stored."""
        try:
            self._ledger_dir.mkdir(parents=True, exist_ok=True)
            ledger_path = self._ledger_dir / "shadow_ledger.jsonl"
            # Load previous hash for chaining
            prev_hash = "GENESIS"
            if ledger_path.exists():
                lines = ledger_path.read_text(encoding="utf-8").strip().split("\n")
                if lines:
                    try:
                        last = json.loads(lines[-1])
                        prev_hash = last.get("event_hash", "GENESIS")
                    except Exception:
                        pass
            event = {
                "event_id": f"m11-{int(time.time())}-{result.evaluation_hash}",
                "snapshot_id": result.snapshot_id,
                "query_hash": result.query_hash,
                "worktree_state_digest": result.worktree_state_digest,
                "ranker_version": result.bm25_version,
                "tokenizer_version": result.tokenizer_version,
                "k1": result.k1,
                "b": result.b,
                "tie_break_policy": result.tie_break_policy,
                "query_type": result.query_type,
                "candidate_paths": [c.path for c in result.candidates],
                "scores": [c.score for c in result.candidates],
                "map_size_bytes": result.map_bytes,
                "state_validation_ms": result.state_validation_ms,
                "snapshot_build_ms": result.snapshot_build_ms,
                "index_build_ms": result.index_build_ms,
                "ranking_ms": result.ranking_ms,
                "total_ms": result.total_ms,
                "is_warm": result.is_warm,
                "evaluation_hash": result.evaluation_hash,
                "previous_event_hash": prev_hash,
                "event_hash": hashlib.sha256(
                    (prev_hash + result.evaluation_hash).encode()
                ).hexdigest()[:16],
            }
            with open(ledger_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception:
            pass  # Ledger write failure never propagates


# ---------------------------------------------------------------------------
# Synthetic task stream
# ---------------------------------------------------------------------------

SYNTHETIC_TASK_STREAM = [
    {
        "task_id": "SYN-001",
        "query": "update read receipt freshness check",
        "known_positives": ["fiofilter/read_receipt.py"],
        "description": "Read receipt freshness logic update",
    },
    {
        "task_id": "SYN-002",
        "query": "change runtime shadow checkpoint stream",
        "known_positives": ["fiofilter/runtime_shadow.py"],
        "description": "Runtime shadow harness checkpoint",
    },
    {
        "task_id": "SYN-003",
        "query": "modify context waste census accounting",
        "known_positives": ["fiofilter/context_census.py"],
        "description": "Census waste accounting logic",
    },
    {
        "task_id": "SYN-004",
        "query": "adjust search grammar grouping transform",
        "known_positives": ["fiofilter/store.py"],
        "description": "Grammar grouping transform (T02)",
    },
    {
        "task_id": "SYN-005",
        "query": "session reexposure shadow evaluation",
        "known_positives": ["fiofilter/reexposure.py"],
        "description": "Session-aware reexposure evaluation",
    },
]


def run_synthetic_task_stream(
    shadow: DiscoveryRuntimeShadow,
    repo_root: pathlib.Path,
    top_k: int = 10,
) -> List[dict]:
    """Run all synthetic tasks and return evaluation results."""
    results = []
    for task in SYNTHETIC_TASK_STREAM:
        ev = shadow.evaluate(repo_root, task["query"], top_k=top_k)
        if ev is None:
            results.append({
                "task_id": task["task_id"],
                "status": "SHADOW_FAILED",
                "known_positives": task["known_positives"],
            })
            continue
        ranked_paths = [c.path for c in ev.candidates]
        # Compute recall metrics against known positives
        gt = task["known_positives"]
        gt_basenames = {pathlib.Path(g).name for g in gt}

        def recall_at(k):
            top = set(ranked_paths[:k])
            top_names = {pathlib.Path(p).name for p in top}
            hits = sum(1 for g in gt_basenames if g in top_names or any(g in p for p in top))
            return hits / len(gt) if gt else 0.0

        results.append({
            "task_id": task["task_id"],
            "status": "OK",
            "query_hash": ev.query_hash,
            "snapshot_id": ev.snapshot_id,
            "worktree_state_digest": ev.worktree_state_digest,
            "evaluation_hash": ev.evaluation_hash,
            "known_positives": task["known_positives"],
            "R@1": recall_at(1),
            "R@3": recall_at(3),
            "R@5": recall_at(5),
            "R@10": recall_at(10),
            "top5_paths": ranked_paths[:5],
            "total_ms": ev.total_ms,
            "state_validation_ms": ev.state_validation_ms,
            "is_warm": ev.is_warm,
            "query_type": ev.query_type,
            "map_bytes": ev.map_bytes,
            "estimated_map_tokens": ev.estimated_map_tokens,
        })
    return results
