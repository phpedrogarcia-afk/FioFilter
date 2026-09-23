# FioFilter current state and task router

This file is the compact orientation after `AGENTS.md`. It is not a substitute
for task-specific evidence.

```text
DEFAULT_BOOTSTRAP_DOCUMENTS=AGENTS.md,AI-START-HERE.md
MISSION_CONTEXT=SHADOW_ONLY
READREF_CANARY=OFF_PAUSED
EXPLICIT_ACTIVE_CONTEXT_CANARY=M20_FIOOS_OPT_IN_ONLY
AUTOMATIC_ACTIVE_SUPPRESSION=NO
PRODUCTION_READY=NO
FIO_HANDOFF_INTEGRATION=NO
```

## What FioFilter is now

FioFilter V0 is a Python evidence engine and deterministic, explicit laboratory.
It classifies captured output, preserves protected evidence, stores permitted RAW
content with integrity checks, and evaluates bounded lossless representations.
It has no production interception path.

M20 adds one operator-invoked `prepare-context` command for the exact FioOS
final-review canary. It requires an assessed non-sensitive contract, exact Git
and source proofs, and preserves critical facts inline. Failed selection proofs
expand to full documents; this is not automatic routing or production use.

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
| Explicit active canary | Operator-invoked FioOS `prepare-context` package only; quality proof pending real mission. |
| Shadow only | Codex Web observer, discovery/reexposure measurement and Mission Context measurement. Observed output is never replaced. |
| Paused/off | READREF controlled canary. Prior canary evidence does not authorize another run. |
| Not authorized | General/automatic suppression, automatic context selection, automatic T02, hooks, proxy, MCP daemon, LLM classifier, Fio Handoff bridge, production integration or production-readiness claims. |

Always preserve the constitutional invariants in `AGENTS.md`. In particular,
capability is not authority, UNKNOWN remains conservative, sensitive persistence
is fail-closed, and recoverability is not permission to hide content.

## Task router / deterministic review matrix

Choose a route before opening deeper material. `FULL_DOCUMENT` means the complete
path; `SECTION_SET` means the exact headings declared below; and
`OPTIONAL_ON_DEMAND` is outside the initial working set. Affected source/tests are
task inputs, not documentation-economics bytes.

| Route | Task class or scenario | Initial requirement |
| --- | --- | --- |
| A | Core evidence, transform correctness, RAW/recovery | `FULL_DOCUMENT` `docs/EVIDENCE-CONTRACT.md` |
| B | Persistence, privacy, sensitivity, RAW store | `SECTION_SET B` below |
| C | Corpus, benchmark, evaluation | `FULL_DOCUMENT` `tests/corpus/README.md`, `docs/M03-R3-CLEAN-SEARCH-CORPUS.md` |
| D | Discovery, ranking, search output | `FULL_DOCUMENT` `docs/M11-DISCOVERY-RUNTIME-SHADOW.md` |
| E | Codex Web live shadow, Efficiency Feed | `FULL_DOCUMENT` `docs/M13-CODEX-WEB-LIVE-SHADOW.md` |
| F | READREF, recovery, local canary | `SECTION_SET F` below; READREF remains paused without explicit authority |
| G | Mission Context, instruction reexposure | `SECTION_SET G` below |
| H | Architecture proposal, major mechanism | `SECTION_SET H` below plus relevant decision sections |
| I | Historical contradiction or supersession | `SECTION_SET` matching decision IDs and referenced predecessor/superseding sections; use the decision lookup below |
| J | Ordinary documentation-only maintenance | `FULL_DOCUMENT` target and directly linked evidence needed to verify it |

Exact section sets (titles omit only the Markdown `#` prefix):

```text
B docs/ARCHITECTURE.md :: Pipeline | Sensitivity and persistence | Disk RAW store | Metadata, batching and truncation | Economics
B docs/EVIDENCE-CONTRACT.md :: I1 — RAW immutability | I2 — Transform linkage | I3 — Byte-exact RAW recovery | I5 — Unknown defaults to RAW | I6 — Failure preservation | I7 — Authority, security and sensitivity | I13 — Source/batch identity | I16 — Audit without secret harvesting
F docs/M15-READREF-CONTROLLED-CANARY.md :: Status and boundary | Delivery and recovery | Economics and telemetry | D1 diagnostic hardening
F docs/M15-D1-CANARY-DIAGNOSTIC-HARDENING.md :: Tool and record contracts | Structural trace and privacy | Unchanged safety and economics | Validation and limits
G FULL_DOCUMENT docs/M15-MISSION-CONTEXT-CONTRACT.md
G docs/M15-S2-MISSION-CONTEXT-MANIFEST.md :: Status | Compact schema | Economics and durable record | Limits
H docs/ARCHITECTURE.md :: Pipeline | Evidence policy and profiles | Sensitivity and persistence | Metadata, batching and truncation | Economics
H FULL_DOCUMENT docs/EVIDENCE-CONTRACT.md
H FULL_DOCUMENT docs/SAFE-AGGRESSIVE-FRONTIER.md
H docs/TEST-STRATEGY.md :: Oracles | CI and portability | Limitations
```

`OPTIONAL_ON_DEMAND`: A loads the affected transform specification and test
strategy when relevant; C loads R4/earlier M03 provenance; D loads M10 or M04;
F loads `Historical C2 result`/M14 evidence; G loads S2 dogfood/S1 provenance;
H loads component-specific sections. Any route loads complete files on fallback.
Frontier inclusion is not authority.

The required scenario checks map deterministically as follows: transform change
→ A; sensitive storage → B; corpus/evaluation → C; READREF canary → F; Mission
Context → G; architecture proposal → H; supersession question → I; ordinary
documentation edit → J.

## Section protocol

Headings are exact repository evidence addresses, not summaries. Locate and emit
their bounded source bytes with the read-only helper, repeating `--heading`:

```bash
python scripts/section_working_set.py docs/ARCHITECTURE.md \
  --heading 'Pipeline' --heading 'Economics'
```

A section starts at its heading and ends immediately before the next heading of
the same or higher level, or EOF. Multiple ranges are emitted in document order;
overlapping/nested ranges count once. `--measure` emits byte accounting instead
of content.

The helper returns the **complete document** and reports
`FULL_DOCUMENT_FALLBACK` when a heading is missing, duplicated, or
the Markdown is not valid UTF-8. Stop if the required path itself is unavailable.
Also expand to the complete document whenever evidence crosses selected sections,
a contradiction appears, or task scope widens. Never silently omit evidence or
treat a successful lookup as proof/authority.

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
   branch and verify CI for the exact SHA. Before a canonical `main` promotion,
   re-check the active remote `FioFilter Canonical Main Guard`, then use only an
   exact, already-tested `git merge --ff-only <SHA>` promotion. Do not merge
   automatically or use `gh pr merge` for an exact-SHA promotion.

Historical M01–M15 reports remain canonical and recoverable under `docs/`; they
are loaded through routes C, D, E, F, G or I, not re-exposed to every mission.
