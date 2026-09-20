"""Synthetic client events only: never start App Server or a model canary."""

import json

import pytest

from fiofilter.canary import CanarySession, _CanaryTurn, dynamic_tools
from fiofilter.read_receipt_ab import ABDelivery


CLASSES = (
    "BEHAVIORAL_CONCERN", "TASK_QUALITY_CONCERN", "SAFETY_CONCERN",
    "PROTOCOL_CONCERN", "OTHER",
)


class Client:
    def __init__(self):
        self.messages = []
        self.interrupts = []

    def send(self, message):
        self.messages.append(message)

    def send_request(self, method, params):
        self.interrupts.append((method, params))
        return 1


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "synthetic.txt"
    source.write_bytes(b"INERT_PRIVATE_PAYLOAD_SENTINEL\n" * 100)
    session = CanarySession(tmp_path, source, enabled=True, assessed_non_sensitive=True)
    client = Client()
    turn = _CanaryTurn(client, session, source.name)
    turn.thread_id, turn.turn_id = "thread", "turn"
    yield session, client, turn
    session.close()


def call(turn, tool, arguments):
    turn.handle({"id": 1, "method": "item/tool/call", "params": {
        "tool": tool, "arguments": arguments,
    }})


def record(session):
    return session.record(repository_id="local/inert", git_head="a" * 40,
                          tool_calls=None, account_usage={}, rate_limits={},
                          thread_usage={}, task_outcome="INTERRUPTED")


def test_abort_schema_requires_only_bounded_class():
    schema = next(t for t in dynamic_tools() if t["name"] == "fio_canary_abort")["inputSchema"]
    assert schema["required"] == ["anomaly_class"]
    assert set(schema["properties"]) == {"anomaly_class"}
    assert schema["properties"]["anomaly_class"] == {"type": "string", "enum": list(CLASSES)}
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("anomaly_class", CLASSES)
def test_model_reports_stop_immediately_without_proving_violation(setup, anomaly_class):
    session, client, turn = setup
    call(turn, "fio_canary_abort", {"anomaly_class": anomaly_class})
    r = record(session)
    assert r["schema_version"] == "FIO_READREF_CANARY_SESSION_V2"
    assert r["raw_only_reason"] == "REPORTED_ANOMALY"
    assert r["safety_gate_triggered"] is True
    assert r["confirmed_safety_violation"] is False
    assert r["anomaly_kind"] == "MODEL_REPORTED_ANOMALY"
    assert r["anomaly_source"] == "MODEL_REPORTED"
    assert r["anomaly_class"] == anomaly_class
    assert r["anomaly_phase"] == "BEFORE_READ"
    assert r["structural_event_trace"] == ["ANOMALY_REPORTED", "INTERRUPT_SENT"]
    assert client.interrupts == [("turn/interrupt", {"threadId": "thread", "turnId": "turn"})]
    assert session.harness.ephemeral_store.closed
    assert session.read().delivery is ABDelivery.RAW
    turn._interrupt()
    assert len(client.interrupts) == 1


@pytest.mark.parametrize("arguments", [
    {}, None, [], "INERT_FREE_TEXT", {"anomaly_class": "INERT_FREE_TEXT"},
    {"anomaly_class": ["OTHER"]}, {"anomaly_class": None},
    {"anomaly_class": "OTHER", "detail": "INERT_PRIVATE_DETAIL"},
    {"anomaly_class": "OTHER", "phase": "AFTER_RECOVERY"},
    {"anomaly_class": "OTHER", "source": "HARNESS_DETECTED"},
])
def test_invalid_model_arguments_rejected_but_still_stop(setup, arguments):
    session, client, turn = setup
    call(turn, "fio_canary_abort", arguments)
    assert client.messages[-1]["result"]["success"] is False
    assert len(client.interrupts) == 1
    r = record(session)
    assert r["raw_only_reason"] == "PROTOCOL_ANOMALY"
    assert r["anomaly_kind"] == "MACHINE_DETECTED_ANOMALY"
    assert r["anomaly_source"] == "CLIENT_DETECTED"
    assert r["anomaly_phase"] == "BEFORE_READ"
    assert "INERT_" not in json.dumps(r)


@pytest.mark.parametrize("stage,phase,after_ref,after_recovery", [
    (0, "BEFORE_READ", False, False), (1, "AFTER_RAW", False, False),
    (2, "AFTER_READREF", True, False), (3, "AFTER_RECOVERY", True, True),
    (4, "RAW_ONLY", True, True),
])
def test_abort_phase_comes_from_client_events(setup, stage, phase, after_ref, after_recovery):
    session, client, turn = setup
    if stage >= 1:
        call(turn, "fio_canary_read", {})
    if stage >= 2:
        call(turn, "fio_canary_read", {})
        reference = client.messages[-1]["result"]["contentItems"][0]["text"]
    if stage >= 3:
        call(turn, "fio_canary_expand", {"reference": reference})
        assert not client.interrupts
        assert record(session)["safety_gate_triggered"] is False
    if stage >= 4:
        call(turn, "fio_canary_read", {})
    call(turn, "fio_canary_abort", {"anomaly_class": "BEHAVIORAL_CONCERN"})
    r = record(session)
    assert (r["anomaly_phase"], r["abort_after_readref"], r["abort_after_recovery"]) == (
        phase, after_ref, after_recovery)
    expected = ["READ_RAW", "READREF_EMITTED", "RECOVERY_REQUESTED", "RECOVERY_SUCCEEDED"]
    if stage == 3:
        assert r["structural_event_trace"] == expected + ["ANOMALY_REPORTED", "INTERRUPT_SENT"]
    # Later fallback or a second anomaly must not overwrite the initiating stop.
    session.read()
    session.stop("APP_SERVER_ERROR")
    assert record(session)["anomaly_phase"] == phase
    assert record(session)["anomaly_class"] == "BEHAVIORAL_CONCERN"
    assert session.raw_only_reason == "REPORTED_ANOMALY"


def test_harness_integrity_detection_is_distinct_and_never_successful_recovery(setup):
    session, client, turn = setup
    call(turn, "fio_canary_read", {})
    call(turn, "fio_canary_read", {})
    reference = client.messages[-1]["result"]["contentItems"][0]["text"]
    session.harness.ephemeral_store._records.clear()
    call(turn, "fio_canary_expand", {"reference": reference})
    r = record(session)
    assert r["anomaly_source"] == "HARNESS_DETECTED"
    assert r["anomaly_kind"] == "MACHINE_DETECTED_ANOMALY"
    assert r["raw_only_reason"] == "RECOVERY_INTEGRITY_ERROR"
    assert r["abort_after_readref"] is True
    assert r["abort_after_recovery"] is False
    assert r["confirmed_safety_violation"] is False  # Rejection prevented delivery.
    assert "RECOVERY_SUCCEEDED" not in r["structural_event_trace"]
    assert len(client.interrupts) == 1


def test_trace_is_bounded_sanitized_and_record_is_a_snapshot(setup):
    session, client, turn = setup
    for _ in range(100):
        call(turn, "fio_canary_read", {})
    call(turn, "fio_canary_abort", {"anomaly_class": "OTHER"})
    r = record(session)
    assert len(r["structural_event_trace"]) == 64
    assert r["structural_event_trace_dropped"] > 0
    assert r["structural_event_trace"][-2:] == ["ANOMALY_REPORTED", "INTERRUPT_SENT"]
    assert set(r["structural_event_trace"]) <= {
        "READ_RAW", "READREF_EMITTED", "RAW_FALLBACK", "ANOMALY_REPORTED", "INTERRUPT_SENT"}
    serialized = json.dumps(r)
    for forbidden in ("INERT_PRIVATE_PAYLOAD", "synthetic.txt", str(session.repo), session.session_id):
        assert forbidden not in serialized
    r["structural_event_trace"].clear()
    assert len(record(session)["structural_event_trace"]) == 64


def test_interrupt_deferred_until_turn_id_without_weakening_stop(setup):
    session, client, turn = setup
    turn.turn_id = None
    call(turn, "fio_canary_abort", {"anomaly_class": "OTHER"})
    assert session.anomaly_stopped and session.harness.ephemeral_store.closed
    assert not client.interrupts
    turn.handle({"method": "turn/started", "params": {"turn": {"id": "later"}}})
    assert client.interrupts == [("turn/interrupt", {"threadId": "thread", "turnId": "later"})]
    assert record(session)["structural_event_trace"][-1] == "INTERRUPT_SENT"


@pytest.mark.parametrize("reason", [
    "RECOVERY_INTEGRITY_ERROR", "PROTOCOL_ANOMALY", "DESIGNATED_READ_BYPASS",
    "NON_UTF8_DELIVERY", "APP_SERVER_ERROR", "APPROVAL_REQUIRED", "TURN_NOT_COMPLETED",
])
def test_existing_machine_stops_keep_cleanup_and_raw_fallback(setup, reason):
    session, _, _ = setup
    session.read()
    session.read()
    session.stop(reason)
    r = record(session)
    assert r["raw_only_reason"] == reason
    assert r["safety_gate_triggered"] is True
    assert r["anomaly_kind"] == "MACHINE_DETECTED_ANOMALY"
    assert r["confirmed_safety_violation"] is False
    assert session.harness.ephemeral_store.closed
    assert session.harness.ephemeral_store.is_empty
    assert session.read().delivery is ABDelivery.RAW


def test_normal_reference_cap_is_not_a_safety_violation_or_abort(setup):
    session, client, turn = setup
    for _ in range(5):
        call(turn, "fio_canary_read", {})
    r = record(session)
    assert r["raw_only_reason"] == "MAX_READREF_REACHED"
    assert r["readref_emissions"] == 3
    assert r["safety_gate_triggered"] is False
    assert r["confirmed_safety_violation"] is False
    assert r["anomaly_source"] is None
    assert r["abort_after_readref"] is False
    assert not client.interrupts


def test_failed_interrupt_send_is_not_recorded_as_sent(setup):
    session, client, turn = setup

    def fail_send(*_args):
        raise OSError("INERT_TRANSPORT_DETAIL")

    client.send_request = fail_send
    with pytest.raises(OSError):
        call(turn, "fio_canary_abort", {"anomaly_class": "OTHER"})
    r = record(session)
    assert r["safety_gate_triggered"] is True
    assert r["structural_event_trace"] == ["ANOMALY_REPORTED"]
    assert "INERT_TRANSPORT_DETAIL" not in json.dumps(r)
    assert session.harness.ephemeral_store.closed
