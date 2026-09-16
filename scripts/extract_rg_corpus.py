"""Extract a local M03_SEARCH_CORPUS_V1 without assigning safety labels.

The utility reads a caller-supplied historical JSONL twice: once for an exact
artifact fingerprint and once for bounded-memory call/output pairing.  Clean
candidates and bounded negative controls are written outside the repository.
No output is connected to the transform engine.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import tempfile
from collections import Counter, OrderedDict
from typing import Any, Dict, List, Optional, TextIO, Tuple

from fiofilter.search_corpus import (
    ARTIFACT_RELATIONSHIPS,
    ARTIFACT_RELATION_UNKNOWN,
    EXTRACTION_TOOL_VERSION,
    SEARCH_CORPUS_SCHEMA_VERSION,
    CommandRejected,
    InvocationRejected,
    ResultRejected,
    RgParseError,
    classify_rg_command,
    contains_shell_failure_wrapper,
    contains_upstream_truncation_marker,
    decode_execution_result,
    deterministic_review_selection,
    encode_rg_output,
    ensure_outside_repository,
    extract_structured_exec_command,
    fingerprint_jsonl_artifact,
    parse_rg_output,
)
from fiofilter.sensitivity import contains_sensitive_material


def _temporary_text_file(target: pathlib.Path) -> Tuple[TextIO, pathlib.Path]:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent), text=True
    )
    return os.fdopen(descriptor, "w", encoding="utf-8", newline="\n"), pathlib.Path(name)


def _publish_no_clobber(temporary: pathlib.Path, target: pathlib.Path) -> None:
    """Publish on the same volume without replacing an existing local corpus."""
    os.link(temporary, target)
    temporary.unlink()


def _entry_id(kind: str, occurrence_index: int, call_id: str) -> str:
    call_digest = hashlib.sha256(call_id.encode("utf-8")).hexdigest()[:10].upper()
    return f"M03-RG-{kind}-{occurrence_index:08d}-{call_digest}"


def _structural_record(record: Any) -> Dict[str, Any]:
    return {
        "ordering_index": record.ordering_index,
        "path_b64": base64.b64encode(record.path).decode("ascii"),
        "line_number": record.line_number,
        "column_number": record.column_number,
        "kind": record.kind,
        "payload_b64": base64.b64encode(record.payload).decode("ascii"),
        "separator_b64": base64.b64encode(record.separator).decode("ascii"),
        "raw_line_ending_b64": base64.b64encode(record.raw_line_ending).decode("ascii"),
        "header_association_b64": (
            base64.b64encode(record.header_association).decode("ascii")
            if record.header_association is not None
            else None
        ),
    }


def _negative_record(
    *,
    artifact_id: str,
    occurrence_index: int,
    call_id: str,
    reason: str,
    content: bytes,
    command: Optional[str],
    exit_code: int,
    truncated: bool,
) -> Dict[str, Any]:
    return {
        "schema_version": SEARCH_CORPUS_SCHEMA_VERSION,
        "record_kind": "NEGATIVE_CONTROL",
        "entry_id": _entry_id("NEGATIVE", occurrence_index, call_id),
        "artifact_id": artifact_id,
        "source_locator_local_only": {
            "call_id": call_id,
            "occurrence_index": occurrence_index,
        },
        "command_local_only": command,
        "execution": {
            "exit_code": exit_code,
            "truncated": truncated,
        },
        "exclusion_reason": reason,
        "sensitivity_screening": {
            "result": "DETECTOR_NO_MATCH",
            "method": "fiofilter.sensitivity.contains_sensitive_material",
            "notes": "Screening result only; not a NON_SENSITIVE assessment.",
        },
        "oracle_labels": None,
        "raw_sha256": hashlib.sha256(content).hexdigest(),
        "raw_content_b64": base64.b64encode(content).decode("ascii"),
    }


def _clean_record(
    *,
    artifact_id: str,
    occurrence_index: int,
    call_id: str,
    command: Any,
    content: bytes,
    parsed: Any,
) -> Dict[str, Any]:
    paths = [record.path for record in parsed.records]
    encoded_records = [record.encode() for record in parsed.records]
    return {
        "schema_version": SEARCH_CORPUS_SCHEMA_VERSION,
        "corpus_id": "M03_SEARCH_CORPUS_V1",
        "record_kind": "CLEAN_CANDIDATE",
        "entry_id": _entry_id("CLEAN", occurrence_index, call_id),
        "artifact_id": artifact_id,
        "source_locator_local_only": {
            "call_id": call_id,
            "occurrence_index": occurrence_index,
        },
        "command_local_only": command.raw,
        "producer_fingerprint": command.fingerprint(),
        "execution": {
            "exit_code": 0,
            "truncated": False,
            "stdout_stderr": "combined",
        },
        "sensitivity_screening": {
            "result": "DETECTOR_NO_MATCH",
            "method": "fiofilter.sensitivity.contains_sensitive_material",
            "notes": "Screening result only; not a NON_SENSITIVE assessment.",
        },
        "heuristic_candidate_metadata": {
            "method": EXTRACTION_TOOL_VERSION,
            "producer_family": "RIPGREP",
            "format_category": parsed.grammar,
            "declares_transform_safety": False,
        },
        "oracle_labels": None,
        "characterization": {
            "grammar": parsed.grammar,
            "record_count": len(parsed.records),
            "distinct_path_count": len(set(paths)),
            "duplicate_path_occurrences": len(paths) - len(set(paths)),
            "duplicate_identical_record_occurrences": (
                len(encoded_records) - len(set(encoded_records))
            ),
            "raw_sha256": parsed.raw_sha256,
            "byte_exact_roundtrip": encode_rg_output(parsed) == content,
            "structural_records": [_structural_record(record) for record in parsed.records],
        },
        "raw_content_b64": base64.b64encode(content).decode("ascii"),
    }


def extract_rg_corpus(
    *,
    session_path: pathlib.Path | str,
    output_path: pathlib.Path | str,
    negative_output_path: pathlib.Path | str,
    manifest_path: pathlib.Path | str,
    observation_date: str,
    relationship_to_prior_artifact: str = ARTIFACT_RELATION_UNKNOWN,
    prior_artifact_id: Optional[str] = None,
    review_limit_per_grammar: int = 12,
    negative_limit_per_reason: int = 5,
    max_pending_calls: int = 4096,
    max_candidate_index: int = 10000,
) -> Dict[str, Any]:
    """Extract every clean candidate and bounded negative controls deterministically."""
    if negative_limit_per_reason < 1:
        raise ValueError("negative_limit_per_reason must be positive")
    if max_pending_calls < 1 or max_candidate_index < 1:
        raise ValueError("memory bounds must be positive")

    session = pathlib.Path(session_path)
    clean_output = ensure_outside_repository(output_path)
    negative_output = ensure_outside_repository(negative_output_path)
    manifest_output = ensure_outside_repository(manifest_path)
    if len({clean_output, negative_output, manifest_output}) != 3:
        raise ValueError("Clean, negative, and manifest outputs must be distinct")
    for target in (clean_output, negative_output, manifest_output):
        if target.exists():
            raise FileExistsError(f"Refusing to overwrite existing corpus output: {target}")

    fingerprint = fingerprint_jsonl_artifact(
        session,
        observation_date=observation_date,
        relationship_to_prior_artifact=relationship_to_prior_artifact,
        prior_artifact_id=prior_artifact_id,
    )

    clean_handle, clean_temp = _temporary_text_file(clean_output)
    negative_handle, negative_temp = _temporary_text_file(negative_output)
    manifest_temp: Optional[pathlib.Path] = None
    pending: OrderedDict[str, Tuple[Dict[str, Any], int]] = OrderedDict()
    exclusions: Counter[str] = Counter()
    negative_written: Counter[str] = Counter()
    clean_categories: Counter[str] = Counter()
    candidate_index: List[Dict[str, Any]] = []
    clean_count = 0
    paired_output_count = 0
    published: List[pathlib.Path] = []

    def reject(
        reason: str,
        *,
        occurrence_index: int,
        call_id: str,
        result: Optional[Any],
        command_text: Optional[str],
    ) -> None:
        exclusions[reason] += 1
        if result is None:
            return
        if negative_written[reason] >= negative_limit_per_reason:
            return
        negative_handle.write(
            json.dumps(
                _negative_record(
                    artifact_id=fingerprint.artifact_id,
                    occurrence_index=occurrence_index,
                    call_id=call_id,
                    reason=reason,
                    content=result.content,
                    command=command_text,
                    exit_code=result.exit_code,
                    truncated=result.truncated,
                ),
                sort_keys=True,
            )
            + "\n"
        )
        negative_written[reason] += 1

    try:
        with open(session, "rb") as source:
            for occurrence_index, raw_line in enumerate(source, start=1):
                if not raw_line.strip():
                    continue
                try:
                    record = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    exclusions["MALFORMED_SOURCE_RECORD"] += 1
                    continue
                if not isinstance(record, dict):
                    exclusions["MALFORMED_SOURCE_RECORD"] += 1
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                payload_type = payload.get("type")
                call_id = payload.get("call_id")

                if payload_type == "custom_tool_call" and isinstance(call_id, str) and call_id:
                    pending[call_id] = (payload, occurrence_index)
                    pending.move_to_end(call_id)
                    if len(pending) > max_pending_calls:
                        pending.popitem(last=False)
                        exclusions["PENDING_CALL_EVICTED"] += 1
                    continue

                if payload_type != "custom_tool_call_output":
                    continue
                if not isinstance(call_id, str) or not call_id:
                    exclusions["OUTPUT_WITHOUT_CALL_ID"] += 1
                    continue
                paired = pending.pop(call_id, None)
                if paired is None:
                    exclusions["UNMATCHED_OUTPUT"] += 1
                    continue
                paired_output_count += 1
                call_payload, call_occurrence = paired

                try:
                    result = decode_execution_result(payload)
                except ResultRejected as exc:
                    reject(
                        exc.reason,
                        occurrence_index=call_occurrence,
                        call_id=call_id,
                        result=None,
                        command_text=None,
                    )
                    continue

                if contains_sensitive_material(result.content):
                    exclusions["SENSITIVE_DETECTOR_MATCH"] += 1
                    continue

                command_text: Optional[str] = None
                try:
                    command_text = extract_structured_exec_command(call_payload)
                    command = classify_rg_command(command_text)
                except (InvocationRejected, CommandRejected) as exc:
                    reject(
                        exc.reason,
                        occurrence_index=call_occurrence,
                        call_id=call_id,
                        result=result,
                        command_text=command_text,
                    )
                    continue

                if result.exit_code == 1:
                    reject(
                        "RG_NO_MATCH_EXIT_1",
                        occurrence_index=call_occurrence,
                        call_id=call_id,
                        result=result,
                        command_text=command_text,
                    )
                    continue
                if result.exit_code != 0:
                    reject(
                        "RG_EXECUTION_ERROR",
                        occurrence_index=call_occurrence,
                        call_id=call_id,
                        result=result,
                        command_text=command_text,
                    )
                    continue
                if result.truncated:
                    reject(
                        "TRUNCATED_RESULT",
                        occurrence_index=call_occurrence,
                        call_id=call_id,
                        result=result,
                        command_text=command_text,
                    )
                    continue
                if contains_upstream_truncation_marker(result.content):
                    reject(
                        "UPSTREAM_TRUNCATION_MARKER",
                        occurrence_index=call_occurrence,
                        call_id=call_id,
                        result=result,
                        command_text=command_text,
                    )
                    continue
                if contains_shell_failure_wrapper(result.content):
                    reject(
                        "SHELL_FAILURE_WRAPPER",
                        occurrence_index=call_occurrence,
                        call_id=call_id,
                        result=result,
                        command_text=command_text,
                    )
                    continue

                try:
                    parsed = parse_rg_output(result.content, command.grammar)
                except RgParseError as exc:
                    reject(
                        exc.reason,
                        occurrence_index=call_occurrence,
                        call_id=call_id,
                        result=result,
                        command_text=command_text,
                    )
                    continue

                if encode_rg_output(parsed) != result.content:
                    raise RuntimeError("Parser admitted output without exact round-trip")
                clean_record = _clean_record(
                    artifact_id=fingerprint.artifact_id,
                    occurrence_index=call_occurrence,
                    call_id=call_id,
                    command=command,
                    content=result.content,
                    parsed=parsed,
                )
                clean_handle.write(json.dumps(clean_record, sort_keys=True) + "\n")
                clean_count += 1
                clean_categories[parsed.grammar] += 1
                if len(candidate_index) >= max_candidate_index:
                    raise RuntimeError(
                        "Candidate index bound exceeded; no output was published"
                    )
                candidate_index.append(
                    {
                        "entry_id": clean_record["entry_id"],
                        "grammar": parsed.grammar,
                        "byte_length": len(result.content),
                        "occurrence_index": call_occurrence,
                    }
                )

        if pending:
            exclusions["UNMATCHED_CALL"] += len(pending)

        review_selection = deterministic_review_selection(
            candidate_index, limit_per_grammar=review_limit_per_grammar
        )
        summary: Dict[str, Any] = {
            "clean_candidate_count": clean_count,
            "clean_category_counts": dict(sorted(clean_categories.items())),
            "paired_output_count": paired_output_count,
            "exclusion_counts": dict(sorted(exclusions.items())),
            "negative_control_counts_written": dict(sorted(negative_written.items())),
            "automated_characterization_scope": "ALL_CLEAN_CANDIDATES",
            "independent_review_selection_count": len(review_selection),
            "oracle_labels_assigned": 0,
        }
        manifest = {
            "schema_version": SEARCH_CORPUS_SCHEMA_VERSION,
            "corpus_id": "M03_SEARCH_CORPUS_V1",
            "source_artifact_fingerprint": fingerprint.to_dict(),
            "extraction_summary": summary,
            "independent_review_selection_method": (
                "DETERMINISTIC_PER_GRAMMAR_SIZE_QUANTILES_THEN_OCCURRENCE"
            ),
            "independent_review_selection": review_selection,
            "negative_control_policy": {
                "selection": "FIRST_N_PER_EXCLUSION_REASON_IN_SOURCE_ORDER",
                "limit_per_reason": negative_limit_per_reason,
                "sensitive_detector_matches_persisted": False,
            },
            "claim_boundary": {
                "characterization_is_transform_safety": False,
                "detector_no_match_is_non_sensitive_assessment": False,
                "oracle_labels_assigned": False,
            },
        }

        clean_handle.flush()
        negative_handle.flush()
        clean_handle.close()
        negative_handle.close()
        manifest_handle, manifest_temp = _temporary_text_file(manifest_output)
        manifest_handle.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        manifest_handle.flush()
        manifest_handle.close()

        _publish_no_clobber(clean_temp, clean_output)
        published.append(clean_output)
        _publish_no_clobber(negative_temp, negative_output)
        published.append(negative_output)
        _publish_no_clobber(manifest_temp, manifest_output)
        published.append(manifest_output)
        return summary
    except Exception:
        if not clean_handle.closed:
            clean_handle.close()
        if not negative_handle.closed:
            negative_handle.close()
        for temporary in (clean_temp, negative_temp, manifest_temp):
            if temporary is not None:
                try:
                    temporary.unlink()
                except FileNotFoundError:
                    pass
        for target in reversed(published):
            try:
                target.unlink()
            except FileNotFoundError:
                pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract the local M03_SEARCH_CORPUS_V1 laboratory corpus"
    )
    parser.add_argument("--session", required=True, help="Local historical JSONL path")
    parser.add_argument("--output", required=True, help="Clean corpus JSONL outside Git")
    parser.add_argument(
        "--negative-output", required=True, help="Bounded negative-control JSONL outside Git"
    )
    parser.add_argument("--manifest", required=True, help="Local fingerprint/summary manifest")
    parser.add_argument(
        "--observation-date",
        required=True,
        help="Explicit YYYY-MM-DD evidence observation date",
    )
    parser.add_argument(
        "--relationship-to-prior-artifact",
        choices=ARTIFACT_RELATIONSHIPS,
        default=ARTIFACT_RELATION_UNKNOWN,
    )
    parser.add_argument("--prior-artifact-id", default=None)
    parser.add_argument("--review-limit-per-grammar", type=int, default=12)
    parser.add_argument("--negative-limit-per-reason", type=int, default=5)
    args = parser.parse_args()

    summary = extract_rg_corpus(
        session_path=args.session,
        output_path=args.output,
        negative_output_path=args.negative_output,
        manifest_path=args.manifest,
        observation_date=args.observation_date,
        relationship_to_prior_artifact=args.relationship_to_prior_artifact,
        prior_artifact_id=args.prior_artifact_id,
        review_limit_per_grammar=args.review_limit_per_grammar,
        negative_limit_per_reason=args.negative_limit_per_reason,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
