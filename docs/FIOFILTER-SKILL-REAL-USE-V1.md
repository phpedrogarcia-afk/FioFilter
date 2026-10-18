# FioFilter Task Context Skill — first real-use evidence

Mission: FIOFILTER-SKILL-REAL-USE-V1

## Prototype recovered

The disposable prototype is the FioFilter checkout nested in the
FIO-ECOSYSTEM-EMPLOYEE-V0-20261017 FioOS build, branch
codex/fio-ecosystem-employee-v0, HEAD
79c1f39c8fede944448d4bc5c88711a978b111d4. Its tracked source was unchanged;
.agents/ and .experiment/ were untracked. The prototype Skill and its
evidence were read in place and left unchanged.

execution-results.json records 53 focused tests passing, 0 failures, and 0
errors for the discovery runtime and discovery-shadow tests at that source
state. The first attempt had 11 temporary-directory setup errors; the repeated
run used a workspace-local pytest base directory and passed all 53. The same
record says local Codex CLI was blocked before model start by access denial
while opening the local Codex state store; its machine path is intentionally
omitted here. This remains
NATIVE_INVOCATION=NOT_PROVEN. The handoff-claims file is preserved in the
prototype; no capture/verify/render output was found alongside these artifacts,
so a Handoff round trip is not claimed by this mission.

## Change boundary

The FioFilter worktree was created from local origin/main at
05371cced56259e9e26276e4e1594c4e1d04a6c0, then isolated on branch
codex/fiofilter-skill-real-use-v1. The worktree was clean before edits.
Changes add the native repository-local Skill, an explicit-only Codex policy,
a small static contract test, this evidence record, and an append-only decision.
No runtime module, FioOS source, global Codex setting, main ref, or remote ref
was changed.

## Real FioFilter task and discovery observation

Task: make an explicitly invoked Codex Skill produce a useful, recoverable
context map using FioFilter's existing navigation-only discovery, without
changing the actual task or hiding sources.

Before adding the Skill or test, the existing CLI was run once against the clean
mission worktree with a short query. It returned:

- query: explicit Codex task-context Skill with recoverable source map via
  discovery-shadow and section retrieval
- HEAD 05371cced56259e9e26276e4e1594c4e1d04a6c0
- snapshot 7004f486bc341c99
- query hash 084ab0c5b44b97f1
- evaluation hash 3634a93827734b84
- worktree-state digest 1c64085128a0b04c
- query type COLD_EVALUATION; 94 Python files indexed; map 948 bytes
- index_authority=NAVIGATION_ONLY

The 948-byte discovery map is an engine-reported byte count; 237 bytes-divided-
by-four is an estimate only. Neither is a Codex token count or savings result.

| Rank | Candidate | Score | Matched tokens | Context decision |
| --- | --- | --- | --- | --- |
| 1 | fiofilter/codex_web_shadow.py | 9.154281 | codex, discovery, shadow | Excluded after source inspection: M13 post-delivery telemetry, not the task-context CLI contract. |
| 2 | tests/test_codex_web_shadow.py | 9.021342 | codex, task, discovery, shadow | Excluded: tests the separate Codex Web adapter. |
| 3 | fiofilter/structural.py | 8.813409 | context, source, map, discovery | Excluded from the minimum set: structural-discovery abstractions; the M11 runtime uses a different structural_python backend. |
| 4 | tests/test_canary.py | 7.650194 | explicit, task, source | Excluded: M15 canary contract; no canary is involved here. |
| 5 | tests/test_discovery_shadow.py | 6.955812 | explicit, discovery, shadow | Supporting candidate: existing discovery tests, but not the M11 runtime's full contract suite. |
| 6 | scripts/fioos_first_consumer_pilot.py | 6.603834 | source, map | Excluded: FioOS consumer pilot, outside this independent task. |
| 7 | fiofilter/cli.py | 6.558664 | context, discovery, shadow | Selected: exposes the explicit discovery-shadow command and JSON result path. |
| 8 | scripts/run_discovery_structural_shadow.py | 6.476276 | source, discovery, shadow | Excluded: older structural-shadow replay/benchmark script, not the CLI path used. |

The task router and direct import/source inspection add these necessary sources,
which the Python-only index is not meant to find:

- AGENTS.md and AI-START-HERE.md: invariant and route requirements.
- docs/M11-DISCOVERY-RUNTIME-SHADOW.md and decision M11-D001:
  navigation-only authority, no evidence satisfaction, no suppression or
  automatic context selection, and failure isolation.
- fiofilter/discovery_runtime_shadow.py and
  fiofilter/structural_python.py: result identity, matched tokens, indexed
  universe, and snapshot implementation.
- scripts/section_working_set.py and decision M16-PD2-D001: exact-heading
  retrieval, with full-document fallback when selection is ambiguous or unsafe.
- tests/test_discovery_runtime_shadow.py: explicit authority, provenance,
  determinism, failure, and map contracts.

Observed limitation: the index only covers Python paths and symbol names.
Markdown, the Skill, route documents, configuration and many testable facts are
outside its scope. The eight ranked candidates included several plausible but
irrelevant FioOS/Codex-Web leads. Ranking alone would not have produced a
reliable working set.

## Context map produced

| Source | Why it belongs | Evidence to inspect | Recovery reference |
| --- | --- | --- | --- |
| .agents/skills/fiofilter-task-context/SKILL.md | Implements the requested user-facing procedure and output contract. | Explicit invocation, verified candidates, uncertainties, and recovery fields. | Exact branch commit and path after local commit. |
| .agents/skills/fiofilter-task-context/agents/openai.yaml | Makes invocation explicit-only in Codex metadata. | allow_implicit_invocation: false. | Exact branch commit and path after local commit. |
| fiofilter/cli.py | Existing CLI dispatch and JSON serialization. | cmd_discovery_shadow and discovery-shadow argument setup. | git -C <root> show 05371cced56259e9e26276e4e1594c4e1d04a6c0:fiofilter/cli.py |
| fiofilter/discovery_runtime_shadow.py | Produces provenance-bound, ranked navigation candidates. | Candidate matched tokens, evaluation identity, Python-only universe, optional ledger. | git -C <root> show 05371cced56259e9e26276e4e1594c4e1d04a6c0:fiofilter/discovery_runtime_shadow.py |
| scripts/section_working_set.py | Recovers canonical document sections without making a summary authoritative. | Exact headings and full-document fallback. | git -C <root> show 05371cced56259e9e26276e4e1594c4e1d04a6c0:scripts/section_working_set.py |
| tests/test_discovery_runtime_shadow.py | Existing executable checks for advisory authority and stable provenance. | Authority, no automatic selection, deterministic IDs, and map output. | Exact HEAD and repository-relative path. |

The real task was oriented through the existing discovery-shadow mechanism
following the recovered prototype's workflow. The context-map evidence above
was assembled from that pre-change result and direct source reads. Because the
native $fiofilter-task-context selector was not available in this executor
session, this demonstrates usefulness of the underlying mechanism and manual
workflow, not successful native Codex invocation. No other canary or repository
experiment was run.

## Validation on the mission branch

- Focused tests: 56 passed, 0 failed. This includes the existing discovery
  runtime/discovery suites and three new static Skill-contract checks.
- The first new-test run had 55 passes and one failure because one assertion
  compared a sentence across Markdown line wrapping. Whitespace normalization
  corrected the test oracle; the final repeat passed all 56. This was not a
  runtime or Skill-loader failure.
- The installed Skill validator reported valid frontmatter; the Codex policy
  parsed as explicit-only; git diff --check was clean.
- These checks validate files and preserved invariants, not native invocation.

## Measurement and second-repository preparation

- Baseline task run with comparable native Codex invocation: unavailable.
- Treatment native Codex token usage, prompt cache, additional model calls, and
  task-success comparison: unavailable.
- Discovery map size: 948 visible bytes; not actual model-token usage or
  savings. No causal savings claim is made.
- Second-repository experiment: prepared, not run, against
  ProjetoFioHandoff, observed on branch main at
  0b9f880294d5964e8182a11b232b128b24995880. Revalidate this baseline when the
  experiment is started. Place this Skill under that repository's
  .agents/skills/fiofilter-task-context/, explicitly invoke
  $fiofilter-task-context for one naturally active engineering task, and
  verify that the map points only to that repository, shows at least one
  recovery reference, labels uncertainty, and leaves all sources/task delivery
  unchanged. Do not install globally or write to the second repository as part
  of this mission. FioFilter CLI availability there is an explicit portability
  precondition; if unavailable, the documented fallback should still complete
  ordinary source discovery.

## Limits

The static contract test checks required manifest and instruction markers; it
does not prove Codex's runtime loader or explicit invocation. Generality beyond
the FioFilter CLI-compatible environment, repeatability, task-quality
improvement, actual token reduction, cache effects, and FioOS/Handoff
round-trip verification remain unproven.

## Local Git identity scar

The unpublished documentation-only commit 7769c24de6b7bc5f79bc5bafee76b3b097fdfe40
contains a mistyped GitHub no-reply email alias. The preceding feature commit
uses the configured no-reply identity. No push occurred, and history was not
rewritten; verify commit identity before any future publication.

## Publication-candidate follow-up (2026-10-17)

The sections above record the earlier mission at that time. The local,
unpublished branch was subsequently repaired for publication review:

- The intermediate commit `7769c24de6b7bc5f79bc5bafee76b3b097fdfe40` became
  `553b28bdaa6bdefec56aa9a52c864c8fd5889643` after correcting only its
  author and committer email to the configured GitHub NOREPLY identity.
- Its descendant tip `aa9d7e99a9baebc1caf7c0042287a26d47238b6a` became
  `b7aa193fd1df19fb778518c86296393ebb94da2b` after changing only its
  parent reference. Both tips have the same tree,
  `ab57d7e70899dbef9658c2e75243066eafe22850`. The old tip remains
  locally recoverable at
  `refs/backup/fiofilter-skill-real-use-v1-before-noreply-fix`.
- The Skill instruction now forbids a *separate persisted* index, while allowing
  the existing `discovery-shadow` in-memory navigation index it explicitly
  invokes. No FioFilter runtime or FioOS consumer code changed.
- The installed Skill validator passed; 56 focused tests passed. The full suite
  passed 668/668 when run outside the managed sandbox with a workspace-local
  temporary directory. Within the sandbox, 33 tests failed because Windows
  denied the `os.link` operation used by the RAW store; one representative test
  passed unchanged outside it. This is an execution-environment distinction,
  not evidence of a product fix.
- Subsequent user-provided evidence reports native explicit invocation in
  FioFilter and navigation in FioHandoff. This follow-up did not rerun the
  native loader. Native invocation in FioHandoff, broader portability, task
  improvement, and causal token savings remain NOT_PROVEN.

This is an explicit-use experimental publication candidate, not authorization
for automatic context selection, evidence suppression, or general activation.
