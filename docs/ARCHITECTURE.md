# FioFilter architecture — hardened V0

The public entry point is `fiofilter.engine.process(ToolResult(...))`. It consumes
bytes already captured by another tool. It does not execute commands or intercept
Codex. M02 supersessions are recorded in `DECISIONS.md`.

## Pipeline

1. Validate byte input and policy enums. Assess sensitivity using full content,
   metadata and the caller declaration. Decide persistence independently.
2. Classify the entire input. No 16 KiB prefix sampling. Nonzero exit wins;
   credential signals, explicit failures, security findings, authority, warnings,
   canonical state and benchmarks precede low-risk reduction eligibility.
3. Intersect the selected Python profile with canonical `DefaultProfile` policy.
   Check invariants after selecting the actual transform ID.
4. Restrict eligibility for incomplete input, unsupported content hints, stderr,
   unknown stream identities and Git command metadata. Metadata never establishes
   that output is safe to compress. Unknown profiles return RAW.
5. Prepare disk or reference-owned ephemeral RAW recovery before an engine-routed transform. If storage
   is forbidden or preparation fails, return RAW; never fabricate a disk reference.
6. Run T01 only for eligible NOISE/PROGRESS. Validate bytes, strict size reduction,
   inline facts and their occurrences, and independent visible decoding == RAW.
7. Return bytes, metadata, per-result metrics and a content-free in-memory audit.
   An explicitly requested non-sensitive JSONL log is written before returning;
   log failure falls back to RAW and is reported in the returned audit.

Operational exceptions in classification, policy, store, transform, validation or
logging return original bytes with an audit reason. Invalid non-byte API input is
a programmer error and raises TypeError: there are no original bytes to return.
Process termination, memory exhaustion beyond a return path, and hostile OS behavior
are outside the ordinary exception guarantee.

## Evidence policy and profiles

`fiofilter/profiles/*.py` is the only operational policy source. YAML copies were
removed. `DefaultProfile` is the upper bound; overlays cannot add eligibility.
At current V0, FioOS/FioIdeias have the same effective T01 scope as the hardened
core, while retaining distinct project identities. They do not have an independent
policy table requiring synchronization.

NOISE requires every line to match the finite known-boilerplate grammar. It may
use T01 in all modes. PROGRESS requires every line to match a known progress or
noise grammar and may use T01 in EXPLORE/BUILD. Other classes are RAW in current
V0. Discovery, diagnostics and success output require future consumer contracts;
this is a transform-scope limit, not a claim they are universally irreducible.

M04 registers `T02_RG_STANDARD_GROUP_V1` but does not add it to core/profile
whitelists or engine selection. Its verified evaluation API requires explicit
structural command provenance, a single ripgrep producer, exit 0, complete output
and the exact authorized grammar. Current `ToolResult.command` is free-form and
cannot by itself establish that provenance, so automatic activation remains RAW.

There is no session object, mutable mode state or one-way escalation. A failure
forces RAW on that result and never locks later calls into PROVE or RAW.

## Sensitivity and persistence

| Disposition | Meaning |
|---|---|
| PERSIST | Explicit request plus caller NON_SENSITIVE assessment; detector may veto |
| EPHEMERAL | Default; immutable RAW bytes held in the returned RawRef only |
| DO_NOT_PERSIST | RAW visibility with no archive reference and no persistent audit |

Sensitivity is UNKNOWN / NON_SENSITIVE / SENSITIVE, independently of the twelve
evidence classes. A public vulnerability finding can be SECURITY with allowed
persistence; a credential embedded in boilerplate is SENSITIVE and cannot acquire
persistence permission from any evidence class. The detector is heuristic and
scans metadata too; absence of a match is never a NON_SENSITIVE determination.

No redaction, encryption, global in-memory history, OS memory locking or retention
engine is implemented. Caller handling, swap and crash dumps are not controlled.
Low-level `RawStore.write` is itself an explicit disk-storage operation for
assessed non-sensitive data, with a detector backstop. It does not save source,
command, session or inline facts. Engine users should use ToolResult's explicit
policy instead of bypassing it with low-level writes.

## Disk RAW store

Default configured root is `~/.fiofilter/raw/`, overridable with
`FIOFILTER_RAW_STORE`. Creating/importing a store handle writes nothing.

- `objects/<two hex chars>/<sha256>`: original raw bytes.
- `meta/<two hex chars>/<sha256>.json`: schema 2, RAW SHA-256 and exact byte length.
- No index, event log or command metadata archive in the store.

Write a unique temporary file in the destination directory, flush and fsync it,
then publish using `os.link` with no overwrite. The temporary name is unlinked
on normal success/failure. Same-directory creation ensures the same volume.
Both simultaneous writers verify the published bytes and metadata before success.
This requires hard-link support, tested on the CI filesystems; unsupported filesystems
raise and the engine returns RAW. No overwrite fallback exists.

Dedup verifies existing content; corruption is never silently repaired. Reads
validate the digest and ignore the supplied path hint, using the store root and
validated lowercase SHA-256. Disabling verification is rejected. Object/metadata
symlinks are rejected; a trusted, private store root and parent directories are
assumed. This is not an adversarial filesystem sandbox.

Metadata is separately and atomically published. Interrupted publication can
leave a complete blob with no sidecar: byte recovery still works, `read_meta`
returns None, and a later explicit write may reconstruct missing derived metadata.
Corrupt or inconsistent metadata raises; missing blobs raise. An attempted disk
write may leave a blob even when metadata fails; returned audit reports
`FAILED_MAY_HAVE_BLOB`, never falsely claims DO_NOT_PERSIST after that write. There is no claim
of a transaction covering both files or power-loss durability of directory entries.
A killed process can leave a private temporary file; V0 does not scavenge it.

M01 stores may already contain secrets and contextual metadata. M02 neither
scans nor deletes those archives automatically. Legacy sidecar schemas are rejected
explicitly; intact blobs remain byte-recoverable. Use a fresh store root for schema 2.

## T01 v2

The header is `[[FIOFILTER:T01:v2]]` followed by LF. An unchanged source line is
followed by a separate `[[FIOFILTER:T01 count=N first=F last=L]]` marker and LF.
N includes the first occurrence; F/L are inclusive 1-based original line positions.
All raw source lines containing `[[FIOFILTER:` decline transformation.

Only exact consecutive byte-identical LF/CRLF lines fold; order, line ending style,
unique lines and unterminated tails survive. Invalid UTF-8, NUL, ANSI/control
sequences and bare CR decline. Marker/header overhead must pay for itself.
`decode_visible` rejects malformed bounds and has a bounded output allocation.
The engine compares decoded bytes to RAW independently of disk/ephemeral recovery.
T01 is a representation for a human/model, never a machine-format minifier.

## T02 RG standard grouping v1

The M04 transform imports the validated M03 parser rather than defining another
rg grammar. It emits a versioned header and length-delimited path header for each
contiguous run, followed by every original line number, payload and line ending.
An A/B/A sequence therefore emits three runs; paths are never globally regrouped.
The independent decoder must reproduce RAW byte for byte. Reserved-marker input,
decoder mismatch, ambiguity, unauthorized grammar and non-reducing candidates
return RAW. This direct API is deterministic but not engine-routed.

## Metadata, batching and truncation

Input/output carry source, command, session, exit code, stream and known-truncated
flag in memory. Process stdout/stderr as separate results when boundaries are
available. `combined` describes already combined input; FioFilter cannot infer
lost interleaving or repair upstream truncation. No batching/session architecture
is implemented. The caller retains source/event identity and ordering.

## Economics

`raw_bytes` and `visible_bytes` count content bytes, including T01 header/markers.
They exclude the Python object, RAW archive and any downstream transport envelope.
Serializing the entire object or ephemeral RAW bytes to a model would defeat local
reduction; no such transport integration has been implemented or measured.

`utf8_bytes_div_4_ESTIMATE` uses bytes/4, not Unicode characters/4 or a tokenizer.
`transform_duration_ms` measures apply() only, excluding store/classifier/validator
and logging. Actual model tokens, turns, corrective retrieval and RAW recovery
counts are optional externally supplied metrics; None means unknown, not zero.
No automatic predictive economics or whole-mission savings are claimed.

## M13 Codex Web post-delivery shadow

`CodexWebShadowEventAdapter` is outside the execution path. A caller may submit
sanitized metadata only after Codex has already received the RAW tool output.
The adapter reuses the M08 historical/read-receipt evaluator, M11 discovery
shadow and M04 T02 evaluator without broadening any capability's authority.

The current runtime has no repository-consumable event subscription. Therefore
the adapter is an explicit observation bridge, not a hook, proxy or execution
intermediary. Passive reads establish at most F1 delivery identity; they are not
relabeled direct-execution F4. T02 is evaluated only when structural producer,
exit, truncation and stream evidence is supplied; otherwise its metadata gate
remains closed. Discovery requires exact structured task text.

`FIO_EFFICIENCY_FEED_V1` persists only hashed identities, counts, explicit token
measurement qualities, repository-relative paths and outcome classes. It has no
fields for prompts, messages, command text, authorization data or file/tool
contents. Its aggregate keeps exact and estimated token classes separate and
cannot activate an optimization.
