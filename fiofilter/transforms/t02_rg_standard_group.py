"""T02 lossless contiguous-run grouping for one authorized ripgrep grammar.

The transform is intentionally not auto-routed.  ``evaluate`` requires explicit
producer evidence that the current engine cannot yet supply.  ``apply`` therefore
returns ``None`` so registry exposure cannot weaken the M03 admission boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from fiofilter.search_corpus import (
    RG_STANDARD_PATH_LINE_TEXT,
    CommandRejected,
    RgParseError,
    classify_rg_command,
    contains_shell_failure_wrapper,
    contains_upstream_truncation_marker,
    encode_rg_output,
    parse_rg_output,
)
from fiofilter.transforms.base import Transform


TRANSFORM_ID = "T02_RG_STANDARD_GROUP_V1"
TRANSFORM_VERSION = 1
REPRESENTATION_HEADER = b"[[FIOFILTER:T02_RG_STANDARD_GROUP:v1]]\n"
RESERVED_PREFIX = b"[[FIOFILTER:T02_RG_STANDARD_GROUP:"
_PATH_PREFIX = b"[[FIOFILTER:T02_RG_STANDARD_GROUP:v1 path_bytes="
_PATH_TERMINATOR = b"]]"
_POSITIVE_INTEGER = re.compile(rb"[1-9][0-9]*")


@dataclass(frozen=True)
class RgStandardEvidence:
    """Caller-supplied proof fields required before T02 may evaluate content."""

    command: str
    command_structurally_grounded: bool
    single_search_producer: bool
    exit_code: int
    truncated: bool
    upstream_truncation_observed: bool
    shell_failure_wrapper_observed: bool
    stream: str = "combined"


@dataclass(frozen=True)
class RgGroupingMetadata:
    transform_id: str
    transform_version: int
    recognized_grammar: Optional[str]
    raw_byte_count: int
    visible_byte_count: int
    candidate_visible_byte_count: Optional[int]
    bytes_saved: int
    no_expansion_fallback: bool
    roundtrip_verified: bool


@dataclass(frozen=True)
class RgGroupingOutcome:
    visible_content: bytes
    applied: bool
    reason: str
    metadata: RgGroupingMetadata


def _outcome(
    raw: bytes,
    *,
    applied: bool,
    reason: str,
    recognized_grammar: Optional[str] = None,
    candidate: Optional[bytes] = None,
    no_expansion: bool = False,
    roundtrip_verified: bool = False,
) -> RgGroupingOutcome:
    visible = candidate if applied and candidate is not None else raw
    return RgGroupingOutcome(
        visible_content=visible,
        applied=applied,
        reason=reason,
        metadata=RgGroupingMetadata(
            transform_id=TRANSFORM_ID,
            transform_version=TRANSFORM_VERSION,
            recognized_grammar=recognized_grammar,
            raw_byte_count=len(raw),
            visible_byte_count=len(visible),
            candidate_visible_byte_count=(len(candidate) if candidate is not None else None),
            bytes_saved=len(raw) - len(visible),
            no_expansion_fallback=no_expansion,
            roundtrip_verified=roundtrip_verified,
        ),
    )


def _encode_grouped(parsed) -> bytes:
    """Encode contiguous path runs without reordering or dropping a record."""
    output = [REPRESENTATION_HEADER]
    current_path = None
    for record in parsed.records:
        if record.path != current_path:
            output.extend(
                [
                    _PATH_PREFIX,
                    str(len(record.path)).encode("ascii"),
                    _PATH_TERMINATOR,
                    record.path,
                    b"\n",
                ]
            )
            current_path = record.path
        output.extend(
            [
                str(record.line_number).encode("ascii"),
                b":",
                record.payload,
                record.raw_line_ending,
            ]
        )
    return b"".join(output)


def _read_representation_line(content: bytes, start: int):
    newline = content.find(b"\n", start)
    if newline < 0:
        body = content[start:]
        if b"\r" in body:
            raise ValueError("Unsupported lone CR in T02 representation")
        return body, b"", len(content)
    encoded = content[start:newline]
    if encoded.endswith(b"\r"):
        body = encoded[:-1]
        if b"\r" in body:
            raise ValueError("Embedded CR in T02 representation")
        ending = b"\r\n"
    else:
        if b"\r" in encoded:
            raise ValueError("Embedded CR in T02 representation")
        body = encoded
        ending = b"\n"
    return body, ending, newline + 1


def decode_visible(content: bytes, max_output_bytes: int = 16 * 1024 * 1024) -> bytes:
    """Independently reconstruct exact RG_STANDARD_PATH_LINE_TEXT bytes."""
    if not isinstance(content, bytes) or not content.startswith(REPRESENTATION_HEADER):
        raise ValueError("Missing T02 v1 representation header")
    if max_output_bytes < 0:
        raise ValueError("Invalid T02 recovery bound")

    position = len(REPRESENTATION_HEADER)
    current_path: Optional[bytes] = None
    records_in_run = 0
    total_records = 0
    output = []
    output_size = 0

    while position < len(content):
        if content.startswith(_PATH_PREFIX, position):
            if current_path is not None and records_in_run == 0:
                raise ValueError("Empty T02 path run")
            digits_start = position + len(_PATH_PREFIX)
            digits_end = content.find(_PATH_TERMINATOR, digits_start)
            if digits_end < 0:
                raise ValueError("Unterminated T02 path header")
            length_raw = content[digits_start:digits_end]
            if _POSITIVE_INTEGER.fullmatch(length_raw) is None:
                raise ValueError("Invalid T02 path length")
            path_length = int(length_raw)
            path_start = digits_end + len(_PATH_TERMINATOR)
            path_end = path_start + path_length
            if path_end >= len(content) or content[path_end:path_end + 1] != b"\n":
                raise ValueError("T02 path length mismatch")
            current_path = content[path_start:path_end]
            # A Windows drive colon is valid. The explicit byte length, rather
            # than a delimiter split, makes it unambiguous here.
            if not current_path or b"\r" in current_path or b"\n" in current_path:
                raise ValueError("Invalid T02 path bytes")
            records_in_run = 0
            position = path_end + 1
            continue

        if current_path is None:
            raise ValueError("T02 record precedes path header")
        body, ending, position = _read_representation_line(content, position)
        line_raw, separator, payload = body.partition(b":")
        if separator != b":" or _POSITIVE_INTEGER.fullmatch(line_raw) is None:
            raise ValueError("Invalid T02 grouped match line")
        reconstructed = b"".join(
            [current_path, b":", line_raw, b":", payload, ending]
        )
        if output_size + len(reconstructed) > max_output_bytes:
            raise ValueError("T02 recovery bound exceeded")
        output.append(reconstructed)
        output_size += len(reconstructed)
        records_in_run += 1
        total_records += 1

    if current_path is None or records_in_run == 0 or total_records == 0:
        raise ValueError("Empty or incomplete T02 representation")
    return b"".join(output)


class RgStandardLosslessGrouping(Transform):
    @property
    def transform_id(self) -> str:
        return TRANSFORM_ID

    @property
    def description(self) -> str:
        return "Lossless contiguous-run grouping for RG_STANDARD_PATH_LINE_TEXT"

    def apply(self, content: bytes) -> Optional[bytes]:
        """Generic engine calls lack producer proof, so automatic use is denied."""
        return None

    def evaluate(
        self, content: bytes, evidence: Optional[RgStandardEvidence]
    ) -> RgGroupingOutcome:
        """Apply T02 only after every M03 producer and grammar gate is proven."""
        if not isinstance(content, bytes):
            raise TypeError("T02 content must be bytes")
        if not isinstance(evidence, RgStandardEvidence):
            return _outcome(raw=content, applied=False, reason="UNPROVEN_PRODUCER_EVIDENCE")
        if not evidence.command_structurally_grounded or not evidence.single_search_producer:
            return _outcome(raw=content, applied=False, reason="UNPROVEN_PRODUCER_EVIDENCE")
        if isinstance(evidence.exit_code, bool) or evidence.exit_code != 0:
            return _outcome(raw=content, applied=False, reason="NONZERO_EXIT_REQUIRES_RAW")
        if evidence.truncated or evidence.upstream_truncation_observed:
            return _outcome(raw=content, applied=False, reason="TRUNCATED_REQUIRES_RAW")
        if evidence.shell_failure_wrapper_observed:
            return _outcome(raw=content, applied=False, reason="SHELL_FAILURE_WRAPPER")
        if evidence.stream not in ("stdout", "combined"):
            return _outcome(raw=content, applied=False, reason="UNSUPPORTED_STREAM")
        if contains_upstream_truncation_marker(content):
            return _outcome(raw=content, applied=False, reason="UPSTREAM_TRUNCATION_MARKER")
        if contains_shell_failure_wrapper(content):
            return _outcome(raw=content, applied=False, reason="SHELL_FAILURE_WRAPPER")

        try:
            command = classify_rg_command(evidence.command)
        except CommandRejected as exc:
            return _outcome(raw=content, applied=False, reason=exc.reason)
        if command.grammar != RG_STANDARD_PATH_LINE_TEXT:
            return _outcome(
                raw=content,
                applied=False,
                reason="UNAUTHORIZED_GRAMMAR",
                recognized_grammar=command.grammar,
            )
        if RESERVED_PREFIX in content:
            return _outcome(
                raw=content,
                applied=False,
                reason="MARKER_COLLISION",
                recognized_grammar=command.grammar,
            )

        try:
            parsed = parse_rg_output(content, command.grammar)
        except RgParseError as exc:
            return _outcome(
                raw=content,
                applied=False,
                reason=exc.reason,
                recognized_grammar=command.grammar,
            )
        if encode_rg_output(parsed) != content:
            return _outcome(
                raw=content,
                applied=False,
                reason="PARSER_ROUNDTRIP_FAILED",
                recognized_grammar=command.grammar,
            )

        candidate = _encode_grouped(parsed)
        try:
            recovered = decode_visible(candidate, max_output_bytes=len(content))
        except ValueError:
            return _outcome(
                raw=content,
                applied=False,
                reason="DECODER_VALIDATION_FAILED",
                recognized_grammar=command.grammar,
                candidate=candidate,
            )
        if recovered != content:
            return _outcome(
                raw=content,
                applied=False,
                reason="BYTE_EXACT_ROUNDTRIP_FAILED",
                recognized_grammar=command.grammar,
                candidate=candidate,
            )
        if len(candidate) >= len(content):
            return _outcome(
                raw=content,
                applied=False,
                reason="VALID_GRAMMAR_NO_ECONOMIC_GAIN",
                recognized_grammar=command.grammar,
                candidate=candidate,
                no_expansion=True,
                roundtrip_verified=True,
            )
        return _outcome(
            raw=content,
            applied=True,
            reason="LOSSLESS_GROUPING_APPLIED",
            recognized_grammar=command.grammar,
            candidate=candidate,
            roundtrip_verified=True,
        )
