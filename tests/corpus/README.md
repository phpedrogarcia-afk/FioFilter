# Corpus harness and schema v4

The executable harness lives in `fiofilter.corpus`; extraction and reporting are
laboratory utilities under `scripts/`. Real session output stays outside Git.
The committed JSONL contains only transparent synthetic fixtures, including one
inert detector-positive placeholder rather than a credential.

## Separation of concerns

Each v4 entry separates five things that v3 conflated:

1. `source_data`: bytes and execution provenance;
2. `sensitivity_screening`: finite detector result, never a non-sensitive claim;
3. `heuristic_suggestion`: extractor-generated hypothesis;
4. `oracle_labels`: optional, separately reviewed reference labels;
5. `derived_metrics`: replay observations partitioned by label provenance.

The extractor never populates `oracle_labels`. Replay never injects oracle
sensitivity or required facts into the `ToolResult` being evaluated.

## Minimal v4 entry

```json
{
  "schema_version": 4,
  "entry_id": "FIOOS-REAL-001",
  "source_data": {
    "provenance": "session:rollout.jsonl:call_id:call_123",
    "command": "git status --short --branch",
    "exit_code": 0,
    "stdout_stderr": "combined",
    "content_type_hint": "text",
    "byte_length": 154,
    "truncated": false,
    "raw_content_b64": "...",
    "raw_ref_path": null
  },
  "sensitivity_screening": {
    "result": "DETECTOR_NO_MATCH",
    "method": "fiofilter.sensitivity.contains_sensitive_material",
    "notes": "No configured pattern matched; sensitivity remains unassessed."
  },
  "heuristic_suggestion": {
    "evidence_class": "CANONICAL_STATE",
    "transform_eligibility": "RAW_REQUIRED",
    "inline_required_facts": ["On branch main"],
    "rationale": "Extractor heuristic for later review.",
    "missed_opportunity_category": null,
    "method": "M03_EXTRACTOR_V1"
  },
  "oracle_labels": null,
  "tags": ["fioos", "git", "real_workload"]
}
```

Exactly one of `raw_content_b64` and `raw_ref_path` is required. `byte_length`
must equal the loaded bytes. A detector result is one of `DETECTOR_MATCH`,
`DETECTOR_NO_MATCH`, `NOT_RUN` or `UNKNOWN`.

## Oracle requirements

Real oracle labels must be added by a separate review step and include:

- provenance: `INDEPENDENT_REVIEW`, `HUMAN_REVIEW` or `GOLD`;
- `reviewer_id` and `review_protocol`;
- evidence class, sensitivity and transform eligibility;
- rationale and any required inline facts;
- a missed-opportunity category only for `SAFE_TO_REDUCE`.

Protected classes and sensitive labels cannot be marked `SAFE_TO_REDUCE`.
Repeated strings in `inline_required_facts` represent required occurrence counts.

### GOLD fixture protocol

`GOLD` is reserved here for small, readable, synthetic regression cases whose
complete bytes and expected behavior are reviewable in Git. It does not describe
the unavailable historical FioOS corpus. Fixture authors verify exact byte
length, use no real secret/private material, state why an inert detector marker
exists and keep source and expected label transparent.

## Legacy v3 migration

v3 files are rejected by default because their `oracle_labels` may have been
created by the extractor itself. To inspect one without upgrading its claims:

```python
from fiofilter.corpus import M03_V3_AS_HEURISTIC, load_corpus

entries = load_corpus(
    "C:/Users/user/.fiofilter/corpus/m03_fioos_sample_v1.jsonl",
    migration=M03_V3_AS_HEURISTIC,
)
```

This maps legacy labels to `heuristic_suggestion`, sets `oracle_labels=None` and
leaves sensitivity screening `UNKNOWN`. Save to a new v4 file only after deciding
how local private artifacts should be retained; do not commit them.

## Replay and reports

```python
from fiofilter.corpus import load_corpus, replay_corpus
from fiofilter.types import Mode

entries = load_corpus("C:/path/to/reviewed-corpus-v4.jsonl")
evaluated, summary = replay_corpus(entries, mode=Mode.BUILD, profile_id="fioos")

for scope, metrics in summary.metrics_by_label_scope.items():
    print(scope, metrics["dangerous_false_transform_eligibility"])
```

Use only `ORACLE:*` scopes for reviewed safety claims. `HEURISTIC:*` scopes are
diagnostics. Token fields are `utf8_bytes_div_4_ESTIMATE`, not actual model tokens.

CLI utilities:

```bash
python scripts/extract_codex_corpus.py \
    --session "C:/path/to/rollout.jsonl" \
    --output "C:/Users/user/.fiofilter/corpus/sample-v4.jsonl" \
    --sample-size 50 \
    --project-tag FIOOS

python scripts/run_corpus_evaluation.py \
    --corpus "C:/Users/user/.fiofilter/corpus/reviewed-v4.jsonl" \
    --mode BUILD \
    --profile fioos
```

The report groups safety comparisons, missed-opportunity shares and confusion
matrices by label scope. Local byte reduction is not whole-mission savings.

## Dedicated clean-search corpus

`M03_SEARCH_CORPUS_V1` is separate from the stratified v3/v4 corpus above. It
must be extracted afresh from one fingerprinted local JSONL and must not reuse
the 50-entry sample as evidence for `DUPLICATED_HEADERS`.

```bash
python scripts/extract_rg_corpus.py \
    --session "/local/path/session.jsonl" \
    --output "/outside/git/m03_search_corpus_v1.jsonl" \
    --negative-output "/outside/git/m03_search_corpus_v1.negative.jsonl" \
    --manifest "/outside/git/m03_search_corpus_v1.manifest.json" \
    --observation-date "YYYY-MM-DD" \
    --relationship-to-prior-artifact UNKNOWN
```

The utility refuses repository-local output paths. It streams the source with
bounded pending-call state, records a content-derived artifact fingerprint,
writes every admitted candidate, retains only a bounded first-N sample for each
negative-control reason, and creates a deterministic per-grammar/size review set.

Admission is limited to a structurally identified single ripgrep command, exit 0,
non-truncated output, no failure wrapper, no detector match, and one of:

- `RG_STANDARD_PATH_LINE_TEXT` (`path:line:payload`);
- `RG_PATH_LINE_COLUMN_TEXT` (`path:line:column:payload`).

Both require byte-exact `encode(parse(raw)) == raw`. Ordering, duplicate
occurrences, path spelling, separators and LF/CRLF/tails are retained. Heading,
context, JSON, ANSI/color, binary notices, mixed/composite producers and unknown
syntax are negative controls, not heuristically recovered candidates.

Ripgrep exit 1 is `NO_MATCH`, not an execution error; exit >=2 is an execution
error. Both are excluded and remain RAW under the broader current nonzero-exit
policy. Extractor output contains heuristic candidate metadata only and always
sets `oracle_labels` to null. See `docs/M03-R3-CLEAN-SEARCH-CORPUS.md` for the
provenance conflict, fingerprint schema, review protocol and readiness gates.
