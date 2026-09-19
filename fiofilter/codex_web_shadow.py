"""Passive, payload-free Codex Web shadow observations for M13.

The adapter accepts events only *after* the runtime has delivered their output.
It cannot intercept, suppress, rewrite, delay, or replace that output.  Raw
prompts and tool/file contents are deliberately absent from the persisted
event and feed schemas.
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import pathlib
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Set

from fiofilter.discovery_runtime_shadow import (
    DiscoveryRuntimeShadow,
    ShadowEvaluation,
    get_worktree_state_digest_v2,
)
from fiofilter.efficiency_feed import (
    EfficiencyFeedRecord,
    LiveEvidenceClass,
    MissionOutcomeClass,
    PathReadObservation,
    TokenMeasurement,
    WasteCandidateClass,
    hash_private_identifier,
)
from fiofilter.read_receipt import (
    FreshnessLevel,
    ReadReceiptDisposition,
)
from fiofilter.runtime_shadow import RuntimeReceiptState
from fiofilter.transforms.t02_rg_standard_group import (
    RgStandardEvidence,
    RgStandardLosslessGrouping,
)


_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


class Availability(str, enum.Enum):
    EXACT_STRUCTURED = "EXACT_STRUCTURED"
    EXACT_UNSTRUCTURED = "EXACT_UNSTRUCTURED"
    DERIVABLE_DETERMINISTICALLY = "DERIVABLE_DETERMINISTICALLY"
    ESTIMATED = "ESTIMATED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


class ToolFamily(str, enum.Enum):
    FILE_READ = "FILE_READ"
    SEARCH = "SEARCH"
    TEST = "TEST"
    SCRIPT = "SCRIPT"
    GIT = "GIT"
    BUILD = "BUILD"
    OTHER = "OTHER"


@dataclass(frozen=True)
class RuntimeSurfaceCensus:
    fields: Mapping[str, Availability]
    hashed_identifiers: Mapping[str, str]
    passive_event_surface_status: str
    notes: Mapping[str, str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "fields": {name: self.fields[name].value for name in sorted(self.fields)},
            "hashed_identifiers": dict(sorted(self.hashed_identifiers.items())),
            "passive_event_surface_status": self.passive_event_surface_status,
            "notes": dict(sorted(self.notes.items())),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"


def _git_output(repo_root: pathlib.Path, *args: str) -> Optional[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def census_codex_web_runtime(
    repo_root: pathlib.Path,
    *,
    environ: Optional[Mapping[str, str]] = None,
    tool_protocol_observed: bool,
    task_text_visible_to_agent: bool,
    passive_event_surface_available: bool,
) -> RuntimeSurfaceCensus:
    """Classify only runtime evidence actually visible to repository code.

    Environment identifiers are represented solely by SHA-256 digests.  The
    census accepts externally observed booleans so tests never need a Codex
    installation and the module never scrapes a UI or scans secret values.
    """
    env = dict(os.environ if environ is None else environ)
    identifiers = {}
    for field_name, env_name in (
        ("SESSION_ID", "CODEX_SESSION_ID"),
        ("THREAD_ID", "CODEX_THREAD_ID"),
        ("BOOTSTRAP_ATTEMPT_ID", "CODEX_FLORA_CCA_BOOTSTRAP_ATTEMPT_ID"),
    ):
        value = env.get(env_name)
        if value:
            identifiers[field_name] = hash_private_identifier(value)

    head = _git_output(repo_root, "rev-parse", "HEAD")
    root = _git_output(repo_root, "rev-parse", "--show-toplevel")
    status = _git_output(repo_root, "status", "--porcelain=v1", "-z")
    cwd_available = pathlib.Path.cwd().exists()

    fields = {
        "SESSION_ID": (
            Availability.EXACT_STRUCTURED
            if "SESSION_ID" in identifiers else Availability.NOT_AVAILABLE
        ),
        "TASK_RUN_ID": Availability.NOT_AVAILABLE,
        "BOOTSTRAP_ATTEMPT_ID": (
            Availability.EXACT_STRUCTURED
            if "BOOTSTRAP_ATTEMPT_ID" in identifiers else Availability.NOT_AVAILABLE
        ),
        "TASK_QUERY": (
            Availability.EXACT_UNSTRUCTURED
            if task_text_visible_to_agent else Availability.NOT_AVAILABLE
        ),
        "MODEL": Availability.NOT_AVAILABLE,
        "TOOL_CALL_ID": Availability.NOT_AVAILABLE,
        "TOOL_NAME": (
            Availability.EXACT_STRUCTURED
            if tool_protocol_observed else Availability.NOT_AVAILABLE
        ),
        "TOOL_ARGUMENTS": (
            Availability.EXACT_STRUCTURED
            if tool_protocol_observed else Availability.NOT_AVAILABLE
        ),
        "TOOL_OUTPUT": (
            Availability.EXACT_STRUCTURED
            if tool_protocol_observed else Availability.NOT_AVAILABLE
        ),
        "FILE_READ_EVENTS": (
            Availability.DERIVABLE_DETERMINISTICALLY
            if tool_protocol_observed else Availability.NOT_AVAILABLE
        ),
        "COMMAND_EXECUTION": (
            Availability.EXACT_STRUCTURED
            if tool_protocol_observed else Availability.NOT_AVAILABLE
        ),
        "CWD": (
            Availability.DERIVABLE_DETERMINISTICALLY
            if cwd_available else Availability.NOT_AVAILABLE
        ),
        "REPOSITORY_ROOT": (
            Availability.DERIVABLE_DETERMINISTICALLY
            if root else Availability.NOT_AVAILABLE
        ),
        "GIT_HEAD": (
            Availability.DERIVABLE_DETERMINISTICALLY
            if head and _HEX_40.fullmatch(head) else Availability.NOT_AVAILABLE
        ),
        "WORKTREE_STATE": (
            Availability.DERIVABLE_DETERMINISTICALLY
            if status is not None else Availability.NOT_AVAILABLE
        ),
        "TIMESTAMPS": Availability.DERIVABLE_DETERMINISTICALLY,
        "TURN_BOUNDARIES": Availability.NOT_AVAILABLE,
        "INPUT_TOKENS": Availability.NOT_AVAILABLE,
        "OUTPUT_TOKENS": Availability.NOT_AVAILABLE,
        "CACHED_INPUT_TOKENS": Availability.NOT_AVAILABLE,
        "REASONING_TOKENS": Availability.NOT_AVAILABLE,
        "CONTEXT_WINDOW": Availability.NOT_AVAILABLE,
        "PROVIDER_USAGE_ACCOUNTING": Availability.NOT_AVAILABLE,
        "EXIT_CODE": (
            Availability.EXACT_STRUCTURED
            if tool_protocol_observed else Availability.NOT_AVAILABLE
        ),
        "STREAM_IDENTITY": Availability.NOT_AVAILABLE,
        "TRUNCATION_STATUS": Availability.NOT_AVAILABLE,
    }
    notes = {
        "AGENT_EVENT_DIRECTION": "AGENT_EVENT_IN_TO_AGENT_EVENT_OUT_OBSERVED_AFTER_DELIVERY",
        "TOKEN_USAGE_EXACT": "UNAVAILABLE",
        "UI_SCRAPING": "NOT_USED",
        "WORKTREE_FINGERPRINT_SOURCE": (
            "WORKTREE_STATE_DIGEST_V2"
            if head and status is not None else "UNAVAILABLE"
        ),
    }
    return RuntimeSurfaceCensus(
        fields=fields,
        hashed_identifiers=identifiers,
        passive_event_surface_status=(
            "AVAILABLE" if passive_event_surface_available else "UNAVAILABLE"
        ),
        notes=notes,
    )


@dataclass(frozen=True)
class CodexWebShadowEvent:
    """Sanitized post-delivery observation; it contains no output payload."""

    event_id_hash: str
    session_id_hash: str
    timestamp: str
    tool_name: str
    tool_family: ToolFamily
    output_size_bytes: int
    output_sha256: str
    exit_code: Optional[int]
    turn_index: Optional[int]
    command: Optional[str]
    repository_relative_path: Optional[str]
    command_structurally_grounded: bool
    single_producer: bool
    truncated: Optional[bool]
    stream_identity: Optional[str]

    def __post_init__(self) -> None:
        for name in ("event_id_hash", "session_id_hash", "output_sha256"):
            if _HEX_64.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if not isinstance(self.tool_family, ToolFamily):
            raise ValueError("tool_family is required")
        if not self.tool_name or "\n" in self.tool_name:
            raise ValueError("tool_name must be one line")
        if isinstance(self.output_size_bytes, bool) or self.output_size_bytes < 0:
            raise ValueError("output_size_bytes must be non-negative")
        if self.turn_index is not None and (
            isinstance(self.turn_index, bool) or self.turn_index < 0
        ):
            raise ValueError("turn_index must be non-negative")
        if self.repository_relative_path is not None:
            PathReadObservation(
                path_hash=hash_private_identifier(self.repository_relative_path),
                repository_relative_path=self.repository_relative_path,
                read_events=0,
                bytes_delivered=0,
            )


class CodexWebShadowEventAdapter:
    """A passive, post-delivery M13 observer with no behavior authority."""

    runtime_behavior_changed = False
    active_suppression = False
    auto_context_selection = False
    automatic_t02_applied = 0

    def __init__(
        self,
        *,
        session_id_hash: str,
        run_id_hash: Optional[str],
        repository_id: str,
        repo_root: pathlib.Path,
        git_head: str,
        worktree_fingerprint: str,
        live_evidence_class: LiveEvidenceClass,
        start_time: str,
        model: Optional[str] = None,
        task_hash: Optional[str] = None,
        token_measurements: Optional[Mapping[str, TokenMeasurement]] = None,
    ) -> None:
        if _HEX_64.fullmatch(session_id_hash) is None:
            raise ValueError("session_id_hash must be SHA-256")
        if run_id_hash is not None and _HEX_64.fullmatch(run_id_hash) is None:
            raise ValueError("run_id_hash must be SHA-256")
        self.session_id_hash = session_id_hash
        self.run_id_hash = run_id_hash
        self.repository_id = repository_id
        self.repo_root = repo_root.resolve()
        self.git_head = git_head
        self.worktree_fingerprint = worktree_fingerprint
        self.live_evidence_class = live_evidence_class
        self.start_time = start_time
        self.model = model
        self.task_hash = task_hash
        self.token_measurements = dict(token_measurements or {
            "input_tokens": TokenMeasurement.unavailable(),
            "output_tokens": TokenMeasurement.unavailable(),
            "cached_input_tokens": TokenMeasurement.unavailable(),
            "reasoning_tokens": TokenMeasurement.unavailable(),
        })

        self._receipts = RuntimeReceiptState(
            session_id=session_id_hash,
            base_dir=self.repo_root,
        )
        self._discovery = DiscoveryRuntimeShadow(ledger_dir=None)
        self._t02 = RgStandardLosslessGrouping()
        self._observed_event_ids: Set[str] = set()
        self._tool_family_bytes: Counter = Counter()
        self._path_counts: Dict[str, Counter] = defaultdict(Counter)
        self._path_values: Dict[str, str] = {}
        self._turn_indices: Set[int] = set()

        self.tool_calls = 0
        self.file_read_events = 0
        self.file_read_bytes = 0
        self.first_reads = 0
        self.repeated_source_view_reads = 0
        self.identical_reread_events = 0
        self.identical_reread_bytes = 0
        self.f4_proven_events = 0
        self.read_reference_candidates = 0
        self.read_reference_hypothetical_bytes_avoided = 0
        self.discovery_queries = 0
        self.first_target_read_position: Optional[int] = None
        self.search_output_events = 0
        self.structurally_proven_rg_events = 0
        self.t02_applicable_events = 0
        self.t02_no_economic_gain = 0
        self.t02_rejected = 0
        self.t02_hypothetical_bytes_avoided = 0
        self.corrective_rereads = 0

    def _accept_event(self, event: CodexWebShadowEvent) -> bool:
        if event.session_id_hash != self.session_id_hash:
            raise ValueError("cross-session event rejected")
        if event.event_id_hash in self._observed_event_ids:
            return False
        self._observed_event_ids.add(event.event_id_hash)
        self.tool_calls += 1
        self._tool_family_bytes[event.tool_family.value] += event.output_size_bytes
        if event.turn_index is not None:
            self._turn_indices.add(event.turn_index)
        if event.tool_family is ToolFamily.SEARCH:
            self.search_output_events += 1
        return True

    def observe_after_delivery(self, event: CodexWebShadowEvent) -> None:
        """Record metadata after RAW delivery; always returns ``None``."""
        if not self._accept_event(event):
            return None
        if event.tool_family is not ToolFamily.FILE_READ:
            return None

        self.file_read_events += 1
        self.file_read_bytes += event.output_size_bytes
        if event.repository_relative_path is not None:
            path_hash = hash_private_identifier(event.repository_relative_path)
            self._path_values[path_hash] = event.repository_relative_path.replace("\\", "/")
            self._path_counts[path_hash]["read_events"] += 1
            self._path_counts[path_hash]["bytes_delivered"] += event.output_size_bytes

        if not (
            event.command_structurally_grounded
            and event.single_producer
            and event.command is not None
        ):
            return None
        try:
            decision = self._receipts.process_historical_or_stream_event(
                call_id=event.event_id_hash,
                command_str=event.command,
                delivered_bytes=event.output_size_bytes,
                delivered_sha256=event.output_sha256,
                call_index=self.tool_calls,
                episode_id=event.turn_index,
                timestamp=event.timestamp,
            )
        except Exception:
            # Observation failure occurs after delivery and cannot affect RAW.
            return None
        if decision is None:
            return None
        if decision.disposition is ReadReceiptDisposition.FIRST_READ_RAW:
            self.first_reads += 1
            return None
        if decision.requested_view is not None and decision.resolved_path_identity is not None:
            self.repeated_source_view_reads += 1
        if decision.freshness_level is FreshnessLevel.F1_HISTORICAL_OUTPUT_IDENTITY:
            self.identical_reread_events += 1
            self.identical_reread_bytes += event.output_size_bytes
            if decision.hypothetical_bytes_avoided > 0:
                self.read_reference_candidates += 1
                self.read_reference_hypothetical_bytes_avoided += (
                    decision.hypothetical_bytes_avoided
                )
        return None

    def observe_t02_after_delivery(
        self,
        event: CodexWebShadowEvent,
        raw_output: bytes,
    ) -> bytes:
        """Evaluate T02 hypothetically and return the identical RAW object."""
        if not self._accept_event(event):
            return raw_output
        if event.tool_family is not ToolFamily.SEARCH:
            self.t02_rejected += 1
            return raw_output
        if len(raw_output) != event.output_size_bytes or (
            hashlib.sha256(raw_output).hexdigest() != event.output_sha256
        ):
            self.t02_rejected += 1
            return raw_output
        if not (
            event.command is not None
            and event.command_structurally_grounded
            and event.single_producer
            and event.exit_code is not None
            and event.truncated is not None
            and event.stream_identity is not None
        ):
            self.t02_rejected += 1
            return raw_output

        evidence = RgStandardEvidence(
            command=event.command,
            command_structurally_grounded=True,
            single_search_producer=True,
            exit_code=event.exit_code,
            truncated=event.truncated,
            upstream_truncation_observed=False,
            shell_failure_wrapper_observed=False,
            stream=event.stream_identity,
        )
        try:
            outcome = self._t02.evaluate(raw_output, evidence)
        except Exception:
            self.t02_rejected += 1
            return raw_output
        if outcome.metadata.recognized_grammar is not None:
            self.structurally_proven_rg_events += 1
        if outcome.applied:
            self.t02_applicable_events += 1
            self.t02_hypothetical_bytes_avoided += outcome.metadata.bytes_saved
        elif outcome.reason == "VALID_GRAMMAR_NO_ECONOMIC_GAIN":
            self.t02_no_economic_gain += 1
        else:
            self.t02_rejected += 1
        return raw_output

    def observe_discovery(
        self,
        task_query: str,
        *,
        task_text_status: Availability,
        top_k: int = 10,
    ) -> Optional[ShadowEvaluation]:
        """Run BM25 only for exact structured task text; retain no raw query."""
        if task_text_status is not Availability.EXACT_STRUCTURED:
            return None
        result = self._discovery.evaluate(self.repo_root, task_query, top_k=top_k)
        if result is not None:
            self.discovery_queries += 1
            if self.task_hash is None:
                self.task_hash = hashlib.sha256(task_query.encode("utf-8")).hexdigest()
        return result

    def build_feed_record(
        self,
        end_time: str,
        mission_outcome: MissionOutcomeClass = MissionOutcomeClass.PARTIAL,
    ) -> EfficiencyFeedRecord:
        path_observations = tuple(
            PathReadObservation(
                path_hash=path_hash,
                repository_relative_path=self._path_values[path_hash],
                read_events=counts["read_events"],
                bytes_delivered=counts["bytes_delivered"],
            )
            for path_hash, counts in sorted(self._path_counts.items())
        )
        waste = {}
        if self.read_reference_candidates:
            waste[WasteCandidateClass.REEXPOSURE_WASTE_CANDIDATE.value] = (
                self.read_reference_candidates
            )
        if self.discovery_queries:
            waste[WasteCandidateClass.DISCOVERY_WASTE_CANDIDATE.value] = (
                self.discovery_queries
            )
        if self.t02_applicable_events:
            waste[WasteCandidateClass.REPRESENTATION_WASTE_CANDIDATE.value] = (
                self.t02_applicable_events
            )
        return EfficiencyFeedRecord(
            session_id_hash=self.session_id_hash,
            run_id_hash=self.run_id_hash,
            repository_id=self.repository_id,
            git_head=self.git_head,
            worktree_fingerprint=self.worktree_fingerprint,
            model=self.model,
            start_time=self.start_time,
            end_time=end_time,
            task_hash=self.task_hash,
            live_evidence_class=self.live_evidence_class,
            token_measurements=self.token_measurements,
            tool_output_bytes=sum(self._tool_family_bytes.values()),
            tool_calls=self.tool_calls,
            turns_if_known=(len(self._turn_indices) if self._turn_indices else None),
            tool_output_bytes_by_family=dict(self._tool_family_bytes),
            file_read_events=self.file_read_events,
            file_read_bytes=self.file_read_bytes,
            first_reads=self.first_reads,
            repeated_source_view_reads=self.repeated_source_view_reads,
            identical_reread_events=self.identical_reread_events,
            identical_reread_bytes=self.identical_reread_bytes,
            f4_proven_events=self.f4_proven_events,
            read_reference_candidates=self.read_reference_candidates,
            read_reference_hypothetical_bytes_avoided=(
                self.read_reference_hypothetical_bytes_avoided
            ),
            discovery_queries=self.discovery_queries,
            first_target_read_position=self.first_target_read_position,
            t02_applicable_events=self.t02_applicable_events,
            t02_no_economic_gain=self.t02_no_economic_gain,
            t02_rejected=self.t02_rejected,
            t02_hypothetical_bytes_avoided=self.t02_hypothetical_bytes_avoided,
            corrective_rereads=self.corrective_rereads,
            mission_outcome_class=mission_outcome,
            search_output_events=self.search_output_events,
            structurally_proven_rg_events=self.structurally_proven_rg_events,
            automatic_t02_applied=self.automatic_t02_applied,
            raw_codex_behavior_changed=self.runtime_behavior_changed,
            active_suppression=self.active_suppression,
            auto_context_selection=self.auto_context_selection,
            path_read_observations=path_observations,
            waste_candidate_counts=waste,
        )


def current_worktree_fingerprint(repo_root: pathlib.Path) -> str:
    """Expand the existing V2 state digest into the feed's SHA-256 field."""
    digest_v2 = get_worktree_state_digest_v2(repo_root)
    return hashlib.sha256(("WORKTREE_STATE_DIGEST_V2:" + digest_v2).encode()).hexdigest()
