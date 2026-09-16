"""Context Waste Census analyzer for real coding-agent workloads.

Measures empirical context cost, reexposure waste (LeanCTX), representation
waste (Headroom), and discovery cost/redundancy (Aider/AgentMap) without
implementing new transforms or runtime engine integrations.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import pathlib
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from fiofilter.search_corpus import (
    RG_STANDARD_PATH_LINE_TEXT,
    InvocationRejected,
    ResultRejected,
    classify_rg_command,
    contains_shell_failure_wrapper,
    contains_upstream_truncation_marker,
    decode_execution_result,
    extract_structured_exec_command,
)
from fiofilter.transforms.t02_rg_standard_group import (
    RgStandardEvidence,
    RgStandardLosslessGrouping,
)

CENSUS_SCHEMA_VERSION = "M05_CONTEXT_CENSUS_V1"

# Evidence tiers
TIER_PROVEN_AVOIDABLE = "PROVEN_AVOIDABLE"
TIER_STRONG_DETERMINISTIC_OPPORTUNITY = "STRONG_DETERMINISTIC_OPPORTUNITY"
TIER_OBSERVED_COST = "OBSERVED_COST"
TIER_HYPOTHESIS_ONLY = "HYPOTHESIS_ONLY"
TIER_UNKNOWN = "UNKNOWN"

# Tool taxonomy
FAMILIES = (
    "FILE_READ",
    "SEARCH",
    "DIRECTORY_LIST",
    "GIT",
    "TEST",
    "BUILD",
    "WRITE_OR_EDIT",
    "SCRIPT",
    "OTHER",
    "UNKNOWN",
)


@dataclass(frozen=True)
class CensusEvent:
    """Internal event representing a paired tool call and its execution output."""

    call_id: str
    timestamp: Optional[str]
    record_index: int
    episode_id: int
    tool_family: str
    producer: str
    command: Optional[str]
    exit_code: Optional[int]
    output_bytes: int
    output_sha256: str
    raw_content_b64: str
    target_path: Optional[str]
    line_range: Optional[Tuple[int, int]]
    operation_class: str
    is_mutation: bool
    truncated: bool


def _extract_path_from_command(cmd: str) -> Optional[str]:
    """Extract target file or directory path when structurally unambiguous."""
    # PowerShell -LiteralPath '...' or -Path '...'
    m_lit = re.search(r"-(?:LiteralPath|Path)\s+['\"]([^'\"]+)['\"]", cmd, re.IGNORECASE)
    if m_lit:
        return m_lit.group(1).replace("/", "\\")
    # Quoted path with file extension
    m_quote = re.search(r"['\"]([^'\"*?<>|]+\.[a-zA-Z0-9_-]+)['\"]", cmd)
    if m_quote:
        return m_quote.group(1).replace("/", "\\")
    # Unix cat/head/tail argument
    tokens = cmd.split()
    if len(tokens) >= 2 and tokens[0] in ("cat", "head", "tail", "type"):
        for tok in reversed(tokens[1:]):
            if not tok.startswith("-") and "." in tok:
                return tok.replace("/", "\\")
    return None


def _extract_range_from_command(cmd: str) -> Optional[Tuple[int, int]]:
    """Extract line range (start, end) if explicitly present."""
    # PowerShell array slice: $x[10..50]
    m_slice = re.search(r"\[(\d+)\.\.(\d+)\]", cmd)
    if m_slice:
        return int(m_slice.group(1)), int(m_slice.group(2))
    # Select-Object -Skip S -First N
    m_skip_first = re.search(
        r"Select-Object\s+.*-Skip\s+(\d+)\s+.*-First\s+(\d+)", cmd, re.IGNORECASE
    )
    if m_skip_first:
        s = int(m_skip_first.group(1))
        n = int(m_skip_first.group(2))
        return s, s + n
    # Select-Object -First N
    m_first = re.search(r"Select-Object\s+.*-First\s+(\d+)", cmd, re.IGNORECASE)
    if m_first:
        return 0, int(m_first.group(1))
    # head -n N
    m_head = re.search(r"\bhead\s+-n\s+(\d+)", cmd)
    if m_head:
        return 0, int(m_head.group(1))
    return None


def classify_tool_call(
    call_payload: Dict[str, Any]
) -> Tuple[str, Optional[str], Optional[str], Optional[Tuple[int, int]], bool, str]:
    """Classify tool call payload into taxonomy and extract targets/ranges.

    Returns:
        (tool_family, command, target_path, line_range, is_mutation, operation_class)
    """
    raw_input = call_payload.get("input")
    cmd: Optional[str] = None
    is_mutation = False

    try:
        cmd = extract_structured_exec_command(call_payload)
    except InvocationRejected:
        pass

    # Check for mutation indicators in input
    input_str = str(raw_input)
    if any(
        w in input_str
        for w in (
            "WriteAllText",
            "Set-Content",
            "Out-File",
            "apply_patch",
            "git apply",
            "patch ",
        )
    ):
        is_mutation = True

    if cmd is None:
        # Complex or multi-tool script wrapper
        if isinstance(raw_input, str):
            if "tools.codex_app__read_thread" in raw_input:
                return "OTHER", None, None, None, is_mutation, "other"
            if is_mutation:
                return "WRITE_OR_EDIT", None, None, None, True, "write"
            return "SCRIPT", None, None, None, False, "script"
        return "UNKNOWN", None, None, None, is_mutation, "unknown"

    cmd_clean = cmd.strip()
    target_path = _extract_path_from_command(cmd_clean)
    line_range = _extract_range_from_command(cmd_clean)

    # Check explicit mutation in command
    if is_mutation or re.search(r"\b(apply_patch|git apply|patch|Set-Content|Out-File)\b", cmd_clean, re.IGNORECASE):
        return "WRITE_OR_EDIT", cmd, target_path, line_range, True, "write"
    if re.search(r"(^|[^\d])>[^>]", cmd_clean) and not re.search(r"\b(pytest|python -m pytest)\b", cmd_clean):
        return "WRITE_OR_EDIT", cmd, target_path, line_range, True, "write"

    # Check TEST
    if re.search(r"\b(pytest|python -m pytest|python -m unittest|npm test|cargo test|ctest)\b", cmd_clean):
        return "TEST", cmd, target_path, line_range, False, "test"

    # Check BUILD
    if re.search(r"\b(python -m compileall|cargo build|npm run build|make)\b", cmd_clean):
        return "BUILD", cmd, target_path, line_range, False, "build"

    # Check SEARCH
    if re.match(r"^(rg|grep|git grep|findstr)\b", cmd_clean):
        return "SEARCH", cmd, target_path, line_range, False, "search"

    # Check FILE_READ
    if re.search(r"\b(Get-Content|cat|head|tail|type|more|less)\b", cmd_clean, re.IGNORECASE):
        return "FILE_READ", cmd, target_path, line_range, False, "read"

    # Check DIRECTORY_LIST
    if re.search(r"\b(Get-ChildItem|dir|ls|tree)\b", cmd_clean, re.IGNORECASE):
        return "DIRECTORY_LIST", cmd, target_path, line_range, False, "read"

    # Check GIT
    if re.match(r"^git\b", cmd_clean):
        if re.search(r"\b(commit|merge|rebase|cherry-pick|revert)\b", cmd_clean):
            return "GIT", cmd, target_path, line_range, True, "git"
        return "GIT", cmd, target_path, line_range, False, "git"

    # Check SCRIPT
    if re.match(r"^(python|node|bash|sh|powershell|pwsh|\./|wsl\.exe)\b", cmd_clean):
        return "SCRIPT", cmd, target_path, line_range, False, "script"

    # Check OTHER
    if re.match(r"^(echo|cd|pwd|which|where|sleep|Start-Sleep|gcloud|Get-Process|Get-CimInstance)\b", cmd_clean, re.IGNORECASE):
        return "OTHER", cmd, target_path, line_range, False, "other"

    # Check variable assignment prefix e.g. $repo = ...; <subcommand>
    m_sub = re.search(r";\s*([a-zA-Z0-9_.-]+)\b", cmd_clean)
    if m_sub:
        sub_word = m_sub.group(1).lower()
        if sub_word in ("git", "pytest", "rg", "get-content", "get-childitem"):
            sub_cmd = cmd_clean[m_sub.start() + 1 :].strip()
            # Recursive classify
            fam, _, tp, lr, mut, op = classify_tool_call({"type": "custom_tool_call", "name": "exec", "input": {"cmd": sub_cmd}})
            return fam, cmd, tp or target_path, lr or line_range, mut or is_mutation, op

    return "UNKNOWN", cmd, target_path, line_range, is_mutation, "unknown"


def decode_tool_output(output_payload: Dict[str, Any]) -> Tuple[bytes, Optional[int], bool]:
    """Safely decode tool output bytes, exit code, and truncation status."""
    try:
        res = decode_execution_result(output_payload)
        return res.content, res.exit_code, res.truncated
    except ResultRejected:
        pass

    raw = output_payload.get("output")
    exit_code: Optional[int] = None
    truncated = False
    content_bytes = b""

    if isinstance(raw, str):
        content_bytes = raw.encode("utf-8")
        if "truncated" in raw.lower():
            truncated = True
    elif isinstance(raw, (dict, list)):
        content_bytes = json.dumps(raw).encode("utf-8")

    return content_bytes, exit_code, truncated


class ContextWasteCensus:
    """Offline analyzer computing empirical context waste and cost metrics."""

    def __init__(self, session_path: pathlib.Path) -> None:
        self.session_path = session_path.resolve()
        self.events: List[CensusEvent] = []
        self.episodes: Dict[int, List[CensusEvent]] = defaultdict(list)
        self.user_prompts: List[Dict[str, Any]] = []
        self._t02 = RgStandardLosslessGrouping()

    def load_session(self) -> None:
        """Parse session JSONL and extract all paired CensusEvent records."""
        calls: Dict[str, Dict[str, Any]] = {}
        call_records: Dict[str, int] = {}
        pending_outputs: Dict[str, Dict[str, Any]] = {}

        current_episode_id = 0
        record_idx = 0

        with open(self.session_path, "r", encoding="utf-8") as f:
            for line in f:
                record_idx += 1
                try:
                    d = json.loads(line)
                except Exception:
                    continue

                ts = d.get("timestamp")
                payload = d.get("payload", {})
                ptype = payload.get("type")

                if ptype == "message" and payload.get("role") == "user":
                    current_episode_id += 1
                    self.user_prompts.append(
                        {
                            "episode_id": current_episode_id,
                            "timestamp": ts,
                            "record_index": record_idx,
                            "id": payload.get("id"),
                        }
                    )
                elif ptype == "custom_tool_call":
                    call_id = payload.get("call_id")
                    if call_id:
                        calls[call_id] = {
                            "timestamp": ts,
                            "record_index": record_idx,
                            "episode_id": current_episode_id,
                            "payload": payload,
                        }
                elif ptype == "custom_tool_call_output":
                    call_id = payload.get("call_id")
                    if call_id:
                        pending_outputs[call_id] = {
                            "timestamp": ts,
                            "record_index": record_idx,
                            "payload": payload,
                        }

        # Pair calls and outputs in order of call record_index
        sorted_calls = sorted(calls.items(), key=lambda x: x[1]["record_index"])
        for call_id, call_info in sorted_calls:
            out_info = pending_outputs.get(call_id)
            if not out_info:
                continue

            call_payload = call_info["payload"]
            out_payload = out_info["payload"]

            fam, cmd, target_path, line_range, is_mut, op_class = classify_tool_call(
                call_payload
            )
            content_bytes, exit_code, truncated = decode_tool_output(out_payload)
            sha256 = hashlib.sha256(content_bytes).hexdigest()

            event = CensusEvent(
                call_id=call_id,
                timestamp=call_info["timestamp"],
                record_index=call_info["record_index"],
                episode_id=call_info["episode_id"],
                tool_family=fam,
                producer=call_payload.get("name", "exec"),
                command=cmd,
                exit_code=exit_code,
                output_bytes=len(content_bytes),
                output_sha256=sha256,
                raw_content_b64=base64.b64encode(content_bytes).decode("ascii"),
                target_path=target_path,
                line_range=line_range,
                operation_class=op_class,
                is_mutation=is_mut,
                truncated=truncated,
            )
            self.events.append(event)
            self.episodes[event.episode_id].append(event)

    def analyze(self) -> Dict[str, Any]:
        """Execute full census analysis across all dimensions."""
        if not self.events:
            self.load_session()

        total_calls = len(self.events)
        total_output_bytes = sum(e.output_bytes for e in self.events)
        parseable_calls = sum(1 for e in self.events if e.tool_family != "UNKNOWN")
        unclassified_calls = total_calls - parseable_calls
        coverage_pct = (parseable_calls / total_calls * 100.0) if total_calls > 0 else 0.0

        # 1. Tool Family Distribution
        family_stats = {}
        for fam in FAMILIES:
            fam_events = [e for e in self.events if e.tool_family == fam]
            if not fam_events:
                family_stats[fam] = {
                    "calls": 0,
                    "bytes": 0,
                    "share_of_total_bytes_pct": 0.0,
                    "min_bytes": 0,
                    "median_bytes": 0,
                    "p90_bytes": 0,
                    "max_bytes": 0,
                }
                continue
            b_list = sorted(e.output_bytes for e in fam_events)
            total_b = sum(b_list)
            p90_idx = int(math.ceil(0.9 * len(b_list))) - 1
            family_stats[fam] = {
                "calls": len(fam_events),
                "bytes": total_b,
                "share_of_total_bytes_pct": round(total_b / total_output_bytes * 100.0, 2) if total_output_bytes > 0 else 0.0,
                "min_bytes": b_list[0],
                "median_bytes": b_list[len(b_list) // 2],
                "p90_bytes": b_list[p90_idx],
                "max_bytes": b_list[-1],
            }

        # 2. Reexposure Analysis (LeanCTX)
        # Tier R1 — Exact Redelivery
        # Group by: (tool_family, target_identity, output_sha256)
        content_deliveries: Dict[Tuple[str, str], List[CensusEvent]] = defaultdict(list)
        for e in self.events:
            # Target identity: target_path if available, otherwise exact command, otherwise sha
            target_key = e.target_path or e.command or "UNKNOWN"
            content_deliveries[(target_key, e.output_sha256)].append(e)

        exact_redelivery_events = 0
        exact_redelivery_bytes_gross = 0
        proven_reexposure_bytes = 0
        reexposure_event_ids: Set[str] = set()

        for (target_key, sha), ev_list in content_deliveries.items():
            if len(ev_list) > 1 and target_key != "UNKNOWN":
                exact_redelivery_events += len(ev_list)
                b_size = ev_list[0].output_bytes
                exact_redelivery_bytes_gross += b_size * len(ev_list)
                # First delivery is required; subsequent are reexposure
                proven_reexposure_bytes += b_size * (len(ev_list) - 1)
                for ev in ev_list[1:]:
                    reexposure_event_ids.add(ev.call_id)

        # Same-path rereads
        reads_by_path: Dict[str, List[CensusEvent]] = defaultdict(list)
        for e in self.events:
            if e.tool_family == "FILE_READ" and e.target_path:
                reads_by_path[e.target_path].append(e)

        same_path_read_count = 0
        identical_reread_count = 0
        identical_reread_bytes = 0
        changed_reread_count = 0
        delta_candidates: List[Dict[str, Any]] = []
        overlapping_range_events = 0
        overlapping_lines = 0
        overlap_bytes_estimate = 0

        for path, r_list in reads_by_path.items():
            same_path_read_count += len(r_list)
            if len(r_list) < 2:
                continue
            for i in range(1, len(r_list)):
                prev = r_list[i - 1]
                curr = r_list[i]
                if curr.output_sha256 == prev.output_sha256:
                    identical_reread_count += 1
                    identical_reread_bytes += curr.output_bytes
                else:
                    changed_reread_count += 1
                    delta_candidates.append(
                        {
                            "path": path,
                            "prev_call_id": prev.call_id,
                            "curr_call_id": curr.call_id,
                            "prev_bytes": prev.output_bytes,
                            "curr_bytes": curr.output_bytes,
                        }
                    )

                # Check line range overlap
                if prev.line_range and curr.line_range:
                    s1, e1 = prev.line_range
                    s2, e2 = curr.line_range
                    overlap_start = max(s1, s2)
                    overlap_end = min(e1, e2)
                    if overlap_end >= overlap_start:
                        overlap_len = overlap_end - overlap_start + 1
                        overlapping_range_events += 1
                        overlapping_lines += overlap_len
                        # Estimate bytes per line
                        avg_bpl = curr.output_bytes / max(1, (e2 - s2 + 1))
                        overlap_bytes_estimate += int(avg_bpl * overlap_len)

        # 3. Representation Waste Analysis (Headroom Lane)
        t02_eligible_events = 0
        t02_transformable_events = 0
        t02_raw_bytes = 0
        t02_visible_bytes = 0
        t02_bytes_saved = 0
        t02_event_ids: Set[str] = set()

        for e in self.events:
            if e.tool_family == "SEARCH" and e.command and e.command.startswith("rg"):
                raw_bytes = base64.b64decode(e.raw_content_b64)
                evidence = RgStandardEvidence(
                    command=e.command,
                    command_structurally_grounded=True,
                    single_search_producer=True,
                    exit_code=e.exit_code if e.exit_code is not None else 0,
                    truncated=e.truncated,
                    upstream_truncation_observed=contains_upstream_truncation_marker(raw_bytes),
                    shell_failure_wrapper_observed=contains_shell_failure_wrapper(raw_bytes),
                )
                try:
                    outcome = self._t02.evaluate(raw_bytes, evidence)
                    t02_eligible_events += 1
                    t02_raw_bytes += len(raw_bytes)
                    t02_visible_bytes += len(outcome.visible_content)
                    if outcome.applied:
                        t02_transformable_events += 1
                        t02_bytes_saved += len(raw_bytes) - len(outcome.visible_content)
                        t02_event_ids.add(e.call_id)
                except Exception:
                    pass

        t02_reduction_pct = (
            round(t02_bytes_saved / t02_raw_bytes * 100.0, 2)
            if t02_raw_bytes > 0
            else 0.0
        )

        # 4. Discovery Cost & Redundancy Analysis (Aider/AgentMap Lane)
        episode_stats = []
        total_discovery_calls = 0
        total_discovery_bytes = 0
        total_unique_files_discovered: Set[str] = set()
        duplicate_search_calls = 0
        duplicate_search_bytes = 0
        duplicate_dir_calls = 0
        duplicate_dir_bytes = 0
        duplicate_read_calls = 0
        duplicate_read_bytes = 0
        discovery_redundant_event_ids: Set[str] = set()

        chain_counter = Counter()

        for ep_id, ep_events in self.episodes.items():
            first_write_idx = None
            for idx, ev in enumerate(ep_events):
                if ev.is_mutation:
                    first_write_idx = idx
                    break

            pre_write_events = (
                ep_events[:first_write_idx] if first_write_idx is not None else ep_events
            )
            post_write_events = (
                ep_events[first_write_idx:] if first_write_idx is not None else []
            )

            s_calls = sum(1 for ev in pre_write_events if ev.tool_family == "SEARCH")
            s_bytes = sum(ev.output_bytes for ev in pre_write_events if ev.tool_family == "SEARCH")
            r_calls = sum(1 for ev in pre_write_events if ev.tool_family == "FILE_READ")
            r_bytes = sum(ev.output_bytes for ev in pre_write_events if ev.tool_family == "FILE_READ")
            d_calls = sum(1 for ev in pre_write_events if ev.tool_family == "DIRECTORY_LIST")
            d_bytes = sum(ev.output_bytes for ev in pre_write_events if ev.tool_family == "DIRECTORY_LIST")
            b_total = sum(ev.output_bytes for ev in pre_write_events)

            total_discovery_calls += len(pre_write_events)
            total_discovery_bytes += b_total

            read_files_pre = {ev.target_path for ev in pre_write_events if ev.target_path}
            total_unique_files_discovered.update(read_files_pre)

            modified_files = {ev.target_path for ev in post_write_events if ev.target_path and ev.is_mutation}
            supporting_reads = read_files_pre - modified_files

            # Duplicate detection within discovery
            seen_search_cmds = set()
            seen_dir_cmds = set()
            seen_read_shas = set()

            for ev in pre_write_events:
                if ev.tool_family == "SEARCH" and ev.command:
                    if ev.command in seen_search_cmds:
                        duplicate_search_calls += 1
                        duplicate_search_bytes += ev.output_bytes
                        discovery_redundant_event_ids.add(ev.call_id)
                    seen_search_cmds.add(ev.command)
                elif ev.tool_family == "DIRECTORY_LIST" and ev.command:
                    if ev.command in seen_dir_cmds:
                        duplicate_dir_calls += 1
                        duplicate_dir_bytes += ev.output_bytes
                        discovery_redundant_event_ids.add(ev.call_id)
                    seen_dir_cmds.add(ev.command)
                elif ev.tool_family == "FILE_READ" and ev.target_path:
                    key = (ev.target_path, ev.output_sha256)
                    if key in seen_read_shas:
                        duplicate_read_calls += 1
                        duplicate_read_bytes += ev.output_bytes
                        discovery_redundant_event_ids.add(ev.call_id)
                    seen_read_shas.add(key)

            # Chain characterization
            chain_tokens = [ev.operation_class for ev in ep_events[:6]]
            if len(chain_tokens) >= 3:
                chain_key = " -> ".join(chain_tokens[:3])
                chain_counter[chain_key] += 1

            episode_stats.append(
                {
                    "episode_id": ep_id,
                    "total_calls": len(ep_events),
                    "first_write_index": first_write_idx,
                    "discovery_calls": len(pre_write_events),
                    "discovery_bytes": b_total,
                    "search_calls": s_calls,
                    "search_bytes": s_bytes,
                    "read_calls": r_calls,
                    "read_bytes": r_bytes,
                    "directory_calls": d_calls,
                    "directory_bytes": d_bytes,
                    "files_read_count": len(read_files_pre),
                    "files_modified_count": len(modified_files),
                    "supporting_reads_count": len(supporting_reads),
                }
            )

        proven_discovery_redundancy_bytes = (
            duplicate_search_bytes + duplicate_dir_bytes + duplicate_read_bytes
        )

        # 5. Deduplication of Proven Avoidable Bytes (No Double Counting)
        # Precedence: EXACT_REEXPOSURE -> T02_REPRESENTATION -> DISCOVERY_DUPLICATE
        all_avoidable_event_ids = reexposure_event_ids | t02_event_ids | discovery_redundant_event_ids
        event_by_id = {e.call_id: e for e in self.events}

        deduplicated_proven_avoidable_bytes = 0
        attribution_counts = Counter()

        for call_id in all_avoidable_event_ids:
            ev = event_by_id[call_id]
            if call_id in reexposure_event_ids:
                deduplicated_proven_avoidable_bytes += ev.output_bytes
                attribution_counts["EXACT_REEXPOSURE"] += 1
            elif call_id in t02_event_ids:
                # T02 saves a fraction of the event's raw bytes
                # Compute exact saved bytes for this event
                raw = base64.b64decode(ev.raw_content_b64)
                evidence = RgStandardEvidence(
                    command=ev.command or "",
                    command_structurally_grounded=True,
                    single_search_producer=True,
                    exit_code=ev.exit_code or 0,
                    truncated=ev.truncated,
                    upstream_truncation_observed=False,
                    shell_failure_wrapper_observed=False,
                )
                outcome = self._t02.evaluate(raw, evidence)
                saved = len(raw) - len(outcome.visible_content)
                deduplicated_proven_avoidable_bytes += saved
                attribution_counts["T02_REPRESENTATION"] += 1
            elif call_id in discovery_redundant_event_ids:
                deduplicated_proven_avoidable_bytes += ev.output_bytes
                attribution_counts["DISCOVERY_DUPLICATE"] += 1

        overall_proven_avoidable_pct = (
            round(deduplicated_proven_avoidable_bytes / total_output_bytes * 100.0, 2)
            if total_output_bytes > 0
            else 0.0
        )

        # Priority Decision Logic
        # Compare highest observed cost, highest proven avoidable bytes, highest strong opportunity
        # Classes: REEXPOSURE, REPRESENTATION, DISCOVERY
        observed_costs = {
            "DISCOVERY": total_discovery_bytes,
            "REEXPOSURE": exact_redelivery_bytes_gross,
            "REPRESENTATION": family_stats["SEARCH"]["bytes"],
        }
        highest_observed_cost_class = max(observed_costs.items(), key=lambda x: x[1])[0]

        proven_avoidables = {
            "REEXPOSURE": proven_reexposure_bytes,
            "REPRESENTATION": t02_bytes_saved,
            "DISCOVERY": proven_discovery_redundancy_bytes,
        }
        highest_proven_avoidable_class = max(proven_avoidables.items(), key=lambda x: x[1])[0]

        strong_opportunities = {
            "REEXPOSURE": identical_reread_bytes,
            "REPRESENTATION": family_stats["SEARCH"]["bytes"] - t02_visible_bytes,
            "DISCOVERY": sum(ep["read_bytes"] for ep in episode_stats if ep["supporting_reads_count"] > 0),
        }
        highest_strong_opportunity_class = max(strong_opportunities.items(), key=lambda x: x[1])[0]

        # Select NEXT_LANE based on empirical decision rule
        if proven_reexposure_bytes > t02_bytes_saved * 2:
            next_lane = "REEXPOSURE_SHADOW"
        elif t02_bytes_saved >= proven_reexposure_bytes:
            next_lane = "REPRESENTATION_NEXT_GRAMMAR"
        else:
            next_lane = "DISCOVERY_STRUCTURAL_SHADOW"

        return {
            "schema_version": CENSUS_SCHEMA_VERSION,
            "denominator": {
                "total_tool_calls": total_calls,
                "parseable_calls": parseable_calls,
                "unclassified_calls": unclassified_calls,
                "coverage_pct": round(coverage_pct, 2),
                "total_tool_output_bytes_observed": total_output_bytes,
                "total_tool_output_tokens_estimate": math.ceil(total_output_bytes / 4),
            },
            "tool_family_distribution": family_stats,
            "reexposure_waste": {
                "tier": TIER_PROVEN_AVOIDABLE,
                "exact_redelivery_events": exact_redelivery_events,
                "exact_redelivery_bytes_gross": exact_redelivery_bytes_gross,
                "proven_reexposure_bytes": proven_reexposure_bytes,
                "exact_redelivery_bytes_observed": proven_reexposure_bytes,
                "proven_identical_redelivery": True,
                "proven_safe_reference_replacement": False,
                "reference_suppressible_bytes": "UNKNOWN_UNTIL_SHADOW_OR_AB",
                "whole_mission_savings": "UNKNOWN",
                "proven_reexposure_tokens_estimate": math.ceil(proven_reexposure_bytes / 4),
                "unique_content_bytes": exact_redelivery_bytes_gross - proven_reexposure_bytes,
                "same_file_reread_count": same_path_read_count,
                "identical_reread_count": identical_reread_count,
                "identical_reread_bytes": identical_reread_bytes,
                "changed_reread_count": changed_reread_count,
                "delta_candidates_count": len(delta_candidates),
                "overlapping_range_events": overlapping_range_events,
                "overlapping_lines": overlapping_lines,
                "overlap_bytes_estimate": overlap_bytes_estimate,
            },
            "representation_waste": {
                "tier": TIER_PROVEN_AVOIDABLE,
                "t02_eligible_events": t02_eligible_events,
                "t02_transformable_events": t02_transformable_events,
                "t02_raw_bytes": t02_raw_bytes,
                "t02_visible_bytes": t02_visible_bytes,
                "t02_proven_local_bytes_avoidable": t02_bytes_saved,
                "t02_proven_tokens_estimate": math.ceil(t02_bytes_saved / 4),
                "t02_local_reduction_percent": t02_reduction_pct,
            },
            "discovery_cost": {
                "tier_cost": TIER_OBSERVED_COST,
                "tier_redundancy": TIER_PROVEN_AVOIDABLE,
                "total_episodes": len(self.episodes),
                "total_discovery_calls": total_discovery_calls,
                "total_discovery_bytes": total_discovery_bytes,
                "total_discovery_tokens_estimate": math.ceil(total_discovery_bytes / 4),
                "unique_files_discovered": len(total_unique_files_discovered),
                "proven_discovery_redundancy_bytes": proven_discovery_redundancy_bytes,
                "proven_discovery_tokens_estimate": math.ceil(proven_discovery_redundancy_bytes / 4),
                "duplicate_search_calls": duplicate_search_calls,
                "duplicate_search_bytes": duplicate_search_bytes,
                "duplicate_dir_calls": duplicate_dir_calls,
                "duplicate_dir_bytes": duplicate_dir_bytes,
                "duplicate_read_calls": duplicate_read_calls,
                "duplicate_read_bytes": duplicate_read_bytes,
                "common_chains": chain_counter.most_common(5),
            },
            "deduplication": {
                "raw_category_totals": {
                    "proven_reexposure_bytes": proven_reexposure_bytes,
                    "t02_representation_bytes": t02_bytes_saved,
                    "proven_discovery_redundancy_bytes": proven_discovery_redundancy_bytes,
                    "sum_before_dedup": (
                        proven_reexposure_bytes
                        + t02_bytes_saved
                        + proven_discovery_redundancy_bytes
                    ),
                },
                "deduplicated_proven_avoidable_bytes": deduplicated_proven_avoidable_bytes,
                "deduplicated_proven_tokens_estimate": math.ceil(deduplicated_proven_avoidable_bytes / 4),
                "proven_avoidable_workload_pct": overall_proven_avoidable_pct,
                "attribution_counts": dict(attribution_counts),
                "double_counting_prevented": True,
            },
            "priority_decision": {
                "highest_observed_cost_class": highest_observed_cost_class,
                "highest_proven_avoidable_bytes_class": highest_proven_avoidable_class,
                "highest_strong_opportunity_class": highest_strong_opportunity_class,
                "next_lane": next_lane,
            },
        }
