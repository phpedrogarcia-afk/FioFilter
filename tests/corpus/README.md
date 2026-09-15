# Corpus Test Harness

This directory will contain the regression corpus for FioFilter.

## Status

**V0**: Empty. Corpus importer defined but no data loaded.

Corpus loading will happen in M02 after explicit authorization to use
the P14 CCA FioOS Tool Results.

## Corpus Entry Schema

Each entry is a JSON object in a JSONL file:

```json
{
  "corpus_entry_id": "p14-001",
  "source": "FioOS-P14-CCA-corpus",
  "raw_content_b64": "<base64-encoded raw bytes>",
  "classification_label": "CANONICAL_STATE",
  "inline_required_facts": [
    "commit abc123",
    "branch main"
  ],
  "expected_disposition": "RAW",
  "expected_inline_facts_present": true,
  "notes": "Git status output; compression destroyed inline facts in CCA test"
}
```

## Known Failure Modes (from P14 CCA corpus)

The P14 corpus contains 40 FioOS Tool Results that were analyzed under CCA.
Known failure modes to reproduce:

1. `curl GET` output compressed → README facts missing → task failure
   (CCA Terminal-Bench 2.1 failure case — validates I4)

2. Canonical Git evidence transformed → commit hash not inline → corrective retrieval
   (validates I4, I7)

3. JSON output structurally equivalent but inline identifier stripped
   (validates I8)

## How to Load Corpus (M02+)

```python
from tests.corpus.loader import load_corpus

entries = load_corpus("tests/corpus/p14_fioos.jsonl")
for entry in entries:
    result = engine.process(entry.tool_result)
    assert result.disposition == entry.expected_disposition
    for fact in entry.inline_required_facts:
        assert fact in result.content.decode("utf-8")
```
