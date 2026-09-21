# M15-S2 — Mission Context manifest foundation

## Status

```text
SCHEMA=FIO_MISSION_CONTEXT_MANIFEST_V1
MISSION_CONTEXT=SHADOW_ONLY
READREF_CANARY=OFF
PROMPT_SUPPRESSION=NO
SEMANTIC_INFERENCE=NO
PROMPT_BODY_PERSISTED=NO
ACTIVE_DELIVERY_AUTHORIZED=NO
```

M15-S2 adds a compact author-supplied provenance envelope to the S1 exact-byte
shadow analyzer. It makes future mission prompts measurable at delivery time
without reconstructing them afterward. It does not rewrite, intercept, shorten,
or replace the mission delivered to an agent.

## Compact schema

The canonical serialization is compact ASCII JSON with sorted keys, no optional
whitespace, and one final LF. Its keys are intentionally short because every
manifest byte is charged to the hypothetical economics:

| Key | Meaning |
| --- | --- |
| `v` | Exact schema version, `FIO_MISSION_CONTEXT_MANIFEST_V1`. |
| `m` | Safe mission identifier. |
| `h` | SHA-256 of the complete exact mission bytes. |
| `n` | Complete exact mission byte count. |
| `s` | Explicit sensitivity assessment; only `NON_SENSITIVE` can support a reference proof. |
| `e` | Ordered byte-range entries. |

Entries are bounded tuples:

```text
["I", mission_start, mission_end]
["D", mission_start, mission_end]
["R", mission_start, mission_end,
 repository_relative_path, artifact_sha256, artifact_start, artifact_end]
```

`I` means `INLINE_CRITICAL`, `D` means `DELTA`, and `R` means
`CANONICAL_REFERENCE`. These codes have no semantics outside this versioned
grammar. `I` and `D` always remain inline. An `R` entry becomes a verified
canonical byte count only if the tracked repository file exists, its complete
SHA-256 matches, its range is valid, and that range is byte-identical to the
declared mission span. A path mention or author label alone is not proof.

The schema contains no `DROP_DUPLICATE`, semantic-equivalence, free-form reason,
prompt, or payload field. Undeclared gaps are `UNKNOWN` and remain inline.
Malformed JSON, extra fields, mission hash/length mismatch, overlap, missing
artifacts, wrong hashes, invalid ranges, sensitivity uncertainty, and detector
matches all fail conservative. They never authorize hiding bytes.

The implementation is `fiofilter.mission_context_manifest`; the explicit runner
is `scripts/run_mission_context_manifest_shadow.py`. Repository proof and
shadow delivery reuse `MissionContextShadowAnalyzer` rather than implementing a
second canonical-reference grammar.

## Economics and durable record

`MANIFEST_BYTES` is the exact size of the supplied serialized manifest,
including its final LF. The only S2 gross opportunity is mechanically verified
canonical content:

```text
PROVEN_REEXPOSURE_BYTES = VERIFIED_CANONICAL_REFERENCE_BYTES
NET_CANDIDATE_REDUCTION_BYTES = PROVEN_REEXPOSURE_BYTES - MANIFEST_BYTES
MANIFEST_ECONOMIC_WIN = NET_CANDIDATE_REDUCTION_BYTES > 0
```

A negative value is preserved. No bytes/4, provider token, Plus-credit,
behavioural-equivalence, or active saving claim follows from this accounting.

The durable result contains identifiers, hashes, counts, proof outcome and
failure classes. It contains no mission body, candidate body, credential,
private absolute path, or semantic model judgment. The supplied mission buffer
is returned unchanged and `ACTIVE_DELIVERY_AUTHORIZED=false`.

## Current-mission dogfood

The exact visible S2 mission text was available during execution and was held in
a transient, untracked file only. The committed
[`M15-S2-DOGFOOD-MANIFEST.json`](M15-S2-DOGFOOD-MANIFEST.json) contains its
hash, length and disposition offsets, not its content.

The author-visible `CRITICAL` section was declared `INLINE_CRITICAL`; the
`OBJECTIVE` section through the end was declared `DELTA`; the preceding routing
and read list remained undeclared and therefore `UNKNOWN`. No text was declared
canonical because this mission mentions repository paths but does not reproduce
the referenced artifact bytes.

```text
MISSION_ID=FIOFILTER-M15-S2-MISSION-CONTEXT-MANIFEST
EVIDENCE_QUALITY=CURRENT_MISSION_VISIBLE_TEXT_UTF8_LF
RAW_MISSION_BYTES=3639
MANIFEST_BYTES=223
INLINE_CRITICAL_BYTES=218
DELTA_BYTES=3153
VERIFIED_CANONICAL_REFERENCE_BYTES=0
UNKNOWN_BYTES=268
PROVEN_REEXPOSURE_BYTES=0
NET_CANDIDATE_REDUCTION_BYTES=-223
MANIFEST_ECONOMIC_WIN=NO
PROOF_OUTCOME=PASS
DELIVERED_MISSION_MUTATED=NO
```

The 223-byte manifest is 6.13% of this mission's raw byte count, but there are
zero proven reexposure bytes against which to amortize it. Therefore this sample
is not an efficiency win. It tests the foundation and provides no estimate of
instruction-waste prevalence.

## Limits

- One exact sample cannot establish prevalence or typical economics.
- Author dispositions are provenance, not permission to suppress content.
- Exact artifact identity proves byte provenance, not behavioural equivalence or
  model salience.
- The schema does not discover spans, infer semantic duplication, or select
  canonical material.
- No prompt optimizer, rewriter, hook, proxy, daemon, Fio Handoff bridge, or
  active Mission Context path was added.
- READREF remains off and unrelated to this shadow-only manifest.
