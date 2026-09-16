"""fiofilter.discovery_shadow — Structural Discovery Ranking and Benchmarks.

Implements:
- Deterministic DiscoveryQueryExtractor (path, symbol, lexical terms, intent).
- Multi-signal explainable ranker supporting 4 ablation modes:
  - LEXICAL_ONLY
  - STRUCTURAL_ONLY
  - LEXICAL_PLUS_STRUCTURAL
  - LEXICAL_PLUS_PPR (Personalized PageRank)
- Commit-History Benchmark over local Git repository state:
  - Parent snapshot -> Child changed files ground truth
  - Query leakage auditing (PATH_LEAKING vs NON_LEAKING)
  - Recall@1, Recall@3, Recall@5, Recall@10, and MRR metrics
- Source A Discovery Shadow Replay analysis.
- Graph construction and ranking economics measurements.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import pathlib
import re
import subprocess
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from fiofilter.structural import (
    ContextCandidate,
    DiscoveryQuery,
    DiscoveryQueryIntent,
    GraphHealthStatus,
    RankingMode,
    StructuralSnapshot,
    SymbolDefinition,
)
from fiofilter.structural_python import PythonAstStructuralBackend

STOPWORDS = {
    "a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with",
    "by", "from", "up", "about", "into", "over", "after", "is", "are", "was",
    "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "but", "not", "so", "if", "then", "else", "when", "while", "that", "this",
    "these", "those", "it", "its", "test", "tests", "add", "fix", "update",
    "feat", "chore", "docs", "refactor", "implement", "make", "change",
}


class DiscoveryQueryExtractor:
    """Deterministic extractor converting natural language task descriptions into query structures."""

    def __init__(self, snapshot: StructuralSnapshot) -> None:
        self.snapshot = snapshot
        self._all_files = set(snapshot.files)
        self._file_stems = {f.split("/")[-1].replace(".py", "").lower(): f for f in snapshot.files}
        self._all_symbol_names = {s.qualified_name.split(".")[-1]: s for s in snapshot.symbol_index.symbols}
        self._symbol_lower_map = {name.lower(): name for name in self._all_symbol_names.keys()}

    def extract_query(self, raw_text: str) -> DiscoveryQuery:
        """Extract explicit paths, symbols, terms, and intent deterministically."""
        cleaned = raw_text.strip()
        words = re.findall(r"[A-Za-z0-9_\-./\\]+", cleaned)

        explicit_paths: List[str] = []
        explicit_symbols: List[str] = []
        lexical_terms: List[str] = []

        for w in words:
            w_norm = w.replace("\\", "/").strip("./")
            # 1. Path check
            if w_norm in self._all_files:
                explicit_paths.append(w_norm)
                continue
            if w_norm.endswith(".py"):
                for f in self._all_files:
                    if f.endswith(w_norm):
                        explicit_paths.append(f)
                        break

            # 2. File stem check
            w_lower = w.lower()
            if w_lower in self._file_stems and len(w_lower) > 3:
                stem_file = self._file_stems[w_lower]
                if stem_file not in explicit_paths:
                    explicit_paths.append(stem_file)

            # 3. Exact symbol check
            if w in self._all_symbol_names:
                explicit_symbols.append(w)
            elif w_lower in self._symbol_lower_map and len(w_lower) > 3:
                explicit_symbols.append(self._symbol_lower_map[w_lower])

            # 4. Lexical word terms
            term_clean = re.sub(r"[^a-zA-Z0-9_]", "", w_lower)
            if len(term_clean) >= 3 and term_clean not in STOPWORDS:
                if term_clean not in lexical_terms:
                    lexical_terms.append(term_clean)

        # Deduplicate while preserving order
        explicit_paths = list(collections.OrderedDict.fromkeys(explicit_paths))
        explicit_symbols = list(collections.OrderedDict.fromkeys(explicit_symbols))

        # Intent classification
        intent = DiscoveryQueryIntent.UNKNOWN
        cleaned_lower = cleaned.lower()
        if re.search(r"\b(callers of|dependents of|depends on|imports|related to)\b", cleaned_lower):
            intent = DiscoveryQueryIntent.RELATED_TO_FILE
        elif explicit_paths and not explicit_symbols:
            intent = DiscoveryQueryIntent.PATH_LOOKUP
        elif explicit_symbols and not explicit_paths:
            intent = DiscoveryQueryIntent.SYMBOL_LOOKUP
        elif lexical_terms or explicit_paths or explicit_symbols:
            intent = DiscoveryQueryIntent.FEATURE_TEXT

        return DiscoveryQuery(
            raw_query=cleaned,
            intent=intent,
            explicit_paths=explicit_paths,
            explicit_symbols=explicit_symbols,
            lexical_terms=lexical_terms,
        )


class StructuralRanker:
    """Multi-signal, ablatable structural ranker producing explainable candidate rankings."""

    def __init__(self, snapshot: StructuralSnapshot) -> None:
        self.snapshot = snapshot
        self.graph = snapshot.file_graph
        self.symbols = snapshot.symbol_index

    def rank_candidates(
        self,
        query: DiscoveryQuery,
        mode: RankingMode = RankingMode.LEXICAL_PLUS_PPR,
        top_k: int = 10,
    ) -> List[ContextCandidate]:
        """Rank all repository files according to the specified ablation mode."""
        files = sorted(self.snapshot.files)
        if not files:
            return []

        # 1. Lexical Scoring Component
        lexical_scores: Dict[str, float] = collections.defaultdict(float)
        matched_symbols_by_file: Dict[str, List[str]] = collections.defaultdict(list)
        matched_terms_by_file: Dict[str, List[str]] = collections.defaultdict(list)
        signal_breakdown: Dict[str, Dict[str, float]] = collections.defaultdict(lambda: collections.defaultdict(float))

        for f in files:
            f_lower = f.lower()

            # Exact path match
            if f in query.explicit_paths:
                lexical_scores[f] += 100.0
                signal_breakdown[f]["EXACT_PATH_MATCH"] = 100.0

            # Lexical term matches in path
            for term in query.lexical_terms:
                if term in f_lower:
                    lexical_scores[f] += 15.0
                    signal_breakdown[f]["LEXICAL_PATH_MATCH"] += 15.0
                    matched_terms_by_file[f].append(term)

            # Symbol matches in file
            file_syms = self.symbols.symbols_in_file(f)
            for sym in file_syms:
                s_name = sym.qualified_name.split(".")[-1]
                s_lower = s_name.lower()

                if s_name in query.explicit_symbols:
                    lexical_scores[f] += 40.0
                    signal_breakdown[f]["EXACT_SYMBOL_MATCH"] += 40.0
                    if s_name not in matched_symbols_by_file[f]:
                        matched_symbols_by_file[f].append(s_name)

                for term in query.lexical_terms:
                    if term in s_lower and len(term) >= 4:
                        lexical_scores[f] += 10.0
                        signal_breakdown[f]["LEXICAL_SYMBOL_MATCH"] += 10.0
                        if s_name not in matched_symbols_by_file[f]:
                            matched_symbols_by_file[f].append(s_name)
                        if term not in matched_terms_by_file[f]:
                            matched_terms_by_file[f].append(term)

        # 2. Structural Seeds from Top Lexical / Explicit Matches
        seed_weights: Dict[str, float] = {}
        for p in query.explicit_paths:
            if p in self.graph.nodes:
                seed_weights[p] = seed_weights.get(p, 0.0) + 100.0

        for f, score in lexical_scores.items():
            if score > 0:
                seed_weights[f] = seed_weights.get(f, 0.0) + score

        # 3. Graph Distance & Proximity
        graph_distances: Dict[str, Optional[int]] = {}
        if seed_weights:
            for f in files:
                min_dist: Optional[int] = None
                for seed in seed_weights:
                    d = self.graph.shortest_path_distance(seed, f)
                    if d is not None:
                        if min_dist is None or d < min_dist:
                            min_dist = d
                graph_distances[f] = min_dist
                if min_dist is not None:
                    # Proximity bonus: 5.0 for distance 0, 2.5 for distance 1, 1.67 for distance 2
                    proximity_bonus = 5.0 / (min_dist + 1.0)
                    signal_breakdown[f]["GRAPH_PROXIMITY"] = proximity_bonus
        else:
            for f in files:
                graph_distances[f] = None

        # 4. Global In-Degree Structural Centrality
        for f in files:
            dependents_count = len(self.graph.dependents(f))
            centrality_score = math.log1p(dependents_count) * 5.0
            signal_breakdown[f]["STRUCTURAL_CENTRALITY"] = centrality_score

        # 5. Personalized PageRank
        ppr_scores: Dict[str, float] = {}
        if mode == RankingMode.LEXICAL_PLUS_PPR:
            ppr_scores = self.graph.pagerank(personalization_seeds=seed_weights if seed_weights else None)
            max_ppr = max(ppr_scores.values()) if ppr_scores else 1.0
            for f in files:
                val = (ppr_scores.get(f, 0.0) / max_ppr) * 20.0 if max_ppr > 0 else 0.0
                signal_breakdown[f]["PAGERANK"] = val

        # 6. Aggregate Score According to Mode
        final_scores: Dict[str, float] = {}
        for f in files:
            sig = signal_breakdown[f]
            if mode == RankingMode.LEXICAL_ONLY:
                final_scores[f] = (
                    sig.get("EXACT_PATH_MATCH", 0.0)
                    + sig.get("EXACT_SYMBOL_MATCH", 0.0)
                    + sig.get("LEXICAL_PATH_MATCH", 0.0)
                    + sig.get("LEXICAL_SYMBOL_MATCH", 0.0)
                )
            elif mode == RankingMode.STRUCTURAL_ONLY:
                # Based purely on graph centrality and proximity to explicit paths
                final_scores[f] = (
                    sig.get("STRUCTURAL_CENTRALITY", 0.0)
                    + (sig.get("GRAPH_PROXIMITY", 0.0) if query.explicit_paths else 0.0)
                )
            elif mode == RankingMode.LEXICAL_PLUS_STRUCTURAL:
                final_scores[f] = (
                    sig.get("EXACT_PATH_MATCH", 0.0)
                    + sig.get("EXACT_SYMBOL_MATCH", 0.0)
                    + sig.get("LEXICAL_PATH_MATCH", 0.0)
                    + sig.get("LEXICAL_SYMBOL_MATCH", 0.0)
                    + sig.get("GRAPH_PROXIMITY", 0.0)
                    + sig.get("STRUCTURAL_CENTRALITY", 0.0)
                )
            elif mode == RankingMode.LEXICAL_PLUS_PPR:
                final_scores[f] = (
                    sig.get("EXACT_PATH_MATCH", 0.0)
                    + sig.get("EXACT_SYMBOL_MATCH", 0.0)
                    + sig.get("LEXICAL_PATH_MATCH", 0.0)
                    + sig.get("LEXICAL_SYMBOL_MATCH", 0.0)
                    + sig.get("GRAPH_PROXIMITY", 0.0)
                    + sig.get("PAGERANK", 0.0)
                )

        # Sort descending by score, tie-break by path name
        sorted_files = sorted(files, key=lambda x: (-final_scores[x], x))

        candidates: List[ContextCandidate] = []
        for rank_idx, f in enumerate(sorted_files[:top_k], 1):
            score = final_scores[f]
            # Explainability
            active_signals = [k for k, v in signal_breakdown[f].items() if v > 0]
            explanation = " + ".join(active_signals) if active_signals else "DEFAULT_UNRANKED"

            candidates.append(
                ContextCandidate(
                    path=f,
                    rank=rank_idx,
                    score=score,
                    signals=dict(signal_breakdown[f]),
                    matched_symbols=matched_symbols_by_file[f],
                    matched_terms=matched_terms_by_file[f],
                    graph_distance=graph_distances[f],
                    snapshot_id=self.snapshot.snapshot_id,
                    graph_health=self.snapshot.health.status,
                    explanation=explanation,
                )
            )

        return candidates


class CommitHistoryBenchmark:
    """Benchmark evaluating candidate retrieval recall on FioFilter's own Git commits."""

    def __init__(self, repo_root: pathlib.Path) -> None:
        self.repo_root = repo_root.resolve()
        self.backend = PythonAstStructuralBackend()

    def discover_eligible_commits(self, max_commits: int = 50) -> List[Dict[str, Any]]:
        """Find non-merge commits with code changes and usable commit messages."""
        cmd = ["git", "log", "--format=%H|%P|%s", f"-n{max_commits}"]
        proc = subprocess.run(
            cmd,
            cwd=self.repo_root,
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if proc.returncode != 0:
            return []

        eligible: List[Dict[str, Any]] = []
        for line in proc.stdout.splitlines():
            parts = line.strip().split("|")
            if len(parts) < 3:
                continue
            sha, parents_str, subject = parts[0], parts[1], parts[2]
            parents = parents_str.split()
            # Must have exactly 1 parent (exclude initial commit and merge commits)
            if len(parents) != 1:
                continue
            parent_sha = parents[0]

            # Inspect files changed in this commit
            diff_cmd = ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha]
            diff_proc = subprocess.run(
                diff_cmd,
                cwd=self.repo_root,
                stdout=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if diff_proc.returncode != 0:
                continue

            changed_py_files = [
                f.replace("\\", "/")
                for f in diff_proc.stdout.splitlines()
                if f.strip().endswith(".py")
            ]

            # Must change at least one Python file
            if not changed_py_files:
                continue

            # Check query leakage: does subject contain any changed filename or symbol?
            path_leaking = any(
                f.split("/")[-1] in subject or f.split("/")[-1].replace(".py", "") in subject
                for f in changed_py_files
            )

            leakage_type = "PATH_LEAKING" if path_leaking else "NON_LEAKING"

            eligible.append(
                {
                    "commit_sha": sha,
                    "parent_sha": parent_sha,
                    "subject": subject,
                    "changed_files": sorted(changed_py_files),
                    "leakage_type": leakage_type,
                }
            )

        return eligible

    def run_benchmark(
        self,
        max_commits: int = 20,
    ) -> Dict[str, Any]:
        """Execute full benchmark across eligible commits comparing ablation modes."""
        eligible_commits = self.discover_eligible_commits(max_commits=max_commits)
        if not eligible_commits:
            return {"error": "NO_ELIGIBLE_COMMITS_FOUND"}

        # Snapshot cache keyed by parent SHA to avoid redundant Git plumbing
        snapshots: Dict[str, StructuralSnapshot] = {}

        results_by_mode: Dict[str, Dict[str, Any]] = {
            m.value: {
                "hits_at_1": 0,
                "hits_at_3": 0,
                "hits_at_5": 0,
                "hits_at_10": 0,
                "all_hits_at_5": 0,
                "all_hits_at_10": 0,
                "reciprocal_ranks": [],
                "no_hits_in_10": 0,
                "total_tasks": 0,
                "total_target_files": 0,
                "found_target_files_at_10": 0,
            }
            for m in RankingMode
        }

        # Also track non-path-leaking subset separately
        non_leaking_results: Dict[str, Dict[str, Any]] = {
            m.value: {
                "hits_at_1": 0,
                "hits_at_3": 0,
                "hits_at_5": 0,
                "hits_at_10": 0,
                "reciprocal_ranks": [],
                "total_tasks": 0,
            }
            for m in RankingMode
        }

        task_evaluations: List[Dict[str, Any]] = []

        for task in eligible_commits:
            parent_sha = task["parent_sha"]
            if parent_sha not in snapshots:
                try:
                    snapshots[parent_sha] = self.backend.build_snapshot_from_git_commit(
                        self.repo_root, parent_sha
                    )
                except Exception:
                    continue

            snap = snapshots[parent_sha]
            if not snap.files:
                continue

            query_extractor = DiscoveryQueryExtractor(snap)
            query = query_extractor.extract_query(task["subject"])
            ranker = StructuralRanker(snap)
            targets = set(task["changed_files"])

            task_modes_summary: Dict[str, Any] = {}

            for mode in RankingMode:
                cands = ranker.rank_candidates(query, mode=mode, top_k=10)
                ranked_paths = [c.path for c in cands]

                # Measure recall metrics
                found_targets = [t for t in targets if t in ranked_paths]
                first_hit_rank: Optional[int] = None
                for idx, p in enumerate(ranked_paths, 1):
                    if p in targets:
                        first_hit_rank = idx
                        break

                rr = 1.0 / first_hit_rank if first_hit_rank is not None else 0.0

                r_dict = results_by_mode[mode.value]
                r_dict["total_tasks"] += 1
                r_dict["total_target_files"] += len(targets)
                r_dict["found_target_files_at_10"] += len(found_targets)
                r_dict["reciprocal_ranks"].append(rr)

                if first_hit_rank == 1:
                    r_dict["hits_at_1"] += 1
                if first_hit_rank and first_hit_rank <= 3:
                    r_dict["hits_at_3"] += 1
                if first_hit_rank and first_hit_rank <= 5:
                    r_dict["hits_at_5"] += 1
                if first_hit_rank and first_hit_rank <= 10:
                    r_dict["hits_at_10"] += 1
                else:
                    r_dict["no_hits_in_10"] += 1

                # All targets found in top K
                if len(found_targets) == len(targets) and first_hit_rank and first_hit_rank <= 5:
                    r_dict["all_hits_at_5"] += 1
                if len(found_targets) == len(targets) and first_hit_rank and first_hit_rank <= 10:
                    r_dict["all_hits_at_10"] += 1

                # Non-leaking subset
                if task["leakage_type"] == "NON_LEAKING":
                    nl_dict = non_leaking_results[mode.value]
                    nl_dict["total_tasks"] += 1
                    nl_dict["reciprocal_ranks"].append(rr)
                    if first_hit_rank == 1:
                        nl_dict["hits_at_1"] += 1
                    if first_hit_rank and first_hit_rank <= 3:
                        nl_dict["hits_at_3"] += 1
                    if first_hit_rank and first_hit_rank <= 5:
                        nl_dict["hits_at_5"] += 1
                    if first_hit_rank and first_hit_rank <= 10:
                        nl_dict["hits_at_10"] += 1

                task_modes_summary[mode.value] = {
                    "first_hit_rank": first_hit_rank,
                    "found_count": len(found_targets),
                    "total_targets": len(targets),
                    "top_3_candidates": ranked_paths[:3],
                }

            task_evaluations.append(
                {
                    "commit_sha": task["commit_sha"],
                    "subject": task["subject"],
                    "leakage_type": task["leakage_type"],
                    "changed_files": task["changed_files"],
                    "modes": task_modes_summary,
                }
            )

        # Aggregate summary table
        metrics_summary: Dict[str, Any] = {}
        for m_name, r_data in results_by_mode.items():
            tot = max(1, r_data["total_tasks"])
            mrr = sum(r_data["reciprocal_ranks"]) / tot
            metrics_summary[m_name] = {
                "tasks_evaluated": tot,
                "changed_file_recall_at_1": round(r_data["hits_at_1"] / tot, 4),
                "changed_file_recall_at_3": round(r_data["hits_at_3"] / tot, 4),
                "changed_file_recall_at_5": round(r_data["hits_at_5"] / tot, 4),
                "changed_file_recall_at_10": round(r_data["hits_at_10"] / tot, 4),
                "tasks_with_all_targets_at_5": r_data["all_hits_at_5"],
                "tasks_with_all_targets_at_10": r_data["all_hits_at_10"],
                "mrr": round(mrr, 4),
                "no_relevant_in_top10": r_data["no_hits_in_10"],
            }

        # Non-leaking summary table
        non_leaking_summary: Dict[str, Any] = {}
        for m_name, nl_data in non_leaking_results.items():
            tot_nl = max(1, nl_data["total_tasks"])
            mrr_nl = sum(nl_data["reciprocal_ranks"]) / tot_nl if nl_data["total_tasks"] > 0 else 0.0
            non_leaking_summary[m_name] = {
                "tasks_evaluated": nl_data["total_tasks"],
                "recall_at_1": round(nl_data["hits_at_1"] / tot_nl, 4) if nl_data["total_tasks"] > 0 else 0.0,
                "recall_at_3": round(nl_data["hits_at_3"] / tot_nl, 4) if nl_data["total_tasks"] > 0 else 0.0,
                "recall_at_5": round(nl_data["hits_at_5"] / tot_nl, 4) if nl_data["total_tasks"] > 0 else 0.0,
                "recall_at_10": round(nl_data["hits_at_10"] / tot_nl, 4) if nl_data["total_tasks"] > 0 else 0.0,
                "mrr": round(mrr_nl, 4),
            }

        return {
            "eligible_commits_count": len(eligible_commits),
            "snapshots_built": len(snapshots),
            "all_eligible_metrics": metrics_summary,
            "non_leaking_subset_metrics": non_leaking_summary,
            "tasks": task_evaluations,
        }
