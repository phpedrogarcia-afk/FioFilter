"""
scripts/extract_codex_corpus.py — Laboratory extraction utility for Codex sessions.

Extracts real tool results from Codex session JSONL logs, applies deterministic
stratified sampling and sensitivity screening, and outputs CorpusEntry JSONL
records to a user-specified path outside the repository.

Usage:
  python scripts/extract_codex_corpus.py \\
      --session "C:\\Users\\phped\\.codex\\sessions\\2026\\08\\23\\rollout-2026-08-23T14-06-11-01a02f96-42a2-7a80-b8bc-6d066d0e322f.jsonl" \\
      --output "C:\\Users\\phped\\.fiofilter\\corpus\\m03_fioos_sample_v1.jsonl" \\
      --sample-size 50 \\
      --project-tag "FIOOS"
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from fiofilter.corpus import CorpusEntry, CorpusOracleLabels, CorpusSourceData
from fiofilter.sensitivity import contains_sensitive_material


STRATA_TARGETS_50 = {
    "git": 8,
    "search": 8,
    "file_read": 8,
    "dir_list": 6,
    "test_success": 6,
    "test_failure": 6,
    "progress_build": 4,
    "script_or_unknown": 4,
}


def classify_call_stratum(inp: str, out: str) -> str:
    """Classify tool call into a stratum based on command and output patterns."""
    c_lower = inp.lower()
    o_lower = out.lower()

    if any(k in c_lower for k in ("pytest", "python -m unittest", "cargo test", "npm test")):
        if any(f in o_lower for f in ("failed", "failure", "error:", "traceback")):
            return "test_failure"
        return "test_success"

    if "git " in c_lower or "git.exe" in c_lower:
        return "git"

    if "rg " in c_lower or "grep " in c_lower:
        return "search"

    if any(k in c_lower for k in ("rg --files", "dir ", "get-childitem", "ls ", "find ")):
        return "dir_list"

    if any(k in c_lower for k in ("get-content", "cat ", "read_file", "type ")):
        return "file_read"

    if any(k in o_lower for k in ("building", "downloading", "fetching", "progress", "installing")):
        return "progress_build"

    return "script_or_unknown"


def extract_command_and_exit_code(inp: str, out: str) -> Tuple[Optional[str], Optional[int]]:
    """Extract command string and exit code from Codex tool call input and output."""
    cmd = None
    exit_code = None

    # Try extracting cmd from tools.exec_command({ cmd: "...", ... })
    m_cmd = re.search(r'cmd:\s*["\']([^"\']+)["\']', inp)
    if m_cmd:
        cmd = m_cmd.group(1)
    else:
        # Fallback to first line of input if short
        lines = inp.strip().splitlines()
        if lines:
            cmd = lines[0][:120]

    # Try extracting exit code from json output
    m_code = re.search(r'["\']exit_code["\']\s*:\s*(\d+)', out)
    if m_code:
        try:
            exit_code = int(m_code.group(1))
        except ValueError:
            pass
    elif "Traceback (most recent call last)" in out or "Error:" in out or "FAILED" in out:
        exit_code = 1
    elif "Script completed" in out:
        exit_code = 0

    return cmd, exit_code


def assign_initial_oracle(stratum: str, cmd: Optional[str], out: str, exit_code: Optional[int]) -> CorpusOracleLabels:
    """Assign independent ground-truth oracle labels based on domain inspection."""
    cmd_str = (cmd or "").lower()
    out_str = out.lower()

    if exit_code is not None and exit_code != 0:
        return CorpusOracleLabels(
            evidence_class="FAILURE",
            sensitivity="NOT_SENSITIVE",
            transform_eligibility="RAW_REQUIRED",
            inline_required_facts=[],
            oracle_rationale="Non-zero exit code or error output requires RAW preservation.",
        )

    if stratum == "git":
        # Extract facts like commit hash, branch name
        facts = []
        m_branch = re.search(r"On branch\s+(\S+)", out)
        if m_branch:
            facts.append(m_branch.group(0))
        m_commit = re.search(r"\b([0-9a-f]{7,40})\b", out)
        if m_commit:
            facts.append(m_commit.group(1))

        return CorpusOracleLabels(
            evidence_class="CANONICAL_STATE",
            sensitivity="NOT_SENSITIVE",
            transform_eligibility="RAW_REQUIRED",
            inline_required_facts=facts,
            oracle_rationale="Git canonical repository state must be preserved exactly.",
        )

    if stratum == "test_success":
        facts = []
        m_pass = re.search(r"\b\d+\s+passed\b", out, re.IGNORECASE)
        if m_pass:
            facts.append(m_pass.group(0))

        return CorpusOracleLabels(
            evidence_class="SUCCESS_SUMMARY",
            sensitivity="NOT_SENSITIVE",
            transform_eligibility="SAFE_TO_REDUCE",
            inline_required_facts=facts,
            oracle_rationale="Passing test summary; safe to reduce repetitive pass lines with fact retention.",
            missed_opportunity_category="KNOWN_SUCCESS_RECORDS",
        )

    if stratum == "test_failure":
        return CorpusOracleLabels(
            evidence_class="FAILURE",
            sensitivity="NOT_SENSITIVE",
            transform_eligibility="RAW_REQUIRED",
            inline_required_facts=[],
            oracle_rationale="Test failure output contains essential diagnostic evidence.",
        )

    if stratum == "dir_list":
        return CorpusOracleLabels(
            evidence_class="DISCOVERY",
            sensitivity="NOT_SENSITIVE",
            transform_eligibility="SAFE_TO_REDUCE",
            inline_required_facts=[],
            oracle_rationale="Directory enumeration; safe to reduce repetitive paths or file lists.",
            missed_opportunity_category="DIRECTORY_OR_PATH_REDUNDANCY",
        )

    if stratum == "progress_build":
        return CorpusOracleLabels(
            evidence_class="PROGRESS",
            sensitivity="NOT_SENSITIVE",
            transform_eligibility="SAFE_TO_REDUCE",
            inline_required_facts=[],
            oracle_rationale="Repetitive build progress output; safe to fold.",
            missed_opportunity_category="REPETITIVE_PROGRESS",
        )

    if stratum == "search":
        # Search queries: often contains repeated file headers or match contexts
        return CorpusOracleLabels(
            evidence_class="DISCOVERY",
            sensitivity="NOT_SENSITIVE",
            transform_eligibility="SAFE_TO_REDUCE",
            inline_required_facts=[],
            oracle_rationale="Search results; safe to reduce duplicate path headers.",
            missed_opportunity_category="DUPLICATED_HEADERS",
        )

    if stratum == "file_read":
        # Full file reads of memory or source code require fidelity
        return CorpusOracleLabels(
            evidence_class="CANONICAL_STATE",
            sensitivity="NOT_SENSITIVE",
            transform_eligibility="RAW_REQUIRED",
            inline_required_facts=[],
            oracle_rationale="Source/memory document content must be preserved losslessly.",
        )

    return CorpusOracleLabels(
        evidence_class="UNKNOWN",
        sensitivity="NOT_SENSITIVE",
        transform_eligibility="RAW_REQUIRED",
        inline_required_facts=[],
        oracle_rationale="Generic script or unclassified execution; requires RAW by default.",
    )


def extract_session_corpus(
    session_path: pathlib.Path | str,
    output_path: pathlib.Path | str,
    sample_size: int = 50,
    project_tag: str = "FIOOS",
    filter_sensitive: bool = True,
) -> Dict[str, Any]:
    """
    Stream a session JSONL file, stratify calls, apply sensitivity filtering,
    and write the resulting CorpusEntry JSONL file.
    """
    session_p = pathlib.Path(session_path)
    output_p = pathlib.Path(output_path)
    output_p.parent.mkdir(parents=True, exist_ok=True)

    if not session_p.exists():
        raise FileNotFoundError(f"Session file not found: {session_p}")

    # Pass 1: Stream line-by-line and collect call metadata into strata buckets
    # Store only lightweight metadata in memory, not the large output bytes!
    tool_inputs: Dict[str, str] = {}
    strata_candidates: Dict[str, List[Dict[str, Any]]] = {k: [] for k in STRATA_TARGETS_50}
    total_calls_seen = 0
    total_outputs_seen = 0
    sensitive_rejected = 0

    with open(session_p, "r", encoding="utf-8", errors="replace") as f:
        for line_idx, line in enumerate(f):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            payload = rec.get("payload", {})
            pt = payload.get("type")

            if pt == "custom_tool_call":
                cid = payload.get("call_id")
                if cid:
                    tool_inputs[cid] = payload.get("input", "")
                    total_calls_seen += 1

            elif pt == "custom_tool_call_output":
                cid = payload.get("call_id")
                if not cid:
                    continue

                total_outputs_seen += 1
                inp = tool_inputs.pop(cid, "")
                out_raw = payload.get("output")

                texts = []
                if isinstance(out_raw, list):
                    for item in out_raw:
                        if isinstance(item, dict) and "text" in item:
                            texts.append(item["text"])
                elif isinstance(out_raw, str):
                    texts.append(out_raw)

                full_out = "".join(texts)
                if not full_out.strip():
                    continue

                raw_bytes = full_out.encode("utf-8")

                # Sensitivity screening
                if filter_sensitive and contains_sensitive_material(raw_bytes):
                    sensitive_rejected += 1
                    continue

                stratum = classify_call_stratum(inp, full_out)
                cmd, exit_code = extract_command_and_exit_code(inp, full_out)

                strata_candidates[stratum].append({
                    "call_id": cid,
                    "line_idx": line_idx,
                    "input": inp,
                    "command": cmd,
                    "exit_code": exit_code,
                    "raw_bytes": raw_bytes,
                    "stratum": stratum,
                })

    # Pass 2: Deterministic stratified sampling
    # Allocate targets proportionally based on STRATA_TARGETS_50
    scale = sample_size / 50.0
    targets = {k: max(1, int(round(v * scale))) for k, v in STRATA_TARGETS_50.items()}

    selected: List[Dict[str, Any]] = []
    for stratum, target_count in targets.items():
        candidates = strata_candidates.get(stratum, [])
        if not candidates:
            continue
        if len(candidates) <= target_count:
            selected.extend(candidates)
        else:
            # Deterministic periodic step
            step = len(candidates) / float(target_count)
            for i in range(target_count):
                idx = int(i * step)
                selected.append(candidates[min(idx, len(candidates) - 1)])

    # Sort selected by original occurrence
    selected.sort(key=lambda x: x["line_idx"])

    # Trim to exact sample_size if needed
    if len(selected) > sample_size:
        selected = selected[:sample_size]

    # Convert to CorpusEntry objects and write to output_path
    entries: List[CorpusEntry] = []
    with open(output_p, "w", encoding="utf-8") as out_f:
        for idx, item in enumerate(selected, start=1):
            entry_id = f"{project_tag}-REAL-{idx:03d}"
            raw_b64 = base64.b64encode(item["raw_bytes"]).decode("ascii")

            source_data = CorpusSourceData(
                provenance=f"session:{session_p.name}:call_id:{item['call_id']}",
                command=item["command"],
                exit_code=item["exit_code"],
                stdout_stderr="combined",
                content_type_hint="text",
                raw_content_b64=raw_b64,
                byte_length=len(item["raw_bytes"]),
                truncated=False,
            )

            oracle_labels = assign_initial_oracle(
                stratum=item["stratum"],
                cmd=item["command"],
                out=item["raw_bytes"].decode("utf-8", errors="replace"),
                exit_code=item["exit_code"],
            )

            entry = CorpusEntry(
                entry_id=entry_id,
                source_data=source_data,
                oracle_labels=oracle_labels,
                tags=[project_tag.lower(), item["stratum"], "real_workload"],
            )
            entries.append(entry)
            out_f.write(json.dumps(entry.to_dict(include_raw=True)) + "\n")

    summary = {
        "session_path": str(session_p),
        "output_path": str(output_p),
        "total_calls_seen": total_calls_seen,
        "total_outputs_seen": total_outputs_seen,
        "sensitive_rejected": sensitive_rejected,
        "sample_size": len(entries),
        "strata_distribution": {k: len([e for e in entries if k in e.tags]) for k in STRATA_TARGETS_50},
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract real Codex tool outputs into a CorpusEntry JSONL file.")
    parser.add_argument("--session", required=True, help="Path to Codex rollout JSONL file")
    parser.add_argument("--output", required=True, help="Path to output JSONL file outside repository")
    parser.add_argument("--sample-size", type=int, default=50, help="Target sample size (default: 50)")
    parser.add_argument("--project-tag", default="FIOOS", help="Project tag for entry IDs (default: FIOOS)")
    parser.add_argument("--no-filter-sensitive", action="store_true", help="Disable sensitivity filtering")

    args = parser.parse_args()
    summary = extract_session_corpus(
        session_path=args.session,
        output_path=args.output,
        sample_size=args.sample_size,
        project_tag=args.project_tag,
        filter_sensitive=not args.no_filter_sensitive,
    )
    print("Corpus extraction complete:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
