# FioOS v0.1 consumer note — pilot evidence

**Historical candidate-era record.** This note describes the pilot before PR
#25 was merged. PR #25 has since been merged into `main`, and post-merge CI
passed. The exact FioOS v0.1 pin remains unchanged. This bounded experiment
report is not a production-security claim or a replacement for the current
consumer implementation and its tests.

FioFilter experimentally uses the public
[`phpedrogarcia-afk/fioos-core`](https://github.com/phpedrogarcia-afk/fioos-core)
v0.1.0 release, pinned at commit
`04ea806b80995ff95b50fb0c8d232baa2148c20a`, for finite local A0 mediation of
development work-item proposals. An agent can propose a catalogued follow-up;
the deterministic controller policy and FioOS Runtime Gateway mediate one
append into an isolated, Git-ignored outbox. Every item remains a proposal for
human review.

The local pilot's plan contains 15 cases: five valid proposals, nine deny
controls, and one same-request replay scenario. In the corrected receipt-based
run, six receipts reported correlated `ALLOW`/`SUCCEEDED`, nine reported
explicit `DENY`/`DENIED` with zero effect, and none were unknown or unexpected.
The six successful receipts corresponded to five unique request/result pairs
and five work-item records. The receipt schema does not distinguish a replay
receipt from an ordinary successful receipt, so no separate observed replay
count is claimed. No duplicate artifact or authority bypass was observed. The
work items point to documented FioFilter uncertainties rather than copying
free-form proposal text.

This is not a production-security claim, autonomous coding, continuous
operation, durable replay, shell/cloud execution, or permission to edit
FioFilter `main`. FioOS v0.1's published local, finite, single-process limits
remain in force. At the time this pilot note was written, the integration
candidate was local and unmerged. PR #25 later merged the consumer into `main`,
and post-merge CI passed. Human review remains required for proposals.

Outbox containment rejects static redirection, but the path-based check/write
sequence is not race-resistant against another local process that can replace
the validated run directory or `notes.jsonl` target before the append. V0.1
assumes the repository and outbox filesystem remain under a trusted local
controller/process; same-host concurrent filesystem tampering is outside this
candidate's trust envelope. No multi-user or TOCTOU-hardening claim is made.

## Local checkout and test

Clone with the pinned FioOS source initialized, or initialize it after cloning:

```sh
git clone --recurse-submodules https://github.com/phpedrogarcia-afk/FioFilter.git
cd FioFilter
# If the repository was cloned without --recurse-submodules:
git submodule update --init --recursive
python -m pip install -e ".[dev]"
python -m pytest integration_tests/test_fioos_consumer.py -q
```
