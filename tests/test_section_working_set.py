"""M16-PD2 deterministic section-routing and byte-accounting contract."""

from __future__ import annotations

import hashlib
from pathlib import Path

from scripts.section_working_set import select_sections


ROOT = Path(__file__).resolve().parents[1]

SECTION_SETS = {
    "B": {
        "docs/ARCHITECTURE.md": (
            "Pipeline",
            "Sensitivity and persistence",
            "Disk RAW store",
            "Metadata, batching and truncation",
            "Economics",
        ),
        "docs/EVIDENCE-CONTRACT.md": (
            "I1 — RAW immutability",
            "I2 — Transform linkage",
            "I3 — Byte-exact RAW recovery",
            "I5 — Unknown defaults to RAW",
            "I6 — Failure preservation",
            "I7 — Authority, security and sensitivity",
            "I13 — Source/batch identity",
            "I16 — Audit without secret harvesting",
        ),
    },
    "F": {
        "docs/M15-READREF-CONTROLLED-CANARY.md": (
            "Status and boundary",
            "Delivery and recovery",
            "Economics and telemetry",
            "D1 diagnostic hardening",
        ),
        "docs/M15-D1-CANARY-DIAGNOSTIC-HARDENING.md": (
            "Tool and record contracts",
            "Structural trace and privacy",
            "Unchanged safety and economics",
            "Validation and limits",
        ),
    },
    "G": {
        "docs/M15-S2-MISSION-CONTEXT-MANIFEST.md": (
            "Status",
            "Compact schema",
            "Economics and durable record",
            "Limits",
        ),
    },
    "H": {
        "docs/ARCHITECTURE.md": (
            "Pipeline",
            "Evidence policy and profiles",
            "Sensitivity and persistence",
            "Metadata, batching and truncation",
            "Economics",
        ),
        "docs/TEST-STRATEGY.md": (
            "Oracles",
            "CI and portability",
            "Limitations",
        ),
    },
}

ROUTE_DOCUMENT_BYTES_BEFORE = {
    "A": 7394,
    "B": 17741,
    "C": 17899,
    "D": 9838,
    "E": 9511,
    "F": 14113,
    "G": 13273,
    "H": 28631,
    "I": 0,
    "J": 0,
}

ROUTE_DOCUMENT_BYTES_AFTER = {
    "A": 7394,
    "B": 10187,
    "C": 17899,
    "D": 9838,
    "E": 9511,
    "F": 12480,
    "G": 11925,
    "H": 19885,
    "I": 0,
    "J": 0,
}


def _read(path: str) -> bytes:
    return (ROOT / path).read_bytes()


def _selected(path: str, headings: tuple[str, ...]) -> bytes:
    result = select_sections(_read(path), headings)
    assert result.fallback_required is False
    return result.content


def test_section_extraction_is_deterministic_and_exact() -> None:
    raw = _read("docs/ARCHITECTURE.md")
    headings = SECTION_SETS["H"]["docs/ARCHITECTURE.md"]
    first = select_sections(raw, headings)
    second = select_sections(raw, headings)

    assert first == second
    assert first.content.startswith(b"## Pipeline\n")
    assert first.full_document_bytes == 10347
    assert first.selected_bytes == 5428
    assert first.avoided_context_bytes == 4919


def test_nested_and_adjacent_sections_count_union_once() -> None:
    raw = b"# Root\nintro\n## A\na\n### Child\nc\n## B\nb\n## C\nc\n"

    nested = select_sections(raw, ("A", "Child"))
    adjacent = select_sections(raw, ("A", "B"))

    assert nested.content == b"## A\na\n### Child\nc\n"
    assert nested.selected_bytes == len(nested.content)
    assert adjacent.content == b"## A\na\n### Child\nc\n## B\nb\n"
    assert adjacent.selected_bytes == len(adjacent.content)


def test_missing_or_ambiguous_heading_falls_back_to_complete_document() -> None:
    raw = b"# Root\n## A\none\n## A\ntwo\n"

    missing = select_sections(raw, ("Missing",))
    ambiguous = select_sections(raw, ("A",))

    assert missing.content == raw
    assert missing.fallback_required is True
    assert missing.fallback_reason == "MISSING_HEADING:Missing"
    assert ambiguous.content == raw
    assert ambiguous.fallback_required is True
    assert ambiguous.fallback_reason == "AMBIGUOUS_HEADING:A"


def test_target_only_inside_backtick_fence_falls_back_as_missing_heading() -> None:
    raw = b"# Root\n```text\n## Target\n```\n"

    result = select_sections(raw, ("Target",))

    assert result.content == raw
    assert result.fallback_required is True
    assert result.fallback_reason == "MISSING_HEADING:Target"


def test_fenced_heading_does_not_truncate_real_selected_section() -> None:
    raw = (
        b"# Root\n## Target\nbefore\n```text\n## Not a boundary\n```\nafter\n"
        b"## Next\nnext\n"
    )

    result = select_sections(raw, ("Target",))

    assert result.fallback_required is False
    assert result.content == b"## Target\nbefore\n```text\n## Not a boundary\n```\nafter\n"


def test_real_and_fenced_same_title_is_not_ambiguous() -> None:
    raw = b"# Root\n## Target\nreal\n```text\n## Target\n```\n## Next\n"

    result = select_sections(raw, ("Target",))

    assert result.fallback_required is False
    assert result.content == b"## Target\nreal\n```text\n## Target\n```\n"


def test_tilde_fence_and_standard_indentation_hide_heading_like_text() -> None:
    raw = b"# Root\n## Target\nbefore\n   ~~~text\n## Not a boundary\n   ~~~\nafter\n## Next\n"

    result = select_sections(raw, ("Target",))

    assert result.fallback_required is False
    assert result.content == (
        b"## Target\nbefore\n   ~~~text\n## Not a boundary\n   ~~~\nafter\n"
    )


def test_unclosed_fence_falls_back_to_complete_document() -> None:
    raw = b"# Root\n## Target\n```text\n## Still code\n"

    result = select_sections(raw, ("Target",))

    assert result.content == raw
    assert result.fallback_required is True
    assert result.fallback_reason == "UNCLOSED_FENCE"


def test_uncertain_backtick_fence_syntax_falls_back_to_complete_document() -> None:
    raw = b"# Root\n```bad`info\n## Target\n```\n"

    result = select_sections(raw, ("Target",))

    assert result.content == raw
    assert result.fallback_required is True
    assert result.fallback_reason == "UNCERTAIN_FENCE_SYNTAX"


def test_declared_section_paths_and_headings_exist_exactly_once() -> None:
    orientation = _read("AI-START-HERE.md").decode("utf-8")
    for route, documents in SECTION_SETS.items():
        assert f"SECTION_SET {route}" in orientation
        for path, headings in documents.items():
            assert (ROOT / path).is_file()
            assert path in orientation
            raw = _read(path)
            result = select_sections(raw, headings)
            assert result.fallback_required is False
            for heading in headings:
                assert orientation.count(heading) >= 1


def test_route_document_accounting_matches_repository_bytes() -> None:
    before_paths = {
        "A": ("docs/EVIDENCE-CONTRACT.md",),
        "B": ("docs/ARCHITECTURE.md", "docs/EVIDENCE-CONTRACT.md"),
        "C": ("tests/corpus/README.md", "docs/M03-R3-CLEAN-SEARCH-CORPUS.md"),
        "D": ("docs/M11-DISCOVERY-RUNTIME-SHADOW.md",),
        "E": ("docs/M13-CODEX-WEB-LIVE-SHADOW.md",),
        "F": (
            "docs/M15-READREF-CONTROLLED-CANARY.md",
            "docs/M15-D1-CANARY-DIAGNOSTIC-HARDENING.md",
        ),
        "G": (
            "docs/M15-MISSION-CONTEXT-CONTRACT.md",
            "docs/M15-S2-MISSION-CONTEXT-MANIFEST.md",
        ),
        "H": (
            "docs/ARCHITECTURE.md",
            "docs/EVIDENCE-CONTRACT.md",
            "docs/SAFE-AGGRESSIVE-FRONTIER.md",
            "docs/TEST-STRATEGY.md",
        ),
        "I": (),
        "J": (),
    }
    measured_before = {
        route: sum(len(_read(path)) for path in paths)
        for route, paths in before_paths.items()
    }
    assert measured_before == ROUTE_DOCUMENT_BYTES_BEFORE

    measured_after = dict(measured_before)
    for route, documents in SECTION_SETS.items():
        for path, headings in documents.items():
            measured_after[route] -= len(_read(path))
            measured_after[route] += len(_selected(path, headings))
    assert measured_after == ROUTE_DOCUMENT_BYTES_AFTER


def test_route_h_sections_expose_every_critical_architecture_requirement() -> None:
    architecture = _selected(
        "docs/ARCHITECTURE.md", SECTION_SETS["H"]["docs/ARCHITECTURE.md"]
    )
    evidence = _read("docs/EVIDENCE-CONTRACT.md")
    frontier = _read("docs/SAFE-AGGRESSIVE-FRONTIER.md")
    testing = _selected(
        "docs/TEST-STRATEGY.md", SECTION_SETS["H"]["docs/TEST-STRATEGY.md"]
    )
    combined = architecture + evidence + frontier + testing

    required_exact_evidence = (
        b"Validate byte input and policy enums",
        b"DefaultProfile` is the upper bound",
        b"Unknown profiles return RAW",
        b"absence of a match is never a NON_SENSITIVE determination",
        b"bytes/4, not Unicode characters/4 or a tokenizer",
        b"bounded future-work record, not authorization",
        b"Visible T02 reconstruction",
    )
    for evidence_fragment in required_exact_evidence:
        assert evidence_fragment in combined


def test_router_is_discoverability_only_and_ledger_remains_on_demand() -> None:
    bootstrap = _read("AGENTS.md") + _read("AI-START-HERE.md")

    assert b"A router is discoverability, not evidence or authority" in bootstrap
    assert b"treat a successful lookup as proof/authority" in bootstrap
    assert b"It is not\na default full read" in bootstrap
    assert b"rg -n '^## ' docs/DECISIONS.md" in bootstrap


def test_bootstrap_byte_count_and_historical_ledger_prefix_are_exact() -> None:
    bootstrap_bytes = len(_read("AGENTS.md")) + len(_read("AI-START-HERE.md"))
    assert bootstrap_bytes == 11372

    historical_prefix_bytes = 107649
    historical_prefix_sha256 = (
        "21ad8e5ce60ba73dea6ab36552f28755472684f3cdfa16ef37a4308c429af10a"
    )
    ledger = _read("docs/DECISIONS.md")
    assert len(ledger) >= historical_prefix_bytes
    assert hashlib.sha256(ledger[:historical_prefix_bytes]).hexdigest() == (
        historical_prefix_sha256
    )


def test_quality_scenarios_have_deterministic_routes() -> None:
    orientation = _read("AI-START-HERE.md").decode("utf-8")
    expected = {
        "A": "transform correctness",
        "B": "sensitivity",
        "D": "ranking",
        "F": "READREF",
        "G": "Mission Context",
        "H": "Architecture proposal",
        "I": "supersession",
        "J": "documentation-only",
    }
    for route, phrase in expected.items():
        matching_rows = [
            line for line in orientation.splitlines() if line.startswith(f"| {route} |")
        ]
        assert len(matching_rows) == 1
        assert phrase in matching_rows[0]
