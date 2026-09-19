"""M13 Efficiency Feed v1 contract and aggregate arithmetic."""

from dataclasses import replace

import pytest

from fiofilter.efficiency_feed import (
    EFFICIENCY_FEED_SCHEMA_VERSION,
    EfficiencyFeedRecord,
    LiveEvidenceClass,
    MissionOutcomeClass,
    PathReadObservation,
    TokenMeasurement,
    TokenMeasurementQuality,
    WasteCandidateClass,
    aggregate_efficiency_feed,
    deserialize_feed_record,
    hash_private_identifier,
    serialize_feed_record,
)


def _record(session="session-a", evidence=LiveEvidenceClass.REAL_CODEX_PARTIAL_SESSION):
    return EfficiencyFeedRecord(
        session_id_hash=hash_private_identifier(session),
        run_id_hash=None,
        repository_id="phpedrogarcia-afk/FioFilter",
        git_head="9" * 40,
        worktree_fingerprint="a" * 64,
        model=None,
        start_time="2026-09-19T10:00:00Z",
        end_time="2026-09-19T10:01:00Z",
        task_hash="b" * 64,
        live_evidence_class=evidence,
        token_measurements={
            "input_tokens": TokenMeasurement.unavailable(),
            "output_tokens": TokenMeasurement(
                value=40,
                quality=TokenMeasurementQuality.PROVIDER_REPORTED_EXACT,
            ),
            "cached_input_tokens": TokenMeasurement(
                value=20,
                quality=TokenMeasurementQuality.ESTIMATED_BYTES_DIV_4,
                basis_bytes=80,
            ),
        },
        tool_output_bytes=120,
        tool_calls=2,
        turns_if_known=None,
        tool_output_bytes_by_family={"FILE_READ": 100, "GIT": 20},
        file_read_events=2,
        file_read_bytes=100,
        first_reads=1,
        repeated_source_view_reads=1,
        identical_reread_events=1,
        identical_reread_bytes=50,
        f4_proven_events=0,
        read_reference_candidates=1,
        read_reference_hypothetical_bytes_avoided=20,
        discovery_queries=0,
        first_target_read_position=None,
        t02_applicable_events=0,
        t02_no_economic_gain=0,
        t02_rejected=1,
        t02_hypothetical_bytes_avoided=0,
        corrective_rereads=0,
        mission_outcome_class=MissionOutcomeClass.PARTIAL,
        search_output_events=1,
        path_read_observations=(
            PathReadObservation(
                path_hash="c" * 64,
                repository_relative_path="fiofilter/v0.py",
                read_events=2,
                bytes_delivered=100,
            ),
        ),
        waste_candidate_counts={
            WasteCandidateClass.REEXPOSURE_WASTE_CANDIDATE.value: 1,
        },
    )


def test_token_provenance_requires_value_contract():
    with pytest.raises(ValueError):
        TokenMeasurement(value=1, quality=TokenMeasurementQuality.UNAVAILABLE)
    with pytest.raises(ValueError):
        TokenMeasurement(value=None, quality=TokenMeasurementQuality.RUNTIME_REPORTED_EXACT)
    with pytest.raises(ValueError):
        TokenMeasurement(value=2, quality=TokenMeasurementQuality.ESTIMATED_BYTES_DIV_4)


def test_missing_token_fields_are_explicitly_unavailable():
    record = _record()
    assert record.token_measurements["input_tokens"].quality is TokenMeasurementQuality.UNAVAILABLE
    assert record.token_measurements["input_tokens"].value is None


def test_required_token_classes_cannot_be_omitted():
    with pytest.raises(ValueError):
        replace(
            _record(),
            token_measurements={"input_tokens": TokenMeasurement.unavailable()},
        )


def test_feed_serialization_is_deterministic_and_contains_no_raw_payload_fields():
    record = _record()
    first = serialize_feed_record(record)
    second = serialize_feed_record(record)
    assert first == second
    assert first.endswith("\n")
    assert '"schema_version":"FIO_EFFICIENCY_FEED_V1"' in first
    assert "raw_prompt" not in first
    assert "file_content" not in first
    assert "authorization" not in first.lower()
    assert deserialize_feed_record(first) == record


def test_unknown_or_raw_payload_fields_are_rejected():
    data = _record().to_dict()
    data["raw_prompt"] = "must never persist"
    with pytest.raises(ValueError):
        EfficiencyFeedRecord.from_dict(data)


def test_feed_v1_rejects_any_active_behavior():
    with pytest.raises(ValueError):
        replace(_record(), active_suppression=True)
    with pytest.raises(ValueError):
        replace(_record(), automatic_t02_applied=1)


def test_feed_rejects_impossible_cross_metric_relationships():
    with pytest.raises(ValueError):
        replace(_record(), identical_reread_events=2)
    with pytest.raises(ValueError):
        replace(_record(), read_reference_hypothetical_bytes_avoided=51)
    with pytest.raises(ValueError):
        replace(_record(), structurally_proven_rg_events=2)


def test_absolute_or_parent_paths_are_rejected():
    with pytest.raises(ValueError):
        PathReadObservation("d" * 64, "/home/user/private.py", 1, 1)
    with pytest.raises(ValueError):
        PathReadObservation("d" * 64, "../private.py", 1, 1)
    with pytest.raises(ValueError):
        PathReadObservation("d" * 64, "src/private.py\nRAW_PROMPT", 1, 1)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("model", "PRIVATE PROMPT SENTINEL"),
        ("start_time", "PRIVATE_PROMPT_SENTINEL"),
        ("tool_output_bytes_by_family", {"PRIVATE_PROMPT_SENTINEL": 120}),
        (
            "token_measurements",
            {
                "input_tokens": TokenMeasurement.unavailable(),
                "output_tokens": TokenMeasurement.unavailable(),
                "cached_input_tokens": TokenMeasurement.unavailable(),
                "PRIVATE_PROMPT_SENTINEL": TokenMeasurement.unavailable(),
            },
        ),
    ],
)
def test_free_text_cannot_be_smuggled_through_controlled_fields(field, value):
    with pytest.raises(ValueError):
        replace(_record(), **{field: value})


def test_aggregate_keeps_exact_and_estimated_tokens_separate():
    first = _record("session-a")
    second = replace(
        _record("session-b", LiveEvidenceClass.CONTROLLED_LIVE_LAB),
        token_measurements={
            "input_tokens": TokenMeasurement(
                value=10,
                quality=TokenMeasurementQuality.RUNTIME_REPORTED_EXACT,
            ),
            "output_tokens": TokenMeasurement(
                value=12,
                quality=TokenMeasurementQuality.ESTIMATED_BYTES_DIV_4,
                basis_bytes=48,
            ),
            "cached_input_tokens": TokenMeasurement.unavailable(),
        },
        mission_outcome_class=MissionOutcomeClass.VERIFIED_COMPLETED,
    )
    aggregate = aggregate_efficiency_feed([first, second])

    assert aggregate["schema_version"] == "FIO_EFFICIENCY_FEED_V1_AGGREGATE"
    assert aggregate["sessions_analyzed"] == 2
    assert aggregate["token_totals_by_quality"]["output_tokens"] == {
        "ESTIMATED_BYTES_DIV_4": 12,
        "PROVIDER_REPORTED_EXACT": 40,
    }
    assert "combined_total" not in aggregate["token_totals_by_quality"]["output_tokens"]
    assert aggregate["tool_output_bytes"] == 240
    assert aggregate["tool_calls"] == 4
    assert aggregate["identical_reread_bytes"] == 100
    assert aggregate["repeated_source_view_reads"] == 2
    assert aggregate["f4_proven_events"] == 0
    assert aggregate["read_reference_hypothetical_bytes_avoided"] == 40
    assert aggregate["dominant_tool_families"][0] == {
        "family": "FILE_READ",
        "output_bytes": 200,
    }
    assert aggregate["live_evidence_class_counts"] == {
        "CONTROLLED_LIVE_LAB": 1,
        "REAL_CODEX_PARTIAL_SESSION": 1,
    }
    assert aggregate["t02_rejected"] == 2


def test_schema_version_is_fixed():
    assert EFFICIENCY_FEED_SCHEMA_VERSION == "FIO_EFFICIENCY_FEED_V1"
