# FioFilter agent instructions

Python 3.9+. Repository: `phpedrogarcia-afk/FioFilter`.

## Required bootstrap

Before acting:

1. Establish real Git state: branch, HEAD, `origin/main`, status and recent commits.
2. Read [AI-START-HERE.md](AI-START-HERE.md).
3. Select the task route there and load only its canonical evidence.
4. If required evidence is missing, contradictory or unavailable, stop or fail
   conservative. A router is discoverability, not evidence or authority.

Do **not** read the complete decision ledger or historical corpus by default.
Use the deterministic decision lookup in `AI-START-HERE.md`, then read only the
relevant sections and any directly referenced evidence. Cross-domain work loads
the union of the applicable routes.

## Constitutional invariants

AGGRESSIVE AT THE EXPLORATION BOUNDARY.
RIGOROUS AT THE EVIDENCE BOUNDARY.

- Evidence and capability never create authority. `INDEX/ROUTER != EVIDENCE OR
  AUTHORITY`; `RECOVERABLE != SAFE_TO_HIDE`.
- Preserve `EVIDENCE_LOSS=0` and all required inline facts, byte boundaries,
  ordering and occurrence requirements. Repetition alone never proves noise.
- UNKNOWN, nonzero exits, ambiguous producer metadata and unproven transforms
  remain conservative/RAW. Profiles and modes may restrict authority, never
  broaden it.
- RAW recovery means only what the returned persistence/reference contract
  proves. It is not visible reversibility, durability, permission to persist, or
  permission to suppress evidence.
- Default recovery is EPHEMERAL. Sensitive or declared-sensitive input is RAW /
  `DO_NOT_PERSIST`, with no persistent audit. Disk writes require explicit
  persistence plus assessed `NON_SENSITIVE`; detector no-match is not proof of
  safety. Never commit actual credentials or private payloads.
- Reject expansion and invalid or non-byte-reconstructable representations.
  Machine-data compatibility requires its own consumer contract.
- Mission Context is `SHADOW_ONLY`. READREF is OFF/paused. No active suppression,
  automatic context selection, automatic T02, hook, proxy, MCP daemon, GUI, LLM
  classifier, auto-learning, Fio Handoff integration or production activation is
  authorized by this file.
- FioFilter is a tested evidence engine and explicit laboratory, not a
  production-readiness claim. Local byte reduction is not provider-token,
  billing, Plus-quota or whole-mission saving.
- Preserve historical decisions and evidence unchanged and recoverable. New
  conclusions supersede explicitly; never rewrite history to simplify a claim.

## Execution discipline

Follow the current user mission. Work on a mission branch for material changes.
Do not force-push, rewrite Git history, merge without authorization, modify
unrelated repositories, or change global configuration.

Run the baseline before edits when code or executable policy may change. Add a
material regression before a correctness fix, then run:

```bash
python -m pytest tests/ -v
python -m compileall fiofilter scripts tests
git diff --check
```

Tests use temporary directories; imports and default construction must not make
persistent writes. Do not weaken meaningful coverage or accept tests that permit
every disposition. Report scope as PROVEN, PARTIALLY_PROVEN, CLAIMED_ONLY, FALSE
or UNKNOWN, and keep bytes, estimates, actual supplied tokens, turns, retrievals
and timings as distinct units.

Record material decisions with ID, QUESTION, EVIDENCE, DECISION, WHY,
ALTERNATIVES_REJECTED and REVERSIBILITY. Commit and publish only intended
changes, verify CI for the exact SHA, do not merge automatically, and stop at the
mission boundary.
