# M07 Read Receipt Shadow Specialization Report

## 1. Executive Summary

Mission **M07** specializes the session-aware reexposure lane specifically for file reads (`FILE_READ`), resolving the architectural tension discovered in M06 where generic error-word classifiers flagged benign documentation as failures.

M07 introduces an explicit architectural decoupling:
- **Plane A — Source Freshness / Byte Identity**: "Are these the exact same requested file/view bytes as previously delivered in this session?" (Deterministically proven via SHA-256 and byte equality).
- **Plane B — Context Policy Authority**: "Even if unchanged, is replacing them with a compact reference behaviorally safe and authorized?" (Kept strictly closed in M07).

Key conclusions from M07:
1. `FRESHNESS_PROVEN` does not imply `ACTIVE_SUPPRESSION_AUTHORIZED`.
2. `MTIME_UNCHANGED` does not imply `CONTENT_UNCHANGED`. Mtime and file size are fast rejection hints; SHA-256 and byte equality are the sole authority for content invariance.
3. In controlled live experimentation, an attacker modifying file content and manually restoring mtime is deterministically caught (`MTIME_SPOOF_DOES_NOT_BYPASS_HASH = PASS`). Level F4 requires exact byte equality.
4. Across 490 historical `FILE_READ` calls in Source A (`206,427,325 B`, SHA-256 `bc4561d4...`):
   - **489 events (99.8%)** have structured source identity.
   - **459 events (93.7%)** have structured view identity.
   - **31 events** achieved `F1_HISTORICAL_OUTPUT_IDENTITY` (184,684 B).
   - **17 events** are economically viable shadow candidates (`HISTORICAL_IDENTICAL_READ_CANDIDATE`), representing **184,194 B raw**, **2,432 B reference**, and **181,762 B avoided** (**98.68% hypothetical reduction** on repeated reads).
   - **14 events** are 35-byte polling log tails that were correctly rejected by the no-expansion invariant (`REFERENCE_NOT_ECONOMIC_RAW`).
5. `ACTIVE_READ_REFERENCE_SUPPRESSION = NO`. No runtime hooks, proxies, daemons, or engine modifications were deployed.
6. Selected `NEXT_LANE = READ_RECEIPT_RUNTIME_SHADOW_HARNESS`.

---

## 2. Metric-Semantic Reconciliation: M05 Census vs M06 Funnel vs M07

| Metric Dimension | M05 Context Census | M06 Reexposure Funnel | M07 Read Receipt Shadow |
| :--- | :--- | :--- | :--- |
| **Analyzed Unit** | Duplicate delivery clusters with target path/cmd | Universal content-hash matches across all 4,430 calls | Structured FILE_READ events with target path |
| **Evaluated Calls** | 4,430 calls | 4,430 calls | 490 calls |
| **Initial Repeat Count** | 205 events (74 first + 131 repeat) | 1,128 content-repeat calls | 31 F1 repeated read deliveries |
| **Initial Repeat Volume** | 260,775 B repeated | 331,661 B content-repeated | 184,684 B repeated |
| **Same-Source Count** | N/A (grouped by target) | 68 same-source calls | 31 same-source same-view deliveries |
| **Same-Source Volume** | N/A | 178,110 B | 184,684 B |
| **Viable Candidates** | 205 events (census hypothesis) | 20 shadow candidates (generic) | 17 economic read candidates (specialized) |
| **Viable Raw Bytes** | 260,775 B | 9,401 B | 184,194 B |
| **Avoided Bytes** | 260,775 B (gross estimate) | 6,776 B (after reference cost) | 181,762 B (after reference cost) |

### Explanation of Reconciliation:
- **M05 vs M06**: M05 required `target_identity != "UNKNOWN"` and measured targeted clusters (260.8 KB). M06 measured universal content recurrence across differing commands (331.7 KB) before filtering down to 20 same-source candidates (6.8 KB avoided) due to conservative text classification of errors and sensitive tokens.
- **M06 vs M07**: In M06, same-path rereads were counted by checking consecutive calls with identical path strings (yielding 32 events and 168,727 B). In M07, session-scoped tracking evaluates exact view expressions:
  - 17 events are large repeated whole-file reads (skills, attachments, config references) totaling 184,194 B where hypothetical reference replacement saves 181,762 B.
  - 14 events are 35-byte polling loop log tails (`campaign.stdout.log -Tail 40`) where hypothetical reference formatting (143 B) would expand output; these were correctly rejected under the no-expansion invariant.

### 2.1 Denominator Hygiene: M05 Broad Family vs M07 Specialized Read Subset
- **M05 Broad `FILE_READ` Family (1,090 calls)**: In `context_census.py`, any command matching `\b(Get-Content|cat|head|tail|type|more|less)\b` was assigned `tool_family = "FILE_READ"`. This broad regex matched 1,090 calls in Source A.
- **M07 Evaluated Read Subset (490 calls)**: M07 operates strictly on the subset where file-read source and view analysis is applicable:
  $$\text{M07\_READ\_DENOMINATOR\_DEFINITION} = \text{Session tool calls where } \texttt{tool\_family == 'FILE\_READ'} \text{ and } \texttt{target\_path is not None}$$
  Exactly 490 calls possess an identifiable target path extracted via `-Path`, `-LiteralPath`, or quoted filename with extension. The remaining 600 calls (such as `git rev-parse HEAD` matching case-insensitive `\bhead\b` without a target path) have `target_path == None` and were excluded from file read receipt specialization.
- **Epistemic Verification**:
  - `M07_READ_DENOMINATOR_DEFINITION`: Structured file-read subset (`tool_family == 'FILE_READ'` with non-None `target_path`).
  - `METRIC_CONTRADICTION`: **NO**.

---

## 3. Architectural Plane Separation

M06 revealed that using generic text classification on file bodies creates severe false negatives: technical documentation, architecture documents, and security diff scripts frequently contain words like `"error"`, `"token"`, `"failure"`, or `"security"`. Gating freshness on the absence of those words resulted in rejecting perfectly valid, unchanged file rereads.

M07 resolves this by strictly decoupling:
1. **Plane A — Source Freshness / Byte Identity**:
   - Focus: Has the file or view changed since receipt creation?
   - Invariant: Exact byte comparison (F4) provides deterministic mathematical proof.
   - Gating: Free from word-based error heuristics.
2. **Plane B — Context Policy Authority**:
   - Focus: Is replacing delivered file bytes with a compact reference behaviorally safe for the coding agent?
   - Invariant: Model reasoning may depend on in-context token presence (salience and recency).
   - Gating: Plane B remains closed (`plane_b_active_authorized = False`). `BEHAVIORAL_EQUIVALENCE = UNKNOWN`.

```
+-------------------------------------------------------------+
|               FILE_READ Operation Event                     |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|             PLANE A: SOURCE FRESHNESS PROOF                 |
|  - Source Identity Normalization (Windows / POSIX)          |
|  - Read View Extraction (FULL_FILE, LINE_RANGE, etc.)       |
|  - Metadata Hint Evaluation (F2: mtime / size)              |
|  - SHA-256 Hash Verification (F3)                           |
|  - Exact Byte Equality Verification (F4)                    |
+-------------------------------------------------------------+
                               |
                   [FRESHNESS_PROVEN = YES]
                               |
                               v
+-------------------------------------------------------------+
|             PLANE B: CONTEXT POLICY AUTHORITY               |
|  - Salience & Recency Assessment                            |
|  - Sensitivity / Persistence Policy Screening               |
|  - Reference Expansion Gating (ref_bytes < raw_bytes)       |
|  - Behavioral Invariance Gate                               |
|                                                             |
|      STATUS IN M07: ACTIVE SUPPRESSION UNAUTHORIZED         |
|      (Records shadow decision without runtime alteration)   |
+-------------------------------------------------------------+
```

---

## 4. Read Receipt and View Models

### 4.1 ReadReceipt Data Model
```python
@dataclass
class ReadReceipt:
    receipt_id: str
    session_id: str
    original_path: str
    resolved_path_identity: Optional[str]
    read_mode: str
    requested_view: ReadView
    delivered_sha256: str
    delivered_bytes: int
    file_size: Optional[int]
    mtime_ns_hint: Optional[int]
    repo_root_if_known: Optional[str]
    git_head_if_known: Optional[str]
    worktree_state_if_known: Optional[str]
    first_seen_call: int
    last_seen_call: int
    first_seen_episode: Optional[int]
    last_seen_episode: Optional[int]
    sensitivity: str = "NOT_SENSITIVE"
    persistence_policy: str = "EPHEMERAL"
    reference_count: int = 0
```

### 4.2 ReadView and View Compatibility
Reading lines 1–100 is not identical to reading the whole file or lines 50–150. M07 enforces explicit view typing:
- `FULL_FILE`: Verbatim full content.
- `LINE_RANGE`: Explicit 1-indexed start/end or tail line count.
- `BYTE_RANGE`: Explicit byte offsets.
- `OTHER_STRUCTURED_VIEW`: Multi-command or composite expressions.
- `UNKNOWN_VIEW`: Unverified syntax.

Two views are compatible if and only if their `view_type` and boundary parameters match exactly.

### 4.3 Freshness Proof Hierarchy
- **`F0_UNKNOWN`**: No freshness proof established.
- **`F1_HISTORICAL_OUTPUT_IDENTITY`**: Historical session replay proves identical output bytes delivered for the same source and view.
- **`F2_METADATA_CONSISTENT`**: Disk file size and mtime match receipt hints. Fast reject hint only; never sole authority.
- **`F3_CURRENT_VIEW_HASH_EQUAL`**: SHA-256 hash of current requested view matches receipt.
- **`F4_CURRENT_VIEW_BYTE_EQUAL`**: Exact byte equality verified between current disk view and receipt.

---

## 5. Mtime Policy and Mtime Spoof Defense

### 5.1 The Fundamental Rule
$$\text{MTIME\_UNCHANGED} \ne \text{CONTENT\_UNCHANGED}$$

File modification time (`mtime`) is vulnerable to:
1. Manual timestamp restoration (`os.utime`, `touch -r`).
2. Coarse filesystem clock granularity on legacy filesystems.
3. Concurrent processes modifying and restoring files.

Therefore:
- Mtime is strictly a **fast rejection hint** (`CHANGE_HINT`).
- If mtime differs, the file likely changed.
- If mtime matches, **content verification is still mandatory**.

### 5.2 Mandatory Adversarial Test Result
In `tests/test_read_receipt.py::TestControlledLiveReadLab::test_sequence_c_mtime_spoof_defense`:
- A synthetic file was read, creating `rcpt-0001`.
- The file content was tampered with, and its original `mtime` was manually restored via `os.utime`.
- The evaluator re-evaluated the file: despite identical `mtime`, SHA-256 hash calculation caught the alteration.
- Result:
  $$\text{MTIME\_SPOOF\_DOES\_NOT\_BYPASS\_HASH} = \mathbf{PASS}$$
  The event was correctly rejected with `SOURCE_CHANGED_RAW`.

---

## 6. Git and Worktree Provenance Policy

Git metadata is supplemental context:
- `git rev-parse HEAD` equality does **not** prove a file is unchanged because the local worktree may be dirty.
- A dirty worktree does **not** prove that this specific file was modified.
- Changing branches to an equivalent commit or merging an unrelated branch does **not** invalidate an untouched file.
- Authority remains: **exact requested bytes (Level F4)**.

---

## 7. Context Saving vs Disk I/O Saving

FioFilter's primary optimization target is **model context cost**, not disk I/O:
$$\text{CONTEXT\_SAVING} \ne \text{I/O\_SAVING}$$

During live evaluation:
- The evaluator reads the file from disk to calculate SHA-256 and verify byte equality (`LOCAL_IO_BYTES_READ`).
- Disk I/O is performed locally and cheaply.
- Model context tokens are spared by substituting the bulky file body with a compact receipt reference (`HYPOTHETICAL_MODEL_VISIBLE_REFERENCE_BYTES`).
- Local disk reading to guarantee zero hallucination and zero evidence loss is an intentional, sound engineering trade-off.

---

## 8. Historical Replay Results on Source A

Replaying all 490 `FILE_READ` events from Source A (`01a02f96`) produced the following breakdown:

### 8.1 Dispositions
| Disposition | Count | Percentage | Description |
| :--- | :---: | :---: | :--- |
| `FIRST_READ_RAW` | 410 | 83.7% | Initial delivery of a file / view in the session |
| `VIEW_IDENTITY_UNKNOWN_RAW` | 30 | 6.1% | Ambiguous or non-deterministic view syntax |
| `HISTORICAL_IDENTICAL_READ_CANDIDATE` | 17 | 3.5% | Proven identical reread with positive byte savings |
| `SOURCE_CHANGED_RAW` | 14 | 2.9% | Content modified between consecutive reads |
| `REFERENCE_NOT_ECONOMIC_RAW` | 14 | 2.9% | 35 B log tails where reference would expand output |
| `SOURCE_IDENTITY_UNKNOWN_RAW` | 5 | 1.0% | Wildcards or unresolved path tokens |
| **Total** | **490** | **100.0%** | |

### 8.2 Economics of Economic Candidates
- **Total Candidates**: 17 calls
- **Raw Repeated Bytes**: 184,194 B (~46,048 estimated tokens)
- **Hypothetical Reference Bytes**: 2,432 B (~608 estimated tokens)
- **Avoided Model-Visible Bytes**: **181,762 B** (~45,440 estimated tokens)
- **Net Context Reduction on Repeated Reads**: **98.68%**
- **Distance Profile**: 76.5% of rereads occurred at distances > 100 calls, indicating long-session skill and reference re-inspection.

---

## 9. Next-Lane Selection

Guidance provided in the mission:
- If real workload coverage is high and controlled F4 proof works: `READ_RECEIPT_RUNTIME_SHADOW_HARNESS`.
- If read grammar/view coverage is weak: `READ_RECEIPT_VIEW_PARSER_EXPANSION`.
- If architecture proves unsafe or economically trivial: `REEXPOSURE_LANE_DEFER`.

### Selection:
$$\mathbf{NEXT\_LANE = READ\_RECEIPT\_RUNTIME\_SHADOW\_HARNESS}$$

### Justification:
- Source and view parsing coverage is outstanding: **99.8% structured source identity** and **93.7% structured view identity**.
- Controlled live read lab proved that F4 byte equality and mtime-spoof defense are mathematically robust.
- The economic potential is concentrated and significant: 181.8 KB avoided across 17 large repeated reads.
- The next step is to build an active runtime shadow harness that can monitor real live coding sessions without modifying runtime delivery, paving the way for behavioral A/B testing.
