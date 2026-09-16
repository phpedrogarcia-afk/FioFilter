"""Synthetic regressions for the M03 search-corpus laboratory boundary."""

import base64
import json
import pathlib

import pytest

from fiofilter.search_corpus import (
    ARTIFACT_RELATION_UNKNOWN,
    RG_PATH_LINE_COLUMN_TEXT,
    RG_STANDARD_PATH_LINE_TEXT,
    CommandRejected,
    InvocationRejected,
    ResultRejected,
    RgParseError,
    classify_rg_command,
    decode_execution_result,
    encode_rg_output,
    extract_structured_exec_command,
    fingerprint_jsonl_artifact,
    parse_rg_output,
)
from scripts.extract_rg_corpus import extract_rg_corpus


def _roundtrip(raw: bytes, grammar: str):
    parsed = parse_rg_output(raw, grammar)
    assert encode_rg_output(parsed) == raw
    assert parsed.byte_exact_roundtrip is True
    return parsed


class TestRgCharacterizer:
    def test_standard_relative_path_line_text_lf(self):
        raw = b"src/app.py:12:def run():\nsrc/app.py:19:    run()\n"
        parsed = _roundtrip(raw, RG_STANDARD_PATH_LINE_TEXT)
        assert [record.line_number for record in parsed.records] == [12, 19]
        assert [record.path for record in parsed.records] == [b"src/app.py", b"src/app.py"]
        assert all(record.raw_line_ending == b"\n" for record in parsed.records)

    def test_path_line_column_text(self):
        raw = b"src/app.py:12:5:def run():\nsrc/app.py:19:9:run()\n"
        parsed = _roundtrip(raw, RG_PATH_LINE_COLUMN_TEXT)
        assert [record.column_number for record in parsed.records] == [5, 9]

    def test_duplicate_paths_and_identical_matches_preserve_multiplicity(self):
        raw = b"src/app.py:12:target\nsrc/app.py:12:target\nsrc/app.py:20:target\n"
        parsed = _roundtrip(raw, RG_STANDARD_PATH_LINE_TEXT)
        assert len(parsed.records) == 3
        assert [record.payload for record in parsed.records].count(b"target") == 3
        assert [record.ordering_index for record in parsed.records] == [0, 1, 2]

    def test_colon_inside_payload_is_not_a_field_delimiter(self):
        raw = b"src/app.py:12:key:value: still exact\n"
        parsed = _roundtrip(raw, RG_STANDARD_PATH_LINE_TEXT)
        assert parsed.records[0].payload == b"key:value: still exact"

    def test_windows_drive_path(self):
        raw = b"C:\\repo\\src\\app.py:12:def run():\n"
        parsed = _roundtrip(raw, RG_STANDARD_PATH_LINE_TEXT)
        assert parsed.records[0].path == b"C:\\repo\\src\\app.py"

    def test_unc_path(self):
        raw = b"\\\\server\\share\\src\\app.py:12:def run():\n"
        parsed = _roundtrip(raw, RG_STANDARD_PATH_LINE_TEXT)
        assert parsed.records[0].path == b"\\\\server\\share\\src\\app.py"

    def test_crlf_and_tail_without_newline_are_preserved(self):
        raw = b"src/a.py:1:first\r\nsrc/b.py:2:second"
        parsed = _roundtrip(raw, RG_STANDARD_PATH_LINE_TEXT)
        assert [r.raw_line_ending for r in parsed.records] == [b"\r\n", b""]

    @pytest.mark.parametrize(
        ("raw", "reason"),
        [
            (b"malformed line\n", "UNRECOGNIZED_LINE"),
            (b"src/a.py:not-a-line:payload\n", "UNRECOGNIZED_LINE"),
            (b"src/a.py:12:5:ambiguous without --column\n", "AMBIGUOUS_COLUMN_DELIMITER"),
            (b"src/a.py:1:match\n--\nsrc/b.py:2:match\n", "UNSUPPORTED_RG_CONTEXT"),
            (b"\x1b[35msrc/a.py\x1b[0m:1:match\n", "UNSUPPORTED_RG_COLOR"),
            (b'{"type":"match","data":{}}\n', "UNSUPPORTED_RG_JSON"),
            (b"Binary file dist/app.exe matches\n", "UNSUPPORTED_RG_BINARY_NOTICE"),
        ],
    )
    def test_unsupported_or_malformed_output_fails_closed(self, raw, reason):
        with pytest.raises(RgParseError) as exc:
            parse_rg_output(raw, RG_STANDARD_PATH_LINE_TEXT)
        assert exc.value.reason == reason

    def test_mixed_producer_output_fails_closed(self):
        raw = b"directory listing\nsrc/a.py:1:match\n"
        with pytest.raises(RgParseError, match="UNRECOGNIZED_LINE"):
            parse_rg_output(raw, RG_STANDARD_PATH_LINE_TEXT)

    def test_command_must_be_single_ripgrep_producer(self):
        command = classify_rg_command("rg -n target src")
        assert command.family == "RIPGREP"
        assert command.grammar == RG_STANDARD_PATH_LINE_TEXT

        with pytest.raises(CommandRejected) as exc:
            classify_rg_command("cat src/a.py; rg target src")
        assert exc.value.reason == "COMPOSITE_COMMAND"

    @pytest.mark.parametrize(
        ("command", "reason"),
        [
            ("rg -C 2 target src", "UNSUPPORTED_RG_CONTEXT"),
            ("rg -nC2 target src", "UNSUPPORTED_RG_CONTEXT"),
            ("rg --heading target src", "UNSUPPORTED_RG_HEADING"),
            ("rg --json target src", "UNSUPPORTED_RG_JSON"),
            ("rg --color=always target src", "UNSUPPORTED_RG_COLOR"),
            ("node -e \"console.log('rg target')\"", "UNKNOWN_PRODUCER"),
        ],
    )
    def test_command_format_modifiers_are_explicitly_excluded(self, command, reason):
        with pytest.raises(CommandRejected) as exc:
            classify_rg_command(command)
        assert exc.value.reason == reason


def _session_call(call_id: str, command: str, output: str, exit_code=0, **result):
    return [
        {
            "timestamp": "2026-09-16T10:00:00Z",
            "payload": {
                "type": "custom_tool_call",
                "call_id": call_id,
                "name": "exec",
                "input": {"cmd": command},
            },
        },
        {
            "timestamp": "2026-09-16T10:00:01Z",
            "payload": {
                "type": "custom_tool_call_output",
                "call_id": call_id,
                "output": {
                    "exit_code": exit_code,
                    "output": output,
                    **result,
                },
            },
        },
    ]


class TestArtifactFingerprint:
    def test_same_session_id_does_not_imply_same_artifact(self, tmp_path):
        session_id = "01a02f96-42a2-7a80-b8bc-6d066d0e322f"
        first = tmp_path / "first.jsonl"
        second = tmp_path / "second.jsonl"
        first.write_text(
            json.dumps({"timestamp": "2026-03-08T00:00:00Z", "payload": {"type": "session_meta", "id": session_id}}) + "\n",
            encoding="utf-8",
        )
        second.write_text(
            json.dumps({"timestamp": "2026-08-23T00:00:00Z", "payload": {"type": "session_meta", "id": session_id, "extra": True}}) + "\n",
            encoding="utf-8",
        )

        a = fingerprint_jsonl_artifact(first, observation_date="2026-09-16")
        b = fingerprint_jsonl_artifact(second, observation_date="2026-09-16")
        assert a.session_id_if_present == b.session_id_if_present == session_id
        assert a.sha256 != b.sha256
        assert a.artifact_id != b.artifact_id
        assert a.relationship_to_prior_artifact == ARTIFACT_RELATION_UNKNOWN
        assert b.relationship_to_prior_artifact == ARTIFACT_RELATION_UNKNOWN
        assert a.record_count == b.record_count == 1


class TestDedicatedRgExtractor:
    def test_existing_output_is_never_overwritten(self, tmp_path):
        session = tmp_path / "session.jsonl"
        session.write_text(
            json.dumps({"payload": {"type": "session_meta", "id": "synthetic"}}) + "\n",
            encoding="utf-8",
        )
        clean = tmp_path / "clean.jsonl"
        clean.write_text("preserve me\n", encoding="utf-8")
        with pytest.raises(FileExistsError):
            extract_rg_corpus(
                session_path=session,
                output_path=clean,
                negative_output_path=tmp_path / "negative.jsonl",
                manifest_path=tmp_path / "manifest.json",
                observation_date="2026-09-16",
            )
        assert clean.read_text(encoding="utf-8") == "preserve me\n"

    def test_streaming_extractor_emits_clean_and_negative_sets(self, tmp_path):
        session_id = "session-synthetic"
        records = [
            {
                "timestamp": "2026-09-16T09:59:59Z",
                "payload": {"type": "session_meta", "id": session_id},
            }
        ]
        records += _session_call(
            "clean-standard",
            "rg -n target src",
            "src/a.py:1:target\nsrc/a.py:3:target\n",
        )
        records += _session_call(
            "clean-column",
            "rg --column target src",
            "src/a.py:1:4:target\r\n",
        )
        records += _session_call("no-match", "rg target src", "", exit_code=1)
        records += _session_call("error", "rg target src", "rg: bad flag\n", exit_code=2)
        records += _session_call(
            "truncated",
            "rg target src",
            "src/a.py:1:target\n[Output truncated at 40000 bytes...]",
        )
        records += _session_call(
            "composite",
            "cat src/a.py; rg target src",
            "source text\nsrc/a.py:1:target\n",
        )
        records += _session_call(
            "context",
            "rg -C 1 target src",
            "src/a.py-1-before\nsrc/a.py:2:target\n",
        )
        records += _session_call(
            "unknown",
            "node -e \"console.log('rg target')\"",
            "rg target\n",
        )

        session = tmp_path / "session.jsonl"
        session.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        clean = tmp_path / "m03_search_corpus_v1.jsonl"
        negative = tmp_path / "m03_search_corpus_v1.negative.jsonl"
        manifest = tmp_path / "m03_search_corpus_v1.manifest.json"

        summary = extract_rg_corpus(
            session_path=session,
            output_path=clean,
            negative_output_path=negative,
            manifest_path=manifest,
            observation_date="2026-09-16",
            review_limit_per_grammar=2,
            negative_limit_per_reason=1,
        )

        assert summary["clean_candidate_count"] == 2
        assert summary["clean_category_counts"] == {
            RG_PATH_LINE_COLUMN_TEXT: 1,
            RG_STANDARD_PATH_LINE_TEXT: 1,
        }
        assert summary["exclusion_counts"]["RG_NO_MATCH_EXIT_1"] == 1
        assert summary["exclusion_counts"]["RG_EXECUTION_ERROR"] == 1
        assert summary["exclusion_counts"]["UPSTREAM_TRUNCATION_MARKER"] == 1
        assert summary["exclusion_counts"]["COMPOSITE_COMMAND"] == 1
        assert summary["exclusion_counts"]["UNSUPPORTED_RG_CONTEXT"] == 1
        assert summary["exclusion_counts"]["UNKNOWN_PRODUCER"] == 1

        clean_records = [json.loads(line) for line in clean.read_text(encoding="utf-8").splitlines()]
        assert len(clean_records) == 2
        assert all(item["record_kind"] == "CLEAN_CANDIDATE" for item in clean_records)
        assert all(item["oracle_labels"] is None for item in clean_records)
        assert all(item["characterization"]["byte_exact_roundtrip"] for item in clean_records)
        assert base64.b64decode(clean_records[0]["raw_content_b64"])

        manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
        fingerprint = manifest_data["source_artifact_fingerprint"]
        assert fingerprint["session_id_if_present"] == session_id
        assert fingerprint["absolute_path_local_only"] == str(session.resolve())
        assert fingerprint["filename"] == session.name
        assert fingerprint["size_bytes"] == session.stat().st_size
        assert len(fingerprint["sha256"]) == 64
        assert fingerprint["first_record_timestamp"] == "2026-09-16T09:59:59Z"
        assert fingerprint["last_record_timestamp"] == "2026-09-16T10:00:01Z"
        assert fingerprint["payload_type_counts"] == {
            "custom_tool_call": 8,
            "custom_tool_call_output": 8,
            "session_meta": 1,
        }
        assert fingerprint["extraction_tool_version"] == "M03_SEARCH_CORPUS_V1_EXTRACTOR_1"
        assert fingerprint["observation_date"] == "2026-09-16"
        assert fingerprint["relationship_to_prior_artifact"] == ARTIFACT_RELATION_UNKNOWN
        assert fingerprint["record_count"] == len(records)
        assert len(manifest_data["independent_review_selection"]) == 2

        negative_records = [
            json.loads(line) for line in negative.read_text(encoding="utf-8").splitlines()
        ]
        assert {item["exclusion_reason"] for item in negative_records} >= {
            "RG_NO_MATCH_EXIT_1",
            "RG_EXECUTION_ERROR",
            "UPSTREAM_TRUNCATION_MARKER",
            "COMPOSITE_COMMAND",
            "UNSUPPORTED_RG_CONTEXT",
            "UNKNOWN_PRODUCER",
        }

    def test_explicit_truncated_flag_is_rejected(self, tmp_path):
        records = _session_call(
            "truncated-flag",
            "rg target src",
            "src/a.py:1:target\n",
            truncated=True,
        )
        session = tmp_path / "session.jsonl"
        session.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")

        summary = extract_rg_corpus(
            session_path=session,
            output_path=tmp_path / "clean.jsonl",
            negative_output_path=tmp_path / "negative.jsonl",
            manifest_path=tmp_path / "manifest.json",
            observation_date="2026-09-16",
        )
        assert summary["clean_candidate_count"] == 0
        assert summary["exclusion_counts"]["TRUNCATED_RESULT"] == 1

    def test_arbitrary_javascript_containing_rg_is_not_admitted(self, tmp_path):
        records = _session_call(
            "javascript",
            "node -e \"const text = 'rg target'; console.log(text)\"",
            "rg target\n",
        )
        session = tmp_path / "session.jsonl"
        session.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
        summary = extract_rg_corpus(
            session_path=session,
            output_path=tmp_path / "clean.jsonl",
            negative_output_path=tmp_path / "negative.jsonl",
            manifest_path=tmp_path / "manifest.json",
            observation_date="2026-09-16",
        )
        assert summary["clean_candidate_count"] == 0
        assert summary["exclusion_counts"]["UNKNOWN_PRODUCER"] == 1


class TestCodexRunnerAndHeadroomRegressions:
    def test_codex_runner_envelope_success_and_failure(self):
        # Success envelope: Script completed with stdout text
        success_payload = {
            "output": [
                {"type": "text", "text": "Script completed"},
                {"type": "text", "text": "src/a.py:1:match\n"},
            ]
        }
        res_ok = decode_execution_result(success_payload)
        assert res_ok.exit_code == 0
        assert res_ok.content == b"src/a.py:1:match\n"
        assert res_ok.truncated is False

        # Failure envelope: Script failed with exit code
        fail_payload = {
            "output": [
                {"type": "text", "text": "Script failed with exit code 2\n"},
                {"type": "text", "text": "rg: error reading file\n"},
            ]
        }
        res_fail = decode_execution_result(fail_payload)
        assert res_fail.exit_code == 2
        assert res_fail.content == b"rg: error reading file\n"

        # Truncation marker envelope
        trunc_payload = {
            "output": [
                {"type": "text", "text": "Script completed"},
                {"type": "text", "text": "output content", "original_token_count": 15000},
            ]
        }
        res_trunc = decode_execution_result(trunc_payload)
        assert res_trunc.truncated is True

    def test_codex_runner_envelope_rejects_unstructured(self):
        with pytest.raises(ResultRejected):
            decode_execution_result({"output": 12345})
        with pytest.raises(ResultRejected):
            decode_execution_result({"output": [{"type": "text", "text": "Some unformatted message"}]})

    def test_real_codex_exec_wrapper_parsing(self):
        # Real Codex wrapper with const r = await tools.exec_command(...)
        raw_js = 'const r = await tools.exec_command({ cmd: "rg -n target src" }); text(r.output);'
        call_payload = {"type": "custom_tool_call", "name": "exec_command", "input": raw_js}
        cmd = extract_structured_exec_command(call_payload)
        assert cmd == "rg -n target src"

        # Reject multiple tool calls
        multi_js = (
            'const r1 = await tools.exec_command({ cmd: "rg -n target src" });\n'
            'const r2 = await tools.exec_command({ cmd: "rg -n other src" });'
        )
        with pytest.raises(InvocationRejected) as exc:
            extract_structured_exec_command({"type": "custom_tool_call", "name": "exec_command", "input": multi_js})
        assert exc.value.reason == "UNSTRUCTURED_INVOCATION"

    @pytest.mark.parametrize(
        ("raw", "grammar", "expect_admit", "reason"),
        [
            (b"C:\\repo\\app.py:10:result\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"\\\\server\\share\\repo\\app.py:10:result\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"src/my-cool-app/test-runner.py:42:assert ok\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"logs/2026-05-03/run.log:15:started\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"advisories/CVE-2021-44228.md:99:vulnerability\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"data/part-01-2024-v2.txt:7:data row\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"src/a.py:10:5:col match\n", RG_PATH_LINE_COLUMN_TEXT, True, None),
            (b"src/a.py:10:5:col match\n", RG_STANDARD_PATH_LINE_TEXT, False, "AMBIGUOUS_COLUMN_DELIMITER"),
            (b"src/config.py:12:url = https://example.com:8080/api\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"src/a.py:10:dup\nsrc/a.py:10:dup\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"src/a.py:1:match\n--\nsrc/a.py:5:match\n", RG_STANDARD_PATH_LINE_TEXT, False, "UNSUPPORTED_RG_CONTEXT"),
            (b"bin/run:25:exec\nMakefile:4:all:\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"build/123/output.py:40:match\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
            (b"some random stdout line\n", RG_STANDARD_PATH_LINE_TEXT, False, "UNRECOGNIZED_LINE"),
            (b"Binary file dist/app.exe matches\n", RG_STANDARD_PATH_LINE_TEXT, False, "UNSUPPORTED_RG_BINARY_NOTICE"),
            (b"\x1b[32msrc/app.py\x1b[0m:1:val\n", RG_STANDARD_PATH_LINE_TEXT, False, "UNSUPPORTED_RG_COLOR"),
            (b'{"type":"match","data":{"path":{"text":"a.py"}}}\n', RG_STANDARD_PATH_LINE_TEXT, False, "UNSUPPORTED_RG_JSON"),
            (b"a.py:12:\n", RG_STANDARD_PATH_LINE_TEXT, True, None),
        ],
    )
    def test_headroom_donor_challenges(self, raw, grammar, expect_admit, reason):
        if expect_admit:
            parsed = parse_rg_output(raw, grammar)
            assert encode_rg_output(parsed) == raw
        else:
            with pytest.raises(RgParseError) as exc:
                parse_rg_output(raw, grammar)
            if reason is not None:
                assert exc.value.reason == reason
