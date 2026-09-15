"""Storage permission, metadata minimization and integrity regressions."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from fiofilter.engine import process
from fiofilter.raw_store import RawStore
from fiofilter.types import (Disposition, EvidenceClass, Mode, Persistence,
                             RawRef, Sensitivity, ToolResult)


def synthetic_secret():
    # Not a credential: generated inert characters, never a real provider value.
    return ''.join(chr(97 + n % 26) for n in range(48))


def test_sensitive_material_never_creates_archive_or_log(tmp_path):
    value = synthetic_secret()
    samples = [
        'Authorization: Bearer ' + value,
        'api_key=' + value, 'token=' + value, 'Cookie: session=' + value,
        'ghp_' + value, 'github_pat_' + value,
        '-----BEGIN PRIVATE KEY-----\n' + value,
        json.dumps({'password': value}),
        'api_\x1b[0mkey=' + value,
    ]
    for n, secret in enumerate(samples):
        raw = b'Building... [   OK   ]\n' * 900 + secret.encode()
        folder = tmp_path / str(n)
        store = RawStore(folder / 'raw')
        result = process(ToolResult(raw, persistence=Persistence.PERSIST,
                                    sensitivity=Sensitivity.NON_SENSITIVE),
                         raw_store=store, metrics_log_path=folder / 'audit.jsonl')
        assert result.content == raw
        assert result.persistence == Persistence.DO_NOT_PERSIST
        assert result.sensitivity == Sensitivity.SENSITIVE
        assert result.raw_ref is None
        assert not folder.exists()
        assert value not in json.dumps(result.audit)
        with pytest.raises(ValueError):
            store.write(raw)
        assert not folder.exists()


def test_secrets_in_metadata_and_explicit_sensitive_flag(tmp_path):
    for field in ('command', 'source', 'session_id', 'content_type_hint'):
        folder = tmp_path / field
        tr = ToolResult(b'.\n' * 200, **{field: 'token=' + synthetic_secret()})
        result = process(tr, raw_store=RawStore(folder), metrics_log_path=folder / 'log')
        assert result.raw_ref is None and result.content == tr.content
        assert not folder.exists()
    tr = ToolResult(b'private personal information', sensitivity=Sensitivity.SENSITIVE)
    assert process(tr).persistence == Persistence.DO_NOT_PERSIST


def test_ephemeral_is_default_even_when_store_supplied(tmp_path, monkeypatch):
    monkeypatch.setenv('FIOFILTER_RAW_STORE', str(tmp_path / 'env-store'))
    monkeypatch.setenv('FIOFILTER_METRICS_LOG', str(tmp_path / 'env-log'))
    store = RawStore(tmp_path / 'explicit-store')
    raw = b'Building... [   OK   ]\n' * 100
    for kwargs in ({}, {'raw_store': store}):
        result = process(ToolResult(raw), **kwargs)
        assert result.disposition == Disposition.TRANSFORM
        assert result.persistence == Persistence.EPHEMERAL
        assert store.read(result.raw_ref) == raw
        assert result.raw_ref.store_path == ''
    assert list(tmp_path.iterdir()) == []


def test_disk_storage_requires_assessment_and_metadata_is_content_only(tmp_raw_store):
    raw = b'security finding: CVE-2026-12345\n'
    unassessed = process(ToolResult(raw, persistence=Persistence.PERSIST), raw_store=tmp_raw_store)
    assert unassessed.persistence == Persistence.EPHEMERAL
    assert not tmp_raw_store.root.exists()
    tr = ToolResult(raw, command='security scanner', source='tool-A', session_id='event-A',
                    persistence=Persistence.PERSIST, sensitivity=Sensitivity.NON_SENSITIVE)
    first = process(tr, raw_store=tmp_raw_store)
    assert first.evidence_class == EvidenceClass.SECURITY
    assert first.persistence == Persistence.PERSIST
    assert tmp_raw_store.read(first.raw_ref) == raw
    tr.source = 'tool-B'
    tr.session_id = 'event-B'
    second = process(tr, raw_store=tmp_raw_store)
    assert first.source != second.source
    assert first.raw_ref == second.raw_ref
    assert tmp_raw_store.read_meta(first.raw_ref) == {
        'schema': 2, 'raw_sha256': hashlib.sha256(raw).hexdigest(), 'byte_length': len(raw)}
    assert not (tmp_raw_store.root / 'index.jsonl').exists()


def test_corrupt_blob_rejected_on_read_and_dedup(tmp_raw_store):
    raw = b'original bytes'
    ref = tmp_raw_store.write(raw)
    Path(ref.store_path).write_bytes(b'corrupted bytes')
    with pytest.raises(ValueError):
        tmp_raw_store.read(ref)
    with pytest.raises(ValueError):
        tmp_raw_store.write(raw)
    assert Path(ref.store_path).read_bytes() == b'corrupted bytes'
    result = process(ToolResult(raw, persistence=Persistence.PERSIST,
                                sensitivity=Sensitivity.NON_SENSITIVE), raw_store=tmp_raw_store)
    assert result.content == raw and result.raw_ref is None
    assert result.disposition != Disposition.TRANSFORM


def test_metadata_and_blob_missing_or_corrupt_are_explicit(tmp_raw_store):
    ref = tmp_raw_store.write(b'metadata consistency')
    path = tmp_raw_store._meta_path(ref.sha256)
    for invalid in ('{broken', '{}', '[]', '{"schema":true}', '\ufffd'):
        path.write_text(invalid, encoding='utf-8')
        assert tmp_raw_store.read(ref) == b'metadata consistency'
        with pytest.raises(ValueError):
            tmp_raw_store.read_meta(ref)
        with pytest.raises(ValueError):
            tmp_raw_store.write(b'metadata consistency')
    path.unlink()
    assert tmp_raw_store.read_meta(ref) is None
    assert tmp_raw_store.read(ref) == b'metadata consistency'
    tmp_raw_store.write(b'metadata consistency')  # Repair only missing derived sidecar.
    assert tmp_raw_store.read_meta(ref)['schema'] == 2
    Path(ref.store_path).unlink()
    with pytest.raises(FileNotFoundError):
        tmp_raw_store.read(ref)
    with pytest.raises(FileNotFoundError):
        tmp_raw_store.read_meta(ref)


def test_no_clobber_concurrent_writers(tmp_raw_store):
    raw = b'concurrent object\r\n' * 100
    with ThreadPoolExecutor(max_workers=8) as pool:
        refs = list(pool.map(lambda _: tmp_raw_store.write(raw), range(32)))
    assert len(set(refs)) == 1
    assert tmp_raw_store.read(refs[0]) == raw
    assert tmp_raw_store.read_meta(refs[0])['byte_length'] == len(raw)
    assert list(tmp_raw_store.root.rglob('.raw-*')) == []


def test_interrupted_publication_never_returns_partial_data(tmp_raw_store):
    raw = b'complete object\n'
    with patch('fiofilter.raw_store.os.link', side_effect=OSError('simulated interruption')):
        with pytest.raises(OSError):
            tmp_raw_store.write(raw)
    assert list(tmp_raw_store.root.rglob('.raw-*')) == []
    assert not tmp_raw_store.exists(hashlib.sha256(raw).hexdigest())
    # Crash after blob publication but before sidecar: recovery survives.
    original = RawStore._publish
    def publish(path, content):
        if path.suffix == '.json':
            raise OSError('simulated sidecar interruption')
        original(path, content)
    with patch.object(RawStore, '_publish', side_effect=publish):
        with pytest.raises(OSError):
            tmp_raw_store.write(raw)
    ref = RawRef(hashlib.sha256(raw).hexdigest(), 'ignored')
    assert tmp_raw_store.read(ref) == raw
    assert tmp_raw_store.read_meta(ref) is None
    assert tmp_raw_store.read(tmp_raw_store.write(raw)) == raw


def test_reference_paths_and_unchecked_reads_are_rejected(tmp_raw_store, tmp_path):
    outside = tmp_path / 'outside'
    outside.write_bytes(b'not an object')
    sha = hashlib.sha256(b'not an object').hexdigest()
    with pytest.raises(FileNotFoundError):
        tmp_raw_store.read(RawRef(sha, str(outside)))
    for invalid in ('../outside', 'A' * 64, '', 'a' * 63):
        with pytest.raises(ValueError):
            tmp_raw_store.exists(invalid)
    ref = tmp_raw_store.write(b'real object')
    with pytest.raises(ValueError):
        tmp_raw_store.read(ref, verify=False)


def test_failed_pipeline_does_not_claim_persistent_bytes_were_never_written(tmp_raw_store):
    from fiofilter.transforms.t01_dup_fold import DuplicateLineFold
    raw = b'Building... [   OK   ]\n' * 100
    tr = ToolResult(raw, persistence=Persistence.PERSIST, sensitivity=Sensitivity.NON_SENSITIVE)
    with patch.object(DuplicateLineFold, 'apply', side_effect=RuntimeError):
        result = process(tr, raw_store=tmp_raw_store)
    assert result.content == raw
    assert result.persistence == Persistence.PERSIST
    assert result.audit['storage_outcome'] == 'READY'
    assert tmp_raw_store.read(result.raw_ref) == raw
    # A separate object: write can publish a blob then fail publishing metadata.
    tr.content += b'.\n'
    original = RawStore._publish
    def publish(path, content):
        if path.suffix == '.json':
            raise OSError('sidecar publication failed')
        original(path, content)
    with patch.object(RawStore, '_publish', side_effect=publish):
        result = process(tr, raw_store=tmp_raw_store)
    assert result.content == tr.content and result.raw_ref is None
    assert result.persistence == Persistence.PERSIST
    assert result.audit['storage_outcome'] == 'FAILED_MAY_HAVE_BLOB'
    assert tmp_raw_store.exists(result.raw_sha256)
