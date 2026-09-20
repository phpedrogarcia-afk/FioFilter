# M15-C1 — deterministic Mission Context contract

## Status and scope

```text
WASTE_CLASS=INSTRUCTION_REEXPOSURE_WASTE
FOUNDATION_DELIVERY=RAW_ONCE
CANONICAL_RECEIPT=EPHEMERAL_SAME_SESSION_ONLY
ACTIVE_DELIVERY_AUTHORIZED=NO
BEHAVIORAL_EQUIVALENCE=UNKNOWN
WHOLE_MISSION_SAVINGS=UNKNOWN
PERSISTENCE=NO
NETWORK=NO
HOOK_OR_PROXY=NO
```

`INSTRUCTION_REEXPOSURE_WASTE` is the repeated delivery of a previously
established mission-instruction foundation to the same task session or a later
mission context. It is a first-class **design waste class**, not a measured
volume or a claim that such repetition may be hidden safely. No census of this
class has been run in M15-C1.

The executable foundation is `fiofilter.mission_context.MissionContextSession`.
It is an in-memory, explicit construction with no CLI, canary, normal-runtime,
App Server, hook, proxy, persistence, or network integration. Every result it
returns delivers RAW bytes. It produces compact bytes only as a deterministic
shadow candidate for a later independently authorized evaluation.

## Contract

The intended flow is deliberately narrow:

```text
FOUNDATION (RAW once)
  -> CANONICALIZE (same-session SHA-256 receipt)
  -> REFERENCE (identity + recoverability only)
  -> SEND DELTA (when non-empty)
  -> KEEP CRITICAL SALIENCE INLINE
```

### Inputs

| Field | Meaning | Required rule |
| --- | --- | --- |
| `session_id` | Explicit ephemeral context scope. | Stable safe identifier; cross-session references fail. |
| `foundation_bytes` | UTF-8 instruction foundation. | Non-empty; delivered RAW on canonicalization. |
| `critical_facts` | Named UTF-8 byte facts designated by the caller. | Each must occur at least once in the foundation; its original non-overlapping occurrence count becomes the inline requirement. |
| `assessment` | `NON_SENSITIVE`, `UNKNOWN`, or `SENSITIVE`. | Only explicit `NON_SENSITIVE` can create/evaluate a candidate; `UNKNOWN => RAW`. |
| `mode` | One of the four evaluations below. | Exact enum only. |
| `inline_critical_bytes` | Caller-supplied visible copy of critical facts. | Required candidate occurrence count for every fact; a reference never counts as inline. |
| `delta_bytes` | UTF-8 task-specific addition. | Required and non-empty for `DELTA`; no partial duplicate analysis is attempted. |
| `repeated_foundation_bytes` | Caller-supplied current repeat for `DROP_DUPLICATE` only. | Must be present and byte-equal to the stored foundation; otherwise return the current bytes RAW without a candidate. |

### Outputs

`CanonicalizationResult` returns `disposition`, `delivered_bytes`, optional
same-session `FoundationReceipt`, and `reason`. `MissionContextDecision`
returns `requested_mode`, `disposition`, `delivered_bytes`, candidate/reference
fields, exact candidate-byte avoidance, `reference_recoverable`,
`active_delivery_authorized`, `behavioral_equivalence`, and `reason`.

`delivered_bytes` is always RAW. A shadow candidate always reports:

```text
active_delivery_authorized = false
behavioral_equivalence = UNKNOWN
```

Thus `RECOVERABLE != SAFE_TO_HIDE`: exact recovery is an integrity oracle, not
authority or behavioural proof for suppressing instructions.

### Four evaluated modes

| Mode | Deterministic evaluation | Delivery / authorization |
| --- | --- | --- |
| `INLINE_CRITICAL` | Baseline: foundation plus delta remains fully RAW and visible. | RAW; zero candidate saving. |
| `REFERENCE_CANONICAL` | Exact same-session foundation with exact recovery, all designated critical occurrences supplied inline, and strict no-expansion. | Shadow candidate only; RAW delivered. |
| `DELTA` | As `REFERENCE_CANONICAL`, with a non-empty UTF-8 delta appended after the inline facts. | Shadow candidate only; RAW foundation plus delta delivered. |
| `DROP_DUPLICATE` | Only a caller-supplied whole repeat byte-equal to the stored foundation; partial block matching, semantic deduplication, and rewrite are deferred. | Shadow candidate only; RAW delivered. |

Candidate bytes are exactly `MISSIONREF + newline + inline_critical_bytes +
delta_bytes`. The contract does not invent separators inside caller-provided
critical or delta data and does not try to extract, summarize, rank, or rewrite
instruction text.

## Fail-closed rules

Return RAW and expose no candidate when any condition holds:

- assessment is `UNKNOWN` or `SENSITIVE`, or the deterministic sensitive scan
  detects material in foundation, inline facts, or delta;
- foundation/critical/delta bytes are invalid UTF-8, empty where prohibited, a
  fact is missing, a fact ID is duplicated, or the inline occurrence count is
  below its recorded foundation count;
- receipt/reference is malformed, unissued, cross-session, length-mismatched,
  or fails SHA-256 recovery verification;
- `REFERENCE_CANONICAL`/`DROP_DUPLICATE` carry a delta, `DELTA` has no delta,
  or `DROP_DUPLICATE` has no supplied repeat or a changed repeat;
- the reference plus explicit inline facts and delta is equal to or larger than
  the RAW delivery;
- the requested mode is not an exact supported enum.

The foundation itself is not persisted. The session retains a byte buffer only
for same-session exact-recovery verification; it never writes a record or
activates an external delivery path.

## Objective tests

`tests/test_mission_context.py` proves in the current corpus that:

1. the foundation is first delivered RAW and a same-session receipt recovers
   byte-exactly;
2. `INLINE_CRITICAL`, `REFERENCE_CANONICAL`, `DELTA`, and `DROP_DUPLICATE` have
   the stated bounded semantics;
3. a recoverable reference still has `active_delivery_authorized=false` and
   `behavioral_equivalence=UNKNOWN`;
4. every original designated critical-fact occurrence must remain in the inline
   candidate representation;
5. UNKNOWN assessment, invalid UTF-8, duplicate fact IDs, a missing inline
   occurrence, an unproven/changed duplicate, a non-economic candidate, and
   cross-session recovery fail closed.

## Limits deliberately retained

This does not measure instruction repetition, provider tokens, model quality,
corrective retrievals, salience/recency effects, or whole-mission savings. It
does not infer critical facts automatically, prove a no-match sensitive scan is
safe, make a reference authoritative, or authorize hiding any foundation text.
An active treatment would need a separately authorized behavioural experiment
with frozen controls and recovery fully charged.
