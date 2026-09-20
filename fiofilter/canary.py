"""Explicit, local M15 READREF canary. No normal-runtime activation.

The only active delivery path is a task-scoped Codex App Server dynamic tool.
The App Server transport and dynamic-tool API are experimental; this is not a
production integration, hook, proxy, MCP server, or daemon.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import queue
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from fiofilter.efficiency_feed import hash_private_identifier
from fiofilter.read_receipt import FreshnessLevel, ReadView, ReadViewType
from fiofilter.read_receipt_ab import (
    ABCondition,
    ABDelivery,
    ABReadResult,
    ReadReceiptABHarness,
    RecoveryError,
)
from fiofilter.types import Sensitivity


APP_SERVER_TRANSPORT = "STDIO"
DYNAMIC_TOOL_API = "EXPERIMENTAL"
PRODUCTION_INTEGRATION = "NO"
MAX_READREF_PER_SESSION = 3
RECOVERY_TRIGGERED_SESSION_FALLBACK = True
RECORD_SCHEMA = "FIO_READREF_CANARY_SESSION_V2"
ANOMALY_CLASSES = (
    "BEHAVIORAL_CONCERN", "TASK_QUALITY_CONCERN", "SAFETY_CONCERN",
    "PROTOCOL_CONCERN", "OTHER",
)
STRUCTURAL_TRACE_LIMIT = 64
_STRUCTURAL_EVENTS = {
    "READ_RAW", "READREF_EMITTED", "RECOVERY_REQUESTED", "RECOVERY_SUCCEEDED",
    "RAW_FALLBACK", "ANOMALY_REPORTED", "ANOMALY_DETECTED", "INTERRUPT_SENT",
}
_STOP_REASONS = {
    "RECOVERY_TRIGGERED", "MAX_READREF_REACHED",
    "RECOVERY_INTEGRITY_ERROR", "PROTOCOL_ANOMALY", "REPORTED_ANOMALY",
    "DESIGNATED_READ_BYPASS", "NON_UTF8_DELIVERY", "APP_SERVER_ERROR",
    "APPROVAL_REQUIRED", "TURN_NOT_COMPLETED",
}
_NORMAL_RAW_ONLY_REASONS = {None, "RECOVERY_TRIGGERED", "MAX_READREF_REACHED"}


class CanaryStopError(RuntimeError):
    """An active canary must stop; subsequent reads are RAW-only."""


class AppServerError(RuntimeError):
    """The local App Server could not safely complete its protocol."""


class CanarySession:
    """Bound M14's unchanged harness with first-active-canary session gates."""

    def __init__(
        self,
        repo: pathlib.Path,
        source: pathlib.Path,
        *,
        enabled: bool = False,
        assessed_non_sensitive: bool = False,
        session_id: Optional[str] = None,
        additional_context_bytes: int = 0,
    ) -> None:
        if additional_context_bytes < 0:
            raise ValueError("additional context bytes cannot be negative")
        self.repo = repo.resolve()
        self.source = source.resolve()
        self.source.relative_to(self.repo)  # A source outside the explicit repo is forbidden.
        self.enabled = enabled
        self.sensitivity = (
            Sensitivity.NON_SENSITIVE if assessed_non_sensitive else Sensitivity.UNKNOWN
        )
        self.session_id = session_id or f"m15-{uuid.uuid4()}"
        self.harness = ReadReceiptABHarness(
            ABCondition.TREATMENT if enabled else ABCondition.CONTROL,
            session_id=self.session_id,
            base_dir=self.repo,
        )
        self.read_count = 0
        self.eligible_rereads = 0
        self.readref_emissions = 0
        self.recovery_requests = 0
        self.raw_fallbacks = 0
        self.raw_bytes_avoided_gross = 0
        self.reference_bytes = 0
        self.recovery_bytes = 0
        self.additional_context_bytes = additional_context_bytes
        self.raw_only_reason: Optional[str] = None
        self._issued_references: set[str] = set()
        self._phase = "BEFORE_READ"
        self._successful_recoveries = 0
        self._anomaly: Optional[Dict[str, Any]] = None
        self._structural_trace: deque[str] = deque(maxlen=STRUCTURAL_TRACE_LIMIT)
        self._trace_dropped = 0

    def _trace_event(self, event: str) -> None:
        # Enum-only, payload-free tail. Diagnostic loss is explicitly counted.
        if event not in _STRUCTURAL_EVENTS:
            raise ValueError("unknown structural event")
        if len(self._structural_trace) == STRUCTURAL_TRACE_LIMIT:
            self._trace_dropped += 1
        self._structural_trace.append(event)

    @property
    def state(self) -> str:
        if not self.enabled:
            return "OFF"
        return "RAW_ONLY" if self.raw_only_reason else "ACTIVE"

    @property
    def anomaly_stopped(self) -> bool:
        return self.raw_only_reason not in _NORMAL_RAW_ONLY_REASONS

    @property
    def net_visible_bytes_saved(self) -> int:
        return (
            self.raw_bytes_avoided_gross
            - self.reference_bytes
            - self.recovery_bytes
            - self.additional_context_bytes
        )

    @property
    def economic_success(self) -> bool:
        return (
            self.readref_emissions > 0
            and self.net_visible_bytes_saved > 0
            and not self.anomaly_stopped
        )

    def stop(self, reason: str, *, anomaly_class: Optional[str] = None,
             harness_detected: bool = False) -> None:
        if reason not in _STOP_REASONS:
            raise ValueError("unknown canary stop reason")
        # Only the client's validated model-report branch supplies a class.
        # No phase, source, detail or violation claim comes from model arguments.
        if reason == "REPORTED_ANOMALY" and anomaly_class not in ANOMALY_CLASSES:
            raise ValueError("model anomaly requires a bounded class")
        if reason != "REPORTED_ANOMALY" and anomaly_class is not None:
            raise ValueError("machine anomaly class is derived from its gate")
        if reason not in _NORMAL_RAW_ONLY_REASONS and self._anomaly is None:
            model_report = reason == "REPORTED_ANOMALY"
            self._anomaly = {
                "anomaly_kind": "MODEL_REPORTED_ANOMALY" if model_report else "MACHINE_DETECTED_ANOMALY",
                "anomaly_source": "MODEL_REPORTED" if model_report else (
                    "HARNESS_DETECTED" if harness_detected else "CLIENT_DETECTED"
                ),
                "anomaly_class": anomaly_class if model_report else (
                    "SAFETY_CONCERN" if reason in {
                        "RECOVERY_INTEGRITY_ERROR", "DESIGNATED_READ_BYPASS", "NON_UTF8_DELIVERY"
                    } else "PROTOCOL_CONCERN"
                ),
                "anomaly_phase": self._phase,
                "abort_after_readref": self.readref_emissions > 0,
                "abort_after_recovery": self._successful_recoveries > 0,
            }
            self._trace_event("ANOMALY_REPORTED" if model_report else "ANOMALY_DETECTED")
        if self.raw_only_reason is None or (
            self.raw_only_reason in _NORMAL_RAW_ONLY_REASONS
            and reason not in _NORMAL_RAW_ONLY_REASONS
        ):
            self.raw_only_reason = reason
        self.harness.set_kill_switch(True)
        if reason not in _NORMAL_RAW_ONLY_REASONS:
            self.harness.close_session()

    def read(self) -> ABReadResult:
        self.read_count += 1
        if self.readref_emissions >= MAX_READREF_PER_SESSION or self.recovery_requests:
            self.harness.set_kill_switch(True)
        result = self.harness.read(
            call_id=f"{self.session_id}-read-{self.read_count}",
            file_path=self.source,
            view=ReadView(ReadViewType.FULL_FILE),
            call_index=self.read_count,
            sensitivity=self.sensitivity,
        )
        decision = result.decision
        if (
            self.read_count > 1
            and self.sensitivity is Sensitivity.NON_SENSITIVE
            and decision is not None
            and decision.freshness_level is FreshnessLevel.F4_CURRENT_VIEW_BYTE_EQUAL
            and decision.plane_a_freshness_proven
            and decision.reference_bytes < result.raw_bytes
        ):
            self.eligible_rereads += 1
        if result.delivery is ABDelivery.READREF:
            if self.raw_only_reason or self.recovery_requests or self.readref_emissions >= MAX_READREF_PER_SESSION:
                self.stop("PROTOCOL_ANOMALY")
                raise CanaryStopError("READREF_AFTER_SESSION_GATE")
            self.readref_emissions += 1
            self.raw_bytes_avoided_gross += result.raw_bytes
            self.reference_bytes += result.reference_bytes
            assert result.reference_text is not None
            self._issued_references.add(result.reference_text)
            self._phase = "AFTER_READREF"
            self._trace_event("READREF_EMITTED")
            if self.readref_emissions == MAX_READREF_PER_SESSION:
                self.stop("MAX_READREF_REACHED")
        else:
            self._phase = "RAW_ONLY" if self.raw_only_reason else "AFTER_RAW"
            self._trace_event("READ_RAW")
            if self.read_count > 1:
                self.raw_fallbacks += 1
                self._trace_event("RAW_FALLBACK")
        return result

    def expand(self, reference: str) -> bytes:
        # Even an invalid first request permanently disables later references.
        self.recovery_requests += 1
        self._trace_event("RECOVERY_REQUESTED")
        self.stop("RECOVERY_TRIGGERED")
        if reference not in self._issued_references:
            self.stop("RECOVERY_INTEGRITY_ERROR")
            raise CanaryStopError("UNISSUED_READREF")
        try:
            recovered = self.harness.expand(reference)
        except RecoveryError as exc:
            self.stop("RECOVERY_INTEGRITY_ERROR", harness_detected=True)
            raise CanaryStopError("READREF_RECOVERY_INTEGRITY_ERROR") from exc
        self.recovery_bytes += len(recovered)
        self._successful_recoveries += 1
        self._phase = "AFTER_RECOVERY"
        self._trace_event("RECOVERY_SUCCEEDED")
        return recovered

    def close(self) -> None:
        self._issued_references.clear()
        self.harness.close_session()

    def record(
        self,
        *,
        repository_id: str,
        git_head: str,
        tool_calls: Optional[int],
        account_usage: Mapping[str, Any],
        rate_limits: Mapping[str, Any],
        thread_usage: Mapping[str, Any],
        task_outcome: str,
    ) -> Dict[str, Any]:
        if task_outcome not in {"COMPLETED", "FAILED", "INTERRUPTED", "ERROR", "UNKNOWN"}:
            raise ValueError("invalid task outcome")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository_id):
            raise ValueError("repository id must be owner/name or local/hash")
        if not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", git_head):
            raise ValueError("invalid git commit")
        return {
            "schema_version": RECORD_SCHEMA,
            "session_hash": hash_private_identifier(self.session_id),
            "repository_id": repository_id,
            "git_head": git_head,
            "canary_state": self.state,
            "raw_only_reason": self.raw_only_reason,
            "safety_gate_triggered": self._anomaly is not None,
            # Existing detectors stop/reject; none proves a delivered safety
            # violation or READREF-caused behavioral regression.
            "confirmed_safety_violation": False,
            **(self._anomaly or {
                "anomaly_kind": None, "anomaly_source": None,
                "anomaly_class": None, "anomaly_phase": None,
                "abort_after_readref": False, "abort_after_recovery": False,
            }),
            "structural_event_trace": list(self._structural_trace),
            "structural_event_trace_dropped": self._trace_dropped,
            "eligible_rereads": self.eligible_rereads,
            "readref_emissions": self.readref_emissions,
            "recovery_requests": self.recovery_requests,
            "raw_fallbacks": self.raw_fallbacks,
            "raw_bytes_avoided_gross": self.raw_bytes_avoided_gross,
            "reference_bytes": self.reference_bytes,
            "recovery_bytes": self.recovery_bytes,
            "additional_context_bytes": self.additional_context_bytes,
            "net_visible_bytes_saved": self.net_visible_bytes_saved,
            "economic_success": self.economic_success,
            "recovery_triggered_session_fallback": RECOVERY_TRIGGERED_SESSION_FALLBACK,
            "tool_calls": tool_calls,
            "account_token_activity_observation": dict(account_usage),
            "rate_limit_observation": dict(rate_limits),
            "thread_token_usage_observation": dict(thread_usage),
            "readref_causal_token_savings": "UNAVAILABLE",
            "task_outcome": task_outcome,
        }


def dynamic_tools() -> list[Dict[str, Any]]:
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    return [
        {
            "type": "function", "name": "fio_canary_read",
            "description": "Read the one explicitly designated source through the controlled canary.",
            "inputSchema": empty,
        },
        {
            "type": "function", "name": "fio_canary_expand",
            "description": "Recover exact bytes from a READREF emitted by this session.",
            "inputSchema": {
                "type": "object", "additionalProperties": False,
                "properties": {"reference": {"type": "string"}},
                "required": ["reference"],
            },
        },
        {
            "type": "function", "name": "fio_canary_abort",
            "description": "Report a behavioral or safety anomaly and stop this canary task.",
            "inputSchema": {
                "type": "object", "additionalProperties": False,
                "properties": {"anomaly_class": {"type": "string", "enum": list(ANOMALY_CLASSES)}},
                "required": ["anomaly_class"],
            },
        },
    ]


def developer_instructions(source_relative: str) -> str:
    return (
        "M15 CONTROLLED CANARY ACTIVE. The only designated source is `"
        + source_relative
        + "`. Read this source exclusively with fio_canary_read, including every "
        "reread. Do not use shell, search, git object inspection, or another tool "
        "to read its content. If a READREF does not contain enough detail, call "
        "fio_canary_expand with that exact reference. Do not synthesize one. "
        "If you notice an anomaly, call fio_canary_abort with anomaly_class set "
        "to BEHAVIORAL_CONCERN, TASK_QUALITY_CONCERN, SAFETY_CONCERN, "
        "PROTOCOL_CONCERN or OTHER. Supply no free-text description. "
        "Other task work remains under the normal workspace sandbox."
    )


def additional_canary_context_bytes(instructions: str, tools: Sequence[Mapping[str, Any]]) -> int:
    """Exact client-supplied canary instruction/schema bytes, not model tokens."""
    return len(instructions.encode("utf-8")) + len(
        json.dumps(tools, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


class AppServerClient:
    """One local stdio App Server connection; no ambient service installation."""

    def __init__(self, cwd: pathlib.Path) -> None:
        self.process = subprocess.Popen(
            ["codex", "app-server", "--stdio"],
            cwd=str(cwd), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
            bufsize=1,
        )
        self._messages: queue.Queue[Optional[Dict[str, Any]]] = queue.Queue()
        self._next_id = 1
        assert self.process.stdout is not None
        self._reader = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("not an object")
                self._messages.put(value)
            except (json.JSONDecodeError, ValueError):
                self._messages.put({"_protocol_error": "NON_JSON_APP_SERVER_STDOUT"})
        self._messages.put(None)

    def send(self, message: Mapping[str, Any]) -> None:
        if self.process.stdin is None:
            raise AppServerError("APP_SERVER_STDIN_UNAVAILABLE")
        try:
            self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
            self.process.stdin.flush()
        except OSError as exc:
            raise AppServerError("APP_SERVER_WRITE_FAILED") from exc

    def send_request(self, method: str, params: Optional[Mapping[str, Any]] = None) -> int:
        request_id = self._next_id
        self._next_id += 1
        message: Dict[str, Any] = {"id": request_id, "method": method}
        if params is not None:
            message["params"] = dict(params)
        self.send(message)
        return request_id

    def receive(self, timeout: float = 30.0) -> Dict[str, Any]:
        try:
            message = self._messages.get(timeout=timeout)
        except queue.Empty as exc:
            raise AppServerError("APP_SERVER_RESPONSE_TIMEOUT") from exc
        if message is None:
            raise AppServerError("APP_SERVER_CLOSED")
        if "_protocol_error" in message:
            raise AppServerError("APP_SERVER_PROTOCOL_ERROR")
        return message

    def request(
        self,
        method: str,
        params: Optional[Mapping[str, Any]] = None,
        *,
        timeout: float = 30.0,
        event_handler: Optional[Any] = None,
    ) -> Mapping[str, Any]:
        request_id = self.send_request(method, params)
        deadline = time.monotonic() + timeout
        while True:
            message = self.receive(max(0.01, deadline - time.monotonic()))
            # Server-initiated requests can reuse our numeric request ids.
            if message.get("method"):
                if event_handler is not None:
                    event_handler(message)
                elif message.get("id") is not None:
                    raise AppServerError("UNHANDLED_SERVER_REQUEST")
                continue
            if message.get("id") != request_id:
                # A prior interrupt response may arrive during a later read.
                continue
            if "error" in message:
                raise AppServerError("APP_SERVER_METHOD_UNAVAILABLE_OR_FAILED")
            result = message.get("result")
            if not isinstance(result, dict):
                raise AppServerError("APP_SERVER_INVALID_RESPONSE")
            return result

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {"name": "fiofilter-m15-canary", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self.send({"method": "initialized", "params": {}})

    def close(self) -> None:
        if self.process.stdin is not None:
            try:
                self.process.stdin.close()
            except OSError:
                pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def __enter__(self) -> "AppServerClient":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()


def _number(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def account_observation(before: Any, after: Any) -> Dict[str, Any]:
    """Account-level activity is concurrent and never a READREF causal metric."""
    try:
        first = _number(before["summary"]["lifetimeTokens"])
        last = _number(after["summary"]["lifetimeTokens"])
    except (TypeError, KeyError):
        first = last = None
    if first is None or last is None:
        return {"status": "UNAVAILABLE", "account_token_activity_observed": False}
    return {
        "status": "ACCOUNT_LEVEL_OBSERVATION",
        "account_token_activity_observed": True,
        "before_lifetime_tokens": first,
        "after_lifetime_tokens": last,
        "delta_tokens": last - first,
        "readref_causal": False,
    }


def rate_limit_observation(before: Any, after: Any) -> Dict[str, Any]:
    try:
        first = before.get("rateLimitsByLimitId", {}).get("codex") or before["rateLimits"]
        last = after.get("rateLimitsByLimitId", {}).get("codex") or after["rateLimits"]
        a = first["primary"]["usedPercent"]
        b = last["primary"]["usedPercent"]
        if (
            isinstance(a, bool) or isinstance(b, bool)
            or not isinstance(a, (int, float)) or not isinstance(b, (int, float))
            or not math.isfinite(a) or not math.isfinite(b)
            or not (0 <= a <= 100 and 0 <= b <= 100)
        ):
            raise TypeError("invalid percent")
    except (AttributeError, KeyError, TypeError):
        return {"status": "UNAVAILABLE", "rate_limit_delta_observed": False}
    return {
        "status": "ACCOUNT_LEVEL_OBSERVATION",
        "rate_limit_delta_observed": True,
        "before_used_percent": a,
        "after_used_percent": b,
        "delta_percentage_points": b - a,
        "readref_causal": False,
    }


def thread_usage_observation(params: Any) -> Dict[str, Any]:
    try:
        total = params["tokenUsage"]["total"]
    except (TypeError, KeyError):
        return {"status": "UNAVAILABLE"}
    allowed = {
        "inputTokens", "outputTokens", "cachedInputTokens", "reasoningOutputTokens",
        "totalTokens", "cacheWriteInputTokens",
    }
    values = {key: _number(total.get(key)) for key in allowed if isinstance(total, dict)}
    if not values or all(value is None for value in values.values()):
        return {"status": "UNAVAILABLE"}
    return {"status": "APP_SERVER_THREAD_RUNTIME_REPORTED", "totals": values, "readref_causal": False}


def _probe(
    client: AppServerClient, method: str, event_handler: Optional[Any] = None
) -> Optional[Mapping[str, Any]]:
    try:
        return client.request(method, timeout=20.0, event_handler=event_handler)
    except AppServerError:
        return None


def _git_metadata(repo: pathlib.Path) -> tuple[str, str]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True,
            text=True, encoding="utf-8", errors="replace", check=False,
        )
        if result.returncode != 0:
            raise ValueError("repository Git metadata unavailable")
        return result.stdout.strip()

    root = pathlib.Path(git("rev-parse", "--show-toplevel")).resolve()
    if root != repo.resolve():
        raise ValueError("--repo must be the Git root")
    if git("status", "--porcelain"):
        raise ValueError("controlled canary requires a clean repository")
    head = git("rev-parse", "HEAD")
    remote = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
    )
    match = re.search(r"[:/]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?$", remote.stdout.strip())
    repository_id = f"{match.group(1)}/{match.group(2).removesuffix('.git')}" if match else f"local/{hash_private_identifier(str(repo))[:16]}"
    return repository_id, head


def _command_reads_designated(command: str, source_relative: str) -> bool:
    normalized = command.replace("\\", "/").lower()
    source = source_relative.lower()
    basename = pathlib.PurePosixPath(source).name
    basename_pattern = r"(?<![a-z0-9_])" + re.escape(basename) + r"(?![a-z0-9_])"
    if source not in normalized and re.search(basename_pattern, normalized) is None:
        return False
    return bool(re.search(r"\b(get-content|gc|type|cat|more|rg|select-string|findstr|python|py|node|git\s+show)\b", normalized))


class _CanaryTurn:
    def __init__(self, client: AppServerClient, session: CanarySession, source_relative: str) -> None:
        self.client = client
        self.session = session
        self.source_relative = source_relative
        self.thread_id: Optional[str] = None
        self.turn_id: Optional[str] = None
        self.turn_status = "UNKNOWN"
        self.done = False
        self.tool_calls = 0
        self._counted_items: set[str] = set()
        self._interrupt_sent = False
        self.thread_usage: Dict[str, Any] = {"status": "UNAVAILABLE"}

    def _interrupt(self) -> None:
        if self._interrupt_sent or not self.thread_id or not self.turn_id:
            return
        self._interrupt_sent = True
        self.client.send_request(
            "turn/interrupt", {"threadId": self.thread_id, "turnId": self.turn_id}
        )
        self.session._trace_event("INTERRUPT_SENT")

    def _tool_response(self, request_id: Any, success: bool, text: str) -> None:
        self.client.send({
            "id": request_id,
            "result": {
                "contentItems": [{"type": "inputText", "text": text}],
                "success": success,
            },
        })

    def _tool(self, message: Mapping[str, Any]) -> None:
        self.tool_calls += 1
        params = message.get("params") or {}
        tool = params.get("tool")
        args = params.get("arguments") or {}
        request_id = message.get("id")
        if not isinstance(args, dict):
            self.session.stop("PROTOCOL_ANOMALY")
            self._tool_response(request_id, False, "CANARY_INVALID_ARGUMENTS")
            self._interrupt()
            return
        try:
            if tool == "fio_canary_read" and not args:
                delivered = self.session.read().payload.decode("utf-8")
            elif tool == "fio_canary_expand" and set(args) == {"reference"} and isinstance(args["reference"], str):
                delivered = self.session.expand(args["reference"]).decode("utf-8")
            elif (
                tool == "fio_canary_abort" and set(args) == {"anomaly_class"}
                and isinstance(args["anomaly_class"], str)
                and args["anomaly_class"] in ANOMALY_CLASSES
            ):
                self.session.stop("REPORTED_ANOMALY", anomaly_class=args["anomaly_class"])
                self._tool_response(request_id, True, "CANARY_STOPPED_RAW_ONLY")
                self._interrupt()
                return
            else:
                self.session.stop("PROTOCOL_ANOMALY")
                self._tool_response(request_id, False, "CANARY_UNKNOWN_TOOL_OR_ARGUMENTS")
                self._interrupt()
                return
        except UnicodeDecodeError:
            self.session.stop("NON_UTF8_DELIVERY")
            self._tool_response(request_id, False, "CANARY_NON_UTF8_STOPPED_RAW_ONLY")
            self._interrupt()
            return
        except CanaryStopError:
            self._tool_response(request_id, False, "CANARY_RECOVERY_ERROR_STOPPED_RAW_ONLY")
            self._interrupt()
            return
        self._tool_response(request_id, True, delivered)

    def handle(self, message: Mapping[str, Any]) -> None:
        method = message.get("method")
        params = message.get("params") or {}
        if method == "item/tool/call":
            self._tool(message)
        elif method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            self.session.stop("APPROVAL_REQUIRED")
            self.client.send({"id": message.get("id"), "result": {"decision": "decline"}})
            self._interrupt()
        elif method == "turn/started":
            self.turn_id = (params.get("turn") or {}).get("id")
            if self.session.anomaly_stopped:
                self._interrupt()
        elif method in {"item/started", "item/completed"}:
            item = params.get("item") or {}
            kind = item.get("type")
            if kind in {"commandExecution", "fileChange"}:
                item_id = str(item.get("id") or "")
                if item_id and item_id not in self._counted_items:
                    self._counted_items.add(item_id)
                    self.tool_calls += 1
                if kind == "commandExecution" and _command_reads_designated(
                    str(item.get("command") or ""), self.source_relative
                ):
                    self.session.stop("DESIGNATED_READ_BYPASS")
                    self._interrupt()
        elif method == "thread/tokenUsage/updated":
            self.thread_usage = thread_usage_observation(params)
        elif method == "turn/completed":
            self.turn_status = str((params.get("turn") or {}).get("status") or "UNKNOWN").upper()
            self.done = True
        elif method == "error":
            self.session.stop("APP_SERVER_ERROR")
            self._interrupt()
        elif message.get("id") is not None:
            self.session.stop("PROTOCOL_ANOMALY")
            self.client.send({"id": message["id"], "error": {"code": -32601, "message": "unsupported canary request"}})
            self._interrupt()


def run_task(
    repo: pathlib.Path,
    source_relative: str,
    prompt: str,
    *,
    assessed_non_sensitive: bool,
    client_factory: Any = AppServerClient,
    on_active: Optional[Callable[[], None]] = None,
) -> Dict[str, Any]:
    """Run one genuine opt-in Codex task; tests inject a protocol fake instead."""
    repository_id, git_head = _git_metadata(repo)
    source_argument = pathlib.Path(source_relative)
    if (
        source_argument.is_absolute() or ".." in source_argument.parts
        or any(character in source_relative for character in ("\x00", "\r", "\n"))
    ):
        raise ValueError("source must be a clean repository-relative path")
    source = (repo / source_relative).resolve()
    source.relative_to(repo.resolve())
    if not source.is_file():
        raise ValueError("designated source must be an existing file")
    try:
        source.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("designated source must be UTF-8") from exc
    tools = dynamic_tools()
    instructions = developer_instructions(source_relative)
    session = CanarySession(
        repo, source, enabled=True, assessed_non_sensitive=assessed_non_sensitive,
        additional_context_bytes=additional_canary_context_bytes(instructions, tools),
    )
    account_before: Optional[Mapping[str, Any]] = None
    account_after: Optional[Mapping[str, Any]] = None
    limits_before: Optional[Mapping[str, Any]] = None
    limits_after: Optional[Mapping[str, Any]] = None
    turn: Optional[_CanaryTurn] = None
    outcome = "UNKNOWN"
    try:
        if on_active is not None:
            on_active()
        with client_factory(repo) as client:
            client.initialize()
            account_before = _probe(client, "account/usage/read")
            limits_before = _probe(client, "account/rateLimits/read")
            thread = client.request(
                "thread/start",
                {
                    "cwd": str(repo), "ephemeral": True,
                    "approvalPolicy": "never", "sandbox": "workspace-write",
                    "serviceName": "fiofilter-m15-canary",
                    "dynamicTools": tools,
                    "developerInstructions": instructions,
                },
            )
            thread_id = (thread.get("thread") or {}).get("id")
            if not isinstance(thread_id, str) or not thread_id:
                raise AppServerError("THREAD_START_WITHOUT_ID")
            turn = _CanaryTurn(client, session, source_relative)
            turn.thread_id = thread_id
            started = client.request(
                "turn/start",
                {
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": prompt}],
                    "approvalPolicy": "never",
                    "sandboxPolicy": {
                        "type": "workspaceWrite",
                        "writableRoots": [str(repo)],
                        "networkAccess": False,
                    },
                },
                event_handler=turn.handle,
            )
            turn.turn_id = (started.get("turn") or {}).get("id") or turn.turn_id
            if session.anomaly_stopped:
                turn._interrupt()
            deadline = time.monotonic() + 1800
            while not turn.done:
                turn.handle(client.receive(max(0.01, deadline - time.monotonic())))
                if time.monotonic() >= deadline:
                    raise AppServerError("CANARY_TURN_TIMEOUT")
            outcome = turn.turn_status if turn.turn_status in {"COMPLETED", "FAILED", "INTERRUPTED"} else "UNKNOWN"
            if outcome != "COMPLETED" and session.raw_only_reason is None:
                session.stop("TURN_NOT_COMPLETED")
            account_after = _probe(client, "account/usage/read", turn.handle)
            limits_after = _probe(client, "account/rateLimits/read", turn.handle)
    except (AppServerError, OSError, subprocess.SubprocessError):
        session.stop("APP_SERVER_ERROR")
        outcome = "ERROR"
    finally:
        session.close()
    return session.record(
        repository_id=repository_id, git_head=git_head,
        tool_calls=turn.tool_calls if turn is not None else None,
        account_usage=account_observation(account_before, account_after),
        rate_limits=rate_limit_observation(limits_before, limits_after),
        thread_usage=turn.thread_usage if turn is not None else {"status": "UNAVAILABLE"},
        task_outcome=outcome,
    )


def probe_account_support(client_factory: Any = AppServerClient) -> Dict[str, str]:
    """Read-only App Server probe; does not start a thread or model turn."""
    try:
        with client_factory(pathlib.Path.cwd()) as client:
            client.initialize()
            usage = _probe(client, "account/usage/read")
            limits = _probe(client, "account/rateLimits/read")
    except (AppServerError, OSError, subprocess.SubprocessError):
        usage = limits = None
    return {
        "app_server_transport": APP_SERVER_TRANSPORT,
        "dynamic_tool_api": DYNAMIC_TOOL_API,
        "production_integration": PRODUCTION_INTEGRATION,
        "account_usage_read": "AVAILABLE" if usage is not None else "UNAVAILABLE",
        "account_rate_limits_read": "AVAILABLE" if limits is not None else "UNAVAILABLE",
        "model_turn_started": "NO",
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit Codex-local READREF canary (default OFF)")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("status", help="show the default OFF state")
    sub.add_parser("probe", help="probe account telemetry without a model turn")
    run = sub.add_parser("run", help="run one explicitly enabled local Codex task")
    run.add_argument("--enable", action="store_true", help="explicitly activate the canary for this invocation")
    run.add_argument("--repo", type=pathlib.Path, default=pathlib.Path.cwd())
    run.add_argument("--source", help="one repository-relative UTF-8 source path")
    run.add_argument("--prompt-file", help="UTF-8 task prompt file, or - for stdin")
    run.add_argument("--assess-non-sensitive", action="store_true", help="explicitly assess only the designated source")
    run.add_argument("--record-out", type=pathlib.Path, help="optional no-clobber sanitized JSON outside the repository")
    args = parser.parse_args(argv)
    if args.command in {None, "status"}:
        print("CANARY OFF (default)")
        return 0
    if args.command == "probe":
        print(json.dumps(probe_account_support(), sort_keys=True))
        return 0
    if not args.enable:
        print("CANARY OFF; no Codex task started")
        return 0
    if not args.source or not args.prompt_file:
        parser.error("--enable requires --source and --prompt-file")
    repo = args.repo.resolve()
    try:
        record_out = args.record_out
        if record_out is not None:
            resolved_record = record_out.resolve()
            if repo == resolved_record or repo in resolved_record.parents:
                raise ValueError("session record must be outside the repository")
            if record_out.exists() or record_out.is_symlink() or not record_out.parent.is_dir():
                raise ValueError("session record requires a new path with an existing parent")
        prompt = sys.stdin.read() if args.prompt_file == "-" else pathlib.Path(args.prompt_file).read_text(encoding="utf-8")
        if not prompt.strip():
            raise ValueError("task prompt cannot be empty")
        record = run_task(
            repo, args.source, prompt,
            assessed_non_sensitive=args.assess_non_sensitive,
            on_active=lambda: print(
                "CANARY ACTIVE (explicit local invocation)" if args.assess_non_sensitive
                else "CANARY ACTIVE (source UNKNOWN; RAW-only)",
                flush=True,
            ),
        )
        encoded = json.dumps(record, sort_keys=True, separators=(",", ":"))
    except (OSError, UnicodeError, ValueError) as exc:
        # The error may contain a private path; do not echo it.
        print(f"CANARY NOT STARTED: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(encoded)
    if record_out is not None:
        try:
            with record_out.open("x", encoding="utf-8") as destination:
                destination.write(encoded + "\n")
        except OSError:
            print("CANARY TASK FINISHED; sanitized record was not saved", file=sys.stderr)
            return 1
    return 0 if record["task_outcome"] == "COMPLETED" and record["raw_only_reason"] in _NORMAL_RAW_ONLY_REASONS else 1


if __name__ == "__main__":
    sys.exit(main())
