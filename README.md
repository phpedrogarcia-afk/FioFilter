# FioFilter

**Project-aware, evidence-aware context reduction layer for coding agents.**

FioFilter is **not** a generic token compressor.

Its objective:

> MAXIMIZE useful progress per context token  
> while maintaining EVIDENCE_LOSS = 0, AUTHORITY_CHANGE = 0,  
> CRITICAL_FACT_INLINE_PRESERVATION = 100%, RAW_RECOVERY = 100%

Its philosophy:

> **AGGRESSIVE AT THE EXPLORATION BOUNDARY.**  
> **RIGOROUS AT THE EVIDENCE BOUNDARY.**

Do not confuse rigor with conservatism. FioFilter attacks known low-value noise
aggressively. It never damages evidence it cannot prove is safe to transform.

---

## Status

**V0 — Foundation only.** Evidence engine and deterministic filter laboratory.  
Not production-ready. No Codex integration in this stage.

---

## What FioFilter Is

FioFilter intercepts tool results (initially from Codex) and, before returning
them to the model context, asks **six questions**:

1. What epistemic/evidence role does this output play?
2. Which facts must remain visible inline?
3. Is this transformation deterministic and reversible?
4. Does the transformed representation reduce context?
5. Could transformation cause another model turn or corrective retrieval?
6. Is RAW cheaper at whole-mission level?

These questions are answered by a **deterministic decision pipeline** using
an **evidence taxonomy** and **project profiles**. No LLM is called in V0.

---

## Why FioFilter Exists — Historical Evidence

| Experiment | Finding |
|---|---|
| P3 | Static-context optimization: 839,815 → 612,776 tokens (−27.03%), quality preserved |
| P11 | Turn reduction between independent reads: 168,793 → 84,509 tokens (−49.93%), QUALITY PASS |
| P11 real | 6 intermediate model turns → 0, identical evidence and quality |
| P13 | Governance-document batching strong, but ~40 KB bundle truncated (two ~25–33 KB bundles were complete) |

**Key findings:**
- Turn reduction is the biggest lever (P11 > P3 by far)
- Batch size has a truncation risk; P13 shows this empirically
- RTK was rejected: compressed representations destroyed diagnostic, directory, progress, JSON, and canonical/security evidence
- CCA was rejected despite exact RAW recovery: 96/137 critical facts inline (70.1%); 4 eligible outputs produced 0% token reduction

**Conclusion:** Reversibility alone is not sufficient. A `raw_ref` is not permission to remove critical inline evidence.

---

## What FioFilter Is NOT

- Not RTK (command-name-based proxy, no evidence taxonomy, no RAW store)
- Not CCA (rule-based splitter without evidence class, no protection for inline facts)
- Not context-compress (MCP server, LLM-judged modes, FTS5 index, forbidden in V0)
- Not a generic compressor
- Not production-ready
- Not a Codex hook (V0)

See [docs/DONOR-AUTOPSY.md](docs/DONOR-AUTOPSY.md) for the bounded analysis.

---

## Architecture Overview

```
Tool Result
     │
     ▼
DECISION ENGINE
     │
     ├─ Normalize Metadata
     ├─ Classify Evidence (deterministic, no LLM)
     ├─ Load Profile
     ├─ Check Protected Invariants
     ├─ Select Disposition: RAW | TRANSFORM | ESCALATE_TO_RAW
     ├─ Write RAW store (before transform attempt)
     ├─ Run Candidate Transform (if selected)
     ├─ Validate Output
     ├─ Compare Economic Local Cost (I9: expansion → RAW)
     └─ Return FilterResult + Metrics
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full specification.

---

## Key Concepts

| Concept | Summary |
|---|---|
| Evidence Class | What epistemic role this output plays (NOISE, DIAGNOSTIC, AUTHORITY, etc.) |
| Mode | EXPLORE / BUILD / PROVE — influences disposition, does not grant authority |
| Disposition | RAW / TRANSFORM / ESCALATE\_TO\_RAW — the decision outcome |
| RAW Store | Immutable, content-addressable, SHA-256, local filesystem |
| Invariants | I1–I16 — the non-negotiable evidence contract |
| Profile | Policy overlay per project (default / fioos / fioideias) |

---

## Repository Structure

```
fiofilter/          Python package (engine, classifier, transforms, profiles, metrics)
tests/              Test families — defined before compression logic
docs/               Architecture, evidence contract, donor autopsy, decisions
profiles/           YAML policy overlays
```

---

## Quickstart (Development)

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/ -v
```

Requires Python 3.9+. No external runtime dependencies in V0.

---

## Evidence Classes

`NOISE` · `DISCOVERY` · `PROGRESS` · `SUCCESS_SUMMARY` · `DIAGNOSTIC` · `FAILURE`  
`CANONICAL_STATE` · `MACHINE_DATA` · `AUTHORITY` · `SECURITY` · `BENCHMARK` · `UNKNOWN`

Default for UNKNOWN: **RAW**.  
Default for AUTHORITY and SECURITY: **RAW** in all modes.

---

## V0 Quality Gates

Before any Codex integration:

| Gate | Requirement |
|---|---|
| RAW_RECOVERY_SHA_MATCH | 100% |
| INLINE_REQUIRED_CRITICAL_FACT_PRESERVATION | 100% |
| UNEXPECTED_PROTECTED_TRANSFORMATIONS | 0 |
| MACHINE_DATA_VALIDITY_FAILURES | 0 |
| SECURITY_OR_AUTHORITY_FACT_LOSS | 0 |
| FAILURE_DIAGNOSTIC_UNSAFE_CASES | 0 |

---

## Decisions

See [docs/DECISIONS.md](docs/DECISIONS.md) for the decision ledger.

Core: D001 evidence-aware · D002 deterministic · D003 RAW immutable ·  
D004 inline facts mandatory · D005 profiles can't weaken invariants ·  
D006 no Codex hooks V0 · D008 whole-mission economics first

---

## GitHub

Repository: https://github.com/phpedrogarcia-afk/FioFilter

Collaboration surface for: Antigravity · Codex local · Codex web · future tooling.
