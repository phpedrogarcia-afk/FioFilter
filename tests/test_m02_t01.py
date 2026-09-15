"""Independent visible reconstruction and strict marker/boundary tests."""
import random
import pytest
from fiofilter.engine import process
from fiofilter.transforms.t01_dup_fold import DuplicateLineFold, decode_visible
from fiofilter.types import Disposition, ToolResult


def test_t01_count_boundaries_line_endings_and_tail():
    for ending in (b'\n', b'\r\n'):
        a = 'mecânica ├── 🔬 '.encode() + b'x' * 80 + ending
        raw = a * 4 + b'unique' + ending + a * 7 + b'last without newline'
        output = DuplicateLineFold().apply(raw)
        assert output is not None
        assert b'count=4 first=1 last=4' in output
        assert b'count=7 first=6 last=12' in output
        assert a in output and output.endswith(b'last without newline')
        assert decode_visible(output) == raw


def test_t01_rejects_marker_collisions_and_unsafe_controls():
    for line in (b'[[FIOFILTER:T01:v2]]\n', b'literal [[FIOFILTER:count=2]]\n',
                 b'spinner\r', b'\x00\n', b'\xff\n', b'\x1b[31mline\n'):
        assert DuplicateLineFold().apply(line * 100) is None
    assert DuplicateLineFold().apply(b'a\na\n') is None


def test_t01_seeded_roundtrips_and_no_expansion():
    rng = random.Random(20260915)
    fired = 0
    for _ in range(200):
        parts = []
        for _ in range(rng.randrange(1, 12)):
            line = rng.choice([b'abc', b'x' * 120, '├── café\u2028literal'.encode(), b''])
            line += rng.choice([b'\n', b'\r\n'])
            parts.append(line * rng.randrange(1, 40))
        raw = b''.join(parts) + rng.choice([b'', b'tail'])
        out = DuplicateLineFold().apply(raw)
        assert out == DuplicateLineFold().apply(raw)
        if out is not None:
            fired += 1
            assert len(out) < len(raw)
            assert decode_visible(out, len(raw)) == raw
    assert fired > 100  # RAW-everything cannot satisfy this test.


def test_decoder_rejects_tampering_and_expansion_bombs():
    output = DuplicateLineFold().apply(b'x' * 100 + b'\n' + (b'x' * 100 + b'\n') * 9)
    for corrupt in (output.replace(b'count=10', b'count=0'),
                    output.replace(b'first=1', b'first=2'),
                    output.replace(b'last=10', b'last=11'),
                    b'no header', output.replace(b'count=10', b'count=999999999')):
        with pytest.raises(ValueError):
            decode_visible(corrupt, max_output_bytes=2000)


def test_inline_required_repeated_fact_blocks_folding(tmp_raw_store):
    raw = b'Building... [   OK   ]\n' * 100
    result = process(ToolResult(raw, inline_required_facts=['Building... [   OK   ]\n']),
                     raw_store=tmp_raw_store)
    assert result.content == raw
    assert result.disposition != Disposition.TRANSFORM
