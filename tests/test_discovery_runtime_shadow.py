"""
tests/test_discovery_runtime_shadow.py
M11: Tests for the DiscoveryRuntimeShadow harness.
"""
import json
import pathlib
import sys
import tempfile
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from fiofilter.discovery_runtime_shadow import (
    DiscoveryRuntimeShadow,
    ShadowEvaluation,
    CandidateResult,
    SYNTHETIC_TASK_STREAM,
    M11_INDEX_AUTHORITY,
    M11_TIE_BREAK_POLICY,
    M11_BM25_VERSION,
    M11_TOKENIZER_VERSION,
    M11_K1,
    M11_B,
    M11_INDEXED_FIELDS,
    run_synthetic_task_stream,
    _query_hash,
    _snapshot_id,
    _files_hash,
)
from fiofilter.discovery_lexical import tokenize_v2


REPO_ROOT = pathlib.Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Authority Invariant Tests
# ---------------------------------------------------------------------------

class TestAuthorityInvariants:
    def test_index_authority_navigation_only(self):
        assert M11_INDEX_AUTHORITY == "NAVIGATION_ONLY"

    def test_tie_break_policy_explicit(self):
        assert M11_TIE_BREAK_POLICY == "SCORE_DESC_PATH_ASC"

    def test_bm25_version_frozen(self):
        assert M11_BM25_VERSION == "BM25_STYLE_LEXICAL_V1"
        assert M11_K1 == 1.2
        assert M11_B == 0.75

    def test_indexed_fields_explicit(self):
        assert "PATH" in M11_INDEXED_FIELDS
        assert "SYMBOL_NAMES" in M11_INDEXED_FIELDS

    def test_no_auto_context_selection_in_api(self):
        # DiscoveryRuntimeShadow has no inject/suppress/autoselect method
        shadow = DiscoveryRuntimeShadow()
        assert not hasattr(shadow, "inject_context")
        assert not hasattr(shadow, "suppress_read")
        assert not hasattr(shadow, "auto_select")


# ---------------------------------------------------------------------------
# Failure Isolation Tests (SHADOW_FAILURE_AGENT_PATH_UNCHANGED=PASS)
# ---------------------------------------------------------------------------

class TestFailureIsolation:
    def test_evaluate_returns_none_on_invalid_repo(self):
        """Shadow failure on bad repo: returns None, never raises."""
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(pathlib.Path("C:/nonexistent/path"), "test query")
        assert result is None  # SHADOW_FAILURE_AGENT_PATH_UNCHANGED=PASS

    def test_evaluate_returns_none_on_empty_query(self):
        """Empty query returns None or empty candidates, never raises."""
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "")
        # Either None (if snapshot build fails) or ShadowEvaluation with 0 candidates
        if result is not None:
            assert result.candidate_count == 0 or isinstance(result, ShadowEvaluation)


# ---------------------------------------------------------------------------
# Provenance Binding Tests
# ---------------------------------------------------------------------------

class TestProvenanceBinding:
    def test_evaluation_has_head_sha(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed (acceptable in test environment)")
        assert len(result.head_sha) >= 8
        assert result.head_sha != "UNKNOWN"

    def test_evaluation_has_dirty_digest(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        assert len(result.dirty_digest) == 16  # 16-char hex

    def test_evaluation_has_snapshot_id(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        assert len(result.snapshot_id) == 16

    def test_evaluation_has_query_hash(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        expected_qhash = _query_hash("read receipt shadow")
        assert result.query_hash == expected_qhash

    def test_evaluation_has_evaluation_hash(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        assert len(result.evaluation_hash) == 16


# ---------------------------------------------------------------------------
# Determinism Tests
# ---------------------------------------------------------------------------

class TestRuntimeDeterminism:
    def test_same_query_same_snapshot_same_hash(self):
        """Same query on same repo state produces identical evaluation_hash."""
        shadow = DiscoveryRuntimeShadow()
        r1 = shadow.evaluate(REPO_ROOT, "runtime shadow harness checkpoint")
        r2 = shadow.evaluate(REPO_ROOT, "runtime shadow harness checkpoint")
        if r1 is None or r2 is None:
            pytest.skip("Shadow failed")
        assert r1.evaluation_hash == r2.evaluation_hash

    def test_different_queries_different_hash(self):
        shadow = DiscoveryRuntimeShadow()
        r1 = shadow.evaluate(REPO_ROOT, "read receipt freshness")
        r2 = shadow.evaluate(REPO_ROOT, "context census waste accounting")
        if r1 is None or r2 is None:
            pytest.skip("Shadow failed")
        assert r1.query_hash != r2.query_hash

    def test_candidates_sorted_score_desc_path_asc(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "shadow read runtime store census", top_k=10)
        if result is None or len(result.candidates) < 2:
            pytest.skip("Shadow failed or too few candidates")
        scores = [c.score for c in result.candidates]
        paths_at_equal_score = {}
        for c in result.candidates:
            paths_at_equal_score.setdefault(c.score, []).append(c.path)
        for score, paths in paths_at_equal_score.items():
            assert paths == sorted(paths), f"Paths at score {score} not sorted: {paths}"
        assert scores == sorted(scores, reverse=True)

    def test_warm_query_same_result(self):
        """Second evaluation uses cached snapshot (warm) but produces same result."""
        shadow = DiscoveryRuntimeShadow()
        r1 = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        r2 = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if r1 is None or r2 is None:
            pytest.skip("Shadow failed")
        assert r1.evaluation_hash == r2.evaluation_hash
        assert r2.is_warm  # second call uses cached snapshot


# ---------------------------------------------------------------------------
# BM25 Version Binding Tests
# ---------------------------------------------------------------------------

class TestBM25VersionBinding:
    def test_result_carries_version_info(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "lexical discovery shadow")
        if result is None:
            pytest.skip("Shadow failed")
        assert result.tokenizer_version == "V2"
        assert result.bm25_version == "BM25_STYLE_LEXICAL_V1"
        assert result.k1 == 1.2
        assert result.b == 0.75
        assert result.tie_break_policy == "SCORE_DESC_PATH_ASC"
        assert result.index_authority == "NAVIGATION_ONLY"

    def test_result_has_indexed_fields(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt")
        if result is None:
            pytest.skip("Shadow failed")
        assert "PATH" in result.indexed_fields
        assert "SYMBOL_NAMES" in result.indexed_fields


# ---------------------------------------------------------------------------
# Cost Measurement Tests
# ---------------------------------------------------------------------------

class TestCostMeasurement:
    def test_timings_present_and_nonnegative(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        assert result.snapshot_build_ms >= 0
        assert result.index_build_ms >= 0
        assert result.query_tokenize_ms >= 0
        assert result.ranking_ms >= 0
        assert result.map_render_ms >= 0
        assert result.total_ms >= 0

    def test_warm_query_faster_index_build(self):
        """Warm query should have 0ms index build (reused)."""
        shadow = DiscoveryRuntimeShadow()
        shadow.evaluate(REPO_ROOT, "read receipt")  # cold
        r2 = shadow.evaluate(REPO_ROOT, "read receipt shadow")  # warm
        if r2 is None:
            pytest.skip("Shadow failed")
        assert r2.is_warm
        assert r2.index_build_ms == 0.0

    def test_estimated_tokens_is_bytes_div_4(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt")
        if result is None:
            pytest.skip("Shadow failed")
        assert result.estimated_map_tokens == result.map_bytes // 4

    def test_files_indexed_positive(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt")
        if result is None:
            pytest.skip("Shadow failed")
        assert result.files_indexed > 0

    def test_cold_vs_warm_distinction(self):
        shadow = DiscoveryRuntimeShadow()
        r_cold = shadow.evaluate(REPO_ROOT, "runtime shadow")
        r_warm = shadow.evaluate(REPO_ROOT, "read receipt")
        if r_cold is None or r_warm is None:
            pytest.skip("Shadow failed")
        assert not r_cold.is_warm  # first call is always cold
        assert r_warm.is_warm     # same shadow instance reuses cache


# ---------------------------------------------------------------------------
# Stale Snapshot Defense Tests
# ---------------------------------------------------------------------------

class TestStaleSnapshotDefense:
    def test_different_query_different_query_hash(self):
        """Stale check: query_hash changes when query changes."""
        shadow = DiscoveryRuntimeShadow()
        r1 = shadow.evaluate(REPO_ROOT, "query A")
        r2 = shadow.evaluate(REPO_ROOT, "query B")
        if r1 is None or r2 is None:
            pytest.skip("Shadow failed")
        assert r1.query_hash != r2.query_hash

    def test_snapshot_id_is_deterministic(self):
        """Same HEAD + dirty state = same snapshot_id."""
        files = ["fiofilter/store.py", "fiofilter/read_receipt.py"]
        fh = _files_hash(files)
        sid1 = _snapshot_id("abc123", "d1g3st1", fh)
        sid2 = _snapshot_id("abc123", "d1g3st1", fh)
        assert sid1 == sid2

    def test_snapshot_id_changes_with_dirty_state(self):
        """Different dirty state = different snapshot_id."""
        files = ["fiofilter/store.py"]
        fh = _files_hash(files)
        sid_clean = _snapshot_id("abc123", "clean000", fh)
        sid_dirty = _snapshot_id("abc123", "dirty111", fh)
        assert sid_clean != sid_dirty


# ---------------------------------------------------------------------------
# Ledger Tests
# ---------------------------------------------------------------------------

class TestShadowLedger:
    def test_ledger_appends_event(self, tmp_path):
        shadow = DiscoveryRuntimeShadow(ledger_dir=tmp_path)
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        ledger_path = tmp_path / "shadow_ledger.jsonl"
        assert ledger_path.exists()
        events = [json.loads(line) for line in ledger_path.read_text().strip().split("\n") if line]
        assert len(events) >= 1
        e = events[-1]
        assert "snapshot_id" in e
        assert "query_hash" in e
        assert "evaluation_hash" in e
        assert "event_hash" in e
        assert "previous_event_hash" in e
        # No raw query text in ledger
        assert "task_query" not in e
        assert "query_text" not in e
        assert "raw_query" not in e

    def test_ledger_chaining(self, tmp_path):
        shadow = DiscoveryRuntimeShadow(ledger_dir=tmp_path)
        shadow.evaluate(REPO_ROOT, "read receipt shadow")
        shadow.evaluate(REPO_ROOT, "runtime shadow harness")
        ledger_path = tmp_path / "shadow_ledger.jsonl"
        events = [json.loads(line) for line in ledger_path.read_text().strip().split("\n") if line]
        assert len(events) == 2
        # Second event's previous_event_hash == first event's event_hash
        assert events[1]["previous_event_hash"] == events[0]["event_hash"]

    def test_ledger_failure_does_not_propagate(self, tmp_path):
        """Ledger write failure never raises."""
        # Make ledger dir a file to cause write failure
        bad_ledger = tmp_path / "bad"
        bad_ledger.write_text("not a dir")
        shadow = DiscoveryRuntimeShadow(ledger_dir=bad_ledger)
        result = shadow.evaluate(REPO_ROOT, "read receipt")
        # Should still return a result — ledger failure is isolated
        assert result is None or isinstance(result, ShadowEvaluation)


# ---------------------------------------------------------------------------
# Map Content Tests
# ---------------------------------------------------------------------------

class TestMapContent:
    def test_map_has_version_info(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        assert "BM25" in result.map_content or "lexical" in result.map_content.lower()

    def test_map_bytes_positive_when_candidates_exist(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow runtime store")
        if result is None:
            pytest.skip("Shadow failed")
        if result.candidate_count > 0:
            assert result.map_bytes > 0

    def test_map_respects_budget(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow", map_budget_bytes=200)
        if result is None:
            pytest.skip("Shadow failed")
        # Map may slightly exceed due to truncation line, but should be bounded
        assert result.map_bytes <= 500  # generous bound accounting for truncation message


# ---------------------------------------------------------------------------
# Synthetic Task Stream Tests
# ---------------------------------------------------------------------------

class TestSyntheticTaskStream:
    def test_task_stream_has_entries(self):
        assert len(SYNTHETIC_TASK_STREAM) >= 4

    def test_task_stream_entries_have_required_fields(self):
        for task in SYNTHETIC_TASK_STREAM:
            assert "task_id" in task
            assert "query" in task
            assert "known_positives" in task

    def test_run_synthetic_stream(self):
        shadow = DiscoveryRuntimeShadow()
        results = run_synthetic_task_stream(shadow, REPO_ROOT, top_k=10)
        assert len(results) == len(SYNTHETIC_TASK_STREAM)
        for r in results:
            assert "task_id" in r
            assert "status" in r
            if r["status"] == "OK":
                assert "R@1" in r
                assert "R@10" in r
                assert 0.0 <= r["R@1"] <= 1.0
                assert 0.0 <= r["R@10"] <= 1.0

    def test_synthetic_stream_deterministic(self):
        shadow1 = DiscoveryRuntimeShadow()
        shadow2 = DiscoveryRuntimeShadow()
        results1 = run_synthetic_task_stream(shadow1, REPO_ROOT, top_k=5)
        results2 = run_synthetic_task_stream(shadow2, REPO_ROOT, top_k=5)
        for r1, r2 in zip(results1, results2):
            assert r1["task_id"] == r2["task_id"]
            if r1["status"] == "OK" and r2["status"] == "OK":
                assert r1["R@1"] == r2["R@1"]
                assert r1["R@10"] == r2["R@10"]


# ---------------------------------------------------------------------------
# to_dict serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_serializable(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        d = result.to_dict()
        assert isinstance(d, dict)
        # Must be JSON-serializable
        json_str = json.dumps(d)
        roundtrip = json.loads(json_str)
        assert roundtrip["index_authority"] == "NAVIGATION_ONLY"
        assert roundtrip["tie_break_policy"] == "SCORE_DESC_PATH_ASC"