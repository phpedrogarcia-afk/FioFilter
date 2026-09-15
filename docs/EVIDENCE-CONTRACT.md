# FioFilter — Evidence Contract

**Version**: V0  
**Status**: Normative — all implementation must comply

This document defines the non-negotiable invariants that govern FioFilter's behavior.
Profiles may narrow compression eligibility. They may never weaken these invariants.
No amount of compression pressure, performance goal, or mission context may override them.

---

## Invariants

### I1 — RAW Immutability

RAW output is immutable once persisted. No process, profile, or configuration
may modify, overwrite, or delete a stored RAW entry in V0.

**Consequence**: The write-once protocol in `raw_store.py` must be enforced
at the filesystem level (atomic rename, no in-place modification).

---

### I2 — Transform Linkage

Every transformed output that has a RAW source must carry:

```
raw_ref          — reference to the RAW store entry
raw_sha256       — SHA-256 hash of the original raw bytes
transform_id     — identifier of the transform applied
policy_decision  — the disposition chosen by the decision engine
evidence_class   — the evidence class assigned by the classifier
```

No transformed output may be returned without all five fields populated.

---

### I3 — Byte-Exact Recovery

RAW recovery must be byte-exact. Specifically:

```python
sha256(raw_store.read(raw_ref)) == raw_ref.raw_sha256
```

This must pass as a test oracle for every stored entry. Approximate recovery,
semantic equivalence, and structural equivalence are NOT sufficient.

---

### I4 — Inline-Required Fact Preservation

Critical facts designated `inline_required` may NEVER exist only behind a
`raw_ref`. They must appear verbatim in the visible output returned to the model.

**This is the invariant CCA violated**: 96/137 critical facts (70.1%) were
preserved inline in the P14 corpus. FioFilter requires 100%.

A transform that removes an inline-required fact must be rejected, and RAW
returned instead.

---

### I5 — Unknown Defaults to RAW

When the classifier assigns evidence class UNKNOWN, or when classifier
confidence falls below the minimum threshold, the disposition is always RAW.

No profile, mode, or caller hint may override this default.

---

### I6 — Failure Escalation

Unexpected failures (non-zero exit codes, crash outputs, exception tracebacks,
test failures) automatically escalate the disposition toward RAW, regardless
of the current mode.

In EXPLORE mode, a failure result escalates to BUILD-equivalent evidence handling.
In BUILD mode, a failure result escalates to PROVE-equivalent evidence handling.
In PROVE mode, a failure result is always RAW.

"Unexpected" is determined by the classifier and invariant checker, not by
the caller. A caller cannot suppress failure escalation.

---

### I7 — Authority and Security Protection

AUTHORITY and SECURITY evidence classes are not compressed unless an explicitly
proven, tested, mathematically lossless transform exists and has been approved
in the decision ledger.

In V0, no such transform exists. AUTHORITY and SECURITY are always RAW.

---

### I8 — Machine Data Validity

Machine-consumed structured data (JSON, YAML, CSV, NDJSON, etc.) must remain
machine-valid after any transformation.

Specifically: if `json.loads(raw)` succeeds, then `json.loads(transformed)` must
also succeed and produce an equal data structure.

If the caller explicitly requests a human representation, this invariant may
be relaxed — but only if the caller provides that instruction explicitly and
the evidence class is not AUTHORITY or SECURITY.

---

### I9 — No-Expansion Rule

A transform whose visible output is larger than or equal to the raw input is
rejected in favor of RAW.

```python
if len(transformed_bytes) >= len(raw_bytes):
    return RAW
```

This is a hard rule applied after every transform, before the result is returned.
A transform that does not save space at the local level provides no local benefit
and must lose to RAW.

---

### I10 — Corrective Retrieval Penalty

A transform that is expected to trigger corrective retrieval (an additional model
turn to re-fetch omitted information) is economically penalized.

If the expected penalty (in terms of model turns or tokens) exceeds the local
savings, the decision engine should prefer RAW.

In V0, corrective retrieval prediction is not automated. The engine records
`corrective_retrieval_required` as a flag when known. This invariant guides
future economic modeling.

**Empirical basis**: P11 showed that turn reduction (6→0 turns) produced
−49.93% whole-mission tokens. A transform that adds even 1 corrective turn
may negate all local byte savings.

---

### I11 — No LLM in V0

No AI/LLM is required or permitted in the V0 classification or transformation
path. All classification and transformation must be deterministic and rule-based.

This is not merely a performance constraint. An LLM-dependent classifier
cannot be tested with deterministic oracles, and its output cannot be audited.

---

### I12 — Profile Non-Weakening

Profiles may narrow compression eligibility (e.g., FioOS profile restricts
DISCOVERY to RAW in BUILD mode). Profiles may NOT:

- Override any invariant I1–I16
- Silently elevate a protected class to TRANSFORM disposition
- Change the default for UNKNOWN from RAW
- Relax the inline-fact preservation requirement

Violation of this invariant is detectable by test: `test_profiles.py` must
verify that no profile can weaken a protected invariant.

---

### I13 — Batch Identity Preservation

Evidence identity and boundaries must survive batching and transformation.

A batch of multiple tool results must not merge their evidence into a single
opaque unit that loses source identity. Each tool result in a batch must be
individually recoverable with its own `raw_ref` and `evidence_class`.

**Empirical basis**: P13 showed that a single large ~40 KB governance-document
batch truncated. Two smaller bundles (~25K + ~33K) were complete. Batch
boundaries matter — and so does each item's recoverability.

---

### I14 — Metric Unit Separation

The following metrics are distinct and must be tracked and reported separately.
They may never be conflated or combined without explicit labeling:

| Metric | Unit |
|---|---|
| `raw_bytes` | bytes in raw content |
| `visible_bytes` | bytes in visible output |
| `raw_token_estimate` | estimated tokens (approximation) |
| `visible_token_estimate` | estimated tokens (approximation) |
| `transform_duration_ms` | milliseconds |
| `corrective_retrievals` | count |
| `model_turns` | turns (mission-level) |

Token estimates are approximations (chars ÷ 4). They are not billing metrics.

---

### I15 — No Local-to-Mission Conflation

No local compression ratio may be reported as equivalent to whole-mission
token savings, model turn savings, or quality improvements.

`visible_bytes / raw_bytes` is a local metric. It does not imply:
- Fewer model turns
- Lower billed tokens
- Better task quality
- Fewer corrective retrievals

**Empirical basis**: The P14 CCA corpus showed 4 genuinely eligible outputs
with 1578→1578 estimated tokens (0% reduction). Local eligibility ≠ local savings.
Local savings ≠ whole-mission savings.

---

### I16 — Logged Decision Requirement

Every disposition decision must be logged with enough information to replay
or audit the decision deterministically:

```json
{
  "raw_sha256": "...",
  "evidence_class": "NOISE",
  "mode": "EXPLORE",
  "profile": "default",
  "invariant_checks": ["I5:OK", "I7:OK"],
  "disposition": "TRANSFORM",
  "transform_id": "T01",
  "timestamp_utc": "..."
}
```

A transform applied without a logged decision is a protocol violation.
The log entry must be written before the result is returned to the caller.

---

## Proposed V0 Additions (Under Consideration for M02)

The following are candidates to add as I17+ if validated experimentally:

- **I17**: A transform candidate that has been rejected (output ≥ input) for
  a given evidence class in N consecutive cases should be de-prioritized
  for that class, logged, and reviewed in the next mission.

- **I18**: Batch size must be bounded. No batch may exceed a configured maximum
  byte count (default: 32,768 bytes, based on P13 evidence). Batches that
  would exceed the limit must be split at evidence boundaries.

These are candidates, not invariants. They require empirical validation before
being added to this contract.
