"""fiofilter.structural — Core Structural Discovery and Index Abstractions.

Formally decouples the CONTROL PLANE (navigation, lossy ranking, graph discovery)
from the EVIDENCE PLANE (lossless, deterministic source evidence verification).

Formal Invariants:
- INDEX != EVIDENCE
- INDEX != AUTHORITY
- RANK != CORRECTNESS
- LOW_RANK != IRRELEVANT
- BUDGET_APPLIES_TO_INDEX_ONLY = True
- EVIDENCE_OVERRIDES_BUDGET = True
- DISCOVERY_READ_SUPPRESSION = False
- AUTO_CONTEXT_SELECTION = False
- INDEX_ONLY_SHADOW = True

Adopted & Adapted Donor Concepts:
- Aider RepoMap: task-personalized ranking, graph centrality (Personalized PageRank),
  budgeted compact signature summaries.
- AgentMap: resolved dependency graph (FILE_GRAPH vs SYMBOL_INDEX), graph-health
  and edge-coverage accounting, blast-radius traversal.
"""

from __future__ import annotations

import datetime
import enum
import hashlib
import json
import math
import pathlib
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


class SourceKind(str, enum.Enum):
    """Origin of a structural snapshot."""
    GIT_COMMIT = "GIT_COMMIT"
    WORKTREE = "WORKTREE"
    SYNTHETIC = "SYNTHETIC"


class GraphHealthStatus(str, enum.Enum):
    """Descriptive stratification of structural graph coverage and health."""
    GRAPH_HEALTH_HIGH_OBSERVED = "GRAPH_HEALTH_HIGH_OBSERVED"
    GRAPH_HEALTH_PARTIAL = "GRAPH_HEALTH_PARTIAL"
    GRAPH_HEALTH_LOW = "GRAPH_HEALTH_LOW"
    UNKNOWN = "UNKNOWN"


class ImportEdgeType(str, enum.Enum):
    """Categorization of dependency relationship between source files."""
    RUNTIME_IMPORT = "RUNTIME_IMPORT"
    TYPE_CHECKING_IMPORT = "TYPE_CHECKING_IMPORT"
    UNRESOLVED_IMPORT = "UNRESOLVED_IMPORT"


class SymbolKind(str, enum.Enum):
    """Kind of extracted code symbol declaration."""
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    ASYNC_FUNCTION = "ASYNC_FUNCTION"
    METHOD = "METHOD"
    VARIABLE = "VARIABLE"


class DiscoveryQueryIntent(str, enum.Enum):
    """Deterministic routing category for task discovery queries."""
    PATH_LOOKUP = "PATH_LOOKUP"
    SYMBOL_LOOKUP = "SYMBOL_LOOKUP"
    RELATED_TO_FILE = "RELATED_TO_FILE"
    FEATURE_TEXT = "FEATURE_TEXT"
    UNKNOWN = "UNKNOWN"


class RankingMode(str, enum.Enum):
    """Ablation configurations for structural discovery ranking."""
    LEXICAL_ONLY = "LEXICAL_ONLY"
    STRUCTURAL_ONLY = "STRUCTURAL_ONLY"
    LEXICAL_PLUS_STRUCTURAL = "LEXICAL_PLUS_STRUCTURAL"
    LEXICAL_PLUS_PPR = "LEXICAL_PLUS_PPR"


# Formal Authority Boundary Declarations
INDEX_AUTHORITY: str = "NAVIGATION_ONLY"
INDEX_CAN_SATISFY_CANONICAL_EVIDENCE: bool = False
INDEX_CAN_AUTHORIZE_CODE_CHANGE: bool = False
INDEX_CAN_HIDE_LOW_RANK_FILES: bool = False
BUDGET_APPLIES_TO_INDEX_ONLY: bool = True
EVIDENCE_OVERRIDES_BUDGET: bool = True
DISCOVERY_READ_SUPPRESSION: bool = False
AUTO_CONTEXT_SELECTION: bool = False
INDEX_ONLY_SHADOW: bool = True


@dataclass(frozen=True)
class SymbolDefinition:
    """Compact declaration metadata extracted from code without full function bodies."""
    file_path: str
    qualified_name: str
    kind: SymbolKind
    line_number: int
    signature_summary: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "qualified_name": self.qualified_name,
            "kind": self.kind.value,
            "line_number": self.line_number,
            "signature_summary": self.signature_summary,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> SymbolDefinition:
        return cls(
            file_path=d["file_path"],
            qualified_name=d["qualified_name"],
            kind=SymbolKind(d["kind"]),
            line_number=int(d["line_number"]),
            signature_summary=d["signature_summary"],
        )


@dataclass(frozen=True)
class FileEdge:
    """Dependency relationship between two files."""
    source_file: str
    target_file: str
    edge_type: ImportEdgeType
    symbol: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "target_file": self.target_file,
            "edge_type": self.edge_type.value,
            "symbol": self.symbol,
        }


@dataclass
class GraphHealth:
    """AgentMap-derived health and coverage metrics for structural indexing."""
    files_seen: int = 0
    files_parsed: int = 0
    parse_failures: int = 0
    imports_seen: int = 0
    local_import_candidates: int = 0
    resolved_local_imports: int = 0
    unresolved_local_imports: int = 0

    @property
    def edge_coverage(self) -> float:
        if self.local_import_candidates <= 0:
            return 1.0 if self.files_parsed > 0 else 0.0
        return round(self.resolved_local_imports / self.local_import_candidates, 4)

    @property
    def parse_coverage(self) -> float:
        if self.files_seen <= 0:
            return 0.0
        return round(self.files_parsed / self.files_seen, 4)

    @property
    def status(self) -> GraphHealthStatus:
        if self.files_seen <= 0:
            return GraphHealthStatus.UNKNOWN
        if self.parse_coverage >= 0.95 and self.edge_coverage >= 0.85:
            return GraphHealthStatus.GRAPH_HEALTH_HIGH_OBSERVED
        if self.parse_coverage >= 0.80 and self.edge_coverage >= 0.50:
            return GraphHealthStatus.GRAPH_HEALTH_PARTIAL
        return GraphHealthStatus.GRAPH_HEALTH_LOW

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_seen": self.files_seen,
            "files_parsed": self.files_parsed,
            "parse_failures": self.parse_failures,
            "imports_seen": self.imports_seen,
            "local_import_candidates": self.local_import_candidates,
            "resolved_local_imports": self.resolved_local_imports,
            "unresolved_local_imports": self.unresolved_local_imports,
            "edge_coverage": self.edge_coverage,
            "parse_coverage": self.parse_coverage,
            "status": self.status.value,
        }


class FileGraph:
    """Resolved file dependency graph supporting dependency querying and PageRank."""

    def __init__(self) -> None:
        self.nodes: Set[str] = set()
        # Adjacency: source -> {target: edge} (source depends on target)
        self._adj: Dict[str, Dict[str, FileEdge]] = {}
        # Reverse adjacency: target -> {source: edge} (target is depended on by source)
        self._rev: Dict[str, Dict[str, FileEdge]] = {}

    @property
    def edge_count(self) -> int:
        return sum(len(targets) for targets in self._adj.values())

    @property
    def edges(self) -> List[FileEdge]:
        edges_list: List[FileEdge] = []
        for targets in self._adj.values():
            edges_list.extend(targets.values())
        return edges_list

    def add_node(self, file_path: str) -> None:
        norm = file_path.replace("\\", "/")
        self.nodes.add(norm)
        if norm not in self._adj:
            self._adj[norm] = {}
        if norm not in self._rev:
            self._rev[norm] = {}

    def add_edge(
        self,
        source: str,
        target: str,
        edge_type: ImportEdgeType = ImportEdgeType.RUNTIME_IMPORT,
        symbol: Optional[str] = None,
    ) -> None:
        s = source.replace("\\", "/")
        t = target.replace("\\", "/")
        self.add_node(s)
        self.add_node(t)
        edge = FileEdge(source_file=s, target_file=t, edge_type=edge_type, symbol=symbol)
        self._adj[s][t] = edge
        self._rev[t][s] = edge

    def dependencies(self, file_path: str) -> List[str]:
        """Return files that file_path imports/depends on."""
        norm = file_path.replace("\\", "/")
        return sorted(self._adj.get(norm, {}).keys())

    def dependents(self, file_path: str) -> List[str]:
        """Return files that import/depend on file_path."""
        norm = file_path.replace("\\", "/")
        return sorted(self._rev.get(norm, {}).keys())

    def neighbors(self, file_path: str) -> List[str]:
        """Combined undirected neighbors (both dependencies and dependents)."""
        norm = file_path.replace("\\", "/")
        deps = set(self._adj.get(norm, {}).keys())
        depts = set(self._rev.get(norm, {}).keys())
        return sorted(deps.union(depts))

    def shortest_path_distance(self, start: str, target: str) -> Optional[int]:
        """Compute unweighted shortest undirected distance using BFS."""
        s = start.replace("\\", "/")
        t = target.replace("\\", "/")
        if s == t:
            return 0
        if s not in self.nodes or t not in self.nodes:
            return None

        visited = {s}
        queue = [(s, 0)]
        while queue:
            curr, dist = queue.pop(0)
            for nbr in self.neighbors(curr):
                if nbr == t:
                    return dist + 1
                if nbr not in visited:
                    visited.add(nbr)
                    queue.append((nbr, dist + 1))
        return None

    def pagerank(
        self,
        personalization_seeds: Optional[Dict[str, float]] = None,
        alpha: float = 0.85,
        max_iter: int = 100,
        tol: float = 1e-6,
    ) -> Dict[str, float]:
        """Deterministic Personalized PageRank (Aider adaptation).

        Args:
            personalization_seeds: Mapping of seed file paths to relative weights.
            alpha: Damping factor (default: 0.85).
            max_iter: Maximum power-iteration steps.
            tol: L1 convergence tolerance.
        """
        nodes = sorted(self.nodes)
        n = len(nodes)
        if n == 0:
            return {}
        if n == 1:
            return {nodes[0]: 1.0}

        # Build personalization vector v
        v: Dict[str, float] = {}
        if personalization_seeds:
            valid_seeds = {
                k.replace("\\", "/"): max(0.0, float(w))
                for k, w in personalization_seeds.items()
                if k.replace("\\", "/") in self.nodes and w > 0
            }
            total_seed_weight = sum(valid_seeds.values())
            if total_seed_weight > 0:
                for node in nodes:
                    v[node] = valid_seeds.get(node, 0.0) / total_seed_weight
            else:
                for node in nodes:
                    v[node] = 1.0 / n
        else:
            for node in nodes:
                v[node] = 1.0 / n

        # Initial distribution p_0 = v
        p: Dict[str, float] = dict(v)

        # Precompute out-degrees (directed dependencies)
        # Note: In repo graphs, a file B depended on by many files A has in-degree in _adj
        # (A -> B means A imports B). High-centrality utilities receive imports.
        # Thus transitions flow along import edges: A -> B.
        out_degrees = {node: len(self._adj.get(node, {})) for node in nodes}

        for _ in range(max_iter):
            next_p = {node: (1.0 - alpha) * v[node] for node in nodes}
            dangling_sum = sum(p[node] for node in nodes if out_degrees[node] == 0)
            dangling_contrib = alpha * dangling_sum / n

            for node in nodes:
                next_p[node] += dangling_contrib
                # Distribute probability mass to targets
                targets = self._adj.get(node, {})
                deg = out_degrees[node]
                if deg > 0:
                    flow = (alpha * p[node]) / deg
                    for target in targets:
                        next_p[target] += flow

            # Check convergence via L1 norm
            diff = sum(abs(next_p[node] - p[node]) for node in nodes)
            p = next_p
            if diff < tol:
                break

        # Normalize to ensure sum = 1.0
        total = sum(p.values())
        if total > 0:
            return {k: round(v_val / total, 6) for k, v_val in sorted(p.items())}
        return {k: round(1.0 / n, 6) for k in sorted(nodes)}

    def to_dict(self) -> Dict[str, Any]:
        edges = []
        for s in sorted(self._adj.keys()):
            for t in sorted(self._adj[s].keys()):
                edges.append(self._adj[s][t].to_dict())
        return {
            "nodes": sorted(self.nodes),
            "edges": edges,
        }


class SymbolIndex:
    """Deterministic symbol lookup table supporting exact and prefix queries."""

    def __init__(self) -> None:
        self.symbols: List[SymbolDefinition] = []
        self._by_exact_name: Dict[str, List[SymbolDefinition]] = {}
        self._by_case_insensitive_name: Dict[str, List[SymbolDefinition]] = {}
        self._by_file: Dict[str, List[SymbolDefinition]] = {}

    def add_symbol(self, sym: SymbolDefinition) -> None:
        self.symbols.append(sym)
        name = sym.qualified_name.split(".")[-1]
        name_lower = name.lower()
        file_norm = sym.file_path.replace("\\", "/")

        self._by_exact_name.setdefault(name, []).append(sym)
        self._by_case_insensitive_name.setdefault(name_lower, []).append(sym)
        self._by_file.setdefault(file_norm, []).append(sym)

    def lookup_exact(self, name: str) -> List[SymbolDefinition]:
        return self._by_exact_name.get(name, [])

    def lookup_case_insensitive(self, name: str) -> List[SymbolDefinition]:
        return self._by_case_insensitive_name.get(name.lower(), [])

    def symbols_in_file(self, file_path: str) -> List[SymbolDefinition]:
        return self._by_file.get(file_path.replace("\\", "/"), [])

    def to_list(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in sorted(self.symbols, key=lambda x: (x.file_path, x.line_number))]


@dataclass
class StructuralSnapshot:
    """Immutable, auditable snapshot of a repository's structural graph and symbols."""
    snapshot_id: str
    source_kind: SourceKind
    repo_root: str
    git_head: Optional[str]
    dirty_state: bool
    backend: str
    backend_version: str
    health: GraphHealth
    files: List[str]
    file_graph: FileGraph
    symbol_index: SymbolIndex
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    limitations: List[str] = field(default_factory=list)

    def to_dict(self, include_symbol_details: bool = True) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "snapshot_id": self.snapshot_id,
            "source_kind": self.source_kind.value,
            "repo_root": self.repo_root,
            "git_head": self.git_head,
            "dirty_state": self.dirty_state,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "health": self.health.to_dict(),
            "files_count": len(self.files),
            "files": sorted(self.files),
            "file_graph": self.file_graph.to_dict(),
            "created_at": self.created_at,
            "limitations": self.limitations,
            "authority": INDEX_AUTHORITY,
        }
        if include_symbol_details:
            d["symbol_index"] = self.symbol_index.to_list()
        return d


@dataclass
class DiscoveryQuery:
    """Deterministic task discovery query extracted from user prompt or commit."""
    raw_query: str
    intent: DiscoveryQueryIntent
    explicit_paths: List[str] = field(default_factory=list)
    explicit_symbols: List[str] = field(default_factory=list)
    lexical_terms: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "intent": self.intent.value,
            "explicit_paths": self.explicit_paths,
            "explicit_symbols": self.explicit_symbols,
            "lexical_terms": self.lexical_terms,
        }


@dataclass
class ContextCandidate:
    """Ranked file candidate produced by structural shadow discovery."""
    path: str
    rank: int
    score: float
    signals: Dict[str, float]
    matched_symbols: List[str]
    matched_terms: List[str]
    graph_distance: Optional[int]
    snapshot_id: str
    graph_health: GraphHealthStatus
    explanation: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "rank": self.rank,
            "score": round(self.score, 4),
            "signals": {k: round(v, 4) for k, v in sorted(self.signals.items())},
            "matched_symbols": self.matched_symbols,
            "matched_terms": self.matched_terms,
            "graph_distance": self.graph_distance,
            "snapshot_id": self.snapshot_id,
            "graph_health": self.graph_health.value,
            "explanation": self.explanation,
        }


@dataclass
class BudgetedMapResult:
    """Compact Aider-style symbol signature map constrained by byte budget."""
    budget_bytes: int
    rendered_map: str
    rendered_bytes: int
    estimated_tokens: int
    included_files_count: int
    total_candidate_files: int
    truncated: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_bytes": self.budget_bytes,
            "rendered_bytes": self.rendered_bytes,
            "estimated_tokens": self.estimated_tokens,
            "included_files_count": self.included_files_count,
            "total_candidate_files": self.total_candidate_files,
            "truncated": self.truncated,
        }


def render_budgeted_map(
    candidates: List[ContextCandidate],
    symbol_index: SymbolIndex,
    budget_bytes: int = 4096,
) -> BudgetedMapResult:
    """Render compact file-and-symbol summaries fitting strictly within budget.

    Guarantees:
    - Never outputs entire function or class bodies.
    - Deterministic ordering by candidate rank.
    - Truncates cleanly at file or symbol boundary when budget is reached.
    - BUDGET_APPLIES_TO_INDEX_ONLY = True.
    """
    lines: List[str] = []
    current_bytes = 0
    included_files = 0
    truncated = False

    for cand in candidates:
        file_header = f"{cand.path}:\n"
        header_bytes = len(file_header.encode("utf-8"))

        if current_bytes + header_bytes > budget_bytes:
            truncated = True
            break

        file_lines = [file_header]
        file_current_bytes = header_bytes

        syms = symbol_index.symbols_in_file(cand.path)
        for sym in syms:
            sym_line = f"  {sym.signature_summary}\n"
            line_bytes = len(sym_line.encode("utf-8"))
            if current_bytes + file_current_bytes + line_bytes > budget_bytes:
                truncated = True
                break
            file_lines.append(sym_line)
            file_current_bytes += line_bytes

        lines.extend(file_lines)
        current_bytes += file_current_bytes
        included_files += 1

    rendered = "".join(lines)
    actual_bytes = len(rendered.encode("utf-8"))
    est_tokens = math.ceil(actual_bytes / 4.0)

    return BudgetedMapResult(
        budget_bytes=budget_bytes,
        rendered_map=rendered,
        rendered_bytes=actual_bytes,
        estimated_tokens=est_tokens,
        included_files_count=included_files,
        total_candidate_files=len(candidates),
        truncated=truncated,
    )
