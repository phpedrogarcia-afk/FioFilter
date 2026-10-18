---
name: fiofilter-task-context
description: Explicitly create a conservative, recoverable context map for an engineering task in a Git repository, using FioFilter discovery-shadow when available. This skill never changes task delivery or hides source context.
---

# FioFilter task context

Use only when the user explicitly invokes $fiofilter-task-context or directly
asks for this capability. The input is one concrete engineering task and a
target repository supplied by the user or current workspace. This skill creates
an inline navigation package; it does not perform the engineering task.

## Boundaries

- Follow the target repository's AGENTS.md and task router. They outrank this
  skill. Do not load unrelated repositories or the full history by default.
- Discovery results are leads, not evidence, authority, or a complete file set.
  INDEX_AUTHORITY=NAVIGATION_ONLY; DISCOVERY_READ_SUPPRESSION=NO;
  AUTO_CONTEXT_SELECTION=NO.
- Never rewrite, suppress, replace, or silently shorten the user's task, source
  files, or required context. RECOVERABLE is not SAFE_TO_HIDE. Unknown or
  ambiguous evidence stays visible and is called out.
- Do not edit files, persist a context package or a separate index, or enable a
  hook. The package is the report in the current response. Do not claim token,
  time, quality, or correctness savings without a comparable measured run.
- Do not send sensitive task text to discovery. Use a short, non-sensitive
  query, or skip discovery and report why.

## Procedure

1. Resolve the target Git root, current HEAD, branch, and worktree status.
   Treat status as metadata, not content identity. Record whether references
   point to committed HEAD content or local modifications.
2. Read the repository's agent instructions and route. For FioFilter, start
   with AGENTS.md and AI-START-HERE.md, then load the complete or bounded
   canonical evidence required by the selected route. Required governance and
   test sources stay in scope even when discovery does not rank them.
3. If the FioFilter CLI is importable, run one explicit navigation query:

       python -B -m fiofilter.cli --json discovery-shadow "<short query>" "<repository-root>" --top-k 8

   Run it from the FioFilter project environment. Report the command outcome,
   HEAD, snapshot ID, query hash, evaluation hash, indexed-file policy,
   authority, and each candidate's rank, score, and matched tokens. The current
   discovery universe is Python sources (PATH and SYMBOL_NAMES); Markdown,
   configuration, and other files may be absent. If the CLI is unavailable,
   errors, or returns no useful candidates, continue ordinary repository
   discovery and mark that limitation. Do not substitute prepare-context,
   read-shadow, or another lane.
4. Verify candidate paths against the repository and inspect enough source to
   decide their role. For each candidate included in the map, state why it is
   relevant using observed path, symbol, matched-token, or source evidence.
   Also record strong-looking false leads and why they were excluded. Do not
   infer semantic relevance from score alone.
5. Retrieve only the task-relevant canonical sections when the repository
   provides a deterministic section helper. In FioFilter, use
   scripts/section_working_set.py with exact declared headings. If a required
   heading is missing or duplicated, UTF-8 or fence parsing is uncertain, or
   evidence crosses the selected sections, use the helper's complete-document
   fallback or read the full required document. Do not invent line ranges as
   substitutes for canonical headings.
6. Produce the context map below. Keep unresolved questions explicit; the map
   is a reading aid, never permission to skip any source required by the task.
7. Add recovery references. For clean, committed sources identify repository,
   exact HEAD SHA, relative path, and a source anchor (heading or symbol); give
   the command git -C <root> show <sha>:<path>. For locally modified sources,
   identify the worktree path and say that HEAD does not contain those bytes.
   Include a SHA-256 when available. Verify at least one selected reference by
   reading it back through its declared path. If exact recovery is not proven,
   say NOT_VERIFIED rather than implying that a path alone guarantees it.

## Context-map output

Return these fields in the current response:

- TASK and TARGET_REPOSITORY
- REPOSITORY_STATE: root, branch, HEAD, and clean/dirty/unknown status
- DISCOVERY: outcome and evaluation identity, or the reason it was skipped
- VERIFIED_CONTEXT: selected paths, why each is relevant, required source
  anchors, and the evidence scope actually inspected
- CANDIDATES_NOT_SELECTED: relevant-looking leads excluded or unresolved, with
  a short evidence-based reason
- UNCERTAINTIES: missing sources, incomplete index coverage, stale/dirty state,
  unresolved relevance, or fallback
- RECOVERY: exact committed references and commands, plus local-worktree
  references where applicable; label any unverified item
- LIMITS: state explicitly that ranking is not evidence and no delivery,
  visibility, prompt, or source content was altered

Byte counts and the engine's bytes-divided-by-four estimate are not actual
model-token usage, cache usage, billing, or mission savings.
