"""
fiofilter.transforms — Transform registry.

V0 transforms:
  T01 — Exact duplicate-line folding (DuplicateLineFold)

T03, T04, T05 are CANDIDATES defined in docs/ARCHITECTURE.md.
They are NOT implemented in V0. Any code attempting to import
them from this package in V0 will raise ImportError.

Only after a separately authorized post-M02 mission:
  1. Implement in t0N_name.py following the Transform ABC
  2. Add to _REGISTRY below
  3. Write test oracle in tests/test_transforms.py
  4. Record decision in docs/DECISIONS.md
"""

from __future__ import annotations

from typing import Dict, Optional, Type

from fiofilter.transforms.base import Transform
from fiofilter.transforms.t01_dup_fold import DuplicateLineFold

# Transform registry: transform_id → Transform class
_REGISTRY: Dict[str, Type[Transform]] = {
    "T01": DuplicateLineFold,
}

# Transforms proven lossless for MACHINE_DATA (I8).
# T01 is NOT lossless for machine data (folds lines, may break structured formats).
# T04 (JSON minification) is a candidate but NOT yet proven or implemented.
LOSSLESS_TRANSFORM_IDS: frozenset = frozenset([
    # "T04",  # JSON minification — requires independent contract and approval
])


def get_transform(transform_id: str) -> Optional[Transform]:
    """
    Get a Transform instance by ID.

    Returns None if the transform_id is not registered.
    The engine treats None as: no transform available → RAW.
    """
    cls = _REGISTRY.get(transform_id)
    if cls is None:
        return None
    return cls()


def available_transform_ids() -> frozenset:
    """Return the set of registered transform IDs."""
    return frozenset(_REGISTRY.keys())
