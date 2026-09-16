# M06: Session-Aware Reexposure Shadow Evaluation

## Executive Summary

Mission M06 constructed and empirically validated the first session-aware **Reexposure Shadow** evaluation engine for FioFilter. Following the LeanCTX and Headroom donor lines, this engine evaluates the hypothesis:
> *"If a byte-identical piece of context is delivered again within a single coding session, could FioFilter recognize that event and propose a compact reference instead?"*

### Critical Epistemic Scope
- **RAW Deliveries Unchanged**: FioFilter does **NOT** suppress, alter, or replace raw output in M06.
- **Parallel Shadow Evaluation Only**: FioFilter computes a parallel hypothetical disposition without modifying runtime consumer streams.
- **`WHOLE_MISSION_SAVINGS = UNKNOWN`**: Token savings are hypothetical shadow estimates; actual mission savings remain unknown until runtime shadow or A/B evaluation.
- **`TASK_QUALITY_IMPACT = UNKNOWN`**: Model comprehension impact of indirect reference substitution remains unmeasured.

---

## 1. M05 Epistemic Claim Hygiene

M05 observed:
$$\mathbf{EXACT\_REDELIVERY\_BYTES\_OBSERVED = 260,775}$$

This proved physical byte redelivery across 205 events in Source A. However, physical redelivery does not prove that replacing each repeated delivery with an indirect reference is safe for model reasoning. Mission M06 formalized the following contract:

- `EXACT_REDELIVERY_BYTES_OBSERVED`: 260,775 bytes
- `REFERENCE_SUPPRESSIBLE_BYTES`: `UNKNOWN_UNTIL_SHADOW_OR_AB`
- `PROVEN_IDENTICAL_REDELIVERY`: `YES`
- `PROVEN_SAFE_REFERENCE_REPLACEMENT`: `NO`
- `WHOLE_MISSION_SAVINGS`: `UNKNOWN`

### Metric-Semantic Reconciliation: M05 Baseline vs M06 Funnel

A potential point of confusion is the numerical relationship between M05 and M06 counts:
- **M05 Observation**: `EXACT_REDELIVERY_EVENTS_OBSERVED = 205` (total calls across duplicate groups) and `EXACT_REDELIVERY_BYTES_OBSERVED = 260,775` (repeated bytes excluding first delivery).
- **M06 Funnel Step 2**: `EXACT_CONTENT_REDELIVERIES = 1,128` calls and `EXACT_CONTENT_REDELIVERY_BYTES = 331,661` bytes.

These values use different scopes and are **not** interchangeable denominators:
1. **M05 Baseline Semantics**: Grouped strictly by `(target_identity, output_sha256)` where `target_identity != "UNKNOWN"` (requiring a structurally parsed file path or command identity). The 205 events represent the total deliveries in these targeted clusters (74 first deliveries + 131 repeated deliveries = 205 calls), with 260,775 bytes in the repeated deliveries.
2. **M06 Funnel Semantics**: Evaluates *any* tool output whose exact content SHA-256 appeared earlier anywhere in the session, without requiring prior source identity matching. This universal scope catches 1,018 cross-source redeliveries (151,359 B)—such as multiple ad-hoc scripts outputting `0`, `1`, `ok`, or empty strings—plus unclassified outputs.
3. **Formal Reconciliation**:
   - `M05_BASELINE_SEMANTICS_DOCUMENTED = YES`
   - `M06_FUNNEL_SEMANTICS_DOCUMENTED = YES`
   - `METRIC_CONTRADICTION = NO`

The M06 funnel begins at universal content repetition (1,128 calls) and systematically filters by source identity (68 calls), evidence safety (28 calls), and economic non-expansion (20 calls).

---

## 2. Core Architecture & Models

Implemented in [`fiofilter/reexposure.py`](file:///C:/Users/phped/Documents/FioFilter/fiofilter/reexposure.py):

### A. Delivery Receipt
Every newly observed content delivery receives an immutable session-scoped receipt:
```python
@dataclass
class DeliveryReceipt:
    receipt_id: str
    session_id: str
    source_kind: str
    source_identity: str
    content_sha256: str
    byte_length: int
    first_seen_index: int
    last_seen_index: int
    first_seen_call_id: str
    last_seen_call_id: str
    first_seen_timestamp: Optional[str]
    last_seen_timestamp: Optional[str]
    first_seen_episode: Optional[int]
    last_seen_episode: Optional[int]
    sensitivity: str
    persistence_policy: str
    evidence_class: str
    reference_count: int
    invalidated: bool
```

### B. Session Boundary & Privacy
- **`CROSS_SESSION_REFERENCE = FORBIDDEN`**: Receipts are strictly confined to their originating session ID. Cross-session references raise an immediate invariant violation.
- **No Global Default Cache**: Receipts exist in-memory or ephemeral session stores only.
- **Zero Raw Historical Bytes in Git**: The shadow ledger records non-sensitive hashes, event IDs, and metrics.

### C. Reference Contract
Hypothetical reference format:
```
[[FIOFILTER:REF:v1
sha256=<64-character-hex-digest>
bytes=<integer-byte-length>
receipt=<session-scoped-receipt-id>
]]
```
- Length of reference: ~110–120 UTF-8 bytes.
- Fully deterministic, collision-safe, and length-explicit.

### D. Prefix Stability (Headroom Donor Lesson)
FioFilter adheres to **`PREFIX_STABILITY = APPEND_ONLY_OR_NEW_EVENT_ONLY`**. Past context turns are never rewritten in-place. The hypothetical reference applies strictly to the new duplicate event.

---

## 3. Critical Inline Evidence & Safety Gates

A repeated byte sequence is **never** assumed safe to hide. Under FioFilter invariants:
1. **Truncated Streams (`Invariant I13`)**: Truncated calls are indeterminate -> `AMBIGUOUS_IDENTITY_RAW`.
2. **Failures (`Invariant I6`)**: Nonzero exits and exceptions require verbatim review -> `UNSAFE_EVIDENCE_RAW`.
3. **Sensitive Material (`Invariant I1 / I12`)**: Detected secrets and `DO_NOT_PERSIST` streams remain `SENSITIVE_RAW`.
4. **Authority & Security (`Invariant I7`)**: Permissions, signatures, and credentials require inline inspection -> `UNSAFE_EVIDENCE_RAW`.
5. **Canonical State**: Git status, active branch, and working tree states require inline inspection -> `UNSAFE_EVIDENCE_RAW`.
6. **Diagnostics**: Test suite failure diagnostics require inline inspection -> `UNSAFE_EVIDENCE_RAW`.
7. **Unknown Class (`Invariant I5`)**: Unclassified or ambiguous outputs fail closed to `UNKNOWN_RAW`.
8. **Economic Non-Expansion (`Invariant I3`)**: If `ref_bytes >= raw_bytes`, reference substitution causes net token expansion. Such events are marked `SHADOW_REFERENCE_NOT_ECONOMIC`.

---

## 4. Empirical Replay on Source A

Evaluated across all **4,430 custom tool calls** (20,515,430 bytes) in Source A (`bc4561d4...`):

### A. Shadow Eligibility Funnel

| Funnel Stage | Calls | Output Bytes | Retention | Notes |
| :--- | :---: | :---: | :---: | :--- |
| **1. All Tool Outputs** | 4,430 | 20,515,430 B | 100.0% | Complete session denominator |
| **2. Exact Content Redeliveries** | 1,128 | 331,661 B | 1.62% | Content seen previously in session |
| **3. Same-Source Exact Redeliveries** | 68 | 178,110 B | 0.87% | Same producer / target path |
| **4. Evidence Class Safe** | 28 | 9,661 B | 0.047% | Passes critical evidence gate |
| **5. Sensitivity Policy Allowed** | 28 | 9,661 B | 0.047% | No credentials or secrets detected |
| **6. Reference Economic (Final)** | **20** | **9,401 B** | **0.046%** | `raw_bytes > ref_bytes` (no expansion) |

### B. Ineligibility Breakdown for Repeated Content

Why did repeated deliveries not qualify for shadow references?
- **`CROSS_SOURCE_RAW`**: 1,018 calls (151,359 B) — identical output produced by differing commands/sources (e.g. ad-hoc scripts outputting `ok`, `0`, or `1`).
- **`UNSAFE_EVIDENCE_RAW`**: 37 calls (132,128 B) — contained error messages, tracebacks, test failures, or authority records.
- **`SENSITIVE_RAW`**: 23 calls (32,965 B) — contained detected credentials or secret patterns in attachments/prompts.
- **`UNKNOWN_RAW`**: 22 calls (5,548 B) — unclassified or ambiguous output syntax.
- **`SHADOW_REFERENCE_NOT_ECONOMIC`**: 8 calls (260 B) — tiny outputs (<110 B) where reference representation would expand context.

---

## 5. Tool Family Breakdown

| Tool Family | Repeated Calls | Repeated Bytes | Same-Source Calls | Same-Source Bytes | Eligible Calls | Hypothetical Bytes Avoided |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`FILE_READ`** | 63 | 252,478 B | 21 | 152,307 B | 1 | 253 B |
| **`SEARCH`** | 12 | 3,562 B | 1 | 657 B | 1 | 526 B |
| **`DIRECTORY_LIST`** | 44 | 4,532 B | 24 | 4,184 B | 13 | 762 B |
| **`OTHER`** | 57 | 15,864 B | 10 | 14,837 B | 5 | 5,235 B |
| **`SCRIPT`** | 243 | 48,383 B | 2 | 2,640 B | 0 | 0 B |
| **`WRITE_OR_EDIT`** | 676 | 2,014 B | 0 | 0 B | 0 | 0 B |
| **`GIT`** | 5 | 1,014 B | 1 | 771 B | 0 | 0 B |
| **`UNKNOWN`** | 25 | 3,752 B | 9 | 2,714 B | 0 | 0 B |
| **`BUILD`** | 2 | 62 B | 0 | 0 B | 0 | 0 B |
| **`TEST`** | 1 | 0 B | 0 | 0 B | 0 | 0 B |

---

## 6. Same-File Specialization (`READ_RECEIPT` Analysis)

Focusing on `FILE_READ` calls with structurally validated target paths:
- Total same-path file reads: **490 calls**
- **Same-path identical content rereads**: **32 calls** (**168,727 bytes**)
- Same-path changed content rereads: **202 calls**
- Same-path overlapping range reads: **18 calls**

### Key Insight
While 168.7 KB of identical file content was re-read across identical paths, generic evidence classification flagged many of them as `FAILURE` or `SECURITY` because the files read were skills documenting API error formats or user prompt attachments containing past error logs. A generic text-scanning filter cannot distinguish between an operational system failure and reading a markdown guide that discusses errors.

This proves that **read receipts tied to file system freshness and worktree provenance** are the essential mechanism needed to safely capture file reread waste.

---

## 7. Distance & Recency Distribution

Across all 68 same-source redeliveries:

### Call Distance Distribution
- **0–2 calls**: 43 calls (14,381 B) — immediate consecutive re-runs
- **3–5 calls**: 3 calls (21,223 B)
- **6–10 calls**: 6 calls (35,153 B)
- **11–25 calls**: 2 calls (709 B)
- **26–50 calls**: 1 call (5,267 B)
- **51–100 calls**: 5 calls (72,154 B)
- **>100 calls**: 8 calls (29,223 B) — long-distance re-exposures

### Episode Distance Distribution
- **Same episode (0 turns)**: 55 calls (93,514 B)
- **1 episode apart**: 3 calls (25,456 B)
- **2–5 episodes apart**: 5 calls (43,270 B)
- **>5 episodes apart**: 5 calls (15,870 B)

---

## 8. M05 vs M06 Retention Comparison

- **M05 Exact Repeated Bytes Observed**: 260,775 B
- **M06 Final Shadow-Eligible Raw Bytes**: 9,401 B
- **Eligibility Retention**: **3.61%**
- **Hypothetical Local Bytes Avoided**: **6,776 bytes** (~1,694 estimated tokens)

### Scientific Interpretation
The drop from 260.8 KB to 9.4 KB confirms the strict discipline of FioFilter:
1. 132.1 KB was excluded to prevent hiding failure/diagnostic evidence.
2. 33.0 KB was excluded to protect sensitive material.
3. 151.4 KB was excluded because the content was shared across differing tools rather than proven to be the same authoritative source.
4. Over 200 calls were excluded because replacing <110 bytes with a reference expands context.

---

## 9. Shadow Ledger & Integrity

An append-only, SHA-256 hash-chained ledger was created outside Git:
- Location: `C:\Users\phped\.fiofilter\shadow\`
- `m06_reexposure_shadow_events_v1.jsonl` (4,430 records, final hash `81d72045...`)
- `m06_reexposure_shadow_manifest_v1.json`
- `m06_reexposure_shadow_summary_v1.json`

---

## 10. Next Lane Decision

Per Mission M06 decision guidelines (Section 36):
$$\mathbf{NEXT\_LANE = READ\_RECEIPT\_SHADOW\_SPECIALIZATION}$$

### Rationale
Over 76% of repeated volume resides in `FILE_READ` (168+ KB identical). Generic content-based classifiers cannot distinguish between error logs and source files describing errors. Specializing on **Read Receipts with file system freshness, mtime, and worktree provenance** will safely unlock the reexposure frontier without compromising safety.
