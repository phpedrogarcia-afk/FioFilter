"""Transform registry.

T01 is engine-routed for its established NOISE/PROGRESS contract. T02 is the
M04 lossless rg grammar transform; it is registered for direct verified use but
profiles do not route it until producer evidence reaches the engine.
"""

from __future__ import annotations

from typing import Dict, Optional, Type

from fiofilter.transforms.base import Transform
from fiofilter.transforms.t01_dup_fold import DuplicateLineFold
from fiofilter.transforms.t02_rg_standard_group import (
    TRANSFORM_ID as T02_RG_STANDARD_GROUP_ID,
    RgStandardLosslessGrouping,
)

# Transform registry: transform_id → Transform class
_REGISTRY: Dict[str, Type[Transform]] = {
    "T01": DuplicateLineFold,
    T02_RG_STANDARD_GROUP_ID: RgStandardLosslessGrouping,
}

# Transforms proven lossless for MACHINE_DATA (I8). T02 is byte-reversible for
# one rg text grammar, not a machine-data consumer contract, so it is not listed.
# T01 may break structured formats; T04 remains unimplemented.
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
