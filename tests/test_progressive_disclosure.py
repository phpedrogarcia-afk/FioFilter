"""M16 progressive-disclosure bootstrap contract."""

from __future__ import annotations

import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _route_rows(orientation: str) -> dict[str, str]:
    rows = {}
    for line in orientation.splitlines():
        match = re.match(r"^\| ([A-J]) \|", line)
        if match:
            rows[match.group(1)] = line
    return rows


def test_default_bootstrap_is_bounded_and_decision_ledger_is_on_demand() -> None:
    agents = _read("AGENTS.md")
    orientation = _read("AI-START-HERE.md")

    assert "DEFAULT_BOOTSTRAP_DOCUMENTS=AGENTS.md,AI-START-HERE.md" in orientation
    assert "Do **not** read the complete decision ledger" in agents
    assert "rg -n '^## ' docs/DECISIONS.md" in orientation
    assert "It is not\na default full read" in orientation


def test_bootstrap_exposes_essential_invariants_before_routing() -> None:
    bootstrap = _read("AGENTS.md") + _read("AI-START-HERE.md")
    required = (
        "Evidence and capability never create authority",
        "UNKNOWN, nonzero exits",
        "Sensitive or declared-sensitive input is RAW",
        "RECOVERABLE != SAFE_TO_HIDE",
        "Mission Context is `SHADOW_ONLY`",
        "READREF is OFF/paused",
        "No active suppression",
        "not a\n  production-readiness claim",
        "Do not force-push, rewrite Git history, merge without authorization",
        "python -m pytest tests/ -v",
        "If required evidence is missing, contradictory or unavailable, stop or fail",
        "Preserve historical decisions and evidence unchanged and recoverable",
    )
    for invariant in required:
        assert invariant in bootstrap


def test_router_covers_required_scenarios_without_full_ledger() -> None:
    orientation = _read("AI-START-HERE.md")
    rows = _route_rows(orientation)

    assert set(rows) == set("ABCDEFGHIJ")
    expected = {
        "A": ("transform correctness", "docs/EVIDENCE-CONTRACT.md"),
        "B": ("sensitivity", "SECTION_SET B"),
        "C": ("Corpus", "docs/M03-R3-CLEAN-SEARCH-CORPUS.md"),
        "D": ("Discovery", "docs/M11-DISCOVERY-RUNTIME-SHADOW.md"),
        "E": ("Codex Web", "docs/M13-CODEX-WEB-LIVE-SHADOW.md"),
        "F": ("READREF", "SECTION_SET F"),
        "G": ("Mission Context", "SECTION_SET G"),
        "H": ("Architecture proposal", "SECTION_SET H"),
        "I": ("supersession", "decision lookup"),
        "J": ("documentation-only", "FULL_DOCUMENT"),
    }
    for route, fragments in expected.items():
        for fragment in fragments:
            assert fragment in rows[route]

    for routed_path in (
        "docs/ARCHITECTURE.md",
        "docs/M15-READREF-CONTROLLED-CANARY.md",
        "docs/M15-S2-MISSION-CONTEXT-MANIFEST.md",
        "docs/SAFE-AGGRESSIVE-FRONTIER.md",
    ):
        assert routed_path in orientation


def test_all_routed_markdown_documents_exist() -> None:
    orientation = _read("AI-START-HERE.md")
    paths = set(re.findall(r"`((?:docs|tests)/[^`]+\.md)`", orientation))

    assert paths
    assert all((ROOT / path).is_file() for path in paths)
