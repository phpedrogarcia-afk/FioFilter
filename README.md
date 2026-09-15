# FioFilter

**Evidence-aware context reduction for coding agents. V0 laboratory; no integration or production-readiness claim.**

> AGGRESSIVE AT THE EXPLORATION BOUNDARY.
> RIGOROUS AT THE EVIDENCE BOUNDARY.

The implemented surface is a Python API that accepts already captured bytes.
It does not intercept Codex, run shell commands, install hooks, or call a model.
M02 audits and hardens M01; it adds no new compression mechanism.

## Development

Python 3.9+; no external runtime dependencies.

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/ -v
```

The pinned test dependency and canonical command run on Windows and Linux in
[CI](.github/workflows/tests.yml). See [test limits](docs/TEST-STRATEGY.md).

## Current behavior

```python
from fiofilter.engine import process
from fiofilter.raw_store import RawStore
from fiofilter.types import ToolResult

raw = b"Building... [   OK   ]\n" * 100
result = process(ToolResult(raw))
assert RawStore().read(result.raw_ref) == raw
```

This example creates no persistent files. Recovery bytes belong to the returned
reference and disappear when that reference is released; no global archive is built.
A transformed result includes a versioned T01 representation, its RAW reference,
SHA-256, evidence class, decision, metrics and an in-memory audit record.

Evidence class and persistence are independent. `RAW` means visible bytes are
unchanged, **not permission to write them to disk**. The default is `EPHEMERAL`.
Sensitive input detected or declared by the caller uses `DO_NOT_PERSIST`: RAW
visibility, no archive reference, no persistent audit log. This is not redaction
and cannot control caller logging, OS swap, or memory dumps.

Persistent storage requires both `persistence=Persistence.PERSIST` and
`sensitivity=Sensitivity.NON_SENSITIVE` on `ToolResult`. A detector can veto
that request. Detection is a backstop, not proof that arbitrary data contains no
secrets or personal information. The low-level `RawStore.write` method is an
explicit disk-write API for caller-assessed non-sensitive data.

## Reduction and preservation

The twelve evidence classes remain. Current T01 eligibility is intentionally
narrow: complete known NOISE grammar in every mode, and complete known PROGRESS
grammar in EXPLORE/BUILD. Unknown repeated sentences are not automatically noise.
Diagnostics, failures, credentials, authority, canonical state, machine data and
benchmarks remain RAW. Discovery and success summaries await their own consumer
contracts; they are [aggressive future frontiers](docs/SAFE-AGGRESSIVE-FRONTIER.md).

All input bytes are inspected, including diagnostic tails. Profiles only restrict
core policy. A pipeline exception, invalid transform, missing inline fact,
non-reducing output or failed visible reconstruction returns the original bytes.
These statements describe structural guards and **VERIFIED IN CURRENT TEST CORPUS**
behavior; they do not establish universal semantic classification accuracy.

RAW recovery and visible transform reversibility are separate checks. T01 v2 has
both; a future transform may not claim reversibility merely because a RAW store exists.

## Metrics

Raw and visible byte counts are exact. `utf8_bytes_div_4_ESTIMATE` is a rough
local estimate, never a billed/model token count. Actual model tokens, turns,
corrective retrievals and recovery counts are separately supplied observations;
`None` means unmeasured. No whole-mission savings have been measured for FioFilter.

M01 documented FioOS P3/P11/P13/P14 as historical workload evidence. That evidence
outranks donor marketing for the workload, but its source corpus is not bundled
and M02 does not independently reproduce those experiments. See the historical
[donor autopsy](docs/DONOR-AUTOPSY.md).

## Project map

- [AI orientation](AI-START-HERE.md), [agent instructions](AGENTS.md)
- [Architecture](docs/ARCHITECTURE.md), [evidence contract I1–I16](docs/EVIDENCE-CONTRACT.md)
- [Decisions, including explicit M01 supersessions](docs/DECISIONS.md)
- [M02 audit and guarantee classifications](docs/M02-AUDIT.md)
- `fiofilter/profiles/*.py`: sole operational policy source; YAML duplicates removed
- `tests/`: synthetic regression corpus; `tests/corpus/`: historical import specification only

[GitHub](https://github.com/phpedrogarcia-afk/FioFilter) is the handoff surface for
Codex Web and local Antigravity. M02 stops before M03 or transform expansion.
