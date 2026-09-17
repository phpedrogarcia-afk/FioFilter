"""fiofilter.read_receipt — Filesystem-aware Read Receipt shadow specialization.

Specializes the reexposure lane specifically for FILE_READ operations:
- Decouples Plane A (Source Freshness / Byte Identity) from Plane B (Context Policy Authority)
- Precise source identity (display path vs resolved canonical identity)
- Explicit read-view identity (FULL_FILE, LINE_RANGE, BYTE_RANGE, UNKNOWN_VIEW)
- Freshness proof hierarchy: F0_UNKNOWN -> F1_HISTORICAL -> F2_METADATA -> F3_HASH -> F4_BYTE
- Mtime is strictly a fast reject / change hint, never sole authority
- Mandatory hash + byte equality for live reference proof (F4)
- Mtime-spoof defense: modified bytes with restored mtime are detected and rejected
- Hypothetical reference formatting with strict no-expansion guarantees
- Append-only hash-chained ledger
"""

from __future__ import annotations

import base64
import enum
import hashlib
import json
import os
import pathlib
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from fiofilter.sensitivity import contains_sensitive_material, scan_text

SCHEMA_VERSION = "M07_READ_RECEIPT_SHADOW_V1"
REFERENCE_VERSION = "v1"

# Distance and Recency Buckets
RECENCY_BUCKETS = (
    "0-2",
    "3-5",
    "6-10",
    "11-25",
    "26-50",
    "51-100",
    ">100",
)

EPISODE_BUCKETS = (
    "0_same_episode",
    "1_episode",
    "2-5_episodes",
    ">5_episodes",
)


def _classify_recency_bucket(distance: int) -> str:
    """Classify call distance into standard bucket."""
    if distance <= 2:
        return "0-2"
    if distance <= 5:
        return "3-5"
    if distance <= 10:
        return "6-10"
    if distance <= 25:
        return "11-25"
    if distance <= 50:
        return "26-50"
    if distance <= 100:
        return "51-100"
    return ">100"


def _classify_episode_bucket(ep_diff: int) -> str:
    """Classify episode distance into standard bucket."""
    if ep_diff == 0:
        return "0_same_episode"
    if ep_diff == 1:
        return "1_episode"
    if ep_diff <= 5:
        return "2-5_episodes"
    return ">5_episodes"


class ReadViewType(str, enum.Enum):
    """Structured categories of file read views."""
    FULL_FILE = "FULL_FILE"
    LINE_RANGE = "LINE_RANGE"
    BYTE_RANGE = "BYTE_RANGE"
    OTHER_STRUCTURED_VIEW = "OTHER_STRUCTURED_VIEW"
    UNKNOWN_VIEW = "UNKNOWN_VIEW"


class FreshnessLevel(str, enum.Enum):
    """Epistemic levels of freshness proof."""
    F0_UNKNOWN = "F0_UNKNOWN"
    F1_HISTORICAL_OUTPUT_IDENTITY = "F1_HISTORICAL_OUTPUT_IDENTITY"
    F2_METADATA_CONSISTENT = "F2_METADATA_CONSISTENT"
    F3_CURRENT_VIEW_HASH_EQUAL = "F3_CURRENT_VIEW_HASH_EQUAL"
    F4_CURRENT_VIEW_BYTE_EQUAL = "F4_CURRENT_VIEW_BYTE_EQUAL"


class ReadReceiptDisposition(str, enum.Enum):
    """Deterministic shadow disposition for a file read event."""
    FIRST_READ_RAW = "FIRST_READ_RAW"
    HISTORICAL_IDENTICAL_READ_CANDIDATE = "HISTORICAL_IDENTICAL_READ_CANDIDATE"
    LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE = "LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE"
    SOURCE_CHANGED_RAW = "SOURCE_CHANGED_RAW"
    VIEW_CHANGED_RAW = "VIEW_CHANGED_RAW"
    SOURCE_IDENTITY_UNKNOWN_RAW = "SOURCE_IDENTITY_UNKNOWN_RAW"
    VIEW_IDENTITY_UNKNOWN_RAW = "VIEW_IDENTITY_UNKNOWN_RAW"
    REFERENCE_NOT_ECONOMIC_RAW = "REFERENCE_NOT_ECONOMIC_RAW"
    ACTIVE_POLICY_NOT_AUTHORIZED_RAW = "ACTIVE_POLICY_NOT_AUTHORIZED_RAW"
    SENSITIVE_POLICY_RAW = "SENSITIVE_POLICY_RAW"
    MISSING_FILE_RAW = "MISSING_FILE_RAW"
    READ_ERROR_RAW = "READ_ERROR_RAW"


@dataclass(frozen=True)
class ReadView:
    """Explicit representation of a requested view into a file."""
    view_type: ReadViewType
    start_line: Optional[int] = None  # 1-indexed, inclusive
    end_line: Optional[int] = None    # 1-indexed, inclusive
    tail_lines: Optional[int] = None
    start_byte: Optional[int] = None
    end_byte: Optional[int] = None
    raw_expr: Optional[str] = None

    @property
    def view_id(self) -> str:
        """Deterministic compact identifier for view equality."""
        if self.view_type == ReadViewType.FULL_FILE:
            return "FULL_FILE"
        if self.view_type == ReadViewType.LINE_RANGE:
            if self.tail_lines is not None:
                return f"TAIL:{self.tail_lines}"
            s = self.start_line if self.start_line is not None else 1
            e = self.end_line if self.end_line is not None else "EOF"
            return f"LINES:{s}-{e}"
        if self.view_type == ReadViewType.BYTE_RANGE:
            s = self.start_byte if self.start_byte is not None else 0
            e = self.end_byte if self.end_byte is not None else "EOF"
            return f"BYTES:{s}-{e}"
        if self.view_type == ReadViewType.OTHER_STRUCTURED_VIEW:
            expr_hash = hashlib.sha256((self.raw_expr or "").encode()).hexdigest()[:12]
            return f"OTHER:{expr_hash}"
        expr_hash = hashlib.sha256((self.raw_expr or "").encode()).hexdigest()[:12]
        return f"UNKNOWN:{expr_hash}"

    def is_compatible_with(self, other: ReadView) -> bool:
        """Return True if both views request the exact same view contract."""
        if self.view_type != other.view_type:
            return False
        if self.view_type == ReadViewType.FULL_FILE:
            return True
        if self.view_type == ReadViewType.LINE_RANGE:
            return (
                self.start_line == other.start_line
                and self.end_line == other.end_line
                and self.tail_lines == other.tail_lines
            )
        if self.view_type == ReadViewType.BYTE_RANGE:
            return (
                self.start_byte == other.start_byte
                and self.end_byte == other.end_byte
            )
        # UNKNOWN or OTHER views are only compatible if exact view_id matches
        return self.view_id == other.view_id


@dataclass
class ReadReceipt:
    """Session-scoped delivery receipt for a specific source and view."""
    receipt_id: str
    session_id: str
    original_path: str
    resolved_path_identity: Optional[str]
    read_mode: str
    requested_view: ReadView
    delivered_sha256: str
    delivered_bytes: int
    file_size: Optional[int] = None
    mtime_ns_hint: Optional[int] = None
    repo_root_if_known: Optional[str] = None
    git_head_if_known: Optional[str] = None
    worktree_state_if_known: Optional[str] = None
    first_seen_call: int = 0
    last_seen_call: int = 0
    first_seen_episode: Optional[int] = None
    last_seen_episode: Optional[int] = None
    first_seen_timestamp: Optional[str] = None
    last_seen_timestamp: Optional[str] = None
    sensitivity: str = "NOT_SENSITIVE"
    persistence_policy: str = "EPHEMERAL"
    reference_count: int = 0


@dataclass
class ReadReceiptDecision:
    """Shadow decision and economic accounting for a read event."""
    call_id: str
    receipt_id: Optional[str]
    disposition: ReadReceiptDisposition
    freshness_level: FreshnessLevel
    original_path: Optional[str]
    resolved_path_identity: Optional[str]
    requested_view: Optional[ReadView]
    raw_bytes: int
    delivered_sha256: str
    hypothetical_reference: Optional[str]
    reference_bytes: int
    hypothetical_bytes_avoided: int
    call_distance: Optional[int]
    episode_distance: Optional[int]
    reason: str
    plane_a_freshness_proven: bool
    plane_b_active_authorized: bool = False
    local_io_bytes_read: int = 0
    model_visible_raw_bytes: int = 0
    hypothetical_model_visible_reference_bytes: int = 0


@dataclass
class LiveReadResult:
    """Ephemeral result of a live read evaluation returning both raw bytes and the shadow decision."""
    raw_bytes: bytes
    decision: ReadReceiptDecision


def format_read_reference(
    receipt_id: str,
    sha256_hex: str,
    view_id: str,
    bytes_len: int,
) -> str:
    """Format the canonical hypothetical shadow reference for a verified read."""
    return (
        f"[[FIOFILTER:READREF:{REFERENCE_VERSION}\n"
        f"receipt={receipt_id}\n"
        f"sha256={sha256_hex}\n"
        f"view={view_id}\n"
        f"bytes={bytes_len}\n"
        f"]]"
    )


def normalize_source_identity(
    path_str: str,
    base_dir: Optional[pathlib.Path] = None,
) -> Tuple[Optional[str], str]:
    """Derive canonical source identity while preserving verbatim display path.

    Returns:
        (resolved_identity, display_path)
    """
    display_path = path_str.strip()
    if not display_path:
        return None, display_path

    # Clean surrounding quotes
    cleaned = display_path.strip("'\"`")

    # If the path contains illegal wildcards or shell tokens
    if any(c in cleaned for c in ("*", "?", "<", ">", "|")):
        return None, display_path

    try:
        p = pathlib.Path(cleaned)
        if not p.is_absolute():
            if base_dir is not None:
                p = (base_dir / p).resolve()
            else:
                # Relative path without known base directory is unresolved
                # Standardize forward slashes to system separator for identity
                norm_rel = str(p).replace("/", "\\") if os.name == "nt" else str(p).replace("\\", "/")
                return norm_rel.lower() if os.name == "nt" else norm_rel, display_path
        else:
            p = p.resolve()

        # On Windows, drive letters and paths are case-insensitive
        p_str = str(p)
        if os.name == "nt":
            # Canonicalize Windows drive letter to lowercase and backslashes
            p_str = p_str.replace("/", "\\")
            if len(p_str) >= 2 and p_str[1] == ":":
                p_str = p_str[0].lower() + p_str[1:]
            return p_str.lower(), display_path
        return str(p), display_path
    except Exception:
        return None, display_path


def parse_read_command(
    cmd: str,
) -> Tuple[Optional[str], ReadView, bool]:
    """Parse a shell command into target path, structured ReadView, and pure-read flag.

    Returns:
        (target_path, ReadView, is_pure_read)
    """
    clean_cmd = cmd.strip()
    if not clean_cmd:
        return None, ReadView(ReadViewType.UNKNOWN_VIEW), False

    # Check for composite commands (semicolons, multiple statements)
    # A single leading variable assignment like `$ErrorActionPreference='Stop';` followed by
    # a single command is acceptable if the remainder is a pure read.
    statements = [s.strip() for s in clean_cmd.split(";") if s.strip()]
    if len(statements) > 1:
        # Check if first is setting or variable assignment and second is read
        if len(statements) == 2 and statements[0].startswith("$ErrorActionPreference"):
            clean_cmd = statements[1]
            statements = [clean_cmd]
        else:
            # Multi-statement / composite script
            # Extract target path if findable, but mark as OTHER_STRUCTURED_VIEW or UNKNOWN_VIEW
            m_path = re.search(r"-(?:LiteralPath|Path)\s+['\"]([^'\"]+)['\"]", clean_cmd, re.IGNORECASE)
            if not m_path:
                m_path = re.search(r"['\"]([^'\"*?<>|]+\.[a-zA-Z0-9_-]+)['\"]", clean_cmd)
            target = m_path.group(1) if m_path else None
            return target, ReadView(ReadViewType.OTHER_STRUCTURED_VIEW, raw_expr=clean_cmd), False

    # 1. PowerShell: Get-Content
    m_gc = re.match(r"^Get-Content\b\s*(.*)$", clean_cmd, re.IGNORECASE)
    if m_gc:
        args_part = m_gc.group(1).strip()

        # Check for pipeline e.g. Get-Content ... | Select-Object ...
        pipe_parts = [p.strip() for p in args_part.split("|")]
        main_gc = pipe_parts[0]
        select_part = pipe_parts[1] if len(pipe_parts) > 1 else None

        # Extract path from main_gc
        target_path: Optional[str] = None
        m_lit = re.search(r"-(?:LiteralPath|Path)\s+['\"]([^'\"]+)['\"]", main_gc, re.IGNORECASE)
        if m_lit:
            target_path = m_lit.group(1)
        else:
            m_lit_unquoted = re.search(r"-(?:LiteralPath|Path)\s+([^\s]+)", main_gc, re.IGNORECASE)
            if m_lit_unquoted:
                target_path = m_lit_unquoted.group(1)
            else:
                m_quoted = re.search(r"['\"]([^'\"]+)['\"]", main_gc)
                if m_quoted:
                    target_path = m_quoted.group(1)
                else:
                    tokens = [t for t in main_gc.split() if not t.startswith("-")]
                    if tokens:
                        target_path = tokens[0]

        # Check for -Tail
        m_tail = re.search(r"-Tail\s+(\d+)", main_gc, re.IGNORECASE)
        if m_tail:
            return target_path, ReadView(ReadViewType.LINE_RANGE, tail_lines=int(m_tail.group(1))), True

        # Check for -TotalCount or -Head
        m_head = re.search(r"-(?:TotalCount|Head)\s+(\d+)", main_gc, re.IGNORECASE)
        if m_head:
            return target_path, ReadView(ReadViewType.LINE_RANGE, start_line=1, end_line=int(m_head.group(1))), True

        # Check for Select-Object in pipeline
        if select_part:
            m_sel = re.match(r"^Select-Object\b\s*(.*)$", select_part, re.IGNORECASE)
            if m_sel:
                s_args = m_sel.group(1)
                m_skip_first = re.search(r"-Skip\s+(\d+)\s+.*-First\s+(\d+)", s_args, re.IGNORECASE)
                if not m_skip_first:
                    m_skip_first = re.search(r"-First\s+(\d+)\s+.*-Skip\s+(\d+)", s_args, re.IGNORECASE)
                    if m_skip_first:
                        first_cnt = int(m_skip_first.group(1))
                        skip_cnt = int(m_skip_first.group(2))
                        return target_path, ReadView(ReadViewType.LINE_RANGE, start_line=skip_cnt + 1, end_line=skip_cnt + first_cnt), True
                else:
                    skip_cnt = int(m_skip_first.group(1))
                    first_cnt = int(m_skip_first.group(2))
                    return target_path, ReadView(ReadViewType.LINE_RANGE, start_line=skip_cnt + 1, end_line=skip_cnt + first_cnt), True

                m_first_only = re.search(r"-First\s+(\d+)", s_args, re.IGNORECASE)
                if m_first_only:
                    return target_path, ReadView(ReadViewType.LINE_RANGE, start_line=1, end_line=int(m_first_only.group(1))), True

                m_last_only = re.search(r"-Last\s+(\d+)", s_args, re.IGNORECASE)
                if m_last_only:
                    return target_path, ReadView(ReadViewType.LINE_RANGE, tail_lines=int(m_last_only.group(1))), True

            return target_path, ReadView(ReadViewType.OTHER_STRUCTURED_VIEW, raw_expr=clean_cmd), False

        # If pure Get-Content without range or pipe -> FULL_FILE
        return target_path, ReadView(ReadViewType.FULL_FILE), True

    # 2. PowerShell index slice: (Get-Content <path>)[start..end]
    m_slice = re.match(r"^\(?Get-Content\s+['\"]?([^'\")]+)['\"]?\)?\s*\[(\d+)\.\.(\d+)\]", clean_cmd, re.IGNORECASE)
    if m_slice:
        p = m_slice.group(1).strip()
        s = int(m_slice.group(2))
        e = int(m_slice.group(3))
        # PowerShell 0-indexed slice -> convert to 1-indexed lines
        return p, ReadView(ReadViewType.LINE_RANGE, start_line=s + 1, end_line=e + 1), True

    # 3. Unix cat / Windows type
    m_cat = re.match(r"^(?:cat|type)\s+['\"]?([^'\"|;]+)['\"]?$", clean_cmd, re.IGNORECASE)
    if m_cat:
        p = m_cat.group(1).strip()
        return p, ReadView(ReadViewType.FULL_FILE), True

    # 4. Unix head: head -n N <path>
    m_head_cmd = re.match(r"^head\s+-n\s+(\d+)\s+['\"]?([^'\"|;]+)['\"]?$", clean_cmd)
    if m_head_cmd:
        n = int(m_head_cmd.group(1))
        p = m_head_cmd.group(2).strip()
        return p, ReadView(ReadViewType.LINE_RANGE, start_line=1, end_line=n), True

    # 5. Unix tail: tail -n N <path>
    m_tail_cmd = re.match(r"^tail\s+-n\s+(\d+)\s+['\"]?([^'\"|;]+)['\"]?$", clean_cmd)
    if m_tail_cmd:
        n = int(m_tail_cmd.group(1))
        p = m_tail_cmd.group(2).strip()
        return p, ReadView(ReadViewType.LINE_RANGE, tail_lines=n), True

    # Fallback: extract target path if possible, but view is UNKNOWN_VIEW
    m_path_fallback = re.search(r"['\"]([^'\"*?<>|]+\.[a-zA-Z0-9_-]+)['\"]", clean_cmd)
    p_fallback = m_path_fallback.group(1) if m_path_fallback else None
    return p_fallback, ReadView(ReadViewType.UNKNOWN_VIEW, raw_expr=clean_cmd), False


def extract_view_bytes(
    file_bytes: bytes,
    view: ReadView,
) -> bytes:
    """Extract view-specific slice of file bytes deterministically."""
    if view.view_type == ReadViewType.FULL_FILE:
        return file_bytes

    if view.view_type == ReadViewType.BYTE_RANGE:
        s = view.start_byte or 0
        e = view.end_byte if view.end_byte is not None else len(file_bytes)
        return file_bytes[s:e]

    if view.view_type == ReadViewType.LINE_RANGE:
        # Split into lines preserving endings
        lines = file_bytes.splitlines(keepends=True)
        total_lines = len(lines)
        if view.tail_lines is not None:
            k = max(0, min(total_lines, view.tail_lines))
            selected = lines[total_lines - k :] if k > 0 else []
            return b"".join(selected)

        s_line = (view.start_line or 1) - 1  # 0-indexed
        e_line = view.end_line if view.end_line is not None else total_lines
        s_line = max(0, min(total_lines, s_line))
        e_line = max(0, min(total_lines, e_line))
        return b"".join(lines[s_line:e_line])

    # For OTHER or UNKNOWN views, fallback to full bytes
    return file_bytes


class ReadReceiptEvaluator:
    """Session-scoped evaluator for file read receipts and shadow references."""

    def __init__(
        self,
        session_id: str,
        base_dir: Optional[pathlib.Path] = None,
    ) -> None:
        self.session_id = session_id
        self.base_dir = base_dir.resolve() if base_dir else None
        # Map: (resolved_source_identity, view_id) -> ReadReceipt
        self._active_receipts: Dict[Tuple[str, str], ReadReceipt] = {}
        self._receipts_by_id: Dict[str, ReadReceipt] = {}
        self._receipt_counter = 0

    def reset_session(self, new_session_id: Optional[str] = None) -> None:
        """Explicitly invalidate all active session receipts."""
        self._active_receipts.clear()
        self._receipts_by_id.clear()
        if new_session_id:
            self.session_id = new_session_id

    def _next_receipt_id(self) -> str:
        self._receipt_counter += 1
        return f"rcpt-{self._receipt_counter:04d}"

    def evaluate_live_read_result(
        self,
        call_id: str,
        file_path: pathlib.Path,
        view: Optional[ReadView] = None,
        call_index: int = 0,
        episode_id: Optional[int] = None,
        timestamp: Optional[str] = None,
        git_head: Optional[str] = None,
        worktree_state: Optional[str] = None,
    ) -> LiveReadResult:
        """Evaluate a live file read on disk against active session receipts.

        Guarantees:
        - Single body read: the exact bytes used for freshness proof are returned to caller
        - Checks Plane A freshness (hash + byte equality)
        - Defends against mtime spoofing (metadata check never bypasses hash check)
        - Keeps Plane B active authorization strictly closed
        - Calculates exact local I/O vs model-visible savings
        """
        requested_view = view or ReadView(ReadViewType.FULL_FILE)
        display_path = str(file_path)

        # 1. Resolve source identity
        norm_id, _ = normalize_source_identity(display_path, self.base_dir)
        if norm_id is None:
            return LiveReadResult(
                raw_bytes=b"",
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=None,
                    disposition=ReadReceiptDisposition.SOURCE_IDENTITY_UNKNOWN_RAW,
                    freshness_level=FreshnessLevel.F0_UNKNOWN,
                    original_path=display_path,
                    resolved_path_identity=None,
                    requested_view=requested_view,
                    raw_bytes=0,
                    delivered_sha256="",
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=None,
                    episode_distance=None,
                    reason="Source path identity cannot be deterministically resolved",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                ),
            )

        # 2. Check file existence
        try:
            st = file_path.stat()
        except FileNotFoundError:
            return LiveReadResult(
                raw_bytes=b"",
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=None,
                    disposition=ReadReceiptDisposition.MISSING_FILE_RAW,
                    freshness_level=FreshnessLevel.F0_UNKNOWN,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=0,
                    delivered_sha256="",
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=None,
                    episode_distance=None,
                    reason="File does not exist on disk",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                ),
            )
        except PermissionError:
            return LiveReadResult(
                raw_bytes=b"",
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=None,
                    disposition=ReadReceiptDisposition.READ_ERROR_RAW,
                    freshness_level=FreshnessLevel.F0_UNKNOWN,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=0,
                    delivered_sha256="",
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=None,
                    episode_distance=None,
                    reason="Permission denied reading file",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                ),
            )
        except Exception as e:
            return LiveReadResult(
                raw_bytes=b"",
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=None,
                    disposition=ReadReceiptDisposition.READ_ERROR_RAW,
                    freshness_level=FreshnessLevel.F0_UNKNOWN,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=0,
                    delivered_sha256="",
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=None,
                    episode_distance=None,
                    reason=f"Disk read failure: {e}",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                ),
            )

        file_size = st.st_size
        mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))

        # 3. Read current view bytes from disk (Single physical read)
        try:
            with open(file_path, "rb") as f:
                full_bytes = f.read()
            view_bytes = extract_view_bytes(full_bytes, requested_view)
        except Exception as e:
            return LiveReadResult(
                raw_bytes=b"",
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=None,
                    disposition=ReadReceiptDisposition.READ_ERROR_RAW,
                    freshness_level=FreshnessLevel.F0_UNKNOWN,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=0,
                    delivered_sha256="",
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=None,
                    episode_distance=None,
                    reason=f"Failed reading view bytes: {e}",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                ),
            )

        raw_bytes_len = len(view_bytes)
        local_io_bytes = len(full_bytes)
        curr_sha256 = hashlib.sha256(view_bytes).hexdigest()

        # 4. Check sensitivity screening
        if contains_sensitive_material(view_bytes):
            return LiveReadResult(
                raw_bytes=view_bytes,
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=None,
                    disposition=ReadReceiptDisposition.SENSITIVE_POLICY_RAW,
                    freshness_level=FreshnessLevel.F0_UNKNOWN,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=raw_bytes_len,
                    delivered_sha256=curr_sha256,
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=None,
                    episode_distance=None,
                    reason="Sensitive material detected in file content; persistence/reference denied",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                    local_io_bytes_read=local_io_bytes,
                    model_visible_raw_bytes=raw_bytes_len,
                    hypothetical_model_visible_reference_bytes=raw_bytes_len,
                ),
            )

        # 5. Check if view is deterministic
        if requested_view.view_type == ReadViewType.UNKNOWN_VIEW:
            return LiveReadResult(
                raw_bytes=view_bytes,
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=None,
                    disposition=ReadReceiptDisposition.VIEW_IDENTITY_UNKNOWN_RAW,
                    freshness_level=FreshnessLevel.F0_UNKNOWN,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=raw_bytes_len,
                    delivered_sha256=curr_sha256,
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=None,
                    episode_distance=None,
                    reason="Read view syntax cannot be deterministically verified",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                    local_io_bytes_read=local_io_bytes,
                    model_visible_raw_bytes=raw_bytes_len,
                    hypothetical_model_visible_reference_bytes=raw_bytes_len,
                ),
            )

        receipt_key = (norm_id, requested_view.view_id)
        existing_receipt = self._active_receipts.get(receipt_key)

        # Case A: First read of this source and view
        if existing_receipt is None:
            rcpt_id = self._next_receipt_id()
            receipt = ReadReceipt(
                receipt_id=rcpt_id,
                session_id=self.session_id,
                original_path=display_path,
                resolved_path_identity=norm_id,
                read_mode="raw",
                requested_view=requested_view,
                delivered_sha256=curr_sha256,
                delivered_bytes=raw_bytes_len,
                file_size=file_size,
                mtime_ns_hint=mtime_ns,
                repo_root_if_known=None,
                git_head_if_known=git_head,
                worktree_state_if_known=worktree_state,
                first_seen_call=call_index,
                last_seen_call=call_index,
                first_seen_episode=episode_id,
                last_seen_episode=episode_id,
                first_seen_timestamp=timestamp,
                last_seen_timestamp=timestamp,
            )
            self._active_receipts[receipt_key] = receipt
            self._receipts_by_id[rcpt_id] = receipt

            return LiveReadResult(
                raw_bytes=view_bytes,
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=rcpt_id,
                    disposition=ReadReceiptDisposition.FIRST_READ_RAW,
                    freshness_level=FreshnessLevel.F0_UNKNOWN,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=raw_bytes_len,
                    delivered_sha256=curr_sha256,
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=None,
                    episode_distance=None,
                    reason="Initial delivery of file read view",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                    local_io_bytes_read=local_io_bytes,
                    model_visible_raw_bytes=raw_bytes_len,
                    hypothetical_model_visible_reference_bytes=raw_bytes_len,
                ),
            )

        # Case B: Subsequent read — evaluate freshness
        call_distance = call_index - existing_receipt.last_seen_call
        ep_distance = (
            (episode_id - existing_receipt.last_seen_episode)
            if (episode_id is not None and existing_receipt.last_seen_episode is not None)
            else None
        )

        # Step B1: Evaluate metadata hint (F2)
        # Note: Even if metadata matches, we MUST check hash and bytes (defense against mtime spoofing)
        meta_match = (
            existing_receipt.mtime_ns_hint == mtime_ns
            and existing_receipt.file_size == file_size
        )
        current_freshness = FreshnessLevel.F2_METADATA_CONSISTENT if meta_match else FreshnessLevel.F0_UNKNOWN

        # Step B2: Evaluate Content Hash (F3)
        if curr_sha256 != existing_receipt.delivered_sha256:
            # Source content changed! Even if mtime was spoofed, hash catches it!
            # Update receipt with new state
            existing_receipt.delivered_sha256 = curr_sha256
            existing_receipt.delivered_bytes = raw_bytes_len
            existing_receipt.file_size = file_size
            existing_receipt.mtime_ns_hint = mtime_ns
            existing_receipt.last_seen_call = call_index
            existing_receipt.last_seen_episode = episode_id

            return LiveReadResult(
                raw_bytes=view_bytes,
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=existing_receipt.receipt_id,
                    disposition=ReadReceiptDisposition.SOURCE_CHANGED_RAW,
                    freshness_level=current_freshness,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=raw_bytes_len,
                    delivered_sha256=curr_sha256,
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=call_distance,
                    episode_distance=ep_distance,
                    reason="File content modified since receipt creation (hash mismatch)",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                    local_io_bytes_read=local_io_bytes,
                    model_visible_raw_bytes=raw_bytes_len,
                    hypothetical_model_visible_reference_bytes=raw_bytes_len,
                ),
            )

        current_freshness = FreshnessLevel.F3_CURRENT_VIEW_HASH_EQUAL

        # Step B3: Evaluate Byte Equality (F4)
        if raw_bytes_len != existing_receipt.delivered_bytes:
            return LiveReadResult(
                raw_bytes=view_bytes,
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=existing_receipt.receipt_id,
                    disposition=ReadReceiptDisposition.SOURCE_CHANGED_RAW,
                    freshness_level=current_freshness,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=raw_bytes_len,
                    delivered_sha256=curr_sha256,
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=call_distance,
                    episode_distance=ep_distance,
                    reason="Byte length mismatch despite hash collision",
                    plane_a_freshness_proven=False,
                    plane_b_active_authorized=False,
                    local_io_bytes_read=local_io_bytes,
                    model_visible_raw_bytes=raw_bytes_len,
                    hypothetical_model_visible_reference_bytes=raw_bytes_len,
                ),
            )

        # F4 Proven!
        current_freshness = FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL

        # Step B4: Economic reference evaluation
        ref_str = format_read_reference(
            receipt_id=existing_receipt.receipt_id,
            sha256_hex=curr_sha256,
            view_id=requested_view.view_id,
            bytes_len=raw_bytes_len,
        )
        ref_bytes = len(ref_str.encode("utf-8"))

        if ref_bytes >= raw_bytes_len:
            # Reference does not save bytes (tiny file expansion)
            return LiveReadResult(
                raw_bytes=view_bytes,
                decision=ReadReceiptDecision(
                    call_id=call_id,
                    receipt_id=existing_receipt.receipt_id,
                    disposition=ReadReceiptDisposition.REFERENCE_NOT_ECONOMIC_RAW,
                    freshness_level=current_freshness,
                    original_path=display_path,
                    resolved_path_identity=norm_id,
                    requested_view=requested_view,
                    raw_bytes=raw_bytes_len,
                    delivered_sha256=curr_sha256,
                    hypothetical_reference=None,
                    reference_bytes=0,
                    hypothetical_bytes_avoided=0,
                    call_distance=call_distance,
                    episode_distance=ep_distance,
                    reason=f"Reference size ({ref_bytes} B) >= raw visible bytes ({raw_bytes_len} B)",
                    plane_a_freshness_proven=True,
                    plane_b_active_authorized=False,
                    local_io_bytes_read=local_io_bytes,
                    model_visible_raw_bytes=raw_bytes_len,
                    hypothetical_model_visible_reference_bytes=raw_bytes_len,
                ),
            )

        # Update receipt access metadata
        existing_receipt.reference_count += 1
        existing_receipt.last_seen_call = call_index
        existing_receipt.last_seen_episode = episode_id
        if timestamp:
            existing_receipt.last_seen_timestamp = timestamp

        avoided_bytes = raw_bytes_len - ref_bytes

        return LiveReadResult(
            raw_bytes=view_bytes,
            decision=ReadReceiptDecision(
                call_id=call_id,
                receipt_id=existing_receipt.receipt_id,
                disposition=ReadReceiptDisposition.LIVE_FRESHNESS_PROVEN_SHADOW_REFERENCE,
                freshness_level=FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL,
                original_path=display_path,
                resolved_path_identity=norm_id,
                requested_view=requested_view,
                raw_bytes=raw_bytes_len,
                delivered_sha256=curr_sha256,
                hypothetical_reference=ref_str,
                reference_bytes=ref_bytes,
                hypothetical_bytes_avoided=avoided_bytes,
                call_distance=call_distance,
                episode_distance=ep_distance,
                reason="Exact view byte identity verified (F4); reference economic",
                plane_a_freshness_proven=True,
                plane_b_active_authorized=False,  # Plane B remains closed in M07!
                local_io_bytes_read=local_io_bytes,
                model_visible_raw_bytes=raw_bytes_len,
                hypothetical_model_visible_reference_bytes=ref_bytes,
            ),
        )

    def evaluate_live_read(
        self,
        call_id: str,
        file_path: pathlib.Path,
        view: Optional[ReadView] = None,
        call_index: int = 0,
        episode_id: Optional[int] = None,
        timestamp: Optional[str] = None,
        git_head: Optional[str] = None,
        worktree_state: Optional[str] = None,
    ) -> ReadReceiptDecision:
        """Evaluate a live file read on disk against active session receipts (compatibility wrapper)."""
        return self.evaluate_live_read_result(
            call_id=call_id,
            file_path=file_path,
            view=view,
            call_index=call_index,
            episode_id=episode_id,
            timestamp=timestamp,
            git_head=git_head,
            worktree_state=worktree_state,
        ).decision

    def evaluate_historical_event(
        self,
        call_id: str,
        command_str: str,
        delivered_bytes: int,
        delivered_sha256: str,
        call_index: int = 0,
        episode_id: Optional[int] = None,
        timestamp: Optional[str] = None,
    ) -> ReadReceiptDecision:
        """Evaluate a historical replay tool call.

        Distinguishes:
        - Structured source vs unknown source
        - Structured view vs unknown view
        - Pure file read vs composite script
        - Historical identical reread candidate (F1) vs changed output
        """
        target_path, view, is_pure = parse_read_command(command_str)

        # Check source identity
        norm_id: Optional[str] = None
        if target_path:
            norm_id, _ = normalize_source_identity(target_path, self.base_dir)

        if norm_id is None:
            return ReadReceiptDecision(
                call_id=call_id,
                receipt_id=None,
                disposition=ReadReceiptDisposition.SOURCE_IDENTITY_UNKNOWN_RAW,
                freshness_level=FreshnessLevel.F0_UNKNOWN,
                original_path=target_path,
                resolved_path_identity=None,
                requested_view=view,
                raw_bytes=delivered_bytes,
                delivered_sha256=delivered_sha256,
                hypothetical_reference=None,
                reference_bytes=0,
                hypothetical_bytes_avoided=0,
                call_distance=None,
                episode_distance=None,
                reason="Source path identity cannot be deterministically resolved",
                plane_a_freshness_proven=False,
                plane_b_active_authorized=False,
                local_io_bytes_read=0,
                model_visible_raw_bytes=delivered_bytes,
                hypothetical_model_visible_reference_bytes=delivered_bytes,
            )

        if view.view_type == ReadViewType.UNKNOWN_VIEW:
            return ReadReceiptDecision(
                call_id=call_id,
                receipt_id=None,
                disposition=ReadReceiptDisposition.VIEW_IDENTITY_UNKNOWN_RAW,
                freshness_level=FreshnessLevel.F0_UNKNOWN,
                original_path=target_path,
                resolved_path_identity=norm_id,
                requested_view=view,
                raw_bytes=delivered_bytes,
                delivered_sha256=delivered_sha256,
                hypothetical_reference=None,
                reference_bytes=0,
                hypothetical_bytes_avoided=0,
                call_distance=None,
                episode_distance=None,
                reason="Read view syntax cannot be deterministically verified",
                plane_a_freshness_proven=False,
                plane_b_active_authorized=False,
                local_io_bytes_read=0,
                model_visible_raw_bytes=delivered_bytes,
                hypothetical_model_visible_reference_bytes=delivered_bytes,
            )

        receipt_key = (norm_id, view.view_id)
        existing_receipt = self._active_receipts.get(receipt_key)

        if existing_receipt is None:
            rcpt_id = self._next_receipt_id()
            receipt = ReadReceipt(
                receipt_id=rcpt_id,
                session_id=self.session_id,
                original_path=target_path or "",
                resolved_path_identity=norm_id,
                read_mode="raw",
                requested_view=view,
                delivered_sha256=delivered_sha256,
                delivered_bytes=delivered_bytes,
                first_seen_call=call_index,
                last_seen_call=call_index,
                first_seen_episode=episode_id,
                last_seen_episode=episode_id,
                first_seen_timestamp=timestamp,
                last_seen_timestamp=timestamp,
            )
            self._active_receipts[receipt_key] = receipt
            self._receipts_by_id[rcpt_id] = receipt

            return ReadReceiptDecision(
                call_id=call_id,
                receipt_id=rcpt_id,
                disposition=ReadReceiptDisposition.FIRST_READ_RAW,
                freshness_level=FreshnessLevel.F0_UNKNOWN,
                original_path=target_path,
                resolved_path_identity=norm_id,
                requested_view=view,
                raw_bytes=delivered_bytes,
                delivered_sha256=delivered_sha256,
                hypothetical_reference=None,
                reference_bytes=0,
                hypothetical_bytes_avoided=0,
                call_distance=None,
                episode_distance=None,
                reason="Initial historical read delivery",
                plane_a_freshness_proven=False,
                plane_b_active_authorized=False,
                local_io_bytes_read=0,
                model_visible_raw_bytes=delivered_bytes,
                hypothetical_model_visible_reference_bytes=delivered_bytes,
            )

        call_distance = call_index - existing_receipt.last_seen_call
        ep_distance = (
            (episode_id - existing_receipt.last_seen_episode)
            if (episode_id is not None and existing_receipt.last_seen_episode is not None)
            else None
        )

        if delivered_sha256 != existing_receipt.delivered_sha256:
            existing_receipt.delivered_sha256 = delivered_sha256
            existing_receipt.delivered_bytes = delivered_bytes
            existing_receipt.last_seen_call = call_index
            existing_receipt.last_seen_episode = episode_id

            return ReadReceiptDecision(
                call_id=call_id,
                receipt_id=existing_receipt.receipt_id,
                disposition=ReadReceiptDisposition.SOURCE_CHANGED_RAW,
                freshness_level=FreshnessLevel.F0_UNKNOWN,
                original_path=target_path,
                resolved_path_identity=norm_id,
                requested_view=view,
                raw_bytes=delivered_bytes,
                delivered_sha256=delivered_sha256,
                hypothetical_reference=None,
                reference_bytes=0,
                hypothetical_bytes_avoided=0,
                call_distance=call_distance,
                episode_distance=ep_distance,
                reason="Historical delivered output changed from previous delivery",
                plane_a_freshness_proven=False,
                plane_b_active_authorized=False,
                local_io_bytes_read=0,
                model_visible_raw_bytes=delivered_bytes,
                hypothetical_model_visible_reference_bytes=delivered_bytes,
            )

        # Identical historical output bytes delivered for same source and view!
        ref_str = format_read_reference(
            receipt_id=existing_receipt.receipt_id,
            sha256_hex=delivered_sha256,
            view_id=view.view_id,
            bytes_len=delivered_bytes,
        )
        ref_bytes = len(ref_str.encode("utf-8"))

        if ref_bytes >= delivered_bytes:
            return ReadReceiptDecision(
                call_id=call_id,
                receipt_id=existing_receipt.receipt_id,
                disposition=ReadReceiptDisposition.REFERENCE_NOT_ECONOMIC_RAW,
                freshness_level=FreshnessLevel.F1_HISTORICAL_OUTPUT_IDENTITY,
                original_path=target_path,
                resolved_path_identity=norm_id,
                requested_view=view,
                raw_bytes=delivered_bytes,
                delivered_sha256=delivered_sha256,
                hypothetical_reference=None,
                reference_bytes=0,
                hypothetical_bytes_avoided=0,
                call_distance=call_distance,
                episode_distance=ep_distance,
                reason=f"Reference size ({ref_bytes} B) >= raw bytes ({delivered_bytes} B)",
                plane_a_freshness_proven=True,
                plane_b_active_authorized=False,
                local_io_bytes_read=0,
                model_visible_raw_bytes=delivered_bytes,
                hypothetical_model_visible_reference_bytes=delivered_bytes,
            )

        existing_receipt.reference_count += 1
        existing_receipt.last_seen_call = call_index
        existing_receipt.last_seen_episode = episode_id
        avoided_bytes = delivered_bytes - ref_bytes

        return ReadReceiptDecision(
            call_id=call_id,
            receipt_id=existing_receipt.receipt_id,
            disposition=ReadReceiptDisposition.HISTORICAL_IDENTICAL_READ_CANDIDATE,
            freshness_level=FreshnessLevel.F1_HISTORICAL_OUTPUT_IDENTITY,
            original_path=target_path,
            resolved_path_identity=norm_id,
            requested_view=view,
            raw_bytes=delivered_bytes,
            delivered_sha256=delivered_sha256,
            hypothetical_reference=ref_str,
            reference_bytes=ref_bytes,
            hypothetical_bytes_avoided=avoided_bytes,
            call_distance=call_distance,
            episode_distance=ep_distance,
            reason="Historical identical output bytes delivered for same source and view (F1)",
            plane_a_freshness_proven=True,
            plane_b_active_authorized=False,
            local_io_bytes_read=0,
            model_visible_raw_bytes=delivered_bytes,
            hypothetical_model_visible_reference_bytes=ref_bytes,
        )


class ReadReceiptLedger:
    """Append-only, SHA-256 hash-chained ledger for read receipt events."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.entries: List[Dict[str, Any]] = []
        self._last_hash = "0" * 64

    def record_event(
        self,
        event_id: str,
        decision: ReadReceiptDecision,
    ) -> Dict[str, Any]:
        """Record a decision into the hash-chained ledger."""
        source_hash = (
            hashlib.sha256(decision.resolved_path_identity.encode()).hexdigest()
            if decision.resolved_path_identity
            else "NONE"
        )
        view_id = decision.requested_view.view_id if decision.requested_view else "NONE"

        payload_to_hash = (
            f"{self._last_hash}:"
            f"{event_id}:"
            f"{decision.receipt_id or 'NONE'}:"
            f"{source_hash}:"
            f"{view_id}:"
            f"{decision.freshness_level.value}:"
            f"{decision.delivered_sha256}:"
            f"{decision.raw_bytes}:"
            f"{decision.reference_bytes}:"
            f"{decision.disposition.value}"
        )
        current_hash = hashlib.sha256(payload_to_hash.encode("utf-8")).hexdigest()

        entry = {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "event_id": event_id,
            "call_id": decision.call_id,
            "receipt_id": decision.receipt_id,
            "source_identity_hash": source_hash,
            "view_identity": view_id,
            "freshness_level": decision.freshness_level.value,
            "delivered_sha256": decision.delivered_sha256,
            "raw_bytes": decision.raw_bytes,
            "reference_bytes": decision.reference_bytes,
            "hypothetical_bytes_avoided": decision.hypothetical_bytes_avoided,
            "call_distance": decision.call_distance,
            "episode_distance": decision.episode_distance,
            "disposition": decision.disposition.value,
            "reason": decision.reason,
            "plane_a_freshness_proven": decision.plane_a_freshness_proven,
            "plane_b_active_authorized": decision.plane_b_active_authorized,
            "previous_event_hash": self._last_hash,
            "event_hash": current_hash,
        }
        self._last_hash = current_hash
        self.entries.append(entry)
        return entry

    def generate_manifest(self) -> Dict[str, Any]:
        """Produce deterministic ledger manifest."""
        dispositions = Counter(e["disposition"] for e in self.entries)
        freshness_levels = Counter(e["freshness_level"] for e in self.entries)
        total_raw = sum(e["raw_bytes"] for e in self.entries)
        total_ref = sum(e["reference_bytes"] for e in self.entries)
        total_avoided = sum(e["hypothetical_bytes_avoided"] for e in self.entries)

        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": self.session_id,
            "total_events": len(self.entries),
            "final_event_hash": self._last_hash,
            "dispositions": dict(dispositions),
            "freshness_levels": dict(freshness_levels),
            "total_raw_bytes": total_raw,
            "total_reference_bytes": total_ref,
            "total_hypothetical_bytes_avoided": total_avoided,
            "active_read_reference_suppression": False,
            "behavioral_equivalence": "UNKNOWN",
        }
