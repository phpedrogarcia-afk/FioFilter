# FioFilter V0 Explicit Integration Spine

## 1. Executive Summary

Mission **M12** integrates all offline-proven FioFilter capabilities behind a unified, explicit local laboratory interface.

```
M12_CANONICAL_VERDICT = M12_V0_EXPLICIT_LAB_PASS
PROJECT_STATUS = V0_EXPLICIT_LAB_COMPLETE
```

FioFilter V0 is an **evidence engine and deterministic filter laboratory**, not an autonomous background daemon. It provides an auditable, programmatic environment for developers and researchers to evaluate discovery navigation, representation compression, and reexposure shadowing without altering agent workflows or risking context corruption.

---

## 2. What FioFilter V0 Does

1. **BM25 Discovery Runtime Shadow (`fiofilter.discovery_runtime_shadow`)**:
   - Computes deterministic lexical file rankings and compact index maps from repository worktrees.
   - Bound to content-sensitive worktree fingerprinting (`WORKTREE_STATE_DIGEST_V2`).
   - Authority: `NAVIGATION_ONLY`.

2. **Read Receipt Shadow Specialization (`fiofilter.read_receipt`, `fiofilter.runtime_shadow`)**:
   - Tracks file read views and computes Plane A byte-level freshness proofs (`F4_CURRENT_VIEW_BYTE_EQUAL`).
   - Evaluates hypothetical reference eligibility (`[[FIOFILTER:READREF:v1 ...]]`) with strict no-expansion guarantees.
   - Authority: `OBSERVATIONAL_SHADOW_ONLY` (always emits exact RAW bytes to the caller).

3. **Lossless Search Output Representation (`fiofilter.transforms.t02_rg_standard_group`)**:
   - Performs verified, byte-exact roundtrippable contiguous-run grouping for authorized `RG_STANDARD_PATH_LINE_TEXT` grammars.
   - Protected by `ENGINE_METADATA_GATE_REMAINS`: only evaluates when explicit `RgStandardEvidence` is provided by the caller.
   - Authority: `TRANSFORM_ONLY_WHEN_PROVEN`.

4. **Unified V0 CLI & Controller (`fiofilter.v0.FioFilterV0Lab`, `fiofilter.cli`)**:
   - Single explicit command surface (`status`, `inspect-repo`, `discovery-shadow`, `read-shadow`, `run-lab-scenario`).
   - Event-level decision traces and strict metric isolation.

---

## 3. What FioFilter V0 Does NOT Do

- **NO Codex / IDE Hooks**: Does not install shell traps, git hooks, or background daemons in `~/.codex` or Antigravity.
- **NO MCP Server or Proxy**: Does not intercept network calls, stdio streams, or LLM traffic.
- **NO Active Read Suppression**: Discovery ranking and read receipts never block, truncate, or suppress tool outputs.
- **NO Automatic Context Injection**: Discovery maps are never injected into prompt contexts autonomously.
- **NO LLMs, Embeddings, or Heuristic Classifiers**: All logic is strictly rule-based, deterministic, and verifiable.
- **NO Raw Query or Sensitive Persistence**: Local shadow ledgers store only SHA-256 hashes; raw queries and sensitive inputs are never persisted.

---

## 4. Capability Registry & Status Model

FioFilter strictly distinguishes capability lifecycle states to avoid false claims of production readiness:

```
IMPLEMENTED → VALIDATED_OFFLINE → SHADOW_READY → LIVE_VALIDATED → ACTIVE_AUTHORIZED → PRODUCTION_READY
```

### Registry Table

| Capability ID | Version | Lifecycle State | Authority | Activation Mode | Evidence Gate | Production Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`T02_RG_STANDARD_GROUP_V1`** | 1.0.0 | `VALIDATED_OFFLINE` | `TRANSFORM_ONLY_WHEN_PROVEN` | `EXPLICIT_ONLY` | `ENGINE_METADATA_GATE_REMAINS` | `NOT_PRODUCTION_READY` |
| **`READ_RECEIPT_SHADOW_V1`** | 1.0.0 | `SHADOW_READY` | `OBSERVATIONAL_SHADOW_ONLY` | `EXPLICIT_SHADOW` | `PASSIVE_OR_DIRECT_EVIDENCE_PROVEN` | `NOT_PRODUCTION_READY` |
| **`DISCOVERY_RUNTIME_SHADOW_V1`** | 1.0.0 | `SHADOW_READY` | `NAVIGATION_ONLY` | `EXPLICIT_SHADOW` | `CONTENT_SENSITIVE_V2_FINGERPRINT` | `NOT_PRODUCTION_READY` |

---

## 5. Cross-Component Invariants

The V0 spine enforces strict operational firewalls between subsystems:

1. **`DISCOVERY_RANKING_CANNOT_AUTHORIZE_READ_SUPPRESSION`**: High or low discovery rank provides orientation hints only; it cannot authorize skipping or suppressing a file read.
2. **`READ_RECEIPT_CANNOT_AUTHORIZE_TRANSFORM`**: Proving byte freshness for a read receipt grants no authority to mutate or compress search outputs.
3. **`T02_CANNOT_HIDE_CRITICAL_EVIDENCE`**: Transforms must roundtrip byte-identically; any ambiguity fails open to RAW.
4. **`SHADOW_CANNOT_CHANGE_RAW_OUTPUT`**: Shadow capabilities observe and record hypothetical metrics without altering delivered bytes.
5. **`UNKNOWN_ANYWHERE_CAN_FAIL_TO_RAW`**: Any unrecognized input, syntax error, or unproven precondition emits exact RAW bytes.
6. **`CAPABILITY_DOES_NOT_GRANT_AUTHORITY`**: A capability being implemented or validated offline confers zero permission for autonomous live activation.

---

## 6. CLI and Programmatic API

### 6.1 Unified CLI (`python -m fiofilter`)

```bash
# Report operational status and capability registry
python -m fiofilter status

# Inspect repository HEAD and V2 content-sensitive fingerprint
python -m fiofilter inspect-repo .

# Evaluate discovery shadow navigation for a task query
python -m fiofilter discovery-shadow "read receipt freshness check" .

# Evaluate a file read through the read-receipt shadow harness
python -m fiofilter read-shadow fiofilter/read_receipt.py

# Execute deterministic end-to-end integration scenario
python -m fiofilter run-lab-scenario .
```

### 6.2 Python Laboratory API

```python
from fiofilter.v0 import FioFilterV0Lab, V0Config
import pathlib

lab = FioFilterV0Lab()

# 1. Check status
status = lab.get_status()

# 2. Discovery shadow navigation
ev = lab.evaluate_discovery(pathlib.Path("."), "read receipt logic")

# 3. File read shadow evaluation (always delivers RAW bytes)
raw_bytes, decision = lab.evaluate_read_shadow("fiofilter/read_receipt.py")

# 4. Search representation evaluation (emits RAW unless explicitly authorized)
raw_out, outcome = lab.evaluate_representation(sample_rg_bytes, evidence=None)

# 5. Review metrics
print(lab.metrics.to_dict())
```

---

## 7. End-to-End Lab Scenario

The V0 spine includes a deterministic end-to-end scenario exercising all subsystems simultaneously:

```
User Task Query
       │
       ▼
[Step 1: Discovery Shadow] ────────► Produces top navigation candidates (duration: ~336 ms)
       │
       ▼
[Step 2: Initial File Read] ───────► Delivers exact RAW bytes (49,200 B, FIRST_READ_RAW)
       │
       ▼
[Step 3: Repeated File Read] ──────► Delivers exact RAW bytes (49,200 B)
                                      └─► Proves F4 byte identity
                                      └─► Computes hypothetical reference (49,058 B avoided)
       │
       ▼
[Step 4: Search Representation] ───► Evaluates T02 candidate under RgStandardEvidence
                                      └─► Emits exact RAW bytes (explicit transform unauthorized)
       │
       ▼
[Step 5: Metrics & Accounting] ────► Strictly separates actual (0 B) from hypothetical (49,058 B)
```

Total scenario execution time: **~350 ms**.

---

## 8. Actual vs Hypothetical Economics

FioFilter V0 enforces a strict accounting division in its decision trace and summary reporting:

- **`ACTUAL_VISIBLE_BYTES_REDUCED`**: Measures bytes actually saved in delivered output when an explicit transform is authorized and applied.
- **`SHADOW_HYPOTHETICAL_BYTES_AVOIDED`**: Measures bytes that *would* have been avoided if an authorized reference replacement had occurred.

```
FORMAL ACCOUNTING INVARIANT:
ACTUAL_VISIBLE_BYTES_REDUCED and SHADOW_HYPOTHETICAL_BYTES_AVOIDED
must NEVER be summed together.
```

In the standard V0 shadow run:
- `ACTUAL_VISIBLE_BYTES_REDUCED = 0`
- `SHADOW_HYPOTHETICAL_BYTES_AVOIDED = 49,058`

---

## 9. Performance Economics

Measured on the 64-file repository snapshot:

| Operation | Latency | Note |
| :--- | :---: | :--- |
| V0 Controller Startup | < 0.05 ms | Instantaneous instantiation |
| Discovery Evaluation (Cold) | ~326 ms | Includes ~143 ms V2 state validation |
| Discovery Evaluation (Reuse) | ~144 ms | Reuses cached BM25 index |
| File Read Shadow Evaluation | ~6.7 ms | Hash + byte comparison |
| T02 Candidate Evaluation | ~0.26 ms | Lossless grouping check |
| Total End-to-End Scenario | ~350 ms | Deterministic local execution |

---

## 10. Remaining Blockers Before Live Active Deployment

Before any subsystem can advance from `SHADOW_READY` to active production deployment, the following gates remain mandatory:

1. **Live Codex Availability**: Codex interaction must resume so shadow harnesses can be observed passively on real user workloads.
2. **Engine Metadata Gate (`ENGINE_METADATA_GATE_REMAINS`)**: Generic CLI/tool wrappers must prove tool identity and invocation flags structurally before T02 can auto-route.
3. **Behavioral Equivalence Trials**: Multi-turn agent trials must prove that hypothetical reference replacements do not degrade agent reasoning or task completion.
4. **Explicit User Authorization**: Active context suppression requires explicit policy opt-in; default remains strict RAW-first.

---

## 11. Final Verdict

```
M12_CANONICAL_VERDICT = M12_V0_EXPLICIT_LAB_PASS
```