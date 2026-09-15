# FioFilter agent instructions

Read [AI-START-HERE.md](AI-START-HERE.md), [decisions](docs/DECISIONS.md),
[evidence contract](docs/EVIDENCE-CONTRACT.md) and real Git state before edits.
Python 3.9+. Repository: `phpedrogarcia-afk/FioFilter`.
Local Antigravity: `C:\Users\phped\Documents\FioFilter`.

## Mission discipline

V0 is an evidence engine and deterministic filter laboratory, not production
integration. Follow the current user mission; do not infer approval for M03.
Use a mission branch for substantial changes. Do not rewrite history, force-push,
merge without authorization, or modify unrelated repositories/global settings.

Do not install Codex hooks, modify `~/.codex`, install RTK/CCA, add an MCP server,
proxy, GUI, LLM pipeline or auto-learning. Donor references stay bounded to the
three documented in M01. Do not claim production readiness or measured mission
savings from a local compression ratio.

## Evidence and storage

AGGRESSIVE AT THE EXPLORATION BOUNDARY.
RIGOROUS AT THE EVIDENCE BOUNDARY.

- Inspect full input for protected evidence. Repetition alone never proves noise.
- UNKNOWN, nonzero exits and uncertain transformations must return RAW bytes.
- Profiles and modes never weaken invariants. Python profiles are canonical.
- Preserve inline-required facts, byte boundaries and occurrence requirements.
- Reject expansion and invalid/unreconstructable T01 representations.
- RAW recoverability is not proof of visible transform reversibility.
- RAW visibility never grants disk persistence. Default recovery is EPHEMERAL.
- Detected/declared sensitive input: DO_NOT_PERSIST, no persistent audit.
- Explicit disk writes require assessed non-sensitive material. Detection is not
  a universal secret/PII oracle. Never put actual credentials in fixtures or Git.
- Store blobs are no-clobber and hash-checked; do not silently repair corrupted
  blobs or overwrite malformed metadata. Missing content-only metadata may be
  reconstructed. No deletion/retention engine is authorized by this instruction.

M02-D001 supersedes the M01 unconditional write-before-transform instruction:
prepare an allowed disk or ephemeral reference before transforming. Sensitive
results stay RAW without an archive. M02-D005 makes audit persistence opt-in.

## Tests and claims

Write a material regression before a correctness fix. Run the original suite
before modifications and the canonical command after changes:

```bash
python -m pytest tests/ -v
```

Tests must use temporary directories; imports/default construction must not write
persistent files. Use seeded standard-library property-like tests when valuable.
Do not optimize test count or accept tests that permit every disposition.

Every transform needs distinct oracles for determinism, no expansion, inline
facts, exception fallback, RAW recovery, and its stated visible-representation
contract. JSON parse equality is insufficient evidence of consumer compatibility;
T02–T05 remain deferred until independently authorized.

Report PROVEN / PARTIALLY_PROVEN / CLAIMED_ONLY / FALSE / UNKNOWN with scope.
Prefer VERIFIED IN CURRENT TEST CORPUS to universal assertions. Raw/visible
bytes, estimates, actual supplied model tokens, turns, retrievals and transform
time are separate units. Check [safe frontiers](docs/SAFE-AGGRESSIVE-FRONTIER.md)
so evidence rigor does not turn the product into a general pass-through.

Record material decisions with ID, QUESTION, EVIDENCE, DECISION, WHY,
ALTERNATIVES_REJECTED and REVERSIBILITY. Preserve historical decisions and name
superseding entries explicitly. Commit and publish intended changes for GitHub
handoff; stop at the mission boundary.
