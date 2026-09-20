# M15-C1 — first genuine active canary evidence

## Scope and provenance

One genuine FioFilter development task ran through the explicit M15 Codex-local
client on a clean local mission branch from `b1b42af188043d196b8ae4e84d4dbfced053ac3f`.
The designated full-file source was `AI-START-HERE.md`, explicitly assessed
NON_SENSITIVE. The task formalized `INSTRUCTION_REEXPOSURE_WASTE` and built a
shadow-only deterministic Mission Context contract. No second canary task,
manufactured reread, global activation, merge, or push occurred during the
active canary.

The sanitized client record is held outside Git in the local temporary
directory. It contains no prompt, raw source content, final model text,
command text, or private absolute path.
The model's final prose and full task trace were not captured by this client;
quality is assessed from the changed files and objective validation below.

## Active observation

```text
CANARY_ACTIVE=YES
VERDICT=M15_C1_PASS_NO_ELIGIBLE_REREAD
TASK_OUTCOME=COMPLETED (App Server turn status)
ELIGIBLE_REREADS=0
READREF_EMITTED=0
RAW_FALLBACKS=0
RECOVERY_REQUESTS=0
GROSS_VISIBLE_BYTES_SAVED=0
REFERENCE_BYTES=0
RECOVERY_BYTES=0
ADDITIONAL_CONTEXT_BYTES=1157
NET_VISIBLE_BYTES_SAVED=-1157
CANARY_ANOMALIES=NONE_REPORTED
ACTUAL_CAUSAL_TOKEN_SAVINGS=UNAVAILABLE
ACCOUNT_TOKEN_COUNTER_DELTA=0
PRIMARY_RATE_LIMIT_USED_PERCENT=12_TO_28
RATE_LIMIT_DELTA_IS_NOT_TOKEN_SAVINGS
```

The record does not include initial-read count or a full trace, so it does not
prove whether the designated source was read once or not at all. It does prove
there was no eligible reread or READREF emission in this session. The negative
net is the client-side additional context charge, not a token measurement.

`account/usage/read` reported lifetime tokens `2676629446 -> 2676629446`
(delta `0`). `account/rateLimits/read` reported primary used percentage
`12 -> 28` (delta `+16` percentage points). The App Server separately reported
per-thread total `763081` tokens. These observations differ in timing and
scope; none is a READREF-causal saving or a reliable task-only bill.

The UTF-8 mission prompt sent to the App Server was `1988` bytes, SHA-256
`fc6985fc91769327f898fdaa9c0ab108972affc80fe81ccf223f92cc195b5362`.
No comparable recent pre-delta prompt for this *same* development task was
available: `REFERENCE_PROMPT_BYTES=UNAVAILABLE` and
`MISSION_INSTRUCTION_REEXPOSURE_REDUCTION=UNAVAILABLE`. The shorter prompt is
an observed prompt size, not a measured reduction against an invented baseline.

## Task quality and boundary

The result is a narrow in-memory shadow contract, not an active optimizer. It
evaluates `INLINE_CRITICAL`, `REFERENCE_CANONICAL`, `DELTA`, and exact whole
`DROP_DUPLICATE`; all actual deliveries remain RAW. Same-session recovery does
not authorize hiding facts, caller-designated critical byte occurrences remain
inline, and UNKNOWN assessment prevents candidates. Donor/repo reconnaissance
is recorded in `M15-C1-D001` and the contract document.

Post-canary review found two task-code defects: `DROP_DUPLICATE` did not require
the current repeated bytes, and invalid UTF-8 raised instead of returning RAW.
Focused tests reproduced both failures. The local review then added exact
repeat proof and RAW fallback, plus a regression for duplicate critical IDs.
The corrected focused tests passed `10/10`; the full suite passed `571/571`;
`compileall` passed. This is verification in the current test corpus, not a
CONTROL/TREATMENT quality comparison. No READREF was emitted, so the repairs
do not indicate a READREF-induced behavioral regression.

**Verdict:** `M15_C1_PASS_NO_ELIGIBLE_REREAD`. A useful development task was
completed and verified, but active context saving was **not observed**. The
canary remains default OFF; production and global activation remain unauthorized.
