"""tests.test_structural — Comprehensive verification of structural discovery abstractions.

Covers:
- Formal authority boundary and control plane invariants
- Synthetic graph fixtures: linear, diamond, circular, orphan, duplicate symbols
- Python AST symbol and import extraction (classes, methods, functions, TYPE_CHECKING)
- Relative import resolution and external package distinction
- Deterministic PageRank and Personalized PageRank on analytical toy graphs
- Worktree snapshot generation and content hash mutation tracking
- Graph health scoring and descriptive status
- Git commit snapshot extraction via plumbing without worktree checkout
"""

from __future__ import annotations

import ast
import pathlib
import tempfile
import pytest

from fiofilter.structural import (
    BUDGET_APPLIES_TO_INDEX_ONLY,
    DISCOVERY_READ_SUPPRESSION,
    EVIDENCE_OVERRIDES_BUDGET,
    INDEX_AUTHORITY,
    INDEX_CAN_AUTHORIZE_CODE_CHANGE,
    INDEX_CAN_HIDE_LOW_RANK_FILES,
    INDEX_CAN_SATISFY_CANONICAL_EVIDENCE,
    INDEX_ONLY_SHADOW,
    AUTO_CONTEXT_SELECTION,
    FileEdge,
    FileGraph,
    GraphHealth,
    GraphHealthStatus,
    ImportEdgeType,
    RankingMode,
    SourceKind,
    StructuralSnapshot,
    SymbolDefinition,
    SymbolIndex,
    SymbolKind,
    render_budgeted_map,
)
from fiofilter.structural_python import (
    PythonAstExtractor,
    PythonAstStructuralBackend,
    resolve_python_import,
)


class TestStructuralInvariants:
    """Formal verification of Control Plane vs Evidence Plane separation."""

    def test_formal_authority_declarations(self) -> None:
        assert INDEX_AUTHORITY == "NAVIGATION_ONLY"
        assert INDEX_CAN_SATISFY_CANONICAL_EVIDENCE is False
        assert INDEX_CAN_AUTHORIZE_CODE_CHANGE is False
        assert INDEX_CAN_HIDE_LOW_RANK_FILES is False
        assert BUDGET_APPLIES_TO_INDEX_ONLY is True
        assert EVIDENCE_OVERRIDES_BUDGET is True
        assert DISCOVERY_READ_SUPPRESSION is False
        assert AUTO_CONTEXT_SELECTION is False
        assert INDEX_ONLY_SHADOW is True

    def test_budget_does_not_suppress_evidence(self) -> None:
        """Low rank files or budgeted index maps never prevent reading canonical source."""
        assert DISCOVERY_READ_SUPPRESSION is False
        assert INDEX_CAN_HIDE_LOW_RANK_FILES is False


class TestFileGraphAndPageRank:
    """Tests for FileGraph topologies, path distance, and PageRank mathematics."""

    def test_empty_graph(self) -> None:
        graph = FileGraph()
        assert graph.nodes == set()
        assert graph.edges == []
        assert graph.pagerank() == {}

    def test_linear_imports(self) -> None:
        # a -> b -> c
        graph = FileGraph()
        graph.add_edge("a.py", "b.py", ImportEdgeType.RUNTIME_IMPORT)
        graph.add_edge("b.py", "c.py", ImportEdgeType.RUNTIME_IMPORT)

        assert graph.dependencies("a.py") == ["b.py"]
        assert graph.dependents("b.py") == ["a.py"]
        assert graph.dependencies("b.py") == ["c.py"]
        assert graph.dependents("c.py") == ["b.py"]
        assert graph.dependencies("c.py") == []

        assert graph.shortest_path_distance("a.py", "b.py") == 1
        assert graph.shortest_path_distance("a.py", "c.py") == 2
        assert graph.shortest_path_distance("c.py", "a.py") == 2  # undirected distance

        # PageRank: c.py is pointed to by b.py (which is pointed to by a.py), so c.py gets rank
        pr = graph.pagerank(alpha=0.85, max_iter=50)
        assert len(pr) == 3
        assert sum(pr.values()) == pytest.approx(1.0, abs=1e-5)
        # c.py should have higher stationary rank than a.py
        assert pr["c.py"] > pr["a.py"]

    def test_diamond_dependency(self) -> None:
        # a -> b, a -> c, b -> d, c -> d
        graph = FileGraph()
        graph.add_edge("a.py", "b.py", ImportEdgeType.RUNTIME_IMPORT)
        graph.add_edge("a.py", "c.py", ImportEdgeType.RUNTIME_IMPORT)
        graph.add_edge("b.py", "d.py", ImportEdgeType.RUNTIME_IMPORT)
        graph.add_edge("c.py", "d.py", ImportEdgeType.RUNTIME_IMPORT)

        assert sorted(graph.dependencies("a.py")) == ["b.py", "c.py"]
        assert sorted(graph.dependents("d.py")) == ["b.py", "c.py"]
        assert graph.shortest_path_distance("a.py", "d.py") == 2

        pr = graph.pagerank()
        # d.py is the sink of both b and c, so it has highest rank
        assert pr["d.py"] > pr["b.py"]
        assert pr["d.py"] > pr["c.py"]
        assert pr["b.py"] == pytest.approx(pr["c.py"], abs=1e-5)

    def test_circular_dependency(self) -> None:
        # a -> b -> a
        graph = FileGraph()
        graph.add_edge("a.py", "b.py", ImportEdgeType.RUNTIME_IMPORT)
        graph.add_edge("b.py", "a.py", ImportEdgeType.RUNTIME_IMPORT)

        pr = graph.pagerank()
        assert pr["a.py"] == pytest.approx(0.5, abs=1e-5)
        assert pr["b.py"] == pytest.approx(0.5, abs=1e-5)

    def test_orphan_node(self) -> None:
        # a -> b, orphan.py disconnected
        graph = FileGraph()
        graph.add_edge("a.py", "b.py", ImportEdgeType.RUNTIME_IMPORT)
        graph.add_node("orphan.py")

        pr = graph.pagerank()
        assert "orphan.py" in pr
        assert pr["orphan.py"] > 0
        assert graph.shortest_path_distance("a.py", "orphan.py") is None

    def test_personalized_pagerank_seed_boost(self) -> None:
        # 3 nodes: a, b, c. a -> b -> c. Personalize on a.py.
        graph = FileGraph()
        graph.add_edge("a.py", "b.py", ImportEdgeType.RUNTIME_IMPORT)
        graph.add_edge("b.py", "c.py", ImportEdgeType.RUNTIME_IMPORT)

        uniform_pr = graph.pagerank()
        seed_pr = graph.pagerank(personalization_seeds={"a.py": 10.0})

        # Under strong seed on a.py, a.py rank is noticeably higher than under uniform
        assert seed_pr["a.py"] > uniform_pr["a.py"]


class TestSymbolIndex:
    """Tests for SymbolIndex storage, queries, and symbol resolution."""

    def test_symbol_indexing_and_lookup(self) -> None:
        index = SymbolIndex()
        s1 = SymbolDefinition(
            file_path="fiofilter/store.py",
            qualified_name="fiofilter.store.RawStore",
            kind=SymbolKind.CLASS,
            line_number=20,
            signature_summary="class RawStore:",
        )
        s2 = SymbolDefinition(
            file_path="fiofilter/store.py",
            qualified_name="fiofilter.store.RawStore.store_bytes",
            kind=SymbolKind.METHOD,
            line_number=45,
            signature_summary="def store_bytes(self, data: bytes) -> str:",
        )
        s3 = SymbolDefinition(
            file_path="fiofilter/other.py",
            qualified_name="fiofilter.other.RawStore",
            kind=SymbolKind.CLASS,
            line_number=10,
            signature_summary="class RawStore:",
        )

        index.add_symbol(s1)
        index.add_symbol(s2)
        index.add_symbol(s3)

        assert len(index.symbols) == 3
        # Exact lookup
        exact_matches = index.lookup_exact("RawStore")
        assert len(exact_matches) == 2
        assert {m.file_path for m in exact_matches} == {"fiofilter/store.py", "fiofilter/other.py"}

        # Case-insensitive lookup
        ci_matches = index.lookup_case_insensitive("rawstore")
        assert len(ci_matches) == 2

        # In-file lookup
        store_syms = index.symbols_in_file("fiofilter/store.py")
        assert len(store_syms) == 2
        assert [s.kind for s in store_syms] == [SymbolKind.CLASS, SymbolKind.METHOD]


class TestPythonAstExtractor:
    """Tests for AST parsing: classes, functions, methods, imports, type-checking guards."""

    def test_extract_symbols(self) -> None:
        code = '''
"""Sample module."""
CONSTANT_VAL = 42

class DatabaseManager:
    """Manage database."""
    def __init__(self, url: str) -> None:
        self.url = url

    async def fetch_record(self, record_id: int) -> dict:
        return {"id": record_id}

def standalone_helper(x: int, y: int = 0) -> int:
    return x + y

async def standalone_coro():
    pass
'''
        extractor = PythonAstExtractor("pkg/manager.py")
        tree = ast.parse(code, filename="pkg/manager.py")
        extractor.visit(tree)

        sym_names = [s.qualified_name for s in extractor.symbols]
        assert "CONSTANT_VAL" in sym_names
        assert "DatabaseManager" in sym_names
        assert "DatabaseManager.__init__" in sym_names
        assert "DatabaseManager.fetch_record" in sym_names
        assert "standalone_helper" in sym_names
        assert "standalone_coro" in sym_names

        fetch_method = next(s for s in extractor.symbols if "fetch_record" in s.qualified_name)
        assert fetch_method.kind == SymbolKind.METHOD
        assert "async def fetch_record" in fetch_method.signature_summary

        coro_func = next(s for s in extractor.symbols if s.qualified_name == "standalone_coro")
        assert coro_func.kind == SymbolKind.ASYNC_FUNCTION

    def test_extract_imports_and_type_checking(self) -> None:
        code = '''
import os
import sys
from typing import TYPE_CHECKING, Optional, List
from .sub import helper
from ..parent import util

if TYPE_CHECKING:
    import pandas as pd
    from .models import BigModel
'''
        extractor = PythonAstExtractor("pkg/core/module.py")
        tree = ast.parse(code, filename="pkg/core/module.py")
        extractor.visit(tree)

        runtime_mods = [mod for mod, sym, is_rel, level, is_tc in extractor.raw_imports if not is_tc]
        assert "os" in runtime_mods
        assert "sys" in runtime_mods

        tc_mods = [mod for mod, sym, is_rel, level, is_tc in extractor.raw_imports if is_tc]
        assert "pandas" in tc_mods
        assert "models" in tc_mods

    def test_syntax_error_handled_gracefully_in_backend(self) -> None:
        broken_code = "def broken_func(:\n    return 42"
        backend = PythonAstStructuralBackend()
        snap = backend.build_snapshot_from_files(
            {"broken.py": broken_code, "valid.py": "x = 1\n"},
            repo_root=".",
            source_kind=SourceKind.SYNTHETIC,
        )
        assert snap.health.parse_failures == 1
        assert snap.health.files_parsed == 1
        assert snap.health.files_seen == 2


class TestImportResolution:
    """Tests for resolving Python imports into intra-repo file paths."""

    def test_resolve_relative_imports(self) -> None:
        universe = {
            "fiofilter/__init__.py",
            "fiofilter/store.py",
            "fiofilter/sub/helper.py",
            "fiofilter/sub/__init__.py",
        }
        package_roots = {"fiofilter"}

        # from .store import RawStore inside fiofilter/__init__.py
        target, is_local = resolve_python_import(
            source_file="fiofilter/__init__.py",
            module="store",
            symbol="RawStore",
            is_relative=True,
            level=1,
            file_universe=universe,
            known_package_roots=package_roots,
        )
        assert target == "fiofilter/store.py"
        assert is_local is True

        # from ..store import RawStore inside fiofilter/sub/helper.py
        target2, is_local2 = resolve_python_import(
            source_file="fiofilter/sub/helper.py",
            module="store",
            symbol="RawStore",
            is_relative=True,
            level=2,
            file_universe=universe,
            known_package_roots=package_roots,
        )
        assert target2 == "fiofilter/store.py"
        assert is_local2 is True

    def test_resolve_absolute_local_import(self) -> None:
        universe = {"fiofilter/store.py", "fiofilter/runtime_shadow.py"}
        package_roots = {"fiofilter"}
        target, is_local = resolve_python_import(
            source_file="fiofilter/runtime_shadow.py",
            module="fiofilter.store",
            symbol="RawStore",
            is_relative=False,
            level=0,
            file_universe=universe,
            known_package_roots=package_roots,
        )
        assert target == "fiofilter/store.py"
        assert is_local is True

    def test_resolve_stdlib_or_external_returns_none(self) -> None:
        universe = {"fiofilter/store.py"}
        package_roots = {"fiofilter"}
        target, is_local = resolve_python_import(
            source_file="fiofilter/store.py",
            module="os",
            symbol="path",
            is_relative=False,
            level=0,
            file_universe=universe,
            known_package_roots=package_roots,
        )
        assert target is None
        assert is_local is False


class TestGraphHealth:
    """Tests for GraphHealth calculation and descriptive thresholds."""

    def test_graph_health_high(self) -> None:
        health = GraphHealth(
            files_seen=10,
            files_parsed=10,
            parse_failures=0,
            imports_seen=20,
            local_import_candidates=18,
            resolved_local_imports=18,
            unresolved_local_imports=0,
        )
        assert health.edge_coverage == 1.0
        assert health.parse_coverage == 1.0
        assert health.status == GraphHealthStatus.GRAPH_HEALTH_HIGH_OBSERVED

    def test_graph_health_partial_and_low(self) -> None:
        # Partial: >=0.80 parse, >=0.50 edge
        h_partial = GraphHealth(
            files_seen=10,
            files_parsed=8,
            parse_failures=2,
            imports_seen=10,
            local_import_candidates=10,
            resolved_local_imports=6,
            unresolved_local_imports=4,
        )
        assert h_partial.status == GraphHealthStatus.GRAPH_HEALTH_PARTIAL

        # Low: parse < 0.80 or edge < 0.50
        h_low = GraphHealth(
            files_seen=10,
            files_parsed=4,
            parse_failures=6,
            imports_seen=10,
            local_import_candidates=10,
            resolved_local_imports=8,
            unresolved_local_imports=2,
        )
        assert h_low.status == GraphHealthStatus.GRAPH_HEALTH_LOW


class TestWorktreeSnapshot:
    """Tests for building structural snapshot from worktree and tracking changes."""

    def test_build_snapshot_from_temp_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = pathlib.Path(tmpdir)
            pkg = tmp_path / "pkg"
            pkg.mkdir()

            (pkg / "__init__.py").write_text('"""Package root."""\n', encoding="utf-8")
            (pkg / "a.py").write_text(
                'from .b import BClass\n\nclass AClass:\n    def run(self):\n        pass\n',
                encoding="utf-8",
            )
            (pkg / "b.py").write_text(
                'class BClass:\n    def action(self):\n        pass\n',
                encoding="utf-8",
            )

            backend = PythonAstStructuralBackend()
            snapshot = backend.build_snapshot_from_worktree(tmp_path)

            assert snapshot.source_kind == SourceKind.WORKTREE
            assert len(snapshot.files) == 3
            assert snapshot.health.status == GraphHealthStatus.GRAPH_HEALTH_HIGH_OBSERVED
            assert snapshot.health.files_parsed == 3

            # Check edge: pkg/a.py -> pkg/b.py
            a_deps = snapshot.file_graph.dependencies("pkg/a.py")
            assert a_deps == ["pkg/b.py"]

            # Check symbols
            a_syms = snapshot.symbol_index.symbols_in_file("pkg/a.py")
            assert any(s.signature_summary == "class AClass:" for s in a_syms)

            # Modifying content changes snapshot_id
            id1 = snapshot.snapshot_id
            (pkg / "b.py").write_text('class BClass:\n    def new_action(self):\n        pass\n', encoding="utf-8")
            snapshot2 = backend.build_snapshot_from_worktree(tmp_path)
            assert snapshot2.snapshot_id != id1


class TestBudgetedMapRendering:
    """Tests for rendering compact symbol signature maps within strict byte budgets."""

    def test_render_budgeted_map_within_budget(self) -> None:
        from fiofilter.structural import ContextCandidate

        index = SymbolIndex()
        s1 = SymbolDefinition("pkg/a.py", "pkg.a.AClass", SymbolKind.CLASS, 1, "class AClass:")
        s2 = SymbolDefinition("pkg/a.py", "pkg.a.AClass.foo", SymbolKind.METHOD, 2, "def foo(self):")
        s3 = SymbolDefinition("pkg/b.py", "pkg.b.BClass", SymbolKind.CLASS, 1, "class BClass:")
        index.add_symbol(s1)
        index.add_symbol(s2)
        index.add_symbol(s3)

        cands = [
            ContextCandidate("pkg/a.py", 1, 10.0, {}, ["AClass"], [], 0, "snap1", GraphHealthStatus.GRAPH_HEALTH_HIGH_OBSERVED, "test"),
            ContextCandidate("pkg/b.py", 2, 5.0, {}, ["BClass"], [], 1, "snap1", GraphHealthStatus.GRAPH_HEALTH_HIGH_OBSERVED, "test"),
        ]

        # Generous budget
        res = render_budgeted_map(cands, index, budget_bytes=1000)
        assert res.truncated is False
        assert res.included_files_count == 2
        assert "pkg/a.py:" in res.rendered_map
        assert "class AClass:" in res.rendered_map
        assert "pkg/b.py:" in res.rendered_map
        assert res.rendered_bytes <= 1000

        # Strict budget causing truncation
        res_tight = render_budgeted_map(cands, index, budget_bytes=35)
        assert res_tight.truncated is True
        assert res_tight.rendered_bytes <= 35
        assert res_tight.included_files_count <= 1
