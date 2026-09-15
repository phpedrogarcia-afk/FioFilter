"""
fiofilter.profiles — Profile loader.

Usage:
    from fiofilter.profiles import get_profile
    profile = get_profile("fioos")
    policy = profile.get_policy(EvidenceClass.DISCOVERY, Mode.BUILD)
"""

from __future__ import annotations

from typing import Dict, Type

from fiofilter.profiles.base import BaseProfile
from fiofilter.profiles.default import DefaultProfile
from fiofilter.profiles.fioos import FioOSProfile
from fiofilter.profiles.fioideias import FioIdeaisProfile

_PROFILES: Dict[str, Type[BaseProfile]] = {
    "default": DefaultProfile,
    "fioos": FioOSProfile,
    "fioideias": FioIdeaisProfile,
}


def get_profile(profile_id: str = "default") -> BaseProfile:
    """
    Get a profile instance by ID.

    Unknown profile IDs raise ValueError; the engine returns RAW.
    Profiles cannot weaken invariants (I12) — the engine enforces this.
    """
    cls = _PROFILES.get(profile_id)
    if cls is None:
        raise ValueError("Unknown profile")
    return cls()


def available_profile_ids() -> frozenset:
    """Return the set of registered profile IDs."""
    return frozenset(_PROFILES.keys())
