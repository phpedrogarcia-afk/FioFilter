"""M15 controlled active-canary gates; no model turn is started here."""

from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from fiofilter.canary import (
    AppServerError,
    CanarySession,
    CanaryStopError,
    _CanaryTurn,
    _command_reads_designated,
    account_observation,
    main,
    probe_account_support,
    rate_limit_observation,
    thread_usage_observation,
)
from fiofilter.read_receipt_ab import ABDelivery


def _source(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "source.txt"
    path.write_bytes(b"assessed non-sensitive source line\n" * 50)
    return path


def test_default_off_and_explicit_cli_gate(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = _source(tmp_path)
    session = CanarySession(tmp_path, source, assessed_non_sensitive=True)
    assert session.state == "OFF"
    assert session.read().delivery is ABDelivery.RAW
    assert session.read().delivery is ABDelivery.RAW
    assert session.readref_emissions == 0
    session.close()
    assert main([]) == 0
    assert "CANARY OFF" in capsys.readouterr().out
    assert main(["run"]) == 0
    assert "no Codex task started" in capsys.readouterr().out


def test_explicit_on_emits_no_more_than_three_references(tmp_path: pathlib.Path) -> None:
    source = _source(tmp_path)
    session = CanarySession(tmp_path, source, enabled=True, assessed_non_sensitive=True)
    assert session.state == "ACTIVE"
    assert session.read().delivery is ABDelivery.RAW
    results = [session.read() for _ in range(4)]
    assert [item.delivery for item in results] == [
        ABDelivery.READREF, ABDelivery.READREF, ABDelivery.READREF, ABDelivery.RAW
    ]
    assert session.readref_emissions == 3
    assert session.state == "RAW_ONLY"
    assert session.raw_only_reason == "MAX_READREF_REACHED"
    assert session.eligible_rereads >= 3
    assert session.raw_fallbacks == 1
    assert results[2].reference_text is not None
    assert session.expand(results[2].reference_text) == source.read_bytes()
    assert session.read().delivery is ABDelivery.RAW
    session.close()


def test_first_recovery_forces_raw_and_charges_exact_bytes(tmp_path: pathlib.Path) -> None:
    source = _source(tmp_path)
    session = CanarySession(
        tmp_path, source, enabled=True, assessed_non_sensitive=True,
        additional_context_bytes=17,
    )
    raw = session.read()
    repeat = session.read()
    assert repeat.reference_text is not None
    recovered = session.expand(repeat.reference_text)
    assert recovered == raw.payload
    assert session.state == "RAW_ONLY"
    assert session.raw_only_reason == "RECOVERY_TRIGGERED"
    assert session.read().delivery is ABDelivery.RAW
    assert session.readref_emissions == 1
    assert session.recovery_requests == 1
    assert session.recovery_bytes == len(raw.payload)
    assert session.raw_bytes_avoided_gross == len(raw.payload)
    assert session.reference_bytes == len(repeat.payload)
    assert session.net_visible_bytes_saved == -len(repeat.payload) - 17
    assert not session.economic_success
    session.close()


def test_recovery_integrity_error_stops_canary_raw_only(tmp_path: pathlib.Path) -> None:
    source = _source(tmp_path)
    session = CanarySession(tmp_path, source, enabled=True, assessed_non_sensitive=True)
    session.read()
    repeat = session.read()
    assert repeat.reference_text is not None
    assert repeat.decision is not None and repeat.decision.receipt_id is not None
    receipt = session.harness.ephemeral_store._records[repeat.decision.receipt_id]
    session.harness.ephemeral_store._records[receipt.receipt_id] = dataclasses.replace(
        receipt, content=b"corrupt"
    )
    with pytest.raises(CanaryStopError, match="READREF_RECOVERY_INTEGRITY_ERROR"):
        session.expand(repeat.reference_text)
    assert session.state == "RAW_ONLY"
    assert session.raw_only_reason == "RECOVERY_INTEGRITY_ERROR"
    assert session.read().delivery is ABDelivery.RAW
    session.close()
    assert session.harness.ephemeral_store.is_empty
    assert session.harness.ephemeral_store.closed


def test_cross_session_reference_cannot_recover_and_ephemeral_cleanup(tmp_path: pathlib.Path) -> None:
    source = _source(tmp_path)
    first = CanarySession(tmp_path, source, enabled=True, assessed_non_sensitive=True)
    second = CanarySession(tmp_path, source, enabled=True, assessed_non_sensitive=True)
    first.read()
    repeat = first.read()
    assert repeat.reference_text is not None
    with pytest.raises(CanaryStopError, match="UNISSUED_READREF"):
        second.expand(repeat.reference_text)
    assert second.raw_only_reason == "RECOVERY_INTEGRITY_ERROR"
    assert second.read().delivery is ABDelivery.RAW
    first.close()
    second.close()
    assert first.harness.ephemeral_store.is_empty
    assert second.harness.ephemeral_store.is_empty


def test_unknown_and_sensitive_assessment_fail_closed(tmp_path: pathlib.Path) -> None:
    source = _source(tmp_path)
    unknown = CanarySession(tmp_path, source, enabled=True)
    assert unknown.read().delivery is ABDelivery.RAW
    assert unknown.read().delivery is ABDelivery.RAW
    assert unknown.readref_emissions == 0
    assert unknown.harness.ephemeral_store.is_empty
    unknown.close()

    sensitive = tmp_path / "sensitive.txt"
    sensitive.write_bytes(b"api_key=INERT_EXAMPLE_VALUE\n" * 50)
    assessed = CanarySession(tmp_path, sensitive, enabled=True, assessed_non_sensitive=True)
    assert assessed.read().delivery is ABDelivery.RAW
    assert assessed.read().delivery is ABDelivery.RAW
    assert assessed.harness.ephemeral_store.is_empty
    assessed.close()


def test_session_record_is_sanitized_and_token_claims_are_noncausal(tmp_path: pathlib.Path) -> None:
    source = _source(tmp_path)
    session = CanarySession(
        tmp_path, source, enabled=True, assessed_non_sensitive=True,
        session_id="private-session-id", additional_context_bytes=11,
    )
    session.read()
    repeat = session.read()
    assert repeat.delivery is ABDelivery.READREF
    record = session.record(
        repository_id="local/example", git_head="a" * 40, tool_calls=2,
        account_usage=account_observation(
            {"summary": {"lifetimeTokens": 100}},
            {"summary": {"lifetimeTokens": 110}},
        ),
        rate_limits=rate_limit_observation(
            {"rateLimits": {"primary": {"usedPercent": 10}}},
            {"rateLimits": {"primary": {"usedPercent": 12}}},
        ),
        thread_usage=thread_usage_observation(
            {"tokenUsage": {"total": {"inputTokens": 15, "outputTokens": 3}}}
        ),
        task_outcome="COMPLETED",
    )
    serialized = json.dumps(record)
    assert "private-session-id" not in serialized
    assert str(tmp_path) not in serialized
    assert "assessed non-sensitive source line" not in serialized
    assert record["raw_bytes_avoided_gross"] == len(source.read_bytes())
    assert record["net_visible_bytes_saved"] == (
        record["raw_bytes_avoided_gross"] - record["reference_bytes"] - 11
    )
    assert record["account_token_activity_observation"]["delta_tokens"] == 10
    assert record["rate_limit_observation"]["delta_percentage_points"] == 2
    assert record["account_token_activity_observation"]["readref_causal"] is False
    assert record["thread_token_usage_observation"]["readref_causal"] is False
    assert record["readref_causal_token_savings"] == "UNAVAILABLE"
    session.close()


def test_telemetry_unavailable_is_explicit_and_probe_starts_no_task() -> None:
    assert account_observation(None, None)["status"] == "UNAVAILABLE"
    assert rate_limit_observation(None, None)["status"] == "UNAVAILABLE"
    assert thread_usage_observation(None)["status"] == "UNAVAILABLE"

    class UnavailableClient:
        def __init__(self, _cwd: pathlib.Path) -> None:
            self.methods: list[str] = []

        def __enter__(self) -> "UnavailableClient":
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def initialize(self) -> None:
            pass

        def request(self, method: str, **_kwargs: object) -> dict:
            self.methods.append(method)
            raise AppServerError("unavailable")

    result = probe_account_support(UnavailableClient)
    assert result["account_usage_read"] == "UNAVAILABLE"
    assert result["account_rate_limits_read"] == "UNAVAILABLE"
    assert result["model_turn_started"] == "NO"


def test_dynamic_tool_path_replaces_repeat_and_detects_anomaly(tmp_path: pathlib.Path) -> None:
    source = _source(tmp_path)
    session = CanarySession(tmp_path, source, enabled=True, assessed_non_sensitive=True)

    class FakeClient:
        def __init__(self) -> None:
            self.messages: list[dict] = []
            self.interrupts: list[tuple[str, dict]] = []

        def send(self, message: dict) -> None:
            self.messages.append(message)

        def send_request(self, method: str, params: dict) -> int:
            self.interrupts.append((method, params))
            return 99

    client = FakeClient()
    turn = _CanaryTurn(client, session, "source.txt")
    turn.thread_id = "thread"
    turn.turn_id = "turn"
    turn.handle({"id": 1, "method": "item/tool/call", "params": {"tool": "fio_canary_read", "arguments": {}}})
    turn.handle({"id": 2, "method": "item/tool/call", "params": {"tool": "fio_canary_read", "arguments": {}}})
    assert "assessed non-sensitive source line" in client.messages[0]["result"]["contentItems"][0]["text"]
    reference = client.messages[1]["result"]["contentItems"][0]["text"]
    assert reference.startswith("[[FIOFILTER:READREF:v1")
    turn.handle({"id": 3, "method": "item/tool/call", "params": {"tool": "fio_canary_expand", "arguments": {"reference": reference}}})
    turn.handle({"id": 4, "method": "item/tool/call", "params": {"tool": "fio_canary_read", "arguments": {}}})
    assert "assessed non-sensitive source line" in client.messages[3]["result"]["contentItems"][0]["text"]
    assert session.readref_emissions == 1
    assert session.state == "RAW_ONLY"
    assert not client.interrupts  # A successful recovery only switches to RAW.
    turn.handle({"id": 5, "method": "item/tool/call", "params": {"tool": "fio_canary_expand", "arguments": {"reference": "forged"}}})
    assert session.raw_only_reason == "RECOVERY_INTEGRITY_ERROR"
    assert client.interrupts[0][0] == "turn/interrupt"
    session.close()


def test_designated_read_bypass_detector_avoids_test_filename_false_positive() -> None:
    assert _command_reads_designated("Get-Content src/score.py", "src/score.py")
    assert _command_reads_designated("python -c 'open(\"score.py\")'", "src/score.py")
    assert not _command_reads_designated("python -m pytest tests/test_score.py -q", "src/score.py")


def test_non_utf8_delivery_stops_and_clears_receipts(tmp_path: pathlib.Path) -> None:
    source = tmp_path / "binary.txt"
    source.write_bytes(b"\xff" * 500)
    session = CanarySession(tmp_path, source, enabled=True, assessed_non_sensitive=True)

    class FakeClient:
        def __init__(self) -> None:
            self.messages: list[dict] = []
            self.interrupted = False

        def send(self, message: dict) -> None:
            self.messages.append(message)

        def send_request(self, _method: str, _params: dict) -> int:
            self.interrupted = True
            return 99

    client = FakeClient()
    turn = _CanaryTurn(client, session, "binary.txt")
    turn.thread_id = "thread"
    turn.turn_id = "turn"
    turn.handle({"id": 1, "method": "item/tool/call", "params": {"tool": "fio_canary_read", "arguments": {}}})
    assert client.messages[0]["result"]["success"] is False
    assert client.interrupted
    assert session.state == "RAW_ONLY"
    assert session.harness.ephemeral_store.is_empty
    session.close()
