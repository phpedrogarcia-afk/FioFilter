# M04 RG standard lossless grouping

## Boundary

M04 implements exactly one transform:

```text
TRANSFORM_ID=T02_RG_STANDARD_GROUP_V1
AUTHORIZED_GRAMMAR=RG_STANDARD_PATH_LINE_TEXT
```

It is not generic ripgrep compression. Column, context, heading, JSON, color,
binary notices and unknown formats remain unauthorized. The historical corpus is
not required at runtime and no historical bytes are committed.

## Producer evidence gate

Verified evaluation requires all of:

- structurally grounded command extraction;
- one single-purpose ripgrep producer;
- command classification to exactly `RG_STANDARD_PATH_LINE_TEXT`;
- exit code 0;
- complete, non-truncated stdout/combined output;
- no upstream truncation or shell-failure wrapper;
- every material line accepted by the validated parser;
- no reserved representation marker collision.

The current engine receives a free-form `ToolResult.command`, not proof of how
that string was extracted. Therefore:

```text
GRAMMAR_TRANSFORM_IMPLEMENTED=YES
AUTOMATIC_ENGINE_ACTIVATION_AUTHORIZED=NO
ENGINE_METADATA_GATE_REMAINS=YES
```

The transform is registered for explicit verified evaluation. Generic
`apply(content)` returns `None`, and no core/profile whitelist selects it.

## Representation v1

The visible representation begins with:

```text
[[FIOFILTER:T02_RG_STANDARD_GROUP:v1]]
```

Each contiguous path run starts with a versioned, byte-length-delimited path
header. Every following match retains the exact line number, payload and original
LF/CRLF/unterminated-tail behavior. Path length avoids colon splitting and admits
validated Windows drive and UNC paths.

Paths are grouped only while consecutive. For input order A/A/B/A, the output has
three runs: A, B, A. A path never disappears because it appeared earlier.

```text
ORDER_PRESERVATION=100_PERCENT_BY_CONSTRUCTION
MULTIPLICITY_PRESERVATION=100_PERCENT_BY_CONSTRUCTION
MATCH_DROPPING=0
FILE_DROPPING=0
GLOBAL_REGROUPING=NO
```

## Decoder and exactness

The decoder parses the representation independently and reconstructs:

```text
path + ":" + line_number + ":" + payload + original_line_ending
```

The activation oracle is:

```text
decode(encode(parse(raw))) == raw
```

Comparison is byte-for-byte. Decoder failure, tampering, invalid lengths,
malformed records or a recovery-bound violation is explicit and cannot normalize
content silently.

## Collision and no-expansion

Raw input containing the reserved T02 prefix returns RAW. Already-transformed
input is not treated as raw rg output. Marker/header overhead counts toward visible
bytes. If the candidate is not strictly smaller:

```text
REASON=VALID_GRAMMAR_NO_ECONOMIC_GAIN
DISPOSITION=RAW
```

No file/match caps, ranking, adaptive K or “N more” summaries exist.

## Fail-closed cases

RAW is required for:

- one unparsed or ambiguous material line;
- column-like ambiguity under the standard grammar;
- composite producer, ungrounded command or mixed canonical output;
- nonzero exit or truncation;
- context separators, headings, JSON, ANSI/color and binary notices;
- marker collision, decoder mismatch or invalid representation;
- valid representations with zero or negative byte gain.

## Headroom donor differential

Adopted:

- group-by-file concept, limited to contiguous runs;
- Windows/UNC, hyphen, date, CVE and digit-heavy path challenges;
- parser-failure telemetry and known ambiguity cases.

Rejected:

- lossy selection, ranking, match/file dropping and adaptive caps;
- heuristic recovery or best-effort acceptance after parse failure;
- global regrouping that changes A/B/A order;
- corrective retrieval rate as justification for information omission.

Headroom is a donor, not an authority. Synthetic fixtures reproduce failure
classes without copying private data.

## Metadata and units

Each verified evaluation exposes transform ID/version, recognized grammar, raw,
candidate and visible byte counts, bytes saved, no-expansion fallback and decoder
roundtrip state. `utf8_bytes_div_4_ESTIMATE` may be derived explicitly.

These are not actual model tokens, billing savings, whole-mission savings or an
operational corrective-retrieval rate. The latter remains
`UNKNOWN_UNTIL_SHADOW_OR_AB`.

## Known limitations

- Concrete M04 representation has not yet been replayed on the private real corpus.
- Automatic engine activation awaits trusted producer metadata propagation.
- Only the exact standard path/line/text grammar is authorized.
- No Codex hook, proxy, MCP, LLM, shadow mode or M05 mechanism is included.
