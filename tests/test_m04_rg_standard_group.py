"""M04 lossless grouping contract for RG_STANDARD_PATH_LINE_TEXT."""

import random

import pytest

from fiofilter.engine import process
from fiofilter.profiles import get_profile
from fiofilter.transforms import available_transform_ids, get_transform
from fiofilter.transforms.t02_rg_standard_group import (
    REPRESENTATION_HEADER,
    RESERVED_PREFIX,
    TRANSFORM_ID,
    RgStandardEvidence,
    RgStandardLosslessGrouping,
    decode_visible,
)
from fiofilter.types import Disposition, EvidenceClass, Mode, ToolResult


def _evidence(command="rg -n target src", **changes):
    values = {
        "command": command,
        "command_structurally_grounded": True,
        "single_search_producer": True,
        "exit_code": 0,
        "truncated": False,
        "upstream_truncation_observed": False,
        "shell_failure_wrapper_observed": False,
        "stream": "combined",
    }
    values.update(changes)
    return RgStandardEvidence(**values)


def _assert_applied(raw, evidence=None):
    outcome = RgStandardLosslessGrouping().evaluate(raw, evidence or _evidence())
    assert outcome.applied is True
    assert outcome.visible_content.startswith(REPRESENTATION_HEADER)
    assert len(outcome.visible_content) < len(raw)
    assert decode_visible(outcome.visible_content, max_output_bytes=len(raw)) == raw
    assert outcome.metadata.transform_id == TRANSFORM_ID
    assert outcome.metadata.recognized_grammar == "RG_STANDARD_PATH_LINE_TEXT"
    assert outcome.metadata.roundtrip_verified is True
    assert outcome.metadata.bytes_saved == len(raw) - len(outcome.visible_content)
    assert outcome.metadata.no_expansion_fallback is False
    return outcome


class TestLosslessRepresentation:
    def test_contiguous_runs_preserve_a_b_a_order(self):
        long_a = b"src/components/alpha/very_long_filename.py"
        long_b = b"src/components/beta/another_very_long_filename.py"
        raw = b"".join(
            [
                long_a + b":1:first\n",
                long_a + b":2:second\n",
                long_a + b":3:third\n",
                long_b + b":4:fourth\n",
                long_b + b":5:fifth\n",
                long_a + b":6:sixth\n",
                long_a + b":7:seventh\n",
                long_a + b":8:eighth\n",
            ]
        )
        outcome = _assert_applied(raw)
        assert outcome.visible_content.count(long_a) == 2
        assert outcome.visible_content.count(long_b) == 1

    def test_duplicate_identical_matches_preserve_multiplicity(self):
        path = b"src/a/long/repeated/component/file.py"
        line = path + b":10:identical payload\n"
        raw = line * 12
        _assert_applied(raw)

    @pytest.mark.parametrize(
        "path",
        [
            b"C:\\repo\\src\\very-long-windows-file.py",
            b"\\\\server\\share\\repo\\very-long-unc-file.py",
            b"src/my-cool-app/test-runner-file.py",
            b"logs/2026-05-03/long-execution-record.log",
            b"advisories/CVE-2021-44228-long-record.md",
            b"data/part-01-2024-v2/segment-998877.txt",
            b"very/" + b"long-directory/" * 12 + b"file.py",
        ],
    )
    def test_path_edge_cases_roundtrip(self, path):
        raw = b"".join(path + b":" + str(i).encode() + b":payload:value\n" for i in range(1, 9))
        _assert_applied(raw)

    def test_lf_crlf_and_missing_final_newline(self):
        path = b"src/long/path/to/repeated/file.py"
        for ending in (b"\n", b"\r\n"):
            raw = b"".join(path + b":" + str(i).encode() + b":payload" + ending for i in range(1, 10))
            _assert_applied(raw)
        no_tail = b"\n".join(path + b":" + str(i).encode() + b":payload" for i in range(1, 10))
        _assert_applied(no_tail)

    def test_empty_payload_is_exact(self):
        path = b"src/a/very/long/path/empty-payload.py"
        raw = b"".join(path + b":" + str(i).encode() + b":\n" for i in range(1, 12))
        _assert_applied(raw)

    def test_no_file_or_match_cap_and_exact_order(self):
        lines = []
        for file_index in range(80):
            path = f"src/generated/component-{file_index:03d}/very-long-file-name.py".encode()
            for match_index in range(4):
                lines.append(
                    path
                    + b":"
                    + str(match_index + 1).encode()
                    + b":full retained payload\n"
                )
        raw = b"".join(lines)
        outcome = _assert_applied(raw)
        assert decode_visible(outcome.visible_content, max_output_bytes=len(raw)) == raw

    def test_marker_collision_and_already_transformed_are_raw(self):
        path = b"src/a/very/long/path/file.py"
        raw = b"".join(path + b":" + str(i).encode() + b":" + RESERVED_PREFIX + b" literal\n" for i in range(1, 9))
        outcome = RgStandardLosslessGrouping().evaluate(raw, _evidence())
        assert outcome.applied is False
        assert outcome.visible_content == raw
        assert outcome.reason == "MARKER_COLLISION"

        already = REPRESENTATION_HEADER + b"not raw rg output\n"
        again = RgStandardLosslessGrouping().evaluate(already, _evidence())
        assert again.applied is False
        assert again.visible_content == already

    def test_decoder_rejects_tampering_explicitly(self):
        path = b"src/a/very/long/repeated/file.py"
        raw = b"".join(path + b":" + str(i).encode() + b":payload\n" for i in range(1, 10))
        visible = _assert_applied(raw).visible_content
        with pytest.raises(ValueError):
            decode_visible(b"broken" + visible)
        with pytest.raises(ValueError):
            decode_visible(visible.replace(b"path_bytes=", b"path_bytes=999", 1))
        with pytest.raises(ValueError):
            decode_visible(visible, max_output_bytes=1)


class TestFailClosedEvidenceBoundary:
    @pytest.mark.parametrize(
        ("raw", "evidence", "reason"),
        [
            (b"src/a.py:1:match\n", _evidence("rg --column target src"), "UNAUTHORIZED_GRAMMAR"),
            (b"src/a.py:1:4:match\n", _evidence("rg --column target src"), "UNAUTHORIZED_GRAMMAR"),
            (b"src/a.py:1:match\n--\nsrc/a.py:2:match\n", _evidence("rg -C 1 target src"), "UNSUPPORTED_RG_CONTEXT"),
            (b"src/a.py\n1:match\n", _evidence("rg --heading target src"), "UNSUPPORTED_RG_HEADING"),
            (b'{"type":"match"}\n', _evidence("rg --json target src"), "UNSUPPORTED_RG_JSON"),
            (b"\x1b[32msrc/a.py\x1b[0m:1:match\n", _evidence("rg --color=always target src"), "UNSUPPORTED_RG_COLOR"),
            (b"Binary file app.exe matches\n", _evidence(), "UNSUPPORTED_RG_BINARY_NOTICE"),
            (b"unknown output\n", _evidence(), "UNRECOGNIZED_LINE"),
            (b"src/a.py:1:match\n", _evidence("cat a.py; rg target src"), "COMPOSITE_COMMAND"),
            (b"src/a.py:1:match\n", _evidence(exit_code=1), "NONZERO_EXIT_REQUIRES_RAW"),
            (b"src/a.py:1:match\n", _evidence(truncated=True), "TRUNCATED_REQUIRES_RAW"),
            (b"src/a.py:1:match\n", _evidence(upstream_truncation_observed=True), "TRUNCATED_REQUIRES_RAW"),
            (b"src/a.py:1:match\n", _evidence(shell_failure_wrapper_observed=True), "SHELL_FAILURE_WRAPPER"),
            (b"src/a.py:1:match\n", _evidence(stream="stderr"), "UNSUPPORTED_STREAM"),
            (b"src/a.py:1:match\n", _evidence(command_structurally_grounded=False), "UNPROVEN_PRODUCER_EVIDENCE"),
            (b"src/a.py:1:match\n", _evidence(single_search_producer=False), "UNPROVEN_PRODUCER_EVIDENCE"),
            (b"src/a.py:10:5:column-like\n", _evidence(), "AMBIGUOUS_COLUMN_DELIMITER"),
            (b"source code\nsrc/a.py:1:match\n", _evidence(), "UNRECOGNIZED_LINE"),
        ],
    )
    def test_unauthorized_or_ambiguous_input_stays_raw(self, raw, evidence, reason):
        outcome = RgStandardLosslessGrouping().evaluate(raw, evidence)
        assert outcome.applied is False
        assert outcome.visible_content == raw
        assert outcome.reason == reason

    def test_truncation_and_failure_markers_are_raw_even_with_benign_metadata(self):
        for raw, reason in (
            (b"src/a.py:1:match\n[Output truncated at 40000 bytes...]", "UPSTREAM_TRUNCATION_MARKER"),
            (b"src/a.py:1:match\nScript failed", "SHELL_FAILURE_WRAPPER"),
        ):
            outcome = RgStandardLosslessGrouping().evaluate(raw, _evidence())
            assert outcome.applied is False
            assert outcome.visible_content == raw
            assert outcome.reason == reason

    def test_single_match_and_no_gain_remain_raw(self):
        raw = b"very/long/path/to/a/single/file.py:1:match\n"
        outcome = RgStandardLosslessGrouping().evaluate(raw, _evidence())
        assert outcome.applied is False
        assert outcome.visible_content == raw
        assert outcome.reason == "VALID_GRAMMAR_NO_ECONOMIC_GAIN"
        assert outcome.metadata.no_expansion_fallback is True
        assert outcome.metadata.roundtrip_verified is True


class TestGeneratedContract:
    def test_deterministic_generated_valid_and_invalid_cases(self):
        rng = random.Random(20260916)
        transform = RgStandardLosslessGrouping()
        valid_cases = transformed = no_expansion = 0
        raw_bytes = visible_bytes = 0
        paths = [
            b"src/generated/very-long-alpha-file.py",
            b"C:\\repo\\generated\\very-long-beta-file.py",
            b"\\\\server\\share\\generated\\very-long-gamma-file.py",
            b"logs/2026-09-16/CVE-2026-12345-generated.log",
        ]
        payloads = [b"match", b"value:with:colons", b"", b"digits-2026-09-16"]
        for _ in range(200):
            path = rng.choice(paths)
            count = rng.randint(1, 14)
            ending = rng.choice([b"\n", b"\r\n"])
            lines = []
            for index in range(count):
                tail = b"" if index == count - 1 and rng.randrange(5) == 0 else ending
                lines.append(path + b":" + str(index + 1).encode() + b":" + rng.choice(payloads) + tail)
            raw = b"".join(lines)
            outcome = transform.evaluate(raw, _evidence())
            valid_cases += 1
            raw_bytes += len(raw)
            visible_bytes += len(outcome.visible_content)
            if outcome.applied:
                transformed += 1
                assert decode_visible(outcome.visible_content, max_output_bytes=len(raw)) == raw
            else:
                no_expansion += 1
                assert outcome.visible_content == raw
                assert outcome.reason == "VALID_GRAMMAR_NO_ECONOMIC_GAIN"

        assert valid_cases == 200
        assert transformed > 0
        assert no_expansion > 0
        assert visible_bytes < raw_bytes

        for index in range(50):
            raw = f"src/a.py:{index + 1}:5:ambiguous\n".encode()
            outcome = transform.evaluate(raw, _evidence())
            assert outcome.applied is False
            assert outcome.visible_content == raw
            assert outcome.reason == "AMBIGUOUS_COLUMN_DELIMITER"


class TestEngineMetadataGate:
    def test_registry_exposes_transform_but_generic_apply_and_profiles_do_not_activate(self):
        assert TRANSFORM_ID in available_transform_ids()
        transform = get_transform(TRANSFORM_ID)
        assert transform is not None
        raw = b"src/a/very/long/path/file.py:1:match\n" * 20
        assert transform.apply(raw) is None
        for mode in Mode:
            assert TRANSFORM_ID not in get_profile("default").get_policy(
                EvidenceClass.DISCOVERY, mode
            ).transform_whitelist

        result = process(ToolResult(content=raw, command="rg -n match src", exit_code=0))
        assert result.disposition != Disposition.TRANSFORM
        assert result.content == raw
        assert result.transform_id is None
