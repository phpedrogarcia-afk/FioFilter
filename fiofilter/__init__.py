"""
FioFilter — Evidence-aware context reduction layer for coding agents.

Public surface (V0):
    process()          — Main entry point: process a ToolResult through the decision engine
    EvidenceClass      — Evidence taxonomy enum
    Mode               — Operational mode enum
    Disposition        — Decision outcome enum
    ToolResult         — Input type
    FilterResult       — Output type
"""

from fiofilter.types import (
    EvidenceClass,
    Mode,
    Disposition,
    ToolResult,
    FilterResult,
    RawRef,
    FilterMetrics,
)
from fiofilter.engine import process

__version__ = "0.0.1.dev0"

__all__ = [
    "process",
    "EvidenceClass",
    "Mode",
    "Disposition",
    "ToolResult",
    "FilterResult",
    "RawRef",
    "FilterMetrics",
]
