# FioFilter

**Evidence-aware context reduction for coding agents. V0 live-shadow observer; no active integration or production-readiness claim.**

> AGGRESSIVE AT THE EXPLORATION BOUNDARY.
> RIGOROUS AT THE EVIDENCE BOUNDARY.

The implemented surface is a Python API that accepts already captured bytes and
an M13 post-delivery Codex Web observation adapter. It does not intercept Codex,
run shell commands, install hooks, change outputs, or call a model.
M02 hardened the engine. M03 added and independently validated an offline corpus
method. M04 implements one lossless grouping transform for the exact validated
`RG_STANDARD_PATH_LINE_TEXT` grammar. Automatic engine routing remains disabled
until trusted structural producer evidence reaches the runtime.

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
A transformed engine result includes a versioned T01 representation, its RAW reference,
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

The twelve evidence classes remain. Current automatic T01 eligibility is intentionally
narrow: complete known NOISE grammar in every mode, and complete known PROGRESS
grammar in EXPLORE/BUILD. Unknown repeated sentences are not automatically noise.
Diagnostics, failures, credentials, authority, canonical state, machine data and
benchmarks remain RAW. Discovery and success summaries await their own consumer
contracts; they are [aggressive future frontiers](docs/SAFE-AGGRESSIVE-FRONTIER.md).

`T02_RG_STANDARD_GROUP_V1` is registered for explicit verified evaluation only.
It groups contiguous path runs, preserves every match and has an independent
byte-exact decoder. Generic `apply(content)`, all profiles and the engine decline
it because current runtime metadata cannot prove structurally grounded producer
identity. See the [M04 contract](docs/M04-RG-STANDARD-LOSSLESS-GROUPING.md).

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

M13 adds `FIO_EFFICIENCY_FEED_V1`. Exact token fields stay explicitly
`UNAVAILABLE` when Codex Web does not expose provider/runtime accounting; the
feed never promotes bytes/4 into actual usage. It stores hashes, counts and
repository-relative paths, never raw prompts, messages or file/tool contents.

M01 documented FioOS P3/P11/P13/P14 as historical workload evidence. That evidence
outranks donor marketing for the workload, but its source corpus is not bundled
and this repository does not independently reproduce those experiments. The
original M03 local sample also is not bundled. Its extractor-generated labels are
heuristic, not ground truth; see the [M03-R1 audit](docs/M03-CORPUS-REPORT.md).

## Corpus laboratory

Corpus schema v4 separates source bytes, detector screening, heuristic suggestions,
independently reviewed oracle labels and derived metrics. Extraction never creates
an oracle. Replay never feeds oracle sensitivity or required facts into FioFilter.
Safety/frontier comparisons and confusion matrices are partitioned by provenance.

Legacy M03 v3 corpora are rejected by default. Explicit
`M03_V3_AS_HEURISTIC` migration demotes their former `oracle_labels`; it does not
validate them. A detector no-match remains `DETECTOR_NO_MATCH`, not
`NON_SENSITIVE`. Real historical outputs remain local and outside Git.

M03-R4 physically verified Source A and authorized only
`RG_STANDARD_PATH_LINE_TEXT`. Source B is a historical report that was not
reproduced on the current local filesystem; its reported fingerprint differs,
but absence alone does not establish the physical relationship. The M03 local
27.82% candidate reduction is not a whole-mission or operational-token claim.

## Project map

- [AI orientation](AI-START-HERE.md), [agent instructions](AGENTS.md)
- [Architecture](docs/ARCHITECTURE.md), [evidence contract I1–I16](docs/EVIDENCE-CONTRACT.md)
- [Decisions, including explicit M01/M03 supersessions](docs/DECISIONS.md)
- [M02 audit and guarantee classifications](docs/M02-AUDIT.md)
- [M03-R1 corpus/oracle audit](docs/M03-CORPUS-REPORT.md)
- [M03-R2 local validation](docs/M03-R2-VALIDATION.md)
- [M03-R3 clean-search corpus specification](docs/M03-R3-CLEAN-SEARCH-CORPUS.md)
- [M03-R4 real search validation](docs/M03-R4-REAL-SEARCH-VALIDATION.md)
- [M04 lossless rg grouping contract](docs/M04-RG-STANDARD-LOSSLESS-GROUPING.md)
- [M13 Codex Web live-shadow contract](docs/M13-CODEX-WEB-LIVE-SHADOW.md)
- `fiofilter/profiles/*.py`: sole operational policy source; YAML duplicates removed
- `tests/`: synthetic regressions; `tests/corpus/`: executable schema and review protocol

[GitHub](https://github.com/phpedrogarcia-afk/FioFilter) is the handoff surface for
Codex Web and local Antigravity. M13 remains shadow-only: no read replacement,
automatic context selection, automatic T02, proxy, MCP or behavioral A/B treatment.
