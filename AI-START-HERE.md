# FioFilter orientation

V0: an implemented Python evidence engine and deterministic T01 laboratory.
M01 created code, M02 hardened it, and M03-R1/R2/R3 hardened the offline corpus method.
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
- T01 v2 only: exact consecutive-line counts/boundaries and a strict decoder.
- In-memory audit on every valid byte result; explicit optional JSONL audit.
- Exact byte metrics, labeled byte-based token estimates, optional externally
  supplied model tokens/turns/retrieval/recovery observations.
- Corpus schema v4 with distinct detector screening, heuristic suggestions,
  independently reviewed oracle provenance and label-scoped replay metrics.
- A separate M03 search-corpus laboratory that fingerprints the local source and
  characterizes two narrow ripgrep grammars with byte-exact reconstruction.
- Synthetic tests and minimal Windows/Linux CI. See `docs/M02-AUDIT.md` for evidence.

## What does not exist

T02 template folding, T03 PASS aggregation, T04 JSON minification, T05 delta,
batch execution, a Git-bundled original FioOS corpus, corrective-retrieval
prediction and whole-mission A/B measurement remain deferred. The fingerprinted
clean-search local run, independent grammar review and M04 selection are not
complete. An API processing already captured
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
its inclusion in that list. R2's 193 apparent `rg` candidates are scoped to one
local artifact whose relationship to an older same-session-ID artifact is
`UNKNOWN`. Do not start M04 from either the historical ranking or that observation.

Corpus replay must use source data only as engine input. Never inject oracle
sensitivity or required facts into the subject under test. Detector no-match is
not a non-sensitive assessment. Use only `ORACLE:*` metric scopes for reviewed
claims; `HEURISTIC:*` scopes are diagnostic. Legacy v3 input requires explicit
`M03_V3_AS_HEURISTIC` demotion.
