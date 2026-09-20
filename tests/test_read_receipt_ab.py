"""M14 Read Receipt Behavioral A/B laboratory contract."""

from __future__ import annotations

import dataclasses
import hashlib
import pathlib

import pytest

from fiofilter.read_receipt import FreshnessLevel, ReadView, ReadViewType
from fiofilter.read_receipt_ab import (
    ABCondition,
    ABDelivery,
    ReadReceiptABHarness,
    RecoveryError,
)
from fiofilter.types import Sensitivity


def _large_file(tmp_path: pathlib.Path, name: str = "sample.txt") -> pathlib.Path:
    path = tmp_path / name
    path.write_bytes((b"stable exact non-sensitive fixture line\n") * 20)
    return path


def _treatment(tmp_path: pathlib.Path) -> ReadReceiptABHarness:
    return ReadReceiptABHarness(
        ABCondition.TREATMENT,
        session_id="m14-session",
        base_dir=tmp_path,
    )


def test_control_always_delivers_raw_even_after_f4(tmp_path: pathlib.Path) -> None:
    path = _large_file(tmp_path)
    harness = ReadReceiptABHarness(ABCondition.CONTROL, "m14-control", tmp_path)
    first = harness.read("one", path, call_index=1, sensitivity=Sensitivity.NON_SENSITIVE)
    repeat = harness.read("two", path, call_index=2, sensitivity=Sensitivity.NON_SENSITIVE)
    assert first.delivery is ABDelivery.RAW
    assert repeat.delivery is ABDelivery.RAW
    assert repeat.decision is not None
    assert repeat.decision.freshness_level is FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL


def test_treatment_first_raw_repeat_direct_f4_readref_and_exact_expand(tmp_path: pathlib.Path) -> None:
    path = _large_file(tmp_path)
    harness = _treatment(tmp_path)
    first = harness.read("one", path, call_index=1, sensitivity=Sensitivity.NON_SENSITIVE)
    repeat = harness.read("two", path, call_index=2, sensitivity=Sensitivity.NON_SENSITIVE)
    assert first.delivery is ABDelivery.RAW
    assert repeat.delivery is ABDelivery.READREF
    assert repeat.reference_text is not None
    expanded = harness.expand(repeat.reference_text)
    assert expanded == first.payload
    assert hashlib.sha256(expanded).hexdigest() == repeat.decision.delivered_sha256


def test_changed_source_and_changed_view_fail_to_raw(tmp_path: pathlib.Path) -> None:
    path = _large_file(tmp_path)
    harness = _treatment(tmp_path)
    harness.read("one", path, call_index=1, sensitivity=Sensitivity.NON_SENSITIVE)
    path.write_bytes((b"changed non-sensitive fixture line\n") * 20)
    changed = harness.read("two", path, call_index=2, sensitivity=Sensitivity.NON_SENSITIVE)
    assert changed.delivery is ABDelivery.RAW
    assert "hash mismatch" in changed.reason

    other_view = harness.read(
        "three",
        path,
        view=ReadView(ReadViewType.LINE_RANGE, start_line=1, end_line=2),
        call_index=3,
        sensitivity=Sensitivity.NON_SENSITIVE,
    )
    assert other_view.delivery is ABDelivery.RAW


def test_missing_receipt_cross_session_sensitive_and_no_expansion_are_raw(tmp_path: pathlib.Path) -> None:
    path = _large_file(tmp_path)
    harness = _treatment(tmp_path)
    harness.read("one", path, call_index=1, sensitivity=Sensitivity.NON_SENSITIVE)
    harness.ephemeral_store._records.clear()  # model a lost session receipt
    missing = harness.read("two", path, call_index=2, sensitivity=Sensitivity.NON_SENSITIVE)
    assert missing.delivery is ABDelivery.RAW
    assert missing.reason == "MISSING_OR_INVALID_RECEIPT_RAW"

    cross = harness.read("three", path, call_index=3, observed_session_id="other", sensitivity=Sensitivity.NON_SENSITIVE)
    assert cross.delivery is ABDelivery.RAW
    assert cross.reason == "CROSS_SESSION_REFERENCE_FORBIDDEN_RAW"

    sensitive = _treatment(tmp_path)
    secret_path = tmp_path / "sensitive.txt"
    secret_path.write_bytes(b"api_key=INERT_EXAMPLE_VALUE\n" * 20)
    # A caller's assessment cannot override the detector backstop.
    blocked = sensitive.read("four", secret_path, call_index=1, sensitivity=Sensitivity.NON_SENSITIVE)
    assert blocked.delivery is ABDelivery.RAW
    assert sensitive.ephemeral_store.is_empty

    tiny = tmp_path / "tiny.txt"
    tiny.write_bytes(b"tiny\n")
    small = _treatment(tmp_path)
    small.read("five", tiny, call_index=1, sensitivity=Sensitivity.NON_SENSITIVE)
    tiny_repeat = small.read("six", tiny, call_index=2, sensitivity=Sensitivity.NON_SENSITIVE)
    assert tiny_repeat.delivery is ABDelivery.RAW


def test_corrupt_receipt_cleanup_and_kill_switch(tmp_path: pathlib.Path) -> None:
    path = _large_file(tmp_path)
    harness = _treatment(tmp_path)
    harness.read("one", path, call_index=1, sensitivity=Sensitivity.NON_SENSITIVE)
    repeat = harness.read("two", path, call_index=2, sensitivity=Sensitivity.NON_SENSITIVE)
    assert repeat.reference_text is not None
    record = harness.ephemeral_store._records[repeat.decision.receipt_id]
    harness.ephemeral_store._records[record.receipt_id] = dataclasses.replace(record, content=b"corrupt")
    with pytest.raises(RecoveryError, match="READREF_LENGTH_MISMATCH|READREF_SHA256_MISMATCH"):
        harness.expand(repeat.reference_text)

    harness.close_session()
    assert harness.ephemeral_store.is_empty
    assert harness.ephemeral_store.closed
    assert harness.read("three", path, call_index=3, sensitivity=Sensitivity.NON_SENSITIVE).delivery is ABDelivery.RAW

    stopped = _treatment(tmp_path)
    stopped.set_kill_switch(True)
    stopped.read("four", path, call_index=1, sensitivity=Sensitivity.NON_SENSITIVE)
    assert stopped.read("five", path, call_index=2, sensitivity=Sensitivity.NON_SENSITIVE).delivery is ABDelivery.RAW


def test_net_accounting_subtracts_recovery_and_additional_context(tmp_path: pathlib.Path) -> None:
    path = _large_file(tmp_path)
    harness = _treatment(tmp_path)
    first = harness.read("one", path, call_index=1, sensitivity=Sensitivity.NON_SENSITIVE)
    repeat = harness.read("two", path, call_index=2, sensitivity=Sensitivity.NON_SENSITIVE)
    assert repeat.reference_text is not None
    harness.expand(repeat.reference_text)
    economics = harness.economics_for_repeat(len(first.payload), repeat, additional_context_bytes=11)
    assert economics.gross_visible_bytes_saved > 0
    assert economics.treatment_recovery_bytes == len(first.payload)
    assert economics.net_visible_bytes_saved == -repeat.reference_bytes - 11
    assert economics.estimated_context_token_equivalent_bytes_div_4 == economics.net_visible_bytes_saved / 4


def test_unknown_sensitivity_and_normal_runtime_authority_fail_closed(tmp_path: pathlib.Path) -> None:
    path = _large_file(tmp_path)
    harness = _treatment(tmp_path)
    assert harness.active_suppression_normal_runtime is False
    assert harness.automatic_activation is False
    first = harness.read("one", path, call_index=1)
    repeat = harness.read("two", path, call_index=2)
    assert first.delivery is ABDelivery.RAW
    assert repeat.delivery is ABDelivery.RAW
