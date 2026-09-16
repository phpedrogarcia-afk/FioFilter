# M05 Context Waste Census Report

## Mission Boundary

This document records the empirical Context Waste Census of the user's real historical
Codex workload conducted under `MISSION_ID=FIOFILTER-M04-FINALIZE-AND-M05-CONTEXT-WASTE-CENSUS`.

Core Operating Doctrine:
- **No new optimization without a waste baseline.**
- Donor lessons (Headroom, LeanCTX, Aider/AgentMap) are evaluated as empirical measurements, not pre-assumed solutions.
- Measurements distinguish strict evidence tiers: `PROVEN_AVOIDABLE`, `STRONG_DETERMINISTIC_OPPORTUNITY`, `OBSERVED_COST`, `HYPOTHESIS_ONLY`, `UNKNOWN`.
- 0 raw historical bytes, prompts, or credentials are committed.
- All token metrics are strictly reported under `utf8_bytes_div_4_ESTIMATE`.
- Whole-mission savings are NOT claimed (`WHOLE_MISSION_SAVINGS = UNKNOWN`).

---

## 1. Source Artifact Verification

| Field | Measured Value |
|---|---|
| Local Path | `C:\Users\phped\.codex\sessions\2026\08\23\rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl` |
| SHA-256 | `bc4561d4588a73a6889ca38d8c180ae467e51eea5f023aaba7a222425cf350a0` |
| Size | `206,427,325` bytes |
| Total JSONL Records | `35,040` |
| Custom Tool Calls | `4,430` |
| Custom Tool Outputs | `4,430` |
| User Messages (Episode Anchors) | `218` |

---

## 2. Whole-Workload Denominator & Classification Coverage

| Metric | Count / Value |
|---|---|
| Total Tool Calls | `4,430` |
| Parseable Calls | `4,111` |
| Unclassified Calls | `319` |
| **Classification Coverage** | **92.8%** |
| Total Tool Output Bytes Observed | **20,515,430 bytes** (~20.5 MB) |
| Estimated Tool Output Tokens (`utf8_bytes_div_4_ESTIMATE`) | **5,128,858 tokens** |

---

## 3. Tool Family Distribution

| Tool Family | Calls | Share of Calls | Total Bytes | Share of Bytes | Median Bytes | P90 Bytes | Max Bytes |
|---|---|---|---|---|---|---|---|
| **`FILE_READ`** | 1,090 | 24.6% | **8,782,048** | **42.81%** | 3,706 | 23,345 | 40,110 |
| **`SCRIPT`** | 991 | 22.4% | **5,584,544** | **27.22%** | 313 | 21,308 | 40,110 |
| **`SEARCH`** | 283 | 6.4% | **1,944,240** | **9.48%** | 2,983 | 19,282 | 40,110 |
| **`TEST`** | 232 | 5.2% | **1,886,450** | **9.20%** | 1,969 | 35,052 | 40,110 |
| **`UNKNOWN`** | 319 | 7.2% | **718,182** | **3.50%** | 378 | 5,387 | 40,109 |
| **`GIT`** | 306 | 6.9% | **604,473** | **2.95%** | 403 | 3,154 | 40,109 |
| **`OTHER`** | 189 | 4.3% | **413,642** | **2.02%** | 266 | 4,804 | 40,107 |
| **`DIRECTORY_LIST`** | 208 | 4.7% | **291,355** | **1.42%** | 209 | 2,640 | 40,109 |
| **`WRITE_OR_EDIT`** | 787 | 17.8% | **271,198** | **1.32%** | 2 | 287 | 40,107 |
| **`BUILD`** | 25 | 0.6% | **19,298** | **0.09%** | 285 | 2,252 | 3,587 |
| **Total** | **4,430** | **100.0%** | **20,515,430** | **100.0%** | — | — | — |

**Key Finding**: `FILE_READ` is the single largest consumer of context in the workload, accounting for **42.81% of all tool output bytes** (8.78 MB), followed by ad-hoc execution scripts (27.22%). Search represents 9.48% and test execution represents 9.20%.

---

## 4. Reexposure Waste — LeanCTX Donor Lane

Evidence Tier: **`PROVEN_AVOIDABLE`** (Exact Redeliveries) / **`STRONG_DETERMINISTIC_OPPORTUNITY`** (Unchanged Rereads & Ranges)

### Tier R1 — Exact Redelivery
- Exact redelivery events: **205**
- Gross bytes in repeated deliveries: **447,645 bytes**
- Unique content bytes (first delivery retained): **186,870 bytes**
- **`EXACT_REDELIVERY_BYTES_OBSERVED`**: **260,775 bytes** (~65,194 estimated tokens)
- `PROVEN_IDENTICAL_REDELIVERY`: **YES** (Identical byte stream redelivered across 205 events)
- `PROVEN_SAFE_REFERENCE_REPLACEMENT`: **NO** (Behavioral equivalence of replacing deliveries with references is unproven)
- `REFERENCE_SUPPRESSIBLE_BYTES`: **UNKNOWN_UNTIL_SHADOW_OR_AB**
- `WHOLE_MISSION_SAVINGS`: **UNKNOWN**

### Same-Path Rereads
- Same-path read count: **490 calls**
- Identical content rereads: **32 calls** (**168,727 bytes**)
- Changed content rereads (`DELTA_CANDIDATE`): **202 calls**
- Overlapping range events: **19 events** (596 overlapping lines, estimated **125,535 overlap bytes**)

---

## 5. Representation Waste — Headroom Donor Lane

Evidence Tier: **`PROVEN_AVOIDABLE`** (T02 Scope Only)

- Ripgrep search events evaluated: **259**
- T02 Transformable events: **15**
- Total evaluated raw bytes: **1,545,272 bytes**
- T02 Visible bytes: **1,537,363 bytes**
- **`T02_PROVEN_LOCAL_BYTES_AVOIDABLE`**: **7,909 bytes** (~1,978 estimated tokens)
- T02 Local reduction across ripgrep output: **0.51%**

*Note*: While T02 achieves 17.31% reduction on clean standard runs, only 15 ripgrep invocations in this session satisfied all strict single-producer and non-composite evidence gates, confirming that representation transforms on search alone address only a modest fraction of the whole workload context.

---

## 6. Discovery Cost — Aider / AgentMap Lane

Evidence Tier: **`OBSERVED_COST`** (Discovery Total) / **`PROVEN_AVOIDABLE`** (Exact Redundancy)

### Discovery Cost Before First Mutation
- Total episodes identified: **165**
- Total discovery calls before first write: **1,183 calls** (26.7% of all calls)
- **`TOTAL_DISCOVERY_BYTES`**: **10,733,497 bytes** (~2,683,375 estimated tokens, **52.3% of total session bytes**)
- Unique files discovered: **199 files**
- Pre-mutation tool distribution:
  - Search: 111 calls (670,410 bytes)
  - File reads: 326 calls (2,810,637 bytes)
  - Directory lists: 74 calls (103,425 bytes)
  - Scripts/other: 672 calls (7,149,025 bytes)

### Proven Discovery Redundancy
- Duplicate directory listing calls: 1 (0 bytes)
- Duplicate read calls during discovery: 14 (**29,366 bytes**)
- **`PROVEN_DISCOVERY_REDUNDANCY_BYTES`**: **29,366 bytes** (~7,342 estimated tokens)

### Common Action Chains
1. `read -> read -> read` (25 occurrences)
2. `script -> script -> script` (12 occurrences)
3. `read -> script -> script` (9 occurrences)
4. `read -> git -> read` (9 occurrences)
5. `read -> script -> read` (7 occurrences)

---

## 7. Deduplication of Proven Avoidable Bytes (No Double Counting)

To prevent double counting across Reexposure, Representation, and Discovery, unique event IDs were combined under strict precedence:
1. `EXACT_REEXPOSURE`
2. `T02_REPRESENTATION`
3. `DISCOVERY_DUPLICATE`

| Opportunity Class | Raw Category Bytes | Attributed Deduplicated Bytes | Attributed Events |
|---|---|---|---|
| `EXACT_REEXPOSURE` | 260,775 B | 260,775 B | 131 |
| `T02_REPRESENTATION` | 7,909 B | 7,909 B | 15 |
| `DISCOVERY_DUPLICATE` | 29,366 B | 0 B (already captured in Reexposure) | 1 |
| **Total Deduplicated** | **298,050 B** | **268,684 B** | **147** |

- **`DEDUPLICATED_PROVEN_AVOIDABLE_BYTES`**: **268,684 bytes** (~67,171 estimated tokens)
- **Proven Avoidable Workload Ratio**: **1.31%** of all observed tool bytes

---

## 8. Priority Comparison & Next Lane Selection

| Dimension | Class | Measured Value | Description |
|---|---|---|---|
| **Highest Observed Cost** | **`DISCOVERY`** | 10,733,497 B (52.3%) | Over half of all context bytes are consumed exploring before the first edit |
| **Highest Proven Avoidable** | **`REEXPOSURE`** | 260,775 B | Repeated exact delivery of previously observed file/target contents |
| **Highest Strong Opportunity** | **`DISCOVERY`** | 2,810,637 B | File reads during discovery that were never subsequently modified |

### Decision Rule Evaluation
- `PROVEN_REEXPOSURE_BYTES` (260,775 B) exceeds `T02_REPRESENTATION` (7,909 B) by **33x**.
- File reading is 4.5x larger than Search in total bytes (8.78 MB vs 1.94 MB).
- While Discovery Cost is massive (10.7 MB), the vast majority represents unproven supporting reads that may have been necessary.
- Reexposure waste provides immediate, deterministic, byte-exact suppression opportunities.

**Selected Next Lane**:
$$\mathbf{NEXT\_LANE = REEXPOSURE\_SHADOW}$$

---

## 9. Census Output Artifacts

Local laboratory census artifacts are preserved outside Git under `C:\Users\phped\.fiofilter\census\`:
- `m05_context_waste_events_v1.jsonl` (4,430 classified event records)
- `m05_context_waste_manifest_v1.json` (Source fingerprint and verification records)
- `m05_context_waste_summary_v1.json` (Complete aggregate metrics)
