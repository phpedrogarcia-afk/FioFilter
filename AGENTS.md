# AGENTS.md — FioFilter Agent Instructions

## Identity

FioFilter is an **evidence-aware context reduction layer** for coding agents.
It is **not** a generic compressor.

Workspace: `C:\Users\phped\Documents\FioFilter`  
GitHub: `https://github.com/phpedrogarcia-afk/FioFilter`  
Language: Python 3.9+

---

## Mission Boundary

**Current stage: V0 — Foundation**

V0 scope is explicitly limited. Read [AI-START-HERE.md](AI-START-HERE.md)
before starting any task.

---

## Absolute Non-Goals in V0

Do NOT under any circumstances:
- Integrate hooks into Codex
- Modify `~/.codex` or any global agent configuration
- Modify any project other than FioFilter
- Install RTK or CCA
- Depend on RTK or CCA at runtime
- Build an MCP server, proxy, GUI, or LLM summarizer
- Implement semantic summarization or call any AI/LLM
- Claim production readiness

---

## Core Philosophy

```
AGGRESSIVE AT THE EXPLORATION BOUNDARY.
RIGOROUS AT THE EVIDENCE BOUNDARY.
```

These are not in tension. They operate in different domains.

---

## Evidence Invariants — READ BEFORE ANY IMPLEMENTATION

All implementation must respect I1–I16 in [docs/EVIDENCE-CONTRACT.md](docs/EVIDENCE-CONTRACT.md).

**Hard rules that must never be violated:**

- **I1**: RAW output is immutable once persisted. Never modify a stored RAW entry.
- **I3**: RAW recovery must be byte-exact (SHA-256 verified).
- **I4**: Critical inline-required facts may NEVER be removed, even with a `raw_ref` present.
- **I5**: UNKNOWN evidence class → RAW, always.
- **I9**: A transform that expands output loses to RAW. Return RAW instead.
- **I11**: No AI/LLM in V0 classification or transform path.

---

## Decision Order

When making any implementation decision:

1. Check [docs/DECISIONS.md](docs/DECISIONS.md) — is this already decided?
2. Check [docs/EVIDENCE-CONTRACT.md](docs/EVIDENCE-CONTRACT.md) — does this violate an invariant?
3. Check [docs/DONOR-AUTOPSY.md](docs/DONOR-AUTOPSY.md) — has a donor already explored this?
4. Write a test first (see [docs/TEST-STRATEGY.md](docs/TEST-STRATEGY.md))
5. Implement the minimal version
6. Record new decisions in [docs/DECISIONS.md](docs/DECISIONS.md)

---

## What Counts as Evidence

The following are **not** interchangeable metrics:

| Metric | What it measures |
|---|---|
| `raw_bytes` | Actual content size |
| `visible_bytes` | What the model sees |
| `raw_token_estimate` | Estimated tokens in RAW |
| `visible_token_estimate` | Estimated tokens in visible output |
| `transform_duration_ms` | Latency cost |
| `model_turns` | Whole-mission cost unit |
| `corrective_retrievals` | Re-fetch cost |

Never conflate these. Never claim a local byte reduction is a whole-mission saving.

---

## Working with the RAW Store

- Default location: `~/.fiofilter/raw/` (outside the repo)
- Always write RAW **before** attempting any transform
- Content-addressable by SHA-256
- Never delete entries in V0
- Test recovery with SHA-256 verification

---

## Fail-Open Rule

If any step in the decision pipeline produces an exception, validation failure,
or ambiguous result: **return RAW**. Always. No exceptions.

---

## Taxonomy Quick Reference

| Class | EXPLORE | BUILD | PROVE |
|---|---|---|---|
| NOISE | TRANSFORM | TRANSFORM | TRANSFORM |
| DISCOVERY | TRANSFORM | TRANSFORM | RAW |
| PROGRESS | TRANSFORM | TRANSFORM | RAW |
| SUCCESS_SUMMARY | TRANSFORM | TRANSFORM | RAW |
| DIAGNOSTIC | TRANSFORM | RAW | RAW |
| FAILURE | RAW | RAW | RAW |
| CANONICAL_STATE | RAW | RAW | RAW |
| MACHINE_DATA | RAW\* | RAW\* | RAW |
| AUTHORITY | RAW | RAW | RAW |
| SECURITY | RAW | RAW | RAW |
| BENCHMARK | RAW | RAW | RAW |
| UNKNOWN | RAW | RAW | RAW |

\* Lossless-only transforms (e.g., JSON minification) permitted if machine validity verified.

---

## Test Requirements

Every new transform must have:
- A round-trip test: `recover(transform(x)) == x` byte-for-byte
- A no-expansion test: `len(transform(x)) < len(x)` or disposition is RAW
- A fail-open test: exception in transform → RAW returned
- A protected-fact test: inline-required facts present in output

Run tests before and after every change:
```bash
python -m pytest tests/ -v
```
