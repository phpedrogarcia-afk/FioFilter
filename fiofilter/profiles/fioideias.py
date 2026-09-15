"""
fiofilter.profiles.fioideias — FioIdeias project profile (stub).

FioIdeias is an idea-evolution/creative project. Evidence characteristics
differ from FioOS (less authority/canonical content, more DISCOVERY/PROGRESS).

This profile is a stub in V0. It falls back to default behavior.
Define project-specific restrictions in M02 once the FioIdeias workload
is characterized.
"""

from __future__ import annotations

from fiofilter.profiles.base import BaseProfile, Policy
from fiofilter.profiles.default import DefaultProfile
from fiofilter.types import EvidenceClass, Mode

_delegate = DefaultProfile()


class FioIdeaisProfile(BaseProfile):
    """FioIdeias project profile — stub, delegates to default in V0."""

    @property
    def profile_id(self) -> str:
        return "fioideias"

    def get_policy(self, evidence_class: EvidenceClass, mode: Mode) -> Policy:
        # V0 stub: delegate to default profile
        # M02: characterize FioIdeias workload and add specific policies
        return _delegate.get_policy(evidence_class, mode)
