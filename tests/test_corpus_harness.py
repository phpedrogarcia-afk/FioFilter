"""Material regressions for corpus provenance, replay, and extraction."""

import base64
import json
import pathlib
from types import SimpleNamespace

import pytest

import fiofilter.corpus as corpus_module
from fiofilter.corpus import (
    M03_V3_AS_HEURISTIC,
    CorpusEntry,
    CorpusHeuristicSuggestion,
    CorpusOracleLabels,
    CorpusSensitivityScreening,
    CorpusSourceData,
    load_corpus,
    replay_corpus,
    validate_corpus_entry,
)
from fiofilter.types import Disposition, EvidenceClass, Mode, Persistence, Sensitivity
from scripts.extract_codex_corpus import (
    classify_call_stratum,
    extract_session_corpus,
)


FIXTURE_PATH = pathlib.Path(__file__).parent / "corpus" / "fixtures" / "synthetic_corpus.jsonl"


def _source(content=b"test output", **kwargs):
    values = {
        "provenance": "test:mock",
        "command": "echo test",
        "exit_code": 0,
        "raw_content_b64": base64.b64encode(content).decode("ascii"),
        "byte_length": len(content),
    }
    values.update(kwargs)
    return CorpusSourceData(**values)


def _oracle(evidence_class="NOISE", **kwargs):
    values = {
        "evidence_class": evidence_class,
        "provenance": "GOLD",
        "reviewer_id": "test-reviewer",
        "review_protocol": "synthetic-unit-test-v1",
        "sensitivity": "NOT_SENSITIVE",
        "transform_eligibility": "RAW_REQUIRED",
        "oracle_rationale": "Synthetic unit-test label.",
    }
    values.update(kwargs)
    return CorpusOracleLabels(**values)


def _entry(content=b"test output", **kwargs):
    values = {
        "entry_id": "TEST-001",
        "source_data": _source(content),
        "oracle_labels": _oracle(),
        "sensitivity_screening": CorpusSensitivityScreening(result="NOT_RUN"),
    }
    values.update(kwargs)
    return CorpusEntry(**values)


class TestCorpusSchemaAndValidation:
    def test_valid_entry_passes_validation(self):
        assert validate_corpus_entry(_entry()) == []

    def test_missing_entry_id_fails_validation(self):
        entry = _entry(entry_id="")
        assert any("Missing entry_id" in error for error in validate_corpus_entry(entry))

    def test_missing_both_b64_and_path_fails(self):
        entry = _entry(
            source_data=CorpusSourceData(provenance="test:mock", byte_length=0)
        )
        errors = validate_corpus_entry(entry)
        assert any("exactly one of raw_content_b64 or raw_ref_path" in error for error in errors)

    def test_invalid_evidence_class_fails(self):
        entry = _entry(oracle_labels=_oracle("NON_EXISTENT_CLASS"))
        errors = validate_corpus_entry(entry)
        assert any("invalid oracle evidence_class" in error for error in errors)

    def test_unknown_fields_tolerated(self):
        data = {
            "schema_version": 4,
            "entry_id": "TEST-004",
            "source_data": {
                "provenance": "test:mock",
                "raw_content_b64": base64.b64encode(b"test").decode("ascii"),
                "byte_length": 4,
                "future_unrecognized_field": 12345,
            },
            "sensitivity_screening": {"result": "NOT_RUN"},
            "oracle_labels": {
                "evidence_class": "NOISE",
                "provenance": "GOLD",
                "reviewer_id": "test-reviewer",
                "review_protocol": "synthetic-unit-test-v1",
                "sensitivity": "NOT_SENSITIVE",
                "transform_eligibility": "RAW_REQUIRED",
                "extra_oracle_metadata": "ignored",
            },
            "new_v4_envelope_property": "tolerated",
        }
        entry = CorpusEntry.from_dict(data)
        assert entry.entry_id == "TEST-004"
        assert validate_corpus_entry(entry) == []

    def test_v3_is_rejected_without_explicit_migration(self):
        legacy = {
            "entry_id": "LEGACY-001",
            "source_data": {
                "provenance": "legacy",
                "raw_content_b64": base64.b64encode(b"legacy").decode("ascii"),
                "byte_length": 6,
            },
            "oracle_labels": {"evidence_class": "NOISE"},
        }
        with pytest.raises(ValueError, match="M03_V3_AS_HEURISTIC"):
            CorpusEntry.from_dict(legacy)

    def test_v3_migration_demotes_claimed_oracle_to_heuristic(self):
        legacy = {
            "entry_id": "LEGACY-002",
            "source_data": {
                "provenance": "legacy",
                "raw_content_b64": base64.b64encode(b"legacy").decode("ascii"),
                "byte_length": 6,
            },
            "oracle_labels": {
                "evidence_class": "NOISE",
                "sensitivity": "NOT_SENSITIVE",
                "transform_eligibility": "RAW_REQUIRED",
            },
        }
        entry = CorpusEntry.from_dict(legacy, migration=M03_V3_AS_HEURISTIC)
        assert entry.oracle_labels is None
        assert entry.heuristic_suggestion.method == "M03_V3_MIGRATED_HEURISTIC"
        assert entry.sensitivity_screening.result == "UNKNOWN"
        assert validate_corpus_entry(entry) == []

    def test_oracle_provenance_requires_reviewer_and_protocol(self):
        entry = _entry(
            oracle_labels=CorpusOracleLabels(
                evidence_class="NOISE",
                provenance="EXTRACTOR",
                reviewer_id="",
                review_protocol="",
            )
        )
        errors = validate_corpus_entry(entry)
        assert any("invalid oracle provenance" in error for error in errors)
        assert any("missing reviewer_id" in error for error in errors)
        assert any("missing review_protocol" in error for error in errors)

    def test_byte_length_mismatch_is_rejected(self):
        entry = _entry(source_data=_source(b"four", byte_length=99))
        assert any("does not match 4 source bytes" in error for error in validate_corpus_entry(entry))

    def test_both_inline_and_external_raw_sources_are_rejected(self, tmp_path):
        external = tmp_path / "raw.bin"
        external.write_bytes(b"test output")
        entry = _entry(
            source_data=_source(b"test output", raw_ref_path=str(external))
        )
        errors = validate_corpus_entry(entry)
        assert any("exactly one" in error for error in errors)

    def test_protected_evidence_cannot_be_labeled_safe_to_reduce(self):
        entry = _entry(
            oracle_labels=_oracle(
                "FAILURE",
                transform_eligibility="SAFE_TO_REDUCE",
                missed_opportunity_category="OTHER",
            )
        )
        assert any("protected evidence" in error for error in validate_corpus_entry(entry))

    def test_sensitive_oracle_cannot_be_labeled_safe_to_reduce(self):
        entry = _entry(
            oracle_labels=_oracle(
                sensitivity="SENSITIVE_SECRET",
                transform_eligibility="SAFE_TO_REDUCE",
                missed_opportunity_category="OTHER",
            )
        )
        assert any("sensitive material" in error for error in validate_corpus_entry(entry))


class TestCorpusLoader:
    def test_load_synthetic_corpus_fixtures(self):
        entries = load_corpus(FIXTURE_PATH)
        assert [entry.entry_id for entry in entries] == [
            "SYNTH-001",
            "SYNTH-002",
            "SYNTH-003",
            "SYNTH-004",
        ]
        assert all(entry.schema_version == 4 for entry in entries)

    def test_load_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_corpus(tmp_path / "does_not_exist.jsonl")

    def test_load_malformed_json_raises(self, tmp_path):
        path = tmp_path / "malformed.jsonl"
        path.write_text('{"entry_id": "broken", not_valid_json\n', encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed JSON"):
            load_corpus(path)

    def test_load_empty_corpus(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("# empty file with only comments\n\n", encoding="utf-8")
        assert load_corpus(path) == []


class TestExternalRawReferences:
    def test_external_raw_reference_file(self, tmp_path):
        content = b"External raw payload stored on disk"
        raw_file = tmp_path / "raw_payload.bin"
        raw_file.write_bytes(content)
        entry = _entry(
            source_data=CorpusSourceData(
                provenance="test:external_disk",
                raw_ref_path=str(raw_file),
                byte_length=len(content),
            )
        )
        assert validate_corpus_entry(entry) == []
        assert entry.source_data.get_bytes() == content

    def test_missing_external_path_raises_on_access(self, tmp_path):
        source = CorpusSourceData(
            provenance="test:missing",
            raw_ref_path=str(tmp_path / "missing.bin"),
            byte_length=1,
        )
        with pytest.raises(FileNotFoundError):
            source.get_bytes()


class TestCorpusReplayAndSafety:
    def test_deterministic_replay_on_synthetic_fixtures(self):
        entries1 = load_corpus(FIXTURE_PATH)
        entries2 = load_corpus(FIXTURE_PATH)
        evaluated1, summary1 = replay_corpus(entries1, mode=Mode.BUILD)
        evaluated2, summary2 = replay_corpus(entries2, mode=Mode.BUILD)
        assert len(evaluated1) == len(evaluated2) == 4
        assert summary1.total_raw_bytes == summary2.total_raw_bytes
        assert summary1.total_visible_bytes == summary2.total_visible_bytes
        gold1 = summary1.metrics_by_label_scope["ORACLE:GOLD"]
        gold2 = summary2.metrics_by_label_scope["ORACLE:GOLD"]
        assert gold1["dangerous_false_transform_eligibility"] == 0
        assert gold1 == gold2

    def test_sensitive_entry_triggers_do_not_persist(self):
        evaluated, summary = replay_corpus(load_corpus(FIXTURE_PATH), mode=Mode.BUILD)
        sensitive = next(entry for entry in evaluated if entry.entry_id == "SYNTH-004")
        assert sensitive.derived_metrics.predicted_disposition == "RAW"
        assert sensitive.derived_metrics.predicted_sensitivity == "SENSITIVE"
        assert summary.metrics_by_label_scope["ORACLE:GOLD"]["unsafe_sensitivity_leak"] == 0

    def test_oracle_independence(self):
        content = b"Building... [   OK   ]\n" * 100
        entry = _entry(
            content,
            oracle_labels=_oracle("CANONICAL_STATE", transform_eligibility="RAW_REQUIRED"),
        )
        evaluated, summary = replay_corpus([entry], mode=Mode.BUILD)
        result = evaluated[0]
        assert result.oracle_labels.evidence_class == "CANONICAL_STATE"
        assert result.derived_metrics.predicted_evidence_class == "NOISE"
        assert summary.metrics_by_label_scope["ORACLE:GOLD"][
            "dangerous_false_transform_eligibility"
        ] == 1

    def test_detector_no_match_is_not_non_sensitive_assessment(self):
        entry = _entry(
            sensitivity_screening=CorpusSensitivityScreening(
                result="DETECTOR_NO_MATCH", method="test-detector"
            )
        )
        assert entry.to_tool_result().sensitivity is Sensitivity.UNKNOWN
        assert entry.sensitivity_screening.result != "NOT_SENSITIVE"

    def test_replay_does_not_inject_oracle_sensitivity_or_inline_facts(self):
        content = b"Building... [   OK   ]\n" * 100
        entry = _entry(
            content,
            oracle_labels=_oracle(
                sensitivity="SENSITIVE_SECRET",
                inline_required_facts=["Building..."],
            ),
        )
        tool_result = entry.to_tool_result()
        assert tool_result.sensitivity is Sensitivity.UNKNOWN
        assert tool_result.inline_required_facts == []

    def test_inline_fact_occurrence_requirements_are_exact(self, monkeypatch):
        content = b"required fact\nrequired fact\n"
        entry = _entry(
            content,
            oracle_labels=_oracle(
                inline_required_facts=["required fact", "required fact"],
            ),
        )
        monkeypatch.setattr(
            corpus_module,
            "process",
            lambda *args, **kwargs: SimpleNamespace(
                content=b"required fact\n",
                disposition=Disposition.TRANSFORM,
                evidence_class=EvidenceClass.NOISE,
                sensitivity=Sensitivity.NON_SENSITIVE,
                persistence=Persistence.EPHEMERAL,
                transform_id="T01",
                policy_decision="synthetic",
                truncated=False,
            ),
        )
        evaluated, summary = replay_corpus([entry])
        scope = "ORACLE:GOLD"
        assert evaluated[0].derived_metrics.inline_facts_preserved_by_label_scope[scope] is False
        assert summary.metrics_by_label_scope[scope][
            "dangerous_false_transform_eligibility"
        ] == 1

    def test_metrics_are_partitioned_by_label_provenance(self):
        content = b"plain text"
        entry = _entry(
            content,
            heuristic_suggestion=CorpusHeuristicSuggestion(
                evidence_class="UNKNOWN",
                transform_eligibility="UNKNOWN",
                method="TEST_HEURISTIC",
            ),
        )
        evaluated, summary = replay_corpus([entry])
        assert set(summary.metrics_by_label_scope) == {
            "ORACLE:GOLD",
            "HEURISTIC:TEST_HEURISTIC",
        }
        assert set(evaluated[0].derived_metrics.comparison_by_label_scope) == set(
            summary.metrics_by_label_scope
        )


class TestExtractorBehavior:
    @staticmethod
    def _session_records():
        return [
            {"type": "session_meta", "payload": {"id": "session_synth"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "call_001",
                    "name": "exec",
                    "input": "tools.exec_command({cmd: 'git status'})",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call_001",
                    "output": [{"type": "input_text", "text": "On branch main\nnothing to commit"}],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "call_002",
                    "name": "exec",
                    "input": "tools.exec_command({cmd: 'pytest tests/'})",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call_002",
                    "output": [{"type": "input_text", "text": "5 passed, 0 failed in 0.2s"}],
                },
            },
        ]

    def test_extractor_on_synthetic_session(self, tmp_path):
        session_file = tmp_path / "synth_session.jsonl"
        output_file = tmp_path / "extracted_corpus.jsonl"
        session_file.write_text(
            "\n".join(json.dumps(record) for record in self._session_records()),
            encoding="utf-8",
        )
        summary = extract_session_corpus(
            session_path=session_file,
            output_path=output_file,
            sample_size=2,
            project_tag="SYNTH",
            filter_sensitive=True,
        )
        assert summary["total_calls_seen"] == 2
        assert summary["total_outputs_seen"] == 2
        assert summary["sample_size"] == 2
        extracted = load_corpus(output_file)
        assert [entry.entry_id for entry in extracted] == [
            "SYNTH-REAL-001",
            "SYNTH-REAL-002",
        ]
        assert all(entry.oracle_labels is None for entry in extracted)
        assert all(entry.heuristic_suggestion is not None for entry in extracted)
        assert all(
            entry.sensitivity_screening.result == "DETECTOR_NO_MATCH"
            for entry in extracted
        )

    def test_rg_files_precedes_generic_search_rule(self):
        assert classify_call_stratum("rg --files src", "src/a.py") == "dir_list"

    def test_zero_failed_is_test_success(self):
        assert (
            classify_call_stratum("pytest tests", "12 passed, 0 failed", exit_code=0)
            == "test_success"
        )

    def test_nonzero_exit_overrides_benign_test_text(self):
        assert (
            classify_call_stratum("pytest tests", "12 passed", exit_code=7)
            == "test_failure"
        )
