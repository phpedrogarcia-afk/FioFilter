# AI-START-HERE.md — FioFilter Orientation for AI Agents

## You are working on FioFilter

FioFilter is an evidence-aware context reduction layer for coding agents.
It is NOT a generic compressor, NOT RTK, NOT CCA, NOT context-compress.

**Read this file first, every session.**

---

## Current Stage: V0 — Foundation

V0 is an **evidence engine and deterministic filter laboratory**.

V0 deliverables:
- [x] Repository foundation (M01)
- [x] Donor autopsy (M01)
- [x] Evidence contract — invariants I1–I16 (M01)
- [x] Evidence taxonomy (M01)
- [x] Decision engine specification (M01)
- [x] RAW store specification (M01)
- [x] Package skeleton (M01)
- [x] Test skeleton (M01)
- [ ] Core implementation (M02)
- [ ] Transform implementation (M02)
- [ ] Corpus regression (M02+)
- [ ] Codex A/B validation (M03+)

---

## What Makes FioFilter Different From Donors

| Property | RTK | CCA | context-compress | FioFilter |
|---|---|---|---|---|
| Evidence taxonomy | No | Partial (tiers) | No | Yes — 12 classes |
| Inline-fact protection | No | 70.1% (P14 corpus) | No | 100% required |
| RAW store | No (SQLite recall only on failure) | Yes (`raw_ref`) | Yes (FTS5 index) | Yes (SHA-256, immutable) |
| LLM in pipeline | No | No | Yes (auto mode) | No (V0) |
| Whole-mission economics | `rtk gain` | Limited | `stats` tool | First-class metric |
| Language | Rust | Node.js | TypeScript | Python |
| Fail-open | Partial | Yes | Unknown | Yes (hard rule) |

---

## Historical Experiments (Non-Negotiable Evidence)

These experiments define FioFilter. Do not replace them with donor marketing claims.

- **P3**: −27.03% tokens via static-context optimization, quality preserved
- **P11**: −49.93% tokens via turn reduction (6 turns → 0); this is the biggest lever
- **P13**: Batching strong but ~40 KB output truncated; two smaller bundles (~25K + ~33K) were complete
- **RTK rejection**: Destroyed diagnostic/directory/JSON/canonical evidence
- **CCA rejection**: Despite RAW recovery, 96/137 inline facts preserved (70.1%) — insufficient

---

## The Six Questions

Before any transform decision, the engine must answer:

1. What epistemic/evidence role does this output play?
2. Which facts must remain visible inline?
3. Is this transformation deterministic and reversible?
4. Does the transformed representation reduce context?
5. Could transformation cause another model turn or corrective retrieval?
6. Is RAW cheaper at whole-mission level?

---

## The Hard Defaults

| Situation | Default |
|---|---|
| Evidence class UNKNOWN | RAW |
| Evidence class AUTHORITY or SECURITY | RAW (all modes) |
| Evidence class FAILURE | RAW |
| Validation fails | RAW |
| Transform exception | RAW |
| Transform expands output (I9) | RAW |
| Inline-required fact missing from output | RAW |

---

## Document Map

| Document | Contents |
|---|---|
| `README.md` | Project overview, historical evidence, architecture sketch |
| `AGENTS.md` | Agent operating instructions |
| `AI-START-HERE.md` | This file — orientation |
| `docs/ARCHITECTURE.md` | Full system architecture |
| `docs/EVIDENCE-CONTRACT.md` | Invariants I1–I16 |
| `docs/DONOR-AUTOPSY.md` | RTK / CCA / context-compress bounded analysis |
| `docs/DECISIONS.md` | Decision ledger D001–D012 |
| `docs/TEST-STRATEGY.md` | Test families and oracle definitions |
| `fiofilter/types.py` | Core types: EvidenceClass, Mode, Disposition, etc. |
| `fiofilter/invariants.py` | I1–I16 enforcement |
| `fiofilter/classifier.py` | Deterministic evidence classifier |
| `fiofilter/engine.py` | Decision pipeline |
| `fiofilter/raw_store.py` | Immutable RAW store |
| `fiofilter/metrics.py` | Per-result and mission economics |
| `profiles/` | YAML policy overlays |
| `tests/` | Test families |

---

## Before Implementing Anything

1. Confirm the task is in V0 scope (see M01 spec section 13 and 18)
2. Check DECISIONS.md
3. Check EVIDENCE-CONTRACT.md
4. Write the test first
5. Implement minimal version
6. Run full test suite
7. Record any new decision
