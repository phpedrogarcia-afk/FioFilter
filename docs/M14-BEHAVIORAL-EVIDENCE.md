# M14 — independent behavioral evidence (E1 + E2)

## Provenance and scope

This document canonicalizes the local E1 and E2 experiment results for the
isolated `ReadReceiptABHarness` at M14 commit
`e40b038a7806d1787202b1a47a118193a60dc702` (tree
`7d02429abdbcc0e9b8efc69048fc8ec6b2488619`). The experiment host used
fresh Codex contexts, disposable repositories, and ephemeral harness sessions;
it did not activate READREF in normal FioFilter or Codex operation. These are
observed results in a small controlled corpus, not a reliability estimate.

Sanitized source artifacts are outside Git in the sibling
`FioFilter-M14-Experiments` directory. Their SHA-256 values identify the exact
evidence summarized here:

| Source artifact | SHA-256 |
| --- | --- |
| `E1/results/M14-E1-summary.json` | `ec1ee3fb77683a3e06d1bda4849c609acd0ab0e8f3de34885aa2e2ae5d8c1628` |
| `E1/results/M14-E1-report.md` | `7d4e33c73bf538532c2efd44fad025131e35e877857793aab9276c87e8b8f8f7` |
| `E2/manifest.json` | `60979ac6bb71e7595452bd7488dd66c7a75a13430ff97ceb1788eecfc0576a42` |
| `E2/results/M14-E2-summary.json` | `0e6ca87fec2517a71048d56dbb237a0392890499e801f6360d7c5ac70a20a17c` |
| `E2/results/M14-E2-report.md` | `88c6668a20d61419fb8cdefc8805ddf86f77dfffd6ba0f0d825b04db6af7a1ba` |

The original verdicts were `M14_E1_PASS_NEAR_ONLY_SIGNAL` and
`M14_E2_PASS_QUALITY_BUT_ECONOMICS_MIXED`; the synthesis below does not erase
either experiment's limitations.

## Qualified behavioral pairs

All four pairs below had passing CONTROL and TREATMENT objective evaluators.
Treatment emitted READREF on the designated repeat in each pair. Net visible
bytes subtract reference, recovery, and additional treatment context from the
matched CONTROL repeat; they are not model tokens.

| Experiment / task | CONTROL | TREATMENT | Recovery requests / bytes | Corrective rereads | Net visible bytes | Tool-call delta |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| E1 `FACT_RECALL_AFTER_REREAD_NEAR` | PASS | PASS | 0 / 0 | 0 | +5,819 | 0 |
| E1 `LONGER_DISTANCE_REREAD` | PASS | PASS | 0 / 0 | 0 | +5,815 | 0 |
| E2 `SINGLE_FILE_CODE_CHANGE_V2` | PASS | PASS | 1 / 588 | 0 | -140 | +1 |
| E2 `DEBUGGING_OR_FAILURE_INVESTIGATION` | PASS | PASS | 0 / 0 | 0 | +424 | -1 |

E2 qualified both fixtures *before* behavioral execution: the initial
evaluator failed, an oracle patch passed, restoring the initial fixture failed
again, neither task prompt exposed the oracle implementation, and changed-file
allowlists were explicit (`src/score.py` or `src/retry.py` only). The E2 manifest
froze fixtures, evaluators, prompts, order, and hashes before the first run.
The four E2 runs followed CONTROL→TREATMENT for the single-file task and
TREATMENT→CONTROL for debugging. E2 recorded no protocol errors or safety
failure; the canonical repository remained unchanged during the experiment.

The original E1 `SINGLE_FILE_CODE_CHANGE` pair was CONTROL FAIL / TREATMENT
FAIL. Its -140-byte net result included one 187-byte recovery, but it is a
`TASK_BASELINE_FAILURE`, **not** a valid behavioral comparison and is excluded
from the aggregate and recovery count below. E1 also preserved two excluded
protocol-invalid host attempts caused by request-ID collisions before the
repeat; the subsequent valid runs showed no safety failure. Neither the
baseline failure nor the host scar is silently promoted to a treatment result.

## Descriptive synthesis and decision boundary

```text
VALID_BEHAVIORAL_PAIRS=4
CONTROL_QUALITY_PASS=4
TREATMENT_QUALITY_PASS=4
OBSERVED_TREATMENT_QUALITY_REGRESSIONS=0
NET_POSITIVE_PAIRS=3
NET_NEGATIVE_PAIRS=1
RECOVERY_EVENTS=1
DESCRIPTIVE_TOTAL_NET_VISIBLE_BYTES_SAVED=11918
ACTUAL_TOKEN_SAVINGS=UNAVAILABLE
```

The +11,918 bytes are the arithmetic sum across four different paired tasks,
not measured token savings, a production expectation, or proof of universal
behavioral equivalence. App-server per-thread token-usage updates were observed,
but no causal actual-token saving can be attributed to READREF. The E2
single-file pair demonstrates that recovery can make an individual substitution
net-negative despite preserved task quality. No safety failure was observed in
the valid pairs; this does not prove safety outside the tested envelope.

**Decision:** `M14_AB_PASS_READ_RECEIPT_CANARY_READY`. Independent factual,
coding, and debugging pairs support a *controlled* canary, with recovery fully
charged and a mixed economics scar retained. This decision supersedes only the
pre-evidence advancement state in `M14-D001` and the M14 experiment document;
it does not weaken any READREF gate or activate normal-runtime delivery.

```text
PRODUCTION_READY=NO
GLOBAL_ACTIVATION_AUTHORIZED=NO
CANARY_AUTHORIZED=YES
CANARY_SCOPE=CONTROLLED_ONLY
```
