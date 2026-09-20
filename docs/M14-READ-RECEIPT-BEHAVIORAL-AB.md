# M14 — Read Receipt Behavioral A/B laboratory

## Scope and status

M14 is an explicit, process-local experiment for the M13-selected candidate
`READ_RECEIPT_REFERENCE`. It is not an activation of FioFilter in Codex Web.

```text
ACTIVE_SUPPRESSION_NORMAL_RUNTIME=NO
AUTOMATIC_ACTIVATION=NO
HOOK=NO
PROXY=NO
MCP=NO
DAEMON=NO
FIO_HANDOFF_BRIDGE_STATUS=NOT_IMPLEMENTED
HANDOFF_REDUNDANCY_ANALYZER=DEFERRED
MODEL_ID_CONTROLLED=NO
ACTUAL_TOKEN_SAVINGS=UNAVAILABLE
```

The implementation is `fiofilter.read_receipt_ab.ReadReceiptABHarness`. It is
constructed explicitly with either `CONTROL` or `TREATMENT`; normal FioFilter
paths do not construct it. Its receipt buffers are process-memory only and are
cleared by `close_session()`.

## Frozen hypothesis and contracts

**Hypothesis**: when an exact same-session, same-source, same-view reread has
direct F4 proof and a recoverable, economic reference, replacing that second
RAW delivery with READREF may reduce visible context without degrading task
correctness. This remains unproven.

| Condition | First delivery | Repeat delivery |
|---|---|---|
| `CONTROL` | RAW | RAW, even if F4 is proven |
| `TREATMENT` | RAW | READREF only when every gate passes; otherwise RAW |

The treatment requires all of the following: same session, normalized source
identity, exact view ID, `F4_CURRENT_VIEW_BYTE_EQUAL` at the direct one-buffer
read boundary, identical SHA-256 and bytes, reference shorter than RAW, explicit
caller assessment `Sensitivity.NON_SENSITIVE`, a live ephemeral receipt, and
successful recovery metadata validation. Detector no-match is not an assessment.

The READREF contains the existing versioned marker, receipt ID, SHA-256, view ID
and byte count. `EXPAND(reference)` accepts only that exact framing and verifies:

```text
SHA256(EXPAND(reference)) == reference.sha256
EXPAND(reference) == session_receipt_buffer
```

Malformed, missing, corrupt, closed, mismatched or cross-session receipts raise
an explicit recovery error; treatment falls back to RAW before emitting a
reference if receipt validation is unavailable.

## Fail-to-RAW matrix

| Condition not proven | Delivery |
|---|---|
| control mode or treatment kill switch | RAW |
| first read | RAW |
| source changed / hash mismatch | RAW |
| different or unknown view | RAW |
| different session | RAW |
| missing, closed or inconsistent receipt | RAW |
| sensitive or not explicitly `NON_SENSITIVE` | RAW |
| reference has no byte gain | RAW |
| failed F4 / any evaluator uncertainty | RAW |

There is no hidden activation and no cross-session lookup.

## Matched-pair accounting

All economics are visible byte accounting. They are not actual model tokens or
billing. For a matched repeat:

```text
NET_VISIBLE_BYTES_SAVED = CONTROL_REPEAT_RAW_BYTES
  - (TREATMENT_REFERENCE_BYTES
     + TREATMENT_RECOVERY_BYTES
     + TREATMENT_ADDITIONAL_CONTEXT_BYTES)
```

Gross READREF reduction and net savings are separate fields. A bytes/4 value,
when useful, is reported only as
`ESTIMATED_CONTEXT_TOKEN_EQUIVALENT_BYTES_DIV_4`.

## Pre-registered task corpus and evaluation

The following task definitions are frozen before any behavioral result. They
must run in fresh, disposable worktrees/repositories at the same M14 commit.
The evaluator is kept outside the task prompt where practical.

| Task ID | Required reread distance | Objective evaluator |
|---|---|---|
| `FACT_RECALL_AFTER_REREAD_NEAR` | near | exact expected answer from a source fixture |
| `SINGLE_FILE_CODE_CHANGE` | near | focused regression test plus changed-file allowlist |
| `MULTI_FILE_CODE_CHANGE` | medium | complete test command plus required two-file mutation set |
| `DEBUGGING_OR_FAILURE_INVESTIGATION` | near | initially failing test becomes passing; forbidden edits absent |
| `LONGER_DISTANCE_REREAD` | far | exact answer or test after intervening neutral work |
| `FIOFILTER_REALISTIC_READ_RECEIPT_CHANGE` | far | focused FioFilter regression and full test suite |

Run order alternates by task: pair 1 CONTROL→TREATMENT, pair 2
TREATMENT→CONTROL, pair 3 CONTROL→TREATMENT. Stop immediately after a plausible
treatment-caused wrong edit, unrecoverable reference, recovery byte mismatch,
cross-session leak, or sensitive-buffer persistence.

## Pair execution kit for independent Codex contexts

The current Codex Web surface does not expose a repository-consumable event
subscription or a supported output-substitution API. Therefore this repository
cannot honestly execute an independent real Codex CONTROL/TREATMENT pair from
within this already-contaminated coding context. The local laboratory is
`CONTROLLED_LIVE_LAB`; it is not a real Codex behavioral result.

The required external host contract is one deliberately narrow function call per
designated file-read event, in the *same process* that delivers the result to
the fresh Codex task:

```python
harness = ReadReceiptABHarness(condition, session_id, base_dir=repo_root)
result = harness.read(call_id, source_path, view, call_index, sensitivity=Sensitivity.NON_SENSITIVE)
# Deliver result.payload verbatim to that task. Never substitute any other tool output.
# A recovery request calls harness.expand(result.reference_text) and delivers its bytes verbatim.
```

That host is an experiment driver, not an installed Codex integration. It must
discard the harness at the end of the task/session, never serialize the store,
and provide no reference for undesignated or uncertain reads.

For each external pair, use two fresh Codex Web tasks and two disposable clones
of the same committed M14 SHA. Before each task verify `git rev-parse HEAD` and
`git status --porcelain` are identical. Give both tasks the same body, differing
only in the selected read interface condition:

```text
TASK BODY
Work only in the supplied disposable repository. Complete <TASK_ID>.
Use the explicit M14 read interface for the designated repeated read of
<PATH_AND_VIEW>. Do not alter task files outside the stated objective.
Run <EVALUATION_COMMAND> before reporting completion.
Return the command output, changed-file list, every READREF recovery request,
and whether the requested source was reread.
```

Control preamble:

```text
CONDITION=CONTROL. Deliver the first and repeat requested views as RAW. Do not
use or synthesize a READREF.
```

Treatment preamble:

```text
CONDITION=TREATMENT. Deliver the first requested view as RAW. On the designated
repeat, emit READREF only if the M14 harness proves direct F4, explicit
NON_SENSITIVE assessment, exact receipt recovery and positive byte gain. On any
uncertainty deliver RAW. If recovery is requested, call EXPAND and record the
full recovered byte cost.
```

Record the frozen repository SHA, task ID, condition, evaluator result, changed
and unexpected files, read/reference/recovery counts, raw/reference/recovery/
additional bytes, and optional wall time. Exact model ID, exact provider tokens,
turn boundaries and context window remain unavailable; do not replace them with
claims. Minimum evidence is three independent matched pairs covering near,
far and coding; up to five may be run if economical.

The setup and capture commands are fixed for every pair (replace only the
explicit task ID and evaluator command selected from the frozen table):

```bash
git clone --no-local <committed-m14-worktree> m14-pair-<task-id>-<condition>
cd m14-pair-<task-id>-<condition>
git checkout --detach <M14_COMMIT_SHA>
test "$(git status --porcelain)" = ""
python -m pytest <FOCUSED_EVALUATOR> -q
python -m pytest tests/ -q
git status --porcelain
git diff --name-only
```

The experiment driver records the command outputs, the visible-byte accounting
from `NetVisibleByteEconomics`, recovery counters, and the final changed-file
list in a local non-Git result file. No prompt, source content, receipt buffer,
credential or absolute home path belongs in that record.

## Advancement rule

No canary is authorized by this harness alone. The first available verdict is
`M14_AB_PASS_HARNESS_READY_EXTERNAL_PAIRS_REQUIRED` until independent pairs
show no task-quality regression, no safety failure, positive net visible-byte
savings after recovery, acceptable recovery burden and replication across more
than one task class.
