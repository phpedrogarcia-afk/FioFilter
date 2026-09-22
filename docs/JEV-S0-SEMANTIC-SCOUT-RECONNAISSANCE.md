# Jev S0 — semantic scout reconnaissance

## Status

```text
MODE=EXPLORE
TYPESAFE_SKILL_PRESENT=YES
TYPESAFE_SKILL_PATH=.agents/skills/typesafe-ai/SKILL.md
SKILL_NAME=typesafe-ai
SKILL_BYTES=10189
TYPESAFE_CREDENTIAL_PRESENT=NO
LIVE_PROBE=BLOCKED_NO_CREDENTIAL
JEV_AUTHORITY=ADVISORY_ONLY
MISSION_CONTEXT=SHADOW_ONLY
READREF=OFF_PAUSED
ACTIVE_SUPPRESSION=NO
PRODUCTION_READY=NO
```

The local skill lock identifies `typesafe-ai/skills`; its installed `SKILL.md`
has SHA-256 `0ab58b7533ebe4ba5342ad6260d69e492cd0955ca9d3ee20b3c91375eea0203d`.
The current official SDK documentation identifies `TYPESAFE_API_KEY` as its API
credential variable. It was not present in the current environment. No value
was read or logged, no request was made, and no TypeSafe package, router, MCP
server, proxy, or Codex configuration was installed.

The official [System One documentation](https://docs.typesafe.ai/concepts/system-one.md)
describes Jev as returning typed decisions and probabilities, rather than text
or reasoning. The [HTTP API](https://docs.typesafe.ai/api.md) accepts one state
and a map of typed questions for `jev-latest`. The local skill and official
[parallel-question guidance](https://docs.typesafe.ai/cookbooks/parallel_questions.md)
support batching independent questions against one bounded state. These are
interface facts, not evidence that any individual judgment is correct.

## Donor autopsy

| Mechanism | Classification | FioFilter boundary |
| --- | --- | --- |
| Deterministic shortlist before semantic reranking | ADOPT_CONCEPT | Only FioFilter code may enumerate routes, documents and sections. Jev never discovers the universe. |
| Typed `Choice` | ADAPT | Rank an already finite set of route IDs, always including `NO_SAFE_SUGGESTION`. The answer cannot select a route. |
| Typed `Score` | ADAPT | Grade investigation priority for a supplied document/section candidate. It can order human attention only. |
| Typed `Noul` | ADAPT | Express probabilities for deeper-evidence, cross-route and architecture-risk questions. Probability never turns UNKNOWN into irrelevant. |
| One state with independent batched questions | ADOPT_CONCEPT | A future opt-in call may batch the questions below, but has no read/suppression side effect. |
| Probability and confidence fields | KEEP | Preserve them as model observations. They are not evidence, certainty, permission, or a safety threshold. |
| External TypeSafe evaluation endpoint | DEPEND | A future live experiment needs an already available credential and documented access. S0 has neither. |
| Project-local agent skill | KEEP | It supplies design/documentation guidance only; it does not alter Codex or FioFilter execution. |
| Automatic model choice, route selection, context deletion, or proof substitution | DELETE | These conflict with deterministic routing, evidence preservation and advisory-only authority. |

The relevant reusable shape is the reranking cookbook's two-stage pattern:
deterministic retrieval creates a bounded candidate set, then a semantic model
only orders that set. FioFilter retains the stronger restriction that the order
cannot alter context delivery in S0.

## `FIOFILTER_JEV_SCOUT_V0` contract

This is a proposed external-sidecar contract, **not an implementation or
runtime integration**. It may be exercised only after a separately authorized
live experiment. FioFilter generates the input deterministically and retains
control of every next action.

### Bounded input

```text
PROTOCOL=FIOFILTER_JEV_SCOUT_V0
MISSION_SUMMARY_MAX_UTF8_BYTES=4096
CANDIDATE_ROUTES_MAX=10
CANDIDATE_DOCUMENTS_MAX=32
CANDIDATE_SECTIONS_MAX=64
SENSITIVITY_ASSESSMENT=NON_SENSITIVE_REQUIRED
```

The state contains only:

```text
MISSION_SUMMARY
CANDIDATE_ROUTES: [{route_id, deterministic_label}]
CANDIDATE_DOCUMENTS: [{route_id, repository_relative_path, blob_sha256}]
CANDIDATE_SECTION_METADATA: [{route_id, repository_relative_path, heading, start_byte, end_byte, blob_sha256}]
```

`CANDIDATE_*` entries must originate from the A–J router, `section_working_set`
or another deterministic FioFilter procedure. The scout receives no unconstrained
repository walk, source payload, credential, raw prompt body, external command,
or persistence/security policy. A caller must explicitly assess the entire
state `NON_SENSITIVE`; absent, ambiguous or sensitive assessment means no live
call. A detector no-match does not create that assessment.

### Advisory typed questions

| ID | Type | Bounded answer space / criterion | Permitted use |
| --- | --- | --- | --- |
| `ROUTE_RANK` | Choice | Supplied route IDs plus `NO_SAFE_SUGGESTION`; which candidate appears most relevant to `MISSION_SUMMARY`? | Display or investigation order only. |
| `NEEDS_DEEPER_EVIDENCE` | Noul | Probability that material outside the suggested initial deterministic route is needed. | Add review attention; never omit material. |
| `CROSS_ROUTE` | Noul | Probability that more than one supplied route is relevant. | Add review attention; never narrow scope. |
| `ARCHITECTURE_RISK` | Noul | Probability that the task changes an authority, evidence or runtime boundary. | Escalate to deterministic route H/I review; never authorize a change. |
| `DOCUMENT_PRIORITY` | Score | Ordered levels: low, medium, high investigation priority for each supplied candidate. | Rank inspection order only. |
| `SECTION_PRIORITY` | Score | Ordered levels: low, medium, high investigation priority for each supplied section. | Rank inspection order only. |

The scout must not receive questions about whether evidence is safe to remove,
whether context is irrelevant/deletable, whether a policy should change, or
which coding model Codex should use. Outputs are typed model observations with
their returned distributions/confidence, not evidence. The deterministic
verifier must re-resolve every suggested route/document/section against the
current router, tracked path, hash and section grammar before it may be shown as
a candidate. Failed resolution is reported as `UNVERIFIED_ADVISORY`, never
silently followed.

```text
EVIDENCE_LOSS=0
AUTHORITY_CHANGE=0
UNKNOWN=>CONSERVATIVE
LOW_RANK!=IRRELEVANT
INDEX_ROUTER_SCOUT_NOT_EVIDENCE=TRUE
RECOVERABLE_NOT_SAFE_TO_HIDE=TRUE
ACTIVE_DELIVERY_AUTHORIZED=NO
```

No S0 output changes prompt bytes, reads, persistence, security policy, Codex
model selection, normal FioFilter behavior or Mission Context shadow results.
Default result retention is no persistence. If a future experiment needs a
record, it must be payload-free and keep model observations distinct from the
deterministic verifier and final task outcome.

## Pre-registered shadow experiment

The experiment uses frozen, non-sensitive tasks with a human/deterministic
oracle of the required canonical evidence. It does not deliver Jev-ranked
content to an agent in S0.

| Arm | Procedure |
| --- | --- |
| CONTROL | PD1/PD2 deterministic router and its normal canonical-evidence procedure. |
| TREATMENT | The same PD1/PD2 output, plus `FIOFILTER_JEV_SCOUT_V0`, plus deterministic verification. The advisory is recorded only; actual context delivery remains the CONTROL set. |

Pre-register per task:

```text
CONTROL_FILES_CONSIDERED
TREATMENT_FILES_SUGGESTED
CONTROL_DOCUMENT_BYTES_LOADED
TREATMENT_DOCUMENT_BYTES_IF_FOLLOWED
JEV_INPUT_BYTES
JEV_CALL_COUNT
JEV_LATENCY_MS (only when a reliable clock surrounds a live call)
ROUTE_MATCH
REQUIRED_EVIDENCE_RECALL
FALSE_NEGATIVE_CRITICAL
RECOVERY_REQUIRED
TASK_QUALITY
```

`ROUTE_MATCH` compares the advisory to the deterministic/control oracle; it is
not a truth predicate. `REQUIRED_EVIDENCE_RECALL` is the fraction of predeclared
required items still present in the verified candidate set. A critical false
negative is any required evidence item absent from that set. `RECOVERY_REQUIRED`
is an observed later retrieval of a predeclared required item; it is not guessed
from a probability. `TASK_QUALITY` is an independently specified evaluator.

```text
CRITICAL_GATE=FALSE_NEGATIVE_CRITICAL_EQUALS_0
```

This gate is necessary before any future active-routing discussion, but is not
sufficient authority for activation. A successful suggestion proves only a
possibility in the tested corpus; reliability requires repeated, quality-qualified
results. Any unavailable credential, service error, malformed response,
unverifiable candidate or uncertainty returns the treatment measurement to the
unchanged PD1/PD2 control set.

## S0 result and limits

```text
LIVE_PROBE=BLOCKED_NO_CREDENTIAL
MODEL_IDENTIFIER=UNAVAILABLE
QUESTION_COUNT=UNAVAILABLE
LATENCY_MS=UNAVAILABLE
RESPONSE_SCHEMA_VALID=UNAVAILABLE
PROBABILITIES_PRESENT=UNAVAILABLE
```

No live result was fabricated. This reconnaissance supports a future bounded
shadow scout experiment, not an active integration, accuracy claim, production
claim, token-saving claim or permission to resume READREF.

**Verdict:** `JEV_S0_PASS_BLOCKED_NO_LIVE_ACCESS`.
