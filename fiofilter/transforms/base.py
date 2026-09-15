"""
fiofilter.transforms.base — Abstract base class for all transforms.

Every transform in FioFilter must implement this interface.
The engine only calls transforms through this ABC — never directly.

Transform contract:
  - apply() must be deterministic: apply(x) == apply(x) always
  - exceptions propagate to the engine, which returns RAW
  - apply() must not expand: len(result) < len(raw) or return None
  - RAW recovery (I3) does not establish visible transform reversibility
  - Inline-required facts must survive (I4 — engine verifies after apply())
"""

from __future__ import annotations

import abc
from typing import Optional


class Transform(abc.ABC):
    """Abstract base class for FioFilter deterministic transforms."""

    @property
    @abc.abstractmethod
    def transform_id(self) -> str:
        """Unique identifier for this transform, e.g. 'T01'."""
        ...

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human-readable description of what this transform does."""
        ...

    @abc.abstractmethod
    def apply(self, content: bytes) -> Optional[bytes]:
        """
        Apply the transform to content.

        Args:
            content: Raw content bytes to transform.

        Returns:
            Transformed bytes if transform fired and produced smaller output.
            None if the transform cannot improve on RAW (no-op or would expand).

        Contract:
          - Must be deterministic: apply(x) == apply(x)
          - Must be fail-open: exceptions are caught by the caller (engine.py)
          - Must not expand: return None if len(result) >= len(content)
          - Must not strip inline-required facts (engine verifies after)

        The engine catches all exceptions from apply() and returns RAW.
        Transforms should not suppress their own exceptions.
        """
        ...
