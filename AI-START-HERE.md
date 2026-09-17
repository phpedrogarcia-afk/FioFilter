# FioFilter orientation

V0: an implemented Python evidence engine and deterministic transform laboratory.
M01 created code, M02 hardened it, M03 validated the corpus method, and M04
implements one lossless rg grouping transform behind a producer-metadata gate.
No Codex integration, MCP, hooks, proxy, GUI, LLM or automatic learning exists.

## Start here

1. Inspect branch, HEAD, origin/main, status, recent commits and `AGENTS.md`.
2. Read `docs/DECISIONS.md` including M02/M03-R1 supersessions, then the evidence contract.
3. Run `python -m pytest tests/ -v` before code changes.
4. Work on a mission branch; publish reviewable state through GitHub.

## What exists

- Twelve evidence classes and deterministic full-input signal detection.
- Core policy in `fiofilter/profiles/default.py`; Python overlays can only restrict it.
- Stateless per-call EXPLORE/BUILD/PROVE. NOISE remains eligible in PROVE.
- Orthogonal `Sensitivity` and `Persistence` enums. Default EPHEMERAL recovery;
  sensitive results are RAW/DO_NOT_PERSIST without archive or persistent log.
- Explicit SHA-256 disk store with no-clobber publication, integrity checking and
  content-only metadata. No index or automatic retention/deletion engine.
- T01 v2: engine-routed exact consecutive-line folding with a strict decoder.
- `T02_RG_STANDARD_GROUP_V1`: explicit verified evaluation only; contiguous-run
  grouping and independent exact decoder, with automatic routing disabled.
- In-memory audit on every valid byte result; explicit optional JSONL audit.
- Exact byte metrics, labeled byte-based token estimates, optional externally
  supplied model tokens/turns/retrieval/recovery observations.
- Corpus schema v4 with distinct detector screening, heuristic suggestions,
  independently reviewed oracle provenance and label-scoped replay metrics.
- A separate M03 search-corpus laboratory that fingerprints the local source and
  characterizes two narrow ripgrep grammars with byte-exact reconstruction.
- Synthetic tests and minimal Windows/Linux CI. See `docs/M02-AUDIT.md` for evidence.

## What does not exist

The legacy T02 template-folding proposal, T03 PASS aggregation, T04 JSON
minification, T05 delta, batch execution, a Git-bundled original FioOS corpus,
automatic rg routing, corrective-retrieval prediction and whole-mission A/B
measurement remain deferred. An API processing already captured
output cannot recover bytes truncated by its upstream caller.

## Decisions and current limits

Read `docs/ARCHITECTURE.md`, `docs/EVIDENCE-CONTRACT.md`, `docs/TEST-STRATEGY.md`,
`docs/M02-AUDIT.md`, `docs/M03-CORPUS-REPORT.md`,
`docs/M03-R2-VALIDATION.md`, `docs/M03-R3-CLEAN-SEARCH-CORPUS.md` and
`docs/SAFE-AGGRESSIVE-FRONTIER.md`. `docs/DECISIONS.md` preserves historical
decisions and explicitly supersedes invalid M03 claims. `docs/DONOR-AUTOPSY.md`
is historical M01 evidence, not a fresh upstream audit or executable specification.

Detection cannot prove absence of arbitrary secrets/PII. Caller-assessed
NON_SENSITIVE plus explicit PERSIST is a storage decision, never permission to
compress protected evidence. Do not describe RAW recovery as guaranteed for
DO_NOT_PERSIST or after a returned ephemeral reference has been discarded.

Current tests establish behavior in their corpus, not universal classification
accuracy. Local reduction is not measured whole-mission savings. Future
aggressive reduction candidates are recorded explicitly; none is authorized by
its inclusion in that list. M03-R4 authorizes only
`RG_STANDARD_PATH_LINE_TEXT`. Source A is verified; Source B is historical and
not currently reproduced. Reported fingerprints differ, while the physical
relationship remains `UNKNOWN` without Source B bytes.

Corpus replay must use source data only as engine input. Never inject oracle
sensitivity or required facts into the subject under test. Detector no-match is
not a non-sensitive assessment. Use only `ORACLE:*` metric scopes for reviewed
claims; `HEURISTIC:*` scopes are diagnostic. Legacy v3 input requires explicit
`M03_V3_AS_HEURISTIC` demotion.

## V0 Explicit Lab Status (M12)

FioFilter V0 integrates proven offline components behind one explicit local laboratory interface:
- CLI: `python -m fiofilter status`
- Full reference: [V0-EXPLICIT-LAB.md](docs/V0-EXPLICIT-LAB.md)
- Project Status: `V0_EXPLICIT_LAB_COMPLETE`
- Discovery & Reexposure Lanes: `READY_FOR_LIVE_CODEX_SHADOW`
- Default behavior remains strict RAW-first; no automatic hooks, proxies, MCP daemons, or read suppression exist.
