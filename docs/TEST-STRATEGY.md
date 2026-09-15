# FioFilter — Test Strategy

**Principle**: Tests are defined before compression logic is implemented.
**Oracle**: Repository state and test results outrank conversational assumptions.

---

## V0 Quality Gates (Required Before Any Codex Integration)

| Gate | Requirement | Test File |
|---|---|---|
| RAW_RECOVERY_SHA_MATCH | 100% | `test_raw_store.py` |
| INLINE_REQUIRED_CRITICAL_FACT_PRESERVATION | 100% | `test_inline_preservation.py` |
| UNEXPECTED_PROTECTED_TRANSFORMATIONS | 0 | `test_invariants.py` |
| MACHINE_DATA_VALIDITY_FAILURES | 0 | `test_machine_data.py` |
| SECURITY_OR_AUTHORITY_FACT_LOSS | 0 | `test_invariants.py` |
| FAILURE_DIAGNOSTIC_UNSAFE_CASES | 0 | `test_decision_engine.py` |

All gates must pass before integration work begins.

---

## Test Families

### Family 1: RAW Byte-Exact Recovery (`test_raw_store.py`)

**What it tests**: The RAW store's core guarantee — I1 + I3.

```python
# Oracle assertions:
assert sha256(store.read(ref)) == ref.raw_sha256   # byte-exact
assert store.read(ref) == original_bytes            # identity
assert store.write(x) == store.write(x)             # idempotent (dedup)
assert (raw_store_root / "objects").exists()        # correct layout
```

**Test cases**:
- Round-trip: write → read → compare bytes + SHA-256
- Idempotency: writing identical content twice produces same `raw_ref`
- Atomicity: interrupted write does not leave corrupt entry (simulated)
- Large content: content > 64KB stored and recovered correctly
- Unicode content: arbitrary bytes recovered correctly
- Empty content: empty bytes stored and recovered

---

### Family 2: Evidence Classification (`test_classifier.py`)

**What it tests**: The classifier correctly routes evidence to classes, defaults
unknown to RAW (I5).

```python
# Oracle assertions:
assert classify("").evidence_class == EvidenceClass.UNKNOWN
assert classify(unknown_content).evidence_class == EvidenceClass.UNKNOWN
assert classify(low_confidence_content).evidence_class == EvidenceClass.UNKNOWN
assert classify(json_content).evidence_class == EvidenceClass.MACHINE_DATA
```

**Test cases**:
- Empty content → UNKNOWN
- Content with no matching rules → UNKNOWN
- JSON-parseable content → MACHINE_DATA
- Non-zero exit code content → candidate for FAILURE
- Repeated identical lines → NOISE or PROGRESS
- Directory listing patterns → DISCOVERY
- All-PASS test output → SUCCESS_SUMMARY
- Any-FAIL test output → FAILURE
- Git log/status patterns → CANONICAL_STATE
- SHA-256 / hash patterns → CANONICAL_STATE (or AUTHORITY context-dependent)
- Classifier confidence below threshold → UNKNOWN

---

### Family 3: Protected Evidence → RAW (`test_invariants.py`)

**What it tests**: I5, I6, I7 — protected classes always produce RAW disposition.

```python
# Oracle assertions (for all modes: EXPLORE, BUILD, PROVE):
assert engine.process(authority_content, mode=any).disposition == Disposition.RAW
assert engine.process(security_content, mode=any).disposition == Disposition.RAW
assert engine.process(unknown_content, mode=any).disposition == Disposition.RAW
assert engine.process(failure_content, mode=any).disposition == Disposition.RAW
```

**Test cases**:
- AUTHORITY class, EXPLORE mode → RAW
- AUTHORITY class, BUILD mode → RAW
- AUTHORITY class, PROVE mode → RAW
- SECURITY class, any mode → RAW
- UNKNOWN class, any mode → RAW
- FAILURE class, any mode → RAW
- CANONICAL_STATE class, any mode → RAW
- BENCHMARK class, any mode → RAW

---

### Family 4: Unexpected Failure Escalation (`test_mode_escalation.py`)

**What it tests**: I6 — failure escalates regardless of current mode.

**Test cases**:
- EXPLORE mode + non-zero exit code → disposition upgraded to RAW
- BUILD mode + non-zero exit code → RAW
- EXPLORE mode + "Exception" in output → FAILURE class → RAW
- Mode escalation is one-directional within a result (not session-wide in V0)

---

### Family 5: Transform Determinism (`test_transforms.py`)

**What it tests**: Transforms produce identical output for identical input.

```python
# Oracle assertions:
assert transform(x) == transform(x)           # determinism
assert transform(x) == transform(x)           # (second call, no state)
```

**Test cases per transform** (T01 in V0):
- T01: `fold_duplicates(x) == fold_duplicates(x)` for arbitrary content
- T01: `fold_duplicates(x)` with no duplicates == x (identity)
- T01: `fold_duplicates(x)` with duplicates produces fold marker
- T01: fold marker contains correct count

---

### Family 6: Transform Does Not Expand (`test_transforms.py` + `test_economics.py`)

**What it tests**: I9 — transforms that expand output lose to RAW.

```python
# Oracle assertions:
result = engine.process(content_with_no_duplicates)
assert result.disposition == Disposition.RAW  # T01 found nothing to fold
assert len(result.content) == len(raw_content)

result = engine.process(content_with_duplicates)
assert len(result.content) < len(raw_content)
```

**Test cases**:
- Content with no duplicates → T01 returns RAW (no savings)
- Content with duplicates → T01 returns TRANSFORM, len(result) < len(raw)
- Pathological case: T01 fold marker longer than saved content → RAW

---

### Family 7: Machine Data Validity (`test_machine_data.py`)

**What it tests**: I8 — MACHINE_DATA transforms preserve machine validity.

```python
# Oracle assertions (future T04):
parsed_raw = json.loads(raw_content)
parsed_transformed = json.loads(result.content)
assert parsed_raw == parsed_transformed
```

**Test cases** (stub in V0; full in M02 when T04 is implemented):
- Valid JSON + T04 → result parses as JSON with equal structure
- Invalid JSON → disposition is RAW (not transformed)
- JSON with whitespace → T04 reduces bytes, result still parses

---

### Family 8: Critical-Fact Inline Preservation (`test_inline_preservation.py`)

**What it tests**: I4 — inline-required facts survive transforms.

```python
# Oracle assertions:
for fact in inline_required_facts:
    assert fact in result.content  # fact present in visible output
```

**Test cases**:
- Transform result contains all inline_required_facts
- If any fact is missing from transform result → disposition is RAW
- Transform result with all facts → accepted
- Edge case: fact appears only in fold marker → verify marker format preserves fact

---

### Family 9: Profile Cannot Weaken Core Invariant (`test_profiles.py`)

**What it tests**: I12 — profiles cannot override constitutional invariants.

```python
# Oracle assertions:
for mode in [Mode.EXPLORE, Mode.BUILD, Mode.PROVE]:
    for profile in [DefaultProfile(), FioOSProfile(), FioIdeaisProfile()]:
        result = engine.process(authority_content, mode=mode, profile=profile)
        assert result.disposition == Disposition.RAW

    result = engine.process(unknown_content, mode=Mode.EXPLORE, profile=FioOSProfile())
    assert result.disposition == Disposition.RAW
```

**Test cases**:
- FioOS profile + AUTHORITY class, any mode → RAW
- FioOS profile + SECURITY class, any mode → RAW
- FioOS profile + UNKNOWN class, any mode → RAW
- FioIdeias profile + FAILURE class, EXPLORE mode → RAW
- Any profile cannot change UNKNOWN default

---

### Family 10: Windows Path / RAW Store Behavior (`test_windows_paths.py`)

**What it tests**: RAW store works correctly on Windows filesystem.

**Test cases**:
- RAW store initialized in a temp Windows path
- Entries stored and recovered from paths with spaces
- Store handles maximum common filename length
- Temp file renamed atomically on same volume
- Store path with backslashes handled correctly
- Store location defaults outside the FioFilter repo

---

### Family 11: Economics / Metric Separation (`test_economics.py`)

**What it tests**: I14, I15 — metrics are distinct, not conflated.

```python
# Oracle assertions:
m = engine.process(content).metrics
assert m.raw_bytes != m.raw_token_estimate  # bytes ≠ tokens
assert m.visible_bytes != m.visible_token_estimate
assert m.raw_token_estimate == approx(len(raw) / 4, rel=0.5)  # approximation
# No metric claims to be equivalent to whole-mission savings
```

**Test cases**:
- Metrics object contains all required fields (I14)
- `raw_bytes` and `raw_token_estimate` are different values
- Token estimates use chars/4 approximation, not exact tokenizer
- Metrics emitted for RAW disposition (not only for TRANSFORM)
- Metrics logged to JSONL

---

### Family 12: Corpus Replay (`tests/corpus/`)

**What it tests**: Known Tool Results from the P14 CCA corpus produce correct
dispositions against their labeled evidence classes.

**Status in V0**: Harness defined, corpus not loaded. Corpus loader reads from
JSONL files with schema:

```json
{
  "corpus_entry_id": "p14-001",
  "source": "FioOS-P14-CCA-corpus",
  "raw_content_b64": "...",
  "classification_label": "CANONICAL_STATE",
  "inline_required_facts": ["commit abc123", "branch main"],
  "expected_disposition": "RAW",
  "expected_inline_facts_present": true
}
```

When corpus is loaded (M02+): all 40 P14 entries must produce correct disposition.
Known failure modes from P14 CCA must be reproduced as expected-RAW test cases.

---

## Transform Test Oracle Pattern

Every transform must define and pass these five assertions:

```python
def test_transform_oracle(transform, raw_content, expected_facts):
    # 1. Determinism
    assert transform(raw_content) == transform(raw_content)

    # 2. No expansion
    result = transform(raw_content)
    if result != raw_content:  # transform fired
        assert len(result) < len(raw_content)

    # 3. Inline fact preservation
    for fact in expected_facts:
        assert fact in result

    # 4. Fail-open
    with mock.patch.object(transform, '_apply', side_effect=Exception):
        fallback = engine.process_with_transform(raw_content)
        assert fallback.disposition == Disposition.RAW

    # 5. Round-trip (via RAW store)
    ref = raw_store.write(raw_content)
    recovered = raw_store.read(ref)
    assert recovered == raw_content  # always — transform doesn't affect RAW store
```

---

## What Is NOT Tested in V0

- Whole-mission Codex A/B (M03+)
- Corrective retrieval prediction (M02+)
- T02 template folding, T03 PASS aggregation, T04 JSON minification (M02)
- T05 delta transform (M02+)
- Multi-threaded concurrency (future)
- Auto-learning or feedback loops (non-goal)
