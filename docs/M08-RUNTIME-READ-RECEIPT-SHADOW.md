# M08 Runtime Read Receipt Shadow Harness Report

## 1. Executive Summary

Mission **M08** constructs and operationally validates the **Incremental Runtime Read Receipt Shadow Harness** for FioFilter.

Where M07 mathematically proved file read freshness in offline batch analysis, M08 proves that shadow observation can operate incrementally in real time without altering what the coding agent receives or modifying the host runtime.

### Key Deliverables & Operational Proofs:
1. **Dual Operational Modes**:
   - **Mode A (`PASSIVE_STREAM_SHADOW`)**: Non-invasive observer tailing an append-only session log (`.jsonl`). Never intercepts execution, injects tokens, or modifies runtime delivery.
   - **Mode B (`DIRECT_READ_LAB`)**: Controlled laboratory harness executing file reads once, returning exact byte-for-byte RAW output to the caller, and computing shadow receipt telemetry asynchronously.
2. **Partial-Write Safety & Crash Consistency**:
   - Tailing observer buffers incomplete lines: `PARTIAL_JSON_DOUBLE_PROCESSING = 0`, `PARTIAL_JSON_LOSS = 0`.
   - Atomic checkpointing (`ShadowCursor`) enables seamless restart/resume with hash-chained ledger continuity.
   - Source rewind/rotation detection fails closed (`SourceRewindException`) if observed logs shrink or rotate unexpectedly.
3. **TOCTOU Race Mitigation & Failure Isolation (Mode B)**:
   - Single-read architecture proves `PROOF_DELIVERY_BYTE_DIVERGENCE_WINDOW = 0_BY_SINGLE_BUFFER` because the same in-memory byte buffer is used for both raw return and telemetry hashing (`FILESYSTEM_POST_READ_MUTATION_POSSIBLE = YES`).
   - Observer failure isolation: telemetry exceptions are strictly contained; raw delivery is never blocked or corrupted (`SHADOW_FAILURE_RAW_DELIVERY_PRESERVED = PASS`).
   - Mtime spoof defense: SHA-256 byte verification defeats timestamp spoofing (`MTIME_SPOOF_DEFENSE = PASS`).
4. **Empirical Stream vs. Batch Equivalence**:
   - Streaming Source A (`206,427,325 B`, 35,040 records) through the runtime harness in pseudo-live chunks yields exact mathematical parity with M07 batch evaluation:
     $$\text{STREAM\_VS\_BATCH\_EQUIVALENCE} = \mathbf{PASS} \quad (490 / 490 \text{ identical decisions})$$
5. **Runtime Overhead & Performance**:
   - Ingestion throughput: **3,954.6 records/sec** (entire 206 MB session processed in 8.861 s).
   - Median chunk latency: **122.17 ms** (p95: 155.94 ms, p99: 165.55 ms per 500-record batch).
   - Peak active in-memory receipts: **410** (`APPROXIMATE_RECEIPT_OBJECT_FOOTPRINT` ≈180 KB).
6. **Epistemic Scope & Target Selection**:
   - Codex runtime is currently unavailable (`LIVE_CODEX_SHADOW = NOT_RUN_CODEX_UNAVAILABLE`).
   - Reexposure lane is frozen in a verified, ready state: `REEXPOSURE_STATUS = READY_FOR_LIVE_CODEX_SHADOW`.
   - Under the mission decision rule, FioFilter selects `NEXT_LANE = DISCOVERY_STRUCTURAL_SHADOW`.

---

## 2. Architectural Design & Mode Separation

The runtime shadow harness decouples observation from execution:

```
                      +------------------------------------------+
                      |         HOST RUNTIME / ENVIRONMENT       |
                      +------------------------------------------+
                                    |              |
                [Mode A: Log Append]              [Mode B: Direct Read]
                                    |              |
                                    v              v
        +-----------------------------+          +-----------------------------+
        |   PASSIVE STREAM SHADOW     |          |       DIRECT READ LAB       |
        |  - Incremental JSONL tail   |          |  - Single disk read         |
        |  - Partial write buffer     |          |  - Unmodified RAW delivery  |
        |  - Atomic checkpoint        |          |  - Telemetry isolation      |
        +-----------------------------+          +-----------------------------+
                        |                                      |
                        +------------------+-------------------+
                                           |
                                           v
                        +-------------------------------------+
                        |     RUNTIME RECEIPT STATE & LEDGER  |
                        |  - Epistemic Freshness Check (A/B)  |
                        |  - Deduplication per call_id        |
                        |  - SHA-256 Hash Chaining            |
                        |  - Observational Salience Tracking  |
                        +-------------------------------------+
```

### 2.1 Mode A: Passive Stream Shadow (`PASSIVE_STREAM_SHADOW`)
- **Role**: Passively tails the agent's growing session log (`rollout-*.jsonl`).
- **Safety Boundary**: Zero runtime modification. Does not hook into subprocesses, intercept stdin/stdout, or install proxy layers.
- **Transaction Flow**:
  1. `PassiveJsonlTailSource` polls new bytes from disk.
  2. Incomplete trailing lines remain buffered in memory; only full newline-terminated lines are parsed.
  3. Paired tool calls (`custom_tool_call` + `custom_tool_call_output`) are reconstructed.
  4. Non-read operations and unstructured commands are bypassed.
  5. Structured `FILE_READ` events are evaluated against session-scoped receipts in `RuntimeReceiptState`.
  6. Ledger entry is appended to `m08_runtime_shadow_events_v1.jsonl`.
  7. Atomic checkpoint (`m08_runtime_shadow_checkpoint_v1.json`) is committed.

### 2.2 Mode B: Direct Read Lab (`DIRECT_READ_LAB`)
- **Role**: Provides a drop-in file reading utility for controlled laboratory benchmarking.
- **Safety Boundary**: Guarantees byte-for-byte exactness with standard OS file reading (`HARNESS_RAW_OUTPUT == DIRECT_BASELINE_READ`).
- **TOCTOU Race Defense**:
  In naïve implementations, an observer reads the file once to compute telemetry, and the agent reads the file again to deliver content. If the file changes between the two reads (Time-of-Check to Time-of-Use), telemetry diverges from delivery. `DirectReadLab` solves this by reading the authoritative file bytes **once**, delivering those exact bytes to the caller, and computing SHA-256 hashes on the identical in-memory buffer (`PROOF_DELIVERY_BYTE_DIVERGENCE_WINDOW = 0_BY_SINGLE_BUFFER`). While disk mutations immediately following the read remain possible (`FILESYSTEM_POST_READ_MUTATION_POSSIBLE = YES`), divergence between returned bytes and evaluated proof is eliminated.
- **Observer Failure Isolation**:
  If any telemetry subsystem encounters an unhandled exception or corrupt metadata, `DirectReadLab` catches the error, sets `decision = None`, and returns the unmodified raw bytes. Telemetry failure can never break application execution (`SHADOW_FAILURE_RAW_DELIVERY_PRESERVED = PASS`).

---

## 3. Partial Write Safety, Crash Consistency, and Rewind Defense

### 3.1 Partial JSON Tailing Algorithm
When a process appends to a log file, writes may be flushed mid-record. Reading incomplete lines causes JSON decode errors or partial state corruption.
`PassiveJsonlTailSource` implements strict boundary handling:
- Reads raw chunks into an internal byte buffer.
- Scans for `\n`.
- If no newline is present, the buffer is retained and `0` records are yielded.
- When a newline arrives, the line is sliced, decoded, and parsed.
- The committed file offset advances only to the boundary of successfully parsed lines.
- **Verified Property**: Writing half a JSON record produces 0 events. Appending the remainder produces exactly 1 event. No double processing, no dropped records.

### 3.2 Crash Consistency and Restart/Resume Equivalence
The harness maintains atomic crash consistency via two artifacts:
1. `m08_runtime_shadow_events_v1.jsonl`: Append-only, SHA-256 hash-chained event ledger.
2. `m08_runtime_shadow_checkpoint_v1.json`: Atomically replaced checkpoint containing:
   - `last_committed_offset`: Byte position in source file.
   - `last_event_hash`: Hash of the latest ledger record.
   - `processed_event_count`: Number of processed read events.
   - `state_snapshot`: Serialized active receipts and deduplication keys.
   - `pending_calls`: In-flight tool calls awaiting output pairing.
   - `current_episode_id` & `record_counter`: Turn and sequence counters.

**Restart Invariant**: Stopping processing at event $N$, killing the process, restarting from checkpoint, and resuming through event $N+M$ produces an identical final event hash and ledger state as an uninterrupted run. Verified in `tests/test_runtime_shadow.py::test_restart_resume_equivalence`.

### 3.3 Source Rewind and Replacement Defense
If an observed log file shrinks (truncation) or inode/path identity rotates unexpectedly, continuing from the old byte offset would cause state corruption.
- `PassiveJsonlTailSource` verifies that current file size is $\ge$ `start_offset`.
- If size drops below committed offset, it immediately halts and raises `SourceRewindException("SOURCE_REWOUND_OR_REPLACED")`.

---

## 4. Empirical Benchmark on Real Workload (Source A)

The runtime shadow harness was executed against the primary historical workload:
- **Source File**: `rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl`
- **File Size**: 206,427,325 B
- **File SHA-256**: `bc4561d4588a73a6889ca38d8c180ae467e51eea5f023aaba7a222425cf350a0`
- **Mode**: Pseudo-live streaming with 500-record tail chunks.

### 4.1 Throughput and Latency Results

| Metric | Measured Value | Unit / Scale |
| :--- | :--- | :--- |
| **Total Session Records** | 35,040 | Records |
| **Evaluated Read Events** | 490 | Tool calls (`FILE_READ` with `target_path`) |
| **Wall-Clock Processing Time** | 8.861 | Seconds |
| **Ingestion Throughput** | 3,954.6 | Records / second |
| **Tail Poll Iterations** | 72 | Iterations (500 records/chunk) |
| **Chunk Latency — Median (p50)** | 122.17 | Milliseconds |
| **Chunk Latency — p95** | 155.94 | Milliseconds |
| **Chunk Latency — p99** | 165.55 | Milliseconds |
| **Peak Active In-Memory Receipts** | 410 | Receipts tracked |
| **Final Ledger Event Hash** | `87ead677...` | SHA-256 (64 hex characters) |

### 4.2 Stream vs. Batch Equivalence Verification

Every decision generated by the streaming runtime harness was compared against the M07 batch evaluation baseline:

| Dimension | Batch M07 Baseline | Mode A Streaming | Match Status |
| :--- | :--- | :--- | :--- |
| **Evaluated Events** | 490 | 490 | **100% IDENTICAL** |
| **`FIRST_READ_RAW`** | 410 | 410 | **100% IDENTICAL** |
| **`HISTORICAL_IDENTICAL_READ_CANDIDATE`** | 17 | 17 | **100% IDENTICAL** |
| **`VIEW_IDENTITY_UNKNOWN_RAW`** | 30 | 30 | **100% IDENTICAL** |
| **`SOURCE_CHANGED_RAW`** | 14 | 14 | **100% IDENTICAL** |
| **`REFERENCE_NOT_ECONOMIC_RAW`** | 14 | 14 | **100% IDENTICAL** |
| **`SOURCE_IDENTITY_UNKNOWN_RAW`** | 5 | 5 | **100% IDENTICAL** |
| **Total Raw Bytes** | 4,265,979 B | 4,265,979 B | **100% IDENTICAL** |
| **Hypothetical Avoided Bytes** | 181,762 B | 181,762 B | **100% IDENTICAL** |

$$\text{STREAM\_VS\_BATCH\_EQUIVALENCE} = \mathbf{PASS}$$

---

## 5. Epistemic Freshness Separation & Observational Salience

### 5.1 Freshness Hierarchy in Runtime Observation
M08 formalizes three distinct runtime freshness levels:
1. `PASSIVE_F1_DELIVERY_IDENTITY`:
   Observed in passive log tailing. We prove that the session previously delivered bytes with hash $H$. We cannot probe the live filesystem without side-effects, so freshness is bounded to historical output equivalence.
2. `POST_OBSERVATION_F4`:
   A passive observer verifies a live file on disk *after* the agent finishes reading it. Proves disk state, but vulnerable to sub-millisecond TOCTOU if concurrent writes occur.
3. `DIRECT_EXECUTION_F4`:
   Achieved exclusively in `DirectReadLab`. The single-read architecture guarantees that the delivered bytes and the verified SHA-256 hash are identically bound.

### 5.2 Observational Salience Risk Distribution
Replacing repeated reads with references reduces token volume, but coding agent reasoning often requires the recent presence of tokens in the active context window. M08 rigorously establishes explicit denominator hygiene:
- `FIRST_DELIVERY_NOT_SALIENCE_RISK = YES`: 445 read calls (4,040,090 B raw) represent first-time deliveries (or views where no prior receipt existed). They carry zero reread salience risk and are excluded from the repeat-read risk denominator.
- `SALIENCE_REPEAT_DENOMINATOR_EXPLICIT = YES`: Exactly 45 calls (225,889 B raw, 181,762 B avoided) represent repeated deliveries where call distance $D$ is established relative to a prior receipt.

| Salience Risk Bucket | Distance ($D = \text{calls since receipt}$) | Repeat Events | % of Repeat Events | Raw Bytes | Avoided Bytes | Operational Implication |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`NEAR`** | $D \le 10$ calls | 10 | 22.2% | 12,441 B | 0 B | High context recency; polling/un-economic |
| **`MEDIUM`** | $11 \le D \le 25$ calls | 17 | 37.8% | 7,948 B | 235 B | Moderate recency; viable candidate zone |
| **`FAR`** | $26 \le D \le 50$ calls | 1 | 2.2% | 16,140 B | 15,998 B | Distant reference; attention may have faded |
| **`VERY_FAR`** | $D > 50$ calls | 17 | 37.8% | 189,360 B | 165,529 B | Deep historical re-reads; cognitive risk high |
| **Total Repeat Deliveries** | — | **45** | **100.0%** | **225,889 B** | **181,762 B** | — |

**Epistemic Insight**: When isolating true repeat deliveries, 37.8% occur at extreme call distances ($D > 50$), while 60.0% occur within 25 calls. Active context suppression without agent-in-the-loop behavioral testing risks attention degradation on distant references. FioFilter's choice to remain strictly in SHADOW mode protects agent cognitive integrity.

---

## 6. Target Availability & Next Lane Decision

### 6.1 Status of Live Codex Environment
- Codex execution environment is currently unavailable.
- Under mission discipline, Antigravity does NOT simulate fake Codex responses or fabricate live proxy benchmarks.
- `LIVE_CODEX_SHADOW = NOT_RUN_CODEX_UNAVAILABLE`.
- Reexposure harness is fully built, tested, and validated: `REEXPOSURE_STATUS = READY_FOR_LIVE_CODEX_SHADOW`.

### 6.2 Decision Rule Application
Mission instructions require:
> If Codex is unavailable, freeze reexposure at `LIVE_SHADOW_READY`, select `NEXT_LANE = DISCOVERY_STRUCTURAL_SHADOW`, and record the decision.

In accordance with this rule:
- Reexposure specialization for read receipts is completed and frozen.
- `ACTIVE_READ_REFERENCE_SUPPRESSION = NO`.
- Selected next research and discovery lane:
  $$\mathbf{NEXT\_LANE = DISCOVERY\_STRUCTURAL\_SHADOW}$$

---

## 7. Audit Artifacts Produced

The following deterministic artifacts were generated and persisted to `C:\Users\phped\.fiofilter\runtime-shadow\`:

1. `m08_runtime_shadow_events_v1.jsonl`: 490 append-only SHA-256 hash-chained shadow events.
2. `m08_runtime_shadow_checkpoint_v1.json`: Final atomic checkpoint with cursor, state snapshot, and sequence counters.
3. `m08_runtime_shadow_manifest_v1.json`: Cryptographic manifest detailing event counts, byte totals, and hash continuity.
4. `m08_runtime_shadow_summary_v1.json`: Structured benchmark metrics for automated consumption.
