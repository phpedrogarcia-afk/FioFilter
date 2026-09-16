"""fiofilter.structural_python — Python AST Structural Backend.

Implements PYTHON_AST_LOCAL_RESOLVER_V1:
- Extracts class, function, async function, method, and variable definitions.
- Distinguishes RUNTIME_IMPORT vs TYPE_CHECKING_IMPORT.
- Resolves local relative and absolute package imports into FILE_GRAPH edges.
- Strictly separates local import candidates from external third-party/stdlib dependencies.
- Computes AgentMap-derived edge coverage and parse coverage health metrics.
- Supports non-destructive Git plumbing snapshots (git ls-tree / git show) without worktree checkout.
- Enforces stale worktree defense with explicit dirty state provenance.
"""

from __future__ import annotations

import ast
import hashlib
import os
import pathlib
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from fiofilter.structural import (
    FileEdge,
    FileGraph,
    GraphHealth,
    ImportEdgeType,
    SourceKind,
    StructuralSnapshot,
    SymbolDefinition,
    SymbolIndex,
    SymbolKind,
)

BACKEND_IDENTITY = "PYTHON_AST_LOCAL_RESOLVER_V1"
BACKEND_VERSION = "1.0.0"

# Standard library and common third-party top-level packages to distinguish from local modules
KNOWN_EXTERNAL_ROOTS = {
    "os", "sys", "re", "json", "hashlib", "pathlib", "collections", "itertools",
    "functools", "typing", "enum", "datetime", "time", "math", "random", "subprocess",
    "tempfile", "shutil", "glob", "io", "copy", "traceback", "inspect", "ast",
    "dataclasses", "unittest", "pytest", "argparse", "logging", "threading",
    "multiprocessing", "concurrent", "asyncio", "socket", "http", "urllib",
    "base64", "uuid", "abc", "contextlib", "warnings", "platform", "struct",
    "anyio", "pluggy", "pip", "setuptools", "wheel", "requests", "cffi",
}

DEFAULT_EXCLUDE_PARTS = {
    ".git", "__pycache__", ".pytest_cache", ".venv", "venv", "env",
    "build", "dist", ".tox", ".mypy_cache", "site-packages",
}


class PythonAstExtractor(ast.NodeVisitor):
    """AST visitor extracting symbol signatures and import statements."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path.replace("\\", "/")
        self.symbols: List[SymbolDefinition] = []
        # Raw imports: List of (imported_module, imported_symbol_or_star, is_relative, level, is_type_checking)
        self.raw_imports: List[Tuple[Optional[str], Optional[str], bool, int, bool]] = []
        self._current_class: Optional[str] = None
        self._in_type_checking = False

    def visit_If(self, node: ast.If) -> None:
        # Check if node is `if TYPE_CHECKING:`
        is_tc = False
        if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            is_tc = True
        elif isinstance(node.test, ast.Attribute) and node.test.attr == "TYPE_CHECKING":
            is_tc = True

        prev_tc = self._in_type_checking
        if is_tc:
            self._in_type_checking = True
            for stmt in node.body:
                self.visit(stmt)
            self._in_type_checking = prev_tc
            for stmt in node.orelse:
                self.visit(stmt)
        else:
            self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        bases_str = ""
        if node.bases:
            bases_parts = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases_parts.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases_parts.append(b.attr)
            bases_str = f"({', '.join(bases_parts)})"

        sig = f"class {node.name}{bases_str}:"
        qname = f"{self._current_class}.{node.name}" if self._current_class else node.name
        self.symbols.append(
            SymbolDefinition(
                file_path=self.file_path,
                qualified_name=qname,
                kind=SymbolKind.CLASS,
                line_number=node.lineno,
                signature_summary=sig,
            )
        )

        prev_class = self._current_class
        self._current_class = qname
        for stmt in node.body:
            self.visit(stmt)
        self._current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._record_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._record_function(node, is_async=True)

    def _record_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        # Build compact signature
        args_parts = []
        for a in node.args.args:
            args_parts.append(a.arg)
        if node.args.vararg:
            args_parts.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args_parts.append(f"**{node.args.kwarg.arg}")

        prefix = "async def" if is_async else "def"
        sig = f"{prefix} {node.name}({', '.join(args_parts)}):"
        kind = SymbolKind.METHOD if self._current_class else (SymbolKind.ASYNC_FUNCTION if is_async else SymbolKind.FUNCTION)
        qname = f"{self._current_class}.{node.name}" if self._current_class else node.name

        self.symbols.append(
            SymbolDefinition(
                file_path=self.file_path,
                qualified_name=qname,
                kind=kind,
                line_number=node.lineno,
                signature_summary=sig,
            )
        )

    def visit_Assign(self, node: ast.Assign) -> None:
        # Top-level constant assignments
        if self._current_class is None:
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id.isupper():
                    self.symbols.append(
                        SymbolDefinition(
                            file_path=self.file_path,
                            qualified_name=t.id,
                            kind=SymbolKind.VARIABLE,
                            line_number=node.lineno,
                            signature_summary=f"{t.id} = ...",
                        )
                    )

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.raw_imports.append((alias.name, None, False, 0, self._in_type_checking))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module
        level = node.level or 0
        is_rel = level > 0
        for alias in node.names:
            self.raw_imports.append((mod, alias.name, is_rel, level, self._in_type_checking))


def resolve_python_import(
    source_file: str,
    module: Optional[str],
    symbol: Optional[str],
    is_relative: bool,
    level: int,
    file_universe: Set[str],
    known_package_roots: Set[str],
) -> Tuple[Optional[str], bool]:
    """Resolve a Python import against a closed universe of repository files.

    Returns:
        (resolved_target_file, is_local_candidate)
        If not a local candidate (e.g. stdlib / external), returns (None, False).
        If a local candidate but target is missing, returns (None, True).
        If a local candidate and target found, returns (target_path, True).
    """
    src_norm = source_file.replace("\\", "/")
    src_parts = src_norm.split("/")
    src_dir = "/".join(src_parts[:-1]) if len(src_parts) > 1 else ""

    if is_relative:
        # Relative import e.g. from .foo import bar, from ..baz import qux
        # level 1 = current directory, level 2 = parent directory
        base_dir_parts = src_parts[:-1]
        steps_up = level - 1
        if steps_up > len(base_dir_parts):
            return None, True

        target_dir_parts = base_dir_parts[: len(base_dir_parts) - steps_up] if steps_up > 0 else base_dir_parts
        base_path = "/".join(target_dir_parts)

        # 1. Try module as a file
        if module:
            mod_rel = module.replace(".", "/")
            candidate1 = f"{base_path}/{mod_rel}.py" if base_path else f"{mod_rel}.py"
            if candidate1 in file_universe:
                return candidate1, True
            candidate1_init = f"{base_path}/{mod_rel}/__init__.py" if base_path else f"{mod_rel}/__init__.py"
            if candidate1_init in file_universe:
                return candidate1_init, True

        # 2. Try symbol as a submodule in base_path (e.g. from . import foo)
        if symbol:
            candidate2 = f"{base_path}/{symbol}.py" if base_path else f"{symbol}.py"
            if candidate2 in file_universe:
                return candidate2, True
            candidate2_init = f"{base_path}/{symbol}/__init__.py" if base_path else f"{symbol}/__init__.py"
            if candidate2_init in file_universe:
                return candidate2_init, True

        return None, True

    # Absolute import
    if not module:
        return None, False

    top_root = module.split(".")[0]
    is_local = (top_root in known_package_roots) or (top_root not in KNOWN_EXTERNAL_ROOTS and src_dir == "")

    if not is_local:
        return None, False

    # Check candidate paths for local absolute import
    # e.g. fiofilter.read_receipt -> fiofilter/read_receipt.py or fiofilter/read_receipt/__init__.py
    mod_path = module.replace(".", "/")
    cand_file = f"{mod_path}.py"
    if cand_file in file_universe:
        return cand_file, True

    cand_init = f"{mod_path}/__init__.py"
    if cand_init in file_universe:
        return cand_init, True

    # If symbol is a submodule: e.g. from fiofilter import read_receipt
    if symbol:
        cand_sym_file = f"{mod_path}/{symbol}.py"
        if cand_sym_file in file_universe:
            return cand_sym_file, True
        cand_sym_init = f"{mod_path}/{symbol}/__init__.py"
        if cand_sym_init in file_universe:
            return cand_sym_init, True

    # Check relative to source_dir if top-level module matches sibling
    if src_dir:
        cand_sibling = f"{src_dir}/{mod_path}.py"
        if cand_sibling in file_universe:
            return cand_sibling, True

    return None, True


class PythonAstStructuralBackend:
    """Backend orchestrating AST extraction, graph resolution, and snapshot construction."""

    def __init__(self) -> None:
        self.identity = BACKEND_IDENTITY
        self.version = BACKEND_VERSION

    def build_snapshot_from_files(
        self,
        files_dict: Dict[str, str],
        repo_root: str,
        source_kind: SourceKind,
        git_head: Optional[str] = None,
        dirty_state: bool = False,
    ) -> StructuralSnapshot:
        """Construct a deterministic snapshot from an in-memory dictionary of file contents."""
        file_universe = {k.replace("\\", "/") for k in files_dict.keys()}
        file_graph = FileGraph()
        symbol_index = SymbolIndex()

        # Discover local package roots from directory structure
        package_roots: Set[str] = set()
        for f in file_universe:
            parts = f.split("/")
            if len(parts) > 1:
                package_roots.add(parts[0])
            else:
                stem = f.replace(".py", "")
                package_roots.add(stem)

        for f in file_universe:
            file_graph.add_node(f)

        health = GraphHealth()
        health.files_seen = len(file_universe)

        # First pass: parse AST and extract symbols & raw imports
        parsed_ast_data: Dict[str, PythonAstExtractor] = {}
        for f in sorted(file_universe):
            src_code = files_dict[f]
            try:
                tree = ast.parse(src_code, filename=f)
                extractor = PythonAstExtractor(f)
                extractor.visit(tree)
                parsed_ast_data[f] = extractor
                health.files_parsed += 1

                for sym in extractor.symbols:
                    symbol_index.add_symbol(sym)
            except Exception:
                health.parse_failures += 1

        # Second pass: resolve imports into graph edges
        for f, extractor in parsed_ast_data.items():
            for mod, sym, is_rel, level, is_tc in extractor.raw_imports:
                health.imports_seen += 1
                target_file, is_local = resolve_python_import(
                    source_file=f,
                    module=mod,
                    symbol=sym,
                    is_relative=is_rel,
                    level=level,
                    file_universe=file_universe,
                    known_package_roots=package_roots,
                )

                if is_local:
                    health.local_import_candidates += 1
                    if target_file and target_file in file_universe:
                        health.resolved_local_imports += 1
                        edge_type = ImportEdgeType.TYPE_CHECKING_IMPORT if is_tc else ImportEdgeType.RUNTIME_IMPORT
                        file_graph.add_edge(source=f, target=target_file, edge_type=edge_type, symbol=sym)
                    else:
                        health.unresolved_local_imports += 1

        # Deterministic snapshot hash
        hasher = hashlib.sha256()
        hasher.update(source_kind.value.encode("utf-8"))
        hasher.update((git_head or "").encode("utf-8"))
        hasher.update(str(dirty_state).encode("utf-8"))
        for f in sorted(file_universe):
            content_sha = hashlib.sha256(files_dict[f].encode("utf-8")).hexdigest()
            hasher.update(f"{f}:{content_sha}\n".encode("utf-8"))
        snapshot_id = f"snap-{hasher.hexdigest()[:16]}"

        limitations = [
            "Dynamic importlib imports cannot be resolved statically.",
            "Star imports (from x import *) cannot bind specific symbols.",
            "Type-checking imports are tracked but do not affect runtime execution.",
            "Non-Python files are excluded from this backend.",
        ]

        return StructuralSnapshot(
            snapshot_id=snapshot_id,
            source_kind=source_kind,
            repo_root=repo_root,
            git_head=git_head,
            dirty_state=dirty_state,
            backend=self.identity,
            backend_version=self.version,
            health=health,
            files=sorted(file_universe),
            file_graph=file_graph,
            symbol_index=symbol_index,
            limitations=limitations,
        )

    def build_snapshot_from_worktree(
        self,
        repo_root: pathlib.Path,
        file_universe_paths: Optional[List[str]] = None,
    ) -> StructuralSnapshot:
        """Build snapshot directly from active worktree files."""
        root = repo_root.resolve()
        files_dict: Dict[str, str] = {}

        if file_universe_paths is not None:
            candidate_paths = [p.replace("\\", "/") for p in file_universe_paths]
        else:
            candidate_paths = []
            for path in root.rglob("*.py"):
                rel_parts = set(path.relative_to(root).parts)
                if rel_parts.intersection(DEFAULT_EXCLUDE_PARTS):
                    continue
                candidate_paths.append(str(path.relative_to(root)).replace("\\", "/"))

        for rel_path in candidate_paths:
            full_path = root / rel_path
            if full_path.exists() and full_path.is_file():
                try:
                    files_dict[rel_path] = full_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

        # Check git provenance if git is available
        git_head: Optional[str] = None
        dirty_state = False
        try:
            head_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if head_proc.returncode == 0:
                git_head = head_proc.stdout.strip()

            status_proc = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if status_proc.returncode == 0 and status_proc.stdout.strip():
                dirty_state = True
        except Exception:
            pass

        return self.build_snapshot_from_files(
            files_dict=files_dict,
            repo_root=str(root),
            source_kind=SourceKind.WORKTREE,
            git_head=git_head,
            dirty_state=dirty_state,
        )

    def build_snapshot_from_git_commit(
        self,
        repo_root: pathlib.Path,
        commit_sha: str,
    ) -> StructuralSnapshot:
        """Build snapshot from an immutable Git commit using non-destructive Git plumbing.

        Never mutates or checks out the working tree.
        """
        root = repo_root.resolve()
        # 1. List files in commit using git ls-tree
        tree_proc = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", commit_sha],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if tree_proc.returncode != 0:
            raise RuntimeError(f"Failed to list tree for commit {commit_sha}: {tree_proc.stderr.strip()}")

        files_dict: Dict[str, str] = {}
        for line in tree_proc.stdout.splitlines():
            line_clean = line.strip().replace("\\", "/")
            if not line_clean.endswith(".py"):
                continue
            parts = set(line_clean.split("/"))
            if parts.intersection(DEFAULT_EXCLUDE_PARTS):
                continue

            # 2. Retrieve file content via git show <commit_sha>:<path>
            show_proc = subprocess.run(
                ["git", "show", f"{commit_sha}:{line_clean}"],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if show_proc.returncode == 0:
                files_dict[line_clean] = show_proc.stdout

        return self.build_snapshot_from_files(
            files_dict=files_dict,
            repo_root=str(root),
            source_kind=SourceKind.GIT_COMMIT,
            git_head=commit_sha,
            dirty_state=False,
        )
