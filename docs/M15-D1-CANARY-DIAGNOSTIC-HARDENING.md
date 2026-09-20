# M15-D1 — bounded canary stop diagnostics

```text
ACTIVE_CANARY=PAUSED_PENDING_DIAGNOSTIC_HARDENING
MODEL_CANARY_RUNS_IN_D1=0
C2_RERUN=NO
GLOBAL_ACTIVATION=NO
FIO_HANDOFF_INTEGRATION=NO
```

## Historical C2 result

The following facts are supplied by the M15-D1 mission's C2 handoff. D1 neither
reruns C2 nor reconstructs missing detail from a model response. Existing C1/C2
records are not edited or upgraded to V2.

```text
VERDICT=M15_C2_FAIL_SAFETY
SAFETY_GATE_TRIGGERED=YES
CONFIRMED_SAFETY_VIOLATION=NO
ANOMALY_DETAIL=UNAVAILABLE_BY_V1_SCHEMA
READREF_EMITTED=1
RECOVERY_REQUESTS=1
NET_VISIBLE_BYTES_SAVED=-1318
TASK_COMPLETED=NO
FILES_CHANGED=NONE
RAW_ONLY_REASON=REPORTED_ANOMALY
```

The abort occurred after recovery. The preserved failure verdict identifies a
stopped safety gate; it does not establish a READREF safety regression, its
cause, or a specific violated invariant. The V1 empty abort schema did not
retain the report's class or phase. Absence of detail is not proof of safety or
proof of a violation. The negative economics remain unchanged.

## Tool and record contracts

`fio_canary_abort` accepts an object containing **only** required
`anomaly_class`, one of `BEHAVIORAL_CONCERN`, `TASK_QUALITY_CONCERN`,
`SAFETY_CONCERN`, `PROTOCOL_CONCERN`, `OTHER`. The schema disallows additional
properties and the client enforces the same boundary. Missing/unknown classes,
free text, wrong types, or model-supplied phase/source become a client-detected
`PROTOCOL_ANOMALY`; they still stop and request interruption. Invalid argument
values are never copied into diagnostics.

New session records have `schema_version=FIO_READREF_CANARY_SESSION_V2`.
Existing keys, including `raw_only_reason`, retain their meanings. JSON fields
use lowercase names and JSON booleans; uppercase YES/NO here is report notation.

| Field | Meaning |
| --- | --- |
| `safety_gate_triggered` | An abnormal stop occurred; normal reference-cap and successful-recovery RAW fallbacks alone are false. |
| `confirmed_safety_violation` | False. Current detectors reject/stop; none establishes a delivered safety violation or READREF-caused behavioral regression. A future affirmative value requires a separately specified machine-verifiable proof. |
| `anomaly_kind` | `MODEL_REPORTED_ANOMALY` or `MACHINE_DETECTED_ANOMALY`; null without an abnormal stop. |
| `anomaly_source` | `MODEL_REPORTED` for a valid abort call; `HARNESS_DETECTED` for a recovery failure raised by the unchanged M14 harness; `CLIENT_DETECTED` for client/protocol checks, including unissued references. Null without anomaly. |
| `anomaly_class` | Required model enum for a valid report. Machine recovery-integrity, bypass and non-UTF-8 checks map to `SAFETY_CONCERN`; other client stops to `PROTOCOL_CONCERN`. A concern is not a confirmed violation. |
| `anomaly_phase` | Last completed read/recovery phase maintained by the client at the first abnormal stop; never supplied by the model. |
| `abort_after_readref` | At least one READREF emitted before the first abnormal stop. False without an abnormal stop. |
| `abort_after_recovery` | At least one **successful** recovery before that stop. A recovery request or failed integrity check is insufficient. |
| `structural_event_trace` | Ordered tail of at most 64 enum strings; no event payload. |
| `structural_event_trace_dropped` | Exact count of older events evicted from that tail. Zero means no eviction. |

The first abnormal stop and its diagnostic snapshot are retained. Later RAW
reads or additional errors cannot overwrite the initiating class, phase or
abort flags. Phase starts at `BEFORE_READ`, becomes `AFTER_RAW` or
`AFTER_READREF` after a corresponding read result, and `AFTER_RECOVERY` after
verified recovery. A subsequent RAW read while a session gate is set becomes
`RAW_ONLY`. Starting a recovery request does not erase the last completed phase;
its position is represented by `RECOVERY_REQUESTED`. Thus failure during a
recovery is distinguishable from a later report after successful recovery.

## Structural trace and privacy

Allowed events are `READ_RAW`, `READREF_EMITTED`, `RECOVERY_REQUESTED`,
`RECOVERY_SUCCEEDED`, `RAW_FALLBACK`, `ANOMALY_REPORTED`, `ANOMALY_DETECTED`,
`INTERRUPT_SENT`. `RAW_FALLBACK` retains the existing counter's meaning: a RAW
result on a later read, including a changed/uneconomic view. A RAW fallback has
both `READ_RAW` and `RAW_FALLBACK` events. Only the first anomaly is recorded.

Read/recovery events describe client-side results, not proof that a model
received, understood or retained them. `INTERRUPT_SENT` is appended after the
transport accepts the send call; it is not an acknowledgment of interruption.
If turn identifiers are unavailable, the existing immediate kill/cleanup still
occurs and the interrupt is deferred until `turn/started` supplies the ID. A
failed transport send must not create a sent event.

The trace contains no timestamps, filenames, commands, raw source bytes,
references, prompts, model responses, exception text, or free-form descriptions.
It is a bounded in-memory deque; records receive a list copy. On overflow the
oldest event is discarded and loss is counted. The first anomaly snapshot
survives trace eviction. Existing sanitized numeric telemetry and hashed session
metadata are unchanged. No raw content persistence is added.

## Unchanged safety and economics

The same M14 harness, direct-F4/sensitivity/recovery requirements, three-reference
cap, first-recovery RAW gate, kill switch and ephemeral cleanup apply. Every
anomaly still stops the canary, clears receipts and requests interruption.
An enum validates diagnostics; it is never an exception to a stop rule.

Recovery, reference and developer-instruction/tool-schema bytes remain charged
by the existing net formula. The larger abort schema/instruction is included
automatically for future runs. No historical byte total is recalculated and no
actual token saving is claimed.

## Validation and limits

The exact base suite passed 571 tests. Twenty-four initial D1 regression cases
failed on V1 before implementation. Tests use synthetic inert buffers and a
fake client, covering required enums, free-text rejection, client/harness/model
provenance, state-derived phases, post-reference and post-recovery stops, bounded
trace, payload exclusion, unchanged gate behavior, cleanup and interruption.
Additional cases cover every existing machine stop, normal cap fallback and
failed interrupt transport. The final local suite passed **604 tests**, including
33 new diagnostic cases; `compileall` and `git diff --check` passed. Local tests
used Python 3.12 with an existing isolated pytest dependency directory supplied
via `PYTHONPATH`; no global package installation was needed. No real App
Server/model session is executed.

Diagnostic integrity is a software-test claim. D1 provides no new behavioral
safety or economic evidence, no successful rerun of C2 and no authorization to
resume a canary. Existing C1/C2 negative and inconclusive results remain visible.
