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

The run contained 15 scenarios: 5 authorized proposals, 9 denials, and 1 exact
same-instance replay. It produced 5 unique artifacts, 0 duplicate artifacts,
0 unknown outcomes, 0 failures, and 0 observed authority bypasses. No Git,
network, cloud, or model call was made by the pilot execution; FioFilter Python
source hashes were unchanged.

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
- Final bounded pilot: 15 proposals, 5 authorized, 9 denied, 1 replay; 5
  artifacts, 0 duplicates, 0 unknown results, 0 failures, and 0 observed
  authority bypasses. FioFilter source hashes were unchanged. Output SHA-256:
  `bb7fe56f38d55897f7ebee6aed81c9a094df84fc86307704617e078d9bb96978`.
  The raw pilot output is ignored and is not part of the candidate.
- The historical baseline comparison remains uncontrolled because line-ending
  behavior differed. Its three discrepancies are still `UNKNOWN`, not claimed
  as fixed by this candidate.
- Hosted GitHub CI was not run; no push is authorized. This remains a local
  candidate, not a production or release claim.
