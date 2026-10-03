# FioOS v0.1 consumer pilot evidence

**Mission:** `FIOFILTER-FIOOS-FIRST-CONSUMER-PILOT-001`
**Status:** local candidate evidence; not committed, pushed, merged, or published.

## Identity and dependency

- FioFilter base: `b740b7813c50d2a05a689041c5f4cb3b761cf394`.
- Candidate branch: `codex/fiofilter-fioos-first-consumer-pilot-20261002`.
- Public source: `https://github.com/phpedrogarcia-afk/fioos-core`.
- Dependency: Git submodule `vendor/fioos-core`, pinned to release `v0.1.0`,
  commit `04ea806b80995ff95b50fb0c8d232baa2148c20a`; no private FioOS source
  or vendored copy is used.

## Effect and pilot

The finite local A0 consumer admits catalogued external proposals, applies a
controller-created deterministic `ProjectPolicy`, and routes only the fixed
`fiofilter.work_item.emit` / `note.append` operation through the public
FioOS `RuntimeGateway` and `LocalNoteAdapter`. The adapter emits a structured
human-review proposal into the Git-ignored `fioos-outbox`; proposals do not
authorize implementation or modify FioFilter source.

The scenario plan contained 15 cases: 5 `VALID`, 9 `DENY`, and 1 `REPLAY`.
The first report's `authorized`, `denied`, and `replayed` totals came from those
scenario labels, not from classifying each receipt; they are not treated as
observed outcome counters. The corrected receipt-based run is recorded below.
No Git, network, cloud, or model call was made by the pilot execution;
FioFilter Python source hashes were unchanged.

- Run directory: `fioos-outbox/pilot-20261002T234252Z-0ac75286/`.
- Output: `notes.jsonl` (5 records).
- SHA-256: `d5de9f2e322a047ecc567c857679cefcd1f44db7d1f7b627dc7a81ec404647b1`.
- Each item is marked `PROPOSED_REQUIRES_HUMAN_REVIEW` and carries request/result
  correlation and the observed FioFilter base HEAD.

## Validation and utility

- Consumer integration tests: 16 passed.
- Focused pinned FioOS admission/Gateway tests: 8 passed (28 deselected).
- FioFilter full-suite run in the candidate worktree: 665 passed.
- Canonical-main baseline: 665 collected, 662 passed, 3 route/byte-accounting
  failures. A read-only EOL comparison found `docs/ARCHITECTURE.md` and
  `docs/TEST-STRATEGY.md` as CRLF in the canonical checkout and LF in the pilot
  worktree. Therefore the baseline and candidate full-suite runs are not a
  controlled same-EOL comparison; the three baseline failures are not
  attributed to this consumer change.
- GitHub CI: not run; no push was made.
- Utility: `USEFUL`. The five proposals map to documented, decision-relevant
  uncertainties (M20 quality, producer provenance, real-corpus replay, M06
  quality impact, and whole-mission economics). This is useful triage input,
  not proof that the proposals should be implemented.

## Claim boundary

This proves one finite local consumer path in the tested environment only. It
does not establish production security, continuous operation, durable replay,
multi-user safety, autonomous coding, shell/cloud execution, or permission to
write FioFilter `main`. Human review remains required for every proposal.

## Counter semantics follow-up

For `FIOFILTER-FIOOS-PR-EVIDENCE-COUNTERS-FIX-001`, the pilot now reports
planned scenarios separately from observed receipt outcomes. On the corrected
run at canonical FioFilter HEAD
`b740b7813c50d2a05a689041c5f4cb3b761cf394`, the plan was 5 valid, 9 deny, and
1 replay case. Receipts showed 6 correlated `ALLOW`/`SUCCEEDED` outcomes, 9
explicit `DENY`/`DENIED` outcomes with zero effect, 0 unknown outcomes, and 0
unexpected outcomes. Those six successful receipts corresponded to 5 unique
successful request/result pairs and 5 emitted artifacts. The receipt from the
planned `REPLAY` case carried the original pair, but replay is not a distinct
observed outcome in the receipt schema.

The receipt schema does not identify a replay as a distinct observed outcome,
so the pilot reports `planned_replay_cases` but deliberately has no
`observed_replayed` counter. The corrected run's ignored raw output was
`fioos-outbox/pilot-20261003T005639Z-8ddaae28/notes.jsonl` with SHA-256
`3059531c87fb75b50be4efce5d876a4113535bbdca7ed6f864b3bb4849cb1368`.

## Final candidate review

- A Windows directory junction could previously redirect `fioos-outbox`
  outside the repository. The consumer now rejects a resolved outbox base
  outside `repo_root`, and the pilot checks that boundary before creating its
  per-run directory. A focused Windows regression verifies both entry points
  reject the junction without creating an external artifact.
- The bounded final review also reproduced a TOCTOU escape in a disposable
  fixture: after consumer construction, replacing its run directory with a
  junction caused the fixed-path adapter append to land outside that fixture's
  repository. The adapter also uses a path check followed by a path-based open
  for `notes.jsonl`; neither sequence is race-resistant against another local
  process with write access to mutate the trusted outbox between validation
  and effect. This is outside the declared trusted-local, single-process v0.1
  envelope, not race-safe containment. The candidate does not claim protection
  against same-host concurrent filesystem tampering or multi-user operation.
- Consumer integration tests: 17 passed on Windows, including the junction
  regression.
- Pinned public FioOS tests: 36 passed from the exact submodule commit above.
- FioFilter full suite: 665 passed in the candidate worktree.
- Original bounded pilot: 15 scenarios (5 `VALID`, 9 `DENY`, 1 `REPLAY`); its
  old authorized/denied/replayed totals were scenario-derived, not observed
  receipt classifications. The corrected run and its receipt-based counters
  are documented above. Raw pilot outputs remain ignored and are not part of
  the candidate.
- The historical baseline comparison remains uncontrolled because line-ending
  behavior differed. Its three discrepancies are still `UNKNOWN`, not claimed
  as fixed by this candidate.
- Hosted GitHub CI was not run; no push is authorized. This remains a local
  candidate, not a production or release claim.
