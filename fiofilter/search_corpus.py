"""Fail-closed M03 search-corpus characterization primitives.

This module is a laboratory boundary, not a transform.  It identifies a narrow
ripgrep producer surface and parses two plain-text grammars only when the exact
input bytes can be reconstructed.  Nothing here is connected to the FioFilter
transform engine or assigns reviewed oracle labels.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import re
import shlex
from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


SEARCH_CORPUS_SCHEMA_VERSION = 1
EXTRACTION_TOOL_VERSION = "M03_SEARCH_CORPUS_V1_EXTRACTOR_1"

RG_STANDARD_PATH_LINE_TEXT = "RG_STANDARD_PATH_LINE_TEXT"
RG_PATH_LINE_COLUMN_TEXT = "RG_PATH_LINE_COLUMN_TEXT"
SUPPORTED_RG_GRAMMARS = (
    RG_STANDARD_PATH_LINE_TEXT,
    RG_PATH_LINE_COLUMN_TEXT,
)

ARTIFACT_RELATION_SAME_BYTES = "SAME_BYTES"
ARTIFACT_RELATION_DERIVED_FROM = "DERIVED_FROM"
ARTIFACT_RELATION_SUBSET = "SUBSET"
ARTIFACT_RELATION_SUPERSET = "SUPERSET"
ARTIFACT_RELATION_DIFFERENT = "DIFFERENT_ARTIFACT"
ARTIFACT_RELATION_UNKNOWN = "UNKNOWN"
ARTIFACT_RELATIONSHIPS = (
    ARTIFACT_RELATION_SAME_BYTES,
    ARTIFACT_RELATION_DERIVED_FROM,
    ARTIFACT_RELATION_SUBSET,
    ARTIFACT_RELATION_SUPERSET,
    ARTIFACT_RELATION_DIFFERENT,
    ARTIFACT_RELATION_UNKNOWN,
)


class SearchCorpusError(ValueError):
    """Base error carrying a stable fail-closed reason."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


class CommandRejected(SearchCorpusError):
    """The command cannot establish one supported ripgrep producer."""


class InvocationRejected(SearchCorpusError):
    """The tool invocation is not structurally recognized."""


class ResultRejected(SearchCorpusError):
    """The execution result envelope is not structurally recognized."""


class RgParseError(SearchCorpusError):
    """The output cannot be parsed under the selected exact grammar."""


@dataclass(frozen=True)
class ArtifactFingerprint:
    """Content identity and bounded metadata for one historical JSONL artifact."""

    artifact_id: str
    session_id_if_present: Optional[str]
    absolute_path_local_only: str
    filename: str
    size_bytes: int
    sha256: str
    first_record_timestamp: Optional[str]
    last_record_timestamp: Optional[str]
    record_count: int
    payload_type_counts: Dict[str, int]
    extraction_tool_version: str
    observation_date: str
    relationship_to_prior_artifact: str
    prior_artifact_id: Optional[str] = None
    malformed_record_count: int = 0
    session_ids_observed: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["session_ids_observed"] = list(self.session_ids_observed)
        return data


@dataclass(frozen=True)
class RgCommand:
    """A structurally isolated ripgrep command and expected output grammar."""

    raw: str
    argv: Tuple[str, ...]
    executable: str
    family: str
    grammar: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw.encode("utf-8")).hexdigest()

    def fingerprint(self) -> Dict[str, Any]:
        return {
            "family": self.family,
            "executable": self.executable,
            "argv": list(self.argv),
            "command_sha256": self.sha256,
            "format_category": self.grammar,
        }


@dataclass(frozen=True)
class ExecutionResult:
    """Supported structured execution result fields."""

    content: bytes
    exit_code: int
    truncated: bool


@dataclass(frozen=True)
class RgStructuralRecord:
    """One exact ripgrep match line."""

    ordering_index: int
    path: bytes
    line_number: int
    column_number: Optional[int]
    kind: str
    payload: bytes
    separator: bytes
    raw_line_ending: bytes
    header_association: Optional[bytes] = None

    def encode(self) -> bytes:
        parts = [
            self.path,
            self.separator,
            str(self.line_number).encode("ascii"),
            self.separator,
        ]
        if self.column_number is not None:
            parts.extend(
                [str(self.column_number).encode("ascii"), self.separator]
            )
        parts.extend([self.payload, self.raw_line_ending])
        return b"".join(parts)


@dataclass(frozen=True)
class RgParseResult:
    """Exact characterization result for one supported grammar."""

    grammar: str
    records: Tuple[RgStructuralRecord, ...]
    raw_sha256: str
    byte_exact_roundtrip: bool


_STANDARD_LINE = re.compile(
    rb"^(?P<path>(?:[A-Za-z]:[\\/][^:\r\n]+|\\\\[^:\r\n]+|[^:\r\n]+))"
    rb":(?P<line>[1-9][0-9]*):(?P<payload>[^\r\n]*)$"
)
_COLUMN_LINE = re.compile(
    rb"^(?P<path>(?:[A-Za-z]:[\\/][^:\r\n]+|\\\\[^:\r\n]+|[^:\r\n]+))"
    rb":(?P<line>[1-9][0-9]*):(?P<column>[1-9][0-9]*):(?P<payload>[^\r\n]*)$"
)
_POSSIBLE_PATH_CONTINUATION = re.compile(
    rb"^[^:\r\n]+:[1-9][0-9]*(?::[1-9][0-9]*)?:"
)
_POSSIBLE_COLUMN_PREFIX = re.compile(rb"^[1-9][0-9]*:")
_TRUNCATION_MARKERS = (
    b"output truncated",
    b"truncated output",
    b"truncated at ",
    b"upstream truncation",
)
_FAILURE_WRAPPERS = (
    b"script failed",
    b"command failed",
    b"process exited with code",
    b"traceback (most recent call last)",
)


def contains_upstream_truncation_marker(content: bytes) -> bool:
    """Recognize explicit truncation evidence without claiming completeness."""
    lowered = content.lower()
    return any(marker in lowered for marker in _TRUNCATION_MARKERS)


def contains_shell_failure_wrapper(content: bytes) -> bool:
    """Recognize common wrapper failures conservatively."""
    lowered = content.lower()
    return any(marker in lowered for marker in _FAILURE_WRAPPERS)


def _split_exact_lines(raw: bytes) -> List[Tuple[bytes, bytes]]:
    if not raw:
        raise RgParseError("RG_EMPTY", "ripgrep exit 0 output has no bytes")
    lines: List[Tuple[bytes, bytes]] = []
    start = 0
    while True:
        newline = raw.find(b"\n", start)
        if newline < 0:
            tail = raw[start:]
            if tail:
                if b"\r" in tail:
                    raise RgParseError("UNSUPPORTED_LINE_ENDING", "lone CR")
                lines.append((tail, b""))
            break
        encoded = raw[start:newline]
        if encoded.endswith(b"\r"):
            body = encoded[:-1]
            if b"\r" in body:
                raise RgParseError("UNSUPPORTED_LINE_ENDING", "embedded CR")
            lines.append((body, b"\r\n"))
        else:
            if b"\r" in encoded:
                raise RgParseError("UNSUPPORTED_LINE_ENDING", "embedded CR")
            lines.append((encoded, b"\n"))
        start = newline + 1
    return lines


def parse_rg_output(raw: bytes, grammar: str) -> RgParseResult:
    """Parse only a narrow grammar and prove byte-exact reconstruction."""
    if grammar not in SUPPORTED_RG_GRAMMARS:
        raise RgParseError("UNSUPPORTED_RG_GRAMMAR", grammar)
    if b"\x00" in raw:
        raise RgParseError("UNSUPPORTED_BINARY_OUTPUT", "NUL byte")
    if b"\x1b" in raw:
        raise RgParseError("UNSUPPORTED_RG_COLOR", "ANSI escape byte")
    stripped = raw.lstrip()
    if stripped.startswith((b"{", b"[")):
        raise RgParseError("UNSUPPORTED_RG_JSON", "machine-data grammar is separate")

    pattern = _COLUMN_LINE if grammar == RG_PATH_LINE_COLUMN_TEXT else _STANDARD_LINE
    records: List[RgStructuralRecord] = []
    for index, (body, ending) in enumerate(_split_exact_lines(raw)):
        if body == b"--":
            raise RgParseError("UNSUPPORTED_RG_CONTEXT", "context group separator")
        if body.lower().startswith(b"binary file ") and body.lower().endswith(b" matches"):
            raise RgParseError("UNSUPPORTED_RG_BINARY_NOTICE", "binary match notice")
        match = pattern.fullmatch(body)
        if match is None:
            raise RgParseError("UNRECOGNIZED_LINE", f"line {index + 1}")
        payload = match.group("payload")
        if grammar == RG_STANDARD_PATH_LINE_TEXT and _POSSIBLE_COLUMN_PREFIX.match(payload):
            raise RgParseError(
                "AMBIGUOUS_COLUMN_DELIMITER",
                f"line {index + 1} begins with a possible column number",
            )
        if _POSSIBLE_PATH_CONTINUATION.match(payload):
            raise RgParseError(
                "AMBIGUOUS_PATH_DELIMITER",
                f"line {index + 1} may contain a colon-bearing path",
            )
        column_raw = match.groupdict().get("column")
        records.append(
            RgStructuralRecord(
                ordering_index=index,
                path=match.group("path"),
                line_number=int(match.group("line")),
                column_number=int(column_raw) if column_raw is not None else None,
                kind="MATCH",
                payload=payload,
                separator=b":",
                raw_line_ending=ending,
                header_association=None,
            )
        )

    result = RgParseResult(
        grammar=grammar,
        records=tuple(records),
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        byte_exact_roundtrip=False,
    )
    reconstructed = encode_rg_output(result)
    if reconstructed != raw:
        raise RgParseError("BYTE_EXACT_ROUNDTRIP_FAILED")
    return RgParseResult(
        grammar=result.grammar,
        records=result.records,
        raw_sha256=result.raw_sha256,
        byte_exact_roundtrip=True,
    )


def encode_rg_output(parsed: RgParseResult) -> bytes:
    """Reconstruct the exact characterized bytes; this is not compression."""
    return b"".join(record.encode() for record in parsed.records)


def _has_unquoted_shell_control(command: str) -> bool:
    quote: Optional[str] = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            escaped = True
            index += 1
            continue
        if quote is not None:
            if char == quote:
                quote = None
            elif quote == '"' and (
                char == "`" or command[index : index + 2] == "$("
            ):
                return True
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
        elif char in ";|&<>\r\n`":
            return True
        elif command[index : index + 2] == "$(":
            return True
        index += 1
    if quote is not None or escaped:
        raise CommandRejected("AMBIGUOUS_COMMAND", "unterminated quoting")
    return False


def _option_matches(token: str, long_name: str, short_name: Optional[str] = None) -> bool:
    if token == long_name or token.startswith(long_name + "="):
        return True
    if short_name and (token == short_name or token.startswith(short_name)):
        return True
    return False


def _has_combined_short_context_option(token: str) -> bool:
    """Recognize conservative rg short-option clusters such as ``-nC2``."""
    return bool(re.fullmatch(r"-[A-Za-z]*[ABC](?:[0-9]+)?", token))


def classify_rg_command(command: str) -> RgCommand:
    """Require one shell-free ripgrep producer and select a narrow grammar."""
    if not isinstance(command, str) or not command.strip() or "\x00" in command:
        raise CommandRejected("INVALID_COMMAND")
    if _has_unquoted_shell_control(command):
        raise CommandRejected("COMPOSITE_COMMAND")
    try:
        argv = tuple(shlex.split(command, posix=True))
    except ValueError as exc:
        raise CommandRejected("AMBIGUOUS_COMMAND", str(exc)) from exc
    if not argv:
        raise CommandRejected("INVALID_COMMAND")
    executable = argv[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if executable not in ("rg", "rg.exe", "ripgrep", "ripgrep.exe"):
        raise CommandRejected("UNKNOWN_PRODUCER")

    for token in argv[1:]:
        if _option_matches(token, "--json"):
            raise CommandRejected("UNSUPPORTED_RG_JSON")
        if _option_matches(token, "--heading"):
            raise CommandRejected("UNSUPPORTED_RG_HEADING")
        if _option_matches(token, "--color") or _option_matches(token, "--colors"):
            raise CommandRejected("UNSUPPORTED_RG_COLOR")
        if (
            _option_matches(token, "--context", "-C")
            or _option_matches(token, "--before-context", "-B")
            or _option_matches(token, "--after-context", "-A")
            or _has_combined_short_context_option(token)
        ):
            raise CommandRejected("UNSUPPORTED_RG_CONTEXT")
        if token in ("--null", "--null-data", "-0"):
            raise CommandRejected("UNSUPPORTED_RG_NULL")
        if token in ("--vimgrep", "--binary"):
            raise CommandRejected("UNSUPPORTED_RG_FORMAT_MODIFIER", token)

    grammar = (
        RG_PATH_LINE_COLUMN_TEXT
        if "--column" in argv[1:]
        else RG_STANDARD_PATH_LINE_TEXT
    )
    return RgCommand(
        raw=command,
        argv=argv,
        executable=executable,
        family="RIPGREP",
        grammar=grammar,
    )


_STRING_LITERAL = re.compile(r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')''')
_SIMPLE_VALUE = re.compile(
    r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|-?[0-9]+|true|false|null)'''
)


def _split_simple_js_fields(body: str) -> List[str]:
    fields: List[str] = []
    start = 0
    quote: Optional[str] = None
    escaped = False
    for index, char in enumerate(body):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote is not None:
            escaped = True
            continue
        if quote is not None:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == ",":
            fields.append(body[start:index].strip())
            start = index + 1
    if quote is not None:
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "unterminated string")
    fields.append(body[start:].strip())
    return [field for field in fields if field]


def _decode_string_literal(literal: str) -> str:
    if _STRING_LITERAL.fullmatch(literal) is None:
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "cmd is not a string literal")
    try:
        value = json.loads(literal) if literal.startswith('"') else ast.literal_eval(literal)
    except (ValueError, SyntaxError, json.JSONDecodeError) as exc:
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "invalid string literal") from exc
    if not isinstance(value, str):
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "cmd is not text")
    return value


def _parse_exec_input(raw: Any) -> str:
    if isinstance(raw, dict):
        command = raw.get("cmd")
        if isinstance(command, str) and command:
            return command
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "mapping lacks string cmd")
    if not isinstance(raw, str):
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "input is not a mapping or string")

    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        decoded = None
    if isinstance(decoded, dict):
        return _parse_exec_input(decoded)

    # Check for multiple tool calls in a single script
    all_tool_calls = re.findall(r"tools\.[a-zA-Z0-9_]+", raw)
    if len(all_tool_calls) != 1 or all_tool_calls[0] != "tools.exec_command":
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "unsupported or multiple tool calls")

    m = re.search(r"tools\.exec_command\s*\(\s*\{", raw)
    if m is None:
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "unsupported exec wrapper")
    start_brace = m.end() - 1
    depth = 0
    quote: Optional[str] = None
    escaped = False
    end_brace = -1
    for idx in range(start_brace, len(raw)):
        ch = raw[idx]
        if escaped:
            escaped = False
            continue
        if ch == "\\" and quote != "'":
            escaped = True
            continue
        if quote is not None:
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end_brace = idx
                break
    if end_brace < 0:
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "unterminated exec_command body")
    body = raw[start_brace + 1 : end_brace]

    values: Dict[str, str] = {}
    for field in _split_simple_js_fields(body):
        match = re.fullmatch(
            r"(?P<key>[\"']?[A-Za-z_][A-Za-z0-9_-]*[\"']?)\s*:\s*(?P<value>.+)", field
        )
        if match is None or _SIMPLE_VALUE.fullmatch(match.group("value")) is None:
            continue
        key = match.group("key").strip("\"'")
        if key in values:
            raise InvocationRejected("UNSTRUCTURED_INVOCATION", "duplicate wrapper field")
        values[key] = match.group("value")
    if "cmd" not in values:
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "wrapper lacks cmd")
    return _decode_string_literal(values["cmd"])


def extract_structured_exec_command(call_payload: Dict[str, Any]) -> str:
    """Extract cmd only from an explicitly identified exec tool call."""
    if not isinstance(call_payload, dict):
        raise InvocationRejected("UNSTRUCTURED_INVOCATION")
    if call_payload.get("type") != "custom_tool_call":
        raise InvocationRejected("UNSTRUCTURED_INVOCATION", "not a custom tool call")
    if call_payload.get("name") not in ("exec", "exec_command"):
        raise InvocationRejected("UNKNOWN_PRODUCER", "tool is not exec")
    return _parse_exec_input(call_payload.get("input"))


def _coerce_result_envelope(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ResultRejected("UNSTRUCTURED_RESULT", "text is not a JSON object") from exc
        if isinstance(decoded, dict):
            return decoded
        raise ResultRejected("UNSTRUCTURED_RESULT", "decoded result is not an object")
    if isinstance(raw, list) and len(raw) == 1:
        item = raw[0]
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            return _coerce_result_envelope(item["text"])
        if isinstance(item, dict) and "exit_code" in item:
            return item
    raise ResultRejected("UNSTRUCTURED_RESULT", "unsupported output envelope")


def decode_execution_result(output_payload: Dict[str, Any]) -> ExecutionResult:
    """Decode only a structured exec result with explicit exit status."""
    if not isinstance(output_payload, dict):
        raise ResultRejected("UNSTRUCTURED_RESULT")
    raw = output_payload.get("output")

    # Synthetic or wrapped dictionary envelope
    if isinstance(raw, dict) and "exit_code" in raw and "output" in raw:
        exit_code = raw["exit_code"]
        content = raw["output"]
        if isinstance(exit_code, bool) or not isinstance(exit_code, int):
            raise ResultRejected("UNSTRUCTURED_RESULT", "missing integer exit_code")
        if not isinstance(content, str):
            raise ResultRejected("UNSTRUCTURED_RESULT", "missing text output")
        truncated = bool(raw.get("truncated", False)) or raw.get("original_token_count") is not None
        return ExecutionResult(content=content.encode("utf-8"), exit_code=exit_code, truncated=truncated)

    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ResultRejected("UNSTRUCTURED_RESULT", "text is not a JSON object") from exc
        if isinstance(decoded, dict):
            return decode_execution_result({"output": decoded})
        raise ResultRejected("UNSTRUCTURED_RESULT", "decoded result is not an object")

    if isinstance(raw, list):
        if len(raw) == 1 and isinstance(raw[0], dict) and "exit_code" in raw[0]:
            return decode_execution_result({"output": raw[0]})
        if len(raw) == 1 and isinstance(raw[0], dict) and isinstance(raw[0].get("text"), str):
            try:
                decoded = json.loads(raw[0]["text"])
                if isinstance(decoded, dict) and "exit_code" in decoded:
                    return decode_execution_result({"output": decoded})
            except Exception:
                pass

        # Real Codex execution runner format:
        # raw[0]["text"] contains runner status: "Script completed" or "Script failed"
        if len(raw) >= 1 and isinstance(raw[0], dict) and isinstance(raw[0].get("text"), str):
            t0 = raw[0]["text"]
            exit_code = None
            if t0.startswith("Script completed"):
                exit_code = 0
            elif t0.startswith("Script failed"):
                m_code = re.search(r"exit code\s+(-?\d+)", t0, re.IGNORECASE)
                exit_code = int(m_code.group(1)) if m_code else 1

            if exit_code is not None:
                content_parts = []
                for it in raw[1:]:
                    if isinstance(it, dict) and isinstance(it.get("text"), str):
                        content_parts.append(it["text"])
                content_str = "".join(content_parts)
                truncated = (
                    "truncated output" in content_str.lower()
                    or "output truncated" in content_str.lower()
                    or any(it.get("original_token_count") is not None for it in raw if isinstance(it, dict))
                )
                return ExecutionResult(
                    content=content_str.encode("utf-8"),
                    exit_code=exit_code,
                    truncated=truncated,
                )

    raise ResultRejected("UNSTRUCTURED_RESULT", "unsupported output envelope")


def fingerprint_jsonl_artifact(
    path: pathlib.Path | str,
    observation_date: str,
    relationship_to_prior_artifact: str = ARTIFACT_RELATION_UNKNOWN,
    prior_artifact_id: Optional[str] = None,
) -> ArtifactFingerprint:
    """Hash exact JSONL bytes and record compact, local-only provenance."""
    artifact_path = pathlib.Path(path)
    if relationship_to_prior_artifact not in ARTIFACT_RELATIONSHIPS:
        raise ValueError("Invalid relationship_to_prior_artifact")
    if not observation_date:
        raise ValueError("observation_date is required for deterministic evidence")
    if not artifact_path.is_file():
        raise FileNotFoundError(f"Session file not found: {artifact_path}")

    digest = hashlib.sha256()
    size_bytes = 0
    record_count = 0
    malformed = 0
    first_timestamp: Optional[str] = None
    last_timestamp: Optional[str] = None
    payload_types: Counter[str] = Counter()
    session_ids: set[str] = set()

    with open(artifact_path, "rb") as handle:
        for raw_line in handle:
            digest.update(raw_line)
            size_bytes += len(raw_line)
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                malformed += 1
                continue
            if not isinstance(record, dict):
                malformed += 1
                continue
            record_count += 1
            timestamp = record.get("timestamp")
            if isinstance(timestamp, str) and timestamp:
                if first_timestamp is None:
                    first_timestamp = timestamp
                last_timestamp = timestamp
            payload = record.get("payload")
            if isinstance(payload, dict):
                payload_type = payload.get("type")
                if isinstance(payload_type, str) and payload_type:
                    payload_types[payload_type] += 1
                if payload_type == "session_meta":
                    session_id = payload.get("id") or payload.get("session_id")
                    if isinstance(session_id, str) and session_id:
                        session_ids.add(session_id)

    hexdigest = digest.hexdigest()
    observed_ids = tuple(sorted(session_ids))
    return ArtifactFingerprint(
        artifact_id=f"M03-ARTIFACT-SHA256-{hexdigest[:16].upper()}",
        session_id_if_present=observed_ids[0] if len(observed_ids) == 1 else None,
        absolute_path_local_only=str(artifact_path.resolve()),
        filename=artifact_path.name,
        size_bytes=size_bytes,
        sha256=hexdigest,
        first_record_timestamp=first_timestamp,
        last_record_timestamp=last_timestamp,
        record_count=record_count,
        payload_type_counts=dict(sorted(payload_types.items())),
        extraction_tool_version=EXTRACTION_TOOL_VERSION,
        observation_date=observation_date,
        relationship_to_prior_artifact=relationship_to_prior_artifact,
        prior_artifact_id=prior_artifact_id,
        malformed_record_count=malformed,
        session_ids_observed=observed_ids,
    )


def deterministic_review_selection(
    candidates: Iterable[Dict[str, Any]], limit_per_grammar: int
) -> List[Dict[str, Any]]:
    """Select deterministic size-quantile coverage within each grammar."""
    if limit_per_grammar < 1:
        raise ValueError("limit_per_grammar must be positive")
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault(str(candidate["grammar"]), []).append(dict(candidate))
    selected: List[Dict[str, Any]] = []
    for grammar in sorted(grouped):
        ordered = sorted(
            grouped[grammar],
            key=lambda item: (
                int(item["byte_length"]),
                int(item["occurrence_index"]),
                str(item["entry_id"]),
            ),
        )
        if len(ordered) <= limit_per_grammar:
            chosen = ordered
        elif limit_per_grammar == 1:
            chosen = [ordered[len(ordered) // 2]]
        else:
            indexes = {
                (index * (len(ordered) - 1)) // (limit_per_grammar - 1)
                for index in range(limit_per_grammar)
            }
            chosen = [ordered[index] for index in sorted(indexes)]
        selected.extend(chosen)
    return selected


def ensure_outside_repository(path: pathlib.Path | str) -> pathlib.Path:
    """Reject local historical corpus outputs located inside this Git checkout."""
    target = pathlib.Path(path).resolve()
    repository_root = pathlib.Path(__file__).resolve().parents[1]
    try:
        target.relative_to(repository_root)
    except ValueError:
        return target
    raise ValueError(f"Historical corpus output must stay outside Git: {target}")
