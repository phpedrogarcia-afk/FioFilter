# M15 — explicit Codex-local READREF canary surface

## Status and boundary

```text
CANARY_DEFAULT=OFF
APP_SERVER_TRANSPORT=STDIO
DYNAMIC_TOOL_API=EXPERIMENTAL
PRODUCTION_INTEGRATION=NO
MCP=NO
GLOBAL_HOOK=NO
PROXY=NO
DAEMON=NO
MAX_READREF_PER_SESSION=3
RECOVERY_TRIGGERED_SESSION_FALLBACK=YES
FIRST_GENUINE_CANARY_TASK=M15-C1_NOT_RUN_HERE
```

`python -m fiofilter.canary` and `python -m fiofilter.canary status` only print
`CANARY OFF (default)`. `probe` starts a local App Server connection and reads
account telemetry support without starting a thread or model turn. Only
`run --enable` can start an active local task. Normal Codex and FioFilter
invocations do not import or instantiate the canary. The implementation uses
the [official Codex App Server protocol](https://developers.openai.com/pt-BR/docs/app-server)
and the E1/E2-proven client-executed dynamic-tool path, not interception of an
ambient Codex session. Dynamic tools remain an experimental API.

An active invocation needs one Git-root `--repo`, one repository-relative UTF-8
`--source`, a UTF-8 `--prompt-file` (or `-` for stdin), and `--enable`. The
repository must be clean before the task. READREF additionally requires the
operator's explicit `--assess-non-sensitive` assessment of the *designated
source only*. Without it, sensitivity is UNKNOWN and every delivery stays RAW.
The client shows `CANARY ACTIVE` or `CANARY ACTIVE (source UNKNOWN; RAW-only)`
before starting the task. No model name, token budget, global config, credential,
or persistent service is installed or changed. The turn requests workspace
writes only under the selected repository, no network access, and no approval
escalation; an unexpected approval request stops the canary.

## Delivery and recovery

The task-scoped `fio_canary_read` dynamic tool is the designated source's only
authorized read interface. The first read is RAW. Each later read calls the
unchanged M14 `ReadReceiptABHarness` with a full-file view and monotonic call
index. Only its exact same-session/source/view direct F4, byte-equal, explicitly
NON_SENSITIVE, shorter-than-RAW and recoverable receipt can emit READREF.
Uncertain, changed, sensitive, unknown or uneconomic views remain RAW.

The client permits at most three READREF emissions in one ephemeral session;
reaching the cap switches subsequent reads to RAW while issued references remain
recoverable.
The first `fio_canary_expand` request immediately disables any further READREF;
successful recovery returns the M14-verified exact bytes and charges all
recovered bytes. Malformed/unissued/corrupt references, non-UTF-8 delivery,
protocol violations, an explicit `fio_canary_abort`, observable designated-read
bypass, unexpected approval requests or App Server failure stop the canary.
The client requests turn interruption for an active anomaly, clears ephemeral
receipts, and any subsequent read is RAW-only. A successful recovery alone
changes the session to RAW-only without interrupting the task. All task threads
are ephemeral and the local App Server process is terminated after the run.

This client is not a universal read interceptor: the exclusive read path is
task-scoped instruction plus dynamic tool. Direct command mentions of the
designated source are detected and stop the canary, but indirection outside
that observable surface cannot be proved absent. M15-C1 must check the actual
task trace and outcome before claiming useful active reduction.

## Economics and telemetry

For emitted references, exact `RAW_BYTES_AVOIDED_GROSS` is the sum of the RAW
view lengths replaced. `REFERENCE_BYTES` and `RECOVERY_BYTES` are actual tool
payload lengths. `ADDITIONAL_CONTEXT_BYTES` is the exact UTF-8 size of the
client-supplied canary developer instructions plus serialized dynamic-tool
schema; this is a conservative client-side byte charge, not provider-token
accounting. The session record computes:

```text
NET_VISIBLE_BYTES_SAVED = RAW_BYTES_AVOIDED_GROSS
  - REFERENCE_BYTES - RECOVERY_BYTES - ADDITIONAL_CONTEXT_BYTES
ECONOMIC_SUCCESS = (READREF_EMISSIONS > 0 AND NET_VISIBLE_BYTES_SAVED > 0
                    AND NO_ANOMALY_STOP)
```

One emission is never itself called a successful session. Negative and zero
net outcomes are retained. Account `account/usage/read` and
`account/rateLimits/read` are probed before and after the task, independently.
Both methods were available in the local no-turn probe on `codex-cli 0.154.0`;
future runs still tolerate either being unavailable. Account token activity and
rate-limit deltas are concurrent account/runtime observations, **not**
READREF-causal savings. If `thread/tokenUsage/updated` arrives, only numeric
per-thread totals are retained with App Server runtime provenance. No token
budget is introduced to obtain telemetry.

The strict `FIO_READREF_CANARY_SESSION_V1` record reuses the Efficiency Feed's
private-identifier hashing but is separate from the shadow-only
`FIO_EFFICIENCY_FEED_V1` schema. It contains session hash, repository ID and
commit, read/reference/recovery/fallback counts, byte economics, available tool
call count, sanitized account/per-thread observations, and task outcome. It
contains no prompt, final model text, raw receipt, credential, command text or
absolute private path. A record is printed at the end; optional `--record-out`
writes the same JSON to a new, no-clobber path outside the repository. No
record file is written by default.

## Validation limit

M15 tests exercise the default OFF state, explicit ON path, three-reference
cap, recovery-triggered RAW fallback, corrupt/cross-session recovery, ephemeral
cleanup, sensitivity and UNKNOWN fail-closed behavior, net accounting,
noncausal/unavailable telemetry, sanitized records, and dynamic-tool delivery.
The read-only account probe starts no model turn. This mission does **not** run
a synthetic or genuine canary task; the first real task is separately scoped
as M15-C1 after review.
