"""
fiofilter.transforms.t01_dup_fold — T01: Exact duplicate-line folding.

Specification:
  PRECONDITIONS:
    - Content is UTF-8 text (not binary).
    - Evidence class is NOISE, DISCOVERY, or PROGRESS.
    - Consecutive duplicate lines must exist for transform to fire.

  PROTECTED_FACTS:
    - First occurrence of any line is always preserved in full.
    - Fold markers include the exact duplicate count.
    - No line content is silently deleted.

  OUTPUT_CONTRACT:
    For runs of N identical consecutive lines (N >= 2):
      <line content> [×N duplicates folded]
    For runs of N >= FOLD_THRESHOLD identical consecutive lines:
      <line content> [×N duplicates folded]
    Non-duplicate lines pass through unchanged.

  RAW_RECOVERY:
    The raw content is stored in the RAW store before this transform runs.
    SHA-256 verified recovery is always available (I3).

  FAIL_OPEN_BEHAVIOR:
    Any exception during apply() propagates to the engine.
    The engine catches it and returns RAW.
    Transforms do not suppress their own exceptions.

  TEST_ORACLE:
    1. apply(x) == apply(x)  [determinism]
    2. len(apply(x)) < len(x) when duplicates exist, else None returned
    3. apply(x) with no duplicates → returns None (no savings)
    4. Fold marker contains correct count
    5. First occurrence of folded line is preserved
"""

from __future__ import annotations

from typing import Optional

from fiofilter.transforms.base import Transform

# Minimum consecutive duplicate count to trigger folding.
# Single duplicates (N=2) are folded by default.
FOLD_THRESHOLD: int = 2

# Fold marker template. {count} is replaced with the duplicate count.
# The marker must be visible and auditable.
_FOLD_MARKER = " [×{count} duplicates folded]"


class DuplicateLineFold(Transform):
    """
    T01: Exact duplicate-line folding.

    Folds consecutive runs of identical lines into:
        <first occurrence> [×N duplicates folded]

    Only triggers when N >= FOLD_THRESHOLD.
    Non-duplicate or insufficient-duplicate content returns None (→ RAW).
    """

    @property
    def transform_id(self) -> str:
        return "T01"

    @property
    def description(self) -> str:
        return "Exact duplicate consecutive-line folding"

    def apply(self, content: bytes) -> Optional[bytes]:
        """
        Apply duplicate-line folding.

        Returns:
            Folded bytes if content was reduced.
            None if no folding occurred or output would not be smaller.
        """
        # Attempt UTF-8 decode. Binary content → None (let engine return RAW).
        try:
            text = content.decode("utf-8")
        except (UnicodeDecodeError, ValueError):
            return None

        lines = text.splitlines(keepends=True)
        if len(lines) < FOLD_THRESHOLD:
            return None

        output_lines = []
        i = 0
        folded_any = False

        while i < len(lines):
            current_line = lines[i]
            # Count consecutive identical lines
            j = i + 1
            while j < len(lines) and lines[j] == current_line:
                j += 1

            count = j - i
            if count >= FOLD_THRESHOLD:
                # Keep first occurrence, add fold marker
                stripped = current_line.rstrip("\r\n")
                newline = current_line[len(stripped):]
                marker = _FOLD_MARKER.format(count=count - 1)
                output_lines.append(stripped + marker + newline)
                folded_any = True
            else:
                # No folding — pass through all occurrences
                output_lines.extend(lines[i:j])

            i = j

        if not folded_any:
            return None  # Nothing was folded → engine returns RAW (I9)

        result_bytes = "".join(output_lines).encode("utf-8")

        # I9: Never expand — if result is not smaller, return None
        if len(result_bytes) >= len(content):
            return None

        return result_bytes
