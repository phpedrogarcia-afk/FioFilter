"""
tests/test_discovery_lexical.py
M10: Tests for the BM25-style lexical ranker.
"""
import pytest
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from fiofilter.discovery_lexical import (
    tokenize_v2,
    tokenize_v2_multiset,
    legacy_tokenize,
    build_document_from_path_and_symbols,
    build_bm25_index_from_paths,
    BM25Index,
    LexicalDocument,
    legacy_rank,
    LegacyLexicalScore,
    _BM25_K1,
    _BM25_B,
)


# ---------------------------------------------------------------------------
# Tokenization V2 tests
# ---------------------------------------------------------------------------

class TestTokenizeV2:
    def test_snake_case_splits_correctly(self):
        result = tokenize_v2("read_receipt_shadow")
        assert result == ["read", "receipt", "shadow"]

    def test_camel_case_splits_correctly(self):
        result = tokenize_v2("ReadReceiptShadow")
        assert result == ["read", "receipt", "shadow"]

    def test_pascal_case_splits_correctly(self):
        result = tokenize_v2("ContextWasteCensus")
        assert result == ["context", "waste", "census"]

    def test_path_separators_split(self):
        result = tokenize_v2("fiofilter/read_receipt.py")
        assert "fiofilter" in result
        assert "read" in result
        assert "receipt" in result
        assert "py" in result or "receipt" in result

    def test_stopwords_filtered(self):
        result = tokenize_v2("do not use the and or")
        for stopword in ["do", "not", "the", "and", "or"]:
            assert stopword not in result

    def test_short_tokens_filtered(self):
        # Threshold: len < 2 means single-char tokens are filtered
        result = tokenize_v2("a bb ccc dddd")
        assert "a" not in result   # 1-char: filtered
        assert "bb" in result      # 2-char: passes (threshold is < 2)
        assert "ccc" in result     # 3-char: passes

    def test_deduplicated(self):
        result = tokenize_v2("shadow shadow shadow")
        assert result.count("shadow") == 1

    def test_empty_string_returns_empty(self):
        assert tokenize_v2("") == []

    def test_none_like_empty(self):
        assert tokenize_v2("") == []

    def test_commit_message_tokenized(self):
        result = tokenize_v2("docs(m09): apply claim hygiene")
        assert "docs" in result or "m09" in result or "claim" in result

    def test_bm25_special_name_tokenized(self):
        result = tokenize_v2("BM25Index")
        assert "bm25" in result or "index" in result

    def test_mixed_separators(self):
        result = tokenize_v2("read-receipt_shadow.py")
        assert "read" in result
        assert "receipt" in result
        assert "shadow" in result


class TestTokenizeV2Multiset:
    def test_counts_repeated_tokens(self):
        result = tokenize_v2_multiset("read_receipt shadow receipt read")
        assert result.get("read", 0) == 2
        assert result.get("receipt", 0) == 2
        assert result.get("shadow", 0) == 1

    def test_empty_string_returns_empty(self):
        assert tokenize_v2_multiset("") == {}

    def test_all_counts_positive(self):
        result = tokenize_v2_multiset("runtime shadow harness")
        for count in result.values():
            assert count > 0


class TestTokenizeQueryCodeParity:
    """Query and code tokenization use the same normalization (V2 parity)."""

    def test_snake_query_matches_snake_code(self):
        """Query 'read receipt' should match tokens from 'fiofilter/read_receipt.py'."""
        query_toks = set(tokenize_v2("read receipt"))
        code_toks = set(tokenize_v2("fiofilter/read_receipt.py"))
        overlap = query_toks & code_toks
        assert len(overlap) >= 2

    def test_camel_query_matches_camel_code(self):
        """Query 'ReadReceipt' should match tokens from 'ReadReceiptEngine'."""
        query_toks = set(tokenize_v2("ReadReceipt"))
        code_toks = set(tokenize_v2("ReadReceiptEngine"))
        overlap = query_toks & code_toks
        assert "read" in overlap or "receipt" in overlap


# ---------------------------------------------------------------------------
# LexicalDocument tests
# ---------------------------------------------------------------------------

class TestLexicalDocument:
    def test_build_from_path(self):
        doc = build_document_from_path_and_symbols("fiofilter/store.py")
        assert doc.path == "fiofilter/store.py"
        assert doc.doc_length >= 0

    def test_build_with_symbols(self):
        doc = build_document_from_path_and_symbols(
            "fiofilter/read_receipt.py",
            ["ReadReceiptEngine", "build_read_receipt"]
        )
        assert "read" in doc.tokens or "receipt" in doc.tokens
        assert doc.doc_length > 0

    def test_doc_length_equals_sum_of_counts(self):
        doc = build_document_from_path_and_symbols(
            "fiofilter/runtime_shadow.py",
            ["RuntimeShadow", "ShadowCursor"]
        )
        assert doc.doc_length == sum(doc.token_counts.values())

    def test_unique_tokens_subset_of_multiset_keys(self):
        doc = build_document_from_path_and_symbols(
            "fiofilter/read_receipt.py",
            ["ReadReceiptEngine"]
        )
        assert set(doc.tokens) == set(doc.token_counts.keys())


# ---------------------------------------------------------------------------
# BM25Index tests
# ---------------------------------------------------------------------------

SAMPLE_PATHS = [
    "fiofilter/read_receipt.py",
    "fiofilter/store.py",
    "fiofilter/runtime_shadow.py",
    "tests/test_read_receipt.py",
    "fiofilter/context_census.py",
]

SAMPLE_SYMS = {
    "fiofilter/read_receipt.py": ["ReadReceiptEngine", "ReadReceipt", "build_read_receipt"],
    "fiofilter/store.py": ["RawStore", "BlobStore", "StoreEntry"],
    "fiofilter/runtime_shadow.py": ["RuntimeShadow", "ShadowCursor", "PassiveJsonlTailSource"],
    "tests/test_read_receipt.py": ["TestReadReceipt", "test_receipt_freshness"],
    "fiofilter/context_census.py": ["ContextWasteCensus", "CensusResult"],
}


class TestBM25Index:
    def test_build_from_paths(self):
        index = build_bm25_index_from_paths(SAMPLE_PATHS, SAMPLE_SYMS)
        assert index._built
        assert len(index.documents) == len(SAMPLE_PATHS)

    def test_frozen_weights(self):
        """BM25 V1 weights must remain frozen."""
        assert _BM25_K1 == 1.2
        assert _BM25_B == 0.75

    def test_rank_read_receipt_query(self):
        """'read receipt' query should rank read_receipt.py highly."""
        index = build_bm25_index_from_paths(SAMPLE_PATHS, SAMPLE_SYMS)
        query_toks = tokenize_v2("read receipt freshness")
        results = index.rank(query_toks, top_k=3)
        top_paths = [r[0] for r in results]
        assert "fiofilter/read_receipt.py" in top_paths or "tests/test_read_receipt.py" in top_paths

    def test_rank_shadow_query(self):
        """'runtime shadow' query should rank runtime_shadow.py highly."""
        index = build_bm25_index_from_paths(SAMPLE_PATHS, SAMPLE_SYMS)
        query_toks = tokenize_v2("runtime shadow harness")
        results = index.rank(query_toks, top_k=2)
        top_paths = [r[0] for r in results]
        assert "fiofilter/runtime_shadow.py" in top_paths

    def test_rank_scores_descending(self):
        """Scores must be in descending order."""
        index = build_bm25_index_from_paths(SAMPLE_PATHS, SAMPLE_SYMS)
        query_toks = tokenize_v2("read receipt shadow census")
        results = index.rank(query_toks)
        scores = [r[1] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_rank_scores_nonnegative(self):
        index = build_bm25_index_from_paths(SAMPLE_PATHS, SAMPLE_SYMS)
        query_toks = tokenize_v2("read receipt")
        results = index.rank(query_toks)
        for _, score in results:
            assert score >= 0.0

    def test_empty_query_returns_no_results(self):
        index = build_bm25_index_from_paths(SAMPLE_PATHS, SAMPLE_SYMS)
        results = index.rank([])
        assert results == []

    def test_top_k_limits_results(self):
        index = build_bm25_index_from_paths(SAMPLE_PATHS, SAMPLE_SYMS)
        query_toks = tokenize_v2("read receipt shadow store census")
        results = index.rank(query_toks, top_k=2)
        assert len(results) <= 2

    def test_unbuilt_index_raises(self):
        docs = [build_document_from_path_and_symbols("fiofilter/store.py")]
        index = BM25Index(documents=docs)
        with pytest.raises(RuntimeError, match="build"):
            index.rank(["store"])

    def test_empty_corpus_builds_cleanly(self):
        index = BM25Index(documents=[])
        index.build()
        results = index.rank(["anything"])
        assert results == []

    def test_idf_positive_for_rare_term(self):
        """IDF must be positive for terms appearing in fewer than all documents."""
        index = build_bm25_index_from_paths(SAMPLE_PATHS, SAMPLE_SYMS)
        # "census" appears only in context_census.py - should have high IDF
        idf_census = index.idf.get("census", 0.0)
        idf_read = index.idf.get("read", 0.0)
        assert idf_census > 0.0
        # A term in fewer docs has higher IDF than one in more docs
        assert idf_census >= idf_read

    def test_bm25_vs_legacy_different_ranking(self):
        """BM25 and legacy rankers may produce different rankings on the same corpus."""
        index = build_bm25_index_from_paths(SAMPLE_PATHS, SAMPLE_SYMS)
        query_toks = tokenize_v2("runtime shadow passive stream")
        bm25_top = [r[0] for r in index.rank(query_toks, top_k=3)]
        legacy_results = legacy_rank(
            "runtime shadow passive stream", SAMPLE_PATHS, SAMPLE_SYMS, top_k=3
        )
        legacy_top = [r.path for r in legacy_results]
        # Both should have runtime_shadow.py in top 3
        assert "fiofilter/runtime_shadow.py" in bm25_top
        assert "fiofilter/runtime_shadow.py" in legacy_top


# ---------------------------------------------------------------------------
# Legacy lexical ranker tests (M09 baseline preserved)
# ---------------------------------------------------------------------------

class TestLegacyRank:
    def test_returns_legacy_lexical_scores(self):
        results = legacy_rank("read receipt", SAMPLE_PATHS, SAMPLE_SYMS)
        assert all(isinstance(r, LegacyLexicalScore) for r in results)

    def test_read_receipt_ranked_by_overlap(self):
        results = legacy_rank("read receipt", SAMPLE_PATHS, SAMPLE_SYMS)
        paths = [r.path for r in results]
        assert "fiofilter/read_receipt.py" in paths

    def test_scores_descending(self):
        results = legacy_rank("read receipt shadow", SAMPLE_PATHS, SAMPLE_SYMS)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_empty_query_returns_empty(self):
        results = legacy_rank("", SAMPLE_PATHS, SAMPLE_SYMS)
        assert results == []

    def test_top_k_limits(self):
        results = legacy_rank("read receipt shadow census", SAMPLE_PATHS, SAMPLE_SYMS, top_k=2)
        assert len(results) <= 2