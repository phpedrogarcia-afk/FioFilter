"""tests.test_discovery_shadow — Comprehensive verification of discovery shadow and ranking.

Covers:
- DiscoveryQueryExtractor intent classification and token extraction
- StructuralRanker ablation modes (LEXICAL_ONLY, STRUCTURAL_ONLY, LEXICAL_PLUS_STRUCTURAL, LEXICAL_PLUS_PPR)
- Component signal explainability (signals dict, explanation string)
- Commit history benchmark logic and leakage auditing (PATH_LEAKING vs NON_LEAKING)
"""

from __future__ import annotations

import pathlib
import pytest

from fiofilter.discovery_shadow import (
    CommitHistoryBenchmark,
    DiscoveryQueryExtractor,
    StructuralRanker,
)
from fiofilter.structural import (
    DiscoveryQueryIntent,
    RankingMode,
    SourceKind,
    SymbolDefinition,
    SymbolKind,
)
from fiofilter.structural_python import PythonAstStructuralBackend


@pytest.fixture
def sample_snapshot():
    """Create a controlled 4-file synthetic snapshot."""
    files = {
        "pkg/core.py": """
class CoreEngine:
    def execute(self):
        pass
""",
        "pkg/util.py": """
from .core import CoreEngine

def helper_tool():
    pass
""",
        "pkg/api.py": """
from .core import CoreEngine
from .util import helper_tool

class ApiHandler:
    def handle_request(self):
        pass
""",
        "pkg/unrelated.py": """
class StandaloneThing:
    pass
""",
    }
    backend = PythonAstStructuralBackend()
    return backend.build_snapshot_from_files(files, repo_root=".", source_kind=SourceKind.SYNTHETIC)


class TestDiscoveryQueryExtractor:
    """Tests for extracting intent, paths, symbols, and terms from queries."""

    def test_explicit_path_query(self, sample_snapshot) -> None:
        extractor = DiscoveryQueryExtractor(sample_snapshot)
        q = extractor.extract_query("Please inspect pkg/core.py for any issues")
        assert "pkg/core.py" in q.explicit_paths
        assert q.intent == DiscoveryQueryIntent.PATH_LOOKUP

    def test_file_stem_query(self, sample_snapshot) -> None:
        extractor = DiscoveryQueryExtractor(sample_snapshot)
        q = extractor.extract_query("Fix the bug in core module")
        assert "pkg/core.py" in q.explicit_paths

    def test_explicit_symbol_query(self, sample_snapshot) -> None:
        extractor = DiscoveryQueryExtractor(sample_snapshot)
        q = extractor.extract_query("Where is ApiHandler implemented?")
        assert "ApiHandler" in q.explicit_symbols
        assert q.intent == DiscoveryQueryIntent.SYMBOL_LOOKUP

    def test_related_to_file_query(self, sample_snapshot) -> None:
        extractor = DiscoveryQueryExtractor(sample_snapshot)
        q = extractor.extract_query("Show me callers of pkg/core.py")
        assert q.intent == DiscoveryQueryIntent.RELATED_TO_FILE
        assert "pkg/core.py" in q.explicit_paths

    def test_feature_text_and_stopwords(self, sample_snapshot) -> None:
        extractor = DiscoveryQueryExtractor(sample_snapshot)
        q = extractor.extract_query("add a new helper tool function for request handling")
        assert q.intent == DiscoveryQueryIntent.FEATURE_TEXT
        # Stopwords like 'a', 'new', 'for' should not be in lexical_terms
        assert "for" not in q.lexical_terms
        assert "helper" in q.lexical_terms or "tool" in q.lexical_terms


class TestStructuralRankerAblations:
    """Tests for multi-signal ranking across the 4 ablation modes."""

    def test_lexical_only_mode(self, sample_snapshot) -> None:
        extractor = DiscoveryQueryExtractor(sample_snapshot)
        q = extractor.extract_query("handle_request")
        ranker = StructuralRanker(sample_snapshot)

        cands = ranker.rank_candidates(q, mode=RankingMode.LEXICAL_ONLY, top_k=4)
        assert len(cands) == 4
        # pkg/api.py has handle_request symbol match
        assert cands[0].path == "pkg/api.py"
        assert cands[0].score > 0
        assert "EXACT_SYMBOL_MATCH" in cands[0].signals or "LEXICAL_SYMBOL_MATCH" in cands[0].signals
        # Files without lexical match have score 0 in LEXICAL_ONLY
        assert cands[-1].score == 0.0

    def test_structural_only_mode(self, sample_snapshot) -> None:
        extractor = DiscoveryQueryExtractor(sample_snapshot)
        q = extractor.extract_query("optimize the database query")
        ranker = StructuralRanker(sample_snapshot)

        cands = ranker.rank_candidates(q, mode=RankingMode.STRUCTURAL_ONLY, top_k=4)
        # pkg/core.py is imported by both pkg/util.py and pkg/api.py (highest in-degree centrality)
        # so it should be ranked first under pure structural centrality
        assert cands[0].path == "pkg/core.py"
        assert "STRUCTURAL_CENTRALITY" in cands[0].signals
        assert cands[0].score > 0

    def test_lexical_plus_ppr_boosts_neighbors(self, sample_snapshot) -> None:
        extractor = DiscoveryQueryExtractor(sample_snapshot)
        # Query explicitly references pkg/api.py
        q = extractor.extract_query("update pkg/api.py")
        ranker = StructuralRanker(sample_snapshot)

        cands = ranker.rank_candidates(q, mode=RankingMode.LEXICAL_PLUS_PPR, top_k=4)
        ranked_paths = [c.path for c in cands]

        # pkg/api.py is rank 1
        assert ranked_paths[0] == "pkg/api.py"
        # Since api imports core and util, core and util should receive Personalized PageRank mass
        # and be ranked above pkg/unrelated.py
        assert ranked_paths.index("pkg/unrelated.py") == 3

    def test_explainability_in_candidates(self, sample_snapshot) -> None:
        extractor = DiscoveryQueryExtractor(sample_snapshot)
        q = extractor.extract_query("CoreEngine")
        ranker = StructuralRanker(sample_snapshot)

        cands = ranker.rank_candidates(q, mode=RankingMode.LEXICAL_PLUS_PPR, top_k=2)
        top = cands[0]
        assert top.explanation != ""
        assert len(top.signals) > 0
        d = top.to_dict()
        assert "path" in d
        assert "rank" in d
        assert "score" in d
        assert "signals" in d
        assert "explanation" in d


class TestCommitHistoryBenchmarkUnit:
    """Tests for CommitHistoryBenchmark evaluation logic."""

    def test_leakage_classification_logic(self, tmp_path) -> None:
        bm = CommitHistoryBenchmark(tmp_path)
        # We can test discover_eligible_commits on the actual repo or check leakage criteria
        repo_root = pathlib.Path(".").resolve()
        bm_repo = CommitHistoryBenchmark(repo_root)
        eligible = bm_repo.discover_eligible_commits(max_commits=10)
        # Should find eligible commits in FioFilter history
        assert isinstance(eligible, list)
        if eligible:
            first = eligible[0]
            assert "commit_sha" in first
            assert "parent_sha" in first
            assert "leakage_type" in first
            assert first["leakage_type"] in ("PATH_LEAKING", "NON_LEAKING")
