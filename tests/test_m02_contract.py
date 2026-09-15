"""Cross-component policy, audit and economics contracts."""
import json
from pathlib import Path
from unittest.mock import patch

from fiofilter.classifier import ClassifyResult
from fiofilter.engine import process
from fiofilter.metrics import make_metrics
from fiofilter.profiles import available_profile_ids, get_profile
from fiofilter.profiles.base import _TRANSFORM_T01
from fiofilter.profiles.default import DefaultProfile
from fiofilter.types import Disposition, EvidenceClass, Mode, ToolResult

ROOT = Path(__file__).resolve().parents[1]


def test_python_profiles_are_only_policy_source_and_cannot_expand_core():
    assert not list((ROOT / 'profiles').glob('*.yaml'))
    for name in available_profile_ids():
        for cls in EvidenceClass:
            for mode in Mode:
                policy = get_profile(name).get_policy(cls, mode)
                core = DefaultProfile().get_policy(cls, mode)
                assert policy.allowed_dispositions <= core.allowed_dispositions
                assert policy.transform_whitelist <= core.transform_whitelist
                if cls == EvidenceClass.NOISE:
                    assert 'T01' in policy.transform_whitelist


def test_permissive_profile_never_expands_transform_class_contract(tmp_raw_store):
    class Permissive:
        def get_policy(self, *args):
            return _TRANSFORM_T01
    raw = b'Building... [   OK   ]\n' * 50
    with patch('fiofilter.engine.get_profile', return_value=Permissive()):
        for cls in EvidenceClass:
            for mode in Mode:
                if cls in (EvidenceClass.NOISE, EvidenceClass.PROGRESS):
                    continue
                with patch('fiofilter.engine._classifier.classify', return_value=ClassifyResult(cls, 1.0)):
                    result = process(ToolResult(raw), mode=mode, raw_store=tmp_raw_store)
                assert result.content == raw
                assert result.disposition != Disposition.TRANSFORM


def test_low_confidence_and_nonzero_exit_override_permissive_policy(tmp_raw_store):
    raw = b'Building... [   OK   ]\n' * 50
    for confidence, exit_code in ((0.1, 0), (float('nan'), 0), (1.0, 9)):
        with patch('fiofilter.engine._classifier.classify', return_value=ClassifyResult(EvidenceClass.NOISE, confidence)):
            result = process(ToolResult(raw, exit_code=exit_code), raw_store=tmp_raw_store)
        assert result.content == raw
        assert result.disposition != Disposition.TRANSFORM


def test_audit_is_replay_description_not_content_archive(tmp_raw_store, tmp_metrics_log):
    result = process(ToolResult(b'Building... [   OK   ]\n' * 50),
                     raw_store=tmp_raw_store, metrics_log_path=tmp_metrics_log)
    record = json.loads(tmp_metrics_log.read_text())
    assert record['audit'] == result.audit
    assert record['audit']['profile'] == 'default'
    assert record['audit']['transform_id'] == 'T01'
    assert record['audit']['invariant_checks']
    assert 'Building' not in tmp_metrics_log.read_text()
    assert record['actual_model_tokens'] is None
    assert record['model_turns'] is None
    assert record['raw_recovery_count'] is None
    assert record['token_estimate_method'].endswith('ESTIMATE')


def test_external_economics_remain_distinct_and_unmeasured_by_default():
    raw = '🔬é'.encode()
    metrics = make_metrics(raw, raw, Disposition.RAW, EvidenceClass.UNKNOWN, Mode.BUILD,
                           actual_model_tokens=700, model_turns=2,
                           corrective_retrievals=1, raw_recovery_count=3)
    assert metrics.raw_bytes == len(raw)
    assert metrics.raw_token_estimate == len(raw) / 4
    assert metrics.actual_model_tokens == 700
    assert metrics.model_turns == 2
    assert metrics.corrective_retrievals == 1
    assert metrics.raw_recovery_count == 3
    assert metrics.transform_duration_ms == 0


def test_no_transform_has_zero_transform_time(tmp_raw_store):
    assert process(ToolResult(b'UNKNOWN payload'), raw_store=tmp_raw_store).metrics.transform_duration_ms == 0


def test_current_docs_and_ci_match_runtime_contract():
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    contract = (ROOT / 'docs/EVIDENCE-CONTRACT.md').read_text(encoding='utf-8')
    ci = (ROOT / '.github/workflows/tests.yml').read_text(encoding='utf-8')
    assert 'utf8_bytes_div_4_ESTIMATE' in readme
    assert 'EPHEMERAL' in readme and 'DO_NOT_PERSIST' in contract
    assert 'python -m pytest tests/ -v' in readme and 'python -m pytest tests/ -v' in ci
    assert 'windows-2022' in ci and 'ubuntu-24.04' in ci
    assert 'T04 is DEFERRED' in contract
    assert 'I16' in contract and 'I17/I18 enforcement' in contract
    from fiofilter.transforms import available_transform_ids
    assert available_transform_ids() == frozenset({'T01'})
    assert 'setuptools.build_meta' in (ROOT / 'pyproject.toml').read_text()
