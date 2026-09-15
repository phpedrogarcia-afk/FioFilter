# FIOFILTER-M02-FOUNDATION-AUDIT-HARDENING

## Verified baseline

Repository: `phpedrogarcia-afk/FioFilter`, public, default branch `main`.
Base HEAD and origin/main: `ddc087077dfe877cd6a3acc4f12839d4ff510a96`.
One root M01 commit; 42 tracked files; clean baseline. BASELINE_DRIFT=NO.

The execution workspace initially had no checkout. Direct Git transport was
unavailable. The GitHub plugin supplied files fixed to the base SHA. Each blob's
Git SHA-1, the tree (`32d447c35ab255e839c476fb0e56fd25370c4697`) and original commit
object were reproduced exactly locally; this was retrieval of the existing
history, not a replacement/rewrite commit. Local main/origin-main refs were set
to that verified remote commit before creating `codex/m02-foundation-audit`.

Before project modifications: `python -m pytest tests/ -v` passed **137 tests**
(Python 3.12, Linux). The runtime lacked pytest and the package index was
unavailable. Unmodified official pytest 8.3.5, pluggy 1.5.0 and iniconfig 2.0.0
source packages were retrieved through GitHub into external scratch dependency
paths; their build-generated version modules were populated with release versions.
PYTHONPATH selected those packages and unrelated pytest plugin auto-loading was
disabled. No test shim, alternate runner or original test modification was used.
These bootstrap dependencies were not added to the repository.

Five targeted regressions were then written and run against M01: **five failed**
(full-content precedence; repetition is not disposability; machine-data profile
bypass; NOISE/PROVE reduction; classifier-exception RAW fallback).

## Material findings and fixes

| Severity | Baseline evidence | Impact | Action / decision |
|---|---|---|---|
| CRITICAL | Generated bearer-shaped content returned SECURITY/RAW and a disk blob; all engine paths wrote RAW | Automatic credential archive, also command/fact sidecars | Orthogonal sensitivity/storage, ephemeral default, no sensitive archive/log; M02-D001 |
| HIGH | NOISE + ERROR beyond 16 KiB transformed (20724 → 73 bytes in the probe) | Protected material misclassified; assurance depended on incidental marker behavior | Full scan, complete known-noise grammar, mixed diagnostics; M02-D003 |
| HIGH | PASS + warning became SUCCESS_SUMMARY/TRANSFORM (500 → 88 bytes) | Diagnostics did not establish protected precedence | Explicit DIAGNOSTIC classification and RAW scope; M02-D003 |
| HIGH | Repeated payment sentences became NOISE/TRANSFORM (620 → 56 bytes) | Repetition incorrectly treated as disposability | No repetition-ratio eligibility; unknown remains RAW; M02-D003 |
| HIGH | Permissive profile applied T01 to valid JSON/MACHINE_DATA | I8 bypass and broken machine representation | Core/profile intersection, selected-ID guard and explicit T01 class scope; M02-D002/D003 |
| HIGH | Classifier/profile/store/logger failures outside transform try block | Claimed fail-to-RAW pipeline could raise instead | Unified operational fallback and in-memory reasons; M02-D003/D005 |
| HIGH | Fixed temporary filename; rename overwrite semantics; unchecked dedup | Concurrent publication/corruption guarantees not established | No-clobber unique temp publication; verify dedup/read; M02-D004 |
| MEDIUM | Metadata mixed SHA content identity with first command/session; direct writes/index were nontransactional | Misattribution, sensitive context duplication and inconsistent crash state | Content-only schema-2 metadata; no index; explicit partial-state behavior; M02-D004 |
| MEDIUM | Literal marker collision, count documentation mismatch, store-only round trips | Visible interpretation not proven reversible | Versioned T01 + decoder/count/boundary/collision oracles; M02-D006 |
| MEDIUM | YAML policy files unused and unvalidated | Silent configuration drift | Remove YAML, Python canonical with policy subset tests; M02-D002 |
| MEDIUM | Default and FioOS NOISE/PROVE returned RAW despite prose | Accidental pass-through conservatism hidden by weak test | Known noise reduces across profiles in PROVE; M02-D007 |
| MEDIUM | Build backend `setuptools.backends.legacy:build` does not exist | README editable-install path unusable | Correct backend, canonical Windows/Linux install/tests; M02-D008 |
| LOW | Bytes/4 labeled chars/4, timing covered other steps, missing real observations | Local economics overstated or ambiguous | Named ESTIMATE method, apply-only timing, optional external observations; M02-D005 |

The probes show unsafe authorization to transform protected/misclassified material.
They do not imply that every shorter example deleted its unique ERROR line: M01
T01 happened to retain distinct lines, but classifier and consumer guarantees were
false, and arbitrary profiles could break machine data. M02 protects both the
eligibility boundary and exact T01 visible reconstruction.

## Guarantee classifications

PROVEN below means a structural property of the implemented valid-input API under
its stated assumptions, not universal real-world evidence recognition. Corpus
results supplement but do not replace those assumptions.

| Guarantee | M01 assessment | Hardened assessment / scope |
|---|---|---|
| Twelve evidence classes and deterministic no-LLM path | PROVEN | PROVEN; taxonomy not expanded for sensitivity |
| I1 no overwrite by store API | PARTIALLY_PROVEN | PROVEN with supported hard-link filesystem/private root; not hostile-OS immutability |
| I2 transform linkage | PARTIALLY_PROVEN | PROVEN for returned TRANSFORM; reference prepared first; RAW may lack ref |
| I3 SHA byte recovery | PARTIALLY_PROVEN (verify=False bypass; unchecked dedup) | PROVEN on successful checked reads; availability conditional, corruption tests pass |
| I4 universal critical-fact extraction | CLAIMED_ONLY | PARTIALLY_PROVEN: declared facts/occurrences and approved T01 grammar; arbitrary semantic extraction unproven |
| I5 actual unknown/low-confidence goes RAW | PROVEN for assigned UNKNOWN | PROVEN structural guard; complete semantic recognition still not universal |
| I6 failures/nonzero preserved | PARTIALLY_PROVEN | PROVEN for nonzero guard; mixed explicit-failure corpus VERIFIED; arbitrary language detection PARTIALLY_PROVEN |
| I7 protected assigned classes RAW | PROVEN for built-in profiles | PROVEN for protected class guards; sensitivity/persistence separately explicit and tested |
| Secret-free automatic persistent storage | FALSE | PROVEN: default engine writes no persistent data; arbitrary explicit-write non-sensitivity remains caller assessment |
| I8 machine safety against permissive profile | FALSE | PROVEN no V0 machine transform; no JSON-equivalence claim |
| I9 strict local non-expansion | PROVEN for existing bytes path | PROVEN returned TRANSFORM requires shorter bytes including header/marker |
| I10 whole-mission optimization | CLAIMED_ONLY | UNKNOWN; supplied observations supported, prediction/A/B deferred |
| I11 determinism/no model | PROVEN | PROVEN for content pipeline, excluding observation clocks |
| I12 complete profile non-weakening | FALSE | PROVEN via core intersection + class contract; adversarial tests |
| I13 batch/stream identity | CLAIMED_ONLY beyond one content buffer | PARTIALLY_PROVEN per-result metadata; no capture/batching/interleaving reconstruction |
| I14/I15 metric separation and mission truth | PARTIALLY_PROVEN | PROVEN field/unit separation; actual mission benefit UNKNOWN |
| I16 sufficient audit of every decision | FALSE (incomplete fields, I/O exceptions) | PROVEN returned in-memory audit for valid bytes; crash-time audit delivery UNKNOWN |
| T01 visible-only reversibility | CLAIMED_ONLY | PARTIALLY_PROVEN by explicit encoder/decoder and seeded corpus plus runtime equality guard |
| Default import/construction lazy | PROVEN | PROVEN; default processing also avoids disk |
| Windows runtime correctness | UNKNOWN from M01 host-path tests alone | CI is the evidence source; do not infer successful Windows execution merely from workflow existence |
| Atomic two-file transaction/power-loss durability | CLAIMED_ONLY | Explicitly NOT claimed; blob/metadata publication separate, interruption behavior tested |
| Persistent global mode escalation | Not implemented | PROVEN absent; modes remain stateless |
| Original FioOS corpus replay / whole-mission saving | CLAIMED_ONLY where described as implemented | UNKNOWN; source corpus/loader/A-B not present |

## Validation record and boundaries

The final local canonical-suite result for this audit snapshot is recorded in the
PR and Git handoff. It includes the original suite with explicit revised-contract
assertions, seeded T01 round trips, randomized failure positions, protected
class/mode/profile combinations, no default disk writes, sensitive content/metadata,
corrupt/missing RAW components, concurrent same-object publication and interruption.
The executable test command, not a hard-coded README count, is authoritative.

No new broad compressor, JSON minifier, hooks, global agent settings, remote
service, retention engine or donor campaign was added. Fixtures contain inert
synthetic data, no actual credential values. Existing M01 secret-like examples
were fake test strings, not acquired credentials.

Remaining limitations: original FioOS corpus absent; no actual model-token/mission
experiment; secret/PII detector incomplete by nature; existing M01 local archives
are outside this checkout and were not inspected/removed; hard-link support varies;
no power-loss/hostile-filesystem guarantee; no recovery of upstream truncation or
merged stream ordering. These bound the claims rather than being hidden by a test
count. See SAFE-AGGRESSIVE-FRONTIER for authorized-scope future candidates.

## Handoff

All intended changes belong to `codex/m02-foundation-audit`, based on the exact M01
SHA above. Git commit/tree identity and the PR provide final revision provenance;
this document does not embed its own future commit SHA. Do not merge into main
without independent approval. Do not begin M03.
