"""Deterministic Markdown section extraction for progressive disclosure.

This laboratory helper never changes a source document.  A selector is an exact
Markdown heading title (the text after the ``#`` prefix).  If any selector is
missing, duplicated, or the document cannot be parsed as UTF-8 Markdown, the
result conservatively expands to the complete document.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_FENCE_RE = re.compile(r"^( {0,3})(`{3,}|~{3,})(.*)$")


class _FenceParseError(ValueError):
    """Markdown fence state is incomplete or cannot be safely interpreted."""


@dataclass(frozen=True)
class SectionSelection:
    content: bytes
    full_document_bytes: int
    selected_bytes: int
    avoided_context_bytes: int
    fallback_required: bool
    fallback_reason: Optional[str]


def _heading_records(raw: bytes) -> List[Tuple[str, int, int, int]]:
    """Return ``(title, level, start, end)`` for every Markdown heading."""

    text = raw.decode("utf-8")
    records: List[Tuple[str, int, int, int]] = []
    offset = 0
    open_fence_character: Optional[str] = None
    open_fence_length = 0
    for line in text.splitlines(keepends=True):
        encoded = line.encode("utf-8")
        logical = line.rstrip("\r\n")

        fence = _FENCE_RE.fullmatch(logical)
        if open_fence_character is not None:
            if fence is not None:
                marker = fence.group(2)
                suffix = fence.group(3)
                if (
                    marker[0] == open_fence_character
                    and len(marker) >= open_fence_length
                    and not suffix.strip(" \t")
                ):
                    open_fence_character = None
                    open_fence_length = 0
            offset += len(encoded)
            continue

        if fence is not None:
            marker = fence.group(2)
            suffix = fence.group(3)
            if marker[0] == "`" and "`" in suffix:
                raise _FenceParseError("UNCERTAIN_FENCE_SYNTAX")
            open_fence_character = marker[0]
            open_fence_length = len(marker)
            offset += len(encoded)
            continue

        match = _HEADING_RE.fullmatch(logical)
        if match:
            records.append((match.group(2), len(match.group(1)), offset, 0))
        offset += len(encoded)

    if open_fence_character is not None:
        raise _FenceParseError("UNCLOSED_FENCE")

    complete: List[Tuple[str, int, int, int]] = []
    for index, (title, level, start, _) in enumerate(records):
        end = len(raw)
        for _, next_level, next_start, _ in records[index + 1 :]:
            if next_level <= level:
                end = next_start
                break
        complete.append((title, level, start, end))
    return complete


def _merge_ranges(ranges: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    merged: List[List[int]] = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(start, end) for start, end in merged]


def select_sections(raw: bytes, headings: Sequence[str]) -> SectionSelection:
    """Select exact heading-bounded sections, or conservatively return ``raw``."""

    if not headings:
        return _fallback(raw, "NO_HEADINGS_DECLARED")
    if len(set(headings)) != len(headings):
        return _fallback(raw, "DUPLICATE_SELECTOR")

    try:
        records = _heading_records(raw)
    except UnicodeDecodeError:
        return _fallback(raw, "INVALID_UTF8_MARKDOWN")
    except _FenceParseError as error:
        return _fallback(raw, str(error))

    ranges: List[Tuple[int, int]] = []
    for heading in headings:
        matches = [(start, end) for title, _, start, end in records if title == heading]
        if not matches:
            return _fallback(raw, "MISSING_HEADING:" + heading)
        if len(matches) != 1:
            return _fallback(raw, "AMBIGUOUS_HEADING:" + heading)
        ranges.append(matches[0])

    merged = _merge_ranges(ranges)
    content = b"".join(raw[start:end] for start, end in merged)
    return SectionSelection(
        content=content,
        full_document_bytes=len(raw),
        selected_bytes=len(content),
        avoided_context_bytes=len(raw) - len(content),
        fallback_required=False,
        fallback_reason=None,
    )


def _fallback(raw: bytes, reason: str) -> SectionSelection:
    return SectionSelection(
        content=raw,
        full_document_bytes=len(raw),
        selected_bytes=len(raw),
        avoided_context_bytes=0,
        fallback_required=True,
        fallback_reason=reason,
    )


def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument(
        "--heading",
        action="append",
        required=True,
        help="exact heading title without the Markdown # prefix; repeatable",
    )
    parser.add_argument(
        "--measure",
        action="store_true",
        help="emit a compact JSON measurement instead of selected document bytes",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    raw = args.document.read_bytes()
    result = select_sections(raw, args.heading)
    if args.measure:
        record = {
            "avoided_context_bytes": result.avoided_context_bytes,
            "document": args.document.as_posix(),
            "fallback_reason": result.fallback_reason,
            "fallback_required": result.fallback_required,
            "full_document_bytes": result.full_document_bytes,
            "headings": args.heading,
            "selected_bytes": result.selected_bytes,
        }
        sys.stdout.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    else:
        if result.fallback_required:
            sys.stderr.write("FULL_DOCUMENT_FALLBACK=" + str(result.fallback_reason) + "\n")
        sys.stdout.buffer.write(result.content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
