"""Adversarial evidence regressions; each assertion rejects a material M01 defect."""
import json
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from fiofilter.classifier import classify
from fiofilter.engine import process
from fiofilter.profiles.base import _TRANSFORM_T01
from fiofilter.types import Disposition, EvidenceClass, Mode, ToolResult

NOISE = b'Building... [   OK   ]\n' * 900


def test_full_content_precedence(tmp_raw_store, tmp_metrics_log):
    for extra, expected in [
        (b'ERROR: lost evidence\n', EvidenceClass.FAILURE),
        (b'137 passed\nwarning: partial result\n', EvidenceClass.DIAGNOSTIC),
        (b'On branch main\nwarning: incomplete\n', EvidenceClass.DIAGNOSTIC),
        (b'{"status": "ERROR", "detail": "broken"}\n', EvidenceClass.FAILURE),
        (b'\x1b[31mER\x1b[0mROR: broken\n', EvidenceClass.FAILURE),
    ]:
        raw = NOISE + extra
        result = process(ToolResult(raw), mode=Mode.EXPLORE,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        assert result.evidence_class == expected
        assert result.content == raw
        assert result.disposition != Disposition.TRANSFORM


def test_repetition_is_not_evidence_of_disposability(tmp_raw_store, tmp_metrics_log):
    raw = b'Payment accepted for order 123\n' * 30
    assert classify(raw).evidence_class == EvidenceClass.UNKNOWN
    assert process(ToolResult(raw), raw_store=tmp_raw_store,
                   metrics_log_path=tmp_metrics_log).content == raw


def test_profile_cannot_route_machine_data_into_t01(tmp_raw_store, tmp_metrics_log):
    raw = json.dumps(['long value for a machine consumer'] * 30, indent=2).encode()
    class PermissiveProfile:
        def get_policy(self, *args):
            return _TRANSFORM_T01
    with patch('fiofilter.engine.get_profile', return_value=PermissiveProfile()):
        result = process(ToolResult(raw), mode=Mode.EXPLORE,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
    assert result.content == raw
    assert result.disposition != Disposition.TRANSFORM


def test_known_noise_reduces_in_prove_without_session_state(tmp_raw_store, tmp_metrics_log):
    for profile in ('default', 'fioos', 'fioideias'):
        process(ToolResult(b'ERROR\n', exit_code=1), mode=Mode.PROVE,
                raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        result = process(ToolResult(NOISE), mode=Mode.PROVE, profile_id=profile,
                         raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
        assert result.evidence_class == EvidenceClass.NOISE
        assert result.disposition == Disposition.TRANSFORM
        assert result.mode == Mode.PROVE


def test_classifier_exception_returns_raw(tmp_raw_store, tmp_metrics_log):
    with patch('fiofilter.engine._classifier.classify', side_effect=RuntimeError):
        result = process(ToolResult(NOISE), raw_store=tmp_raw_store,
                         metrics_log_path=tmp_metrics_log)
    assert result.content == NOISE
    assert result.disposition != Disposition.TRANSFORM


def test_mixed_encodings_metadata_and_nonzero_preserve_bytes(tmp_raw_store):
    cases = [
        ToolResult(b'', exit_code=1, stream='stderr'),
        ToolResult(b'Everything looks fine\n', exit_code=2),
        ToolResult(NOISE + b'ERROR\n', exit_code=0),
        ToolResult(NOISE + b'\xff\xfe'),
        ToolResult(NOISE + b'\x00'),
        ToolResult(NOISE, truncated=True),
        ToolResult(NOISE, stream='stderr'),
        ToolResult(NOISE, content_type_hint='json'),
        ToolResult(NOISE, command='git status --porcelain'),
        ToolResult(b'{\n' + NOISE + b'malformed json\n'),
        ToolResult('├── exemplo\r\n└── resultado\n'.encode()),
        ToolResult(b'x' * 300_000 + b'\nERROR: late failure\n'),
    ]
    for tr in cases:
        result = process(tr, raw_store=tmp_raw_store)
        assert result.content == tr.content
        assert result.disposition != Disposition.TRANSFORM
        assert result.exit_code == tr.exit_code
        assert result.stream == tr.stream
        assert result.truncated == tr.truncated
        if result.raw_ref is not None:
            assert tmp_raw_store.read(result.raw_ref) == tr.content


def test_random_position_failure_precedence(tmp_raw_store):
    rng = random.Random(20260915)
    for _ in range(80):
        lines = [b'Building... [   OK   ]\n'] * rng.randrange(10, 1200)
        lines.insert(rng.randrange(len(lines)+1), rng.choice([
            b'ERROR: hidden\n', b'FAIL\n', b'\x1b[31mFAILED\x1b[0m\n']))
        raw = b''.join(lines)
        result = process(ToolResult(raw, exit_code=0), raw_store=tmp_raw_store)
        assert result.evidence_class == EvidenceClass.FAILURE
        assert result.content == raw


def test_all_operational_exception_paths_fall_back_to_raw(tmp_raw_store, tmp_metrics_log):
    from fiofilter.transforms.t01_dup_fold import DuplicateLineFold
    from fiofilter.types import Persistence, Sensitivity
    for target in ('fiofilter.engine.get_profile', 'fiofilter.engine.get_transform',
                   'fiofilter.engine.decode_visible', 'fiofilter.engine._metrics.log_metrics'):
        with patch(target, side_effect=RuntimeError('payload must not be logged')):
            result = process(ToolResult(NOISE), raw_store=tmp_raw_store,
                             metrics_log_path=tmp_metrics_log)
        assert result.content == NOISE
        assert result.disposition != Disposition.TRANSFORM
        assert 'payload' not in json.dumps(result.audit)
    with patch.object(DuplicateLineFold, 'apply', side_effect=RuntimeError):
        result = process(ToolResult(NOISE), raw_store=tmp_raw_store)
    assert result.content == NOISE
    with patch.object(tmp_raw_store, 'write', side_effect=OSError):
        result = process(ToolResult(NOISE, persistence=Persistence.PERSIST,
                                    sensitivity=Sensitivity.NON_SENSITIVE), raw_store=tmp_raw_store)
    assert result.content == NOISE and result.raw_ref is None


def test_invalid_transform_results_and_unknown_profile_are_raw(tmp_raw_store):
    from fiofilter.transforms.t01_dup_fold import DuplicateLineFold
    for invalid in (b'', 'wrong type', b'arbitrarily shorter but loses evidence', NOISE + b'x'):
        with patch.object(DuplicateLineFold, 'apply', return_value=invalid):
            result = process(ToolResult(NOISE), raw_store=tmp_raw_store)
        assert result.content == NOISE
        assert result.disposition != Disposition.TRANSFORM
    assert process(ToolResult(NOISE), profile_id='unknown', raw_store=tmp_raw_store).content == NOISE


def test_transform_cannot_run_before_recovery(tmp_raw_store):
    from fiofilter.transforms.t01_dup_fold import DuplicateLineFold
    from fiofilter.types import Persistence, Sensitivity
    original = DuplicateLineFold.apply
    import hashlib
    def apply(self, raw):
        assert tmp_raw_store.exists(hashlib.sha256(raw).hexdigest())
        return original(self, raw)
    with patch.object(DuplicateLineFold, 'apply', apply):
        result = process(ToolResult(NOISE, persistence=Persistence.PERSIST,
                                    sensitivity=Sensitivity.NON_SENSITIVE), raw_store=tmp_raw_store)
    assert result.disposition == Disposition.TRANSFORM
    assert tmp_raw_store.read(result.raw_ref) == NOISE
