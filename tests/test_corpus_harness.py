"""
tests/test_corpus_harness.py — Tests for the empirical corpus harness.

Verifies:
  - Schema validation & constraints
  - Loader behavior (valid, empty, malformed, unknown fields)
  - External raw references
  - Non-persistence of sensitive data
  - Deterministic replay & derived metrics
  - Oracle independence
  - Extractor behavior on synthetic session log
"""

import base64
import json
import pathlib
import pytest

from fiofilter.corpus import (
    CorpusDerivedMetrics,
    CorpusEntry,
    CorpusOracleLabels,
    CorpusSourceData,
    load_corpus,
    replay_corpus,
    validate_corpus_entry,
)
from fiofilter.types import Mode, Persistence, Sensitivity
from scripts.extract_codex_corpus import extract_session_corpus


FIXTURE_PATH = pathlib.Path(__file__).parent / "corpus" / "fixtures" / "synthetic_corpus.jsonl"


class TestCorpusSchemaAndValidation:
    def test_valid_entry_passes_validation(self):
        entry = CorpusEntry(
            entry_id="TEST-001",
            source_data=CorpusSourceData(
                provenance="test:mock",
                command="echo test",
                exit_code=0,
                raw_content_b64=base64.b64encode(b"test output").decode("ascii"),
                byte_length=11,
            ),
            oracle_labels=CorpusOracleLabels(
                evidence_class="NOISE",
                sensitivity="NOT_SENSITIVE",
                transform_eligibility="SAFE_TO_REDUCE",
                oracle_rationale="Mock test noise",
            ),
        )
        errors = validate_corpus_entry(entry)
        assert errors == []

    def test_missing_entry_id_fails_validation(self):
        entry = CorpusEntry(
            entry_id="",
            source_data=CorpusSourceData(
                provenance="test:mock",
                raw_content_b64=base64.b64encode(b"test").decode("ascii"),
            ),
            oracle_labels=CorpusOracleLabels(evidence_class="NOISE"),
        )
        errors = validate_corpus_entry(entry)
        assert any("Missing entry_id" in e for e in errors)

    def test_missing_both_b64_and_path_fails(self):
        entry = CorpusEntry(
            entry_id="TEST-002",
            source_data=CorpusSourceData(provenance="test:mock"),
            oracle_labels=CorpusOracleLabels(evidence_class="NOISE"),
        )
        errors = validate_corpus_entry(entry)
        assert any("neither raw_content_b64 nor raw_ref_path" in e for e in errors)

    def test_invalid_evidence_class_fails(self):
        entry = CorpusEntry(
            entry_id="TEST-003",
            source_data=CorpusSourceData(
                provenance="test:mock",
                raw_content_b64=base64.b64encode(b"test").decode("ascii"),
            ),
            oracle_labels=CorpusOracleLabels(evidence_class="NON_EXISTENT_CLASS"),
        )
        errors = validate_corpus_entry(entry)
        assert any("invalid oracle evidence_class" in e for e in errors)

    def test_unknown_fields_tolerated(self):
        data = {
            "entry_id": "TEST-004",
            "source_data": {
                "provenance": "test:mock",
                "raw_content_b64": base64.b64encode(b"test").decode("ascii"),
                "future_unrecognized_field": 12345,
            },
            "oracle_labels": {
                "evidence_class": "NOISE",
                "transform_eligibility": "SAFE_TO_REDUCE",
                "extra_oracle_metadata": "ignored",
            },
            "new_v3_envelope_property": "tolerated",
        }
        entry = CorpusEntry.from_dict(data)
        assert entry.entry_id == "TEST-004"
        assert validate_corpus_entry(entry) == []


class TestCorpusLoader:
    def test_load_synthetic_corpus_fixtures(self):
        entries = load_corpus(FIXTURE_PATH)
        assert len(entries) == 4
        ids = [e.entry_id for e in entries]
        assert ids == ["SYNTH-001", "SYNTH-002", "SYNTH-003", "SYNTH-004"]

    def test_load_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_corpus(tmp_path / "does_not_exist.jsonl")

    def test_load_malformed_json_raises(self, tmp_path):
        p = tmp_path / "malformed.jsonl"
        p.write_text("{\"entry_id\": \"broken\", not_valid_json\n", encoding="utf-8")
        with pytest.raises(ValueError, match="Malformed JSON"):
            load_corpus(p)

    def test_load_empty_corpus(self, tmp_path):
        p = tmp_path / "empty.jsonl"
        p.write_text("# empty file with only comments\n\n", encoding="utf-8")
        entries = load_corpus(p)
        assert entries == []


class TestExternalRawReferences:
    def test_external_raw_reference_file(self, tmp_path):
        external_content = b"External raw payload stored on disk"
        raw_file = tmp_path / "raw_payload.bin"
        raw_file.write_bytes(external_content)

        entry = CorpusEntry(
            entry_id="TEST-EXT-001",
            source_data=CorpusSourceData(
                provenance="test:external_disk",
                raw_ref_path=str(raw_file),
                byte_length=len(external_content),
            ),
            oracle_labels=CorpusOracleLabels(
                evidence_class="DISCOVERY",
                transform_eligibility="SAFE_TO_REDUCE",
            ),
        )
        assert validate_corpus_entry(entry) == []
        assert entry.source_data.get_bytes() == external_content

    def test_missing_external_path_raises_on_access(self, tmp_path):
        entry = CorpusEntry(
            entry_id="TEST-EXT-002",
            source_data=CorpusSourceData(
                provenance="test:missing",
                raw_ref_path=str(tmp_path / "missing.bin"),
            ),
            oracle_labels=CorpusOracleLabels(evidence_class="NOISE"),
        )
        with pytest.raises(FileNotFoundError):
            entry.source_data.get_bytes()


class TestCorpusReplayAndSafety:
    def test_deterministic_replay_on_synthetic_fixtures(self, tmp_path):
        entries1 = load_corpus(FIXTURE_PATH)
        entries2 = load_corpus(FIXTURE_PATH)

        eval1, summary1 = replay_corpus(entries1, mode=Mode.BUILD)
        eval2, summary2 = replay_corpus(entries2, mode=Mode.BUILD)

        assert summary1.total_entries == 4
        assert summary1.total_raw_bytes == summary2.total_raw_bytes
        assert summary1.total_visible_bytes == summary2.total_visible_bytes
        assert summary1.dangerous_false_transform_eligibility == 0
        assert summary1.dangerous_false_transform_eligibility == summary2.dangerous_false_transform_eligibility

    def test_sensitive_entry_triggers_do_not_persist(self):
        entries = load_corpus(FIXTURE_PATH)
        eval_entries, summary = replay_corpus(entries, mode=Mode.BUILD)

        # SYNTH-004 contains a fake AWS secret key
        synth4 = next(e for e in eval_entries if e.entry_id == "SYNTH-004")
        assert synth4.derived_metrics.predicted_disposition == "RAW"
        assert synth4.derived_metrics.predicted_sensitivity == "SENSITIVE"
        assert summary.unsafe_sensitivity_leak == 0

    def test_oracle_independence(self):
        # Oracle says CANONICAL_STATE, but content is just noise
        entry = CorpusEntry(
            entry_id="ORC-INDEP-001",
            source_data=CorpusSourceData(
                provenance="test:oracle_check",
                command="echo noise",
                raw_content_b64=base64.b64encode(b"noise\n" * 10).decode("ascii"),
            ),
            oracle_labels=CorpusOracleLabels(
                evidence_class="CANONICAL_STATE",
                transform_eligibility="RAW_REQUIRED",
                oracle_rationale="Oracle independently mandates RAW despite classifier prediction",
            ),
        )
        eval_entries, summary = replay_corpus([entry], mode=Mode.BUILD)
        res = eval_entries[0]
        # Verify oracle and predicted classes are independently maintained
        assert res.oracle_labels.evidence_class == "CANONICAL_STATE"
        # Classifier may predict NOISE
        assert res.derived_metrics.predicted_evidence_class in ("NOISE", "UNKNOWN", "PROGRESS")


class TestExtractorBehavior:
    def test_extractor_on_synthetic_session(self, tmp_path):
        # Create a tiny synthetic Codex session JSONL log
        session_file = tmp_path / "synth_session.jsonl"
        output_file = tmp_path / "extracted_corpus.jsonl"

        lines = [
            json.dumps({"type": "session_meta", "payload": {"id": "session_synth"}}),
            json.dumps({
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "call_001",
                    "name": "exec",
                    "input": "tools.exec_command({cmd: 'git status'})",
                },
            }),
            json.dumps({
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call_001",
                    "output": [{"type": "input_text", "text": "On branch main\nnothing to commit"}],
                },
            }),
            json.dumps({
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call",
                    "call_id": "call_002",
                    "name": "exec",
                    "input": "tools.exec_command({cmd: 'pytest tests/'})",
                },
            }),
            json.dumps({
                "type": "response_item",
                "payload": {
                    "type": "custom_tool_call_output",
                    "call_id": "call_002",
                    "output": [{"type": "input_text", "text": "5 passed in 0.2s"}],
                },
            }),
        ]
        session_file.write_text("\n".join(lines), encoding="utf-8")

        summary = extract_session_corpus(
            session_path=session_file,
            output_path=output_file,
            sample_size=2,
            project_tag="SYNTH",
            filter_sensitive=True,
        )

        assert summary["total_calls_seen"] == 2
        assert summary["sample_size"] == 2
        assert output_file.exists()

        extracted = load_corpus(output_file)
        assert len(extracted) == 2
        assert extracted[0].entry_id == "SYNTH-REAL-001"
        assert extracted[1].entry_id == "SYNTH-REAL-002"
