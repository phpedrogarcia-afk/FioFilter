# Evidence contract — V0 / M02

Normative goals plus explicit implementation limits. Profiles/modes never weaken
evidence invariants. M02 amendments supersede M01 unconditional persistence,
automatic persistent logging, mode-escalation wording and JSON-equivalence claims;
see M02-D001 through M02-D008 in `DECISIONS.md`.

## I1 — RAW immutability

The library never overwrites an existing blob. Explicit disk writes use unique
temporary files and no-clobber publication, then verify existing data. Ephemeral
bytes are immutable and owned by RawRef. No protection against an OS/admin changing
files is claimed; corruption is detected. No automatic deletion engine exists.

## I2 — Transform linkage

Every returned TRANSFORM result has raw_ref (disk or ephemeral), raw_sha256,
transform_id, policy_decision and evidence_class. DO_NOT_PERSIST cannot transform.
A RAW result may have no reference; it still exposes original bytes and its audit.

## I3 — Byte-exact RAW recovery

Every successful recovery verifies `sha256(bytes) == ref.sha256` and returns
original bytes. Verification cannot be disabled. Availability is conditional on
the intact blob or a retained ephemeral reference. It is not promised for
DO_NOT_PERSIST, missing/corrupt archives or discarded in-memory references.

RAW recovery is distinct from reconstructing RAW from visible transformed bytes.
T01 additionally supports the latter with an independent decoder/oracle.

## I4 — Inline-required facts

Declared/classifier-designated facts must appear as original UTF-8 bytes inline;
their occurrence counts must not decrease. A multi-line fact broken by a marker
or a repeated required fact folded to one occurrence rejects the transform.
T01 preserves source lines and verifies exact visible reconstruction. Automatic
identification of every material fact in arbitrary language is not established.

## I5 — Unknown defaults to RAW

Unknown classes, insufficient/invalid confidence and unknown profiles cannot
transform. Repetition is not proof that a sentence is disposable.

## I6 — Failure preservation

Any nonzero exit forces RAW regardless of class, mode or profile. Explicit failure
signals anywhere in the input also force RAW. This is per-result disposition,
not mutable session state or implicit mode changes. Signal detection remains
heuristic; complete known-noise grammar is additionally required for reduction.

## I7 — Authority, security and sensitivity

AUTHORITY and SECURITY are RAW in V0. Sensitivity is an orthogonal attribute,
not another evidence class. Detected/declared sensitive input is DO_NOT_PERSIST:
RAW visibility without an archive or persistent audit log. Absence of detector
matches does not prove non-sensitivity. An explicit NON_SENSITIVE assessment and
PERSIST request authorize storage, never transformation of protected evidence.

## I8 — Machine consumer compatibility

No machine-data transform is approved in V0. T04 is DEFERRED. Future contracts
must distinguish byte identity, parse equivalence, semantic equivalence,
canonical representation and consumer compatibility. `json.loads(a) ==
json.loads(b)` alone does not cover duplicate keys, lexical numbers, ordering,
signatures, whitespace consumers or alternate parsers. No generic caller hint
relaxes this invariant or authorizes JSON minification.

## I9 — No expansion

Returned TRANSFORM bytes must be strictly shorter than RAW, including marker and
header overhead. Otherwise return RAW. This is local content cost only.

## I10 — Corrective retrieval economics

Avoid reductions whose corrective retrieval cost defeats the mission benefit.
V0 does not predict this cost. Externally supplied retrieval/turn observations
are recorded separately and unmeasured values remain None. This invariant is
an economic design constraint, not an implemented optimization model.

## I11 — Deterministic V0

No LLM or network call exists in classification/transformation. Classification,
policy and T01 content are deterministic for identical inputs. Clock-derived
latency and optional audit timestamps are observations, not deterministic content.

## I12 — Profile non-weakening

Canonical Python policy is the upper bound. The engine intersects profile
whitelists/dispositions with core policy, checks the selected transform and
restricts T01 to NOISE/PROGRESS. No YAML operational policy remains.

## I13 — Source/batch identity

A result retains source/command/session/stream/exit/truncation metadata in memory.
Separate streams should be separate calls. No batching or interleaving capture is
implemented. The library cannot reconstruct boundaries already lost upstream.

## I14 — Units and unknown measurements

Exact raw/visible content bytes, byte-based token ESTIMATES, apply-only milliseconds,
actual model tokens, model turns, corrective retrievals and RAW recovery counts
are distinct. External observations default to None, not a manufactured zero.
The bytes/4 estimate is not billing or model-token truth.

## I15 — No local-to-mission conflation

Local content reduction does not establish fewer model turns, fewer billed tokens,
better quality or whole-mission savings. No FioFilter mission A/B has been measured.
Historical FioOS experiments are not measurements of this implementation.

## I16 — Audit without secret harvesting

Each returned valid-byte result has an in-memory audit with schema, profile, mode,
class, invariant checks reached, reason, disposition, transform ID, persistence
and sensitivity. Early failures explicitly identify the failed stage; checks not
reached are not claimed to have passed. Results retain SHA/context in memory.

Disk JSONL audit is independently opt-in for non-sensitive results. It contains
controlled decision fields, counts/estimates and digest, never source content,
commands, session strings or inline facts. DO_NOT_PERSIST bypasses disk logging.
Log failure returns RAW with in-memory failure audit. A crash before return can
prevent any audit delivery; persistent logging is not an unconditional invariant.

## Unapproved proposals

I17 adaptive transform deprioritization and I18 batch limits mentioned in M01 were
proposals, not implemented invariants. They remain deferred, unnumbered extensions
for a later mission. No code should claim I17/I18 enforcement.
