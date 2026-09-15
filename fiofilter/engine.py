"""Stateless evidence pipeline. Any operational uncertainty returns original bytes.

Modes affect this call only. Profiles restrict the default policy; neither
profiles, metadata hints nor storage consent grant transformation authority.
"""
import hashlib
import re
import time
from typing import List, Optional

from fiofilter import classifier as _classifier
from fiofilter import invariants as _invariants
from fiofilter import metrics as _metrics
from fiofilter.profiles import get_profile
from fiofilter.profiles.default import DefaultProfile
from fiofilter.raw_store import RawStore, get_default_store
from fiofilter.sensitivity import contains_sensitive_material
from fiofilter.transforms import LOSSLESS_TRANSFORM_IDS, get_transform
from fiofilter.transforms.t01_dup_fold import decode_visible
from fiofilter.types import (Disposition, EvidenceClass, FilterResult, Mode,
                             Persistence, Sensitivity, ToolResult)


def _inline_facts_present(content: bytes, facts: List[str]) -> bool:
    try:
        return all(fact.encode('utf-8') in content for fact in facts)
    except (AttributeError, UnicodeError):
        return False


def process(tool_result: ToolResult, mode: Mode = Mode.BUILD,
            profile_id: str = 'default', raw_store: Optional[RawStore] = None,
            metrics_log_path=None) -> FilterResult:
    """Process valid byte input. No disk side effects unless explicitly requested.

    PERSIST requires NON_SENSITIVE caller assessment and no detector signal.
    DO_NOT_PERSIST returns RAW without retaining a recovery archive. A metrics
    path independently opts into a content-free audit log for non-sensitive
    results; sensitive results are audited only in the returned object.
    """
    raw = tool_result.content
    if not isinstance(raw, bytes):
        raise TypeError('ToolResult.content must be bytes')
    sha = hashlib.sha256(raw).hexdigest()
    visible = raw
    evidence = EvidenceClass.UNKNOWN
    disposition = Disposition.RAW
    persistence = Persistence.DO_NOT_PERSIST
    sensitivity = Sensitivity.UNKNOWN
    ref = None
    facts = []
    transform_id = None
    duration = 0.0
    reason = 'RAW_DEFAULT'
    checks = []
    selected_profile = 'unknown'
    stage = 'INPUT_POLICY'
    pipeline_failed = False
    storage_outcome = 'NOT_ATTEMPTED'
    valid_mode = mode if isinstance(mode, Mode) else Mode.BUILD
    try:
        if (not isinstance(mode, Mode)
                or not isinstance(tool_result.persistence, Persistence)
                or not isinstance(tool_result.sensitivity, Sensitivity)):
            raise ValueError('Invalid policy enum')
        metadata = '\n'.join(str(x) for x in (
            tool_result.command, tool_result.source, tool_result.session_id,
            tool_result.content_type_hint, tool_result.inline_required_facts,
            tool_result.stream, profile_id) if x is not None).encode('utf-8')
        sensitivity = tool_result.sensitivity
        if (contains_sensitive_material(raw) or contains_sensitive_material(metadata)
                or sensitivity == Sensitivity.SENSITIVE):
            sensitivity = Sensitivity.SENSITIVE
            persistence = Persistence.DO_NOT_PERSIST
        else:
            persistence = tool_result.persistence
            if persistence == Persistence.PERSIST and sensitivity != Sensitivity.NON_SENSITIVE:
                persistence = Persistence.EPHEMERAL
        stage = 'CLASSIFY'
        classification = _classifier.classify(raw, exit_code=tool_result.exit_code)
        evidence = classification.evidence_class
        if (not isinstance(evidence, EvidenceClass)
                or not (_classifier.MIN_CONFIDENCE <= classification.confidence <= 1)):
            evidence = EvidenceClass.UNKNOWN
        facts = list(classification.inline_required_facts) + list(tool_result.inline_required_facts)
        if not all(isinstance(f, str) for f in facts):
            raise ValueError('Invalid inline fact')
        stage = 'POLICY'
        if profile_id not in ('default', 'fioos', 'fioideias'):
            raise ValueError('Unknown profile')
        selected_profile = profile_id
        policy = get_profile(profile_id).get_policy(evidence, mode)
        core = DefaultProfile().get_policy(evidence, mode)
        allowed = policy.transform_whitelist & core.transform_whitelist
        candidate = 'T01' if 'T01' in allowed else None
        ok, results = _invariants.check_all(
            evidence_class=evidence, mode=mode, exit_code=tool_result.exit_code,
            proposed_transform_id=candidate, lossless_transform_ids=LOSSLESS_TRANSFORM_IDS)
        checks = [{'id': name, 'passed': r.ok} for name, r in zip(
            ('I5', 'I6', 'I7', 'protected_class', 'mode', 'I8'), results)]
        eligible = (ok and candidate == 'T01'
                    and evidence in (EvidenceClass.NOISE, EvidenceClass.PROGRESS)
                    and Disposition.TRANSFORM in policy.allowed_dispositions
                    and Disposition.TRANSFORM in core.allowed_dispositions)
        # Metadata can restrict eligibility, never establish low evidence value.
        if (tool_result.truncated or tool_result.stream not in ('combined', 'stdout', 'file')
                or tool_result.content_type_hint not in (None, 'text')
                or re.search(r'\bgit(?:\.exe)?\b', tool_result.command or '', re.I)):
            eligible = False
            reason = 'METADATA_REQUIRES_RAW'
        if persistence == Persistence.DO_NOT_PERSIST:
            eligible = False
            reason = 'NO_ARCHIVE_RAW'
            storage_outcome = 'FORBIDDEN'
        else:
            stage = 'RECOVERY'
            store = raw_store if raw_store is not None else get_default_store()
            if persistence == Persistence.PERSIST:
                storage_outcome = 'WRITE_ATTEMPTED'
                ref = store.write(raw)  # No command/session/facts in content metadata.
                if store.read(ref) != raw:
                    raise ValueError('Recovery mismatch')
            else:
                ref = RawStore.ephemeral(raw)
            storage_outcome = 'READY'
        if eligible:
            stage = 'TRANSFORM'
            transform = get_transform(candidate)
            started = time.perf_counter()
            try:
                output = transform.apply(raw)
            finally:
                duration = (time.perf_counter() - started) * 1000
            stage = 'VALIDATE'
            if output is None:
                reason = 'T01_NO_SAVINGS_OR_UNSAFE_FORMAT'
            elif not isinstance(output, bytes) or not output or len(output) >= len(raw):
                reason = 'T01_INVALID_OR_NONREDUCING'
            elif (not _inline_facts_present(output, facts)
                  or any(output.count(f.encode()) < raw.count(f.encode()) for f in facts)):
                reason = 'INLINE_FACT_OR_MULTIPLICITY_GUARD'
            elif decode_visible(output, max_output_bytes=len(raw)) != raw:
                raise ValueError('T01 reconstruction mismatch')
            else:
                visible = output
                disposition = Disposition.TRANSFORM
                transform_id = candidate
                reason = 'T01_VALIDATED'
                checks.extend({'id': name, 'passed': True} for name in
                              ('I2', 'I4', 'I9', 'T01_VISIBLE_BYTE_IDENTITY'))
        elif reason == 'RAW_DEFAULT':
            reason = 'EVIDENCE_OR_PROFILE_REQUIRES_RAW'
    except Exception:
        visible = raw
        disposition = Disposition.ESCALATE_TO_RAW
        transform_id = None
        reason = stage + '_FAILED_RAW'
        pipeline_failed = True
        # Do not claim non-persistence after a disk write was attempted. A
        # sidecar failure may leave a complete blob; retain valid ready refs.
        if storage_outcome == 'WRITE_ATTEMPTED':
            storage_outcome = 'FAILED_MAY_HAVE_BLOB'
            ref = None
        elif ref is None:
            persistence = Persistence.DO_NOT_PERSIST

    metrics = _metrics.make_metrics(raw, visible, disposition, evidence,
                                   valid_mode, transform_duration_ms=duration)
    audit = {'schema': 2, 'profile': selected_profile,
             'invariant_checks': checks, 'reason': reason,
             'disposition': disposition.value, 'evidence_class': evidence.value,
             'mode': valid_mode.value, 'transform_id': transform_id,
             'persistence': persistence.value, 'sensitivity': sensitivity.value,
             'storage_outcome': storage_outcome}
    # I16: returned in-memory audit always exists. Disk logging is optional.
    if (metrics_log_path is not None and not pipeline_failed
            and persistence != Persistence.DO_NOT_PERSIST):
        try:
            _metrics.log_metrics(metrics, sha, transform_id=transform_id,
                                 log_path=metrics_log_path, audit=audit)
        except Exception:
            visible = raw
            disposition = Disposition.ESCALATE_TO_RAW
            transform_id = None
            reason = 'AUDIT_WRITE_FAILED_RAW'
            metrics = _metrics.make_metrics(raw, raw, disposition, evidence, valid_mode,
                                            transform_duration_ms=duration)
            audit.update(reason=reason, disposition=disposition.value, transform_id=None)
    return FilterResult(
        content=visible, disposition=disposition, raw_ref=ref, raw_sha256=sha,
        evidence_class=evidence, mode=valid_mode, metrics=metrics,
        transform_id=transform_id, policy_decision=reason, inline_required_facts=facts,
        persistence=persistence, sensitivity=sensitivity, audit=audit,
        source=tool_result.source, command=tool_result.command, session_id=tool_result.session_id,
        stream=tool_result.stream,
        exit_code=tool_result.exit_code, truncated=tool_result.truncated)
