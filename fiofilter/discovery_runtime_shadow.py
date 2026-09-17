"""
fiofilter/discovery_runtime_shadow.py
M11: Lexical-first discovery runtime shadow harness.

DiscoveryRuntimeShadow provides a shadow navigation mechanism using BM25_LEXICAL.
It does NOT inject context, suppress reads, block grep, replace source evidence,
install hooks, or modify any runtime.

Authority invariants:
  INDEX_AUTHORITY=NAVIGATION_ONLY
  DISCOVERY_READ_SUPPRESSION=NO
  AUTO_CONTEXT_SELECTION=NO
  SHADOW_FAILURE_AGENT_PATH_UNCHANGED=PASS
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from fiofilter.discovery_lexical import (
    BM25Index,
    _BM25_K1,
    _BM25_B,
    build_bm25_index_from_paths,
    tokenize_v2,
)
from fiofilter.structural_python import PythonAstStructuralBackend


# ---------------------------------------------------------------------------
# Version constants (frozen for M11-V1)
# ---------------------------------------------------------------------------

M11_TOKENIZER_VERSION = "V2"
M11_BM25_VERSION = "BM25_STYLE_LEXICAL_V1"
M11_K1 = _BM25_K1   # 1.2
M11_B = _BM25_B     # 0.75
M11_INDEXED_FIELDS = ("PATH", "SYMBOL_NAMES")
M11_TIE_BREAK_POLICY = "SCORE_DESC_PATH_ASC"
M11_INDEX_AUTHORITY = "NAVIGATION_ONLY"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

def _get_head_sha(repo_root: pathlib.Path) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=repo_root,
    )
    return r.stdout.strip() if r.returncode == 0 else "UNKNOWN"


def _get_dirty_digest(repo_root: pathlib.Path) -> str:
    """Hash of the git status output — changes when working tree is dirty."""
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, cwd=repo_root,
    )
    status = r.stdout.strip() if r.returncode == 0 else ""
    return hashlib.sha256(status.encode()).hexdigest()[:16]


def _query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def _snapshot_id(head_sha: str, dirty_digest: str, indexed_files_hash: str) -> str:
    combined = f"{head_sha}:{dirty_digest}:{indexed_files_hash}"
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
    dirty_digest: str
    snapshot_id: str
    query_hash: str

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
    snapshot_build_ms: float
    index_build_ms: float
    query_tokenize_ms: float
    ranking_ms: float
    map_render_ms: float
    total_ms: float
    is_warm: bool  # True if snapshot was reused from previous call

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
    Lexical-first discovery runtime shadow.

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

        # Provenance
        head_sha = _get_head_sha(repo_root)
        dirty_digest = _get_dirty_digest(repo_root)

        # --- Snapshot ---
        t_snap_start = time.monotonic()
        snapshot = self._backend.build_snapshot_from_worktree(repo_root)
        all_files = sorted(snapshot.file_graph.nodes)  # sorted for determinism
        files_hash = _files_hash(all_files)
        sid = _snapshot_id(head_sha, dirty_digest, files_hash)
        t_snap_ms = (time.monotonic() - t_snap_start) * 1000

        # Warm reuse: reuse cached BM25 index if snapshot_id is identical
        is_warm = False
        if self._cache is not None and self._cache.snapshot_id == sid:
            index = self._cache.bm25_index
            sym_by_file = self._cache.symbol_names_by_path
            file_paths = self._cache.file_paths
            t_index_ms = 0.0
            is_warm = True
        else:
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
            # Cache
            self._cache = _CachedSnapshot(
                snapshot_id=sid,
                file_paths=all_files,
                symbol_names_by_path=sym_by_file,
                bm25_index=index,
                build_ms=t_index_ms,
            )
            file_paths = all_files

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
            candidates.append(CandidateResult(rank=i + 1, path=path, score=round(score, 6), matched_tokens=matched))

        # --- Map rendering ---
        t_map_start = time.monotonic()
        map_lines = [f"# Discovery shadow — {head_sha[:8]} | query:{qhash}"]
        map_lines.append(f"# tokenizer:{M11_TOKENIZER_VERSION} bm25:{M11_BM25_VERSION} k1={M11_K1} b={M11_B}")
        map_lines.append(f"# tie_break:{M11_TIE_BREAK_POLICY} authority:{M11_INDEX_AUTHORITY}")
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
            snapshot_id=sid,
            query_hash=qhash,
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
            snapshot_build_ms=round(t_snap_ms, 2),
            index_build_ms=round(t_index_ms, 2),
            query_tokenize_ms=round(t_tok_ms, 4),
            ranking_ms=round(t_rank_ms, 4),
            map_render_ms=round(t_map_ms, 4),
            total_ms=round(total_ms, 2),
            is_warm=is_warm,
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
                "ranker_version": result.bm25_version,
                "tokenizer_version": result.tokenizer_version,
                "k1": result.k1,
                "b": result.b,
                "tie_break_policy": result.tie_break_policy,
                "candidate_paths": [c.path for c in result.candidates],
                "scores": [c.score for c in result.candidates],
                "map_size_bytes": result.map_bytes,
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
            "evaluation_hash": ev.evaluation_hash,
            "known_positives": task["known_positives"],
            "R@1": recall_at(1),
            "R@3": recall_at(3),
            "R@5": recall_at(5),
            "R@10": recall_at(10),
            "top5_paths": ranked_paths[:5],
            "total_ms": ev.total_ms,
            "is_warm": ev.is_warm,
            "map_bytes": ev.map_bytes,
            "estimated_map_tokens": ev.estimated_map_tokens,
        })
    return results