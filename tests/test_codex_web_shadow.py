"""M13 Codex Web shadow adapter safety and runtime-surface contract."""

import hashlib
import pathlib

import pytest

from fiofilter.codex_web_shadow import (
    Availability,
    CodexWebShadowEvent,
    CodexWebShadowEventAdapter,
    ToolFamily,
    census_codex_web_runtime,
)
from fiofilter.efficiency_feed import LiveEvidenceClass, hash_private_identifier


def _adapter(tmp_path, session="session-a"):
    return CodexWebShadowEventAdapter(
        session_id_hash=hash_private_identifier(session),
        run_id_hash=None,
        repository_id="phpedrogarcia-afk/FioFilter",
        repo_root=pathlib.Path(__file__).parents[1],
        git_head="9" * 40,
        worktree_fingerprint="a" * 64,
        live_evidence_class=LiveEvidenceClass.REAL_CODEX_PARTIAL_SESSION,
        start_time="2026-09-19T10:00:00Z",
    )


def _event(session="session-a", **changes):
    values = {
        "event_id_hash": hashlib.sha256(b"event-1").hexdigest(),
        "session_id_hash": hash_private_identifier(session),
        "timestamp": "2026-09-19T10:00:10Z",
        "tool_name": "exec_command",
        "tool_family": ToolFamily.OTHER,
        "output_size_bytes": 10,
        "output_sha256": hashlib.sha256(b"0123456789").hexdigest(),
        "exit_code": 0,
        "turn_index": None,
        "command": None,
        "repository_relative_path": None,
        "command_structurally_grounded": False,
        "single_producer": False,
        "truncated": None,
        "stream_identity": None,
    }
    values.update(changes)
    return CodexWebShadowEvent(**values)


def test_runtime_census_does_not_expose_raw_identifiers(tmp_path):
    census = census_codex_web_runtime(
        pathlib.Path(__file__).parents[1],
        environ={
            "CODEX_SESSION_ID": "secret-session-id",
            "CODEX_THREAD_ID": "secret-session-id",
            "CODEX_FLORA_CCA_BOOTSTRAP_ATTEMPT_ID": "attempt-id",
        },
        tool_protocol_observed=True,
        task_text_visible_to_agent=True,
        passive_event_surface_available=False,
    )
    encoded = census.to_json()
    assert "secret-session-id" not in encoded
    assert "attempt-id" not in encoded
    assert census.fields["SESSION_ID"] is Availability.EXACT_STRUCTURED
    assert census.fields["TASK_RUN_ID"] is Availability.NOT_AVAILABLE
    assert census.fields["BOOTSTRAP_ATTEMPT_ID"] is Availability.EXACT_STRUCTURED
    assert census.fields["TASK_QUERY"] is Availability.EXACT_UNSTRUCTURED
    assert census.fields["INPUT_TOKENS"] is Availability.NOT_AVAILABLE
    assert census.passive_event_surface_status == "UNAVAILABLE"


def test_event_adapter_is_post_observation_and_never_suppresses(tmp_path):
    adapter = _adapter(tmp_path)
    assert adapter.observe_after_delivery(_event()) is None
    record = adapter.build_feed_record("2026-09-19T10:01:00Z")
    assert record.tool_calls == 1
    assert record.tool_output_bytes == 10
    assert adapter.runtime_behavior_changed is False
    assert adapter.active_suppression is False
    assert adapter.auto_context_selection is False
    assert adapter.automatic_t02_applied == 0


def test_file_read_reuse_is_f1_only_and_session_scoped(tmp_path):
    adapter = _adapter(tmp_path)
    digest = hashlib.sha256(b"x" * 1000).hexdigest()
    first = _event(
        tool_family=ToolFamily.FILE_READ,
        output_size_bytes=1000,
        output_sha256=digest,
        command="cat fiofilter/v0.py",
        repository_relative_path="fiofilter/v0.py",
        command_structurally_grounded=True,
        single_producer=True,
    )
    second = _event(
        event_id_hash=hashlib.sha256(b"event-2").hexdigest(),
        tool_family=ToolFamily.FILE_READ,
        output_size_bytes=1000,
        output_sha256=digest,
        command="cat fiofilter/v0.py",
        repository_relative_path="fiofilter/v0.py",
        command_structurally_grounded=True,
        single_producer=True,
    )
    adapter.observe_after_delivery(first)
    adapter.observe_after_delivery(second)
    record = adapter.build_feed_record("2026-09-19T10:01:00Z")
    assert record.file_read_events == 2
    assert record.first_reads == 1
    assert record.repeated_source_view_reads == 1
    assert record.identical_reread_events == 1
    assert record.identical_reread_bytes == 1000
    assert record.f4_proven_events == 0
    assert record.read_reference_candidates == 1
    assert record.read_reference_hypothetical_bytes_avoided > 0

    other_session = _adapter(tmp_path, session="session-b")
    other_session.observe_after_delivery(_event(session="session-b", **{
        "tool_family": ToolFamily.FILE_READ,
        "output_size_bytes": 1000,
        "output_sha256": digest,
        "command": "cat fiofilter/v0.py",
        "repository_relative_path": "fiofilter/v0.py",
        "command_structurally_grounded": True,
        "single_producer": True,
    }))
    assert other_session.build_feed_record("2026-09-19T10:01:00Z").identical_reread_events == 0

    with pytest.raises(ValueError):
        adapter.observe_after_delivery(_event(session="session-b"))


def test_t02_metadata_gate_remains_without_stream_and_truncation_proof(tmp_path):
    adapter = _adapter(tmp_path)
    path = b"src/very/long/repeated/path/file.py"
    raw = b"".join(path + b":" + str(i).encode() + b":match\n" for i in range(1, 12))
    event = _event(
        tool_family=ToolFamily.SEARCH,
        output_size_bytes=len(raw),
        output_sha256=hashlib.sha256(raw).hexdigest(),
        command="rg -n match src",
        command_structurally_grounded=True,
        single_producer=True,
        truncated=None,
        stream_identity=None,
    )
    returned = adapter.observe_t02_after_delivery(event, raw)
    assert returned is raw
    record = adapter.build_feed_record("2026-09-19T10:01:00Z")
    assert record.t02_applicable_events == 0
    assert record.t02_rejected == 1
    assert adapter.automatic_t02_applied == 0


def test_t02_complete_evidence_is_hypothetical_and_raw_delivery_is_unchanged(tmp_path):
    adapter = _adapter(tmp_path)
    path = b"src/very/long/repeated/path/file.py"
    raw = b"".join(path + b":" + str(i).encode() + b":match\n" for i in range(1, 12))
    event = _event(
        tool_family=ToolFamily.SEARCH,
        output_size_bytes=len(raw),
        output_sha256=hashlib.sha256(raw).hexdigest(),
        command="rg -n match src",
        command_structurally_grounded=True,
        single_producer=True,
        truncated=False,
        stream_identity="combined",
    )
    returned = adapter.observe_t02_after_delivery(event, raw)
    assert returned is raw
    record = adapter.build_feed_record("2026-09-19T10:01:00Z")
    assert record.t02_applicable_events == 1
    assert record.t02_hypothetical_bytes_avoided > 0
    assert record.structurally_proven_rg_events == 1
    assert adapter.automatic_t02_applied == 0


def test_shadow_evaluator_failure_cannot_change_delivered_output(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path)
    raw = b"src/long/path/file.py:1:match\n" * 30
    event = _event(
        tool_family=ToolFamily.SEARCH,
        output_size_bytes=len(raw),
        output_sha256=hashlib.sha256(raw).hexdigest(),
        command="rg -n match src",
        command_structurally_grounded=True,
        single_producer=True,
        truncated=False,
        stream_identity="combined",
    )

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic observer failure")

    monkeypatch.setattr(adapter._t02, "evaluate", fail)
    returned = adapter.observe_t02_after_delivery(event, raw)
    assert returned is raw
    assert adapter.build_feed_record("2026-09-19T10:01:00Z").t02_rejected == 1


def test_discovery_requires_structured_task_text_and_persists_only_hash(tmp_path, monkeypatch):
    adapter = _adapter(tmp_path)
    sentinel = object()

    monkeypatch.setattr(adapter._discovery, "evaluate", lambda *args, **kwargs: sentinel)
    assert adapter.observe_discovery(
        "PRIVATE_PROMPT_SENTINEL",
        task_text_status=Availability.EXACT_UNSTRUCTURED,
    ) is None
    assert adapter.observe_discovery(
        "structured navigation terms",
        task_text_status=Availability.EXACT_STRUCTURED,
    ) is sentinel
    encoded = adapter.build_feed_record("2026-09-19T10:01:00Z").to_json()
    assert "structured navigation terms" not in encoded
    assert "PRIVATE_PROMPT_SENTINEL" not in encoded


def test_raw_prompt_and_t02_content_never_enter_feed_serialization(tmp_path):
    adapter = _adapter(tmp_path)
    prompt = "PRIVATE_PROMPT_SENTINEL"
    assert adapter.observe_discovery(
        prompt,
        task_text_status=Availability.EXACT_UNSTRUCTURED,
    ) is None
    raw = b"PRIVATE_FILE_CONTENT_SENTINEL"
    adapter.observe_t02_after_delivery(
        _event(
            tool_family=ToolFamily.SEARCH,
            output_size_bytes=len(raw),
            output_sha256=hashlib.sha256(raw).hexdigest(),
            command="rg -n sentinel src",
            command_structurally_grounded=True,
            single_producer=True,
            truncated=False,
            stream_identity="combined",
        ),
        raw,
    )
    encoded = adapter.build_feed_record("2026-09-19T10:01:00Z").to_json()
    assert prompt not in encoded
    assert raw.decode() not in encoded
