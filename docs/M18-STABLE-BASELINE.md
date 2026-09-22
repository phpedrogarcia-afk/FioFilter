# M18 — stable baseline and feature-freeze rule

## Canonical scope

This is a compact status index for the canonical baseline at
`ed0146ca074a02787a9cf7e0b748dd8f77a92c9f`. It does not replace the evidence
contract, tests, router, decision ledger or historical reports. When a task
needs a claim below, load its linked canonical source through `AI-START-HERE.md`.

```text
FEATURE_EXPANSION=FROZEN_UNLESS_REQUIRED_FOR_CORRECTNESS
MISSION_CONTEXT=SHADOW_ONLY
READREF_CANARY=OFF_PAUSED
ACTIVE_SUPPRESSION=NO
AUTOMATIC_CONTEXT_SELECTION=NO
AUTOMATIC_T02=NO
FIO_HANDOFF_INTEGRATION=NO
PRODUCTION_READY=NO
```

## Current supported baseline

| Mechanism | Classification | Current path | Evidence / tests | Safe to remove |
| --- | --- | --- | --- | --- |
| Evidence engine, policy, T01 and RAW linkage | `PROVEN_ACTIVE` | `fiofilter/engine.py`, `fiofilter/invariants.py`, `fiofilter/transforms/t01_dup_fold.py` | `docs/EVIDENCE-CONTRACT.md`; core/M02 tests | NO |
| Sensitivity, EPHEMERAL RAW and explicit persistence | `PROVEN_ACTIVE` | `fiofilter/sensitivity.py`, `fiofilter/raw_store.py` | Evidence contract I1–I7/I16; storage tests | NO |
| T02 RG standard grouping | `PROVEN_SUPPORTING` | `fiofilter/transforms/t02_rg_standard_group.py` | M04 contract and T02 tests; explicit evidence only | NO |
| V0 explicit lab and CLI | `PROVEN_SUPPORTING` | `fiofilter/v0.py`, `fiofilter/cli.py` | `docs/V0-EXPLICIT-LAB.md`; V0 integration tests | NO |
| Progressive-disclosure router and section helper | `PROVEN_SUPPORTING` | `AGENTS.md`, `AI-START-HERE.md`, `scripts/section_working_set.py` | M16 decisions; routing and fence tests | NO |
| Discovery runtime and Codex Web observer | `SHADOW_ONLY` | `fiofilter/discovery_runtime_shadow.py`, `fiofilter/codex_web_shadow.py` | M11/M13 docs and shadow tests | UNKNOWN |
| Efficiency Feed V1 | `SHADOW_ONLY` | `fiofilter/efficiency_feed.py` | M13 contract and feed tests | UNKNOWN |
| Read-receipt evaluator / runtime shadow | `SHADOW_ONLY` | `fiofilter/read_receipt.py`, `fiofilter/runtime_shadow.py` | M07/M08/M13 docs and tests | UNKNOWN |
| Mission Context S1/S2 and manifest | `SHADOW_ONLY` | `fiofilter/mission_context*.py` | M15 S1/S2 docs and tests | UNKNOWN |
| ReadReceipt A/B harness | `EXPERIMENTAL` | `fiofilter/read_receipt_ab.py` | M14 protocol and tests | UNKNOWN |
| Explicit M15 App Server canary | `PAUSED` | `fiofilter/canary.py` | M15 canary/D1 docs and tests | UNKNOWN |
| Corpus/search characterization tools | `EXPERIMENTAL` | `fiofilter/corpus.py`, `fiofilter/search_corpus.py`, `scripts/extract_*.py` | M03 contracts and corpus tests | NO |
| Legacy census, reexposure and structural helpers | `PROVEN_SUPPORTING` | `fiofilter/context_census.py`, `fiofilter/reexposure.py`, `fiofilter/structural*.py` | retained imports, scripts and tests | UNKNOWN |
| M01–M16 reports and decision record | `HISTORICAL_ONLY` | `docs/`, `docs/DECISIONS.md` | append-only evidence chain | NO |
| JEV / continuity mechanism | `UNKNOWN` on canonical main | no canonical implementation or decision | no M17/KR1 evidence on this baseline | UNKNOWN |

`PROVEN_ACTIVE` means a supported, explicit library behavior now; it never means
autonomous delivery or production readiness. `PROVEN_SUPPORTING` is required
infrastructure whose authority remains bounded. `UNKNOWN` is retained rather
than removed because absence of a current dependency proof is not removal proof.

## What this baseline does and does not do

It deterministically classifies captured output; preserves protected evidence;
uses byte-verified, fail-to-RAW representations; keeps permitted RAW recoverable
under its stated contract; and offers explicit laboratory/shadow measurement.

It does **not** autonomously intercept Codex, suppress context, inject discovery
results, route T02 from generic text, claim provider-token/billing savings,
claim model-quality improvement, retain private cross-session content, integrate
Fio Handoff, or claim production readiness.

READREF active optimization is deferred. The canary implementation is paused:
diagnostic hardening is complete, but a future canary requires a separately
authorized mission and fresh evidence. Mission Context has no delivery authority;
canonical-reference provenance is not permission to hide text.

## Complexity and dogfooding

No dead or orphaned implementation is proven by the current tree. The older
corpus, reexposure and structural helpers retain direct tests, imports or
historical-evidence value; `UNKNOWN => KEEP`. Unmerged remote work is not
canonical evidence and is not adopted here.

The repository is ready for normal, conservative dogfooding: use the A–J router,
the explicit lab/shadow surfaces where a real mission supplies the required
metadata, and keep delivered content RAW unless an existing, scoped contract
proves otherwise. Observe natural work; do not manufacture multi-session tasks
or convert byte opportunities into token, economic or behavioural claims.

## Expansion gate

A new mechanism may enter active development only when a mission records all:

1. a real observed bottleneck;
2. evidence that current mechanisms do not adequately address it;
3. a falsifiable hypothesis;
4. consideration of a smaller solution;
5. expected value greater than added complexity; and
6. preservation of evidence and authority invariants.

Technology novelty, vendor demonstrations, an unmerged branch, capability alone
or repository-byte accounting alone are not sufficient. A mechanism can remain
parked indefinitely without indicating project failure.
