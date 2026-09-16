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

