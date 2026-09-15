# FioFilter — Decision Ledger

**Format**: DXX — Title — Rationale — Date  
**Authority**: Repository state outranks conversational assumptions.  
**Amendment**: A decision may be superseded by a later decision. Superseded
decisions are NOT deleted — they are marked SUPERSEDED and the superseding
decision is cited.

---

## D001 — Evidence-Aware, Not Compression-Ratio-First

FioFilter's primary metric is evidence preservation under context reduction.
Compression ratio is a secondary metric that must never be optimized at the
expense of evidence.

**Rationale**: P14 corpus — 4 genuinely compression-eligible outputs produced
1578→1578 estimated tokens (0% reduction). High compression ratios are a
lagging indicator of value, not a target. The goal is "useful progress per
context token," not "lowest token count."

**Date**: M01 / 2026-09-15

---

## D002 — Deterministic-First; No LLM in V0

All classification and transformation in V0 must be deterministic and rule-based.
No AI/LLM call is permitted in the classification or transformation path.

**Rationale**: LLM classification is non-deterministic, untestable with
deterministic oracles, adds token cost to save tokens, and introduces latency.
The classification layer must be auditable. Invariant I11 codifies this.

**Date**: M01 / 2026-09-15

---

## D003 — RAW Is Immutable and Byte-Recoverable

Once persisted, a RAW store entry is never modified or deleted. Recovery
must be byte-exact (SHA-256 verified). Invariant I1 + I3 codify this.

**Rationale**: RTK's failure mode (no RAW store at all) means compressed output
is the only output. CCA's `raw_ref` is correct but insufficient without I4.
FioFilter needs a store that is always written, always complete.

**Date**: M01 / 2026-09-15

---

## D004 — Critical Inline Evidence Cannot Be Moved Solely Behind raw_ref

Facts designated `inline_required` must appear in the visible output.
A `raw_ref` does not grant permission to remove them. Invariant I4 codifies this.

**Rationale**: CCA failure — 96/137 critical facts preserved inline (70.1%).
The missing 29.9% required a corrective model turn via `raw_ref`. The
context-compress `curl GET` failure in Terminal-Bench 2.1 is a further
empirical confirmation: compressed output without inline fact preservation
causes task failures. 100% is the requirement.

**Date**: M01 / 2026-09-15

---

## D005 — Project Profiles Cannot Weaken Core Invariants

Profiles (default, fioos, fioideias) are policy overlays. They may restrict
compression eligibility. They may never override invariants I1–I16 or change
the default for UNKNOWN from RAW. Invariant I12 codifies this.

**Rationale**: Without this rule, a FioOS profile could inadvertently allow
compression of AUTHORITY or CANONICAL_STATE evidence by narrowing definitions.
The invariants are constitutional; profiles are legislative.

**Date**: M01 / 2026-09-15

---

## D006 — No Codex Hooks in V0

FioFilter does not install hooks into Codex, modify `~/.codex`, or modify
any global agent configuration in V0.

**Rationale**: Building the engine independently of Codex allows the engine
to be tested and validated before being trusted with live agent context.
Coupling too early creates architectural debt before the core is proven.
The hook integration is V1+.

**Date**: M01 / 2026-09-15

---

## D007 — No Compressor Tournament

The donor autopsy is bounded to three pre-selected donors (RTK, CCA,
context-compress). No additional tools are evaluated for comparison in M01.

**Rationale**: A compressor tournament would expand scope, consume mission
budget, and provide diminishing returns — the three donors cover the major
architectural patterns. New tools may be added as Donor D+ if specifically
justified, recorded here.

**Date**: M01 / 2026-09-15

---

## D008 — Whole-Mission Economics Outrank Local Compression

A local `visible_bytes < raw_bytes` finding does not prove whole-mission benefit.
Metrics must distinguish: local bytes, estimated tokens, model turns, corrective
retrievals. Invariants I14 and I15 codify this.

**Rationale**: P11 evidence — turn reduction (6→0 intermediate turns) produced
−49.93% whole-mission tokens. P3 evidence — static-context optimization produced
−27.03%. Turn reduction >> local byte reduction. A transform that adds one
corrective turn may negate all local savings.

**Date**: M01 / 2026-09-15

---

## D009 — Aggressive Exploration Is Compatible With Strict Evidence Boundaries

The EXPLORE mode + NOISE/DISCOVERY/PROGRESS evidence classes permit aggressive
context reduction. This is NOT in tension with strict evidence boundaries.
The boundaries apply at the AUTHORITY/SECURITY/FAILURE/CANONICAL_STATE level.

**Rationale**: Confusing rigor with conservatism makes FioFilter useless.
NOISE should be attacked aggressively. The philosophy is:
AGGRESSIVE AT THE EXPLORATION BOUNDARY, RIGOROUS AT THE EVIDENCE BOUNDARY.

**Date**: M01 / 2026-09-15

---

## D010 — Python for V0, Not Rust

FioFilter V0 is implemented in Python. Rust is explicitly rejected for V0.

**Rationale**: RTK uses Rust but still failed evidence preservation. Language
choice is not evidence safety. Python offers: faster iteration, readable
deterministic tests, no compilation step, standard library `hashlib`/`json`/
`difflib` for transforms, `pytest` for test oracles. V0 is a laboratory;
inspectability matters more than performance.

**Date**: M01 / 2026-09-15

---

## D011 — RAW Is Written Before Any Transform Attempt

The RAW store write happens before the transform is attempted, not after.

**Rationale**: If the transform throws an exception, the RAW store entry must
already exist for recovery. A post-transform write would create a window where
a transform failure leaves no recovery path. Belt-and-suspenders for I3.

**Date**: M01 / 2026-09-15

---

## D012 — T02 (Template Folding) Deferred to M02

T02 (repeated-template folding) is a transform candidate but is NOT implemented
in V0.

**Rationale**: Template detection requires identifying N ≥ 3 structurally identical
blocks differing only in variable fields. This is more complex than T01 (exact
duplicate-line folding) and exceeds V0's foundation scope. T01, T03 (PASS
aggregation), and T04 (JSON minification) are simpler and cover primary NOISE/
SUCCESS_SUMMARY/MACHINE_DATA cases. T02 is a M02 candidate.

**Note**: T03 and T04 are candidates, not approved implementations. They must be
implemented and tested in M02 before use.

**Date**: M01 / 2026-09-15

---

## D013 — GitHub Remote Is phpedrogarcia-afk/FioFilter

The GitHub repository `https://github.com/phpedrogarcia-afk/FioFilter` was
discovered unambiguously via `gh repo list phpedrogarcia-afk`. It was empty
(no commits) at M01 execution. The local repository is connected to this remote.

**Rationale**: Preserves a clean, portable repository structure. GitHub is the
durable collaboration surface for Antigravity, Codex local, Codex web, and
future tooling.

**Date**: M01 / 2026-09-15
