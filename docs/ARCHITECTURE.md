# FioFilter — Architecture

## Purpose

FioFilter is a deterministic, evidence-aware context reduction layer for coding agents.
It processes tool results before they enter the model context, aiming to maximize
useful progress per context token while preserving evidence integrity.

---

## Governing Philosophy

```
AGGRESSIVE AT THE EXPLORATION BOUNDARY.
RIGOROUS AT THE EVIDENCE BOUNDARY.
```

These are not in tension. EXPLORE mode + NOISE class permits aggressive folding.
PROVE mode + AUTHORITY class enforces RAW regardless of size.

---

## System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FIOFILTER V0                                │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ToolResult (raw bytes + metadata)                                  │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    DECISION ENGINE                           │  │
│  │                   (engine.py)                                │  │
│  │                                                              │  │
│  │  1. normalize_metadata(tool_result)                          │  │
│  │  2. classifier.classify(meta, content) → EvidenceClass       │  │
│  │  3. profile.get_policy(evidence_class, mode) → Policy        │  │
│  │  4. invariants.check(evidence_class, policy) → OK / FORCE_RAW│  │
│  │  5. select_disposition(class, mode, policy, inv) → Disposition│  │
│  │  6. raw_store.write(content) → RawRef   [BEFORE transform]   │  │
│  │  7. transforms.apply(disposition, content) → TransformResult  │  │
│  │  8. validator.validate(result, class, meta) → bool           │  │
│  │  9. if len(result) >= len(raw): return RAW   [I9]            │  │
│  │  10. if inline_facts_missing: return RAW     [I4]            │  │
│  │  11. metrics.record(...)                                     │  │
│  │  12. return FilterResult                                     │  │
│  └────────────────────────┬────────────────────────────────────┘  │
│                           │                                         │
│          ┌────────────────┴─────────────────┐                      │
│          ▼                                   ▼                      │
│    ┌──────────────────┐             ┌───────────────────┐          │
│    │   RAW STORE      │             │  TRANSFORM OUTPUT │          │
│    │  (raw_store.py)  │             │  (visible content │          │
│    │  SHA-256         │             │   + raw_ref link) │          │
│    │  content-addr.   │             └───────────────────┘          │
│    │  immutable       │                                             │
│    │  filesystem      │                                             │
│    └──────────────────┘                                             │
│                                                                     │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │               METRICS LOGGER (metrics.py)                  │    │
│  │  raw_bytes · visible_bytes · token_estimates · duration_ms  │    │
│  │  evidence_class · mode · decision · corrective_retrievals   │    │
│  └────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  PROFILES: profiles/default.yaml · fioos.yaml · fioideias.yaml     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Package Layout

```
fiofilter/
  __init__.py          Version and public surface
  types.py             EvidenceClass, Mode, Disposition, ToolResult, FilterResult,
                       RawRef, TransformResult, FilterMetrics — all dataclasses/enums
  invariants.py        I1–I16 as callable functions; invariants.check() returns
                       InvariantResult with forced disposition or OK
  classifier.py        Deterministic rule-based classifier; no LLM; returns
                       ClassifyResult(evidence_class, confidence, inline_required_facts)
  engine.py            Decision pipeline — single entry point: process()
  raw_store.py         Immutable local RAW store; content-addressable by SHA-256;
                       atomic writes; metadata sidecar; Windows-safe paths
  metrics.py           FilterMetrics dataclass + JSONL logger
  transforms/
    __init__.py        Transform registry
    base.py            Transform ABC: apply(content, meta) → TransformResult
                                      recover(result, raw_ref) → bytes
    t01_dup_fold.py    T01: Exact duplicate-line folding
  profiles/
    __init__.py        Profile loader
    base.py            BaseProfile ABC: get_policy(evidence_class, mode) → Policy
    default.py         Default profile (standard taxonomy table)
    fioos.py           FioOS profile (additional protections)
    fioideias.py       FioIdeias profile (stub)

tests/
  conftest.py          Shared fixtures: tmp RAW store, synthetic tool results
  test_raw_store.py    RAW byte-exact recovery, atomicity, SHA-256 match
  test_invariants.py   I1–I16 individually testable
  test_classifier.py   UNKNOWN→RAW, evidence class routing
  test_decision_engine.py  Full pipeline integration: all disposition paths
  test_transforms.py   Determinism, no-expansion, round-trip, fail-open (T01)
  test_machine_data.py Machine validity (future T04)
  test_inline_preservation.py  I4: inline-required facts survive transforms
  test_profiles.py     Profile cannot weaken core invariant (I12)
  test_windows_paths.py  RAW store on Windows paths, long paths
  test_mode_escalation.py  EXPLORE/BUILD/PROVE behavior; I6 auto-escalation
  test_economics.py    I9 (expansion=RAW), I14/I15 metric separation
  corpus/
    README.md          Corpus importer specification (data not yet loaded)

profiles/
  default.yaml         Default disposition table
  fioos.yaml           FioOS policy overlay
  fioideias.yaml       FioIdeias policy overlay (stub)
```

---

## Decision Pipeline — Detailed

### Step 1: Normalize Metadata

Extract from the raw ToolResult:
- `command` (if known)
- `exit_code` (if applicable)
- `content_type` hint (JSON/text/binary)
- `byte_length`
- `source` (e.g., shell, file-read)

No classification happens here. Pure extraction.

### Step 2: Classify Evidence

The classifier applies deterministic rules (regex, structural analysis, exit code) to assign an `EvidenceClass`.

Rules fire in priority order:
1. Exit code non-zero → candidate for FAILURE
2. Binary content → MACHINE_DATA (lossless-only)
3. JSON-parseable content → MACHINE_DATA
4. Security/authority patterns → AUTHORITY or SECURITY
5. Git/hash patterns → CANONICAL_STATE
6. Benchmark patterns → BENCHMARK
7. Repetitive/duplicate content → NOISE or PROGRESS
8. Directory listing → DISCOVERY
9. Test output → SUCCESS_SUMMARY or FAILURE
10. Default → UNKNOWN

**Confidence below threshold → UNKNOWN → RAW** (I5).

The classifier also returns `inline_required_facts`: a list of fact strings that
must be present in any transformed output.

### Step 3: Load Profile

The active profile (default, fioos, or fioideias) is loaded.
`profile.get_policy(evidence_class, mode)` returns an allowed disposition set
and a transform whitelist.

Profiles may restrict but never expand the core taxonomy table.

### Step 4: Check Protected Invariants

`invariants.check()` examines the evidence class and policy for invariant violations:
- AUTHORITY or SECURITY → force RAW (I7)
- UNKNOWN → force RAW (I5)
- FAILURE → force RAW (I6 escalation if unexpected)
- MACHINE_DATA + non-lossless transform → force RAW (I8)

Any invariant that fires returns `InvariantResult(forced=True, disposition=RAW, reason=...)`.

### Step 5: Select Disposition

If invariants did not force RAW, select from allowed dispositions based on
evidence class and mode. V0 dispositions: RAW, TRANSFORM, ESCALATE_TO_RAW.

### Step 6: Write RAW Store First

Before any transform attempt, the raw content is written to the RAW store.
This guarantees recovery even if the transform subsequently fails.

### Step 7: Run Candidate Transform

The transform registry selects the appropriate transform based on evidence class
and whitelisted transforms. Transform is called with content + metadata.

**Fail-open**: Any exception → catch and return RAW.

### Step 8: Validate Output

The validator checks:
- Transform output is text (not None, not binary garbage)
- For MACHINE_DATA: the output re-parses correctly (I8)
- The output contains all `inline_required_facts` (I4)

Validation failure → RAW.

### Step 9: Economic Size Check

If `len(transformed) >= len(raw)`: return RAW (I9).

This is a hard rule. A transform that does not compress loses to RAW.

### Step 10: Inline Fact Verification

Recheck that all `inline_required_facts` are present in `transformed.content`.
If any are missing: return RAW (I4).

(This is a second check after validation — belt and suspenders for I4.)

### Step 11: Emit Metrics

Record `FilterMetrics` to the JSONL log:
- `raw_bytes`, `visible_bytes`, `raw_token_estimate`, `visible_token_estimate`
- `transform_duration_ms`, `decision`, `evidence_class`, `mode`

### Step 12: Return FilterResult

Returns `FilterResult` with:
- `content` (visible output)
- `disposition`
- `raw_ref` (always — even for RAW dispositions)
- `raw_sha256`
- `transform_id` (if transformed)
- `policy_decision`
- `evidence_class`
- `metrics`

---

## RAW Store Design

**Location**: `~/.fiofilter/raw/` (outside repo; configurable via `FIOFILTER_RAW_STORE`)

**Layout**:
```
{raw_store_root}/
  objects/
    {sha256[0:2]}/
      {sha256}        ← immutable content blob (binary, no extension)
  meta/
    {sha256[0:2]}/
      {sha256}.json   ← metadata sidecar
  index.jsonl         ← append-only reference log
```

**Write protocol** (atomic):
1. Compute SHA-256 of content bytes
2. Check if `objects/{prefix}/{sha256}` already exists → if yes, skip write (dedup)
3. Write content to `objects/{prefix}/{sha256}.tmp`
4. Rename `.tmp` → final path (atomic on same volume)
5. Write metadata sidecar
6. Append to `index.jsonl`

**Recovery**: Read `objects/{prefix}/{sha256}`, verify SHA-256 == `raw_ref.sha256`.

**V0 constraints**: No deletion. No network. No external DB.

---

## Evidence Taxonomy — Disposition Table

| Evidence Class | EXPLORE | BUILD | PROVE |
|---|---|---|---|
| NOISE | TRANSFORM | TRANSFORM | TRANSFORM |
| DISCOVERY | TRANSFORM | TRANSFORM | RAW |
| PROGRESS | TRANSFORM | TRANSFORM | RAW |
| SUCCESS_SUMMARY | TRANSFORM | TRANSFORM | RAW |
| DIAGNOSTIC | TRANSFORM | RAW | RAW |
| FAILURE | RAW | RAW | RAW |
| CANONICAL_STATE | RAW | RAW | RAW |
| MACHINE_DATA | lossless-only | lossless-only | RAW |
| AUTHORITY | RAW | RAW | RAW |
| SECURITY | RAW | RAW | RAW |
| BENCHMARK | RAW | RAW | RAW |
| UNKNOWN | RAW | RAW | RAW |

---

## Modes

| Mode | Purpose | Effect |
|---|---|---|
| EXPLORE | Discovery tasks, broad searches, repetitive output | Unlocks TRANSFORM for NOISE/DISCOVERY/PROGRESS |
| BUILD | Default development mode | Standard taxonomy table |
| PROVE | Security, authority, benchmarks, failures | Most classes forced to RAW |

Modes influence policy. They do not grant authority. They cannot override invariants.

---

## Metrics — Unit Boundaries

The following are NOT equivalent and MUST be tracked separately (I14, I15):

| Metric | Unit |
|---|---|
| `raw_bytes` | bytes |
| `visible_bytes` | bytes |
| `raw_token_estimate` | ~tokens (approximation: chars/4) |
| `visible_token_estimate` | ~tokens |
| `transform_duration_ms` | milliseconds |
| `corrective_retrieval_required` | boolean/count |
| `model_turns` | turns (mission-level, future) |

A local `visible_bytes < raw_bytes` does NOT imply fewer model turns or better
whole-mission economics. P11 evidence: turn reduction (6→0 turns) produced
−49.93% tokens; P3 evidence: static-context optimization produced −27.03%.

---

## Anti-Patterns — What FioFilter Must Never Become

1. **RTK clone**: Do not compress by command name without evidence classification.
   RTK's failure mode (destroying diagnostic/canonical evidence) is well-documented.

2. **CCA clone**: Do not compress without guaranteeing 100% inline critical fact preservation.
   CCA achieved 96/137 (70.1%) — insufficient.

3. **Ratio optimizer**: Do not optimize for the highest compression ratio.
   The 4 genuinely eligible outputs in the P14 corpus produced 0% reduction.
   Ratio is a lagging indicator of value, not a target.

4. **Conservative by default**: NOISE should be aggressively compressed.
   Conservatism at the exploration boundary wastes context.

5. **LLM-dependent**: No AI in V0 pipeline. Deterministic classification first.

---

## V0 Scope Boundary

V0 implements: RAW store + types + invariants + classifier stub + engine + T01 + metrics + tests.

V0 does NOT implement: Codex hooks, MCP, proxy, GUI, LLM, T02-T05 (candidates only), auto-learning.
