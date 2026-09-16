# M04-R1 Real Historical Replay Report

## Mission Boundary

This document records the empirical replay validation of the production transform
`T02_RG_STANDARD_GROUP_V1` conducted under `MISSION_ID=FIOFILTER-M04-R1-REAL-HISTORICAL-REPLAY`.

M03-R4 proved the grammar `RG_STANDARD_PATH_LINE_TEXT`.
M04 implemented the production transform `T02_RG_STANDARD_GROUP_V1`.
M04-R1 proved that the actual production transform works on every real historical clean
candidate that authorized it.

In accordance with project doctrine:
- No new transforms implemented.
- No grammar support broadened.
- T02 is not auto-activated in the generic engine (`ENGINE_METADATA_GATE_REMAINS = YES`).
- 0 raw historical bytes or credentials committed.
- Token metrics strictly reported under `utf8_bytes_div_4_ESTIMATE`.
- Whole-mission savings NOT claimed (`WHOLE_MISSION_SAVINGS = UNKNOWN`).

---

## 1. Real Corpus Identity

- **Corpus Path**: `C:\Users\phped\.fiofilter\corpus\m03_rg_clean_candidates_v1.jsonl`
- **Corpus SHA-256**: `c711a07f75f734bdbaacda35b42fa45e0075bb1c5a49f4b9c5eb7f6e396c768c`
- **Total Candidates Replayed**: **23** (100% of admitted real clean candidates)
- **Authorized Grammar**: `RG_STANDARD_PATH_LINE_TEXT` (all 23 entries belong to this grammar)

---

## 2. Production Transform Replay & Dispositions

All 23 candidates were evaluated using the production implementation
`RgStandardLosslessGrouping.evaluate()` with structured caller-supplied evidence:

| Disposition | Count | Percentage | Description |
|---|---|---|---|
| `TRANSFORMED` | **16** | 69.57% | Grouping applied, positive byte savings, verified roundtrip |
| `RAW_NO_ECONOMIC_GAIN` | **7** | 30.43% | Valid grammar, but candidate size $\ge$ raw size; safely preserved as RAW |
| `RAW_SAFETY_OR_GRAMMAR_REJECTION` | **0** | 0.0% | Zero safety, parser, or grammar rejections on admitted clean corpus |
| **Total** | **23** | **100.0%** | |

---

## 3. Byte-Exact Roundtrip Proof

For every candidate where T02 activated:
$$\text{decode\_visible}(\text{transformed}) \equiv \text{raw}$$

- Transformed entries replayed: 16
- Roundtrip passes: **16 / 16 (100.0%)**
- `TRANSFORMED_ROUNDTRIP_FAILURES`: **0**

---

## 4. Fact Retention & Structural Invariants

Comparing the parsed AST of original raw bytes against the decoded output across all
transformed entries confirmed:

- `MATCH_DROPPING`: **0**
- `FILE_DROPPING`: **0**
- `ORDER_CHANGE`: **0**
- `MULTIPLICITY_CHANGE`: **0**
- `PAYLOAD_CHANGE`: **0**
- `PATH_CHANGE`: **0**
- `LINE_NUMBER_CHANGE`: **0**

Every line number, file path, match payload, and separator is preserved exactly inline.

---

## 5. Negative Controls & Headroom Adversarial Replay

- **Real Negative Controls Replayed**: 34 entries from `m03_rg_negative_controls_v1.jsonl`
  across 8 failure categories.
  - `REAL_NEGATIVE_FALSE_TRANSFORMS`: **0**
- **Headroom Adversarial Challenges Replayed**: 18 synthetic cases (Windows drive paths,
  UNC paths, hyphens, dated directories, CVE paths, digit-separated paths, colon in payload,
  context separators, column-like output, binary notices, color codes, marker collisions).
  - `AMBIGUOUS_CASES_TRANSFORMED`: **0**

---

## 6. Real Production Economics

Across all 23 real clean candidates:

- `TOTAL_RAW_BYTES`: **62,373 bytes**
- `TOTAL_VISIBLE_BYTES`: **51,577 bytes**
- `TOTAL_BYTES_SAVED`: **10,796 bytes**
- `LOCAL_BYTE_REDUCTION_PERCENT`: **17.31%**
- `TRANSFORMED_COUNT`: **16**
- `RAW_NO_ECONOMIC_GAIN_COUNT`: **7**
- `RAW_SAFETY_REJECTION_COUNT`: **0**

### Transformed Reduction Distribution

- Minimum reduction: **0.60%** (saving 2 B on a 332 B output)
- Median reduction: **17.98%**
- P90 reduction: **30.72%**
- Maximum reduction: **30.83%** (saving 1,704 B on a 5,527 B output; saving 2,887 B on a 9,399 B output)

### Estimated Token Economics (`utf8_bytes_div_4_ESTIMATE`)

- Estimated raw tokens: **15,594**
- Estimated visible tokens: **12,895**
- Estimated tokens saved: **2,699**

---

## 7. M03 Simulation vs M04 Production Comparison

| Metric | M03 Simulation | M04 Production | Delta |
|---|---|---|---|
| Visible Bytes | 45,021 B | 51,577 B | +6,556 B |
| Bytes Saved | 17,352 B | 10,796 B | -6,556 B |
| Reduction % | 27.82% | 17.31% | -10.51% |
| Transformed Entries | 20 | 16 | -4 |
| RAW (No Economic Gain) | 3 | 7 | +4 |

### Quantitative Analysis of Overhead

- `SIMULATION_TO_PRODUCTION_OVERHEAD_BYTES`: **6,556 bytes**
- `SIMULATION_TO_PRODUCTION_OVERHEAD_PERCENT`: **10.51%** of total raw bytes

The overhead reflects intentional, safety-critical design decisions:
1. **Representation Header**: `[[FIOFILTER:T02_RG_STANDARD_GROUP:v1]]\n` (39 bytes per transformed payload).
2. **Explicit Path-Length Framing**: `[[FIOFILTER:T02_RG_STANDARD_GROUP:v1 path_bytes=LENGTH]]\n` (~49-55 bytes per path run). Unlike the simulation's naive `path\n`, explicit length framing completely eliminates path parsing ambiguity (e.g. Windows drive colons, spaces, and colons in directory names).
3. **No-Expansion Enforcement (Invariant I4)**: Because of the robust framing overhead, 4 borderline cases where simulation showed marginal savings (36B, 100B, 287B, 335B with high unique-file-to-match ratios) resulted in `candidate >= raw`. T02 safely fell back to RAW rather than causing expansion.

---

## 8. Engine Metadata Gate Status

- `ENGINE_METADATA_GATE_REMAINS = YES`
- Generic `apply(content)` intentionally returns `None`.
- Automatic engine auto-routing and profile whitelisting remain deferred until caller-supplied
  structural producer evidence can be securely propagated at runtime.

---

## 9. Decision

**`M04_TRANSFORM_REAL_REPLAY_VALIDATED = YES`**

All 10 validation conditions passed:
1. 23 / 23 real candidates replayed.
2. 0 roundtrip failures on transformed outputs.
3. 0 false transforms on real negative controls.
4. 0 ambiguous/adversarial cases transformed.
5. 0 matches dropped, 0 files dropped, 0 order changes, 0 multiplicity changes.
6. Positive local byte reduction (17.31% net savings, 10,796 B).
7. 0 raw historical bytes committed to Git.
8. Full test suite passing (295 / 295 tests).
9. Codebase clean and unbloated.
10. Engine metadata gate preserved without premature integration.
