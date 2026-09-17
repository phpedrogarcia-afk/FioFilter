# FioFilter — Decision Ledger

**Format**: DXX — Title — Rationale — Date  
**Authority**: Repository state outranks conversational assumptions.  
**Amendment**: A decision may be superseded by a later decision. Superseded
decisions are NOT deleted — they are marked SUPERSEDED and the superseding
decision is cited.

---

## D001 — Evidence-Aware, Not Compression-Ratio-First

FioFilter's primary metric is evidence preservation under context reduction.
Compression ratio is a secondary metric that must never be optimized at the
expense of evidence.

**Rationale**: P14 corpus — 4 genuinely compression-eligible outputs produced
1578→1578 estimated tokens (0% reduction). High compression ratios are a
lagging indicator of value, not a target. The goal is "useful progress per
context token," not "lowest token count."

**Date**: M01 / 2026-09-15

---

## D002 — Deterministic-First; No LLM in V0

All classification and transformation in V0 must be deterministic and rule-based.
No AI/LLM call is permitted in the classification or transformation path.

**Rationale**: LLM classification is non-deterministic, untestable with
deterministic oracles, adds token cost to save tokens, and introduces latency.
The classification layer must be auditable. Invariant I11 codifies this.

**Date**: M01 / 2026-09-15

---

## D003 — RAW Is Immutable and Byte-Recoverable

**M02 status**: Unconditional persistence rationale SUPERSEDED by M02-D001; store mechanics by M02-D004.

Once persisted, a RAW store entry is never modified or deleted. Recovery
must be byte-exact (SHA-256 verified). Invariant I1 + I3 codify this.

**Rationale**: RTK's failure mode (no RAW store at all) means compressed output
is the only output. CCA's `raw_ref` is correct but insufficient without I4.
FioFilter needs a store that is always written, always complete.

**Date**: M01 / 2026-09-15

---

## D004 — Critical Inline Evidence Cannot Be Moved Solely Behind raw_ref

Facts designated `inline_required` must appear in the visible output.
A `raw_ref` does not grant permission to remove them. Invariant I4 codifies this.

**Rationale**: CCA failure — 96/137 critical facts preserved inline (70.1%).
The missing 29.9% required a corrective model turn via `raw_ref`. The
context-compress `curl GET` failure in Terminal-Bench 2.1 is a further
empirical confirmation: compressed output without inline fact preservation
causes task failures. 100% is the requirement.

**Date**: M01 / 2026-09-15

---

## D005 — Project Profiles Cannot Weaken Core Invariants

Profiles (default, fioos, fioideias) are policy overlays. They may restrict
compression eligibility. They may never override invariants I1–I16 or change
the default for UNKNOWN from RAW. Invariant I12 codifies this.

**Rationale**: Without this rule, a FioOS profile could inadvertently allow
compression of AUTHORITY or CANONICAL_STATE evidence by narrowing definitions.
The invariants are constitutional; profiles are legislative.

**Date**: M01 / 2026-09-15

---

## D006 — No Codex Hooks in V0

FioFilter does not install hooks into Codex, modify `~/.codex`, or modify
any global agent configuration in V0.

**Rationale**: Building the engine independently of Codex allows the engine
to be tested and validated before being trusted with live agent context.
Coupling too early creates architectural debt before the core is proven.
The hook integration is V1+.

**Date**: M01 / 2026-09-15

---

## D007 — No Compressor Tournament

The donor autopsy is bounded to three pre-selected donors (RTK, CCA,
context-compress). No additional tools are evaluated for comparison in M01.

**Rationale**: A compressor tournament would expand scope, consume mission
budget, and provide diminishing returns — the three donors cover the major
architectural patterns. New tools may be added as Donor D+ if specifically
justified, recorded here.

**Date**: M01 / 2026-09-15

---

## D008 — Whole-Mission Economics Outrank Local Compression

A local `visible_bytes < raw_bytes` finding does not prove whole-mission benefit.
Metrics must distinguish: local bytes, estimated tokens, model turns, corrective
retrievals. Invariants I14 and I15 codify this.

**Rationale**: P11 evidence — turn reduction (6→0 intermediate turns) produced
−49.93% whole-mission tokens. P3 evidence — static-context optimization produced
−27.03%. Turn reduction >> local byte reduction. A transform that adds one
corrective turn may negate all local savings.

**Date**: M01 / 2026-09-15

---

## D009 — Aggressive Exploration Is Compatible With Strict Evidence Boundaries

The EXPLORE mode + NOISE/DISCOVERY/PROGRESS evidence classes permit aggressive
context reduction. This is NOT in tension with strict evidence boundaries.
The boundaries apply at the AUTHORITY/SECURITY/FAILURE/CANONICAL_STATE level.

**Rationale**: Confusing rigor with conservatism makes FioFilter useless.
NOISE should be attacked aggressively. The philosophy is:
AGGRESSIVE AT THE EXPLORATION BOUNDARY, RIGOROUS AT THE EVIDENCE BOUNDARY.

**Date**: M01 / 2026-09-15

---

## D010 — Python for V0, Not Rust

FioFilter V0 is implemented in Python. Rust is explicitly rejected for V0.

**Rationale**: RTK uses Rust but still failed evidence preservation. Language
choice is not evidence safety. Python offers: faster iteration, readable
deterministic tests, no compilation step, standard library `hashlib`/`json`/
`difflib` for transforms, `pytest` for test oracles. V0 is a laboratory;
inspectability matters more than performance.

**Date**: M01 / 2026-09-15

---

## D011 — RAW Is Written Before Any Transform Attempt

**M02 status**: QUALIFIED by M02-D001: permitted disk or ephemeral recovery first; sensitive results remain RAW without archive.

The RAW store write happens before the transform is attempted, not after.

**Rationale**: If the transform throws an exception, the RAW store entry must
already exist for recovery. A post-transform write would create a window where
a transform failure leaves no recovery path. Belt-and-suspenders for I3.

**Date**: M01 / 2026-09-15

---

## D012 — T02 (Template Folding) Deferred to M02

**M02 status**: M02 implementation schedule SUPERSEDED by M02-D006: T02–T05 remain deferred.

T02 (repeated-template folding) is a transform candidate but is NOT implemented
in V0.

**Rationale**: Template detection requires identifying N ≥ 3 structurally identical
blocks differing only in variable fields. This is more complex than T01 (exact
duplicate-line folding) and exceeds V0's foundation scope. T01, T03 (PASS
aggregation), and T04 (JSON minification) are simpler and cover primary NOISE/
SUCCESS_SUMMARY/MACHINE_DATA cases. T02 is a M02 candidate.

**Note**: T03 and T04 are candidates, not approved implementations. They must be
implemented and tested in M02 before use.

**Date**: M01 / 2026-09-15

---

## D013 — GitHub Remote Is phpedrogarcia-afk/FioFilter

The GitHub repository `https://github.com/phpedrogarcia-afk/FioFilter` was
discovered unambiguously via `gh repo list phpedrogarcia-afk`. It was empty
(no commits) at M01 execution. The local repository is connected to this remote.

**Rationale**: Preserves a clean, portable repository structure. GitHub is the
durable collaboration surface for Antigravity, Codex local, Codex web, and
future tooling.

**Date**: M01 / 2026-09-15

---

# M02 — Foundation audit and hardening

The M01 entries above remain historical. The following supersessions govern
current runtime behavior; they do not retroactively change what M01 implemented.

## M02-D001 — Independent sensitivity and persistence

- **QUESTION**: Does evidence requiring RAW authorize persistent storage?
- **EVIDENCE**: M01 engine wrote every output; a generated inert bearer-shaped
  probe became SECURITY/RAW and created a disk blob. Metadata stored command,
  session and inline facts. D003/D011 assumed unconditional persistence.
- **DECISION**: Sensitivity is orthogonal to the unchanged twelve-class taxonomy.
  Engine defaults to reference-owned EPHEMERAL recovery. Detected/declared
  sensitivity forces RAW/DO_NOT_PERSIST, no archive or persistent audit. PERSIST
  requires explicit request plus caller NON_SENSITIVE assessment, subject to veto.
  The explicit low-level disk write API rejects detector matches and documents its
  assessed-input precondition. No universal non-sensitivity inference is made.
- **WHY**: Preserve visible evidence without silently building a secret archive.
  Public security findings and credential material have different storage needs.
- **ALTERNATIVES_REJECTED**: Unconditional disk writes; extra evidence classes;
  encryption/key management; automatic redaction that changes evidence; global
  ephemeral history. Detection alone is not proof of safe persistence.
- **REVERSIBILITY**: Add separately approved persistence backends later without
  changing evidence classes. Existing M01 archives are not automatically deleted
  or migrated. Supersedes D003's always-complete store and qualifies D011: prepare
  permitted recovery before transforming, never persist solely because RAW is required.

## M02-D002 — One operational profile source

- **QUESTION**: Which of Python and YAML controls policy?
- **EVIDENCE**: Only Python was loaded; YAML files were independent declarations
  with no loader or drift test. NOISE/PROVE also differed between prose and runtime.
- **DECISION**: Remove `profiles/*.yaml`. Python `DefaultProfile` is the core upper
  bound; engine intersects overlays with it. FioOS delegates where current T01
  scope coincides; FioIdeias retains its stub identity. Test every class/mode/profile
  subset and absence of YAML operational copies. Unknown profiles fail to RAW.
- **WHY**: Small deterministic policy surface, no silent decorative configuration.
- **ALTERNATIVES_REJECTED**: YAML loader dependency; a generation pipeline for three
  redundant policy files; trusting profiles to uphold I12 without engine guards.
- **REVERSIBILITY**: A future canonical external format needs an explicit migration
  and validation relationship. This implements D005, not a weakening of it.

## M02-D003 — Full evidence boundary and bounded T01 eligibility

- **QUESTION**: Can repetition/prefix inspection prove that output is safe to fold?
- **EVIDENCE**: M01 transformed an ERROR after 16 KiB, PASS + warning and repeated
  payment records. DIAGNOSTIC had no classifier branch. A permissive profile applied
  T01 to JSON because the selected transform was not actually rechecked under I8.
- **DECISION**: Inspect all bytes; protect mixed failure/diagnostic signals before
  low-risk classification. Strictly handle invalid UTF-8/NUL and inspect normalized
  ANSI text without changing returned bytes. Require complete known noise/progress
  grammar for T01. Limit T01's engine contract to NOISE/PROGRESS, intersect policies,
  retain source/stream/exit/truncation metadata, and fail operational exceptions to RAW.
- **WHY**: A single matching line or repetition ratio is not proof about the rest.
- **ALTERNATIVES_REJECTED**: Longer prefix sampling; arbitrary repeated text as NOISE;
  unrestricted T01 on success/diagnostic/discovery/machine output; RAW for all inputs.
- **REVERSIBILITY**: Extend grammars using labeled workload evidence; other classes
  await specific transform contracts. Supersedes M01 broad T01 policy, not D009's
  aggressive exploration principle.

## M02-D004 — No-clobber storage and content-only metadata

- **QUESTION**: Are M01 atomicity, dedup and metadata claims established?
- **EVIDENCE**: Fixed `.tmp` names raced; rename could overwrite on POSIX; dedup
  skipped hash verification; sidecars/index mixed content identity with first-event
  context; `verify=False` bypassed integrity and RawRef paths were trusted.
- **DECISION**: Unique same-directory temporary files, file fsync, `os.link` atomic
  no-clobber publication, verify on write/dedup/read, validate addresses, ignore
  external reference paths. Schema-2 sidecars contain only SHA/length/schema; remove
  index and event metadata. Missing sidecar is explicit and reconstructable;
  corruption/legacy schema is an error, intact blob recovery remains independent.
- **WHY**: Minimize state and secret-bearing metadata without claiming a two-file
  transaction or universal filesystem durability.
- **ALTERNATIVES_REJECTED**: Overwrite rename/replace; shared temp names; SQLite or
  distributed locks; silent corruption repair; retaining redundant event index.
- **REVERSIBILITY**: Another proven publication primitive may replace hard links.
  Unsupported filesystems fail to RAW. Existing M01 blobs remain readable by hash;
  contextual sidecars are not silently migrated or deleted. Power-loss durability,
  hostile parent directories and kill-time temporary scavenging remain outside V0.

## M02-D005 — Audit and metric truth

- **QUESTION**: What is observed, estimated, persisted or merely proposed?
- **EVIDENCE**: M01 labeled byte length/4 as chars/4; apply timing covered other
  stages; missing actual token/turn fields; recovery defaulted to unmeasured zero;
  persistent logs omitted profile/invariant rationale and could raise outside fallback.
- **DECISION**: Label `utf8_bytes_div_4_ESTIMATE`; measure apply only. Add optional
  supplied model tokens, turns, corrective retrieval and recovery counts, default
  None. Return an in-memory decision audit always; disk logging is explicit and
  skipped for DO_NOT_PERSIST. Log failure returns RAW with a returned failure reason.
- **WHY**: Distinguish local economics from mission observations and avoid audit
  becoming a secondary sensitive-data archive.
- **ALTERNATIVES_REJECTED**: Invented mission savings, automatic token billing
  claims, retention/prediction engines, unconditional persistent audit.
- **REVERSIBILITY**: Add real tokenizer/mission integrations under separate approval.
  Supersedes M01 I16 unconditional disk logging; preserves D008/I14/I15 unit boundaries.

## M02-D006 — Versioned T01 representation, no JSON minification

- **QUESTION**: Does RAW recovery prove visible reversibility or marker safety?
- **EVIDENCE**: M01's inline marker could collide with literal output; count prose
  contradicted count-1 implementation; tests recovered from the store without
  decoding visible output. T04 documents treated parse equality as enough.
- **DECISION**: T01 v2 has reserved header/marker syntax, exact run count including
  first, 1-based inclusive source boundaries, unchanged first line, LF/CRLF/tail
  handling and strict bounded decoding. Reject literal collisions, unsafe controls,
  overhead without savings, lost inline occurrences and unequal reconstructed bytes.
  T02–T05 remain DEFERRED; parse equivalence is not universal consumer compatibility.
- **WHY**: Separate two independent recovery claims and make representations auditable.
- **ALTERNATIVES_REJECTED**: Ambiguous appended marker; assuming identical lines have
  no material multiplicity; implementing T04 because parsing is convenient.
- **REVERSIBILITY**: v2 is explicitly versioned; M01 visible markers are not decoded
  as v2. RAW blobs remain original bytes. Supersedes D012's M02 implementation schedule
  for T02/T03/T04; no new transform is authorized by this mission.

## M02-D007 — Stateless modes and safe aggressive frontiers

- **QUESTION**: Is mode/session complexity premature or PROVE over-conservative?
- **EVIDENCE**: Inspection found no session engine, mutable escalation or mode
  mutation. Actual Default/FioOS policy denied NOISE in PROVE despite stated allowance;
  the test accepted any nonempty result and hid the discrepancy.
- **DECISION**: Keep existing stateless per-call modes; failure changes disposition,
  not later calls. Enable known NOISE/T01 in PROVE for every profile. Record
  SAFE_AGGRESSIVE_FRONTIER for all classes and profile limits without implementing it.
- **WHY**: Avoid inventing a session architecture or letting evidence discipline
  degrade into permanent pass-through behavior.
- **ALTERNATIVES_REJECTED**: Removing valuable mode policy; permanent RAW after a
  failure; speculative session machinery; new reduction mechanisms during M02.
- **REVERSIBILITY**: A separately approved session architecture can compose these
  stateless calls. Supersedes mode-escalation prose, preserves D009.

## M02-D008 — Portable canonical verification and precise claims

- **QUESTION**: How can Codex Web and Windows Antigravity trust the handoff?
- **EVIDENCE**: M01 editable-install backend path was nonexistent; Windows tests
  mostly used host temp paths; docs claimed specifications/stubs where code existed,
  universal properties without sufficient tests, and corpus replay without a loader.
- **DECISION**: Correct build backend to setuptools.build_meta; pin pytest 8.3.5
  and remove unused pytest-cov dev dependency. Minimal standard Windows 2022 and
  Ubuntu 24.04 CI on Python 3.9 executes editable install and canonical pytest command.
  Pin action SHAs, read-only permissions, no credentials retained, cache or artifacts.
  Rewrite current docs with scoped guarantees and retain annotated M01 donor history.
- **WHY**: Exercise actual Windows behavior and minimum Python, while preserving
  precise baseline/final evidence in GitHub. No branch-protection setting is implied.
- **ALTERNATIVES_REJECTED**: Large CI matrix, caches/artifacts without need, global
  agent configuration, pretending local Linux tests prove Windows compatibility,
  silently rewriting M01 decisions or claiming historical corpus reproduction.
- **REVERSIBILITY**: CI versions/dependency pins can be revised through review.
  Workflow results prove only the installed/tested SHA and runner corpus; integration,
  universal semantics and whole-mission economics require future evidence.

## M03-D001 — Executable corpus harness and provenance separation

- **QUESTION**: How should real historical coding-agent outputs be ingested without
  violating privacy or coupling core FioFilter to proprietary agent logs?
- **EVIDENCE**: Real Codex sessions contain credentials, tokens, and private paths.
  83 calls in canonical session `01a02f96-42a2-7a80-b8bc-6d066d0e322f` contained
  sensitive patterns. Standalone P14 CCA corpus files were not preserved on disk.
- **DECISION**: Establish a generic `fiofilter.corpus` schema separating Source Data,
  Independent Oracle Labels, and Derived Metrics. Ingestion reads caller-specified local
  files strictly outside the repository. Laboratory extraction from Codex logs is
  isolated in `scripts/extract_codex_corpus.py`. Commit only synthetic, non-sensitive
  fixtures to Git.
- **WHY**: Satisfies zero-leakage invariant while providing a rigorous, reproducible
  empirical test harness.
- **ALTERNATIVES_REJECTED**: Committing raw user outputs to Git; hardcoding Codex
  log schemas into the core engine; fabricating a substitute and calling it "P14".
- **REVERSIBILITY**: High. The corpus schema is versioned; external paths are caller-defined.

## M03-D002 — Empirical observation of T01 on real workloads

- **QUESTION**: Does T01 (exact duplicate consecutive-line folding) provide practical
  context reduction on real coding agent executions?
- **EVIDENCE**: Replay of 50 stratified real-workload tool outputs from FioOS canonical
  session `01a02f96` yielded 0.0% reduction. Real tool outputs (search, build, test,
  directory listings) do not contain identical consecutive lines due to advancing numbers,
  timestamps, varying match snippets, and execution wrapper headers.
- **DECISION**: Record that T01 is an edge-case noise filter rather than a general
  reduction engine. Do not weaken T01's exact equality contract to force compression.
- **WHY**: Preserves evidence integrity. Compressing non-identical lines requires
  distinct domain-specific contracts and oracles.
- **ALTERNATIVES_REJECTED**: Weakening T01 with fuzzy/heuristic matching; claiming
  T01 reduces real workloads based on synthetic benchmarks.
- **REVERSIBILITY**: High. T01 remains unchanged; new transforms are evaluated independently.

## M03-D003 — Selection of M04 frontier: search match header deduplication

- **QUESTION**: Where is the largest safe reduction frontier in real coding agent
  workloads for M04 investigation?
- **EVIDENCE**: Analysis of 21 safe missed opportunities in the real workload sample
  revealed that 60.01% of compressible bytes (97.5 KB in sample) originate from repeated
  file path headers in search (`rg`/`grep`) outputs. Grouping search matches under file
  path headers preserves 100% of line numbers, matched code, and file paths with near-zero
  risk of corrective retrieval.
- **DECISION**: Select `DUPLICATED_HEADERS` as the recommended frontier for M04.
  Defer progress folding and pass-list aggregation to later evaluations.
- **WHY**: Combines the largest single context opportunity (60%) with the lowest evidence
  risk and highest determinism.
- **ALTERNATIVES_REJECTED**: Speculative multi-transform implementation in M03; selecting
  progress folding (higher ambiguity in intermediate states); prioritizing pass-list
  aggregation (smaller byte share).
- **REVERSIBILITY**: Completely reversible; M04 will evaluate `DUPLICATED_HEADERS` in an
  isolated mission branch before implementation.

## M03-R1-D001 — Oracle provenance is distinct from extraction — supersedes M03-D001 in part

- **QUESTION**: Can labels generated by the extraction strata be treated as an
  independent oracle?
- **EVIDENCE**: `assign_initial_oracle` derived evidence class, eligibility and
  frontier bucket directly from extractor-selected strata. No reviewer identity or
  review protocol was recorded. The original report nevertheless called them
  independently audited ground truth.
- **DECISION**: Schema v4 separates `heuristic_suggestion` from optional
  `oracle_labels`. Oracle provenance is limited to `INDEPENDENT_REVIEW`,
  `HUMAN_REVIEW` or transparent synthetic `GOLD`, with required reviewer and
  protocol. The extractor emits heuristics only. Legacy v3 is rejected unless
  explicitly demoted using `M03_V3_AS_HEURISTIC`.
- **WHY**: Safety and frontier claims require a reference independent of the rule
  being evaluated; renaming a heuristic does not provide independence.
- **ALTERNATIVES_REJECTED**: Keep the v3 name with a disclaimer; infer reviewer
  provenance; silently accept legacy labels as v4 oracle data.
- **REVERSIBILITY**: A future version may add stronger provenance types or signed
  review artifacts. It must not silently upgrade v3 claims.

## M03-R1-D002 — Screening is not assessment; replay is source-only

- **QUESTION**: May detector no-match establish NON_SENSITIVE, and may oracle facts
  be injected into the FioFilter input during evaluation?
- **EVIDENCE**: The extractor filtered configured matches and labeled every retained
  record `NOT_SENSITIVE`. `CorpusEntry.to_tool_result` then supplied that label and
  oracle-required facts to the engine, so the detector/preservation evaluation was
  circular. One committed fixture did not even match the detector pattern it was
  intended to exercise.
- **DECISION**: Record detector results separately as `DETECTOR_MATCH`,
  `DETECTOR_NO_MATCH`, `NOT_RUN` or `UNKNOWN`. Replay always supplies
  `Sensitivity.UNKNOWN` and no label-derived inline facts. Compare required facts
  afterward with occurrence multiplicity. Use an inert, detector-positive fixture.
- **WHY**: Absence of a finite regex match cannot prove absence of sensitive data;
  an oracle must observe the subject rather than change its behavior.
- **ALTERNATIVES_REJECTED**: Trust detector no-match; keep injection for convenience;
  add real-looking credentials to fixtures; disable sensitivity testing.
- **REVERSIBILITY**: Detector implementations and review protocols may evolve while
  the screening/assessment boundary remains explicit.

## M03-R1-D003 — Label-scoped metrics and historical-claim demotion — supersedes M03-D002 evidence status

- **QUESTION**: Which M03 measurements may be presented as safety evidence?
- **EVIDENCE**: Runtime byte counts were mixed with comparisons against heuristic
  labels. The external 50-record corpus and review artifacts are unavailable in
  Git, preventing independent replay in Codex Web. Token figures are bytes/4
  estimates.
- **DECISION**: Partition safety comparisons, missed-opportunity metrics and
  confusion matrices by keys such as `ORACLE:INDEPENDENT_REVIEW` and
  `HEURISTIC:M03_EXTRACTOR_V1`. Label token values as
  `utf8_bytes_div_4_ESTIMATE`. Preserve original values as historical local
  observations, not reproduced proof.
- **WHY**: Runtime observations remain useful, but their claim strength must follow
  label provenance and measurement scope.
- **ALTERNATIVES_REJECTED**: Delete all M03 results; retain aggregate safety totals
  without scope; present token estimates as actual tokens or mission savings.
- **REVERSIBILITY**: New reviewed corpora can add oracle scopes and superseding
  measurements without altering historical records.

## M03-R1-D004 — `DUPLICATED_HEADERS` remains unselected — supersedes M03-D003

- **QUESTION**: Does the reported 60.01% bucket authorize a search-output transform?
- **EVIDENCE**: Bucket assignment came from the extractor, not an independent review.
  The proposed set-of-triples contract discards ordering and multiplicity and does
  not cover headings, context separators, path grammars, columns, ANSI, warnings,
  stderr, truncation, JSON/binary formats or mixed protected evidence.
- **DECISION**: Keep `DUPLICATED_HEADERS` as a
  `HEURISTIC_CANDIDATE_PENDING_LOCAL_VALIDATION`. Do not select M04 or implement a
  transform until the external sample is reviewed and a lossless consumer contract
  covers the supported formats and RAW fallback.
- **WHY**: The candidate may still be an aggressive frontier, but its safety and
  ranking are not yet proven.
- **ALTERNATIVES_REJECTED**: Implement from the historical percentage; declare all
  discovery output permanently RAW; treat set equality as evidence identity.
- **REVERSIBILITY**: Independent local evidence can promote, rerank or reject the
  candidate in a later authorized mission.

## M03-R1-D005 — Corpus counters describe parser events, not physical executions

- **QUESTION**: What exactly did the reported 4,362 count measure, and how does it
  relate to a separate historical 4,567 value?
- **EVIDENCE**: The extractor increments `total_calls_seen` for every parseable
  `custom_tool_call` payload with a truthy `call_id`, before matching output and
  without requiring tool name `exec`. `total_outputs_seen` is a separate event
  counter. The source definition for 4,567 is absent from the repository.
- **DECISION**: Describe 4,362 only as the historical count of parseable call events
  under that code path. Record the relationship to 4,567 as UNKNOWN; do not call
  either number completed physical `exec` calls without a matching definition.
- **WHY**: Precise event semantics prevent false reconciliation and denominator
  errors in sampling claims.
- **ALTERNATIVES_REJECTED**: Infer completion from call creation; assume both counts
  measure the same event; alter the historical number to make them agree.
- **REVERSIBILITY**: A later audit with source telemetry can define and reconcile
  counters explicitly while retaining this uncertainty record.

## M03-R2-D001 — Independent local validation of `DUPLICATED_HEADERS` candidate — qualifies M03-R1-D004

- **QUESTION**: Does independent local examination of historical session records
  support selecting `DUPLICATED_HEADERS` as an authorized reduction frontier?
- **EVIDENCE**: Independent local review of all 8 search-stratum records in primary
  sample `m03_fioos_sample_v1.jsonl` revealed that 0 of the 97,503 bytes (0.0%) are
  confirmed safe to reduce: 80.3 KB were truncated chat thread / search output
  requiring RAW under I13; 11.0 KB was canonical Python source code requiring RAW
  under I7; 1.3 KB was SSH failure diagnostic requiring RAW under I6; 4.2 KB was
  single-file search with nonzero exit requiring RAW under I6; and 4.8 KB was
  composite directory listing + grep output with ambiguous grammar (UNKNOWN).
  However, broader inspection of the full canonical session `01a02f96` proved that
  193 pure, untruncated multi-file `rg` calls with authentic repeated headers DO
  exist in real coding workflows.
- **DECISION**: Classify candidate status as
  `DUPLICATED_HEADERS_PARTIALLY_VALIDATED_MORE_EVIDENCE_REQUIRED` and mission
  verdict as `M03_R2_PASS_MORE_VALIDATION_REQUIRED`. Do not authorize M04 transform
  implementation yet. Require an uncorrupted, cleanly sampled search corpus and a
  formal lossless preservation grammar contract (handling Windows colons, column
  numbers, context lines, ANSI, binary notices, and fail-open RAW fallback) before
  any transform is built.
- **WHY**: Preventing premature transform development on contaminated sample data
  while acknowledging authentic workload reduction potential discovered in the
  underlying session.
- **ALTERNATIVES_REJECTED**: Rejecting the candidate entirely (ignoring the 193 pure
  session calls); authorizing M04 immediately based on heuristic percentage;
  building a transform on truncated or composite outputs.
- **REVERSIBILITY**: A dedicated search corpus and approved grammar contract can
  advance the candidate to fully validated status in a future mission.

## M03-R3-D001 — Artifact identity requires content provenance — qualifies M03-R2-D001

- **QUESTION**: Does a shared session identifier establish that the approximately
  203,780,102-byte August rollout described by M03 and the 16,076,013-byte March
  artifact inspected by R2 are the same historical source?
- **EVIDENCE**: The repository records different paths, filenames, dates and sizes
  for the same session ID. Only the smaller R2 artifact has a recorded SHA-256.
  Neither artifact is available to Codex Web for byte comparison, and no derivation
  or containment record exists.
- **DECISION**: Designate the historical descriptions `M03_SOURCE_A` and
  `M03_SOURCE_B`; set `SESSION_PROVENANCE_CONFLICT=YES` and `RELATION=UNKNOWN`.
  Re-scope the 193-call finding to a local observation of Source B pending a fresh
  fingerprinted run. Every future historical JSONL receives a content-derived
  artifact ID, SHA-256, byte size, local-only path, record/timestamp counts when
  measured, extractor version, observation date and explicit prior relationship.
- **WHY**: Session IDs identify logical sessions, not byte identity. Calling an
  unreconciled artifact canonical would transfer evidence across an unproved link.
- **ALTERNATIVES_REJECTED**: Assume identical bytes from the session ID; silently
  choose either path as canonical; delete R2's useful observation; claim that one
  artifact supersedes or contains the other without hashes and comparison evidence.
- **REVERSIBILITY**: A later local comparison may replace `UNKNOWN` with one allowed
  relationship while preserving both source records and the evidence used.

## M03-R3-D002 — Narrow fail-closed ripgrep characterization before M04

- **QUESTION**: What is the smallest executable boundary that can prepare a clean
  search corpus without implementing or pre-authorizing header compression?
- **EVIDENCE**: The stratified M03 sample admitted composite, truncated, nonzero,
  source-read and failure outputs. Ripgrep has distinct exit semantics and multiple
  incompatible output grammars. Set/semantic equality would lose order,
  multiplicity, delimiters and line endings.
- **DECISION**: Add the isolated `M03_SEARCH_CORPUS_V1` extractor and byte parser.
  Admit one structurally identified, shell-free ripgrep command with exit 0, no
  truncation/failure/sensitivity-screen match, and only
  `RG_STANDARD_PATH_LINE_TEXT` or `RG_PATH_LINE_COLUMN_TEXT`. Require
  `encode(parse(raw)) == raw`. Exclude headings, context, JSON, ANSI, binary notices
  and unknown syntax. Extract all clean candidates plus bounded deterministic
  negative controls and a per-grammar size-quantile review selection. Assign no
  oracle label and do not connect this code to the transform engine.
- **WHY**: A narrow recognized grammar with exact reconstruction supplies useful
  local evidence while failing closed on every format not yet contracted.
- **ALTERNATIVES_REJECTED**: Reuse the flawed 50-entry sample; substring-match `rg`;
  normalize text; parse paths by naïve colon splitting; support every ripgrep mode;
  implement `DUPLICATED_HEADERS` during corpus preparation.
- **REVERSIBILITY**: Future missions may add separately named grammars only with
  synthetic counterexamples, negative controls and exact roundtrip evidence. No
  current transform or policy behavior changes.

## M03-R4-D001 — Validation of RG_STANDARD_PATH_LINE_TEXT grammar and M04 Gate Authorization

- **QUESTION**: Does real Codex historical session evidence validate that `RG_STANDARD_PATH_LINE_TEXT`
  and/or `RG_PATH_LINE_COLUMN_TEXT` are safe, byte-exact, reproducible, and economically viable
  for lossless grouping under an M04 transform investigation?
- **EVIDENCE**:
  - **Artifact Provenance**: Source A exists locally at `C:\Users\phped\.codex\sessions\2026\08\23\rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl`
    (206,427,325 bytes, SHA-256 `bc4561d4588a73a6889ca38d8c180ae467e51eea5f023aaba7a222425cf350a0`,
    Artifact ID: `M03-ARTIFACT-SHA256-BC4561D4588A73A6`, 35,040 total records, 4,430 custom tool calls/outputs paired).
    Source B does not exist on disk (directory `2026\03` absent, no 16,076,013 B file found; inferred from UUID timestamp decoding).
    Source A is physically verified. Source B is `HISTORICAL_NOT_REPRODUCED`.
    Their reported fingerprints differ, but the current physical relationship is
    `UNKNOWN` because Source B bytes were unavailable; absence alone is not proof.
  - **Extraction & Characterization**: Extracted 23 clean candidates from 4,430 calls. All 23 belong to `RG_STANDARD_PATH_LINE_TEXT`.
    0 occurrences of clean `RG_PATH_LINE_COLUMN_TEXT`.
  - **Exact Byte Roundtrip**: 23 / 23 (100.0%) passed `encode(parse(raw)) == raw` byte-for-byte. 0 roundtrip failures.
  - **Negative Controls**: 34 negative controls written across 8 distinct exclusion categories; verified 0 false admissions.
  - **Headroom Donor Adversarial Tests**: 18 challenge cases tested (Windows drive paths, UNC paths, hyphens, dated paths,
    CVE paths, digit-separated paths, colon in payload, duplicate matches, context separators, extensionless files, digit path segments).
    0 ambiguous cases admitted. Fails closed to RAW on ambiguity.
  - **Independent Review (`M03_R4_REAL_SEARCH_VALIDATION_V1`, Reviewer `ANTIGRAVITY_M03_R4`)**:
    12 candidates reviewed across size quantiles: 10 assigned `SAFE_FOR_LOSSLESS_GROUPING`, 2 assigned `RAW_REQUIRED`
    (economic non-expansion guard where candidates had 0 duplicate paths, e.g. 2 matches in 2 files, 4 matches in 4 files).
    0 cases invalid or sensitive. Information omission is 0 under the lossless
    contract; operational corrective retrieval remains unmeasured until shadow/A-B.
  - **Lossless Grouping Economics**: Across 23 candidates (62,373 raw bytes), lossless candidate grouping produced 45,021 bytes,
    yielding 17,352 bytes saved (27.82% reduction, or 4,338 tokens saved under `utf8_bytes_div_4_ESTIMATE`).
- **DECISION**:
  - Authorize `RG_STANDARD_PATH_LINE_TEXT` as **VALIDATED** for M04 transform investigation.
  - Classify `RG_PATH_LINE_COLUMN_TEXT` as **MORE_REAL_EVIDENCE_REQUIRED** (retained in laboratory parser but deferred from M04).
  - Do not implement any M04 transform in M03-R4.
- **WHY**: Strict empirical evidence proves `RG_STANDARD_PATH_LINE_TEXT` occurs cleanly in real workloads, reconstructs byte-for-byte,
  has zero false admissions on negative controls, fails closed on ambiguity, and yields substantial context reduction without evidence loss.
- **ALTERNATIVES_REJECTED**:
  - Authorizing `DUPLICATED_HEADERS` universally (rejected: only exact grammar ID is validated).
  - Authorizing `RG_PATH_LINE_COLUMN_TEXT` without real workload evidence (rejected: zero real occurrences observed).
  - Rejecting the search frontier or creating another methodology mission (rejected: real evidence is decisive).
- **REVERSIBILITY**: If subsequent M04 transform implementation or consumer testing reveals unforeseen compatibility issues,
  the transform contract can be refined or revoked without affecting T01 or baseline invariants.

## M04-D001 — Lossless contiguous-run grouping with engine metadata gate

- **QUESTION**: How can the authorized `RG_STANDARD_PATH_LINE_TEXT` grammar be
  grouped without changing order, multiplicity, byte reconstruction or the M03
  producer boundary, and how far may the current engine integrate it?
- **EVIDENCE**: M03-R4 observed 23 real clean cases, 23/23 parser roundtrips,
  34 negative controls with zero false admissions, 18 donor ambiguity challenges
  with zero admissions, and a bounded independent review. The current `ToolResult`
  carries a free-form command and exit/truncation fields but no provenance bit
  proving that command extraction was structurally grounded and single-purpose.
  M03-R4 also measured no information omission, not an operational corrective
  retrieval rate. Source A is physically verified; Source B is historical and
  currently unreproduced, so their current physical relationship remains unknown.
- **DECISION**: Implement exactly one transform, `T02_RG_STANDARD_GROUP_V1`, using
  the already validated M03 parser. Encode only contiguous runs, repeat a path
  header when the path returns after another run, and require an independent
  decoder to reconstruct exact bytes. Expose structured producer evidence and
  complete transform metadata through a verified evaluation API. Register the
  transform, but keep generic `apply`, engine selection and every profile route
  disabled until trusted structural producer evidence is propagated at runtime.
  Treat non-reducing valid inputs as RAW with
  `VALID_GRAMMAR_NO_ECONOMIC_GAIN`.
- **WHY**: Contiguous runs retain global sequence and every occurrence while
  removing repeated path bytes. The metadata gate preserves the empirical M03
  admission boundary instead of treating arbitrary discovery-shaped text as rg.
  The full versioned ID avoids equating this transform with the older unimplemented
  short-name T02 template-folding proposal.
- **ALTERNATIVES_REJECTED**: Global grouping; ranking or dropping matches/files;
  best-effort parsing; authorizing column/context/heading/JSON/color/binary output;
  allowing profiles to infer producer evidence; using zero omitted facts as a
  measured corrective-retrieval rate; delaying the transform for another M03 loop.
- **REVERSIBILITY**: Removing the registry entry removes the isolated feature;
  no engine/profile path currently depends on it. A later metadata mission may
  add automatic routing without changing this representation or decoder contract.

## M04-R1-D001 — Real historical replay validation of T02_RG_STANDARD_GROUP_V1

- **QUESTION**: Does the production transform `T02_RG_STANDARD_GROUP_V1` successfully
  replay on 100% of the real historical clean candidates that authorized it,
  preserving exact byte recovery, zero false admissions, and measurable reduction?
- **EVIDENCE**:
  - Replayed all 23 real clean candidates from `C:\Users\phped\.fiofilter\corpus\m03_rg_clean_candidates_v1.jsonl`
    (SHA-256 `c711a07f75f734bdbaacda35b42fa45e0075bb1c5a49f4b9c5eb7f6e396c768c`).
  - Production transform produced 16 `TRANSFORMED` and 7 `RAW_NO_ECONOMIC_GAIN` (`VALID_GRAMMAR_NO_ECONOMIC_GAIN`).
    Zero safety rejections (`RAW_SAFETY_OR_GRAMMAR_REJECTION = 0`).
  - Byte-exact roundtrip verified: 16 / 16 transformed entries passed `decode_visible(transformed) == raw` byte-for-byte
    (`TRANSFORMED_ROUNDTRIP_FAILURES = 0`).
  - Structural fact preservation: `MATCH_DROPPING = 0`, `FILE_DROPPING = 0`, `ORDER_CHANGE = 0`,
    `MULTIPLICITY_CHANGE = 0`, `PAYLOAD_CHANGE = 0`, `PATH_CHANGE = 0`, `LINE_NUMBER_CHANGE = 0`.
  - Negative controls: Replayed 34 negative controls from `m03_rg_negative_controls_v1.jsonl`;
    `REAL_NEGATIVE_FALSE_TRANSFORMS = 0`.
  - Headroom adversarial challenges: Replayed 18 challenge cases; `AMBIGUOUS_CASES_TRANSFORMED = 0`.
  - Real economics: 62,373 raw bytes -> 51,577 visible bytes, saving 10,796 bytes (17.31% net reduction,
    or 2,699 tokens saved under `utf8_bytes_div_4_ESTIMATE`).
  - Simulation-to-production overhead: 6,556 bytes (10.51% of raw), reflecting robust version marker header (39 B),
    length-framed path headers (~49-55 B per path run) to eliminate colon and Windows-path ambiguity, and
    strict no-expansion fallback on 4 borderline cases.
  - Engine metadata status: `ENGINE_METADATA_GATE_REMAINS = YES`; generic `apply()` remains disabled.
- **DECISION**: Formally record `M04_TRANSFORM_REAL_REPLAY_VALIDATED = YES`. Confirm that
  `T02_RG_STANDARD_GROUP_V1` satisfies all empirical correctness and safety gates on real workloads.
  Maintain the engine metadata gate without automatic runtime routing until trusted provenance is available.
- **WHY**: The production transform satisfies every invariant on 100% of real historical clean candidates
  without requiring a single code change, while safely failing open to RAW when framing eliminates economic gain.
- **ALTERNATIVES_REJECTED**:
  - Forcing production representation to match unadorned M03 simulation (rejected: length-framing is essential for safe Windows/colon parsing).
  - Prematurely auto-activating T02 in generic engine or profiles without runtime producer evidence (rejected: preserves separation of transform correctness from integration architecture).
  - Delaying approval for further replay iterations (rejected: evidence on all 23 real candidates is unanimous).
- **REVERSIBILITY**: Replay validation confirms existing behavior without changing code or APIs; future missions may integrate runtime metadata propagation without altering the validated transform or decoder.

## M05-D001 — Selection of next development lane: Reexposure shadow layer

- **QUESTION**: Based on empirical measurement of real Codex workloads, which context waste class presents the highest proven avoidable volume and where should subsequent development focus?
- **EVIDENCE**: Complete census of Source A (`01a02f96`, 206,427,325 B, SHA-256 `bc4561d4...`) across 4,430 custom tool calls (20,515,430 total output bytes) revealed:
  - Reexposure Waste (LeanCTX lane): 205 exact redeliveries totaling 447,645 gross bytes, yielding 260,775 bytes (~65,194 tokens under `utf8_bytes_div_4_ESTIMATE`) of strictly proven avoidable waste, plus 490 same-file reread events (32 identical saving 168,727 B, 19 overlapping range reads with 596 overlapping lines).
  - Representation Waste (Headroom lane): 259 ripgrep calls evaluated; 15 admitted under T02 saving 7,909 proven avoidable bytes (~1,978 tokens).
  - Discovery Cost (Aider/AgentMap lane): 10,733,497 bytes across 1,183 pre-mutation calls in 165 episodes (52.3% of workload). Only 29,366 bytes were proven redundant; the remainder represents essential exploratory context.
  - Deduplicated total proven avoidable bytes: 268,684 bytes (1.31% of total output bytes). Reexposure constitutes 97.05% of all proven avoidable bytes, exceeding T02 representation headroom by ~33x.
- **DECISION**: Select `NEXT_LANE = REEXPOSURE_SHADOW`. Prioritize design of a session-aware shadow reexposure elimination layer for future missions. Do not implement runtime shadow mechanics in M05. Record `WHOLE_MISSION_SAVINGS = UNKNOWN`.
- **WHY**: Reexposure provides 33x greater proven byte-savings leverage than search grouping, operates on exact byte identity, preserves 100% of facts and authority, and avoids high-risk speculative filtering of exploratory reads.
- **ALTERNATIVES_REJECTED**:
  - Expanding static representation transforms first (low relative leverage; 7.9 KB vs 260.8 KB).
  - Aggressive discovery pruning or pre-filtering (high risk of evidence loss and model degradation on reasoning context).
  - Immediate implementation of hooks, proxy, or cache in M05 (violates mission scope and rigorous empirical gating).
- **REVERSIBILITY**: High. This decision selects research direction; no engine, profile, or transform code is modified.

## M05-D002 — Epistemic scope of exact redelivery versus reference replacement

- **QUESTION**: Does observation of 260,775 bytes of identical redelivery prove that replacing those deliveries with compact references is safe and preserves coding-agent task performance?
- **EVIDENCE**: M05 established `EXACT_REDELIVERY_BYTES_OBSERVED = 260,775` across 205 events via exact content SHA-256 matching. While this demonstrates physical byte redelivery within the session, it does not evaluate whether consumer reasoning or task execution depends on the inline presence of the full text rather than an indirect reference.
- **DECISION**: Formally record:
  - `EXACT_REDELIVERY_BYTES_OBSERVED = 260,775`
  - `PROVEN_IDENTICAL_REDELIVERY = YES`
  - `PROVEN_SAFE_REFERENCE_REPLACEMENT = NO`
  - `REFERENCE_SUPPRESSIBLE_BYTES = UNKNOWN_UNTIL_SHADOW_OR_AB`
  - `WHOLE_MISSION_SAVINGS = UNKNOWN`
  `NEXT_LANE` remains `REEXPOSURE_SHADOW`. Shadow evaluation must measure hypothetical reference eligibility under evidence and authority gates before any active suppression can be considered.
- **WHY**: Preserves scientific rigor by distinguishing observed physical repetition from behavioral safety of context substitution.
- **ALTERNATIVES_REJECTED**: Treating identical bytes as proof of safe reference substitution; claiming 260 KB of net context savings prior to shadow/A-B measurement.
- **REVERSIBILITY**: High. Pure epistemic classification boundary; no runtime engine code is altered.

## M06-D001 — Reexposure shadow results and selection of read receipt specialization

- **QUESTION**: Does empirical shadow evaluation of exact redeliveries in real coding agent workloads authorize active suppression, and where should reexposure development focus?
- **EVIDENCE**: Sequential shadow evaluation of all 4,430 calls in Source A (`bc4561d4...`) revealed:
  - Exact Content Redeliveries: 1,128 calls (331,661 B).
  - Same-Source Redeliveries: 68 calls (178,110 B).
  - Final Shadow-Eligible Candidates: 20 calls (9,401 B raw, 2,625 B hypothetical reference, 6,776 B hypothetical avoided).
  - Eligibility Retention: 3.61% of M05 repeated volume. 132.1 KB was excluded due to error/diagnostic markers, 33.0 KB due to sensitive material, 151.4 KB due to cross-source divergence, and 260 B due to economic non-expansion.
  - File Read Opportunity: Same-path file rereads account for 32 calls and 168,727 bytes of exact repeated content, but generic text classifiers flag documentation discussing errors as failures.
- **DECISION**: Formally record:
  - Active redelivery suppression remains **UNAUTHORIZED**.
  - `WHOLE_MISSION_SAVINGS = UNKNOWN`.
  - Select `NEXT_LANE = READ_RECEIPT_SHADOW_SPECIALIZATION`.
  - Prioritize design of a specialized read receipt evaluator with file system freshness, mtime, and worktree provenance.
- **WHY**: FILE_READ contains over 76% of repeated volume (168 KB). Specialized read receipts with provenance can safely distinguish static file inspection from execution failure logs, unlocking substantial context reduction without risk.
- **ALTERNATIVES_REJECTED**:
  - Authorizing active suppression in M06 (rejected: requires shadow/A-B behavioral validation).
  - Selecting generic reexposure active prototype (rejected: 96% of generic candidates fail evidence or economic gates).
  - Rejecting reexposure lane (rejected: 168 KB same-path file opportunity remains massive).
- **REVERSIBILITY**: High. Pure architectural direction; no runtime engine code is altered.

## M06-D002 — Metric scope reconciliation between M05 census and M06 funnel

- **QUESTION**: Do the reported counts of M05 exact redeliveries (205 events, 260,775 B) and M06 funnel redeliveries (1,128 calls, 331,661 B) represent a contradiction or counting defect?
- **EVIDENCE**: Investigation of event grouping confirmed two distinct scopes:
  - M05 census grouped by `(target_identity, output_sha256)` where `target_identity != "UNKNOWN"` (requiring parsed path or command). The 205 events were the total deliveries across targeted duplicate clusters (74 first deliveries + 131 repeat deliveries), and 260,775 B was the sum of repeated deliveries.
  - M06 funnel Step 2 evaluated universal content-hash recurrence across all 4,430 session calls (excluding first seen), capturing 1,018 cross-source matches (151,359 B) from differing tools/scripts before filtering down to same-source candidates.
- **DECISION**: Formally record:
  - `M05_BASELINE_SEMANTICS_DOCUMENTED = YES`
  - `M06_FUNNEL_SEMANTICS_DOCUMENTED = YES`
  - `METRIC_CONTRADICTION = NO`
  The metrics represent non-interchangeable scopes: M05 evaluated structurally targeted duplicate groups, while M06 evaluated the top of a universal content-repetition funnel.
- **WHY**: Maintains absolute precision and transparency in denominator reporting.
- **ALTERNATIVES_REJECTED**: Conflating universal content repetition with targeted duplicate clusters; redefining M05 historical observations retroactively.
- **REVERSIBILITY**: High. Pure epistemic and documentation clarification.

## M07-D001 — Specialization of read receipts, plane separation, and mtime spoof defense

- **QUESTION**: How should FioFilter specialize reexposure for file reads without premature context suppression or false-negative keyword gating?
- **EVIDENCE**: Controlled live experimentation and historical replay across Source A (`01a02f96`, 206,427,325 B, SHA-256 `bc4561d4...`) established:
  - **Plane Separation**: M06 showed that generic text classification flags benign documentation discussing errors as failures. Decoupling Plane A (Source Freshness / Byte Identity) from Plane B (Context Policy Authority) allows documentation to achieve `FRESHNESS_PROVEN = YES` while keeping `ACTIVE_SUPPRESSION_AUTHORIZED = NO`.
  - **Mtime Spoof Defense**: Live synthetic lab confirmed that `MTIME_UNCHANGED != CONTENT_UNCHANGED`. An adversary modifying bytes and restoring original timestamps is caught by SHA-256 content verification (`MTIME_SPOOF_DOES_NOT_BYPASS_HASH = PASS`). Level F4 requires exact byte equality.
  - **Read Grammar & View Coverage**: Out of 490 FILE_READ events in Source A, 489 (99.8%) have structured source identity and 459 (93.7%) have structured view identity.
  - **Historical Candidate Reconciliation**: 31 events achieved `F1_HISTORICAL_OUTPUT_IDENTITY` (184,684 B). 17 events are economic candidates (`HISTORICAL_IDENTICAL_READ_CANDIDATE`, 184,194 B raw, 2,432 B reference, 181,762 B avoided, 98.68% hypothetical savings). 14 events are uneconomic 35 B polling log tails rejected under the no-expansion invariant. Reconciled against M06 (32 events, 168,727 B) by shifting from adjacent path pairing to session-scoped view-aware tracking.
  - **Behavioral Authority**: Active context suppression carries salience and recency risks because model reasoning may depend on in-context token presence.
- **DECISION**:
  - Decouple Plane A (source freshness and byte identity) from Plane B (context suppression policy authority).
  - Record:
    - `M07_READ_DENOMINATOR_DEFINITION = All session tool calls classified under tool_family == 'FILE_READ' having a non-None target_path extracted by regex.`
    - `METRIC_CONTRADICTION = NO`
  - Require SHA-256 and byte equality (Level F4) for live freshness proof; treat mtime/size strictly as fast rejection hints.
  - Enforce strict no-expansion on hypothetical references (`[[FIOFILTER:READREF:v1 ...]]`).
  - Maintain `ACTIVE_READ_REFERENCE_SUPPRESSION = NO` (zero runtime suppression or modification).
  - Record `BEHAVIORAL_EQUIVALENCE = UNKNOWN`, `WHOLE_MISSION_SAVINGS = UNKNOWN`.
  - Select `NEXT_LANE = READ_RECEIPT_RUNTIME_SHADOW_HARNESS`.
- **WHY**: Establishes deterministic mathematical certainty for file content freshness without compromising model reasoning, evidence integrity, or authority.
- **ALTERNATIVES_REJECTED**:
  - Using mtime or git HEAD as proof of content invariance (vulnerable to spoofing, race conditions, and uncommitted edits).
  - Active runtime suppression in M07 (violates evidence gating before behavioral A/B proof).
  - Keyword-based error filtering on file bodies (causes false-negative exclusion on technical documentation).
- **REVERSIBILITY**: High. Pure shadow specialization; generic engine runtime remains completely unmodified.

## M08-D001 — Operational proof of runtime shadow harness, reexposure freeze, and lane selection

- **QUESTION**: How should FioFilter prove runtime observation for read receipts without modifying agent execution or waiting for an unavailable Codex environment?
- **EVIDENCE**:
  - Dual-mode architecture implemented and empirically benchmarked:
    - Mode A (`PASSIVE_STREAM_SHADOW`): Ingests append-only JSONL via `PassiveJsonlTailSource` with complete partial-write safety (`PARTIAL_JSON_DOUBLE_PROCESSING = 0`, `PARTIAL_JSON_LOSS = 0`). Streamed 35,040 records of Source A (206 MB) in 8.861 s (3,954.6 rec/sec) with median chunk latency of 122.17 ms.
    - Exact equivalence: Mode A streaming evaluation produced 490/490 identical decisions to M07 batch baseline (`STREAM_VS_BATCH_EQUIVALENCE = PASS`).
    - Mode B (`DIRECT_READ_LAB`): Single-read architecture mitigates byte divergence (`PROOF_DELIVERY_BYTE_DIVERGENCE_WINDOW = 0_BY_SINGLE_BUFFER`, `FILESYSTEM_POST_READ_MUTATION_POSSIBLE = YES`), achieves exact byte-for-byte transparency (`HARNESS_RAW_OUTPUT == DIRECT_BASELINE_READ`), isolates observer telemetry failures (`SHADOW_FAILURE_RAW_DELIVERY_PRESERVED = PASS`), and defeats timestamp spoofing.
    - Crash consistency & rewind defense: Verified via atomic checkpoints (`ShadowCursor`) and `SourceRewindException`.
    - Observational salience hygiene: `FIRST_DELIVERY_NOT_SALIENCE_RISK = YES` (445 first-time deliveries excluded from reread salience risk), `SALIENCE_REPEAT_DENOMINATOR_EXPLICIT = YES` (45 true repeat events: NEAR 22.2%, MEDIUM 37.8%, FAR 2.2%, VERY_FAR 37.8%).
    - Memory footprint: Labeled as `APPROXIMATE_RECEIPT_OBJECT_FOOTPRINT` ≈180 KB.
  - Codex execution environment is currently unavailable (`LIVE_CODEX_SHADOW = NOT_RUN_CODEX_UNAVAILABLE`).
- **DECISION**:
  - Formally record:
    - `ACTIVE_READ_REFERENCE_SUPPRESSION = NO`
    - `FIRST_DELIVERY_NOT_SALIENCE_RISK = YES`
    - `SALIENCE_REPEAT_DENOMINATOR_EXPLICIT = YES`
    - `PROOF_DELIVERY_BYTE_DIVERGENCE_WINDOW = 0_BY_SINGLE_BUFFER`
    - `FILESYSTEM_POST_READ_MUTATION_POSSIBLE = YES`
    - `LIVE_CODEX_SHADOW = NOT_RUN_CODEX_UNAVAILABLE`
    - `REEXPOSURE_STATUS = READY_FOR_LIVE_CODEX_SHADOW`
    - `NEXT_LANE = DISCOVERY_STRUCTURAL_SHADOW`
  - Freeze the reexposure research lane in this verified, operational state.
  - Advance FioFilter discovery into the structural shadow lane for multi-turn coding agent patterns.
- **WHY**: Operational harness proof is established without waiting on external dependencies or compromising behavioral safety. Conforms strictly to mission discipline and decision rules.
- **ALTERNATIVES_REJECTED**:
  - Blocking progress waiting for Codex availability.
  - Fabricating synthetic Codex interactions to simulate live execution.
  - Activating premature reference redelivery without agent-in-the-loop behavioral testing.
- **REVERSIBILITY**: High. Shadow harnesses remain read-only and decoupled from core engine primitives.


---

## M09-D001 — Structural Discovery Shadow as Non-Authoritative Control Plane

- **QUESTION**: How should structural repository indexing (RepoMap/AgentMap donor mechanisms) be integrated into FioFilter without violating lossless evidence invariants or introducing unverified context pruning?
- **EVIDENCE**:
  - **Donor Mechanism Evaluation**:
    - Aider RepoMap: Personalized PageRank (PPR) power iteration with damping alpha=0.85, task-personalized teleport seeds, compact budgeted symbol signature maps (1KB to 8KB).
    - AgentMap: Strict decoupling of FILE_GRAPH from SYMBOL_INDEX, Graph Health accounting (parse_coverage=100%, `RECOGNIZED_LOCAL_IMPORT_RESOLUTION_COVERAGE=429/429`, `GRAPH_RELATION_COMPLETENESS=UNKNOWN` — AST IMPORT edges only; CALLS, TEST_RELATES, REEXPORTS not extracted), distinction of intra-repo candidates from external/stdlib roots.
  - **Single Implementation Backend**: `PYTHON_AST_LOCAL_RESOLVER_V1` implemented strictly via Python standard library `ast`, `hashlib`, `pathlib`, `subprocess` (zero heavy external dependencies, zero LSP servers, zero daemon processes, zero embeddings).
  - **Commit-History Benchmark**: Evaluated across 13 eligible historical commits in FioFilter's own Git repository using non-destructive Git plumbing (`git ls-tree` / `git show`):
    - All Eligible Commits (13 tasks):
      - `LEXICAL_ONLY`: R@1=23.1%, R@3=53.8%, R@5=61.5%, R@10=69.2%, MRR=0.3821, MissTop10=4
      - `STRUCTURAL_ONLY`: R@1=7.7%, R@3=15.4%, R@5=23.1%, R@10=30.8%, MRR=0.1346, MissTop10=9
      - `LEXICAL_PLUS_STRUCTURAL`: R@1=23.1%, R@3=46.2%, R@5=46.2%, R@10=53.8%, MRR=0.3462, MissTop10=6
      - `LEXICAL_PLUS_PPR`: R@1=23.1%, R@3=46.2%, R@5=46.2%, R@10=53.8%, MRR=0.3462, MissTop10=6
    - Non-Leaking Subset (10 strictly audited tasks where commit message contained no file path or file stem):
      - `LEXICAL_ONLY`: R@1=20.0%, R@3=50.0%, R@5=60.0%, R@10=70.0%, MRR=0.3633
      - `STRUCTURAL_ONLY`: R@1=10.0%, R@3=10.0%, R@5=20.0%, R@10=30.0%, MRR=0.1417
      - `LEXICAL_PLUS_STRUCTURAL`: R@1=20.0%, R@3=50.0%, R@5=50.0%, R@10=60.0%, MRR=0.3500
      - `LEXICAL_PLUS_PPR`: R@1=20.0%, R@3=50.0%, R@5=50.0%, R@10=60.0%, MRR=0.3500
  - **Explicit Donor Hypothesis Result**:
    - `CURRENT_GLOBAL_STRUCTURAL_SIGNALS_DO_NOT_BEAT_LEXICAL_BASELINE`: **PROVEN** on 10-commit non-leaking corpus.
    - `PPR_VALUE_AS_IMPLEMENTED`: **NOT_PROVEN** — identical or inferior to LEXICAL_ONLY in all measured recall bands.
    - `STRUCTURAL_ONLY_VIABLE_AS_STANDALONE`: **FALSE** — 30% Recall@10 is insufficient.
    - `GLOBAL_CENTRALITY_DISAMBIGUATES_TASK_INTENT`: **NOT_PROVEN**.
    - These are valid empirical **negative results** and constitute success per M09 mission contract.
  - **Source A Discovery Shadow Replay**: Replayed 490 `FILE_READ` calls across 256 distinct targets in 151 episodes. Exactly 490 (100.0%) occurred in the pre-edit exploration phase before any mutating operations.
    - `SOURCE_A_DISCOVERY_ACTIVITY_CHARACTERIZED`: YES — episode structure characterized.
    - `SOURCE_A_STRUCTURAL_RANK_REPLAY`: NOT_PROVEN — no ground-truth task→target labels from Source A; ranking quality unverified.
  - **Overhead & Economics**: Building the full AST snapshot for 60 files and 848 symbols required only 180.70 ms and negligible memory (~2 MB). Budgeted signature maps compress the entire repository structure into 1KB (~254 tokens) to 8KB (~2046 tokens).
- **DECISION**:
  - Formally establish that the structural discovery lane belongs strictly to the non-authoritative CONTROL PLANE, distinct from the lossless EVIDENCE PLANE:
    - `INDEX != EVIDENCE`
    - `INDEX != AUTHORITY`
    - `RANK != CORRECTNESS`
    - `LOW_RANK != IRRELEVANT`
    - `BUDGET_APPLIES_TO_INDEX_ONLY = True`
    - `EVIDENCE_OVERRIDES_BUDGET = True`
    - `DISCOVERY_READ_SUPPRESSION = False`
    - `AUTO_CONTEXT_SELECTION = False`
    - `INDEX_ONLY_SHADOW = True`
  - Structural indices and budgeted maps may be used for exploration assistance, navigation, and explanation, but CANNOT be used to silently prune, suppress, or substitute for canonical source reads requested by the coding agent.
  - Advance the structural shadow lane in this validated shadow-only state without active suppression.
  - **M09 VERDICT**: `M09_DISCOVERY_SHADOW_PASS_MORE_RANKING_EVIDENCE_REQUIRED`
- **WHY**: Maintains evidence rigor and behavioral safety while delivering reproducible, explainable structural navigation with zero external runtime dependencies. Negative donor hypothesis result (structural does not beat lexical) is a valid finding that simplifies the M10 direction.
- **ALTERNATIVES_REJECTED**:
  - Active read suppression during discovery (would risk omitting critical context needed by the LLM before behavioral equivalence is independently proven).
  - External language server protocol (LSP) or Tree-sitter binary daemons (unnecessary complexity and violates minimal dependency mission rule).
  - Vector embeddings or LLM-based query expansion (nondeterministic, heavyweight, and violates offline determinism).
- **REVERSIBILITY**: High. The structural shadow is completely decoupled from the evidence store, transform engine, and read receipt ledger.


---

## M10-D001 — BM25_LEXICAL as Strong Deterministic Baseline; Structural Relations Not Authorized

- **QUESTION**: Does BM25-style lexical ranking improve over the M09 legacy stem-overlap baseline, and does the miss autopsy justify adding structural relations (IMPORTS, CALLS, TEST_RELATES)?
- **EVIDENCE**:
  - **BM25_STYLE_LEXICAL_V1** implemented in `fiofilter/discovery_lexical.py`:
    - Query tokenization V2: normalizes snake_case, camelCase, PascalCase into atomic lowercase tokens; same normalization applied to code for query-code parity.
    - Frozen V1 weights: `k1=1.2`, `b=0.75`.
    - Preserved `LEGACY_LEXICAL` (M09 mode) for ablation parity.
  - **Benchmark Expansion**: Rescanned all 18 FioFilter commits; 9 benchmarked (7 non-leaking, 2 path-leaking); 9 correctly skipped (new-file commits where GT files did not exist in parent snapshot).
  - **Ablation Results (non-leaking, n=7)**:
    - `LEGACY_LEXICAL`: R@1=16.3%, R@5=54.0%, R@10=60.3%, MRR=0.6786
    - `BM25_LEXICAL`: R@1=16.3%, R@5=57.9%, R@10=65.9%, MRR=0.6786
    - **BM25_LEXICAL wins R@10 by +5.6pp; MRR equal.**
  - **Miss Autopsy V2**: 1 miss@10 in both modes (commit 5091ac08). Cause: `ZERO_LEXICAL_OVERLAP` — commit message uses epistemic/abstract terms ("clarify, epistemic, scope, redelivery, replacement") while ground-truth file is `context_census.py`. No ranking algorithm, structural or lexical, can bridge this vocabulary gap from available query signals.
  - **Structural Relations Authorization**: Negative. Miss autopsy finds no miss attributable to missing graph topology. `DO_NOT_PAY_GRAPH_COMPLEXITY_FOR_A_LEXICAL_PROBLEM = ENFORCED`.
  - **Source A**: `SOURCE_A_BM25_LEXICAL_REPLAY = NOT_PROVEN` (no task→target labels available).
- **DECISION**:
  - Establish `BM25_LEXICAL` as the new strong deterministic lexical baseline.
  - Freeze V1 weights: `k1=1.2`, `b=0.75`. Any change requires a superseding M10-D001 entry.
  - Do NOT implement `fiofilter/structural_relations.py` — miss autopsy does not justify it.
  - Record:
    - `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_R10 = PROVEN` (+5.6pp on 7-commit non-leaking corpus)
    - `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_MRR = NOT_PROVEN` (equal on this corpus)
    - `STRUCTURAL_RELATIONS_V2_AUTHORIZED = FALSE`
    - `PPR_VALUE_AS_IMPLEMENTED = NOT_PROVEN` (unchanged from M09)
    - `DISCOVERY_READ_SUPPRESSION = NO` (frozen)
  - **M10 VERDICT**: `BM25_LEXICAL_MARGINAL_WIN_STRUCTURAL_RELATIONS_NOT_AUTHORIZED`
- **WHY**: BM25 provides measurable improvement with zero added complexity or external dependencies. The miss autopsy definitively attributes the only failure to a vocabulary mismatch that structural graph edges cannot resolve. Structural relations remain unauthorized — a valid and valuable negative result that keeps FioFilter simpler.
- **ALTERNATIVES_REJECTED**:
  - Implementing structural_relations.py (IMPORTS, CALLS, TEST_RELATES) without miss autopsy justification (rejected: DO_NOT_PAY_GRAPH_COMPLEXITY_FOR_A_LEXICAL_PROBLEM).
  - Embeddings or LLM query expansion (rejected: nondeterministic, heavyweight, violates offline determinism constraint).
  - Tuning BM25 k1/b weights before holdout evaluation (rejected: must freeze V1 weights before any evaluation to avoid overfitting).
  - Declaring BM25 universally superior to legacy (rejected: improvement is PROVEN only on 7-commit non-leaking corpus; MRR equal).
- **REVERSIBILITY**: High. `discovery_lexical.py` is completely additive — it does not modify any existing engine, transform, or profile. Legacy ranker preserved for regression comparison.


---

## M10-R1-D001 — Benchmark Reconciliation, Determinism Hardening, Field Diagnostic

- **QUESTION**: Does the M10 benchmark population, leakage classification, and ranking implementation satisfy integrity requirements for an evidence-grade benchmark?
- **EVIDENCE**:
  - **M09 Merge-Policy Incident**: PR #8 merged with `gh pr merge 8 --squash` instead of exact fast-forward. Squash commit tree SHA matches branch head tree SHA (content preserved). Author identity violation: `ph.pedrogarcia@gmail.com` (not NOREPLY). `DO_NOT_USE_GH_PR_MERGE_FOR_EXACT_FAST_FORWARD_MISSIONS=YES`.
  - **Benchmark Census Repair** (exact `git ls-tree` path matching, not basename): 19 commits total (18 main + 1 branch head). Buckets: ROOT_NO_PARENT=1, NO_PYTHON_CHANGE=3, NEW_FILE_ONLY=6, EXISTING_FILE_ONLY=5, MIXED_EXISTING_AND_NEW=4. Benchmarkable: 9. Leakage reclassified: NON_LEAKING=5, PATH_LEAKING=4 (was 7/2 in M10 original — corrected by exact tokenize_v2 stem matching).
  - **Ranking Determinism Fix**: `BM25Index.rank()` and `legacy_rank()` now sort by `(-score, path)` — stable tie-breaker, deterministic regardless of PYTHONHASHSEED or insertion order.
  - **Hash-Seed Reproducibility**: `HASH_SEED_RANKING_DETERMINISM=PASS` (seeds 1, 42, 999 produce identical rankings).
  - **Input-Order Independence**: `INPUT_ORDER_INDEPENDENCE=PASS` (original, reversed, shuffled corpus orders produce identical rankings).
  - **Corrected Metrics** (NON_LEAKING, n=5): LEGACY_LEXICAL R@10=36.7% MRR=0.6000; BM25_LEXICAL R@10=36.7% MRR=0.4500. Original M10 BM25_LEXICAL R@10 win (+5.6pp) was a benchmark artifact of incorrect leakage classification. `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_R10=NOT_PROVEN` on corrected corpus.
  - **Small-Sample Limitations**: N=5 non-leaking → `NO_WEIGHT_TUNING`, `TEMPORAL_HOLDOUT=INSUFFICIENT_SAMPLE`, `GENERAL_SUPERIORITY=NOT_PROVEN`.
  - **Zero-Overlap Field Diagnostic** (miss commit 5091ac08, GT=`fiofilter/context_census.py`):
    - PATH_ONLY overlap: 0 tokens
    - PATH_PLUS_SYMBOL overlap: 0 tokens (symbols: CensusEvent, ContextWasteCensus, analyze, load_session, etc.)
    - FULL_SOURCE_TEXT overlap: 3 tokens (exact, m05, redelivery)
    - Result: `CURRENT_PATH_SYMBOL_BM25_HAS_ZERO_DIRECT_OVERLAP` + `INDEX_FIELD_COVERAGE_GAP`
    - The original M10 claim "no algorithm can bridge this gap" is **CORRECTED**: the gap is a field coverage limitation, not a fundamental impossibility. Full source text indexing is `DIAGNOSTICALLY_PROMISING`.
  - **Structural Bridge Diagnostic**: At parent snapshot 725597f8, BM25 returns zero positive-score results for the miss query — `NO_LEXICAL_SEED_EXISTS`. Importers of context_census.py (run_context_waste_census.py, test_context_census.py) are not reachable via BM25 expansion because there are no seeds. `STRUCTURAL_RELATION_STATUS=NOT_AUTHORIZED_YET`.
- **DECISION**:
  - Record M09 merge-policy incident as audited. Do NOT rewrite history.
  - Correct benchmark census and leakage classification. Preserve original M10 artifacts.
  - Adopt `(-score, path)` sorting as permanent determinism contract for BM25 and legacy rankers.
  - Record `HASH_SEED_RANKING_DETERMINISM=PASS`, `INPUT_ORDER_INDEPENDENCE=PASS`.
  - Demote M10 original BM25 R@10 win claim: `BM25_LEXICAL_BEATS_LEGACY_LEXICAL_R10=NOT_PROVEN` on corrected corpus.
  - Record `INDEX_FIELD_COVERAGE_GAP` (full text has overlap; path+symbol does not).
  - Record `STRUCTURAL_BRIDGE_RESULT=NO_LEXICAL_SEED_EXISTS`.
  - Set `STRUCTURAL_RELATION_STATUS=NOT_AUTHORIZED_YET` (diagnostically noted, not authorized).
  - Canonical verdict: `M10_CANONICAL_VERDICT=M10_DISCOVERY_REFINEMENT_PASS_LEXICAL_FIRST`.
- **WHY**: Evidence-grade benchmarks require exact path matching, correct leakage classification, deterministic ranking, and scoped claims. The field coverage gap is an actionable finding (field expansion is a legitimate future direction) rather than a dead end.
- **ALTERNATIVES_REJECTED**:
  - Keeping PATH_LEAKING classification based on naive prefix matching (rejected: exact tokenize_v2 stem matching is more rigorous).
  - Claiming BM25 wins on non-leaking corpus without leakage correction (rejected: overclaim).
  - Claiming "no algorithm can bridge the vocabulary gap" universally (rejected: field coverage gap makes full-text indexing potentially viable).
  - Adding structural relations or full-text indexing in M10-R1 (rejected: diagnostic only, not authorized).
- **REVERSIBILITY**: High. Determinism fix is a pure sort key change. Benchmark corrected, original artifacts preserved. Full-text indexing or structural relations require separate authorization.


---

## M11-D001 — Lexical-First Discovery Runtime Shadow Harness

- **QUESTION**: Can FioFilter establish an explicit runtime shadow harness for lexical discovery navigation without changing agent behavior, violating evidence invariants, or installing intrusive hooks?
- **EVIDENCE**:
  - **M10-R1 Finalization**: Exact fast-forward promotion to main (`362e6e6eba526ca1d7ebe1e28553678a92573e6e`, tree `08566b3b3e4c9def41c31271cb3a5a94c597ec0a`). No squash, full commit provenance preserved.
  - **Harness Implementation**: `DiscoveryRuntimeShadow` in `fiofilter/discovery_runtime_shadow.py`.
    - Returns metadata only: snapshot ID, query hash, ranked candidate paths, explanations, map bytes, timings.
    - Explicit invocation only — no background daemons, MCP servers, proxies, shell traps, or agent hooks.
    - Invariants enforced: `INDEX_AUTHORITY = NAVIGATION_ONLY`, `DISCOVERY_READ_SUPPRESSION = NO`, `AUTO_CONTEXT_SELECTION = NO`, `SHADOW_FAILURE_AGENT_PATH_UNCHANGED = PASS`.
  - **Provenance & Determinism**:
    - Every evaluation bound to: `head_sha`, `dirty_digest`, `snapshot_id`, `query_hash`, `tokenizer_version`, `bm25_version` (`k1=1.2, b=0.75`), `indexed_fields`, `tie_break_policy` (`SCORE_DESC_PATH_ASC`).
    - Stale snapshot defense: `dirty_digest` from `git status --porcelain` invalidates cache upon worktree change.
    - `RUNTIME_SHADOW_DETERMINISM = PASS`.
  - **Self-Shadow Experiment (Live Anecdotal Evidence)**:
    - Prework prediction before M11 edits using M11's own mission query.
    - Primary modified file `fiofilter/discovery_runtime_shadow.py` retrieved at rank 6 (`SELF_SHADOW_CHANGED_FILE_RECALL_AT_10 = 0.5`).
    - Label: `ANECDOTAL_LIVE_EVIDENCE_N1_TASK`.
  - **Synthetic Stream**: 5 deterministic tasks; cold query ~251 ms, warm query ~230 ms; map ~909 bytes (~227 estimated tokens).
  - **Privacy**: Append-only local ledger (`shadow_ledger.jsonl`) stores only query hashes and metadata; raw task queries are never logged.
  - **Tests**: 37 new tests in `tests/test_discovery_runtime_shadow.py` (485 total suite passing).
- **DECISION**:
  - Authorize `DiscoveryRuntimeShadow` as the explicit discovery shadow harness.
  - Enforce `INDEX_AUTHORITY = NAVIGATION_ONLY` and strict failure isolation (`SHADOW_FAILURE_AGENT_PATH_UNCHANGED = PASS`).
  - Maintain behavioral claims as unproven: `DISCOVERY_BYTES_AVOIDABLE = UNKNOWN`, `MODEL_TURN_SAVINGS = UNKNOWN`, `BEHAVIORAL_EQUIVALENCE = UNKNOWN`.
  - Transition discovery shadow lane to: `DISCOVERY_READY_FOR_LIVE_CODEX_SHADOW`.
  - **M11 VERDICT**: `M11_DISCOVERY_RUNTIME_SHADOW_PASS_LIVE_TARGET_READY`.
- **WHY**: M11 establishes an auditable, deterministic, zero-risk navigation orientation plane. It enables evaluating potential discovery benefits without altering agent interactions or creating untested context injection hazards.
- **ALTERNATIVES_REJECTED**:
  - Automatic prompt injection / context insertion (rejected: violates evidence boundary and agent agency).
  - Read suppression based on index ranking (rejected: indexing is navigational, not evidentiary).
  - Global hooks / shell interception / MCP daemon (rejected: violates mission discipline).
  - Persisting raw task queries to disk ledger (rejected: privacy violation).
  - Claiming token/turn savings without live multi-turn agent trials (rejected: unverified claim hygiene).
- **REVERSIBILITY**: High. Standalone component with zero hooks, external dependencies, or side-effects on the runtime environment.


---

## M11-R1-D001 — Content-Sensitive Worktree Fingerprinting (V2) & Self-Shadow Invalidation

- **QUESTION**: How should FioFilter detect worktree mutations accurately and handle contaminated prework evidence without weakening evidence discipline?
- **EVIDENCE**:
  - **Status-Only Failure Case**: Demonstrated in controlled laboratory repository: modifying an already-dirty file produces identical `git status --porcelain` text (`' M file.py'`), leaving status-derived hash unchanged. Result: `STATUS_ONLY_STALE_DETECTION_FAILURE = REPRODUCED`.
  - **Content-Sensitive Fingerprint (V2)**: Implemented `get_worktree_state_digest_v2()` in `fiofilter/discovery_runtime_shadow.py`. Binds to HEAD SHA + `git diff --binary HEAD -- *.py` + sorted untracked *.py SHA-256 byte hashes. Scoped to `INDEXED_FILE_UNIVERSE_POLICY = "PYTHON_SOURCES_V1"`.
  - **Adversarial Verification Gates**:
    - `ALREADY_DIRTY_SECOND_MUTATION_DETECTED = PASS`
    - `STAGED_UNSTAGED_MATRIX = PASS`
    - `UNTRACKED_SAME_STATUS_CONTENT_CHANGE_DETECTED = PASS`
    - `DELETE_RENAME_NEW_FILE = PASS`
    - `CONTENT_IDENTITY_NOT_MTIME_IDENTITY = PASS` (mtime touch with identical bytes preserves digest)
    - `CACHE_HIT_REQUIRES_V2_KEY = PASS` (composite key: repo, head, digest_v2, bm25_v, policy)
    - `STALE_CACHE_DEFENSE = PASS` (dirty file mutation forces index rebuild)
  - **Formal Invariants**: `WORKTREE_STATUS_IS_NOT_CONTENT_IDENTITY`, `CACHE_HIT_MUST_BE_PROVEN`.
  - **Self-Shadow Experiment Audit**: Local inspection of `m11_self_shadow_prework_v1.json` revealed candidate #6 was `fiofilter/discovery_runtime_shadow.py`. That file was created on disk prior to the prework script execution. Result: `SELF_SHADOW_PREWORK_CONTAMINATED = YES`. Status updated to `M11_SELF_SHADOW_N1 = INVALIDATED_PREWORK_CONTAMINATION`. The artifact is preserved locally as negative evidence; `Recall@10 = 0.5` is NOT counted as live empirical evidence.
  - **Synthetic Stream Semantics**: Task SYN-004 returned R@10=0 (`store.py` vs query describing T02). Clarified semantics: `HARNESS_EXECUTION_SUCCESS = 5/5`, `TARGET_RETRIEVAL_AT_10 = 4/5`. Failure classified as `QUERY_TARGET_MISMATCH_AND_TARGET_LABEL_QUESTIONABLE`. Negative result preserved.
  - **Remeasured Runtime Costs (V2)**: Cold query ~326 ms (state validation ~143 ms, AST parsing ~174 ms, index build ~8.6 ms); index-reuse query ~144 ms (state validation ~143 ms, index build 0 ms). Terminology: `INDEX_REUSE_QUERY`.
  - **Tests**: 43 tests in `tests/test_discovery_runtime_shadow.py` (491 total suite passing).
- **DECISION**:
  - Replace status-only dirty digest with `WORKTREE_STATE_DIGEST_V2`.
  - Require proven V2 cache key match for index reuse (`CACHE_HIT_MUST_BE_PROVEN`).
  - Invalidate M11 self-shadow experiment while preserving the local artifact.
  - Correct synthetic stream reporting semantics.
  - Maintain Discovery lane status: `DISCOVERY_READY_FOR_LIVE_CODEX_SHADOW`.
  - **M11 CANONICAL VERDICT**: `M11_DISCOVERY_RUNTIME_SHADOW_PASS_LIVE_TARGET_READY`.
- **WHY**: Freshness must be grounded in exact content deltas rather than git porcelain text. Negative or contaminated experimental results must be invalidated and preserved rather than rationalized or hidden.
- **ALTERNATIVES_REJECTED**:
  - Retaining status-only dirty digest (rejected: fails second-mutation detection).
  - Deleting or silently replacing contaminated self-shadow artifact (rejected: violates evidence preservation).
  - Hashing entire filesystem indiscriminately (rejected: creates noisy invalidations from unrelated files).
  - Calling index-reuse queries "full warm cache" (rejected: obscures essential state validation overhead).
- **REVERSIBILITY**: High. V2 digest and cache keys are purely in-memory and isolated to the discovery shadow harness.


---

## M12-D001 — FioFilter V0 Explicit Integration Spine

- **QUESTION**: Has FioFilter reached a coherent explicit V0 whose existing proven capabilities can operate together without widening authority?
- **EVIDENCE**:
  - **Integrated Architecture**: Unified existing proven components under `FioFilterV0Lab` (`fiofilter/v0.py`) and CLI (`fiofilter/cli.py`, `python -m fiofilter`):
    - BM25 Discovery Runtime Shadow (`fiofilter/discovery_runtime_shadow.py`) with V2 content-sensitive fingerprinting (`WORKTREE_STATE_DIGEST_V2`).
    - Read Receipt Shadow Evaluator (`fiofilter/read_receipt.py`, `fiofilter/runtime_shadow.py`).
    - Lossless ripgrep grouping (`fiofilter/transforms/t02_rg_standard_group.py`) under caller-supplied `RgStandardEvidence`.
  - **Capability Registry**: Established explicit registry with 6 non-collapsing lifecycle states: `IMPLEMENTED`, `VALIDATED_OFFLINE`, `SHADOW_READY`, `LIVE_VALIDATED`, `ACTIVE_AUTHORIZED`, `PRODUCTION_READY`. All capabilities remain `NOT_PRODUCTION_READY`.
  - **Cross-Component Invariants**:
    - `DISCOVERY_RANKING_CANNOT_AUTHORIZE_READ_SUPPRESSION = True`
    - `READ_RECEIPT_CANNOT_AUTHORIZE_TRANSFORM = True`
    - `T02_CANNOT_HIDE_CRITICAL_EVIDENCE = True`
    - `SHADOW_CANNOT_CHANGE_RAW_OUTPUT = True`
    - `UNKNOWN_ANYWHERE_CAN_FAIL_TO_RAW = True`
    - `CAPABILITY_DOES_NOT_GRANT_AUTHORITY = True`
    - `ENGINE_METADATA_GATE_REMAINS = True`
    - `DEFAULT_DISPOSITION = RAW`
  - **End-to-End Laboratory Scenario**: Deterministically executes task query navigation -> file read -> repeated read -> search output -> metrics accounting in ~350 ms. Exact RAW bytes delivered across all reading and search stages.
  - **Accounting Integrity**: Formally separated `ACTUAL_VISIBLE_BYTES_REDUCED` (0 B in default lab) from `SHADOW_HYPOTHETICAL_BYTES_AVOIDED` (49,058 B in repeated read). Forbidden from being summed.
  - **Failure Isolation & Privacy**: Exceptions fail open to RAW bytes; local ledgers store only SHA-256 hashes without raw task queries.
  - **Tests**: 17 new tests in `tests/test_v0_integration.py` (508 total across full test suite passing).
- **DECISION**:
  - Authorize the FioFilter V0 Explicit Integration Spine.
  - Declare project status: `V0_EXPLICIT_LAB_COMPLETE`.
  - Discovery and Reexposure lanes both hold at: `READY_FOR_LIVE_CODEX_SHADOW`.
  - Next milestone when Codex resumes: `LIVE_SHADOW_VALIDATION`.
  - **M12 CANONICAL VERDICT**: `M12_V0_EXPLICIT_LAB_PASS`.
- **WHY**: M12 provides a single, coherent, and safe interface for developers to inspect and evaluate FioFilter's capabilities without introducing unauthorized runtime hooks, proxy interception, or autonomous context manipulation.
- **ALTERNATIVES_REJECTED**:
  - Adding more offline optimization algorithms before integrating V0 (rejected: violates phase discipline).
  - Summing hypothetical reference savings with actual transform savings (rejected: misleading accounting).
  - Installing background daemons or auto-intercepting Codex/Antigravity sessions (rejected: strictly prohibited).
  - Claiming production readiness from offline lab pass (rejected: honest lifecycle boundaries).
- **REVERSIBILITY**: High. Standalone integration layer with zero global hooks or side effects.
