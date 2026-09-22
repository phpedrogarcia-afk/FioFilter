# FioFilter current state and task router

This file is the compact orientation after `AGENTS.md`. It is not a substitute
for task-specific evidence.

```text
DEFAULT_BOOTSTRAP_DOCUMENTS=AGENTS.md,AI-START-HERE.md
MISSION_CONTEXT=SHADOW_ONLY
READREF_CANARY=OFF_PAUSED
ACTIVE_SUPPRESSION=NO
PRODUCTION_READY=NO
FIO_HANDOFF_INTEGRATION=NO
```

## What FioFilter is now

FioFilter V0 is a Python evidence engine and deterministic, explicit laboratory.
It classifies captured output, preserves protected evidence, stores permitted RAW
content with integrity checks, and evaluates bounded lossless representations.
It has no production interception path.

Implemented and testable components include T01 consecutive-line folding,
explicit `T02_RG_STANDARD_GROUP_V1` evaluation behind producer-metadata gates,
BM25 discovery experiments, read-reexposure/receipt laboratories, payload-free
Codex Web shadow telemetry, and the `FIO_EFFICIENCY_FEED_V1` schema. Implemented
does not mean automatically authorized.

M15-S2/R1 is complete. `FIO_MISSION_CONTEXT_MANIFEST_V1` binds exact mission
bytes to compact author dispositions and repository-verifiable canonical ranges.
Its manifest is canonical LF across Windows/Linux. Mission Context still only
measures shadow candidates and never changes delivered prompts.

## Authority state

| State | Current boundary |
| --- | --- |
| Active laboratory | Explicit local engine/CLI calls and deterministic tests; RAW-first defaults remain. |
| Shadow only | Codex Web observer, discovery/reexposure measurement and Mission Context measurement. Observed output is never replaced. |
| Paused/off | READREF controlled canary. Prior canary evidence does not authorize another run. |
| Not authorized | Active suppression, automatic context selection, automatic T02, hooks, proxy, MCP daemon, LLM classifier, Fio Handoff bridge, production integration or production-readiness claims. |

Always preserve the constitutional invariants in `AGENTS.md`. In particular,
capability is not authority, UNKNOWN remains conservative, sensitive persistence
is fail-closed, and recoverability is not permission to hide content.

## Task router / deterministic review matrix

Choose the matching row before opening deeper material. Read the listed minimum;
add another route only when the task actually crosses that domain.

| Route | Task class or scenario | Minimum canonical read set |
| --- | --- | --- |
| A | Core evidence, transform correctness, RAW/recovery semantics | `docs/EVIDENCE-CONTRACT.md`; the specific transform specification (for T02, `docs/M04-RG-STANDARD-LOSSLESS-GROUPING.md`); affected code/tests. Add `docs/TEST-STRATEGY.md` only for coverage/oracle changes. |
| B | Persistence, privacy, sensitivity or RAW-store change | Relevant sections of `docs/ARCHITECTURE.md` and `docs/EVIDENCE-CONTRACT.md`; `fiofilter/sensitivity.py`, `fiofilter/raw_store.py` and their tests. Use selected decision sections if changing policy. |
| C | Corpus, benchmark or evaluation change | `tests/corpus/README.md`; `docs/M03-R3-CLEAN-SEARCH-CORPUS.md`; add `docs/M03-R4-REAL-SEARCH-VALIDATION.md` only for real-search evidence; affected corpus code/tests. Earlier M03 reports are provenance, not default input. |
| D | Discovery, ranking or search-output change | `docs/M11-DISCOVERY-RUNTIME-SHADOW.md`; add `docs/M10-DISCOVERY-RANKING-REFINEMENT.md` for ranking and `docs/M04-RG-STANDARD-LOSSLESS-GROUPING.md` for T02 representation; affected code/tests. |
| E | Codex Web live-shadow or Efficiency Feed change | `docs/M13-CODEX-WEB-LIVE-SHADOW.md`; `fiofilter/codex_web_shadow.py`, `fiofilter/efficiency_feed.py` and affected tests. |
| F | READREF, recovery or local canary change | `docs/M15-READREF-CONTROLLED-CANARY.md` and `docs/M15-D1-CANARY-DIAGNOSTIC-HARDENING.md`; canary/read-receipt code and tests. Add M14 behavioral evidence only for A/B claims. READREF remains paused unless a new mission explicitly authorizes a run. |
| G | Mission Context or instruction-reexposure change | `docs/M15-MISSION-CONTEXT-CONTRACT.md` and `docs/M15-S2-MISSION-CONTEXT-MANIFEST.md`; mission-context code/tests. Add `docs/M15-S1-MISSION-CONTEXT-REAL-SHADOW.md` only for S1 measurement provenance. |
| H | Architecture proposal or major new mechanism | `docs/ARCHITECTURE.md`, `docs/EVIDENCE-CONTRACT.md`, `docs/SAFE-AGGRESSIVE-FRONTIER.md`, `docs/TEST-STRATEGY.md`, then relevant decision sections. Inclusion in a frontier is not authorization. |
| I | Historical decision, contradiction or supersession investigation | Use the decision lookup below; read only matching ledger sections, referenced superseding entries and directly relevant historical evidence. Expand only when the chain requires it. |
| J | Ordinary documentation-only maintenance | Target document and directly linked canonical sources needed to verify the edit. Check links and factual scope. No ledger or historical corpus read is required by default. |

The required scenario checks map deterministically as follows: transform change
→ A; sensitive storage → B; corpus/evaluation → C; READREF canary → F; Mission
Context → G; architecture proposal → H; supersession question → I; ordinary
documentation edit → J.

## Decision ledger lookup

`docs/DECISIONS.md` remains the complete append-only historical ledger. It is not
a default full read. Discover headings cheaply:

```bash
rg -n '^## ' docs/DECISIONS.md
```

Then locate an exact ID/topic and read only that section plus any explicitly
referenced predecessor or superseding entry:

```bash
rg -n 'M15-S2-D001|supersed' docs/DECISIONS.md
```

Use a mission-specific pattern; the example is not a standing requirement to
read M15. If the relevant chain cannot be established, stop or report UNKNOWN
rather than silently treating the index as evidence.

## Ordinary workflow

1. Confirm real Git state and clean/dirty scope.
2. Select route(s) above and load their minimum evidence.
3. Run the relevant baseline before executable changes.
4. Implement only the authorized delta and preserve RAW/fail-closed behavior.
5. Run relevant tests, the full suite, compileall and `git diff --check`.
6. Record material decisions without altering prior entries; publish a reviewable
   branch and verify CI for the exact SHA. Do not merge automatically.

Historical M01–M15 reports remain canonical and recoverable under `docs/`; they
are loaded through routes C, D, E, F, G or I, not re-exposed to every mission.
