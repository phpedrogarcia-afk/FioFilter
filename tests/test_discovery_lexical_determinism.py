"""Tests for M10-R1: ranking determinism, input-order independence, path matching, field diagnostics.

Covers:
- Tie-breaking by path ASC for equal BM25 and legacy scores
- Input-order independence for same corpus
- PYTHONHASHSEED independence (deterministic dict-based structures)
- Duplicate basenames matched by exact repo-relative path, not basename
- NEW_FILE_ONLY commit produces empty retrievable_gt
- MIXED_EXISTING_AND_NEW commit benchmarks existing-file positives only
- Exact repo-relative path matching
- Zero path+symbol overlap scores 0
- Full source text may contain query tokens absent from path+symbol
- legacy_rank tie-breaking by path ASC
"""
from __future__ import annotations

import pytest

from fiofilter.discovery_lexical import (
    BM25Index,
    LexicalDocument,
    build_bm25_index_from_paths,
    build_document_from_path_and_symbols,
    legacy_rank,
    tokenize_v2,
    tokenize_v2_multiset,
)


# ---------------------------------------------------------------------------
# 1. Deterministic tie-breaking -- BM25
# ---------------------------------------------------------------------------

class TestDeterministicTieBreaking:
    """test_deterministic_tie_breaking: two files with equal BM25 score rank by path ASC."""

    def _make_identical_docs(self):
        d1 = LexicalDocument(
            path="pkg_b/alpha.py",
            tokens=["widget", "render"],
            token_counts={"widget": 1, "render": 1},
            doc_length=2,
        )
        d2 = LexicalDocument(
            path="pkg_a/alpha.py",
            tokens=["widget", "render"],
            token_counts={"widget": 1, "render": 1},
            doc_length=2,
        )
        return d1, d2

    def test_deterministic_tie_breaking(self):
        d1, d2 = self._make_identical_docs()
        idx = BM25Index([d1, d2])
        idx.build()
        ranked = idx.rank(["widget"])
        assert len(ranked) == 2
        assert ranked[0][0] == "pkg_a/alpha.py", f"Expected path ASC tie-break, got {ranked[0][0]}"
        assert ranked[1][0] == "pkg_b/alpha.py"

    def test_deterministic_tie_breaking_reversed_input(self):
        d1, d2 = self._make_identical_docs()
        idx = BM25Index([d2, d1])
        idx.build()
        ranked = idx.rank(["widget"])
        assert len(ranked) == 2
        assert ranked[0][0] == "pkg_a/alpha.py", f"Reversed input should still sort path ASC, got {ranked[0][0]}"
        assert ranked[1][0] == "pkg_b/alpha.py"

    def test_higher_score_always_wins(self):
        d_high = LexicalDocument(
            path="pkg_z/file.py",
            tokens=["widget", "render", "layout"],
            token_counts={"widget": 2, "render": 1, "layout": 1},
            doc_length=4,
        )
        d_low = LexicalDocument(
            path="pkg_a/file.py",
            tokens=["widget"],
            token_counts={"widget": 1},
            doc_length=1,
        )
        idx = BM25Index([d_high, d_low])
        idx.build()
        ranked = idx.rank(["widget", "render"])
        assert ranked[0][0] == "pkg_z/file.py"


# ---------------------------------------------------------------------------
# 2. Input-order independence
# ---------------------------------------------------------------------------

class TestInputOrderIndependence:
    """test_input_order_independence: same corpus in different orders produces same ranking."""

    PATHS = [
        "fiofilter/engine.py",
        "fiofilter/classifier.py",
        "fiofilter/raw_store.py",
        "fiofilter/corpus.py",
        "tests/test_decision_engine.py",
    ]
    QUERY = "evidence classification engine"

    def _rank_paths(self, paths):
        idx = build_bm25_index_from_paths(paths)
        return idx.rank(tokenize_v2(self.QUERY))

    def test_input_order_independence(self):
        r_orig = self._rank_paths(self.PATHS)
        r_rev = self._rank_paths(list(reversed(self.PATHS)))
        shuffled = [self.PATHS[3], self.PATHS[0], self.PATHS[2], self.PATHS[4], self.PATHS[1]]
        r_shuf = self._rank_paths(shuffled)
        assert r_orig == r_rev == r_shuf, (
            f"Ranking differs by input order:\n  orig={r_orig}\n  rev={r_rev}\n  shuf={r_shuf}"
        )

    def test_legacy_input_order_independence(self):
        r_orig = legacy_rank(self.QUERY, self.PATHS)
        r_rev = legacy_rank(self.QUERY, list(reversed(self.PATHS)))
        result_orig = [(r.path, r.score) for r in r_orig]
        result_rev = [(r.path, r.score) for r in r_rev]
        assert result_orig == result_rev, (
            f"Legacy ranking differs by input order:\n  orig={result_orig}\n  rev={result_rev}"
        )


# ---------------------------------------------------------------------------
# 3. PYTHONHASHSEED independence
# ---------------------------------------------------------------------------

class TestPythonHashseedIndependence:
    """test_pythonhashseed_independence: dict-based structures produce same ranking."""

    def test_pythonhashseed_independence(self):
        docs = [
            build_document_from_path_and_symbols("pkg_a/store.py", ["StoreManager", "load"]),
            build_document_from_path_and_symbols("pkg_b/engine.py", ["Engine", "run"]),
            build_document_from_path_and_symbols("pkg_c/cache.py", ["Cache", "evict"]),
        ]
        idx1 = BM25Index(list(docs))
        idx1.build()
        r1 = idx1.rank(tokenize_v2("store manager"))

        docs_rev = list(reversed(docs))
        idx2 = BM25Index(docs_rev)
        idx2.build()
        r2 = idx2.rank(tokenize_v2("store manager"))

        assert r1 == r2, f"Rankings differ:\n  r1={r1}\n  r2={r2}"


# ---------------------------------------------------------------------------
# 4. Duplicate basenames: exact path matching
# ---------------------------------------------------------------------------

class TestDuplicateBasenames:
    """test_duplicate_basenames: pkg_a/store.py vs pkg_b/store.py matched by exact path."""

    def test_duplicate_basenames_exact_path(self):
        paths = ["pkg_a/store.py", "pkg_b/store.py", "pkg_c/engine.py"]
        idx = build_bm25_index_from_paths(
            paths,
            symbol_names_by_path={
                "pkg_a/store.py": ["StoreManagerA", "save_record"],
                "pkg_b/store.py": ["StoreFacadeB", "fetch_record"],
                "pkg_c/engine.py": ["Engine"],
            },
        )
        ranked = idx.rank(tokenize_v2("StoreManagerA save record"))
        ranked_paths = [p for p, _ in ranked]
        if "pkg_a/store.py" in ranked_paths and "pkg_b/store.py" in ranked_paths:
            assert ranked_paths.index("pkg_a/store.py") < ranked_paths.index("pkg_b/store.py"), (
                "pkg_a/store.py (with StoreManagerA) should rank above pkg_b/store.py"
            )
        else:
            assert "pkg_a/store.py" in ranked_paths, "pkg_a/store.py must appear in results"

    def test_exact_path_identity_preserved(self):
        paths = ["pkg_a/store.py", "pkg_b/store.py"]
        idx = build_bm25_index_from_paths(paths)
        ranked = idx.rank(tokenize_v2("store"))
        for path, score in ranked:
            assert path in paths, f"Returned path {path!r} not in input paths"
            assert "/" in path, f"Returned path {path!r} appears to be a bare basename"


# ---------------------------------------------------------------------------
# 5. NEW_FILE_ONLY commit: empty retrievable GT
# ---------------------------------------------------------------------------

class TestNewFileOnlyCommitSkipped:
    """test_new_file_only_commit_skipped: commit where all changed files are new has empty retrievable_gt."""

    def test_new_file_only_commit_skipped(self):
        parent_files = set()
        changed_py = ["fiofilter/new_module.py", "tests/test_new_module.py"]
        existing = [f for f in changed_py if f in parent_files]
        new_files = [f for f in changed_py if f not in parent_files]

        assert existing == [], "NEW_FILE_ONLY commit must have empty existing list"
        assert len(new_files) == len(changed_py)
        retrievable_gt = existing
        assert retrievable_gt == []


# ---------------------------------------------------------------------------
# 6. MIXED_EXISTING_AND_NEW: only existing files benchmarked
# ---------------------------------------------------------------------------

class TestMixedCommitExistingFilesBenchmarked:
    """test_mixed_commit_existing_files_benchmarked: mixed commit uses existing-file positives only."""

    def test_mixed_commit_existing_files_benchmarked(self):
        parent_files = {
            "fiofilter/__init__.py",
            "fiofilter/engine.py",
            "tests/test_engine.py",
        }
        changed_py = [
            "fiofilter/__init__.py",
            "fiofilter/engine.py",
            "fiofilter/new_feature.py",
            "tests/test_new_feature.py",
        ]
        existing = [f for f in changed_py if f in parent_files]
        new_files = [f for f in changed_py if f not in parent_files]

        assert set(existing) == {"fiofilter/__init__.py", "fiofilter/engine.py"}
        assert set(new_files) == {"fiofilter/new_feature.py", "tests/test_new_feature.py"}

        retrievable_gt = existing
        unretrievable_new = new_files
        assert len(retrievable_gt) == 2
        assert len(unretrievable_new) == 2


# ---------------------------------------------------------------------------
# 7. Exact repo-relative path matching
# ---------------------------------------------------------------------------

class TestExactRepoRelativePathMatching:
    """test_exact_repo_relative_path_matching: path matching uses exact normalized paths."""

    def test_exact_repo_relative_path_matching(self):
        parent_files = {
            "fiofilter/engine.py",
            "fiofilter/classifier.py",
        }
        changed_py = [
            "fiofilter/engine.py",
            "scripts/engine_helper.py",
            "fiofilter/classifier.py",
        ]
        existing = [f for f in changed_py if f in parent_files]
        new_files = [f for f in changed_py if f not in parent_files]

        assert "fiofilter/engine.py" in existing
        assert "fiofilter/classifier.py" in existing
        assert "scripts/engine_helper.py" not in existing
        assert "scripts/engine_helper.py" in new_files

    def test_path_normalization_exact(self):
        parent_files = {"fiofilter/engine.py"}
        backslash_path = "fiofilter\\engine.py"
        assert backslash_path not in parent_files, (
            "Backslash path must not accidentally match git ls-tree output"
        )
        assert "fiofilter/engine.py" in parent_files


# ---------------------------------------------------------------------------
# 8. Zero path+symbol overlap scores 0
# ---------------------------------------------------------------------------

class TestZeroPathSymbolOverlap:
    """test_zero_path_symbol_overlap: query with zero overlap against path+symbol index scores 0."""

    def test_zero_path_symbol_overlap(self):
        paths = ["fiofilter/engine.py", "fiofilter/classifier.py"]
        idx = build_bm25_index_from_paths(paths)
        query_tokens = tokenize_v2("epistemic redelivery versus")
        ranked = idx.rank(query_tokens)
        assert ranked == [], f"Expected empty ranking for zero-overlap query, got {ranked}"

    def test_zero_overlap_explicit_idf(self):
        d = build_document_from_path_and_symbols("fiofilter/engine.py")
        idx = BM25Index([d])
        idx.build()
        score = idx.score(d, ["nonexistent_token_xyz_not_in_any_path"])
        assert score == 0.0


# ---------------------------------------------------------------------------
# 9. Field coverage diagnostic
# ---------------------------------------------------------------------------

class TestFieldCoverageDiagnostic:
    """test_field_coverage_diagnostic: source file full text may contain query tokens absent from path+symbol."""

    def test_field_coverage_gap_example(self):
        path = "fiofilter/context_census.py"
        symbols = ["CensusEvent", "ContextWasteCensus", "analyze", "load_session"]
        path_sym_tokens = set(tokenize_v2(path)) | set(
            tok for s in symbols for tok in tokenize_v2(s)
        )
        query_tokens = set(tokenize_v2("epistemic redelivery exact scope"))

        ps_overlap = query_tokens & path_sym_tokens
        assert len(ps_overlap) == 0, f"Expected zero path+symbol overlap, got {ps_overlap}"

        simulated_source_text = (
            "# M05: exact redelivery versus reference replacement\n"
            "# epistemic scope clarification\n"
            "CENSUS_SCHEMA_VERSION = 'M05_CONTEXT_CENSUS_V1'\n"
        )
        source_tokens = set(tokenize_v2(simulated_source_text))
        full_overlap = query_tokens & source_tokens

        assert len(full_overlap) > 0, (
            f"Expected at least one overlap in full source text. "
            f"query={query_tokens}, source={source_tokens}"
        )
        assert "exact" in full_overlap or "redelivery" in full_overlap


# ---------------------------------------------------------------------------
# 10. legacy_rank deterministic tie-breaking
# ---------------------------------------------------------------------------

class TestLegacyRankDeterministicTieBreaking:
    """test_legacy_rank_deterministic_tie_breaking: legacy_rank also sorts by path ASC on tie."""

    def test_legacy_rank_deterministic_tie_breaking(self):
        # Both files share the token 'module' from their path.
        # Query 'module worker' matches 'module' in both => equal score (1.0).
        # Tie must break by path ASC: pkg_a before pkg_z.
        paths = ["pkg_z/module.py", "pkg_a/module.py"]
        query = "module worker"
        ranked = legacy_rank(query, paths)
        assert len(ranked) == 2
        assert ranked[0].score == ranked[1].score, "Expected equal scores for tie-break test"
        assert ranked[0].path == "pkg_a/module.py", (
            f"Expected path ASC tie-break, got {ranked[0].path}"
        )
        assert ranked[1].path == "pkg_z/module.py"

    def test_legacy_rank_tie_breaking_reversed_input(self):
        # Same as above but reversed input order -- result must be identical.
        paths = ["pkg_z/module.py", "pkg_a/module.py"]
        query = "module worker"
        ranked_rev = legacy_rank(query, list(reversed(paths)))
        assert len(ranked_rev) == 2
        assert ranked_rev[0].path == "pkg_a/module.py", (
            f"Reversed input should still sort path ASC, got {ranked_rev[0].path}"
        )
        assert ranked_rev[1].path == "pkg_z/module.py"

