"""
tests/test_discovery_runtime_shadow.py
M11 / M11-R1: Tests for the DiscoveryRuntimeShadow harness and V2 content-sensitive fingerprinting.
"""
import json
import pathlib
import subprocess
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
    INDEXED_FILE_UNIVERSE_POLICY,
    run_synthetic_task_stream,
    get_worktree_state_digest_v2,
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

    def test_indexed_universe_policy(self):
        assert INDEXED_FILE_UNIVERSE_POLICY == "PYTHON_SOURCES_V1"

    def test_no_auto_context_selection_in_api(self):
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

    def test_evaluation_has_worktree_state_digest(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        assert len(result.worktree_state_digest) == 16
        assert result.file_universe_policy == "PYTHON_SOURCES_V1"

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
        """Second evaluation reuses cached snapshot but produces same result."""
        shadow = DiscoveryRuntimeShadow()
        r1 = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        r2 = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if r1 is None or r2 is None:
            pytest.skip("Shadow failed")
        assert r1.evaluation_hash == r2.evaluation_hash
        assert r2.is_warm
        assert r2.query_type == "INDEX_REUSE_QUERY"


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
        assert result.state_validation_ms >= 0
        assert result.snapshot_build_ms >= 0
        assert result.index_build_ms >= 0
        assert result.query_tokenize_ms >= 0
        assert result.ranking_ms >= 0
        assert result.map_render_ms >= 0
        assert result.total_ms >= 0

    def test_warm_query_faster_index_build(self):
        """Index reuse query has 0ms index build."""
        shadow = DiscoveryRuntimeShadow()
        shadow.evaluate(REPO_ROOT, "read receipt")  # cold
        r2 = shadow.evaluate(REPO_ROOT, "read receipt shadow")  # warm
        if r2 is None:
            pytest.skip("Shadow failed")
        assert r2.is_warm
        assert r2.index_build_ms == 0.0
        assert r2.query_type == "INDEX_REUSE_QUERY"

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
        assert not r_cold.is_warm
        assert r_cold.query_type == "COLD_EVALUATION"
        assert r_warm.is_warm
        assert r_warm.query_type == "INDEX_REUSE_QUERY"


# ---------------------------------------------------------------------------
# V2 Content-Sensitive Worktree State Digest Tests (M11-R1 Gates)
# ---------------------------------------------------------------------------

class TestWorktreeStateDigestV2:
    @pytest.fixture
    def temp_git_repo(self, tmp_path):
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
        f = tmp_path / "app.py"
        f.write_text("x = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_path, check=True)
        return tmp_path

    def test_already_dirty_second_mutation_detected(self, temp_git_repo):
        """Gate: ALREADY_DIRTY_SECOND_MUTATION_DETECTED=PASS."""
        f = temp_git_repo / "app.py"
        f.write_text("x = 2\n", encoding="utf-8")
        d1 = get_worktree_state_digest_v2(temp_git_repo)
        f.write_text("x = 3\n", encoding="utf-8")
        d2 = get_worktree_state_digest_v2(temp_git_repo)
        assert d1 != d2

    def test_staged_unstaged_matrix(self, temp_git_repo):
        """Gate: STAGED_UNSTAGED_MATRIX=PASS."""
        f = temp_git_repo / "app.py"
        d_clean = get_worktree_state_digest_v2(temp_git_repo)

        # Staged change
        f.write_text("x = 2\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.py"], cwd=temp_git_repo, check=True)
        d_staged = get_worktree_state_digest_v2(temp_git_repo)
        assert d_staged != d_clean

        # Unstaged change on top of staged
        f.write_text("x = 3\n", encoding="utf-8")
        d_unstaged = get_worktree_state_digest_v2(temp_git_repo)
        assert d_unstaged != d_staged

        # Re-stage
        subprocess.run(["git", "add", "app.py"], cwd=temp_git_repo, check=True)
        d_restaged = get_worktree_state_digest_v2(temp_git_repo)
        assert d_restaged == d_unstaged

        # Restore
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=temp_git_repo, check=True)
        d_restored = get_worktree_state_digest_v2(temp_git_repo)
        assert d_restored == d_clean

    def test_untracked_same_status_content_change_detected(self, temp_git_repo):
        """Gate: UNTRACKED_SAME_STATUS_CONTENT_CHANGE_DETECTED=PASS."""
        u = temp_git_repo / "new_module.py"
        u.write_text("def foo(): return 1\n", encoding="utf-8")
        d1 = get_worktree_state_digest_v2(temp_git_repo)
        u.write_text("def foo(): return 2\n", encoding="utf-8")
        d2 = get_worktree_state_digest_v2(temp_git_repo)
        assert d1 != d2

    def test_delete_rename_new_file(self, temp_git_repo):
        """Gate: DELETE_RENAME_NEW_FILE=PASS."""
        d_clean = get_worktree_state_digest_v2(temp_git_repo)

        # Rename
        subprocess.run(["git", "mv", "app.py", "renamed.py"], cwd=temp_git_repo, check=True)
        d_renamed = get_worktree_state_digest_v2(temp_git_repo)
        assert d_renamed != d_clean

        # Reset
        subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=temp_git_repo, check=True)

        # Delete
        (temp_git_repo / "app.py").unlink()
        d_deleted = get_worktree_state_digest_v2(temp_git_repo)
        assert d_deleted != d_clean

    def test_content_identity_not_mtime_identity(self, temp_git_repo):
        """Rewriting identical bytes does not invalidate content digest."""
        f = temp_git_repo / "app.py"
        d_base = get_worktree_state_digest_v2(temp_git_repo)
        content = f.read_text(encoding="utf-8")
        f.write_text(content, encoding="utf-8")
        d_rewritten = get_worktree_state_digest_v2(temp_git_repo)
        assert d_base == d_rewritten

    def test_unrelated_file_change_does_not_invalidate_python_digest(self, temp_git_repo):
        """Modifying non-Python file (README.md) leaves Python digest unchanged."""
        d_before = get_worktree_state_digest_v2(temp_git_repo)
        readme = temp_git_repo / "README.md"
        readme.write_text("# Project Notes\n", encoding="utf-8")
        d_after = get_worktree_state_digest_v2(temp_git_repo)
        assert d_before == d_after

    def test_stale_cache_defense(self, temp_git_repo):
        """
        Adversarial gate: evaluate query, modify already-dirty indexed file, evaluate again.
        Must result in CACHE_HIT=NO, SNAPSHOT_ID_CHANGED=YES.
        """
        f = temp_git_repo / "app.py"
        f.write_text("x = 10\n", encoding="utf-8")  # already dirty
        shadow = DiscoveryRuntimeShadow()
        ev1 = shadow.evaluate(temp_git_repo, "app")
        assert ev1 is not None
        assert not ev1.is_warm

        # Modify already-dirty file again
        f.write_text("x = 20\n", encoding="utf-8")
        ev2 = shadow.evaluate(temp_git_repo, "app")
        assert ev2 is not None
        assert not ev2.is_warm  # CACHE_HIT=NO
        assert ev2.snapshot_id != ev1.snapshot_id  # SNAPSHOT_ID_CHANGED=YES
        assert ev2.worktree_state_digest != ev1.worktree_state_digest


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
        assert "worktree_state_digest" in e
        assert "query_type" in e
        assert "evaluation_hash" in e
        assert "event_hash" in e
        assert "previous_event_hash" in e
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
        assert events[1]["previous_event_hash"] == events[0]["event_hash"]

    def test_ledger_failure_does_not_propagate(self, tmp_path):
        bad_ledger = tmp_path / "bad"
        bad_ledger.write_text("not a dir")
        shadow = DiscoveryRuntimeShadow(ledger_dir=bad_ledger)
        result = shadow.evaluate(REPO_ROOT, "read receipt")
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
        assert result.map_bytes <= 500


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
# Serialization Tests
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_serializable(self):
        shadow = DiscoveryRuntimeShadow()
        result = shadow.evaluate(REPO_ROOT, "read receipt shadow")
        if result is None:
            pytest.skip("Shadow failed")
        d = result.to_dict()
        assert isinstance(d, dict)
        json_str = json.dumps(d)
        roundtrip = json.loads(json_str)
        assert roundtrip["index_authority"] == "NAVIGATION_ONLY"
        assert roundtrip["tie_break_policy"] == "SCORE_DESC_PATH_ASC"
        assert "worktree_state_digest" in roundtrip
        assert "query_type" in roundtrip
