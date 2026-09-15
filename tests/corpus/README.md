# Corpus Test Harness

This directory contains the regression corpus harness and schema for FioFilter.

## Status

**V0 / M03**: Executable corpus harness implemented in `fiofilter.corpus`.
Laboratory extraction utility implemented in `scripts/extract_codex_corpus.py`.
Evaluation runner implemented in `scripts/run_corpus_evaluation.py`.

**Privacy and Safety Boundary**:
Raw historical user session data and Tool Results are **never committed to Git**.
Real extracted workload samples are stored locally outside the repository (e.g. `~/.fiofilter/corpus/`).
This repository contains **only synthetic, non-sensitive test fixtures** (`fixtures/synthetic_corpus.jsonl`).

---

## Corpus Entry Schema (v3)

Corpus files are JSONL files where each non-empty line is a JSON object with this structure:

```json
{
  "entry_id": "FIOOS-REAL-001",
  "source_data": {
    "provenance": "session:01a02f96-42a2-7a80-b8bc-6d066d0e322f:call_id:call_123",
    "command": "git status --short --branch",
    "exit_code": 0,
    "stdout_stderr": "combined",
    "content_type_hint": "text",
    "byte_length": 154,
    "truncated": false,
    "raw_content_b64": "T24gYnJhbmNoIG1haW4K...",
    "raw_ref_path": null
  },
  "oracle_labels": {
    "evidence_class": "CANONICAL_STATE",
    "sensitivity": "NOT_SENSITIVE",
    "transform_eligibility": "RAW_REQUIRED",
    "inline_required_facts": [
      "On branch main"
    ],
    "oracle_rationale": "Git status represents canonical repository state and must remain RAW.",
    "missed_opportunity_category": null
  },
  "tags": [
    "fioos",
    "git",
    "real_workload"
  ]
}
```

### Key Schema Elements

1. **Source Data**:
   - `provenance`: Originating session or tool call identifier.
   - `command`: The command string executed.
   - `exit_code`: Numeric exit code.
   - `stdout_stderr`: Stream distinction (`stdout`, `stderr`, `combined`, `file`).
   - `raw_content_b64`: Base64-encoded raw bytes (for synthetic fixtures or self-contained samples).
   - `raw_ref_path`: External filesystem path to raw bytes (outside repository).

2. **Oracle Labels** (Independent of FioFilter):
   - `evidence_class`: Ground-truth evidence class.
   - `sensitivity`: `NOT_SENSITIVE`, `SENSITIVE_SECRET`, `SENSITIVE_PII`, or `UNKNOWN`.
   - `transform_eligibility`: `SAFE_TO_REDUCE`, `RAW_REQUIRED`, or `UNKNOWN`.
   - `inline_required_facts`: Critical facts that must remain visible inline.
   - `missed_opportunity_category`: Candidate bucket when `SAFE_TO_REDUCE` was missed (`DUPLICATED_HEADERS`, `REPETITIVE_PROGRESS`, `KNOWN_SUCCESS_RECORDS`, `DIRECTORY_OR_PATH_REDUNDANCY`, `KNOWN_BOILERPLATE`, `STRUCTURED_BUT_CONSUMER_SPECIFIC`, `OTHER`).

3. **Derived Metrics** (Generated during replay):
   - `predicted_evidence_class`, `predicted_disposition`, `predicted_sensitivity`, `raw_bytes`, `visible_bytes`, `raw_token_estimate`, `visible_token_estimate`, `safety_classification`.

---

## Executable Usage

### 1. Ingest / Replay Corpus in Python

```python
from fiofilter.corpus import load_corpus, replay_corpus
from fiofilter.types import Mode

entries = load_corpus("C:/Users/user/.fiofilter/corpus/m03_fioos_sample_v1.jsonl")
evaluated, summary = replay_corpus(entries, mode=Mode.BUILD, profile_id="fioos")

print(f"Total entries: {summary.total_entries}")
print(f"Dangerous false transform eligibility: {summary.dangerous_false_transform_eligibility}")
print(f"Safe opportunities missed: {summary.safe_opportunity_missed}")
print(f"Local byte reduction: {summary.local_byte_reduction_pct}%")
```

### 2. Extract Real Sample from Codex Rollout

```bash
python scripts/extract_codex_corpus.py \
    --session "C:/Users/user/.codex/sessions/.../rollout-....jsonl" \
    --output "C:/Users/user/.fiofilter/corpus/m03_fioos_sample_v1.jsonl" \
    --sample-size 50 \
    --project-tag "FIOOS"
```

### 3. Evaluate Corpus via CLI Runner

```bash
python scripts/run_corpus_evaluation.py \
    --corpus "C:/Users/user/.fiofilter/corpus/m03_fioos_sample_v1.jsonl" \
    --mode BUILD \
    --profile fioos
```
